# -*- coding: utf-8 -*-
# Offline tests for the title detail window: the season grouping it shares with the directory, its view model from a
# recorded TitleFull (public English titles: a movie from query type=browse, a series from type=seasons), the window's
# fill, clicks and menu, the classic fallback, and its skin lint.

import os
import re
import json
import importlib
from xml.etree import ElementTree
from .common import pytest, api

WINDOWS = os.path.join(os.path.dirname(__file__), '..', 'resources', 'skins', 'Default', '1080i')
XML = os.path.join(WINDOWS, 'a4k-detail.xml')
PLUGIN = 'plugin://plugin.video.a4kstreaming/'
MOVIE, SERIES = 'tt3659388', 'tt11280740'

def fixture():
    with open(os.path.join(os.path.dirname(__file__), 'titlefull.json')) as f:
        return json.load(f)

@pytest.fixture(scope='module')
def core():
    core = api.A4kStreamingApi({'kodi': True}).core
    core.url = PLUGIN
    return core

@pytest.fixture
def detail(core):
    return importlib.import_module('a4kStreaming.ui.detail')

@pytest.fixture
def home(core):
    return importlib.import_module('a4kStreaming.ui.home')

@pytest.fixture
def listing(core):
    return vars(importlib.import_module('a4kStreaming.listing'))

@pytest.fixture(autouse=True)
def clean(core, monkeypatch):
    properties = importlib.import_module('a4kStreaming.lib.kodi_mock')._window_properties
    properties.clear()
    importlib.import_module('a4kStreaming.ui.detail')._cache.clear()
    monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: '')
    yield
    properties.clear()

@pytest.fixture
def calls(core, monkeypatch):
    log = []
    monkeypatch.setattr(core.kodi.xbmc, 'executebuiltin', lambda builtin, wait=False: log.append(builtin))
    return log

@pytest.fixture
def errors(detail, monkeypatch):
    log = []
    monkeypatch.setattr(detail.logger, 'error', log.append)
    return log

# A. season grouping: the directory and the window share it, and it yields exactly today's season URLs

def episode(id, season, number, date):
    return {'id': id, 'series': {'seasonNumber': season, 'episodeNumber': number},
            'releaseDate': dict(zip(('year', 'month', 'day'), date)) if date else None}

# out-of-order air dates, a season with no episode 1, an episode with no date, an episode 0, a day past month end
SYNTHETIC = [
    episode('tt01', 1, 1, (2020, 1, 31)), episode('tt02', 1, 2, (2020, 1, 24)), episode('tt03', 1, 3, (2020, 3, 5)),
    episode('tt04', 2, 2, (2021, 5, 1)), episode('tt05', 2, 1, (2021, 4, 30)), episode('tt06', 2, 3, (2021, 12, 20)),
    episode('tt07', 3, 2, (2022, 1, 1)),
    episode('tt08', 4, 1, (2023, 6, 10)), episode('tt09', 4, 2, None), episode('tt10', 4, 3, (2023, 6, 10)),
    episode('tt11', 5, 0, (2024, 2, 2)), episode('tt12', 5, 1, (2024, 2, 9)),
]

# recorded from __add_seasons before group_seasons was taken out of it
GOLDEN = {
    SERIES: [
        ('?action=query&type=episodes&id=tt11280740&season=1&year=2022&month=1&day=1&year_end=2022&month_end=4&day_end=8', 'Season 1 (2022) - 9 Episodes'),
        ('?action=query&type=episodes&id=tt11280740&season=2&year=2022&month=4&day=8&year_end=2025&month_end=3&day_end=21', 'Season 2 (2025) - 10 Episodes'),
    ],
    'tt0': [
        ('?action=query&type=episodes&id=tt0&season=1&year=2020&month=1&day=1&year_end=2020&month_end=3&day_end=5', 'Season 1 (2020) - 3 Episodes'),
        ('?action=query&type=episodes&id=tt0&season=2&year=2020&month=3&day=5&year_end=2021&month_end=12&day_end=20', 'Season 2 (2021) - 2 Episodes'),
        ('?action=query&type=episodes&id=tt0&season=4&year=2023&month=5&day=1&year_end=2023&month_end=6&day_end=10', 'Season 4 (2023) - 2 Episodes'),
        ('?action=query&type=episodes&id=tt0&season=5&year=2023&month=6&day=10&year_end=2024&month_end=3&day_end=2', 'Season 5 (2024) - 2 Episodes'),
    ],
}

def titles():
    return [fixture()['series'], {'id': 'tt0', 'primaryImage': None, 'episodes': {'episodes': json.loads(json.dumps(SYNTHETIC))}}]

@pytest.mark.parametrize('index', [0, 1])
def test_seasons_listing_keeps_todays_urls(core, listing, monkeypatch, index):
    title = titles()[index]
    added = []
    monkeypatch.setattr(core.kodi.xbmcplugin, 'addDirectoryItems', lambda handle, items, n: added.extend(items))
    listing['__add_seasons'](core, title)
    assert [(url, item.label) for url, item, _ in added] == [(PLUGIN + url, label) for url, label in GOLDEN[title['id']]]

@pytest.mark.parametrize('index', [0, 1])
def test_group_seasons_yields_the_listings_urls(core, listing, index):
    title = titles()[index]
    seasons = listing['group_seasons'](core, title['episodes']['episodes'])
    urls = [listing['season_url'](core, title['id'], key, season) for key, season in seasons.items()]
    assert urls == [PLUGIN + url for url, _ in GOLDEN[title['id']]]
    assert [season.episodes for season in seasons.values()] == [int(label.split(' - ')[1].split()[0]) for _, label in GOLDEN[title['id']]]

# B. view model from TitleFull

def test_movie_view_model(core, detail, listing):
    title = fixture()['movie']
    vm = detail.view_model(core, title)
    assert {k: vm[k] for k in ('id', 'type', 'kicker', 'title', 'rating', 'year', 'runtime', 'certificate')} == {
        'id': MOVIE, 'type': 'movie', 'kicker': 'MOVIE · ADVENTURE', 'title': 'The Martian', 'rating': '8.0',
        'year': '2015', 'runtime': '2h 24m', 'certificate': 'PG-13'}
    assert vm['plot'].startswith('An astronaut stranded on Mars')
    # the still frame, sized for the backdrop and for the glass
    assert vm['fanart'].endswith('_V1_UX1280_CR0,0,1280,720_AL_.jpg') and vm['blur'].endswith('_V1_UX64_CR0,0,64,36_AL_.jpg')
    assert vm['play'] == listing['play_url'](core, title) and vm['play'].startswith(PLUGIN + '?action=play&type=ey')
    assert vm['trailer'] == 'RunPlugin(%s?action=trailer&id=%s&vi=vi113423129&play=true)' % (PLUGIN, MOVIE)
    assert vm['watchlist'] == 'RunPlugin(%s?action=profile&type=watchlist_add&id=%s)' % (PLUGIN, MOVIE)
    assert vm['seasons'] == []
    # stars with their characters first, the rest of the cast, then the director and the writers, each person once
    people = [(p['name'], p['role']) for p in vm['cast']]
    assert people[:3] == [('Matt Damon', 'Mark Watney'), ('Jessica Chastain', 'Melissa Lewis'), ('Kristen Wiig', 'Annie Montrose')]
    assert people[-3:] == [('Ridley Scott', 'Director'), ('Drew Goddard', 'Writer'), ('Andy Weir', 'Writer')]
    assert len(people) == len({p['id'] for p in vm['cast']})
    assert all(p['face'] is None or p['face'].endswith('_CR0,0,200,200_AL_.jpg') for p in vm['cast'])

def test_series_view_model(core, detail):
    vm = detail.view_model(core, fixture()['series'])
    assert (vm['type'], vm['kicker'], vm['title'], vm['runtime'], vm['play']) == ('tvSeries', 'TV SERIES · DRAMA', 'Severance', '2 Seasons', '')
    # the pills are the listing's seasons (season 3 has only year dates, so neither lists it, and the count says what
    # can be opened, not IMDb's 3); the latest aired opens
    assert [(p['label'], p['url']) for p in vm['seasons']] == [
        ('Season %s' % (i + 1), PLUGIN + url + '&widget=1') for i, (url, _) in enumerate(GOLDEN[SERIES])]
    assert vm['season'] == 1
    assert vm['cast'][0]['name'] == 'Adam Scott' and vm['cast'][0]['role']

def test_view_model_leaves_the_cached_title_alone(core, detail):
    title = fixture()['series']
    assert detail.view_model(core, title) == detail.view_model(core, title)

def test_context_list_is_the_listings_menu(core, detail, listing):
    for title in fixture().values():
        assert detail.view_model(core, title)['menu'] == listing['title_context_menu'](core, title)

def card(type='movie', id=MOVIE, **extra):
    info = {'Property(a4k.type)': type, 'Property(a4k.id)': id, 'Property(a4k.trailers)': 'vi1_vi2',
            'Property(a4k.rated)': 'false', 'Label': 'The Martian', 'Plot': 'Plot.', 'Year': '2015', 'Rating': '8.0',
            'MPAA': 'PG-13', 'Genre': 'Adventure / Drama', 'Duration(secs)': '8640', 'Art(fanart)': 'f.jpg',
            'Art(blur)': 'b.jpg', 'FolderPath': PLUGIN + '?action=play&type=abc'}
    info.update(extra)
    return info

def test_card_paints_from_the_selected_card(core, detail):
    vm = detail.from_card(card())
    assert {k: vm[k] for k in ('kicker', 'title', 'year', 'rating', 'runtime', 'certificate', 'plot', 'fanart', 'blur', 'play')} == {
        'kicker': 'MOVIE · ADVENTURE', 'title': 'The Martian', 'year': '2015', 'rating': '8.0', 'runtime': '2h 24m',
        'certificate': 'PG-13', 'plot': 'Plot.', 'fanart': 'f.jpg', 'blur': 'b.jpg', 'play': PLUGIN + '?action=play&type=abc'}
    assert vm['trailer'] == 'RunPlugin(%s?action=trailer&id=%s&vi=vi1&play=true)' % (PLUGIN, MOVIE)
    series = detail.from_card(card('tvSeries', SERIES, **{'Property(a4k.trailers)': ''}))
    assert (series['play'], series['runtime'], series['trailer'], series['kicker']) == ('', '', '', 'TV SERIES · ADVENTURE')

def test_runtime_format(detail):
    assert [detail.runtime(s) for s in (None, 59, 2700, 3600, 8640)] == ['', '', '45m', '1h 0m', '2h 24m']

# C. fetch and cache

def test_title_is_fetched_once_and_kept(core, detail, monkeypatch):
    asked = []
    monkeypatch.setattr(core, 'query', lambda core, params: asked.append(dict(params)) or fixture()['series'])
    assert detail.fetch(core, SERIES, True)['id'] == SERIES
    assert detail.fetch(core, SERIES, True)['id'] == SERIES
    assert asked == [{'type': 'seasons', 'id': SERIES, 'silent': True, 'raw': True}]
    monkeypatch.setattr(detail.time, 'time', lambda: 10 ** 12)
    detail.fetch(core, SERIES, True)
    assert len(asked) == 2
    monkeypatch.setattr(core, 'query', lambda core, params: asked.append(dict(params)) or [])
    assert detail.fetch(core, MOVIE, False) is None and asked[-1]['type'] == 'browse'

def test_query_raw_returns_the_title(core, monkeypatch):
    # the request layer answers with the recorded title; raw skips the listing
    monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: '29' if key.endswith('page_size') else '')
    movie = fixture()['movie']
    monkeypatch.setattr(core.request, 'execute', lambda *a, **k: type('R', (), {'status_code': 200, 'content': json.dumps({'data': {'title': movie}}), 'text': ''})())
    monkeypatch.setattr(core.utils, 'sanitize_response', lambda data: movie)  # the fixture is already sanitised
    assert core.query(core, core.utils.DictAsObject({'type': 'browse', 'id': MOVIE, 'silent': True, 'raw': True}))['id'] == MOVIE

# D. the window

class Sync(object):
    # threading stand-in: threads and timers run at start()
    class Thread(object):
        def __init__(self, target, *args, **kwargs): self.target = target
        def start(self): self.target()
        def cancel(self): pass

    @staticmethod
    def Timer(seconds, target): return Sync.Thread(target)

@pytest.fixture
def opened(core, detail, monkeypatch):
    # open() runs the window the way Kodi would: onInit, then the worker; the window is kept for the test
    monkeypatch.setattr(detail, 'threading', Sync)
    monkeypatch.setattr(detail, 'fetch', lambda core, id, series: fixture()['series' if series else 'movie'])
    windows = []
    monkeypatch.setattr(detail.Detail, 'doModal', lambda self: windows.append(self) or self.onInit())
    return windows

def test_movie_window_paints_and_fills(core, detail, opened, calls):
    assert detail.open(card()) is True
    win = opened[0]
    assert win.error is None and win.getProperty('a4k.title') == 'The Martian' and win.getProperty('a4k.runtime') == '2h 24m'
    assert win.getProperty('a4k.series') == '' and win.getProperty('a4k.auth') == ''
    assert [i.label for i in win.getControl(detail.CAST).items][:2] == ['Matt Damon', 'Jessica Chastain']
    assert win.getControl(detail.SEASONS).items == [] and win.getProperty('a4k.episodes') == ''
    assert calls == []

def test_series_window_opens_the_latest_season_and_switches_on_dwell(core, detail, opened):
    detail.open(card('tvSeries', SERIES))
    win = opened[0]
    assert win.getProperty('a4k.series') == 'true'
    assert [i.label for i in win.getControl(detail.SEASONS).items] == ['Season 1', 'Season 2']
    assert win.getProperty('a4k.season') == 'Season 2' and win.getProperty('a4k.episodes') == PLUGIN + GOLDEN[SERIES][1][0] + '&widget=1'
    # the mock list reports position 0: a pill that keeps focus loads its season (the mock doModal has returned, so the
    # window counts as closed; reopen it)
    win.closed = False
    win.setFocusId(detail.SEASONS)
    win.onAction(Action(detail.ACTION_MOVE_LEFT))
    assert win.getProperty('a4k.season') == 'Season 1' and win.getProperty('a4k.episodes') == PLUGIN + GOLDEN[SERIES][0][0] + '&widget=1'

def test_on_init_again_does_not_refetch(core, detail, opened, monkeypatch):
    detail.open(card())
    monkeypatch.setattr(detail, 'fetch', lambda *a: pytest.fail('fetched again'))
    opened[0].onInit()

class Action(object):
    def __init__(self, id): self.id = id
    def getId(self): return self.id

def test_buttons_episodes_and_menu(core, detail, home, opened, calls, monkeypatch):
    detail.open(card('tvSeries', SERIES))
    win = opened[0]
    episode = PLUGIN + '?action=play&type=ep1'
    labels = {'Container(530).ListItem.Property(a4k.type)': 'tvEpisode', 'Container(530).ListItem.FolderPath': episode,
              'Container(530).ListItemAbsolute(0).FolderPath': episode}
    monkeypatch.setattr(core.kodi.xbmc, 'getInfoLabel', lambda label: labels.get(label, ''))
    win.setFocusId(detail.EPISODES)
    win.onAction(Action(home.ACTION_SELECT_ITEM))
    win.onClick(detail.PLAY)  # a series plays the open season's first episode
    win.onClick(detail.TRAILER)
    menus = []
    monkeypatch.setattr(core.kodi.xbmcgui.Dialog(), 'contextmenu', lambda items: menus.append(items) or items.index('IMDb: Add to list'))
    win.onClick(detail.MORE)
    win.setFocusId(detail.WATCHLIST)
    win.onAction(Action(home.ACTION_CONTEXT_MENU))
    add_to_list = 'RunPlugin(%s?action=profile&type=list_add&id=%s)' % (PLUGIN, SERIES)
    assert calls == ['PlayMedia(%s)' % episode, 'PlayMedia(%s)' % episode,
                     'RunPlugin(%s?action=trailer&id=%s&vi=vi3510815001&play=true)' % (PLUGIN, SERIES), add_to_list, add_to_list]
    assert menus[0] == [label for label, _ in win.vm['menu']] and win.error is None

def test_movie_play_uses_the_title_play_url(core, detail, listing, opened, calls):
    detail.open(card())
    opened[0].onClick(detail.PLAY)
    assert calls == ['PlayMedia(%s)' % listing['play_url'](core, fixture()['movie'])]

def test_back_closes(core, detail, opened, monkeypatch):
    detail.open(card())
    win = opened[0]
    win.onAction(Action(10))
    assert win.closed and win.error is None

def test_no_answer_keeps_the_card(core, detail, opened, monkeypatch):
    monkeypatch.setattr(detail, 'fetch', lambda *a: None)
    assert detail.open(card()) is True
    assert opened[0].getProperty('a4k.title') == 'The Martian' and opened[0].getControl(detail.CAST).items == []

# E. fallback: one log line, then the classic listing for the title for the rest of the session

@pytest.mark.parametrize('breakage', ['xml', 'worker'])
def test_window_error_falls_back_to_the_classic_listing(core, detail, home, opened, calls, errors, monkeypatch, breakage):
    if breakage == 'xml':
        def broken(self, id): raise RuntimeError('no such control')
        monkeypatch.setattr(detail.Detail, 'getControl', broken)
    else:
        monkeypatch.setattr(detail, 'view_model', lambda core, title: 1 / 0)
    home.select(card('tvSeries', SERIES))
    assert calls == ['ActivateWindow(Videos,%s?action=query&type=seasons&id=%s,return)' % (PLUGIN, SERIES)]
    assert len(errors) == 1 and core.kodi.xbmcgui.Window(10000).getProperty(detail.FAILED)
    home.select(card())
    assert calls[-1] == 'ActivateWindow(Videos,%s?action=query&type=browse&id=%s,return)' % (PLUGIN, MOVIE)
    assert len(opened) == 1 and len(errors) == 1

def test_missing_window_file_falls_back(core, detail, home, calls, errors, monkeypatch):
    def missing(*args): raise RuntimeError('a4k-detail.xml not found')
    monkeypatch.setattr(detail, 'Detail', missing)
    home.select(card())
    assert calls == ['ActivateWindow(Videos,%s?action=query&type=browse&id=%s,return)' % (PLUGIN, MOVIE)] and len(errors) == 1

def test_episodes_and_people_from_home_keep_their_classic_click(core, home, calls, monkeypatch):
    monkeypatch.setattr(importlib.import_module('a4kStreaming.ui.detail'), 'open', lambda info: pytest.fail('opened detail'))
    home.select(card('tvEpisode', 'tt9', FolderPath=''))
    home.select(card('person', 'nm1'))
    assert calls == ['PlayMedia(%s?action=play&type=&id=tt9)' % PLUGIN]

@pytest.mark.parametrize('focus, type, fetched', [
    (302, 'tvSeries', [(SERIES, True)]), (301, 'movie', [(SERIES, False)]), (302, 'tvEpisode', []), (201, 'movie', []),
    (202, 'movie', [(SERIES, False)]),
])
def test_home_prefetches_the_title_that_keeps_focus(core, home, detail, monkeypatch, focus, type, fetched):
    # a move starts the dwell timer; when it fires, the focused title's detail request runs (the window then opens full)
    monkeypatch.setattr(home, 'threading', Sync)
    item = 'Container(%s).ListItem' % focus if focus in home.ROWS else 'Container(301).ListItemAbsolute(0)'
    labels = {item + '.Property(a4k.type)': type, item + '.Property(a4k.id)': SERIES}
    monkeypatch.setattr(core.kodi.xbmc, 'getInfoLabel', lambda label: labels.get(label, ''))
    seen = []
    monkeypatch.setattr(detail, 'fetch', lambda core, id, series: seen.append((id, series)))
    win = home.Home('a4k-home.xml', '', 'Default', '1080i')
    win.setFocusId(focus)
    win.onAction(Action(home.ACTION_MOVES[0]))
    assert seen == fetched and win.error is None

def test_open_window_id_returns_to_home_after_detail(core, detail, opened):
    home_window = core.kodi.xbmcgui.Window(10000)
    home_window.setProperty('a4k.ui.window', '13000')
    detail.open(card())
    assert home_window.getProperty('a4k.ui.window') == '13000'

@pytest.mark.parametrize('current, expected', [(13000, []), (10000, ['ReplaceWindow(13000)'])])
def test_closing_detail_returns_to_the_home_window(core, detail, opened, calls, monkeypatch, current, expected):
    # 10000: the user went Home and reopened the add-on into the detail window; Back must not land on Kodi's Home
    core.kodi.xbmcgui.Window(10000).setProperty('a4k.ui.window', '13000')
    monkeypatch.setattr(core.kodi.xbmcgui, 'getCurrentWindowId', lambda: current)
    detail.open(card())
    assert calls == expected

# F. skin lint (the shared checks run over every window in test_ui.py)

def root():
    return ElementTree.parse(XML).getroot()

def test_python_control_ids_exist_and_kodi_can_wrap_them(detail):
    types = {int(c.get('id')): c.get('type') for c in root().iter('control') if c.get('id')}
    assert {i: types[i] for i in detail.BUTTONS} == {i: 'button' for i in detail.BUTTONS}
    assert [types[i] for i in (detail.SEASONS, detail.EPISODES, detail.CAST)] == ['list'] * 3
    containers = {int(n) for n in re.findall(r'Container\((\d+)\)', open(XML).read())}
    containers |= {int(n) for n in re.findall(r'ControlGroup\((\d+)\)', open(XML).read())}
    assert containers <= set(types)

def test_every_property_the_xml_reads_is_set(core, detail, opened):
    detail.open(card('tvSeries', SERIES))
    read = set(re.findall(r'Window\.Property\(([\w.]+)\)', open(XML).read()))
    assert read <= set(opened[0].properties)

def test_episodes_row_shows_on_its_url_alone():
    # the URL arrives after the window opened; a row hidden until it has items never loads them (Kodi skips updating a
    # hidden container), so the episodes shelf stayed empty on the rig
    group = [c for c in root().iter('control') if c.get('id') == '330'][0]
    assert group.findtext('visible') == '!String.IsEmpty(Window.Property(a4k.episodes))'

def test_focusable_controls_navigate_explicitly(detail):
    page = [c for c in root().iter('control') if c.get('id') == '100'][0]
    groups = {c.get('id') for c in page.findall('control')} | {str(detail.PLOT), '500'}  # the plot and the buttons link up and down
    focusable = [c for c in root().iter('control') if c.get('type') == 'list' or c.get('id') in ('500', str(detail.PLOT))]
    assert len(focusable) == 5
    for control in focusable:
        assert {'onup', 'ondown', 'onleft', 'onright'} <= {child.tag for child in control}
        targets = [control.findtext(tag) for tag in ('onup', 'ondown') if control.findtext(tag) != 'noop']
        assert targets and set(targets) <= groups
