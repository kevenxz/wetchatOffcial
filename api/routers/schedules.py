"""Schedule management routes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from api.models import (
    CreateScheduleRequest,
    ScheduleConfig,
    ScheduleExecuteResponse,
    ScheduleMode,
    ScheduleStatus,
    UpdateScheduleRequest,
)
from api.scheduler import scheduler_engine
from api.store import save_schedules, schedule_store

router = APIRouter(prefix="/schedules", tags=["schedules"])


def _utc_now() -> datetime:
    """Return current UTC datetime used by schedule APIs."""
    return datetime.now(tz=timezone.utc)


def _validate_schedule(mode: ScheduleMode, run_at: datetime | None, interval_minutes: int | None) -> None:
    """Validate required fields for each schedule mode."""
    if mode == ScheduleMode.once and run_at is None:
        raise HTTPException(status_code=400, detail="run_at is required when mode=once")
    if mode == ScheduleMode.interval and not interval_minutes:
        raise HTTPException(status_code=400, detail="interval_minutes is required when mode=interval")


def _compute_next_run(schedule: ScheduleConfig) -> datetime | None:
    """Calculate next run time for displaying/updating schedule state."""
    now = _utc_now()
    if schedule.mode == ScheduleMode.once:
        if not schedule.run_at:
            return None
        return schedule.run_at if schedule.run_at > now else now
    if schedule.mode == ScheduleMode.interval and schedule.interval_minutes:
        return now + timedelta(minutes=schedule.interval_minutes)
    return None


from datetime import timedelta


@router.get("", response_model=list[ScheduleConfig])
async def list_schedules() -> list[ScheduleConfig]:
    """List all schedules sorted by creation time (desc)."""
    return sorted(schedule_store.values(), key=lambda item: item.created_at, reverse=True)


@router.post("", response_model=ScheduleConfig, status_code=201)
async def create_schedule(body: CreateScheduleRequest) -> ScheduleConfig:
    """Create a new schedule config and persist it."""
    _validate_schedule(body.mode, body.run_at, body.interval_minutes)
    now = _utc_now()
    schedule = ScheduleConfig(
        schedule_id=str(uuid.uuid4()),
        name=body.name.strip(),
        mode=body.mode,
        run_at=body.run_at,
        interval_minutes=body.interval_minutes,
        theme_name=body.theme_name,
        account_ids=body.account_ids,
        hot_topics=body.hot_topics,
        hotspot_capture=body.hotspot_capture,
        generation_config=body.generation_config,
        enabled=body.enabled,
        status=ScheduleStatus.running if body.enabled else ScheduleStatus.stopped,
        next_run_at=(body.run_at if body.mode == ScheduleMode.once else now + timedelta(minutes=body.interval_minutes or 1))
        if body.enabled
        else None,
        created_at=now,
    )
    schedule_store[schedule.schedule_id] = schedule
    save_schedules()
    return schedule


@router.put("/{schedule_id}", response_model=ScheduleConfig)
async def update_schedule(schedule_id: str, body: UpdateScheduleRequest) -> ScheduleConfig:
    """Patch an existing schedule config."""
    schedule = schedule_store.get(schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail=f"schedule {schedule_id!r} not found")

    patch = body.model_dump(exclude_unset=True, mode="python")
    merged = {**schedule.model_dump(mode="python"), **patch}

    mode = merged.get("mode", schedule.mode)
    run_at = merged.get("run_at", schedule.run_at)
    interval_minutes = merged.get("interval_minutes", schedule.interval_minutes)
    _validate_schedule(mode, run_at, interval_minutes)

    updated_schedule = ScheduleConfig(**merged)
    updated_schedule.updated_at = _utc_now()
    if updated_schedule.status == ScheduleStatus.running and updated_schedule.enabled:
        updated_schedule.next_run_at = (
            updated_schedule.run_at
            if updated_schedule.mode == ScheduleMode.once
            else _utc_now() + timedelta(minutes=updated_schedule.interval_minutes or 1)
        )
    schedule_store[schedule_id] = updated_schedule
    save_schedules()
    return updated_schedule


@router.delete("/{schedule_id}", status_code=204, response_model=None)
async def delete_schedule(schedule_id: str) -> None:
    """Delete schedule config."""
    if schedule_id not in schedule_store:
        raise HTTPException(status_code=404, detail=f"schedule {schedule_id!r} not found")
    del schedule_store[schedule_id]
    save_schedules()


@router.post("/{schedule_id}/start", response_model=ScheduleConfig)
async def start_schedule(schedule_id: str) -> ScheduleConfig:
    """Start schedule and set next run time."""
    schedule = schedule_store.get(schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail=f"schedule {schedule_id!r} not found")
    _validate_schedule(schedule.mode, schedule.run_at, schedule.interval_minutes)
    schedule.status = ScheduleStatus.running
    schedule.enabled = True
    schedule.updated_at = _utc_now()
    schedule.next_run_at = (
        schedule.run_at
        if schedule.mode == ScheduleMode.once
        else _utc_now() + timedelta(minutes=schedule.interval_minutes or 1)
    )
    save_schedules()
    return schedule


@router.post("/{schedule_id}/stop", response_model=ScheduleConfig)
async def stop_schedule(schedule_id: str) -> ScheduleConfig:
    """Stop schedule and clear next run time."""
    schedule = schedule_store.get(schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail=f"schedule {schedule_id!r} not found")
    schedule.status = ScheduleStatus.stopped
    schedule.enabled = False
    schedule.next_run_at = None
    schedule.updated_at = _utc_now()
    save_schedules()
    return schedule


@router.post("/{schedule_id}/run-now", response_model=ScheduleExecuteResponse)
async def run_schedule_now(schedule_id: str) -> ScheduleExecuteResponse:
    """Manually execute one schedule immediately."""
    schedule = schedule_store.get(schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail=f"schedule {schedule_id!r} not found")

    try:
        task_id = await scheduler_engine.run_now(schedule_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ScheduleExecuteResponse(message="schedule executed", task_id=task_id)
