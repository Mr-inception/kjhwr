"""Run the core pipeline on the real January data and print the results."""
import sys
from datetime import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from app import core

DATA = Path(__file__).resolve().parents[1] / "data"
actuals = core.load_actuals(DATA / "actuals_raw.csv")
forecasts = core.load_forecasts(DATA / "forecasts_raw.csv")

print("=== DAY-AHEAD: latest forecast before D-1 cutoff (UK time) ===")
for hh in (7, 9, 10, 12):
    sel = core.expand_to_half_hourly(core.select_for_day_ahead(forecasts, time(hh, 0)))
    m = core.join_actuals(sel, actuals)
    print(f"cutoff {hh:02d}:00 ->", core.compute_metrics(m))

print("\n=== ERROR BY FORECAST HORIZON ===")
rows = []
for h in (1, 3, 6, 12, 24, 36, 48):
    sel = core.expand_to_half_hourly(core.select_by_horizon(forecasts, h))
    m = core.join_actuals(sel, actuals)
    rows.append({"horizon_h": h, **core.compute_metrics(m)})
print(pd.DataFrame(rows).to_string(index=False))

print("\nExpected actual rows in January:", len(actuals))