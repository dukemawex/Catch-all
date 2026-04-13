"""
src/visualize.py

Plotting helpers for the mechinterp-phishing-probe experiments.

All functions accept a ``save_path`` keyword argument; when provided the
figure is persisted to disk as a .png file (suitable for README embedding).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import seaborn as sns

# ---------------------------------------------------------------------------
# Global style defaults
# ---------------------------------------------------------------------------

PALETTE_BENIGN = "#4C9BE8"    # calming blue  → benign
PALETTE_PHISHING = "#E84C4C"  # alert red     → phishing
FIGURE_DPI = 150
FIGURE_STYLE = "whitegrid"


def _save_or_show(fig: plt.Figure, save_path: Optional[Union[str, Path]]) -> None:
    """Save *fig* to *save_path* (creating parent dirs) or display inline."""
    if save_path is not None:
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=FIGURE_DPI, bbox_inches="tight")
        print(f"Figure saved → {save_path}")
    plt.show()


# ---------------------------------------------------------------------------
# Attention heatmaps
# ---------------------------------------------------------------------------

def plot_attention_head_comparison(
    attn_benign: np.ndarray,
    attn_phishing: np.ndarray,
    layer_idx: int,
    head_idx: int,
    token_labels_benign: Optional[List[str]] = None,
    token_labels_phishing: Optional[List[str]] = None,
    title_prefix: str = "",
    save_path: Optional[Union[str, Path]] = None,
) -> None:
    """
    Plot benign vs. phishing attention patterns side-by-side for a single head.

    Parameters
    ----------
    attn_benign : np.ndarray, shape (n_layers, n_heads, seq_len_b, seq_len_b)
    attn_phishing : np.ndarray, shape (n_layers, n_heads, seq_len_p, seq_len_p)
    layer_idx, head_idx : int
    token_labels_* : list of str, optional
        Token strings to label axes.
    title_prefix : str
        Optional prefix for the suptitle (e.g. "Pair 3 — False Urgency").
    save_path : path-like, optional
    """
    sns.set_style(FIGURE_STYLE)

    pattern_benign = attn_benign[layer_idx, head_idx]     # (seq_len_b, seq_len_b)
    pattern_phishing = attn_phishing[layer_idx, head_idx]  # (seq_len_p, seq_len_p)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    for ax, pattern, labels, colour, label_text in zip(
        axes,
        [pattern_benign, pattern_phishing],
        [token_labels_benign, token_labels_phishing],
        [PALETTE_BENIGN, PALETTE_PHISHING],
        ["Benign", "Phishing"],
    ):
        cmap = sns.light_palette(colour, as_cmap=True)
        xticklabels = labels if labels is not None else False
        yticklabels = labels if labels is not None else False
        sns.heatmap(
            pattern,
            ax=ax,
            cmap=cmap,
            vmin=0,
            vmax=1,
            xticklabels=xticklabels,
            yticklabels=yticklabels,
            cbar_kws={"shrink": 0.8},
        )
        ax.set_title(f"{label_text}", fontsize=13, fontweight="bold", color=colour)
        ax.set_xlabel("Source token", fontsize=10)
        ax.set_ylabel("Destination token", fontsize=10)
        if labels is not None:
            ax.tick_params(axis="x", rotation=45, labelsize=8)
            ax.tick_params(axis="y", rotation=0, labelsize=8)

    head_label = f"L{layer_idx}.H{head_idx}"
    suptitle = (
        f"{title_prefix} | Attention Pattern — {head_label}"
        if title_prefix
        else f"Attention Pattern — {head_label}"
    )
    fig.suptitle(suptitle, fontsize=14, y=1.02)
    plt.tight_layout()
    _save_or_show(fig, save_path)


# ---------------------------------------------------------------------------
# Residual stream divergence curve
# ---------------------------------------------------------------------------

def plot_divergence_curve(
    divergence_curve: np.ndarray,
    pair_index: int,
    tactic: str = "",
    save_path: Optional[Union[str, Path]] = None,
) -> None:
    """
    Plot the per-layer L2 divergence between benign and phishing residual streams.

    Parameters
    ----------
    divergence_curve : np.ndarray, shape (n_layers,)
    pair_index : int
    tactic : str
        Human-readable tactic name for the subtitle.
    save_path : path-like, optional
    """
    sns.set_style(FIGURE_STYLE)
    n_layers = len(divergence_curve)
    layers = list(range(n_layers))

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(layers, divergence_curve, marker="o", color=PALETTE_PHISHING, linewidth=2)
    ax.fill_between(layers, divergence_curve, alpha=0.15, color=PALETTE_PHISHING)
    ax.set_xlabel("Layer", fontsize=12)
    ax.set_ylabel("Mean L2 distance", fontsize=12)
    ax.set_title(
        f"Residual Stream Divergence — Pair {pair_index}"
        + (f" ({tactic})" if tactic else ""),
        fontsize=13,
    )
    ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
    ax.grid(axis="x", alpha=0.3)
    plt.tight_layout()
    _save_or_show(fig, save_path)


# ---------------------------------------------------------------------------
# Aggregate head divergence heatmap
# ---------------------------------------------------------------------------

def plot_head_divergence_heatmap(
    head_divergence_matrix: np.ndarray,
    top_heads: Optional[List[Tuple[int, int, float]]] = None,
    save_path: Optional[Union[str, Path]] = None,
) -> None:
    """
    Plot a (n_layers × n_heads) heatmap of mean attention divergence scores.

    Parameters
    ----------
    head_divergence_matrix : np.ndarray, shape (n_layers, n_heads)
    top_heads : list of (layer, head, score), optional
        Top-k heads to annotate with star markers.
    save_path : path-like, optional
    """
    sns.set_style(FIGURE_STYLE)
    n_layers, n_heads = head_divergence_matrix.shape

    fig, ax = plt.subplots(figsize=(12, 6))
    sns.heatmap(
        head_divergence_matrix,
        ax=ax,
        cmap="YlOrRd",
        annot=True,
        fmt=".3f",
        linewidths=0.4,
        cbar_kws={"label": "Mean absolute attention difference"},
    )
    ax.set_xlabel("Attention head", fontsize=12)
    ax.set_ylabel("Layer", fontsize=12)
    ax.set_title(
        "Attention Head Divergence: Phishing vs. Benign (aggregate across pairs)",
        fontsize=13,
    )

    if top_heads:
        for layer_idx, head_idx, _ in top_heads:
            ax.add_patch(
                plt.Rectangle(
                    (head_idx, layer_idx),
                    1,
                    1,
                    fill=False,
                    edgecolor="blue",
                    lw=2.5,
                )
            )

    plt.tight_layout()
    _save_or_show(fig, save_path)


# ---------------------------------------------------------------------------
# Activation patching heatmap
# ---------------------------------------------------------------------------

def plot_patching_attribution(
    attribution_matrix: np.ndarray,
    token_labels: Optional[List[str]] = None,
    title: str = "Activation Patching Attribution",
    save_path: Optional[Union[str, Path]] = None,
) -> None:
    """
    Plot the (n_layers × seq_len) patching attribution heatmap.

    Parameters
    ----------
    attribution_matrix : np.ndarray, shape (n_layers, seq_len)
    token_labels : list of str, optional
    title : str
    save_path : path-like, optional
    """
    sns.set_style(FIGURE_STYLE)

    fig, ax = plt.subplots(figsize=(max(10, attribution_matrix.shape[1] * 0.5), 6))
    xticklabels = token_labels if token_labels is not None else True
    sns.heatmap(
        attribution_matrix,
        ax=ax,
        cmap="magma",
        xticklabels=xticklabels,
        yticklabels=True,
        cbar_kws={"label": "|Δ logit diff| after patch"},
    )
    ax.set_xlabel("Token position", fontsize=12)
    ax.set_ylabel("Layer", fontsize=12)
    ax.set_title(title, fontsize=13)
    if token_labels is not None:
        ax.tick_params(axis="x", rotation=45, labelsize=8)
    plt.tight_layout()
    _save_or_show(fig, save_path)


# ---------------------------------------------------------------------------
# Anomaly score distribution
# ---------------------------------------------------------------------------

def plot_anomaly_score_distributions(
    benign_scores: np.ndarray,
    phishing_scores: np.ndarray,
    save_path: Optional[Union[str, Path]] = None,
) -> None:
    """
    Plot overlapping KDE distributions of Isolation Forest anomaly scores
    for benign vs. phishing residual stream vectors.

    Parameters
    ----------
    benign_scores : np.ndarray
    phishing_scores : np.ndarray
    save_path : path-like, optional
    """
    sns.set_style(FIGURE_STYLE)

    fig, ax = plt.subplots(figsize=(8, 4))
    sns.kdeplot(benign_scores, ax=ax, fill=True, alpha=0.4,
                color=PALETTE_BENIGN, label="Benign")
    sns.kdeplot(phishing_scores, ax=ax, fill=True, alpha=0.4,
                color=PALETTE_PHISHING, label="Phishing")
    ax.axvline(0, color="gray", linestyle="--", linewidth=1, label="Decision boundary")
    ax.set_xlabel("Isolation Forest anomaly score", fontsize=12)
    ax.set_ylabel("Density", fontsize=12)
    ax.set_title(
        "Anomaly Score Distribution: Benign vs. Phishing Residual Streams",
        fontsize=13,
    )
    ax.legend()
    plt.tight_layout()
    _save_or_show(fig, save_path)


# ---------------------------------------------------------------------------
# SAE feature bar chart
# ---------------------------------------------------------------------------

def plot_sae_phishing_features(
    feature_indices: List[int],
    mean_activations_phishing: np.ndarray,
    mean_activations_benign: np.ndarray,
    feature_labels: Optional[List[str]] = None,
    top_k: int = 15,
    save_path: Optional[Union[str, Path]] = None,
) -> None:
    """
    Bar chart comparing mean SAE feature activations for phishing vs. benign prompts.

    Parameters
    ----------
    feature_indices : list of int
        SAE feature indices to display (should be the phishing-specific features).
    mean_activations_phishing : np.ndarray, shape (n_features,)
    mean_activations_benign : np.ndarray, shape (n_features,)
    feature_labels : list of str, optional
        Human-readable semantic labels for each feature.
    top_k : int
        Number of top features to display.
    save_path : path-like, optional
    """
    sns.set_style(FIGURE_STYLE)

    n_to_show = min(top_k, len(feature_indices))
    indices_to_show = feature_indices[:n_to_show]

    phishing_vals = mean_activations_phishing[:n_to_show]
    benign_vals = mean_activations_benign[:n_to_show]

    if feature_labels is not None:
        x_labels = [f"F{idx}\n{feature_labels[i]}" for i, idx in enumerate(indices_to_show)]
    else:
        x_labels = [f"Feature {idx}" for idx in indices_to_show]

    x = np.arange(n_to_show)
    width = 0.38

    fig, ax = plt.subplots(figsize=(max(12, n_to_show * 0.9), 5))
    ax.bar(x - width / 2, phishing_vals, width, label="Phishing",
           color=PALETTE_PHISHING, alpha=0.85)
    ax.bar(x + width / 2, benign_vals, width, label="Benign",
           color=PALETTE_BENIGN, alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, fontsize=8, rotation=30, ha="right")
    ax.set_ylabel("Mean SAE feature activation", fontsize=12)
    ax.set_title(
        f"Top-{n_to_show} Phishing-Specific SAE Features "
        "(layer 8 residual stream)",
        fontsize=13,
    )
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    _save_or_show(fig, save_path)


# ---------------------------------------------------------------------------
# Ranked anomaly table (text helper)
# ---------------------------------------------------------------------------

def print_ranked_anomaly_table(
    attribution_matrix: np.ndarray,
    token_labels: Optional[List[str]] = None,
    top_k: int = 10,
) -> None:
    """
    Print a ranked table of (layer, token_position, attribution_score) for the
    top-k entries in *attribution_matrix*.

    Parameters
    ----------
    attribution_matrix : np.ndarray, shape (n_layers, seq_len)
    token_labels : list of str, optional
    top_k : int
    """
    flat = attribution_matrix.flatten()
    top_flat_indices = np.argsort(flat)[::-1][:top_k]
    n_positions = attribution_matrix.shape[1]

    header = f"{'Rank':<6}{'Layer':<8}{'Position':<12}{'Token':<20}{'Attribution':>12}"
    print(header)
    print("-" * len(header))

    for rank, flat_idx in enumerate(top_flat_indices, start=1):
        layer_idx = int(flat_idx // n_positions)
        pos = int(flat_idx % n_positions)
        score = float(attribution_matrix[layer_idx, pos])
        token_str = (
            token_labels[pos] if token_labels is not None and pos < len(token_labels)
            else str(pos)
        )
        print(f"{rank:<6}{layer_idx:<8}{pos:<12}{repr(token_str):<20}{score:>12.5f}")
