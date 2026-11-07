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
    def __init__(self, core, monkeypatch, files_by_link, choices, autoplay=False, dead_links=()):
        self.dialogs = []
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
        }
        monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: settings.get(key, ''))
        monkeypatch.setattr(core, 'provider_meta', lambda core: utils.DictAsObject({'name': 'test'}))
        monkeypatch.setattr(core.cache, 'get_general', lambda: utils.DictAsObject({}))
        monkeypatch.setattr(core, 'provider', lambda core, params: self.searches.append(params) or utils.DictAsObject({'results': results, 'cached': results}))
        monkeypatch.setattr(core.cache, 'get_last_selected_result', lambda: {})
        for name in ['save_general', 'save_last_selected_result']:
            monkeypatch.setattr(core.cache, name, lambda data: None)
        monkeypatch.setattr(core.kodi, 'notification', lambda text, time=3000: self.notifications.append(text))

        def select(heading, items, preselect=None, **kwargs):
            self.dialogs.append((heading, preselect))
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
    h = __PlayHarness(core, monkeypatch, {'B': [__video('b')]}, choices=[1, 2])
    assert h.run() == 'http://b'
    assert h.dialogs == [('Choose source', 1), ('Choose source', 1)]
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
    assert h.dialogs == [('Choose source', 3)]
    assert h.notifications == ['Failed to resolve debrid']

def test_play_file_picker_cancel_returns_to_selection(core, monkeypatch):
    files = {'A': [__video('a1'), __video('a2')], 'B': [__video('b')]}
    h = __PlayHarness(core, monkeypatch, files, choices=[1, -1, 2])
    assert h.run() == 'http://b'
    assert h.dialogs == [('Choose source', 1), ('Choose file', None), ('Choose source', 1)]

def test_play_autoplay_file_picker_cancel_opens_selection(core, monkeypatch):
    files = {'A': [__video('a1'), __video('a2')]}
    h = __PlayHarness(core, monkeypatch, files, choices=[-1, -1], autoplay=True)
    assert h.run() is None
    assert h.dialogs == [('Choose file', None), ('Choose source', 1)]

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
    def __init__(self, core, monkeypatch, providers, settings=None, pm_cached=None, canceled=False, pm_content=None, cache=None):
        self.requests = []
        self.threads = []
        self.cache = {} if cache is None else cache
        monkeypatch.setattr(core.cache, 'get_last_results', lambda: core.json.loads(core.json.dumps(self.cache)))
        monkeypatch.setattr(core.cache, 'save_last_results', lambda data: (self.cache.clear(), self.cache.update(core.json.loads(core.json.dumps(data)))))
        self.progress = []
        self.saved = []
        utils = core.utils
        all_settings = {'premiumize.apikey': 'key'}
        all_settings.update(settings or {})
        monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: all_settings.get(key, ''))
        monkeypatch.setattr(core.cache, 'get_provider', lambda: {key: True for key in providers})
        modules = {key.lower(): utils.DictAsObject({'sources': (lambda s: lambda: s)(s)}) for key, s in providers.items()}
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

def test_search_ignores_a_leftover_alldebrid_key(core, monkeypatch):
    provider = __FakeProvider([__raw('The.Movie.2020.1080p.WEB.x264-GRP', h) for h in ['aa', 'bb']])
    h = __SearchHarness(core, monkeypatch, {'ONE': provider}, settings={'premiumize.apikey': '', 'alldebrid.apikey': 'k'})
    search = h.run()
    assert h.requests == [] and search.cached == {}

def test_play_new_search_refreshes(core, monkeypatch):
    h = __PlayHarness(core, monkeypatch, {}, choices=[0, -1])
    assert h.run() is None
    assert [bool(p.refresh) for p in h.searches] == [False, True]

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

def test_play_dead_link_moves_to_next_source(core, monkeypatch):
    h = __PlayHarness(core, monkeypatch, {'A': [__video('a')], 'B': [__video('b')]}, choices=[], autoplay=True, dead_links=['http://a'])
    assert h.run() == 'http://b'
    assert h.resolved == ['A', 'B']
    assert h.probed == ['http://a', 'http://b']

def test_play_dead_link_returns_to_selection(core, monkeypatch):
    h = __PlayHarness(core, monkeypatch, {'A': [__video('a')], 'B': [__video('b')]}, choices=[1, 2], dead_links=['http://a'])
    assert h.run() == 'http://b'
    assert h.dialogs == [('Choose source', 1), ('Choose source', 1)]
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
