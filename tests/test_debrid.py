# -*- coding: utf-8 -*-
# Offline tests for the Debrid window (a4k-debrid.xml, ui/debrid.py) and action=cloud (cloud.py): the status chips and
# progress, the refresh schedule, the in-place row diffing that keeps the focus, the Ready toast, errors and the
# missing key, the Cloud rows and play URL, and the requests (key-bearing reads never cached, writes POSTed).

import os
import re
import json
import importlib
from types import SimpleNamespace
from xml.etree import ElementTree
from .common import pytest, api

ROOT = os.path.join(os.path.dirname(__file__), '..')
XML = os.path.join(ROOT, 'resources', 'skins', 'Default', '1080i', 'a4k-debrid.xml')
NOW = 1_800_000_000

@pytest.fixture(scope='module')
def core():
    return api.A4kStreamingApi({'kodi': True}).core

@pytest.fixture
def debrid(core):
    return importlib.import_module('a4kStreaming.ui.debrid')

@pytest.fixture(autouse=True)
def clean(core, monkeypatch):
    properties = importlib.import_module('a4kStreaming.lib.kodi_mock')._window_properties
    properties.clear()
    monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: 'test-key' if key == 'premiumize.apikey' else '')
    yield
    properties.clear()

def transfer(id, status, progress=None, name=None, **extra):
    return dict({'id': id, 'name': name or 'Item %s' % id, 'status': status, 'progress': progress, 'message': ''}, **extra)

# A. chips, progress, rows

@pytest.mark.parametrize('status,label', [
    ('queued', 'Queued'), ('running', 'Downloading'), ('waiting', 'Downloading'), ('seeding', 'Downloading'),
    ('finished', 'Finished'), ('error', 'Error'), ('timeout', 'Error'), ('deleted', 'Error'), ('banned', 'banned'),
    (None, ''),
])
def test_status_chips(debrid, status, label):
    assert debrid.chip(status) == label

@pytest.mark.parametrize('item,pct', [
    (transfer(1, 'running', 0.425), 43), (transfer(1, 'running', 0.005), 1), (transfer(1, 'running', 0), 0),
    (transfer(1, 'running', None), 0), (transfer(1, 'finished', None), 100), (transfer(1, 'finished', 1), 100),
    (transfer(1, 'running', 'bad'), 0), (transfer(1, 'running', 1.7), 100),
])
def test_progress_is_a_whole_percent_and_finished_without_one_is_done(debrid, item, pct):
    assert debrid.percent(item) == pct

def test_transfer_row(debrid):
    row = debrid.transfer_row(transfer(7, 'seeding', 0.5, message='Seeding', folder_id='f', file_id=None))
    assert row == {'id': '7', 'label': 'Item 7', 'chip': 'Downloading', 'state': 'downloading', 'pct': 50,
                   'msg': 'Seeding', 'folder': 'f', 'file': ''}
    assert debrid.transfer_row(transfer(8, 'banned'))['state'] == 'other'

def test_ready_toast_only_on_a_transition_to_finished(debrid):
    rows = [debrid.transfer_row(t) for t in (transfer(1, 'finished'), transfer(2, 'finished'), transfer(3, 'running', 0.1))]
    assert debrid.ready(None, rows) == []  # the first refresh announces nothing
    assert debrid.ready({'1': 'Downloading', '2': 'Finished', '3': 'Queued'}, rows) == ['Item 1']
    assert debrid.ready({}, rows) == []  # one that shows up already finished is not news

def test_account_header(debrid):
    assert debrid.account({'premium_until': NOW + 86400 * 41.5, 'limit_used': 0.125, 'space_used': 3 * 1024 ** 3}, NOW) \
        == ('Premium  ·  42 days left', False, 13, '3.0 GB stored')
    assert debrid.account({'premium_until': NOW + 3600, 'limit_used': 0}, NOW)[0] == 'Premium  ·  1 day left'
    assert debrid.account({'premium_until': False}, NOW) == ('Expired', True, None, '')
    assert debrid.account({'premium_until': NOW - 10, 'space_used': 5 * 1024 ** 2}, NOW) == ('Expired', True, None, '5 MB stored')

def test_cloud_rows_newest_first_with_kinds(debrid):
    content = [
        {'id': 'a', 'name': 'Old.mkv', 'type': 'file', 'size': 2 * 1024 ** 3, 'created_at': 100},
        {'id': 'b', 'name': 'New folder', 'type': 'folder', 'created_at': 300},
        {'id': 'c', 'name': 'notes.txt', 'type': 'file', 'size': 1024 ** 2, 'created_at': 200},
    ]
    rows = debrid.cloud_rows(content, ['MKV', 'MP4'])
    assert [(row['id'], row['kind']) for row in rows] == [('b', 'folder'), ('c', 'file'), ('a', 'video')]
    assert rows[0]['meta'] == 'Folder  ›' and rows[2]['meta'].startswith('2.0 GB  ·  ')

def test_breadcrumb(debrid):
    assert debrid.crumb({'name': 'root', 'parent_id': None}) == 'Cloud'
    crumbs = [{'id': 'r', 'name': 'root', 'parent_id': None}, {'id': 'm', 'name': 'Movies', 'parent_id': 'r'}]
    assert debrid.crumb({'name': 'Movies', 'parent_id': 'r', 'breadcrumbs': crumbs}) == 'Cloud  ›  Movies'
    assert debrid.crumb({'name': 'Extras', 'parent_id': 'm', 'breadcrumbs': crumbs}) == 'Cloud  ›  Movies  ›  Extras'
    assert debrid.crumb({'name': 'Extras', 'parent_id': 'm'}) == 'Cloud  ›  Extras'

# B. the refresh schedule

def test_schedule_runs_at_once_in_view_then_fast_while_active_and_slow_when_idle(debrid):
    schedule = debrid.Schedule()
    assert schedule.due(0, True)
    schedule.done(0, active=True)
    assert not schedule.due(1.9, True) and schedule.due(2, True)
    schedule.done(2, active=False)
    assert not schedule.due(16.9, True) and schedule.due(17, True)

def test_schedule_stops_while_hidden_and_refreshes_on_return(debrid):
    schedule = debrid.Schedule()
    schedule.due(0, True)
    schedule.done(0, active=False)
    assert not schedule.due(100, False)  # covered: no refresh however late
    assert schedule.due(100.25, True)  # back in view: at once, not at the next tick of the old period
    schedule.done(100.25, active=True)
    assert not schedule.due(101, True)
    schedule.soon()
    assert schedule.due(101, True)

# C. row diffing

def rows_of(*ids, **pct):
    return [{'id': id, 'label': id, 'pct': pct.get(id, 0)} for id in ids]

def test_diff_repaints_only_changed_rows(debrid):
    assert debrid.diff(rows_of('a', 'b', 'c'), rows_of('a', 'b', 'c', b=40), 'b') == ([1], 0, 1)
    assert debrid.diff(rows_of('a', 'b'), rows_of('a', 'b'), 'a') == ([], 0, 0)

def test_diff_follows_the_focused_id_when_a_row_comes_or_goes(debrid):
    # a new transfer on top: every slot repaints, one item is added at the end, focus moves down with its transfer
    assert debrid.diff(rows_of('a', 'b'), rows_of('n', 'a', 'b'), 'a') == ([0, 1, 2], 1, 1)
    # the row above went away: one item fewer, focus moves up with it
    assert debrid.diff(rows_of('a', 'b', 'c'), rows_of('b', 'c'), 'c') == ([0, 1], -1, 1)
    # the focused row went away
    assert debrid.diff(rows_of('a', 'b'), rows_of('a'), 'b') == ([], -1, None)

class FakeTag(object):
    def __init__(self):
        self.resume = None

    def setResumePoint(self, time, total):
        self.resume = (time, total)

class FakeItem(object):
    def __init__(self, label='', offscreen=True, **kwargs):
        self.label, self.label2, self.properties, self.tag = label, '', {}, FakeTag()

    def setLabel(self, label):
        self.label = label

    def setLabel2(self, label):
        self.label2 = label

    def setProperty(self, key, value):
        self.properties[key] = value

    def getProperty(self, key):
        return self.properties.get(key, '')

    def getVideoInfoTag(self):
        return self.tag

class FakeList(object):
    def __init__(self):
        self.items, self.position, self.resets = [], 0, 0

    def addItems(self, items):
        self.items.extend(items)

    def removeItem(self, index):
        self.items.pop(index)

    def reset(self):
        self.resets += 1
        self.items = []

    def size(self):
        return len(self.items)

    def getSelectedPosition(self):
        return self.position if self.items else -1

    def selectItem(self, index):
        self.position = index

    def getListItem(self, index):
        return self.items[index]

    def setPercent(self, percent):
        self.percent = percent

@pytest.fixture
def window(core, debrid, monkeypatch):
    monkeypatch.setattr(core.kodi.xbmcgui, 'ListItem', FakeItem)
    monkeypatch.setattr(debrid.Debrid, 'poll', lambda self: None)
    monkeypatch.setattr(debrid.Debrid, 'load_cloud_later', lambda self, folder, back_to=None, focus=False: self.load_cloud(folder, back_to, focus))
    window = debrid.Debrid('a4k-debrid.xml', '', 'Default', '1080i')
    for id in (debrid.TABS, debrid.DOWNLOADS, debrid.CLOUD, debrid.FAIR_USE):
        window.controls[id] = FakeList()
    window.onInit()
    assert window.error is None
    return window

def test_rows_update_in_place_and_keep_the_focused_transfer(debrid, window):
    downloads = window.getControl(debrid.DOWNLOADS)
    window.apply(debrid.DOWNLOADS, [debrid.transfer_row(t) for t in (transfer(1, 'running', 0.1), transfer(2, 'queued'))])
    downloads.selectItem(1)  # the user is on transfer 2
    first = list(downloads.items)
    window.apply(debrid.DOWNLOADS, [debrid.transfer_row(t) for t in (transfer(9, 'queued'), transfer(1, 'running', 0.5), transfer(2, 'running', 0.2))])
    assert downloads.resets == 0 and downloads.items[:2] == first  # the same ListItems, repainted
    assert [item.label for item in downloads.items] == ['Item 9', 'Item 1', 'Item 2']
    assert downloads.position == 2  # still on transfer 2
    assert downloads.items[1].label2 == '50%' and downloads.items[1].tag.resume == (50, 100)
    assert downloads.items[0].tag.resume == (0.01, 100)  # 0 %: never quite 0, so Kodi redraws the bar
    window.apply(debrid.DOWNLOADS, [debrid.transfer_row(transfer(9, 'queued'))])
    assert downloads.resets == 0 and downloads.size() == 1 and downloads.position == 0

def test_empty_list_hands_the_focus_to_the_tabs(debrid, window):
    window.apply(debrid.DOWNLOADS, [debrid.transfer_row(transfer(1, 'finished'))])
    window.setFocusId(debrid.DOWNLOADS)
    window.apply(debrid.DOWNLOADS, [])
    assert window.getFocusId() == debrid.TABS and window.getProperty('a4k.empty.200') == 'true'

# D. refresh: Premiumize answers, fails, or there is no key

class Premiumize(object):
    # answers by endpoint; records every request with the cache argument it was made with
    def __init__(self, answers):
        self.answers, self.requests = answers, []

    def __call__(self, core, request, cache=True, stale_ok=False):
        self.requests.append((request, cache))
        endpoint = re.search(r'/api/([\w/]+)', request['url']).group(1)
        answer = self.answers.get(endpoint, {'status': 'success'})
        if isinstance(answer, list):
            answer = answer.pop(0)
        return SimpleNamespace(status_code=200 if answer is not None else 500,
                               content=json.dumps(answer) if answer is not None else '')

@pytest.fixture
def toasts(core, debrid, monkeypatch):
    log = []
    monkeypatch.setattr(debrid.kodi, 'notification', lambda text, time=3000: log.append(text))
    return log

def test_refresh_paints_header_and_rows_and_toasts_ready(core, debrid, window, monkeypatch, toasts):
    server = Premiumize({
        'account/info': {'status': 'success', 'premium_until': 4102444800, 'limit_used': 0.3, 'space_used': 1024 ** 3},
        'transfer/list': [{'status': 'success', 'transfers': [transfer(1, 'running', 0.9)]},
                          {'status': 'success', 'transfers': [transfer(1, 'finished')]}],
    })
    monkeypatch.setattr(core.request, 'execute', server)
    assert window.refresh() is True  # one is downloading: the fast period
    assert window.getProperty('a4k.fairuse') == '30%' and window.getControl(debrid.FAIR_USE).percent == 30
    assert window.getProperty('a4k.account').endswith('days left') and window.getProperty('a4k.storage') == '1.0 GB stored'
    assert toasts == []
    assert window.refresh() is False
    assert toasts == ['Ready: Item 1'] and window.getProperty('a4k.finished') == 'true'
    assert len([r for r, _ in server.requests if 'account/info' in r['url']]) == 1  # the account once, not every poll
    assert all(cache is False for _, cache in server.requests)

def test_a_failed_refresh_keeps_the_list_and_shows_retry(core, debrid, window, monkeypatch):
    server = Premiumize({'transfer/list': [{'status': 'success', 'transfers': [transfer(1, 'running', 0.2)]}, None,
                                           {'status': 'error', 'message': 'Not logged in.'}]})
    monkeypatch.setattr(core.request, 'execute', server)
    window.refresh()
    assert window.refresh() is False
    assert window.getProperty('a4k.banner') == debrid.UNREACHABLE and window.getProperty('a4k.banner.act') == 'Retry'
    assert [item.label for item in window.getControl(debrid.DOWNLOADS).items] == ['Item 1']
    window.refresh()
    assert window.getProperty('a4k.banner') == 'Premiumize: Not logged in.'
    window.schedule.next = 99
    window.banner_click()
    assert window.schedule.next == 0 and window.account_due

def test_no_key_shows_the_settings_hint(core, debrid, window, monkeypatch):
    monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: '')
    server = Premiumize({})
    monkeypatch.setattr(core.request, 'execute', server)
    ran = []
    monkeypatch.setattr(debrid.home, 'run', ran.append)
    assert window.refresh() is False and server.requests == []
    assert window.getProperty('a4k.banner') == debrid.NO_KEY and window.getProperty('a4k.banner.act') == 'Open Settings'
    window.banner_click()
    assert ran == ['RunScript(plugin.video.a4kstreaming,settings)']

def test_window_hidden_under_a_dialog_or_the_loader(core, debrid, window, monkeypatch):
    monkeypatch.setattr(core.kodi.xbmcgui, 'getCurrentWindowId', lambda: window.own_id)
    assert window.visible()
    monkeypatch.setattr(core.kodi.xbmcgui, 'getCurrentWindowDialogId', lambda: 10138)
    assert not window.visible()

def test_over_a_play_call_the_loader_does_not_hide_it_and_play_waits(core, debrid, window, monkeypatch, toasts):
    # Open Downloads from the uncached wait: the play call's loader stamp is live the whole time
    monkeypatch.setattr(core.kodi.xbmcgui, 'getCurrentWindowId', lambda: window.own_id)
    monkeypatch.setattr(debrid.kodi, 'busy_live', lambda: True)
    assert not window.visible()
    window.over_call = True
    assert window.visible()
    ran = []
    monkeypatch.setattr(debrid.home, 'run', ran.append)
    window.play('f1')
    assert ran == [] and toasts == ['Go back and pick the source again to play it']

# E. actions

def test_finished_transfer_opens_its_folder_or_plays_its_file(core, debrid, window, monkeypatch):
    ran, picks = [], []
    monkeypatch.setattr(debrid.home, 'run', ran.append)
    monkeypatch.setattr(debrid, 'select', lambda heading, labels: picks.append(labels) or 0)
    monkeypatch.setattr(core.request, 'execute', Premiumize({'folder/list': {'status': 'success', 'content': [], 'parent_id': 'r'}}))
    window.transfer_actions(debrid.transfer_row(transfer(1, 'finished', file_id='f1')))
    assert ran == ['PlayMedia(plugin://plugin.video.a4kstreaming/?action=cloud&type=play&id=f1)']
    window.transfer_actions(debrid.transfer_row(transfer(2, 'finished', folder_id='d2', file_id='f2')))
    assert window.tab == debrid.CLOUD and window.folder == 'd2' and window.parent == 'r'
    window.transfer_actions(debrid.transfer_row(transfer(3, 'running', 0.4)))
    assert picks == [['Play', 'Delete'], ['Open in Cloud', 'Delete'], ['Delete']]

def test_delete_asks_first_then_posts(core, debrid, window, monkeypatch):
    server = Premiumize({})
    monkeypatch.setattr(core.request, 'execute', server)
    monkeypatch.setattr(debrid, 'select', lambda heading, labels: labels.index('Delete'))
    answers = [False, True]
    monkeypatch.setattr(debrid, 'confirm', lambda heading, yes: answers.pop(0))
    row = debrid.transfer_row(transfer(5, 'running', 0.4))
    window.transfer_actions(row)
    assert server.requests == []  # Cancel deletes nothing
    window.transfer_actions(row)
    request, _ = server.requests[0]
    assert request['method'] == 'POST' and request['url'].endswith('/transfer/delete?apikey=test-key') and request['data'] == {'id': '5'}

def test_cloud_click_opens_folders_plays_videos_and_back_goes_up(core, debrid, window, monkeypatch):
    ran = []
    monkeypatch.setattr(debrid.home, 'run', ran.append)
    root = {'status': 'success', 'name': 'root', 'content': [{'id': 'm', 'name': 'Movies', 'type': 'folder', 'created_at': 2},
                                                            {'id': 'v', 'name': 'Clip.mp4', 'type': 'file', 'created_at': 1}]}
    movies = {'status': 'success', 'name': 'Movies', 'parent_id': 'r', 'content': []}
    server = Premiumize({'folder/list': [root, movies, root]})
    monkeypatch.setattr(core.request, 'execute', server)
    window.show_tab(debrid.CLOUD)
    cloud = window.getControl(debrid.CLOUD)
    assert [item.label for item in cloud.items] == ['Movies', 'Clip.mp4']
    cloud.selectItem(1)
    window.onClick(debrid.CLOUD)
    assert ran == ['PlayMedia(plugin://plugin.video.a4kstreaming/?action=cloud&type=play&id=v)']
    cloud.selectItem(0)
    window.onClick(debrid.CLOUD)
    assert window.getProperty('a4k.crumb') == 'Cloud  ›  Movies' and window.getProperty('a4k.empty.300') == 'true'
    window.back(debrid.CLOUD)
    assert window.folder == 'r' and window.getControl(debrid.CLOUD).position == 0  # back on Movies
    assert 'includebreadcrumbs=true' in server.requests[0][0]['url'] and all(cache is False for _, cache in server.requests)

def test_close_waits_for_the_window_threads(core, debrid, monkeypatch):
    # a window freed on its own thread crashed Kodi 21 (SIGSEGV on close): open() joins them first
    import threading
    monkeypatch.setattr(core.kodi.xbmcgui, 'ListItem', FakeItem)
    gate, done = threading.Event(), []
    def poll(self):
        gate.wait(5)
        done.append(True)
    def modal(window):
        for id in (debrid.TABS, debrid.DOWNLOADS, debrid.CLOUD, debrid.FAIR_USE):
            window.controls[id] = FakeList()
        window.onInit()
        threading.Timer(0.1, gate.set).start()  # the refresh still running as the window closes
    monkeypatch.setattr(debrid.Debrid, 'poll', poll)
    monkeypatch.setattr(debrid.home, 'modal', modal)
    debrid.open()
    assert done == [True] and not debrid.LEFT_OVER

def test_fair_use_bar_comes_back_after_playback(debrid, window):
    window.paint_account({'status': 'success', 'premium_until': 0, 'limit_used': 0.5, 'space_used': 0})
    window.controls[debrid.FAIR_USE] = FakeList()  # the XML reloaded on return
    window.onInit()
    assert window.getControl(debrid.FAIR_USE).percent == 50

# F. action=cloud

@pytest.fixture
def cloud(core):
    return importlib.import_module('a4kStreaming.cloud')

def test_cloud_play_hands_the_link_with_its_subtitles_to_kodi(core, cloud, monkeypatch):
    server = Premiumize({
        'item/details': {'status': 'success', 'id': 'v', 'name': 'Clip.mkv', 'folder_id': 'd',
                         'link': 'https://cdn.example.com/Clip.mkv', 'stream_link': 'https://cdn.example.com/Clip.m3u8'},
        'folder/list': {'status': 'success', 'content': [
            {'name': 'Clip.mkv', 'link': 'https://cdn.example.com/Clip.mkv'},
            {'name': 'Clip.en.srt', 'link': 'https://cdn.example.com/Clip.en.srt'},
            {'name': 'Other.srt', 'link': 'https://cdn.example.com/Other.srt'}]},
    })
    monkeypatch.setattr(core.request, 'execute', server)
    items, subs = [], []
    monkeypatch.setattr(core.utils, 'end_action', lambda core, ok, item=None: items.append((ok, item)))
    real = core.kodi.xbmcgui.ListItem

    def listitem(*args, **kwargs):
        item = real(*args, **kwargs)
        item.path = kwargs.get('path')
        item.setSubtitles = subs.extend
        return item
    monkeypatch.setattr(core.kodi.xbmcgui, 'ListItem', listitem)
    assert cloud.play(core, 'v') is True
    ok, item = items[0]
    assert ok and item.path == 'https://cdn.example.com/Clip.mkv'
    assert subs == ['https://cdn.example.com/Clip.en.srt']
    assert all(cache is False for _, cache in server.requests)

def test_cloud_play_failure_resolves_nothing(core, cloud, monkeypatch, toasts):
    monkeypatch.setattr(core.request, 'execute', Premiumize({'item/details': {'status': 'error', 'message': 'Not found'}}))
    items = []
    monkeypatch.setattr(core.utils, 'end_action', lambda core, ok, item=None: items.append(ok))
    monkeypatch.setattr(core.kodi, 'notification', toasts.append)
    assert cloud.play(core, 'v') is False and items == [False] and toasts == ['Premiumize: Not found']

@pytest.mark.parametrize('type,id,opened', [
    ('root', None, ('cloud', '')), ('premiumize_files', 'abc', ('cloud', 'abc')), ('premiumize_transfers', None, ('downloads', '')),
])
def test_old_cloud_urls_open_the_window(core, cloud, debrid, monkeypatch, type, id, opened):
    log = []
    monkeypatch.setattr(core.kodi.xbmcplugin, 'endOfDirectory', lambda handle, succeeded=True, **kwargs: log.append(('end', succeeded)), raising=False)
    monkeypatch.setattr(debrid, 'open', lambda tab, folder: log.append((tab, folder)))
    params = core.utils.DictAsObject({'type': type, 'id': id})
    assert cloud.cloud(core, params) == core.skip_end_of_dir
    assert log == [('end', False), opened]

# G. the window's XML and its entry

def test_python_ids_exist_with_types_kodi_can_wrap(debrid):
    types = {int(c.get('id')): c.get('type') for c in ElementTree.parse(XML).iter('control') if c.get('id')}
    assert types == {debrid.TABS: 'list', debrid.CLEAR: 'button', debrid.BANNER: 'button', debrid.DOWNLOADS: 'list',
                     debrid.CLOUD: 'list', debrid.FAIR_USE: 'progress'}

def test_every_property_the_xml_reads_is_set(debrid):
    text = open(XML).read()
    source = open(debrid.__file__).read()
    for name in set(re.findall(r'(?:Window|ListItem)\.Property\((a4k\.[\w.]+|on)[,)]', text)):
        if name.startswith('a4k.empty.'):
            name = 'a4k.empty.'
        assert "'%s" % name in source, name

def test_the_tile_opens_the_window(core, monkeypatch):
    home = importlib.import_module('a4kStreaming.ui.home')
    xml = open(os.path.join(ROOT, 'resources', 'skins', 'Default', '1080i', 'a4k-home.xml')).read()
    assert '<property name="a4k.grid">debrid</property>' in xml and 'action=cloud' not in xml
    opened = []
    monkeypatch.setattr(importlib.import_module('a4kStreaming.ui.debrid'), 'open', lambda: opened.append(True))
    monkeypatch.setattr(core.kodi.xbmc, 'getInfoLabel', lambda label: 'debrid' if label.endswith('Property(a4k.grid)') else '')
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    window.setFocusId(home.TILES)
    window.onAction(SimpleNamespace(getId=lambda: home.ACTION_SELECT_ITEM))
    assert opened == [True] and window.error is None
