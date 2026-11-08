# -*- coding: utf-8 -*-
# Offline tests for the reference skin parity (#018): the home top menu, the Search window, the year chips over the category
# grids, and the appearance settings (home rows, their order, the top shelf's source and rotation).

import os
import re
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

def test_menu_is_in_the_xml_and_navigates_like_the_reference(home):
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

@pytest.mark.parametrize('value,shown', [('', 'true'), ('true', 'true'), ('false', '')])
def test_category_tabs_follow_the_setting(core, home, monkeypatch, value, shown):
    settings(core, monkeypatch, {'appearance.tabs': value})
    assert opened(home, monkeypatch).get('a4k.tabs') == shown

def test_category_tabs_open_the_category_grids(core, home, grid, monkeypatch):
    shown = []
    monkeypatch.setattr(grid, 'show', lambda path, title, kicker='': shown.append((path, title)))
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    for id in sorted(home.TABS):
        window.onClick(id)
    assert [path.split('type=')[1].split('&')[0] for path, _ in shown] == [
        'popularMovies', 'popularTVShows', 'popularAnimations', 'popularAnimationTVShows', 'popularRealityTVShows']
    assert [title for _, title in shown] == ['Trending Movies', 'Trending TV Shows', 'Animations', 'Animated TV', 'Reality TV']
    assert window.error is None

def test_watch_now_focuses_play_and_settings_opens_the_settings_window(core, home, monkeypatch, calls):
    from types import SimpleNamespace
    opened = []
    monkeypatch.setattr(home, 'run', lambda builtin: opened.append(builtin))
    monkeypatch.setattr(home.threading, 'Thread', lambda target: SimpleNamespace(start=lambda: None))
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    window.setFocusId(home.WATCH_NOW)
    window.onClick(home.WATCH_NOW)
    assert window.getFocusId() == home.HERO_PLAY
    window.onClick(home.SETTINGS)
    assert opened == ['RunScript(plugin.video.a4kstreaming,settings)'] and calls == [] and window.error is None

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

# 3. year chips over the category grids

def category_window(grid, path):
    win = grid.Grid('a4k-grid.xml', '', 'Default', '1080i')
    win.steps = []
    win.go(path, 'Animations')
    win.onInit()
    return win

def test_category_grids_take_year_chips_and_others_do_not(core, grid):
    from datetime import datetime
    win = category_window(grid, PLUGIN + '?action=query&type=popularAnimations')
    chips = win.getControl(grid.YEARS).items
    labels = [c.getLabel() for c in chips]
    assert labels[:2] == ['All Years', str(datetime.now().year)] and labels[-1] == '1970'
    assert len(labels) == datetime.now().year - 1970 + 2 and chips[0].getProperty('on') == 'true'
    assert win.getProperty('a4k.years') == 'true' and win.error is None
    other = category_window(grid, PLUGIN + '?action=query&type=fan_picks')
    assert other.getProperty('a4k.years') == '' and other.getControl(grid.YEARS).items == []

def test_a_year_chip_reruns_the_same_category_within_the_year(core, grid):
    win = category_window(grid, PLUGIN + '?action=query&type=popularAnimations&widget=1')
    win.steps.append(('x', 'y', 'z', 3))  # a page under the one shown
    win.path = PLUGIN + '?action=query&type=popularAnimations&paginationToken=abc&page=2&cursor_time=1&widget=1'
    win.pick_year('2019')
    assert win.getProperty('a4k.path') == PLUGIN + '?action=query&type=popularAnimations&widget=1&target_year=2019'
    assert win.steps == [] and win.getProperty('a4k.kicker') == '2019' and win.getProperty('a4k.title') == 'Animations'
    chips = win.getControl(grid.YEARS).items
    assert [c.getLabel() for c in chips if c.getProperty('on')] == ['2019']
    win.onInit()  # a return from detail keeps the chosen year
    assert [c.getLabel() for c in win.getControl(grid.YEARS).items if c.getProperty('on')] == ['2019']
    win.pick_year('')
    assert win.getProperty('a4k.path') == PLUGIN + '?action=query&type=popularAnimations&widget=1'
    assert win.getProperty('a4k.kicker') == '' and win.error is None

def test_year_chip_clicks_reach_python(core, grid):
    win = category_window(grid, PLUGIN + '?action=query&type=popularMovies&widget=1')
    chips = win.getControl(grid.YEARS)
    chips.getSelectedItem = lambda: chips.items[3]  # the mock list has no selection of its own
    win.onClick(grid.YEARS)
    assert win.getProperty('a4k.path').endswith('&target_year=%s' % grid.year_chips()[3]) and win.error is None

@pytest.mark.parametrize('year,expected', [
    ('', (None, '2026-11-07')),
    ('2019', ('2019-01-01', '2019-12-31')),
    ('2026', ('2026-01-01', '2026-11-07')),  # never past today, as the unfiltered gallery
])
def test_category_dates(imdb, year, expected):
    from datetime import datetime
    assert imdb.category_dates(datetime(2026, 11, 7), year) == expected

def test_category_query_sends_the_years_dates(core, imdb, monkeypatch):
    import json
    sent = []
    monkeypatch.setattr(core.request, 'execute', lambda core, request, *a, **k: sent.append(request) or type('R', (), {'status_code': 500, 'content': b'', 'text': '', 'fetched_at': 0})())
    monkeypatch.setattr(core.kodi, 'get_int_setting', lambda *a: 20)
    for year in ('2019', None):
        try:
            imdb.query(core, core.utils.DictAsObject({'type': 'popularAnimations', 'target_year': year}))
        except Exception:
            pass
    bodies = [json.loads(r['data']) if isinstance(r['data'], str) else r['data'] for r in sent]
    assert bodies[0]['variables']['startDate'] == '2019-01-01' and bodies[0]['variables']['endDate'] == '2019-12-31'
    assert bodies[1]['variables']['startDate'] is None
    assert 'releaseDateRange: { start: $startDate, end: $endDate }' in bodies[0]['query']

# operator bugs: the focused poster's flicker, captions under the zoom

@pytest.mark.parametrize('name', ['a4k-home.xml', 'a4k-grid.xml', 'a4k-detail.xml', 'a4k-search.xml'])
def test_focused_art_shows_at_once_and_only_the_art_zooms(name):
    for layout in xml(name).iter('focusedlayout'):
        # the focused layout's art is the texture the unfocused layout already holds: a fade would start it from black
        assert layout.find('.//fadetime') is None
        zooms = [g for g in layout.iter('control') if g.get('type') == 'group' and g.find("animation[@effect='zoom']") is not None]
        art = [g for g in zooms if any('ListItem.Art(' in (t.text or '') for t in g.iter('texture'))]
        for group in art:  # captions keep their baseline: no label zooms with the art
            assert not [c for c in group.iter('control') if c.get('type') == 'label'], name

def test_grid_zoomed_poster_stays_inside_its_slot():
    # 1.08 about the poster's centre, plus the 9 px ring: clear of the row above and of the captions below
    panel = control(xml('a4k-grid.xml'), 500)
    focused = panel.find('focusedlayout')
    height = int(focused.get('height'))
    poster = [c for c in focused.iter('control') if (c.findtext('texture') or '') == '$INFO[ListItem.Art(poster)]'][0]
    top, size = int(poster.findtext('top')), int(poster.findtext('height'))
    centre = top + size / 2.0
    zoomed_top, zoomed_bottom = centre - size / 2.0 * 1.08 - 9, centre + size / 2.0 * 1.08 + 9
    captions = [c for c in focused.iter('control') if c.get('type') == 'label' and int(c.findtext('top')) > centre]
    title = min(int(c.findtext('top')) for c in captions)
    captions_end = max(int(c.findtext('top')) + int(c.findtext('height')) for c in captions)
    assert zoomed_top >= 0 and zoomed_bottom <= title and captions_end <= height

# the traced-D loader in place of Kodi's busy dialog

MEDIA = os.path.join(WINDOWS, '..', 'media')

def test_loader_is_one_animated_png_stepped_once_a_frame():
    import struct
    # Kodi decodes an .apng once into a texture array and steps it per drawn frame; a multiimage of PNGs held each
    # frame 3 or 4 vsyncs at random (measured on a TV box) and reloaded them from disk
    assert os.listdir(os.path.join(MEDIA, 'loader')) == ['comet.apng']
    data = open(os.path.join(MEDIA, 'loader', 'comet.apng'), 'rb').read()
    chunks, i = [], 8
    while i < len(data):
        size, kind = struct.unpack('>I4s', data[i:i + 8])
        chunks.append((kind, data[i + 8:i + 8 + size]))
        i += 12 + size
    assert struct.unpack('>II', chunks[0][1][:8]) == (180, 180)
    frames, plays = struct.unpack('>II', dict(chunks)[b'acTL'])
    assert (frames, plays) == (96, 0)  # one turn in 96 frames, looped forever
    delays = set(struct.unpack('>HH', c[20:24]) for k, c in chunks if k == b'fcTL')
    assert delays == {(12, 1000)}  # under a 60 Hz frame: one step per vsync, 1.6 s a turn
    assert len(data) < 150000
    base = open(os.path.join(MEDIA, 'a4k', 'loader_base.png'), 'rb').read()
    assert struct.unpack('>II', base[16:24]) == (180, 180) and len(base) < 8000

@pytest.mark.parametrize('name', ['a4k-home.xml', 'a4k-grid.xml', 'a4k-search.xml', 'a4k-detail.xml'])
def test_windows_draw_the_loader_while_the_add_on_is_busy(name):
    root = xml(name)
    assert not [c for c in root.iter('control') if c.get('type') == 'multiimage']
    assert [c for c in root.iter('control') if c.findtext('texture') == 'loader/comet.apng']
    # hidden under any modal dialog: Kodi's busy dialog is one, so the two are never drawn together
    busy = [c for c in root.iter('control')
            if c.findtext('visible') == '!String.IsEmpty(Window(Home).Property(a4k.busy)) + !System.HasActiveModalDialog']
    assert len(busy) == 2  # the dim layer and the loader
    assert 'Property(a4k.busy))</visible>' not in open(os.path.join(WINDOWS, name)).read()
    assert 'Loading…' not in open(os.path.join(WINDOWS, name)).read()

def test_home_waits_behind_the_loader_until_the_top_shelf_has_a_title(core, home, monkeypatch):
    assert opened(home, monkeypatch)['a4k.loading'] == 'true'
    page = control(xml('a4k-home.xml'), 100)
    assert [a.get('condition') for a in page.findall('animation')] == [
        '!String.IsEmpty(Window.Property(a4k.loading))', 'String.IsEmpty(Window.Property(a4k.loading))']
    # the hiding fade has no length: played in reverse it never ends, and the page stayed transparent (seen live)
    assert page.findall('animation')[0].get('reversible') == 'false'

@pytest.mark.parametrize('items', ['5', '0'])  # a title, or 15 s without one: never a loader for good
def test_the_first_top_shelf_title_ends_the_loading(core, monkeypatch, items):
    import threading
    module = importlib.import_module('a4kStreaming.ui.home')  # the real rotate (the home fixture stubs it)
    win = module.Home('a4k-home.xml', '', 'Default', '1080i')
    win.setProperty('a4k.loading', 'true')
    win.stopped = threading.Event()
    waits = []
    monkeypatch.setattr(win.stopped, 'wait', lambda t: waits.append(t) or t == module.HERO_TURN)  # closes at the first turn
    monkeypatch.setattr(core.kodi.xbmc, 'getInfoLabel', lambda label: items if label.endswith('NumItems') else 'Heat')
    win.rotate()
    assert win.getProperty('a4k.loading') == '' and win.getProperty('a4k.hero.label') == 'Heat'
    assert waits == ([] if items == '5' else [0.1] * 150) + [module.HERO_TURN]  # 100 ms looks, 15 s at most

@pytest.fixture
def on_screen(core, monkeypatch):
    # an a4k window (42) open; returns a setter for the window on screen
    core.kodi.xbmcgui.Window(10000).setProperty('a4k.ui.window', '42')
    current = [42]
    monkeypatch.setattr(core.kodi.xbmcgui, 'getCurrentWindowId', lambda: current[0])
    return lambda id: current.__setitem__(0, id)

def busy(core):
    # 'true' while the loader is up (the property holds a time stamp then)
    return 'true' if core.kodi.xbmcgui.Window(10000).getProperty('a4k.busy') else ''

def test_busy_draws_the_windows_loader_over_an_a4k_window(core, calls, on_screen):
    core.kodi.open_busy_dialog()
    assert calls == [] and busy(core) == 'true'
    core.kodi.close_busy_dialog()
    assert calls == [] and busy(core) == ''

def test_busy_falls_back_to_kodis_dialog_when_the_open_window_is_stale(core, calls, on_screen):
    on_screen(13)  # OPEN_WINDOW still names 42, but Kodi's Videos window (or playback) is on screen
    with core.kodi.busy_dialog():
        assert calls == ['ActivateWindow(busydialognocancel)'] and busy(core) == ''
    assert calls[-1] == 'Dialog.Close(busydialognocancel)'
    del calls[:]
    with core.kodi.busy_dialog(native=False):  # the play action: Kodi's own busy dialog is already up there
        with core.kodi.busy_dialog():
            pass
    assert calls == [] and busy(core) == ''

def test_nested_busy_keeps_the_outer_loader_until_the_outer_closes(core, calls, on_screen):
    with core.kodi.busy_dialog(native=False):
        with core.kodi.busy_dialog():
            assert busy(core) == 'true'
        assert busy(core) == 'true'  # the inner close (quick sources, the split) leaves the play's loader up
        with core.kodi.busy_dialog():
            on_screen(13)  # opened while nested: the outer's indicator holds, no second one
        assert calls == [] and busy(core) == 'true'
    assert busy(core) == ''
    core.kodi.close_busy_dialog()  # an error path closing what it never opened: nothing to undo
    on_screen(42)
    with core.kodi.busy_dialog():
        assert busy(core) == 'true'
    assert calls == [] and busy(core) == ''

@pytest.mark.parametrize('screen, loader', [(42, 'true'), (13, '')])
@pytest.mark.parametrize('link', ['https://host/v.mkv', None])
def test_the_play_action_runs_behind_the_loader_over_an_a4k_window(core, calls, on_screen, monkeypatch, screen,
                                                                   loader, link):
    # from the start of the call Kodi waits on until the stream plays; elsewhere Kodi's own busy dialog alone
    on_screen(screen)
    seen = []
    monkeypatch.setattr(core, 'play', lambda core, params: seen.append(busy(core)) or link)
    monkeypatch.setattr(core.kodi, 'wait_for_playback', lambda: seen.append('wait %s' % busy(core)))
    core.main(PLUGIN, 1, 'action=play&type=&id=tt1')
    assert seen == [loader] + (['wait %s' % loader] if link else []) and calls == [] and busy(core) == ''

@pytest.mark.parametrize('age, runs', [(None, True), (1, False), (59, False), (61, True)])
def test_windows_start_nothing_new_while_the_loader_is_up(core, calls, home, age, runs):
    # Kodi's busy dialog took the keys during a play; it is kept closed now, so a second Play is dropped here. A stamp
    # older than 60 s was left by a killed plugin call: the action runs and the stale loader goes.
    home_window = core.kodi.xbmcgui.Window(10000)
    if age is not None:
        home_window.setProperty('a4k.busy', str(core.kodi.time.time() - age))
    home.run('PlayMedia(%s?action=play&type=&id=tt1)' % PLUGIN)
    assert calls == (['PlayMedia(%s?action=play&type=&id=tt1)' % PLUGIN] if runs else [])
    assert bool(home_window.getProperty('a4k.busy')) == (not runs)

def test_the_loader_stamp_stays_fresh_while_the_scope_lives(core, on_screen, monkeypatch):
    # a play spans the source sheet, which can take minutes: the watcher renews the stamp, and its last renewal never
    # lands after the close
    monkeypatch.setattr(core.kodi, 'BUSY_BEAT', 0)
    home_window = core.kodi.xbmcgui.Window(10000)
    with core.kodi.busy_dialog():
        home_window.setProperty('a4k.busy', str(core.kodi.time.time() - 61))
        for _ in range(100):
            if core.kodi.busy_live():
                break
            core.kodi.time.sleep(0.01)
        assert core.kodi.busy_live()
    assert home_window.getProperty('a4k.busy') == ''

@pytest.mark.parametrize('states, looks', [
    ([False, True, True, False], 4),  # the player takes the stream, then stops (failed): the loader goes
    ([False] * 60, 51),  # the player never takes it: 5 s
    ([True, True, 'fullscreen'], 3),  # the video window takes over
])
def test_the_loader_holds_until_the_stream_plays(core, on_screen, monkeypatch, states, looks):
    # Kodi's own wait for the first frame shows its busy dialog over the add-on's windows (seen on the TV box)
    states = list(states)
    seen = []
    def media(condition):
        if condition != 'Player.HasMedia':
            return False
        seen.append(1)
        state = states.pop(0)
        if state == 'fullscreen':
            on_screen(12005)
            return True
        return state
    monkeypatch.setattr(core.kodi.xbmc, 'getCondVisibility', media)
    with core.kodi.busy_dialog():
        core.kodi.wait_for_playback()
    assert len(seen) == looks
    on_screen(13)
    with core.kodi.busy_dialog():  # elsewhere: nothing to stand in for
        del seen[:]
        core.kodi.wait_for_playback()
    assert seen == []

def test_busy_over_an_a4k_window_closes_kodis_busy_dialog(core, monkeypatch, on_screen):
    # Kodi opens its busy dialog 220 ms into a PlayMedia it waits on, often after the loader is up: closed as it shows
    import threading
    up = {'busydialog': [False, False, True]}  # a few looks in
    closed = threading.Event()
    log = []
    monkeypatch.setattr(core.kodi.xbmc, 'getCondVisibility',
                        lambda condition: bool(up.get(condition[16:-1]) and up[condition[16:-1]].pop(0)))
    monkeypatch.setattr(core.kodi.xbmc, 'executebuiltin', lambda builtin, wait=False: log.append(builtin) or closed.set())
    with core.kodi.busy_dialog():
        assert closed.wait(2)
    assert log == ['Dialog.Close(busydialog,true)']

# 6. appearance settings (the reference app's options and defaults)

def url(type):
    return PLUGIN + '?action=query&type=%s&widget=1' % type

def slots(properties):
    return [(properties['a4k.title.%s' % slot], properties['a4k.row.%s' % slot]) for slot in range(301, 308)]

def test_appearance_defaults_are_the_references(core, home, monkeypatch):
    settings(core, monkeypatch, {'imdb.at-main': 'token'})
    shown = opened(home, monkeypatch)
    assert slots(shown) == [('Trending Movies', url('popularMovies')), ('Trending TV Shows', url('popularTVShows')),
                            ('Watchlist', url('watchlist'))] + [('', '')] * 4
    assert (shown['a4k.browse'], shown['a4k.tabs'], shown['a4k.auth']) == ('true', 'true', 'true')
    settings(core, monkeypatch, {})  # signed out: no Watchlist
    assert [title for title, _ in slots(opened(home, monkeypatch))][:3] == ['Trending Movies', 'Trending TV Shows', '']

def test_settings_xml_defaults_match_the_code(core):
    appearance = importlib.import_module('a4kStreaming.ui.appearance')
    text = open(os.path.join(WINDOWS, '..', '..', '..', 'settings.xml')).read().replace('&', '&amp;')  # Kodi takes a bare &
    nodes = {n.get('id')[len('appearance.'):]: n for n in ElementTree.fromstring(text).iter('setting')
             if (n.get('id') or '').startswith('appearance.')}
    toggles = {key: n.get('default') for key, n in nodes.items() if n.get('type') == 'bool'}
    assert toggles == {key: 'true' if key in appearance.ON else 'false' for key in
                       ['browse', 'tabs', 'continue_watching'] + [key for key in appearance.ROWS if key != 'my_list']}
    assert appearance.HERO_TURNS[int(nodes['hero_turn'].get('default'))] == 15
    assert len(nodes['hero_turn'].get('lvalues').split('|')) == len(appearance.HERO_TURNS)
    assert appearance.HERO_SOURCES[int(nodes['hero_source'].get('default'))] == 'movies'
    assert len(nodes['hero_source'].get('lvalues').split('|')) == len(appearance.HERO_SOURCES)
    assert nodes['order'].get('visible') == 'false' and nodes['my_list'].get('visible') == 'false'

def test_row_toggles_and_order_fill_the_slots_in_order(core, home, monkeypatch):
    settings(core, monkeypatch, {'imdb.at-main': 'token', 'appearance.trending_tv': 'false', 'appearance.reality': 'true',
                                 'appearance.animations': 'true', 'appearance.browse': 'false', 'appearance.tabs': 'false',
                                 'appearance.order': 'watchlist,reality,gone,trending_movies'})
    shown = opened(home, monkeypatch)
    # the saved order first (an unknown key dropped), then the others in the default order
    assert slots(shown) == [('Watchlist', url('watchlist')), ('Reality TV', url('popularRealityTVShows')),
                            ('Trending Movies', url('popularMovies')), ('Animations', url('popularAnimations'))] + [('', '')] * 3
    assert (shown['a4k.browse'], shown['a4k.tabs']) == ('', '')

def test_my_list_is_a_row_with_its_name_when_signed_in(core, home, monkeypatch):
    values = {'imdb.at-main': 'token', 'appearance.my_list': 'ls0042 Weekend Picks', 'appearance.watchlist': 'false'}
    settings(core, monkeypatch, values)
    assert slots(opened(home, monkeypatch))[2] == ('Weekend Picks', url('list') + '&id=ls0042')
    settings(core, monkeypatch, dict(values, **{'imdb.at-main': ''}))
    assert slots(opened(home, monkeypatch))[2] == ('', '')

def test_next_item_of_a_slot_opens_the_grid_under_that_rows_title(core, home, monkeypatch):
    shown = []
    monkeypatch.setattr(importlib.import_module('a4kStreaming.ui.grid'), 'show', lambda path, title: shown.append(title))
    settings(core, monkeypatch, {'appearance.order': 'reality', 'appearance.reality': 'true'})
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    home.apply(window)
    path = url('popularRealityTVShows') + '&paginationToken=abc'
    monkeypatch.setattr(core.kodi.xbmc, 'getInfoLabel', lambda label: path if label == 'Container(301).ListItem.FolderPath' else '')
    window.setFocusId(301)
    window.onAction(type('Action', (), {'getId': lambda self: home.ACTION_SELECT_ITEM})())
    assert shown == ['Reality TV'] and window.error is None

@pytest.mark.parametrize('values,sources,lists', [
    ({}, [(301, 'TRENDING NOW')], ('', '')),
    ({'appearance.trending_movies': 'false'}, [(291, 'TRENDING NOW')], (url('popularMovies'), '')),
    ({'appearance.hero_source': '1'}, [(302, 'TRENDING NOW')], ('', '')),
    ({'appearance.hero_source': '2', 'appearance.trending_tv': 'false'}, [(301, 'TRENDING NOW'), (292, 'TRENDING NOW')],
     ('', url('popularTVShows'))),
    # My home sections: every row that is on but the Watchlist, each with its own kicker
    ({'appearance.hero_source': '3', 'appearance.reality': 'true', 'appearance.trending_tv': 'false', 'imdb.at-main': 't',
      'appearance.my_list': 'ls7 Weekend Picks'}, [(301, 'TRENDING NOW'), (302, 'REALITY'), (303, 'WEEKEND PICKS')], ('', '')),
    ({'appearance.hero_source': '3', 'appearance.trending_movies': 'false', 'appearance.trending_tv': 'false'},
     [(291, 'TRENDING NOW')], (url('popularMovies'), '')),  # nothing on: the trending movies
])
def test_hero_source_follows_the_setting(core, home, monkeypatch, values, sources, lists):
    settings(core, monkeypatch, values)
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    home.apply(window)
    assert list(window.sources) == sources
    assert (window.getProperty('a4k.row.291'), window.getProperty('a4k.row.292')) == lists

@pytest.mark.parametrize('value,turn', [('', 15), ('0', 10), ('1', 15), ('2', 20), ('3', 30), ('4', 0)])
def test_hero_rotation_follows_the_setting(core, home, monkeypatch, value, turn):
    settings(core, monkeypatch, {'appearance.hero_turn': value})
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    home.apply(window)
    assert window.hero_turn == turn

def test_hero_rotation_off_never_turns(core, monkeypatch):
    import threading
    module = importlib.import_module('a4kStreaming.ui.home')
    win = module.Home('a4k-home.xml', '', 'Default', '1080i')
    win.hero_turn = 0
    win.stopped = threading.Event()
    waits, turns = [], []
    monkeypatch.setattr(win.stopped, 'wait', lambda t: waits.append(t) or len(waits) > 3)
    monkeypatch.setattr(win, 'turn', lambda: turns.append(1))
    monkeypatch.setattr(core.kodi.xbmc, 'getInfoLabel', lambda label: '5' if label.endswith('NumItems') else 'Heat')
    win.rotate()
    assert waits == [module.HERO_IDLE] * 4 and turns == []

def test_hero_takes_one_title_of_each_source_in_turn_without_repeats(core, home, monkeypatch):
    ids = {(301, 0): 'tt1', (301, 1): 'tt2', (302, 0): 'tt2', (302, 1): 'tt3', (302, 2): 'tt4'}
    def label(text):
        if text.endswith('NumItems'):
            return {'Container(301).NumItems': '2', 'Container(302).NumItems': '3'}[text]
        for (container, index), id in ids.items():
            if text == 'Container(%s).ListItemAbsolute(%s).Property(a4k.id)' % (container, index):
                return id
        return ''
    monkeypatch.setattr(core.kodi.xbmc, 'getInfoLabel', label)
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    window.sources = ((301, 'A'), (302, 'B'))
    assert window.hero_items() == [(301, 0, 'A'), (302, 0, 'B'), (302, 1, 'B'), (302, 2, 'B')]  # tt2 once

def test_hero_series_reads_go_to_show_and_opens_its_detail(core, home, monkeypatch, calls):
    item = 'Container(302).ListItemAbsolute(0).'
    values = {'Container(302).NumItems': '1', item + 'Property(a4k.type)': 'tvSeries', item + 'Property(a4k.id)': 'tt5',
              item + 'Label': 'A Show'}
    monkeypatch.setattr(core.kodi.xbmc, 'getInfoLabel', lambda label: values.get(label, ''))
    opened_detail = []
    monkeypatch.setattr(importlib.import_module('a4kStreaming.ui.detail'), 'open', lambda info: opened_detail.append(info) or True)
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    window.sources = ((302, 'TRENDING NOW'),)
    window.show_hero()
    assert (window.getProperty('a4k.hero.act'), window.getProperty('a4k.hero.kicker')) == ('Go to Show', 'TRENDING NOW')
    window.onClick(home.HERO_PLAY)
    assert [info['Property(a4k.id)'] for info in opened_detail] == ['tt5'] and calls == []

def test_the_settings_apply_the_new_appearance_once_closed(core, home, monkeypatch, calls):
    import threading
    values = {}
    settings(core, monkeypatch, values)
    # not up yet, up (the user changes two settings), a gap (the window hands over to Kodi's dialog), up, closed
    looks = iter([False, True, True, False, True, True, False, False])
    def active(condition):
        assert condition == home.SETTINGS_SHOWN
        up = next(looks)
        if up:
            values.update({'appearance.hero_source': '1', 'appearance.reality': 'true'})
        return up
    monkeypatch.setattr(core.kodi.xbmc, 'getCondVisibility', active, raising=False)
    threads, timers = [], []
    monkeypatch.setattr(home.threading, 'Thread', lambda target: SimpleTimer(threads, target))
    monkeypatch.setattr(home.threading, 'Timer', lambda seconds, target, args=(): SimpleTimer(timers, (target, args)))
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    window.stopped = threading.Event()
    monkeypatch.setattr(window.stopped, 'wait', lambda seconds: False)
    home.apply(window)
    window.hero = 3
    window.onClick(home.SETTINGS)
    # opened without waiting (a blocking builtin holds Python's lock), watched from a thread
    assert calls == ['RunScript(plugin.video.a4kstreaming,settings)'] and threads == [window.settings_closed]
    assert window.getProperty('a4k.title.303') == ''
    window.settings_closed()
    assert window.getProperty('a4k.title.303') == 'Reality TV' and list(window.sources) == [(302, 'TRENDING NOW')]
    # every slot with a listing shows for FRESH_TIME (a hidden list never loads), then the shelf starts over
    assert window.getProperty('a4k.fresh') == 'true' and timers == [(window.setProperty, ('a4k.fresh', '')), (window.turn, ())]
    assert window.hero == -1 and window.error is None

def test_settings_watch_stops_looking_when_nothing_opens(core, home, monkeypatch):
    import threading
    looks = []
    monkeypatch.setattr(core.kodi.xbmc, 'getCondVisibility', lambda condition: looks.append(1) and False, raising=False)
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    window.stopped = threading.Event()
    monkeypatch.setattr(window.stopped, 'wait', lambda seconds: False)
    reapplied = []
    monkeypatch.setattr(window, 'reapply', lambda: reapplied.append(1))
    window.settings_closed()
    assert len(looks) == home.SETTINGS_OPEN + 3 and reapplied == [1]  # and once more after the settle
    monkeypatch.setattr(window.stopped, 'wait', lambda seconds: seconds == home.SETTINGS_SETTLE)  # closes meanwhile
    window.settings_closed()
    assert reapplied == [1]

class SimpleTimer(object):
    def __init__(self, log, target): self.log, self.target = log, target
    def start(self): self.log.append(self.target)

def test_my_list_picker_offers_the_title_lists(core, monkeypatch):
    import json
    appearance = importlib.import_module('a4kStreaming.ui.appearance')
    sheets = importlib.import_module('a4kStreaming.ui.sheets')
    settings(core, monkeypatch, {'imdb.at-main': 'token', 'appearance.my_list': 'ls2 Favoritos'})
    files = [{'file': PLUGIN + '?action=query&type=list&id=ls1', 'label': 'Weekend Picks', 'plot': 'Movie or TV Series from Weekend Picks'},
             {'file': PLUGIN + '?action=query&type=list&id=ls9', 'label': 'Actors', 'plot': 'Stars, Directors or Writers from Actors'},
             {'file': PLUGIN + '?action=query&type=list&id=ls2', 'label': 'Favoritos', 'plot': 'Movie or TV Series from Favoritos'}]
    monkeypatch.setattr(core.kodi.xbmc, 'executeJSONRPC', lambda request: json.dumps({'result': {'files': files}}))
    asked = []
    monkeypatch.setattr(sheets, 'select', lambda heading, labels, preselect=-1: asked.append((labels, preselect)) or 1)
    saved = {}
    monkeypatch.setattr(core.kodi.addon, 'setSetting', lambda key, value: saved.update({key: value}), raising=False)
    appearance.pick_my_list()
    assert asked == [(['None', 'Weekend Picks', 'Favoritos'], 2)] and saved == {'appearance.my_list': 'ls1 Weekend Picks'}

def test_down_on_the_last_shown_row_stays_there(core, home, monkeypatch):
    values = {}
    settings(core, monkeypatch, values)
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    home.apply(window)
    window.wire()
    row = window.getControl
    assert row(301).down is row(320) and row(302).down is row(302)  # signed out: two rows
    values['appearance.reality'] = 'true'  # a third row: the second goes down to it again
    home.apply(window)
    window.wire()
    assert row(302).down is row(330) and row(303).down is row(303)

# 7. series detail page (#023): episode cards, the focused-episode panel, season marks, the action row

@pytest.fixture
def listing(core):
    return vars(importlib.import_module('a4kStreaming.listing'))

@pytest.fixture
def detail(core):
    return importlib.import_module('a4kStreaming.ui.detail')

def an_episode(number, date, **extra):
    episode = {'id': 'tt9%s' % number, 'titleType': 'tvEpisode', 'titleText': 'Chapter %s' % number, 'primaryImage': None,
               'series': {'seasonNumber': 1, 'episodeNumber': number}, 'releaseDate': dict(zip(('year', 'month', 'day'), date))}
    episode.update(extra)
    return episode

def episode_items(core, listing, monkeypatch, episodes, plot='The show.'):
    added = []
    monkeypatch.setattr(core.kodi.xbmcplugin, 'addDirectoryItems', lambda handle, items, n: added.extend(items))
    settings(core, monkeypatch, {})
    title = {'id': 'tt1', 'titleText': 'A Show', 'plot': plot, 'episodes': {'seasons': [1], 'episodes': episodes}}
    listing['__add_episodes'](core, title, 1)
    return [item for _, item, _ in added]

def test_episode_cards_carry_the_tv_skins_label_title_meta_and_own_plot(core, listing, monkeypatch):
    aired = an_episode(1, (2022, 2, 18), plot='Mark meets a new hire.', runtime=3720,
                       ratingsSummary={'aggregateRating': 7.64, 'voteCount': 900})
    unaired = an_episode(2, (2099, 10, 30))
    first, second = episode_items(core, listing, monkeypatch, [aired, unaired])
    # the label is the numbered title; the card reads the bare title, "S1 E1", rating, and date · runtime
    assert first.label == '1. Chapter 1'
    assert {k: v for k, v in first.properties.items() if k in listing['episode_properties'](aired, True)} == {
        'a4k.label': 'S1 E1', 'a4k.name': 'Chapter 1', 'a4k.plot': 'Mark meets a new hire.', 'a4k.rating': '7.6',
        'a4k.meta': 'February 18, 2022 · 62m'}
    # no plot of its own: the panel stays hidden (the show's plot is not the episode's); unaired says so
    assert (second.getProperty('a4k.plot'), second.getProperty('a4k.rating'), second.getProperty('a4k.meta')) == (
        '', '', 'October 30, 2099 · Unaired')

@pytest.mark.parametrize('date,text', [
    ({'year': 2026, 'month': 10, 'day': 30}, 'October 30, 2026'), ({'year': 2026, 'month': 1}, 'January 2026'),
    ({'year': 2026}, '2026'), ({}, ''), (None, '')])
def test_date_text_is_imdbs_display(listing, date, text):
    assert listing['date_text'](date) == text

def test_season_tabs_mark_watched_and_progress(core, detail):
    def ep(id, season, number, rated):
        return {'id': id, 'series': {'seasonNumber': season, 'episodeNumber': number}, 'userRating': rated,
                'releaseDate': {'year': 2020 + season, 'month': 1, 'day': number}}
    title = {'id': 'tt1', 'episodes': {'episodes': [
        ep('a1', 1, 1, 8), ep('a2', 1, 2, 9),        # all rated: watched
        ep('b1', 2, 1, 7), ep('b2', 2, 2, None), ep('b3', 2, 3, None), ep('b4', 2, 4, None),  # one of four
        ep('c1', 3, 1, None), ep('c2', 3, 2, None),  # none
    ]}}
    pills, _ = detail.seasons(core, title)
    assert [(p['label'], p['watched'], p['progress']) for p in pills] == [
        ('Season 1', 'true', ''), ('Season 2', '', '25'), ('Season 3', '', '')]

def test_episode_panel_shows_the_focused_episodes_label_title_and_plot(listing):
    root = xml('a4k-detail.xml')
    shows = 'Control.HasFocus(530) + !String.IsEmpty(Container(530).ListItem.Property(a4k.plot))'
    panel = [g for g in root.find('controls').findall('control') if g.findtext('visible') == shows]
    assert len(panel) == 1  # a window-level group, so the page's scroll never moves it
    texts = ' '.join(c.findtext('label') or '' for c in panel[0].iter('control'))
    assert re.findall(r'Container\(530\)\.ListItem\.Property\(([\w.]+)\)', texts) == ['a4k.label', 'a4k.name', 'a4k.plot']
    # the title's info and buttons fade out under it
    info = control(root, 200)
    assert [a.get('condition') for a in info.findall('animation')] == [shows]
    # every episode property the cards and the panel read is one the listing sets
    episodes = ElementTree.tostring(control(root, 530)).decode() + texts
    read = set(re.findall(r'ListItem\.Property\((a4k\.[\w.]+)\)', episodes))
    assert read == set(listing['episode_properties'](an_episode(1, (2022, 1, 1)), True))

def test_series_row_has_no_play_and_icon_buttons(detail):
    root = xml('a4k-detail.xml')
    assert root.findtext('defaultcontrol') == '500'  # the row's first shown button
    assert control(root, detail.PLAY).findtext('visible') == 'String.IsEmpty(Window.Property(a4k.series))'
    assert control(root, detail.TRAILER).findtext('label') == '$INFO[Window.Property(a4k.trailers)]'
    assert [(control(root, i).findtext('width'), control(root, i).findtext('label')) for i in (detail.WATCHLIST, detail.MORE)] == [
        ('76', '$INFO[Window.Property(a4k.wlabel)]'), ('76', '•••')]
    # the season pills read the marks the window sets
    pills = ElementTree.tostring(control(root, detail.SEASONS)).decode()
    assert set(re.findall(r'ListItem\.Property\((\w+)\)', pills)) == {'url', 'watched', 'progress'}

# 8. the ··· menu (#023): the TV skin's rows, in its order, filtered by state, no prefixes

TITLE_ROWS = ['Rate', 'Add to watchlist', 'Remove from watchlist', 'Add to IMDb list', 'Remove from IMDb list', 'More Like This']

def labels_of(listing, core, **title):
    return [label for label, _ in listing['title_context_menu'](core, dict({'id': 'tt1', 'primaryVideos': ['vi1', 'vi2']}, **title))]

@pytest.mark.parametrize('state, rows', [
    ({'userRating': None, 'a4k.in_watchlist': False},
     ['Rate', 'Add to watchlist', 'Add to IMDb list', 'Remove from IMDb list', 'More Like This']),
    ({'userRating': 8, 'a4k.in_watchlist': True},
     ['Rate', 'Unrate', 'Remove from watchlist', 'Add to IMDb list', 'Remove from IMDb list', 'More Like This']),
    ({'userRating': None}, TITLE_ROWS),  # a card: the watchlist state is unknown, so both rows (the TV skin's rule)
])
def test_movie_menu_rows(core, listing, state, rows):
    assert labels_of(listing, core, titleType='movie', **state) == rows

@pytest.mark.parametrize('state, rows', [
    ({'userRating': None, 'a4k.in_watchlist': False, 'a4k.show_watched': False},
     ['Rate', 'Add to watchlist', 'Add to IMDb list', 'Remove from IMDb list', 'More Like This', 'Mark show watched']),
    ({'userRating': 9, 'a4k.in_watchlist': True, 'a4k.show_watched': True},
     ['Rate', 'Unrate', 'Remove from watchlist', 'Add to IMDb list', 'Remove from IMDb list', 'More Like This',
      'Unmark show watched']),
    ({'userRating': None}, TITLE_ROWS + ['Mark show watched', 'Unmark show watched']),
])
def test_show_menu_rows(core, listing, state, rows):
    assert labels_of(listing, core, titleType='tvSeries', **state) == rows

@pytest.mark.parametrize('state, rows', [
    ({'userRating': None}, ['Play from here', 'Rate', 'Mark watched', 'Episode details']),
    ({'userRating': 7, 'a4k.resumable': True},
     ['Play from here', 'Reset resume progress', 'Rate', 'Unmark watched', 'Episode details']),
])
def test_episode_menu_rows(core, listing, state, rows):
    assert labels_of(listing, core, titleType='tvEpisode', **dict(state, **{'a4k.play': 'plugin://x/?action=play&type=e1'})) == rows

def test_menu_rows_carry_no_prefix_and_none_the_page_or_the_source_sheet_covers(core, listing):
    gone = ('Trailer', 'Trailers', 'Choose Trailer', 'All Cast', 'Cast & Crew', 'Add sources', 'Force file select',
            'Refresh sources', 'Force source select')
    for type in ('movie', 'tvSeries', 'tvEpisode'):
        for rated in (None, 8):
            rows = labels_of(listing, core, titleType=type, userRating=rated, **{'a4k.play': 'p'})
            assert not [row for row in rows if ':' in row or row in gone]

def test_menu_builtins(core, listing):
    menu = dict(listing['title_context_menu'](core, {'id': 'tt5', 'titleType': 'tvSeries', 'userRating': 8}))
    assert menu['Unrate'] == 'RunPlugin(%s?action=profile&type=mark_as_unwatched&id=tt5)' % core.url
    assert menu['Mark show watched'] == 'RunPlugin(%s?action=profile&type=mark_as_watched&id=tt5&show=true)' % core.url
    play = 'plugin://plugin.video.a4kstreaming/?action=play&type=e1'
    episode = dict(listing['title_context_menu'](core, {'id': 'tt6', 'titleType': 'tvEpisode', 'a4k.play': play, 'a4k.resumable': True,
                                                        'a4k.key': 'tt1:1:2'}))
    assert episode['Play from here'] == 'PlayMedia(%s,noresume)' % play
    assert episode['Reset resume progress'] == 'RunPlugin(%s?action=reset_resume&path=%s&key=tt1%%3A1%%3A2)' % (
        core.url, 'plugin%3A%2F%2Fplugin.video.a4kstreaming%2F%3Faction%3Dplay%26type%3De1')

def test_watchlist_gallery_titles_offer_remove_only(core, listing):
    assert 'Add to watchlist' not in labels_of(listing, core, titleType='movie', **{'a4k.in_watchlist': True})

# 9. the TV skin's card line and marks, the detail line (#023)

@pytest.mark.parametrize('title, line', [
    ({'releaseYear': 2024, 'ratingsSummary': {'aggregateRating': 7.8}, 'runtime': 7800}, '2024 · ★ 7.8 · 2h 10m'),
    ({'releaseYear': 2008, 'releaseEndYear': 2013, 'ratingsSummary': {'aggregateRating': 9.5}, 'runtime': 2700}, '2008–2013 · ★ 9.5 · 45m'),
    ({'releaseYear': 2020, 'releaseEndYear': 2020}, '2020'),
    ({'releaseYear': None, 'ratingsSummary': None, 'runtime': None}, ''),
])
def test_card_meta_is_the_tv_skins_line(listing, title, line):
    assert listing['card_meta'](title) == line

@pytest.mark.parametrize('title, badge', [
    ({'episodes': {'isOngoing': True, 'seasons': [1, 2, 3]}}, ('TV·3', 'ongoing')),
    ({'episodes': {'isOngoing': False, 'seasons': [1, 2, 3, 4, 5]}}, ('TV·5', 'ended')),
    ({'releaseEndYear': 2013}, ('TV', 'ended')),  # no isOngoing: the end year decides
    ({}, ('TV', 'ongoing')),
])
def test_tv_badge(listing, title, badge):
    assert listing['tv_badge'](title) == badge

@pytest.mark.parametrize('name', ['a4k-home.xml', 'a4k-grid.xml', 'a4k-search.xml'])
def test_every_poster_card_has_the_meta_line_and_marks(name):
    root = xml(name)
    for kind in ('itemlayout', 'focusedlayout'):
        for layout in root.iter(kind):
            textures = ' '.join(t.text or '' for t in layout.iter('texture'))
            if 'ListItem.Art(poster)' not in textures:
                continue
            labels = ' '.join(c.findtext('label') or '' for c in layout.iter('control'))
            visibles = ' '.join(c.findtext('visible') or '' for c in layout.iter('control'))
            assert '$INFO[ListItem.Property(a4k.meta)]' in labels and 'ListItem.Year' not in labels, name
            assert 'ListItem.Property(a4k.rated),true' in visibles and 'ListItem.Property(a4k.tvstate),ongoing' in visibles, name
            assert '$INFO[ListItem.Property(a4k.tv)]' in labels and 'a4k/check.png' in textures, name

def test_detail_line_ended_series_years_unaired_and_own_rating(core, detail):
    base = {'id': 'tt1', 'titleType': 'tvSeries', 'titleText': 'A Show', 'releaseYear': 2008, 'releaseEndYear': 2013,
            'releaseDate': {'year': 2008, 'month': 1, 'day': 20}, 'genres': ['Drama'], 'userRating': 9}
    vm = detail.view_model(core, base)
    assert vm['meta'] == '2008–2013 · Drama' and vm['yours'] == 'Your ★ 9'
    movie = dict(base, titleType='movie', releaseEndYear=None, releaseYear=2099, releaseDate={'year': 2099, 'month': 10, 'day': 30},
                 userRating=None, runtime=6000)
    vm = detail.view_model(core, movie)
    assert vm['meta'] == 'October 30, 2099 · 1h 40m · Drama · Unaired' and vm['yours'] == ''

def test_trailer_picker_rows_are_name_and_runtime(core, monkeypatch):
    imdb = importlib.import_module('a4kStreaming.imdb')
    body = {'data': {'title': {'primaryVideos': {'edges': [
        {'node': {'id': 'vi1', 'name': {'value': 'Official Trailer'}, 'runtime': {'value': 151}}},
        {'node': {'id': 'vi2', 'name': None, 'runtime': None}}]}}}}
    requests = []
    def execute(core, request, cache=True):
        requests.append(request)
        response = lambda: None
        response.content, response.status_code = core.json.dumps(body), 200
        return response
    monkeypatch.setattr(core.request, 'execute', execute)
    assert imdb.trailer_rows(core, 'tt1', ['vi1', 'vi2']) == [('►  Official Trailer', '2:31'), ('►  Video 2', '')]
    assert len(requests) == 1

def test_trailer_with_none_says_so_and_several_open_the_picker(core, monkeypatch):
    imdb = importlib.import_module('a4kStreaming.imdb')
    notes, shown = [], []
    monkeypatch.setattr(core.kodi, 'notification', lambda text, time=3000: notes.append(text))
    imdb.trailer(core, core.utils.DictAsObject({'id': 'tt1', 'vi': '', 'play': 'true'}))
    assert notes == ['No trailers available']
    sheets = importlib.import_module('a4kStreaming.ui.sheets')
    monkeypatch.setattr(imdb, 'trailer_rows', lambda core, id, videos: [('►  A', '1:00'), ('►  B', '2:00')])
    monkeypatch.setattr(sheets, 'select', lambda heading, labels, rows=None, **k: shown.append((heading, rows)) or -1)
    imdb.trailer(core, core.utils.DictAsObject({'id': 'tt1', 'vi': 'vi1_vi2', 'play': 'true'}))
    assert shown == [('Trailers', [('►  A', '1:00'), ('►  B', '2:00')])]  # Back: nothing plays
