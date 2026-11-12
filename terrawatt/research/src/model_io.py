"""Module I: save / load models and metadata safely."""
import json
import joblib
from .config import MODELS_DIR, RESULTS_DIR


def save_model(model, name, meta=None):
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODELS_DIR / f"{name}.joblib")
    if meta is not None:
        (MODELS_DIR / f"{name}_meta.json").write_text(json.dumps(meta, indent=2, default=str))


def load_model(name):
    """Return (model, meta, error_message). Never raises for a missing/corrupt file."""
    path = MODELS_DIR / f"{name}.joblib"
    if not path.exists():
        return None, None, f"Model file '{path.name}' not found. Run `python train.py` first."
    try:
        model = joblib.load(path)
    except Exception as exc:
        return None, None, f"Could not load '{path.name}' ({exc}). Re-run `python train.py`."
    meta_path = MODELS_DIR / f"{name}_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return model, meta, None


def check_input_columns(row_df, expected):
    """Make sure every feature the saved model expects is present (added as NaN if blank)."""
    import numpy as np
    out = row_df.copy()
    for col in expected:
        if col not in out.columns:
            out[col] = np.nan      # the pipeline's imputer fills blanks with training medians
    return out[list(expected)]


def save_json(obj, name):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / name).write_text(json.dumps(obj, indent=2, default=str))


def load_json(name):
    path = RESULTS_DIR / name
    return json.loads(path.read_text()) if path.exists() else None
