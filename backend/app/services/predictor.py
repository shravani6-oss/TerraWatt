"""Load trained models and answer what-if questions.

Design notes (why predictions are trustworthy here):
  * The regression target (World Bank renewable share of FINAL energy) is observed only up to ~2019/2020, so each
    country's baseline is its feature vector in its LAST LABELLED YEAR (never a mix of years), with the exact column
    order stored in the model card. Missing features are imputed by the model's own median imputer and are reported.
  * Electricity-mix scenarios (Ember data, to 2025) are computed exactly by `scenario.py`; their relative change in
    fossil / nuclear generation is then applied to the model's reference-year values.
  * Artefacts are checked against the running scikit-learn/numpy/pandas versions and are retrained automatically
    (~10 s) when they cannot be loaded, so a version mismatch never surfaces as a generic error.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from ..ml.pipeline import FEATURE_LABELS, FEATURES, SCENARIO_FEATURES, TARGET
from . import scenario as mixsim
from .data_service import EnergyData

log = logging.getLogger("terrawatt.predictor")

FEATURE_UNITS = {"electricity_access": "%", "clean_cooking_access": "%", "elec_fossil_twh": "TWh", "elec_nuclear_twh": "TWh",
                 "energy_per_capita_kwh": "kWh", "energy_intensity": "MJ/$", "gdp_per_capita": "US$", "gdp_growth": "%"}
PCT_FEATURES = {"electricity_access", "clean_cooking_access"}
NONNEG = {"elec_fossil_twh", "elec_nuclear_twh", "energy_per_capita_kwh", "energy_intensity", "gdp_per_capita"}


class ModelsUnavailable(Exception):
    pass


class ScenarioInputError(ValueError):
    pass


class Predictor:
    def __init__(self, models_dir: Path, data: EnergyData, data_csv: Path | None = None, auto_retrain: bool = True):
        self.dir, self.data = Path(models_dir), data
        self.data_csv = Path(data_csv) if data_csv else data.path
        self.auto_retrain = auto_retrain
        self.reg = self.clf = None
        self.cards, self.clusters = {}, {}
        self.error = None
        self.retrained = False
        self._load()

    # ------------------------------------------------------------------ loading
    def _try_load(self):
        self.reg = joblib.load(self.dir / "regressor.joblib")
        self.clf = joblib.load(self.dir / "classifier.joblib")
        self.cards = json.loads((self.dir / "model_cards.json").read_text())
        self.clusters = json.loads((self.dir / "clusters.json").read_text())
        built = self.cards.get("env", {}).get("sklearn") or self.cards.get("sklearn")
        if built and built.split(".")[:2] != sklearn.__version__.split(".")[:2]:
            raise RuntimeError(f"models built with scikit-learn {built}, running {sklearn.__version__}")
        if self.cards.get("features") != FEATURES:
            raise RuntimeError("model feature list does not match the code")
        # smoke test: one prediction with the stored column order
        c = self.data.countries[0]
        self._run(self.baseline_row(c)[0])

    def _load(self):
        try:
            self._try_load()
            return
        except Exception as exc:  # missing, incompatible or stale artefacts
            log.warning("Model load failed (%s: %s)", exc.__class__.__name__, exc)
            first = f"{exc.__class__.__name__}: {exc}"
        if self.auto_retrain:
            try:
                from ..ml.train import train_all
                log.info("Retraining models for this environment…")
                train_all(self.data_csv, self.dir)
                self._try_load()
                self.retrained = True
                self.error = None
                return
            except Exception as exc2:
                first = f"{first}; automatic retraining failed: {exc2.__class__.__name__}: {exc2}"
        self.reg = self.clf = None
        self.error = f"Models unavailable ({first}). Run: python -m backend.manage train"
        log.error(self.error)

    def _require(self):
        if self.error:
            raise ModelsUnavailable(self.error)

    # ------------------------------------------------------------------ baseline
    def reference_year(self, country: str) -> int | None:
        c = self.data._by_country[country]
        s = c[TARGET].dropna()
        if len(s):
            return int(s.index.max())
        # no labelled history (e.g. countries added from Ember/OWID): use the last year <= the model's label window
        # in which the country has most feature values, so the baseline is still one consistent year
        last = self.cards.get("data_window", {}).get("target_years", [0, 2019])[1]
        sub = c.loc[c.index <= last, [f for f in FEATURES if f in c.columns]].dropna(how="all")
        if sub.empty:
            return None
        return int(sub.notna().sum(axis=1).sort_values(kind="stable").index[-1]) if False else int(sub.index.max())

    def baseline_row(self, country: str) -> tuple[dict, list[str], int]:
        """Feature vector in the country's last labelled year (NaN where not observed) + imputed feature names."""
        ry = self.reference_year(country)
        if ry is None:
            raise ScenarioInputError(f"{country} has no renewable-share observations, so the model has no baseline for it.")
        r = self.data._by_country[country].loc[ry]
        row = {"country": country, "year": ry}
        for f in FEATURES:
            v = r[f] if f in r.index else np.nan
            row[f] = float(v) if v == v else np.nan
        imputed = [f for f in FEATURES if math.isnan(row[f])]
        return row, imputed, ry

    def _frames(self, row):
        cols = self.cards["regression"]["columns"]
        return pd.DataFrame([row])[cols], pd.DataFrame([row])[FEATURES]

    def _run(self, row):
        reg_X, clf_X = self._frames(row)
        share = float(np.clip(self.reg.predict(reg_X)[0], 0, 100))
        p_high = float(self.clf.predict_proba(clf_X)[0, 1])
        return share, p_high

    # ------------------------------------------------------------------ config for the UI
    def config(self, country: str) -> dict:
        self._require()
        row, imputed, ry = self.baseline_row(country)
        ranges = self.cards.get("scenario_ranges", {})
        feats = []
        for k in SCENARIO_FEATURES:
            rg = ranges.get(k, {})
            base = None if math.isnan(row[k]) else row[k]
            lo, hi = self.bounds(k, base, rg)
            feats.append({"key": k, "label": FEATURE_LABELS[k], "unit": FEATURE_UNITS.get(k, ""), "baseline": base,
                          "min": lo, "max": hi, "step": self.step(lo, hi), "imputed": k in imputed,
                          "median": rg.get("median")})
        return {"country": country, "reference_year": ry, "features": feats,
                "electricity_mix": mixsim.baseline_summary(self.data, country) if hasattr(mixsim, "baseline_summary") else None,
                "presets": mixsim.PRESETS, "imputed_features": imputed,
                "model_card_trained_at": self.cards.get("trained_at")}

    @staticmethod
    def step(lo, hi):
        span = hi - lo
        return round(span / 200, 4) if span > 0 else 0.01

    @staticmethod
    def bounds(k, base, rg):
        if k in PCT_FEATURES:
            return 0.0, 100.0
        lo, hi = rg.get("p1", 0.0), rg.get("p99", 1.0)
        if base is not None:
            lo, hi = min(lo, base), max(hi, base * 1.5 if base > 0 else hi)
        if k in NONNEG:
            lo = max(0.0, lo)
        return float(lo), float(hi)

    # ------------------------------------------------------------------ validation
    def validate_overrides(self, country: str, overrides: dict) -> dict:
        row, _, _ = self.baseline_row(country)
        ranges = self.cards.get("scenario_ranges", {})
        clean = {}
        for k, v in overrides.items():
            if k not in SCENARIO_FEATURES:
                raise ScenarioInputError(f"'{k}' cannot be changed in the what-if lab. Allowed: {', '.join(SCENARIO_FEATURES)}.")
            if v is None or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ScenarioInputError(f"{FEATURE_LABELS[k]} must be a finite number.")
            if k in PCT_FEATURES and not 0 <= v <= 100:
                raise ScenarioInputError(f"{FEATURE_LABELS[k]} must be between 0 and 100.")
            if k in NONNEG and v < 0:
                raise ScenarioInputError(f"{FEATURE_LABELS[k]} cannot be negative.")
            rg = ranges.get(k, {})
            hi = max(rg.get("p99", v), 0 if math.isnan(row[k]) else row[k]) * 5 + 1
            if v > hi and k not in PCT_FEATURES:
                raise ScenarioInputError(f"{FEATURE_LABELS[k]} = {v:g} is far outside the range the model was trained on.")
            clean[k] = float(v)
        return clean

    # ------------------------------------------------------------------ prediction
    def predict(self, country: str, overrides: dict, mix: dict | None = None, access_gap_pct: float | None = None) -> dict:
        self._require()
        base, imputed, ry = self.baseline_row(country)
        overrides = dict(overrides or {})
        notes = []
        mix_result = None
        if mix:
            try:
                mix_result = mixsim.run(self.data, country, mix)
            except ValueError as exc:
                raise ScenarioInputError(str(exc))
            # apply the RELATIVE change in fossil / nuclear generation to the model's reference-year values
            for src, feat in (("elec_fossil_twh", "elec_fossil_twh"), ("elec_nuclear_twh", "elec_nuclear_twh")):
                b = next(x["twh"] for x in mix_result["baseline"]["by_source"] if x["key"] == src)
                s_ = next(x["twh"] for x in mix_result["scenario"]["by_source"] if x["key"] == src)
                if b > 0 and not math.isnan(base[feat]) and abs(s_ - b) > 1e-9 and feat not in overrides:
                    overrides[feat] = base[feat] * s_ / b
                    notes.append(f"{FEATURE_LABELS[feat]} scaled by {s_ / b:.2f}× (relative change from the electricity-mix scenario).")
        if access_gap_pct:
            cur = base["electricity_access"]
            if not math.isnan(cur) and "electricity_access" not in overrides:
                overrides["electricity_access"] = cur + (100 - cur) * access_gap_pct / 100
        overrides = self.validate_overrides(country, overrides)
        scen = {**base, **overrides}
        b_share, b_high = self._run(base)
        s_share, s_high = self._run(scen)
        effects = []
        for k, v in overrides.items():
            if base.get(k) is not None and base[k] == base[k] and abs(base[k] - v) < 1e-12:
                continue
            effects.append({"feature": k, "label": FEATURE_LABELS[k], "from": None if math.isnan(base[k]) else base[k],
                            "to": v, "effect": round(self._run({**base, k: v})[0] - b_share, 2)})
        thr = self.cards["classification"]["threshold_final"]
        reg_row = next(r for r in self.cards["regression"]["table"] if r["selected"])
        clean_inputs = {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in base.items()}
        return {"country": country, "reference_year": ry, "has_labelled_history": bool(self.data._by_country[country][TARGET].notna().any()),
                "baseline": {"share": round(b_share, 2), "p_high": round(b_high, 3), "inputs": clean_inputs},
                "scenario": {"share": round(s_share, 2), "p_high": round(s_high, 3),
                             "inputs": {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in scen.items()}},
                "delta": round(s_share - b_share, 2), "delta_p_high": round(s_high - b_high, 3),
                "high_threshold": round(thr, 2), "effects": effects, "imputed_features": imputed,
                "reliability": "low" if len(imputed) >= 5 else ("medium" if imputed else "normal"),
                "reliability_note": (f"{len(imputed)} of {len(FEATURES)} model inputs are not reported for this country and were filled "
                                     "with the training median, so the estimate says little about this country." if len(imputed) >= 5 else
                                     ("Some inputs were not reported and were filled with the training median." if imputed else None)),
                "changed_inputs": [{"feature": k, "label": FEATURE_LABELS[k], "unit": FEATURE_UNITS.get(k, ""),
                                    "from": None if math.isnan(base[k]) else base[k], "to": v} for k, v in overrides.items()],
                "electricity_mix": mix_result, "notes": notes,
                "model": {"regressor": self.cards["regression"]["chosen"], "classifier": self.cards["classification"]["chosen"],
                          "rmse_holdout": reg_row["RMSE"], "r2_holdout": reg_row["R2"],
                          "trained_on": self.cards.get("data_window", {}).get("target_years")},
                "disclaimer": ("Statistical associations learned from country data up to the last labelled year, not causal effects or "
                               "policy forecasts. The model includes country identity, so it mostly anchors to each country's own history; "
                               "treat the scenario estimate as 'what similar patterns in the data imply', with the hold-out error as its uncertainty.")}

    def cluster_of(self, country: str):
        return self.clusters.get("countries", {}).get(country)

    def peers(self, country: str, n=6) -> list[str]:
        c = self.cluster_of(country)
        if not c:
            return []
        same = [(k, abs(v["pc1"] - c["pc1"]) + abs(v["pc2"] - c["pc2"]))
                for k, v in self.clusters["countries"].items() if v["cluster"] == c["cluster"] and k != country]
        return [k for k, _ in sorted(same, key=lambda x: x[1])[:n]]
