"""Tests for the weekly public-jobs cache."""
from datetime import datetime, timedelta, timezone

from app.public_jobs import router as pj

NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)


def test_due_when_empty_or_older_than_a_week():
    assert pj.is_due(None, None, NOW)
    assert pj.is_due(NOW - timedelta(days=8), None, NOW)
    assert not pj.is_due(NOW - timedelta(days=2), None, NOW)


def test_failed_refresh_waits_an_hour_before_retrying():
    stale = NOW - timedelta(days=30)
    assert not pj.is_due(stale, NOW - timedelta(minutes=10), NOW)
    assert pj.is_due(stale, NOW - timedelta(hours=2), NOW)


def test_rows_keep_only_real_recent_listings_and_cap_per_role():
    recent = "2026-11-01T00:00:00Z"
    jobs = [
        {"title": "ML Engineer", "apply_url": "https://adzuna/1", "company": "A", "created": "2026-11-10T00:00:00Z"},
        {"title": "No link", "apply_url": None, "created": recent},
        {"title": "", "apply_url": "https://adzuna/x", "created": recent},
        {"title": "Ancient", "apply_url": "https://adzuna/old", "created": "2022-05-01T00:00:00Z"},
        {"title": "No date", "apply_url": "https://adzuna/nodate"},
        {"title": "ML 2", "apply_url": "https://adzuna/2", "created": recent},
        {"title": "ML 3", "apply_url": "https://adzuna/3", "created": recent},
        {"title": "ML 4", "apply_url": "https://adzuna/4", "created": recent},
    ]
    rows = pj.rows_from_jobs("Machine Learning Engineer", jobs, "2026-11-13T00:00:00+00:00")
    assert [r["title"] for r in rows] == ["ML Engineer", "ML 2", "ML 3"]
    assert rows[0]["posted_at"] == "2026-11-10T00:00:00Z"
    assert all(r["role_title"] == "Machine Learning Engineer" for r in rows)


def test_refresh_keeps_old_rows_when_adzuna_returns_nothing(monkeypatch):
    calls = []

    class _Table:
        def __getattr__(self, name):
            calls.append(name)
            return lambda *a, **k: self

    monkeypatch.setattr(pj, "fetch_jobs", lambda *a, **k: [])
    monkeypatch.setattr(pj.db_client, "table", lambda name: _Table())
    pj.refresh_public_jobs()
    assert "delete" not in calls and "insert" not in calls
