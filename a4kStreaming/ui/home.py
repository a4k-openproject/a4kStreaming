# -*- coding: utf-8 -*-
# Home window: the top shelf (the trending movies in turn), the rows and the Browse tiles of a4k-home.xml.
# The rows are the plugin's own listings loaded by Kodi (<content>), so this file only routes clicks and the hero menu
# and turns the top shelf.

import threading
import traceback
from types import SimpleNamespace

from ..lib import kodi, logger
from . import app

ROWS = (301, 302, 303)
ROW_TITLES = {301: 'Trending Movies', 302: 'Trending TV Shows', 303: 'Watchlist'}
HERO_PLAY = 201
HERO_INFO = 202
HERO_ROW = 301
TILES = 400

# the top menu (a4k-home.xml 160): Watch Now, the category tabs (the Category tabs setting), Search and the Settings gear
WATCH_NOW = 161
TABS = {162: ('popularMovies', 'Trending Movies'), 163: ('popularTVShows', 'Trending TV Shows'),
        164: ('popularAnimations', 'Animations'), 165: ('popularAnimationTVShows', 'Animated TV'),
        166: ('popularRealityTVShows', 'Reality TV')}
SEARCH = 167
SETTINGS = 168
MENU = (WATCH_NOW, SEARCH, SETTINGS) + tuple(TABS)

# the top shelf turns to the next of the first HERO_COUNT trending movies every HERO_TURN seconds
HERO_TURN = 15
HERO_COUNT = 6
HERO_FIELDS = {'label': 'Label', 'plot': 'Plot', 'year': 'Year', 'rating': 'Rating', 'mpaa': 'MPAA',
               'fanart': 'Art(fanart)', 'blur': 'Art(blur)'}  # a4k.hero.<key> = the item's InfoLabel
HERO_FADE = 0.25  # the hero text's fade-out in a4k-home.xml (a4k.hero.shown), before the next title is set
NO_DIALOG = 9999  # getCurrentWindowDialogId() with no modal dialog up

ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92
ACTION_SELECT_ITEM = 7
ACTION_MOUSE_LEFT_CLICK = 100
ACTION_CONTEXT_MENU = 117
ACTION_MOVES = (1, 2, 3, 4)
PREFETCH_DWELL = 0.4

INFO = ('FolderPath', 'Property(a4k.id)', 'Property(a4k.type)', 'Property(a4k.rated)', 'Property(a4k.trailers)',
        # what the detail window paints before its own request lands
        'Label', 'Plot', 'Year', 'Rating', 'MPAA', 'Genre', 'Duration(secs)', 'Art(fanart)', 'Art(blur)', 'Art(poster)')

def labels(item):
    # read before any dialog opens: Container(id) resolves against the topmost dialog first
    return {key: kodi.xbmc.getInfoLabel('%s.%s' % (item, key)) for key in INFO}

def click_builtin(info):
    # what selecting a row item does, the same as in the classic listing: movies and episodes play, series open their
    # seasons, anything else with a path opens as a listing
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

def select(info):
    # movies and series open the detail window; when it fails, the title's classic listing
    if info.get('Property(a4k.type)', '') in ('movie', 'tvSeries'):
        from . import detail
        if not detail.open(info):
            run(detail.classic(info))
        return
    run(click_builtin(info))

MORE_LIKE_THIS = 'IMDb: More like this'
ACCOUNT = '?action=profile&'  # rating, watched, watchlist and list actions: each needs an IMDb login

def menu(items, id, title):
    # a title's context list (label, builtin) as a select sheet, without the account actions when signed out (they
    # would only answer with the missing login notification); More like this opens the grid
    from . import sheets
    if not kodi.get_setting('imdb.at-main'):
        items = [item for item in items if ACCOUNT not in item[1]]
    choice = sheets.select(title, [label for label, _ in items])
    if choice is None or choice < 0:
        return
    label, builtin = items[choice]
    if label == MORE_LIKE_THIS:
        from . import grid
        return grid.more_like_this(id, title)
    run(builtin)

def prefetch(item):
    # the detail request of the title at item (an InfoLabel prefix such as Container(301).ListItem), made now so its
    # detail window opens with the shelves already there
    type = kodi.xbmc.getInfoLabel(item + '.Property(a4k.type)')
    id = kodi.xbmc.getInfoLabel(item + '.Property(a4k.id)')
    if type in ('movie', 'tvSeries') and id:
        from . import detail
        detail.fetch(detail.plugin_core(), id, type == 'tvSeries')

class Home(kodi.xbmcgui.WindowXML):
    error = None
    timer = None
    hero = 0
    own_id = None
    stopped = None

    def onInit(self):
        # runs again on every return to the window (after playback, after a listing): no network, nothing to undo
        try:
            # raises when the XML did not load; a grouplist would raise anyway (Python cannot wrap that type)
            self.getControl(HERO_PLAY)
            self.own_id = kodi.xbmcgui.getCurrentWindowId()
            kodi.xbmcgui.Window(app.HOME_WINDOW).setProperty(app.OPEN_WINDOW, str(self.own_id))
            if self.stopped is None:
                self.stopped = threading.Event()
                threading.Thread(target=self.rotate).start()
        except Exception:
            self.__fail()

    def onAction(self, action):
        try:
            action_id = action.getId()
            focus = self.getFocusId()
            if action_id in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
                return self.back(focus)
            if action_id in ACTION_MOVES:
                return self.dwell()
            selected = action_id in (ACTION_SELECT_ITEM, ACTION_MOUSE_LEFT_CLICK)
            if selected and focus in ROWS:
                info = labels('Container(%s).ListItem' % focus)
                if not info['Property(a4k.type)'] and 'paginationToken=' in info['FolderPath']:
                    from . import grid  # the row's Next item: the rest of the row in the grid
                    return grid.show(info['FolderPath'], ROW_TITLES[focus])
                select(info)
            elif selected and focus == TILES:
                tile = kodi.xbmc.getInfoLabel('Container(%s).ListItem.Property(a4k.grid)' % TILES)
                if tile:  # Debrid and Settings run their own onclick
                    from . import grid
                    grid.browse(tile, kodi.xbmc.getInfoLabel('Container(%s).ListItem.Label' % TILES))
            elif action_id == ACTION_CONTEXT_MENU and focus in (HERO_PLAY, HERO_INFO):
                # rows get Kodi's own menu with the listing's items; the hero buttons are not list items
                self.hero_menu()
        except Exception:
            self.__fail()

    def back(self, focus):
        # as dobby: Back on a row goes to the top shelf's Play, on the top shelf to Watch Now, on the top menu it leaves
        if focus in MENU:
            return self.close()
        self.setFocusId(WATCH_NOW if focus in (HERO_PLAY, HERO_INFO) else HERO_PLAY)

    def onClick(self, control_id):
        try:
            if control_id in MENU:
                return self.tab(control_id)
            info = labels(self.hero_item())
            if control_id == HERO_PLAY:
                run(click_builtin(info))
            elif control_id == HERO_INFO and info['Property(a4k.id)']:
                select(info)
        except Exception:
            self.__fail()

    def tab(self, control_id):
        if control_id == WATCH_NOW:
            self.setFocusId(HERO_PLAY)
        elif control_id == SEARCH:
            from . import grid
            grid.search()
        elif control_id == SETTINGS:
            run('Addon.OpenSettings(%s)' % kodi.addon_id)
        else:
            from . import grid
            grid.show(app.row_url(TABS[control_id][0]), TABS[control_id][1])

    def hero_item(self):
        return 'Container(%s).ListItemAbsolute(%s)' % (HERO_ROW, self.hero)

    def show_hero(self):
        item = self.hero_item()
        for key, field in HERO_FIELDS.items():
            self.setProperty('a4k.hero.%s' % key, kodi.xbmc.getInfoLabel('%s.%s' % (item, field)))
        self.setProperty('a4k.hero.shown', 'true')  # the text fades in; the art crossfades by its fadetime

    def rotate(self):
        # Paint the top shelf as soon as its row is in (Kodi gives the window no event for that: look every 100 ms,
        # 15 s at most), then turn it every HERO_TURN seconds until the window closes.
        try:
            for _ in range(150):
                if self.stopped.is_set() or kodi.xbmc.getInfoLabel('Container(%s).NumItems' % HERO_ROW) not in ('', '0'):
                    break
                self.stopped.wait(0.1)
            if not self.stopped.is_set():
                self.show_hero()
            self.setProperty('a4k.loading', '')  # the page fades in, with the title or after 15 s without one
            while not self.stopped.wait(HERO_TURN):
                self.turn()
        except Exception:
            logger.debug(traceback.format_exc())

    def idle(self):
        # no dialog, detail or grid window or player is over this window
        return kodi.xbmcgui.getCurrentWindowId() == self.own_id and kodi.xbmcgui.getCurrentWindowDialogId() == NO_DIALOG

    def turn(self):
        # never under a dialog, the detail or grid window or the player; only properties change, focus stays put
        if not self.idle():
            return
        count = min(int(kodi.xbmc.getInfoLabel('Container(%s).NumItems' % HERO_ROW) or 0), HERO_COUNT)
        if count < 2:
            return
        self.setProperty('a4k.hero.shown', '')  # the shown title fades out first; the buttons act on it until then
        if not self.stopped.wait(HERO_FADE):
            if not self.idle():  # something opened during the fade: keep the shown title
                self.setProperty('a4k.hero.shown', 'true')
                return
            self.hero = (self.hero + 1) % count
            self.show_hero()

    def dwell(self):
        # a title card that keeps focus for PREFETCH_DWELL gets its detail request made now, on a timer thread, so its
        # detail window opens with the shelves already there
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(PREFETCH_DWELL, self.prefetch)
        self.timer.start()

    def prefetch(self):
        try:
            focus = self.getFocusId()
            item = 'Container(%s).ListItem' % focus if focus in ROWS else self.hero_item() if focus == HERO_INFO else None
            if item:
                prefetch(item)
        except Exception:
            logger.debug(traceback.format_exc())

    def stop(self):
        if self.timer:
            self.timer.cancel()
        if self.stopped:
            self.stopped.set()

    def close(self):
        self.stop()
        super(Home, self).close()

    def hero_menu(self):
        info = labels(self.hero_item())
        if not info['Property(a4k.id)']:
            return
        from .. import listing
        items = listing.title_context_menu(SimpleNamespace(url=app.PLUGIN, kodi=kodi), title_from_info(info))
        menu(items, info['Property(a4k.id)'], info['Label'])

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

def modal(window):
    # doModal for a window opened over another a4k window (detail, grid). It takes the open-window slot in its onInit;
    # on close the slot goes back to the window below, and so does the screen when the user went Home and reopened the
    # add-on into this one (Back must not land on Kodi's Home).
    __home = kodi.xbmcgui.Window(app.HOME_WINDOW)
    previous = __home.getProperty(app.OPEN_WINDOW)
    try:
        window.doModal()
    finally:
        window.closed = True
        if previous:
            __home.setProperty(app.OPEN_WINDOW, previous)
            if kodi.xbmcgui.getCurrentWindowId() != int(previous) and not kodi.xbmc.Monitor().abortRequested():
                replace_current(previous)

def open():
    window = Home('a4k-home.xml', kodi.addon_path, 'Default', '1080i')
    # row URLs are set before the window opens: a row's provider fires once, at load (spike 2b)
    window.setProperty('a4k.home', 'true')
    window.setProperty('a4k.loading', 'true')  # the traced D until the top shelf has its first title
    if kodi.get_setting('appearance.tabs') != 'false':
        window.setProperty('a4k.tabs', 'true')
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
        window.stop()
        kodi.xbmcgui.Window(app.HOME_WINDOW).clearProperty(app.OPEN_WINDOW)
    error = window.error
    del window
    if error:
        raise RuntimeError(error)
