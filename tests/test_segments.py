# -*- coding: utf-8 -*-
# Offline tests for intro / recap skip and the next episode: the segment lookup (mocked HTTP), the Skip decisions and
# countdown, and the player Watch over a fake player (ui/skip.py).

import datetime
import importlib
import json
from .common import pytest, api

@pytest.fixture(scope='module')
def core():
    return api.A4kStreamingApi({'kodi': True}).core

@pytest.fixture(scope='module')
def segments(core):
    return importlib.import_module('a4kStreaming.segments')

@pytest.fixture(scope='module')
def skip(core):
    return importlib.import_module('a4kStreaming.ui.skip')

MAP = {
    'tt0000001': [[100, 1, 1], [200, 2, 2]],
    'tt0000002': [[300, 1, 1], [301, 1, 1]],  # one season split over two MAL ids
    'tt0000003': [[400, None, 2]],  # tvdb has no season: tmdb's
}

class Http(object):
    # get_json double: url substring -> body, or an exception to raise; every url asked is logged
    def __init__(self, answers):
        self.answers, self.asked = answers, []

    def __call__(self, url):
        self.asked.append(url)
        for part, answer in self.answers.items():
            if part in url:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        return None

class Db(object):
    def __init__(self):
        self.data, self.ages = {}, {}

    def get(self, key): return self.data.get(key, {})
    def age(self, key): return self.ages.get(key)

    def set(self, key, value):
        self.data[key], self.ages[key] = value, 0

def aniskip(*results):
    return {'found': True, 'results': [{'interval': {'startTime': s, 'endTime': e}, 'skipType': t, 'episodeLength': n}
                                       for t, s, e, n in results]}

# lookup: anime

def test_mal_for_picks_one_mal_id_tvdb_first_then_tmdb(segments):
    assert segments.mal_for('tt0000001', 2, MAP) == 200
    assert segments.mal_for('tt0000002', 1, MAP) is None
    assert segments.mal_for('tt0000003', 2, MAP) == 400
    assert segments.mal_for('tt0000001', 3, MAP) is None
    assert segments.mal_for('tt9999999', 1, MAP) is None

def test_shipped_anime_map_loads(segments):
    mapping = segments.anime_map()
    assert len(mapping) > 1000
    assert all(isinstance(row, list) and len(row) == 3 for rows in mapping.values() for row in rows)

def test_anime_answers_from_the_anime_database_only(segments):
    http = Http({'aniskip': aniskip(('op', 80.5, 170, 1420.2), ('recap', 0, 40, 1420.2), ('mixed-ed', 1300, 1390, 1420.2))})
    body, ttl = segments.fetch('tt0000001', 2, 7, http, MAP)
    assert http.asked == [segments.ANIME_URL % (200, 7)]
    assert body == {'intro': {'start': 80.5, 'end': 170, 'confident': True}, 'recap': {'start': 0, 'end': 40, 'confident': True},
                    'credits': {'start': 1300, 'confident': True}, 'length': 1420.2}
    assert ttl == segments.HIT_TTL

def test_anime_miss_and_split_seasons_ask_the_tv_databases(segments):
    http = Http({'aniskip': {'results': []}, 'introdb.app': {'intro': {'start_sec': 10, 'end_sec': 70, 'submission_count': 5}}})
    body, _ = segments.fetch('tt0000001', 1, 3, http, MAP)
    assert len(http.asked) == 3 and body['intro'] == {'start': 10, 'end': 70, 'confident': True}
    http = Http({})
    segments.fetch('tt0000002', 1, 3, http, MAP)
    assert not any('aniskip' in url for url in http.asked) and len(http.asked) == 2
    assert segments.INTRODB_URL % 'imdb_id=tt0000002&season=1&episode=3' in http.asked

# lookup: TV databases, merge and the confident rule

def tv(segments, introdb, theintrodb):
    return segments.fetch('tt0000009', 1, 2, Http({'introdb.app': introdb, 'theintrodb.org': theintrodb}), MAP)[0]

def test_two_databases_agreeing_within_three_seconds_are_confident(segments):
    body = tv(segments, {'intro': {'start_sec': 60, 'end_sec': 120, 'submission_count': 1}},
              {'intro': [{'start_ms': 62500, 'end_ms': 117000}]})
    assert body['intro'] == {'start': 60, 'end': 120, 'confident': True}
    body = tv(segments, {'intro': {'start_sec': 60, 'end_sec': 120, 'submission_count': 1}},
              {'intro': [{'start_ms': 60000, 'end_ms': 124000}]})
    assert body['intro']['confident'] is False

def test_three_introdb_submissions_are_confident_alone(segments):
    assert tv(segments, {'recap': {'start_sec': 0, 'end_sec': 30, 'submission_count': 3}}, None)['recap']['confident'] is True
    assert tv(segments, {'recap': {'start_sec': 0, 'end_sec': 30, 'submission_count': 2}}, None)['recap']['confident'] is False

def test_theintrodb_alone_is_never_confident_and_its_closest_candidate_is_compared(segments):
    assert tv(segments, None, {'intro': [{'start_ms': 1000, 'end_ms': 50000}]})['intro'] == {'start': 1, 'end': 50, 'confident': False}
    body = tv(segments, {'intro': {'start_sec': 300, 'end_sec': 360, 'submission_count': 0}},
              {'intro': [{'start_ms': 0, 'end_ms': 40000}, {'start_ms': 301000, 'end_ms': 359000}]})
    assert body['intro'] == {'start': 300, 'end': 360, 'confident': True}

def test_credits_merge_open_ended_and_length_is_null(segments):
    body = tv(segments, {'outro': {'start_sec': 1300, 'end_sec': None, 'submission_count': 0}},
              {'credits': [{'start_ms': 1302000, 'end_ms': None}]})
    assert body['credits'] == {'start': 1300, 'confident': True} and body['length'] is None
    # introdb open-ended, theintrodb complete: theintrodb is the base, and its times are not vouched for by the count
    body = tv(segments, {'intro': {'start_sec': 50, 'end_sec': None, 'submission_count': 9}},
              {'intro': [{'start_ms': 58000, 'end_ms': 110000}]})
    assert body['intro'] == {'start': 58, 'end': 110, 'confident': False}

def test_bad_segments_are_dropped(segments):
    body = tv(segments, {'intro': {'start_sec': 'x'}, 'recap': {'start_sec': 40, 'end_sec': 20}},
              {'intro': [{'start_ms': 9000, 'end_ms': 3000}], 'credits': 'nope'})
    assert body == segments.EMPTY

def test_ttl_short_on_an_error_a_day_on_nothing(segments):
    _, ttl = segments.fetch('tt0000009', 1, 2, Http({'introdb.app': IOError('timeout')}), MAP)
    assert ttl == segments.ERR_TTL
    _, ttl = segments.fetch('tt0000009', 1, 2, Http({}), MAP)
    assert ttl == segments.MISS_TTL

def test_lookup_caches_and_never_raises(segments):
    db = Db()
    http = Http({'introdb.app': {'intro': {'start_sec': 10, 'end_sec': 70, 'submission_count': 4}}})
    first = segments.lookup(db, 'tt0000009', 1, 2, http, MAP)
    assert segments.lookup(db, 'tt0000009', 1, 2, http, MAP) == first and len(http.asked) == 2
    db.ages['segments_tt0000009_1_2'] = segments.HIT_TTL + 1
    segments.lookup(db, 'tt0000009', 1, 2, http, MAP)
    assert len(http.asked) == 4
    # an errored answer is kept only for ERR_TTL
    db = Db()
    segments.lookup(db, 'tt0000009', 1, 2, Http({'theintrodb': IOError('down')}), MAP)
    assert json.loads(db.data['segments_tt0000009_1_2'])['ttl'] == segments.ERR_TTL
    assert segments.lookup(Db(), 'tt0000009', 1, 2, Http({'introdb.app': {'intro': 'garbage'}}), {'tt0000009': 'bad'}) == segments.EMPTY

def test_get_json_errors_raise_and_a_404_is_nothing(segments, monkeypatch):
    requests = importlib.import_module('requests')

    class Response(object):
        def __init__(self, status, body=None):
            self.status_code, self.ok, self.body = status, 200 <= status < 300, body

        def json(self):
            return self.body

    seen = {}

    def get(url, timeout=None, headers=None):
        seen['timeout'] = timeout
        return responses.pop(0)

    responses = [Response(200, {'a': 1}), Response(404), Response(500), Response(429)]
    monkeypatch.setattr(requests, 'get', get)
    assert segments.get_json('u') == {'a': 1} and seen['timeout'] == 3
    assert segments.get_json('u') is None
    for _ in range(2):
        with pytest.raises(IOError):
            segments.get_json('u')

# next episode

def episode(id, s, e, date=(2020, 1, 1)):
    return {'id': id, 'series': {'seasonNumber': s, 'episodeNumber': e}, 'releaseDate': dict(zip(('year', 'month', 'day'), date))}

def test_next_episode_is_the_first_released_one_after(segments):
    today = datetime.date(2024, 6, 1)
    eps = [episode('tt3', 2, 1), episode('tt1', 1, 1), episode('tt2', 1, 2), episode('tt0', 0, 5), episode('tt9', 2, 2, (2030, 1, 1))]
    assert segments.next_episode(eps, 1, 1, today) == 'tt2'
    assert segments.next_episode(eps, 1, 2, today) == 'tt3'
    assert segments.next_episode(eps, 2, 1, today) is None
    assert segments.next_episode([{'id': 'x'}, None], 1, 1, today) is None

# Skip: auto-skip and button decisions (the player reference cases)

DUR = 1430.0

def model(segments, confident=True, length=None, intro='auto', recap='auto', credits='auto', has_next=True):
    found = {'intro': {'start': 83.0, 'end': 114.0, 'confident': confident}, 'recap': {'start': 0.0, 'end': 41.5, 'confident': confident},
             'credits': {'start': 1380.0, 'confident': True}, 'length': length}
    return segments.Skip(found, {'intro': intro, 'recap': recap, 'credits': credits}, has_next)

def test_confident_auto_skips_once_with_the_label(segments):
    m = model(segments)
    t = m.tick(90, DUR, True, 0)
    assert (t.seek_to, t.toast, t.button) == (114.0, 'intro', None)
    t = m.tick(5, DUR, True, 0.5)
    assert (t.seek_to, t.toast) == (41.5, 'recap')

def test_seeking_back_into_a_skipped_segment_shows_the_button(segments):
    m = model(segments)
    m.tick(84, DUR, True, 0)
    m.tick(114, DUR, True, 0.5)
    t = m.tick(85, DUR, True, 1)
    assert (t.seek_to, t.toast, t.button, t.button_seek) == (None, None, 'intro', 114.0)

def test_not_confident_shows_the_button_in_auto_mode(segments):
    t = model(segments, confident=False).tick(90, DUR, True, 0)
    assert (t.seek_to, t.button) == (None, 'intro')

def test_button_mode_never_auto_skips(segments):
    t = model(segments, intro='button', recap='button').tick(10, DUR, True, 0)
    assert (t.seek_to, t.button, t.button_seek) == (None, 'recap', 41.5)

def test_off_mode_shows_nothing(segments):
    m = model(segments, intro='off', recap='off', credits='off')
    for pos in (10, 90, 1400):
        t = m.tick(pos, DUR, True, 0)
        assert (t.seek_to, t.button) == (None, None)

def test_the_segment_ends_one_second_before_its_end(segments):
    m = model(segments, intro='button', recap='button')
    assert m.tick(82.9, DUR, True, 0).button is None
    assert m.tick(83, DUR, True, 0).button == 'intro'
    assert m.tick(112.9, DUR, True, 0).button == 'intro'
    assert m.tick(113, DUR, True, 0).button is None

def test_length_within_twenty_seconds_auto_skips_outside_shows_the_button(segments):
    assert model(segments, length=1450.0).tick(90, DUR, True, 0).seek_to == 114.0
    assert model(segments, length=1410.0).tick(90, DUR, True, 0).seek_to == 114.0
    far = model(segments, length=1451.0).tick(90, DUR, True, 0)
    assert (far.seek_to, far.button) == (None, 'intro')
    # a length with the duration still unknown cannot be checked: the button, not a blind skip
    unknown = model(segments, length=1430.0).tick(90, -1, True, 0)
    assert (unknown.seek_to, unknown.button) == (None, 'intro')
    # a null length trusts the times whatever the duration
    assert model(segments).tick(90, 3000, True, 0).seek_to == 114.0

def test_intro_from_the_start_auto_skips_whatever_the_length(segments):
    at0 = segments.Skip({'intro': {'start': 0, 'end': 90, 'confident': True}, 'length': 1375.374}, {'intro': 'auto'}, False)
    t = at0.tick(0.5, 1428.3, True, 0)
    assert (t.seek_to, t.button) == (90, None)
    at30 = segments.Skip({'intro': {'start': 30, 'end': 120, 'confident': True}, 'length': 1375.374}, {'intro': 'auto'}, False)
    t = at30.tick(31, 1428.3, True, 0)
    assert (t.seek_to, t.button) == (None, 'intro')

def test_absent_modes_default_to_auto_and_missing_credits_give_nothing(segments):
    m = segments.Skip({'intro': {'start': 83, 'end': 114, 'confident': True}, 'recap': None, 'credits': None, 'length': None}, {}, True)
    assert m.tick(90, DUR, True, 0).seek_to == 114
    assert m.tick(1400, DUR, True, 0).button is None

# Skip: the next episode countdown

def test_credits_auto_counts_down_ten_seconds_then_fires_once(segments):
    m = model(segments)
    assert m.tick(1379, DUR, True, 0).button is None
    t = m.tick(1380, DUR, True, 1)
    assert (t.button, t.button_seek, t.countdown) == ('next', None, 10) and m.countdown_active()
    t = m.tick(1385, DUR, True, 6.5)
    assert (t.countdown, t.fire_next) == (5, False)
    t = m.tick(1390, DUR, True, 11)
    assert (t.countdown, t.fire_next) == (0, True)
    assert m.tick(1391, DUR, True, 11.5).fire_next is False

def test_cancelling_the_countdown_keeps_the_button(segments):
    m = model(segments)
    m.tick(1380, DUR, True, 0)
    m.cancel_countdown()
    assert not m.countdown_active()
    t = m.tick(1395, DUR, True, 20)
    assert (t.button, t.countdown, t.fire_next) == ('next', None, False)

def test_a_paused_countdown_holds(segments):
    m = model(segments)
    m.tick(1380, DUR, True, 0)
    m.tick(1381, DUR, False, 5)
    t = m.tick(1381, DUR, False, 60)
    assert (t.countdown, t.fire_next) == (10, False)
    assert m.tick(1382, DUR, True, 63).countdown == 7

def test_credits_button_mode_shows_no_countdown(segments):
    t = model(segments, credits='button').tick(1400, DUR, True, 0)
    assert (t.button, t.countdown, t.fire_next) == ('next', None, False)

def test_credits_without_a_next_episode_give_nothing(segments):
    m = model(segments, has_next=False)
    assert m.tick(1400, DUR, True, 0).button is None
    assert m.tick(1420, DUR, True, 20).fire_next is False and not m.countdown_active()

@pytest.mark.parametrize('back', [90, 500])
def test_leaving_the_credits_resets_the_countdown_on_every_path(segments, back):
    m = model(segments)
    assert m.tick(1380, DUR, True, 0).countdown == 10
    assert m.tick(1384, DUR, True, 4).countdown == 6
    m.tick(back, DUR, True, 4.5)
    assert not m.countdown_active()
    m.tick(back + 1, DUR, True, 5)
    t = m.tick(1380, DUR, True, 20)
    assert (t.fire_next, t.countdown) == (False, 10)

def test_the_natural_end_during_a_running_countdown_is_next_episode(segments):
    m = model(segments)
    assert not m.next_on_natural_end()
    m.tick(1379, DUR, True, 0)
    assert not m.next_on_natural_end()
    m.tick(1425, DUR, True, 0.5)
    assert m.next_on_natural_end()
    cancelled = model(segments)
    cancelled.tick(1425, DUR, True, 0)
    cancelled.cancel_countdown()
    assert not cancelled.next_on_natural_end()
    for mode in ('button', 'off'):
        plain = model(segments, credits=mode)
        plain.tick(1425, DUR, True, 0)
        assert not plain.next_on_natural_end()
    last = model(segments, has_next=False)
    last.tick(1425, DUR, True, 0)
    assert not last.next_on_natural_end()

# the player side (ui/skip.py) over a fake player

class Player(object):
    def __init__(self, pos=0.0, total=DUR):
        self.pos, self.total, self.seeks = pos, total, []

    def getTime(self): return self.pos
    def getTotalTime(self): return self.total

    def seekTime(self, pos):
        self.seeks.append(pos)
        self.pos = pos

@pytest.fixture
def watch(core, segments, skip, monkeypatch):
    log = {'builtins': [], 'notices': [], 'next': 0}
    monkeypatch.setattr(core.kodi.xbmc, 'executebuiltin', lambda builtin, wait=False: log['builtins'].append(builtin))
    monkeypatch.setattr(core.kodi.xbmc, 'getCondVisibility', lambda cond: log.get(cond, False), raising=False)
    monkeypatch.setattr(skip.kodi, 'notification', lambda text, time=3000: log['notices'].append(text))
    monkeypatch.setattr(skip.Button, 'show', lambda self: log.__setitem__('shown', self.getProperty('a4k.label')))
    monkeypatch.setattr(skip.Button, 'close', lambda self: log.__setitem__('shown', None))

    def make(**kwargs):
        w = skip.Watch(core, Player(), None, {'id': 'tt1', 'tvshowid': 'tt0', 'season': 1, 'episode': 1},
                       on_next=lambda: log.__setitem__('next', log['next'] + 1))
        w.model, w.next_id, w.log = model(segments, **kwargs), 'tt2', log
        return w
    return make

class Action(object):
    def __init__(self, id): self.id = id
    def getId(self): return self.id

def test_watch_auto_skips_with_a_notice(watch):
    w = watch()
    w.player.pos = 90
    w.step(0)
    assert w.player.seeks == [114.0] and w.log['notices'] == ['Skipped intro'] and not w.log.get('shown')

def test_watch_button_shows_and_a_press_seeks(watch, skip):
    w = watch(intro='button')
    w.player.pos = 90
    w.step(0)
    assert w.log['shown'] == 'Skip intro'
    w.window.onClick(skip.BUTTON)
    w.step(0.5)
    assert w.player.seeks == [114.0] and w.log['shown'] is None

def test_watch_back_dismisses_the_intro_button_until_it_leaves(watch, skip):
    w = watch(intro='button')
    w.player.pos = 90
    w.step(0)
    w.window.onAction(Action(skip.ACTION_NAV_BACK))
    w.step(0.5)
    assert w.log['shown'] is None and w.player.seeks == []
    w.step(1)
    assert w.log['shown'] is None
    w.player.pos = 200
    w.step(1.5)
    w.player.pos = 90
    w.step(2)
    assert w.log['shown'] == 'Skip intro'

def test_watch_hides_under_the_osd(watch):
    w = watch(intro='button')
    w.player.pos = 90
    w.log['Window.IsVisible(videoosd)'] = True
    w.step(0)
    assert not w.log.get('shown')

def test_watch_countdown_label_fires_next_once(watch, skip):
    w = watch()
    w.player.pos = 1380
    w.step(0)
    assert w.log['shown'] == 'Next episode in 10'
    w.step(10)
    assert w.log['builtins'] == ['PlayMedia(%s?action=play&type=&id=tt2&next=1,noresume)' % skip.app.PLUGIN] and w.log['next'] == 1
    w.ended()
    assert len(w.log['builtins']) == 1 and w.log['next'] == 1

def test_watch_key_cancels_the_countdown_and_press_plays_next(watch, skip):
    w = watch()
    w.player.pos = 1380
    w.step(0)
    w.window.onAction(Action(1))  # left
    w.step(1)
    assert w.window.getProperty('a4k.label') == 'Next episode' and w.log['shown'] and not w.model.countdown_active()
    w.ended()
    assert w.log['builtins'] == []
    w = watch()
    w.player.pos = 1380
    w.step(0)
    w.window.onClick(skip.BUTTON)
    w.step(0.5)
    assert len(w.log['builtins']) == 1 and w.log['next'] == 1

def test_watch_back_hides_the_next_button_and_cancels_the_countdown(watch, skip):
    # the pill consumes Back: the first hides it, so the next one reaches the video (Back stops playback)
    w = watch()
    w.player.pos = 1380
    w.step(0)
    w.window.onAction(Action(skip.ACTION_NAV_BACK))
    w.step(0.5)
    assert w.log['shown'] is None and not w.model.countdown_active()
    w.ended()
    assert w.log['builtins'] == []

def test_watch_pause_does_not_cancel_and_the_natural_end_plays_next(watch, skip):
    w = watch()
    w.player.pos = 1380
    w.step(0)
    w.window.onAction(Action(12))  # pause
    w.log['Player.Paused'] = True
    w.step(30)
    assert w.log['shown'] == 'Next episode in 10' and w.model.countdown_active()
    w.ended()
    assert len(w.log['builtins']) == 1

def test_hand_off_and_take(core, skip):
    DictAsObject = core.utils.DictAsObject
    skip.hand_off(DictAsObject({'mediatype': 'episode', 'imdbnumber': 'tt5', 'tvshowid': 'tt4', 'season': 2, 'episode': 3}))
    assert skip.take() == {'id': 'tt5', 'tvshowid': 'tt4', 'season': 2, 'episode': 3}
    assert skip.take() == {}
    skip.hand_off(DictAsObject({'mediatype': 'movie', 'imdbnumber': 'tt6'}))
    assert skip.take() == {}
    assert skip.start(core, None, None, {}) is None

def test_modes_follow_the_settings_and_default_to_auto(core, skip, monkeypatch):
    values = {'general.skip_intro': '1', 'general.skip_recap': '2'}
    monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: values.get(key, ''))
    assert skip.modes() == {'intro': 'button', 'recap': 'off', 'credits': 'auto'}
