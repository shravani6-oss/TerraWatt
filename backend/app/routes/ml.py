from flask import Blueprint, Response, current_app, jsonify, request

from ..errors import ApiError
from ..schemas import PredictIn
from ..services import reports
from ..services import scenario as mixsim
from ..services.predictor import ModelsUnavailable, ScenarioInputError
from .energy import country_arg

bp = Blueprint("ml", __name__, url_prefix="/api/ml")


def pred():
    return current_app.extensions["tw"].predictor


def _need_models():
    p = pred()
    if p.error:
        raise ApiError(503, "models_unavailable", p.error)
    return p


@bp.get("/status")
def status():
    """Model health for the UI / doctor: versions, load state and whether artefacts were rebuilt at startup."""
    p = pred()
    return jsonify({"ok": p.error is None, "error": p.error, "retrained_at_startup": p.retrained,
                    "trained_at": p.cards.get("trained_at"), "env": p.cards.get("env")})


@bp.get("/models")
def models():
    return jsonify(_need_models().cards)


@bp.get("/clusters")
def clusters():
    return jsonify(_need_models().clusters)


@bp.get("/scenario-config")
def scenario_config():
    p = _need_models()
    c = country_arg(request.args.get("country", "India"))
    try:
        return jsonify(p.config(c))
    except ScenarioInputError as exc:
        raise ApiError(422, "scenario_unavailable", str(exc))


def _run(body: PredictIn):
    p = _need_models()
    c = country_arg(body.country)
    try:
        return p.predict(c, body.overrides, body.mix or None, body.access_gap_pct)
    except ModelsUnavailable as exc:
        raise ApiError(503, "models_unavailable", str(exc))
    except ScenarioInputError as exc:
        raise ApiError(422, "invalid_scenario", str(exc))


@bp.post("/predict")
def predict():
    return jsonify(_run(PredictIn.model_validate(request.get_json(silent=True) or {})))


@bp.post("/scenario-report")
def scenario_report():
    body = PredictIn.model_validate(request.get_json(silent=True) or {})
    result = _run(body)
    pdf = reports.scenario_pdf(result, current_app.extensions["tw"].data.provenance())
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=terrawatt-scenario-{result['country'].replace(' ', '_')}.pdf"})
