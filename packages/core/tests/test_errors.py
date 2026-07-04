from solar_mcp_core.errors import BadInput, QuotaExceeded, SolarMCPError, SourceUnavailable


def test_bad_input_names_field_and_allowed_range() -> None:
    err = BadInput(field="tilt_deg", value=95, allowed="0 to 90")
    assert "tilt_deg" in str(err)
    assert "95" in str(err)
    assert "0 to 90" in str(err)
    assert err.field == "tilt_deg"


def test_quota_exceeded_mentions_rolling_window_and_remaining() -> None:
    err = QuotaExceeded(source="nrel", remaining=0)
    assert "rolling" in str(err)
    assert "X-RateLimit-Remaining=0" in str(err)

    without_header = QuotaExceeded(source="nrel")
    assert "limit reached" in str(without_header)


def test_source_unavailable_carries_detail() -> None:
    err = SourceUnavailable(source="nrel", detail="HTTP 503 after 3 attempts")
    assert "nrel" in str(err)
    assert "503" in str(err)


def test_all_share_base_class() -> None:
    for err in (
        BadInput("f", 1, "a"),
        QuotaExceeded("s"),
        SourceUnavailable("s", "d"),
    ):
        assert isinstance(err, SolarMCPError)
