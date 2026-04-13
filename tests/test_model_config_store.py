"""Tests for model config storage helpers."""
from __future__ import annotations

import json

from api.models import ImageModelConfig, ModelConfig, TextModelConfig
from api import store


def test_get_model_config_falls_back_to_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "MODEL_CONFIG_FILE", tmp_path / "model_config.json")
    monkeypatch.setattr(store, "_model_config", None)
    monkeypatch.setenv("OPENAI_API_KEY", "text-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://text.example.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "text-model")
    monkeypatch.setenv("DALLE_ENABLED", "true")
    monkeypatch.setenv("IMAGE_API_KEY", "image-key")
    monkeypatch.setenv("IMAGE_API_BASE", "https://image.example.com/v1")
    monkeypatch.setenv("IMAGE_MODEL", "flux-dev")

    config = store.get_model_config()

    assert config.text.api_key == "text-key"
    assert config.text.base_url == "https://text.example.com/v1"
    assert config.text.model == "text-model"
    assert config.image.enabled is True
    assert config.image.api_key == "image-key"
    assert config.image.base_url == "https://image.example.com/v1"
    assert config.image.model == "flux-dev"


def test_save_model_config_persists_and_reloads(monkeypatch, tmp_path) -> None:
    model_config_file = tmp_path / "model_config.json"
    monkeypatch.setattr(store, "MODEL_CONFIG_FILE", model_config_file)
    monkeypatch.setattr(store, "_model_config", None)

    payload = ModelConfig(
        text=TextModelConfig(api_key="text-key", base_url="https://text.example.com/v1", model="text-model"),
        image=ImageModelConfig(enabled=True, api_key="image-key", base_url="https://image.example.com/v1", model="flux-dev"),
    )

    saved = store.save_model_config(payload)

    assert saved.text.model == "text-model"
    assert model_config_file.exists()
    assert json.loads(model_config_file.read_text(encoding="utf-8"))["image"]["model"] == "flux-dev"

    monkeypatch.setattr(store, "_model_config", None)
    reloaded = store.get_model_config()

    assert reloaded.text.api_key == "text-key"
    assert reloaded.image.enabled is True
    assert reloaded.image.api_key == "image-key"
