"""Shared in-memory and JSON-backed storage."""
from __future__ import annotations

import json
import os
from pathlib import Path

from api.models import (
    AccountConfig,
    ImageModelConfig,
    ModelConfig,
    ReviewQueueItem,
    ScheduleConfig,
    TaskResponse,
    TextModelConfig,
    TopicCandidate,
    UserAccount,
    WorkflowRunStepRecord,
)

DATA_DIR = Path("data")
TASKS_FILE = DATA_DIR / "tasks.json"
STYLE_CONFIG_FILE = DATA_DIR / "style_config.json"
CUSTOM_THEMES_FILE = DATA_DIR / "custom_themes.json"
MODEL_CONFIG_FILE = DATA_DIR / "model_config.json"
ACCOUNTS_FILE = DATA_DIR / "accounts.json"
USERS_FILE = DATA_DIR / "users.json"
SCHEDULES_FILE = DATA_DIR / "schedules.json"
TOPICS_FILE = DATA_DIR / "topics.json"
REVIEWS_FILE = DATA_DIR / "reviews.json"
WORKFLOW_RUN_STEPS_FILE = DATA_DIR / "workflow_run_steps.json"

task_store: dict[str, TaskResponse] = {}
topic_store: dict[str, TopicCandidate] = {}
review_store: dict[str, ReviewQueueItem] = {}
workflow_run_step_store: dict[str, WorkflowRunStepRecord] = {}


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict) -> None:
    _ensure_data_dir()
    temp_file = path.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    temp_file.replace(path)


def load_tasks() -> None:
    if not TASKS_FILE.exists():
        return
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        for task_id, payload in data.items():
            task_store[task_id] = TaskResponse(**payload)
    except Exception:
        return


def save_tasks() -> None:
    payload = {task_id: task.model_dump(mode="json") for task_id, task in task_store.items()}
    _write_json(TASKS_FILE, payload)


def load_topics() -> None:
    if not TOPICS_FILE.exists():
        return
    try:
        with open(TOPICS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        for topic_id, payload in data.items():
            topic_store[topic_id] = TopicCandidate(**payload)
    except Exception:
        return


def save_topics() -> None:
    payload = {topic_id: topic.model_dump(mode="json") for topic_id, topic in topic_store.items()}
    _write_json(TOPICS_FILE, payload)


def load_reviews() -> None:
    if not REVIEWS_FILE.exists():
        return
    try:
        with open(REVIEWS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        for review_id, payload in data.items():
            review_store[review_id] = ReviewQueueItem(**payload)
    except Exception:
        return


def save_reviews() -> None:
    payload = {review_id: item.model_dump(mode="json") for review_id, item in review_store.items()}
    _write_json(REVIEWS_FILE, payload)


def load_workflow_run_steps() -> None:
    if not WORKFLOW_RUN_STEPS_FILE.exists():
        return
    try:
        with open(WORKFLOW_RUN_STEPS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        for run_step_id, payload in data.items():
            workflow_run_step_store[run_step_id] = WorkflowRunStepRecord(**payload)
    except Exception:
        return


def save_workflow_run_steps() -> None:
    payload = {
        run_step_id: step.model_dump(mode="json")
        for run_step_id, step in workflow_run_step_store.items()
    }
    _write_json(WORKFLOW_RUN_STEPS_FILE, payload)


DEFAULT_STYLE: dict[str, str] = {
    "container": "padding: 0 8px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif; color: #2c3e50; line-height: 1.8; font-size: 16px; letter-spacing: 0.3px; word-break: break-word; overflow-wrap: break-word;",
    "h1": "font-size: 28px; font-weight: 700; color: #1a1a1a; margin: 10px 0 20px; text-align: center; padding-bottom: 12px; border-bottom: 2px solid #07c160; letter-spacing: 1px; line-height: 1.4;",
    "h2": "font-size: 22px; font-weight: 600; color: #2c3e50; margin: 20px 0 14px; padding-left: 12px; border-left: 4px solid #07c160; line-height: 1.4; letter-spacing: 0.5px;",
    "h3": "font-size: 19px; font-weight: 600; color: #34495e; margin: 24px 0 12px; padding-left: 10px; border-left: 3px solid #07c160; letter-spacing: 0.3px;",
    "h4": "font-size: 17px; font-weight: 600; color: #07c160; margin: 20px 0 10px; letter-spacing: 0.3px;",
    "h5": "font-size: 16px; font-weight: 600; color: #5a6c7d; margin: 18px 0 8px;",
    "h6": "font-size: 15px; font-weight: 600; color: #7f8c8d; margin: 16px 0 8px;",
    "p": "margin: 8px 0; font-size: 16px; color: #34495e; line-height: 1.8; letter-spacing: 0.5px;",
    "strong": "font-weight: 600; color: #07c160; letter-spacing: 0.2px;",
    "em": "font-style: italic; color: #07c160; font-weight: 500;",
    "del": "text-decoration: line-through; color: #94a3b8; opacity: 0.7;",
    "blockquote": "border-left: 4px solid #07c160; background: #f6f8fa; padding: 16px 20px; margin: 20px 0; color: #475569; border-radius: 2px;",
    "ul": "padding-left: 24px; list-style-type: disc; color: #34495e; margin: 8px 0;",
    "ol": "padding-left: 24px; list-style-type: decimal; color: #34495e; margin: 8px 0;",
    "li": "padding-left: 4px; margin: 8px 0; line-height: 1.8; font-size: 16px; color: #34495e;",
    "a": "color: #07c160; text-decoration: none; border-bottom: 1px solid #07c160; font-weight: 500;",
    "hr": "border: none; height: 1px; background: #e2e8f0; margin: 28px 0;",
    "img": "display: block; margin: 24px auto; max-width: 100%; border-radius: 4px;",
    "figure": "margin: 24px 0; display: flex; flex-direction: column; justify-content: center; align-items: center;",
    "figcaption": "text-align: center; font-size: 14px; color: #94a3b8; margin-top: 8px; letter-spacing: 0.2px;",
    "code": "background: #f0fdf4; padding: 3px 6px; border-radius: 3px; color: #059669; font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, monospace; font-size: 0.9em; margin: 0 3px; border: 1px solid #bbf7d0;",
    "pre": "margin: 16px 0; overflow-x: auto;",
    "pre code": "display: block; background: #f8fafc; padding: 16px; border-radius: 4px; overflow-x: auto; font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, monospace; font-size: 14px; line-height: 1.6; color: #334155; border: 1px solid #e2e8f0;",
    "table": "display: table; width: 100%; text-align: left; border-collapse: collapse; margin: 16px 0;",
    "th": "border: 1px solid #e2e8f0; padding: 10px 14px; font-size: 15px; color: #065f46; line-height: 1.6; background: #f0fdf4; font-weight: 600; letter-spacing: 0.3px;",
    "td": "border: 1px solid #e2e8f0; padding: 10px 14px; font-size: 15px; color: #334155; line-height: 1.6;",
}

PRESET_THEMES: dict[str, dict[str, str]] = {
    "默认主题": DEFAULT_STYLE,
    "学术论文": {
        "h1": "font-size: 24px; font-weight: bold; margin-top: 28px; margin-bottom: 16px; color: #1a1a1a; line-height: 1.35; text-align: center;",
        "h2": "font-size: 18px; font-weight: bold; margin-top: 24px; margin-bottom: 12px; color: #1a1a1a; border-bottom: 2px solid #333; padding-bottom: 4px;",
        "h3": "font-size: 16px; font-weight: bold; margin-top: 18px; margin-bottom: 8px; color: #333;",
        "p": "font-size: 15px; line-height: 2; margin-bottom: 14px; color: #333; text-indent: 2em; letter-spacing: 0.3px;",
        "strong": "font-weight: bold; color: #000;",
        "blockquote": "padding: 12px 16px; border-left: 3px solid #999; background-color: #fafafa; color: #555; font-size: 14px; margin-bottom: 14px; font-style: italic;",
        "ul": "margin-bottom: 14px; padding-left: 24px; color: #333;",
        "ol": "margin-bottom: 14px; padding-left: 24px; color: #333;",
        "li": "font-size: 15px; line-height: 2; margin-bottom: 4px;",
        "a": "color: #0645ad; text-decoration: underline;",
    },
    "极光玻璃": {
        "h1": "font-size: 24px; font-weight: 800; margin-top: 28px; margin-bottom: 16px; color: #6366f1; line-height: 1.3; background: linear-gradient(90deg, #6366f1, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent;",
        "h2": "font-size: 19px; font-weight: 700; margin-top: 22px; margin-bottom: 12px; color: #7c3aed; border-left: 4px solid #a855f7; padding-left: 10px;",
        "h3": "font-size: 16px; font-weight: 600; margin-top: 16px; margin-bottom: 8px; color: #8b5cf6;",
        "p": "font-size: 15px; line-height: 1.8; margin-bottom: 16px; color: #4b5563; letter-spacing: 0.5px;",
        "strong": "font-weight: bold; color: #7c3aed;",
        "blockquote": "padding: 12px 16px; border-left: 4px solid #c084fc; background: linear-gradient(135deg, #f5f3ff, #ede9fe); color: #6d28d9; font-size: 14px; margin-bottom: 16px; border-radius: 0 8px 8px 0;",
        "ul": "margin-bottom: 16px; padding-left: 20px; color: #4b5563;",
        "ol": "margin-bottom: 16px; padding-left: 20px; color: #4b5563;",
        "li": "font-size: 15px; line-height: 1.8; margin-bottom: 6px;",
        "a": "color: #7c3aed; text-decoration: none; border-bottom: 1px dashed #a78bfa;",
    },
    "赛博朋克": {
        "h1": "font-size: 24px; font-weight: 900; margin-top: 28px; margin-bottom: 16px; color: #00ff9f; line-height: 1.3; text-transform: uppercase; letter-spacing: 2px;",
        "h2": "font-size: 19px; font-weight: 700; margin-top: 22px; margin-bottom: 12px; color: #00d4ff; border-left: 4px solid #ff0080; padding-left: 10px;",
        "h3": "font-size: 16px; font-weight: 600; margin-top: 16px; margin-bottom: 8px; color: #ff0080;",
        "p": "font-size: 15px; line-height: 1.75; margin-bottom: 16px; color: #e0e0e0; letter-spacing: 0.5px;",
        "strong": "font-weight: bold; color: #ff0080;",
        "blockquote": "padding: 12px 16px; border-left: 4px solid #00ff9f; background-color: #1a1a2e; color: #00d4ff; font-size: 14px; margin-bottom: 16px;",
        "ul": "margin-bottom: 16px; padding-left: 20px; color: #e0e0e0;",
        "ol": "margin-bottom: 16px; padding-left: 20px; color: #e0e0e0;",
        "li": "font-size: 15px; line-height: 1.75; margin-bottom: 6px;",
        "a": "color: #00ff9f; text-decoration: none;",
    },
    "莫兰迪森林": {
        "h1": "font-size: 22px; font-weight: bold; margin-top: 28px; margin-bottom: 16px; color: #4a6741; line-height: 1.4;",
        "h2": "font-size: 18px; font-weight: bold; margin-top: 22px; margin-bottom: 12px; color: #5b7a50; border-left: 4px solid #8fae82; padding-left: 8px;",
        "h3": "font-size: 16px; font-weight: bold; margin-top: 16px; margin-bottom: 8px; color: #6b8c5e;",
        "p": "font-size: 15px; line-height: 1.8; margin-bottom: 16px; color: #5c5c5c; letter-spacing: 0.3px;",
        "strong": "font-weight: bold; color: #4a6741;",
        "blockquote": "padding: 12px 16px; border-left: 4px solid #8fae82; background-color: #f2f5ef; color: #6b8c5e; font-size: 14px; margin-bottom: 16px;",
        "ul": "margin-bottom: 16px; padding-left: 20px; color: #5c5c5c;",
        "ol": "margin-bottom: 16px; padding-left: 20px; color: #5c5c5c;",
        "li": "font-size: 15px; line-height: 1.8; margin-bottom: 6px;",
        "a": "color: #4a6741; text-decoration: none; border-bottom: 1px solid #8fae82;",
    },
    "黑金奢华": {
        "h1": "font-size: 24px; font-weight: 800; margin-top: 28px; margin-bottom: 16px; color: #d4af37; line-height: 1.35;",
        "h2": "font-size: 19px; font-weight: 700; margin-top: 22px; margin-bottom: 12px; color: #c5a028; border-left: 4px solid #d4af37; padding-left: 10px;",
        "h3": "font-size: 16px; font-weight: 600; margin-top: 16px; margin-bottom: 8px; color: #b8960f;",
        "p": "font-size: 15px; line-height: 1.75; margin-bottom: 16px; color: #d0d0d0; letter-spacing: 0.5px;",
        "strong": "font-weight: bold; color: #d4af37;",
        "blockquote": "padding: 12px 16px; border-left: 4px solid #d4af37; background-color: #1c1c1c; color: #c5a028; font-size: 14px; margin-bottom: 16px;",
        "ul": "margin-bottom: 16px; padding-left: 20px; color: #d0d0d0;",
        "ol": "margin-bottom: 16px; padding-left: 20px; color: #d0d0d0;",
        "li": "font-size: 15px; line-height: 1.75; margin-bottom: 6px;",
        "a": "color: #d4af37; text-decoration: none;",
    },
}

_style_config: dict[str, str] = {}
_custom_themes: dict[str, dict[str, str]] = {}
_model_config: ModelConfig | None = None


def _merge_default_style(config: dict[str, str]) -> dict[str, str]:
    return {**DEFAULT_STYLE, **config}


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {}


def get_preset_themes() -> dict[str, dict[str, str]]:
    return {name: _merge_default_style(config) for name, config in PRESET_THEMES.items()}


def get_custom_themes() -> dict[str, dict[str, str]]:
    global _custom_themes
    if not _custom_themes:
        raw_themes = _load_json(CUSTOM_THEMES_FILE)
        _custom_themes = {name: _merge_default_style(config) for name, config in raw_themes.items()}
    return dict(_custom_themes)


def _save_custom_themes() -> None:
    payload = {name: config for name, config in _custom_themes.items()}
    _write_json(CUSTOM_THEMES_FILE, payload)


def create_custom_theme(name: str, config: dict[str, str]) -> dict[str, dict[str, str]]:
    cleaned_name = name.strip()
    if not cleaned_name:
        raise ValueError("主题名称不能为空")
    if cleaned_name in PRESET_THEMES or cleaned_name in get_custom_themes():
        raise ValueError("主题名称已存在")
    _custom_themes[cleaned_name] = _merge_default_style(config)
    _save_custom_themes()
    return get_custom_themes()


def update_custom_theme(theme_name: str, next_name: str, config: dict[str, str]) -> dict[str, dict[str, str]]:
    themes = get_custom_themes()
    if theme_name not in themes:
        raise ValueError("未找到对应的自定义主题")
    cleaned_name = next_name.strip()
    if not cleaned_name:
        raise ValueError("主题名称不能为空")
    if cleaned_name != theme_name and (cleaned_name in PRESET_THEMES or cleaned_name in themes):
        raise ValueError("主题名称已存在")
    if cleaned_name != theme_name:
        del _custom_themes[theme_name]
    _custom_themes[cleaned_name] = _merge_default_style(config)
    _save_custom_themes()
    return get_custom_themes()


def delete_custom_theme(theme_name: str) -> dict[str, dict[str, str]]:
    themes = get_custom_themes()
    if theme_name not in themes:
        raise ValueError("未找到对应的自定义主题")
    del _custom_themes[theme_name]
    _save_custom_themes()
    return get_custom_themes()


def import_custom_themes(payload: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    if not payload:
        raise ValueError("导入内容不能为空")
    get_custom_themes()
    for theme_name, config in payload.items():
        cleaned_name = theme_name.strip()
        if not cleaned_name:
            raise ValueError("存在空主题名称")
        if cleaned_name in PRESET_THEMES:
            raise ValueError(f"主题名称冲突: {cleaned_name}")
        _custom_themes[cleaned_name] = _merge_default_style(config)
    _save_custom_themes()
    return get_custom_themes()


def get_style_config() -> dict[str, str]:
    global _style_config
    if _style_config:
        return _style_config
    raw_config = _load_json(STYLE_CONFIG_FILE)
    _style_config = _merge_default_style(raw_config) if raw_config else dict(DEFAULT_STYLE)
    return _style_config


def save_style_config(new_style: dict[str, str]) -> dict[str, str]:
    global _style_config
    current = get_style_config()
    current.update(new_style)
    _style_config = _merge_default_style(current)
    _write_json(STYLE_CONFIG_FILE, _style_config)
    return dict(_style_config)


def _is_enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _default_model_config_from_env() -> ModelConfig:
    text_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    text_base_url = (os.getenv("OPENAI_API_BASE") or "").strip() or None
    text_model = (os.getenv("OPENAI_MODEL") or "gpt-4o").strip() or "gpt-4o"

    image_enabled = _is_enabled(os.getenv("DALLE_ENABLED"))
    image_api_key = (os.getenv("IMAGE_API_KEY") or text_api_key).strip()
    image_base_url = (os.getenv("IMAGE_API_BASE") or text_base_url or "").strip() or None
    image_model = (
        (os.getenv("IMAGE_MODEL") or os.getenv("DALLE_MODEL") or "dall-e-3").strip()
        or "dall-e-3"
    )

    return ModelConfig(
        text=TextModelConfig(
            api_key=text_api_key,
            base_url=text_base_url,
            model=text_model,
        ),
        image=ImageModelConfig(
            enabled=image_enabled,
            api_key=image_api_key,
            base_url=image_base_url,
            model=image_model,
        ),
    )


def get_model_config() -> ModelConfig:
    global _model_config
    if _model_config is not None:
        return _model_config.model_copy(deep=True)

    raw_config = _load_json(MODEL_CONFIG_FILE)
    if raw_config:
        try:
            _model_config = ModelConfig(**raw_config)
            return _model_config.model_copy(deep=True)
        except Exception:
            pass

    return _default_model_config_from_env()


def save_model_config(new_config: ModelConfig) -> ModelConfig:
    global _model_config
    _model_config = new_config.model_copy(deep=True)
    _write_json(MODEL_CONFIG_FILE, _model_config.model_dump(mode="json"))
    return _model_config.model_copy(deep=True)


_account_store: dict[str, AccountConfig] = {}
_user_store: dict[str, UserAccount] = {}
schedule_store: dict[str, ScheduleConfig] = {}


def load_accounts() -> None:
    """从 JSON 文件加载账号配置到内存。"""
    if not ACCOUNTS_FILE.exists():
        return
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        for account_id, payload in data.items():
            _account_store[account_id] = AccountConfig(**payload)
    except Exception:
        return


def load_users() -> None:
    """Load system users from JSON file."""
    if not USERS_FILE.exists():
        return
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        for user_id, payload in data.items():
            _user_store[user_id] = UserAccount(**payload)
    except Exception:
        return


def _save_accounts() -> None:
    """原子写入账号配置到 JSON 文件。"""
    payload = {aid: acc.model_dump(mode="json") for aid, acc in _account_store.items()}
    _write_json(ACCOUNTS_FILE, payload)


def _save_users() -> None:
    payload = {uid: user.model_dump(mode="json") for uid, user in _user_store.items()}
    _write_json(USERS_FILE, payload)


def load_schedules() -> None:
    """Load schedule configs from JSON file."""
    if not SCHEDULES_FILE.exists():
        return
    try:
        with open(SCHEDULES_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        for schedule_id, payload in data.items():
            schedule_store[schedule_id] = ScheduleConfig(**payload)
    except Exception:
        return


def save_schedules() -> None:
    """Persist schedule configs to JSON file."""
    payload = {sid: schedule.model_dump(mode="json") for sid, schedule in schedule_store.items()}
    _write_json(SCHEDULES_FILE, payload)


def list_accounts() -> list[AccountConfig]:
    """返回所有账号，按创建时间倒序。"""
    return sorted(_account_store.values(), key=lambda a: a.created_at, reverse=True)


def list_users() -> list[UserAccount]:
    return sorted(_user_store.values(), key=lambda u: u.created_at, reverse=True)


def get_account(account_id: str) -> AccountConfig | None:
    """按 ID 查询账号。"""
    return _account_store.get(account_id)


def get_user(user_id: str) -> UserAccount | None:
    return _user_store.get(user_id)


def get_user_by_username(username: str) -> UserAccount | None:
    lowered = username.strip().lower()
    for user in _user_store.values():
        if user.username == lowered:
            return user
    return None


def create_account(account: AccountConfig) -> AccountConfig:
    """新增账号并持久化。"""
    _account_store[account.account_id] = account
    _save_accounts()
    return account


def create_user(user: UserAccount) -> UserAccount:
    existing = get_user_by_username(user.username)
    if existing is not None and existing.user_id != user.user_id:
        raise ValueError(f"用户 {user.username!r} 已存在")
    _user_store[user.user_id] = user
    _save_users()
    return user


def update_account(account_id: str, patch: dict) -> AccountConfig:
    """差量更新账号字段并持久化，返回更新后的对象。"""
    account = _account_store.get(account_id)
    if account is None:
        raise ValueError(f"账号 {account_id!r} 不存在")
    updated = account.model_copy(update=patch)
    _account_store[account_id] = updated
    _save_accounts()
    return updated


def update_user(user_id: str, patch: dict) -> UserAccount:
    user = _user_store.get(user_id)
    if user is None:
        raise ValueError(f"用户 {user_id!r} 不存在")
    updated = user.model_copy(update=patch)
    duplicate = get_user_by_username(updated.username)
    if duplicate is not None and duplicate.user_id != user_id:
        raise ValueError(f"用户 {updated.username!r} 已存在")
    _user_store[user_id] = updated
    _save_users()
    return updated


def delete_account(account_id: str) -> None:
    """删除账号并持久化。"""
    if account_id not in _account_store:
        raise ValueError(f"账号 {account_id!r} 不存在")
    del _account_store[account_id]
    _save_accounts()


def delete_user(user_id: str) -> None:
    if user_id not in _user_store:
        raise ValueError(f"用户 {user_id!r} 不存在")
    del _user_store[user_id]
    _save_users()


def list_topics(status: str | None = None) -> list[TopicCandidate]:
    topics = list(topic_store.values())
    if status is not None:
        topics = [topic for topic in topics if topic.status.value == status]
    return sorted(topics, key=lambda topic: topic.created_at, reverse=True)


def get_topic(topic_id: str) -> TopicCandidate | None:
    return topic_store.get(topic_id)


def create_topic(topic: TopicCandidate) -> TopicCandidate:
    topic_store[topic.topic_id] = topic
    save_topics()
    return topic


def update_topic(topic_id: str, patch: dict) -> TopicCandidate:
    topic = topic_store.get(topic_id)
    if topic is None:
        raise ValueError(f"topic {topic_id!r} not found")
    updated = topic.model_copy(update=patch)
    topic_store[topic_id] = updated
    save_topics()
    return updated


def list_reviews(status: str | None = None) -> list[ReviewQueueItem]:
    reviews = list(review_store.values())
    if status is not None:
        reviews = [review for review in reviews if review.status.value == status]
    return sorted(reviews, key=lambda review: review.created_at, reverse=True)


def get_review(review_id: str) -> ReviewQueueItem | None:
    return review_store.get(review_id)


def create_review(review: ReviewQueueItem) -> ReviewQueueItem:
    review_store[review.review_id] = review
    save_reviews()
    return review


def update_review(review_id: str, patch: dict) -> ReviewQueueItem:
    review = review_store.get(review_id)
    if review is None:
        raise ValueError(f"review {review_id!r} not found")
    updated = review.model_copy(update=patch)
    review_store[review_id] = updated
    save_reviews()
    return updated


def list_workflow_run_steps(
    task_id: str | None = None,
    run_id: str | None = None,
) -> list[WorkflowRunStepRecord]:
    steps = list(workflow_run_step_store.values())
    if task_id is not None:
        steps = [step for step in steps if step.task_id == task_id]
    if run_id is not None:
        steps = [step for step in steps if step.run_id == run_id]
    return sorted(steps, key=lambda step: step.created_at, reverse=True)


def delete_workflow_run_steps_for_task(task_id: str) -> int:
    run_step_ids = [
        run_step_id
        for run_step_id, step in workflow_run_step_store.items()
        if step.task_id == task_id
    ]
    for run_step_id in run_step_ids:
        del workflow_run_step_store[run_step_id]
    if run_step_ids:
        save_workflow_run_steps()
    return len(run_step_ids)


def get_workflow_run_step(run_step_id: str) -> WorkflowRunStepRecord | None:
    return workflow_run_step_store.get(run_step_id)


def create_workflow_run_step(step: WorkflowRunStepRecord) -> WorkflowRunStepRecord:
    workflow_run_step_store[step.run_step_id] = step
    save_workflow_run_steps()
    return step


def update_workflow_run_step(run_step_id: str, patch: dict) -> WorkflowRunStepRecord:
    step = workflow_run_step_store.get(run_step_id)
    if step is None:
        raise ValueError(f"workflow run step {run_step_id!r} not found")
    updated = step.model_copy(update=patch)
    workflow_run_step_store[run_step_id] = updated
    save_workflow_run_steps()
    return updated


load_tasks()
load_topics()
load_reviews()
load_workflow_run_steps()
load_accounts()
load_users()
load_schedules()
