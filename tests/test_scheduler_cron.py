"""Tests for cron scheduling, timezone handling and missed-run reconciliation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from api.models import ScheduleConfig, ScheduleMode, ScheduleStatus
from api.scheduler import (
    SchedulerEngine,
    _compute_next_run,
    _count_missed_runs,
    validate_schedule_fields,
)
from api.store import schedule_store

NOW = datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc)


def _schedule(**overrides) -> ScheduleConfig:
    payload = {
        "schedule_id": "schedule-1",
        "name": "每日早报",
        "mode": ScheduleMode.cron,
        "cron_expression": "0 8 * * *",
        "timezone": "Asia/Shanghai",
        "created_at": NOW,
        "status": ScheduleStatus.running,
        "enabled": True,
    }
    payload.update(overrides)
    return ScheduleConfig(**payload)


def test_cron_next_run_respects_the_schedule_timezone() -> None:
    """08:00 Asia/Shanghai is 00:00 UTC."""
    # A minute before the trigger, the next fire is that same day.
    before = NOW - timedelta(minutes=1)
    assert _compute_next_run(_schedule(), before) == datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc)


def test_cron_next_run_is_always_strictly_in_the_future() -> None:
    """At the exact fire time the next occurrence is the following day.

    Returning ``now`` would make the scheduler re-select the same trigger on every
    tick and fire the plan continuously.
    """
    assert _compute_next_run(_schedule(), NOW) == datetime(2026, 9, 25, 0, 0, tzinfo=timezone.utc)


def test_cron_expression_supports_weekday_ranges() -> None:
    schedule = _schedule(cron_expression="30 9 * * 1-5")

    next_run = _compute_next_run(schedule, NOW)

    assert next_run is not None
    # 09:30 Shanghai == 01:30 UTC.
    assert (next_run.hour, next_run.minute) == (1, 30)


def test_invalid_cron_expression_is_reported() -> None:
    with pytest.raises(ValueError, match="cron_expression"):
        validate_schedule_fields(ScheduleMode.cron, None, None, "not a cron", "Asia/Shanghai")


def test_cron_mode_requires_an_expression() -> None:
    with pytest.raises(ValueError, match="cron_expression"):
        validate_schedule_fields(ScheduleMode.cron, None, None, "", "Asia/Shanghai")


def test_invalid_timezone_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        validate_schedule_fields(ScheduleMode.cron, None, None, "0 8 * * *", "Mars/Olympus")


def test_once_and_interval_validation_is_unchanged() -> None:
    with pytest.raises(ValueError, match="run_at"):
        validate_schedule_fields(ScheduleMode.once, None, None)
    with pytest.raises(ValueError, match="interval_minutes"):
        validate_schedule_fields(ScheduleMode.interval, None, None)
    # Valid combinations must not raise.
    validate_schedule_fields(ScheduleMode.once, NOW, None)
    validate_schedule_fields(ScheduleMode.interval, None, 30)


def test_interval_next_run_uses_the_configured_minutes() -> None:
    schedule = _schedule(mode=ScheduleMode.interval, interval_minutes=45, cron_expression=None)

    assert _compute_next_run(schedule, NOW) == NOW + timedelta(minutes=45)


def test_missed_runs_counts_skipped_interval_windows() -> None:
    schedule = _schedule(
        mode=ScheduleMode.interval,
        interval_minutes=30,
        cron_expression=None,
        next_run_at=NOW - timedelta(hours=2),
    )

    assert _count_missed_runs(schedule, NOW) == 4


def test_missed_runs_is_zero_when_not_overdue() -> None:
    schedule = _schedule(next_run_at=NOW + timedelta(hours=1))
    assert _count_missed_runs(schedule, NOW) == 0


@pytest.mark.asyncio
async def test_reconcile_rolls_cron_forward_and_records_missed_runs() -> None:
    backup = dict(schedule_store)
    schedule_store.clear()
    schedule = _schedule(next_run_at=NOW - timedelta(days=1))
    schedule_store["schedule-1"] = schedule

    engine = SchedulerEngine()
    try:
        with patch("api.scheduler._utc_now", return_value=NOW):
            with patch("api.scheduler.save_schedules"):
                await engine.reconcile_on_startup()

        # A recurring cron plan must not fire a burst; it rolls forward and only
        # records that one occurrence was skipped.
        assert schedule.missed_runs == 1
        assert schedule.next_run_at is not None
        assert schedule.next_run_at > NOW
    finally:
        schedule_store.clear()
        schedule_store.update(backup)


@pytest.mark.asyncio
async def test_reconcile_rearms_an_overdue_one_shot_plan() -> None:
    backup = dict(schedule_store)
    schedule_store.clear()
    schedule = _schedule(
        mode=ScheduleMode.once,
        cron_expression=None,
        run_at=NOW - timedelta(hours=3),
        next_run_at=NOW - timedelta(hours=3),
    )
    schedule_store["schedule-1"] = schedule

    engine = SchedulerEngine()
    try:
        with patch("api.scheduler._utc_now", return_value=NOW):
            with patch("api.scheduler.save_schedules"):
                await engine.reconcile_on_startup()
        assert schedule.next_run_at == NOW
        assert schedule.missed_runs == 1
    finally:
        schedule_store.clear()
        schedule_store.update(backup)


@pytest.mark.asyncio
async def test_reconcile_skips_stopped_schedules() -> None:
    backup = dict(schedule_store)
    schedule_store.clear()
    stopped = _schedule(status=ScheduleStatus.stopped, next_run_at=NOW - timedelta(days=1))
    schedule_store["schedule-1"] = stopped

    engine = SchedulerEngine()
    try:
        with patch("api.scheduler._utc_now", return_value=NOW):
            with patch("api.scheduler.save_schedules"):
                await engine.reconcile_on_startup()
        assert stopped.missed_runs == 0
    finally:
        schedule_store.clear()
        schedule_store.update(backup)


def test_scheduler_status_reports_stopped_before_start() -> None:
    assert SchedulerEngine().status() == "stopped"
