# -*- coding: utf-8 -*-
# Kodi setup mode: Kodi set up as an a4kStreaming device. It opens the add-on when Kodi starts (service.py), Back on the
# add-on's home asks before leaving it (ui/home.py), menu sounds and popups go off, Estuary's home menu keeps only
# Favourites with a4kStreaming in it, and a keymap makes Back stop any video. Each value it changes is saved first in
# kodi_mode.json (the add-on's profile); the file being there is what "on" means. Turning it off puts the saved values
# back, except those the user changed since, or resets the values it manages to Kodi's defaults.

import io
import json
import os
from xml.etree import ElementTree

from .lib import kodi, logger, utils

PATH = os.path.join(kodi.addon_profile, 'kodi_mode.json')
PROMPTED = 'kodi_mode.prompted'  # hidden setting: the one-time question on the add-on's home was asked
AUTOOPENED = 'a4k.kodi_mode.opened'  # on Kodi's Home window: the add-on opened itself this Kodi session
AUTOOPEN_WAIT = 30  # s the service waits for Kodi's Home to be idle after start
# s Home must stay idle with nothing playing first: Kodi started by an Android "open with" shows Home and asks for the
# play about 3.5 s later (seen on the TV box)
# ponytail: a timing guess; a slower play request still finds the add-on open and plays over it
AUTOOPEN_SETTLE = 4
LOOK = 0.5
ESTUARY = 'skin.estuary'
KEYMAP = 'a4kstreaming.xml'

# Kodi settings (JSON-RPC ids): the value set, the sheet's line
KODI = {
    'audiooutput.guisoundmode': (0, 'Menu sounds off', 'Kodi: Play GUI sounds, Never'),
    'lookandfeel.enablerssfeeds': (False, 'News ticker off', "The RSS line at the bottom of Kodi's home"),
    'general.addonnotifications': (False, 'Add-on update popups off', 'Updates still install'),
}
# Estuary's main menu items, hidden by these skin bools; Favourites stays, a4kStreaming is its one tile
HIDE = {'HomeMenuNoMovieButton': 'Movies', 'HomeMenuNoTVShowButton': 'TV shows', 'HomeMenuNoMusicButton': 'Music',
        'HomeMenuNoMusicVideoButton': 'Music videos', 'HomeMenuNoTVButton': 'TV', 'HomeMenuNoRadioButton': 'Radio',
        'HomeMenuNoGamesButton': 'Games', 'HomeMenuNoProgramsButton': 'Add-ons', 'HomeMenuNoPicturesButton': 'Pictures',
        'HomeMenuNoVideosButton': 'Videos', 'HomeMenuNoWeatherButton': 'Weather'}
FAV_BUTTON = 'HomeMenuNoFavButton'
SKIN_BOOLS = dict([(name, True) for name in HIDE] + [(FAV_BUTTON, False)])
# the keys that are Back in the video window, per keymap section (keyboard: Android's Back arrives as backspace)
BACK_KEYS = {'keyboard': ('backspace', 'escape', 'browser_back'), 'remote': ('back',),
             'gamepad': ('back', 'b'), 'joystick': ('back', 'b')}
KEYMAP_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<!-- a4kStreaming, Kodi setup mode: Back stops the video. Turning the mode off deletes this file. -->
<keymap>
  <FullscreenVideo>
    <keyboard><backspace>Stop</backspace><escape>Stop</escape><browser_back>Stop</browser_back></keyboard>
    <remote><back>Stop</back></remote>
    <gamepad><back>Stop</back><b>Stop</b></gamepad>
    <joystick profile="game.controller.default"><b>Stop</b></joystick>
  </FullscreenVideo>
</keymap>
'''
UNDO = ('Your current values are saved', 'To undo: a4kStreaming settings, Advanced, Kodi setup mode')

# Kodi

def rpc(method, **params):
    # the call's result, None on an error
    try:
        answer = json.loads(kodi.xbmc.executeJSONRPC(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})))
    except Exception:
        return None
    if 'error' in answer:
        logger.error('%s: %s' % (method, answer['error']))
    return answer.get('result')

def get(id):
    return (rpc('Settings.GetSettingValue', setting=id) or {}).get('value')

def skin():
    return get('lookandfeel.skin')

def skin_bool(name):
    return bool(kodi.xbmc.getCondVisibility('Skin.HasSetting(%s)' % name))

def set_skin_bool(name, value):
    kodi.xbmc.executebuiltin('Skin.SetBool(%s,%s)' % (name, 'true' if value else 'false'), True)

def save():
    # JSON-RPC changes live in memory until Kodi saves its settings; a skin builtin saves them (Kodi on Android is
    # often killed rather than quit). The bool does not exist, so nothing else changes.
    kodi.xbmc.executebuiltin('Skin.Reset(a4k.kodi_mode)', True)

def favourite():
    # the a4kStreaming favourite, as AddFavourite wants it (a toggle: the same call removes it)
    return dict(type='script', path=kodi.addon_id, title=kodi.addon_name, thumbnail=kodi.addon_icon)

def favourite_present():
    found = (rpc('Favourites.GetFavourites', properties=['path']) or {}).get('favourites') or []
    return any(item.get('type') == 'script' and kodi.addon_id in (item.get('path') or '') for item in found)

def toggle_favourite():
    rpc('Favourites.AddFavourite', **favourite())

def keymaps():
    return kodi.xbmcvfs.translatePath('special://profile/keymaps/')

def keymap_path():
    return os.path.join(keymaps(), KEYMAP)

def keymap_taken():
    # a keymap of the user's maps Back in the video window already (an unreadable one counts: its keys are left alone)
    folder = keymaps()
    names = os.listdir(folder) if os.path.isdir(folder) else []
    for name in names:
        if not name.lower().endswith('.xml') or name == KEYMAP:
            continue
        try:
            root = ElementTree.parse(os.path.join(folder, name)).getroot()
        except Exception:
            return True
        for window in root.iter():
            if window.tag.lower() != 'fullscreenvideo':
                continue
            for section in window:
                keys = BACK_KEYS.get(section.tag.lower(), ())
                if any(key.tag.lower() in keys for key in section):
                    return True
    return False

def reload_keymaps():
    kodi.xbmc.executebuiltin('Action(reloadkeymaps)')

# the saved state

def load(path=None):
    try:
        with io.open(path or PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

def write(state, path=None):
    folder = os.path.dirname(PATH)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    utils.write_atomic(path or PATH, json.dumps(state))  # a kill mid-write leaves the previous file, never a truncated one

def active():
    return os.path.exists(PATH)

def leftover_path():
    # Estuary's home menu bools a turn-off on another skin could not put back: Skin.SetBool reaches the current skin only
    return os.path.splitext(PATH)[0] + '.leftover.json'

def leave_for_later(state, reset=False):
    if state.get('skin_bools') and skin() != state.get('skin'):
        write({'skin': state['skin'], 'skin_bools': state['skin_bools'], 'reset': reset}, leftover_path())

def finish_leftover():
    # the menu bools left by a turn-off on another skin, done once their skin is the current one (the service at start,
    # the confirm sheet before it plans). True when done.
    state = load(leftover_path()) if os.path.exists(leftover_path()) else None
    if not state or skin() != state.get('skin'):
        return False
    if state.get('reset'):  # as reset_defaults on Estuary: every bool the mode manages
        for name in SKIN_BOOLS:
            kodi.xbmc.executebuiltin('Skin.Reset(%s)' % name, True)
    else:  # as restore: what was, except those changed since
        for name, item in state.get('skin_bools', {}).items():
            if skin_bool(name) == item['set']:
                set_skin_bool(name, item['was'])
    save()
    os.remove(leftover_path())
    return True

def drift(state):
    # the saved items the user changed since: [(label, label2)]
    found = []
    for id, item in state.get('kodi', {}).items():
        if get(id) != item['set']:
            found.append((KODI[id][1], 'Changed since: kept as you set it'))
    if state.get('skin_bools') and skin() == state.get('skin'):
        for name, item in state['skin_bools'].items():
            if skin_bool(name) != item['set']:
                found.append(('Home menu: %s' % HIDE.get(name, 'Favourites'), 'Changed since: kept as you set it'))
    return found

def status():
    # the settings row's value
    if not active():
        return 'Off'
    state = load()
    if state is None:
        return 'Active (saved values unreadable)'
    changed = len(drift(state))
    return 'Active, %s changed since' % changed if changed else 'Active'

# turning it on

def plan():
    # what turning it on would change: {kodi: {id: [was, set]}, skin_bools: {...}, favourite, keymap, estuary}
    current = skin()
    estuary = current == ESTUARY
    kodi_now = dict((id, get(id)) for id in KODI)
    bools_now = dict((name, skin_bool(name)) for name in SKIN_BOOLS) if estuary else {}
    return {
        'skin': current,
        'kodi': dict((id, {'was': kodi_now[id], 'set': value}) for id, (value, _, _) in KODI.items() if kodi_now[id] != value),
        'skin_bools': dict((name, {'was': now, 'set': SKIN_BOOLS[name]}) for name, now in bools_now.items() if now != SKIN_BOOLS[name]),
        'favourite': not favourite_present(),
        'keymap': not keymap_taken() and not os.path.exists(keymap_path()),
        'estuary': estuary,
    }

def lines(state):
    # the confirm sheet's rows, one per change: (label, label2)
    rows = [('Opens a4kStreaming when Kodi starts', 'Once per Kodi start, from Kodi\'s home'),
            ('Back on a4kStreaming\'s home asks first', 'Exit, or go to Kodi\'s menu')]
    rows += [(KODI[id][1], KODI[id][2]) for id in state['kodi']]
    if not state['estuary']:
        rows.append(('Home menu: needs the Estuary skin', 'Left as it is'))
    elif state['skin_bools']:
        rows.append(("Kodi's home menu shows only Favourites", '%s hidden; Kodi settings stay on the gear icon'
                     % ', '.join(HIDE.values())))
    if state['favourite']:
        rows.append(('a4kStreaming in your Kodi favourites', "On Kodi's home as a Favourites tile"))
    if state['keymap']:
        rows.append(('Back stops any video, also outside a4kStreaming', 'Not over the on-screen controls'))
    elif not os.path.exists(keymap_path()):
        rows.append(('Back in videos: left as it is', 'A keymap of yours already sets it'))
    return rows + [UNDO]

def apply(state):
    # the planned changes, the file written before the first one; the file keeps what took. On already (another sheet
    # was answered first): nothing, so the saved originals are not overwritten by values the mode set itself
    if active():
        return load()
    state = dict((key, value) for key, value in state.items() if key != 'estuary')
    state['v'] = 1
    write(state)
    for id, item in state['kodi'].items():
        rpc('Settings.SetSettingValue', setting=id, value=item['set'])
    for name, item in state['skin_bools'].items():
        set_skin_bool(name, item['set'])
    if state['favourite']:
        toggle_favourite()
    if state['keymap']:
        if not os.path.isdir(keymaps()):
            os.makedirs(keymaps())
        with io.open(keymap_path(), 'w', encoding='utf-8') as f:
            f.write(KEYMAP_XML)
        reload_keymaps()
    save()
    state['kodi'] = dict((id, item) for id, item in state['kodi'].items() if get(id) == item['set'])
    state['skin_bools'] = dict((name, item) for name, item in state['skin_bools'].items() if skin_bool(name) == item['set'])
    state['favourite'] = state['favourite'] and favourite_present()
    write(state)
    return state

# turning it off

def remove_extras(state, any_favourite=False):
    # the favourite and the keymap, when the mode added them and they are still there
    if (state.get('favourite') or any_favourite) and favourite_present():
        toggle_favourite()
    if os.path.exists(keymap_path()):
        os.remove(keymap_path())
        reload_keymaps()

def restore():
    # the saved values back, except those changed since (returned, as drift lines); the file goes
    state = load() or {}
    kept = drift(state)
    for id, item in state.get('kodi', {}).items():
        if get(id) == item['set']:
            rpc('Settings.SetSettingValue', setting=id, value=item['was'])
    if skin() == state.get('skin'):
        for name, item in state.get('skin_bools', {}).items():
            if skin_bool(name) == item['set']:
                set_skin_bool(name, item['was'])
    leave_for_later(state)
    remove_extras(state)
    save()
    os.remove(PATH)
    return kept

def reset_defaults():
    # every value the mode manages, changed by it or not, to Kodi's default; the favourite and keymap go
    state = load() or {}
    for id in KODI:
        rpc('Settings.ResetSettingValue', setting=id)
    if skin() == ESTUARY:
        for name in SKIN_BOOLS:
            kodi.xbmc.executebuiltin('Skin.Reset(%s)' % name, True)
    leave_for_later(state, reset=True)
    remove_extras(state, any_favourite=True)
    save()
    if os.path.exists(PATH):
        os.remove(PATH)

# the sheets

def sheet():
    # the settings row: the confirm sheet when off, Restore / Reset when on
    from .ui import sheets
    if not active():
        return confirm()
    state = load() or {}
    kept = drift(state)
    restore_line = 'Puts back what Kodi had before'
    if kept:
        restore_line += '; %s you changed since stay as they are' % len(kept)
    rows = [('Turn off: restore earlier settings', restore_line),
            ('Turn off: reset these to Kodi defaults', 'Only what this mode manages'),
            ('Cancel', '')] + kept
    choice = sheets.select('Kodi setup mode', [label for label, _ in rows], preselect=2, rows=rows, actions=3)
    if choice == 0:
        restore()
        kodi.notification('Kodi setup mode is off')
    elif choice == 1:
        reset_defaults()
        kodi.notification('Kodi setup mode is off: Kodi defaults')

def confirm():
    # every change in plain words, then Turn on / Cancel. True when turned on.
    from .ui import sheets
    finish_leftover()
    state = plan()
    rows = [('Turn on', ''), ('Cancel', '')] + lines(state)
    if sheets.select('Set up Kodi for a4kStreaming', [label for label, _ in rows], preselect=0, rows=rows, actions=2) != 0:
        return False
    apply(state)
    kodi.notification('Kodi setup mode is on')
    return True

def prompt():
    # the one-time question on the add-on's home (ui/home.py asks for it once): either answer is an answer
    from .ui import sheets
    kodi.xbmcaddon.Addon(kodi.addon_id).setSetting(PROMPTED, 'true')
    rows = [('Set it up…', 'Opens it with Kodi; lists each change first'), ('Not now', '')]
    if sheets.select('Start Kodi straight into a4kStreaming?', [label for label, _ in rows], preselect=0, rows=rows) == 0:
        confirm()

def prompt_due():
    return not active() and kodi.get_setting(PROMPTED) != 'true'

# the service

def autoopen(monitor):
    # once per Kodi session, with the mode on: open the add-on once Kodi's Home has been on screen for a moment with
    # no dialog over it. Not when Kodi started to play something (an Android "open with"), not when the add-on is open
    # already.
    home = kodi.xbmcgui.Window(10000)
    if not active() or home.getProperty(AUTOOPENED):
        return False
    home.setProperty(AUTOOPENED, 'true')
    xbmc = kodi.xbmc
    idle = 0
    for _ in range(int(AUTOOPEN_WAIT / LOOK)):
        if xbmc.getCondVisibility('Player.HasMedia') or home.getProperty('a4k.ui.window'):
            return False
        idle = idle + 1 if xbmc.getCondVisibility('Window.IsActive(home) + !System.HasActiveModalDialog') else 0
        if (idle - 1) * LOOK >= AUTOOPEN_SETTLE:  # the time since the first idle look, not the count of looks
            xbmc.executebuiltin('RunScript(%s,autoopen)' % kodi.addon_id)
            return True
        if monitor.waitForAbort(LOOK):
            return False
    return False
