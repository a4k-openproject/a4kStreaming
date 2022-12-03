# -*- coding: utf-8 -*-

import os
import sys
import json
import re
import importlib
from contextlib import contextmanager
from threading import Timer

kodi = sys.modules[__name__]
api_mode = os.getenv('A4KSTREAMING_API_MODE')

if api_mode:
    try: api_mode = json.loads(api_mode)
    except: api_mode = None

if api_mode:
    if api_mode.get('kodi', False):
        from .kodi_mock import xbmc, xbmcaddon, xbmcplugin, xbmcgui, xbmcvfs
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

else:
    import xbmc
    import xbmcaddon
    import xbmcplugin
    import xbmcgui
    import xbmcvfs

addon = xbmcaddon.Addon('plugin.video.a4kstreaming')
addon_id = addon.getAddonInfo('id')
addon_name = addon.getAddonInfo('name')
addon_version = addon.getAddonInfo('version')
addon_icon = addon.getAddonInfo('icon')
try:
    addon_path = xbmcvfs.translatePath(addon.getAddonInfo('path'))
    addon_profile = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
except:
    addon_path = xbmc.translatePath(addon.getAddonInfo('path'))
    addon_profile = xbmc.translatePath(addon.getAddonInfo('profile'))

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

def get_kodi_setting(setting, log_error=True):
    return json_rpc('Settings.GetSettingValue', {"setting": setting}, log_error)

def notification(text, time=3000):
    def __run(): xbmc.executebuiltin('Notification(%s, %s, %d, %s)' % (addon_name, text, time, addon_icon))
    try: notification.t.cancel()
    except: pass
    notification.t = Timer(0.5, __run)
    notification.t.start()

def open_busy_dialog():
    xbmc.executebuiltin('ActivateWindow(busydialognocancel)')

def close_busy_dialog():
    xbmc.executebuiltin('Dialog.Close(busydialognocancel)')

@contextmanager
def busy_dialog():
    open_busy_dialog()
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
