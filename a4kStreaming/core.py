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

viewTypes = [
    51,   # Poster
    52,   # Icon Wall
    53,   # Shift
    54,   # Info Wall
    55,   # Wide List
    500,  # Wall
]
viewType = None
contentType = 'videos'

from .explorer import root, query, profile, trailer, years, play, search, cloud, cache_sources
from .provider import provider, provider_meta
from .trakt import trakt

provider(core, core.utils.DictAsObject({ 'type': 'install', 'init': True }))

def not_supported():
    kodi.notification('Not supported yet')
    utils.end_action(core, True)

def main(url, handle, paramstring):
    core.api_mode_enabled = False
    core.url = url
    core.handle = handle

    listitem_path = kodi.xbmc.getInfoLabel('ListItem.FolderPath')
    params = utils.DictAsObject(utils.parse_qsl(paramstring))
    action = params.get('action', None)

    if action is None:
        # the root opens the home window when the window interface is on; a widget always gets the listing
        if params.widget != '1':
            from .ui import app as ui_app
            if ui_app.enabled():
                ui_app.open_from_root(core.handle)
                return

        core.viewType = kodi.get_setting('views.menu')
        core.contentType = 'videos'
        root(core)

    elif action == 'years':
        core.viewType = kodi.get_setting('views.menu')
        core.contentType = 'videos'
        years(core, params)

    elif action == 'search':
        core.viewType = kodi.get_setting('views.titles')
        core.contentType = 'movies'
        search(core, params)

    elif action == 'cloud':
        core.viewType = kodi.get_setting('views.menu')
        core.contentType = 'videos'
        if cloud(core, params) == skip_end_of_dir:
            return

    elif action == 'query':
        if params.type == 'seasons':
            core.viewType = kodi.get_setting('views.seasons')
        elif params.type == 'episodes':
            core.viewType = kodi.get_setting('views.episodes')
        elif params.type == 'browse':
            core.viewType = kodi.get_setting('views.movie')
        else:
            core.viewType = kodi.get_setting('views.titles')
        query(core, params)

    elif action == 'profile':
        profile(core, params)
        return

    elif action == 'trailer':
        trailer(core, params)
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

    kodi.xbmcplugin.setContent(core.handle, core.contentType)
    kodi.xbmcplugin.endOfDirectory(core.handle)

    # a skin widget (widget=1) has no view of its own to switch, so it skips the wait and the view mode
    if params.widget != '1':
        kodi.xbmc.sleep(100)
        dir_switch = not listitem_path or listitem_path == kodi.xbmc.getInfoLabel('Container.FolderPath')
        if dir_switch:
            utils.apply_viewtype(core)

    # the listing is on screen: refresh any page that was answered stale, then keep the cache under its size cap
    request.revalidate(core)
    db.cleanup()
