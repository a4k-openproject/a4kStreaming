# -*- coding: utf-8 -*-
# Offline tests for the dobby skin parity (#018): the home top menu, the Search window, the year chips over the category
# grids, and the appearance settings (home rows, their order, the top shelf's source and rotation).

import os
import importlib
from xml.etree import ElementTree
from .common import pytest, api

WINDOWS = os.path.join(os.path.dirname(__file__), '..', 'resources', 'skins', 'Default', '1080i')
PLUGIN = 'plugin://plugin.video.a4kstreaming/'

@pytest.fixture(scope='module')
def core():
    core = api.A4kStreamingApi({'kodi': True}).core
    core.url = PLUGIN
    return core

@pytest.fixture
def home(core, monkeypatch):
    home = importlib.import_module('a4kStreaming.ui.home')
    monkeypatch.setattr(home.Home, 'rotate', lambda self: None)
    return home

@pytest.fixture
def grid(core):
    return importlib.import_module('a4kStreaming.ui.grid')

@pytest.fixture(autouse=True)
def clean(core, monkeypatch):
    properties = importlib.import_module('a4kStreaming.lib.kodi_mock')._window_properties
    properties.clear()
    monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: '')
    yield
    properties.clear()

def settings(core, monkeypatch, values):
    monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: values.get(key, ''))

@pytest.fixture
def calls(core, monkeypatch):
    log = []
    monkeypatch.setattr(core.kodi.xbmc, 'executebuiltin', lambda builtin, wait=False: log.append(builtin))
    return log

def xml(name):
    return ElementTree.parse(os.path.join(WINDOWS, name)).getroot()

def control(root, id):
    return [c for c in root.iter('control') if c.get('id') == str(id)][0]

def opened(home, monkeypatch):
    properties = {}
    monkeypatch.setattr(home.Home, 'doModal', lambda self: properties.update(self.properties))
    home.open()
    return properties

# 1. home top menu

def test_menu_is_in_the_xml_and_navigates_like_dobby(home):
    root = xml('a4k-home.xml')
    menu = control(root, 160)
    assert menu.get('type') == 'grouplist' and menu.findtext('ondown') == str(home.HERO_PLAY)
    assert control(root, 210).findtext('onup') == str(home.WATCH_NOW)
    ids = {int(c.get('id')) for c in menu.iter('control') if c.get('id') and c.get('type') == 'button'}
    assert ids == set(home.MENU)
    # hidden by a conditional animation, never by <visible>: a hidden control cannot take focus
    bar = control(root, 150)
    assert bar.find('visible') is None
    assert {a.get('condition') for a in bar.findall('animation')} == {'!ControlGroup(160).HasFocus()'}
    # the category tabs follow the setting, the others always show
    for id in home.TABS:
        assert control(root, id).findtext('visible') == '!String.IsEmpty(Window.Property(a4k.tabs))'
    for id in (home.WATCH_NOW, home.SEARCH, home.SETTINGS):
        assert control(root, id).find('visible') is None

@pytest.mark.parametrize('value,shown', [('', 'true'), ('true', 'true'), ('false', None)])
def test_category_tabs_follow_the_setting(core, home, monkeypatch, value, shown):
    settings(core, monkeypatch, {'appearance.tabs': value})
    assert opened(home, monkeypatch).get('a4k.tabs') == shown

def test_category_tabs_open_dobbys_category_grids(core, home, grid, monkeypatch):
    shown = []
    monkeypatch.setattr(grid, 'show', lambda path, title, kicker='': shown.append((path, title)))
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    for id in sorted(home.TABS):
        window.onClick(id)
    assert [path.split('type=')[1].split('&')[0] for path, _ in shown] == [
        'popularMovies', 'popularTVShows', 'popularAnimations', 'popularAnimationTVShows', 'popularRealityTVShows']
    assert [title for _, title in shown] == ['Trending Movies', 'Trending TV Shows', 'Animations', 'Animated TV', 'Reality TV']
    assert window.error is None

def test_watch_now_focuses_play_and_settings_opens_the_addon_settings(core, home, monkeypatch, calls):
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    window.setFocusId(home.WATCH_NOW)
    window.onClick(home.WATCH_NOW)
    assert window.getFocusId() == home.HERO_PLAY
    window.onClick(home.SETTINGS)
    assert calls == ['Addon.OpenSettings(plugin.video.a4kstreaming)'] and window.error is None
