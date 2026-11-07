# -*- coding: utf-8 -*-
# Offline tests for the window interface: the skin lint, the root routing and its classic fallback, and the
# home window's click and menu mapping.

import os
import re
import struct
import importlib
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
    'a4k/fade_bottom.png': (8, 256),
    'a4k/mask_poster.png': (264, 396),
    'a4k/placeholder_poster.png': (264, 396),
    'a4k/ring.png': (128, 128),
    'a4k/rr20.png': (64, 64),
    'a4k/rr24.png': (64, 64),
    'a4k/scrim_bottom.png': (1, 512),
    'a4k/scrim_left.png': (256, 128),
    'a4k/shadow.png': (256, 256),
    'a4k/star.png': (64, 64),
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

def failed(core):
    return core.kodi.xbmcgui.Window(10000).getProperty('a4k.ui.failed')

# A. skin lint

def windows():
    return sorted(os.path.join(WINDOWS, name) for name in os.listdir(WINDOWS) if name.endswith('.xml'))

def png_size(path):
    with open(path, 'rb') as f:
        head = f.read(24)
    assert head[:8] == b'\x89PNG\r\n\x1a\n' and head[12:16] == b'IHDR', path
    return struct.unpack('>II', head[16:24])

def test_skin_has_the_home_window():
    assert [os.path.basename(path) for path in windows()] == ['a4k-home.xml']

@pytest.mark.parametrize('path', windows())
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

@pytest.mark.parametrize('path', windows())
def test_window_fonts_are_skin_fonts(path):
    fonts = {node.text for node in ElementTree.parse(path).iter('font')}
    assert fonts and fonts <= FONTS

@pytest.mark.parametrize('path', windows())
def test_window_uses_no_includes_or_named_colours(path):
    # a script window resolves both against the active skin, which may not have them
    root = ElementTree.parse(path).getroot()
    assert not list(root.iter('include'))
    colour_tags = {'textcolor', 'focusedcolor', 'disabledcolor', 'shadowcolor', 'selectedcolor', 'backgroundcolor'}
    colours = [node.text for node in root.iter() if node.tag in colour_tags]
    colours += [node.get('colordiffuse') for node in root.iter() if node.get('colordiffuse')]
    assert colours and all(re.fullmatch(r'[0-9A-F]{8}', colour) for colour in colours)

def test_rows_do_not_reload_on_play_or_stop():
    # Kodi reloads every unsorted <content> on each OnPlay/OnStop (DirectoryProvider::Announce). The reloads start new
    # Python interpreters next to the playing plugin call, and two starting at once crash Kodi 21 (seen live with the
    # trailer). programcount is 0 on every plugin item, and the sort is stable, so the listing order stays.
    root = ElementTree.parse(os.path.join(WINDOWS, 'a4k-home.xml')).getroot()
    rows = [node for node in root.iter('content') if (node.text or '').strip()]
    assert len(rows) == 3 and all(node.get('sortby') == 'programcount' for node in rows)

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
    focusable = [c for c in root.iter('control') if c.get('type') in ('list', 'panel') or c.get('id') == '210']
    assert len(focusable) == 5
    for control in focusable:
        assert {'onleft', 'onright', 'ondown'} <= {child.tag for child in control}
        targets = [control.findtext(tag) for tag in ('onup', 'ondown') if control.findtext(tag) not in (None, 'noop')]
        assert targets and set(targets) <= groups

def test_python_control_ids_exist_in_the_xml(home):
    root = ElementTree.parse(os.path.join(WINDOWS, 'a4k-home.xml')).getroot()
    ids = {int(control.get('id')) for control in root.iter('control') if control.get('id')}
    used = {100, home.HERO_PLAY, home.HERO_INFO} | set(home.ROWS)
    used.add(int(re.search(r'Container\((\d+)\)', home.HERO_ITEM).group(1)))
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
    assert set(re.findall(r'Window\.Property\(([\w.]+)\)', xml)) <= set(opened)
    assert opened['a4k.row.301'] == PLUGIN + '?action=query&type=popularMovies&widget=1'
    assert opened['a4k.row.303'] == PLUGIN + '?action=query&type=watchlist&widget=1'

def test_watchlist_row_needs_an_imdb_login(core, home, monkeypatch):
    settings(core, monkeypatch)
    opened = {}
    monkeypatch.setattr(home.Home, 'doModal', lambda self: opened.update(self.properties))
    home.open()
    assert 'a4k.row.303' not in opened and 'a4k.auth' not in opened
    assert opened['a4k.row.302'] == PLUGIN + '?action=query&type=popularTVShows&widget=1'

# B. root routing

def test_root_opens_the_windows_by_default(core, monkeypatch, calls):
    settings(core, monkeypatch)
    core.main(PLUGIN, 1, '')
    assert calls == [('end', False), 'RunScript(plugin.video.a4kstreaming)']

def test_root_in_classic_mode_is_the_listing(core, monkeypatch, calls):
    settings(core, monkeypatch, {'ui.mode': '1', 'views.menu': '4'})
    core.main(PLUGIN, 1, '')
    assert calls[:2] == [('items', 12), ('end', True)]
    assert not any('RunScript' in str(call) for call in calls)

def test_widget_root_stays_a_listing(core, monkeypatch, calls):
    settings(core, monkeypatch)
    core.main(PLUGIN, 1, 'widget=1')
    assert calls == [('items', 12), ('end', True)]

def test_root_outside_the_videos_window_stays_a_listing(core, monkeypatch, calls):
    # a skin widget or shortcut asking for the root without widget=1
    settings(core, monkeypatch, {'views.menu': '4'})
    monkeypatch.setattr(core.kodi.xbmcgui, 'getCurrentWindowId', lambda: 10000)
    core.main(PLUGIN, 1, '')
    assert calls[:2] == [('items', 12), ('end', True)]

def test_non_root_urls_never_ask_for_the_windows(core, app, monkeypatch, calls):
    settings(core, monkeypatch, {'views.menu': '4'})
    monkeypatch.setattr(app, 'enabled', lambda: pytest.fail('asked for the windows'))
    core.main(PLUGIN, 1, 'action=years&type=root')
    assert ('end', True) in calls

def test_missing_skin_file_falls_back_to_classic_and_logs_once(core, app, monkeypatch, calls, errors):
    settings(core, monkeypatch, {'views.menu': '4'})
    monkeypatch.setattr(app, 'SKIN_XML', os.path.join(WINDOWS, 'missing.xml'))
    core.main(PLUGIN, 1, '')
    core.main(PLUGIN, 1, '')
    assert [call for call in calls if call[0] in ('items', 'end')] == [('items', 12), ('end', True)] * 2
    assert failed(core) and len(errors) == 1 and 'missing.xml' in errors[0]

def test_a_failed_session_stays_classic(core, monkeypatch, calls):
    settings(core, monkeypatch, {'views.menu': '4'})
    core.kodi.xbmcgui.Window(10000).setProperty('a4k.ui.failed', 'true')
    core.main(PLUGIN, 1, '')
    assert calls[:2] == [('items', 12), ('end', True)]

# C. script entry and fallback

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

def test_window_error_falls_back_to_classic(core, app, home, monkeypatch, calls, errors):
    settings(core, monkeypatch)
    def broken(*args): raise RuntimeError('no such control')
    monkeypatch.setattr(home.Home, 'getControl', broken)
    app.run()
    classic = 'ActivateWindow(Videos,%s,return)' % PLUGIN
    assert calls == ['ReplaceWindow(13000)', classic]
    assert failed(core) and len(errors) == 1 and 'no such control' in errors[0]
    app.run()
    assert calls == ['ReplaceWindow(13000)', classic, classic] and len(errors) == 1

def test_open_error_falls_back_to_classic(core, app, home, monkeypatch, calls, errors):
    settings(core, monkeypatch)
    def broken(): raise RuntimeError('WindowXML failed')
    monkeypatch.setattr(home, 'open', broken)
    app.run()
    assert calls == ['ActivateWindow(Videos,%s,return)' % PLUGIN] and failed(core) and len(errors) == 1

def test_run_in_classic_mode_opens_the_listing(core, app, monkeypatch, calls):
    settings(core, monkeypatch, {'ui.mode': '1'})
    app.run()
    assert calls == ['ActivateWindow(Videos,%s,return)' % PLUGIN]

def test_run_returns_to_an_open_home_window(core, app, home, monkeypatch, calls):
    settings(core, monkeypatch)
    core.kodi.xbmcgui.Window(10000).setProperty('a4k.ui.window', '13001')
    core.kodi.xbmcgui.Window(13001).setProperty('a4k.home', 'true')
    monkeypatch.setattr(home, 'open', lambda: pytest.fail('opened a second home window'))
    app.run()
    assert calls == ['ReplaceWindow(13001)']

def test_prewarm_lists_the_public_rows(core, app, monkeypatch):
    rpc = []
    monkeypatch.setattr(core.kodi, 'json_rpc', lambda method, params, log_error=True: rpc.append((method, params['directory'])))
    settings(core, monkeypatch)
    app.prewarm()
    assert rpc == [('Files.GetDirectory', PLUGIN + '?action=query&type=%s&widget=1' % type) for type in ('popularMovies', 'popularTVShows')]
    settings(core, monkeypatch, {'ui.mode': '1'})
    app.prewarm()
    assert len(rpc) == 2

# D. clicks and menus

def info(type, id='tt1', path='', rated='false', trailers=''):
    return {'FolderPath': path, 'Property(a4k.type)': type, 'Property(a4k.id)': id,
            'Property(a4k.rated)': rated, 'Property(a4k.trailers)': trailers}

def test_click_on_a_movie_plays_it(home):
    path = PLUGIN + '?action=play&type=eyJ0aXRsZSI6ICJBIn0='
    assert home.click_builtin(info('movie', path=path)) == 'PlayMedia(%s)' % path
    assert home.click_builtin(info('movie')) == 'PlayMedia(%s?action=play&type=&id=tt1)' % PLUGIN
    assert home.click_builtin(info('tvEpisode', 'tt9')) == 'PlayMedia(%s?action=play&type=&id=tt9)' % PLUGIN

def test_click_on_a_series_opens_its_seasons(home):
    path = PLUGIN + '?action=query&type=seasons&id=tt2'
    assert home.click_builtin(info('tvSeries', 'tt2', path=path)) == 'ActivateWindow(Videos,%s,return)' % path
    assert home.click_builtin(info('tvSeries', 'tt2')) == 'ActivateWindow(Videos,%s,return)' % path

def test_click_on_the_next_item_opens_the_listing_and_people_do_nothing(home):
    path = PLUGIN + '?action=query&type=popularMovies&paginationToken=abc&page=2&cursor_time=1'
    assert home.click_builtin(info('', '', path=path)) == 'ActivateWindow(Videos,%s,return)' % path
    assert home.click_builtin(info('person', 'nm1', path=PLUGIN + '?action=query&type=browse&id=nm1')) is None
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

def test_select_on_a_row_runs_the_items_builtin(core, home, monkeypatch, calls):
    path = PLUGIN + '?action=query&type=seasons&id=tt5'
    win = window(core, home, monkeypatch, 302, {
        'Container(302).ListItem.Property(a4k.type)': 'tvSeries',
        'Container(302).ListItem.Property(a4k.id)': 'tt5',
        'Container(302).ListItem.FolderPath': path,
    })
    win.onAction(Action(home.ACTION_SELECT_ITEM))
    assert calls == ['ActivateWindow(Videos,%s,return)' % path] and win.error is None

def test_context_menu_on_rows_is_kodis_and_on_the_hero_is_ours(core, home, monkeypatch, calls):
    settings(core, monkeypatch)
    menus = []
    def contextmenu(labels):
        menus.append(labels)
        return labels.index('IMDb: Trailer')
    monkeypatch.setattr(core.kodi.xbmcgui.Dialog(), 'contextmenu', contextmenu)
    hero = {'Container(301).ListItemAbsolute(0).Property(a4k.%s)' % key: value
            for key, value in (('type', 'movie'), ('id', 'tt7'), ('trailers', 'vi7'), ('rated', 'false'))}
    win = window(core, home, monkeypatch, 301, hero)
    win.onAction(Action(home.ACTION_CONTEXT_MENU))
    assert menus == [] and calls == []
    win.setFocusId(home.HERO_PLAY)
    win.onAction(Action(home.ACTION_CONTEXT_MENU))
    assert menus and 'IMDb: Set rating' in menus[0]
    assert calls == ['RunPlugin(%s?action=trailer&id=tt7&vi=vi7&play=true)' % PLUGIN]

def test_hero_buttons(core, home, monkeypatch, calls):
    hero = {'Container(301).ListItemAbsolute(0).Property(a4k.type)': 'movie',
            'Container(301).ListItemAbsolute(0).Property(a4k.id)': 'tt7'}
    win = window(core, home, monkeypatch, home.HERO_PLAY, hero)
    win.onClick(home.HERO_PLAY)
    win.onClick(home.HERO_INFO)
    assert calls == ['PlayMedia(%s?action=play&type=&id=tt7)' % PLUGIN,
                     'ActivateWindow(Videos,%s?action=query&type=browse&id=tt7,return)' % PLUGIN]

def test_back_closes_and_errors_close_with_the_traceback(core, home, monkeypatch):
    closed = []
    monkeypatch.setattr(home.Home, 'close', lambda self: closed.append(True))
    win = window(core, home, monkeypatch, 301, {})
    win.onAction(Action(home.ACTION_NAV_BACK))
    assert closed == [True] and win.error is None
    monkeypatch.setattr(home, 'labels', lambda item: 1 / 0)
    win.onAction(Action(home.ACTION_SELECT_ITEM))
    assert closed == [True, True] and 'ZeroDivisionError' in win.error
