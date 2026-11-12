"""Module C: Simple and multiple linear regression with a chronological split."""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.dummy import DummyRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from .config import LABELS, TARGET, TEST_YEARS
from .plot_utils import save_fig
from .preprocessing import build_preprocessor


def regression_metrics(y_true, y_pred):
    mse = mean_squared_error(y_true, y_pred)
    return {"MAE": mean_absolute_error(y_true, y_pred), "MSE": mse,
            "RMSE": float(np.sqrt(mse)), "R2": r2_score(y_true, y_pred)}


def chronological_split(df, test_years=TEST_YEARS):
    """Train on earlier years, test on the most recent years (no future info in training)."""
    df = df.dropna(subset=[TARGET])
    cutoff = int(df.year.max()) - test_years
    return df[df.year <= cutoff].copy(), df[df.year > cutoff].copy(), cutoff


def best_single_feature(train, features):
    """Pick the feature most correlated (absolute) with the target - using TRAIN data only."""
    corr = train[features + [TARGET]].corr()[TARGET].drop(TARGET).abs()
    return corr.idxmax(), corr.sort_values(ascending=False)


def build_models(features, simple_feature):
    imputer = lambda: SimpleImputer(strategy="median")
    return {
        "Baseline (predict train mean)": DummyRegressor(strategy="mean"),
        "Simple Linear Regression": Pipeline([("prep", build_preprocessor([simple_feature], scale=False, log_cols=[])),
                                              ("reg", LinearRegression())]),
        "Multiple Linear Regression": Pipeline([("prep", build_preprocessor(features + ["year"])),
                                                ("reg", LinearRegression())]),
        "Multiple LR + country (one-hot)": Pipeline([("prep", build_preprocessor(features + ["year"], ["country"])),
                                                     ("reg", LinearRegression())]),
    }


def run_regression(df, features):
    """Train/evaluate regression models. Returns dict with results, models and plots."""
    train, test, cutoff = chronological_split(df)
    simple_feature, corr = best_single_feature(train, features)
    models = build_models(features, simple_feature)
    rows, preds = [], {}
    for name, model in models.items():
        cols = {"Simple Linear Regression": [simple_feature],
                "Multiple Linear Regression": features + ["year"],
                "Multiple LR + country (one-hot)": features + ["year", "country"]}.get(name, features)
        model.fit(train[cols], train[TARGET])
        p = model.predict(test[cols])
        preds[name] = p
        rows.append({"Model": name, **regression_metrics(test[TARGET], p)})
    table = pd.DataFrame(rows).round(4)

    # ---- plots ----
    simple = models["Simple Linear Regression"]
    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.scatter(train[simple_feature], train[TARGET], s=8, alpha=.25, color="grey", label="Train")
    ax.scatter(test[simple_feature], test[TARGET], s=10, alpha=.6, color="#2e8b57", label="Test (actual)")
    xs = pd.DataFrame({simple_feature: np.linspace(train[simple_feature].min(), train[simple_feature].max(), 100)})
    ax.plot(xs[simple_feature], simple.predict(xs), color="red", lw=2.5, label="Regression line")
    ax.set(title="Simple linear regression line", xlabel=LABELS[simple_feature], ylabel=LABELS[TARGET])
    ax.legend(); fig.tight_layout()
    save_fig(fig, "reg_simple_line")

    best_name = table.sort_values("RMSE").iloc[0]["Model"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    y = test[TARGET].values
    for ax, name in zip(axes, ["Multiple Linear Regression", best_name]):
        ax.scatter(y, preds[name], s=10, alpha=.5, color="#2e8b57")
        lim = [0, max(y.max(), np.nanmax(preds[name]))]
        ax.plot(lim, lim, "r--", label="Perfect prediction")
        ax.set(title=f"Actual vs predicted: {name}", xlabel="Actual share (%)", ylabel="Predicted share (%)")
        ax.legend()
    fig.tight_layout(); save_fig(fig, "reg_actual_vs_pred")

    fig, ax = plt.subplots(figsize=(8, 4.5))
    tmp = test[["year"]].assign(actual=y, predicted=preds[best_name]).groupby("year").mean()
    ax.plot(tmp.index, tmp.actual, "o-", label="Actual (mean of countries)")
    ax.plot(tmp.index, tmp.predicted, "s--", label=f"Predicted ({best_name})")
    ax.set(title="Held-out years: average actual vs predicted", xlabel="Year", ylabel="Share (%)")
    ax.legend(); fig.tight_layout(); save_fig(fig, "reg_test_years")

    sample = test[["country", "year"]].assign(actual=y, predicted=np.round(preds[best_name], 2)).head(20)
    return {"table": table, "models": models, "simple_feature": simple_feature,
            "feature_correlations": corr, "cutoff_year": cutoff, "n_train": len(train),
            "n_test": len(test), "best_name": best_name, "sample_predictions": sample,
            "features": features, "train": train, "test": test}
