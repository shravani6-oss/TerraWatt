# Architecture notes

**Request path.** `create_app()` builds config → initialises SQLite → loads the dataset once (pandas, cached) → loads joblib models → registers blueprints. `before_request` enforces the CSRF header on mutating `/api` calls; `after_request` adds CSP and security headers and cache policy (public data cacheable 60 s, anything user-specific `no-store`).

**Data layer.** `EnergyData` normalises the CSV's awkward headers, coerces numerics, and derives: total generation, renewable share of electricity, estimated grid intensity (mix × lifecycle factors), population (density × area) and CO₂ per person. Latest-value lookups are per metric, because indicators end in different years (e.g. renewable share 2019, electricity access 2020).

**Forecast engine.** Series are densified (interior gaps interpolated). Candidates: persistence, 8-year linear, damped Holt, linear+damped ensemble. Damped parameters are grid-searched on calibration origins only. Errors are normalised by each series' recent volatility; the 10th/90th percentiles per horizon (made monotone) give 80% intervals. Coverage is measured on later, unseen origins. CO₂ is modelled in log space.

**ML training.** Regression: chronological split, model picked on an inner validation window, scored once on test years, then refit on all labelled data for serving. Classification: GroupShuffleSplit by country, StratifiedGroupKFold F1 for selection. Clustering: K-Means with silhouette-selected K in 3-6, PCA for display, "intervention priority" = mean percentile deficit across five indicators.

**Frontend.** `main.js` owns the hash router and app shell; pages are lazily imported ES modules returning DOM nodes built with a tiny `h()` helper (no `innerHTML` with user data). `charts.js` renders responsive SVG with CSS-variable colours so light/dark need no re-render logic beyond variable swaps.

**Known limits.** In-memory throttle/cache (single process); SQLite (swap for Postgres to scale writes); dataset is static, so "alerts" evaluate against the newest reported year and forecasts rather than a live feed.

## v2 additions
* `backend/app/dataset/build.py` builds `data/processed/terrawatt_dataset.csv` (+ `indicator_catalog.json`, `validation_report.json`) from `data/raw/*`; `python -m backend.manage build-data`. Each indicator keeps its own latest year (`EnergyData.year_for`).
* `services/scenario.py` is the exact electricity-mix accounting; `services/predictor.py` combines it with the trained models (auto-retrain on version mismatch, `ModelsUnavailable` → 503).
* `services/carbon.py` (factors versioned `tw-carbon-2`), `services/entries.py` (entries store raw `inputs_json` and are re-evaluated on read) and `services/goals.py` (comparable-month rules, badges) back `routes/footprint.py` and `routes/goals.py`.
* `python -m backend.manage doctor` verifies environment, data, models, DB schema and frontend files.
