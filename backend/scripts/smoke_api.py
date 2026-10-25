"""Call the API in-process and print compact summaries."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)
f = c.get("/api/forecast", params={"date": "2026-01-20"}).json()
print("cutoff_utc:", f["cutoff_utc"])
print("publish times used:", f["forecast_publish_times"])
print("correction:", f["correction"])
print("band:", f["band"])
print("summary:", f["summary"])
print("first row:", json.dumps(f["rows"][0], indent=1))

a = c.get("/api/accuracy").json()
print("\noverall:", a["overall"])
print("quantiles:", a["signed_error_quantiles_mw"])
print("by_wind_level:", [(x["level"], x["mae_mw"], x["bias_mw"]) for x in a["by_wind_level"]])