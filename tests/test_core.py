from datetime import datetime, timedelta, timezone

import pytest

from dexcom_agent_tools import server
from dexcom_agent_tools.config import ConfigError, Settings, convert
from dexcom_agent_tools.source import FakeSource
from dexcom_agent_tools.stats import compute_stats, to_units


def test_missing_credentials_fail_clearly():
    s = Settings.from_env({})
    with pytest.raises(ConfigError, match="DEXCOM_USERNAME.*DEXCOM_PASSWORD"):
        s.require_credentials()


def test_dry_run_skips_credentials():
    Settings.from_env({"DEXCOM_DRY_RUN": "1"}).require_credentials()


def test_bad_region_and_units():
    with pytest.raises(ConfigError):
        Settings.from_env({"DEXCOM_REGION": "eu"})
    with pytest.raises(ConfigError):
        Settings.from_env({"DEXCOM_UNITS": "furlongs"})
    assert Settings.from_env({"DEXCOM_UNITS": "mmol"}).units == "mmol/L"


def test_convert():
    assert convert(180, "mg/dL") == 180
    assert convert(180, "mmol/L") == 10.0


def test_stats():
    st = compute_stats([50, 60, 100, 150, 200, 260], 70, 180)
    assert st["count"] == 6
    assert st["tir_percent"] == pytest.approx(33.3)
    assert st["tbr_percent"] == pytest.approx(33.3)
    assert st["tbr_very_low_percent"] == pytest.approx(16.7)
    assert st["tar_percent"] == pytest.approx(33.3)
    assert st["tar_very_high_percent"] == pytest.approx(16.7)
    assert compute_stats([]) == {"count": 0}
    assert to_units(st, "mmol/L")["mean_mmol_l"] == round(st["mean_mg_dl"] / 18.0182, 1)


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(server, "_settings", lambda: Settings.from_env({"DEXCOM_DRY_RUN": "1"}))
    monkeypatch.setattr(server, "_source", lambda: FakeSource())


def test_tools_with_fake_source(fake):
    cur = server.get_current_glucose()
    assert cur["reading"]["units"] == "mg/dL"
    now = datetime.now(timezone.utc)
    out = server.get_glucose((now - timedelta(hours=2)).isoformat(), now.isoformat(), units="mmol/L")
    assert 20 <= out["count"] <= 25
    assert out["readings"][0]["units"] == "mmol/L"
    st = server.get_glucose_stats()
    assert st["count"] >= 280 and st["coverage_percent"] > 95


def test_window_validation(fake):
    from mcp.server.mcpserver.exceptions import ToolError

    now = datetime.now(timezone.utc)
    with pytest.raises(ToolError, match="before end"):
        server.get_glucose(now.isoformat(), (now - timedelta(hours=1)).isoformat())
    with pytest.raises(ToolError, match="24 hours"):
        server.get_glucose((now - timedelta(days=3)).isoformat(), (now - timedelta(days=2)).isoformat())


def test_tool_errors_when_unconfigured(monkeypatch):
    from mcp.server.mcpserver.exceptions import ToolError

    monkeypatch.setattr(server, "_settings", lambda: Settings.from_env({}))
    monkeypatch.setattr(server, "_source", lambda: server.make_source(Settings.from_env({})))
    with pytest.raises(ToolError, match="Missing Dexcom credentials"):
        server.get_current_glucose()
