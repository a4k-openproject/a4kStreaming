# -*- coding: utf-8 -*-

import os
import sys
import json
import re
import time
import importlib
from contextlib import contextmanager
from threading import Event, Thread, Timer

kodi = sys.modules[__name__]
api_mode = os.getenv('A4KSTREAMING_API_MODE')

if api_mode:
    try: api_mode = json.loads(api_mode)
    except: api_mode = None

if api_mode:
    if api_mode.get('kodi', False):
        from .kodi_mock import xbmc, xbmcaddon, xbmcplugin, xbmcgui, xbmcvfs, set_info_tag
    else:
        from . import kodi_mock

        for target in ['xbmc', 'xbmcaddon', 'xbmcplugin', 'xbmcgui', 'xbmcvfs']:
            if target == 'kodi':
                continue
            elif api_mode.get(target, False):
                mod = getattr(kodi_mock, target)
            else:
                mod = importlib.import_module(target)
            setattr(kodi, target, mod)

        set_info_tag = kodi_mock.set_info_tag
else:
    import xbmc
    import xbmcaddon
    import xbmcplugin
    import xbmcgui
    import xbmcvfs
    from .kodi_listitem import set_info_tag

addon = xbmcaddon.Addon('plugin.video.a4kstreaming')
addon_id = addon.getAddonInfo('id')
addon_name = addon.getAddonInfo('name')
addon_version = addon.getAddonInfo('version')
addon_icon = addon.getAddonInfo('icon')
addon_path = xbmcvfs.translatePath(addon.getAddonInfo('path'))
addon_profile = xbmcvfs.translatePath(addon.getAddonInfo('profile'))

def json_rpc(method, params, log_error=True):
    try:
        result = xbmc.executeJSONRPC(
            json.dumps({
                'jsonrpc': '2.0',
                'method': method,
                'id': 1,
                'params': params or {}
            })
        )
        if 'error' in result and log_error:
            from . import logger
            logger.error(result)
        return json.loads(result)['result']['value']
    except KeyError:
        return None

def string(id, default):
    # the add-on's own string from strings.po; the English default where Kodi has none (the offline mock)
    try: return addon.getLocalizedString(id) or default
    except Exception: return default

def get_kodi_setting(setting, log_error=True):
    return json_rpc('Settings.GetSettingValue', {"setting": setting}, log_error)

def notification(text, time=3000):
    def __run(): xbmc.executebuiltin('Notification(%s, %s, %d, %s)' % (addon_name, text, time, addon_icon))
    try: notification.t.cancel()
    except: pass
    notification.t = Timer(0.5, __run)
    notification.t.start()

BUSY = 'a4k.busy'  # on Kodi's Home window: the add-on's own windows draw their traced-D loader while it is set
NATIVE_BUSY = ('busydialog', 'busydialognocancel')
NATIVE_LOOK = 0.05  # s between looks for Kodi's busy dialog while the loader stands in for it
BUSY_BEAT = 1  # s between fresh time stamps in BUSY while the loader is up
BUSY_STALE = 60  # s: an older stamp was left by a plugin call killed before it could clear it
__busy = {'depth': 0, 'done': None, 'watch': None, 'native': False}

def __over_window():
    # one of the add-on's windows is on screen (ui/app.py OPEN_WINDOW holds the one on top)
    window = xbmcgui.Window(10000).getProperty('a4k.ui.window')
    return bool(window) and window == str(xbmcgui.getCurrentWindowId())

def busy_live():
    # the loader is up for a live call: BUSY holds a stamp its watcher renews every BUSY_BEAT. A stale stamp (a plugin
    # call killed mid-scope) is cleared here, so it neither blocks the windows nor keeps the loader drawn.
    stamp = xbmcgui.Window(10000).getProperty(BUSY)
    try:
        if time.time() - float(stamp) < BUSY_STALE:
            return True
    except ValueError:
        pass
    if stamp:
        xbmcgui.Window(10000).clearProperty(BUSY)
    return False

def __keep_native_closed(done):
    # Kodi opens its busy dialog 220 ms into a plugin call it waits on (PlayMedia of a plugin:// URL) and keeps it
    # until the call ends, drawn whenever no other modal dialog is above it. Over the add-on's windows the loader is
    # the one indicator, so Kodi's is closed as soon as it shows (its wait goes on without it and never reopens it).
    # It also renews the stamp in BUSY, for as long as the scope (a play spans the source sheet too) is alive.
    stamped = time.time()
    while True:
        for name in NATIVE_BUSY:
            if xbmc.getCondVisibility('Window.IsActive(%s)' % name):
                xbmc.executebuiltin('Dialog.Close(%s,true)' % name)
        if time.time() - stamped >= BUSY_BEAT:
            stamped = time.time()
            xbmcgui.Window(10000).setProperty(BUSY, str(stamped))
        if done.wait(NATIVE_LOOK):
            return

def open_busy_dialog(native=True):
    # Nested opens share the outermost one's indicator. Over one of the add-on's windows, that window's loader, with
    # Kodi's own busy dialog kept closed (the skins hide the loader under any modal dialog, so the two never show
    # together). Elsewhere Kodi's busy dialog when native.
    __busy['depth'] += 1
    if __busy['depth'] > 1:
        return
    if __over_window():
        xbmcgui.Window(10000).setProperty(BUSY, str(time.time()))
        __busy['done'] = done = Event()
        __busy['watch'] = Thread(target=__keep_native_closed, args=(done,), daemon=True)
        __busy['watch'].start()
    elif native:
        __busy['native'] = True
        xbmc.executebuiltin('ActivateWindow(busydialognocancel)')

def close_busy_dialog():
    if __busy['depth'] == 0:  # nothing open: an error path closing what it never opened
        return
    __busy['depth'] -= 1
    if __busy['depth']:
        return
    if __busy['done']:
        __busy['done'].set()
        __busy['watch'].join()  # its last stamp lands before the clear below, never after it
        __busy['done'] = __busy['watch'] = None
    xbmcgui.Window(10000).clearProperty(BUSY)
    if __busy['native']:
        __busy['native'] = False
        xbmc.executebuiltin('Dialog.Close(busydialognocancel)')

PLAYBACK_LOOK = 0.1  # s
PLAYBACK_START = 50  # looks (5 s) for the player to take the stream
PLAYBACK_LOOKS = 300  # looks (30 s) for its first frame: Kodi's own wait has no limit

def wait_for_playback():
    # Kodi opens the stream after the add-on hands it over and waits for the first frame behind its busy dialog. Over
    # the add-on's windows the loader stays up instead, until the video window takes over, the stream fails, or 30 s
    # pass; elsewhere there is nothing to stand in for.
    if not __busy['done']:
        return
    monitor = xbmc.Monitor()
    started = False
    for look in range(PLAYBACK_LOOKS):
        if not __over_window():
            return
        playing = xbmc.getCondVisibility('Player.HasMedia')
        if started and not playing or not started and look >= PLAYBACK_START:
            return
        started = started or playing
        if monitor.waitForAbort(PLAYBACK_LOOK):
            return

@contextmanager
def busy_dialog(native=True):
    open_busy_dialog(native)
    try:
        yield
    finally:
        close_busy_dialog()

def get_setting(group, id=None):
    key = '%s.%s' % (group, id) if id else group
    return xbmcaddon.Addon(addon_id).getSetting(key).strip()

def get_int_setting(group, id=None):
    return int(get_setting(group, id))

def get_bool_setting(group, id=None):
    return get_setting(group, id).lower() == 'true'
