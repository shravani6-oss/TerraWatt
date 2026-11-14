# Changelog

## v2.0
* **Dataset**: rebuilt for 2000–2025 (192 countries/territories) from OWID (Ember, Energy Institute, GCP) plus the World Bank/IEA series; per-indicator provenance catalogue, validation report, `build-data` command. Indicator-specific latest years; partial 2025 flagged; no forward-fill.
* **Renewables** page: source-wise generation, shares, growth, ranking, comparison, dominant source, movers.
* **Carbon calculator**: simple household mode (INR bill, LPG, vehicles, transit, flights, approximate answers, skips, estimated/actual flags, ranges, per person, benchmark, methodology) and advanced mode; versioned factors.
* **My Sustainability**: goals against a baseline month, comparable-month rules, badges, suggestions, DB persistence.
* **What-if lab**: exact electricity-mix engine + model estimate, presets, reset, comparison, PDF; robust model loading (auto-retrain, 503 with message, per-country config, reliability flags).
* **Model lab**: robust per-tab loading, Gaussian mixture added, explanations and examples.
* **Forecast** to 2030/35/40 with verified official targets where comparable.
* **UI**: removed decorative sparklines and duplicate stats; progressive disclosure; mobile layout fixes.
* **Tooling**: `manage.py doctor`, relaxed requirements + `requirements-tested.txt`, new test suites and `tests/e2e_v2.py` (replaces `e2e_smoke.py`).
