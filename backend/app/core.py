"""Core logic: decision-time forecast selection, alignment, and error metrics."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

LONDON = ZoneInfo("Europe/London")
DEFAULT_CUTOFF = time(9, 0)  # D-1, UK local time


def load_actuals(path: Path | str) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=["startTime", "generation"])
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df = df.rename(columns={"startTime": "start_time", "generation": "actual_mw"})
    return df.drop_duplicates("start_time").sort_values("start_time").reset_index(drop=True)


def load_forecasts(path: Path | str) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=["startTime", "publishTime", "generation"])
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    df = df.rename(
        columns={"startTime": "start_time", "publishTime": "publish_time", "generation": "forecast_mw"}
    )
    df = df.drop_duplicates(["start_time", "publish_time"])
    df["horizon_h"] = (df["start_time"] - df["publish_time"]).dt.total_seconds() / 3600
    return df.sort_values(["start_time", "publish_time"]).reset_index(drop=True)


def cutoff_for(delivery_date: date, cutoff_local: time = DEFAULT_CUTOFF) -> pd.Timestamp:
    """Decision cutoff (UTC) for a delivery day: D-1 at `cutoff_local` UK time."""
    naive = datetime.combine(delivery_date - timedelta(days=1), cutoff_local)
    return (
        pd.Timestamp(naive)
        .tz_localize(LONDON, ambiguous=False, nonexistent="shift_forward")
        .tz_convert("UTC")
    )


def select_for_day_ahead(forecasts: pd.DataFrame, cutoff_local: time = DEFAULT_CUTOFF) -> pd.DataFrame:
    """For each target hour, the latest forecast published at or before the D-1 cutoff.

    Targets with no eligible forecast are dropped (never filled with later data).
    """
    f = forecasts.copy()
    f["delivery_date"] = f["start_time"].dt.tz_convert(LONDON).dt.date
    cuts = pd.DataFrame({"delivery_date": f["delivery_date"].unique()})
    cuts["cutoff"] = [cutoff_for(d, cutoff_local) for d in cuts["delivery_date"]]
    f = f.merge(cuts, on="delivery_date")
    eligible = f[f["publish_time"] <= f["cutoff"]]
    latest = eligible.sort_values(["start_time", "publish_time"]).drop_duplicates(
        "start_time", keep="last"
    )
    return latest.sort_values("start_time").reset_index(drop=True)


def select_by_horizon(forecasts: pd.DataFrame, horizon_h: float) -> pd.DataFrame:
    """For each target hour, the latest forecast published at least `horizon_h` hours before it."""
    targets = forecasts[["start_time"]].drop_duplicates().copy()
    targets["cutoff"] = targets["start_time"] - pd.Timedelta(hours=horizon_h)
    right = forecasts[["start_time", "publish_time", "forecast_mw"]].sort_values("publish_time")
    out = pd.merge_asof(
        targets.sort_values("cutoff"),
        right,
        left_on="cutoff",
        right_on="publish_time",
        by="start_time",
        direction="backward",
    )
    out = out.dropna(subset=["publish_time"]).drop(columns=["cutoff"])
    out["horizon_h"] = (out["start_time"] - out["publish_time"]).dt.total_seconds() / 3600
    return out.sort_values("start_time").reset_index(drop=True)


def expand_to_half_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """Hold each hourly forecast over both half-hour settlement periods."""
    second = df.copy()
    second["start_time"] = second["start_time"] + pd.Timedelta(minutes=30)
    return pd.concat([df, second]).sort_values("start_time").reset_index(drop=True)


def join_actuals(selected: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    """Inner-join forecasts to actuals. error = forecast - actual (positive = over-forecast)."""
    m = selected.merge(actuals, on="start_time", how="inner")
    m["error_mw"] = m["forecast_mw"] - m["actual_mw"]
    m["abs_error_mw"] = m["error_mw"].abs()
    return m


def compute_metrics(m: pd.DataFrame) -> dict:
    if m.empty:
        return {"n": 0}
    mae = m["abs_error_mw"].mean()
    mean_actual = m["actual_mw"].mean()
    return {
        "n": int(len(m)),
        "mae_mw": round(float(mae), 1),
        "rmse_mw": round(float((m["error_mw"] ** 2).mean() ** 0.5), 1),
        "bias_mw": round(float(m["error_mw"].mean()), 1),
        "p50_abs_error_mw": round(float(m["abs_error_mw"].quantile(0.5)), 1),
        "p90_abs_error_mw": round(float(m["abs_error_mw"].quantile(0.9)), 1),
        "p95_abs_error_mw": round(float(m["abs_error_mw"].quantile(0.95)), 1),
        "mean_actual_mw": round(float(mean_actual), 1),
        "nmae_pct": round(float(mae / mean_actual * 100), 2),
    }