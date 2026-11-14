"""Module G: ensemble comparison, cross-validation, hyper-parameter tuning, final evaluation."""
import time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import (GridSearchCV, GroupKFold, KFold, RandomizedSearchCV,
                                     StratifiedGroupKFold, StratifiedKFold, cross_val_score)
from sklearn.pipeline import Pipeline
from .classification import evaluate_classifier, make_models
from .config import RANDOM_STATE, TARGET
from .plot_utils import save_fig
from .preprocessing import build_preprocessor


def cross_validate_ensembles(data, imbalanced, folds=(5, 10)):
    """Compare DT / Bagging / RF with StratifiedGroupKFold (no country in two folds)
    and plain StratifiedKFold (rows of one country can sit in different folds -> optimistic)."""
    models = make_models(data["features"], imbalanced)
    names = ["Decision Tree", "Bagging", "Random Forest"]
    X, y, groups = data["X_train"], data["y_train"], data["groups_train"]
    rows = []
    for k in folds:
        splitters = {
            "Grouped stratified (honest)": StratifiedGroupKFold(n_splits=k, shuffle=True, random_state=RANDOM_STATE),
            "Plain stratified (optimistic)": StratifiedKFold(n_splits=k, shuffle=True, random_state=RANDOM_STATE)}
        for sname, cv in splitters.items():
            for n in names:
                scores = cross_val_score(models[n], X, y, cv=cv, groups=groups, scoring="f1", n_jobs=1)
                rows.append({"Folds": k, "CV strategy": sname, "Model": n,
                             "Mean F1": scores.mean(), "Std F1": scores.std()})
    table = pd.DataFrame(rows).round(4)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)
    for ax, k in zip(axes, folds):
        sub = table[table.Folds == k]
        sns.barplot(data=sub, x="Model", y="Mean F1", hue="CV strategy", ax=ax, palette="Greens")
        ax.set(title=f"{k}-fold cross-validation (F1)", ylim=(0.5, 1.0))
    fig.tight_layout(); save_fig(fig, "ens_cv_comparison")
    return table


def regression_cv(train, features, folds=5):
    """Ordinary KFold vs GroupKFold for the multiple linear regression (R2 on training years)."""
    cols = features + ["year"]
    model = Pipeline([("prep", build_preprocessor(cols)), ("reg", LinearRegression())])
    X, y, g = train[cols], train[TARGET], train["country"]
    kf = cross_val_score(model, X, y, cv=KFold(folds, shuffle=True, random_state=RANDOM_STATE), scoring="r2")
    gk = cross_val_score(model, X, y, cv=GroupKFold(n_splits=folds), groups=g, scoring="r2")
    return pd.DataFrame([{"CV": f"KFold (k={folds}) - random rows", "Mean R2": kf.mean(), "Std R2": kf.std()},
                         {"CV": f"GroupKFold (k={folds}) - unseen countries", "Mean R2": gk.mean(), "Std R2": gk.std()}]).round(4)


def tune_random_forest(data, imbalanced, folds=5):
    """GridSearchCV vs RandomizedSearchCV over the same, laptop-friendly parameter space."""
    X, y, groups = data["X_train"], data["y_train"], data["groups_train"]
    cv = list(StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=RANDOM_STATE).split(X, y, groups))
    cw = "balanced" if imbalanced else None
    pipe = Pipeline([("prep", build_preprocessor(data["features"], scale=False)),
                     ("clf", RandomForestClassifier(class_weight=cw, random_state=RANDOM_STATE, n_jobs=-1))])
    space = {"clf__n_estimators": [100, 200], "clf__max_depth": [None, 10, 20],
             "clf__min_samples_leaf": [1, 2, 4], "clf__max_features": ["sqrt", 0.5]}
    out = {}
    t = time.time()
    grid = GridSearchCV(pipe, space, cv=cv, scoring="f1", n_jobs=1).fit(X, y)
    out["Grid"] = {"search": grid, "seconds": time.time() - t, "n_candidates": 36}
    t = time.time()
    rnd = RandomizedSearchCV(pipe, space, n_iter=12, cv=cv, scoring="f1", n_jobs=1,
                             random_state=RANDOM_STATE).fit(X, y)
    out["Randomized"] = {"search": rnd, "seconds": time.time() - t, "n_candidates": 12}
    table = pd.DataFrame([{"Search": k, "Candidates": v["n_candidates"], "Best CV F1": v["search"].best_score_,
                           "Seconds": v["seconds"], "Best parameters": str(v["search"].best_params_)}
                          for k, v in out.items()])
    table[["Best CV F1", "Seconds"]] = table[["Best CV F1", "Seconds"]].round(4)
    return out, table


def final_evaluation(data, candidates):
    """Pick the best model by CROSS-VALIDATION on training data only, then test once."""
    X, y, groups = data["X_train"], data["y_train"], data["groups_train"]
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    cv_scores = {n: cross_val_score(m, X, y, cv=cv, groups=groups, scoring="f1").mean()
                 for n, m in candidates.items() if n != "Tuned Random Forest"}
    return cv_scores


def feature_importance_plots(model, data, suffix="", label=""):
    """Impurity importance (tree models) and permutation importance on the untouched test set."""
    names = model.named_steps["prep"].get_feature_names_out()
    clf = model.named_steps["clf"]
    result = {}
    if hasattr(clf, "feature_importances_"):
        result["impurity"] = pd.Series(clf.feature_importances_, index=names).sort_values(ascending=False)
    perm = permutation_importance(model, data["X_test"], data["y_test"], n_repeats=5,
                                  random_state=RANDOM_STATE, scoring="f1")
    result["permutation"] = pd.Series(perm.importances_mean, index=data["features"]).sort_values(ascending=False)
    fig, axes = plt.subplots(1, len(result), figsize=(7 * len(result), 5))
    for ax, (k, s) in zip(np.atleast_1d(axes), result.items()):
        s.head(10).iloc[::-1].plot(kind="barh", ax=ax, color="#2e8b57")
        ax.set(title=f"Feature importance ({k}) {label}", xlabel="Importance")
    fig.tight_layout(); save_fig(fig, "ens_feature_importance" + suffix)
    return result


def final_confusion_plot(cm, name):
    fig, ax = plt.subplots(figsize=(4.5, 4))
    sns.heatmap(np.array(cm), annot=True, fmt="d", cmap="Greens", cbar=False, ax=ax,
                xticklabels=["Low", "High"], yticklabels=["Low", "High"])
    ax.set(title=f"Final model on untouched test set\n{name}", xlabel="Predicted", ylabel="Actual")
    fig.tight_layout(); save_fig(fig, "final_confusion_matrix")
