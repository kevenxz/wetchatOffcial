"""In-process scheduler for periodic workflow execution."""
from __future__ import annotations

import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone

import structlog

from api.models import (
    PlatformType,
    PushRecord,
    PushStatus,
    ScheduleConfig,
    ScheduleMode,
    ScheduleStatus,
    TaskResponse,
    TaskStatus,
)
from api.hotspot_snapshot import maybe_refresh_hotspot_snapshot
from api.store import (
    get_account,
    get_custom_themes,
    get_preset_themes,
    get_style_config,
    save_schedules,
    save_tasks,
    schedule_store,
    task_store,
)
from api.workflow_sync import sync_task_from_workflow_event
from api.ws_manager import manager
from workflow.graph import run_workflow
from workflow.utils.wechat_draft_service import push_article_to_wechat_draft

logger = structlog.get_logger(__name__)


def _utc_now() -> datetime:
    """Return current UTC datetime for all scheduler timestamps."""
    return datetime.now(tz=timezone.utc)


def _resolve_theme_config(theme_name: str | None) -> tuple[str, dict[str, str]]:
    """Resolve a theme name to actual style config.

    Resolution order:
    1. Current global style (`__current__`)
    2. Preset theme
    3. Custom theme
    """
    normalized = (theme_name or "").strip()
    if not normalized or normalized == "__current__":
        return "__current__", get_style_config()

    preset = get_preset_themes()
    if normalized in preset:
        return normalized, preset[normalized]

    custom = get_custom_themes()
    if normalized in custom:
        return normalized, custom[normalized]

    raise ValueError(f"theme {normalized!r} not found")


def _cron_next_run(expression: str, timezone_name: str, now: datetime) -> datetime | None:
    """Next fire time for a cron expression, evaluated in its own timezone.

    APScheduler's ``CronTrigger`` is used for parsing so the accepted syntax
    matches the documented 5-field cron form. The result is always strictly in the
    future: a fire time equal to ``now`` would otherwise be re-selected on every
    scheduler tick and the plan would fire continuously.
    """
    cleaned = (expression or "").strip()
    if not cleaned:
        return None
    try:
        from zoneinfo import ZoneInfo

        from apscheduler.triggers.cron import CronTrigger

        zone = ZoneInfo(timezone_name or "Asia/Shanghai")
        trigger = CronTrigger.from_crontab(cleaned, timezone=zone)
        reference = now.astimezone(zone)
        next_fire = trigger.get_next_fire_time(None, reference)
        if next_fire is not None and next_fire <= reference:
            next_fire = trigger.get_next_fire_time(next_fire, reference + timedelta(seconds=1))
    except Exception as exc:  # noqa: BLE001
        logger.warning("cron_parse_failed", expression=cleaned, timezone=timezone_name, error=str(exc))
        return None
    return next_fire.astimezone(timezone.utc) if next_fire else None


def _compute_next_run(schedule: ScheduleConfig, now: datetime | None = None) -> datetime | None:
    """Compute next trigger time based on schedule mode and current time."""
    now = now or _utc_now()
    if schedule.mode == ScheduleMode.once:
        if schedule.run_at is None:
            return None
        if schedule.run_at < now:
            return now
        return schedule.run_at

    if schedule.mode == ScheduleMode.interval and schedule.interval_minutes:
        return now + timedelta(minutes=schedule.interval_minutes)

    if schedule.mode == ScheduleMode.cron:
        return _cron_next_run(schedule.cron_expression or "", schedule.timezone, now)
    return None


def _count_missed_runs(schedule: ScheduleConfig, now: datetime) -> int:
    """How many triggers were skipped while the process was down."""
    next_run = schedule.next_run_at
    if next_run is None or next_run >= now:
        return 0

    if schedule.mode == ScheduleMode.interval and schedule.interval_minutes:
        window = timedelta(minutes=schedule.interval_minutes)
        return max(1, int((now - next_run) // window))
    # once / cron: only the single overdue trigger is treated as missed.
    return 1


def validate_schedule_fields(
    mode: ScheduleMode,
    run_at: datetime | None,
    interval_minutes: int | None,
    cron_expression: str | None = None,
    timezone_name: str | None = None,
) -> None:
    """Validate the required fields for one schedule mode.

    Raises :class:`ValueError` with an operator-facing Chinese message.
    """
    if mode == ScheduleMode.once and run_at is None:
        raise ValueError("mode=once 时必须提供 run_at")
    if mode == ScheduleMode.interval and not interval_minutes:
        raise ValueError("mode=interval 时必须提供 interval_minutes")

    # The timezone is validated first because cron evaluation depends on it, and a
    # bad timezone would otherwise surface as a confusing cron-parse error.
    if timezone_name:
        try:
            from zoneinfo import ZoneInfo

            ZoneInfo(timezone_name)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"timezone {timezone_name!r} 不是有效的时区") from exc

    if mode == ScheduleMode.cron:
        if not (cron_expression or "").strip():
            raise ValueError("mode=cron 时必须提供 cron_expression")
        if _cron_next_run(cron_expression or "", timezone_name or "Asia/Shanghai", _utc_now()) is None:
            raise ValueError("cron_expression 无法解析，请使用标准 5 段式表达式，例如 '0 8 * * 1-5'")


def compute_next_run(schedule: ScheduleConfig, now: datetime | None = None) -> datetime | None:
    """Public wrapper around the next-run computation used by the API layer."""
    return _compute_next_run(schedule, now)


def _resolve_schedule_keywords(schedule: ScheduleConfig) -> str:
    """Resolve the initial workflow keywords for one schedule run."""
    if schedule.hotspot_capture.enabled:
        # Hotspot-enabled runs always start from schedule name, then capture node rewrites keywords.
        return schedule.name
    if schedule.hot_topics:
        return random.choice(schedule.hot_topics)
    return schedule.name


class SchedulerEngine:
    """Background scheduler loop.

    Responsibilities:
    - Poll schedule_store periodically
    - Trigger workflow execution on due schedules
    - Push generated articles to configured accounts
    """

    def __init__(self) -> None:
        """Initialize loop task holder and running guard set."""
        self._task: asyncio.Task | None = None
        self._running_schedule_ids: set[str] = set()
        self._running_task_ids: dict[str, str] = {}

    def start(self) -> None:
        """Start background scheduler loop if not already running."""
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop())
        logger.info("scheduler_started")

    def status(self) -> str:
        """Return ``running`` / ``stopped`` for the health endpoint."""
        return "running" if self._task and not self._task.done() else "stopped"

    async def stop(self) -> None:
        """Gracefully stop background scheduler loop."""
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        logger.info("scheduler_stopped")

    async def run_now(self, schedule_id: str) -> str:
        """Execute one schedule immediately and return created task_id."""
        schedule = schedule_store.get(schedule_id)
        if schedule is None:
            raise ValueError(f"schedule {schedule_id!r} not found")
        # If an execution is already in progress, return the existing task id
        # instead of raising, so "stop -> run now" won't fail with UX-level error.
        if schedule_id in self._running_schedule_ids:
            running_task_id = self._running_task_ids.get(schedule_id)
            if running_task_id:
                logger.info(
                    "schedule_run_now_reused_running_task",
                    schedule_id=schedule_id,
                    task_id=running_task_id,
                )
                return running_task_id
        return await self._execute_schedule(schedule, trigger="manual")

    async def _run_loop(self) -> None:
        """Scheduler main loop; ticks every 20 seconds."""
        while True:
            try:
                await self._tick()
            except Exception as exc:  # noqa: BLE001
                logger.exception("scheduler_tick_failed", error=str(exc))
            await asyncio.sleep(20)

    async def reconcile_on_startup(self) -> None:
        """Reconcile schedule state after a restart.

        Overdue :class:`ScheduleMode.once` plans are re-armed to fire immediately;
        recurring plans record how many triggers were skipped while the process was
        down and roll forward to the next real occurrence instead of firing a burst.
        """
        now = _utc_now()
        reconciled = 0
        for schedule in list(schedule_store.values()):
            if schedule.status != ScheduleStatus.running or not schedule.enabled:
                continue
            missed = _count_missed_runs(schedule, now)
            if missed:
                schedule.missed_runs = int(schedule.missed_runs or 0) + missed
                logger.warning(
                    "schedule_missed_runs",
                    schedule_id=schedule.schedule_id,
                    missed=missed,
                    last_next_run_at=schedule.next_run_at.isoformat() if schedule.next_run_at else None,
                )
            if schedule.mode == ScheduleMode.once and schedule.next_run_at and schedule.next_run_at <= now:
                # A one-shot plan that was due while offline still deserves to run.
                schedule.next_run_at = now
            else:
                schedule.next_run_at = _compute_next_run(schedule, now)
            schedule.updated_at = now
            reconciled += 1

        if reconciled:
            save_schedules()
            logger.info("scheduler_reconciled", schedules=reconciled)

    async def _tick(self) -> None:
        """Single scheduler tick: refresh hotspots if due, then run due schedules."""
        # Hotspot refresh rides the existing 20s loop rather than a second timer. It is
        # internally rate-limited by HOTSPOT_REFRESH_INTERVAL_MINUTES and swallows its own
        # errors, so it can never block or fail schedule execution.
        await maybe_refresh_hotspot_snapshot()

        now = _utc_now()
        for schedule in list(schedule_store.values()):
            if not schedule.enabled or schedule.status != ScheduleStatus.running:
                continue
            if schedule.next_run_at is None:
                schedule.next_run_at = _compute_next_run(schedule, now)
                schedule.updated_at = now
                save_schedules()
            if schedule.next_run_at and schedule.next_run_at <= now:
                # Due schedule: execute now.
                await self._execute_schedule(schedule, trigger="timer")

    async def _execute_schedule(self, schedule: ScheduleConfig, trigger: str) -> str:
        """Execute one schedule end-to-end.

        Flow:
        1. Create a normal TaskResponse record
        2. Run workflow with `skip_auto_push=True`
        3. Push generated article to configured accounts using theme
        4. Update schedule runtime metadata
        """
        if schedule.schedule_id in self._running_schedule_ids:
            raise ValueError("schedule is already running")

        self._running_schedule_ids.add(schedule.schedule_id)
        now = _utc_now()
        keywords = _resolve_schedule_keywords(schedule)
        hotspot_capture_config = schedule.hotspot_capture.model_dump(mode="python")

        task = TaskResponse(
            task_id=str(uuid.uuid4()),
            keywords=keywords,
            original_keywords=keywords,
            generation_config=schedule.generation_config,
            status=TaskStatus.pending,
            created_at=now,
            hotspot_capture_config=hotspot_capture_config,
            article_theme=schedule.theme_name,
            publish_account_ids=list(schedule.account_ids),
        )
        task_store[task.task_id] = task
        self._running_task_ids[schedule.schedule_id] = task.task_id
        save_tasks()

        logger.info(
            "schedule_triggered",
            schedule_id=schedule.schedule_id,
            trigger=trigger,
            task_id=task.task_id,
            keywords=keywords,
            hotspot_capture_enabled=schedule.hotspot_capture.enabled,
        )

        try:
            await run_workflow(
                task_id=task.task_id,
                keywords=task.keywords,
                generation_config=task.generation_config.model_dump(),
                hotspot_capture_config=hotspot_capture_config,
                progress_callback=self._progress_callback,
                skip_auto_push=True,
            )

            task = task_store.get(task.task_id, task)
            # Push only when article generation succeeded and accounts are configured.
            if task.status == TaskStatus.done and task.generated_article and schedule.account_ids:
                await self._push_task(task, schedule.account_ids, schedule.theme_name)

            schedule.last_run_at = _utc_now()
            schedule.last_error = None
            if schedule.mode == ScheduleMode.once:
                schedule.status = ScheduleStatus.stopped
                schedule.enabled = False
                schedule.next_run_at = None
            else:
                schedule.next_run_at = _compute_next_run(schedule, _utc_now())
            schedule.updated_at = _utc_now()
            save_schedules()
            save_tasks()
        except Exception as exc:  # noqa: BLE001
            schedule.last_error = str(exc)
            schedule.updated_at = _utc_now()
            if schedule.mode == ScheduleMode.interval:
                schedule.next_run_at = _compute_next_run(schedule, _utc_now())
            else:
                schedule.status = ScheduleStatus.stopped
                schedule.enabled = False
                schedule.next_run_at = None
            save_schedules()
            logger.exception("schedule_execute_failed", schedule_id=schedule.schedule_id, error=str(exc))
        finally:
            self._running_schedule_ids.discard(schedule.schedule_id)
            self._running_task_ids.pop(schedule.schedule_id, None)

        return task.task_id

    async def _progress_callback(self, task_id: str, data: dict) -> None:
        """Sync workflow progress payload to task_store and websocket clients."""
        task = task_store.get(task_id)
        if task:
            sync_task_from_workflow_event(task, data)
            save_tasks()
        await manager.broadcast(task_id, data)

    async def _push_task(self, task: TaskResponse, account_ids: list[str], theme_name: str | None) -> None:
        """Push generated article to multiple accounts and record each result."""
        resolved_theme_name, style_config = _resolve_theme_config(theme_name)
        publish_policy = dict((task.config_snapshot or {}).get("publish_policy") or {})
        auto_publish = bool(publish_policy.get("auto_publish", False))
        task.article_theme = resolved_theme_name
        for account_id in account_ids:
            account = get_account(account_id)
            now = _utc_now()
            if account is None:
                # Keep failure records for missing accounts to make troubleshooting easier.
                task.push_records.append(
                    PushRecord(
                        push_id=str(uuid.uuid4()),
                        account_id=account_id,
                        account_name="unknown",
                        platform=PlatformType.wechat_mp,
                        pushed_at=now,
                        status=PushStatus.failed,
                        error=f"account {account_id!r} not found",
                        publish_status="failed",
                        theme_name=resolved_theme_name,
                    )
                )
                continue
            if not account.enabled or account.platform != PlatformType.wechat_mp:
                # Only enabled WeChat public accounts are supported for push.
                task.push_records.append(
                    PushRecord(
                        push_id=str(uuid.uuid4()),
                        account_id=account.account_id,
                        account_name=account.name,
                        platform=account.platform,
                        pushed_at=now,
                        status=PushStatus.failed,
                        error="account disabled or unsupported platform",
                        publish_status="failed",
                        theme_name=resolved_theme_name,
                    )
                )
                continue

            try:
                # Theme style is injected during markdown -> html rendering.
                draft_info = await push_article_to_wechat_draft(
                    article=task.generated_article or {},
                    app_id=account.app_id,
                    app_secret=account.app_secret,
                    style_config=style_config,
                    auto_publish=auto_publish,
                    publish_poll_interval_seconds=float(publish_policy.get("publish_poll_interval_seconds") or 5),
                    publish_poll_max_attempts=int(publish_policy.get("publish_poll_max_attempts") or 10),
                )
                task.push_records.append(
                    PushRecord(
                        push_id=str(uuid.uuid4()),
                        account_id=account.account_id,
                        account_name=account.name,
                        platform=account.platform,
                        pushed_at=now,
                        status=PushStatus.success,
                        draft_info=draft_info,
                        publish_status=str(draft_info.get("publish_status") or "draft_only"),
                        publish_id=str(draft_info.get("publish_id") or "") or None,
                        theme_name=resolved_theme_name,
                    )
                )
                task.draft_info = draft_info
            except Exception as exc:  # noqa: BLE001
                task.push_records.append(
                    PushRecord(
                        push_id=str(uuid.uuid4()),
                        account_id=account.account_id,
                        account_name=account.name,
                        platform=account.platform,
                        pushed_at=now,
                        status=PushStatus.failed,
                        error=str(exc),
                        publish_status="failed",
                        theme_name=resolved_theme_name,
                    )
                )
            task.updated_at = _utc_now()


scheduler_engine = SchedulerEngine()
