from datetime import datetime, timezone

from app.core.datetimes import utc_iso


def test_naive_and_aware_datetimes_serialize_as_utc_z() -> None:
    naive = datetime(2026, 9, 27, 5, 43, 0)
    assert utc_iso(naive) == "2026-09-27T05:43:00Z"
    nairobi = datetime(2026, 9, 27, 8, 43, 0, tzinfo=timezone.utc)
    assert utc_iso(nairobi) == "2026-09-27T08:43:00Z"
