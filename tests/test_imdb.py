# -*- coding: utf-8 -*-
# Offline tests for the IMDb request layer, listings and art (no network).

import importlib
from .common import pytest, api

@pytest.fixture(scope='module')
def core():
    return api.A4kStreamingApi({'kodi': True}).core

@pytest.fixture
def request_module(core, monkeypatch):
    module = importlib.import_module('a4kStreaming.lib.request')
    monkeypatch.setattr(module, '__local', __import__('threading').local())
    return module

@pytest.fixture
def sleeps(core, monkeypatch):
    calls = []
    monkeypatch.setattr(core.time, 'sleep', lambda s: calls.append(s))
    return calls

class Store(dict):
    ages = None

@pytest.fixture
def mem_db(core, monkeypatch):
    store = Store()
    store.ages = {}
    monkeypatch.setattr(core.db, 'set', lambda key, value: store.__setitem__(key, value))
    monkeypatch.setattr(core.db, 'get', lambda key: store[key])
    monkeypatch.setattr(core.db, 'age', lambda key: store.ages.get(key, 0) if key in store else None, raising=False)
    monkeypatch.setattr(core.db, 'clear', lambda prefix='': [store.pop(k) for k in list(store) if k.startswith(prefix)], raising=False)
    return store

class FakeResponse(object):
    def __init__(self, status_code, content=b'{}'):
        self.status_code = status_code
        self.content = content
        self.text = content.decode('utf-8') if isinstance(content, bytes) else content
        self.closed = False

    def close(self):
        self.closed = True

def fake_session(request_module, monkeypatch, answers):
    sent = []

    class FakeSession(object):
        def __init__(self):
            self.cookies = request_module.requests.cookies.RequestsCookieJar()
        def mount(self, prefix, adapter): pass
        def request(self, **kwargs):
            sent.append(kwargs)
            answer = answers.pop(0) if len(answers) > 1 else answers[0]
            if isinstance(answer, Exception):
                raise answer
            if callable(answer):
                return answer(kwargs)
            return answer
    monkeypatch.setattr(request_module.requests, 'Session', FakeSession)
    return sent

def settings(core, monkeypatch, values=None):
    all_values = {'general.page_size': '29', 'general.lists_page_size': '29'}
    all_values.update(values or {})
    monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: all_values.get(key, ''))

# A. request hygiene

def test_imdb_requests_send_the_referer(core):
    request = core.utils.get_graphql_query({'query': 'query fn { title(id: "tt1") { id } }'})
    assert request['headers']['referer'] == 'https://www.imdb.com/'
    assert request['headers']['x-imdb-client-name'] == 'imdb-web-next'

@pytest.mark.parametrize('status', [408, 429, 500, 502, 503, 504])
def test_request_retries_transient_statuses_with_backoff(core, request_module, monkeypatch, sleeps, status):
    sent = fake_session(request_module, monkeypatch, [FakeResponse(status), FakeResponse(status), FakeResponse(200, b'ok')])
    response = request_module.execute(core, {'method': 'GET', 'url': 'https://example.com/'}, cache=False)
    assert response.status_code == 200
    assert len(sent) == 3
    assert sleeps == [0.35, 0.7]

def test_request_retries_network_errors_and_gives_up_after_three(core, request_module, monkeypatch, sleeps):
    sent = fake_session(request_module, monkeypatch, [request_module.requests.exceptions.ConnectionError('down')])
    response = request_module.execute(core, {'method': 'POST', 'url': 'https://graphql.imdb.com'}, cache=False)
    assert response.status_code == 500
    assert len(sent) == 3
    assert sleeps == [0.35, 0.7]

def test_request_does_not_retry_client_errors(core, request_module, monkeypatch, sleeps):
    sent = fake_session(request_module, monkeypatch, [FakeResponse(404)])
    assert request_module.execute(core, {'method': 'GET', 'url': 'https://example.com/'}, cache=False).status_code == 404
    assert len(sent) == 1 and sleeps == []

def test_graphql_errors_with_null_data_are_not_cached_and_surface(core, request_module, monkeypatch, sleeps, mem_db):
    settings(core, monkeypatch)
    notifications = []
    monkeypatch.setattr(core.kodi, 'notification', lambda text, time=3000: notifications.append(text))
    error = b'{"errors": [{"message": "Invalid cursor signature"}], "data": {"advancedTitleSearch": null}}'
    sent = fake_session(request_module, monkeypatch, [FakeResponse(200, error)])

    params = core.utils.DictAsObject({'type': 'popularMovies', 'paginationToken': 'old'})
    assert core.query(core, params) == []
    assert len(sent) == 2  # the query-level retry reaches IMDb instead of re-reading a cached error
    assert mem_db == {}
    assert notifications == ['Something went wrong. Check logs']

def test_graphql_partial_errors_still_count_as_data(core, request_module):
    assert request_module.graphql_failed(b'{"errors": [{"message": "x"}], "data": null}')
    assert request_module.graphql_failed(b'{"errors": [{"message": "x"}]}')
    assert not request_module.graphql_failed(b'{"errors": [{"message": "x"}], "data": {"title": {"id": "tt1"}}}')
    assert not request_module.graphql_failed(b'{"data": {"title": null}}')
    assert not request_module.graphql_failed('')

# B. mutations are never cached and make cached reads go away

def test_imdb_mutation_is_never_served_from_cache(core, request_module, monkeypatch, mem_db):
    settings(core, monkeypatch, {'imdb.at-main': 'token'})
    sent = fake_session(request_module, monkeypatch, [FakeResponse(200, b'{"data": {"tt1": {"rating": {"value": 7}}}}')])
    rate = lambda: core.query(core, core.utils.DictAsObject({'type': 'rate', 'rating': 7, 'titleid': 'tt1'}))
    assert rate() is True
    assert rate() is True
    assert len(sent) == 2
    assert mem_db == {}

def test_read_after_an_imdb_mutation_is_fresh(core, request_module, monkeypatch, mem_db):
    settings(core, monkeypatch, {'imdb.at-main': 'token'})
    status = b'{"data": {"lists": {"edges": [{"node": {"tt1": false, "listClass": {"id": "WATCH_LIST"}}}]}}}'
    sent = fake_session(request_module, monkeypatch, [FakeResponse(200, status)])
    read = lambda: core.query(core, core.utils.DictAsObject({'type': 'status', 'ids': ['tt1']}))
    read()
    read()
    assert len(sent) == 1  # the 5 s de-duplication still works for reads

    core.query(core, core.utils.DictAsObject({'type': 'add_to_predefined_list', 'class_type': 'WATCH_LIST', 'titleid': 'tt1'}))
    read()
    assert len(sent) == 3  # mutation + a fresh read
    assert ['mutation' in core.json.loads(s['data'])['query'] for s in sent] == [False, True, False]

def test_debrid_delete_is_not_cached_and_clears_only_its_host(core, request_module, monkeypatch, mem_db):
    sent = fake_session(request_module, monkeypatch, [FakeResponse(200, b'{"status": "success"}')])
    mem_db['graphql.imdb.com_x'] = b'page'
    transfers = core.debrid.premiumize_transfers('key')
    request_module.execute(core, dict(transfers))
    assert any(k.startswith('www.premiumize.me_') for k in mem_db)

    delete = core.debrid.premiumize_transfer_delete('key', 'id1')
    request_module.execute(core, dict(delete))
    request_module.execute(core, dict(delete))
    assert len(sent) == 3
    assert list(mem_db) == ['graphql.imdb.com_x']

def test_db_clear_removes_only_the_prefix(core):
    core.db.set('graphql.imdb.com_test1', b'a')
    core.db.set('www.premiumize.me_test1', b'b')
    core.db.clear('www.premiumize.me')
    assert core.db.age('graphql.imdb.com_test1') is not None
    assert core.db.age('www.premiumize.me_test1') is None
    core.db.clear('graphql.imdb.com')
    assert core.db.age('graphql.imdb.com_test1') is None

# C. fewer round trips

def __episode(season, number):
    return {'node': {'id': 'tt%02d%03d' % (season, number), 'releaseDate': {'day': 1, 'month': 1, 'year': 2000 + season},
                     'series': {'episodeNumber': {'seasonNumber': season, 'episodeNumber': number}}}}

def __seasons_answer(seasons, first_page, has_next=True, alias_has_next=False):
    def answer(kwargs):
        body = __import__('json').loads(kwargs['data'])
        if 'includeSeasons' in body['query']:
            episodes = dict(('s%s' % i, {'edges': [__episode(s, n) for n in (1, 2)], 'pageInfo': {'hasNextPage': alias_has_next}})
                            for i, s in enumerate(seasons))
            return FakeResponse(200, __import__('json').dumps({'data': {'title': {'episodes': episodes}}}).encode())
        if body['variables'].get('paginationToken'):
            page = {'edges': [__episode(seasons[-1], 3)], 'pageInfo': {'hasNextPage': False, 'endCursor': None}}
            return FakeResponse(200, __import__('json').dumps({'data': {'title': {'episodes': {'episodes': page}}}}).encode())
        title = {'id': 'tt1', 'titleType': {'id': 'tvSeries'}, 'titleText': {'text': 'Show'},
                 'episodes': {'seasons': [{'number': s} for s in seasons],
                              'episodes': {'edges': first_page, 'pageInfo': {'hasNextPage': has_next, 'endCursor': 'c1'}}}}
        return FakeResponse(200, __import__('json').dumps({'data': {'title': title}}).encode())
    return answer

def __season_ids(core, monkeypatch):
    settings(core, monkeypatch)
    return [e['id'] for e in core.query(core, core.utils.DictAsObject({'type': 'seasons', 'id': 'tt1', 'silent': True}))]

def test_long_show_fetches_all_seasons_in_one_aliased_request(core, request_module, monkeypatch, mem_db):
    sent = fake_session(request_module, monkeypatch, [__seasons_answer([1, 2, 3], [__episode(1, 1)])])
    assert __season_ids(core, monkeypatch) == ['tt01001', 'tt01002', 'tt02001', 'tt02002', 'tt03001', 'tt03002']
    assert len(sent) == 2
    query = __import__('json').loads(sent[1]['data'])['query']
    assert 's0: episodes(first: 250, filter: { includeSeasons: ["1"] })' in query
    assert 's2: episodes(first: 250, filter: { includeSeasons: ["3"] })' in query
    assert 'fragment SeasonsNode on Title' in query

def test_short_show_makes_one_request(core, request_module, monkeypatch, mem_db):
    sent = fake_session(request_module, monkeypatch, [__seasons_answer([1, 2], [__episode(1, 1)], has_next=False)])
    assert __season_ids(core, monkeypatch) == ['tt01001']
    assert len(sent) == 1

@pytest.mark.parametrize('seasons,alias_has_next,calls', [([1], False, 2), ([1, 2], True, 3)])
def test_single_season_or_huge_season_walks_the_cursor(core, request_module, monkeypatch, mem_db, seasons, alias_has_next, calls):
    sent = fake_session(request_module, monkeypatch, [__seasons_answer(seasons, [__episode(1, 1)], alias_has_next=alias_has_next)])
    assert __season_ids(core, monkeypatch) == ['tt01001', 'tt%02d003' % seasons[-1]]
    assert len(sent) == calls
    assert __import__('json').loads(sent[-1]['data'])['variables']['paginationToken'] == 'c1'

def test_knownfor_asks_for_the_largest_page(core, request_module, monkeypatch, mem_db):
    settings(core, monkeypatch, {'imdb.at-main': 'token'})
    sent = fake_session(request_module, monkeypatch, [FakeResponse(200, b'{"data": {"name": {"credits": {"edges": [], "pageInfo": {"hasNextPage": false}}}}}')])
    core.query(core, core.utils.DictAsObject({'type': 'knownfor', 'id': 'nm1'}))
    assert __import__('json').loads(sent[0]['data'])['variables']['limit'] == 250

# D. sized artwork

def test_art_sizes_sit_on_a_40px_grid(core):
    for size in [core.utils.poster_size, core.utils.thumb_size, core.utils.fanart_size, core.utils.cast_size]:
        assert size[0] % 40 == 0, size

def test_resize_keeps_an_existing_crop_transform(core):
    image = {'url': 'https://m.media-amazon.com/images/M/abc@._V1_CR600,1,2999,4499_.jpg', 'width': 2999, 'height': 4499}
    assert core.utils.fix_cast_size(image) == 'https://m.media-amazon.com/images/M/abc@._V1_CR600,1,2999,4499_UX280_CR0,0,280,420_AL_.jpg'

def test_resize_without_dimensions_still_yields_a_valid_url(core):
    image = {'url': 'https://m.media-amazon.com/images/M/abc@._V1_.jpg'}
    assert core.utils.fix_thumb_size(image) == 'https://m.media-amazon.com/images/M/abc@._V1_UX480_.jpg'

def test_resize_leaves_foreign_urls_alone(core):
    assert core.utils.fix_poster_size({'url': 'https://example.com/a.png', 'width': 1, 'height': 1}) == 'https://example.com/a.png'

# E. gallery page cache

def __page(cursor='c2', title_id=None):
    titles = [{'node': {'title': {'id': title_id, 'titleType': {'id': 'movie'}, 'titleText': {'text': 'A Movie'}}}}] if title_id else []
    body = {'data': {'advancedTitleSearch': {'titles': titles, 'pageInfo': {'hasNextPage': True, 'endCursor': cursor}}}}
    return FakeResponse(200, core_json().dumps(body).encode())

def core_json():
    return __import__('json')

def __popular(core, **extra):
    return core.query(core, core.utils.DictAsObject(dict({'type': 'popularMovies'}, **extra)))

@pytest.fixture
def next_urls(core, monkeypatch):
    urls = []
    monkeypatch.setattr(core.kodi.xbmcplugin, 'addDirectoryItem', lambda handle, url, item, folder: urls.append(url))
    return urls

def __keys(store, prefix='graphql.imdb.com_'):
    return [k for k in store if k.startswith(prefix)]

def test_gallery_page_stays_fresh_for_30_minutes(core, request_module, monkeypatch, mem_db):
    settings(core, monkeypatch)
    sent = fake_session(request_module, monkeypatch, [__page()])
    __popular(core)
    key = __keys(mem_db)[0]
    mem_db.ages[key] = 29 * 60
    __popular(core)
    assert len(sent) == 1
    mem_db.ages[key] = 31 * 60
    __popular(core)  # api mode (tests, scripts) never serves stale
    assert len(sent) == 2

def test_stale_first_page_shows_at_once_and_refreshes_after(core, request_module, monkeypatch, mem_db):
    settings(core, monkeypatch)
    monkeypatch.setattr(core, 'api_mode_enabled', False)
    sent = fake_session(request_module, monkeypatch, [__page()])
    __popular(core)
    key = __keys(mem_db)[0]
    mem_db.ages[key] = 3 * 60 * 60
    __popular(core)
    assert len(sent) == 1 and len(request_module.pending_revalidation) == 1
    request_module.revalidate(core)
    assert len(sent) == 2 and request_module.pending_revalidation == []

def test_stale_cursor_page_and_day_old_page_are_fetched(core, request_module, monkeypatch, mem_db):
    settings(core, monkeypatch)
    monkeypatch.setattr(core, 'api_mode_enabled', False)
    sent = fake_session(request_module, monkeypatch, [__page()])
    __popular(core, paginationToken='c1')
    cursor_page = __keys(mem_db)[0]
    mem_db.ages[cursor_page] = 31 * 60
    __popular(core, paginationToken='c1')  # a page reached by a cursor is never shown stale
    __popular(core)
    first_page = [k for k in __keys(mem_db) if k != cursor_page][0]
    mem_db.ages[first_page] = 25 * 60 * 60
    __popular(core)  # older than a day: fetched, not shown
    assert len(sent) == 4 and request_module.pending_revalidation == []

def test_user_lists_are_not_kept_past_5_seconds(core, request_module, monkeypatch, mem_db):
    settings(core, monkeypatch, {'imdb.at-main': 'token'})
    body = b'{"data": {"predefinedList": {"items": {"titles": [], "pageInfo": {"hasNextPage": false}}}}}'
    sent = fake_session(request_module, monkeypatch, [FakeResponse(200, body)])
    core.query(core, core.utils.DictAsObject({'type': 'watchlist'}))
    mem_db.ages[__keys(mem_db)[0]] = 6
    core.query(core, core.utils.DictAsObject({'type': 'watchlist'}))
    assert len(sent) == 2

def test_imdb_write_drops_kept_gallery_pages(core, request_module, monkeypatch, mem_db):
    settings(core, monkeypatch, {'imdb.at-main': 'token'})
    sent = fake_session(request_module, monkeypatch, [__page(), FakeResponse(200, b'{"data": {"tt1": {"date": "x"}}}'), __page()])
    __popular(core)
    core.query(core, core.utils.DictAsObject({'type': 'unrate', 'titleid': 'tt1'}))
    assert __keys(mem_db) == []
    __popular(core)
    assert len(sent) == 3

def test_cache_key_includes_the_token(core, request_module, monkeypatch, mem_db):
    sent = fake_session(request_module, monkeypatch, [__page()])
    for token in ['one', 'two', 'one']:
        settings(core, monkeypatch, {'imdb.at-main': token})
        __popular(core)
    assert len(sent) == 2

def test_next_item_carries_page_and_cursor_time(core, request_module, monkeypatch, mem_db, next_urls):
    settings(core, monkeypatch)
    fake_session(request_module, monkeypatch, [__page(cursor='a+b/c==')])
    __popular(core, page='2')
    params = dict(core.utils.parse_qsl(next_urls[0].split('?', 1)[1]))
    assert params['paginationToken'] == 'a+b/c=='
    assert params['page'] == '3'
    assert abs(int(params['cursor_time']) - core.time.time()) < 5

def test_expired_cursor_walks_from_the_first_page(core, request_module, monkeypatch, mem_db):
    settings(core, monkeypatch)
    sent = fake_session(request_module, monkeypatch, [__page(cursor='fresh1'), __page(cursor='fresh2'), __page(cursor='c4')])
    __popular(core, paginationToken='old', page='3', cursor_time=str(int(core.time.time()) - 31 * 60))
    tokens = [core_json().loads(s['data'])['variables']['paginationToken'] for s in sent]
    assert tokens == [None, 'fresh1', 'fresh2']

def test_recent_cursor_is_used_as_is(core, request_module, monkeypatch, mem_db):
    settings(core, monkeypatch)
    sent = fake_session(request_module, monkeypatch, [__page()])
    __popular(core, paginationToken='recent', page='2', cursor_time=str(int(core.time.time()) - 60))
    assert [core_json().loads(s['data'])['variables']['paginationToken'] for s in sent] == ['recent']

def test_main_refreshes_stale_pages_after_the_listing_is_shown(core, request_module, monkeypatch, mem_db):
    settings(core, monkeypatch, {})
    monkeypatch.setattr(core, 'api_mode_enabled', True)
    events = []
    sent = fake_session(request_module, monkeypatch, [lambda kwargs: events.append('fetch') or __page()])
    __popular(core)
    mem_db.ages[__keys(mem_db)[0]] = 2 * 60 * 60
    monkeypatch.setattr(core.kodi.xbmcplugin, 'endOfDirectory', lambda handle, **kwargs: events.append('end'), raising=False)
    monkeypatch.setattr(core.kodi.xbmc, 'sleep', lambda ms: None)
    monkeypatch.setattr(core.db, 'cleanup', lambda: events.append('cleanup'))
    core.main('plugin://plugin.video.a4kstreaming/', 1, 'action=query&type=popularMovies')
    assert events == ['fetch', 'end', 'fetch', 'cleanup']
    assert len(sent) == 2

# G. still-frame art and groundwork for a tvOS-style skin

def __image(name, width, height):
    return {'url': 'https://m.media-amazon.com/images/M/%s._V1_.jpg' % name, 'width': width, 'height': height}

def __title(title_id='tt1', titleType='movie', **extra):
    title = {
        'id': title_id, 'titleType': titleType, 'titleText': 'A Title', 'releaseYear': 2020,
        'primaryImage': __image('poster', 2000, 3000), 'stillFrame': [__image('still', 1920, 1080)],
        'primaryVideos': ['vi1', 'vi2'],
    }
    title.update(extra)
    return title

def __listing():
    return vars(importlib.import_module('a4kStreaming.listing'))

@pytest.fixture
def items(core, monkeypatch):
    added = []
    monkeypatch.setattr(core.kodi.xbmcplugin, 'addDirectoryItems', lambda handle, list_items, n: added.extend(list_items))
    return added

@pytest.fixture
def reads(core, monkeypatch):
    keys = []
    values = {'general.autoplay': 'true'}
    monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: keys.append(key) or values.get(key, ''))
    return keys

def test_title_fragment_asks_for_one_still_frame(core):
    query = core.json.loads(core.utils.get_graphql_query({'query': 'query fn { title(id: "tt1") { ...TitleFull\n } }'})['data'])['query']
    assert 'stillFrame: images(first: 1, filter: { types: ["still_frame"] })' in query
    # aliased, so it never clashes with TitleFull's own images(first: 10)
    assert 'images(first: 10, filter: { types: ["still_frame"] })' in query

def test_crop_offset_is_a_whole_pixel(core):
    assert core.utils.get_image_params({'width': 1920, 'height': 1081}, 520, 780) == 'UY780_CR432,0,520,780_AL_'

def test_movie_and_series_get_still_art(core, items, reads):
    __listing()['__add_titles'](core, [__title(), __title('tt2', 'tvSeries')])
    for _, item, _ in items:
        assert item.art['poster'].endswith('poster._V1_UX520_CR0,0,520,780_AL_.jpg')
        assert item.art['fanart'].endswith('still._V1_UX1280_CR0,0,1280,720_AL_.jpg')
        assert item.art['landscape'].endswith('still._V1_UX960_CR0,0,960,540_AL_.jpg')
        assert item.art['blur'].endswith('still._V1_UX64_CR0,0,64,36_AL_.jpg')

def test_title_without_a_still_has_no_wide_art(core, items, reads):
    __listing()['__add_titles'](core, [__title(stillFrame=[])])
    assert items[0][1].art['fanart'] is None

def test_seasons_inherit_the_series_fanart_and_blur(core, items, reads):
    episodes = [{'id': 'tt1%s' % n, 'series': {'seasonNumber': n, 'episodeNumber': 1}, 'releaseDate': {'year': 2020 + n, 'month': 1, 'day': 1}} for n in [1, 2]]
    __listing()['__add_seasons'](core, __title('tt2', 'tvSeries', episodes={'episodes': episodes}))
    assert len(items) == 2
    for _, item, _ in items:
        assert item.art['fanart'].endswith('still._V1_UX1280_CR0,0,1280,720_AL_.jpg')
        assert item.art['blur'].endswith('still._V1_UX64_CR0,0,64,36_AL_.jpg')

def test_episodes_get_the_same_wide_keys_from_their_own_still(core, items, reads):
    episode = __title('tt3', 'tvEpisode', primaryImage=__image('episode', 1000, 1500), images=[__image('episode_still', 1920, 1080)],
                      series={'seasonNumber': 1, 'episodeNumber': 1})
    __listing()['__add_episodes'](core, [episode], 1)
    art = items[0][1].art
    assert art['fanart'].endswith('episode_still._V1_UX1280_CR0,0,1280,720_AL_.jpg')
    assert art['landscape'].endswith('episode_still._V1_UX960_CR0,0,960,540_AL_.jpg')
    assert art['blur'].endswith('episode_still._V1_UX64_CR0,0,64,36_AL_.jpg')

def test_items_carry_a4k_properties(core, items, reads):
    __listing()['__add_titles'](core, [__title(userRating=8), __title('tt2', 'tvSeries', userRating=None, primaryVideos=[])])
    props = [{k: v for k, v in item.properties.items() if k.startswith('a4k.')} for _, item, _ in items]
    assert props[0] == {'a4k.id': 'tt1', 'a4k.type': 'movie', 'a4k.rated': 'true', 'a4k.trailers': 'vi1_vi2',
                        'a4k.meta': props[0]['a4k.meta'], 'a4k.tv': '', 'a4k.tvstate': ''}
    assert props[1] == {'a4k.id': 'tt2', 'a4k.type': 'tvSeries', 'a4k.rated': 'false', 'a4k.trailers': '',
                        'a4k.meta': props[1]['a4k.meta'], 'a4k.tv': 'TV', 'a4k.tvstate': props[1]['a4k.tvstate']}

def test_title_context_menu_is_the_menu_the_item_gets(core, items, reads):
    title = __title()
    __listing()['__add_titles'](core, [title])
    menu = __listing()['title_context_menu'](core, title)
    assert menu == items[0][1].context_menu
    assert __listing()['title_context_menu'](core, __title(titleType='person')) == []

def test_play_url_is_the_url_the_item_gets(core, items, reads):
    titles = [__title(), __title('tt2', releaseYear=None), __title('tt3', 'tvEpisode', series={'seasonNumber': 1, 'episodeNumber': 2})]
    __listing()['__add_titles'](core, [dict(t) for t in titles])
    assert [__listing()['play_url'](core, t) for t in titles] == [url for url, _, _ in items]
    assert items[1][0] == '%s?action=play&type=&id=tt2' % core.url
    assert __listing()['play_url'](core, __title(titleType='tvSeries')) is None

def test_settings_are_read_once_per_listing(core, items, reads):
    __listing()['__add_titles'](core, [__title('tt%s' % n) for n in range(10)])
    assert reads.count('general.autoplay') == 1
    episodes = [__title('tt%s' % n, 'tvEpisode', series={'seasonNumber': 1, 'episodeNumber': n}) for n in range(1, 6)]
    __listing()['__add_episodes'](core, episodes, 1)
    assert reads.count('general.autoplay') == 2

# H. listing flags: the content type before the items, and which listings Kodi may keep on disk

@pytest.mark.parametrize('paramstring, action, cached', [
    ('widget=1', 'root', True),
    ('action=query&type=popularMovies', 'query', True),
    ('action=query&type=fan_picks', 'query', True),
    ('action=query&type=year&target_year=2020', 'query', True),
    ('action=query&type=more_like_this&id=tt1', 'query', True),
    ('action=query&type=seasons&id=tt1', 'query', True),
    ('action=query&type=episodes&id=tt1&season=1', 'query', True),
    ('action=query&type=browse&id=tt1', 'query', True),
    ('action=query&type=knownfor&id=nm1', 'query', True),
    ('action=query&type=watchlist', 'query', False),
    ('action=query&type=top_picks', 'query', False),
    ('action=query&type=lists', 'query', False),
    ('action=query&type=list&id=ls1', 'query', False),
    ('action=cloud&type=root', 'cloud', False),
])
def test_listing_sets_its_content_first_and_caches_only_public_pages(core, monkeypatch, paramstring, action, cached):
    events = []
    monkeypatch.setattr(core, action, lambda core, params=None: core.utils.add_directory_items(core, [('url', None, True)]))
    monkeypatch.setattr(core.kodi.xbmcplugin, 'setContent', lambda handle, content: events.append('content'))
    monkeypatch.setattr(core.kodi.xbmcplugin, 'addDirectoryItems', lambda handle, items, count: events.append('items'))
    monkeypatch.setattr(core.kodi.xbmcplugin, 'endOfDirectory', lambda handle, **kwargs: events.append(kwargs), raising=False)
    monkeypatch.setattr(core.kodi.xbmc, 'sleep', lambda ms: None)
    monkeypatch.setattr(core.kodi.xbmc, 'executebuiltin', lambda builtin: None)
    monkeypatch.setattr(core.request, 'revalidate', lambda core: None)
    monkeypatch.setattr(core.db, 'cleanup', lambda: None)
    core.main('plugin://plugin.video.a4kstreaming/', 1, paramstring + ('' if 'widget' in paramstring else '&widget=1'))
    assert events == ['content', 'items', {'cacheToDisc': cached}]
