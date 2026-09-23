#!/usr/bin/env python3
"""
FlintSecure — corpus metric aggregator
--------------------------------------
Loads data/benchmark_data.csv (or --csv), normalizes LabA/LabB physical labels,
treats Chrome+Edge as Chromium, excludes Brave/Safari, and writes publication
metrics to data/metrics.json.

Usage:
  python3 scripts/aggregate_metrics.py
  python3 scripts/aggregate_metrics.py --csv data/benchmark_data.csv --print-json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics as st
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "benchmark_data.csv"
OUT_JSON = ROOT / "data" / "metrics.json"

PHYS_RE = re.compile(r"physical\s*=\s*([^;]+)", re.I)
LAB_SEAT = re.compile(
    r"^lab\s*([ab])\s*[-_]?(?:(?:chr|ed|fire|cr|edge|chrome|firefox|ff)\s*[-_]*)?(\d+)"
    r"\s*(?:[-_]*(?:chr|ed|fire|cr|edge|chrome|firefox|ff))?$",
    re.I,
)
LAB_BROWSER_SEAT = re.compile(
    r"^lab\s*([ab])\s*[-_]*(?:chr|ed|fire|cr|edge|chrome|firefox|ff)\s*[-_]*(\d+)$",
    re.I,
)

SIGNAL_FIELDS = [
    "canvas_hash",
    "gpu_renderer",
    "screen_width",
    "screen_height",
    "platform_string",
    "language_code",
    "timezone_id",
    "local_fp",
]


def engine(browser: str | None) -> str | None:
    b = (browser or "").strip().lower()
    if b in ("chrome", "edge", "chromium"):
        return "Chromium"
    if b == "firefox":
        return "Firefox"
    return None


def clean_physical(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    m = LAB_BROWSER_SEAT.match(s) or LAB_SEAT.match(s)
    if m:
        return f"Lab{m.group(1).upper()}-{int(m.group(2)):02d}"
    low = s.lower()
    if low == "macos tahoe":
        return "macOS-Tahoe"
    if low == "android neon":
        return "Android-Neon"
    return None


def physical_id(row: dict) -> str | None:
    note = (row.get("participant_note") or "").strip()
    m = PHYS_RE.search(note)
    if m:
        p = clean_physical(m.group(1).strip())
        if p:
            return p
    return clean_physical((row.get("device_label") or "").strip())


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def percentile(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(s[int(k)])
    return float(s[f] * (c - k) + s[c] * (k - f))


def load_rows(csv_path: Path):
    text = csv_path.read_text(encoding="utf-8", errors="replace")
    # Older exports used literal \n instead of real newlines.
    if text.count("\n") < 2 and "\\n" in text:
        text = text.replace("\\n", "\n")
    rows = list(csv.DictReader(text.splitlines()))
    kept = []
    for r in rows:
        eng = engine(r.get("browser"))
        if not eng:
            continue
        item = dict(r)
        item["_engine"] = eng
        item["_physical"] = physical_id(r)
        kept.append(item)
    return kept


def consistency_table(groups: dict, fields=SIGNAL_FIELDS, min_n=2):
    out = {}
    for eng in ("Chromium", "Firefox"):
        eng_groups = {k: v for k, v in groups.items() if k[1] == eng and len(v) >= min_n}
        rates = {}
        for f in fields:
            scores = []
            for rs in eng_groups.values():
                vals = [r.get(f) for r in rs]
                mode = Counter(vals).most_common(1)[0][0]
                scores.append(sum(1 for v in vals if v == mode) / len(vals))
            rates[f] = round(100 * st.mean(scores), 1) if scores else None
        out[eng] = {
            "rates": rates,
            "n_groups": len(eng_groups),
            "n_sessions": sum(len(v) for v in eng_groups.values()),
        }
    return out


def layer_counts(rs):
    c = Counter((r.get("match_method") or "").lower() for r in rs)
    return {
        "n": len(rs),
        "exact": c.get("exact", 0),
        "recovery": c.get("recovery", 0),
        "fuzzy": c.get("fuzzy", 0),
        "new": c.get("new", 0),
    }


def lat_stats(rs):
    out = {}
    for col in (
        "screen_ms",
        "canvas_ms",
        "webgl_ms",
        "platform_ms",
        "collector_total_ms",
        "api_ms",
    ):
        vals = [fnum(r.get(col)) for r in rs]
        vals = [v for v in vals if v is not None]
        out[col] = {
            "n": len(vals),
            "mean": round(st.mean(vals), 1) if vals else None,
            "p50": round(percentile(vals, 50), 1) if vals else None,
            "p95": round(percentile(vals, 95), 1) if vals else None,
        }
    e2e = []
    for r in rs:
        a, b = fnum(r.get("collector_total_ms")), fnum(r.get("api_ms"))
        if a is not None and b is not None:
            e2e.append(a + b)
    out["e2e_ms"] = {
        "n": len(e2e),
        "mean": round(st.mean(e2e), 1) if e2e else None,
        "p50": round(percentile(e2e, 50), 1) if e2e else None,
        "p95": round(percentile(e2e, 95), 1) if e2e else None,
    }
    return out


def ts(r):
    s = (r.get("submitted_at") or "").strip('"')
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min


def compute(rows):
    N = len(rows)
    gt = [r for r in rows if r["_physical"]]
    college = [r for r in gt if r["_physical"].startswith("Lab")]
    dates = sorted(
        (r.get("submitted_at") or "").strip('"')[:10]
        for r in rows
        if r.get("submitted_at")
    )

    # E1 / baseline stability by physical + engine
    base_gt = [r for r in gt if (r.get("scenario") or "") == "baseline"]
    base_groups = defaultdict(list)
    for r in base_gt:
        base_groups[(r["_physical"], r["_engine"])].append(r)
    stability = consistency_table(base_groups)

    e1 = [r for r in rows if r.get("experiment_id") == "E1"]
    e2 = [r for r in rows if r.get("experiment_id") == "E2"]
    e3 = [r for r in rows if r.get("experiment_id") == "E3"]
    e4 = [r for r in rows if r.get("experiment_id") == "E4"]

    layers = {
        "baseline": layer_counts(
            [r for r in rows if (r.get("scenario") or "") == "baseline"]
        ),
        "storage_clear": layer_counts(
            [r for r in rows if (r.get("scenario") or "") == "storage_clear"]
        ),
        "resize": layer_counts(
            [r for r in rows if (r.get("scenario") or "") == "resize"]
        ),
        "overall": layer_counts(rows),
        "e2_only": layer_counts(e2),
    }

    # Fragmentation / false-merge against physical GT
    frag = defaultdict(set)
    for r in gt:
        frag[(r["_physical"], r["_engine"])].add(r["device_id"])
    frag_keys = {k: v for k, v in frag.items() if len(v) > 1}

    id_to_phys = defaultdict(set)
    for r in gt:
        id_to_phys[(r["device_id"], r["_engine"])].add(r["_physical"])
    merge_keys = {k: v for k, v in id_to_phys.items() if len(v) > 1}
    merge_sessions = sum(
        1 for r in gt if len(id_to_phys[(r["device_id"], r["_engine"])]) > 1
    )

    seen = set()
    false_new = 0
    for r in sorted(gt, key=ts):
        key = (r["_physical"], r["_engine"])
        is_new = (r.get("match_method") or "").lower() == "new"
        if key not in seen:
            seen.add(key)
        elif is_new:
            false_new += 1

    # E4: Chromium vs Firefox on same physical
    phys_engines = defaultdict(lambda: {"Chromium": set(), "Firefox": set()})
    for r in gt:
        phys_engines[r["_physical"]][r["_engine"]].add(r["device_id"])
    paired = []
    overlap = 0
    for pid, engmap in phys_engines.items():
        if engmap["Chromium"] and engmap["Firefox"]:
            paired.append(pid)
            if engmap["Chromium"] & engmap["Firefox"]:
                overlap += 1

    # Chrome vs Edge same-engine linking
    phys_ce = defaultdict(lambda: {"Chrome": set(), "Edge": set()})
    for r in gt:
        b = r.get("browser")
        if b in ("Chrome", "Edge"):
            phys_ce[r["_physical"]][b].add(r["device_id"])
    ce_paired = [
        p for p, m in phys_ce.items() if m["Chrome"] and m["Edge"]
    ]
    ce_overlap = sum(
        1 for p in ce_paired if phys_ce[p]["Chrome"] & phys_ce[p]["Edge"]
    )

    new_n = layers["overall"]["new"]
    non_exact = (
        layers["overall"]["recovery"]
        + layers["overall"]["fuzzy"]
        + layers["overall"]["new"]
    )

    lab_seats = sorted({r["_physical"] for r in college})
    merge_examples = []
    for (did, eng), physs in sorted(merge_keys.items(), key=lambda x: -len(x[1])):
        merge_examples.append(
            {
                "device_id": did[:8],
                "engine": eng,
                "n_physicals": len(physs),
                "physicals": sorted(physs),
            }
        )

    return {
        "N": N,
        "date_range": [dates[0], dates[-1]] if dates else None,
        "browsers_raw": Counter(r.get("browser") for r in rows).most_common(),
        "engines": Counter(r["_engine"] for r in rows).most_common(),
        "experiments": {
            "E1": len(e1),
            "E2": len(e2),
            "E3": len(e3),
            "E4": len(e4),
        },
        "n_gt": len(gt),
        "n_college": len(college),
        "lab_a_seats": [x for x in lab_seats if x.startswith("LabA")],
        "lab_b_seats": [x for x in lab_seats if x.startswith("LabB")],
        "n_lab_seats": len(lab_seats),
        "stability_physical_baseline": stability,
        "layers": layers,
        "new_assignment": {"n": new_n, "rate_pct": round(100 * new_n / N, 2)},
        "non_exact": {"n": non_exact, "rate_pct": round(100 * non_exact / N, 2)},
        "layer1_counterfactual_fold": round(non_exact / new_n, 1) if new_n else None,
        "false_new_after_first": false_new,
        "fragmentation": {
            "n_keys": len(frag),
            "n_fragmented": len(frag_keys),
            "key_rate_pct": round(100 * len(frag_keys) / len(frag), 1) if frag else None,
            "examples": [
                {"key": f"{k[0]}|{k[1]}", "n_ids": len(v)}
                for k, v in sorted(frag_keys.items(), key=lambda x: -len(x[1]))
            ],
        },
        "false_merge_gt": {
            "n_keys": len(id_to_phys),
            "n_merged": len(merge_keys),
            "key_rate_pct": round(100 * len(merge_keys) / len(id_to_phys), 1)
            if id_to_phys
            else None,
            "merge_sessions": merge_sessions,
            "session_rate_pct": round(100 * merge_sessions / len(gt), 1) if gt else None,
            "examples": merge_examples,
        },
        "latency_e3": lat_stats(e3),
        "e4": {
            "n": len(e4),
            "paired_physicals": len(paired),
            "overlapping_ids": overlap,
            "paired_list": sorted(paired),
            "chrome_edge_paired": len(ce_paired),
            "chrome_edge_shared_id": ce_overlap,
        },
        "os": Counter(r.get("os_name") for r in rows).most_common(),
    }


def budget_status(p95, budget):
    if p95 is None:
        return "n/a"
    return "Pass" if p95 < budget else "Fail"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--out", default=str(OUT_JSON))
    parser.add_argument("--print-json", action="store_true")
    args = parser.parse_args()

    rows = load_rows(Path(args.csv))
    metrics = compute(rows)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

    lat = metrics["latency_e3"]
    stab = metrics["stability_physical_baseline"]
    print(f"N={metrics['N']}  GT={metrics['n_gt']}  college_seats={metrics['n_lab_seats']}")
    print(f"LabA={len(metrics['lab_a_seats'])} LabB={len(metrics['lab_b_seats'])}")
    print(
        "E1–E4:",
        metrics["experiments"],
        "new%",
        metrics["new_assignment"]["rate_pct"],
    )
    print(
        "Stability Chromium local_fp",
        stab["Chromium"]["rates"]["local_fp"],
        "Firefox",
        stab["Firefox"]["rates"]["local_fp"],
    )
    print(
        "False-merge sessions",
        metrics["false_merge_gt"]["session_rate_pct"],
        "% | E4 paired",
        metrics["e4"]["paired_physicals"],
        "overlap",
        metrics["e4"]["overlapping_ids"],
    )
    print(
        "E3 client p50/p95",
        lat["collector_total_ms"]["p50"],
        lat["collector_total_ms"]["p95"],
        "e2e",
        lat["e2e_ms"]["p50"],
        lat["e2e_ms"]["p95"],
        "API budget",
        budget_status(lat["api_ms"]["p95"], 100),
    )
    print(f"Wrote {out_path}")
    if args.print_json:
        print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
