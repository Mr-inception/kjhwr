# UK wind generation: day-ahead forecast monitor

A web app for a day-ahead power buying team. It shows the latest national wind forecast that was available when a purchase decision had to be made, and quantifies how accurate those forecasts have been. Scope: Elexon `FUELHH` (WIND actuals) and `WINDFOR` (wind forecasts) only, for delivery days in January 2026.

**Live app:** https://kjhwr-liart.vercel.app/

## AI tools

This project was built with the assistance of Claude (Anthropic) for design discussion, code generation and review. I ran, tested and checked the results at each step (see the test suite and the findings below).

## What the app does

1. **Delivery-day forecast.** Pick a delivery day and a decision cutoff (default 09:00 UK time on the day before). The app shows the latest forecast published at or before that cutoff, a 90% planning range, an optional bias-adjusted line, and actual generation (labelled as evaluation only).
2. **Forecast accuracy.** MAE, RMSE, bias and error percentiles; error by forecast horizon, hour of day, wind level and day; and an out-of-sample backtest of a bias adjustment.

## Key design decisions

- **Decision-time forecast.** For each target time, use the latest forecast with `publishTime` at or before D-1 at the cutoff (Europe/London time, DST-safe). Later forecasts are never used. The cutoff is a parameter because I did not verify the exact auction gate-closure time.
- **Alignment.** Forecasts are hourly and actuals half-hourly, so each hourly forecast is held over both half-hours.
- **Error sign.** `error = forecast - actual`; positive means over-forecast.
- **Planning range.** Built from signed error quantiles (P5 and P95) of the previous 14 days, using only days up to D-2, since D-1 is incomplete at decision time. It is asymmetric because errors are one-sided.
- **Bias adjustment.** A ratio (actual/forecast over the previous 14 days, up to D-2). Offered as an option, not a default.

## Findings (January 2026, 09:00 cutoff)

- Day-ahead MAE is about 2,145 MW (18.5% of mean actual wind); mean bias is about +1,852 MW, with the forecast above actual on 27 of 31 days.
- Error grows with horizon (nMAE 15.6% at 1h to 20.7% at 48h).
- Backtest, 14-day ratio window, 16 days scored: MAE falls from about 2,118 to 1,172 MW. The adjustment does not help every day (for example, 20 January got worse), and this is a single month, so treat it as promising, not proven.
- I did not establish the cause of the bias.

## Limitations

- One month of data; no demand data, so the app does not compute how much power to buy.
- Decision cutoff is an assumption (configurable).
- The data is a static snapshot committed to the repo (January 2026 is historical), not a live Elexon feed.

## Repository layout

```
backend/
  app/core.py          Selection logic, alignment, metrics
  app/analysis.py      Builds the views served by the API (forecast, accuracy, backtest)
  app/main.py          FastAPI routes
  index.py             Vercel entrypoint
  data/                Elexon snapshot (actuals_raw.csv, forecasts_raw.csv)
  scripts/             fetch_data.py (re-download), exploration and diagnostic scripts
  tests/               pytest suite (logic and API, including no-future-data checks)
  Dockerfile, requirements.txt, requirements-dev.txt
frontend/
  src/App.jsx          Tabs
  src/Forecast.jsx     Delivery-day view
  src/Accuracy.jsx     Accuracy dashboard
  src/api.js           API client
  Dockerfile, nginx.conf, vercel.json
docker-compose.yml
```

## Run with Docker

```
docker compose up --build
```

Open http://localhost:8080.

## Run locally (Windows PowerShell)

```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt -r backend\requirements-dev.txt
cd backend
uvicorn app.main:app --reload
```

In a second terminal:

```
cd frontend
npm install
npm run dev
```

Open the URL Vite prints. The dev server proxies `/api` to port 8000.

## Tests

```
cd backend
pytest -v
```

## API

`GET /api/meta`, `/api/forecast?date=YYYY-MM-DD&cutoff=HH:MM`, `/api/accuracy?cutoff=HH:MM`, `/api/backtest?cutoff=HH:MM`, `/api/health`. Interactive docs at `/docs` when running the backend.

## Deployment

Two Vercel projects: the backend (root directory `backend`) and the frontend (root directory `frontend`), where `frontend/vercel.json` rewrites `/api/*` to the backend.
