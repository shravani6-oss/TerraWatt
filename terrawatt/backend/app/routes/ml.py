from flask import Blueprint, current_app, jsonify, request

from ..errors import ApiError
from ..ml.pipeline import FEATURE_LABELS, SCENARIO_FEATURES
from ..schemas import PredictIn
from ..services.predictor import ModelsUnavailable
from .energy import country_arg

bp = Blueprint("ml", __name__, url_prefix="/api/ml")


def pred():
    return current_app.extensions["tw"].predictor


@bp.get("/models")
def models():
    p = pred()
    if p.error:
        raise ApiError(503, "models_unavailable", p.error)
    return jsonify(p.cards)


@bp.get("/clusters")
def clusters():
    p = pred()
    if p.error:
        raise ApiError(503, "models_unavailable", p.error)
    return jsonify(p.clusters)


@bp.get("/scenario-config")
def scenario_config():
    p = pred()
    ranges = p.cards.get("scenario_ranges", {})
    return jsonify({"features": [{"key": k, "label": FEATURE_LABELS[k], **ranges.get(k, {})} for k in SCENARIO_FEATURES]})


@bp.post("/predict")
def predict():
    body = PredictIn.model_validate(request.get_json(silent=True) or {})
    c = country_arg(body.country)
    unknown = [k for k in body.overrides if k not in SCENARIO_FEATURES]
    if unknown:
        raise ApiError(422, "validation_error", f"Unsupported inputs: {unknown}", {"allowed": SCENARIO_FEATURES})
    try:
        return jsonify(pred().predict(c, body.overrides))
    except ModelsUnavailable as exc:
        raise ApiError(503, "models_unavailable", str(exc))
