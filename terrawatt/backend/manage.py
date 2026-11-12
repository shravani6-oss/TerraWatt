"""Management CLI:  python -m backend.manage <train|create-admin|seed-demo>"""
import argparse
import logging
import sys

from .app.config import Config


def cmd_train(_):
    from .app.ml.train import train_all
    cfg = Config()
    logging.basicConfig(level="INFO")
    card = train_all(cfg.DATA_CSV, cfg.MODELS_DIR)
    print("Trained:", card["regression"]["chosen"], "/", card["classification"]["chosen"])


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
    ca = sub.add_parser("create-admin")
    ca.add_argument("--email", required=True)
    ca.add_argument("--password", required=True)
    ca.add_argument("--name", default="Administrator")
    ca.set_defaults(fn=cmd_create_admin)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
