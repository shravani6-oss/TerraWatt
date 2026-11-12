"""Backtested time-series forecasting.

Design goals: honesty over flash. Every forecast ships with
  * the method that won a rolling-origin backtest across ALL countries,
  * empirical prediction intervals calibrated on earlier origins and checked on later ones,
  * a flag telling the UI which forecast years lie beyond the validated horizon.

Candidate methods (pure NumPy, no heavy dependencies):
  naive      - repeat the last observation
  linear     - OLS line through the last `window` observations
  damped     - Holt's damped-trend exponential smoothing (params tuned on the backtest)
  ensemble   - mean of linear and damped
"""
from __future__ import annotations

import itertools
import math
import threading
from dataclasses import dataclass

import numpy as np

from .data_service import METRICS, EnergyData

MAX_BACKTEST_H = 5
MIN_HISTORY = 8
LOG_METRICS = {"co2_kt"}
METHODS = ["naive", "linear", "damped", "ensemble"]


def _fill(years: np.ndarray, vals: np.ndarray) -> np.ndarray:
    """Dense yearly array from first to last year; interior gaps are linearly interpolated."""
    full = np.arange(years[0], years[-1] + 1)
    return np.interp(full, years, vals)


def f_naive(y, h):
    return np.full(h, y[-1])


def f_linear(y, h, window=8):
    yy = y[-window:]
    x = np.arange(len(yy))
    slope, icpt = np.polyfit(x, yy, 1)
    return icpt + slope * (len(yy) - 1 + np.arange(1, h + 1))


def f_damped(y, h, alpha=0.5, beta=0.2, phi=0.9):
    level, trend = y[0], (y[1] - y[0])
    for t in range(1, len(y)):
        prev_l, prev_b = level, trend
        level = alpha * y[t] + (1 - alpha) * (prev_l + phi * prev_b)
        trend = beta * (level - prev_l) + (1 - beta) * phi * prev_b
    steps = np.cumsum(phi ** np.arange(1, h + 1))
    return level + steps * trend


@dataclass
class DampedParams:
    alpha: float = 0.5
    beta: float = 0.2
    phi: float = 0.9


def run_method(name: str, y: np.ndarray, h: int, dp: DampedParams) -> np.ndarray:
    if name == "naive":
        return f_naive(y, h)
    if name == "linear":
        return f_linear(y, h)
    if name == "damped":
        return f_damped(y, h, dp.alpha, dp.beta, dp.phi)
    if name == "ensemble":
        return (f_linear(y, h) + f_damped(y, h, dp.alpha, dp.beta, dp.phi)) / 2
    raise ValueError(name)


def _volatility(y: np.ndarray) -> float:
    d = np.diff(y[-8:])
    return float(np.std(d)) if len(d) >= 2 else 0.0


class ForecastEngine:
    def __init__(self, data: EnergyData):
        self.data = data
        self._cache: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- helpers
    def _prep(self, country: str, metric: str):
        years, vals = self.data.series_array(country, metric)
        if len(years) < MIN_HISTORY:
            return None
        y = _fill(years, vals)
        if metric in LOG_METRICS:
            y = np.log(np.clip(y, 1e-6, None))
        return int(years[0]), int(years[-1]), y

    @staticmethod
    def _inverse(metric: str, arr):
        arr = np.asarray(arr, dtype=float)
        if metric in LOG_METRICS:
            return np.exp(arr)
        return arr

    @staticmethod
    def _clip(metric: str, arr):
        arr = np.asarray(arr, dtype=float)
        if METRICS[metric].bounded_pct:
            return np.clip(arr, 0, 100)
        return np.clip(arr, 0, None)

    # ---------------------------------------------------------------- backtest
    def backtest(self, metric: str) -> dict:
        with self._lock:
            if metric in self._cache:
                return self._cache[metric]
        series = {}
        for c in self.data.countries:
            p = self._prep(c, metric)
            if p:
                series[c] = p
        if not series:
            raise ValueError(f"No series long enough to backtest {metric}")
        last_year = max(p[1] for p in series.values())
        origins = list(range(last_year - 10, last_year))        # e.g. 2009 .. 2018
        split = last_year - 5                                  # calibration origins <= split < validation origins
        cal_origins = [o for o in origins if o <= split]
        val_origins = [o for o in origins if o > split]

        def collect(origin_list, dp, methods=METHODS):
            """errors[method][h] -> list of (error, volatility)."""
            out = {m: {h: [] for h in range(1, MAX_BACKTEST_H + 1)} for m in methods}
            for c, (y0, y1, y) in series.items():
                for o in origin_list:
                    if o < y0 + MIN_HISTORY - 1 or o >= y1:
                        continue
                    hist = y[: o - y0 + 1]
                    vol = _volatility(hist)
                    for h in range(1, min(MAX_BACKTEST_H, y1 - o) + 1):
                        actual = y[o - y0 + h]
                        for m in methods:
                            fc = run_method(m, hist, h, dp)[-1]
                            out[m][h].append((actual - fc, vol))
            return out

        # --- tune damped parameters on calibration origins (global, not per-country)
        best_dp, best_mae = DampedParams(), math.inf
        for a, b, phi in itertools.product((0.3, 0.5, 0.8), (0.1, 0.2, 0.4), (0.8, 0.9, 0.98)):
            dp = DampedParams(a, b, phi)
            errs = collect(cal_origins, dp, ("damped",))["damped"]
            mae = np.mean([abs(e) for h in errs.values() for e, _ in h]) if any(errs.values()) else math.inf
            if mae < best_mae:
                best_dp, best_mae = dp, mae
        cal = collect(cal_origins, best_dp)
        val = collect(val_origins, best_dp)

        def mae_table(errs):
            return {m: {str(h): (float(np.mean([abs(e) for e, _ in v])) if v else None) for h, v in hs.items()}
                    for m, hs in errs.items()}

        def overall(errs):
            return {m: float(np.mean([abs(e) for v in hs.values() for e, _ in v])) for m, hs in errs.items()}

        cal_mae, val_mae = overall(cal), overall(val)
        best = min(cal_mae, key=cal_mae.get)                    # selection uses calibration origins only
        # --- normalised-error quantiles for intervals (calibrated on calibration origins)
        vols = [v for hs in cal[best].values() for _, v in hs if v > 0]
        floor = max(0.05 * float(np.median(vols)), 1e-6) if vols else 1e-6
        q = {}
        for h, pairs in cal[best].items():
            z = np.array([e / max(v, floor) for e, v in pairs])
            q[h] = (float(np.quantile(z, 0.10)), float(np.quantile(z, 0.90)))
        lows = np.minimum.accumulate([q[h][0] for h in sorted(q)])   # widen monotonically with horizon
        highs = np.maximum.accumulate([q[h][1] for h in sorted(q)])
        quant = {h: (float(lows[h - 1]), float(highs[h - 1])) for h in sorted(q)}
        # --- honest coverage on validation origins
        inside = total = 0
        for h, pairs in val[best].items():
            lo, hi = quant[h]
            for e, v in pairs:
                z = e / max(v, floor)
                inside += lo <= z <= hi
                total += 1
        coverage = inside / total if total else None
        result = {
            "metric": metric, "method": best, "damped": best_dp.__dict__, "floor": floor, "quantiles": quant,
            "n_series": len(series), "last_year": last_year,
            "origins": {"calibration": [cal_origins[0], cal_origins[-1]], "validation": [val_origins[0], val_origins[-1]]},
            "mae_calibration": cal_mae, "mae_validation": val_mae,
            "mae_by_horizon_validation": mae_table(val), "interval_coverage_validation": coverage,
            "n_validation_forecasts": total, "log_scale": metric in LOG_METRICS,
            "skill_vs_naive": (1 - val_mae[best] / val_mae["naive"]) if val_mae["naive"] else None,
        }
        with self._lock:
            self._cache[metric] = result
        return result

    # ---------------------------------------------------------------- forecast
    def forecast(self, country: str, metric: str, horizon_to: int = 2030, target: float | None = None) -> dict:
        bt = self.backtest(metric)
        prep = self._prep(country, metric)
        if prep is None:
            raise ValueError(f"Not enough history for {country} / {metric} (need {MIN_HISTORY}+ observations).")
        y0, y1, y = prep
        horizon = max(1, min(horizon_to - y1, 15))
        dp = DampedParams(**bt["damped"])
        med = run_method(bt["method"], y, horizon, dp)
        vol = max(_volatility(y), bt["floor"])
        quant = bt["quantiles"]
        rows = []
        for h in range(1, horizon + 1):
            if h in quant:
                lo_q, hi_q = quant[h]
            else:   # beyond the validated horizon: widen with sqrt(h) and flag it
                scale = math.sqrt(h / MAX_BACKTEST_H)
                lo_q, hi_q = quant[MAX_BACKTEST_H][0] * scale, quant[MAX_BACKTEST_H][1] * scale
            m, lo, hi = med[h - 1], med[h - 1] + lo_q * vol, med[h - 1] + hi_q * vol
            rows.append({"year": y1 + h, "value": m, "lo": lo, "hi": hi, "validated": h <= MAX_BACKTEST_H})
        # back-transform & clip
        for r in rows:
            for k in ("value", "lo", "hi"):
                r[k] = round(float(self._clip(metric, self._inverse(metric, r[k]))), 3)
        hist = self.data.series(country, metric)
        slope = None
        yrs, vals = self.data.series_array(country, metric)
        if len(yrs) >= 5:
            slope = float(np.polyfit(yrs[-5:], vals[-5:], 1)[0])
        crossing = None
        if target is not None:
            last_val = hist[-1]["value"]
            if last_val is not None and last_val >= target:
                crossing = {"status": "already_reached", "year": hist[-1]["year"]}
            else:
                hit = next((r for r in rows if r["value"] >= target), None)
                crossing = ({"status": "forecast", "year": hit["year"]} if hit else {"status": "not_within_horizon"})
        m = METRICS[metric]
        return {
            "country": country, "metric": metric, "label": m.label, "unit": m.unit,
            "history": hist, "forecast": rows, "last_observed_year": y1,
            "recent_slope_per_year": round(slope, 3) if slope is not None else None,
            "model": {"method": bt["method"], "damped": bt["damped"] if bt["method"] in ("damped", "ensemble") else None,
                      "n_countries_backtested": bt["n_series"],
                      "validation_mae": bt["mae_validation"][bt["method"]],
                      "validation_mae_naive": bt["mae_validation"]["naive"],
                      "skill_vs_naive": bt["skill_vs_naive"],
                      "interval": "80%", "interval_coverage_validation": bt["interval_coverage_validation"],
                      "log_scale": bt["log_scale"], "validated_horizon_years": MAX_BACKTEST_H},
            "target_crossing": crossing,
            "caveat": ("Statistical extrapolation of past trends, not a policy or physics model. "
                       f"Years beyond {y1 + MAX_BACKTEST_H} exceed the validated backtest horizon."),
        }
