# -*- coding: utf-8 -*-
# Title detail window (a4k-detail.xml): opened from the home window for a movie or a series.
# It paints at once from the card the user selected, then fetches the title on a worker thread and fills the season
# pills and the cast; the episodes shelf is the plugin's own episodes listing, loaded by Kodi (<content>).

import copy
import threading
import time
import traceback
from types import SimpleNamespace

from ..lib import kodi, logger
from . import app, home

BUTTONS = (501, 502, 503, 504)
PLAY, TRAILER, WATCHLIST, MORE = BUTTONS
SEASONS = 520
EPISODES = 530
CAST = 540

ACTION_MOVE_LEFT = 1
ACTION_MOVE_RIGHT = 2

# a title that failed in the window opens its classic listing for the rest of the session; logged once
FAILED = 'a4k.ui.detail.failed'
SEASON_DWELL = 0.3  # seconds a season pill keeps focus before its episodes load

KIND = {'movie': 'Movie', 'tvSeries': 'TV Series', 'tvEpisode': 'Episode'}

# a4k-detail.xml reads these window properties
PROPERTIES = ('kicker', 'title', 'rating', 'year', 'runtime', 'certificate', 'plot', 'fanart', 'blur', 'trailer')

# TitleFull by id, for this script process: back and forth between home and detail is free
CACHE_TTL = 10 * 60
CACHE_SIZE = 64
_cache = {}

def runtime(seconds):
    minutes = int(seconds or 0) // 60
    if not minutes:
        return ''
    return '%sh %sm' % divmod(minutes, 60) if minutes >= 60 else '%sm' % minutes

def kicker(type, genre):
    return ' · '.join(part for part in (KIND.get(type, ''), genre) if part).upper()

def __menu(core, title):
    from .. import listing
    return listing.title_context_menu(core, title)

def __actions(menu, has_trailer):
    builtins = dict(menu)
    return builtins['IMDb: Trailer'] if has_trailer else '', builtins.get('IMDb: Add to watchlist', '')

def from_card(info):
    # the view model from the selected card's InfoLabels (home.labels), so the window paints before any request
    type = info.get('Property(a4k.type)', '')
    title = home.title_from_info(info)
    menu = __menu(SimpleNamespace(url=app.PLUGIN, kodi=kodi), title)
    trailer, watchlist = __actions(menu, title['primaryVideos'])
    seconds = info.get('Duration(secs)', '')
    return {
        'id': title['id'],
        'type': type,
        'kicker': kicker(type, info.get('Genre', '').split(' / ')[0]),
        'title': info.get('Label', ''),
        'rating': info.get('Rating', ''),
        'year': info.get('Year', ''),
        'runtime': runtime(seconds) if seconds.isdigit() and type != 'tvSeries' else '',
        'certificate': info.get('MPAA', ''),
        'plot': info.get('Plot', ''),
        'fanart': info.get('Art(fanart)', '') or info.get('Art(poster)', ''),
        'blur': info.get('Art(blur)', ''),
        'play': info.get('FolderPath', '') if type != 'tvSeries' else '',
        'trailer': trailer,
        'watchlist': watchlist,
        'menu': menu,
        'seasons': [],
        'season': 0,
        'cast': [],
    }

def cast(core, title):
    # stars, then the rest of the cast, then the other principal credits (director, writers), each person once, as the
    # classic Cast & Crew listing orders them; the role is the character, else the credit
    characters = {}
    for credit in title.get('credits', None) or []:
        if credit.get('name', None) and credit.get('characters', None):
            characters[credit['name']['id']] = ' / '.join(credit['characters'])
    principal = title.get('principalCredits', None) or []
    groups = [(c['category'], c['credits']) for c in principal if c['category'] == 'Stars']
    groups.append(('Cast', title.get('credits', None) or []))
    groups += [(c['category'], c['credits']) for c in principal if c['category'] != 'Stars']

    people, seen = [], set()
    for category, credits in groups:
        for credit in credits:
            person = credit.get('name', None) or credit
            if person['id'] in seen:
                continue
            seen.add(person['id'])
            role = category[:-1] if category.endswith('s') else category
            people.append({
                'id': person['id'],
                'name': person['nameText'],
                'role': characters.get(person['id'], '' if category in ('Stars', 'Cast') else role),
                'face': core.utils.resize_image(person.get('primaryImage', None), (200, 200)),
            })
    return people

def __released(core, date):
    try:
        return core.date(date['year'], date['month'], date['day']) <= core.date.today()
    except Exception:
        return False

def seasons(core, title):
    # [{label, url}] for the season pills, and the one to open on: the latest season with an aired episode
    from .. import listing
    episodes = (title.get('episodes', None) or {}).get('episodes', None) or []
    released = [ep['series']['seasonNumber'] for ep in episodes
                if ep.get('series', None) and ep.get('releaseDate', None) and __released(core, ep['releaseDate'])]
    grouped = listing.group_seasons(core, copy.deepcopy(episodes))  # it rewrites release dates; the cache keeps its own
    pills = [{'key': key, 'label': 'Season %s' % key, 'url': listing.season_url(core, title['id'], key, season) + '&widget=1'}
             for key, season in grouped.items()]
    latest = max(released) if released else None
    selected = next((i for i, pill in enumerate(pills) if pill['key'] == latest), 0)
    return pills, selected

def view_model(core, title):
    # strings and URLs for the window, from a TitleFull (query type=browse, or type=seasons with every episode)
    from .. import listing
    type = 'movie' if title['titleType'] in ('tvMovie', 'tvSpecial', 'video') else title['titleType']
    series = type == 'tvSeries'
    still = next(iter(title.get('stillFrame', None) or []), None)
    art = still or title.get('primaryImage', None)
    rating = (title.get('ratingsSummary', None) or {}).get('aggregateRating', None)
    genres = title.get('genres', None) or []
    count = len((title.get('episodes', None) or {}).get('seasons', None) or [])
    menu = __menu(core, title)
    trailer, watchlist = __actions(menu, title.get('primaryVideos', None))
    pills, selected = seasons(core, title) if series else ([], 0)
    return {
        'id': title['id'],
        'type': type,
        'kicker': kicker(type, genres[0] if genres else ''),
        'title': title['titleText'],
        'rating': '%.1f' % rating if rating else '',
        'year': str(title.get('releaseYear', None) or ''),
        'runtime': ('%s Season%s' % (count, '' if count == 1 else 's') if count else '') if series else runtime(title.get('runtime', None)),
        'certificate': title.get('certificate', None) or '',
        'plot': title.get('plot', None) or '',
        'fanart': core.utils.fix_fanart_size(art) or '',
        'blur': core.utils.fix_blur_size(art) or '',
        'play': '' if series else listing.play_url(core, title),
        'trailer': trailer,
        'watchlist': watchlist,
        'menu': menu,
        'seasons': pills,
        'season': selected,
        'cast': cast(core, title),
    }

def fetch(core, id, series):
    # TitleFull (with every episode for a series), from the in-process cache when it is fresh
    hit = _cache.get(id, None)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    params = core.utils.DictAsObject({'type': 'seasons' if series else 'browse', 'id': id, 'silent': True, 'raw': True})
    title = core.query(core, params)
    if not isinstance(title, dict):
        return None
    while len(_cache) >= CACHE_SIZE:
        _cache.pop(next(iter(_cache)))
    _cache[id] = (time.time(), title)
    return title

def plugin_core():
    # the plugin's core module, imported off the GUI path (the worker thread); its URLs point at the plugin
    from .. import core
    core.url = app.PLUGIN
    return core

def classic(info):
    # the classic listing for the title: a series' seasons, a movie's page
    type = 'seasons' if info.get('Property(a4k.type)', '') == 'tvSeries' else 'browse'
    return 'ActivateWindow(Videos,%s?action=query&type=%s&id=%s,return)' % (app.PLUGIN, type, info.get('Property(a4k.id)', ''))

def fail(reason):
    __home = kodi.xbmcgui.Window(app.HOME_WINDOW)
    if __home.getProperty(FAILED):
        return
    __home.setProperty(FAILED, 'true')
    logger.error('detail window failed, using the classic listing: %s' % reason)

class Detail(kodi.xbmcgui.WindowXML):
    error = None
    vm = None
    started = False
    closed = False
    timer = None

    def paint(self, vm):
        self.vm = vm
        for key in PROPERTIES:
            self.setProperty('a4k.%s' % key, vm[key])

    def onInit(self):
        # runs again on every return (after a trailer, playback or a listing): no network, the worker starts once
        try:
            self.getControl(PLAY)  # raises when the XML did not load
            kodi.xbmcgui.Window(app.HOME_WINDOW).setProperty(app.OPEN_WINDOW, str(kodi.xbmcgui.getCurrentWindowId()))
            if not self.started:
                self.started = True
                threading.Thread(target=self.fill).start()
        except Exception:
            self.__fail()

    def fill(self):
        try:
            core = plugin_core()
            title = fetch(core, self.vm['id'], self.vm['type'] == 'tvSeries')
            if title is None or self.closed:
                return  # no answer: the card's text stays, the shelves stay empty
            vm = view_model(core, title)
            if self.closed:
                return
            self.paint(vm)
            self.fill_lists(vm)
        except Exception:
            self.__fail()

    def fill_lists(self, vm):
        ListItem = kodi.xbmcgui.ListItem
        people = []
        for person in vm['cast']:
            item = ListItem(label=person['name'], label2=person['role'], offscreen=True)
            item.setArt({'thumb': person['face'] or ''})
            people.append(item)
        self.getControl(CAST).addItems(people)

        if not vm['seasons']:
            return
        pills = []
        for pill in vm['seasons']:
            item = ListItem(label=pill['label'], offscreen=True)
            item.setProperty('url', pill['url'])
            pills.append(item)
        control = self.getControl(SEASONS)
        control.addItems(pills)
        control.selectItem(vm['season'])
        self.select_season(vm['season'])

    def select_season(self, index=None):
        if self.closed or not self.vm['seasons']:
            return
        if index is None:
            index = self.getControl(SEASONS).getSelectedPosition()
        pill = self.vm['seasons'][max(index, 0)]
        if self.getProperty('a4k.episodes') != pill['url']:
            self.setProperty('a4k.season', pill['label'])
            self.setProperty('a4k.episodes', pill['url'])

    def __dwell(self):
        # a season's episodes load once its pill keeps focus for a moment, so arrowing across pills starts no listings
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(SEASON_DWELL, self.__guard_select)
        self.timer.start()

    def __guard_select(self):
        try:
            self.select_season()
        except Exception:
            self.__fail()

    def onAction(self, action):
        try:
            action_id = action.getId()
            if action_id in (home.ACTION_PREVIOUS_MENU, home.ACTION_NAV_BACK):
                return self.close()
            focus = self.getFocusId()
            if focus == SEASONS and action_id in (ACTION_MOVE_LEFT, ACTION_MOVE_RIGHT):
                self.__dwell()
            elif focus == EPISODES and action_id in (home.ACTION_SELECT_ITEM, home.ACTION_MOUSE_LEFT_CLICK):
                # a provider row: Kodi sends no click to Python (spike 2c); the item's path is its play URL
                home.run(home.click_builtin(home.labels('Container(%s).ListItem' % EPISODES)))
            elif focus in BUTTONS and action_id == home.ACTION_CONTEXT_MENU:
                self.menu()
        except Exception:
            self.__fail()

    def onClick(self, control_id):
        try:
            if control_id == PLAY:
                self.play()
            elif control_id == TRAILER:
                home.run(self.vm['trailer'])
            elif control_id == WATCHLIST:
                home.run(self.vm['watchlist'])
            elif control_id == MORE:
                self.menu()
            elif control_id == SEASONS:
                self.select_season()
        except Exception:
            self.__fail()

    def play(self):
        if self.vm['play']:
            return home.run('PlayMedia(%s)' % self.vm['play'])
        # a series plays the first episode of the open season
        path = kodi.xbmc.getInfoLabel('Container(%s).ListItemAbsolute(0).FolderPath' % EPISODES)
        if path:
            home.run('PlayMedia(%s)' % path)

    def menu(self):
        items = self.vm['menu']
        choice = kodi.xbmcgui.Dialog().contextmenu([label for label, _ in items])
        if choice is not None and choice >= 0:
            home.run(items[choice][1])

    def close(self):
        self.closed = True
        if self.timer:
            self.timer.cancel()
        super(Detail, self).close()

    def __fail(self):
        self.error = traceback.format_exc()
        self.close()

def open(info):
    # True when the window ran; False when it failed (logged once per session) and the caller opens the classic listing
    __home = kodi.xbmcgui.Window(app.HOME_WINDOW)
    if __home.getProperty(FAILED):
        return False
    previous = __home.getProperty(app.OPEN_WINDOW)
    try:
        window = Detail('a4k-detail.xml', kodi.addon_path, 'Default', '1080i')
        # a reopened add-on (after the Home key) comes back to this window, not to the home window under it
        window.setProperty('a4k.home', 'true')
        window.setProperty('a4k.auth', 'true' if kodi.get_setting('imdb.at-main') else '')
        window.paint(from_card(info))
        window.setProperty('a4k.series', 'true' if window.vm['type'] == 'tvSeries' else '')
        try:
            window.doModal()
        finally:
            window.closed = True
            if previous:
                __home.setProperty(app.OPEN_WINDOW, previous)
        error = window.error
        del window
        if error:
            raise RuntimeError(error)
        return True
    except Exception:
        fail(traceback.format_exc())
        return False
