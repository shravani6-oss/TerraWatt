"""Module D: binary classification of high vs low renewable-energy adoption."""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.ensemble import BaggingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, precision_score,
                             recall_score)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier
from .config import RANDOM_STATE, TARGET
from .plot_utils import save_fig
from .preprocessing import build_preprocessor


def make_classification_data(df, features, test_size=0.2):
    """Country-grouped hold-out split + training-only median threshold.

    * All rows of a country go to EITHER train or test (a country's years are very similar,
      so a random row split would leak information and inflate scores).
    * The 'High' threshold is the TRAINING median of renewable share (no test information).
    A stratified split is not used for the hold-out because the label depends on a threshold
    computed from the training set (circular); stratification IS used in cross-validation.
    """
    data = df.dropna(subset=[TARGET]).reset_index(drop=True)
    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=RANDOM_STATE)
    tr_idx, te_idx = next(gss.split(data, groups=data["country"]))
    train, test = data.iloc[tr_idx].copy(), data.iloc[te_idx].copy()
    threshold = float(train[TARGET].median())
    for d in (train, test):
        d["label"] = (d[TARGET] > threshold).astype(int)
        d["label_name"] = np.where(d["label"] == 1, "High", "Low")
    return {"train": train, "test": test, "threshold": threshold, "features": features,
            "X_train": train[features], "y_train": train["label"].values,
            "X_test": test[features], "y_test": test["label"].values,
            "groups_train": train["country"].values}


def class_balance(y):
    counts = pd.Series(y).value_counts().sort_index()
    return {"Low(0)": int(counts.get(0, 0)), "High(1)": int(counts.get(1, 0)),
            "ratio_majority_to_minority": float(counts.max() / max(counts.min(), 1))}


def make_models(features, imbalanced=False):
    """Pipelines: scaling only for distance/linear models; trees need no scaling."""
    cw = "balanced" if imbalanced else None
    def pipe(clf, scale):
        return Pipeline([("prep", build_preprocessor(features, scale=scale)), ("clf", clf)])
    return {
        "Logistic Regression": pipe(LogisticRegression(max_iter=2000, class_weight=cw, random_state=RANDOM_STATE), True),
        "KNN (k=5)": pipe(KNeighborsClassifier(n_neighbors=5), True),
        "Gaussian Naive Bayes": pipe(GaussianNB(), True),
        "Decision Tree": pipe(DecisionTreeClassifier(max_depth=8, class_weight=cw, random_state=RANDOM_STATE), False),
        "Bagging": pipe(BaggingClassifier(estimator=DecisionTreeClassifier(random_state=RANDOM_STATE),
                                          n_estimators=50, random_state=RANDOM_STATE, n_jobs=-1), False),
        "Random Forest": pipe(RandomForestClassifier(n_estimators=200, class_weight=cw,
                                                     random_state=RANDOM_STATE, n_jobs=-1), False),
    }


def evaluate_classifier(model, X, y):
    pred = model.predict(X)
    return {"Accuracy": accuracy_score(y, pred), "Precision": precision_score(y, pred, zero_division=0),
            "Recall": recall_score(y, pred, zero_division=0), "F1": f1_score(y, pred, zero_division=0),
            "confusion_matrix": confusion_matrix(y, pred, labels=[0, 1]).tolist()}


def run_classification(data):
    balance = class_balance(data["y_train"])
    imbalanced = balance["ratio_majority_to_minority"] > 1.5
    models = make_models(data["features"], imbalanced)
    rows, cms = [], {}
    for name, model in models.items():
        model.fit(data["X_train"], data["y_train"])
        res = evaluate_classifier(model, data["X_test"], data["y_test"])
        cms[name] = res.pop("confusion_matrix")
        rows.append({"Model": name, **res})
    table = pd.DataFrame(rows).round(4)

    # plots
    metrics = ["Accuracy", "Precision", "Recall", "F1"]
    fig, ax = plt.subplots(figsize=(11, 5))
    table.set_index("Model")[metrics].plot(kind="bar", ax=ax, width=.8, colormap="Greens")
    ax.set(title="Classification model performance (held-out countries)", ylabel="Score", ylim=(0, 1.05))
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right"); fig.tight_layout()
    save_fig(fig, "clf_model_comparison")
    fig, axes = plt.subplots(2, 3, figsize=(13, 8))
    for ax, (name, cm) in zip(axes.ravel(), cms.items()):
        sns.heatmap(np.array(cm), annot=True, fmt="d", cmap="Greens", cbar=False, ax=ax,
                    xticklabels=["Low", "High"], yticklabels=["Low", "High"])
        ax.set(title=name, xlabel="Predicted", ylabel="Actual")
    fig.tight_layout(); save_fig(fig, "clf_confusion_matrices")
    return {"table": table, "models": models, "confusion_matrices": cms, "balance": balance,
            "imbalanced": imbalanced, "threshold": data["threshold"]}
