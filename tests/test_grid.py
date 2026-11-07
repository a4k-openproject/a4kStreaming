# -*- coding: utf-8 -*-
# Offline tests for the browse grid (a4k-grid.xml) and what opens it: the Browse tiles, search, years, the detail
# window's cast and More like this, the rest of a home row. Also the home window's top shelf rotation and the detail
# plot. The grid's skin lint; the shared checks run over every window in test_ui.py.

import os
import re
import threading
import importlib
from types import SimpleNamespace
from datetime import datetime
from xml.etree import ElementTree
from .common import pytest, api

WINDOWS = os.path.join(os.path.dirname(__file__), '..', 'resources', 'skins', 'Default', '1080i')
XML = os.path.join(WINDOWS, 'a4k-grid.xml')
PLUGIN = 'plugin://plugin.video.a4kstreaming/'
NEXT = PLUGIN + '?action=query&type=fan_picks&paginationToken=abc&page=2&cursor_time=1'

@pytest.fixture(scope='module')
def core():
    core = api.A4kStreamingApi({'kodi': True}).core
    core.url = PLUGIN
    return core

@pytest.fixture
def grid(core):
    return importlib.import_module('a4kStreaming.ui.grid')

@pytest.fixture
def home(core):
    return importlib.import_module('a4kStreaming.ui.home')

@pytest.fixture
def detail(core):
    return importlib.import_module('a4kStreaming.ui.detail')

@pytest.fixture(autouse=True)
def clean(core, monkeypatch):
    properties = importlib.import_module('a4kStreaming.lib.kodi_mock')._window_properties
    properties.clear()
    importlib.import_module('a4kStreaming.ui.detail')._cache.clear()
    monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: '')
    yield
    properties.clear()

def login(core, monkeypatch):
    monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: 'token' if key == 'imdb.at-main' else '')

@pytest.fixture
def calls(core, monkeypatch):
    log = []
    monkeypatch.setattr(core.kodi.xbmc, 'executebuiltin', lambda builtin, wait=False: log.append(builtin))
    return log

@pytest.fixture
def notes(core, monkeypatch):
    log = []
    monkeypatch.setattr(core.kodi, 'notification', lambda text, time=3000: log.append(text))
    return log

@pytest.fixture
def errors(grid, monkeypatch):
    log = []
    monkeypatch.setattr(grid.logger, 'error', log.append)
    return log

@pytest.fixture
def labels(core, monkeypatch):
    # the InfoLabels Kodi would answer; tests fill the dict
    values = {}
    monkeypatch.setattr(core.kodi.xbmc, 'getInfoLabel', lambda label: values.get(label, ''))
    return values

@pytest.fixture
def shown(grid, monkeypatch):
    log = []
    monkeypatch.setattr(grid, 'show', lambda path, title, kicker='': log.append((path, title, kicker)))
    return log

class Sync(object):
    # threading stand-in: threads and timers run at start()
    class Thread(object):
        def __init__(self, target, args=(), **kwargs): self.target, self.args = target, args
        def start(self): self.target(*self.args)
        def cancel(self): pass

    @staticmethod
    def Timer(seconds, target): return Sync.Thread(target)

class Action(object):
    def __init__(self, id): self.id = id
    def getId(self): return self.id

def item(type='', path='', label='', id=''):
    return {'Property(a4k.type)': type, 'FolderPath': path, 'Label': label, 'Property(a4k.id)': id}

# A. the Browse tiles

def tiles():
    root = ElementTree.parse(os.path.join(WINDOWS, 'a4k-home.xml')).getroot()
    panel = [c for c in root.iter('control') if c.get('id') == '400'][0]
    for node in panel.find('content').findall('item'):
        prop = node.find("property[@name='a4k.grid']")
        yield node.findtext('label'), prop.text if prop is not None else None, node.findtext('onclick')

def test_tiles_open_the_grid_and_debrid_keeps_its_directory(core, grid, home, labels, shown, calls, monkeypatch):
    flows = []
    monkeypatch.setattr(grid, 'search', lambda: flows.append('search'))
    monkeypatch.setattr(grid, 'years', lambda: flows.append('years'))
    win = home.Home('a4k-home.xml', '', 'Default', '1080i')
    win.setFocusId(home.TILES)
    expected = []
    for label, tile, onclick in tiles():
        labels.update({'Container(400).ListItem.Property(a4k.grid)': tile or '', 'Container(400).ListItem.Label': label})
        win.onAction(Action(home.ACTION_SELECT_ITEM))
        assert (tile is None) == (onclick is not None), label  # a tile either opens the grid or runs its own onclick
        if tile and tile not in ('search', 'years'):
            expected.append((PLUGIN + '?action=query&type=%s&widget=1' % tile, label, ''))
    assert flows == ['search', 'years'] and shown == expected and calls == [] and win.error is None
    assert [label for label, _, _ in tiles()][:5] == ['Search', 'Watchlist', 'Recommended', 'Lists', 'By Year']
    assert dict((label, tile) for label, tile, _ in tiles())['Lists'] == 'lists'
    assert 'action=cloud' in dict((label, onclick) for label, _, onclick in tiles())['Debrid']

def test_tile_listing_types_are_queries_the_plugin_knows(core):
    imdb = importlib.import_module('a4kStreaming.imdb')
    types = {tile for _, tile, _ in tiles() if tile not in (None, 'search', 'years')}
    assert types <= set(imdb.gallery_types) | {'watchlist', 'top_picks', 'lists'}

def test_home_row_next_item_opens_the_rest_of_the_row(core, home, labels, shown):
    labels.update({'Container(301).ListItem.FolderPath': NEXT})
    win = home.Home('a4k-home.xml', '', 'Default', '1080i')
    win.setFocusId(301)
    win.onAction(Action(home.ACTION_SELECT_ITEM))
    assert shown == [(NEXT, 'Trending Movies', '')]

# B. the grid window

@pytest.fixture
def opened(core, grid, monkeypatch):
    # open() runs the window the way Kodi would: onInit; the window is kept for the test
    monkeypatch.setattr(grid, 'threading', Sync)
    windows = []
    monkeypatch.setattr(grid.Grid, 'doModal', lambda self: windows.append(self) or self.onInit())
    return windows

class Panel(object):
    # the grid's panel as Python sees a provider list: no position (getSelectedPosition is -1), selectItem works
    def __init__(self): self.selected = []
    def getSelectedPosition(self): return -1
    def selectItem(self, index): self.selected.append(index)

def window(grid, opened, monkeypatch, path=PLUGIN + '?action=query&type=fan_picks&widget=1', title='Fan Favorites',
           kicker='Browse'):
    assert grid.open(path, title, kicker) is True
    win = opened[0]
    win.closed = False  # the mock doModal has returned
    panel = Panel()
    monkeypatch.setattr(win, 'getControl', lambda id: panel if id == grid.PANEL else pytest.fail(id))
    monkeypatch.setattr(win, 'refocus', lambda: None)  # test_focus_comes_back_* drives it
    win.setFocusId(grid.PANEL)
    return win, panel

def test_grid_paints_its_header_and_listing(core, grid, opened):
    assert grid.open(PLUGIN + '?action=query&type=fan_picks&widget=1', 'Fan Favorites', 'Browse') is True
    win = opened[0]
    assert win.error is None and win.steps == []
    assert {k: win.getProperty('a4k.' + k) for k in ('kicker', 'title', 'page', 'path')} == {
        'kicker': 'BROWSE', 'title': 'Fan Favorites', 'page': '', 'path': PLUGIN + '?action=query&type=fan_picks&widget=1'}
    assert core.kodi.xbmcgui.Window(10000).getProperty('a4k.ui.window') == '10025'

def test_next_item_pages_forward_and_back_walks_back(core, grid, opened, labels, monkeypatch):
    closed = []
    monkeypatch.setattr(grid.Grid, 'close', lambda self: closed.append(True))
    win, panel = window(grid, opened, monkeypatch)
    labels.update({'Container(500).ListItem.FolderPath': NEXT, 'Container(500).CurrentItem': '30'})
    win.onAction(Action(7))
    assert win.getProperty('a4k.path') == NEXT + '&widget=1' and win.getProperty('a4k.page') == 'Page 2'
    assert win.getProperty('a4k.title') == 'Fan Favorites' and panel.selected == [0]  # the new page starts at the top
    labels['Container(500).CurrentItem'] = '5'
    win.onAction(Action(92))
    assert win.getProperty('a4k.path') == PLUGIN + '?action=query&type=fan_picks&widget=1' and win.getProperty('a4k.page') == ''
    assert panel.selected == [0, 29] and closed == []  # back on the Next item it came from
    win.onAction(Action(10))
    assert closed == [True] and win.error is None

def test_a_list_opens_in_place_with_its_name(core, grid, opened, labels, monkeypatch):
    win, panel = window(grid, opened, monkeypatch, PLUGIN + '?action=query&type=lists&widget=1', 'Lists', '')
    path = PLUGIN + '?action=query&type=list&id=ls1'
    labels.update({'Container(500).ListItem.FolderPath': path, 'Container(500).ListItem.Label': 'Weekend',
                   'Container(500).CurrentItem': '3'})
    win.onAction(Action(7))
    assert (win.getProperty('a4k.title'), win.getProperty('a4k.kicker'), win.getProperty('a4k.path')) == ('Weekend', '', path + '&widget=1')
    assert win.steps == [(PLUGIN + '?action=query&type=lists&widget=1', 'Lists', '', 2)]

def test_select_routes_titles_people_and_episodes(core, grid, home, opened, labels, calls, notes, monkeypatch):
    selected = []
    monkeypatch.setattr(home, 'select', lambda info: selected.append(info['Property(a4k.id)']))
    win, panel = window(grid, opened, monkeypatch)
    win.select(item('movie', id='tt1'))
    win.select(item('tvSeries', id='tt2'))
    win.select(item('tvEpisode', PLUGIN + '?action=play&type=ep', id='tt3'))
    person = item('person', PLUGIN + '?action=query&type=knownfor&id=nm1', 'Ana Torres', 'nm1')
    win.select(person)  # known for needs an IMDb login: the classic listing's notification
    assert selected == ['tt1', 'tt2'] and calls == ['PlayMedia(%s?action=play&type=ep)' % PLUGIN]
    assert notes == [grid.NO_LOGIN] and win.steps == []
    login(core, monkeypatch)
    win.select(person)
    assert win.getProperty('a4k.title') == 'Ana Torres' and win.getProperty('a4k.kicker') == 'KNOWN FOR'
    win.select(item())  # an empty item does nothing
    assert len(win.steps) == 1

def test_focus_near_the_end_prefetches_the_next_page_once(core, grid, opened, labels, monkeypatch):
    rpc = []
    monkeypatch.setattr(core.kodi, 'json_rpc', lambda method, params, log_error=True: rpc.append((method, params['directory'])))
    win, panel = window(grid, opened, monkeypatch)
    labels.update({'Container(500).NumItems': '31', 'Container(500).ListItemAbsolute(30).FolderPath': NEXT,
                   'Container(500).CurrentItem': '6'})
    win.onAction(Action(4))
    assert rpc == []
    labels['Container(500).CurrentItem'] = '20'  # two rows of six from the Next item
    win.onAction(Action(4))
    win.onAction(Action(3))
    assert rpc == [('Files.GetDirectory', NEXT + '&widget=1')] and win.error is None

@pytest.mark.parametrize('counts, focused', [
    (['0', '0', '30'], [500]),  # back from an empty page: Kodi dropped focus, the items come, the panel gets it
    (['30'], [500]),            # the panel is the only focusable control: focusing it again moves nothing
    (['0'] * 200, []),          # still empty after 15 s: give up
])
def test_focus_comes_back_when_items_come(core, grid, opened, labels, monkeypatch, counts, focused):
    win, panel = window(grid, opened, monkeypatch)
    sleeps, calls = [], []
    monkeypatch.setattr(core.kodi.xbmc, 'sleep', lambda ms: sleeps.append(ms))
    monkeypatch.setattr(core.kodi.xbmc, 'getInfoLabel', lambda label: counts.pop(0) if label == 'Container(500).NumItems' else '')
    monkeypatch.setattr(win, 'setFocusId', calls.append)
    win.wait_and_focus(win.path)
    assert calls == focused and len(sleeps) <= 150
    win.wait_and_focus('another page')  # a later step owns the focus now
    assert calls == focused

def test_moves_outside_the_panel_are_ignored(core, grid, opened, monkeypatch):
    win, panel = window(grid, opened, monkeypatch)
    win.setFocusId(0)
    monkeypatch.setattr(win, 'moved', lambda: pytest.fail('moved'))
    win.onAction(Action(4))

# C. fallback: one log line, then the classic listing for the rest of the session

def test_window_error_falls_back_to_the_classic_listing_once(core, grid, opened, calls, errors, monkeypatch):
    def broken(self, id): raise RuntimeError('no such control')
    monkeypatch.setattr(grid.Grid, 'getControl', broken)
    grid.show(PLUGIN + '?action=query&type=fan_picks&widget=1', 'Fan Favorites')
    assert calls == ['ActivateWindow(Videos,%s?action=query&type=fan_picks,return)' % PLUGIN]
    assert len(errors) == 1 and core.kodi.xbmcgui.Window(10000).getProperty(grid.FAILED)
    monkeypatch.setattr(grid, 'Grid', lambda *a: pytest.fail('opened the grid again'))
    grid.show(PLUGIN + '?action=search&query=heat&widget=1', 'heat', 'Search')
    assert calls[-1] == 'ActivateWindow(Videos,%s?action=search&query=heat,return)' % PLUGIN and len(errors) == 1

def test_missing_window_file_falls_back(core, grid, calls, errors, monkeypatch):
    def missing(*args): raise RuntimeError('a4k-grid.xml not found')
    monkeypatch.setattr(grid, 'Grid', missing)
    grid.more_like_this('tt1', 'Heat')
    assert calls == ['ActivateWindow(Videos,%s?action=query&type=more_like_this&id=tt1,return)' % PLUGIN] and len(errors) == 1

@pytest.mark.parametrize('current, expected', [(13000, []), (10000, ['ReplaceWindow(13000)'])])
def test_closing_the_grid_returns_to_the_window_below(core, grid, opened, calls, monkeypatch, current, expected):
    core.kodi.xbmcgui.Window(10000).setProperty('a4k.ui.window', '13000')
    monkeypatch.setattr(core.kodi.xbmcgui, 'getCurrentWindowId', lambda: current)
    grid.open(PLUGIN + '?action=query&type=fan_picks&widget=1', 'Fan Favorites')
    assert calls == expected
    assert core.kodi.xbmcgui.Window(10000).getProperty('a4k.ui.window') == '13000'

# D. search, years, known for, more like this

def test_search_asks_then_shows_the_results(core, grid, shown, monkeypatch):
    imdb = importlib.import_module('a4kStreaming.imdb')
    asked = []
    answers = [('the martian', True), ('', False), (None, True)]
    monkeypatch.setattr(imdb, 'ask_search', lambda core, history, select=None: asked.append(select) or answers.pop(0))
    for _ in range(3):
        grid.search()
    assert shown == [(PLUGIN + '?action=search&query=the+martian&widget=1', 'the martian', 'Search')]
    assert asked == [importlib.import_module('a4kStreaming.ui.sheets').select] * 3  # the history as a sheet

def test_ask_search_history_then_keyboard(core, monkeypatch):
    imdb = importlib.import_module('a4kStreaming.imdb')
    picks = []
    def select(heading, items): return picks.pop(0)
    picks[:] = [2]
    assert imdb.ask_search(core, ['heat', 'alien'], select=select) == ('alien', True)
    picks[:] = [-1]  # Back on the history
    assert imdb.ask_search(core, ['heat'], select=select) == (None, True)
    keyboard = core.kodi.xbmc.Keyboard('', '')
    monkeypatch.setattr(keyboard, 'getText', lambda: 'heat')
    monkeypatch.setattr(keyboard, 'isConfirmed', lambda: True)
    picks[:] = [0]  # New Search
    assert imdb.ask_search(core, ['alien'], select=select) == ('heat', True)
    assert imdb.ask_search(core, [], select=select) == ('heat', True)

def test_years_picks_a_decade_then_a_year_and_back_returns_to_the_decades(core, grid, shown, monkeypatch):
    sheets = importlib.import_module('a4kStreaming.ui.sheets')
    asked = []
    picks = [1, -1, 1, 0, -1]
    monkeypatch.setattr(sheets, 'select', lambda heading, items: asked.append((heading, items)) or picks.pop(0))
    grid.years()
    now = datetime.now().year
    decade = now - now % 10 - 10
    assert [heading for heading, _ in asked] == ['Discover by Year', '%s-%s' % (decade, decade + 9)] * 2
    assert asked[1][1][0] == str(decade + 9) and len(asked[1][1]) == 10
    assert shown == [(PLUGIN + '?action=query&type=year&widget=1&target_year=%s' % (decade + 9), str(decade + 9), 'Year')]
    grid.years()  # Back on the decades
    assert len(shown) == 1

def test_known_for_needs_an_imdb_login(core, grid, shown, notes, monkeypatch):
    grid.known_for('nm1', 'Ana Torres')
    assert shown == [] and notes == [grid.NO_LOGIN]
    login(core, monkeypatch)
    grid.known_for('nm1', 'Ana Torres')
    assert shown == [(PLUGIN + '?action=query&type=knownfor&widget=1&id=nm1', 'Ana Torres', 'Known for')]

def test_more_like_this_from_a_context_menu_opens_the_grid(core, home, grid, shown, calls, monkeypatch):
    items = [('IMDb: Trailer', 'RunPlugin(t)'), (home.MORE_LIKE_THIS, 'ActivateWindow(Videos,m,return)')]
    picks = [1, 0, -1]
    monkeypatch.setattr(core.kodi.xbmcgui.Dialog(), 'contextmenu', lambda labels: picks.pop(0))
    for _ in range(3):
        home.menu(items, 'tt1', 'Heat')
    assert shown == [(PLUGIN + '?action=query&type=more_like_this&widget=1&id=tt1', 'Heat', 'More like this')]
    assert calls == ['RunPlugin(t)']

def test_detail_cast_opens_known_for_and_the_plot_opens_in_full(core, detail, grid, monkeypatch):
    fetched = importlib.import_module('tests.test_detail')
    monkeypatch.setattr(detail, 'threading', Sync)
    monkeypatch.setattr(detail, 'fetch', lambda core, id, series: fetched.fixture()['movie'])
    windows = []
    monkeypatch.setattr(detail.Detail, 'doModal', lambda self: windows.append(self) or self.onInit())
    detail.open(fetched.card())
    win = windows[0]
    people, texts = [], []
    monkeypatch.setattr(grid, 'known_for', lambda id, name: people.append((id, name)))
    monkeypatch.setattr(core.kodi.xbmcgui.Dialog(), 'textviewer', lambda heading, text: texts.append((heading, text)))
    win.onClick(detail.CAST)  # the mock list's selected item is the first face
    win.onClick(detail.PLOT)
    assert people == [(win.getControl(detail.CAST).items[0].getProperty('id'), 'Matt Damon')] and people[0][0].startswith('nm')
    assert texts == [('The Martian', win.vm['plot'])] and win.vm['plot'] and win.error is None

# E. the top shelf rotation

def shelf(core, home, labels, monkeypatch, count='20'):
    win = home.Home('a4k-home.xml', '', 'Default', '1080i')
    win.own_id = 13000
    monkeypatch.setattr(core.kodi.xbmcgui, 'getCurrentWindowId', lambda: 13000)
    labels['Container(301).NumItems'] = count
    for index in range(int(count or 0)):
        labels['Container(301).ListItemAbsolute(%s).Label' % index] = 'Movie %s' % index
        labels['Container(301).ListItemAbsolute(%s).Art(fanart)' % index] = 'f%s.jpg' % index
    win.setFocusId(302)
    monkeypatch.setattr(win, 'setFocusId', lambda id: pytest.fail('took focus'))
    monkeypatch.setattr(win, 'setFocus', lambda control: pytest.fail('took focus'), raising=False)
    return win

def test_on_init_starts_the_rotation_once_and_close_stops_it(core, home, monkeypatch):
    started = []
    class Thread(object):
        def __init__(self, target): self.target = target
        def start(self): started.append(self.target)
    monkeypatch.setattr(home, 'threading', SimpleNamespace(Thread=Thread, Event=threading.Event))
    win = home.Home('a4k-home.xml', '', 'Default', '1080i')
    win.onInit()
    win.onInit()  # back from detail: the same rotation goes on
    assert started == [win.rotate] and not win.stopped.is_set() and win.error is None
    win.close()
    assert win.stopped.is_set()

def test_open_stops_the_rotation_when_the_window_ends(core, home, monkeypatch):
    windows = []
    monkeypatch.setattr(home.Home, 'rotate', lambda self: None)
    monkeypatch.setattr(home.Home, 'doModal', lambda self: windows.append(self) or self.onInit())
    home.open()
    assert windows[0].stopped.is_set()

def test_rotation_paints_when_the_row_is_in_then_turns_every_15_seconds(core, home, labels, monkeypatch):
    win = shelf(core, home, labels, monkeypatch, count='')
    polls = []
    def wait(seconds):
        polls.append(seconds)
        if len(polls) == 3:  # the row lands after three polls
            labels.update({'Container(301).NumItems': '20', 'Container(301).ListItemAbsolute(0).Label': 'Movie 0',
                           'Container(301).ListItemAbsolute(1).Label': 'Movie 1'})
        return len(polls) >= 6
    painted = []
    monkeypatch.setattr(win, 'show_hero', lambda: painted.append(win.hero))
    win.stopped = SimpleNamespace(is_set=lambda: False, wait=wait)  # the window closes at the sixth wait
    win.rotate()
    assert polls == [0.1, 0.1, 0.1, home.HERO_TURN, home.HERO_TURN, home.HERO_TURN]
    assert painted == [0, 1, 2] and win.error is None

def test_turn_walks_the_first_six_and_wraps(core, home, labels, monkeypatch):
    win = shelf(core, home, labels, monkeypatch)
    win.show_hero()
    seen = [win.getProperty('a4k.hero.label')]
    for _ in range(home.HERO_COUNT):
        win.turn()
        seen.append(win.getProperty('a4k.hero.label'))
    assert seen == ['Movie %s' % i for i in range(6)] + ['Movie 0']
    assert win.getProperty('a4k.hero.fanart') == 'f0.jpg'

@pytest.mark.parametrize('window_id, dialog_id', [(13001, 9999), (13000, 10138), (12005, 9999)])
def test_turn_waits_under_a_dialog_or_another_window(core, home, labels, monkeypatch, window_id, dialog_id):
    win = shelf(core, home, labels, monkeypatch)
    monkeypatch.setattr(core.kodi.xbmcgui, 'getCurrentWindowId', lambda: window_id)
    monkeypatch.setattr(core.kodi.xbmcgui, 'getCurrentWindowDialogId', lambda: dialog_id)
    win.turn()
    assert win.hero == 0 and win.getProperty('a4k.hero.label') == ''

def test_turn_needs_two_titles(core, home, labels, monkeypatch):
    win = shelf(core, home, labels, monkeypatch, count='1')
    win.turn()
    assert win.hero == 0

def test_hero_buttons_follow_the_shown_title(core, home, labels, calls, monkeypatch):
    win = shelf(core, home, labels, monkeypatch)
    labels.update({'Container(301).ListItemAbsolute(1).Property(a4k.type)': 'movie',
                   'Container(301).ListItemAbsolute(1).Property(a4k.id)': 'tt8'})
    win.turn()
    win.onClick(home.HERO_PLAY)
    assert calls == ['PlayMedia(%s?action=play&type=&id=tt8)' % PLUGIN]

# F. skin lint

def root():
    return ElementTree.parse(XML).getroot()

def test_panel_is_wrappable_and_keeps_focus_in(grid):
    window = root()
    panel = [c for c in window.iter('control') if c.get('id') == str(grid.PANEL)][0]
    assert panel.get('type') == 'panel' and window.findtext('defaultcontrol') == str(grid.PANEL)
    assert all(panel.findtext(edge) == 'noop' for edge in ('onup', 'ondown', 'onleft', 'onright'))
    # a provider list hands select to Kodi unless the container has its own onclick (spike 2c)
    assert panel.findtext('onclick')
    focusable = [c for c in window.iter('control') if c.get('type') in ('list', 'panel', 'button', 'wraplist', 'fixedlist')]
    assert focusable == [panel]

def test_panel_lists_the_path_property(grid):
    content = root().find(".//control[@id='500']/content")
    assert content.text.strip() == '$INFO[Window.Property(a4k.path)]' and content.get('target') == 'videos'

def test_every_property_the_xml_reads_is_set(core, grid, opened):
    grid.open(NEXT, 'Fan Favorites', 'Browse')
    read = set(re.findall(r'Window\.Property\(([\w.]+)\)', open(XML).read()))
    assert read and read <= set(opened[0].properties)

def test_grid_posters_use_the_poster_mask_at_its_aspect():
    posters = [c for c in root().iter('control') if c.findtext('texture') == '$INFO[ListItem.Art(poster)]']
    assert posters
    for poster in posters:
        assert poster.find('texture').get('diffuse') == 'a4k/mask_poster.png'
        assert int(poster.findtext('width')) * 396 == int(poster.findtext('height')) * 264

def test_tiles_and_posters_switch_per_item():
    # an itemlayout's condition is checked once for the whole panel (every item was drawn as a tile on the rig), so the
    # Next item and the lists are told apart by <visible> inside the one layout
    tile = 'String.IsEmpty(ListItem.Property(a4k.type))'
    panel = root().find(".//control[@id='500']")
    layouts = panel.findall('itemlayout') + panel.findall('focusedlayout')
    assert len(layouts) == 2 and all(layout.get('condition') is None for layout in layouts)
    for layout in layouts:
        assert sorted(group.findtext('visible') for group in layout.findall('control')) == ['!' + tile, tile]
