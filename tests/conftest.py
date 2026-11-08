# -*- coding: utf-8 -*-

import importlib
import pytest

@pytest.fixture(autouse=True)
def progress_store(request, tmp_path, monkeypatch):
    # every test gets an empty Continue Watching store of its own (a4kStreaming/progress.py); test_api imports the
    # add-on without the Kodi mock on purpose
    if request.module.__name__.endswith('test_api'):
        return None
    from tests import common  # noqa: F401  (the add-on's import paths and the Kodi mock)
    progress = importlib.import_module('a4kStreaming.progress')
    monkeypatch.setattr(progress, 'PATH', str(tmp_path / 'progress.json'))
    monkeypatch.setattr(importlib.import_module('a4kStreaming.kodi_mode'), 'PATH', str(tmp_path / 'kodi_mode.json'))  # off
    return progress
