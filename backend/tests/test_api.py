import pandas as pd
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_forecast_has_48_half_hours():
    r = client.get("/api/forecast", params={"date": "2026-01-15"})
    assert r.status_code == 200
    assert len(r.json()["rows"]) == 48


def test_forecast_never_uses_forecast_published_after_cutoff():
    body = client.get("/api/forecast", params={"date": "2026-01-15", "cutoff": "09:00"}).json()
    cutoff = pd.Timestamp(body["cutoff_utc"])
    assert all(pd.Timestamp(t) <= cutoff for t in body["forecast_publish_times"])
    assert all(pd.Timestamp(r["forecast_publish_time"]) <= cutoff for r in body["rows"])


def test_correction_history_stops_at_d_minus_2():
    body = client.get("/api/forecast", params={"date": "2026-01-10"}).json()
    assert body["correction"]["history_end"] == "2026-01-08"


def test_early_day_has_no_correction_or_band():
    body = client.get("/api/forecast", params={"date": "2026-01-02"}).json()
    assert body["correction"] is None and body["band"] is None
    assert body["rows"][0]["band_low_mw"] is None


def test_later_day_has_sane_band_and_correction():
    body = client.get("/api/forecast", params={"date": "2026-01-20"}).json()
    assert 0.5 < body["correction"]["ratio"] < 1.0
    row = body["rows"][0]
    assert row["band_low_mw"] < row["band_high_mw"]


def test_unknown_date_is_404():
    assert client.get("/api/forecast", params={"date": "2026-03-01"}).status_code == 404


def test_bad_cutoff_is_422():
    assert client.get("/api/forecast", params={"date": "2026-01-15", "cutoff": "25:99"}).status_code == 422


def test_accuracy_overall_covers_all_january():
    body = client.get("/api/accuracy").json()
    assert body["overall"]["n"] == 1488
    assert set(body["signed_error_quantiles_mw"]) >= {"p05", "p50", "p95"}
    assert len(body["by_horizon"]) == 7
    assert len(body["daily"]) == 31

def test_backtest_rows_and_scored_days():
    body = client.get("/api/backtest").json()
    rows = {r["window_days"]: r for r in body["rows"]}
    assert set(rows) == {3, 7, 14}
    # a full 14-day window ending at D-2 first exists for 16 Jan -> 16 scored days
    assert rows[14]["days_scored"] == 16
    assert rows[7]["days_scored"] == 23
    assert rows[3]["days_scored"] == 27


def test_backtest_matches_offline_script_and_adjustment_helps():
    rows = {r["window_days"]: r for r in client.get("/api/backtest").json()["rows"]}
    assert abs(rows[14]["raw_mae_mw"] - 2118) <= 1
    assert abs(rows[14]["adjusted_mae_mw"] - 1172) <= 1
    assert all(r["adjusted_mae_mw"] < r["raw_mae_mw"] for r in rows.values())