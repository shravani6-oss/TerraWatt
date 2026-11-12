"""Load trained models and answer what-if questions."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import pandas as pd

from ..ml.pipeline import FEATURE_LABELS, FEATURES, SCENARIO_FEATURES
from .data_service import EnergyData

log = logging.getLogger("terrawatt.predictor")


class ModelsUnavailable(Exception):
    pass


class Predictor:
    def __init__(self, models_dir: Path, data: EnergyData):
        self.dir, self.data = Path(models_dir), data
        self.reg = self.clf = None
        self.cards, self.clusters = {}, {}
        self.error = None
        self._load()

    def _load(self):
        try:
            self.reg = joblib.load(self.dir / "regressor.joblib")
            self.clf = joblib.load(self.dir / "classifier.joblib")
            self.cards = json.loads((self.dir / "model_cards.json").read_text())
            self.clusters = json.loads((self.dir / "clusters.json").read_text())
        except Exception as exc:  # missing or incompatible artefacts
            self.error = f"Models unavailable ({exc.__class__.__name__}). Run: python -m backend.manage train"
            log.warning(self.error)

    def _require(self):
        if self.error:
            raise ModelsUnavailable(self.error)

    def baseline_row(self, country: str) -> dict:
        row = {"country": country, "year": self.data.headline_year}
        for f in FEATURES:
            lat = self.data.latest(country, f)
            row[f] = lat[1] if lat else None
        return row

    def predict(self, country: str, overrides: dict) -> dict:
        self._require()
        base = self.baseline_row(country)
        scen = {**base, **{k: v for k, v in overrides.items() if k in SCENARIO_FEATURES and v is not None}}
        cols = self.cards["regression"]["columns"]
        frame = lambda r: pd.DataFrame([r])[cols]
        clf_frame = lambda r: pd.DataFrame([r])[FEATURES]
        thr = self.cards["classification"]["threshold_final"]

        def run(r):
            share = float(min(100, max(0, self.reg.predict(frame(r))[0])))
            p_high = float(self.clf.predict_proba(clf_frame(r))[0, 1])
            return share, p_high
        b_share, b_high = run(base)
        s_share, s_high = run(scen)
        sens = []
        for k, v in overrides.items():
            if k in SCENARIO_FEATURES and v is not None and base.get(k) != v:
                one = {**base, k: v}
                sens.append({"feature": k, "label": FEATURE_LABELS[k], "from": base.get(k), "to": v,
                             "effect": round(run(one)[0] - b_share, 2)})
        return {"country": country, "baseline": {"share": round(b_share, 2), "p_high": round(b_high, 3), "inputs": base},
                "scenario": {"share": round(s_share, 2), "p_high": round(s_high, 3)},
                "delta": round(s_share - b_share, 2), "high_threshold": round(thr, 2), "effects": sens,
                "model": {"regressor": self.cards["regression"]["chosen"],
                          "classifier": self.cards["classification"]["chosen"],
                          "rmse_holdout": next(r["RMSE"] for r in self.cards["regression"]["table"] if r["selected"])},
                "disclaimer": ("Associations learned from 2000–2019 country data, not causal effects. "
                               "A model with country identity inside it mostly anchors to each country's own history.")}

    def cluster_of(self, country: str):
        return self.clusters.get("countries", {}).get(country)

    def peers(self, country: str, n=6) -> list[str]:
        c = self.cluster_of(country)
        if not c:
            return []
        same = [(k, abs(v["pc1"] - c["pc1"]) + abs(v["pc2"] - c["pc2"]))
                for k, v in self.clusters["countries"].items() if v["cluster"] == c["cluster"] and k != country]
        return [k for k, _ in sorted(same, key=lambda x: x[1])[:n]]
