"""
src/probe_utils.py

Shared utilities for the mechinterp-phishing-probe experiments.

Provides helpers for:
  - Tokenising prompts with TransformerLens
  - Extracting and comparing residual stream activations across layers
  - Computing attention-head divergence scores between prompt pairs
  - Performing activation patching via the TransformerLens hooks API
  - Running Isolation Forest anomaly detection on residual stream vectors
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
from sklearn.ensemble import IsolationForest

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
FIGURES_DIR = REPO_ROOT / "figures"
FIGURES_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Activation extraction
# ---------------------------------------------------------------------------

def run_and_cache(
    model,
    prompt: str,
    device: str = "cpu",
) -> Tuple[torch.Tensor, dict]:
    """
    Run *prompt* through *model* and return ``(logits, cache)``.

    Parameters
    ----------
    model : HookedTransformer
        A TransformerLens ``HookedTransformer`` instance.
    prompt : str
        The raw text prompt to process.
    device : str
        Target torch device (``"cpu"`` or ``"cuda"``).

    Returns
    -------
    logits : torch.Tensor, shape (1, seq_len, vocab_size)
    cache : transformer_lens.ActivationCache
        Full activation cache as returned by ``model.run_with_cache()``.
    """
    tokens = model.to_tokens(prompt).to(device)
    logits, cache = model.run_with_cache(tokens)
    return logits, cache


def extract_residual_stream(
    cache,
    n_layers: int = 12,
) -> np.ndarray:
    """
    Extract the residual stream at every layer's post-attention hook.

    Parameters
    ----------
    cache : transformer_lens.ActivationCache
    n_layers : int
        Number of transformer layers (12 for GPT-2 Small).

    Returns
    -------
    residual_array : np.ndarray, shape (n_layers, seq_len, d_model)
        Residual stream activations for each layer.
    """
    residual_stream_layers = []
    for layer_idx in range(n_layers):
        hook_name = f"blocks.{layer_idx}.hook_resid_post"
        # shape: (1, seq_len, d_model)
        activation = cache[hook_name].squeeze(0).detach().cpu().numpy()
        residual_stream_layers.append(activation)
    return np.stack(residual_stream_layers, axis=0)  # (n_layers, seq_len, d_model)


def extract_attention_patterns(
    cache,
    n_layers: int = 12,
    n_heads: int = 12,
) -> np.ndarray:
    """
    Extract attention patterns from all layers.

    Parameters
    ----------
    cache : transformer_lens.ActivationCache
    n_layers : int
    n_heads : int

    Returns
    -------
    attention_array : np.ndarray, shape (n_layers, n_heads, seq_len, seq_len)
    """
    attn_layers = []
    for layer_idx in range(n_layers):
        hook_name = f"blocks.{layer_idx}.attn.hook_pattern"
        # shape: (1, n_heads, seq_len, seq_len)
        pattern = cache[hook_name].squeeze(0).detach().cpu().numpy()
        attn_layers.append(pattern)
    return np.stack(attn_layers, axis=0)  # (n_layers, n_heads, seq_len, seq_len)


# ---------------------------------------------------------------------------
# Divergence metrics
# ---------------------------------------------------------------------------

def compute_residual_stream_l2_divergence(
    residual_benign: np.ndarray,
    residual_phishing: np.ndarray,
) -> np.ndarray:
    """
    Compute the mean L2 distance between benign and phishing residual streams
    at each layer, averaged over the *shared* sequence prefix.

    Both arrays must have shape ``(n_layers, seq_len, d_model)``.  When the
    sequence lengths differ the shorter length is used for the comparison.

    Parameters
    ----------
    residual_benign : np.ndarray, shape (n_layers, seq_len_b, d_model)
    residual_phishing : np.ndarray, shape (n_layers, seq_len_p, d_model)

    Returns
    -------
    divergence_curve : np.ndarray, shape (n_layers,)
        Mean L2 distance per layer.
    """
    n_layers = residual_benign.shape[0]
    min_seq_len = min(residual_benign.shape[1], residual_phishing.shape[1])
    divergence_curve = np.zeros(n_layers)
    for layer_idx in range(n_layers):
        diff = (
            residual_benign[layer_idx, :min_seq_len, :]
            - residual_phishing[layer_idx, :min_seq_len, :]
        )
        # L2 norm per token, then mean over tokens
        divergence_curve[layer_idx] = float(np.linalg.norm(diff, axis=-1).mean())
    return divergence_curve


def compute_attention_head_divergence(
    attn_benign: np.ndarray,
    attn_phishing: np.ndarray,
) -> np.ndarray:
    """
    Compute the mean absolute attention-weight difference per (layer, head) pair.

    Both arrays must have shape ``(n_layers, n_heads, seq_len, seq_len)``.
    The shorter sequence dimension is used for the comparison.

    Returns
    -------
    head_divergence : np.ndarray, shape (n_layers, n_heads)
    """
    n_layers, n_heads = attn_benign.shape[:2]
    min_seq = min(attn_benign.shape[2], attn_phishing.shape[2])
    head_divergence = np.zeros((n_layers, n_heads))
    for layer_idx in range(n_layers):
        for head_idx in range(n_heads):
            diff = np.abs(
                attn_benign[layer_idx, head_idx, :min_seq, :min_seq]
                - attn_phishing[layer_idx, head_idx, :min_seq, :min_seq]
            )
            head_divergence[layer_idx, head_idx] = float(diff.mean())
    return head_divergence


def rank_attention_heads(
    head_divergence_matrix: np.ndarray,
    top_k: int = 3,
) -> List[Tuple[int, int, float]]:
    """
    Return the top-k (layer, head) pairs sorted by divergence score.

    Parameters
    ----------
    head_divergence_matrix : np.ndarray, shape (n_layers, n_heads)
    top_k : int

    Returns
    -------
    ranked : list of (layer_idx, head_idx, score) tuples, descending by score
    """
    flat_scores = head_divergence_matrix.flatten()
    top_flat_indices = np.argsort(flat_scores)[::-1][:top_k]
    n_heads = head_divergence_matrix.shape[1]
    ranked = []
    for flat_idx in top_flat_indices:
        layer_idx = int(flat_idx // n_heads)
        head_idx = int(flat_idx % n_heads)
        score = float(head_divergence_matrix[layer_idx, head_idx])
        ranked.append((layer_idx, head_idx, score))
    return ranked


# ---------------------------------------------------------------------------
# Logit-difference helpers
# ---------------------------------------------------------------------------

def get_final_token_logits(
    logits: torch.Tensor,
    model,
    token_a: str,
    token_b: str,
) -> float:
    """
    Compute the logit difference ``logit(token_a) - logit(token_b)`` at the
    last sequence position.

    Parameters
    ----------
    logits : torch.Tensor, shape (1, seq_len, vocab_size)
    model : HookedTransformer
    token_a : str  — the "positive" token (e.g. a phishing-associated word)
    token_b : str  — the "negative" token (e.g. a benign-associated word)

    Returns
    -------
    logit_diff : float
    """
    vocab = model.tokenizer
    id_a = vocab.encode(token_a)[0]
    id_b = vocab.encode(token_b)[0]
    last_logits = logits[0, -1, :]  # (vocab_size,)
    return float(last_logits[id_a] - last_logits[id_b])


# ---------------------------------------------------------------------------
# Activation patching
# ---------------------------------------------------------------------------

def patch_residual_stream_at_layer(
    model,
    clean_tokens: torch.Tensor,
    corrupt_cache,
    layer_idx: int,
    token_positions: Optional[List[int]] = None,
    device: str = "cpu",
) -> torch.Tensor:
    """
    Patch the residual stream of *clean_tokens* at *layer_idx* using activations
    from *corrupt_cache*, then return the resulting logits.

    Parameters
    ----------
    model : HookedTransformer
    clean_tokens : torch.Tensor, shape (1, seq_len)
    corrupt_cache : transformer_lens.ActivationCache
        Activations from the corrupt (phishing) forward pass.
    layer_idx : int
        Layer at which to apply the patch.
    token_positions : list of int or None
        Positions to patch.  If ``None``, all positions are patched.
    device : str

    Returns
    -------
    patched_logits : torch.Tensor, shape (1, seq_len, vocab_size)
    """
    hook_name = f"blocks.{layer_idx}.hook_resid_post"
    corrupt_activation = corrupt_cache[hook_name].to(device)  # (1, seq_len, d_model)

    def patch_hook(activation: torch.Tensor, hook) -> torch.Tensor:
        """Replace clean activations with corrupt activations at specified positions."""
        if token_positions is None:
            activation[:, :, :] = corrupt_activation[:, : activation.shape[1], :]
        else:
            for pos in token_positions:
                if pos < activation.shape[1]:
                    activation[:, pos, :] = corrupt_activation[:, pos, :]
        return activation

    patched_logits = model.run_with_hooks(
        clean_tokens,
        fwd_hooks=[(hook_name, patch_hook)],
    )
    return patched_logits


def compute_patching_attribution_matrix(
    model,
    clean_tokens: torch.Tensor,
    corrupt_cache,
    baseline_logit_diff: float,
    n_layers: int = 12,
    device: str = "cpu",
) -> np.ndarray:
    """
    Compute a patching attribution matrix by patching each (layer, position)
    independently and measuring the change in logit difference.

    The logit difference proxy used here is the mean logit magnitude at the
    last position — a lightweight substitute when labelled positive/negative
    tokens are not available.

    Parameters
    ----------
    model : HookedTransformer
    clean_tokens : torch.Tensor
    corrupt_cache : transformer_lens.ActivationCache
    baseline_logit_diff : float
        Logit-diff on the unpatched clean run.
    n_layers : int
    device : str

    Returns
    -------
    attribution_matrix : np.ndarray, shape (n_layers, seq_len)
        Absolute change in logit diff after each single-position patch.
    """
    seq_len = clean_tokens.shape[1]
    attribution_matrix = np.zeros((n_layers, seq_len))

    for layer_idx in range(n_layers):
        for pos in range(seq_len):
            patched_logits = patch_residual_stream_at_layer(
                model=model,
                clean_tokens=clean_tokens,
                corrupt_cache=corrupt_cache,
                layer_idx=layer_idx,
                token_positions=[pos],
                device=device,
            )
            patched_logit_diff = float(
                patched_logits[0, -1, :].mean().detach().cpu()
            )
            attribution_matrix[layer_idx, pos] = abs(
                patched_logit_diff - baseline_logit_diff
            )

    return attribution_matrix


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------

def run_isolation_forest(
    phishing_residuals: np.ndarray,
    benign_residuals: np.ndarray,
    contamination: float = 0.1,
    random_state: int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Fit an Isolation Forest on *benign_residuals* and score both sets.

    The model is trained to represent the distribution of benign activations;
    phishing activations are expected to receive more negative anomaly scores.

    Parameters
    ----------
    phishing_residuals : np.ndarray, shape (n_phishing, feature_dim)
    benign_residuals : np.ndarray, shape (n_benign, feature_dim)
    contamination : float
        Expected fraction of outliers in the training data.
    random_state : int

    Returns
    -------
    benign_scores : np.ndarray, shape (n_benign,)
        Anomaly scores for benign samples (higher = more normal).
    phishing_scores : np.ndarray, shape (n_phishing,)
        Anomaly scores for phishing samples (lower = more anomalous).
    """
    iso_forest = IsolationForest(
        contamination=contamination,
        random_state=random_state,
        n_estimators=100,
    )
    iso_forest.fit(benign_residuals)
    benign_scores = iso_forest.decision_function(benign_residuals)
    phishing_scores = iso_forest.decision_function(phishing_residuals)
    return benign_scores, phishing_scores


def build_residual_feature_matrix(
    residual_array: np.ndarray,
    pooling: str = "mean",
) -> np.ndarray:
    """
    Flatten a per-layer residual stream tensor into a single feature vector
    suitable for anomaly detection.

    Parameters
    ----------
    residual_array : np.ndarray, shape (n_layers, seq_len, d_model)
    pooling : str
        ``"mean"`` averages over the sequence dimension;
        ``"last"`` takes the final token only.

    Returns
    -------
    feature_vector : np.ndarray, shape (n_layers * d_model,)
    """
    if pooling == "mean":
        pooled = residual_array.mean(axis=1)  # (n_layers, d_model)
    elif pooling == "last":
        pooled = residual_array[:, -1, :]    # (n_layers, d_model)
    else:
        raise ValueError(f"Unknown pooling strategy: {pooling!r}")
    return pooled.flatten()


# ---------------------------------------------------------------------------
# Tokenisation helpers
# ---------------------------------------------------------------------------

def get_token_strings(model, prompt: str) -> List[str]:
    """Return the list of string tokens for *prompt* under *model*'s tokeniser."""
    token_ids = model.to_tokens(prompt)[0].tolist()
    return [model.tokenizer.decode([tid]) for tid in token_ids]


def find_highest_attention_position(
    attention_patterns: np.ndarray,
    layer_idx: int,
    head_idx: int,
) -> int:
    """
    Return the source token position with the highest *total outgoing* attention
    weight for a given (layer, head) pair.

    Parameters
    ----------
    attention_patterns : np.ndarray, shape (n_layers, n_heads, seq_len, seq_len)
        attention_patterns[l, h, dest, src] = weight from src to dest.
    layer_idx : int
    head_idx : int

    Returns
    -------
    position : int
    """
    head_pattern = attention_patterns[layer_idx, head_idx]  # (seq_len, seq_len)
    # Sum attention received by each source position across all destination positions
    total_attention = head_pattern.sum(axis=0)  # (seq_len,)
    return int(np.argmax(total_attention))
