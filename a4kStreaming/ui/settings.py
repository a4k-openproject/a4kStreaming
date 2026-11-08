# -*- coding: utf-8 -*-
# The settings window (a4k-settings.xml): the categories of resources/settings.xml on a rail, the current one's rows in
# a pane. The rows are read from that file (ids, types, defaults, ranges, options, order), so Kodi's own dialog and
# this window cannot drift apart; only the help lines and value formats live here. Two rows are the window's own: Reset
# this section (not on a category with secrets: accounts are never reset) and, last, Kodi's own settings dialog.
# Every change is written at once. It runs in an interpreter of its own (RunScript, ui.py), as Kodi's own dialog does;
# the home window reapplies its settings once the window has closed.

import io
import os
import re
import json
import traceback
from xml.etree import ElementTree

from ..lib import kodi, logger
from . import app, appearance
from .home import ACTION_PREVIOUS_MENU, ACTION_NAV_BACK

RAIL = 100
PANE = 200
LEFT, RIGHT, UP, DOWN = 1, 2, 3, 4  # Kodi's ACTION_MOVE_*
SESSION = 'a4k.settings.'  # on Kodi's Home window: the last category and its row, for this Kodi session
PICKER = 3  # an enum with more options than this opens the sheet picker on OK; fewer cycle
MORE = '›'  # the value of a row that opens something

HELP = {
    'general.max_quality': 'Sources above this quality are left out.',
    'general.max_movie_size': 'Movie sources larger than this are left out. Left or Right to change, OK to type it.',
    'general.dolby_vision_allowed': 'Off leaves Dolby Vision sources out, for a TV or player that shows them in the wrong colours.',
    'general.autoplay': 'Plays the best source without showing the source list.',
    'general.skip_intro': 'Auto skips the intro, Button shows a Skip button, Off does neither.',
    'general.skip_recap': 'Auto skips the recap, Button shows a Skip button, Off does neither.',
    'general.skip_credits': 'At the credits Auto plays the next episode, Button shows a Next episode button.',
    'general.back_stops': 'Back from the video stops it and keeps its place for Continue Watching. Off leaves it playing behind the menus.',
    'general.search_all_providers': 'Off: with a Premiumize key a quick search runs first, and every provider is searched '
                                    'when it finds nothing or when you ask for it.',
    'general.search_timeout': 'How long a source search waits for the providers. Left or Right to change, OK to type it.',
    'general.remembered_searches': 'Searches kept, so a title opened again lists its sources at once. Off keeps none.',
    'provider.install': 'Installs a provider package from a URL or a file.',
    'provider.manage': 'Turns installed providers on or off.',
    'provider.check': 'Looks for a newer version of the installed provider package.',
    'appearance.browse': 'The Browse row of category tiles.',
    'appearance.tabs': 'The category tabs in the top menu.',
    'appearance.continue_watching': 'The movies and episodes you stopped partway, as the first row on Home.',
    'appearance.trending_movies': 'Shows this row on Home.',
    'appearance.trending_tv': 'Shows this row on Home.',
    'appearance.reality': 'Shows this row on Home.',
    'appearance.animations': 'Shows this row on Home.',
    'appearance.animation_tv': 'Shows this row on Home.',
    'appearance.watchlist': 'Your IMDb Watchlist as a row on Home.',
    'appearance.my_list_pick': 'One of your IMDb lists as a row on Home.',
    'appearance.order_pick': 'The order of the rows on Home.',
    'appearance.hero_source': 'Which titles the big top shelf turns through.',
    'appearance.hero_turn': 'How often the top shelf turns to its next title.',
    'imdb.at-main': 'Optional. Watchlist, your lists, ratings and watched marks need it: the at-main cookie of a signed-in '
                    'imdb.com in a browser.',
    'general.mark_as_watched_rating': 'IMDb has no watched mark, so marking a title watched rates it this.',
    'premiumize.apikey': 'Optional. The API key from premiumize.me/account; checked when you enter it.',
    'trakt.username': 'The Trakt profile the imports read.',
    'trakt.clientid': 'A Trakt API app client ID, for the imports only.',
    'trakt.migrate_status': 'Rates every title watched on Trakt, which marks it watched on IMDb.',
    'trakt.migrate_collections': 'Adds your Trakt collections to the IMDb lists Movies Collection and Shows Collection, which must exist.',
    'general.page_size': 'Titles per page in the rows and grids.',
    'general.lists_page_size': 'Titles per page in the Watchlist and your lists.',
    'kodi.mode': 'Makes Kodi an a4kStreaming device: opens it at start, home shows only a4kStreaming, menu sounds off. '
                 'Lists each change first; turning it off puts them back.',
}
DESCRIPTIONS = {  # by the category's label id
    '33001': 'What plays, and what happens around it.',
    '33003': 'Where titles play from, and how long to look.',
    '33007': 'What the home screen shows.',
    '33005': 'Sign-ins. Nothing here is needed to browse.',
    '33008': 'Rarely needed.',
}
STEPS = {'general.max_movie_size': 5, 'general.search_timeout': 5, 'general.page_size': 5, 'general.lists_page_size': 5}
FORMATS = {
    'general.max_movie_size': lambda n: 'No limit' if n >= 200 else '%s GB' % n,
    'general.search_timeout': lambda n: '%s s' % n,
    'general.remembered_searches': lambda n: 'Off' if n == 0 else str(n),
    'general.mark_as_watched_rating': lambda n: '%s / 10' % n,
}
ORDER_HELP = 'OK picks this row up, then Up or Down moves it.'
GRAB_HELP = 'Up or Down moves the row. OK drops it here, Back puts it back.'
SIGN_IN = 'Sign in to IMDb first'
IMDB = 'imdb.at-main'

def strings():
    # strings.po's English, the label where Kodi has none (the offline mock)
    path = os.path.join(kodi.addon_path, 'resources', 'language', 'resource.language.en_gb', 'strings.po')
    with io.open(path, encoding='utf-8') as f:
        return dict(re.findall(r'msgctxt "#(\d+)"\nmsgid "(.*)"', f.read()))

def kind(node):
    type = node.get('type')
    if node.get('visible') == 'false':
        return 'hidden'
    if type == 'action':
        return 'order' if node.get('id') == 'appearance.order_pick' else 'action'
    if type == 'text':
        return 'secret' if node.get('option') == 'hidden' else 'text'
    return {'slider': 'number'}.get(type, type)  # bool, enum

def categories():
    # resources/settings.xml as [(label id, label, [row])], hidden settings included (a reset sets them too)
    po = strings()
    text = lambda id: kodi.string(int(id), po.get(id, id))
    with io.open(os.path.join(kodi.addon_path, 'resources', 'settings.xml'), encoding='utf-8') as f:
        root = ElementTree.fromstring(re.sub(r'&(?!amp;)', '&amp;', f.read()))  # Kodi takes a bare &
    found = []
    for category in root.iter('category'):
        rows = []
        for node in category.iter('setting'):
            id = node.get('id')
            if not id:  # a separator
                continue
            row = {'id': id, 'kind': kind(node), 'label': text(node.get('label')) if node.get('label') else '',
                   'default': node.get('default'), 'action': node.get('action'), 'help': HELP.get(id, '')}
            if node.get('lvalues'):
                row['options'] = [text(value) for value in node.get('lvalues').split('|')]
            if row['kind'] == 'number':
                bounds = [int(value) for value in node.get('range').split(',')]
                row.update(min=bounds[0], max=bounds[-1], step=STEPS.get(id, bounds[1] if len(bounds) == 3 else 1))
            rows.append(row)
        found.append((category.get('label'), text(category.get('label')), rows))
    return found

def shown(categories):
    # the pane's rows per category: the visible settings, Reset this section, Kodi's dialog at the very end
    panes = []
    for index, (_, label, rows) in enumerate(categories):
        pane = [row for row in rows if row['kind'] != 'hidden']
        if not any(row['kind'] == 'secret' for row in rows):
            pane.append({'id': '', 'kind': 'reset', 'label': 'Reset this section',
                         'help': 'Sets every %s setting back to its default.' % label})
        if index == len(categories) - 1:
            pane.append({'id': '', 'kind': 'native', 'label': "Kodi's settings dialog",
                         'help': 'The same settings in the dialog Kodi draws.'})
        panes.append(pane)
    return panes

def get(id, default=''):
    return kodi.get_setting(id) or (default or '')

def number(row):
    try:
        return int(float(get(row['id'], row['default'])))
    except ValueError:
        return int(row['default'])

def needs_login(row):
    # Watchlist and My List show disabled while signed out (appearance.ACCOUNT)
    return row['id'].startswith('appearance.') and row['id'][11:].replace('_pick', '') in appearance.ACCOUNT \
        and not get(IMDB)

def premiumize_ok(key):
    # the key against Premiumize's account info: True, False when rejected, None when Premiumize did not answer
    from .. import core
    try:
        response = core.request.execute(core, core.debrid.premiumize_account(key), cache=False)
        if response.status_code >= 500:
            return None
        return json.loads(response.content).get('status') == 'success'
    except Exception:
        return None

def confirm(heading, yes):
    from . import sheets
    return sheets.select(heading, [yes, 'Cancel']) == 0

class Window(kodi.xbmcgui.WindowXMLDialog):
    error = None
    native = False  # Kodi's own dialog asked for: the caller opens it once this window closes
    only_order = False  # opened for the Home order alone (its action in Kodi's own dialog): leaving it closes
    started = False

    def onInit(self):
        if self.started:
            return
        self.started = True
        self.rejected = set()
        self.order = None  # the Home order editor's keys while it is open
        self.grab = None  # the index of the row picked up in it
        self.before = None
        try:
            self.cats = categories()
            self.panes = shown(self.cats)
            self.rail = self.getControl(RAIL)
            self.pane = self.getControl(PANE)
            ListItem = kodi.xbmcgui.ListItem
            self.rail.addItems([ListItem(label=label, offscreen=True) for _, label, _ in self.cats])
            session = kodi.xbmcgui.Window(app.HOME_WINDOW)
            last = session.getProperty(SESSION + 'cat')
            cat = int(last) if last.isdigit() and int(last) < len(self.cats) else 0
            self.show(cat, session.getProperty(SESSION + 'row.%s' % cat))
            if self.only_order:
                self.show(self.find('appearance.order_pick')[0])
                self.open_order()
            self.setFocusId(PANE if last or self.only_order else RAIL)
        except Exception:
            self.__fail()

    # the rail and the pane

    def show(self, cat, row=0):
        self.cat = cat
        self.rows = self.panes[cat]
        self.rail.selectItem(cat)
        self.setProperty('a4k.desc', DESCRIPTIONS.get(self.cats[cat][0], ''))
        self.pane.reset()
        self.pane.addItems([self.item(r) for r in self.rows])
        row = int(row) if str(row).isdigit() else 0
        self.pane.selectItem(min(row, len(self.rows) - 1))

    def item(self, row):
        item = kodi.xbmcgui.ListItem(label=row['label'], offscreen=True)
        self.paint(item, row)
        return item

    def paint(self, item, row):
        off = needs_login(row)
        item.setLabel2(SIGN_IN if off else self.value(row))
        item.setProperty('a4k.off', 'true' if off else '')
        item.setProperty('a4k.step', 'true' if row['kind'] in ('enum', 'number') and not off else '')
        item.setProperty('a4k.help', row['help'])

    def value(self, row):
        kind, id = row['kind'], row['id']
        if kind == 'bool':
            return 'On' if get(id, row['default']) == 'true' else 'Off'
        if kind == 'enum':
            return row['options'][self.index(row)]
        if kind == 'number':
            n = number(row)
            return FORMATS.get(id, str)(n)
        if kind == 'text':
            return get(id)
        if kind == 'secret':  # never the value itself
            return 'Rejected' if id in self.rejected else 'Set' if get(id) else 'Not set'
        if id == 'appearance.my_list_pick':
            chosen = appearance.my_list()
            return chosen[1] if chosen else 'None'
        if id == 'kodi.mode':
            from .. import kodi_mode
            return kodi_mode.status()
        return MORE if kind in ('action', 'order') else ''

    def index(self, row):
        try:
            return min(max(int(get(row['id'], row['default'])), 0), len(row['options']) - 1)
        except ValueError:
            return int(row['default'])

    def find(self, id):
        return next((cat, i) for cat, rows in enumerate(self.panes) for i, row in enumerate(rows) if row['id'] == id)

    def set(self, id, value):
        kodi.xbmcaddon.Addon(kodi.addon_id).setSetting(id, value)

    def refresh(self):
        position = self.pane.getSelectedPosition()
        self.paint(self.pane.getListItem(position), self.rows[position])

    def remember(self):
        session = kodi.xbmcgui.Window(app.HOME_WINDOW)
        session.setProperty(SESSION + 'cat', str(self.cat))
        session.setProperty(SESSION + 'row.%s' % self.cat, str(self.pane.getSelectedPosition()))

    # input

    def onAction(self, action):
        try:
            action_id = action.getId()
            focus = self.getFocusId()
            if action_id in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
                return self.back(focus)
            if focus == RAIL and action_id == RIGHT:  # here, not the rail's onright: Kodi would move the focus first,
                return self.setFocusId(PANE)  # and the Right then stepped the pane's first row too (seen live)
            if focus == RAIL and action_id in (UP, DOWN):  # Kodi moved the rail already: its pane follows at once
                position = self.rail.getSelectedPosition()
                if position != self.cat:
                    self.remember()
                    self.show(position, kodi.xbmcgui.Window(app.HOME_WINDOW).getProperty(SESSION + 'row.%s' % position))
            elif focus == PANE and self.order is not None:
                if action_id in (UP, DOWN) and self.grab is not None:
                    self.move(self.pane.getSelectedPosition())
            elif focus == PANE and action_id in (LEFT, RIGHT):
                row = self.rows[self.pane.getSelectedPosition()]
                if row['kind'] in ('enum', 'number') and not needs_login(row):
                    self.step(row, -1 if action_id == LEFT else 1)
                elif action_id == LEFT:
                    self.setFocusId(RAIL)
        except Exception:
            self.__fail()

    def back(self, focus):
        # one level out: a picked-up row goes back, the order editor to its row, the pane to the rail, the rail closes
        if focus == PANE and self.order is not None:
            return self.cancel() if self.grab is not None else self.close_order()
        self.remember()
        if focus == PANE:
            return self.setFocusId(RAIL)
        self.close()

    def onClick(self, control_id):
        try:
            if control_id == RAIL:
                return self.setFocusId(PANE)
            if control_id != PANE:
                return
            if self.order is not None:
                return self.pick()
            self.activate(self.rows[self.pane.getSelectedPosition()])
        except Exception:
            self.__fail()

    def activate(self, row):
        kind, id = row['kind'], row['id']
        if needs_login(row):  # to the IMDb row
            cat, index = self.find(IMDB)
            self.remember()
            return self.show(cat, index)
        if kind == 'bool':
            self.set(id, 'false' if get(id, row['default']) == 'true' else 'true')
        elif kind == 'enum' and len(row['options']) > PICKER:
            from . import sheets
            choice = sheets.select(row['label'], row['options'], preselect=self.index(row))
            if choice is not None and choice >= 0:
                self.set(id, str(choice))
        elif kind == 'enum':
            self.set(id, str((self.index(row) + 1) % len(row['options'])))
        elif kind == 'number':
            typed = kodi.xbmcgui.Dialog().numeric(0, row['label'], str(number(row)))
            if typed:
                self.set(id, str(min(max(int(typed), row['min']), row['max'])))
        elif kind == 'text':
            typed = kodi.xbmcgui.Dialog().input(row['label'], defaultt=get(id)).strip()
            if typed:
                self.set(id, typed)
        elif kind == 'secret':
            self.secret(row)
        elif id == 'appearance.my_list_pick':
            appearance.pick_my_list()  # in this process: no second interpreter
        elif id == 'kodi.mode':
            from .. import kodi_mode
            kodi_mode.sheet()
        elif kind == 'action':
            kodi.xbmc.executebuiltin(row['action'])
        elif kind == 'order':
            return self.open_order()
        elif kind == 'reset':
            return self.reset()
        elif kind == 'native':
            self.native = True
            self.remember()
            return self.close()
        self.refresh()

    def step(self, row, delta):
        # Left / Right: the previous or next option or step, stopping at the ends
        if row['kind'] == 'enum':
            current, new = self.index(row), min(max(self.index(row) + delta, 0), len(row['options']) - 1)
        else:
            current = number(row)
            new = min(max(current + delta * row['step'], row['min']), row['max'])
        if new != current:
            self.set(row['id'], str(new))
            self.refresh()

    def secret(self, row):
        # typed hidden through Kodi's keyboard, never shown, logged or prefilled; Back or nothing typed changes nothing
        id = row['id']
        if get(id):
            from . import sheets
            choice = sheets.select(row['label'], ['Replace', 'Remove'])
            if choice == 1 and confirm('Remove the %s key?' % row['label'], 'Remove'):
                self.rejected.discard(id)
                self.set(id, '')
            if choice != 0:
                return
        gui = kodi.xbmcgui
        typed = gui.Dialog().input(row['label'], type=getattr(gui, 'INPUT_ALPHANUM', 0),
                                   option=getattr(gui, 'ALPHANUM_HIDE_INPUT', 2)).strip()
        if not typed:
            return
        self.set(id, typed)
        self.rejected.discard(id)
        if id == 'premiumize.apikey':
            ok = premiumize_ok(typed)
            if ok is False:
                self.rejected.add(id)
            elif ok is None:
                kodi.notification('Premiumize did not answer: the key is saved, not checked')

    def reset(self):
        _, label, rows = self.cats[self.cat]
        if not confirm('Reset %s to defaults?' % label, 'Reset'):
            return
        for row in rows:
            if row['default'] is not None and row['id'] != 'kodi_mode.prompted':  # the one-time question stays asked
                self.set(row['id'], row['default'])
        self.show(self.cat, self.pane.getSelectedPosition())

    # the Home order editor: the pane lists the rows; OK picks one up, Up/Down moves it, OK drops it (saved), Back
    # puts it back where it was

    def open_order(self):
        self.order = appearance.order()
        self.grab = None
        self.setProperty('a4k.desc', 'The order of the rows on Home.')
        self.pane.reset()
        self.pane.addItems([kodi.xbmcgui.ListItem(label='', offscreen=True) for _ in self.order])
        self.relabel()
        self.pane.selectItem(0)

    def relabel(self):
        chosen = appearance.my_list()
        for index, key in enumerate(self.order):
            item = self.pane.getListItem(index)
            item.setLabel(chosen[1] if key == 'my_list' and chosen else appearance.ROWS[key][0])
            grabbed = index == self.grab
            item.setLabel2('Moving' if grabbed else '' if appearance.on(key) else 'Off')
            item.setProperty('a4k.grabbed', 'true' if grabbed else '')
            item.setProperty('a4k.help', GRAB_HELP if self.grab is not None else ORDER_HELP)

    def pick(self):
        if self.grab is None:
            self.grab = self.pane.getSelectedPosition()
            self.before = list(self.order)
        else:
            self.grab = None
            self.set('appearance.order', ','.join(self.order))
        self.relabel()

    def move(self, position):
        # Kodi moved the focus already: the picked-up row follows it
        if position != self.grab and 0 <= position < len(self.order):
            self.order.insert(position, self.order.pop(self.grab))
            self.grab = position
            self.relabel()

    def cancel(self):
        key = self.order[self.grab]
        self.order, self.grab = self.before, None
        self.relabel()
        self.pane.selectItem(self.order.index(key))

    def close_order(self):
        self.order = None
        if self.only_order:
            return self.close()
        cat, index = self.find('appearance.order_pick')
        self.show(cat, index)

    def __fail(self):
        self.error = traceback.format_exc()
        self.close()

def open(only_order=False):
    # True when Kodi's own dialog should follow: the window failed (logged) or its last row asked for it
    try:
        window = Window('a4k-settings.xml', kodi.addon_path, 'Default', '1080i')
        window.only_order = only_order
        window.doModal()
        native, error = window.native, window.error
        del window
        if error:
            raise RuntimeError(error)
        return native
    except Exception:
        logger.error('settings window failed: %s' % traceback.format_exc())
        return True

def run(only_order=False):
    # RunScript(<add-on>,settings|order) (ui.py). Run inside the home window's interpreter, the home rows reloading after
    # the window closed crashed Kodi (seen on the TV box); Kodi's own dialog runs its actions this way too. The
    # Home order editor alone is opened from that dialog, so it never opens it again.
    if open(only_order) and not only_order:
        kodi.xbmc.executebuiltin('Addon.OpenSettings(%s)' % kodi.addon_id)
