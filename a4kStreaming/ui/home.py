# -*- coding: utf-8 -*-
# Home window: the top shelf (the titles of its Hero shows source in turn), the Browse tiles and the rows of a4k-home.xml.
# The rows are the plugin's own listings loaded by Kodi (<content>), so this file only routes clicks and the hero menu,
# fills the row slots from the Appearance settings and turns the top shelf.

import threading
import time
import traceback
from types import SimpleNamespace

from ..lib import kodi, logger
from .. import kodi_mode, progress
from . import app, appearance

ROWS = (301, 302, 303, 304, 305, 306, 307)  # slots for the rows that are on, in their order (a4k.row.30n, a4k.title.30n)
CONTINUE = 308  # Continue Watching (its own landscape row under Browse, a4k.row.308)
CONTINUE_SETTLE = 1.5  # s after the player went before the row reloads (see after_play)
PLAYER_WAIT = 10  # s a reload waits for the player to go; one still playing (Back stops playback off) skips it
PLAYER_LOOK = 0.5
HERO_PLAY = 201
HERO_INFO = 202
HERO_ROW = 301
HERO_LISTS = {'trending_movies': 291, 'trending_tv': 292}  # the top shelf's own lists when no row shows its source
TILES = 400

# the top menu (a4k-home.xml 160): Watch Now, the category tabs (the Category tabs setting), Search and the Settings gear
WATCH_NOW = 161
TABS = {162: ('popularMovies', 'Trending Movies'), 163: ('popularTVShows', 'Trending TV Shows'),
        164: ('popularAnimations', 'Animations'), 165: ('popularAnimationTVShows', 'Animated TV'),
        166: ('popularRealityTVShows', 'Reality TV')}
SEARCH = 167
SETTINGS = 168
MENU = (WATCH_NOW, SEARCH, SETTINGS) + tuple(TABS)

# the top shelf turns to the next of the first HERO_COUNT titles of each source every hero_turn seconds (the Hero
# rotation setting, HERO_TURN by default); with rotation off it looks again every HERO_IDLE seconds
HERO_TURN = 15
HERO_IDLE = 1
HERO_COUNT = 6
HERO_FIELDS = {'label': 'Label', 'plot': 'Plot', 'year': 'Year', 'rating': 'Rating',
               'fanart': 'Art(fanart)', 'blur': 'Art(blur)'}  # a4k.hero.<key> = the item's InfoLabel
HERO_TYPES = {'movie': 'Movie', 'tvSeries': 'TV Series'}  # the TV skin's hero badge after the rating
HERO_RELOAD = 1.0  # after the settings change the sources: the new listings' time to land before the shelf starts over
HERO_FADE = 0.25
FRESH = 'a4k.fresh'
FRESH_TIME = 5  # a hidden list never loads; once loading, a slot stays shown by Container.IsUpdating
SETTINGS_LOOK = 0.25  # how often the home window looks whether the settings it opened have closed
SETTINGS_SHOWN = 'Window.IsActive(a4k-settings.xml) | Window.IsActive(addonsettings)'
SETTINGS_SETTLE = 1  # seen live: read at once, the Home order just saved was still the old one
SETTINGS_OPEN = 20  # looks for the settings window or dialog to open (5 s: the window starts an interpreter)
SETTINGS_WAIT = 4 * 3600 * 4  # looks while it stays open (4 h)  # the hero text's fade-out in a4k-home.xml (a4k.hero.shown), before the next title is set
NO_DIALOG = 9999  # getCurrentWindowDialogId() with no modal dialog up

LEAVE = ['Exit', "Kodi's menu", 'Cancel']  # Back on the top menu in Kodi setup mode

ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92
ACTION_SELECT_ITEM = 7
ACTION_MOUSE_LEFT_CLICK = 100
ACTION_CONTEXT_MENU = 117
ACTION_MOVES = (1, 2, 3, 4)
PREFETCH_DWELL = 0.4

# a window's threads (spawn, release)
TIMEOUT = 10  # s per attempt of a request on a window's thread (lib/request's default is 60); no retry once it stopped
# s a closing window waits for its threads. It waits on the interpreter's main thread, inside the callback of the window
# below, which takes no keys meanwhile: threads that only wait end at once, one with a request out is left over
JOIN = 0.5
ROOT_JOIN = TIMEOUT + 2  # the window a call opened first: no window below, and the interpreter ends right after its close
LEFT_OVER = []  # windows whose threads outlived JOIN: kept, so they are never freed on one of those threads
LOCK = threading.Lock()

INFO = ('FolderPath', 'Property(a4k.id)', 'Property(a4k.type)', 'Property(a4k.rated)', 'Property(a4k.trailers)',
        'Property(a4k.at)',  # a Continue Watching episode: the show's detail opens at "<season>:<episode>"
        # what the detail window paints before its own request lands
        'Label', 'Plot', 'Year', 'Rating', 'MPAA', 'Genre', 'Duration(secs)', 'Art(fanart)', 'Art(blur)', 'Art(poster)')

def labels(item):
    # read before any dialog opens: Container(id) resolves against the topmost dialog first
    return {key: kodi.xbmc.getInfoLabel('%s.%s' % (item, key)) for key in INFO}

def play_builtin(url):
    # noresume: Kodi keeps its own resume point for a play URL it played and would ask about it; the play's own sheet
    # asks Resume or Start over from the add-on's store (playback.resume_from)
    return 'PlayMedia(%s,noresume)' % url

def click_builtin(info):
    # what selecting a movie or an episode does: it plays (series, people, lists and Next are the windows' own steps)
    type = info.get('Property(a4k.type)', '')
    if type in ('movie', 'tvEpisode'):
        return play_builtin(info.get('FolderPath', '') or '%s?action=play&type=&id=%s' % (app.PLUGIN, info.get('Property(a4k.id)', '')))
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
    # nothing new while the loader is up: Kodi's busy dialog, which took the keys during a play, is kept closed over
    # these windows (lib/kodi.py), so a second Play would start a second search
    # ponytail: a loader left by a killed plugin call blocks actions for up to kodi.BUSY_STALE (60 s), then clears
    if builtin and not kodi.busy_live():
        kodi.xbmc.executebuiltin(builtin)

def select(info):
    # movies and series open the detail window
    if info.get('Property(a4k.type)', '') in ('movie', 'tvSeries'):
        from . import detail
        return detail.open(info)
    run(click_builtin(info))

MORE_LIKE_THIS = 'More Like This'
ACCOUNT = '?action=profile&'  # rating, watched, watchlist and list actions: each needs an IMDb login

def menu(items, id, title, ran=None):
    # a title's context list (label, builtin) as a select sheet, without the account actions when signed out (they
    # would only answer with the missing login notification); More Like This opens the grid, ran(builtin) hears what
    # was run
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
    if ran:
        ran(builtin)

def prefetch(item):
    # the detail request of the title at item (an InfoLabel prefix such as Container(301).ListItem), made now so its
    # detail window opens with the shelves already there
    type = kodi.xbmc.getInfoLabel(item + '.Property(a4k.type)')
    id = kodi.xbmc.getInfoLabel(item + '.Property(a4k.id)')
    if type in ('movie', 'tvSeries') and id:
        from . import detail
        detail.fetch(detail.plugin_core(), id, type == 'tvSeries')

def continue_url():
    # the row's listing; t is the store's change time, so a changed store is a new URL (Kodi reloads it, and never
    # serves an older listing it kept for the same URL)
    if not appearance.on('continue_watching'):
        return ''
    return '%s?action=continue&widget=1&t=%s' % (app.PLUGIN, progress.stamp())

def apply(window):
    # the Appearance settings as the window's properties: the Browse row, the category tabs, each row slot's title and
    # listing (a slot without one is hidden), and the top shelf's sources and rotation
    signed_in = bool(kodi.get_setting('imdb.at-main'))
    flags = {'a4k.auth': signed_in, 'a4k.tabs': appearance.on('tabs'), 'a4k.browse': appearance.on('browse')}
    for key, value in flags.items():
        window.setProperty(key, 'true' if value else '')
    window.setProperty('a4k.row.%s' % CONTINUE, continue_url())
    shown = appearance.rows(signed_in)
    slots = {}
    for slot, row in zip(ROWS, shown + [('', '', '', '')] * (len(ROWS) - len(shown))):
        key, title, url, _ = row
        window.setProperty('a4k.row.%s' % slot, url)
        window.setProperty('a4k.title.%s' % slot, title)
        slots[key] = slot
    kickers = {key: kicker for key, _, _, kicker in shown}
    sources = []
    for key in appearance.hero_keys(shown):
        if key not in slots:  # a trending source whose row is off: the hidden list of its own
            slots[key] = HERO_LISTS[key]
        sources.append((slots[key], kickers.get(key) or appearance.ROWS[key][2]))
    for key, list_id in HERO_LISTS.items():
        window.setProperty('a4k.row.%s' % list_id, appearance.row_url(appearance.ROWS[key][1]) if slots.get(key) == list_id else '')
    window.sources = tuple(sources)
    window.hero_turn = appearance.hero_turn()

class Home(kodi.xbmcgui.WindowXML):
    error = None
    dwelling = None  # the running dwell's cancel (spawn)
    threads = ()
    hero = 0
    own_id = None
    stopped = None
    sources = ((HERO_ROW, appearance.ROWS['trending_movies'][2]),)  # (container, kicker) per source, set by apply()
    hero_turn = HERO_TURN
    shown = None  # (container, index, kicker) of the title on the top shelf
    turning = threading.Lock()  # one turn at a time: the restart after a settings change and the rotation
    asked = False

    def onInit(self):
        # runs again on every return to the window (after playback, after a listing): no network, nothing to undo
        try:
            # raises when the XML did not load; a grouplist would raise anyway (Python cannot wrap that type)
            self.getControl(HERO_PLAY)
            self.own_id = kodi.xbmcgui.getCurrentWindowId()
            self.wire()
            kodi.xbmcgui.Window(app.HOME_WINDOW).setProperty(app.OPEN_WINDOW, str(self.own_id))
            kodi.busy_live()  # clears a stale loader stamp (see run)
            if self.stopped is None:
                self.stopped = threading.Event()
                spawn(self, self.rotate)
            elif self.getProperty('a4k.row.%s' % CONTINUE) and (playing() or self.getProperty('a4k.row.%s' % CONTINUE) != continue_url()):
                # back from a play (or a detail window that played): the Continue Watching row reloads once, after the
                # player went and only with nothing over the window. Rows reloading next to a running plugin call or
                # the player's stop, or right as a window of this interpreter closes, crashed Kodi (a4k-home.xml,
                # ui/settings.py).
                spawn(self, self.reload_continue)
        except Exception:
            self.__fail()

    def reload_continue(self):
        try:
            if not after_play(self.stopped):
                return
            url = continue_url()
            if self.stopped.is_set() or not self.idle() or self.getProperty('a4k.row.%s' % CONTINUE) == url:
                return  # the next return to the window looks again
            self.setProperty('a4k.row.%s' % CONTINUE, url)
            self.setProperty(FRESH, 'true')  # an empty row is hidden, and a hidden list never loads
            spawn(self, self.setProperty, FRESH, '', delay=FRESH_TIME)
        except Exception:
            logger.debug(traceback.format_exc())

    def onAction(self, action):
        try:
            action_id = action.getId()
            focus = self.getFocusId()
            if action_id in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
                return self.back(focus)
            if action_id in ACTION_MOVES:
                return self.dwell()
            selected = action_id in (ACTION_SELECT_ITEM, ACTION_MOUSE_LEFT_CLICK)
            if selected and focus == CONTINUE:
                select(labels('Container(%s).ListItem' % CONTINUE))
            elif selected and focus in ROWS:
                info = labels('Container(%s).ListItem' % focus)
                if not info['Property(a4k.type)'] and 'paginationToken=' in info['FolderPath']:
                    from . import grid  # the row's Next item: the rest of the row in the grid
                    return grid.show(info['FolderPath'], self.getProperty('a4k.title.%s' % focus))
                select(info)
            elif selected and focus == TILES:
                tile = kodi.xbmc.getInfoLabel('Container(%s).ListItem.Property(a4k.grid)' % TILES)
                if tile == 'debrid':
                    from . import debrid
                    debrid.open()
                elif tile:
                    from . import grid
                    grid.browse(tile, kodi.xbmc.getInfoLabel('Container(%s).ListItem.Label' % TILES))
            elif action_id == ACTION_CONTEXT_MENU and focus in (HERO_PLAY, HERO_INFO):
                # rows get Kodi's own menu with the listing's items; the hero buttons are not list items
                self.hero_menu()
        except Exception:
            self.__fail()

    def back(self, focus):
        # Back on a row goes to the top shelf's Play, on the top shelf to Watch Now, on the top menu it leaves (asking
        # first in Kodi setup mode, where Kodi's menu is not the way out)
        if focus not in MENU:
            return self.setFocusId(WATCH_NOW if focus in (HERO_PLAY, HERO_INFO) else HERO_PLAY)
        if not kodi_mode.active():
            return self.close()
        from . import sheets
        choice = sheets.select('Leave a4kStreaming?', LEAVE, preselect=2)
        if choice == 0:  # Android: Kodi goes to the background and stays warm, as Back at a TV app's root does
            kodi.xbmc.executebuiltin('Minimize' if kodi.xbmc.getCondVisibility('System.Platform.Android') else 'Quit')
        elif choice == 1:
            self.close()

    def ask_kodi_mode(self):
        # the one-time question about Kodi setup mode, in an interpreter of its own (as the settings window), once the
        # page is up with nothing over it and nothing playing
        if self.asked or not self.idle() or playing() or not kodi_mode.prompt_due():
            return
        self.asked = True  # the question itself marks it asked (kodi_mode.prompt)
        run('RunScript(%s,kodi_mode_prompt)' % kodi.addon_id)

    def onClick(self, control_id):
        try:
            if control_id in MENU:
                return self.tab(control_id)
            if self.hero < 0:
                return  # the top shelf restarts on new sources (reapply): the index it showed now names another title
            info = labels(self.hero_item())
            if control_id == HERO_PLAY and info['Property(a4k.type)'] == 'tvSeries':
                select(info)  # Go to Show: a series' first button opens its detail
            elif control_id == HERO_PLAY:
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
            self.settings()
        else:
            from . import grid
            grid.show(app.row_url(TABS[control_id][0]), TABS[control_id][1])

    def settings(self):
        # the settings window (ui/settings.py) in an interpreter of its own, over this one; it opens Kodi's own dialog
        # when it fails or its last row asks for it. Once both are closed the Home settings take effect here. Watched
        # from a thread: a blocking executebuiltin holds Python's lock, and the dialog's actions (ui.py) then could not
        # run until it closed (seen live).
        run('RunScript(%s,settings)' % kodi.addon_id)
        spawn(self, self.settings_closed)

    def settings_closed(self, opened=False):
        try:
            for tick in range(SETTINGS_WAIT):
                if self.stopped.wait(SETTINGS_LOOK):
                    return
                if kodi.xbmc.getCondVisibility(SETTINGS_SHOWN):
                    opened = True
                elif opened or tick > SETTINGS_OPEN:
                    break
            # Kodi's dialog passes a value set by its actions (Home order, My List) on as it closes, and the window hands
            # over to that dialog: look again after that
            if self.stopped.wait(SETTINGS_SETTLE):
                return
            if kodi.xbmc.getCondVisibility(SETTINGS_SHOWN):
                return self.settings_closed(True)
            self.reapply()
        except Exception:
            logger.debug(traceback.format_exc())

    def reapply(self):
        # the rows load their new listings and the top shelf starts over on its sources
        sources = self.sources
        apply(self)
        self.wire()
        self.setProperty(FRESH, 'true')  # every slot with a listing shows for a moment, so a new listing starts loading
        spawn(self, self.setProperty, FRESH, '', delay=FRESH_TIME)
        if self.sources != sources:
            self.hero = -1
            self.setProperty('a4k.hero.shown', '')  # the old title goes; the buttons do nothing until the next paints
            spawn(self, self.turn, delay=HERO_RELOAD)

    def wire(self):
        # Down on the last row that shows stays there. Past it only hidden slots follow, their chain ends in noop, and
        # Kodi then wrapped focus around to the top shelf (seen live). The other rows keep the XML's Down.
        shown = [slot for slot in ROWS if self.getProperty('a4k.row.%s' % slot)]
        if not shown:  # Continue Watching is the last row
            self.getControl(CONTINUE).controlDown(self.getControl(CONTINUE))
        for slot in shown:
            row = self.getControl(slot)
            last = slot == shown[-1]
            row.controlDown(row if last or slot == ROWS[-1] else self.getControl((slot - 300 + 1) * 10 + 300))

    def hero_items(self):
        # the top shelf's titles: the first HERO_COUNT of each source, one of each in turn, a title met again dropped
        lists = []
        for container, kicker in self.sources:
            count = min(int(kodi.xbmc.getInfoLabel('Container(%s).NumItems' % container) or 0), HERO_COUNT)
            lists.append([(container, index, kicker) for index in range(count)])
        items, seen = [], set()
        for index in range(HERO_COUNT):
            for source in lists:
                if index >= len(source):
                    continue
                id = kodi.xbmc.getInfoLabel('Container(%s).ListItemAbsolute(%s).Property(a4k.id)' % source[index][:2])
                if id in seen:
                    continue
                if id:
                    seen.add(id)
                items.append(source[index])
        return items

    def hero_item(self):
        container, index, _ = self.shown or (self.sources[0][0], 0, '')
        return 'Container(%s).ListItemAbsolute(%s)' % (container, index)

    def show_hero(self, items=None):
        items = items if items is not None else self.hero_items()
        if items:
            self.hero = max(self.hero, 0) % len(items)
            self.shown = items[self.hero]
        item = self.hero_item()
        for key, field in HERO_FIELDS.items():
            self.setProperty('a4k.hero.%s' % key, kodi.xbmc.getInfoLabel('%s.%s' % (item, field)))
        type = kodi.xbmc.getInfoLabel(item + '.Property(a4k.type)')
        series = type == 'tvSeries'
        self.setProperty('a4k.hero.type', HERO_TYPES.get(type, ''))
        self.setProperty('a4k.hero.act', 'Go to Show' if series else 'Play')
        self.setProperty('a4k.hero.kicker', self.shown[2] if self.shown else '')
        self.setProperty('a4k.hero.shown', 'true')  # the text fades in; the art crossfades by its fadetime

    def rotate(self):
        # Paint the top shelf as soon as a source is in (Kodi gives the window no event for that: look every 100 ms,
        # 15 s at most), then turn it every hero_turn seconds until the window closes.
        try:
            for _ in range(150):
                if self.stopped.is_set() or any(kodi.xbmc.getInfoLabel('Container(%s).NumItems' % container) not in ('', '0')
                                                for container, _ in self.sources):
                    break
                self.stopped.wait(0.1)
            if not self.stopped.is_set():
                self.show_hero()
            self.setProperty('a4k.loading', '')  # the page fades in, with the title or after 15 s without one
            self.ask_kodi_mode()  # its sheet starts an interpreter first: the page has faded in by then
            while not self.stopped.wait(self.hero_turn or HERO_IDLE):
                self.ask_kodi_mode()
                if self.hero_turn or self.hero < 0:  # a restart the delayed turn could not paint: once in view
                    self.turn()
        except Exception:
            logger.debug(traceback.format_exc())

    def idle(self):
        # no dialog, detail or grid window or player is over this window
        return kodi.xbmcgui.getCurrentWindowId() == self.own_id and kodi.xbmcgui.getCurrentWindowDialogId() == NO_DIALOG

    def turn(self):
        # never under a dialog, the detail or grid window or the player; only properties change, focus stays put
        with self.turning:
            if not self.idle():
                return
            items = self.hero_items()
            if not items or (len(items) < 2 and self.hero >= 0):  # one title stays; a restart (hero -1) paints even one
                return
            self.setProperty('a4k.hero.shown', '')  # the shown title fades out first; the buttons act on it until then
            if not self.stopped.wait(HERO_FADE):
                if not self.idle():  # something opened during the fade: keep the shown title (none while it restarts)
                    self.setProperty('a4k.hero.shown', 'true' if self.hero >= 0 else '')
                    return
                self.hero = (self.hero + 1) % max(len(items), 1)
                self.show_hero(items)

    def dwell(self):
        # a title card that keeps focus for PREFETCH_DWELL gets its detail request made now, on a thread of the window,
        # so its detail window opens with the shelves already there
        if self.dwelling:
            self.dwelling.set()
        self.dwelling = spawn(self, self.prefetch, delay=PREFETCH_DWELL)

    def prefetch(self):
        try:
            focus = self.getFocusId()
            item = 'Container(%s).ListItem' % focus if focus in ROWS + (CONTINUE,) else self.hero_item() if focus == HERO_INFO else None
            if item:
                prefetch(item)
        except Exception:
            logger.debug(traceback.format_exc())

    def stop(self):
        if self.stopped:
            self.stopped.set()

    def close(self):
        self.stop()
        super(Home, self).close()

    def hero_menu(self):
        info = labels(self.hero_item())
        if not info['Property(a4k.id)'] or self.hero < 0:
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

def playing():
    return bool(kodi.xbmc.getCondVisibility('Player.HasMedia'))

def after_play(stopped):
    # Back from the video shows the window before the player stops and records the position (service.py): wait until
    # the player went, then a settle. False when the window stopped (stopped, its Event, also ends the waits at once,
    # so a closed window's thread ends with it) or the player stays
    waited = 0
    while playing():
        if waited >= PLAYER_WAIT or stopped.wait(PLAYER_LOOK):
            return False
        waited += PLAYER_LOOK
    return not stopped.wait(CONTINUE_SETTLE)

def spawn(window, target, *args, delay=None):
    # Every thread of an a4k window starts here and is joined before the window is freed (release): Kodi 21 dies with
    # SIGSEGV when a WindowXML is freed off its interpreter's main thread, and a thread whose target is a bound method
    # holds the window past `del window`. delay stands in for threading.Timer, whose run never drops its function: a
    # stored timer made a window -> timer -> method -> window cycle, and the GC then freed the window on any thread.
    # The delay ends early when the window stops; the returned Event, once set, cancels the target (a restarted dwell).
    # window.stopped must be the window's Event; a stopped window starts nothing.
    cancel = threading.Event()
    def run():
        if delay is None or not (window.stopped.wait(delay) or cancel.is_set()):
            target(*args)
    with LOCK:
        if not window.stopped.is_set():
            thread = threading.Thread(target=run)
            thread.request_timeout = TIMEOUT  # lib/request: the default timeout of this thread's requests
            thread.stopped = window.stopped  # lib/request: no retry once the window stopped
            window.threads = [alive for alive in window.threads if alive.is_alive()] + [thread]
            thread.start()
    return cancel

def release(window, join=JOIN):
    # on the interpreter's main thread once the window's doModal returned: its waits end, its threads are joined against
    # one deadline, and a window with a thread still running is kept rather than freed on that thread. Kept windows whose
    # threads have all ended since are dropped here, so they are freed on this thread.
    with LOCK:
        if window.stopped:
            window.stopped.set()
        threads = list(window.threads)
    deadline = time.time() + join
    for thread in threads:
        thread.join(max(0, deadline - time.time()))
    if any(thread.is_alive() for thread in threads):
        LEFT_OVER.append(window)  # ponytail: a hung request keeps its window until a later close finds it ended
    LEFT_OVER[:] = [kept for kept in LEFT_OVER if any(thread.is_alive() for thread in kept.threads)]

def modal(window, join=JOIN):
    # doModal for a window opened over another a4k window (detail, grid). It takes the open-window slot in its onInit;
    # on close the slot goes back to the window below, and so does the screen when the user went Home and reopened the
    # add-on into this one (Back must not land on Kodi's Home). Its threads are joined before it is freed (release).
    # Like run(), nothing opens while the loader is up, except Debrid opened by the play call itself (over_call).
    __home = kodi.xbmcgui.Window(app.HOME_WINDOW)
    previous = __home.getProperty(app.OPEN_WINDOW)
    try:
        if getattr(window, 'over_call', False) or not kodi.busy_live():
            window.doModal()
    finally:
        window.closed = True
        try:
            if previous:
                __home.setProperty(app.OPEN_WINDOW, previous)
                if kodi.xbmcgui.getCurrentWindowId() != int(previous) and not kodi.xbmc.Monitor().abortRequested():
                    replace_current(previous)
        finally:
            release(window, join)

def open(cover=None):
    # cover: the launch cover (app.launch), closed as the window takes its place
    window = Home('a4k-home.xml', kodi.addon_path, 'Default', '1080i')
    # row URLs are set before the window opens: a row's provider fires once, at load (spike 2b)
    window.setProperty('a4k.home', 'true')
    window.setProperty('a4k.loading', 'true')  # the traced D until the top shelf has its first title
    window.setProperty('a4k.hero.act', 'Play')
    apply(window)
    own_id = window_id(window)
    if cover:
        cover.close()  # app.launch: closing, it no longer blocks the activation and stays drawn until it is done
    if own_id:
        replace_current(own_id)  # doModal then skips its own, history-adding, activation
    try:
        window.doModal()
    finally:
        kodi.xbmcgui.Window(app.HOME_WINDOW).clearProperty(app.OPEN_WINDOW)
        release(window, ROOT_JOIN)
    error = window.error
    del window
    if error:
        raise RuntimeError(error)
