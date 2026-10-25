"""FastAPI app: wind forecast vs actual, decision-time view and accuracy analytics."""
from __future__ import annotations

from datetime import date, time

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import analysis, core

CUTOFF_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
DEFAULT_CUTOFF_STR = core.DEFAULT_CUTOFF.strftime("%H:%M")

app = FastAPI(title="UK Wind Forecast Monitor", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


def _cutoff(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/meta")
def meta(cutoff: str = Query(DEFAULT_CUTOFF_STR, pattern=CUTOFF_PATTERN)):
    dates = analysis.available_dates(_cutoff(cutoff))
    return {
        "default_cutoff": DEFAULT_CUTOFF_STR,
        "timezone": "Europe/London",
        "first_date": dates[0].isoformat(),
        "last_date": dates[-1].isoformat(),
        "dates": [d.isoformat() for d in dates],
        "error_definition": "error = forecast - actual (positive = over-forecast)",
    }


@app.get("/api/forecast")
def forecast(
    delivery_date: date = Query(..., alias="date"),
    cutoff: str = Query(DEFAULT_CUTOFF_STR, pattern=CUTOFF_PATTERN),
):
    view = analysis.forecast_view(delivery_date, _cutoff(cutoff))
    if view is None:
        raise HTTPException(404, f"No data for delivery date {delivery_date}")
    return view


@app.get("/api/accuracy")
def accuracy(cutoff: str = Query(DEFAULT_CUTOFF_STR, pattern=CUTOFF_PATTERN)):
    return analysis.accuracy_view(_cutoff(cutoff))

@app.get("/api/backtest")
def backtest(cutoff: str = Query(DEFAULT_CUTOFF_STR, pattern=CUTOFF_PATTERN)):
    return analysis.backtest_view(_cutoff(cutoff))