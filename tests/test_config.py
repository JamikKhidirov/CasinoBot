import os
import importlib

import config


def test_env_ids_comma_and_semicolon(monkeypatch):
    monkeypatch.setenv("ADMINS", "111, 222;333")
    importlib.reload(config)
    assert config.ADMINS == [1, 111, 222, 333]


def test_env_ids_empty(monkeypatch):
    monkeypatch.delenv("ADMINS", raising=False)
    importlib.reload(config)
    assert config.ADMINS == [1]


def test_env_int_fallback(monkeypatch):
    monkeypatch.setenv("OWNER_ID", "not-a-number")
    importlib.reload(config)
    assert config.OWNER_ID == config._DEFAULT_OWNER_ID


def test_proxy_url_none_by_default(monkeypatch):
    monkeypatch.delenv("PROXY_URL", raising=False)
    importlib.reload(config)
    assert config.PROXY_URL is None


def test_owner_id_in_admins(monkeypatch):
    monkeypatch.setenv("OWNER_ID", "555")
    monkeypatch.setenv("ADMINS", "111,222")
    importlib.reload(config)
    assert 555 in config.ADMINS
