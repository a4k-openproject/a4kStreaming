# -*- coding: utf-8 -*-
# Search window (a4k-search.xml), in the Apple TV style: an on-screen QWERTY keyboard, the query line, the facet
# chips (Type, Genre, Era, Rating, Country, Clear) and a six-column results grid that follows the typing after a 500 ms
# pause. The results are the plugin's own listing, loaded by Kodi from the a4k.path property (<content>): text alone is
# IMDb's title search (type=find), any facet the advanced title search (type=facets), whose page grows as focus nears the
# end. A window error is logged and closes the window.

import threading
import traceback
from urllib.parse import urlencode

from ..lib import kodi, logger
from .. import imdb
from . import app, home

KEYS = 600
FACETS = 610
RESULTS = 620
HINT = 'Movies and TV shows'

DEBOUNCE = 0.5  # the search runs once typing pauses this long
NEAR_END = 12  # two rows of six: focus this close to the end asks for the next page

# the keyboard, a ten-column grid: three QWERTY rows, delete ends the second, space and
# Type (Kodi's own keyboard) end the third. No voice key: Kodi has no speech input.
KEY_ROWS = [list('qwertyuiop'), list('asdfghjkl') + ['del'], list('zxcvbnm') + ['space', 'type']]
ICONS = {'del': 'a4k/icon_delete.png', 'space': 'a4k/icon_space.png', 'type': 'a4k/icon_keyboard.png'}

def facets():
    # (id, label, any, values, multi) per facet chip; the values are imdb.py's, so the window and the query agree
    return [
        ('type', 'Type', 'All', imdb.SEARCH_TYPES, False),
        ('genre', 'Genre', 'Any', imdb.SEARCH_GENRES, True),
        ('era', 'Era', 'Any', imdb.SEARCH_ERAS, False),
        ('rating', 'Rating', 'Any', imdb.SEARCH_RATINGS, False),
        ('country', 'Country', 'Any', imdb.SEARCH_COUNTRIES, False),
    ]

def no_filters():
    return {'type': '', 'genre': [], 'era': '', 'rating': '', 'country': ''}

def filtered(filters):
    return any(filters.values())

def chip_label(label, any, values, value):
    # "Type: All", "Genre: Action", "Genre: Action +2"
    names = dict(values)
    if isinstance(value, list):
        shown = names[value[0]] + (' +%s' % (len(value) - 1) if len(value) > 1 else '') if value else any
    else:
        shown = names.get(value, any)
    return '%s: %s' % (label, shown)

def url(query, filters, count=0):
    # the results listing for the text and the facets: '' when there is neither
    query = query.strip()
    if filtered(filters):
        params = [('action', 'query'), ('type', 'facets'), ('query', query), ('title_type', filters['type']),
                  ('genres', ','.join(filters['genre'])), ('era', filters['era']), ('rating', filters['rating']),
                  ('country', filters['country']), ('count', str(count) if count else '')]
    elif query:
        params = [('action', 'query'), ('type', 'find'), ('query', query)]
    else:
        return ''
    return '%s?%s&widget=1' % (app.PLUGIN, urlencode([(key, value) for key, value in params if value]))

class Search(kodi.xbmcgui.WindowXML):
    error = None
    closed = False
    timer = None
    dwell_timer = None
    query = ''
    filters = None
    count = 0
    path = ''

    def onInit(self):
        # runs again on every return (after detail or playback): no network, nothing to undo
        try:
            keys = self.getControl(KEYS)  # raises when the XML did not load
            kodi.xbmcgui.Window(app.HOME_WINDOW).setProperty(app.OPEN_WINDOW, str(kodi.xbmcgui.getCurrentWindowId()))
            if self.filters is None:
                self.filters = no_filters()
                self.setProperty('a4k.hint', HINT)
                keys.addItems(self.key_items())
                self.show_facets()
                self.setFocusId(KEYS)
        except Exception:
            self.__fail()

    def key_items(self):
        items = []
        for row in KEY_ROWS:
            for key in row:
                item = kodi.xbmcgui.ListItem(label='' if key in ICONS else key, offscreen=True)
                item.setProperty('key', key)
                if key in ICONS:
                    item.setArt({'icon': ICONS[key]})
                items.append(item)
        return items

    def show_facets(self):
        chips = []
        for id, label, any, values, _ in facets():
            item = kodi.xbmcgui.ListItem(label=chip_label(label, any, values, self.filters[id]), offscreen=True)
            item.setProperty('facet', id)
            item.setProperty('on', 'true' if self.filters[id] else '')
            chips.append(item)
        if filtered(self.filters):
            item = kodi.xbmcgui.ListItem(label='Clear', offscreen=True)
            item.setProperty('facet', 'clear')
            chips.append(item)
        control = self.getControl(FACETS)
        position = control.getSelectedPosition()
        control.reset()
        control.addItems(chips)
        control.selectItem(min(max(position, 0), len(chips) - 1))

    def onClick(self, control_id):
        try:
            if control_id == KEYS:
                self.press(self.getControl(KEYS).getSelectedItem().getProperty('key'))
            elif control_id == FACETS:
                self.pick(self.getControl(FACETS).getSelectedItem().getProperty('facet'))
        except Exception:
            self.__fail()

    def press(self, key):
        if key == 'type':
            return self.keyboard()
        if key == 'del':
            self.query = self.query[:-1]
        elif key == 'space':
            self.query += ' '
        else:
            self.query += key
        self.typed()

    def typed(self):
        self.setProperty('a4k.query', self.query)
        self.setProperty('a4k.hint', '' if self.query else HINT)
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(DEBOUNCE, self.guarded, args=(self.apply,))
        self.timer.start()

    def keyboard(self):
        # Kodi's own keyboard: its text runs at once
        keyboard = kodi.xbmc.Keyboard(self.query, HINT)
        keyboard.doModal()
        if keyboard.isConfirmed():
            self.query = keyboard.getText()
            self.typed()
            self.timer.cancel()
            self.apply()

    def pick(self, id):
        from . import sheets
        if id == 'clear':
            self.filters = no_filters()
        else:
            _, label, any, values, multi = next(facet for facet in facets() if facet[0] == id)
            if multi:
                self.pick_many(sheets, id, label, any, values)
            else:
                current = [value for value, _ in values].index(self.filters[id]) + 1 if self.filters[id] else 0
                choice = sheets.select(label, [any] + [name for _, name in values], preselect=current)
                if choice is None or choice < 0:
                    return
                self.filters[id] = values[choice - 1][0] if choice else ''
        self.show_facets()
        self.apply()

    def pick_many(self, sheets, id, label, any, values):
        # the Genre picker toggles and stays open: the sheet comes back after each pick until Back; Any clears
        choice = 0
        while True:
            chosen = self.filters[id]
            rows = [(any, '')] + [(name, 'Selected' if value in chosen else '') for value, name in values]
            choice = sheets.select(label, [row[0] for row in rows], preselect=choice, rows=rows)
            if choice is None or choice < 0:
                return
            if choice == 0:
                self.filters[id] = []
                return
            value = values[choice - 1][0]
            self.filters[id] = [v for v, _ in values if (v in chosen) != (v == value)]

    def apply(self, more=False):
        # the listing for the query and the facets. An emptied query keeps the results that are there.
        if self.closed:
            return
        self.count = self.count + imdb.SEARCH_PAGE if more else imdb.SEARCH_PAGE
        path = url(self.query, self.filters, self.count)
        if path and path != self.path:
            if not more:
                self.getControl(RESULTS).selectItem(0)
            self.path = path
            self.setProperty('a4k.path', path)

    def onAction(self, action):
        try:
            action_id = action.getId()
            if action_id in (home.ACTION_PREVIOUS_MENU, home.ACTION_NAV_BACK):
                return self.close()
            if self.getFocusId() != RESULTS:
                return
            if action_id in home.ACTION_MOVES:
                self.moved()
            elif action_id in (home.ACTION_SELECT_ITEM, home.ACTION_MOUSE_LEFT_CLICK):
                # a provider list: Kodi sends no click to Python (spike 2c)
                info = home.labels('Container(%s).ListItem' % RESULTS)
                if info['Property(a4k.type)']:
                    home.select(info)
        except Exception:
            self.__fail()

    def moved(self):
        self.dwell()
        # a facet search whose page came back full may have more: ask for the next page before focus gets to the end
        count = int(kodi.xbmc.getInfoLabel('Container(%s).NumItems' % RESULTS) or 0)
        position = int(kodi.xbmc.getInfoLabel('Container(%s).CurrentItem' % RESULTS) or 1) - 1
        if 'type=facets' in self.path and count >= self.count and count - position <= NEAR_END and self.count < imdb.SEARCH_MAX:
            self.apply(more=True)

    def dwell(self):
        if self.dwell_timer:
            self.dwell_timer.cancel()
        self.dwell_timer = threading.Timer(home.PREFETCH_DWELL, self.guarded, args=(self.prefetch,))
        self.dwell_timer.start()

    def prefetch(self):
        if not self.closed and self.getFocusId() == RESULTS:
            home.prefetch('Container(%s).ListItem' % RESULTS)

    def guarded(self, fn):
        try:
            fn()
        except Exception:
            logger.debug(traceback.format_exc())

    def close(self):
        self.closed = True
        for timer in (self.timer, self.dwell_timer):
            if timer:
                timer.cancel()
        super(Search, self).close()

    def __fail(self):
        self.error = traceback.format_exc()
        self.close()

def open():
    try:
        window = Search('a4k-search.xml', kodi.addon_path, 'Default', '1080i')
        # a reopened add-on (after the Home key) comes back to this window, not to the one under it
        window.setProperty('a4k.home', 'true')
        home.modal(window)
        error = window.error
        del window
        if error:
            raise RuntimeError(error)
    except Exception:
        logger.error('search window failed: %s' % traceback.format_exc())
