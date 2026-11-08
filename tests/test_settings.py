# -*- coding: utf-8 -*-
# Offline tests for the settings window (ui/settings.py, a4k-settings.xml): resources/settings.xml read as its rows,
# each control type, secret masking, the section reset, the Home order editor, and how the home window opens it.

import os
import re
import importlib
from xml.etree import ElementTree
from .common import pytest, api
from .utils import Spawned

ROOT = os.path.join(os.path.dirname(__file__), '..')
SECRET = 'k3y-VALUE-never-shown'

@pytest.fixture(scope='module')
def core():
    return api.A4kStreamingApi({'kodi': True}).core

@pytest.fixture
def settings(core):
    return importlib.import_module('a4kStreaming.ui.settings')

@pytest.fixture
def sheets(core):
    return importlib.import_module('a4kStreaming.ui.sheets')

class Item(object):
    def __init__(self, label='', label2='', offscreen=False): self.label, self.label2, self.properties = label, label2, {}
    def setLabel(self, label): self.label = label
    def setLabel2(self, label): self.label2 = label
    def setProperty(self, key, value): self.properties[key] = value
    def getProperty(self, key): return self.properties.get(key, '')

class List(object):
    # a list control that keeps its selection, as Kodi's does
    def __init__(self): self.items, self.selected = [], 0
    def addItems(self, items): self.items.extend(items)
    def reset(self): self.items, self.selected = [], 0
    def size(self): return len(self.items)
    def selectItem(self, index): self.selected = index
    def getSelectedPosition(self): return self.selected if self.items else -1
    def getListItem(self, index): return self.items[index]

class Action(object):
    def __init__(self, id): self.id = id
    def getId(self): return self.id

@pytest.fixture
def values(core, monkeypatch):
    values = {}
    monkeypatch.setattr(core.kodi.addon, 'getSetting', lambda key: values.get(key, ''))
    monkeypatch.setattr(core.kodi.addon, 'setSetting', lambda key, value: values.__setitem__(key, value), raising=False)
    return values

@pytest.fixture(autouse=True)
def clean(core, monkeypatch):
    properties = importlib.import_module('a4kStreaming.lib.kodi_mock')._window_properties
    properties.clear()
    monkeypatch.setattr(core.kodi.xbmcgui, 'ListItem', Item)
    yield
    properties.clear()

@pytest.fixture
def window(settings, values, monkeypatch):
    # an opened window: onInit filled the rail and the pane
    def opened(only_order=False):
        win = settings.Window('a4k-settings.xml', '', 'Default', '1080i')
        win.controls = {settings.RAIL: List(), settings.PANE: List()}
        win.closed = False
        monkeypatch.setattr(win, 'close', lambda: setattr(win, 'closed', True))
        win.only_order = only_order
        win.onInit()
        assert win.error is None
        return win
    return opened

def labels(win):
    return [item.label for item in win.pane.items]

def go(win, id):
    # focus the pane on the row of setting id
    cat, index = win.find(id)
    win.show(cat, index)
    win.setFocusId(200)
    return win.pane.items[index]

def press(win, id):
    win.onAction(Action(id))

# 1. settings.xml read as the window's rows

def test_every_visible_setting_is_in_exactly_one_pane(settings):
    text = re.sub(r'&(?!amp;)', '&amp;', open(os.path.join(ROOT, 'resources', 'settings.xml')).read())
    visible = [n.get('id') for n in ElementTree.fromstring(text).iter('setting')
               if n.get('id') and n.get('visible') != 'false']
    shown = [row['id'] for pane in settings.shown(settings.categories()) for row in pane if row['id']]
    assert sorted(shown) == sorted(visible) and len(shown) == len(set(shown))
    assert set(settings.HELP) == set(visible)  # one help line per row, none left over

def test_categories_kinds_and_ranges_come_from_settings_xml(settings):
    cats = settings.categories()
    assert [label for _, label, _ in cats] == ['Playback', 'Sources', 'Home', 'Accounts', 'Advanced']
    rows = {row['id']: row for _, _, rows in cats for row in rows}
    assert sorted(id for id, row in rows.items() if row['kind'] == 'secret') == ['imdb.at-main', 'premiumize.apikey', 'trakt.clientid']
    assert {id for id, row in rows.items() if row['kind'] == 'hidden'} == {'appearance.order', 'appearance.my_list', 'kodi_mode.prompted'}
    assert rows['appearance.order_pick']['kind'] == 'order' and rows['provider.install']['kind'] == 'action'
    assert rows['provider.install']['action'] == 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=provider&type=install)'
    assert (rows['general.remembered_searches']['min'], rows['general.remembered_searches']['step'],
            rows['general.remembered_searches']['max']) == (0, 10, 500)
    assert (rows['general.max_movie_size']['step'], rows['general.mark_as_watched_rating']['step']) == (5, 1)
    assert rows['general.max_quality']['options'] == ['SD', '720P', '1080P', '4K']
    assert rows['general.max_quality']['label'] == 'Highest quality'

def test_reset_rows_skip_accounts_and_kodis_dialog_is_last(settings):
    panes = settings.shown(settings.categories())
    assert [any(row['kind'] == 'reset' for row in pane) for pane in panes] == [True, True, True, False, True]
    assert panes[-1][-1]['kind'] == 'native' and sum(row['kind'] == 'native' for pane in panes for row in pane) == 1

# 2. each control type

def test_first_open_shows_playback_on_the_rail(window):
    win = window()
    assert [item.label for item in win.rail.items] == ['Playback', 'Sources', 'Home', 'Accounts', 'Advanced']
    assert win.getFocusId() == 100 and win.cat == 0 and labels(win)[0] == 'Highest quality'
    assert win.getProperty('a4k.desc') == 'What plays, and what happens around it.'

def test_bool_toggles_and_writes_true_false(window, values):
    win = window()
    item = go(win, 'general.autoplay')
    assert item.label2 == 'Off' and item.getProperty('a4k.step') == ''
    win.onClick(200)
    assert values['general.autoplay'] == 'true' and item.label2 == 'On'
    win.onClick(200)
    assert values['general.autoplay'] == 'false' and item.label2 == 'Off'
    press(win, 2)  # Right on a bool does nothing, Left goes to the rail
    assert win.getFocusId() == 200
    press(win, 1)
    assert win.getFocusId() == 100

def test_enum_steps_with_left_right_and_stops_at_the_ends(window, values):
    win = window()
    item = go(win, 'general.max_quality')
    assert item.label2 == '4K' and item.getProperty('a4k.step') == 'true'
    press(win, 2)
    assert 'general.max_quality' not in values  # already the last: nothing written
    for _ in range(5):
        press(win, 1)
    assert values['general.max_quality'] == '0' and item.label2 == 'SD'

def test_enum_ok_cycles_three_options_and_opens_the_picker_for_more(window, values, sheets, monkeypatch):
    win = window()
    item = go(win, 'general.skip_intro')
    for expected in ('Button', 'Off', 'Auto'):
        win.onClick(200)
        assert item.label2 == expected
    asked = []
    monkeypatch.setattr(sheets, 'select', lambda heading, labels, preselect=-1: asked.append((heading, labels, preselect)) or 1)
    item = go(win, 'appearance.hero_turn')
    win.onClick(200)
    assert asked == [('Top shelf rotation', ['10 s', '15 s', '20 s', '30 s', 'Off'], 1)]
    assert values['appearance.hero_turn'] == '1' and item.label2 == '15 s'

def test_number_steps_clamps_and_formats(window, values, core, monkeypatch):
    win = window()
    item = go(win, 'general.max_movie_size')
    assert item.label2 == 'No limit'
    press(win, 2)
    assert 'general.max_movie_size' not in values
    press(win, 1)
    assert values['general.max_movie_size'] == '195' and item.label2 == '195 GB'
    item = go(win, 'general.remembered_searches')
    press(win, 1)
    press(win, 1)
    press(win, 1)
    assert values['general.remembered_searches'] == '0' and item.label2 == 'Off'
    typed = iter(['999', ''])
    monkeypatch.setattr(core.kodi.xbmcgui, 'Dialog', lambda: type('D', (), {'numeric': lambda self, t, h, d: next(typed)})())
    win.onClick(200)  # typed past the top: the maximum
    assert values['general.remembered_searches'] == '500'
    win.onClick(200)  # cancelled: unchanged
    assert values['general.remembered_searches'] == '500'

def test_text_row_types_through_the_keyboard(window, values, core, monkeypatch):
    win = window()
    values['trakt.username'] = 'old'
    item = go(win, 'trakt.username')
    asked = []
    monkeypatch.setattr(core.kodi.xbmcgui, 'Dialog', lambda: type('D', (), {
        'input': lambda self, heading, defaultt='', **kw: asked.append(defaultt) or ' maria '})())
    win.onClick(200)
    assert asked == ['old'] and values['trakt.username'] == 'maria' and item.label2 == 'maria'

def test_action_rows_run_their_builtin(window, core, monkeypatch):
    ran = []
    monkeypatch.setattr(core.kodi.xbmc, 'executebuiltin', lambda builtin, wait=False: ran.append(builtin))
    win = window()
    assert go(win, 'provider.manage').label2 == '›'
    win.onClick(200)
    assert ran == ['RunPlugin(plugin://plugin.video.a4kstreaming/?action=provider&type=manage)'] and win.error is None

def test_kodi_setup_mode_row_shows_its_state_and_opens_its_sheet_in_process(window, core, monkeypatch):
    mode = importlib.import_module('a4kStreaming.kodi_mode')
    opened, ran = [], []
    monkeypatch.setattr(mode, 'sheet', lambda: opened.append(True))
    monkeypatch.setattr(core.kodi.xbmc, 'executebuiltin', lambda builtin, wait=False: ran.append(builtin))
    win = window()
    assert go(win, 'kodi.mode').label2 == 'Off'
    win.onClick(200)
    assert opened == [True] and ran == [] and win.error is None

def test_account_rows_are_disabled_signed_out_and_lead_to_the_imdb_row(window, values):
    win = window()
    item = go(win, 'appearance.watchlist')
    assert (item.label2, item.getProperty('a4k.off')) == ('Sign in to IMDb first', 'true')
    win.onClick(200)
    assert 'appearance.watchlist' not in values and win.rows[win.pane.getSelectedPosition()]['id'] == 'imdb.at-main'
    values['imdb.at-main'] = SECRET
    item = go(win, 'appearance.watchlist')
    assert (item.label2, item.getProperty('a4k.off')) == ('On', '')

def test_my_list_runs_its_picker_in_process(window, values, monkeypatch):
    appearance = importlib.import_module('a4kStreaming.ui.appearance')
    values['imdb.at-main'] = SECRET
    monkeypatch.setattr(appearance, 'pick_my_list', lambda: values.__setitem__('appearance.my_list', 'ls1 Weekend Picks'))
    win = window()
    item = go(win, 'appearance.my_list_pick')
    assert item.label2 == 'None'
    win.onClick(200)
    assert item.label2 == 'Weekend Picks'

# 3. secrets

def every_text(win):
    # every label, label2 and property of every row in every category
    texts = []
    for cat in range(len(win.panes)):
        win.show(cat)
        for item in win.pane.items:
            texts += [item.label, item.label2] + list(item.properties.values())
    return texts

def test_a_secret_value_never_appears_in_any_row(window, values):
    for id in ('imdb.at-main', 'premiumize.apikey', 'trakt.clientid'):
        values[id] = SECRET
    win = window()
    texts = every_text(win)
    assert texts and not any(SECRET in text for text in texts)
    assert [go(win, id).label2 for id in ('imdb.at-main', 'premiumize.apikey', 'trakt.clientid')] == ['Set'] * 3

def test_secrets_are_hidden_in_kodis_dialog_too():
    text = re.sub(r'&(?!amp;)', '&amp;', open(os.path.join(ROOT, 'resources', 'settings.xml')).read())
    nodes = {n.get('id'): n for n in ElementTree.fromstring(text).iter('setting')}
    assert all(nodes[id].get('option') == 'hidden' for id in ('imdb.at-main', 'premiumize.apikey', 'trakt.clientid'))

@pytest.fixture
def keyboard(core, monkeypatch):
    import types
    typed, asked = [], []
    def input(heading, defaultt='', type=0, option=0):
        asked.append((heading, defaultt, option))
        return typed.pop(0)
    monkeypatch.setattr(core.kodi.xbmcgui, 'Dialog', lambda: types.SimpleNamespace(input=input))
    return typed, asked

def test_secret_entry_is_hidden_unprefilled_and_checked(window, values, settings, keyboard, monkeypatch):
    typed, asked = keyboard
    answers = iter([False, True, None])
    monkeypatch.setattr(settings, 'premiumize_ok', lambda key: next(answers))
    notified = []
    monkeypatch.setattr(settings.kodi, 'notification', lambda text: notified.append(text))
    win = window()
    item = go(win, 'premiumize.apikey')
    assert item.label2 == 'Not set'
    typed.append('   ')  # nothing typed: nothing changes
    win.onClick(200)
    assert 'premiumize.apikey' not in values and asked == [('Premiumize', '', 2)]
    typed.append(SECRET)
    win.onClick(200)
    assert values['premiumize.apikey'] == SECRET and item.label2 == 'Rejected'
    sheet = iter([0, 0])  # set: Replace
    monkeypatch.setattr(importlib.import_module('a4kStreaming.ui.sheets'), 'select', lambda *a, **k: next(sheet))
    typed.append(SECRET + '2')
    win.onClick(200)
    assert item.label2 == 'Set' and notified == []
    typed.append(SECRET + '3')
    win.onClick(200)  # Premiumize did not answer: saved, said so
    assert item.label2 == 'Set' and len(notified) == 1 and SECRET not in notified[0]
    assert all(default == '' for _, default, _ in asked)

def test_secret_remove_needs_the_confirm(window, values, sheets, monkeypatch):
    values['imdb.at-main'] = SECRET
    win = window()
    item = go(win, 'imdb.at-main')
    picks = iter([1, 1, 1, 0])  # Remove, Cancel; then Remove, Remove
    monkeypatch.setattr(sheets, 'select', lambda *a, **k: next(picks))
    win.onClick(200)
    assert values['imdb.at-main'] == SECRET
    win.onClick(200)
    assert values['imdb.at-main'] == '' and item.label2 == 'Not set'

def test_premiumize_check_reads_the_account_status(settings, core, monkeypatch):
    sent = []
    def answer(content, status=200):
        return lambda core, request, cache=True: sent.append(request) or type('R', (), {'status_code': status, 'content': content})()
    monkeypatch.setattr(core.request, 'execute', answer(b'{"status":"success","premium_until":1}'))
    assert settings.premiumize_ok('abc') is True and sent[0]['url'].endswith('/api/account/info?apikey=abc')
    monkeypatch.setattr(core.request, 'execute', answer(b'{"status":"error","message":"Not logged in."}', 401))
    assert settings.premiumize_ok('abc') is False
    monkeypatch.setattr(core.request, 'execute', answer(b'', 500))
    assert settings.premiumize_ok('abc') is None

# 4. reset

def test_reset_writes_its_categorys_defaults_after_the_confirm(window, values, sheets, monkeypatch):
    values.update({'appearance.browse': 'false', 'appearance.order': 'reality', 'general.autoplay': 'true',
                   'imdb.at-main': SECRET})
    win = window()
    cat, _ = win.find('appearance.browse')
    win.show(cat, len(win.panes[cat]) - 1)
    win.setFocusId(200)
    assert win.rows[-1]['kind'] == 'reset'
    picks = iter([1, 0])  # Cancel, then Reset
    asked = []
    monkeypatch.setattr(sheets, 'select', lambda heading, labels, **k: asked.append((heading, labels)) or next(picks))
    win.onClick(200)
    assert values['appearance.browse'] == 'false'
    win.onClick(200)
    assert asked[0] == ('Reset Home to defaults?', ['Reset', 'Cancel'])
    assert (values['appearance.browse'], values['appearance.order'], values['appearance.hero_turn']) == ('true', '', '1')
    assert values['general.autoplay'] == 'true' and values['imdb.at-main'] == SECRET  # other categories untouched
    assert go(win, 'appearance.browse').label2 == 'On'

def test_reset_of_advanced_keeps_the_kodi_setup_question_asked(window, values, sheets, monkeypatch):
    values.update({'kodi_mode.prompted': 'true', 'general.page_size': '50'})
    win = window()
    cat, _ = win.find('general.page_size')
    win.show(cat, len(win.panes[cat]) - 2)  # Reset this section; Kodi's dialog is last
    win.setFocusId(200)
    monkeypatch.setattr(sheets, 'select', lambda heading, labels, **k: 0)
    win.onClick(200)
    assert values['general.page_size'] == '29' and values['kodi_mode.prompted'] == 'true'

# 5. the Home order editor

def order_labels(win):
    return [(item.label, item.label2) for item in win.pane.items]

def test_order_editor_picks_up_moves_and_drops(window, values):
    win = window()
    go(win, 'appearance.order_pick')
    win.onClick(200)
    assert win.order is not None and [label for label, _ in order_labels(win)][:3] == ['Trending Movies', 'Trending TV Shows', 'Reality TV']
    assert order_labels(win)[2] == ('Reality TV', 'Off')
    win.pane.selectItem(2)
    win.onClick(200)  # pick up Reality TV
    assert win.pane.items[2].getProperty('a4k.grabbed') == 'true' and win.pane.items[2].label2 == 'Moving'
    for position in (1, 0, 0):  # Kodi moved the focus up twice, then stopped at the top
        win.pane.selectItem(position)
        press(win, 3)
    assert [label for label, _ in order_labels(win)][:3] == ['Reality TV', 'Trending Movies', 'Trending TV Shows']
    assert 'appearance.order' not in values  # nothing saved until the drop
    win.onClick(200)
    assert values['appearance.order'] == 'reality,trending_movies,trending_tv,animations,animation_tv,my_list,watchlist'
    assert not any(item.getProperty('a4k.grabbed') for item in win.pane.items)

def test_order_editor_back_cancels_the_move_then_leaves(window, values):
    values['appearance.order'] = 'watchlist'
    win = window()
    go(win, 'appearance.order_pick')
    win.onClick(200)
    win.onClick(200)  # pick up the Watchlist
    win.pane.selectItem(1)
    press(win, 4)
    assert win.order[:2] == ['trending_movies', 'watchlist']
    press(win, 92)  # Back: put back, nothing saved
    assert win.order[0] == 'watchlist' and win.grab is None and values['appearance.order'] == 'watchlist'
    assert win.pane.getSelectedPosition() == 0 and win.getFocusId() == 200
    press(win, 92)  # Back again: the Home rows, on the Home order row
    assert win.order is None and win.rows[win.pane.getSelectedPosition()]['id'] == 'appearance.order_pick'
    assert not win.closed

def test_order_editor_alone_closes_when_left(window, values):
    win = window(only_order=True)
    assert win.order is not None and win.getFocusId() == 200
    press(win, 92)
    assert win.closed

# 6. focus, Back and the session memory

def test_rail_moves_switch_the_pane_and_back_steps_out_one_level(window):
    win = window()
    win.rail.selectItem(2)
    press(win, 4)
    assert win.cat == 2 and labels(win)[0] == 'Browse row'
    win.onClick(100)
    assert win.getFocusId() == 200
    press(win, 92)
    assert win.getFocusId() == 100 and not win.closed
    press(win, 92)
    assert win.closed

def test_right_on_the_rail_enters_the_pane_without_stepping_its_first_row(window, values):
    win = window()  # Playback, whose first row is an enum
    assert win.getFocusId() == 100
    before = win.pane.items[0].label2
    press(win, 2)
    assert win.getFocusId() == 200 and win.pane.items[0].label2 == before and 'general.max_quality' not in values

def test_the_window_reopens_on_the_last_category_and_row(window):
    win = window()
    win.show(3, 2)
    win.setFocusId(200)
    press(win, 92)
    press(win, 92)
    again = window()
    assert (again.cat, again.pane.getSelectedPosition(), again.getFocusId()) == (3, 2, 200)

def test_kodis_dialog_row_closes_and_asks_for_it(window):
    win = window()
    win.show(len(win.panes) - 1, len(win.panes[-1]) - 1)
    win.setFocusId(200)
    win.onClick(200)
    assert win.native and win.closed

# 7. the home window opens it

@pytest.fixture
def home(core, monkeypatch):
    home = importlib.import_module('a4kStreaming.ui.home')
    monkeypatch.setattr(home.Home, 'rotate', lambda self: None)
    return home

def test_gear_runs_the_window_in_its_own_interpreter_and_watches_it(home, core, monkeypatch):
    calls, threads = [], Spawned(run=False)
    monkeypatch.setattr(home, 'run', calls.append)
    monkeypatch.setattr(home, 'spawn', threads)
    window = home.Home('a4k-home.xml', '', 'Default', '1080i')
    window.onClick(home.SETTINGS)
    assert calls == ['RunScript(plugin.video.a4kstreaming,settings)'] and [t.target for t in threads] == [window.settings_closed]
    assert window.error is None

@pytest.mark.parametrize('native,only_order,opened', [(False, False, []), (True, False, ['dialog']), (True, True, [])])
def test_run_opens_kodis_dialog_when_the_window_fails_or_asks(settings, core, monkeypatch, native, only_order, opened):
    log = []
    monkeypatch.setattr(settings, 'open', lambda only_order: native)
    monkeypatch.setattr(core.kodi.xbmc, 'executebuiltin', lambda builtin: log.append('dialog'), raising=False)
    settings.run(only_order)
    assert log == opened  # the order editor alone is already over Kodi's dialog

def test_kodis_dialog_row_makes_open_return_true(settings, values, monkeypatch):
    monkeypatch.setattr(settings.Window, 'doModal', lambda self: setattr(self, 'native', True), raising=False)
    assert settings.open() is True

def test_a_window_error_is_logged_and_asks_for_kodis_dialog(settings, monkeypatch):
    errors = []
    monkeypatch.setattr(settings.logger, 'error', errors.append)
    def broken(self):
        raise RuntimeError('no control 100')
    monkeypatch.setattr(settings.Window, 'getControl', lambda self, id: broken(self))
    assert settings.open() is True and len(errors) == 1 and 'no control 100' in errors[0]
