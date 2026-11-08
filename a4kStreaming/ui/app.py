# -*- coding: utf-8 -*-
# The window interface's entry: the plugin root asked from the Videos window (the Add-ons row, a favourite) and the
# script (Program add-ons) open the home window. Imports only lib.kodi and the logger, so main.py asks it before the router loads.

import traceback
from urllib.parse import parse_qsl

from ..lib import kodi, logger

PLUGIN = 'plugin://plugin.video.a4kstreaming/'
HOME_WINDOW = 10000
VIDEOS_WINDOW = 10025

# on Kodi's Home window, so it outlives one plugin or script invocation: the a4k window on screen
OPEN_WINDOW = 'a4k.ui.window'
BUSY_LOOKS = 50
BUSY_LOOK = 20  # ms

def row_url(type):
    return '%s?action=query&type=%s&widget=1' % (PLUGIN, type)

def __home():
    return kodi.xbmcgui.Window(HOME_WINDOW)

def from_videos(paramstring):
    # the root asked by the Videos window opens the home window; a skin widget (widget=1), a widget picker or a script
    # asking for the root gets the listing
    params = dict(parse_qsl(paramstring.lstrip('?')))
    return 'action' not in params and params.get('widget') != '1' and \
        kodi.xbmcgui.getCurrentWindowId() == VIDEOS_WINDOW

def reopen(cover=None):
    # the home window is still open further back (the user went Home, or reopened the add-on): go back to it rather
    # than open a second one. True when it did.
    window_id = __home().getProperty(OPEN_WINDOW)
    if window_id:
        try:
            if kodi.xbmcgui.Window(int(window_id)).getProperty('a4k.home'):
                from .home import replace_current
                if cover:
                    cover.close()
                replace_current(window_id)
                return True
        except Exception:
            pass
        __home().clearProperty(OPEN_WINDOW)
    return False

def launch(handle):
    # The plugin root from the Videos window, run in this process: no RunScript hop to a second interpreter (Kodi neither
    # waits on nor stops a plugin that goes on after endOfDirectory). Kodi refuses to activate a window while a modal
    # dialog is up: its busy dialog, waiting on this call, and the cover itself unless it is closing. So the cover (the
    # home window's first frame) goes up first and hides the Videos window as it lists its root; it starts closing as
    # the home window takes its place, and its close animation keeps it drawn until the home window is on screen.
    cover = kodi.xbmcgui.WindowXMLDialog('a4k-cover.xml', kodi.addon_path, 'Default', '1080i')
    cover.show()
    kodi.xbmcplugin.endOfDirectory(handle, succeeded=False)
    for _ in range(BUSY_LOOKS):  # Kodi closes its busy dialog a moment after the directory ends
        if not kodi.xbmc.getCondVisibility('Window.IsActive(busydialog)'):
            break
        kodi.xbmc.sleep(BUSY_LOOK)
    try:
        if not reopen(cover):
            __open(cover)
    finally:
        cover.close()

def run():
    # the script entry (Program add-ons)
    if not reopen():
        __open()

def __open(cover=None):
    try:
        from . import home
        home.open(cover)
    except Exception:
        logger.error('home window failed: %s' % traceback.format_exc())

def prewarm():
    # service side: list the public home rows that are on (Appearance) through Kodi, the same code path and cache keys
    # the window uses, so the first home open after start (or after the gallery cache TTL) reads warm cache
    from .appearance import public_types
    for type in public_types():
        kodi.json_rpc('Files.GetDirectory', {'directory': row_url(type), 'media': 'files'}, log_error=False)
