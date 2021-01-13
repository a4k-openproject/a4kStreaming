# -*- coding: utf-8 -*-

from .common import (
    sys,
    os,
    json,
    re,
    time,
    api,
    utils
)

provider_url = os.environ.get('A4KSTREAMING_PROVIDER_URL')
premiumize_apikey = os.environ.get('A4KSTREAMING_PREMIUMIZE_APIKEY')
imdb_token = os.environ.get('A4KSTREAMING_IMDB_TOKEN')
trakt_apikey = os.environ.get('A4KSTREAMING_TRAKT_APIKEY')
trakt_username = os.environ.get('A4KSTREAMING_TRAKT_USERNAME')

def __remove_cache(a4kstreaming_api):
    try:
        os.remove(a4kstreaming_api.core.cache.__search_filepath)
    except: pass
    try:
        os.remove(a4kstreaming_api.core.cache.__provider_filepath)
    except: pass
    try:
        os.remove(a4kstreaming_api.core.cache.__last_results_filepath)
    except: pass

def __setup_provider(a4kstreaming_api):
    def select(*args, **kwargs): return 1
    a4kstreaming_api.core.kodi.xbmcgui.Dialog().select = select
    keyboard = a4kstreaming_api.core.kodi.xbmc.Keyboard('', '')
    keyboard.getText = lambda: provider_url
    keyboard.isConfirmed = lambda: True
    __invoke(a4kstreaming_api, 'provider', { 'type': 'install' })

    provider = a4kstreaming_api.core.cache.get_provider()
    selected = {}
    for key in list(provider.keys())[8:9]:
        selected[key] = True
    a4kstreaming_api.core.cache.save_provider(selected)

def __invoke(a4kstreaming_api, action, params={}, settings={}, prerun=None, remove_cache=True):
    if remove_cache:
        __remove_cache(a4kstreaming_api)

    fn = lambda: None
    fn.params = a4kstreaming_api.core.utils.DictAsObject(params)
    fn.settings = {
        'general.timeout': '30',
        'premiumize.apikey': premiumize_apikey,
        'imdb.at-main': imdb_token,
        'trakt.clientid': trakt_apikey,
        'trakt.username': trakt_username,
    }
    fn.settings.update(settings)

    if prerun:
        prerun()

    start = time.time()
    fn.results = getattr(a4kstreaming_api, action)(fn.params, fn.settings)
    end = time.time()
    print(end - start)

    return fn

def test_trailer():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    trailer = __invoke(a4kstreaming_api, 'trailer', { 'id': 'vi727367449' })

    assert len(trailer.results) > 0

def test_play_movie():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    def prerun():
        __setup_provider(a4kstreaming_api)

    title = b'eyJtZWRpYXR5cGUiOiAibW92aWUiLCAiaW1kYm51bWJlciI6ICJ0dDAxMDgxNjAiLCAidGl0bGUiOiAiU2xlZXBsZXNzIGluIFNlYXR0bGUiLCAib3JpZ2luYWx0aXRsZSI6ICJTbGVlcGxlc3MgaW4gU2VhdHRsZSIsICJ0dnNob3dpZCI6IG51bGwsICJzZWFzb25zIjogbnVsbCwgInR2c2hvd3RpdGxlIjogIiIsICJ5ZWFyIjogMTk5MywgInByZW1pZXJlZCI6ICIxOTkzLTYtMjUiLCAiZHVyYXRpb24iOiA2MzAwLCAibXBhYSI6ICJQRyIsICJnZW5yZSI6IFsiQ29tZWR5IiwgIkRyYW1hIiwgIlJvbWFuY2UiXSwgImNvdW50cnkiOiBbIlVuaXRlZCBTdGF0ZXMiXSwgInRyYWlsZXIiOiAiP2FjdGlvbj10cmFpbGVyJmlkPXZpNzI3MzY3NDQ5IiwgInBsb3QiOiAiQSByZWNlbnRseSB3aWRvd2VkIG1hbidzIHNvbiBjYWxscyBhIHJhZGlvIHRhbGstc2hvdyBpbiBhbiBhdHRlbXB0IHRvIGZpbmQgaGlzIGZhdGhlciBhIHBhcnRuZXIuIiwgInRhZ2xpbmUiOiAiV2hhdCBpZiBzb21lb25lIHlvdSBuZXZlciBtZXQsIHNvbWVvbmUgeW91IG5ldmVyIHNhdywgc29tZW9uZSB5b3UgbmV2ZXIga25ldyB3YXMgdGhlIG9ubHkgc29tZW9uZSBmb3IgeW91PyIsICJvdmVybGF5IjogMCwgInN0dWRpbyI6IFsiVHJpU3RhciBQaWN0dXJlcyIsICJUcmlTdGFyIFBpY3R1cmVzIiwgIkNvbHVtYmlhIFRyaVN0YXIgRmlsbSJdLCAiZGlyZWN0b3IiOiBbIk5vcmEgRXBocm9uIl0sICJ3cml0ZXIiOiBbIkplZmYgQXJjaCIsICJOb3JhIEVwaHJvbiIsICJEYXZpZCBTLiBXYXJkIl19'
    play = __invoke(a4kstreaming_api, 'play', { 'type': title }, prerun=prerun)

    assert play.results is not None

def test_play_episode():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    def prerun():
        __setup_provider(a4kstreaming_api)

    title = b'eyJtZWRpYXR5cGUiOiAiZXBpc29kZSIsICJpbWRibnVtYmVyIjogInR0MDU4MzYzMiIsICJ0aXRsZSI6ICJUaGUgT25lIHdpdGggdGhlIE5hcCBQYXJ0bmVycyIsICJvcmlnaW5hbHRpdGxlIjogIlRoZSBPbmUgd2l0aCB0aGUgTmFwIFBhcnRuZXJzIiwgInR2c2hvd2lkIjogInR0MDEwODc3OCIsICJzZWFzb25zIjogWzEsIDIsIDMsIDQsIDUsIDYsIDcsIDgsIDksIDEwXSwgInR2c2hvd3RpdGxlIjogIkZyaWVuZHMiLCAieWVhciI6IDIwMDAsICJwcmVtaWVyZWQiOiAiMjAwMC0xMS05IiwgImR1cmF0aW9uIjogMTMyMCwgIm1wYWEiOiAiVFYtUEciLCAiZ2VucmUiOiBbIkNvbWVkeSIsICJSb21hbmNlIl0sICJjb3VudHJ5IjogWyJVbml0ZWQgU3RhdGVzIl0sICJ0cmFpbGVyIjogbnVsbCwgInBsb3QiOiAiSm9leSBhbmQgUm9zcyBhY2NpZGVudGFsbHkgdGFrZSBhIG5hcCB0b2dldGhlciAtIGFuZCBtdWNoIHRvIHRoZWlyIGRpc21heSwgZmluZCB0aGF0IHRoZXkgbGlrZSBpdC4gUGhvZWJlIGFuZCBSYWNoZWwgY29tcGV0ZSB0byBiZWNvbWUgTW9uaWNhJ3MgbWFpZCBvZiBob25vci4iLCAidGFnbGluZSI6IG51bGwsICJvdmVybGF5IjogMCwgImVwaXNvZGUiOiA2LCAic2Vhc29uIjogNywgInN0dWRpbyI6IFsiQnJpZ2h0L0thdWZmbWFuL0NyYW5lIFByb2R1Y3Rpb25zIiwgIldhcm5lciBCcm9zLiBUZWxldmlzaW9uIiwgIk5hdGlvbmFsIEJyb2FkY2FzdGluZyBDb21wYW55IChOQkMpIl0sICJkaXJlY3RvciI6IFsiR2FyeSBIYWx2b3Jzb24iXSwgIndyaXRlciI6IFsiRGF2aWQgQ3JhbmUiLCAiTWFydGEgS2F1ZmZtYW4iLCAiQnJpYW4gQnVja25lciIsICJTZWJhc3RpYW4gSm9uZXMiXX0='
    play = __invoke(a4kstreaming_api, 'play', { 'type': title }, prerun=prerun)

    assert play.results is not None

def test_popular():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'query', { 'type': 'popular' })

    assert len(fn.results) > 0

def test_fan_picks():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'query', { 'type': 'fan_picks' })

    assert len(fn.results) > 0

def test_top_picks():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'query', { 'type': 'top_picks' })

    assert len(fn.results) > 0

def test_more_like_this():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'query', { 'type': 'more_like_this', 'id': 'tt0383574' })

    assert len(fn.results) > 0

def test_watchlist():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'query', { 'type': 'watchlist' })

    assert len(fn.results) > 0

def test_lists():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'query', { 'type': 'lists' })

    assert len(fn.results) > 0

def test_list():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'query', { 'type': 'list', 'id': 'ls082494257' })

    assert len(fn.results) > 0

def test_seasons():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'query', { 'type': 'seasons', 'id': 'tt3288518' })

    assert len(fn.results) > 0

def test_seasons_with_paging():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'query', { 'type': 'seasons', 'id': 'tt0239195' })

    assert len(fn.results) > 0

def test_episodes():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'query', {
        'type': 'episodes',
        'id': 'tt0108778',
        'season': '4',
        'year': '1997',
        'month': '09',
        'day': '25',
        'year_end': '1998',
        'month_end': '05',
        'day_end': '07',
    })

    assert len(fn.results) > 0

def test_year():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'query', { 'type': 'year', 'target_year': '1990' })

    assert len(fn.results) > 0

def test_browse_movie():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'query', { 'type': 'browse', 'id': 'tt6723592' })

    assert len(fn.results) > 0

def test_browse_episode():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'query', { 'type': 'browse', 'id': 'tt13052876' })

    assert len(fn.results) > 0

def test_person():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'query', { 'type': 'person', 'id': 'nm1434871' })

    assert fn.results is None

def test_status():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'query', { 'type': 'status', 'ids': ['tt8111088', 'tt7126948'] })

    assert len(fn.results) > 0

def test_ratings():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'query', { 'type': 'ratings', 'ids': ['tt8111088', 'tt7126948'] })

    assert len(fn.results) > 0

def test_search():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'search', { 'query': 'tenet' })

    assert len(fn.results) > 0

def test_provider_install():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    def select(*args, **kwargs): return 1
    a4kstreaming_api.core.kodi.xbmcgui.Dialog().select = select
    keyboard = a4kstreaming_api.core.kodi.xbmc.Keyboard('', '')
    keyboard.getText = lambda: provider_url
    keyboard.isConfirmed = lambda: True

    __invoke(a4kstreaming_api, 'provider', { 'type': 'install' })

    assert len(a4kstreaming_api.core.cache.get_provider()) > 0

def test_provider_manage():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    sources = ['SRC1', 'SRC2', 'SRC3', 'SRC4']
    expected_selection = [1, 3]

    def prerun():
        a4kstreaming_api.core.cache.save_provider({
            'SRC1': True,
            'SRC2': False,
            'SRC3': True,
            'SRC4': False,
        })

    def multiselect(*args, **kwargs): return expected_selection
    a4kstreaming_api.core.kodi.xbmcgui.Dialog().multiselect = multiselect

    __invoke(a4kstreaming_api, 'provider', { 'type': 'manage' }, prerun=prerun)

    provider = a4kstreaming_api.core.cache.get_provider()

    for index in [0, 1, 2, 3]:
        if index in expected_selection:
            assert provider[sources[index]] is True
        else:
            assert provider[sources[index]] is False

def test_watchlist_add():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'profile', { 'type': 'watchlist_add', 'id': 'tt8111088' })
    assert fn.results is True

    fn = __invoke(a4kstreaming_api, 'profile', { 'type': 'watchlist_add', 'ids': 'tt8111088__tt7126948' })
    assert fn.results is True

def test_watchlist_remove():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'profile', { 'type': 'watchlist_remove', 'id': 'tt8111088' })
    assert fn.results is True

    fn = __invoke(a4kstreaming_api, 'profile', { 'type': 'watchlist_remove', 'ids': 'tt8111088__tt7126948' })
    assert fn.results is True

def test_rate_rate():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    def select(*args, **kwargs): return 1
    a4kstreaming_api.core.kodi.xbmcgui.Dialog().select = select
    fn = __invoke(a4kstreaming_api, 'profile', { 'type': 'rate', 'id': 'tt8111088' })

    assert fn.results is True

def test_rate_unrate():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    def select(*args, **kwargs): return 0
    a4kstreaming_api.core.kodi.xbmcgui.Dialog().select = select
    fn = __invoke(a4kstreaming_api, 'profile', { 'type': 'rate', 'id': 'tt8111088' })

    assert fn.results is True

def test_mark_as_watched():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'profile', { 'type': 'mark_as_watched', 'id': 'tt2011749' })

    assert fn.results is True

def test_mark_as_unwatched():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'profile', { 'type': 'mark_as_unwatched', 'id': 'tt2011749' })

    assert fn.results is True

def test_season_mark_as_watched():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'profile', { 'type': 'mark_as_watched', 'ids': 'tt3676824__tt3676822__tt3676826__tt3676830__tt3676828__tt3676832__tt3676836__tt3676834__tt3676844__tt3676840__tt3676846__tt3676848' })

    assert fn.results is True

def test_season_mark_as_unwatched():
    a4kstreaming_api = api.A4kStreamingApi({'kodi': True})

    fn = __invoke(a4kstreaming_api, 'profile', { 'type': 'mark_as_unwatched', 'ids': 'tt3676824__tt3676822__tt3676826__tt3676830__tt3676828__tt3676832__tt3676836__tt3676834__tt3676844__tt3676840__tt3676846__tt3676848' })

    assert fn.results is True
