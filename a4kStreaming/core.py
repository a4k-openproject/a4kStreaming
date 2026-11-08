# -*- coding: utf-8 -*-

import sys
import os
import json
import threading
import time
import base64
import importlib
import traceback
from collections import OrderedDict
from datetime import datetime, date

from .lib import (
    kodi,
    logger,
    request,
    utils,
    cache,
    debrid,
)

from .lib.database import db

core = sys.modules[__name__]
utils.core = core

removed_bytes = db.cleanup()
if removed_bytes:
    logger.notice('Removed %s bytes from cache' % removed_bytes)

api_mode_enabled = True
url = ''
handle = None
skip_end_of_dir = 'skip_end_of_dir'

contentType = 'videos'

from .explorer import root, query, profile, trailer, play, cloud, cache_sources
from .imdb import gallery_types
from .provider import provider, provider_meta
from .trakt import trakt

provider(core, core.utils.DictAsObject({ 'type': 'install', 'init': True }))

# listings Kodi may keep on disk and show again on Back: the menus and public IMDb pages. Personal ones (watchlist,
# lists, recommended), search results and debrid folders run again on every visit.
public_queries = set(gallery_types + ['seasons', 'episodes', 'browse', 'knownfor'])

def cache_to_disc(action, type):
    if action is None:
        return True
    return action == 'query' and type in public_queries

def not_supported():
    kodi.notification('Not supported yet')
    utils.end_action(core, True)

def main(url, handle, paramstring):
    core.api_mode_enabled = False
    core.url = url
    core.handle = handle

    params = utils.DictAsObject(utils.parse_qsl(paramstring))
    action = params.get('action', None)

    if action is None:
        # the menu a skin's widget picker browses (main.py opens the home window for the Videos window)
        core.contentType = 'videos'
        root(core)

    elif action == 'cloud':
        # the Debrid tile's listing
        core.contentType = 'videos'
        if cloud(core, params) == skip_end_of_dir:
            return

    elif action == 'query':
        query(core, params)

    elif action == 'profile':
        profile(core, params)
        return

    elif action == 'trailer':
        trailer(core, params)
        return

    elif action == 'reset_resume':
        # the episode menu's Reset resume progress: Kodi keeps the resume point against the item's play URL
        kodi.json_rpc('Files.SetFileDetails', {'file': params.path, 'media': 'video', 'resume': {'position': 0, 'total': 0}})
        kodi.xbmc.executebuiltin('Container.Refresh')
        return

    elif action == 'play':
        play(core, params)
        return

    elif action == 'provider':
        provider(core, params)
        return

    elif action == 'trakt':
        trakt(core, params)
        return

    elif action == 'cache_sources':
        cache_sources(core, params)
        kodi.xbmcplugin.endOfDirectory(core.handle)
        return

    else:
        not_supported()

    kodi.xbmcplugin.endOfDirectory(core.handle, cacheToDisc=cache_to_disc(action, params.type))

    # the listing is on screen: refresh any page that was answered stale, then keep the cache under its size cap
    request.revalidate(core)
    db.cleanup()
