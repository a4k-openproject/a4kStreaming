# -*- coding: utf-8 -*-
# Offline tests for the window interface: the skin lint, the root routing and the launch, the home window's
# click and menu mapping, and the play flow's sheets (select sheet and source search progress).

import gc
import os
import re
import struct
import threading
import time
import weakref
import importlib
from types import SimpleNamespace
from xml.etree import ElementTree
from .common import pytest, api

SKIN = os.path.join(os.path.dirname(__file__), '..', 'resources', 'skins', 'Default')
WINDOWS = os.path.join(SKIN, '1080i')
MEDIA = os.path.join(SKIN, 'media')
PLUGIN = 'plugin://plugin.video.a4kstreaming/'

# Estuary's Font.xml (identical in Kodi 20 and 21); any other name renders as font13
FONTS = {'font10', 'font12', 'font13', 'font14', 'font27', 'font32', 'font37', 'font45', 'font60',
         'font20_title', 'font25_title', 'font30_title', 'font32_title', 'font36_title', 'font40_title',
         'font45_title', 'font52_title'}

# every texture the windows ship, at the size scripts/make_textures.py draws it (9-slice borders depend on it)
TEXTURES = {
    'a4k/bg_home.png': (960, 540),
    'a4k/check.png': (64, 64),
    'a4k/chip.png': (120, 60),
    'a4k/chip_line.png': (120, 60),
    'a4k/fade_bottom.png': (8, 256),
    'a4k/icon_delete.png': (64, 64),
    'a4k/icon_gear.png': (64, 64),
    'a4k/icon_keyboard.png': (64, 64),
    'a4k/icon_space.png': (64, 64),
    'a4k/loader_base.png': (180, 180),
    'a4k/mask_ep.png': (400, 224),
    'a4k/mask_face.png': (176, 176),
    'a4k/mask_poster.png': (264, 396),
    'a4k/pill.png': (128, 64),
    'a4k/placeholder_ep.png': (400, 224),
    'a4k/placeholder_face.png': (176, 176),
    'a4k/placeholder_poster.png': (264, 396),
    'a4k/ring.png': (128, 128),
    'a4k/ring_face.png': (188, 188),
    'a4k/rr20.png': (64, 64),
    'a4k/rr20_line.png': (64, 64),
    'a4k/rr24.png': (64, 64),
    'a4k/rr4.png': (8, 8),
    'a4k/scrim_bottom.png': (1, 512),
    'a4k/scrim_left.png': (256, 128),
    'a4k/shadow.png': (256, 256),
    'a4k/sheet.png': (128, 128),
    'a4k/star.png': (64, 64),
    'a4k/tabbar.png': (256, 92),
    'a4k/white.png': (8, 8),
}

@pytest.fixture(scope='module')
def core():
    return api.A4kStreamingApi({'kodi': True}).core

@pytest.fixture
def app(core):
    return importlib.import_module('a4kStreaming.ui.app')

@pytest.fixture
def home(core):
    return importlib.import_module('a4kStreaming.ui.home')

@pytest.fixture(autouse=True)
def no_rotation(home, monkeypatch):
    # onInit starts the top shelf's rotation thread; test_grid.py drives rotate() and turn() itself
    monkeypatch.setattr(home.Home, 'rotate', lambda self: None)

@pytest.fixture(autouse=True)
def clean_windows(core):
    properties = importlib.import_module('a4kStreaming.lib.kodi_mock')._window_properties
    properties.clear()
    yield
    properties.clear()

def settings(core, monkeypatch, values=None):
    monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: (values or {}).get(key, ''))

@pytest.fixture
def calls(core, monkeypatch):
    # every builtin, directory item batch and endOfDirectory a plugin call makes, in order
    log = []
    monkeypatch.setattr(core.kodi.xbmc, 'executebuiltin', lambda builtin, wait=False: log.append(builtin))
    monkeypatch.setattr(core.kodi.xbmcplugin, 'addDirectoryItems', lambda handle, items, count=0: log.append(('items', len(items))))
    monkeypatch.setattr(core.kodi.xbmcplugin, 'endOfDirectory', lambda handle, succeeded=True, **kwargs: log.append(('end', succeeded)), raising=False)
    monkeypatch.setattr(core.kodi.xbmc, 'sleep', lambda ms: None)
    monkeypatch.setattr(core.db, 'cleanup', lambda: None)
    monkeypatch.setattr(core.request, 'revalidate', lambda core: None)
    return log

@pytest.fixture
def errors(app, monkeypatch):
    log = []
    monkeypatch.setattr(app.logger, 'error', log.append)
    return log

# A. skin lint

def windows():
    return sorted(os.path.join(WINDOWS, name) for name in os.listdir(WINDOWS) if name.endswith('.xml'))

def controlled():
    # every window but the launch cover, which has no ids, text or colours of its own
    return [path for path in windows() if not path.endswith('a4k-cover.xml')]

def png_size(path):
    with open(path, 'rb') as f:
        head = f.read(24)
    assert head[:8] == b'\x89PNG\r\n\x1a\n' and head[12:16] == b'IHDR', path
    return struct.unpack('>II', head[16:24])

def test_skin_has_the_windows_and_sheets():
    assert [os.path.basename(path) for path in windows()] == ['a4k-cover.xml', 'a4k-debrid.xml', 'a4k-detail.xml', 'a4k-grid.xml', 'a4k-home.xml', 'a4k-progress.xml', 'a4k-search.xml', 'a4k-settings.xml', 'a4k-sheet.xml', 'a4k-skip.xml']

@pytest.mark.parametrize('path', controlled())
def test_window_xml_parses_with_unique_control_ids(path):
    ids = [control.get('id') for control in ElementTree.parse(path).iter('control') if control.get('id')]
    assert ids and len(ids) == len(set(ids))

@pytest.mark.parametrize('path', windows())
def test_window_textures_exist_at_their_size(path):
    root = ElementTree.parse(path).getroot()
    used = set()
    for node in root.iter():
        for value in [node.text or ''] + list(node.attrib.values()):
            used.update(re.findall(r'a4k/[\w.]+\.png', value))
    assert used and used <= set(TEXTURES)
    for name in used:
        assert png_size(os.path.join(MEDIA, name)) == TEXTURES[name], name

def test_every_shipped_texture_is_listed():
    shipped = {'a4k/' + name for name in os.listdir(os.path.join(MEDIA, 'a4k'))}
    assert shipped == set(TEXTURES)

@pytest.mark.parametrize('path', controlled())
def test_window_fonts_are_skin_fonts(path):
    fonts = {node.text for node in ElementTree.parse(path).iter('font')}
    assert fonts and fonts <= FONTS

@pytest.mark.parametrize('path', controlled())
def test_window_uses_no_includes_or_named_colours(path):
    # a script window resolves both against the active skin, which may not have them
    root = ElementTree.parse(path).getroot()
    assert not list(root.iter('include'))
    colour_tags = {'textcolor', 'focusedcolor', 'disabledcolor', 'shadowcolor', 'selectedcolor', 'backgroundcolor'}
    colours = [node.text for node in root.iter() if node.tag in colour_tags]
    colours += [node.get('colordiffuse') for node in root.iter() if node.get('colordiffuse')]
    assert colours and all(re.fullmatch(r'[0-9A-F]{8}', colour) for colour in colours)

@pytest.mark.parametrize('name,count', [('a4k-home.xml', 10), ('a4k-detail.xml', 1), ('a4k-grid.xml', 1), ('a4k-search.xml', 1)])
def test_rows_do_not_reload_on_play_or_stop(name, count):
    # Kodi reloads every unsorted <content> on each OnPlay/OnStop (DirectoryProvider::Announce). The reloads start new
    # Python interpreters next to the playing plugin call, and two starting at once crash Kodi 21 (seen live with the
    # trailer). programcount is 0 on every plugin item, and the sort is stable, so the listing order stays.
    root = ElementTree.parse(os.path.join(WINDOWS, name)).getroot()
    rows = [node for node in root.iter('content') if (node.text or '').strip()]
    assert len(rows) == count and all(node.get('sortby') == 'programcount' for node in rows)

def test_every_call_gets_a_fresh_interpreter():
    # Kodi 21 crashes when reused interpreters start and end at once (xbmc/xbmc#27025, fixed only in 22): the home rows
    # reloading as a detail closes after a play crashed it in 6 of 9 tries on the TV box, and none in 10 with reuse off
    root = ElementTree.parse(os.path.join(os.path.dirname(__file__), '..', 'addon.xml')).getroot()
    assert [node.text for node in root.iter('reuselanguageinvoker')] == ['false']

def test_controls_place_themselves():
    # the active skin's Defaults.xml fills in any tag a control leaves out: under Confluence a textbox without left/top
    # landed at 330,333 and pushed the hero's meta line and plot out of view (seen live)
    for path in windows():
        root = ElementTree.parse(path).getroot()
        loose = [node.get('type') for node in root.iter('control') if node.find('left') is None or node.find('top') is None]
        assert loose == [], path

def test_focusable_controls_navigate_explicitly():
    # the page grouplist links only its groups, and a container with no edge action wraps around
    root = ElementTree.parse(os.path.join(WINDOWS, 'a4k-home.xml')).getroot()
    page = [c for c in root.iter('control') if c.get('id') == '100'][0]
    groups = {c.get('id') for c in page.findall('control')}
    hidden = {'291', '292'}  # the top shelf's own lists: never drawn, never in the navigation
    focusable = [c for c in root.iter('control') if (c.get('type') in ('list', 'panel') or c.get('id') == '210')
                 and c.get('id') not in hidden]
    assert len(focusable) == 10
    for control in focusable:
        assert {'onleft', 'onright', 'ondown'} <= {child.tag for child in control}
        targets = [control.findtext(tag) for tag in ('onup', 'ondown') if control.findtext(tag) not in (None, 'noop')]
        assert targets and set(targets) <= groups | {'161'}  # the top shelf's buttons go up to the top menu

def test_python_control_ids_exist_in_the_xml(home):
    root = ElementTree.parse(os.path.join(WINDOWS, 'a4k-home.xml')).getroot()
    ids = {int(control.get('id')) for control in root.iter('control') if control.get('id')}
    used = {100, home.HERO_PLAY, home.HERO_INFO, home.HERO_ROW, home.TILES, home.CONTINUE} | set(home.ROWS)
    assert used <= ids
    xml_containers = {int(n) for n in re.findall(r'Container\((\d+)\)', open(os.path.join(WINDOWS, 'a4k-home.xml')).read())}
    assert xml_containers <= ids

# control types Kodi's Python getControl can wrap (interfaces/legacy/Window.cpp); anything else raises
PYTHON_CONTROL_TYPES = {'button', 'label', 'fadelabel', 'textbox', 'image', 'list', 'wraplist', 'fixedlist', 'panel',
                        'progress', 'radiobutton', 'slider', 'edit', 'group', 'spincontrolex'}

def test_python_only_gets_controls_kodi_can_wrap(core, home, monkeypatch):
    root = ElementTree.parse(os.path.join(WINDOWS, 'a4k-home.xml')).getroot()
    types = {int(c.get('id')): c.get('type') for c in root.iter('control') if c.get('id')}
    asked = []
    original = home.Home.getControl
    monkeypatch.setattr(home.Home, 'getControl', lambda self, id: asked.append(id) or original(self, id))
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    window.onInit()
    assert asked and window.error is None
    assert all(types[id] in PYTHON_CONTROL_TYPES for id in asked)

def test_every_row_property_the_xml_reads_is_set(core, home, monkeypatch):
    settings(core, monkeypatch, {'imdb.at-main': 'token'})
    opened = {}
    monkeypatch.setattr(home.Home, 'doModal', lambda self: opened.update(self.properties))
    home.open()
    xml = open(os.path.join(WINDOWS, 'a4k-home.xml')).read()
    hero = {'a4k.hero.' + key for key in list(home.HERO_FIELDS) + ['shown', 'kicker', 'type']}  # set once a title is in
    read = set(re.findall(r'Window\.Property\(([\w.]+)\)', xml))
    assert read - hero - {home.FRESH} <= set(opened) and read & hero == hero  # a4k.fresh: after the settings
    assert opened['a4k.row.301'] == PLUGIN + '?action=query&type=popularMovies&widget=1'
    assert opened['a4k.row.303'] == PLUGIN + '?action=query&type=watchlist&widget=1'

def test_watchlist_row_needs_an_imdb_login(core, home, monkeypatch):
    settings(core, monkeypatch)
    opened = {}
    monkeypatch.setattr(home.Home, 'doModal', lambda self: opened.update(self.properties))
    home.open()
    assert opened['a4k.row.303'] == '' and opened['a4k.auth'] == ''
    assert opened['a4k.row.302'] == PLUGIN + '?action=query&type=popularTVShows&widget=1'

# B. root routing and launch

def test_only_the_videos_windows_root_opens_the_home_window(core, app, monkeypatch):
    assert app.from_videos('') and app.from_videos('?')
    assert not app.from_videos('?widget=1') and not app.from_videos('?action=query&type=popularMovies')
    monkeypatch.setattr(core.kodi.xbmcgui, 'getCurrentWindowId', lambda: 10000)  # a widget picker, a script
    assert not app.from_videos('')

def test_root_listing_is_the_widget_menu(core, monkeypatch, calls):
    settings(core, monkeypatch)
    core.main(PLUGIN, 1, '')
    core.main(PLUGIN, 1, 'widget=1')
    assert calls == [('items', 10), ('end', True)] * 2

def test_classic_routes_are_gone(core, monkeypatch, calls):
    settings(core, monkeypatch)
    notes = []
    monkeypatch.setattr(core.kodi, 'notification', lambda text, time=3000: notes.append(text))
    monkeypatch.setattr(core.utils, 'end_action', lambda core, failed: None)
    for route in ('action=years&type=root', 'action=search&type=input'):
        core.main(PLUGIN, 1, route)
    assert notes == ['Not supported yet'] * 2

@pytest.fixture
def cover(core, monkeypatch, calls):
    # the launch cover's show and close, in the order of the builtins and directory calls
    monkeypatch.setattr(core.kodi.xbmcgui.WindowXMLDialog, 'show', lambda self: calls.append('cover'))
    monkeypatch.setattr(core.kodi.xbmcgui.WindowXMLDialog, 'close', lambda self: calls.append('uncover'))

def test_launch_covers_ends_the_directory_then_opens_home_in_process(core, app, monkeypatch, calls, cover, errors):
    settings(core, monkeypatch)
    app.launch(7)
    # the cover is closing (no longer blocking) as the home window takes the Videos window's place; closed again after
    assert calls == ['cover', ('end', False), 'uncover', 'ReplaceWindow(13000)', 'uncover'] and errors == []
    assert not core.kodi.xbmcgui.Window(10000).getProperty('a4k.ui.window')

def test_launch_waits_for_kodis_busy_dialog(core, app, monkeypatch, calls, cover):
    settings(core, monkeypatch)
    busy = [True, True, False]
    monkeypatch.setattr(core.kodi.xbmc, 'getCondVisibility', lambda condition: busy.pop(0) if busy else False)
    app.launch(7)
    assert busy == [] and calls[:4] == ['cover', ('end', False), 'uncover', 'ReplaceWindow(13000)']

def test_launch_returns_to_an_open_home_window(core, app, home, monkeypatch, calls, cover):
    settings(core, monkeypatch)
    core.kodi.xbmcgui.Window(10000).setProperty('a4k.ui.window', '13001')
    core.kodi.xbmcgui.Window(13001).setProperty('a4k.home', 'true')
    monkeypatch.setattr(home, 'open', lambda cover=None: pytest.fail('opened a second home window'))
    app.launch(7)
    assert calls == ['cover', ('end', False), 'uncover', 'ReplaceWindow(13001)', 'uncover']

# C. script entry

def test_run_opens_home_and_clears_its_window_id(core, app, monkeypatch, calls, errors):
    settings(core, monkeypatch)
    seen = []
    monkeypatch.setattr(core.kodi.xbmcgui, 'getCurrentWindowId', lambda: 13001)
    original = importlib.import_module('a4kStreaming.ui.home').Home.onInit
    def on_init(self):
        original(self)
        seen.append(core.kodi.xbmcgui.Window(10000).getProperty('a4k.ui.window'))
    monkeypatch.setattr(importlib.import_module('a4kStreaming.ui.home').Home, 'onInit', on_init)
    app.run()
    # the window takes the Videos window's place in Kodi's history, so a listing opened from it returns to it
    assert seen == ['13001'] and calls == ['ReplaceWindow(13000)'] and errors == []
    assert not core.kodi.xbmcgui.Window(10000).getProperty('a4k.ui.window')

def test_window_error_is_logged(core, app, home, monkeypatch, calls, errors):
    settings(core, monkeypatch)
    def broken(*args): raise RuntimeError('no such control')
    monkeypatch.setattr(home.Home, 'getControl', broken)
    app.run()
    assert calls == ['ReplaceWindow(13000)'] and len(errors) == 1 and 'no such control' in errors[0]

def test_open_error_is_logged(core, app, home, monkeypatch, calls, errors):
    settings(core, monkeypatch)
    def broken(cover=None): raise RuntimeError('WindowXML failed')
    monkeypatch.setattr(home, 'open', broken)
    app.run()
    assert calls == [] and len(errors) == 1 and 'WindowXML failed' in errors[0]

def test_run_returns_to_an_open_home_window(core, app, home, monkeypatch, calls):
    settings(core, monkeypatch)
    core.kodi.xbmcgui.Window(10000).setProperty('a4k.ui.window', '13001')
    core.kodi.xbmcgui.Window(13001).setProperty('a4k.home', 'true')
    monkeypatch.setattr(home, 'open', lambda cover=None: pytest.fail('opened a second home window'))
    app.run()
    assert calls == ['ReplaceWindow(13001)']

def test_prewarm_lists_the_public_rows(core, app, monkeypatch):
    rpc = []
    monkeypatch.setattr(core.kodi, 'json_rpc', lambda method, params, log_error=True: rpc.append((method, params['directory'])))
    settings(core, monkeypatch)
    app.prewarm()
    assert rpc == [('Files.GetDirectory', PLUGIN + '?action=query&type=%s&widget=1' % type) for type in ('popularMovies', 'popularTVShows')]

# D. clicks and menus

def info(type, id='tt1', path='', rated='false', trailers=''):
    return {'FolderPath': path, 'Property(a4k.type)': type, 'Property(a4k.id)': id,
            'Property(a4k.rated)': rated, 'Property(a4k.trailers)': trailers}

def test_click_on_a_movie_plays_it(home):
    path = PLUGIN + '?action=play&type=eyJ0aXRsZSI6ICJBIn0='
    assert home.click_builtin(info('movie', path=path)) == 'PlayMedia(%s,noresume)' % path
    assert home.click_builtin(info('movie')) == 'PlayMedia(%s?action=play&type=&id=tt1,noresume)' % PLUGIN
    assert home.click_builtin(info('tvEpisode', 'tt9')) == 'PlayMedia(%s?action=play&type=&id=tt9,noresume)' % PLUGIN

def test_click_runs_nothing_but_plays(home):
    # series, people, lists and Next items are the windows' own steps, never a Videos listing
    assert home.click_builtin(info('tvSeries', 'tt2', path=PLUGIN + '?action=query&type=seasons&id=tt2')) is None
    path = PLUGIN + '?action=query&type=popularMovies&paginationToken=abc&page=2&cursor_time=1'
    assert home.click_builtin(info('', '', path=path)) is None
    assert home.click_builtin(info('person', 'nm1', path=PLUGIN + '?action=query&type=knownfor&id=nm1')) is None
    assert home.click_builtin(info('')) is None

def test_title_from_info_feeds_the_context_menu(core, home, monkeypatch):
    title = home.title_from_info(info('movie', rated='true', trailers='vi1_vi2'))
    assert title == {'id': 'tt1', 'titleType': 'movie', 'primaryVideos': ['vi1', 'vi2'], 'userRating': 1}
    assert home.title_from_info(info('tvSeries'))['primaryVideos'] is None

class Action(object):
    def __init__(self, id): self.id = id
    def getId(self): return self.id

def window(core, home, monkeypatch, focus, labels):
    monkeypatch.setattr(core.kodi.xbmc, 'getInfoLabel', lambda label: labels.get(label, ''))
    win = home.Home('a4k-home.xml', '', 'Default', '1080i')
    win.setFocusId(focus)
    return win

def test_select_on_a_title_opens_its_detail_and_other_items_run_their_builtin(core, home, monkeypatch, calls):
    opened = []
    monkeypatch.setattr(importlib.import_module('a4kStreaming.ui.detail'), 'open', lambda info: opened.append(info) or True)
    win = window(core, home, monkeypatch, 302, {
        'Container(302).ListItem.Property(a4k.type)': 'tvSeries',
        'Container(302).ListItem.Property(a4k.id)': 'tt5',
        'Container(302).ListItem.Label': 'A Show',
    })
    win.onAction(Action(home.ACTION_SELECT_ITEM))
    assert [(i['Property(a4k.id)'], i['Label']) for i in opened] == [('tt5', 'A Show')] and calls == [] and win.error is None
    path = PLUGIN + '?action=query&type=popularTVShows&paginationToken=abc&page=2'
    grids = []
    monkeypatch.setattr(importlib.import_module('a4kStreaming.ui.grid'), 'show', lambda path, title: grids.append((path, title)))
    win = window(core, home, monkeypatch, 302, {'Container(302).ListItem.FolderPath': path})
    win.setProperty('a4k.title.302', 'Trending TV Shows')
    win.onAction(Action(home.ACTION_SELECT_ITEM))  # the row's Next item: the rest of the row in the grid
    assert grids == [(path, 'Trending TV Shows')] and calls == [] and len(opened) == 1
    folder = PLUGIN + '?action=query&type=lists'
    win = window(core, home, monkeypatch, 302, {'Container(302).ListItem.FolderPath': folder})
    win.onAction(Action(home.ACTION_SELECT_ITEM))
    assert calls == [] and len(grids) == 1

def test_context_menu_on_rows_is_kodis_and_on_the_hero_is_ours(core, home, monkeypatch, calls):
    settings(core, monkeypatch, {'imdb.at-main': 'token'})
    menus = []
    def select(heading, labels):
        menus.append(labels)
        return labels.index('Rate')
    monkeypatch.setattr(importlib.import_module('a4kStreaming.ui.sheets'), 'select', select)
    hero = {'Container(301).ListItemAbsolute(0).Property(a4k.%s)' % key: value
            for key, value in (('type', 'movie'), ('id', 'tt7'), ('trailers', 'vi7'), ('rated', 'false'))}
    win = window(core, home, monkeypatch, 301, hero)
    win.onAction(Action(home.ACTION_CONTEXT_MENU))
    assert menus == [] and calls == []
    win.setFocusId(home.HERO_PLAY)
    win.onAction(Action(home.ACTION_CONTEXT_MENU))
    assert menus == [['Rate', 'Add to watchlist', 'Remove from watchlist', 'Add to IMDb list', 'Remove from IMDb list', 'More Like This']]
    assert calls == ['RunPlugin(%s?action=profile&type=rate&id=tt7)' % PLUGIN]

def test_hero_buttons(core, home, monkeypatch, calls):
    opened = []
    monkeypatch.setattr(importlib.import_module('a4kStreaming.ui.detail'), 'open', lambda info: opened.append(info) or True)
    hero = {'Container(301).ListItemAbsolute(0).Property(a4k.type)': 'movie',
            'Container(301).ListItemAbsolute(0).Property(a4k.id)': 'tt7'}
    win = window(core, home, monkeypatch, home.HERO_PLAY, hero)
    win.onClick(home.HERO_PLAY)
    win.onClick(home.HERO_INFO)
    assert calls == ['PlayMedia(%s?action=play&type=&id=tt7,noresume)' % PLUGIN]
    assert [i['Property(a4k.id)'] for i in opened] == ['tt7']

def test_back_walks_up_to_the_menu_then_closes_and_errors_close_with_the_traceback(core, home, monkeypatch):
    # a row goes to the top shelf's Play, the top shelf to Watch Now, the top menu closes the window
    closed = []
    monkeypatch.setattr(home.Home, 'close', lambda self: closed.append(True))
    win = window(core, home, monkeypatch, 301, {})
    win.onAction(Action(home.ACTION_NAV_BACK))
    assert win.getFocusId() == home.HERO_PLAY and closed == []
    win.onAction(Action(home.ACTION_NAV_BACK))
    assert win.getFocusId() == home.WATCH_NOW and closed == []
    win.onAction(Action(home.ACTION_NAV_BACK))
    assert closed == [True] and win.error is None
    monkeypatch.setattr(home, 'labels', lambda item: 1 / 0)
    win.setFocusId(301)
    win.onAction(Action(home.ACTION_SELECT_ITEM))
    assert closed == [True, True] and 'ZeroDivisionError' in win.error

# E. sheets: the select sheet and the source search progress card (the play loop's use is in test_unit.py)

@pytest.fixture
def sheets(core):
    return importlib.import_module('a4kStreaming.ui.sheets')

@pytest.fixture
def sheet_errors(sheets, monkeypatch):
    log = []
    monkeypatch.setattr(sheets.logger, 'error', log.append)
    return log

def __result(core, release_title, size, debrid=None):
    result = {'release_title': release_title, 'size': size, 'ref': core.utils.DictAsObject({'title': 'The Movie', 'year': 2020})}
    core.utils.cleanup_result(result)
    if debrid:
        result['debrid'] = debrid
    return result

@pytest.mark.parametrize('release_title, size, debrid, row', [
    ('The.Movie.2020.2160p.UHD.BluRay.x265.10bit.HDR.TrueHD.7.1.Atmos-GROUP', 58.3, 'PM',
     ('4K  HDR 10BIT  H265  TRUEHD 7.1', 'PM  ·  58.3 GB  ·  GROUP')),
    ('The Movie 2020 1080p WEB-DL DDP5.1 H.264-GROUP', 6.1, 'PM', ('1080P  H264  DD+ 5.1', 'PM  ·  6.1 GB  ·  P GROUP')),
    ('The.Movie.2020.HDCAM-GRP', 1.4, None, ('CAM', '1.4 GB  ·  HD GRP')),
])
def test_source_row_from_a_result(core, sheets, release_title, size, debrid, row):
    assert sheets.source_row(__result(core, release_title, size, debrid)) == row

class SheetList(object):
    def __init__(self): self.items, self.selected = [], -1
    def size(self): return len(self.items)
    def addItems(self, items): self.items.extend(items)
    def selectItem(self, index): self.selected = index
    def getSelectedPosition(self): return self.selected

def test_select_sheet_rows_preselect_and_click(core, sheets, monkeypatch, sheet_errors):
    settings(core, monkeypatch)
    shown = []
    monkeypatch.setattr(sheets.Sheet, 'getControl', lambda self, id: self.__dict__.setdefault('list', SheetList()))
    def doModal(self):
        shown.append(self)
        self.onInit()
        self.getControl(sheets.LIST).selectItem(2)
        self.onClick(sheets.LIST)
    monkeypatch.setattr(sheets.Sheet, 'doModal', doModal)
    labels = ['[COLOR white][B]New Search[/B][/COLOR]', '[LIGHT]4.2 GB  |  [B][COLOR white]720P[/COLOR][/B][/LIGHT]', 'Other']
    assert sheets.select('Choose', labels, preselect=1) == 2
    win = shown[0]
    assert win.getProperty('a4k.heading') == 'Choose' and win.getFocusId() == sheets.LIST
    # without rows the labels are the rows, minus colours (the focused row is white)
    assert [(i.label, i.label2) for i in win.getControl(sheets.LIST).items] == [
        ('[B]New Search[/B]', ''), ('[LIGHT]4.2 GB  |  [B]720P[/B][/LIGHT]', ''), ('Other', '')]
    assert sheet_errors == []

@pytest.mark.parametrize('preselect, selected', [(1, 1), (-1, -1), (5, -1)])
def test_select_sheet_preselect_in_range_only(core, sheets, monkeypatch, preselect, selected):
    settings(core, monkeypatch)
    seen = []
    monkeypatch.setattr(sheets.Sheet, 'getControl', lambda self, id: self.__dict__.setdefault('list', SheetList()))
    monkeypatch.setattr(sheets.Sheet, 'doModal', lambda self: self.onInit() or seen.append(self.getControl(sheets.LIST).selected))
    assert sheets.select('Choose', ['a', 'b'], preselect=preselect, rows=[('a', 'x'), ('b', 'y')]) == -1  # closed without a click
    assert seen == [selected]

def test_select_sheet_back_is_minus_one(core, sheets, monkeypatch):
    settings(core, monkeypatch)
    monkeypatch.setattr(sheets.Sheet, 'getControl', lambda self, id: self.__dict__.setdefault('list', SheetList()))
    def doModal(self):
        self.onInit()
        self.getControl(sheets.LIST).selectItem(1)
        self.onAction(Action(sheets.ACTION_NAV_BACK))
    monkeypatch.setattr(sheets.Sheet, 'doModal', doModal)
    assert sheets.select('Choose', ['a', 'b']) == -1

@pytest.mark.parametrize('breakage', ['constructor', 'oninit', 'click'])
def test_select_window_error_is_logged_and_cancels(core, sheets, monkeypatch, sheet_errors, breakage):
    settings(core, monkeypatch)
    if breakage == 'constructor':
        def missing(*args): raise RuntimeError('a4k-sheet.xml not found')
        monkeypatch.setattr(sheets, 'Sheet', missing)
    elif breakage == 'oninit':
        def broken(self, id): raise RuntimeError('Non-Existent Control 600')
        monkeypatch.setattr(sheets.Sheet, 'getControl', broken)
    else:
        monkeypatch.setattr(sheets.Sheet, 'getControl', lambda self, id: self.__dict__.setdefault('list', SheetList()))
        monkeypatch.setattr(sheets.Sheet, 'doModal', lambda self: self.onInit() or self.onClick(sheets.LIST) or None)
        monkeypatch.setattr(SheetList, 'getSelectedPosition', lambda self: 1 / 0)
    monkeypatch.setattr(core.kodi.xbmcgui, 'Dialog', lambda: pytest.fail('stock dialog opened'))
    assert sheets.select('Choose', ['a', 'b'], preselect=1) == -1
    assert len(sheet_errors) == 1

class StockProgress(object):
    # records the calls the source search makes on xbmcgui.DialogProgress
    def __init__(self): self.calls = []
    def create(self, heading, message=''): self.calls.append(('create', heading, message))
    def update(self, percent, message=''): self.calls.append(('update', percent, message))
    def iscanceled(self): return False
    def close(self): self.calls.append(('close',))

def test_progress_has_the_stock_dialogs_api(core, sheets):
    # the search calls create(heading, message), update(percent, message), iscanceled() and close(); same signatures
    import inspect
    for name in ('create', 'update', 'iscanceled', 'close'):
        ours = list(inspect.signature(getattr(sheets.Progress, name)).parameters.values())
        stock = list(inspect.signature(getattr(StockProgress, name)).parameters.values())
        assert [(p.name, p.default) for p in ours] == [(p.name, p.default) for p in stock], name

def test_progress_card_shows_the_message_lines_and_the_bar(core, sheets, monkeypatch, sheet_errors):
    shown, closed = [], []
    monkeypatch.setattr(sheets.ProgressWindow, 'show', lambda self: shown.append(self))
    monkeypatch.setattr(sheets.ProgressWindow, 'close', lambda self: closed.append(self))
    progress = sheets.Progress()
    progress.create('a4kStreaming', 'Results: 0\nDone: 0/2\nPending: 2  A | B')
    card = shown[0]
    assert [card.getProperty('a4k.line%s' % i) for i in (1, 2, 3)] == ['Results: 0', 'Done: 0/2', 'Pending: 2  A | B']
    assert card.getProperty('a4k.heading') == 'a4kStreaming' and card.getControl(sheets.BAR).percent == 0
    progress.update(40, 'Results: 3')
    assert [card.getProperty('a4k.line%s' % i) for i in (1, 2, 3)] == ['Results: 3', '', '']
    assert card.getControl(sheets.BAR).percent == 40 and not progress.iscanceled()
    card.onAction(Action(sheets.ACTION_PREVIOUS_MENU))
    assert progress.iscanceled() and closed == [card]
    progress.close()
    assert sheet_errors == []

def test_progress_window_error_is_logged_and_the_search_goes_on(core, sheets, monkeypatch, sheet_errors):
    closed = []
    monkeypatch.setattr(sheets.ProgressWindow, 'show', lambda self: None)
    monkeypatch.setattr(sheets.ProgressWindow, 'close', lambda self: closed.append(self))
    progress = sheets.Progress()
    progress.create('a4kStreaming', 'one')
    def broken(percent): raise RuntimeError('control gone')
    progress.bar.setPercent = broken
    progress.update(30, 'two')
    progress.update(60, 'three')
    progress.close()
    assert len(sheet_errors) == 1 and len(closed) == 1 and not progress.iscanceled()

def test_progress_is_the_card(core, sheets):
    assert isinstance(sheets.progress(), sheets.Progress)

# sheet skin lint (the shared checks run over every window above)

def __xml(name):
    return ElementTree.parse(os.path.join(WINDOWS, name)).getroot()

def test_sheet_python_ids_exist_with_types_kodi_can_wrap(sheets):
    for name, id, type in (('a4k-sheet.xml', sheets.LIST, 'list'), ('a4k-progress.xml', sheets.BAR, 'progress')):
        types = {int(c.get('id')): c.get('type') for c in __xml(name).iter('control') if c.get('id')}
        assert types == {id: type} and type in PYTHON_CONTROL_TYPES
        containers = {int(n) for n in re.findall(r'Container\((\d+)\)', open(os.path.join(WINDOWS, name)).read())}
        assert containers <= set(types)

def test_sheet_properties_the_xml_reads_are_set(core, sheets, monkeypatch):
    settings(core, monkeypatch)
    windows = []
    monkeypatch.setattr(sheets.Sheet, 'getControl', lambda self, id: self.__dict__.setdefault('list', SheetList()))
    monkeypatch.setattr(sheets.Sheet, 'doModal', lambda self: windows.append(self) or self.onInit())
    monkeypatch.setattr(sheets.ProgressWindow, 'show', lambda self: windows.append(self))
    sheets.select('Choose', ['a'])
    sheets.Progress().create('a4kStreaming', 'line')
    for name, window in zip(('a4k-sheet.xml', 'a4k-progress.xml'), windows):
        read = set(re.findall(r'Window\.Property\(([\w.]+)\)', open(os.path.join(WINDOWS, name)).read()))
        assert read and read <= set(window.properties), name

def test_sheet_list_takes_focus_and_does_not_leave_sideways():
    root = __xml('a4k-sheet.xml')
    # no defaultcontrol: the list is empty when the window inits; onInit fills and focuses it
    assert root.find('defaultcontrol') is None
    rows = [c for c in root.iter('control') if c.get('id') == '600'][0]
    # up and down wrap at the ends, as Kodi's own select does; left and right stay
    assert rows.findtext('onleft') == 'noop' and rows.findtext('onright') == 'noop'
    assert rows.find('onup') is None and rows.find('ondown') is None

# the windows' threads (ui/home.py spawn and release): Kodi 21 dies with SIGSEGV when a WindowXML is freed off its
# interpreter's main thread, so a window is never freed on one of its own threads

class Win(object):
    # a window as spawn and release see it
    threads = ()

    def __init__(self):
        self.stopped = threading.Event()

def test_release_stops_and_joins_the_window_threads(home):
    win, woke = Win(), []
    home.spawn(win, lambda: woke.append(win.stopped.wait(5)))
    home.spawn(win, lambda: woke.append(win.stopped.wait(5)))
    home.release(win)
    assert woke == [True, True] and not any(t.is_alive() for t in win.threads) and win not in home.LEFT_OVER

def test_a_thread_that_outlives_the_join_keeps_its_window(home, monkeypatch):
    monkeypatch.setattr(home, 'JOIN', 0.2)
    monkeypatch.setattr(home, 'LEFT_OVER', [])
    win, gate = Win(), threading.Event()
    home.spawn(win, gate.wait, 5)  # a request that does not end with the window
    started = time.time()
    home.release(win)
    assert home.LEFT_OVER == [win] and time.time() - started < 1
    gate.set()
    win.threads[0].join(1)

def test_a_close_waits_at_most_join_and_a_later_close_frees_the_left_over(home, monkeypatch):
    # the join runs inside the callback of the window below, which takes no keys meanwhile: a request still out does
    # not hold it, and the window it keeps goes, on this thread, at the first close after its thread ended
    monkeypatch.setattr(home, 'LEFT_OVER', [])
    win, gate = Win(), threading.Event()
    home.spawn(win, gate.wait, 30)
    started = time.time()
    home.release(win)
    assert time.time() - started < home.JOIN + 0.2 <= 1 and home.LEFT_OVER == [win]
    gate.set()
    win.threads[0].join(1)
    window = weakref.ref(win)
    del win
    home.release(Win())
    assert home.LEFT_OVER == [] and window() is None

def test_the_root_window_waits_the_long_bound_and_a_child_join(core, home, monkeypatch):
    # nothing waits for keys under the window a call opened first, and the interpreter ends right after its close: a
    # request still out there would run into the teardown
    joins = []
    monkeypatch.setattr(home, 'release', lambda window, join=home.JOIN: joins.append(join))
    monkeypatch.setattr(home.Home, 'doModal', lambda self: None)
    monkeypatch.setattr(home.Home, 'rotate', lambda self: None)
    home.open()
    home.modal(SimpleNamespace(doModal=lambda: None))
    assert joins == [home.ROOT_JOIN, home.JOIN] and home.ROOT_JOIN == home.TIMEOUT + 2 and home.JOIN <= 0.5
    monkeypatch.setattr(core.kodi.xbmcgui.WindowXML, 'doModal', lambda self: None)
    debrid = importlib.import_module('a4kStreaming.ui.debrid')
    debrid.open(root=True)
    debrid.open()
    assert joins[2:] == [home.ROOT_JOIN, home.JOIN]
    monkeypatch.undo()
    win, gate = Win(), threading.Event()
    home.spawn(win, gate.wait, 0.8)  # longer than JOIN, inside ROOT_JOIN
    home.release(win, home.ROOT_JOIN)
    assert not win.threads[0].is_alive() and win not in home.LEFT_OVER

def test_a_stopped_window_thread_makes_no_retry(core, home):
    # a window closed while its request was out: no second or third attempt (each up to TIMEOUT)
    request = importlib.import_module('a4kStreaming.lib.request')
    win, sent, answers = Win(), [], []
    def send(**kwargs):
        sent.append(kwargs['url'])
        win.stopped.set()  # the close, during the first attempt
        raise IOError('unreachable')
    session = SimpleNamespace(request=send)
    home.spawn(win, lambda: answers.append(getattr(request, '__send')(core, session, {'method': 'GET', 'url': 'https://example.com/'})))
    win.threads[0].join(5)
    assert sent == ['https://example.com/'] and answers[0].status_code == 500

def test_a_delayed_call_runs_once_unless_cancelled_or_its_window_stops(home):
    win, ran = Win(), []
    home.spawn(win, ran.append, 'stopped', delay=5)
    home.spawn(win, ran.append, 'cancelled', delay=0.05).set()
    home.spawn(win, ran.append, 'ran', delay=0.05)
    win.threads[2].join(1)
    started = time.time()
    home.release(win)  # the 5 s delay ends with the window, its call never made
    assert ran == ['ran'] and time.time() - started < 1
    home.spawn(win, ran.append, 'late')  # a stopped window starts nothing
    assert ran == ['ran'] and len(win.threads) == 3

def test_a_released_window_is_freed_at_its_del_with_no_cycle_left(home):
    # a stored threading.Timer kept window -> timer -> bound method -> window: del freed nothing, and the GC later freed
    # the window on whatever thread it ran on. With the GC off, the window must go at del, on this thread.
    gc.disable()
    try:
        win = home.Home('a4k-home.xml', '', 'Default', '1080i')
        win.stopped = threading.Event()
        win.dwell()
        win.dwell()  # a restarted dwell: the first one cancelled
        win.reapply()  # the FRESH reset and the top shelf's restart, both delayed
        home.spawn(win, win.rotate)
        home.release(win)
        window = weakref.ref(win)
        del win
        assert window() is None
    finally:
        gc.enable()

def test_modal_joins_a_thread_still_running_as_the_window_closes(core, home, monkeypatch):
    detail = importlib.import_module('a4kStreaming.ui.detail')
    gate, done = threading.Event(), []
    def fill(self):
        gate.wait(5)
        done.append(self.closed)
    def doModal(self):
        self.onInit()  # starts fill
        threading.Timer(0.1, gate.set).start()  # the fetch lands after the window closed
    monkeypatch.setattr(detail.Detail, 'fill', fill)
    monkeypatch.setattr(detail.Detail, 'doModal', doModal)
    detail.open(importlib.import_module('tests.test_detail').card())
    assert done == [True]

def test_after_play_ends_as_soon_as_the_window_stops(core, home, monkeypatch):
    monkeypatch.setattr(core.kodi.xbmc, 'getCondVisibility', lambda condition: True)  # the player stays
    stopped = threading.Event()
    stopped.set()
    started = time.time()
    assert home.after_play(stopped) is False and time.time() - started < 0.1
    stopped = threading.Event()
    threading.Timer(0.1, stopped.set).start()  # closed during the wait
    assert home.after_play(stopped) is False and time.time() - started < 0.5

def test_window_threads_start_only_through_spawn():
    ui = os.path.join(os.path.dirname(__file__), '..', 'a4kStreaming', 'ui')
    for name in ('home', 'detail', 'grid', 'search', 'debrid'):
        with open(os.path.join(ui, name + '.py')) as f:
            started = re.findall(r'\b(?:Thread|Timer)\(', f.read())
        assert started == (['Thread('] if name == 'home' else []), name  # the one in spawn

def test_a_window_thread_requests_with_the_short_timeout(core, home, monkeypatch):
    request = importlib.import_module('a4kStreaming.lib.request')
    timeouts = []
    monkeypatch.setattr(request, '__send', lambda core, session, sent: timeouts.append(sent['timeout']) or SimpleNamespace(status_code=404, content=''))
    call = lambda: request.execute(core, {'method': 'GET', 'url': 'https://example.com/'}, cache=False)
    call()
    win = Win()
    home.spawn(win, call)
    home.release(win)
    assert timeouts == [60, home.TIMEOUT]
