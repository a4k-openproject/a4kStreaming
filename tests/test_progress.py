# -*- coding: utf-8 -*-
# Continue Watching (#029): the progress store, the service's Back stops playback rule, the row's listing, the episode
# cards' resume bars, the resume choice of a play and the home row's wiring.

import importlib
from .common import pytest, api
from .utils import Spawned

PLUGIN = 'plugin://plugin.video.a4kstreaming/'
EPISODE = {'mediatype': 'episode', 'imdbnumber': 'tt92', 'tvshowid': 'tt1', 'season': 1, 'episode': 2,
           'title': '2. The Second', 'tvshowtitle': 'A Show', 'poster': 'still.jpg', 'year': 2022}
MOVIE = {'mediatype': 'movie', 'imdbnumber': 'tt5', 'title': 'A Film', 'poster': 'poster.jpg', 'year': 2015}

@pytest.fixture(scope='module')
def core():
    core = api.A4kStreamingApi({'kodi': True}).core
    core.url = PLUGIN
    return core

@pytest.fixture
def progress(core, progress_store):
    return progress_store

@pytest.fixture
def items(core, monkeypatch):
    added = []
    monkeypatch.setattr(core.kodi.xbmcplugin, 'addDirectoryItems', lambda handle, items, n=0: added.extend(items))
    monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: '')
    return added

# A. the store

def test_entries_are_keyed_by_ids_not_urls(progress):
    episode, movie = progress.meta(EPISODE), progress.meta(MOVIE)
    assert progress.key(episode) == 'tt1:1:2' and progress.key(movie) == 'tt5'
    assert episode['title'] == 'The Second' and episode['show_title'] == 'A Show' and episode['art'] == 'still.jpg'
    assert progress.meta(dict(EPISODE, tvshowid=None)) is None  # an episode without its show cannot be keyed

@pytest.mark.parametrize('pos, shown', [(0, False), (60, True), (5640, True), (5700, False)])
def test_in_progress_is_1_to_94_percent(progress, pos, shown):
    assert progress.in_progress({'pos': pos, 'dur': 6000}) is shown

def test_record_keeps_watched_and_finishes_at_the_end(progress):
    meta = progress.meta(EPISODE)
    store = progress.record({}, meta, 600, 3000, 100)
    assert progress.in_progress(store['tt1:1:2']) and not store['tt1:1:2']['watched']
    store = progress.record(store, meta, 2000, 3000, 200, finished=True)  # the next episode from the credits
    assert store['tt1:1:2']['pos'] == 3000 and store['tt1:1:2']['watched'] and not progress.in_progress(store['tt1:1:2'])
    store = progress.record(store, meta, 300, 3000, 300)  # watched again: in the row, still watched
    assert progress.in_progress(store['tt1:1:2']) and store['tt1:1:2']['watched']
    assert progress.watched_episodes(store, 'tt1') == {'tt92'}

def test_listing_is_the_latest_first_and_prune_drops_the_old(progress):
    store = progress.record({}, progress.meta(MOVIE), 600, 6000, 100)
    store = progress.record(store, progress.meta(EPISODE), 600, 3000, 200)
    store['done'] = {'pos': 10, 'dur': 10, 't': 300}
    assert [progress.key(e) for e in progress.listing(store)] == ['tt1:1:2', 'tt5']
    assert list(progress.prune(store, 100 + progress.MAX_AGE)) == ['done', 'tt1:1:2']

def test_save_load_remove_and_stamp(progress):
    assert progress.load() == {} and progress.stamp() == '0'
    progress.save({'tt5': {'pos': 1, 'dur': 2}})
    assert progress.load() == {'tt5': {'pos': 1, 'dur': 2}} and progress.stamp() != '0'
    progress.remove('tt5')
    assert progress.load() == {}
    with open(progress.PATH, 'w') as f:
        f.write('{half')
    assert progress.load() == {}  # unreadable: empty

def test_a_corrupt_store_is_moved_aside_not_wiped_by_the_next_save(progress):
    with open(progress.PATH, 'w') as f:
        f.write('{"tt5": {"pos": 1, "dur": 2}}{"tt')
    assert progress.load() == {}
    progress.save({'tt7': {'pos': 1, 'dur': 2}})
    with open(progress.PATH + '.bad') as f:
        assert f.read() == '{"tt5": {"pos": 1, "dur": 2}}{"tt'
    assert progress.load() == {'tt7': {'pos': 1, 'dur': 2}}

def test_two_writers_never_share_a_temp_file(progress, monkeypatch):
    # Kodi runs every interpreter in one process: a save that starts while another is mid-way gets a temp file of its own,
    # so both renames land and the store stays whole
    import os
    replace, nested = os.replace, []
    def interleaved(src, dst):
        if not nested:
            nested.append(src)
            progress.save({'b': {'pos': 1, 'dur': 2}})
        replace(src, dst)
    monkeypatch.setattr(os, 'replace', interleaved)
    progress.save({'a': {'pos': 1, 'dur': 2}})
    assert progress.load() == {'a': {'pos': 1, 'dur': 2}}
    assert [n for n in os.listdir(os.path.dirname(progress.PATH)) if n.endswith('.tmp')] == []

def test_a_failed_save_leaves_the_store_and_no_temp_file(progress, monkeypatch):
    import os
    progress.save({'a': {'pos': 1, 'dur': 2}})
    def fail(src, dst):
        raise OSError('disk full')
    with monkeypatch.context() as patch:
        patch.setattr(os, 'replace', fail)
        progress.save({'b': {'pos': 1, 'dur': 2}})
    assert progress.load() == {'a': {'pos': 1, 'dur': 2}}
    assert sorted(os.listdir(os.path.dirname(progress.PATH))) == ['progress.json']

# B. Back stops playback (service.BackStop)

@pytest.fixture
def service(core):
    return importlib.import_module('a4kStreaming.service')

HOME, VIDEO, SCREENSAVER = 10000, 12005, 12900

def steps(service, windows, enabled=True):
    back = service.BackStop()
    return [back.step(window, enabled) for window in windows]

def test_the_osd_or_a_dialog_over_the_video_keeps_playing(service):
    # the OSD, the info and the skip button are dialogs: the video window stays the current one
    assert not any(steps(service, [VIDEO, VIDEO, VIDEO, VIDEO]))

def test_leaving_the_video_for_the_windows_stops(service):
    assert steps(service, [HOME, VIDEO, HOME, HOME, HOME]) == [False, False, False, True, False]

def test_the_setting_off_keeps_kodis_behaviour(service):
    assert not any(steps(service, [VIDEO, HOME, HOME, HOME], enabled=False))

def test_a_play_still_loading_and_the_screensaver_never_stop(service):
    assert not any(steps(service, [HOME, HOME, HOME]))  # the video window never showed yet
    assert not any(steps(service, [VIDEO, SCREENSAVER, SCREENSAVER, VIDEO, HOME]))  # one look away is not two

# B2. Resume from (service.Resume)

def test_the_resume_seeks_once_and_keeps_the_old_position_until_the_play_is_there(service):
    resume = service.Resume(3000)
    assert resume.step(True, 0, 6000, 100) and resume.start == 3000
    assert not resume.step(True, 2, 6000, 105) and resume.start == 3000  # still buffering at the new position
    assert not resume.step(True, 2996, 6000, 108) and resume.start == 0  # landed: the play counts from here

def test_a_seek_that_never_lands_lets_the_play_count_after_a_while(service):
    resume = service.Resume(3000)
    resume.step(True, 0, 6000, 100)
    assert not resume.step(True, 20, 6000, 100 + service.SEEK_WAIT) and resume.start == 3000
    assert not resume.step(True, 21, 6000, 101 + service.SEEK_WAIT) and resume.start == 0

@pytest.mark.parametrize('total', [None, 0])
def test_a_stream_of_unknown_length_still_seeks(service, total):
    # getTotalTime can throw or read 0 on the first poll, even with Player.HasDuration
    resume = service.Resume(3000)
    assert resume.step(True, 0, total, 100) and resume.start == 3000

@pytest.mark.parametrize('same,total', [(False, 6000), (True, 3020), (True, 2900)])
def test_no_seek_for_another_title_or_past_the_new_streams_end(service, same, total):
    # another source of the title can be a shorter cut: a seek past its end would end the play as finished
    resume = service.Resume(3000)
    assert not resume.step(same, 0, total, 100) and resume.start == 0

# C. the row's listing and the episode cards

def test_continue_watching_lists_the_store(core, progress, items):
    store = progress.record({}, progress.meta(MOVIE), 600, 6000, 100)
    progress.save(progress.record(store, progress.meta(EPISODE), 1500, 3000, 200))
    importlib.import_module('a4kStreaming.listing').continue_watching(core)
    (episode_url, episode, folder), (movie_url, movie, _) = items
    assert episode.label == 'A Show' and episode.resume == (1500.0, 3000.0) and not folder
    assert episode.properties['a4k.type'] == 'tvSeries' and episode.properties['a4k.id'] == 'tt1'
    assert episode.properties['a4k.at'] == '1:2' and episode.properties['a4k.meta'] == 'S1 E2 · The Second'
    assert episode.art['thumb'] == 'still.jpg' and episode_url == PLUGIN + '?action=play&type=&id=tt92'
    assert movie.label == 'A Film' and movie.properties['a4k.type'] == 'movie' and movie.properties['a4k.at'] == ''
    assert movie.properties['a4k.meta'] == '2015' and movie_url == PLUGIN + '?action=play&type=&id=tt5'

def test_core_routes_the_row_uncached(core, progress, items, monkeypatch):
    ends = []
    monkeypatch.setattr(core.kodi.xbmcplugin, 'endOfDirectory', lambda handle, cacheToDisc=True, **k: ends.append(cacheToDisc), raising=False)
    monkeypatch.setattr(core.request, 'revalidate', lambda core: None)
    core.main(PLUGIN, 1, 'action=continue&widget=1&t=0')
    assert items == [] and ends == [False]

def an_episode(number, rating=None):
    return {'id': 'tt9%s' % number, 'titleType': 'tvEpisode', 'titleText': 'Chapter %s' % number, 'primaryImage': None,
            'userRating': rating, 'series': {'seasonNumber': 1, 'episodeNumber': number},
            'releaseDate': {'year': 2022, 'month': 2, 'day': number}}

def test_episode_cards_carry_the_stores_resume_point_and_watched(core, progress, items):
    store = progress.record({}, progress.meta(dict(EPISODE, episode=1, imdbnumber='tt91')), 900, 3000, 100)
    progress.save(progress.record(store, progress.meta(EPISODE), 3000, 3000, 200))
    title = {'id': 'tt1', 'titleText': 'A Show', 'episodes': {'seasons': [1], 'episodes': [an_episode(1), an_episode(2), an_episode(3)]}}
    importlib.import_module('a4kStreaming.listing').__dict__['__add_episodes'](core, title, 1)
    first, second, third = [item for _, item, _ in items]
    assert first.resume == (900.0, 3000.0) and second.resume is None and third.resume is None
    assert [label for label, _ in first.context_menu][1] == 'Reset resume progress'
    assert 'key=tt1%3A1%3A1' in dict(first.context_menu)['Reset resume progress']
    assert 'Reset resume progress' not in dict(second.context_menu)

def test_reset_resume_clears_the_entry(core, progress, monkeypatch):
    monkeypatch.setattr(core.kodi, 'json_rpc', lambda *a, **k: None)
    progress.save({'tt1:1:1': {'pos': 1, 'dur': 2}, 'tt5': {'pos': 1, 'dur': 2}})
    core.main(PLUGIN, 1, 'action=reset_resume&path=p&key=tt1%3A1%3A1')
    assert list(progress.load()) == ['tt5']

# D. the resume choice and the hand-off

@pytest.fixture
def playback(core):
    return importlib.import_module('a4kStreaming.playback')

def test_resume_or_start_over(core, progress, playback, monkeypatch):
    entry = progress.meta(EPISODE)
    progress.save(progress.record({}, entry, 754, 3000, 100))
    asked = []
    answer = [0]
    monkeypatch.setattr(playback.sheets, 'select', lambda heading, labels: asked.append((heading, labels)) or answer[0])
    assert playback.resume_from(core, entry, False) == 754
    assert asked == [('A Show · S1 E2', ['Resume from 12:34', 'Start over'])]
    answer[0] = 1
    assert playback.resume_from(core, entry, False) == 0
    answer[0] = -1
    assert playback.resume_from(core, entry, False) is None  # Back: no play
    assert playback.resume_from(core, entry, True) == 0 and len(asked) == 3  # the next episode never asks
    assert playback.resume_from(core, progress.meta(MOVIE), False) == 0 and len(asked) == 3  # nothing in progress

def test_the_hand_off_carries_the_entry(core):
    skip = importlib.import_module('a4kStreaming.ui.skip')
    title = core.utils.DictAsObject(EPISODE)
    skip.hand_off(title, {'id': 'tt92'})
    assert skip.take() == {'id': 'tt92', 'tvshowid': 'tt1', 'season': 1, 'episode': 2, 'progress': {'id': 'tt92'}}
    skip.hand_off(core.utils.DictAsObject(MOVIE), {'id': 'tt5'})
    assert skip.take() == {'progress': {'id': 'tt5'}}

# E. the home row

@pytest.fixture
def home(core):
    return importlib.import_module('a4kStreaming.ui.home')

def test_the_row_has_its_own_toggle_on_by_default(core, home, monkeypatch):
    values = {}
    monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: values.get(key, ''))
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    home.apply(window)
    assert window.getProperty('a4k.row.308') == PLUGIN + '?action=continue&widget=1&t=0'
    assert 'continue' not in str(window.sources)  # never a top shelf source
    assert all('continue' not in type for type in importlib.import_module('a4kStreaming.ui.appearance').public_types())
    values['appearance.continue_watching'] = 'false'
    home.apply(window)
    assert window.getProperty('a4k.row.308') == ''

def test_a_card_opens_the_detail_at_its_episode(core, home, monkeypatch):
    detail = importlib.import_module('a4kStreaming.ui.detail')
    opened = []
    monkeypatch.setattr(detail, 'open', lambda info: opened.append(info))
    labels = {'Container(308).ListItem.Property(a4k.type)': 'tvSeries', 'Container(308).ListItem.Property(a4k.id)': 'tt1',
              'Container(308).ListItem.Property(a4k.at)': '1:2'}
    monkeypatch.setattr(core.kodi.xbmc, 'getInfoLabel', lambda label: labels.get(label, ''))
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    window.setFocusId(home.CONTINUE)
    window.onAction(type('A', (), {'getId': lambda self: home.ACTION_SELECT_ITEM})())
    assert opened[0]['Property(a4k.id)'] == 'tt1' and detail.at(opened[0]) == (1, 2)
    assert detail.at({}) is None

def test_the_row_reloads_on_return_only_when_the_store_moved(core, home, progress, monkeypatch):
    threads, sleeps, media = Spawned(run=False), [], []
    monkeypatch.setattr(home, 'spawn', threads)
    monkeypatch.setattr(home.kodi.xbmc, 'getCondVisibility', lambda cond: cond == 'Player.HasMedia' and bool(media and media.pop()))
    monkeypatch.setattr(home.kodi.xbmcgui, 'getCurrentWindowId', lambda: window.own_id)
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    home.apply(window)
    window.onInit()
    monkeypatch.setattr(window.stopped, 'wait', lambda seconds: sleeps.append(seconds) or False)  # never stopped
    threads.clear()  # the top shelf's rotation
    window.onInit()  # back, nothing played
    assert threads == []
    progress.save({'tt5': {'pos': 1, 'dur': 2}})
    window.onInit()  # back from a play
    assert [t.target for t in threads] == [window.reload_continue]
    media[:] = [True, True]  # Back from the video: the player stops a moment after the window shows
    window.reload_continue()
    assert sleeps == [home.PLAYER_LOOK, home.PLAYER_LOOK, home.CONTINUE_SETTLE]
    assert window.getProperty('a4k.row.308') == PLUGIN + '?action=continue&widget=1&t=' + progress.stamp()

class Stopped(object):
    # a window's stopped Event whose waits are recorded and return at once
    def __init__(self, stopped, waits): self.stopped, self.waits = stopped, waits
    def wait(self, seconds): return self.waits.append(seconds) or self.stopped

def test_after_play_gives_up_on_a_player_that_stays_or_a_closed_window(home, monkeypatch):
    waits = []
    monkeypatch.setattr(home.kodi.xbmc, 'getCondVisibility', lambda cond: True)
    assert home.after_play(Stopped(False, waits)) is False and sum(waits) == home.PLAYER_WAIT
    assert home.after_play(Stopped(True, waits)) is False
    monkeypatch.setattr(home.kodi.xbmc, 'getCondVisibility', lambda cond: False)
    assert home.after_play(Stopped(False, waits)) is True and home.after_play(Stopped(True, waits)) is False
