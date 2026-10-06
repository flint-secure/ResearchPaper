# FlintSecure research-paper reproducibility bundle

This repository contains the anonymized benchmark records and analysis scripts needed to reproduce the reported results for **Evaluating Browser Signal Stability for Device Identification: A Controlled Laboratory Study Motivated by Nepali Mobile-Web Payments**.

The manuscript source and paper PDF are maintained separately from this public repository.
This repository also excludes the full FlintSecure application, deployment files, private research PDFs, credentials, and unrelated project documentation.

## Contents

- `data/benchmark_data.csv`: 9,401 anonymized session records.
  It retains only fields used by the manuscript analyses; no account, payment, or personal contact fields are included.
- `data/metrics.json`: derived stability, routing, device/session merge metrics, baseline
  observation spans, and pooled, per-device/engine, and device-balanced latency summaries.
- `data/threshold_sensitivity.json`: derived results for 25 fuzzy-threshold replays.
- `data/weight_sensitivity.json`: six scoring configurations replayed at a fixed cutoff.
- `scripts/aggregate_metrics.py`: recomputes `metrics.json` from the CSV.
- `scripts/threshold_replay.py`: reproduces chronological empty-store threshold and weight comparisons.
- `scripts/generate_figures.py`: generates two vector PDF plots from the derived results.
  Generated plots are written to the Git-ignored `.check/manuscript/figures/` directory.

The session and device identifiers in the release data are pseudonymous technical identifiers used to preserve repeated-session and device-linkage relationships.
The physical labels refer to the controlled laboratory setup described in the paper.

## Reproduce the results

Requirements: Python 3.11+, `matplotlib`, and NumPy.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
make reproduce
```

The commands recompute the metrics and both sensitivity analyses and generate plots locally.
To run individual stages:

```bash
make metrics
make replay
make figures
```

The replay is a deterministic implementation of the exact-match, stored-ID recovery, and blocked fuzzy-matching paths used for the sensitivity analyses.
The default threshold sweep covers 0.70 through 0.90 in 0.01 increments, with additional refinements at 0.705, 0.709, 0.7096, and 0.7097.
Merge-affected labeled-session coverage changes from 82.5% at 0.7096 to 58.2% at 0.7097, while affected physical-device involvement remains 17/24 (70.8%) at every tested cutoff.
The replay yields 31/9,401 new assignments (0.33%) at 0.70 and 50/9,401 (0.53%) at 0.7097 and every tested cutoff through 0.90.
Rates are derived from the raw counts; new-assignment percentages are rounded to two decimals.

The same command also writes `weight_sensitivity.json`, comparing the configured and equal weights and omission of each of the four transmitted fields at a fixed threshold of 0.70.
Platform/screen-width candidate blocking stays fixed even when either scoring contribution is omitted.
For custom runs, use `--thresholds`, `--weight-threshold`, `--out`, and `--weights-out`.
These are exploratory counterfactual replays of the released cohort, not independently validated calibration.

The stability and collection measurements concern the inline benchmark collectors, not the packaged SDK.
The labeled baseline device/engine groups span at most 3.58 minutes, so they do not establish multi-day natural drift or actual browser-update/private-mode behavior.
