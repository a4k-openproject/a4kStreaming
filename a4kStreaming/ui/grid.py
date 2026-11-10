# -*- coding: utf-8 -*-
# Browse grid (a4k-grid.xml): one window for the Browse tiles (lists, watchlist, recommended, a year, search results,
# the public lists), more like this, a person's known-for titles and the rest of a home row. Its items are the
# plugin's own listing, built in this process (load) and filled from Python, so a long-press on a card reaches onAction
# and opens the add-on's sheet: Kodi runs its own context menu for a <content> row before the window's Python sees the
# key, and has none for a Python-filled list.
# The listing's Next item pages forward and a list or a person opens in place; Back walks those steps back, then closes.
# A window error is logged and closes the window.

import re
import threading
import traceback
from datetime import datetime

from ..lib import kodi, logger
from . import app, home

PANEL = 500
YEARS = 520
NEAR_END = 12  # two rows of six: focus this close to a Next item fetches the next page in the background
# the category galleries (the home's tabs) take year chips: All Years, then this year back to 1970
CATEGORIES = ('popularMovies', 'popularTVShows', 'popularAnimations', 'popularAnimationTVShows', 'popularRealityTVShows')
FIRST_YEAR = 1970
ACTION_SHOW_INFO = 11  # the Info key
FILL = threading.Lock()  # one listing goes into a panel at a time (a step and a late answer race)

def category(path):
    match = re.search(r'[?&]type=(\w+)', path)
    return match.group(1) if match and match.group(1) in CATEGORIES else ''

def year_path(path, year):
    # the category's first page, within the year (or all years when there is none)
    path = re.sub(r'&(paginationToken|page|cursor_time|target_year)=[^&]*', '', path)
    return '%s&target_year=%s' % (path, year) if year else path

def year_chips():
    return [''] + [str(year) for year in range(datetime.now().year, FIRST_YEAR - 1, -1)]

def widget(path):
    # grid paths carry widget=1, as the home rows' do
    return path if 'widget=1' in path else path + '&widget=1'

def page_of(path):
    match = re.search(r'[?&]page=(\d+)', path)
    return int(match.group(1)) if match else 1

def prefetch_page(path):
    # the next page's listing, run once in the background: its IMDb answer lands in the request cache (public pages
    # keep it for 30 minutes), so the page opens from cache when the user gets to the Next item
    try:
        kodi.json_rpc('Files.GetDirectory', {'directory': widget(path), 'media': 'files'}, log_error=False)
    except Exception:
        logger.debug(traceback.format_exc())

def load(window, panel, path, position=0, focus=False):
    # the listing at path into the window's panel (grid and search), asked on a window thread: the plugin's own items,
    # built here (core.listing_items) as window.items [(url, list_item, is_folder, menu)]. An answer for a path the
    # window has left is dropped. The cursor goes to position; focus gives the panel focus once it has items (Kodi
    # drops it from an emptied list, and getFocusId() still answers the panel, seen live).
    from . import detail
    try:
        core = detail.plugin_core()
        items = core.listing_items(path)
        with FILL:
            if window.closed or window.path != path:
                return
            for url, item, _, _ in items:
                item.setPath(url)  # ListItem.FolderPath, which select reads, and the info dialog's play
            control = window.getControl(panel)
            control.reset()
            control.addItems([item for _, item, _, _ in items])
            window.items = items
            control.selectItem(max(min(position, len(items) - 1), 0))
            window.setProperty('a4k.loading', '')
            if focus and items:
                window.setFocusId(panel)
        core.request.revalidate(core)  # a stale page answered from the cache is asked again, now that it shows
    except Exception:
        logger.error('listing failed: %s' % traceback.format_exc())
        if window.path == path:
            window.setProperty('a4k.loading', '')

def entry(window, panel):
    # the panel's selected item as (url, list_item, is_folder, menu); None on an empty panel
    index = window.getControl(panel).getSelectedPosition()
    return window.items[index] if 0 <= index < len(window.items) else None

def menu(window, panel):
    # long-press on a card: the add-on's sheet with the listing's rows for it; nothing for a person, a list or Next.
    # Episode details opens Kodi's info dialog itself: Kodi drops an Action(Info) sent while the sheet closes
    from . import detail
    selected = entry(window, panel)
    if selected and selected[3]:
        item = selected[1]
        rows = [(label, '' if builtin == detail.INFO else builtin) for label, builtin in selected[3]]
        home.menu(rows, item.getProperty('a4k.id'), item.getLabel(), lambda builtin: builtin or info(window, panel))

def info(window, panel):
    # Kodi's video info dialog for a title: a Python-filled list has no provider to open it
    selected = entry(window, panel)
    if selected and selected[1].getProperty('a4k.type') not in ('', 'person'):
        kodi.xbmcgui.Dialog().info(selected[1])

class Grid(kodi.xbmcgui.WindowXML):
    error = None
    closed = False
    stopped = None  # set in show(); every thread of the window ends on it (home.spawn)
    threads = ()
    dwelling = None  # the running dwell's cancel
    prefetched = None
    path = ''
    title = ''
    kicker = ''
    steps = None  # the (path, title, kicker, position) of every page or list under the one shown
    year = None  # the chosen year chip ('' for All Years) once the chips are filled
    items = ()  # the shown listing as [(url, list_item, is_folder, menu)], in the panel's order (load)
    started = False

    def go(self, path, title, kicker=''):
        self.path, self.title, self.kicker = widget(path), title, kicker
        page = page_of(path)
        self.setProperty('a4k.kicker', kicker.upper())
        self.setProperty('a4k.title', title)
        self.setProperty('a4k.page', 'Page %s' % page if page > 1 else '')

    def fill(self, position=0):
        # the shown path's listing: the panel empties (the loader shows) until it is in, then takes focus unless the
        # year chips hold it (the panel is the only other control that takes focus)
        focus = self.getFocusId() != YEARS
        self.items = ()
        self.getControl(PANEL).reset()
        self.setProperty('a4k.loading', 'true')
        home.spawn(self, load, self, PANEL, self.path, position, focus)

    def onInit(self):
        # runs again on every return (after detail, playback or a listing): only the first asks for the listing
        try:
            self.getControl(PANEL)  # raises when the XML did not load
            kodi.xbmcgui.Window(app.HOME_WINDOW).setProperty(app.OPEN_WINDOW, str(kodi.xbmcgui.getCurrentWindowId()))
            kodi.busy_live()  # clears a stale loader stamp (home.run), which the skin would keep drawn
            if not self.started:  # a return keeps its items: play and stop reload nothing
                self.started = True
                self.fill()
            if self.year is None and category(self.path):
                self.year = ''
                self.setProperty('a4k.years', 'true')
                self.show_years()
        except Exception:
            self.__fail()

    def show_years(self):
        chips = []
        for year in year_chips():
            item = kodi.xbmcgui.ListItem(label=year or 'All Years', offscreen=True)
            item.setProperty('year', year)
            item.setProperty('on', 'true' if year == self.year else '')
            chips.append(item)
        control = self.getControl(YEARS)
        control.reset()
        control.addItems(chips)
        control.selectItem(year_chips().index(self.year))

    def onClick(self, control_id):
        try:
            if control_id == YEARS:
                self.pick_year(self.getControl(YEARS).getSelectedItem().getProperty('year'))
        except Exception:
            self.__fail()

    def pick_year(self, year):
        # the same category within the year, from its first page; the chip stays marked and the steps start over
        if year == self.year:
            return
        self.year = year
        # marked in place: resetting the focused list drops its focus to the panel (seen live), whose select then fires
        chips = self.getControl(YEARS)
        for index, chip in enumerate(year_chips()):
            chips.getListItem(index).setProperty('on', 'true' if chip == year else '')
        self.steps = []
        self.go(year_path(self.path, year), self.title, year)
        self.fill()

    def onAction(self, action):
        try:
            action_id = action.getId()
            if action_id in (home.ACTION_PREVIOUS_MENU, home.ACTION_NAV_BACK):
                return self.back()
            if self.getFocusId() != PANEL:
                return
            if action_id in home.ACTION_MOVES:
                self.moved()
            elif action_id in (home.ACTION_SELECT_ITEM, home.ACTION_MOUSE_LEFT_CLICK):
                # the item's InfoLabels say what it is
                self.select(home.labels('Container(%s).ListItem' % PANEL))
            elif action_id == home.ACTION_CONTEXT_MENU:
                menu(self, PANEL)
            elif action_id == ACTION_SHOW_INFO:
                info(self, PANEL)
        except Exception:
            self.__fail()

    def select(self, info):
        type, path = info['Property(a4k.type)'], info['FolderPath']
        if type in ('movie', 'tvSeries'):
            home.select(info)
        elif type == 'person':
            self.step(path, info['Label'], 'Known for')
        elif type:
            home.run(home.click_builtin(info))
        elif 'paginationToken=' in path:
            self.step(path, self.title, self.kicker)
        elif path:  # one of the user's lists
            self.step(path, info['Label'], self.kicker)

    def position(self):
        return self.getControl(PANEL).getSelectedPosition()

    def step(self, path, title, kicker):
        # forward to the next page, a list or a person, from its top
        self.steps.append((self.path, self.title, self.kicker, self.position()))
        self.go(path, title, kicker)
        self.fill()

    def back(self):
        if not self.steps:
            return self.close()
        path, title, kicker, position = self.steps.pop()
        self.go(path, title, kicker)
        self.fill(position)  # back on the item it stepped from

    def moved(self):
        self.dwell()
        if not self.items or len(self.items) - self.position() > NEAR_END:
            return
        last = self.items[-1][0]
        if 'paginationToken=' in last and last != self.prefetched:
            self.prefetched = last
            home.spawn(self, prefetch_page, last)  # holds no window, but the window's close waits for it all the same

    def dwell(self):
        # a title that keeps focus for a moment gets its detail request made now, as on the home window
        if self.dwelling:
            self.dwelling.set()
        self.dwelling = home.spawn(self, self.prefetch, delay=home.PREFETCH_DWELL)

    def prefetch(self):
        try:
            if not self.closed and self.getFocusId() == PANEL:
                home.prefetch('Container(%s).ListItem' % PANEL)
        except Exception:
            logger.debug(traceback.format_exc())

    def close(self):
        self.closed = True
        super(Grid, self).close()

    def __fail(self):
        self.error = traceback.format_exc()
        self.close()

def show(path, title, kicker=''):
    try:
        window = Grid('a4k-grid.xml', kodi.addon_path, 'Default', '1080i')
        window.stopped = threading.Event()
        # a reopened add-on (after the Home key) comes back to this window, not to the one under it
        window.setProperty('a4k.home', 'true')
        window.setProperty('a4k.loading', 'true')  # the loader, not "Nothing here", until onInit asks for the listing
        window.steps = []
        window.go(path, title, kicker)
        home.modal(window)
        error = window.error
        del window
        if error:
            raise RuntimeError(error)
    except Exception:
        logger.error('grid window failed: %s' % traceback.format_exc())

# entry points: the Browse tiles, the detail window's cast and More like this

def browse(tile, label):
    # a Browse tile's a4k.grid property: search, years, or the query type of a listing
    if tile == 'search':
        return search()
    if tile == 'years':
        return years()
    show(app.row_url(tile), label)

def known_for(id, name):
    # a person's titles are public (no IMDb login)
    show('%s&id=%s' % (app.row_url('knownfor'), id), name, 'Known for')

def more_like_this(id, title):
    show('%s&id=%s' % (app.row_url('more_like_this'), id), title, 'More like this')

def search():
    from . import search as window
    window.open()

def years():
    # a decade, then a year (Back returns to the decades), newest first
    from . import sheets
    now = datetime.now().year
    decades = list(range(now - now % 10, 1899, -10))
    choice = -1
    while True:  # Back on the years returns to the decades with the picked one focused
        choice = sheets.select('Discover by Year', ['%s-%s' % (start, start + 9) for start in decades], preselect=choice)
        if choice < 0:
            return
        years = [year for year in range(decades[choice] + 9, decades[choice] - 1, -1) if year <= now]
        pick = sheets.select('%s-%s' % (decades[choice], decades[choice] + 9), [str(year) for year in years])
        if pick >= 0:
            return show('%s&target_year=%s' % (app.row_url('year'), years[pick]), str(years[pick]), 'Year')
