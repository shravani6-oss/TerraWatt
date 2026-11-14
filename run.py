"""Development entry point:  python run.py   (auto-trains models on first run)."""
import os
import sys

from backend.app import create_app
from backend.app.config import Config

if __name__ == "__main__":
    cfg = Config()
    if not (cfg.MODELS_DIR / "regressor.joblib").exists():
        print("No trained models found - training once (about 10-20 s)...")
        from backend.manage import cmd_train
        cmd_train(None)
    app = create_app()
    port = int(os.getenv("PORT", "5000"))
    print(f"TerraWatt running on http://127.0.0.1:{port}")
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=port, debug=cfg.ENV != "production" and "--no-debug" not in sys.argv,
            use_reloader=False)
