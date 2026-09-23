#!/usr/bin/env python3
"""Reproduce the fuzzy-threshold replay reported in the manuscript.

The replay mirrors the three matching layers used by the benchmark service:
exact local fingerprint, stored-device recovery, and blocked fuzzy matching.
It uses only the checked-in CSV and Python's standard library.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CLIENT_ID = "dev_client"

PHYSICAL_RE = re.compile(r"physical\s*=\s*([^;]+)", re.I)
LAB_SEAT_RE = re.compile(
    r"^lab\s*([ab])\s*[-_]?(?:(?:chr|ed|fire|cr|edge|chrome|firefox|ff)\s*[-_]*)?"
    r"(\d+)\s*(?:[-_]*(?:chr|ed|fire|cr|edge|chrome|firefox|ff))?$",
    re.I,
)
LAB_BROWSER_SEAT_RE = re.compile(
    r"^lab\s*([ab])\s*[-_]*(?:chr|ed|fire|cr|edge|chrome|firefox|ff)\s*[-_]*(\d+)$",
    re.I,
)

RULES = (
    ("gpu_renderer", 1.00, "fuzzy", False),
    ("canvas_hash", 0.90, "exact", False),
    ("screen_width", 0.65, "exact", True),
    ("platform", 0.55, "exact", True),
    ("timezone", 0.50, "exact", False),
    ("language", 0.45, "exact", False),
)


def clean(value: str | None) -> str:
    return (value or "").strip().strip('"')


def browser_engine(browser: str) -> str:
    value = browser.strip().lower()
    if value in {"chrome", "edge", "chromium"}:
        return "Chromium"
    if value == "firefox":
        return "Firefox"
    return ""


def clean_physical(raw: str) -> str:
    value = raw.strip()
    match = LAB_BROWSER_SEAT_RE.match(value) or LAB_SEAT_RE.match(value)
    if match:
        return f"Lab{match.group(1).upper()}-{int(match.group(2)):02d}"
    aliases = {"macos tahoe": "macOS-Tahoe", "android neon": "Android-Neon"}
    return aliases.get(value.lower(), "")


def physical_id(row: dict[str, str]) -> str:
    note = clean(row.get("participant_note"))
    match = PHYSICAL_RE.search(note)
    if match:
        result = clean_physical(match.group(1))
        if result:
            return result
    return clean_physical(clean(row.get("device_label")))


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(clean(value).replace("Z", "+00:00"))


def load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = []
        for raw in csv.DictReader(handle):
            row = {key: clean(value) for key, value in raw.items()}
            row["id"] = int(row["id"])
            row["submitted"] = parse_timestamp(row["submitted_at"])
            row["engine"] = browser_engine(row.get("browser", ""))
            row["physical"] = physical_id(row)
            row["in_scope"] = bool(row["engine"])
            rows.append(row)
    return sorted(rows, key=lambda row: (row["submitted"], row["id"]))


class Store:
    def __init__(self) -> None:
        self.by_fp: dict[str, dict] = {}
        self.by_id: dict[str, dict] = {}
        self.blocks: defaultdict[str, list[str]] = defaultdict(list)

    @staticmethod
    def fp_key(fp: str) -> str:
        return f"{CLIENT_ID}|{fp}"

    @staticmethod
    def id_key(device_id: str) -> str:
        return f"{CLIENT_ID}|{device_id}"

    def save(self, record: dict) -> None:
        self.by_fp[self.fp_key(record["local_fp"])] = record
        self.by_id[self.id_key(record["device_id"])] = record
        self.blocks[f"{CLIENT_ID}|{block_key(record['signals'])}"].append(
            record["local_fp"]
        )

    def update(self, record: dict) -> None:
        self.by_id[self.id_key(record["device_id"])] = record
        self.by_fp[self.fp_key(record["local_fp"])] = record

    def remap(self, old_fp: str, new_fp: str, record: dict, block: str) -> None:
        if old_fp and old_fp != new_fp:
            self.by_fp.pop(self.fp_key(old_fp), None)
        record["local_fp"] = new_fp
        self.by_fp[self.fp_key(new_fp)] = record
        self.by_id[self.id_key(record["device_id"])] = record
        if block:
            self.blocks[f"{CLIENT_ID}|{block}"].append(new_fp)

    def by_local_fp(self, fp: str) -> dict | None:
        return self.by_fp.get(self.fp_key(fp))

    def by_device_id(self, device_id: str) -> dict | None:
        return self.by_id.get(self.id_key(device_id))

    def candidates(self, block: str) -> list[dict]:
        seen: set[str] = set()
        result = []
        for fp in self.blocks.get(f"{CLIENT_ID}|{block}", []):
            record = self.by_fp.get(self.fp_key(fp))
            if record and record["device_id"] not in seen:
                seen.add(record["device_id"])
                result.append(record)
        return result


def block_key(signals: dict[str, str]) -> str:
    return f"{signals.get('platform') or 'unknown'}:{signals.get('screen_width') or 'unknown'}"


def levenshtein(left: str, right: str) -> int:
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, 1):
        current = [i]
        for j, right_char in enumerate(right, 1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def similarity(left: str, right: str, mode: str) -> float:
    if mode == "exact":
        return 1.0 if left == right else 0.0
    left, right = left.strip().lower(), right.strip().lower()
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0
    return 1.0 - levenshtein(left, right) / max(len(left), len(right))


def score(incoming: dict[str, str], stored: dict[str, str]) -> float:
    weighted = 0.0
    total_weight = 0.0
    for name, weight, mode, required in RULES:
        left, right = incoming.get(name, ""), stored.get(name, "")
        if not left or not right:
            if required:
                return 0.0
            continue
        value = similarity(left, right, mode)
        weighted += weight * value
        total_weight += weight
    return weighted / total_weight if total_weight else 0.0


def identify(store: Store, row: dict, threshold: float, sequence: int) -> tuple[dict, int]:
    signals = {
        "platform": row["platform_string"],
        "screen_width": row["screen_width"],
        "canvas_hash": row["canvas_hash"],
        "gpu_renderer": row["gpu_renderer"],
    }
    local_fp = row["local_fp"]

    record = store.by_local_fp(local_fp)
    if record:
        return {"device_id": record["device_id"], "method": "exact"}, sequence

    stored_id = row.get("stored_device_id", "")
    if stored_id:
        record = store.by_device_id(stored_id)
        if record:
            block = block_key(signals)
            old_fp = record["local_fp"]
            record["signals"] = signals
            store.remap(old_fp, local_fp, record, block)
            store.update(record)
            return {"device_id": record["device_id"], "method": "recovery"}, sequence

    block = block_key(signals)
    best, best_score = None, 0.0
    for candidate in store.candidates(block):
        candidate_score = score(signals, candidate["signals"])
        if candidate_score > best_score:
            best, best_score = candidate, candidate_score
    if best is not None and best_score >= threshold:
        old_fp = best["local_fp"]
        best["signals"] = signals
        store.remap(old_fp, local_fp, best, block)
        store.update(best)
        return {"device_id": best["device_id"], "method": "fuzzy"}, sequence

    sequence += 1
    device_id = f"replay-{sequence:06d}"
    store.save({"device_id": device_id, "local_fp": local_fp, "signals": signals})
    return {"device_id": device_id, "method": "new"}, sequence


def layer_counts(rows: list[dict]) -> dict[str, int]:
    result = {"n": len(rows), "exact": 0, "recovery": 0, "fuzzy": 0, "new": 0}
    for row in rows:
        result[row["method"]] += 1
    return result


def round1(value: float) -> float:
    return math.floor(value * 10 + 0.5) / 10


def observed_metrics(rows: list[dict]) -> dict:
    in_scope = [row for row in rows if row["in_scope"]]
    observed = []
    for row in in_scope:
        copy = dict(row)
        copy["method"] = row.get("match_method", "").lower()
        copy["device_id"] = row.get("device_id", "")
        observed.append(copy)
    id_to_phys: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    for row in observed:
        if row["physical"]:
            id_to_phys[(row["device_id"], row["engine"])].add(row["physical"])
    merged = {key for key, physicals in id_to_phys.items() if len(physicals) > 1}
    return {
        "layers": layer_counts(observed),
        "merge_sessions": sum(
            1
            for row in observed
            if (row["device_id"], row["engine"]) in merged and row["physical"]
        ),
        "false_new": count_false_new(observed),
    }


def count_false_new(rows: list[dict]) -> int:
    seen: set[tuple[str, str]] = set()
    count = 0
    for row in sorted(rows, key=lambda item: (item["submitted"], item["id"])):
        key = (row["physical"], row["engine"])
        if not row["physical"]:
            continue
        if key in seen and row["method"] == "new":
            count += 1
        seen.add(key)
    return count


def replay(rows: list[dict], threshold: float) -> list[dict]:
    store = Store()
    local_storage: dict[str, str] = {}
    sequence = 0
    output = []
    for row in rows:
        stored_id = "" if row["scenario"] == "storage_clear" else local_storage.get(row["session_id"], "")
        current = dict(row)
        current["stored_device_id"] = stored_id
        result, sequence = identify(store, current, threshold, sequence)
        current.update(result)
        if row["scenario"] != "storage_clear":
            local_storage[row["session_id"]] = result["device_id"]
        output.append(current)
    return output


def aggregate(rows: list[dict], threshold: float, observed: dict) -> dict:
    in_scope = [row for row in rows if row["in_scope"]]
    by_scenario = {
        scenario: layer_counts([row for row in in_scope if row["scenario"] == scenario])
        for scenario in ("baseline", "storage_clear", "resize")
    }
    gt = [row for row in in_scope if row["physical"]]
    fragmentation: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    id_to_phys: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    for row in gt:
        fragmentation[(row["physical"], row["engine"])].add(row["device_id"])
        id_to_phys[(row["device_id"], row["engine"])].add(row["physical"])
    merged = {key for key, physicals in id_to_phys.items() if len(physicals) > 1}
    merge_sessions = sum(
        1 for row in gt if (row["device_id"], row["engine"]) in merged
    )
    layers = layer_counts(in_scope)
    result = {
        "threshold": threshold,
        "layers_overall": layers,
        "layers_by_scenario": by_scenario,
        "new_assignment_n": layers["new"],
        "new_assignment_rate_pct": round1(100 * layers["new"] / len(in_scope)),
        "false_new_after_first": count_false_new(gt),
        "fragmentation_n_keys": len(fragmentation),
        "fragmentation_n_fragmented": sum(
            1 for devices in fragmentation.values() if len(devices) > 1
        ),
        "merge_n_keys": len(id_to_phys),
        "merge_n_merged": len(merged),
        "merge_key_rate_pct": round1(100 * len(merged) / len(id_to_phys)),
        "merge_sessions": merge_sessions,
        "merge_session_rate_pct": round1(100 * merge_sessions / len(gt)),
        "n_gt": len(gt),
        "n_in_scope": len(in_scope),
    }
    observed_layers = observed["layers"]
    deltas = {
        key: layers[key] - observed_layers[key]
        for key in ("n", "exact", "recovery", "fuzzy", "new")
    }
    fuzzy_new_observed = observed_layers["fuzzy"] + observed_layers["new"]
    fuzzy_new_delta = abs(deltas["fuzzy"]) + abs(deltas["new"])
    merge_rate_delta = abs(result["merge_session_rate_pct"] - round1(100 * observed["merge_sessions"] / len(gt)))
    faithful = (
        fuzzy_new_observed > 0
        and fuzzy_new_delta <= 0.25 * fuzzy_new_observed + 5
        and merge_rate_delta <= 15.0
        and deltas["n"] == 0
    )
    if faithful and any(deltas[key] for key in ("exact", "recovery", "fuzzy", "new")):
        notes = "Replay approximately reproduces observed outcomes; residual deltas are expected from empty-store reconstruction."
    elif faithful:
        notes = "Replay matched observed layer counts exactly on the in-scope export."
    else:
        notes = "Replay did not closely reproduce observed layer/merge totals; do not treat sensitivity deltas as production calibration without caveats."
    result["validation_vs_observed"] = {
        "observed_layers": observed_layers,
        "layer_deltas": deltas,
        "observed_merge_sessions": observed["merge_sessions"],
        "merge_session_delta": merge_sessions - observed["merge_sessions"],
        "observed_false_new": observed["false_new"],
        "false_new_delta": result["false_new_after_first"] - observed["false_new"],
        "faithful_enough": faithful,
        "notes": notes,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/benchmark_data.csv")
    parser.add_argument("--out", default="data/threshold_sensitivity.json")
    parser.add_argument("--thresholds", default="0.70,0.80,0.85")
    args = parser.parse_args()
    thresholds = [float(value.strip()) for value in args.thresholds.split(",") if value.strip()]
    rows = load_rows(Path(args.csv))
    observed = observed_metrics(rows)
    results = []
    for threshold in thresholds:
        result = aggregate(replay(rows, threshold), threshold, observed)
        if abs(threshold - 0.70) < 1e-9:
            pass
        else:
            result.pop("validation_vs_observed", None)
        results.append(result)
        print(
            f"threshold={threshold:.2f} in_scope={result['n_in_scope']} "
            f"fuzzy={result['layers_overall']['fuzzy']} "
            f"new={result['new_assignment_n']} ({result['new_assignment_rate_pct']:.2f}%) "
            f"merge_sessions={result['merge_sessions']} ({result['merge_session_rate_pct']:.1f}%)"
        )
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "csv": args.csv,
        "method": "Global chronological replay from empty in-memory store; per-session simulated localStorage; storage_clear omits and does not update stored ID; signals={platform,screen_width,canvas_hash,gpu_renderer}; aggregates restricted to Chrome+Edge+Firefox.",
        "thresholds": results,
    }
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {destination}")


if __name__ == "__main__":
    main()
