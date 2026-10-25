"""Diagnose the systematic over-forecast: alignment, hour-of-day, wind level, calibration."""
import sys
from datetime import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from app import core

DATA = Path(__file__).resolve().parents[1] / "data"
actuals = core.load_actuals(DATA / "actuals_raw.csv")
forecasts = core.load_forecasts(DATA / "forecasts_raw.csv")

sel = core.expand_to_half_hourly(core.select_for_day_ahead(forecasts, time(9, 0)))

print("=== 1. ALIGNMENT TEST: shift forecast timestamps, look for lowest MAE ===")
rows = []
for shift in (-180, -120, -90, -60, -30, 0, 30, 60, 90, 120, 180):
    s = sel.copy()
    s["start_time"] = s["start_time"] + pd.Timedelta(minutes=shift)
    m = core.join_actuals(s, actuals)
    rows.append({"shift_min": shift, "n": len(m),
                 "mae_mw": round(m.abs_error_mw.mean(), 1),
                 "bias_mw": round(m.error_mw.mean(), 1)})
print(pd.DataFrame(rows).to_string(index=False))

m = core.join_actuals(sel, actuals)
m["hour"] = m["start_time"].dt.tz_convert(core.LONDON).dt.hour

print("\n=== 2. BY HOUR OF DAY (UK) ===")
h = m.groupby("hour").agg(mae=("abs_error_mw", "mean"), bias=("error_mw", "mean"),
                          actual=("actual_mw", "mean")).round(0)
print(h.T.to_string())

print("\n=== 3. BY WIND LEVEL (actual quartiles) ===")
m["level"] = pd.qcut(m["actual_mw"], 4, labels=["Q1 low", "Q2", "Q3", "Q4 high"])
l = m.groupby("level", observed=True).agg(
    n=("error_mw", "size"), actual=("actual_mw", "mean"), forecast=("forecast_mw", "mean"),
    mae=("abs_error_mw", "mean"), bias=("error_mw", "mean")).round(0)
l["ratio_f_over_a"] = (l["forecast"] / l["actual"]).round(3)
print(l.to_string())

print("\n=== 4. LINEAR CALIBRATION: actual = a * forecast + b ===")
a, b = np.polyfit(m["forecast_mw"], m["actual_mw"], 1)
print(f"slope={a:.3f} intercept={b:.0f} MW | corr={np.corrcoef(m.forecast_mw, m.actual_mw)[0, 1]:.3f}")

print("\n=== 5. WHAT IF THE CLIENT REMOVED THE MEAN BIAS? ===")
bias = m.error_mw.mean()
print(f"raw MAE={m.abs_error_mw.mean():.0f}  bias-corrected MAE={(m.error_mw - bias).abs().mean():.0f}")
print(f"ratio-corrected MAE={(m.forecast_mw * m.actual_mw.sum() / m.forecast_mw.sum() - m.actual_mw).abs().mean():.0f}")

print("\n=== 6. DAILY BIAS (UK date): how consistent is it? ===")
m["date"] = m["start_time"].dt.tz_convert(core.LONDON).dt.date
d = m.groupby("date").agg(bias=("error_mw", "mean"), mae=("abs_error_mw", "mean")).round(0)
print(d.describe().round(0).to_string())
print("days with over-forecast:", int((d.bias > 0).sum()), "of", len(d))
print("worst 5 days by MAE:")
print(d.sort_values("mae", ascending=False).head(5).to_string())