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

## ML
`GET /ml/models` model cards · `GET /ml/clusters` · `GET /ml/scenario-config` slider ranges · `POST /ml/predict` `{country, overrides:{electricity_access: 100}}` → baseline vs scenario share, high-adopter probability, per-change effects.

## Carbon
`GET /footprint/factors` · `POST /footprint/estimate` (public) `{period:"2026-01", country, electricity_kwh, gas_m3, car_km, flight_km, renewable_pct}` → total, parts, ranked recommendations.
🔒 `GET /footprint/entries`, `POST /footprint/entries` (upsert per month), `DELETE /footprint/entries/{id}`, `GET /footprint/summary`, `GET /footprint/export.csv`.

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
