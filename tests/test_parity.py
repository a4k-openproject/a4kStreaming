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

# 2. search window

@pytest.fixture
def search(core):
    return importlib.import_module('a4kStreaming.ui.search')

@pytest.fixture
def imdb(core):
    return importlib.import_module('a4kStreaming.imdb')

class Timer(object):
    # threading.Timer stand-in: records the delay and runs only when the test says so
    made = []
    def __init__(self, delay, fn, args=()):
        self.delay, self.fn, self.args, self.cancelled = delay, fn, args, False
        Timer.made.append(self)
    def start(self): pass
    def cancel(self): self.cancelled = True
    def fire(self): self.fn(*self.args)

@pytest.fixture
def timers(search, monkeypatch):
    Timer.made = []
    monkeypatch.setattr(search.threading, 'Timer', Timer)
    return Timer.made

def window(search):
    win = search.Search('a4k-search.xml', '', 'Default', '1080i')
    win.onInit()
    return win

def test_search_window_is_skeleton_first(core, search, monkeypatch):
    # onInit fills the keyboard and the chips and focuses the keys; no listing until something is typed
    win = window(search)
    keys = win.getControl(search.KEYS).items
    assert [k.getProperty('key') for k in keys] == list('qwertyuiopasdfghjkl') + ['del'] + list('zxcvbnm') + ['space', 'type']
    assert [k.getLabel() for k in keys if k.getProperty('key') in search.ICONS] == ['', '', ''] and keys[-1].art == {'icon': 'a4k/icon_keyboard.png'}
    chips = win.getControl(search.FACETS).items
    assert [c.getLabel() for c in chips] == ['Type: All', 'Genre: Any', 'Era: Any', 'Rating: Any', 'Country: Any']
    assert win.getFocusId() == search.KEYS and win.getProperty('a4k.path') == '' and win.getProperty('a4k.hint') == search.HINT
    win.onInit()  # a return from detail adds nothing
    assert len(win.getControl(search.KEYS).items) == 29 and win.error is None

def test_typing_runs_the_search_once_typing_pauses(core, search, timers):
    win = window(search)
    for key in 'dun':
        win.press(key)
    win.press('del')
    win.press('space')
    assert win.getProperty('a4k.query') == 'du ' and win.getProperty('a4k.hint') == ''
    assert [t.delay for t in timers] == [0.5] * 5 and [t.cancelled for t in timers] == [True] * 4 + [False]
    assert win.getProperty('a4k.path') == ''  # nothing until the pause
    timers[-1].fire()
    assert win.getProperty('a4k.path') == PLUGIN + '?action=query&type=find&query=du&widget=1'

def test_an_emptied_query_keeps_the_results(core, search, timers):
    win = window(search)
    win.press('a')
    timers[-1].fire()
    win.press('del')
    timers[-1].fire()
    assert win.getProperty('a4k.path').endswith('query=a&widget=1') and win.getProperty('a4k.hint') == search.HINT

def test_type_key_opens_kodis_keyboard_and_searches_at_once(core, search, timers, monkeypatch):
    keyboard = core.kodi.xbmc.Keyboard('', '')
    monkeypatch.setattr(keyboard, 'getText', lambda: 'Le Mans')
    monkeypatch.setattr(keyboard, 'isConfirmed', lambda: True)
    win = window(search)
    win.press('type')
    assert win.getProperty('a4k.path') == PLUGIN + '?action=query&type=find&query=Le+Mans&widget=1'
    assert timers[-1].cancelled

@pytest.mark.parametrize('query,filters,count,expected', [
    ('', {}, 0, ''),
    ('  ', {}, 0, ''),
    ('heat ', {}, 0, '?action=query&type=find&query=heat&widget=1'),
    ('', {'type': 'series'}, 36, '?action=query&type=facets&title_type=series&count=36&widget=1'),
    ('amor', {'genre': ['Drama', 'Romance'], 'era': '2000s', 'rating': 'teens', 'country': 'FR'}, 72,
     '?action=query&type=facets&query=amor&genres=Drama%2CRomance&era=2000s&rating=teens&country=FR&count=72&widget=1'),
])
def test_search_url(search, query, filters, count, expected):
    full = dict(search.no_filters(), **filters)
    assert search.url(query, full, count) == (PLUGIN + expected if expected else '')

@pytest.mark.parametrize('params,expected', [
    ({}, {'titleTypeConstraint': {'anyTitleTypeIds': ['movie', 'tvMovie', 'tvSeries', 'tvMiniSeries']}}),
    ({'query': 'heat', 'title_type': 'movies', 'genres': 'Action,Crime', 'era': 'lt1990', 'country': 'US'}, {
        'titleTypeConstraint': {'anyTitleTypeIds': ['movie', 'tvMovie']},
        'titleTextConstraint': {'searchTerm': 'heat'},
        'genreConstraint': {'anyGenreIds': ['Action', 'Crime']},
        'releaseDateConstraint': {'releaseDateRange': {'end': '1989-12-31'}},
        'originCountryConstraint': {'anyPrimaryCountries': ['US']}}),
    ({'title_type': 'series', 'era': 'ge2010', 'rating': 'kids'}, {
        'titleTypeConstraint': {'anyTitleTypeIds': ['tvSeries', 'tvMiniSeries']},
        'releaseDateConstraint': {'releaseDateRange': {'start': '2010-01-01'}},
        'certificateConstraint': {'anyRegionCertificateRatings': [
            {'region': 'US', 'rating': r} for r in ('G', 'TV-Y', 'TV-Y7', 'TV-G')]}}),
    ({'era': '1990s', 'rating': 'nonsense'}, {
        'titleTypeConstraint': {'anyTitleTypeIds': ['movie', 'tvMovie', 'tvSeries', 'tvMiniSeries']},
        'releaseDateConstraint': {'releaseDateRange': {'start': '1990-01-01', 'end': '1999-12-31'}}}),
])
def test_facet_constraints(core, imdb, params, expected):
    assert imdb.search_constraints(core.utils.DictAsObject(params)) == expected

def test_facet_lists_are_neutral(imdb):
    labels = [label for _, label in imdb.SEARCH_COUNTRIES]
    assert labels == sorted(labels) and len(set(labels)) == len(labels)
    assert set(imdb.SEARCH_CERTIFICATES['kids']) < set(imdb.SEARCH_CERTIFICATES['family']) < set(imdb.SEARCH_CERTIFICATES['teens'])

def test_facet_query_pages_grow_and_stop_at_imdbs_largest(core, imdb, monkeypatch):
    import json
    sent = []
    def execute(core, request, *args, **kwargs):
        sent.append(request)
        return type('R', (), {'status_code': 500, 'content': b'', 'text': '', 'fetched_at': 0})()
    monkeypatch.setattr(core.request, 'execute', execute)
    monkeypatch.setattr(core.kodi, 'get_int_setting', lambda *a: 20)
    try:
        imdb.query(core, core.utils.DictAsObject({'type': 'facets', 'genres': 'Action', 'count': '9999'}))
    except Exception:
        pass  # the failed response's error handling is not under test
    body = sent[-1]['data']
    variables = (json.loads(body) if isinstance(body, str) else body)['variables']
    assert variables['first'] == imdb.SEARCH_MAX and variables['constraints']['genreConstraint'] == {'anyGenreIds': ['Action']}

def test_facet_chips_pick_clear_and_multi_select(core, search, timers, monkeypatch):
    sheets = importlib.import_module('a4kStreaming.ui.sheets')
    picks, seen = [], []
    def select(heading, labels, preselect=-1, rows=None):
        seen.append((heading, preselect, rows and [r[1] for r in rows[:3]]))
        return picks.pop(0)
    monkeypatch.setattr(sheets, 'select', select)
    win = window(search)
    picks[:] = [2]  # Type: Series
    win.pick('type')
    assert win.filters['type'] == 'series' and win.getProperty('a4k.path').endswith('type=facets&title_type=series&count=36&widget=1')
    chips = win.getControl(search.FACETS).items
    assert [c.getLabel() for c in chips][0] == 'Type: Series' and chips[0].getProperty('on') == 'true'
    assert chips[-1].getLabel() == 'Clear'
    picks[:] = [1, 2, 1, -1]  # Genre: Action on, Adventure on, Action off, Back
    win.pick('genre')
    assert win.filters['genre'] == ['Adventure']
    assert seen[-1] == ('Genre', 1, ['', '', 'Selected'])  # the sheet comes back on the toggled row
    assert win.getControl(search.FACETS).items[1].getLabel() == 'Genre: Adventure'
    picks[:] = [-1]  # Back on a single facet changes nothing
    win.pick('era')
    assert win.filters['era'] == ''
    win.pick('clear')
    assert win.filters == search.no_filters() and len(win.getControl(search.FACETS).items) == 5
    assert win.error is None

def test_results_select_opens_detail_and_back_closes(core, search, home, monkeypatch):
    opened, closed = [], []
    monkeypatch.setattr(home, 'select', lambda info: opened.append(info['Property(a4k.id)']))
    monkeypatch.setattr(core.kodi.xbmc, 'getInfoLabel', lambda label: {
        'Container(620).ListItem.Property(a4k.type)': 'movie', 'Container(620).ListItem.Property(a4k.id)': 'tt9'}.get(label, ''))
    win = window(search)
    win.setFocusId(search.RESULTS)
    win.onAction(type('A', (), {'getId': lambda self: home.ACTION_SELECT_ITEM})())
    assert opened == ['tt9']
    monkeypatch.setattr(search.Search, 'close', lambda self: closed.append(True))
    win.onAction(type('A', (), {'getId': lambda self: home.ACTION_NAV_BACK})())
    assert closed == [True] and win.error is None

def test_results_ask_for_more_near_the_end_of_a_full_facet_page(core, search, timers, monkeypatch):
    values = {}
    monkeypatch.setattr(core.kodi.xbmc, 'getInfoLabel', lambda label: values.get(label, ''))
    win = window(search)
    win.filters['genre'] = ['Action']
    win.apply()
    values.update({'Container(620).NumItems': '36', 'Container(620).CurrentItem': '20'})
    win.moved()
    assert 'count=36&' in win.getProperty('a4k.path')  # 16 left: not yet
    values['Container(620).CurrentItem'] = '25'
    win.moved()
    assert 'count=72&' in win.getProperty('a4k.path')
    values.update({'Container(620).NumItems': '50', 'Container(620).CurrentItem': '45'})
    win.moved()
    assert 'count=72&' in win.getProperty('a4k.path')  # a short page: IMDb has no more

def test_search_entry_points_route_to_the_window(core, home, monkeypatch):
    opened = []
    monkeypatch.setattr(importlib.import_module('a4kStreaming.ui.search'), 'open', lambda: opened.append(True) or True)
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    window.onClick(home.SEARCH)
    assert opened == [True]
