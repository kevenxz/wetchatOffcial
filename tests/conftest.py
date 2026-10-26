from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def isolate_logging(tmp_path, monkeypatch):
    """Keep test output out of the repository's production log files.

    ``api/logging_config.setup_logging()`` runs at *import* time of ``api.main``, so any
    test that imports the app — every ``TestClient(app)`` test — installs the real
    rotating file handler. Before this fixture, a single test module added lines to
    ``logs/app.log``, and 47% of that file turned out to be test output (34 fixture
    task_ids such as ``task-1`` and ``test_task_123``), which made the production log
    useless for diagnosis.

    File logging is redirected into the per-test ``tmp_path``. Console output and pytest's
    own capture are untouched, so a developer still sees everything in the terminal.
    """
    from api import logging_config

    log_dir = tmp_path / "logs"
    monkeypatch.setenv("LOG_DIR", str(log_dir))
    permissive = logging.getLogger()
    original_level = permissive.level
    logging_config.setup_logging(log_dir_override=log_dir)

    yield

    # Drop the temporary handlers so nothing keeps writing into tmp_path afterwards.
    logging_config._detach_owned_handlers()
    permissive.setLevel(original_level)


@pytest.fixture(autouse=True)
def isolate_local_storage(tmp_path, monkeypatch):
    """Redirect every local JSON store into a per-test directory.

    ``api.store`` resolves ``data/`` relative to the working directory, so without
    this fixture a test that clears a store and calls ``save_*()`` overwrites the
    developer's real ``data/*.json``, and a test exercising ``bootstrap_storage()``
    would rename those files to ``*.imported``. Local runtime state is not test
    data, so it is isolated here once for the whole suite.
    """
    from api import persistence, store

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Snapshot the real configuration and contents so they can be restored exactly.
    original_registry = {kind: tuple(entry) for kind, entry in store._KIND_REGISTRY.items()}
    path_attr_names = (
        "TASKS_FILE",
        "TOPICS_FILE",
        "REVIEWS_FILE",
        "WORKFLOW_RUN_STEPS_FILE",
        "ACCOUNTS_FILE",
        "USERS_FILE",
        "SCHEDULES_FILE",
        "ARTICLE_STATS_FILE",
        "STYLE_CONFIG_FILE",
        "CUSTOM_THEMES_FILE",
        "MODEL_CONFIG_FILE",
    )
    original_paths = {
        name: getattr(store, name) for name in path_attr_names if hasattr(store, name)
    }
    original_contents = {kind: dict(entry[0]) for kind, entry in original_registry.items()}

    # Point every path constant and the registry at the tmp directory.
    monkeypatch.setattr(store, "DATA_DIR", data_dir, raising=False)
    for name, value in original_paths.items():
        monkeypatch.setattr(store, name, data_dir / Path(value).name, raising=False)

    store._KIND_REGISTRY.clear()
    for kind, (container, path, model) in original_registry.items():
        store._KIND_REGISTRY[kind] = (container, data_dir / path.name, model)

    for container, _path, _model in original_registry.values():
        container.clear()
    persistence.reset_state()

    yield

    store._KIND_REGISTRY.clear()
    store._KIND_REGISTRY.update(original_registry)
    for kind, (container, _path, _model) in original_registry.items():
        container.clear()
        container.update(original_contents.get(kind, {}))
    for name, value in original_paths.items():
        setattr(store, name, value)
    persistence.reset_state()
