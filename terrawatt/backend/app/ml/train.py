"""Train and evaluate every model used by the API, then write artefacts + model cards.

    python -m backend.manage train

Protocols (chosen to avoid the usual leakage traps):
  regression      chronological split; model picked on an inner validation window, reported once on the test years
  classification  country-grouped split (a country's years are near-duplicates), label threshold from TRAIN median,
                  model picked by StratifiedGroupKFold F1 on train only, reported once on the held-out countries
  clustering      latest-5-year country averages, log+standardise, K by silhouette in 3..6
"""
from __future__ import annotations

import json
import logging
import platform
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, mean_absolute_error, mean_squared_error,
                             precision_score, r2_score, recall_score, roc_auc_score, silhouette_score)
from sklearn.model_selection import GroupShuffleSplit, StratifiedGroupKFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ..services.data_service import load_frame
from .pipeline import FEATURE_LABELS, FEATURES, TARGET, build_preprocessor

log = logging.getLogger("terrawatt.ml")
SEED = 42
TEST_YEARS = 4
CLUSTER_FEATURES = ["renewable_share", "electricity_access", "clean_cooking_access", "gdp_per_capita",
                    "energy_per_capita_kwh", "low_carbon_elec_pct", "energy_intensity"]
CLUSTER_LOG = ["gdp_per_capita", "energy_per_capita_kwh"]


def _reg_metrics(y, p):
    mse = mean_squared_error(y, p)
    return {"MAE": float(mean_absolute_error(y, p)), "RMSE": float(np.sqrt(mse)), "R2": float(r2_score(y, p))}


def train_regression(df):
    d = df.dropna(subset=[TARGET])
    cutoff = int(d.year.max()) - TEST_YEARS
    train, test = d[d.year <= cutoff], d[d.year > cutoff]
    feats = FEATURES + ["year"]

    def cands():
        return {
            "Baseline (train mean)": (DummyRegressor(), feats),
            "Ridge": (Pipeline([("prep", build_preprocessor(feats)), ("m", Ridge(alpha=1.0))]), feats),
            "Ridge + country": (Pipeline([("prep", build_preprocessor(feats, ["country"])), ("m", Ridge(alpha=1.0))]),
                                feats + ["country"]),
            "Gradient boosting": (Pipeline([("prep", build_preprocessor(feats, scale=False)),
                                            ("m", HistGradientBoostingRegressor(max_depth=5, learning_rate=0.08,
                                                                                 max_iter=250, random_state=SEED))]),
                                  feats),
        }
    # inner validation window (last 3 training years) for model selection
    inner_cut = cutoff - 3
    itrain, ival = train[train.year <= inner_cut], train[train.year > inner_cut]
    inner = {}
    for name, (m, cols) in cands().items():
        m.fit(itrain[cols], itrain[TARGET])
        inner[name] = _reg_metrics(ival[TARGET], m.predict(ival[cols]))["RMSE"]
    chosen = min((k for k in inner if not k.startswith("Baseline")), key=inner.get)
    rows, fitted = [], {}
    for name, (m, cols) in cands().items():
        m.fit(train[cols], train[TARGET])
        fitted[name] = (m, cols)
        rows.append({"model": name, **_reg_metrics(test[TARGET], m.predict(test[cols])),
                     "inner_val_rmse": inner[name], "selected": name == chosen})
    model, cols = fitted[chosen]
    # Final model refit on ALL labelled years so what-if answers use the freshest data (metrics above stay honest)
    final, _ = cands()[chosen]
    final.fit(d[cols], d[TARGET])
    imp = permutation_importance(model, test[cols], test[TARGET], n_repeats=5, random_state=SEED,
                                 scoring="neg_root_mean_squared_error")
    importance = sorted(({"feature": c, "label": FEATURE_LABELS.get(c, c), "importance": float(v)}
                         for c, v in zip(cols, imp.importances_mean) if c != "country"),
                        key=lambda r: -r["importance"])
    meta = {"chosen": chosen, "columns": cols, "cutoff_year": cutoff, "n_train": int(len(train)), "n_test": int(len(test)),
            "table": rows, "importance": importance[:10]}
    return final, meta


def train_classifier(df):
    d = df.dropna(subset=[TARGET]).reset_index(drop=True)
    tr_idx, te_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(d, groups=d.country))
    train, test = d.iloc[tr_idx].copy(), d.iloc[te_idx].copy()
    threshold = float(train[TARGET].median())
    for part in (train, test):
        part["label"] = (part[TARGET] > threshold).astype(int)

    def mk(clf, scale):
        return Pipeline([("prep", build_preprocessor(FEATURES, scale=scale)), ("clf", clf)])
    cands = {
        "Logistic regression": mk(LogisticRegression(max_iter=3000, random_state=SEED), True),
        "Random forest": mk(RandomForestClassifier(n_estimators=250, min_samples_leaf=2, max_features=0.5,
                                                    random_state=SEED, n_jobs=1), False),
        "Gradient boosting": mk(HistGradientBoostingClassifier(max_depth=4, learning_rate=0.08, max_iter=200,
                                                               random_state=SEED), False),
    }
    X, y, g = train[FEATURES], train["label"].values, train["country"].values
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    cv_f1 = {n: float(cross_val_score(m, X, y, cv=cv, groups=g, scoring="f1").mean()) for n, m in cands.items()}
    chosen = max(cv_f1, key=cv_f1.get)
    rows, fitted = [], {}
    for name, m in cands.items():
        m.fit(X, y)
        fitted[name] = m
        pred, proba = m.predict(test[FEATURES]), m.predict_proba(test[FEATURES])[:, 1]
        rows.append({"model": name, "cv_f1": cv_f1[name], "accuracy": float(accuracy_score(test.label, pred)),
                     "precision": float(precision_score(test.label, pred, zero_division=0)),
                     "recall": float(recall_score(test.label, pred, zero_division=0)),
                     "f1": float(f1_score(test.label, pred, zero_division=0)),
                     "roc_auc": float(roc_auc_score(test.label, proba)),
                     "confusion": confusion_matrix(test.label, pred, labels=[0, 1]).tolist(), "selected": name == chosen})
    model = fitted[chosen]
    imp = permutation_importance(model, test[FEATURES], test["label"], n_repeats=5, random_state=SEED, scoring="f1")
    importance = sorted(({"feature": c, "label": FEATURE_LABELS.get(c, c), "importance": float(v)}
                         for c, v in zip(FEATURES, imp.importances_mean)), key=lambda r: -r["importance"])
    # Final classifier uses all countries; the threshold is the median over all labelled rows.
    full_threshold = float(d[TARGET].median())
    # refit a fresh clone on all data (sklearn.clone keeps params, drops fitted state)
    final = clone(cands[chosen]).fit(d[FEATURES], (d[TARGET] > full_threshold).astype(int))
    meta = {"chosen": chosen, "threshold_eval": threshold, "threshold_final": full_threshold, "table": rows,
            "n_train": int(len(train)), "n_test": int(len(test)), "n_test_countries": int(test.country.nunique()),
            "importance": importance[:10]}
    return final, meta


def run_clustering(df):
    last = df[df.year > df.year.max() - 5]
    table = last.groupby("country")[CLUSTER_FEATURES].mean()
    table = table.dropna(thresh=len(CLUSTER_FEATURES) - 2)
    X = pd.DataFrame(SimpleImputer(strategy="median").fit_transform(table), index=table.index, columns=CLUSTER_FEATURES)
    for c in CLUSTER_LOG:
        X[c] = np.log1p(X[c].clip(lower=0))
    Z = StandardScaler().fit_transform(X)
    sil = {k: float(silhouette_score(Z, KMeans(k, n_init=10, random_state=SEED).fit_predict(Z))) for k in range(2, 9)}
    k = max((x for x in sil if 3 <= x <= 6), key=sil.get)
    km = KMeans(k, n_init=20, random_state=SEED).fit(Z)
    table = table.assign(cluster=km.labels_)
    profile = table.groupby("cluster")[CLUSTER_FEATURES].mean()
    order = profile["renewable_share"].sort_values().index.tolist()
    names = {}
    for rank, cid in enumerate(order):
        tier = "Low" if rank < k / 3 else ("High" if rank >= k - k / 3 else "Medium")
        names[int(cid)] = f"{tier} renewable share"
    seen = {}
    for cid in sorted(names):              # disambiguate repeated tiers (only when K > 3)
        seen[names[cid]] = seen.get(names[cid], 0) + 1
        if list(names.values()).count(names[cid]) > 1:
            names[cid] += f" ({'ABCDEF'[seen[names[cid]] - 1]})"
    pcs = PCA(2, random_state=SEED).fit_transform(Z)
    # intervention-priority score: mean percentile deficit across five indicators
    parts = []
    for col, worse_high in [("renewable_share", False), ("electricity_access", False), ("clean_cooking_access", False),
                            ("low_carbon_elec_pct", False), ("energy_intensity", True)]:
        r = table[col].rank(pct=True)
        parts.append(r if worse_high else 1 - r)
    priority = pd.concat(parts, axis=1).mean(axis=1)
    countries = {c: {"cluster": int(table.loc[c, "cluster"]), "label": names[int(table.loc[c, "cluster"])],
                     "pc1": float(pcs[i, 0]), "pc2": float(pcs[i, 1]), "priority": float(priority[c])}
                 for i, c in enumerate(table.index)}
    profiles = [{"cluster": int(cid), "label": names[int(cid)], "n": int((table.cluster == cid).sum()),
                 "means": {f: float(profile.loc[cid, f]) for f in CLUSTER_FEATURES},
                 "examples": table[table.cluster == cid]["renewable_share"].sort_values(ascending=False).head(5).index.tolist()}
                for cid in sorted(profile.index)]
    return {"k": int(k), "silhouette": sil, "silhouette_chosen": sil[k], "features": CLUSTER_FEATURES,
            "profiles": profiles, "countries": countries, "window_years": [int(df.year.max()) - 4, int(df.year.max())]}


def scenario_ranges(df):
    d = df[FEATURES + ["year"]]
    return {c: {"p1": float(d[c].quantile(.01)), "p99": float(d[c].quantile(.99)), "median": float(d[c].median())}
            for c in FEATURES}


def train_all(csv_path: Path, models_dir: Path) -> dict:
    models_dir.mkdir(parents=True, exist_ok=True)
    df = load_frame(csv_path)
    log.info("Training regression…")
    reg, reg_meta = train_regression(df)
    log.info("Training classifier…")
    clf, clf_meta = train_classifier(df)
    log.info("Clustering…")
    clusters = run_clustering(df)
    joblib.dump(reg, models_dir / "regressor.joblib")
    joblib.dump(clf, models_dir / "classifier.joblib")
    (models_dir / "clusters.json").write_text(json.dumps(clusters))
    card = {"trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sklearn": sklearn.__version__, "python": platform.python_version(),
            "dataset_rows": int(len(df)), "features": FEATURES, "target": TARGET,
            "regression": reg_meta, "classification": clf_meta,
            "clustering": {k: v for k, v in clusters.items() if k != "countries"},
            "scenario_ranges": scenario_ranges(df)}
    (models_dir / "model_cards.json").write_text(json.dumps(card, indent=1))
    return card
