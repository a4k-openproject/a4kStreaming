# -*- coding: utf-8 -*-
# Offline tests for the settings window's Subtitles category (ui/subtitles.py): the Kodi 21 setting ids it names, the
# install / enable row, routing of each row to Kodi (JSON-RPC), a4kSubtitles (its Addon) or our own settings, the
# language rows' writes, and the masked account rows.

import json
import importlib
from .common import pytest
from .test_settings import core, settings, sheets, values, clean, window, go, press, every_text

SHARED = (core, settings, sheets, values, clean, window)  # test_settings' fixtures, used here by name

SECRET = 'subs-k3y-VALUE-never-shown'

# Kodi 21 (Omega) system/settings/settings.xml, tag 21.3-Omega (21.2 is the same file): section player, category,
# type, default, and the options: values of a static list, the name of Kodi's filler for a dynamic one, or
# (minimum, step, maximum)
KODI21 = {
    'locale.subtitlelanguage': ('language', 'string', 'original', 'subtitlestreamlanguages'),
    'locale.audiolanguage': ('language', 'string', 'mediadefault', 'audiostreamlanguages'),
    'accessibility.subhearing': ('language', 'boolean', False, None),
    'subtitles.languages': ('subtitles', 'list[string]', ['English'], 'subtitledownloadlanguages'),
    'subtitles.tv': ('subtitles', 'addon', '', None),
    'subtitles.movie': ('subtitles', 'addon', '', None),
    'subtitles.fontname': ('subtitles', 'string', 'DEFAULT', 'subtitlesfonts'),
    'subtitles.fontsize': ('subtitles', 'integer', 42, (12, 2, 74)),
    'subtitles.style': ('subtitles', 'integer', 0, ['0', '1', '2', '3']),
    'subtitles.colorpick': ('subtitles', 'string', 'FFFFFFFF', None),
    'subtitles.opacity': ('subtitles', 'integer', 100, (0, 1, 100)),
    'subtitles.bordersize': ('subtitles', 'integer', 25, (0, 1, 100)),
    'subtitles.bordercolorpick': ('subtitles', 'string', 'FF000000', None),
    'subtitles.backgroundtype': ('subtitles', 'integer', 0, ['0', '1', '2', '3']),
    'subtitles.bgcolorpick': ('subtitles', 'string', 'FF000000', None),
    'subtitles.bgopacity': ('subtitles', 'integer', 80, (0, 1, 100)),
    'subtitles.align': ('subtitles', 'integer', 2, ['0', '1', '2', '3', '4']),
    'subtitles.charset': ('subtitles', 'string', 'DEFAULT', 'charsets'),
}
LANGUAGES = ['English', 'French', 'German', 'Portuguese', 'Spanish']
FILLERS = {  # what Kodi's fillers list, cut short
    'subtitlestreamlanguages': [('None', 'none'), ('Forced only', 'forced_only'), ('Original language', 'original'),
                                ('User interface language', 'default')] + [(name, name) for name in LANGUAGES],
    'audiostreamlanguages': [('Media default', 'mediadefault'), ('Original language', 'original')]
    + [(name, name) for name in LANGUAGES],
    'subtitlesfonts': [('Kodi default', 'DEFAULT'), ('arial.ttf', 'arial.ttf')],
    'charsets': [('Default', 'DEFAULT'), ('Western Europe (Windows)', 'CP1252')],
}

@pytest.fixture
def subtitles(core):
    return importlib.import_module('a4kStreaming.ui.subtitles')

class Kodi(object):
    # Kodi's JSON-RPC for settings and add-ons, its builtins, and a4kSubtitles' own settings
    def __init__(self):
        self.settings = {id: list(default) if isinstance(default, list) else default
                         for id, (_, _, default, _) in KODI21.items()}
        self.addon = None  # None (missing), False (disabled), True (enabled)
        self.in_repository = True
        self.declines = False  # the user says No to Kodi's install prompt
        self.subs = {}
        self.builtins, self.calls = [], []

    def rpc(self, request):
        request = json.loads(request)
        method, params = request['method'], request.get('params', {})
        self.calls.append((method, params))
        result = None
        if method == 'Settings.GetSettings':  # as Kodi 21.2 answers on the TV box: no colour button (*colorpick)
            result = {'settings': [self.definition(id) for id, (category, _, _, _) in KODI21.items()
                                   if category == params['filter']['category'] and not id.endswith('colorpick')]}
        elif method == 'Settings.GetSettingValue':
            hidden = params['setting'] in ('subtitles.bgcolorpick', 'subtitles.bgopacity') \
                and self.settings['subtitles.backgroundtype'] not in (2, 3)
            if hidden:  # Kodi rejects a setting its dependencies hide
                return json.dumps({'error': {'code': -32602}})
            result = {'value': self.settings[params['setting']]}
        elif method == 'Settings.SetSettingValue':
            current, value = self.settings[params['setting']], params['value']
            assert type(value) is type(current), (params, current)  # Kodi refuses '2' for an integer
            self.settings[params['setting']] = value
            result = True
        elif method == 'Addons.GetAddons':
            assert params['type'] == 'xbmc.subtitle.module'
            offered = params.get('installed') is False and self.addon is None and self.in_repository
            found = [{'addonid': 'service.subtitles.a4ksubtitles'}] if offered else [] if self.addon is None else [{'addonid': 'service.subtitles.a4ksubtitles', 'enabled': self.addon,
                                                   'version': '3.26.0'}]
            result = {'addons': found, 'limits': {}} if found else {'limits': {}}
        elif method == 'Addons.SetAddonEnabled':
            assert params == {'addonid': 'service.subtitles.a4ksubtitles', 'enabled': True}
            self.addon, result = True, 'OK'
        return json.dumps({'result': result})

    def definition(self, id):
        _, type, default, options = KODI21[id]
        setting = {'id': id, 'type': type, 'default': default, 'value': self.settings[id]}
        if isinstance(options, str) and type == 'string':
            setting['options'] = [{'label': label, 'value': value} for label, value in FILLERS[options]]
        return setting

    def builtin(self, builtin, wait=False):
        self.builtins.append((builtin, wait))
        if builtin == 'InstallAddon(service.subtitles.a4ksubtitles)' and self.in_repository and not self.declines:
            self.addon = True

    def Addon(self, id):
        assert id == 'service.subtitles.a4ksubtitles' and self.addon, id  # Kodi raises for a missing add-on
        subs = self.subs
        return type('Addon', (), {'getSetting': lambda _, key: subs.get(key, ''),
                                  'setSetting': lambda _, key, value: subs.__setitem__(key, value)})()

    def saves(self):
        return [b for b, wait in self.builtins if b == 'Skin.Reset(a4k.kodi_mode)' and wait]

@pytest.fixture
def kodi(core, subtitles, monkeypatch):
    fake = Kodi()
    monkeypatch.setattr(core.kodi.xbmc, 'executeJSONRPC', fake.rpc)
    monkeypatch.setattr(core.kodi.xbmc, 'executebuiltin', fake.builtin)
    monkeypatch.setattr(subtitles.kodi.xbmcaddon, 'Addon', lambda id: fake.Addon(id) if id == subtitles.SUBS
                        else core.kodi.addon)
    return fake

def pane(win):
    cat = [label for _, label, _ in win.cats].index('Subtitles')
    win.show(cat)
    win.setFocusId(200)
    return [(row['kind'], row['label']) for row in win.rows]

def ids(win):
    pane(win)
    return [row['id'] for row in win.rows if row['kind'] != 'header']

def kodi_rows(subtitles):
    # every row's Kodi setting, as the table names it
    for entry in subtitles.ROWS:
        if isinstance(entry, tuple):
            extra = entry[4] if len(entry) > 4 else {}
            id = extra.get('kodi', entry[0][5:] if entry[0].startswith('kodi:') else None)
            if id:
                yield entry, id

# 1. the Kodi 21 ids

def test_every_kodi_id_and_option_is_one_kodi_21_has(subtitles):
    checked = 0
    for entry, id in kodi_rows(subtitles):
        assert id in KODI21, id
        _, type, default, options = KODI21[id]
        kind, extra = entry[1], entry[4] if len(entry) > 4 else {}
        if entry[0].startswith('subtitles:'):  # made of several: checked by the routing tests
            continue
        checked += 1
        if kind == 'bool':
            assert type == 'boolean', id
        elif kind == 'number':
            low, step, high = options
            assert type == 'integer' and low <= extra['min'] < extra['max'] <= high, id
            assert extra['step'] % step == 0 and int(extra['default']) == default, id
        elif extra.get('dynamic'):
            assert type == 'string' and isinstance(options, str), id
        elif options:  # a static list: the same values
            assert type == 'integer' and extra['values'] == options, id
        else:  # a colour
            assert type == 'string' and default in extra['values'] and all(len(v) == 8 for v in extra['values']), id
    assert checked == 14
    for id in ('subtitles.bgcolorpick', 'subtitles.bgopacity'):
        assert subtitles.BOX[0] in KODI21 and set(subtitles.BOX[1]) <= set(KODI21[subtitles.BOX[0]][3])

def test_the_derived_rows_use_their_kodi_settings_as_kodi_types_them(subtitles):
    assert KODI21[subtitles.LANGUAGE][3] == 'subtitlestreamlanguages' and KODI21[subtitles.LANGUAGES][1] == 'list[string]'
    assert set(subtitles.SWITCH) <= {value for _, value in FILLERS['subtitlestreamlanguages']}
    assert set(subtitles.NOT_A_LANGUAGE) <= {value for _, value in FILLERS['subtitlestreamlanguages']}
    assert KODI21['subtitles.movie'][1] == KODI21['subtitles.tv'][1] == 'addon'

# 2. the category per a4kSubtitles' state

def test_missing_a4ksubtitles_is_one_install_row_and_the_kodi_rows(window, kodi):
    win = window()
    rows = pane(win)
    assert rows[:2] == [('header', 'a4kSubtitles'), ('action', 'Install a4kSubtitles')]
    assert [label for kind, label in rows if kind == 'header'] == ['a4kSubtitles', 'Language', 'Appearance', 'More']
    assert not any(id.startswith('a4ksubtitles:') for id in ids(win)) and 'subtitles:service' not in ids(win)
    assert not any(kind == 'reset' for kind, _ in rows) and rows[-1] == ('native', "Kodi's subtitle settings")
    assert win.pane.items[1].label2 == '›'

def test_install_runs_kodis_install_and_the_section_fills(window, kodi):
    win = window()
    pane(win)
    win.pane.selectItem(1)
    win.onClick(200)
    assert kodi.builtins == [('InstallAddon(service.subtitles.a4ksubtitles)', True)]
    assert win.rows[1]['label'] == 'a4kSubtitles' and win.pane.items[1].label2 == '3.26.0'
    assert 'a4ksubtitles:general.auto_search' in ids(win) and win.error is None

def test_install_from_no_repository_says_so_and_changes_nothing(window, kodi, settings, monkeypatch):
    kodi.in_repository = False
    said = []
    monkeypatch.setattr(settings.subtitles.kodi, 'notification', said.append)
    win = window()
    pane(win)
    win.pane.selectItem(1)
    win.onClick(200)
    assert said == ['a4kSubtitles not found: update the a4kStreaming repository and retry']
    assert win.rows[1]['label'] == 'Install a4kSubtitles' and kodi.builtins == []

def test_declining_kodis_install_prompt_says_nothing(window, kodi, settings, monkeypatch):
    kodi.declines = True
    said = []
    monkeypatch.setattr(settings.subtitles.kodi, 'notification', said.append)
    win = window()
    pane(win)
    win.pane.selectItem(1)
    win.onClick(200)
    assert kodi.builtins == [('InstallAddon(service.subtitles.a4ksubtitles)', True)]
    assert said == [] and win.rows[1]['label'] == 'Install a4kSubtitles'

def test_disabled_a4ksubtitles_is_an_enable_row(window, kodi):
    kodi.addon = False
    win = window()
    assert pane(win)[1] == ('action', 'Enable a4kSubtitles')
    win.pane.selectItem(1)
    win.onClick(200)
    assert kodi.addon is True and ('Addons.SetAddonEnabled', {'addonid': 'service.subtitles.a4ksubtitles',
                                                             'enabled': True}) in kodi.calls
    assert 'a4ksubtitles:general.use_ai' in ids(win)

def test_ready_shows_every_row_grouped(window, kodi, settings):
    kodi.addon = True
    win = window()
    rows = pane(win)
    assert [label for kind, label in rows if kind == 'header'] == [
        'a4kSubtitles', 'Language', 'Auto download', 'AI translation', 'Providers', 'Accounts', 'Search', 'Appearance',
        'More']
    assert len([r for r in win.rows if r['kind'] != 'header']) == 41  # the two box rows show with a box
    assert all(row['help'] for row in win.rows if row['kind'] != 'header' and 'enabled' not in row['id'])
    kodi.settings['subtitles.backgroundtype'] = 2
    win.rebuild()
    assert len([r for r in pane(win) if r[0] != 'header']) == 43
    assert win.pane.items[1].label2 == '3.26.0' and win.pane.items[1].getProperty('a4k.tone') == 'value'
    win.pane.selectItem(1)
    win.onClick(200)  # ready: nothing to do
    assert kodi.builtins == []

def test_kodi_not_answering_leaves_only_the_rows_that_need_none(window, kodi, core, monkeypatch):
    monkeypatch.setattr(core.kodi.xbmc, 'executeJSONRPC', lambda request: '{"result": {"value": []}}')
    win = window()
    assert pane(win) == [('header', 'a4kSubtitles'), ('action', 'Install a4kSubtitles'), ('header', 'More'),
                         ('native', "Kodi's subtitle settings")]

# 3. routing: each row reads and writes only its own store

@pytest.fixture
def ready(window, kodi):
    kodi.addon = True
    win = window()
    pane(win)
    return win

def test_an_a4ksubtitles_row_writes_its_add_on_only(ready, kodi, values):
    kodi.subs['general.auto_download'] = 'false'
    item = go(ready, 'a4ksubtitles:general.auto_download')
    assert item.label2 == 'Off'
    ready.onClick(200)
    assert kodi.subs == {'general.auto_download': 'true'} and item.label2 == 'On' and values == {}
    assert not any(method == 'Settings.SetSettingValue' for method, _ in kodi.calls)

def test_a_kodi_row_writes_kodi_typed_and_saved(ready, kodi, values):
    item = go(ready, 'kodi:accessibility.subhearing')
    ready.onClick(200)
    assert kodi.settings['accessibility.subhearing'] is True and item.label2 == 'On' and len(kodi.saves()) == 1
    item = go(ready, 'kodi:subtitles.style')
    press(ready, 2)
    assert kodi.settings['subtitles.style'] == 1 and item.label2 == 'Bold'
    item = go(ready, 'kodi:subtitles.fontsize')
    press(ready, 2)
    assert kodi.settings['subtitles.fontsize'] == 44 and item.label2 == '44'
    item = go(ready, 'kodi:subtitles.opacity')
    press(ready, 1)
    assert kodi.settings['subtitles.opacity'] == 95 and item.label2 == '95 %'
    assert len(kodi.saves()) == 4 and values == {} and kodi.subs == {}

def test_colours_store_argb_and_show_custom_for_others(ready, kodi, sheets, monkeypatch):
    item = go(ready, 'kodi:subtitles.colorpick')
    assert item.label2 == 'White'
    monkeypatch.setattr(sheets, 'select', lambda heading, labels, preselect=-1: labels.index('Yellow'))
    ready.onClick(200)
    assert kodi.settings['subtitles.colorpick'] == 'FFFFFF00' and item.label2 == 'Yellow'
    kodi.settings['subtitles.colorpick'] = 'FF123456'
    assert go(ready, 'kodi:subtitles.colorpick').label2 == 'Custom'

def test_the_colour_rows_show_though_kodis_settings_list_leaves_them_out(ready, kodi, subtitles):
    assert not any(id.endswith('colorpick') for id in subtitles.known())
    assert {'kodi:subtitles.colorpick', 'kodi:subtitles.bordercolorpick'} <= set(ids(ready))
    assert 'kodi:subtitles.bgcolorpick' not in ids(ready)  # no box: Kodi rejects it, so it is not even asked
    assert ('Settings.GetSettingValue', {'setting': 'subtitles.bgcolorpick'}) not in kodi.calls
    kodi.settings['subtitles.backgroundtype'] = 2
    ready.rebuild()
    assert 'kodi:subtitles.bgcolorpick' in ids(ready)

def test_a_dynamic_list_shows_kodis_labels_and_writes_its_values(ready, kodi):
    item = go(ready, 'kodi:subtitles.charset')
    assert item.label2 == 'Default'
    press(ready, 2)
    assert kodi.settings['subtitles.charset'] == 'CP1252' and item.label2 == 'Western Europe (Windows)'

def test_a_box_background_shows_its_colour_and_opacity(ready, kodi):
    assert 'kodi:subtitles.bgopacity' not in ids(ready)
    go(ready, 'kodi:subtitles.backgroundtype')
    press(ready, 2)
    press(ready, 2)  # Shadow, then Box: the pane rebuilds, still on Background
    assert kodi.settings['subtitles.backgroundtype'] == 2
    assert ready.rows[ready.pane.getSelectedPosition()]['id'] == 'kodi:subtitles.backgroundtype'
    assert ready.pane.items[ready.pane.getSelectedPosition()].label2 == 'Box'
    assert go(ready, 'kodi:subtitles.bgopacity').label2 == '80 %'
    assert go(ready, 'kodi:subtitles.bgcolorpick').label2 == 'Black'

def test_the_service_row_sets_both_kodi_services(ready, kodi):
    item = go(ready, 'subtitles:service')
    assert item.label2 == 'Off'
    ready.onClick(200)
    assert kodi.settings['subtitles.movie'] == kodi.settings['subtitles.tv'] == 'service.subtitles.a4ksubtitles'
    assert item.label2 == 'On'
    ready.onClick(200)
    assert kodi.settings['subtitles.movie'] == kodi.settings['subtitles.tv'] == ''

# 4. the language rows

def test_subtitles_off_forced_and_on(ready, kodi, values):
    kodi.settings.update({'locale.subtitlelanguage': 'Spanish', 'subtitles.languages': ['Spanish', 'French']})
    kodi.subs['general.auto_search'] = 'true'
    assert go(ready, 'subtitles:on').label2 == 'On'
    ready.onClick(200)  # cycles: Forced only, which a4kSubtitles reads itself
    assert kodi.settings['locale.subtitlelanguage'] == 'forced_only' and kodi.subs['general.auto_search'] == 'true'
    ready.onClick(200)
    assert kodi.settings['locale.subtitlelanguage'] == 'none' and focused(ready).label2 == 'Off'
    assert kodi.subs['general.auto_search'] == 'false'
    assert go(ready, 'subtitles:preferred').label2 == 'Spanish'  # what On turns back on
    go(ready, 'subtitles:on')
    ready.onClick(200)
    assert kodi.settings['locale.subtitlelanguage'] == 'Spanish' and kodi.subs['general.auto_search'] == 'true'

def test_leaving_off_keeps_a4ksubtitles_search_as_it_was(ready, kodi, values):
    kodi.settings.update({'locale.subtitlelanguage': 'Spanish', 'subtitles.languages': ['Spanish']})
    kodi.subs['general.auto_search'] = 'false'  # turned off on purpose
    go(ready, 'subtitles:on')
    ready.onClick(200)
    ready.onClick(200)
    assert focused(ready).label2 == 'Off' and kodi.subs['general.auto_search'] == 'false'
    ready.onClick(200)
    assert focused(ready).label2 == 'On' and kodi.subs['general.auto_search'] == 'false'

def test_the_switch_repaints_find_subtitles_at_once(ready, kodi):
    # the switch writes a4kSubtitles' automatic search: its row shows the new value without leaving the category
    kodi.settings.update({'locale.subtitlelanguage': 'Spanish', 'subtitles.languages': ['Spanish']})
    kodi.subs['general.auto_search'] = 'true'
    find = 'a4ksubtitles:general.auto_search'
    go(ready, 'subtitles:on')
    press(ready, 2)
    press(ready, 2)  # Forced only, then Off
    assert kodi.subs['general.auto_search'] == 'false' and focused(ready).label2 == 'Off'
    assert ready.rows[ready.pane.getSelectedPosition()]['id'] == 'subtitles:on'  # the focus stays on the switch
    assert ready.pane.items[[row['id'] for row in ready.rows].index(find)].label2 == 'Off'
    press(ready, 1)  # back to Forced only: the search as it was
    assert ready.pane.items[[row['id'] for row in ready.rows].index(find)].label2 == 'On'

def focused(win):
    return win.pane.items[win.pane.getSelectedPosition()]

def test_an_unknown_subtitles_id_is_ignored(subtitles, kodi):
    kodi.settings['locale.subtitlelanguage'] = 'English'
    assert subtitles.get('other:id') == '' and subtitles.set('other:id', 'true') is False
    assert kodi.settings['locale.subtitlelanguage'] == 'English' and kodi.settings['subtitles.languages'] == ['English']
    assert all(e[0].partition(':')[0] in ('', 'kodi', 'a4ksubtitles', 'subtitles') for e in subtitles.ROWS if isinstance(e, tuple))

def test_without_a4ksubtitles_the_switch_writes_kodi_only(window, kodi):
    win = window()
    pane(win)
    go(win, 'subtitles:on')
    press(win, 2)
    assert kodi.settings['locale.subtitlelanguage'] == 'forced_only' and kodi.subs == {}

def test_the_preferred_language_leads_the_download_list(ready, kodi, sheets, monkeypatch):
    kodi.settings.update({'locale.subtitlelanguage': 'English', 'subtitles.languages': ['English', 'French']})
    item = go(ready, 'subtitles:preferred')
    assert ready.rows[ready.pane.getSelectedPosition()]['options'][:2] == ['Original language', 'User interface language']
    asked = []
    monkeypatch.setattr(sheets, 'select', lambda heading, labels, preselect=-1: asked.append(labels[preselect])
                        or labels.index('Spanish'))
    ready.onClick(200)
    assert asked == ['English'] and item.label2 == 'Spanish'
    assert kodi.settings['locale.subtitlelanguage'] == 'Spanish' and kodi.settings['subtitles.languages'] == ['Spanish', 'French']
    monkeypatch.setattr(sheets, 'select', lambda heading, labels, preselect=-1: labels.index('French'))
    ready.onClick(200)  # the alternative becomes the preferred: the two swap
    assert kodi.settings['subtitles.languages'] == ['French', 'Spanish']
    monkeypatch.setattr(sheets, 'select', lambda heading, labels, preselect=-1: labels.index('Original language'))
    ready.onClick(200)  # not a language: the download list stays
    assert kodi.settings['locale.subtitlelanguage'] == 'original' and kodi.settings['subtitles.languages'] == ['French', 'Spanish']

def test_a_listed_preferred_language_keeps_every_entry(ready, kodi, sheets, monkeypatch):
    kodi.settings.update({'locale.subtitlelanguage': 'English', 'subtitles.languages': ['English', 'French', 'German']})
    monkeypatch.setattr(sheets, 'select', lambda heading, labels, preselect=-1: labels.index('German'))
    go(ready, 'subtitles:preferred')
    ready.onClick(200)
    assert kodi.settings['subtitles.languages'] == ['German', 'French', 'English']

def test_the_preferred_language_while_off_is_the_one_on_turns_back_on(ready, kodi, sheets, monkeypatch):
    kodi.settings.update({'locale.subtitlelanguage': 'none', 'subtitles.languages': ['English']})
    monkeypatch.setattr(sheets, 'select', lambda heading, labels, preselect=-1: labels.index('German'))
    go(ready, 'subtitles:preferred')
    ready.onClick(200)
    assert kodi.settings['locale.subtitlelanguage'] == 'none' and kodi.settings['subtitles.languages'] == ['German']

def test_the_alternative_language_is_second_in_the_download_list(ready, kodi, sheets, monkeypatch):
    kodi.settings['subtitles.languages'] = ['English', 'French', 'Portuguese']
    item = go(ready, 'subtitles:alternative')
    row = ready.rows[ready.pane.getSelectedPosition()]
    assert item.label2 == 'French' and row['options'][0] == 'None' and 'Forced only' not in row['options']
    assert 'Original language' not in row['options']
    monkeypatch.setattr(sheets, 'select', lambda heading, labels, preselect=-1: labels.index('German'))
    ready.onClick(200)
    assert kodi.settings['subtitles.languages'] == ['English', 'German', 'French', 'Portuguese'] and item.label2 == 'German'
    monkeypatch.setattr(sheets, 'select', lambda heading, labels, preselect=-1: 0)
    ready.onClick(200)
    assert kodi.settings['subtitles.languages'] == ['English', 'French', 'Portuguese'] and item.label2 == 'French'  # the next one moves up

def test_the_alternative_never_takes_the_preferred_place(ready, kodi, sheets, settings, monkeypatch):
    said = []
    monkeypatch.setattr(settings.subtitles.kodi, 'notification', said.append)
    kodi.settings.update({'locale.subtitlelanguage': 'English', 'subtitles.languages': ['English', 'French']})
    monkeypatch.setattr(sheets, 'select', lambda heading, labels, preselect=-1: labels.index('English'))
    item = go(ready, 'subtitles:alternative')
    ready.onClick(200)
    assert kodi.settings['subtitles.languages'] == ['English', 'French'] and item.label2 == 'French'
    assert said == ['That is already the preferred language']
    kodi.settings['subtitles.languages'] = []  # an empty list starts with the preferred language
    monkeypatch.setattr(sheets, 'select', lambda heading, labels, preselect=-1: labels.index('French'))
    ready.onClick(200)
    assert kodi.settings['subtitles.languages'] == ['English', 'French']
    kodi.settings.update({'locale.subtitlelanguage': 'original', 'subtitles.languages': []})
    ready.onClick(200)
    assert kodi.settings['subtitles.languages'] == [] and said[-1] == 'Pick the preferred language first'

# 5. secrets

ACCOUNTS = ('a4ksubtitles:general.ai_api_key', 'a4ksubtitles:opensubtitles.username',
            'a4ksubtitles:opensubtitles.password', 'a4ksubtitles:subdl.apikey', 'a4ksubtitles:subsource.apikey')

def test_account_values_never_appear_in_any_row(ready, kodi):
    for id in ACCOUNTS:
        kodi.subs[id.partition(':')[2]] = SECRET
    texts = every_text(ready)
    assert texts and not any(SECRET in text for text in texts)
    assert [go(ready, id).label2 for id in ACCOUNTS] == ['Set'] * 5
    assert all(go(ready, id).getProperty('a4k.chip') == 's' for id in ACCOUNTS)

def test_an_account_is_typed_hidden_unprefilled_and_named(ready, kodi, sheets, monkeypatch):
    import types
    asked = []
    def input(heading, defaultt='', type=0, option=0):
        asked.append((heading, defaultt, option))
        return SECRET
    monkeypatch.setattr(importlib.import_module('a4kStreaming.lib.kodi').xbmcgui, 'Dialog',
                        lambda: types.SimpleNamespace(input=input))
    item = go(ready, 'a4ksubtitles:subdl.apikey')
    assert item.label2 == 'Not set'
    ready.onClick(200)
    assert kodi.subs['subdl.apikey'] == SECRET and item.label2 == 'Set' and asked == [('SubDL API key', '', 2)]
    go(ready, 'a4ksubtitles:general.ai_api_key')
    ready.onClick(200)
    assert asked[-1] == ('AI translation · API key', '', 2)
    picks = iter([1, 0])  # Remove, then confirm
    monkeypatch.setattr(sheets, 'select', lambda *a, **k: next(picks))
    item = go(ready, 'a4ksubtitles:subdl.apikey')
    ready.onClick(200)
    assert kodi.subs['subdl.apikey'] == '' and item.label2 == 'Not set'

# 6. Kodi's subtitle settings

def test_kodis_subtitle_settings_row_closes_and_opens_them(ready, settings, core, monkeypatch):
    ready.pane.selectItem(len(ready.rows) - 1)
    ready.onClick(200)
    assert ready.native == 'ActivateWindow(playersettings,subtitles)' and ready.closed
    ran = []
    monkeypatch.setattr(settings, 'open', lambda only_order: 'ActivateWindow(playersettings,subtitles)')
    monkeypatch.setattr(core.kodi.xbmc, 'executebuiltin', lambda builtin: ran.append(builtin), raising=False)
    settings.run()
    assert ran == ['ActivateWindow(playersettings,subtitles)']
