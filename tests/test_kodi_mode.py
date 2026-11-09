# -*- coding: utf-8 -*-
# Offline tests for Kodi setup mode (a4kStreaming/kodi_mode.py) over a fake Kodi: turning it on records only what it
# changes, drift, restore, reset to defaults, the favourite toggle, the keymap and its skip, the one-time question,
# the service's auto-open and Back on the home window's top menu.

import json
import types
import importlib
from .common import pytest, api

DEFAULTS = {'audiooutput.guisoundmode': 1, 'lookandfeel.enablerssfeeds': False, 'general.addonnotifications': False,
            'lookandfeel.skin': 'skin.estuary'}

@pytest.fixture(scope='module')
def core():
    return api.A4kStreamingApi({'kodi': True}).core

@pytest.fixture
def mode(core, tmp_path, monkeypatch):
    mode = importlib.import_module('a4kStreaming.kodi_mode')
    monkeypatch.setattr(mode, 'PATH', str(tmp_path / 'profile' / 'kodi_mode.json'))
    monkeypatch.setattr(mode, 'keymaps', lambda: str(tmp_path / 'keymaps'))
    monkeypatch.setattr(core.kodi, 'notification', lambda text, time=3000: None)
    return mode

class Kodi(object):
    # Kodi's settings, the current skin's bools, the favourites and every builtin, as the mode sees them
    def __init__(self, mode):
        self.mode = mode
        self.settings = dict(DEFAULTS, **{'lookandfeel.enablerssfeeds': True})
        self.bools = {'homemenunomoviebutton'}
        self.favourites = []
        self.builtins = []
        self.calls = []
        self.conditions = {}

    def rpc(self, request):
        request = json.loads(request)
        method, params = request['method'], request['params']
        self.calls.append(method)
        if method.startswith('Settings.Set') or method.startswith('Favourites.Add'):
            assert self.mode.active()  # the file is written before the first change
        if method == 'Settings.GetSettingValue':
            return json.dumps({'result': {'value': self.settings[params['setting']]}})
        if method == 'Settings.SetSettingValue':
            self.settings[params['setting']] = params['value']
            return json.dumps({'result': True})
        if method == 'Settings.ResetSettingValue':
            self.settings[params['setting']] = DEFAULTS[params['setting']]
            return json.dumps({'result': 'OK'})
        if method == 'Favourites.GetFavourites':
            return json.dumps({'result': {'favourites': [{'type': 'script', 'path': path} for path in self.favourites] or None}})
        if method == 'Favourites.AddFavourite':  # a toggle, as Kodi's
            path = params['path']
            self.favourites.remove(path) if path in self.favourites else self.favourites.append(path)
            return json.dumps({'result': 'OK'})
        raise AssertionError(method)

    def builtin(self, builtin, wait=False):
        self.builtins.append(builtin)
        if builtin.startswith('Skin.SetBool('):
            name, value = builtin[13:-1].split(',')
            self.bools.add(name.lower()) if value == 'true' else self.bools.discard(name.lower())
        elif builtin.startswith('Skin.Reset('):
            self.bools.discard(builtin[11:-1].lower())

    def condition(self, condition):
        if condition.startswith('Skin.HasSetting('):
            return condition[16:-1].lower() in self.bools
        return self.conditions.get(condition, False)

@pytest.fixture
def fake(core, mode, monkeypatch):
    kodi = Kodi(mode)
    monkeypatch.setattr(core.kodi.xbmc, 'executeJSONRPC', kodi.rpc)
    monkeypatch.setattr(core.kodi.xbmc, 'executebuiltin', kodi.builtin)
    monkeypatch.setattr(core.kodi.xbmc, 'getCondVisibility', kodi.condition)
    return kodi

def turn_on(mode):
    return mode.apply(mode.plan())

# A. turning it on

def test_turning_on_records_only_what_it_changes(mode, fake, tmp_path):
    state = turn_on(mode)
    assert state['kodi'] == {'audiooutput.guisoundmode': {'was': 1, 'set': 0}, 'lookandfeel.enablerssfeeds': {'was': True, 'set': False}}
    assert fake.settings['audiooutput.guisoundmode'] == 0 and fake.settings['lookandfeel.enablerssfeeds'] is False
    assert 'HomeMenuNoMovieButton' not in state['skin_bools'] and len(state['skin_bools']) == 10  # Favourites stays shown
    assert fake.bools == set(name.lower() for name in mode.HIDE)
    assert fake.favourites == ['plugin.video.a4kstreaming'] and state['favourite'] and state['keymap']
    keymap = (tmp_path / 'keymaps' / 'a4kstreaming.xml').read_text()
    assert '<FullscreenVideo>' in keymap and '<backspace>Stop</backspace>' in keymap and 'VideoOSD' not in keymap
    assert 'Action(reloadkeymaps)' in fake.builtins and fake.builtins[-1] == 'Skin.Reset(a4k.kodi_mode)'  # saved to disk
    assert mode.load() == state and mode.status() == 'Active'

def test_the_sheet_lists_each_change(mode, fake):
    lines = [label for label, _ in mode.lines(mode.plan())]
    assert lines == ['Opens a4kStreaming when Kodi starts', "Back on a4kStreaming's home asks first", 'Menu sounds off',
                     'News ticker off', "Kodi's home menu shows only Favourites", 'a4kStreaming in your Kodi favourites',
                     'Back stops any video, also outside a4kStreaming', 'Your current values are saved']

def test_another_skin_keeps_its_menu_and_the_sheet_says_so(mode, fake):
    fake.settings['lookandfeel.skin'] = 'skin.other'
    state = turn_on(mode)
    assert state['skin_bools'] == {} and fake.bools == {'homemenunomoviebutton'}
    assert ('Home menu: needs the Estuary skin', 'Left as it is') in mode.lines(dict(mode.plan(), estuary=False))

def test_a_favourite_already_there_is_neither_added_nor_removed(mode, fake):
    fake.favourites = ['plugin.video.a4kstreaming']
    assert not turn_on(mode)['favourite'] and fake.favourites == ['plugin.video.a4kstreaming']
    mode.restore()
    assert fake.favourites == ['plugin.video.a4kstreaming']

def test_a_change_kodi_refused_is_not_recorded(mode, fake, monkeypatch):
    rpc = fake.rpc
    monkeypatch.setattr(mode.kodi.xbmc, 'executeJSONRPC', lambda request: json.dumps({'error': {'code': -32602}})
                        if 'enablerssfeeds' in request and 'SetSettingValue' in request else rpc(request))
    monkeypatch.setattr(mode.logger, 'error', lambda message: None)
    assert list(turn_on(mode)['kodi']) == ['audiooutput.guisoundmode'] and mode.status() == 'Active'

# B. drift, restore, reset

def test_restore_puts_back_what_was_and_keeps_what_the_user_changed_since(mode, fake, tmp_path):
    turn_on(mode)
    fake.settings['audiooutput.guisoundmode'] = 2  # the user changed it since
    fake.bools.discard('homemenunovideosbutton')
    assert mode.status() == 'Active, 2 changed since'
    assert [label for label, _ in mode.drift(mode.load())] == ['Menu sounds off', 'Home menu: Videos']
    kept = mode.restore()
    assert len(kept) == 2 and fake.settings['audiooutput.guisoundmode'] == 2 and fake.settings['lookandfeel.enablerssfeeds'] is True
    assert fake.bools == {'homemenunomoviebutton'}  # hidden before the mode, hidden after it
    assert fake.favourites == [] and not (tmp_path / 'keymaps' / 'a4kstreaming.xml').exists()
    assert fake.builtins[-2:] == ['Action(reloadkeymaps)', 'Skin.Reset(a4k.kodi_mode)']
    assert not mode.active() and mode.status() == 'Off'

def test_restore_skips_the_menu_after_a_skin_change(mode, fake):
    turn_on(mode)
    fake.settings['lookandfeel.skin'] = 'skin.other'
    before = set(fake.bools)
    mode.restore()
    assert fake.bools == before

def test_a_write_cut_short_keeps_the_saved_originals(mode, fake, monkeypatch):
    import os
    state = turn_on(mode)
    with monkeypatch.context() as patch:
        patch.setattr(os, 'replace', lambda src, dst: (_ for _ in ()).throw(OSError('killed')))
        with pytest.raises(OSError):
            mode.write({})
    assert mode.load() == state and os.listdir(os.path.dirname(mode.PATH)) == ['kodi_mode.json']

def test_an_unreadable_file_reads_active_not_off(mode, fake):
    turn_on(mode)
    open(mode.PATH, 'w').close()
    assert mode.status() == 'Active (saved values unreadable)'

def test_reset_sets_every_managed_value_to_kodis_default(mode, fake, tmp_path):
    turn_on(mode)
    fake.settings['general.addonnotifications'] = True  # not changed by the mode, still one it manages
    mode.reset_defaults()
    assert {id: fake.settings[id] for id in mode.KODI} == {id: DEFAULTS[id] for id in mode.KODI}
    assert fake.calls.count('Settings.ResetSettingValue') == 3
    assert fake.bools == set() and fake.favourites == [] and not (tmp_path / 'keymaps' / 'a4kstreaming.xml').exists()
    assert not mode.active()

# C. the keymap

def keymap(tmp_path, name, body):
    folder = tmp_path / 'keymaps'
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(body)

@pytest.mark.parametrize('body,taken', [
    ('<keymap><FullscreenVideo><keyboard><backspace>Back</backspace></keyboard></FullscreenVideo></keymap>', True),
    ('<keymap><fullscreenvideo><remote><back>Stop</back></remote></fullscreenvideo></keymap>', True),
    ('<keymap><FullscreenVideo><joystick profile="game.controller.default"><b>Back</b></joystick></FullscreenVideo></keymap>', True),
    ('<keymap><FullscreenVideo><keyboard><b>Bookmarks</b></keyboard></FullscreenVideo></keymap>', False),
    ('<keymap><VideoOSD><keyboard><backspace>Back</backspace></keyboard></VideoOSD></keymap>', False),
    ('<keymap><FullscreenVideo>', True),  # unreadable: left alone
])
def test_a_users_back_mapping_in_the_video_skips_the_keymap(mode, fake, tmp_path, body, taken):
    keymap(tmp_path, 'mine.xml', body)
    assert mode.keymap_taken() is taken
    state = turn_on(mode)
    assert state['keymap'] is not taken and (tmp_path / 'keymaps' / 'a4kstreaming.xml').exists() is not taken
    if taken:
        assert ('Back in videos: left as it is', 'A keymap of yours already sets it') in mode.lines(dict(state, estuary=True))
        assert 'Action(reloadkeymaps)' not in fake.builtins

def test_our_own_keymap_is_not_a_users(mode, fake, tmp_path):
    keymap(tmp_path, 'a4kstreaming.xml', mode.KEYMAP_XML)
    assert not mode.keymap_taken()

# D. the sheets

def test_the_row_turns_it_on_after_the_confirm_and_off_with_restore_or_reset(mode, fake, core, monkeypatch):
    sheets = importlib.import_module('a4kStreaming.ui.sheets')
    asked, answers = [], [1, 0, 2, 0]  # Cancel, Turn on, (on) Cancel, Restore
    def select(heading, labels, preselect=-1, rows=None, actions=0):
        asked.append((heading, actions))
        return answers.pop(0)
    monkeypatch.setattr(sheets, 'select', select)
    mode.sheet()
    assert not mode.active()
    mode.sheet()
    assert mode.active()
    mode.sheet()
    assert mode.active()
    mode.sheet()
    assert not mode.active()
    assert asked == [('Set up Kodi for a4kStreaming', 2)] * 2 + [('Kodi setup mode', 3)] * 2

@pytest.mark.parametrize('position,choice', [(3, -1), (1, 1)])
def test_info_rows_of_a_sheet_do_nothing_on_ok(core, monkeypatch, position, choice):
    sheets = importlib.import_module('a4kStreaming.ui.sheets')
    closed = []
    def doModal(self):  # OK on the row at position
        self.close = lambda: closed.append(True)
        self.getControl = lambda id: types.SimpleNamespace(getSelectedPosition=lambda: position)
        self.onClick(sheets.LIST)
    monkeypatch.setattr(sheets.Sheet, 'doModal', doModal)
    assert sheets.select('Set up', ['a', 'b', 'c', 'd'], actions=2) == choice and closed == ([True] if choice != -1 else [])

# E. the one-time question

@pytest.fixture
def values(core, monkeypatch):
    values = {}
    monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: values.get(key, ''))
    monkeypatch.setattr(core.kodi.addon, 'setSetting', lambda key, value: values.__setitem__(key, value), raising=False)
    return values

@pytest.fixture
def home(core, monkeypatch):
    home = importlib.import_module('a4kStreaming.ui.home')
    monkeypatch.setattr(home.Home, 'rotate', lambda self: None)
    return home

def asking(home, monkeypatch, idle=True, playing=False):
    ran = []
    monkeypatch.setattr(home, 'run', ran.append)
    monkeypatch.setattr(home, 'playing', lambda: playing)
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    monkeypatch.setattr(window, 'idle', lambda: idle)
    return window, ran

def test_the_question_is_asked_once(mode, values, home, monkeypatch):
    window, ran = asking(home, monkeypatch)
    window.ask_kodi_mode()
    window.ask_kodi_mode()
    assert ran == ['RunScript(plugin.video.a4kstreaming,kodi_mode_prompt)']

@pytest.mark.parametrize('idle,playing', [(False, False), (True, True)])
def test_the_question_waits_for_no_dialog_and_no_play(mode, values, home, monkeypatch, idle, playing):
    window, ran = asking(home, monkeypatch, idle, playing)
    window.ask_kodi_mode()
    assert ran == [] and not window.asked

def test_the_question_is_not_asked_when_asked_before_or_with_the_mode_on(mode, fake, values, home, monkeypatch):
    values['kodi_mode.prompted'] = 'true'
    window, ran = asking(home, monkeypatch)
    window.ask_kodi_mode()
    values.clear()
    turn_on(mode)
    window.ask_kodi_mode()
    assert ran == []

@pytest.mark.parametrize('answer,on', [(0, True), (1, False), (-1, False)])
def test_either_answer_marks_it_asked_and_set_it_up_opens_the_confirm(mode, fake, values, monkeypatch, answer, on):
    sheets = importlib.import_module('a4kStreaming.ui.sheets')
    answers = [answer, 0]
    monkeypatch.setattr(sheets, 'select', lambda heading, labels, preselect=-1, rows=None, actions=0: answers.pop(0))
    mode.prompt()
    assert values['kodi_mode.prompted'] == 'true' and mode.active() is on and not mode.prompt_due()

# F. the service's auto-open

def autoopen(mode, fake, looks):
    # looks: the conditions true at each look
    seen = iter(looks[1:])
    monitor = types.SimpleNamespace(waitForAbort=lambda _: False)
    def step(_):
        fake.conditions = dict.fromkeys(next(seen, ()), True)
        return False
    monitor.waitForAbort = step
    fake.conditions = dict.fromkeys(looks[0] if looks else (), True)
    return mode.autoopen(monitor)

HOME_IDLE = 'Window.IsActive(home) + !System.HasActiveModalDialog'

SETTLED = [(HOME_IDLE,)] * 8  # 4 s of looks

def test_it_opens_once_per_session_once_home_stayed_idle(mode, fake):
    turn_on(mode)
    fake.builtins = []
    assert autoopen(mode, fake, [(), (HOME_IDLE,), (HOME_IDLE,), ()] + SETTLED)
    assert fake.builtins == ['RunScript(plugin.video.a4kstreaming,autoopen)']
    assert not autoopen(mode, fake, SETTLED) and len(fake.builtins) == 1

def test_it_does_not_open_with_the_mode_off_or_a_play(mode, fake):
    assert not autoopen(mode, fake, [(HOME_IDLE,)])
    turn_on(mode)
    fake.builtins = []
    assert not autoopen(mode, fake, [('Player.HasMedia', HOME_IDLE)]) and fake.builtins == []

def test_a_play_starting_while_home_settles_keeps_it_closed(mode, fake):
    # Kodi started by an Android "open with": Home shows, then the play starts
    turn_on(mode)
    fake.builtins = []
    assert not autoopen(mode, fake, SETTLED[:6] + [('Player.HasMedia',)] + SETTLED) and fake.builtins == []

def test_it_gives_up_when_home_never_settles(mode, fake):
    turn_on(mode)
    fake.builtins = []
    assert not autoopen(mode, fake, []) and fake.builtins == []

# G. Back on the home window's top menu

@pytest.mark.parametrize('on,answer,expected', [
    (False, None, (['closed'], [])),
    (True, 0, ([], ['Minimize'])),
    (True, 1, (['closed'], [])),
    (True, 2, ([], [])),
    (True, -1, ([], [])),
])
def test_back_on_the_top_menu_asks_in_the_mode(mode, fake, home, monkeypatch, on, answer, expected):
    if on:
        turn_on(mode)
    fake.builtins, fake.conditions = [], {'System.Platform.Android': True}
    sheets = importlib.import_module('a4kStreaming.ui.sheets')
    asked = []
    monkeypatch.setattr(sheets, 'select', lambda heading, labels, preselect=-1, rows=None, actions=0: asked.append(labels) or answer)
    closed = []
    monkeypatch.setattr(home.Home, 'close', lambda self: closed.append('closed'))
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    window.back(home.WATCH_NOW)
    assert (closed, fake.builtins) == expected and asked == ([home.LEAVE] if on else [])
