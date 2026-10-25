"""Rolling out-of-sample test of bias correction + signed error quantiles."""
import sys
from datetime import time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from app import core

DATA = Path(__file__).resolve().parents[1] / "data"
actuals = core.load_actuals(DATA / "actuals_raw.csv")
forecasts = core.load_forecasts(DATA / "forecasts_raw.csv")

sel = core.expand_to_half_hourly(core.select_for_day_ahead(forecasts, time(9, 0)))
m = core.join_actuals(sel, actuals)
m["date"] = m["start_time"].dt.tz_convert(core.LONDON).dt.date

daily = m.groupby("date").agg(
    err=("error_mw", "sum"), n=("error_mw", "size"),
    act=("actual_mw", "sum"), fc=("forecast_mw", "sum"),
)

print("=== SIGNED ERROR QUANTILES (forecast - actual, MW), day-ahead 09:00 ===")
print(m["error_mw"].quantile([0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]).round(0).to_string())

rows = []
for window in (3, 7, 14):
    parts = []
    for d, g in m.groupby("date"):
        # only actuals up to D-2 are complete at the D-1 09:00 decision time
        hist = daily.loc[[x for x in daily.index
                          if d - timedelta(days=window + 1) <= x <= d - timedelta(days=2)]]
        if len(hist) < window:
            continue
        add_bias = hist["err"].sum() / hist["n"].sum()
        ratio = hist["act"].sum() / hist["fc"].sum()
        g = g.copy()
        g["add_corr_err"] = (g["forecast_mw"] - add_bias) - g["actual_mw"]
        g["ratio_corr_err"] = g["forecast_mw"] * ratio - g["actual_mw"]
        parts.append(g)
    e = pd.concat(parts)
    rows.append({
        "window_days": window,
        "days_evaluated": e["date"].nunique(),
        "raw_mae": round(e["error_mw"].abs().mean()),
        "add_mae": round(e["add_corr_err"].abs().mean()),
        "ratio_mae": round(e["ratio_corr_err"].abs().mean()),
        "raw_bias": round(e["error_mw"].mean()),
        "add_bias": round(e["add_corr_err"].mean()),
        "ratio_bias": round(e["ratio_corr_err"].mean()),
    })

print("\n=== OUT-OF-SAMPLE ROLLING CORRECTION (same days compared for raw vs corrected) ===")
print(pd.DataFrame(rows).to_string(index=False))