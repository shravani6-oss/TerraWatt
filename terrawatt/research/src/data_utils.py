"""Dataset loading and basic type cleaning (Module A, steps 1, 5, 7)."""
import re
import numpy as np
import pandas as pd
from .config import DATA_DIR, RENAME_MAP, REQUIRED_COLUMNS


class DataFormatError(Exception):
    """Raised when the CSV does not look like the Kaggle sustainable-energy dataset."""


def _norm(name):
    """Normalise a column name so small formatting differences do not matter."""
    text = str(name).replace("\\n", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


_RENAME_NORM = {_norm(k): v for k, v in RENAME_MAP.items()}


def find_default_csv():
    """Return the first CSV in the data/ folder, or None."""
    files = sorted(DATA_DIR.glob("*.csv"))
    return files[0] if files else None


def standardize_columns(df):
    """Rename raw Kaggle columns to short names and check required ones exist."""
    df = df.copy()
    df.columns = [_RENAME_NORM.get(_norm(c), _norm(c).replace(" ", "_")) for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DataFormatError(
            f"The CSV is missing required column(s): {missing}. Expected the Kaggle file "
            "'Global Data on Sustainable Energy' (columns such as 'Entity', 'Year', "
            "'Renewable energy share in the total final energy consumption (%)').")
    return df


def clean_types(df):
    """Whitespace -> NaN, strip thousand separators, coerce numbers, drop duplicates."""
    df = df.copy()
    report = {"rows_before": len(df)}
    df = df.replace(r"^\s*$", np.nan, regex=True)
    df["country"] = df["country"].astype(str).str.strip()
    for col in df.columns:
        if col == "country":
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            # e.g. density stored as text like "2,239"
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", "", regex=False),
                                    errors="coerce")
    df = df.dropna(subset=["year"])
    df["year"] = df["year"].astype(int)
    report["duplicates_removed"] = int(df.duplicated().sum())
    df = df.drop_duplicates().reset_index(drop=True)
    report["rows_after"] = len(df)
    return df, report


def load_dataset(source=None):
    """Load a CSV path / uploaded file-like object -> (clean dataframe, cleaning report)."""
    if source is None:
        source = find_default_csv()
        if source is None:
            raise FileNotFoundError(
                f"No CSV found in {DATA_DIR}. Download the Kaggle dataset and place the CSV "
                "in the 'data' folder (see README.md), or upload it in the dashboard.")
    try:
        raw = pd.read_csv(source)
    except Exception as exc:  # unreadable / not a CSV
        raise DataFormatError(f"Could not read the file as CSV: {exc}") from exc
    return clean_types(standardize_columns(raw))


def available_features(df, candidates):
    """Keep only candidate columns that exist in df."""
    return [c for c in candidates if c in df.columns]


def drop_sparse_columns(df, max_missing=0.5, protect=()):
    """Drop columns whose missing fraction exceeds max_missing. Returns (df, dropped list)."""
    frac = df.isna().mean()
    dropped = [c for c in df.columns if frac[c] > max_missing and c not in protect]
    return df.drop(columns=dropped), dropped
