# -*- coding: utf-8 -*-
# The window interface: entry from the plugin root and from RunScript, and the classic fallback.
# Imports only lib.kodi and the logger, so the plugin router can ask enabled() for free.

import os
import traceback

from ..lib import kodi, logger

PLUGIN = 'plugin://plugin.video.a4kstreaming/'
SKIN_XML = os.path.join(kodi.addon_path, 'resources', 'skins', 'Default', '1080i', 'a4k-home.xml')
SCRIPT = os.path.join(kodi.addon_path, 'ui.py')
HOME_WINDOW = 10000
VIDEOS_WINDOW = 10025

# session state lives on Kodi's Home window, so it outlives one plugin or script invocation
FAILED = 'a4k.ui.failed'
OPEN_WINDOW = 'a4k.ui.window'

# rows the service keeps warm: the public ones, the same URLs the home window loads
PREWARM_ROWS = ['popularMovies', 'popularTVShows']

def row_url(type):
    return '%s?action=query&type=%s&widget=1' % (PLUGIN, type)

def __home():
    return kodi.xbmcgui.Window(HOME_WINDOW)

def windows_mode():
    # ui.mode enum: 0 Windows (default), 1 Classic
    return kodi.get_setting('ui.mode') != '1'

def fail(reason):
    # drop to classic for the rest of the session; log only the first failure
    if __home().getProperty(FAILED):
        return
    __home().setProperty(FAILED, 'true')
    logger.error('window interface failed, using the classic listing: %s' % reason)

def enabled():
    # the plugin root opens the windows only when asked from the Videos window: a skin widget or a script asking for the
    # root without widget=1 still gets the classic listing
    if not windows_mode() or __home().getProperty(FAILED):
        return False
    if kodi.xbmcgui.getCurrentWindowId() != VIDEOS_WINDOW:
        return False
    missing = [path for path in (SKIN_XML, SCRIPT) if not os.path.exists(path)]
    if missing:
        fail('missing %s' % ', '.join(missing))
        return False
    return True

def open_from_root(handle):
    # the root directory is not listed; the home window opens over the Videos window instead
    kodi.xbmcplugin.endOfDirectory(handle, succeeded=False)
    kodi.xbmc.executebuiltin('RunScript(%s)' % kodi.addon_id)

def classic():
    kodi.xbmc.executebuiltin('ActivateWindow(Videos,%s,return)' % PLUGIN)

def run():
    if not windows_mode() or __home().getProperty(FAILED):
        return classic()

    # the home window is still open further back (the user went Home, or ".." in a listing reached the root): go back
    # to it rather than open a second one
    window_id = __home().getProperty(OPEN_WINDOW)
    if window_id:
        try:
            if kodi.xbmcgui.Window(int(window_id)).getProperty('a4k.home'):
                from .home import replace_current
                return replace_current(window_id)
        except Exception:
            pass
        __home().clearProperty(OPEN_WINDOW)

    try:
        from . import home
        home.open()
    except Exception:
        fail(traceback.format_exc())
        classic()

def prewarm():
    # service side: list the public home rows through Kodi, the same code path and cache keys the window uses, so the
    # first home open after start (or after the gallery cache TTL) reads warm cache
    if not windows_mode():
        return
    for type in PREWARM_ROWS:
        kodi.json_rpc('Files.GetDirectory', {'directory': row_url(type), 'media': 'files'}, log_error=False)
