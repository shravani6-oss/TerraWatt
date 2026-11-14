"""Evaluate stored footprint rows with the CURRENT emission-factor version (so history stays comparable)."""
from __future__ import annotations

import json

from . import carbon


def inputs_of(row) -> tuple[str, dict]:
    mode = row["mode"] if "mode" in row.keys() and row["mode"] else "advanced"
    if row["inputs_json"]:
        return mode, json.loads(row["inputs_json"])
    # legacy v1 row: reconstruct advanced inputs from the original columns
    return "advanced", {"electricity_kwh": row["electricity_kwh"], "gas_m3": row["gas_m3"], "car_km": row["car_km"],
                        "flight_km": row["flight_km"], "renewable_pct": row["renewable_pct"], "household_size": 1}


def result_for(row, data) -> dict:
    mode, inp = inputs_of(row)
    size = row["household_size"] if "household_size" in row.keys() and row["household_size"] else inp.get("household_size", 1)
    inp = {**inp, "household_size": size}
    grid = carbon.grid_factor(data, row["country"])
    return carbon.evaluate(mode, inp, grid)
