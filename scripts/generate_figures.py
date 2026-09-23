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
        "font.size": 9,
        "axes.labelsize": 9,
        "axes.titlesize": 10,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "figure.titlesize": 10,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)

output_dir = os.path.join(os.path.dirname(__file__), "..", "figures")
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
        "GPU",
        "Screen W",
        "Screen H",
        "Platform",
        "Language",
        "Timezone",
        "local_fp",
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

    x = np.arange(len(signals))
    width = 0.34
    fig, ax = plt.subplots(figsize=(6.8, 2.9), dpi=300)
    ax.bar(
        x - 0.5 * width,
        chromium,
        width,
        label="Chromium (Chrome+Edge)",
        color="#1f77b4",
        edgecolor="black",
        linewidth=0.5,
    )
    ax.bar(
        x + 0.5 * width,
        firefox,
        width,
        label="Firefox",
        color="#ff7f0e",
        edgecolor="black",
        linewidth=0.5,
    )
    ax.set_ylabel("Within-physical Consistency (%)")
    ax.set_ylim(0, 110)
    ax.set_xticks(x)
    ax.set_xticklabels(signals, rotation=15, ha="right")
    ax.legend(loc="lower left", frameon=True, fontsize=7)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    path = os.path.join(output_dir, "stability-chart.pdf")
    plt.savefig(path, format="pdf", bbox_inches="tight")
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

    # The replay evaluates three discrete thresholds. Separate panels make both
    # outcomes readable without implying a continuous relationship between them.
    x = np.arange(len(thresholds))
    fig, axes = plt.subplots(1, 2, figsize=(6.8, 2.35), dpi=300)
    panels = [
        (axes[0], merge_rates, "Merged labeled sessions (%)", "#1f77b4", 100),
        (axes[1], new_rates, "New assignments (%)", "#c44e52", 0.7),
    ]
    for ax, values, ylabel, color, upper in panels:
        bars = ax.bar(
            x,
            values,
            width=0.58,
            color=color,
            edgecolor="black",
            linewidth=0.5,
        )
        ax.set_ylabel(ylabel)
        ax.set_ylim(0, upper)
        ax.set_xticks(x)
        ax.set_xticklabels([f"$\\tau$={threshold:.2f}" for threshold in thresholds])
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        ax.set_axisbelow(True)
        for bar, value in zip(bars, values):
            offset = upper * 0.025
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + offset,
                f"{value:.1f}",
                ha="center",
                va="bottom",
                fontsize=7,
            )

    axes[0].set_xlabel("Fuzzy threshold")
    axes[1].set_xlabel("Fuzzy threshold")
    fig.subplots_adjust(wspace=0.42, bottom=0.22, left=0.10, right=0.98, top=0.98)
    plt.tight_layout()
    path = os.path.join(output_dir, "threshold-tradeoff.pdf")
    plt.savefig(path, format="pdf", bbox_inches="tight")
    print(f"Saved {path}")
    plt.close()


if __name__ == "__main__":
    metrics = load_metrics()
    sensitivity = load_sensitivity()
    generate_stability_chart(metrics)
    generate_threshold_tradeoff(sensitivity)
