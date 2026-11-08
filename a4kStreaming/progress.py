# -*- coding: utf-8 -*-
# Continue Watching: the play positions of the movies and episodes the add-on plays, kept in progress.json in the
# add-on's profile. The service's player monitor writes them (service.py), the listings and windows read them. One entry
# per movie (its id) or episode (show id, season and episode), whatever URL it played from: play URLs carry the title's
# metadata and change with it.

import json
import os
import re
import time

from .lib import kodi

PATH = os.path.join(kodi.addon_profile, 'progress.json')
IN_PROGRESS = (1, 94)  # percent; from 95 % on a title counts as finished and leaves the row
ROW_SIZE = 20
KEEP = 200
MAX_AGE = 180 * 24 * 3600

def meta(title):
    # what an entry keeps of the play URL's title metadata (playback.play): None for an episode without its show
    # id, season and episode, which cannot be keyed
    episode = title.get('mediatype') == 'episode'
    if episode and not (title.get('tvshowid') and title.get('season') and title.get('episode')):
        return None
    name = title.get('title') or ''
    return {
        'type': 'episode' if episode else 'movie',
        'id': title.get('imdbnumber') or '',
        'show': title.get('tvshowid') if episode else None,
        'season': int(title['season']) if episode else None,
        'episode': int(title['episode']) if episode else None,
        # the season listing numbers its episode titles ("3. Name")
        'title': re.sub(r'^\d+\. ', '', name) if episode else name,
        'show_title': title.get('tvshowtitle') or '' if episode else '',
        'art': title.get('poster') or '',
        'year': title.get('year') or '',
    }

def key(entry):
    if entry.get('show'):
        return '%s:%s:%s' % (entry['show'], entry['season'], entry['episode'])
    return entry.get('id') or ''

def percent(entry):
    try:
        return int(round(float(entry['pos']) / float(entry['dur']) * 100))
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return 0

def in_progress(entry):
    return bool(entry) and IN_PROGRESS[0] <= percent(entry) <= IN_PROGRESS[1]

def clock(seconds):
    # "1:02:03", "42:05"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return '%d:%02d:%02d' % (hours, minutes, secs) if hours else '%d:%02d' % (minutes, secs)

def record(store, meta, pos, dur, now, finished=False):
    # the play's position; finished (the end, the next episode from the credits) puts it at the end. watched stays once
    # set, so a rewatched episode keeps its mark while it is in progress again
    if not meta or not dur:
        return store
    previous = store.get(key(meta)) or {}
    entry = dict(meta, pos=float(dur if finished else pos), dur=float(dur), t=now)
    entry['watched'] = bool(previous.get('watched')) or percent(entry) > IN_PROGRESS[1]
    store[key(meta)] = entry
    return prune(store, now)

def prune(store, now):
    fresh = sorted(((k, e) for k, e in store.items() if now - e.get('t', 0) < MAX_AGE), key=lambda item: -item[1].get('t', 0))
    return dict(fresh[:KEEP])

def listing(store):
    # the row: in progress, the latest play first
    entries = sorted((e for e in store.values() if in_progress(e)), key=lambda e: -e.get('t', 0))
    return entries[:ROW_SIZE]

def watched_episodes(store, show):
    # the episode ids of a show played to the end (season marks count them as watched)
    return {e.get('id') for e in store.values() if e.get('show') == show and e.get('watched')}

def load(path=None):
    try:
        with open(path or PATH, encoding='utf-8') as f:
            store = json.load(f)
        return store if isinstance(store, dict) else {}
    except Exception:  # none yet, or unreadable: an empty store
        return {}

def save(store, path=None):
    # a temp file renamed over the store: the service and the plugin both write, and a reader never sees half a file
    path = path or PATH
    temp = '%s.%s.tmp' % (path, os.getpid())
    try:
        with open(temp, 'w', encoding='utf-8') as f:
            json.dump(store, f)
        os.replace(temp, path)
    except Exception:
        from .lib import logger
        logger.notice('progress: not saved')

def remove(entry_key, path=None):
    store = load(path)
    if store.pop(entry_key, None) is not None:
        save(store, path)

def stamp(path=None):
    # the store's change time: a window reloads its rows when it moved
    try:
        return str(int(os.path.getmtime(path or PATH) * 1000))
    except OSError:
        return '0'

def now():
    return int(time.time())
