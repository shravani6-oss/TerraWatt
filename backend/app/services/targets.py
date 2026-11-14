"""Verified official targets (data/targets.json). Only comparable indicators are ever matched."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).resolve().parents[3] / "data" / "targets.json"


@lru_cache(maxsize=1)
def _load() -> dict:
    return json.loads(PATH.read_text()) if PATH.exists() else {"targets": []}


def official_target(country: str, metric: str, forecast: list[dict]) -> dict | None:
    t = next((x for x in _load()["targets"] if x["country"] == country and x["metric"] == metric), None)
    if not t:
        return None
    row = next((f for f in forecast if f["year"] == t["year"]), None)
    out = dict(t)
    if row:
        out.update({"forecast_value": row["value"], "forecast_lo": row["lo"], "forecast_hi": row["hi"],
                    "gap_pp": round(t["value"] - row["value"], 2),
                    "interval_reaches_target": row["lo"] <= t["value"] <= row["hi"] or row["hi"] >= t["value"]})
    return out


def has_target(country: str, metric: str) -> bool:
    return any(x["country"] == country and x["metric"] == metric for x in _load()["targets"])


def all_targets() -> list[dict]:
    return _load()["targets"]
