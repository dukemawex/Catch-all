# mechinterp-phishing-probe
## Mechanistic Interpretability for Social Engineering Detection

> **Applying circuit-level analysis to find "malicious intent" in language model activations — before the output is generated.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![TransformerLens](https://img.shields.io/badge/TransformerLens-1.19+-green.svg)](https://github.com/neelnanda-io/TransformerLens)
[![SAELens](https://img.shields.io/badge/SAELens-3.0+-orange.svg)](https://github.com/jbloomAus/SAELens)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Motivation

In October 2023, attackers used a voice-phishing (vishing) social engineering attack to gain access to MGM Resorts' IT infrastructure, causing an estimated $100 million in damages. The attack succeeded not because defences lacked technical sophistication, but because the attacker's language was fluent, authoritative, and designed to trigger fast, unquestioning action.

This is **Linguistic Dissonance** in action — a term from Teger AI's social engineering research framework that describes the semantic gap between a message's stated professional context and its coercive, high-urgency demands. A CEO impersonation email that reads *"Wire $87,500 immediately, do not loop in Legal"* exploits exactly this gap.

Large language models encode rich representations of language, including register, authority, and urgency. **This repository asks: are those representations interpretable? Can we locate, in the model's internal activations, the features that encode social-engineering intent — and detect them before any output is generated?**

This project is a research portfolio piece supporting an AI safety fellowship application, demonstrating practical mechanistic interpretability skills applied to a real-world threat model.

---

## Research Questions

- **RQ1 — Localisation:** Which attention heads and residual stream layers in GPT-2 Small most strongly differentiate benign from phishing email prompts? Is this differentiation concentrated in specific circuits or diffuse across the network?
- **RQ2 — Causality:** Does activation patching confirm that identified circuits *causally* encode social-engineering intent, or are they merely correlated? At which layer does patching produce the largest logit shift?
- **RQ3 — Decomposability:** Can a pretrained Sparse Autoencoder (SAE) trained on GPT-2 Small's residual stream decompose phishing activations into a small, interpretable *phishing feature set* — analogous to Indicators of Compromise in traditional cybersecurity?

---

## Repository Structure

```
mechinterp-phishing-probe/
├── README.md
├── requirements.txt
├── data/
│   └── prompts.py              # 10 curated phishing/benign prompt pairs
├── figures/                    # Auto-generated .png outputs from notebooks
├── notebooks/
│   ├── 01_transformerlens_exploration.ipynb
│   ├── 02_activation_patching.ipynb
│   └── 03_sae_feature_analysis.ipynb
└── src/
    ├── probe_utils.py          # Shared activation-extraction and patching utilities
    └── visualize.py            # Publication-quality plotting helpers
```

---

## Methodology Overview

### Notebook 1 — TransformerLens Exploratory Analysis

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/dukemawex/Catch-all/blob/main/notebooks/01_transformerlens_exploration.ipynb)

Using the `HookedTransformer` API from TransformerLens, we run all 10 phishing/benign prompt pairs through GPT-2 Small and cache every intermediate activation. For each pair we visualise attention patterns side-by-side (benign vs. phishing), compute per-layer residual stream L2 divergence, and aggregate (layer, head) attention divergence scores across all pairs to identify the top-3 most discriminative attention heads. Markdown cells frame findings in terms of *residual stream*, *attention circuits*, and *activation space* — the vocabulary of mechanistic interpretability research.

### Notebook 2 — Activation Patching

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/dukemawex/Catch-all/blob/main/notebooks/02_activation_patching.ipynb)

We apply causal activation patching to the three most divergent prompt pairs. For each pair, we systematically replace the residual stream of the benign (clean) run at every (layer, token-position) pair with the corresponding activation from the phishing (corrupt) run, measuring the resulting shift in the model's logit distribution. The resulting attribution matrix identifies the **social engineering signal layer** — the locus in GPT-2 Small's residual stream where phishing intent is most causally encoded. We also run an Isolation Forest on mean-pooled residual stream vectors, demonstrating unsupervised separation of the phishing activation distribution from the benign baseline. Together these results constitute a proof-of-concept for *latent-space evals*.

### Notebook 3 — SAE Feature Analysis

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/dukemawex/Catch-all/blob/main/notebooks/03_sae_feature_analysis.ipynb)

Using the SAELens library, we load a pretrained Sparse Autoencoder trained on GPT-2 Small's layer-8 residual stream (`blocks.8.hook_resid_post`). We encode all prompts through the SAE and identify the *phishing feature set*: SAE features with ≥2× higher mean activation on phishing prompts than benign. We assign semantic labels (urgency words, authority nouns, financial action verbs) to each phishing feature and visualise their co-activation structure. The analysis frames sparse interpretable features as *latent-space Indicators of Compromise (IoCs)* — directly bridging mechanistic interpretability with applied cybersecurity threat modelling.

---

## Key Findings

> See notebooks for full quantitative results.

Preliminary findings (GPT-2 Small, 10 prompt pairs):

- Residual stream divergence increases sharply after layers 4–6, suggesting social-engineering signals are amplified by mid-network circuits.
- A small number of (layer, head) pairs (approximately 3–5 out of 144) account for a disproportionate share of the attention divergence between benign and phishing prompts.
- Activation patching identifies a single "social engineering signal layer" where replacing activations produces the largest logit shift toward phishing-associated tokens.
- The Isolation Forest separates phishing residual vectors from benign vectors with consistent anomaly score differences.
- The pretrained SAE at layer 8 isolates a compact phishing feature set (<5% of total features), labellable into interpretable semantic categories.

---

## Connection to AI Safety

This project connects to several active AI safety research threads:

**Latent-space evals.** The standard approach to LLM safety evaluation examines model *outputs*. Latent-space evals — evaluating model *activations* rather than generations — offer the possibility of detecting harmful intent *before* it reaches the output distribution. The activation patching results in Notebook 2 provide a mechanistic grounding for this approach.

**Superposition and dictionary learning.** Elhage et al. (2022) showed that transformer models represent many more features than their dimensionality naively allows, using *superposition*. Sparse Autoencoders (Cunningham et al., 2023) decompose these superposed representations into interpretable sparse features. Notebook 3 applies this decomposition to the threat detection domain, demonstrating that phishing-specific features can be isolated and labelled without supervision.

**Circuit-level understanding.** Wang et al. (2022) demonstrated that specific, reusable circuits in GPT-2 Small mediate indirect object identification. Our attention-head divergence and patching results are consistent with the hypothesis that a similarly structured *social engineering circuit* exists in the model — a sub-network that differentially processes urgency, authority, and threat language.

**Representation engineering.** Zou et al. (2023) showed that high-level behavioural properties (honesty, harmlessness) are linearly encoded in the residual stream and can be manipulated via targeted steering vectors. Our phishing feature set is a step toward defining such a steering direction for social-engineering resistance.

---

## Setup & Usage

### Requirements

```bash
pip install -r requirements.txt
```

### Running locally

```bash
jupyter notebook notebooks/
```

### Running on Colab (recommended)

Click the Colab badge at the top of each notebook. All notebooks include `!pip install` cells and are tested on Colab free-tier with a T4 GPU.

### Data

The prompt pairs are defined in `data/prompts.py` as `PROMPT_PAIRS` — a list of dicts with `"benign"`, `"phishing"`, and `"tactic"` keys. Extend or replace this list to test on your own prompt sets.

---

## References

- **Elhage et al. (2022).** *A Mathematical Framework for Transformer Circuits.* Transformer Circuits Thread. https://transformer-circuits.pub/2021/framework/index.html
- **Elhage et al. (2022).** *Toy Models of Superposition.* Transformer Circuits Thread. https://transformer-circuits.pub/2022/toy_model/index.html
- **Wang et al. (2022).** *Interpretability in the Wild: a Circuit for Indirect Object Identification in GPT-2.* arXiv:2211.00593.
- **Cunningham et al. (2023).** *Sparse Autoencoders Find Highly Interpretable Features in Language Models.* arXiv:2309.08600.
- **Nanda & Chan (2022).** *TransformerLens: A library for mechanistic interpretability of GPT-style language models.* https://github.com/neelnanda-io/TransformerLens
- **Zou et al. (2023).** *Representation Engineering: A Top-Down Approach to AI Transparency.* arXiv:2310.01405.
- **Conmy et al. (2023).** *Towards Automated Circuit Discovery for Mechanistic Interpretability.* arXiv:2304.14997.
- **Bloom (2024).** *SAELens: Training and Analysing Sparse Autoencoders on Language Models.* https://github.com/jbloomAus/SAELens
