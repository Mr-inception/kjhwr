"""Analysis service: builds the decision-time dataset and the views the API serves."""
from __future__ import annotations

import os
from datetime import date, time, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd

from . import core

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
HORIZONS = (1, 3, 6, 12, 24, 36, 48)
HISTORY_DAYS = 14      # window used for the correction ratio and error band
MIN_HISTORY_DAYS = 3   # below this we return no correction/band rather than a shaky one


def _r(x, nd=1):
    return round(float(x), nd)


def _iso(ts) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


@lru_cache(maxsize=1)
def load_data():
    return (
        core.load_actuals(DATA_DIR / "actuals_raw.csv"),
        core.load_forecasts(DATA_DIR / "forecasts_raw.csv"),
    )


@lru_cache(maxsize=32)
def day_ahead_frame(cutoff: time) -> pd.DataFrame:
    """Half-hourly day-ahead forecast (latest before D-1 cutoff) joined to actuals. Treat as read-only."""
    actuals, forecasts = load_data()
    sel = core.expand_to_half_hourly(core.select_for_day_ahead(forecasts, cutoff))
    m = core.join_actuals(sel, actuals)
    local = m["start_time"].dt.tz_convert(core.LONDON)
    m["date"] = local.dt.date
    m["hour"] = local.dt.hour
    return m


def available_dates(cutoff: time) -> list[date]:
    return sorted(day_ahead_frame(cutoff)["date"].unique())


def _history(m: pd.DataFrame, d: date) -> tuple[pd.DataFrame | None, date]:
    """Errors a buyer could know when deciding for day d: only days up to D-2 (D-1 is incomplete)."""
    hi = d - timedelta(days=2)
    lo = d - timedelta(days=HISTORY_DAYS + 1)
    h = m[(m["date"] >= lo) & (m["date"] <= hi)]
    return (h if h["date"].nunique() >= MIN_HISTORY_DAYS else None), hi


def forecast_view(d: date, cutoff: time) -> dict | None:
    m = day_ahead_frame(cutoff)
    day = m[m["date"] == d]
    if day.empty:
        return None

    hist, hist_end = _history(m, d)
    correction = band = None
    ratio = q05 = q95 = None
    if hist is not None:
        ratio = float(hist["actual_mw"].sum() / hist["forecast_mw"].sum())
        q05, q95 = (float(x) for x in hist["error_mw"].quantile([0.05, 0.95]))
        correction = {
            "method": "ratio",
            "ratio": round(ratio, 4),
            "history_days": int(hist["date"].nunique()),
            "history_end": hist_end.isoformat(),
        }
        # error = forecast - actual  =>  actual lies in [F - q95, F - q05] with ~90% historical coverage
        band = {"level": 0.90, "error_p05_mw": _r(q05), "error_p95_mw": _r(q95)}

    rows = []
    for r in day.itertuples():
        f = float(r.forecast_mw)
        rows.append({
            "start_time": _iso(r.start_time),
            "forecast_mw": f,
            "forecast_publish_time": _iso(r.publish_time),
            "actual_mw": float(r.actual_mw),
            "error_mw": float(r.error_mw),
            "corrected_forecast_mw": _r(f * ratio) if ratio is not None else None,
            "band_low_mw": _r(f - q95) if q95 is not None else None,
            "band_high_mw": _r(f - q05) if q05 is not None else None,
        })

    summary = core.compute_metrics(day)
    if ratio is not None:
        summary["corrected_mae_mw"] = _r((day["forecast_mw"] * ratio - day["actual_mw"]).abs().mean())

    return {
        "delivery_date": d.isoformat(),
        "cutoff_local": cutoff.strftime("%H:%M"),
        "cutoff_utc": _iso(core.cutoff_for(d, cutoff)),
        "forecast_publish_times": [_iso(t) for t in sorted(day["publish_time"].unique())],
        "correction": correction,
        "band": band,
        "summary": summary,
        "rows": rows,
    }


@lru_cache(maxsize=1)
def horizon_table() -> list[dict]:
    actuals, forecasts = load_data()
    out = []
    for h in HORIZONS:
        sel = core.expand_to_half_hourly(core.select_by_horizon(forecasts, h))
        out.append({"horizon_h": h, **core.compute_metrics(core.join_actuals(sel, actuals))})
    return out


def accuracy_view(cutoff: time) -> dict:
    m = day_ahead_frame(cutoff)

    qs = m["error_mw"].quantile([0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95])
    signed = {f"p{int(round(k * 100)):02d}": _r(v) for k, v in qs.items()}

    daily = [
        {"date": d.isoformat(), "n": int(len(g)), "mae_mw": _r(g["abs_error_mw"].mean()),
         "bias_mw": _r(g["error_mw"].mean()), "mean_actual_mw": _r(g["actual_mw"].mean())}
        for d, g in m.groupby("date")
    ]
    by_hour = [
        {"hour": int(h), "mae_mw": _r(g["abs_error_mw"].mean()), "bias_mw": _r(g["error_mw"].mean())}
        for h, g in m.groupby("hour")
    ]
    labels = ["Q1 (lowest wind)", "Q2", "Q3", "Q4 (highest wind)"]
    lv = pd.qcut(m["actual_mw"], 4, labels=labels)
    by_level = [
        {"level": str(k), "n": int(len(g)), "actual_min_mw": _r(g["actual_mw"].min()),
         "actual_max_mw": _r(g["actual_mw"].max()), "mean_actual_mw": _r(g["actual_mw"].mean()),
         "mean_forecast_mw": _r(g["forecast_mw"].mean()), "mae_mw": _r(g["abs_error_mw"].mean()),
         "bias_mw": _r(g["error_mw"].mean())}
        for k, g in m.assign(level=lv).groupby("level", observed=True)
    ]
    return {
        "cutoff_local": cutoff.strftime("%H:%M"),
        "error_definition": "error = forecast - actual (positive = over-forecast)",
        "overall": core.compute_metrics(m),
        "signed_error_quantiles_mw": signed,
        "daily": daily,
        "by_hour": by_hour,
        "by_wind_level": by_level,
        "by_horizon": horizon_table(),
    }

BACKTEST_WINDOWS = (3, 7, 14)


@lru_cache(maxsize=8)
def backtest_view(cutoff: time) -> dict:
    """Rolling out-of-sample test of the ratio correction.

    For delivery day D, the ratio uses only the `window` days ending at D-2 (D-1 is incomplete at
    decision time). Days without a full window are not scored, so each row has its own day count.
    """
    m = day_ahead_frame(cutoff)
    daily = m.groupby("date").agg(act=("actual_mw", "sum"), fc=("forecast_mw", "sum"))
    rows = []
    for window in BACKTEST_WINDOWS:
        raw_errs, adj_errs, days = [], [], 0
        for d, g in m.groupby("date"):
            lo, hi = d - timedelta(days=window + 1), d - timedelta(days=2)
            hist = daily.loc[[x for x in daily.index if lo <= x <= hi]]
            if len(hist) < window:
                continue
            ratio = hist["act"].sum() / hist["fc"].sum()
            raw_errs.append(g["abs_error_mw"])
            adj_errs.append((g["forecast_mw"] * ratio - g["actual_mw"]).abs())
            days += 1
        if not days:
            continue
        raw = float(pd.concat(raw_errs).mean())
        adj = float(pd.concat(adj_errs).mean())
        rows.append({
            "window_days": window,
            "days_scored": days,
            "raw_mae_mw": _r(raw),
            "adjusted_mae_mw": _r(adj),
            "improvement_pct": _r((raw - adj) / raw * 100),
        })
    return {"method": "ratio", "cutoff_local": cutoff.strftime("%H:%M"), "rows": rows}