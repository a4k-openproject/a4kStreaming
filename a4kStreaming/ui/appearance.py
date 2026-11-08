# -*- coding: utf-8 -*-
# The Appearance settings, the Apple TV skin options with its defaults: the Browse row, which home rows show and in
# what order, the category tabs, what the top shelf shows and how often it turns. Also the My List picker, run by the
# settings window and by ui.py from Kodi's settings dialog (the Home order editor is the settings window's).

import json

from ..lib import kodi
from .app import row_url

# key: (title, listing type, the top shelf's kicker over its titles); this order is the default home order
ROWS = {
    'trending_movies': ('Trending Movies', 'popularMovies', 'TRENDING NOW'),
    'trending_tv': ('Trending TV Shows', 'popularTVShows', 'TRENDING NOW'),
    'reality': ('Reality TV', 'popularRealityTVShows', 'REALITY'),
    'animations': ('Animations', 'popularAnimations', 'ANIMATION'),
    'animation_tv': ('Animated TV', 'popularAnimationTVShows', 'ANIMATED TV'),
    'my_list': ('My List', 'list', ''),  # the list's own name as title and kicker
    'watchlist': ('Watchlist', 'watchlist', ''),
}
# the toggles on by default; continue_watching is its own row (list 308), never one of the ordered slots or a hero source
ON = ('browse', 'tabs', 'continue_watching', 'trending_movies', 'trending_tv', 'watchlist')
ACCOUNT = ('my_list', 'watchlist')  # need an IMDb login
NOT_IN_HERO = ('watchlist',)  # "My home sections" draws from the others that are on
HERO_TURNS = (10, 15, 20, 30, 0)  # appearance.hero_turn, seconds; 0 is Off
HERO_SOURCES = ('movies', 'tv', 'both', 'home')  # appearance.hero_source
HERO_DEFAULT = ('trending_movies',)

def setting(key):
    return kodi.get_setting('appearance.' + key)

def on(key):
    if key == 'my_list':  # on while a list is chosen
        return bool(my_list())
    value = setting(key)
    return value == 'true' if value else key in ON

def index(key, values, default):
    try:
        return values[int(setting(key))]
    except (ValueError, IndexError):
        return default

def hero_turn():
    return index('hero_turn', HERO_TURNS, 15)

def hero_source():
    return index('hero_source', HERO_SOURCES, 'movies')

def order():
    # the saved order (appearance.order, keys joined by commas), unknown keys dropped and new ones at their default place
    saved = [key for key in setting('order').split(',') if key in ROWS]
    return saved + [key for key in ROWS if key not in saved]

def my_list():
    # appearance.my_list: "<list id> <list name>", or empty for none
    id, _, name = setting('my_list').partition(' ')
    return (id, name or ROWS['my_list'][0]) if id else None

def rows(signed_in):
    # the home rows that are on, in the saved order: (key, title, listing URL, kicker)
    shown = []
    for key in order():
        title, type, kicker = ROWS[key]
        if not on(key) or (key in ACCOUNT and not signed_in):
            continue
        url = row_url(type)
        if key == 'my_list':
            chosen = my_list()
            if not chosen:
                continue
            url = '%s&id=%s' % (url, chosen[0])
            title = chosen[1]
            kicker = title.upper()
        shown.append((key, title, url, kicker))
    return shown

def hero_keys(shown):
    # the rows the top shelf takes its titles from: one source, both trending ones, or every row
    # that is on (no Watchlist); with none on, the trending movies
    source = hero_source()
    if source == 'tv':
        return ('trending_tv',)
    if source == 'both':
        return ('trending_movies', 'trending_tv')
    if source == 'home':
        return tuple(key for key, _, _, _ in shown if key not in NOT_IN_HERO) or HERO_DEFAULT
    return HERO_DEFAULT

def public_types():
    # the listing types of the rows that are on and need no login (the service keeps them warm)
    return [ROWS[key][1] for key in order() if on(key) and key not in ACCOUNT]

# the My List settings action

def lists():
    # the signed-in user's title lists, as the Lists listing gives them: [(id, name)]
    request = {'jsonrpc': '2.0', 'id': 1, 'method': 'Files.GetDirectory',
               'params': {'directory': row_url('lists'), 'media': 'files', 'properties': ['plot']}}
    files = json.loads(kodi.xbmc.executeJSONRPC(json.dumps(request))).get('result', {}).get('files') or []
    found = []
    for item in files:
        id = item.get('file', '').partition('&id=')[2].split('&')[0]
        # listing.__add_lists says what a list holds in its plot; people lists cannot be a row of titles
        if id and item.get('plot', '').startswith('Movie or TV Series'):
            found.append((id, item.get('label', '')))
    return found

def pick_my_list():
    from . import sheets
    if not kodi.get_setting('imdb.at-main'):
        return kodi.notification('My List needs an IMDb login')
    found = lists()
    current = my_list()
    labels = ['None'] + [name for _, name in found]
    preselect = next((i + 1 for i, (id, _) in enumerate(found) if current and id == current[0]), 0)
    choice = sheets.select('My List', labels, preselect=preselect)
    if choice is None or choice < 0:
        return
    kodi.xbmcaddon.Addon(kodi.addon_id).setSetting('appearance.my_list', '%s %s' % found[choice - 1] if choice else '')
