"""Management CLI:  python -m backend.manage <train|build-data|doctor|create-admin>"""
import argparse
import os
import logging
import sys

from .app.config import Config


def cmd_train(_):
    from .app.ml.train import train_all
    cfg = Config()
    logging.basicConfig(level="INFO")
    card = train_all(cfg.DATA_CSV, cfg.MODELS_DIR)
    print("Trained:", card["regression"]["chosen"], "/", card["classification"]["chosen"])


def cmd_build_data(a):
    """Rebuild + validate the processed dataset from the raw extracts (or fresh OWID files)."""
    import json
    from pathlib import Path
    from .app.dataset.build import build
    root = Path(__file__).resolve().parent.parent
    src = json.loads((root / "data/raw/SOURCES.json").read_text())
    rep = build(root / "data/global-data-on-sustainable-energy.csv",
                Path(a.owid_energy or root / "data/raw/owid-energy-extract.csv"),
                Path(a.owid_co2 or root / "data/raw/owid-co2-extract.csv"),
                root / "data/processed", {k: v for k, v in src.items() if k != "note"})
    print("OK" if rep["ok"] else "FAILED", "|", rep["checks"].get("countries"), "countries |",
          len(rep["errors"]), "errors |", len(rep["warnings"]), "warnings")
    for e in rep["errors"]:
        print("  ERROR:", e)
    if not rep["ok"]:
        sys.exit(1)


def cmd_doctor(_):
    """Environment self-check: versions, dataset, models, a sample prediction/forecast, database, frontend files."""
    import importlib
    import json
    import platform
    import tempfile
    from pathlib import Path
    ok = True

    def line(good, name, detail=""):
        nonlocal ok
        ok = ok and good
        print(("  OK    " if good else "  FAIL  ") + name + (f" — {detail}" if detail else ""))
    print(f"Python {platform.python_version()}")
    line(sys.version_info >= (3, 10), "Python >= 3.10")
    for mod in ("flask", "pandas", "numpy", "sklearn", "joblib", "jwt", "pydantic", "reportlab"):
        try:
            m = importlib.import_module(mod)
            from importlib import metadata
            dist = {"sklearn": "scikit-learn", "jwt": "PyJWT"}.get(mod, mod)
            line(True, mod, metadata.version(dist))
        except Exception as exc:
            line(False, mod, f"{exc.__class__.__name__}: {exc}")
    cfg = Config()
    from .app.services.data_service import get_dataset
    try:
        d = get_dataset(str(cfg.DATA_CSV))
        line(True, "dataset", f"{len(d.countries)} countries, {d.first_year}-{d.last_year}, headline year {d.headline_year}")
        rep = Path(cfg.DATA_CSV).parent / "validation_report.json"
        line(rep.exists() and json.loads(rep.read_text()).get("ok") is True, "dataset validation report")
    except Exception as exc:
        line(False, "dataset", f"{exc.__class__.__name__}: {exc}")
        sys.exit(1)
    from .app.services.predictor import Predictor
    p = Predictor(cfg.MODELS_DIR, d, cfg.DATA_CSV, auto_retrain=False)
    line(p.error is None, "models load", p.error or f"trained {p.cards.get('trained_at')} with scikit-learn {p.cards.get('env', {}).get('sklearn')}")
    if p.error is None:
        r = p.predict("India", {"electricity_access": 100}, {"solar_mult": 2})
        line(0 <= r["scenario"]["share"] <= 100, "sample what-if prediction", f"India {r['baseline']['share']} -> {r['scenario']['share']}")
    from .app.services.forecast import ForecastEngine
    try:
        f = ForecastEngine(d).forecast("India", "renewable_elec_share", 2030)
        line(bool(f["forecast"]), "sample forecast", f"{len(f['forecast'])} years")
    except Exception as exc:
        line(False, "sample forecast", f"{exc.__class__.__name__}: {exc}")
    from .app.db import connect, init_db
    with tempfile.TemporaryDirectory() as t:
        init_db(Path(t) / "x.db")
        tables = {r["name"] for r in connect(Path(t) / "x.db").execute("SELECT name FROM sqlite_master WHERE type='table'")}
        line({"users", "footprint_entries", "goals", "goal_progress", "badges"} <= tables, "database schema")
    line(os.environ.get("SECRET_KEY") is not None or cfg.ENV != "production", "SECRET_KEY set (required in production)")
    missing = [f for f in ("index.html", "css/app.css", "js/main.js") if not (cfg.FRONTEND_DIR / f).exists()]
    line(not missing, "frontend files", ", ".join(missing))
    print("\nAll checks passed." if ok else "\nSome checks failed.")
    sys.exit(0 if ok else 1)


def cmd_create_admin(a):
    from .app import create_app
    from .app.db import connect
    from .app.security import hash_password, validate_password_strength
    validate_password_strength(a.password)
    app = create_app(TESTING=True)
    conn = connect(app.config["DATABASE_PATH"])
    conn.execute("INSERT INTO users (email, name, password_hash, role) VALUES (?,?,?, 'admin') "
                 "ON CONFLICT(email) DO UPDATE SET role='admin', password_hash=excluded.password_hash",
                 (a.email.lower(), a.name, hash_password(a.password)))
    conn.commit()
    print(f"Admin ready: {a.email}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="backend.manage")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("train").set_defaults(fn=cmd_train)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    bd = sub.add_parser("build-data")
    bd.add_argument("--owid-energy")
    bd.add_argument("--owid-co2")
    bd.set_defaults(fn=cmd_build_data)
    ca = sub.add_parser("create-admin")
    ca.add_argument("--email", required=True)
    ca.add_argument("--password", required=True)
    ca.add_argument("--name", default="Administrator")
    ca.set_defaults(fn=cmd_create_admin)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
