# -*- coding: utf-8 -*-
# Offline unit tests for pure helpers (no network).

import importlib
from .common import pytest, api

@pytest.fixture(scope='module')
def core():
    # lazy: importing core at collection time would break test_api's import-mocking checks
    return api.A4kStreamingApi({'kodi': True}).core

@pytest.fixture(scope='module')
def playback(core):
    return importlib.import_module('a4kStreaming.playback')

def __cleanup(core, release_title, ref=None, size=4.2, no_meta=False):
    if ref is None:
        ref = {'title': 'The Movie', 'year': 2020, 'country': ['United States']}
    result = {'release_title': release_title, 'size': size, 'ref': core.utils.DictAsObject(ref)}
    core.utils.cleanup_result(result, no_meta=no_meta)
    result.pop('ref')
    return result

@pytest.mark.parametrize('release_title,expected', [
    ('The.Movie.2020.2160p.UHD.BluRay.x265.10bit.HDR.TrueHD.7.1.Atmos-GROUP',
     {'videocodec': 'H265', 'hdr': 'HDR 10BIT', 'rip': 'UHD', 'audiocodec': 'TRUEHD 7.1', 'quality': '4K', 'release_title': 'GROUP'}),
    ('The Movie 2020 1080p WEB-DL DDP5.1 H.264-GROUP',
     {'videocodec': 'H264', 'hdr': '', 'rip': 'WEB-DL', 'audiocodec': 'DD+ 5.1', 'quality': '1080P', 'release_title': 'P GROUP'}),
    ('The.Movie.2020.720p.BluRay.x264.AAC.2.0-GRP',
     {'videocodec': 'H264', 'hdr': '', 'rip': 'BLURAY', 'audiocodec': 'AAC 2.0', 'quality': '720P', 'release_title': 'GRP'}),
    ('The.Movie.2020.1080p.WEB.x264.6CH-GRP',
     {'videocodec': 'H264', 'hdr': '', 'audiocodec': '5.1', 'quality': '1080P', 'release_title': 'GRP'}),
    ('The.Movie.2020.HDCAM.x264-GRP',
     {'videocodec': 'H264', 'hdr': '', 'rip': '', 'audiocodec': '', 'quality': 'CAM', 'release_title': 'HD GRP'}),
    ('The.Movie.2020.2160p.WEB-DL.DV.HDR10+.HEVC.DDP.5.1.mkv',
     {'videocodec': 'H265', 'hdr': 'DV', 'rip': 'WEB-DL', 'audiocodec': 'DD+ 5.1', 'quality': '4K', 'release_title': 'P', 'mkv': True}),
    ('The.Movie.2020.480p.DVDRip.XviD.MP3-GRP',
     {'videocodec': '', 'hdr': '', 'rip': 'DVD', 'audiocodec': 'MP3', 'quality': 'SD', 'release_title': 'GRP'}),
])
def test_cleanup_result_fields(core, release_title, expected):
    result = __cleanup(core, release_title)
    for key, value in expected.items():
        assert result[key] == value, key
    assert ('mkv' in result) == ('mkv' in expected)

def test_cleanup_result_title(core):
    result = __cleanup(core, 'The.Movie.2020.720p.BluRay.x264.AAC.2.0-GRP')
    assert result['title'] == '4.2 GB  |  [B][COLOR white]720P[/COLOR][/B]  |  H264  |  AAC 2.0  |  GRP'

    result = __cleanup(core, 'The.Movie.2020.HDCAM-GRP')
    assert result['title'] == '4.2 GB  |  [B][COLOR white]CAM[/COLOR][/B]  |  HD GRP'

def test_cleanup_result_no_meta(core):
    result = __cleanup(core, 'The.Movie.2020.1080p.WEBRip.x265-GRP', no_meta=True)
    assert result['quality'] == '1080P'
    assert result['title'] == '4.2 GB  |  GRP'

def test_cleanup_result_strips_season_and_show(core):
    ref = {'title': 'Pilot', 'tvshowtitle': 'Show Name', 'year': 2019, 'season': 1, 'country': 'United Kingdom'}
    result = __cleanup(core, 'Show.Name.S01.COMPLETE.SEASON.01.1080p.WEB.H264-GRP', ref=ref)
    assert result['release_title'] == 'S01 GRP'
    assert result['videocodec'] == 'H264'
    assert result['quality'] == '1080P'

def test_result_sort_key(playback):
    def r(name, quality='1080P', hdr='', videocodec='H264', size=1.0, audiocodec=''):
        return {'name': name, 'quality': quality, 'hdr': hdr, 'videocodec': videocodec, 'size': size, 'audiocodec': audiocodec, 'release_title': name}

    results = [
        r('cam', quality='CAM', size=50),
        r('sd', quality='SD'),
        r('1080_small', size=2),
        r('1080_big', size=10),
        r('1080_h265', videocodec='H265', size=1),
        r('1080_hdr', hdr='HDR', size=1),
        r('1080_dv', hdr='DV', size=1),
        r('4k', quality='4K', size=1),
        r('720', quality='720P', size=30),
        r('1080_big_atmos', size=10, audiocodec='ATMOS'),
        r('1080_big_truehd', size=10, audiocodec='TRUEHD'),
        r('1080_big_10bit', size=10, hdr=' 10BIT'),
    ]
    ordered = [x['name'] for x in sorted(results, key=playback.result_sort_key)]
    assert ordered == [
        '4k',
        '1080_dv',
        '1080_hdr',
        '1080_h265',
        '1080_big_10bit',
        '1080_big_truehd',
        '1080_big_atmos',
        '1080_big',
        '1080_small',
        '720',
        'sd',
        'cam',
    ]

def __episode_result(core, season, episode, package='single'):
    return {'ref': core.utils.DictAsObject({'season': season, 'episode': episode}), 'package': package}

def __filter(core, playback, result, names):
    files = [{'path': name} for name in names]
    return [f['path'] for f in playback.util_filter_episodes(core, result, files, 'path')]

def test_util_filter_episodes_matches_formats(core, playback):
    result = __episode_result(core, 1, 2, package='show')
    names = [
        'Show.S01E02.1080p.mkv',
        'Show.S01E03.1080p.mkv',
        'Show.s1e2.mkv',
        'Show.1x02.mkv',
        'Show 01x02.mkv',
        'Show.S01E01E02.mkv',
        'Show.S01E02E03.mkv',
        'Show.S01.E02.mkv',
        'Show.S02E02.mkv',
        'Show.S01E12.mkv',
        'Show.S01E002.mkv',
    ]
    assert __filter(core, playback, result, names) == [
        'Show.S01E02.1080p.mkv',
        'Show.s1e2.mkv',
        'Show.1x02.mkv',
        'Show 01x02.mkv',
        'Show.S01E01E02.mkv',
        'Show.S01E02E03.mkv',
        'Show.S01.E02.mkv',
        'Show.S01E002.mkv',
    ]

def test_util_filter_episodes_season_pack_without_season_tags(core, playback):
    names = ['Show.E01.mkv', 'Show.E02.mkv', 'Show.Episode.02.mkv', 'Show.E12.mkv']
    assert __filter(core, playback, __episode_result(core, 3, 2, package='season'), names) == ['Show.E02.mkv', 'Show.Episode.02.mkv']
    # non-season packages do not accept bare episode numbers
    assert __filter(core, playback, __episode_result(core, 3, 2, package='show'), names) == []

def test_util_filter_episodes_season_pack_with_season_tags(core, playback):
    names = ['Show.S03E01.mkv', 'Show.S03E02.mkv', 'Show.E02.mkv']
    assert __filter(core, playback, __episode_result(core, 3, 2, package='season'), names) == ['Show.S03E02.mkv']

def test_sanitize_response(core):
    response = {
        'data': {
            'title': {
                'id': 'tt0000001',
                'titleType': {'id': 'tvMiniSeries'},
                'titleText': {'text': 'Some Title'},
                'genres': {'genres': [{'text': 'Drama'}, {'text': 'Comedy'}]},
                'credits': {
                    'edges': [{'node': {'name': {'id': 'nm1', 'nameText': {'text': 'A Person'}}}}],
                    'pageInfo': {'hasNextPage': False, 'endCursor': 'x'},
                },
                'episodes': {'edges': [{'node': {'id': 'tt2'}}, {'node': {'id': 'tt3'}}]},
            }
        }
    }
    assert core.utils.sanitize_response(response) == {
        'id': 'tt0000001',
        'titleType': 'tvSeries',
        'titleText': 'Some Title',
        'genres': ['Drama', 'Comedy'],
        'credits': {
            'edges': [{'id': 'nm1', 'nameText': 'A Person'}],
            'pageInfo': {'hasNextPage': False, 'endCursor': 'x'},
        },
        'episodes': ['tt2', 'tt3'],  # single-key dicts collapse to their value
    }

def test_sanitize_response_scalars_and_lists(core):
    sanitize = core.utils.sanitize_response
    assert sanitize(None) is None
    assert sanitize('x') == 'x'
    assert sanitize([{'text': 'a'}, {'node': {'text': 'b'}}]) == ['a', 'b']
    assert sanitize({'titleType': {'id': 'movie'}, 'id': 'tt1'}) == {'titleType': 'movie', 'id': 'tt1'}

def test_get_image_params(core):
    get_image_params = core.utils.get_image_params
    assert get_image_params({}, 480, 270) == 'UX480_'
    assert get_image_params({'width': 1920, 'height': 1080}, 480, 270) == 'UX480_CR0,0,480,270_AL_'
    assert get_image_params({'width': 2000, 'height': 3000}, 528, 781) == 'UX528_CR0,0,528,781_AL_'
    assert get_image_params({'width': 1920, 'height': 1080}, 528, 781) == 'UY781_CR430,0,528,781_AL_'
    assert get_image_params({'width': 1000, 'height': 1500}, 480, 270) == 'UX480_CR0,0,480,270_AL_'

def test_fix_image_size(core):
    image = {'url': 'https://m.media-amazon.com/images/M/abc._V1_.jpg', 'width': 2000, 'height': 3000}
    assert core.utils.fix_poster_size(image) == 'https://m.media-amazon.com/images/M/abc._V1_UX520_CR0,0,520,780_AL_.jpg'
    assert core.utils.fix_thumb_size(None) is None
    assert core.utils.fix_fanart_size({'url': None}) is None

class __PlayHarness(object):
    def __init__(self, core, monkeypatch, files_by_link, choices, autoplay=False, dead_links=(), mode='1', quick=None, uncached=None,
                 from_cache=False):
        self.dialogs = []
        self.items = []
        self.probed = []
        self.notifications = []
        self.resolved = []
        self.searches = []
        choices = list(choices)
        utils = core.utils

        title = {'mediatype': 'movie', 'imdbnumber': 'tt0000001', 'title': 'The Movie', 'duration': 100}
        results = {}
        for i, (name, quality) in enumerate([('A', '4K'), ('B', '1080P'), ('C', '720P')]):
            results['PM%s' % name] = {
                'quality': quality, 'hdr': '', 'videocodec': 'H264', 'audiocodec': '', 'size': 10.0,
                'release_title': name, 'title': name, core.utils.result_link_key: name, 'debrid': 'PM', 'package': 'single',
                'ref': utils.DictAsObject(title),
            }
        self.params = utils.DictAsObject({'type': core.base64.b64encode(core.json.dumps(title).encode()).decode('ascii')})

        settings = {
            'premiumize.apikey': 'key', 'general.max_quality': '3', 'general.max_movie_size': '200',
            'general.dolby_vision_allowed': 'false', 'general.autoplay': 'true' if autoplay else 'false',
            'ui.mode': mode,  # classic by default: the stock dialogs, exactly as before the sheets
        }
        monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: settings.get(key, ''))
        monkeypatch.setattr(core, 'provider_meta', lambda core: utils.DictAsObject({'name': 'test'}))
        monkeypatch.setattr(core.cache, 'get_general', lambda: utils.DictAsObject({}))
        # the search's shape: every row under its hash, the cached ones again under PM<hash>
        raw = dict((key[2:], result) for key, result in results.items())
        raw.update(uncached or {})

        def provider(core, params):
            # quick: the quick sources' cached rows, answered until the full search is asked for
            self.searches.append(utils.DictAsObject(dict(params)))
            if quick is not None and not params.full:
                return utils.DictAsObject({'results': quick, 'cached': dict(('PM%s' % key, row) for key, row in quick.items()), 'quick': True})
            return utils.DictAsObject({'results': raw, 'cached': results, 'from_cache': from_cache and not params.refresh})
        monkeypatch.setattr(core, 'provider', provider)
        monkeypatch.setattr(core.cache, 'get_last_selected_result', lambda: {})
        for name in ['save_general', 'save_last_selected_result']:
            monkeypatch.setattr(core.cache, name, lambda data: None)
        monkeypatch.setattr(core.kodi, 'notification', lambda text, time=3000: self.notifications.append(text))

        def select(heading, items, preselect=None, **kwargs):
            self.dialogs.append((heading, preselect))
            self.items.append(items)
            return choices.pop(0)
        dialog = lambda: None
        dialog.select = select
        monkeypatch.setattr(core.kodi.xbmcgui, 'Dialog', lambda: dialog)

        def probe(url, timeout=5):
            self.probed.append(url)
            return url not in dead_links
        monkeypatch.setattr(core.request, 'probe', probe)

        def execute(core, request, cache=True):
            response = lambda: None
            self.resolved.append(request['data']['src'])
            response.content = core.json.dumps({'content': files_by_link.get(request['data']['src'], [])})
            return response
        monkeypatch.setattr(core.request, 'execute', execute)

        self.run = lambda: core.play(core, self.params)

def __video(name):
    return {'path': '%s.mkv' % name, 'size': 2 * 1024 ** 3, 'link': 'http://%s' % name}

def test_play_resolve_failure_returns_to_selection(core, monkeypatch):
    h = __PlayHarness(core, monkeypatch, {'B': [__video('b')]}, choices=[0, 1])
    assert h.run() == 'http://b'
    assert h.dialogs == [('Choose source', 0), ('Choose source', 1)]  # back on the sheet at the next source
    assert h.resolved == ['A', 'B']
    assert h.notifications == ['Failed to resolve debrid']

def test_play_autoplay_falls_through_to_next_source(core, monkeypatch):
    h = __PlayHarness(core, monkeypatch, {'C': [__video('c')]}, choices=[], autoplay=True)
    assert h.run() == 'http://c'
    assert h.dialogs == []
    assert h.resolved == ['A', 'B', 'C']

def test_play_autoplay_all_fail_opens_selection(core, monkeypatch):
    h = __PlayHarness(core, monkeypatch, {}, choices=[-1], autoplay=True)
    assert h.run() is None
    assert h.resolved == ['A', 'B', 'C']
    assert h.dialogs == [('Choose source', 0)]  # past the last source: the first
    assert h.notifications == ['Failed to resolve debrid']

def test_play_file_picker_cancel_returns_to_selection(core, monkeypatch):
    files = {'A': [__video('a1'), __video('a2')], 'B': [__video('b')]}
    h = __PlayHarness(core, monkeypatch, files, choices=[0, -1, 1])
    assert h.run() == 'http://b'
    assert h.dialogs == [('Choose source', 0), ('Choose file', None), ('Choose source', 1)]

def test_play_autoplay_file_picker_cancel_opens_selection(core, monkeypatch):
    files = {'A': [__video('a1'), __video('a2')]}
    h = __PlayHarness(core, monkeypatch, files, choices=[-1, -1], autoplay=True)
    assert h.run() is None
    assert h.dialogs == [('Choose file', None), ('Choose source', 1)]

# the play loop in windows mode: the select sheet, with the stock select as its fallback

@pytest.fixture
def sheets(core):
    sheets = importlib.import_module('a4kStreaming.ui.sheets')
    core.kodi.xbmcgui.Window(10000).clearProperty(sheets.FAILED)
    yield sheets
    core.kodi.xbmcgui.Window(10000).clearProperty(sheets.FAILED)

class SheetList(object):
    # the sheet's list control: remembers the selected row
    def __init__(self): self.items, self.selected = [], -1
    def size(self): return len(self.items)
    def addItems(self, items): self.items.extend(items)
    def selectItem(self, index): self.selected = index
    def getSelectedPosition(self): return self.selected

class KeyAction(object):
    def __init__(self, id): self.id = id
    def getId(self): return self.id

def __sheet_user(sheets, monkeypatch, picks):
    # each doModal shows the sheet, records what it shows, then the user clicks the row in picks (None = Back)
    shown = []
    monkeypatch.setattr(sheets.Sheet, 'getControl', lambda self, id: self.__dict__.setdefault('list', SheetList()))
    def doModal(self):
        self.onInit()
        rows = [(i.label, i.label2) for i in self.getControl(sheets.LIST).items]
        shown.append((self.getProperty('a4k.heading'), rows, self.getControl(sheets.LIST).selected, self.getFocusId()))
        pick = picks.pop(0)
        if pick is None:
            return self.onAction(KeyAction(92))
        self.getControl(sheets.LIST).selectItem(pick)
        self.onClick(sheets.LIST)
    monkeypatch.setattr(sheets.Sheet, 'doModal', doModal)
    return shown

def test_play_in_windows_mode_picks_from_the_sheet(core, monkeypatch, sheets):
    shown = __sheet_user(sheets, monkeypatch, [0, 1])
    h = __PlayHarness(core, monkeypatch, {'B': [__video('b')]}, choices=[], mode='0')
    assert h.run() == 'http://b'
    assert h.dialogs == []  # the stock select never opened
    rows = [('4K  H264', 'PM  ·  10.0 GB  ·  A'), ('1080P  H264', 'PM  ·  10.0 GB  ·  B'), ('720P  H264', 'PM  ·  10.0 GB  ·  C'),
            ('Pick file manually: Off', 'Select a source, then choose which file inside it to stream')]
    # A fails to resolve: back to the sheet, the same rows, the next source preselected
    assert shown == [('Choose source', rows, 0, sheets.LIST), ('Choose source', rows, 1, sheets.LIST)]
    assert h.resolved == ['A', 'B'] and h.notifications == ['Failed to resolve debrid']

def test_play_sheet_back_cancels(core, monkeypatch, sheets):
    __sheet_user(sheets, monkeypatch, [None])
    h = __PlayHarness(core, monkeypatch, {}, choices=[], mode='0')
    assert h.run() is None and h.resolved == []

def test_play_sheet_error_falls_back_to_the_stock_select_and_logs_once(core, monkeypatch, sheets):
    errors = []
    monkeypatch.setattr(sheets.logger, 'error', errors.append)
    def missing(*args): raise RuntimeError('a4k-sheet.xml not found')
    monkeypatch.setattr(sheets, 'Sheet', missing)
    h = __PlayHarness(core, monkeypatch, {'B': [__video('b')]}, choices=[0, 1], mode='0')
    assert h.run() == 'http://b'
    assert h.dialogs == [('Choose source', 0), ('Choose source', 1)]
    assert len(errors) == 1 and core.kodi.xbmcgui.Window(10000).getProperty(sheets.FAILED)

def test_play_autoplay_in_windows_mode_shows_no_sheet(core, monkeypatch, sheets):
    monkeypatch.setattr(sheets, 'Sheet', lambda *args: pytest.fail('sheet opened'))
    h = __PlayHarness(core, monkeypatch, {'C': [__video('c')]}, choices=[], autoplay=True, mode='0')
    assert h.run() == 'http://c' and h.dialogs == []

def test_graphql_query_next_day_rolls_over_month(core, monkeypatch):
    class LastDayOfMonth(core.utils.date):
        @classmethod
        def today(cls):
            return cls(2021, 1, 31)
    monkeypatch.setattr(core.utils, 'date', LastDayOfMonth)

    request = core.utils.get_graphql_query({'query': 'query fn { title { ...TitleFull\n } }'})
    query = core.json.loads(request['data'])['query']
    assert 'releasedOnOrAfter: { day: 1, month: 2, year: 2021 }' in query

def test_search_without_importable_sources(core, monkeypatch):
    monkeypatch.setattr(core.cache, 'get_provider', lambda: {'MISSING_SOURCE': True})
    params = core.utils.DictAsObject({'type': 'search', 'title': {}, 'start_time': core.utils.time_ms()})
    search = core.provider(core, params)
    assert search.results == {}
    assert search.cached == {}

class __FakeProvider(object):
    def __init__(self, results, wait=False):
        self.results = results
        self.cancelled = False
        self.release = __import__('threading').Event()
        if not wait:
            self.release.set()

    def movie(self, title, year, imdb, apikeys=None):
        self.release.wait(5)
        return [dict(r) for r in self.results]

    def cancel_operations(self):
        self.cancelled = True
        self.release.set()

def __raw(name, hash, package='single', size=2048):
    return {'release_title': name, 'hash': hash, 'package': package, 'size': size}

class __SearchHarness(object):
    def __init__(self, core, monkeypatch, providers, settings=None, pm_cached=None, canceled=False, pm_content=None, cache=None, mode='1',
                 quick=(), switched_off=()):
        self.requests = []
        self.threads = []
        self.cache = {} if cache is None else cache
        monkeypatch.setattr(core.cache, 'get_last_results', lambda: core.json.loads(core.json.dumps(self.cache)))
        monkeypatch.setattr(core.cache, 'save_last_results', lambda data: (self.cache.clear(), self.cache.update(core.json.loads(core.json.dumps(data)))))
        self.progress = []
        self.saved = []
        utils = core.utils
        all_settings = {'premiumize.apikey': 'key', 'ui.mode': mode}
        all_settings.update(settings or {})
        monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: all_settings.get(key, ''))
        monkeypatch.setattr(core.cache, 'get_provider', lambda: {key: key not in switched_off for key in providers})
        modules = {key.lower(): utils.DictAsObject({'sources': (lambda s: lambda: s)(s)}) for key, s in providers.items()}
        if quick:
            # the provider package itself (providers.<name>.en): its quick sources
            modules['en'] = utils.DictAsObject({'get_quick': lambda: [key.lower() for key in quick]})
        monkeypatch.setattr(core, 'importlib', utils.DictAsObject({'import_module': lambda name: modules[name.rsplit('.', 1)[1]]}))

        def execute(core, request, cache=True):
            self.requests.append(request)
            self.threads.append(core.threading.current_thread())
            response = lambda: None
            hashes = request.get('data', {}).get('items[]', [])
            status = [h in (pm_cached or []) for h in hashes]
            response.content = core.json.dumps({'status': 'success', 'response': status, 'filesize': [0] * len(hashes)})
            if pm_content is not None:
                response.content = pm_content(hashes) if callable(pm_content) else pm_content
            response.status_code = 200
            return response
        monkeypatch.setattr(core.request, 'execute', execute)

        progress = lambda: None
        progress.create = lambda *args: self.progress.append(('create',) + args)
        progress.update = lambda *args: self.progress.append(('update',) + args)
        progress.close = lambda: self.progress.append(('close',))
        progress.iscanceled = lambda: canceled
        monkeypatch.setattr(core.kodi.xbmcgui, 'DialogProgress', lambda: progress)

        title = {'mediatype': 'movie', 'imdbnumber': 'tt0000001', 'title': 'The Movie', 'year': 2020}
        self.params = lambda **extra: utils.DictAsObject(dict({'type': 'search', 'title': utils.DictAsObject(title), 'start_time': utils.time_ms()}, **extra))
        self.run = lambda **extra: core.provider(core, self.params(**extra))

def test_search_does_not_wait_a_second_before_searching(core, monkeypatch):
    h = __SearchHarness(core, monkeypatch, {'FAST': __FakeProvider([__raw('The.Movie.2020.1080p.WEB.x264-GRP', 'aa')])}, pm_cached=['aa'])
    start = core.time.time()
    search = h.run()
    assert core.time.time() - start < 0.5
    assert list(search.cached.keys()) == ['PMaa']
    assert not any(p[0] == 'create' for p in h.progress)  # fast searches never flash the dialog

def test_search_cancel_stops_pending_providers(core, monkeypatch):
    slow = __FakeProvider([__raw('The.Movie.2020.720p.WEB.x264-GRP', 'bb')], wait=True)
    fast = __FakeProvider([__raw('The.Movie.2020.1080p.WEB.x264-GRP', 'aa')])
    h = __SearchHarness(core, monkeypatch, {'SLOW': slow, 'FAST': fast}, pm_cached=['aa', 'bb'], canceled=True)
    start = core.time.time()
    h.run(start_time=core.utils.time_ms() - 2000)  # dialog is up at once, user pressed cancel
    assert core.time.time() - start < 1
    assert slow.cancelled
    assert not fast.cancelled

def test_search_returns_partial_results_at_the_time_limit(core, monkeypatch):
    slow = __FakeProvider([__raw('The.Movie.2020.720p.WEB.x264-GRP', 'bb')], wait=True)
    slow.cancel_operations = lambda: setattr(slow, 'cancelled', True)  # a provider that ignores cancel
    fast = __FakeProvider([__raw('The.Movie.2020.1080p.WEB.x264-GRP', 'aa')])
    h = __SearchHarness(core, monkeypatch, {'SLOW': slow, 'FAST': fast}, settings={'general.search_timeout': '1'}, pm_cached=['aa', 'bb'])
    start = core.time.time()
    search = h.run()
    assert core.time.time() - start < 2
    assert list(search.cached.keys()) == ['PMaa']
    assert slow.cancelled

    slow.release.set()  # the straggler finishes later and must not leak into the returned results
    core.time.sleep(0.2)
    assert list(search.cached.keys()) == ['PMaa']

def test_search_progress_lists_done_and_pending_providers(core, monkeypatch):
    slow = __FakeProvider([], wait=True)
    fast = __FakeProvider([__raw('The.Movie.2020.1080p.WEB.x264-GRP', 'aa'), __raw('The.Movie.2020.720p.WEB.x264-GRP', 'bb')])
    h = __SearchHarness(core, monkeypatch, {'SLOW': slow, 'FAST': fast}, settings={'general.search_timeout': '1'}, pm_cached=['aa'])
    h.run(start_time=core.utils.time_ms() - 2000)
    updates = [p[2] for p in h.progress if p[0] == 'update']
    assert any('FAST  [B]2[/B]' in u and 'Pending:[/COLOR]  [B]1[/B]  SLOW' in u for u in updates)
    assert 'Time  left' in updates[0]

# the source search in windows mode: the progress card instead of the stock dialog

def __cards(sheets, monkeypatch, back=False):
    cards = []
    def show(self):
        cards.append(self)
        if back:
            self.onAction(KeyAction(92))
    monkeypatch.setattr(sheets.ProgressWindow, 'show', show)
    monkeypatch.setattr(sheets.ProgressWindow, 'close', lambda self: setattr(self, 'closed', True))
    return cards

def test_search_in_windows_mode_shows_the_progress_card(core, monkeypatch, sheets):
    cards = __cards(sheets, monkeypatch)
    slow = __FakeProvider([], wait=True)
    fast = __FakeProvider([__raw('The.Movie.2020.1080p.WEB.x264-GRP', 'aa'), __raw('The.Movie.2020.720p.WEB.x264-GRP', 'bb')])
    h = __SearchHarness(core, monkeypatch, {'SLOW': slow, 'FAST': fast}, settings={'general.search_timeout': '1'}, pm_cached=['aa'], mode='0')
    search = h.run(start_time=core.utils.time_ms() - 2000)
    assert list(search.cached.keys()) == ['PMaa']
    assert h.progress == []  # the stock dialog never opened
    card = cards[0]
    assert len(cards) == 1 and card.closed
    assert card.getProperty('a4k.heading') == core.kodi.addon_name
    assert 'Time  left' in card.getProperty('a4k.line1')
    assert 'FAST  [B]2[/B]' in card.getProperty('a4k.line2') and 'SLOW' in card.getProperty('a4k.line3')
    assert 0 < card.getControl(sheets.BAR).percent <= 100

def test_search_in_windows_mode_shows_no_card_for_a_fast_search(core, monkeypatch, sheets):
    cards = __cards(sheets, monkeypatch)
    h = __SearchHarness(core, monkeypatch, {'FAST': __FakeProvider([__raw('The.Movie.2020.1080p.WEB.x264-GRP', 'aa')])}, pm_cached=['aa'], mode='0')
    assert list(h.run().cached.keys()) == ['PMaa']
    assert cards == [] and h.progress == []

def test_search_card_back_cancels_and_keeps_the_results(core, monkeypatch, sheets):
    cards = __cards(sheets, monkeypatch, back=True)
    slow = __FakeProvider([__raw('The.Movie.2020.720p.WEB.x264-GRP', 'bb')], wait=True)
    fast = __FakeProvider([__raw('The.Movie.2020.1080p.WEB.x264-GRP', 'aa')])
    h = __SearchHarness(core, monkeypatch, {'SLOW': slow, 'FAST': fast}, pm_cached=['aa', 'bb'], mode='0')
    start = core.time.time()
    # the card comes up once fast has answered, the user presses Back
    search = h.run(start_time=core.utils.time_ms() - 900)
    assert core.time.time() - start < 1
    assert slow.cancelled and not fast.cancelled and cards[0].canceled and cards[0].closed
    assert list(search.cached.keys()) == ['PMaa']

def test_request_reuses_one_session_per_thread(core, monkeypatch):
    request_module = importlib.import_module('a4kStreaming.lib.request')
    created = []

    class FakeSession(object):
        def __init__(self):
            created.append(self)
            self.cookies = request_module.requests.cookies.RequestsCookieJar()
        def mount(self, prefix, adapter): pass
        def request(self, **kwargs):
            response = lambda: None
            response.status_code = 404
            return response
    monkeypatch.setattr(request_module.requests, 'Session', FakeSession)
    monkeypatch.setattr(request_module, '__local', __import__('threading').local())

    call = lambda: request_module.execute(core, {'method': 'GET', 'url': 'https://example.com/'}, cache=False)
    call()
    call()
    assert len(created) == 1
    thread = core.threading.Thread(target=call)
    thread.start()
    thread.join()
    assert len(created) == 2

def test_request_session_keeps_no_response_cookies(core, monkeypatch):
    import email.message
    import urllib.request
    request_module = importlib.import_module('a4kStreaming.lib.request')
    monkeypatch.setattr(request_module, '__local', __import__('threading').local())
    headers = email.message.Message()
    headers['Set-Cookie'] = 'session-id=abc; Path=/'
    response = lambda: None
    response.info = lambda: headers
    jar = request_module.get_session().cookies
    jar.extract_cookies(response, urllib.request.Request('https://example.com/'))
    assert len(jar) == 0

def test_search_checks_premiumize_once_for_all_hashes(core, monkeypatch):
    one = __FakeProvider([__raw('The.Movie.2020.1080p.WEB.x264-GRP', 'AA'), __raw('The.Movie.2020.720p.WEB.x264-GRP', 'bb')])
    two = __FakeProvider([__raw('The.Movie.2020.1080p.WEB.x264-GRP', 'aa'), __raw('The.Movie.2020.2160p.WEB.x265-GRP', '"cc"')])
    h = __SearchHarness(core, monkeypatch, {'ONE': one, 'TWO': two}, settings={'premiumize.apikey': 'a&b#c'}, pm_cached=['aa', 'cc'])
    search = h.run()
    assert len(h.requests) == 1
    assert h.threads == [core.threading.current_thread()]  # the check reuses the calling thread's session
    request = h.requests[0]
    assert request['url'] == 'https://www.premiumize.me/api/cache/check?apikey=a%26b%23c'
    assert sorted(request['data']['items[]']) == ['aa', 'bb', 'cc']
    body = __import__('requests').Request('POST', request['url'], data={'items[]': ['aa', 'bb']}).prepare().body
    assert body == 'items%5B%5D=aa&items%5B%5D=bb'
    assert sorted(search.cached.keys()) == ['PMaa', 'PMcc']
    assert sorted(search.results.keys()) == ['aa', 'bb', 'cc']
    assert search.cached['PMcc']['title_with_debrid'].startswith('PM  |  ')

@pytest.mark.parametrize('pm_content,cached', [
    (lambda hashes: '{"status": "success", "response": [true]}', ['PMaa']),  # short answer: padded with false
    (lambda hashes: '{"status": "success", "response": [false, false, false, true]}', []),  # long answer: truncated
    ('{"status": "error", "message": "Not logged in"}', []),
    ('not json', []),
])
def test_search_premiumize_answer_is_aligned_and_failure_is_uncached(core, monkeypatch, pm_content, cached):
    provider = __FakeProvider([__raw('The.Movie.2020.1080p.WEB.x264-GRP', h) for h in ['aa', 'bb', 'cc']])
    h = __SearchHarness(core, monkeypatch, {'ONE': provider}, pm_content=pm_content)
    search = h.run()
    assert sorted(search.cached.keys()) == cached
    assert sorted(search.results.keys()) == ['aa', 'bb', 'cc']  # every row stays on the uncached side

class __QuickSource(object):
    # a quick source: debrid-tagged rows only when a debrid key is passed, as the provider package documents
    def __init__(self, rows, delay=0, fail=False):
        self.rows, self.delay, self.fail, self.calls = rows, delay, fail, []

    def movie(self, title, year, imdb, apikeys=None):
        self.calls.append(apikeys)
        if self.fail:
            raise RuntimeError('source down')
        __import__('time').sleep(self.delay)
        return [dict(r, debrid='PM', url='https://example.com/resolve/premiumize/test-key/%s/0' % r['hash']) for r in self.rows] if apikeys else []

    def cancel_operations(self):
        pass

@pytest.mark.parametrize('case,source,settings,extra,switched_off,quick', [
    ('cached rows win the race', {}, {}, {}, (), True),
    ('the timer fires first', {'delay': 0.5}, {}, {}, (), False),
    ('the quick search errors', {'fail': True}, {}, {}, (), False),
    ('nothing cached', {'rows': []}, {}, {}, (), False),
    ('full search by default', {}, {'general.search_all_providers': 'true'}, {}, (), None),
    ('no debrid key', {}, {'premiumize.apikey': ''}, {}, (), None),
    ('switched off in Manage', {}, {}, {}, ('QUICK',), None),
    ('full search asked for', {}, {}, {'full': True}, (), None),
    ('search again (refresh)', {}, {}, {'refresh': True}, (), None),  # every provider, never the quick ones
])
def test_search_quick_sources_first_and_when_the_full_search_takes_over(core, monkeypatch, case, source, settings, extra, switched_off, quick):
    # quick: True = the quick rows, False = tried and fell back, None = never tried
    monkeypatch.setattr(importlib.import_module('a4kStreaming.provider'), 'quick_wait', 0.2)
    fast = __QuickSource(**dict({'rows': [__raw('The.Movie.2020.1080p.WEB.x264-GRP', 'aa')]}, **source))
    full = __FakeProvider([__raw('The.Movie.2020.2160p.WEB.x265-GRP', 'bb')])
    h = __SearchHarness(core, monkeypatch, {'QUICK': fast, 'FULL': full}, settings=settings, pm_cached=['bb'], quick=['QUICK'], switched_off=switched_off)
    search = h.run(**extra)

    quick_calls = [apikeys for apikeys in fast.calls if apikeys]
    assert quick_calls == ([] if quick is None else [{'pm': 'key'}])
    assert bool(search.quick) is bool(quick)
    if quick:
        assert list(search.cached.keys()) == ['PMaa'] and h.requests == []  # already cached: no cache check
        row = search.cached['PMaa']
        assert 'url' not in row and row[core.utils.result_link_key].endswith(':?xt=urn:btih:aa')  # played by hash, not by the key-bearing link
    else:
        assert ('PMbb' in search.cached) == bool(settings.get('premiumize.apikey', 'key'))  # the full search's own split
        assert 'PMaa' not in search.cached  # and no late quick answer in it

def test_search_ignores_a_leftover_alldebrid_key(core, monkeypatch):
    provider = __FakeProvider([__raw('The.Movie.2020.1080p.WEB.x264-GRP', h) for h in ['aa', 'bb']])
    h = __SearchHarness(core, monkeypatch, {'ONE': provider}, settings={'premiumize.apikey': '', 'alldebrid.apikey': 'k'})
    search = h.run()
    assert h.requests == [] and search.cached == {}

def test_play_search_again_on_a_remembered_list_searches_everything_afresh(core, monkeypatch):
    h = __PlayHarness(core, monkeypatch, {}, choices=[4, -1], from_cache=True)
    assert h.run() is None
    assert h.items[0][-1] == '[COLOR white][B]Search again[/B][/COLOR]'  # after the file pick toggle
    assert [(bool(p.full), bool(p.refresh)) for p in h.searches] == [(False, False), (True, True)]

def test_play_a_fresh_full_list_has_no_search_again(core, monkeypatch):
    h = __PlayHarness(core, monkeypatch, {}, choices=[-1])
    h.run()
    assert len(h.items[0]) == 4 and 'Search again' not in h.items[0][-1]

def test_play_file_pick_toggle_flips_in_place_and_lists_one_file(core, monkeypatch):
    # the toggle row keeps the focus and flips its label; then a source holding one file lists it instead of playing
    h = __PlayHarness(core, monkeypatch, {'A': [__video('a')]}, choices=[3, 0, 0])
    assert h.run() == 'http://a'
    assert [items[3] for items in h.items[:2]] == ['[COLOR white][B]Pick file manually: Off[/B][/COLOR]',
                                                  '[COLOR white][B]Pick file manually: On[/B][/COLOR]']
    assert h.dialogs == [('Choose source', 0), ('Choose source', 3), ('Choose file', None)]

def test_search_caches_raw_results_and_redoes_debrid_split(core, monkeypatch):
    cache = {}
    provider = __FakeProvider([__raw('The.Movie.2020.1080p.WEB.x264-GRP', h) for h in ['aa', 'bb']])
    calls = []
    movie = provider.movie
    provider.movie = lambda *args, **kwargs: calls.append(1) or movie(*args, **kwargs)
    pm_cached = ['aa']
    h = __SearchHarness(core, monkeypatch, {'ONE': provider}, pm_content=lambda hashes: core.json.dumps({'response': [x in pm_cached for x in hashes]}), cache=cache)

    assert list(h.run().cached.keys()) == ['PMaa']
    assert sorted(cache['tt0000001']['results'].keys()) == ['aa', 'bb']
    assert 'ref' not in cache['tt0000001']['results']['aa'] and 'title' not in cache['tt0000001']['results']['aa']  # raw rows, not split ones

    pm_cached[:] = ['bb']  # the debrid cache changed since the search
    search = h.run()
    assert len(calls) == 1  # served from the cache
    assert list(search.cached.keys()) == ['PMbb']
    assert search.cached['PMbb']['ref'].imdbnumber == 'tt0000001'
    assert len(h.requests) == 2  # but the split was checked again

    h.run(refresh=True)
    assert len(calls) == 2

def test_search_cache_keeps_20_most_recent(core, monkeypatch):
    cache = dict(('tt%07d' % i, {'time': i + 1, 'results': {'x': {}}}) for i in range(2, 22))
    h = __SearchHarness(core, monkeypatch, {'ONE': __FakeProvider([__raw('The.Movie.2020.1080p.WEB.x264-GRP', 'aa')])}, cache=cache)
    h.run()
    assert len(cache) == 20
    assert 'tt0000001' in cache and 'tt0000002' not in cache

@pytest.mark.parametrize('setting, kept', [('5', 5), ('0', 0), ('', 20)])
def test_search_cache_holds_the_remembered_searches_setting(core, monkeypatch, setting, kept):
    cache = dict(('tt%07d' % i, {'time': i + 1, 'results': {'x': {}}}) for i in range(2, 22))
    provider = __FakeProvider([__raw('The.Movie.2020.1080p.WEB.x264-GRP', 'aa')])
    h = __SearchHarness(core, monkeypatch, {'ONE': provider}, cache=cache, settings={'general.remembered_searches': setting})
    first = h.run()
    if kept:
        assert len(cache) == kept and 'tt0000001' in cache
    else:
        assert len(cache) == 20 and 'tt0000001' not in cache  # 0: nothing written, nothing read
    assert first.from_cache is False and h.run().from_cache is bool(kept)
    assert h.run(refresh=True).from_cache is False

@pytest.mark.parametrize('release_title,ref,expected', [
    ('The.Movie.2020.1080p.WEB.x264-GRP', {'mediatype': 'movie', 'title': 'The Movie'}, (False, False)),
    ('Another.Film.2020.2160p.WEB.x265-GRP', {'mediatype': 'movie', 'title': 'The Movie'}, (True, False)),
    ('Amelie.2001.1080p.BluRay.x264-GRP', {'mediatype': 'movie', 'title': u'Amélie'}, (False, False)),
    ('Schindlers.List.1993.1080p.BluRay.x264-GRP', {'mediatype': 'movie', 'title': "Schindler's List"}, (False, False)),
    ('Show.Name.S01E02.The.Long.Night.1080p.WEB.x264-GRP', {'mediatype': 'episode', 'tvshowtitle': 'Show Name', 'title': 'The Long Night'}, (False, True)),
    ('Show.Name.S01.1080p.WEB.x264-GRP', {'mediatype': 'episode', 'tvshowtitle': 'Show Name', 'title': 'The Long Night'}, (False, False)),
    ('Other.Show.S01E02.The.Long.Night.1080p-GRP', {'mediatype': 'episode', 'tvshowtitle': 'Show Name', 'title': 'The Long Night'}, (True, True)),
    ('Whatever.1080p', {'mediatype': 'movie', 'title': None}, (False, False)),
])
def test_rank_guards(core, release_title, ref, expected):
    assert core.utils.rank_guards(release_title, core.utils.DictAsObject(ref)) == expected

def test_result_sort_key_ranks_title_guards_first(playback):
    def r(name, quality, mismatch=False, hit=False):
        return {'name': name, 'quality': quality, 'hdr': '', 'videocodec': 'H264', 'size': 1.0, 'audiocodec': '', 'release_title': name,
                'title_mismatch': mismatch, 'episode_title_hit': hit}
    results = [r('wrong_show_4k', '4K', mismatch=True), r('right_720', '720P'), r('named_episode_720', '720P', hit=True), r('right_1080', '1080P')]
    ordered = [x['name'] for x in sorted(results, key=playback.result_sort_key)]
    assert ordered == ['named_episode_720', 'right_1080', 'right_720', 'wrong_show_4k']

def test_search_sets_rank_guards_from_the_raw_release_name(core, monkeypatch):
    provider = __FakeProvider([__raw('Another.Film.2020.2160p.WEB.x265-GRP', 'aa'), __raw('The.Movie.2020.1080p.WEB.x264-GRP', 'bb')])
    search = __SearchHarness(core, monkeypatch, {'ONE': provider}, pm_cached=['aa', 'bb']).run()
    assert search.cached['PMaa']['title_mismatch'] is True
    assert search.cached['PMbb']['title_mismatch'] is False

def __quick_row(core, name, size):
    title = {'mediatype': 'movie', 'imdbnumber': 'tt0000001', 'title': 'The Movie', 'duration': 100}
    return {'quality': '1080P', 'hdr': '', 'videocodec': 'H264', 'audiocodec': '', 'size': size, 'release_title': name, 'title': name,
            core.utils.result_link_key: name, 'debrid': 'PM', 'package': 'single', 'seeds': 0, 'ref': core.utils.DictAsObject(title)}

def test_play_quick_rows_over_the_size_limit_bring_the_full_search(core, monkeypatch):
    h = __PlayHarness(core, monkeypatch, {'B': [__video('b')]}, choices=[1], quick={'Q': __quick_row(core, 'Q', 300.0)})
    assert h.run() == 'http://b'
    assert [bool(p.full) for p in h.searches] == [False, True]
    assert len(h.items[0]) == 4  # the three full results and the file pick toggle

def test_play_search_all_providers_replaces_the_quick_rows(core, monkeypatch):
    h = __PlayHarness(core, monkeypatch, {'B': [__video('b')]}, choices=[2, 1], quick={'Q': __quick_row(core, 'Q', 10.0)})
    assert h.run() == 'http://b'
    assert [bool(p.full) for p in h.searches] == [False, True]
    assert len(h.items[0]) == 3 and 'Search all providers' in h.items[0][-1]
    assert len(h.items[1]) == 4 and not any('Q' in item for item in h.items[1])  # the full results alone
    assert h.resolved == ['B']

def test_play_full_search_keeps_uncached_rows_behind_the_last_row(core, monkeypatch):
    h = __PlayHarness(core, monkeypatch, {}, choices=[4, -1, -1], uncached={'d': __quick_row(core, 'D', 10.0)})
    assert h.run() is None
    assert 'Show uncached sources (1)' in h.items[0][-1]
    assert [heading for heading, _ in h.dialogs] == ['Choose source', 'Uncached sources', 'Choose source']
    assert h.dialogs[2] == ('Choose source', 3)  # Back: the sheet again, on its first action row
    assert len(h.items[1]) == 1 and 'D' in h.items[1][0] and 'Not cached' in h.items[1][0]

def test_play_with_nothing_cached_shows_the_uncached_rows(core, monkeypatch):
    h = __PlayHarness(core, monkeypatch, {}, choices=[-1], uncached={'d': __quick_row(core, 'D', 10.0)})
    monkeypatch.setattr(core, 'provider', lambda core, params: core.utils.DictAsObject({'results': {'d': __quick_row(core, 'D', 10.0)}, 'cached': {}}))
    assert h.run() is None
    assert [heading for heading, _ in h.dialogs] == ['Uncached sources']

def test_play_dead_link_moves_to_next_source(core, monkeypatch):
    h = __PlayHarness(core, monkeypatch, {'A': [__video('a')], 'B': [__video('b')]}, choices=[], autoplay=True, dead_links=['http://a'])
    assert h.run() == 'http://b'
    assert h.resolved == ['A', 'B']
    assert h.probed == ['http://a', 'http://b']

def test_play_dead_link_returns_to_selection(core, monkeypatch):
    h = __PlayHarness(core, monkeypatch, {'A': [__video('a')], 'B': [__video('b')]}, choices=[0, 1], dead_links=['http://a'])
    assert h.run() == 'http://b'
    assert h.dialogs == [('Choose source', 0), ('Choose source', 1)]
    assert h.notifications == ['Failed to resolve debrid']

def test_link_alive_makes_a_single_attempt(core, playback, monkeypatch):
    import urllib3
    attempts = []

    def make_request(*args, **kwargs):
        attempts.append(1)
        raise urllib3.exceptions.ConnectTimeoutError('timed out')
    monkeypatch.setattr(urllib3.connectionpool.HTTPConnectionPool, '_make_request', make_request)
    assert getattr(playback, '__link_alive')(core, 'https://dead.invalid/file.mkv') is False
    assert len(attempts) == 1

@pytest.mark.parametrize('install, zip_path, asked', [
    ('0', '/tmp/p.zip', False),  # a plugin URL's params are strings
    (0, '/tmp/p.zip', False),
    (None, None, True),
    ('x', None, True),
])
def test_provider_install_takes_the_choice_as_a_string_or_int(core, monkeypatch, install, zip_path, asked):
    dialogs, copied = [], []
    dialog = core.utils.DictAsObject({'select': lambda *a, **k: dialogs.append(a) or -1})
    monkeypatch.setattr(core.kodi.xbmcgui, 'Dialog', lambda: dialog)
    def copyfile(src, dst):
        copied.append(src)
        raise RuntimeError('stop here')
    monkeypatch.setattr(core.utils.shutil, 'copyfile', copyfile)
    monkeypatch.setattr(core.kodi, 'notification', lambda *a, **k: None)
    params = {'type': 'install', 'install': install, 'zip_path': zip_path}
    core.provider(core, core.utils.DictAsObject({k: v for k, v in params.items() if v is not None}))
    assert bool(dialogs) == asked and copied == ([] if asked else [zip_path])

def test_logs_never_carry_a_debrid_key(core, monkeypatch):
    logger = importlib.import_module('a4kStreaming.lib.logger')
    logged = []
    monkeypatch.setattr(logger.xbmc, 'log', lambda message, level: logged.append(message))
    monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: {'premiumize.apikey': 'test-key-1'}.get(key, ''))
    hash = 'ab' * 20
    core.logger.debug('POST ^ - https://www.premiumize.me/api/transfer/directdl?apikey=test-key-1')
    core.logger.notice(RuntimeError('https://example.com/language%3Denglish%7Cpremiumize%3Dtest-key-1%7Cx/stream/movie/tt0000001.json'))
    core.logger.notice('https://example.com/language=english|premiumize=test-key-1/stream/movie/tt0000001.json')
    core.logger.error('https://example.com/resolve/premiumize/test-key-1/%s/null/0/Example.mkv' % hash)
    core.logger.notice('a link of any other shape: https://example.com/play/test-key-1/%s' % hash)
    core.logger.notice('https://example.com/api?apikey=test-key-2&id=1')  # a key no longer in the settings
    assert len(logged) == 6
    assert not any('test-key' in message for message in logged)
    assert logged[3].endswith('/resolve/premiumize/***/%s/null/0/Example.mkv' % hash)
    assert logged[5].endswith('https://example.com/api?apikey=***&id=1')

# the uncached pick (#023): Premiumize gets the source, the wait shows its progress, a resolve that answers plays it

class __FakePremiumize(object):
    def __init__(self, core, monkeypatch, ready_after=1, status='running', created=None, cancel_at=None, keep=0):
        self.calls, self.progress, self.notes, self.polls = [], [], [], 0
        self.clock = [1000.0]
        def execute(core, request, cache=True):
            url = request['url'].split('?')[0].rsplit('/', 2)
            action = '/'.join(url[-2:])
            self.calls.append(action)
            if action == 'transfer/create':
                body = created if created is not None else {'status': 'success', 'id': 't1'}
            elif action == 'transfer/directdl':
                self.polls += 1
                body = {'status': 'success', 'content': [{'path': 'a.mkv'}]} if ready_after is not None and self.polls > ready_after \
                    else {'status': 'error', 'message': 'not cached'}
            elif action == 'transfer/list':
                body = {'transfers': [{'id': 't1', 'status': status, 'progress': 0.25, 'message': '1.2 MB/s'}]}
            else:
                body = {'status': 'success'}
            response = lambda: None
            response.content, response.status_code = core.json.dumps(body), 200
            return response
        monkeypatch.setattr(core.request, 'execute', execute)
        progress = lambda: None
        progress.create = lambda *a: self.progress.append(('create',) + a)
        progress.update = lambda *a: self.progress.append(('update',) + a)
        progress.close = lambda: self.progress.append(('close',))
        progress.iscanceled = lambda: cancel_at is not None and self.polls >= cancel_at
        monkeypatch.setattr(core.kodi.xbmcgui, 'DialogProgress', lambda: progress)
        monkeypatch.setattr(core.kodi.xbmc, 'sleep', lambda ms: self.clock.__setitem__(0, self.clock[0] + ms / 1000.0))
        monkeypatch.setattr(core.time, 'time', lambda: self.clock[0])
        monkeypatch.setattr(core.kodi, 'notification', lambda text, time=3000: self.notes.append(text))
        self.asked = []
        sheets = importlib.import_module('a4kStreaming.ui.sheets')
        monkeypatch.setattr(sheets, 'select', lambda heading, labels, **k: self.asked.append(labels) or keep)

def __uncached_source(core):
    return __quick_row(core, 'D', 10.0)

def test_transfer_plays_once_a_resolve_answers(core, monkeypatch, playback):
    pm = __FakePremiumize(core, monkeypatch, ready_after=2)
    assert playback.transfer(core, 'key', __uncached_source(core)) is True
    assert pm.calls == ['transfer/create', 'transfer/directdl', 'transfer/list', 'transfer/directdl', 'transfer/list',
                        'transfer/directdl']
    assert pm.progress[0] == ('create', 'Premiumize', 'Adding to Premiumize\u2026')
    assert ('update', 25, 'Premiumize: running\n1.2 MB/s') in pm.progress and pm.progress[-1] == ('close',)

def test_transfer_cancel_keeps_it_in_premiumize(core, monkeypatch, playback):
    pm = __FakePremiumize(core, monkeypatch, ready_after=None, cancel_at=1, keep=0)
    assert playback.transfer(core, 'key', __uncached_source(core)) is False
    assert pm.asked == [['Keep downloading in Premiumize', 'Remove from Premiumize']]
    assert 'transfer/delete' not in pm.calls

def test_transfer_cancel_can_remove_it(core, monkeypatch, playback):
    pm = __FakePremiumize(core, monkeypatch, ready_after=None, cancel_at=1, keep=1)
    assert playback.transfer(core, 'key', __uncached_source(core)) is False
    assert pm.calls[-1] == 'transfer/delete' and pm.notes == ['Removed from Premiumize']

def test_transfer_wait_stops_after_the_cap(core, monkeypatch, playback):
    pm = __FakePremiumize(core, monkeypatch, ready_after=None)
    assert playback.transfer(core, 'key', __uncached_source(core)) is False
    assert pm.notes == ['Still downloading in Premiumize: try again later']
    assert 'transfer/delete' not in pm.calls and pm.polls == playback.TRANSFER_MAX // playback.TRANSFER_POLL + 1

@pytest.mark.parametrize('created, status, note', [
    ({'status': 'error', 'message': 'Invalid source'}, 'running', 'Invalid source'),
    (None, 'error', '1.2 MB/s'),  # a failed transfer: its message
])
def test_transfer_errors_say_why(core, monkeypatch, playback, created, status, note):
    pm = __FakePremiumize(core, monkeypatch, ready_after=None, created=created, status=status)
    assert playback.transfer(core, 'key', __uncached_source(core)) is False
    assert pm.notes == [note]

def test_play_an_uncached_pick_plays_through_the_normal_path_once_ready(core, monkeypatch, playback):
    h = __PlayHarness(core, monkeypatch, {'D': [__video('d')]}, choices=[4, 0], uncached={'d': __uncached_source(core)})
    monkeypatch.setattr(playback, 'transfer', lambda core, apikey, result: result['release_title'] == 'D')
    assert h.run() == 'http://d'
    assert [heading for heading, _ in h.dialogs] == ['Choose source', 'Uncached sources']
    assert h.resolved == ['D']
