#!/usr/bin/env python3
"""Generate the figures used by the paper from the checked-in result JSON files."""

import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "Liberation Serif", "DejaVu Serif"],
        "font.size": 8,
        "axes.labelsize": 8,
        "axes.titlesize": 8,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "figure.titlesize": 8,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)

output_dir = str(Path(__file__).resolve().parents[1] / ".check" / "manuscript" / "figures")
metrics_path = Path(__file__).resolve().parents[1] / "data" / "metrics.json"
sensitivity_path = (
    Path(__file__).resolve().parents[1] / "data" / "threshold_sensitivity.json"
)
os.makedirs(output_dir, exist_ok=True)


def load_metrics():
    if metrics_path.exists():
        return json.loads(metrics_path.read_text(encoding="utf-8"))
    return None


def load_sensitivity():
    if sensitivity_path.exists():
        return json.loads(sensitivity_path.read_text(encoding="utf-8"))
    return None


def generate_stability_chart(metrics=None):
    signals = [
        "Canvas",
        "GPU renderer",
        "Screen width",
        "Screen height",
        "Platform",
        "Language",
        "Time zone",
        "Composite hash",
    ]
    keys = [
        "canvas_hash",
        "gpu_renderer",
        "screen_width",
        "screen_height",
        "platform_string",
        "language_code",
        "timezone_id",
        "local_fp",
    ]
    if metrics:
        stab = metrics["stability_physical_baseline"]
        chromium = [stab["Chromium"]["rates"][k] for k in keys]
        firefox = [stab["Firefox"]["rates"][k] for k in keys]
    else:
        chromium = [96.6, 97.7, 100.0, 100.0, 100.0, 100.0, 100.0, 95.5]
        firefox = [92.1, 97.1, 100.0, 100.0, 100.0, 100.0, 100.0, 92.1]

    y = np.arange(len(signals))
    width = 0.34
    fig, ax = plt.subplots(figsize=(3.45, 2.75), dpi=300, constrained_layout=True)
    ax.barh(
        y - 0.5 * width,
        chromium,
        width,
        label="Chromium",
        color="#0072B2",
        edgecolor="black",
        linewidth=0.5,
    )
    ax.barh(
        y + 0.5 * width,
        firefox,
        width,
        label="Firefox",
        color="#D55E00",
        hatch="///",
        edgecolor="black",
        linewidth=0.5,
    )
    ax.set_xlabel("Signal consistency (%)")
    ax.set_xlim(0, 105)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_yticks(y)
    ax.set_yticklabels(signals)
    ax.set_ylim(len(signals) - 0.5, -1.6)
    ax.legend(loc="upper left", ncol=2, frameon=False, fontsize=8,
              handlelength=1.1, columnspacing=0.8)
    ax.set_axisbelow(True)
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    path = os.path.join(output_dir, "stability-chart.pdf")
    plt.savefig(path, format="pdf")
    print(f"Saved {path}")
    plt.close()


def generate_threshold_tradeoff(sensitivity=None):
    if sensitivity and sensitivity.get("thresholds"):
        rows = sensitivity["thresholds"]
        thresholds = [r["threshold"] for r in rows]
        merge_rates = [r["merge_session_rate_pct"] for r in rows]
        new_rates = [r["new_assignment_rate_pct"] for r in rows]
    else:
        thresholds = [0.70, 0.80, 0.85]
        merge_rates = [82.5, 58.2, 58.2]
        new_rates = [0.3, 0.5, 0.5]

    # Markers are evaluated replays; dashed segments only guide the eye.
    fig, axes = plt.subplots(2, 1, figsize=(3.45, 2.8), dpi=300,
                             sharex=True, constrained_layout=True)
    axes[0].plot(thresholds, merge_rates, "o--", markersize=3,
                 linewidth=0.9, label="Labeled sessions", color="#0072B2")
    if sensitivity and "device_involvement_rate_pct" in rows[0]:
        device_rates = [row["device_involvement_rate_pct"] for row in rows]
        axes[0].plot(thresholds, device_rates, "s--", markersize=3,
                     linewidth=0.9, label="Physical devices", color="#D55E00")
    axes[0].set_title("(a) Merge involvement", loc="left", fontsize=8)
    axes[0].set_ylabel("Affected (%)", fontsize=8)
    axes[0].set_ylim(0, 100)
    axes[0].legend(loc="lower left", fontsize=8)
    axes[1].plot(thresholds, new_rates, "o--", markersize=3,
                 linewidth=0.9, color="#0072B2")
    axes[1].set_title("(b) New assignments", loc="left", fontsize=8)
    axes[1].set_ylabel("Sessions (%)", fontsize=8)
    axes[1].set_ylim(0, max(0.7, max(new_rates) * 1.2))
    axes[1].set_xlabel("Fuzzy threshold", fontsize=8)
    axes[1].set_xticks(np.arange(0.70, 0.901, 0.05))
    for ax in axes:
        ax.tick_params(labelsize=8)
        ax.grid(linestyle=":", alpha=0.4)
    path = os.path.join(output_dir, "threshold-tradeoff.pdf")
    plt.savefig(path, format="pdf")
    print(f"Saved {path}")
    plt.close()


if __name__ == "__main__":
    metrics = load_metrics()
    sensitivity = load_sensitivity()
    generate_stability_chart(metrics)
    generate_threshold_tradeoff(sensitivity)
