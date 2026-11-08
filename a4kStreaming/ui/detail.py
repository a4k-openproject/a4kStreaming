# -*- coding: utf-8 -*-
# Title detail window (a4k-detail.xml): opened from the home window or the grid for a movie or a series.
# It paints at once from the card the user selected, then fetches the title on a worker thread and fills the season
# pills and the cast; the episodes shelf is the plugin's own episodes listing, loaded by Kodi (<content>).

import copy
import threading
import time
import traceback
from types import SimpleNamespace

from ..lib import kodi, logger
from .. import progress
from . import app, home

BUTTONS = (501, 502, 503, 504)
PLAY, TRAILER, WATCHLIST, MORE = BUTTONS
SEASONS = 520
EPISODES = 530
CAST = 540
PLOT = 510  # the plot's focus frame: select opens the whole plot

ACTION_MOVE_LEFT = 1
ACTION_MOVE_RIGHT = 2

SEASON_DWELL = 0.3  # seconds a season pill keeps focus before its episodes load
EPISODE_LOOK = 0.1  # s between looks for the opened season's episodes, to focus the one asked for
EPISODE_LOOKS = 50

KIND = {'movie': 'Movie', 'tvSeries': 'TV Series', 'tvEpisode': 'Episode'}

# a4k-detail.xml reads these window properties
PROPERTIES = ('kicker', 'title', 'rating', 'meta', 'plot', 'fanart', 'blur', 'trailer', 'trailers', 'inwatchlist', 'wlabel', 'yours',
              'playlabel')

# TitleFull by id, for this script process: back and forth between home and detail is free
CACHE_TTL = 10 * 60
CACHE_SIZE = 64
_cache = {}

def runtime(seconds):
    from .. import listing
    return listing.runtime_text(seconds)

def kicker(type):
    return KIND.get(type, '').upper()

def meta(date, runtime, genres):
    # the line after the star rating, as the TV skin writes it: the release date (else the year), runtime, three genres
    return ' · '.join(part for part in (date, runtime, ', '.join(genres[:3])) if part)

STATE = ('id', 'titleType', 'userRating', 'primaryVideos', 'a4k.in_watchlist', 'a4k.show_watched')

def buttons(core, title):
    # the action row and the ··· menu for the title's state: Trailer (one video, plays) or Trailers (a picker), the
    # + / check watchlist button, the TV skin's menu rows; state keeps what a later change rebuilds them from
    from .. import listing
    videos = title.get('primaryVideos', None) or []
    return {
        'trailer': listing.trailer_builtin(core, title),
        'trailers': 'Trailers' if len(videos) > 1 else 'Trailer',
        'watchlist': listing.watchlist_builtin(core, title),
        'inwatchlist': 'true' if title.get('a4k.in_watchlist', None) is True else '',
        'wlabel': '' if title.get('a4k.in_watchlist', None) is True else '+',
        'menu': listing.title_context_menu(core, title),
        'state': dict((key, title.get(key, None)) for key in STATE),
    }

def in_watchlist(core, id):
    # the TV skin's detail asks the watchlist about the title as it opens: True or False; None signed out or unanswered
    if not kodi.get_setting('imdb.at-main'):
        return None
    try:
        lists = core.query(core, core.utils.DictAsObject({'type': 'status', 'ids': [id], 'silent': True})) or []
        return next((node[id] for node in lists if node.get('listClass', None) == 'WATCH_LIST' and isinstance(node.get(id, None), bool)), None)
    except Exception:
        logger.error(traceback.format_exc())
        return None

def show_watched(core, title):
    # every released episode rated (the listing's watched rule); None for a movie or a show with none released
    episodes = [ep for ep in (title.get('episodes', None) or {}).get('episodes', None) or []
                if ep.get('releaseDate', None) and __released(core, ep['releaseDate'])]
    if title['titleType'] != 'tvSeries' or not episodes:
        return None
    return all(ep.get('userRating', None) is not None for ep in episodes)

def from_card(info):
    # the view model from the selected card's InfoLabels (home.labels), so the window paints before any request
    type = info.get('Property(a4k.type)', '')
    title = home.title_from_info(info)
    seconds = info.get('Duration(secs)', '')
    genres = info.get('Genre', '')
    vm = {
        'id': title['id'],
        'type': type,
        'kicker': kicker(type),
        'title': info.get('Label', ''),
        'rating': info.get('Rating', ''),
        'meta': meta(info.get('Year', ''), runtime(seconds) if seconds.isdigit() else '', genres.split(' / ') if genres else []),
        'plot': info.get('Plot', ''),
        'yours': '',
        'fanart': info.get('Art(fanart)', '') or info.get('Art(poster)', ''),
        'blur': info.get('Art(blur)', ''),
        'play': info.get('FolderPath', '') if type != 'tvSeries' else '',
        'playlabel': play_label(title['id']),
        'at': at(info),
        'seasons': [],
        'season': 0,
        'cast': [],
    }
    vm.update(buttons(SimpleNamespace(url=app.PLUGIN, kodi=kodi), title))
    return vm

def cast(core, title):
    # stars, then the rest of the cast, then the other principal credits (director, writers), each person once; the role
    # is the character, else the credit
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

def play_label(id):
    # Play, or Resume for a movie in progress (its play asks Resume or Start over)
    return 'Resume' if progress.in_progress(progress.load().get(id, None)) else 'Play'

def at(info):
    # a Continue Watching card's "<season>:<episode>": (season, episode), else None
    try:
        season, episode = info.get('Property(a4k.at)', '').split(':')
        return int(season), int(episode)
    except ValueError:
        return None

def season_marks(season, finished=()):
    # the TV skin's season tab marks: watched when its last episode is watched (the seasons listing's check), else
    # the share of its episodes watched as a progress bar. Watched is rated (a signed-in user's ratings) or played to
    # the end (finished: the episode ids the progress store has), so the marks show signed out as well.
    def seen(ep):
        return ep.get('userRating', None) is not None or ep.get('id', None) in finished
    rated = sum(1 for ep in season.episode_list if seen(ep))
    watched = seen(season.last_episode or {})
    progress = rated * 100 // len(season.episode_list) if not watched and 0 < rated < len(season.episode_list) else 0
    return 'true' if watched else '', str(progress) if progress else ''

def seasons(core, title, wanted=None):
    # [{label, url, watched, progress}] for the season pills, and the one to open on: the wanted season, else the latest
    # season with an aired episode
    from .. import listing
    finished = progress.watched_episodes(progress.load(), title['id'])
    episodes = (title.get('episodes', None) or {}).get('episodes', None) or []
    released = [ep['series']['seasonNumber'] for ep in episodes
                if ep.get('series', None) and ep.get('releaseDate', None) and __released(core, ep['releaseDate'])]
    grouped = listing.group_seasons(core, copy.deepcopy(episodes))  # it rewrites release dates; the cache keeps its own
    pills = []
    for key, season in grouped.items():
        season.episode_list = [ep for ep in episodes if ep['id'] in season.episode_ids]
        watched, share = season_marks(season, finished)
        pills.append({'key': key, 'label': 'Season %s' % key, 'watched': watched, 'progress': share,
                      'url': listing.season_url(core, title['id'], key, season) + '&widget=1'})
    latest = max(released) if released else None
    selected = next((i for i, pill in enumerate(pills) if pill['key'] == wanted), None)
    if selected is None:
        selected = next((i for i, pill in enumerate(pills) if pill['key'] == latest), 0)
    return pills, selected

def view_model(core, title, wanted=None):
    # strings and URLs for the window, from a TitleFull (query type=browse, or type=seasons with every episode)
    from .. import listing
    type = 'movie' if title['titleType'] in ('tvMovie', 'tvSpecial', 'video') else title['titleType']
    series = type == 'tvSeries'
    still = next(iter(title.get('stillFrame', None) or []), None)
    art = still or title.get('primaryImage', None)
    rating = (title.get('ratingsSummary', None) or {}).get('aggregateRating', None)
    genres = title.get('genres', None) or []
    title = dict(title, **{'a4k.show_watched': show_watched(core, title)})
    pills, selected = seasons(core, title, wanted) if series else ([], 0)
    # the TV skin's line: an ended series' years, else the release date (else the year); Unaired before it; the
    # signed-in user's own rating as its own mark
    year, end = title.get('releaseYear', None), title.get('releaseEndYear', None)
    date = '%s\u2013%s' % (year, end) if series and year and end and end != year else \
        listing.date_text(title.get('releaseDate', None)) or str(year or '')
    unaired = not title.get('releaseDate', None) or not __released(core, title['releaseDate'])
    yours = title.get('userRating', None)
    vm = {
        'id': title['id'],
        'type': type,
        'kicker': kicker(type),
        'title': title['titleText'],
        'rating': '%.1f' % rating if rating else '',
        'meta': ' \u00b7 '.join(part for part in (meta(date, runtime(title.get('runtime', None)), genres), 'Unaired' if unaired else '') if part),
        'yours': 'Your \u2605 %s' % yours if yours else '',
        'plot': title.get('plot', None) or '',
        'fanart': core.utils.fix_fanart_size(art) or '',
        'blur': core.utils.fix_blur_size(art) or '',
        'play': '' if series else listing.play_url(core, title),
        'playlabel': play_label(title['id']),
        'seasons': pills,
        'season': selected,
        'cast': cast(core, title),
    }
    vm.update(buttons(core, title))
    return vm

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

class Detail(kodi.xbmcgui.WindowXML):
    error = None
    vm = None
    started = False
    closed = False
    stopped = None  # set in open(); every thread of the window ends on it (home.spawn)
    threads = ()
    dwelling = None  # the running season dwell's cancel
    title = None  # the fetched title, for the season marks again after a play
    stamp = None  # the progress store's change time the episodes listing was asked with (its t param)

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
                self.stamp = progress.stamp()
                home.spawn(self, self.fill)
            elif self.title and (home.playing() or self.stamp != progress.stamp()):
                home.spawn(self, self.refresh)  # back from a play: the bars and marks move
        except Exception:
            self.__fail()

    def refresh(self):
        # the store changed under the window: the season marks and the Play label again, and the shown season's
        # episodes reload under a new URL (once, from onInit, after the player went: never next to a running plugin
        # call or the player's stop)
        try:
            if not home.after_play(self.stopped) or self.closed or self.stamp == progress.stamp():
                return
            self.stamp = progress.stamp()
            vm = view_model(plugin_core(), self.title, self.vm['seasons'][self.season_index()]['key'] if self.vm['seasons'] else None)
            if self.closed:
                return
            self.vm = dict(self.vm, playlabel=vm['playlabel'], seasons=vm['seasons'])
            self.setProperty('a4k.playlabel', vm['playlabel'])
            control = self.getControl(SEASONS)
            for index, pill in enumerate(vm['seasons']):
                item = control.getListItem(index)
                for key in ('watched', 'progress'):
                    item.setProperty(key, pill[key])
            self.select_season(self.season_index())
        except Exception:
            self.__fail()

    def season_index(self):
        return max(self.getControl(SEASONS).getSelectedPosition(), 0)

    def fill(self):
        try:
            core = plugin_core()
            title = fetch(core, self.vm['id'], self.vm['type'] == 'tvSeries')
            if title is None or self.closed:
                return  # no answer: the card's text stays, the shelves stay empty
            # the watchlist state is asked on every open, never cached with the title
            self.title = dict(title, **{'a4k.in_watchlist': in_watchlist(core, self.vm['id'])})
            wanted = self.vm.get('at', None)
            vm = view_model(core, self.title, wanted[0] if wanted else None)
            if self.closed:
                return
            self.paint(vm)
            self.fill_lists(vm)
            if wanted:
                self.focus_episode(*wanted)
        except Exception:
            self.__fail()

    def fill_lists(self, vm):
        ListItem = kodi.xbmcgui.ListItem
        people = []
        for person in vm['cast']:
            item = ListItem(label=person['name'], label2=person['role'], offscreen=True)
            item.setArt({'thumb': person['face'] or ''})
            item.setProperty('id', person['id'])
            people.append(item)
        self.getControl(CAST).addItems(people)

        if not vm['seasons']:
            return
        pills = []
        for pill in vm['seasons']:
            item = ListItem(label=pill['label'], offscreen=True)
            for key in ('url', 'watched', 'progress'):
                item.setProperty(key, pill[key])
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
        url = '%s&t=%s' % (pill['url'], self.stamp)
        if self.getProperty('a4k.episodes') != url:
            self.setProperty('a4k.season', pill['label'])
            self.setProperty('a4k.episodes', url)

    def focus_episode(self, season, episode):
        # a Continue Watching card's episode: focused once the opened season's listing is in (a bounded wait, given
        # up when the window closes)
        label = 'S%s E%s' % (season, episode)
        for _ in range(EPISODE_LOOKS):
            if self.closed:
                return
            count = int(kodi.xbmc.getInfoLabel('Container(%s).NumItems' % EPISODES) or 0)
            for index in range(count):
                if kodi.xbmc.getInfoLabel('Container(%s).ListItemAbsolute(%s).Property(a4k.label)' % (EPISODES, index)) == label:
                    kodi.xbmc.executebuiltin('Control.SetFocus(%s,%s,absolute)' % (EPISODES, index))
                    return
            if count or self.stopped.wait(EPISODE_LOOK):
                return  # the listing is in and the episode is not in it, or the window went

    def __dwell(self):
        # a season's episodes load once its pill keeps focus for a moment, so arrowing across pills starts no listings
        if self.dwelling:
            self.dwelling.set()
        self.dwelling = home.spawn(self, self.__guard_select, delay=SEASON_DWELL)

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
                self.toggle_watchlist()
            elif control_id == MORE:
                self.menu()
            elif control_id == SEASONS:
                self.select_season()
            elif control_id == CAST:
                self.person()
            elif control_id == PLOT:
                self.full_plot()
        except Exception:
            self.__fail()

    def play(self):
        # a series has no Play button (the TV skin's row): its episodes play from the shelf
        if self.vm['play']:
            home.run(home.play_builtin(self.vm['play']))

    def menu(self):
        home.menu(self.vm['menu'], self.vm['id'], self.vm['title'], self.__changed)

    def __changed(self, builtin):
        # a watchlist row run from the menu flips the button as the button itself does
        if 'type=watchlist_' in builtin:
            self.__flip('type=watchlist_add' in builtin)

    def toggle_watchlist(self):
        # the TV skin's + / check button: add or remove by state, then the button and the menu show the other one
        builtin = self.vm['watchlist']
        home.run(builtin)
        self.__flip('type=watchlist_add' in builtin)

    def __flip(self, added):
        state = dict(self.vm['state'], **{'a4k.in_watchlist': added})
        self.vm = dict(self.vm, **buttons(SimpleNamespace(url=app.PLUGIN, kodi=kodi), state))
        for key in ('inwatchlist', 'wlabel'):
            self.setProperty('a4k.%s' % key, self.vm[key])

    def person(self):
        # a cast face opens the person's known-for grid
        item = self.getControl(CAST).getSelectedItem()
        if item and item.getProperty('id'):
            from . import grid
            grid.known_for(item.getProperty('id'), item.getLabel())

    def full_plot(self):
        if self.vm['plot']:
            kodi.xbmcgui.Dialog().textviewer(self.vm['title'], self.vm['plot'])

    def close(self):
        self.closed = True
        super(Detail, self).close()

    def __fail(self):
        self.error = traceback.format_exc()
        if not self.closed:  # a worker's error after the close: the window is gone already
            self.close()

def open(info):
    # a window error is logged and closes the window
    try:
        window = Detail('a4k-detail.xml', kodi.addon_path, 'Default', '1080i')
        window.stopped = threading.Event()
        # a reopened add-on (after the Home key) comes back to this window, not to the home window under it
        window.setProperty('a4k.home', 'true')
        window.setProperty('a4k.auth', 'true' if kodi.get_setting('imdb.at-main') else '')
        window.paint(from_card(info))
        window.setProperty('a4k.series', 'true' if window.vm['type'] == 'tvSeries' else '')
        home.modal(window)
        error = window.error
        del window
        if error:
            raise RuntimeError(error)
    except Exception:
        logger.error('detail window failed: %s' % traceback.format_exc())
