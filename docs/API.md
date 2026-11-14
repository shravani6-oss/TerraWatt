# TerraWatt REST API

Base path `/api`. JSON in/out. Errors always look like `{"error": {"code", "message", "details?"}}` (400 bad request, 401 unauthenticated, 403 forbidden/CSRF, 404, 409, 422 validation, 429 throttled, 503 models missing).
Auth: `POST /auth/login` sets an HttpOnly `tw_session` cookie. **All POST/PUT/PATCH/DELETE requests must send `X-Requested-With: TerraWatt`.** 🔒 = sign-in required, 🛡 = admin.

## Public data
| Method & path | Notes |
|---|---|
| `GET /health` | status, row count, models loaded |
| `GET /meta` | countries, years, metric catalogue (`derived`, `forecastable`), provenance |
| `GET /overview?year=` | global KPIs, movers, leaders |
| `GET /trend/global` | yearly global series (mix, shares, TWh, CO₂) |
| `GET /rankings?metric=&year=&q=&sort=asc\|desc&limit=` | ranked countries with YoY change |
| `GET /map?metric=&year=` | points with lat/lon and min/max |
| `GET /countries/{name}` | profile: cards (rank, percentile, 1y/5y change), mix, series, peers, cluster, recommendations |
| `GET /compare?countries=a,b,c&metric=` | 1-5 countries |
| `GET /records?q=&year=&sort=&order=&page=&per_page=` | dataset explorer |
| `GET /forecast/{name}?metric=&to=&target=` | history, forecast with 80% interval, model card, target crossing |
| `GET /forecast-quality?metric=` | full backtest report |

## Renewables, availability, targets
`GET /renewables/global?year=` source-wise global generation, shares and growth · `GET /renewables/ranking?source=&year=&metric=` · `GET /renewables/dominant` dominant source per country · `GET /renewables/country/{name}` · `GET /availability/{name}` per-indicator years and gaps · `GET /targets` verified official targets (forecast responses include `official_target` with a comparability label).
`/meta` metrics carry `latest_year`, `default_year` and `source`; `provenance` holds the per-indicator catalogue. Year arguments outside the dataset range return 422.

## ML / What-if
`GET /ml/status` (loaded? versions, reason if not) · `GET /ml/models` model cards (regression, classification, clustering, gmm) · `GET /ml/clusters` · `GET /ml/scenario-config?country=` baseline values, ranges, electricity mix, presets, reliability · `POST /ml/predict` `{country, overrides?, mix?, access_gap_pct?}` → baseline vs scenario share, high-adopter probability, per-change effects, mix accounting · `POST /ml/scenario-report` → PDF. Returns 503 with an actionable message when models are unavailable and 422 for out-of-range inputs.

## Carbon
`GET /footprint/factors` (tariff presets, factor version, vehicle/flight options) · `POST /footprint/estimate` (public) with `mode: "simple"` (`household_size`, `electricity{bill_inr,tariff_inr_per_kwh|kwh,renewable_pct}`, `cooking{type,per_month}`, `vehicles[]`, `transit`, `flights{frequency}`, `other`) or `mode: "advanced"` (`electricity_kwh, gas_m3, lpg_kg, car_km, flight_km, renewable_pct`) → total, range, per person, categories, items with actual/estimated basis, benchmark, recommendations.
🔒 `GET /footprint/entries`, `POST /footprint/entries` (upsert per month; returns `new_badges`), `DELETE /footprint/entries/{id}`, `GET /footprint/summary`, `GET /footprint/export.csv`.

## Goals (🔒)
`GET /goals/progress` (goal, baseline, current, target, reduction, remaining, progress %, history, excluded months with reasons, badges, recommendations) · `POST /goals` `{target_pct | target_kg, baseline_period}` · `DELETE /goals/active`.

## Auth & account
`POST /auth/register` · `POST /auth/login` · `POST /auth/logout` · `GET /auth/me` · 🔒 `PUT /auth/password` · 🔒 `PATCH /users/me` · 🔒 `DELETE /users/me`.

## Alerts (🔒)
`GET|POST /alerts/rules` (`condition`: below · above · yoy_drop · forecast_below + `year`) · `PATCH|DELETE /alerts/rules/{id}` · `POST /alerts/evaluate` · `GET|DELETE /notifications` · `POST /notifications/read` · `GET|POST /watchlist` · `DELETE /watchlist/{country}`.

## Export
`GET /export/rankings.csv?metric=&year=` · `GET /export/country/{name}.csv` · `GET /export/country/{name}.pdf`.

## Admin (🛡)
`GET /admin/stats` · `GET /admin/users?q=&page=` · `PATCH /admin/users/{id}` `{role?, is_active?}` · `GET /admin/audit` · `POST /admin/models/reload`.

### Example
```bash
curl localhost:5000/api/forecast/India?metric=renewable_share\&to=2030\&target=40
curl -c jar -H 'X-Requested-With: TerraWatt' -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"Str0ngPass1"}' localhost:5000/api/auth/login
```
