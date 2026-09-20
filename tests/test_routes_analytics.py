"""Behavior tests for admin dashboard analytics."""

from datetime import date
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.routes import analytics

ADMIN_ENDPOINTS = (
    "/admin/dashboard/metrics",
    "/admin/dashboard/charts/jobs-over-time",
    "/admin/dashboard/charts/job-status-breakdown",
    "/admin/dashboard/charts/export-format-breakdown",
    "/admin/dashboard/search-analytics",
    "/admin/dashboard/system-health",
)


@pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
def test_dashboard_endpoints_require_authentication(client: TestClient, endpoint: str):
    assert client.get(endpoint).status_code == 401


class ScalarDatabase:
    def __init__(self, values):
        self.values = iter(values)
        self.statements = []

    def execute(self, statement, params=None):
        self.statements.append((str(statement), params))
        return Mock(scalar=Mock(return_value=next(self.values)))


def test_dashboard_metrics_maps_each_database_count_to_its_contract():
    db = ScalarDatabase(range(1, 19))

    result = analytics.get_dashboard_metrics(Mock(), db, {"role": "admin"})

    assert result == {
        "jobs": {"total": 1, "today": 2, "this_week": 3, "pending": 4, "in_progress": 5},
        "videos": {"total": 6, "completed": 7, "failed": 8},
        "users": {"total": 9, "free": 10, "pro": 11, "signups_today": 12, "signups_this_week": 13},
        "sessions": {"active": 14},
        "searches": {"today": 15, "this_week": 16},
        "exports": {"today": 17, "this_week": 18},
    }
    assert len(db.statements) == 18


@pytest.mark.parametrize(
    ("period", "expected_fragment"),
    (("daily", "DATE(created_at)"), ("weekly", "DATE_TRUNC('week'"), ("monthly", "DATE_TRUNC('month'")),
)
def test_jobs_over_time_selects_requested_bucket(period: str, expected_fragment: str):
    db = Mock()
    db.execute.return_value.all.return_value = [(date(2026, 9, 1), 4), (date(2026, 9, 2), 7)]

    result = analytics.get_jobs_over_time(Mock(), db, {"role": "admin"}, period=period, days=14)

    assert result == {"labels": ["2026-09-01", "2026-09-02"], "data": [4, 7]}
    statement, params = db.execute.call_args.args
    assert expected_fragment in str(statement)
    assert params["start_date"] is not None


def test_jobs_over_time_rejects_unknown_bucket_without_querying():
    db = Mock()

    assert analytics.get_jobs_over_time(Mock(), db, {"role": "admin"}, period="hourly") == {
        "error": "Invalid period. Use 'daily', 'weekly', or 'monthly'"
    }
    db.execute.assert_not_called()


def test_breakdown_endpoints_preserve_labels_and_counts():
    db = Mock()
    db.execute.return_value.all.return_value = [("completed", 8), ("failed", 2)]

    assert analytics.get_job_status_breakdown(Mock(), db, {"role": "admin"}) == {
        "labels": ["completed", "failed"],
        "data": [8, 2],
    }

    db.reset_mock()
    db.execute.return_value.all.return_value = [("srt", 5), (None, 1)]
    assert analytics.get_export_format_breakdown(Mock(), db, {"role": "admin"}, days=7) == {
        "labels": ["srt", "unknown"],
        "data": [5, 1],
    }
