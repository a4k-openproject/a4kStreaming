# -*- coding: utf-8 -*-
# Offline tests for the browse grid (a4k-grid.xml) and what opens it: the Browse tiles, search, years, the detail
# window's cast and More like this, the rest of a home row. Also the home window's top shelf rotation and the detail
# plot. The grid's skin lint; the shared checks run over every window in test_ui.py.

import os
import re
import threading
import time
import importlib
from types import SimpleNamespace
from datetime import datetime
from xml.etree import ElementTree
from .common import pytest, api
from .utils import Spawned

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

def test_tiles_open_the_grid_and_debrid_its_window(core, grid, home, labels, shown, calls, monkeypatch):
    flows = []
    monkeypatch.setattr(grid, 'search', lambda: flows.append('search'))
    monkeypatch.setattr(grid, 'years', lambda: flows.append('years'))
    monkeypatch.setattr(importlib.import_module('a4kStreaming.ui.debrid'), 'open', lambda: flows.append('debrid'))
    win = home.Home('a4k-home.xml', '', 'Default', '1080i')
    win.setFocusId(home.TILES)
    expected = []
    for label, tile, onclick in tiles():
        labels.update({'Container(400).ListItem.Property(a4k.grid)': tile or '', 'Container(400).ListItem.Label': label})
        win.onAction(Action(home.ACTION_SELECT_ITEM))
        assert tile and onclick is None, label  # every tile is Python's: the grid, or the Debrid window
        if tile not in ('search', 'years', 'debrid'):
            expected.append((PLUGIN + '?action=query&type=%s&widget=1' % tile, label, ''))
    assert flows == ['years', 'debrid'] and shown == expected and calls == [] and win.error is None
    # Search and Settings are in the top menu
    assert [label for label, _, _ in tiles()][:4] == ['Watchlist', 'Recommended', 'Lists', 'By Year']
    assert not {'Search', 'Settings'} & {label for label, _, _ in tiles()}
    assert dict((label, tile) for label, tile, _ in tiles())['Lists'] == 'lists'
    assert dict((label, tile) for label, tile, _ in tiles())['Debrid'] == 'debrid'

def test_tile_listing_types_are_queries_the_plugin_knows(core):
    imdb = importlib.import_module('a4kStreaming.imdb')
    types = {tile for _, tile, _ in tiles() if tile not in (None, 'search', 'years', 'debrid')}
    assert types <= set(imdb.gallery_types) | {'watchlist', 'top_picks', 'lists'}

def test_home_row_next_item_opens_the_rest_of_the_row(core, home, labels, shown):
    labels.update({'Container(301).ListItem.FolderPath': NEXT})
    win = home.Home('a4k-home.xml', '', 'Default', '1080i')
    win.setProperty('a4k.title.301', 'Trending Movies')  # the slot's title, as apply() sets it
    win.setFocusId(301)
    win.onAction(Action(home.ACTION_SELECT_ITEM))
    assert shown == [(NEXT, 'Trending Movies', '')]

# B. the grid window

FAN = PLUGIN + '?action=query&type=fan_picks&widget=1'

@pytest.fixture
def listings(core, detail, monkeypatch):
    # what core.listing_items answers per path, built in the window's process; a test fills it, [] otherwise
    answers = {}
    monkeypatch.setattr(detail.plugin_core(), 'listing_items', lambda path: answers.get(path, []))
    return answers

@pytest.fixture
def opened(core, grid, listings, monkeypatch):
    # open() runs the window the way Kodi would: onInit; the window is kept for the test
    monkeypatch.setattr(grid.home, 'spawn', Spawned())  # the window's threads run at once
    windows = []
    monkeypatch.setattr(grid.Grid, 'doModal', lambda self: windows.append(self) or self.onInit())
    return windows

def card(type='', path='', label='', id='', menu=()):
    # a listing entry as core.listing_items answers it: (url, list_item, is_folder, menu rows)
    item = importlib.import_module('a4kStreaming.lib.kodi').xbmcgui.ListItem(label=label, offscreen=True)
    item.setProperty('a4k.type', type)
    item.setProperty('a4k.id', id)
    return (path, item, type != 'movie', list(menu))

def page(count, next=None):
    return [card('movie', PLUGIN + '?action=play&id=tt%s' % n, 'Title %s' % n, 'tt%s' % n) for n in range(count)] + \
        ([card(path=next, label='Next')] if next else [])

class Panel(object):
    # the grid's panel as Python fills it: its items and its cursor
    def __init__(self): self.items, self.selected, self.position = [], [], 0
    def reset(self): self.items = []
    def addItems(self, items): self.items.extend(items)
    def getSelectedPosition(self): return self.position if self.items else -1
    def selectItem(self, index): self.selected.append(index)

def window(grid, opened, monkeypatch, path=FAN, title='Fan Favorites', kicker='Browse'):
    panel, controls = Panel(), {}
    monkeypatch.setattr(grid.Grid, 'getControl', lambda self, id: panel if id == grid.PANEL else controls.setdefault(
        id, importlib.import_module('a4kStreaming.lib.kodi_mock').ControlList()))
    grid.show(path, title, kicker)
    win = opened[0]
    win.closed = False  # the mock doModal has returned
    win.setFocusId(grid.PANEL)
    return win, panel

def test_grid_paints_its_header_and_listing(core, grid, opened, listings, monkeypatch):
    listings[FAN] = page(3)
    win, panel = window(grid, opened, monkeypatch)
    assert win.error is None and win.steps == [] and win.path == FAN
    assert {k: win.getProperty('a4k.' + k) for k in ('kicker', 'title', 'page', 'loading')} == {
        'kicker': 'BROWSE', 'title': 'Fan Favorites', 'page': '', 'loading': ''}
    assert panel.items == [item for _, item, _, _ in listings[FAN]] and win.items == listings[FAN]
    assert [item.getPath() for item in panel.items] == [url for url, _, _, _ in listings[FAN]]  # ListItem.FolderPath
    assert core.kodi.xbmcgui.Window(10000).getProperty('a4k.ui.window') == '10025'
    win.onInit()  # back from a detail or a play: nothing reloads
    assert panel.selected == [0]

def test_next_item_pages_forward_and_back_walks_back(core, grid, opened, listings, labels, monkeypatch):
    closed = []
    monkeypatch.setattr(grid.Grid, 'close', lambda self: closed.append(True))
    listings[FAN], listings[NEXT + '&widget=1'] = page(30, NEXT), page(5)
    win, panel = window(grid, opened, monkeypatch)
    labels.update({'Container(500).ListItem.FolderPath': NEXT})
    panel.position = 30
    win.onAction(Action(7))
    assert win.path == NEXT + '&widget=1' and win.getProperty('a4k.page') == 'Page 2'
    assert win.getProperty('a4k.title') == 'Fan Favorites' and panel.selected == [0, 0]  # the new page starts at the top
    assert win.items == listings[NEXT + '&widget=1'] and len(panel.items) == 5
    panel.position = 4
    win.onAction(Action(92))
    assert win.path == FAN and win.getProperty('a4k.page') == '' and len(panel.items) == 31
    assert panel.selected == [0, 0, 30] and closed == []  # back on the Next item it came from
    win.onAction(Action(10))
    assert closed == [True] and win.error is None

def test_a_list_opens_in_place_with_its_name(core, grid, opened, listings, labels, monkeypatch):
    lists = PLUGIN + '?action=query&type=lists&widget=1'
    path = PLUGIN + '?action=query&type=list&id=ls1'
    listings[lists] = [card(path=path, label='Weekend')] * 3
    win, panel = window(grid, opened, monkeypatch, lists, 'Lists', '')
    labels.update({'Container(500).ListItem.FolderPath': path, 'Container(500).ListItem.Label': 'Weekend'})
    panel.position = 2
    win.onAction(Action(7))
    assert (win.getProperty('a4k.title'), win.getProperty('a4k.kicker'), win.path) == ('Weekend', '', path + '&widget=1')
    assert win.steps == [(lists, 'Lists', '', 2)]

def test_select_routes_titles_people_and_episodes(core, grid, home, opened, labels, calls, notes, monkeypatch):
    selected = []
    monkeypatch.setattr(home, 'select', lambda info: selected.append(info['Property(a4k.id)']))
    win, panel = window(grid, opened, monkeypatch)
    win.select(item('movie', id='tt1'))
    win.select(item('tvSeries', id='tt2'))
    win.select(item('tvEpisode', PLUGIN + '?action=play&type=ep', id='tt3'))
    person = item('person', PLUGIN + '?action=query&type=knownfor&id=nm1', 'Ana Torres', 'nm1')
    assert selected == ['tt1', 'tt2'] and calls == ['PlayMedia(%s?action=play&type=ep,noresume)' % PLUGIN]
    win.select(person)  # a person's titles are public: no login asked
    assert notes == []
    assert win.getProperty('a4k.title') == 'Ana Torres' and win.getProperty('a4k.kicker') == 'KNOWN FOR'
    win.select(item())  # an empty item does nothing
    assert len(win.steps) == 1

def test_focus_near_the_end_prefetches_the_next_page_once(core, grid, opened, listings, monkeypatch):
    rpc = []
    monkeypatch.setattr(core.kodi, 'json_rpc', lambda method, params, log_error=True: rpc.append((method, params['directory'])))
    listings[FAN] = page(30, NEXT)
    win, panel = window(grid, opened, monkeypatch)
    panel.position = 5
    win.onAction(Action(4))
    assert rpc == []
    panel.position = 19  # two rows of six from the Next item
    win.onAction(Action(4))
    win.onAction(Action(3))
    assert rpc == [('Files.GetDirectory', NEXT + '&widget=1')] and win.error is None

def test_an_answer_for_a_page_the_grid_left_is_dropped(core, grid, opened, listings, labels, monkeypatch):
    listings[FAN], listings[NEXT + '&widget=1'] = page(30, NEXT), page(5)
    win, panel = window(grid, opened, monkeypatch)
    monkeypatch.setattr(grid.home, 'spawn', Spawned(run=False))
    loads = grid.home.spawn
    labels.update({'Container(500).ListItem.FolderPath': NEXT})
    win.onAction(Action(7))
    assert panel.items == [] and win.getProperty('a4k.loading') == 'true'  # the loader shows until the page is in
    win.onAction(Action(92))
    loads[0].fire()  # the Next page answers after Back
    assert panel.items == [] and win.items == ()
    loads[1].fire()
    assert len(panel.items) == 31 and win.getProperty('a4k.loading') == ''

@pytest.mark.parametrize('focus, focused', [
    (500, 500),  # a step from the panel: Kodi drops the focus of the emptied panel, the items bring it back
    (520, 520),  # a year chip picked: the chips keep it
])
def test_the_panel_takes_focus_once_its_items_are_in(core, grid, opened, listings, monkeypatch, focus, focused):
    listings[FAN] = page(3)
    win, panel = window(grid, opened, monkeypatch)
    win.setFocusId(focus)
    win.fill()
    assert win.getFocusId() == focused and len(panel.items) == 3

def test_long_press_opens_the_add_ons_sheet_with_the_titles_rows(core, grid, home, opened, listings, calls, monkeypatch):
    sheets = []
    monkeypatch.setattr(home, 'menu', lambda rows, id, title, ran=None: sheets.append((rows, id, title, ran)))
    info = []
    monkeypatch.setattr(core.kodi.xbmcgui, 'Dialog', lambda: SimpleNamespace(info=info.append))
    rows = [('Play from here', 'PlayMedia(x,noresume)'), ('Episode details', 'Action(Info)')]
    listings[FAN] = [card('tvEpisode', 'x', 'S1 E1 Pilot', 'tt7', rows), card('person', 'p', 'Ana Torres', 'nm1'), card(path=NEXT, label='Next')]
    win, panel = window(grid, opened, monkeypatch)
    win.onAction(Action(home.ACTION_CONTEXT_MENU))
    (shown, id, title, ran), = sheets
    assert shown == [('Play from here', 'PlayMedia(x,noresume)'), ('Episode details', '')] and (id, title) == ('tt7', 'S1 E1 Pilot')
    ran('')  # Episode details: Kodi's info dialog, opened here (an Action(Info) sent while the sheet closes is dropped)
    assert info == [panel.items[0]] and calls == []
    win.onAction(Action(grid.ACTION_SHOW_INFO))  # the Info key
    assert info == [panel.items[0]] * 2
    for position in (1, 2):  # a person and the Next item have no rows and no info
        panel.position = position
        win.onAction(Action(home.ACTION_CONTEXT_MENU))
        win.onAction(Action(grid.ACTION_SHOW_INFO))
    assert len(sheets) == 1 and len(info) == 2 and win.error is None

def test_a_failed_listing_is_logged_and_the_loader_goes(core, grid, opened, detail, errors, monkeypatch):
    def broken(path): raise RuntimeError('offline')
    monkeypatch.setattr(detail.plugin_core(), 'listing_items', broken)
    win, panel = window(grid, opened, monkeypatch)
    assert len(errors) == 1 and win.getProperty('a4k.loading') == '' and win.error is None

def test_moves_outside_the_panel_are_ignored(core, grid, opened, monkeypatch):
    win, panel = window(grid, opened, monkeypatch)
    win.setFocusId(0)
    monkeypatch.setattr(win, 'moved', lambda: pytest.fail('moved'))
    win.onAction(Action(4))

# C. errors: logged, and the window closes

def test_window_error_is_logged(core, grid, opened, calls, errors, monkeypatch):
    def broken(self, id): raise RuntimeError('no such control')
    monkeypatch.setattr(grid.Grid, 'getControl', broken)
    grid.show(PLUGIN + '?action=query&type=fan_picks&widget=1', 'Fan Favorites')
    grid.show(PLUGIN + '?action=query&type=find&query=heat&widget=1', 'heat', 'Search')
    assert calls == [] and len(opened) == 2 and len(errors) == 2

def test_missing_window_file_is_logged(core, grid, calls, errors, monkeypatch):
    def missing(*args): raise RuntimeError('a4k-grid.xml not found')
    monkeypatch.setattr(grid, 'Grid', missing)
    grid.more_like_this('tt1', 'Heat')
    assert calls == [] and len(errors) == 1

@pytest.mark.parametrize('current, expected', [(13000, []), (10000, ['ReplaceWindow(13000)'])])
def test_closing_the_grid_returns_to_the_window_below(core, grid, opened, calls, monkeypatch, current, expected):
    core.kodi.xbmcgui.Window(10000).setProperty('a4k.ui.window', '13000')
    monkeypatch.setattr(core.kodi.xbmcgui, 'getCurrentWindowId', lambda: current)
    grid.show(PLUGIN + '?action=query&type=fan_picks&widget=1', 'Fan Favorites')
    assert calls == expected
    assert core.kodi.xbmcgui.Window(10000).getProperty('a4k.ui.window') == '13000'

# D. search, years, known for, more like this

def test_search_opens_the_search_window(core, grid, shown, monkeypatch):
    opened = []
    monkeypatch.setattr(importlib.import_module('a4kStreaming.ui.search'), 'open', lambda: opened.append(True))
    grid.search()
    assert opened == [True] and shown == []

def test_years_picks_a_decade_then_a_year_and_back_returns_to_the_decades(core, grid, shown, monkeypatch):
    sheets = importlib.import_module('a4kStreaming.ui.sheets')
    asked = []
    picks = [1, -1, 1, 0, -1]
    preselects = []
    def select(heading, items, preselect=-1):
        asked.append((heading, items))
        preselects.append(preselect)
        return picks.pop(0)
    monkeypatch.setattr(sheets, 'select', select)
    grid.years()
    assert preselects == [-1, -1, 1, -1]  # Back on the years focuses the decade picked before
    now = datetime.now().year
    decade = now - now % 10 - 10
    assert [heading for heading, _ in asked] == ['Discover by Year', '%s-%s' % (decade, decade + 9)] * 2
    assert asked[1][1][0] == str(decade + 9) and len(asked[1][1]) == 10
    assert shown == [(PLUGIN + '?action=query&type=year&widget=1&target_year=%s' % (decade + 9), str(decade + 9), 'Year')]
    grid.years()  # Back on the decades
    assert len(shown) == 1 and preselects[-1] == -1

def test_known_for_needs_no_imdb_login(core, grid, shown, notes):
    grid.known_for('nm1', 'Ana Torres')
    assert notes == []
    assert shown == [(PLUGIN + '?action=query&type=knownfor&widget=1&id=nm1', 'Ana Torres', 'Known for')]

def test_more_like_this_from_a_context_menu_opens_the_grid(core, home, grid, shown, calls, monkeypatch):
    items = [('Rate', 'RunPlugin(t)'), (home.MORE_LIKE_THIS, 'ActivateWindow(Videos,m,return)')]
    picks = [1, 0, -1]
    monkeypatch.setattr(importlib.import_module('a4kStreaming.ui.sheets'), 'select', lambda heading, labels: picks.pop(0))
    for _ in range(3):
        home.menu(items, 'tt1', 'Heat')
    assert shown == [(PLUGIN + '?action=query&type=more_like_this&widget=1&id=tt1', 'Heat', 'More like this')]
    assert calls == ['RunPlugin(t)']

def test_title_menu_is_a_sheet_and_hides_account_actions_when_signed_out(core, home, calls, monkeypatch):
    listing = importlib.import_module('a4kStreaming.listing')
    items = listing.title_context_menu(SimpleNamespace(url=PLUGIN, kodi=core.kodi), {
        'id': 'tt1', 'titleType': 'movie', 'primaryVideos': ['vi1'], 'userRating': None}, autoplay=False)
    shown = []
    monkeypatch.setattr(importlib.import_module('a4kStreaming.ui.sheets'), 'select',
                        lambda heading, labels: shown.append((heading, labels)) or labels.index(labels[0]))
    monkeypatch.setattr(core.kodi.xbmcgui.Dialog(), 'contextmenu', lambda labels: pytest.fail('stock context menu'))
    home.menu(items, 'tt1', 'Heat')
    account = ['Rate', 'Add to watchlist', 'Remove from watchlist', 'Add to IMDb list', 'Remove from IMDb list']
    assert shown[0] == ('Heat', ['More Like This'])  # picked: the grid opens, nothing runs
    login(core, monkeypatch)
    home.menu(items, 'tt1', 'Heat')
    assert shown[1][1] == [label for label, _ in items] == account + ['More Like This']
    assert calls == ['RunPlugin(%s?action=profile&type=rate&id=tt1)' % PLUGIN]

def test_detail_cast_opens_known_for_and_the_plot_opens_in_full(core, detail, grid, monkeypatch):
    fetched = importlib.import_module('tests.test_detail')
    monkeypatch.setattr(detail.home, 'spawn', Spawned())
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
    win.stopped = threading.Event()
    monkeypatch.setattr(home, 'HERO_FADE', 0)
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
    spawned = Spawned(run=False)
    monkeypatch.setattr(home, 'spawn', spawned)
    win = home.Home('a4k-home.xml', '', 'Default', '1080i')
    win.onInit()
    win.onInit()  # back from detail: the same rotation goes on
    assert [t.target for t in spawned] == [win.rotate] and not win.stopped.is_set() and win.error is None
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
        return len(polls) >= 8
    painted = []
    monkeypatch.setattr(win, 'show_hero', lambda items=None: painted.append(win.hero))
    win.stopped = SimpleNamespace(is_set=lambda: False, wait=wait)  # the window closes at the eighth wait
    win.rotate()
    turn = [home.HERO_TURN, home.HERO_FADE]  # each turn waits for the text's fade-out
    assert polls == [0.1, 0.1, 0.1] + turn * 2 + [home.HERO_TURN]
    assert painted == [0, 1, 2] and win.error is None

def test_turn_walks_the_first_six_and_wraps(core, home, labels, monkeypatch):
    win = shelf(core, home, labels, monkeypatch)
    win.show_hero()
    seen = [win.getProperty('a4k.hero.label')]
    for _ in range(home.HERO_COUNT):
        win.turn()
        seen.append(win.getProperty('a4k.hero.label'))
    assert seen == ['Movie %s' % i for i in range(6)] + ['Movie 0']
    assert win.getProperty('a4k.hero.fanart') == 'f0.jpg' and win.getProperty('a4k.hero.shown') == 'true'

def test_turn_fades_the_text_out_before_the_next_title(core, home, labels, monkeypatch):
    win = shelf(core, home, labels, monkeypatch)
    win.show_hero()
    seen = []
    def wait(seconds):
        seen.append((seconds, win.getProperty('a4k.hero.shown'), win.getProperty('a4k.hero.label'), win.hero))
        return closing
    win.stopped = SimpleNamespace(wait=wait)
    closing = False
    win.turn()
    assert seen == [(home.HERO_FADE, '', 'Movie 0', 0)] and win.hero == 1
    assert (win.getProperty('a4k.hero.shown'), win.getProperty('a4k.hero.label')) == ('true', 'Movie 1')
    closing = True  # the window closes during the fade: nothing more is set
    win.turn()
    assert win.hero == 1 and win.getProperty('a4k.hero.shown') == '' and win.getProperty('a4k.hero.label') == 'Movie 1'

@pytest.mark.parametrize('name, value', [('getCurrentWindowDialogId', 10138), ('getCurrentWindowId', 13001)])
def test_turn_keeps_the_title_when_a_window_opens_during_the_fade(core, home, labels, monkeypatch, name, value):
    win = shelf(core, home, labels, monkeypatch)
    win.show_hero()
    def wait(seconds):
        monkeypatch.setattr(core.kodi.xbmcgui, name, lambda: value)
        return False
    win.stopped = SimpleNamespace(wait=wait)
    win.turn()
    assert win.hero == 0
    assert (win.getProperty('a4k.hero.shown'), win.getProperty('a4k.hero.label')) == ('true', 'Movie 0')

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
    assert calls == ['PlayMedia(%s?action=play&type=&id=tt8,noresume)' % PLUGIN]

def test_new_hero_sources_clear_the_title_and_the_buttons_wait_for_the_next(core, home, labels, calls, monkeypatch):
    # the settings swapped the sources: the old title stayed drawn while its index named a title of the new rows
    win = shelf(core, home, labels, monkeypatch)
    labels.update({'Container(301).ListItemAbsolute(0).Property(a4k.type)': 'movie',
                   'Container(301).ListItemAbsolute(0).Property(a4k.id)': 'tt0',
                   'Container(302).NumItems': '1', 'Container(302).ListItemAbsolute(0).Label': 'Show 0',
                   'Container(302).ListItemAbsolute(0).Property(a4k.type)': 'movie',
                   'Container(302).ListItemAbsolute(0).Property(a4k.id)': 'tt9'})
    win.show_hero()
    spawned = Spawned(run=False)
    monkeypatch.setattr(home, 'spawn', spawned)
    monkeypatch.setattr(home, 'apply', lambda window: setattr(window, 'sources', ((302, 'NEW'),)))
    monkeypatch.setattr(win, 'wire', lambda: None)
    win.reapply()
    assert win.hero == -1 and win.getProperty('a4k.hero.shown') == ''
    win.onClick(home.HERO_PLAY)
    win.onClick(home.HERO_INFO)
    win.onAction(SimpleNamespace(getId=lambda: home.ACTION_CONTEXT_MENU))
    assert calls == [] and win.error is None
    def wait(seconds):  # a dialog opens during the restart's fade: nothing old comes back
        monkeypatch.setattr(core.kodi.xbmcgui, 'getCurrentWindowDialogId', lambda: 10138)
        return False
    monkeypatch.setattr(win.stopped, 'wait', wait)
    spawned[-1].fire()
    assert win.hero == -1 and win.getProperty('a4k.hero.shown') == ''
    monkeypatch.setattr(core.kodi.xbmcgui, 'getCurrentWindowDialogId', lambda: home.NO_DIALOG)
    monkeypatch.setattr(win.stopped, 'wait', lambda seconds: False)
    win.turn()  # the rotation's next look
    assert (win.getProperty('a4k.hero.shown'), win.getProperty('a4k.hero.label')) == ('true', 'Show 0')
    win.onClick(home.HERO_PLAY)
    assert calls == ['PlayMedia(%s?action=play&type=&id=tt9,noresume)' % PLUGIN]

def test_two_turns_never_run_at_once(core, home, labels, monkeypatch):
    # the restart after a settings change and the rotation: each reads and writes hero, so the shelf skipped a title
    win = shelf(core, home, labels, monkeypatch)
    inside, most = [0], [0]
    def wait(seconds):
        inside[0] += 1
        most[0] = max(most[0], inside[0])
        time.sleep(0.05)
        inside[0] -= 1
        return False
    win.stopped = SimpleNamespace(wait=wait)
    turns = [threading.Thread(target=win.turn) for _ in range(2)]
    for turn in turns:
        turn.start()
    for turn in turns:
        turn.join(2)
    assert most == [1] and win.hero == 2

# F. skin lint

def root():
    return ElementTree.parse(XML).getroot()

def test_panel_is_wrappable_and_keeps_focus_in(grid):
    window = root()
    panel = [c for c in window.iter('control') if c.get('id') == str(grid.PANEL)][0]
    assert panel.get('type') == 'panel' and window.findtext('defaultcontrol') == str(grid.PANEL)
    assert all(panel.findtext(edge) == 'noop' for edge in ('ondown', 'onleft', 'onright'))
    # Python fills it and handles OK: no <content> row (Kodi's own context menu), no onclick
    assert panel.find('content') is None and panel.find('onclick') is None
    # up reaches the category's year chips, which say noop at their own edges and go back down to the panel
    years = [c for c in window.iter('control') if c.get('id') == str(grid.YEARS)][0]
    assert panel.findtext('onup') == str(grid.YEARS) and years.findtext('ondown') == str(grid.PANEL)
    assert all(years.findtext(edge) == 'noop' for edge in ('onup', 'onleft', 'onright'))
    focusable = [c for c in window.iter('control') if c.get('type') in ('list', 'panel', 'button', 'wraplist', 'fixedlist')]
    assert focusable == [panel, years]

def test_every_property_the_xml_reads_is_set(core, grid, opened):
    grid.show(NEXT, 'Fan Favorites', 'Browse')
    read = set(re.findall(r'Window\.Property\(([\w.]+)\)', open(XML).read()))
    assert read and read - {'a4k.years'} <= set(opened[0].properties)  # a4k.years: onInit, for a category

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
