"""Sanity-check the raw Elexon data before building the pipeline."""
from pathlib import Path

import pandas as pd

D = Path(__file__).resolve().parents[1] / "data"
a = pd.read_csv(D / "actuals_raw.csv", parse_dates=["startTime", "publishTime"])
f = pd.read_csv(D / "forecasts_raw.csv", parse_dates=["startTime", "publishTime"])

f["horizon_h"] = (f.startTime - f.publishTime).dt.total_seconds() / 3600

print("=== NULLS ===")
print(a[["startTime", "generation"]].isna().sum().to_dict())
print(f[["startTime", "publishTime", "generation"]].isna().sum().to_dict())

print("\n=== DUPLICATES (startTime, publishTime) ===")
print(f.duplicated(["startTime", "publishTime"]).sum())

print("\n=== MINUTE VALUES OF startTime ===")
print("actuals :", sorted(a.startTime.dt.minute.unique()))
print("forecast:", sorted(f.startTime.dt.minute.unique()))

print("\n=== HORIZON (hours) ===")
print(f.horizon_h.describe().to_string())
print("negative horizon rows:", (f.horizon_h < 0).sum())

print("\n=== PUBLISH TIMES (UTC HH:MM, count) ===")
print(f.publishTime.dt.strftime("%H:%M").value_counts().sort_index().to_string())

print("\n=== PUBLISHES PER DAY (distinct publishTime) ===")
print(f.groupby(f.publishTime.dt.date).publishTime.nunique().describe().to_string())

print("\n=== GENERATION STATS (MW) ===")
print("actual  :", a.generation.describe().round(0).to_dict())
print("forecast:", f.generation.describe().round(0).to_dict())

jan = f[(f.startTime >= "2026-01-01") & (f.startTime < "2026-02-01") & (f.horizon_h >= 0)]
print("\n=== FORECASTS PER JAN TARGET (horizon>=0) ===")
print(jan.groupby("startTime").size().describe().to_string())

t = pd.Timestamp("2026-01-15 12:00", tz="UTC")
print(f"\n=== ALL FORECASTS FOR TARGET {t} ===")
print(f[f.startTime == t][["publishTime", "horizon_h", "generation"]].to_string())