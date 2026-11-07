# -*- coding: utf-8 -*-
# Home window: the top shelf (first trending movie), the rows and the Browse tiles of a4k-home.xml.
# The rows are the plugin's own listings loaded by Kodi (<content>), so this file only routes clicks and the hero menu.

import traceback
from types import SimpleNamespace

from ..lib import kodi
from . import app

ROWS = (301, 302, 303)
HERO_PLAY = 201
HERO_INFO = 202
HERO_ITEM = 'Container(301).ListItemAbsolute(0)'

ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92
ACTION_SELECT_ITEM = 7
ACTION_MOUSE_LEFT_CLICK = 100
ACTION_CONTEXT_MENU = 117

INFO = ('FolderPath', 'Property(a4k.id)', 'Property(a4k.type)', 'Property(a4k.rated)', 'Property(a4k.trailers)')

def labels(item):
    # read before any dialog opens: Container(id) resolves against the topmost dialog first
    return {key: kodi.xbmc.getInfoLabel('%s.%s' % (item, key)) for key in INFO}

def click_builtin(info):
    # what selecting a row item does, the same as in the classic listing: movies and episodes play, series open their
    # seasons, anything else with a path (the row's Next item) opens as a listing
    type = info.get('Property(a4k.type)', '')
    id = info.get('Property(a4k.id)', '')
    path = info.get('FolderPath', '')
    if type in ('movie', 'tvEpisode'):
        return 'PlayMedia(%s)' % (path or '%s?action=play&type=&id=%s' % (app.PLUGIN, id))
    if type == 'tvSeries':
        return 'ActivateWindow(Videos,%s,return)' % (path or '%s?action=query&type=seasons&id=%s' % (app.PLUGIN, id))
    if path and not type:
        return 'ActivateWindow(Videos,%s,return)' % path
    return None

def title_from_info(info):
    # the title dict listing.title_context_menu reads, rebuilt from the a4k.* item properties
    trailers = info.get('Property(a4k.trailers)', '')
    return {
        'id': info.get('Property(a4k.id)', ''),
        'titleType': info.get('Property(a4k.type)', ''),
        'primaryVideos': trailers.split('_') if trailers else None,
        'userRating': 1 if info.get('Property(a4k.rated)', '') == 'true' else None,
    }

def run(builtin):
    if builtin:
        kodi.xbmc.executebuiltin(builtin)

class Home(kodi.xbmcgui.WindowXML):
    error = None

    def onInit(self):
        # runs again on every return to the window (after playback, after a listing): no network, nothing to undo
        try:
            # raises when the XML did not load; a grouplist would raise anyway (Python cannot wrap that type)
            self.getControl(HERO_PLAY)
            kodi.xbmcgui.Window(app.HOME_WINDOW).setProperty(app.OPEN_WINDOW, str(kodi.xbmcgui.getCurrentWindowId()))
        except Exception:
            self.__fail()

    def onAction(self, action):
        try:
            action_id = action.getId()
            if action_id in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
                return self.close()
            focus = self.getFocusId()
            if action_id in (ACTION_SELECT_ITEM, ACTION_MOUSE_LEFT_CLICK) and focus in ROWS:
                run(click_builtin(labels('Container(%s).ListItem' % focus)))
            elif action_id == ACTION_CONTEXT_MENU and focus in (HERO_PLAY, HERO_INFO):
                # rows get Kodi's own menu with the listing's items; the hero buttons are not list items
                self.hero_menu()
        except Exception:
            self.__fail()

    def onClick(self, control_id):
        try:
            info = labels(HERO_ITEM)
            if control_id == HERO_PLAY:
                run(click_builtin(info))
            elif control_id == HERO_INFO and info['Property(a4k.id)']:
                run('ActivateWindow(Videos,%s?action=query&type=browse&id=%s,return)' % (app.PLUGIN, info['Property(a4k.id)']))
        except Exception:
            self.__fail()

    def hero_menu(self):
        info = labels(HERO_ITEM)
        if not info['Property(a4k.id)']:
            return
        from .. import listing
        items = listing.title_context_menu(SimpleNamespace(url=app.PLUGIN, kodi=kodi), title_from_info(info))
        choice = kodi.xbmcgui.Dialog().contextmenu([label for label, _ in items])
        if choice is not None and choice >= 0:
            run(items[choice][1])

    def __fail(self):
        self.error = traceback.format_exc()
        self.close()

# Kodi's ids for script windows (WINDOW_PYTHON_START..END)
PYTHON_WINDOWS = range(13000, 13100)

def window_id(window):
    # a script window cannot ask its own id; find it by a property only this instance carries
    token = str(id(window))
    window.setProperty('a4k.token', token)
    for candidate in PYTHON_WINDOWS:
        try:
            if kodi.xbmcgui.Window(candidate).getProperty('a4k.token') == token:
                return candidate
        except Exception:  # no such window
            continue
    return None

def replace_current(window_id):
    # Take the place of the window we were opened from (the Videos add-on list) in Kodi's window history. The history
    # holds each window id once: with Videos under the home window, opening a listing in Videos cuts the home window out
    # of it, and Back from the listing lands on Kodi's Home screen. Back from the home window now goes to Home, too.
    kodi.xbmc.executebuiltin('ReplaceWindow(%s)' % window_id, True)

def open():
    window = Home('a4k-home.xml', kodi.addon_path, 'Default', '1080i')
    # row URLs are set before the window opens: a row's provider fires once, at load (spike 2b)
    window.setProperty('a4k.home', 'true')
    window.setProperty('a4k.row.301', app.row_url('popularMovies'))
    window.setProperty('a4k.row.302', app.row_url('popularTVShows'))
    if kodi.get_setting('imdb.at-main'):
        window.setProperty('a4k.auth', 'true')
        window.setProperty('a4k.row.303', app.row_url('watchlist'))
    own_id = window_id(window)
    if own_id:
        replace_current(own_id)  # doModal then skips its own, history-adding, activation
    try:
        window.doModal()
    finally:
        kodi.xbmcgui.Window(app.HOME_WINDOW).clearProperty(app.OPEN_WINDOW)
    error = window.error
    del window
    if error:
        raise RuntimeError(error)
