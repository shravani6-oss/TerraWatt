"""Module A: preprocessing helpers (imputation, encoding, scaling, missing-value plots)."""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import (FunctionTransformer, LabelEncoder, MinMaxScaler,
                                   OneHotEncoder, StandardScaler)
from .config import LOG_COLS


def safe_log1p(x):
    """log(1 + x) that never sees negative numbers (top-level so joblib can save it)."""
    return np.log1p(np.clip(x, 0, None))


def build_preprocessor(numeric_cols, categorical_cols=(), log_cols=LOG_COLS, scale=True):
    """ColumnTransformer: median-impute (+log) (+scale) numbers; mode-impute + one-hot categories.

    Meant to be the first step of a Pipeline, so it is fitted on training data only.
    """
    numeric_cols = list(numeric_cols)
    logged = [c for c in numeric_cols if c in log_cols]
    plain = [c for c in numeric_cols if c not in log_cols]

    def num_pipe(use_log):
        steps = [("impute", SimpleImputer(strategy="median"))]
        if use_log:
            steps.append(("log", FunctionTransformer(safe_log1p, feature_names_out="one-to-one")))
        if scale:
            steps.append(("scale", StandardScaler()))
        return Pipeline(steps)

    parts = []
    if plain:
        parts.append(("num", num_pipe(False), plain))
    if logged:
        parts.append(("num_log", num_pipe(True), logged))
    if categorical_cols:
        parts.append(("cat", Pipeline([
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore"))]), list(categorical_cols)))
    return ColumnTransformer(parts, verbose_feature_names_out=False)


def split_column_types(df):
    """Identify numerical and categorical columns."""
    num = df.select_dtypes(include="number").columns.tolist()
    cat = df.select_dtypes(exclude="number").columns.tolist()
    return num, cat


def inspect_dataset(df):
    """Return a text overview: head/tail, shape, dtypes, summary stats."""
    num, cat = split_column_types(df)
    lines = ["=== FIRST 5 ROWS ===", df.head().to_string(), "", "=== LAST 5 ROWS ===",
             df.tail().to_string(), "", f"Shape: {df.shape}", f"Columns: {list(df.columns)}", "",
             "=== DATA TYPES ===", df.dtypes.astype(str).to_string(), "",
             f"Numerical columns ({len(num)}): {num}", f"Categorical columns ({len(cat)}): {cat}",
             "", "=== SUMMARY STATISTICS ===", df.describe().T.to_string(),
             "", f"Years: {df['year'].min()} - {df['year'].max()}",
             f"Countries: {df['country'].nunique()}"]
    return "\n".join(lines)


def missing_summary(df):
    """Count and percentage of missing values per column."""
    out = pd.DataFrame({"missing_count": df.isna().sum(), "missing_pct": df.isna().mean() * 100})
    return out.sort_values("missing_pct", ascending=False).round(2)


def plot_missing_heatmap(df):
    fig, ax = plt.subplots(figsize=(11, 5))
    sns.heatmap(df.isna().T, cbar=False, cmap="viridis", yticklabels=True, xticklabels=False, ax=ax)
    ax.set_title("Missing values heatmap (yellow = missing)")
    ax.set_xlabel("Records (rows)"); ax.set_ylabel("Column")
    fig.tight_layout()
    return fig


def plot_missing_bar(df):
    ms = missing_summary(df)
    ms = ms[ms.missing_pct > 0].sort_values("missing_pct")
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(ms.index, ms.missing_pct, color="#2e8b57")
    ax.axvline(50, color="red", ls="--", label="50% drop threshold")
    ax.set_title("Missing values per column (%)"); ax.set_xlabel("Missing (%)"); ax.legend()
    fig.tight_layout()
    return fig


def scaling_demo(df, column="gdp_per_capita"):
    """Show Min-Max vs Standard scaling on one column."""
    values = df[[column]].dropna().head(8)
    mm = MinMaxScaler().fit(df[[column]].dropna())
    ss = StandardScaler().fit(df[[column]].dropna())
    out = values.copy()
    out["min_max (0 to 1)"] = mm.transform(values).ravel().round(4)
    out["standard (z-score)"] = ss.transform(values).ravel().round(4)
    return out


def label_encoding_demo(y_labels):
    """Label Encoding is applied only to an actual target (e.g. 'Low'/'High')."""
    enc = LabelEncoder().fit(y_labels)
    return dict(zip(enc.classes_, enc.transform(enc.classes_).tolist()))


def onehot_demo(df, col="country", n=4):
    sample = df[[col]].drop_duplicates().head(n)
    enc = OneHotEncoder(sparse_output=False).fit(sample)
    return pd.DataFrame(enc.transform(sample), columns=enc.get_feature_names_out(), index=sample[col])
