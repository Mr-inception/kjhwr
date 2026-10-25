from datetime import date, time

import pandas as pd

from app import core


def fc(rows):
    df = pd.DataFrame(rows, columns=["start_time", "publish_time", "forecast_mw"])
    df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
    df["publish_time"] = pd.to_datetime(df["publish_time"], utc=True)
    df["horizon_h"] = (df["start_time"] - df["publish_time"]).dt.total_seconds() / 3600
    return df


TARGET = "2026-01-15 12:00"
ROWS = [
    (TARGET, "2026-01-14 07:30", 100),
    (TARGET, "2026-01-14 09:30", 200),
    (TARGET, "2026-01-14 15:30", 300),
    (TARGET, "2026-01-15 02:30", 400),
]


def test_picks_latest_before_cutoff_0900():
    sel = core.select_for_day_ahead(fc(ROWS), time(9, 0))
    assert len(sel) == 1
    assert sel.loc[0, "forecast_mw"] == 100


def test_later_cutoff_includes_later_publish():
    sel = core.select_for_day_ahead(fc(ROWS), time(10, 0))
    assert sel.loc[0, "forecast_mw"] == 200


def test_never_uses_forecast_published_after_cutoff():
    sel = core.select_for_day_ahead(fc(ROWS), time(9, 0))
    cutoff = core.cutoff_for(date(2026, 1, 15), time(9, 0))
    assert (sel["publish_time"] <= cutoff).all()


def test_same_day_forecast_is_not_eligible():
    # Target on Jan 14 only has a forecast published on Jan 14 -> after the Jan 13 cutoff
    rows = [("2026-01-14 23:00", "2026-01-14 07:30", 500)]
    assert core.select_for_day_ahead(fc(rows), time(9, 0)).empty


def test_negative_horizon_forecasts_excluded():
    rows = [(TARGET, "2026-01-15 15:30", 999)]  # published after the target
    assert core.select_for_day_ahead(fc(rows), time(9, 0)).empty


def test_cutoff_respects_london_dst():
    # July: London is UTC+1, so 09:00 local on Jul 1 is 08:00 UTC
    assert core.cutoff_for(date(2026, 7, 2), time(9, 0)) == pd.Timestamp("2026-07-01 08:00", tz="UTC")
    # January: London is UTC
    assert core.cutoff_for(date(2026, 1, 15), time(9, 0)) == pd.Timestamp("2026-01-14 09:00", tz="UTC")


def test_expand_to_half_hourly():
    out = core.expand_to_half_hourly(fc([(TARGET, "2026-01-14 07:30", 100)]))
    assert list(out["start_time"].dt.minute) == [0, 30]
    assert list(out["forecast_mw"]) == [100, 100]


def test_metrics_known_values():
    sel = pd.DataFrame(
        {"start_time": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 00:30"], utc=True),
         "forecast_mw": [110, 90]}
    )
    act = pd.DataFrame(
        {"start_time": sel["start_time"], "actual_mw": [100, 100]}
    )
    m = core.compute_metrics(core.join_actuals(sel, act))
    assert m["n"] == 2
    assert m["mae_mw"] == 10.0
    assert m["rmse_mw"] == 10.0
    assert m["bias_mw"] == 0.0


def test_bias_sign_positive_means_over_forecast():
    sel = pd.DataFrame({"start_time": pd.to_datetime(["2026-01-01 00:00"], utc=True), "forecast_mw": [120]})
    act = pd.DataFrame({"start_time": sel["start_time"], "actual_mw": [100]})
    assert core.compute_metrics(core.join_actuals(sel, act))["bias_mw"] == 20.0


def test_select_by_horizon():
    rows = [
        (TARGET, "2026-01-13 12:00", 1),  # 48h ahead
        (TARGET, "2026-01-14 06:00", 2),  # 30h ahead
        (TARGET, "2026-01-15 02:00", 3),  # 10h ahead
    ]
    f = fc(rows)
    assert core.select_by_horizon(f, 24).loc[0, "forecast_mw"] == 2
    assert core.select_by_horizon(f, 6).loc[0, "forecast_mw"] == 3
    assert core.select_by_horizon(f, 60).empty