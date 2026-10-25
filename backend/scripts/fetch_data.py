"""Fetch WIND actuals (FUELHH) and WINDFOR forecasts from Elexon BMRS for Jan 2026."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd

BASE = "https://data.elexon.co.uk/bmrs/api/v1/datasets"
OUT = Path(__file__).resolve().parents[1] / "data"
OUT.mkdir(exist_ok=True)


def daterange_chunks(start: date, end: date, days: int):
    cur = start
    while cur <= end:
        nxt = min(cur + timedelta(days=days - 1), end)
        yield cur, nxt
        cur = nxt + timedelta(days=1)


def get(client: httpx.Client, url: str, params: dict) -> list[dict]:
    r = client.get(url, params=params, timeout=60)
    if r.status_code != 200:
        print("ERROR", r.status_code, r.url, r.text[:300])
        r.raise_for_status()
    return r.json()


def fetch_actuals(client: httpx.Client) -> pd.DataFrame:
    rows = []
    for a, b in daterange_chunks(date(2026, 1, 1), date(2026, 1, 31), 7):
        data = get(client, f"{BASE}/FUELHH/stream", {
            "settlementDateFrom": a.isoformat(),
            "settlementDateTo": b.isoformat(),
            "fuelType": "WIND",
        })
        print("FUELHH", a, b, len(data))
        rows += data
    df = pd.DataFrame(rows)
    return df.drop_duplicates(subset=["startTime"]).sort_values("startTime")


def fetch_forecasts(client: httpx.Client) -> pd.DataFrame:
    rows = []
    # forecasts used for Jan 2026 decisions can be published from late Dec 2025
    for a, b in daterange_chunks(date(2025, 12, 29), date(2026, 1, 31), 2):
        start = datetime(a.year, a.month, a.day, tzinfo=timezone.utc)
        end = datetime(b.year, b.month, b.day, tzinfo=timezone.utc) + timedelta(days=1)
        data = get(client, f"{BASE}/WINDFOR/stream", {
            "publishDateTimeFrom": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "publishDateTimeTo": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        print("WINDFOR", a, b, len(data))
        rows += data
    df = pd.DataFrame(rows)
    return df.drop_duplicates(subset=["startTime", "publishTime"]).sort_values(
        ["startTime", "publishTime"]
    )


if __name__ == "__main__":
    with httpx.Client() as client:
        actuals = fetch_actuals(client)
        forecasts = fetch_forecasts(client)
    actuals.to_csv(OUT / "actuals_raw.csv", index=False)
    forecasts.to_csv(OUT / "forecasts_raw.csv", index=False)
    print("\nACTUALS", actuals.shape)
    print(actuals.head(3).to_string())
    print(actuals.startTime.min(), "->", actuals.startTime.max())
    print("\nFORECASTS", forecasts.shape)
    print(forecasts.head(3).to_string())
    print(forecasts.startTime.min(), "->", forecasts.startTime.max())
    print(forecasts.publishTime.min(), "->", forecasts.publishTime.max())