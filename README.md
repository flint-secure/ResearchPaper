# FlintSecure research-paper reproducibility bundle

This repository contains the manuscript source, the anonymized benchmark records, and the
small analysis scripts needed to reproduce the reported results for **Evaluating Browser Signal
Stability for Device Identification: A Controlled Laboratory Study Motivated by Nepali
Mobile-Web Payments**.

It intentionally excludes the full FlintSecure application, deployment files, private research
PDFs, credentials, LaTeX intermediates, and unrelated project documentation.

## Contents

- `paper.tex`, `sections/`, and `IEEEtran.cls`: IEEE manuscript source.
- `data/benchmark_data.csv`: 9,401 anonymized session records. It retains only fields used by
  the manuscript analyses; no account, payment, or personal contact fields are included.
- `data/metrics.json`: derived stability, routing, merge, and latency metrics.
- `data/threshold_sensitivity.json`: derived fuzzy-threshold replay results.
- `scripts/aggregate_metrics.py`: recomputes `metrics.json` from the CSV.
- `scripts/threshold_replay.py`: reproduces the chronological empty-store threshold replay.
- `scripts/generate_figures.py`: regenerates the two figures used by the manuscript.
- `figures/`: vector PDF figures included by the manuscript.

The session and device identifiers in the release data are pseudonymous technical identifiers
used to preserve repeated-session and device-linkage relationships. The physical labels refer to
the controlled laboratory setup described in the paper.

## Reproduce the paper

Requirements: Python 3.11+, `matplotlib`, NumPy, and a LaTeX installation with `pdflatex`.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
make reproduce
```

The commands recompute the metrics and threshold replay, regenerate the figures, and build
`paper.pdf`. To run individual stages:

```bash
make metrics
make replay
make figures
make pdf
```

The threshold replay is a deterministic implementation of the exact-match, stored-ID recovery,
and blocked fuzzy-matching paths used for the reported sensitivity analysis. Its output should
reproduce the published values: merge-affected labeled sessions of 82.5%, 58.2%, and 58.2% at
thresholds 0.70, 0.80, and 0.85, respectively.
