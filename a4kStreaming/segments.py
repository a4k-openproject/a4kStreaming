# -*- coding: utf-8 -*-
# Intro, recap and credits times for a series episode, from public community timestamp databases, and the player's
# decisions on them: auto-skip, the skip button and the next episode countdown. No Kodi imports: the service feeds Skip
# the player position on a short tick and draws what it answers (ui/skip.py). HTTP goes through get_json.

import json
import math
import os
from concurrent.futures import ThreadPoolExecutor

TIMEOUT = 3  # seconds per source; a slow source is no data
AGREE = 3  # seconds two databases may differ on a start or an end and still vouch for each other
HIT_TTL = 7 * 86400
MISS_TTL = 86400
ERR_TTL = 600  # a source errored: the answer is incomplete, so it is asked again soon
COUNTDOWN = 10.0
LENGTH_TOLERANCE = 20.0  # the measured episode length may differ from the playing duration by this much
START_ANCHOR = 1.0  # a segment starting this close to 0 is skipped whatever the length

ANIME_URL = ('https://api.aniskip.com/v2/skip-times/%s/%s'
             '?types=op&types=recap&types=ed&types=mixed-op&types=mixed-ed&episodeLength=0')
INTRODB_URL = 'https://api.introdb.app/segments?%s'
THEINTRODB_URL = 'https://api.theintrodb.org/v4/media?%s'

MAP_PATH = os.path.join(os.path.dirname(__file__), 'anime_map.json')  # scripts/anime_map.py writes it
EMPTY = {'intro': None, 'recap': None, 'credits': None, 'length': None}

def get_json(url):
    # the parsed body; None when the source answered nothing (a 404); raises on a timeout, a 5xx, a 429 or bad JSON
    import requests
    response = requests.get(url, timeout=TIMEOUT, headers={'Accept': 'application/json', 'User-Agent': 'a4kStreaming'})
    if response.status_code == 429 or response.status_code >= 500:
        raise IOError('upstream %s' % response.status_code)
    return response.json() if response.ok else None

def num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)

__anime_map = []

def anime_map():
    if not __anime_map:
        try:
            with open(MAP_PATH) as f:
                __anime_map.append(json.load(f))
        except Exception:
            __anime_map.append({})
    return __anime_map[0]

def mal_for(imdb, season, mapping=None):
    # the single MAL id of this IMDb season, tvdb season first and tmdb as the fallback; None when absent or split
    rows = (anime_map() if mapping is None else mapping).get(imdb, [])
    ids = [row[0] for row in rows if row[1] == season] or [row[0] for row in rows if row[2] == season]
    # ponytail: one IMDb season split over several MAL ids skips the anime database (the episode offset per part is
    # unknown); map episode ranges per part if the TV databases turn out thin for those seasons
    return ids[0] if len(set(ids)) == 1 else None

def anime(data):
    out = dict(EMPTY)
    results = data.get('results') if isinstance(data, dict) else None
    for result in results if isinstance(results, list) else []:
        interval = result.get('interval') or {}
        start, end = num(interval.get('startTime')), num(interval.get('endTime'))
        if start is None or end is None:
            continue
        kind = result.get('skipType')
        if kind in ('op', 'mixed-op') and not out['intro']:
            out['intro'] = {'start': start, 'end': end, 'confident': True}
        elif kind == 'recap' and not out['recap']:
            out['recap'] = {'start': start, 'end': end, 'confident': True}
        elif kind in ('ed', 'mixed-ed') and not out['credits']:
            out['credits'] = {'start': start, 'confident': True}
        else:
            continue
        out['length'] = out['length'] or num(result.get('episodeLength')) or None
    return out if out['intro'] or out['recap'] or out['credits'] else None

def introdb_segment(segment):
    # end None = open-ended (credits); count only introdb has
    start = num(segment.get('start_sec')) if isinstance(segment, dict) else None
    if start is None:
        return None
    return {'start': start, 'end': num(segment.get('end_sec')), 'count': num(segment.get('submission_count')) or 0}

def theintrodb_segments(segments):
    out = []
    for segment in segments if isinstance(segments, list) else []:
        if not isinstance(segment, dict):
            continue
        start, end = (num(segment.get('start_ms')) or 0) / 1000, num(segment.get('end_ms'))
        end = None if end is None else end / 1000
        if end is None or end > start:
            out.append({'start': start, 'end': end})
    return out

def merge(a, bs):
    # one segment from both TV databases: theintrodb's candidate closest to introdb's, then the confident rule
    b = min(bs, key=lambda s: abs(s['start'] - a['start'])) if a and bs else (bs[0] if bs else None)
    agree = bool(a and b) and abs(a['start'] - b['start']) <= AGREE and (
        a['end'] is None or b['end'] is None or abs(a['end'] - b['end']) <= AGREE)
    # introdb open-ended but theintrodb complete: theintrodb is the base
    base = b if a and a['end'] is None and b and b['end'] is not None else (a or b)
    if not base:
        return None
    # introdb's submission count vouches only for introdb's own segment
    return {'start': base['start'], 'end': base['end'], 'confident': agree or (base is a and a['count'] >= 3)}

def tv(introdb, theintrodb):
    introdb = introdb if isinstance(introdb, dict) else {}
    theintrodb = theintrodb if isinstance(theintrodb, dict) else {}

    def segment(kind, other):
        s = merge(introdb_segment(introdb.get(kind)), theintrodb_segments(theintrodb.get(other)))
        return s if s and s['end'] is not None and s['end'] > s['start'] else None

    credits = merge(introdb_segment(introdb.get('outro')), theintrodb_segments(theintrodb.get('credits')))
    return {
        'intro': segment('intro', 'intro'),
        'recap': segment('recap', 'recap'),
        'credits': credits and {'start': credits['start'], 'confident': credits['confident']},
        'length': None,
    }

def fetch(imdb, season, episode, get=get_json, mapping=None):
    # (segments, ttl): the anime database for a mapped anime season, else (or on a miss) both TV databases at once
    failed = []

    def ask(url):
        try:
            return get(url)
        except Exception:
            failed.append(url)
            return None

    mal = mal_for(imdb, season, mapping)
    body = anime(ask(ANIME_URL % (mal, episode))) if mal is not None else None
    if not body:
        query = 'imdb_id=%s&season=%s&episode=%s' % (imdb, season, episode)
        with ThreadPoolExecutor(2) as pool:
            a, b = pool.map(ask, [INTRODB_URL % query, THEINTRODB_URL % query])
        body = tv(a, b)
    empty = not (body['intro'] or body['recap'] or body['credits'])
    return body, ERR_TTL if failed else MISS_TTL if empty else HIT_TTL

def lookup(db, imdb, season, episode, get=get_json, mapping=None):
    # fetch() through the add-on's disk cache (core.db); never raises
    key = 'segments_%s_%s_%s' % (imdb, season, episode)
    try:
        cached, age = db.get(key), db.age(key)
        if cached and age is not None:
            cached = json.loads(cached)
            if age < cached['ttl']:
                return cached['body']
    except Exception:
        pass
    try:
        body, ttl = fetch(imdb, season, episode, get, mapping)
    except Exception:
        return dict(EMPTY)
    try: db.set(key, json.dumps({'ttl': ttl, 'body': body}).encode())
    except Exception: pass
    return body

def next_episode(episodes, season, episode, today):
    # the id of the first released episode after season x episode in a series' episode list (query type=seasons)
    later = []
    for ep in episodes or []:
        series, date = (ep or {}).get('series') or {}, (ep or {}).get('releaseDate') or {}
        s, e = series.get('seasonNumber'), series.get('episodeNumber')
        try:
            released = (date['year'], date['month'], date['day']) <= (today.year, today.month, today.day)
        except Exception:
            released = False
        if isinstance(s, int) and isinstance(e, int) and s > 0 and released and (s, e) > (season, episode):
            later.append((s, e, ep.get('id')))
    return min(later)[2] if later else None

class Tick(object):
    # what the player shows after one tick
    seek_to = None  # auto-skip: seek here now (seconds)
    toast = None  # 'intro' / 'recap': the short "Skipped ..." notice after an auto-skip
    button = None  # 'intro' / 'recap' / 'next': the button on screen, None for none
    button_seek = None  # where the intro or recap button seeks
    countdown = None  # whole seconds left on the next episode countdown, None when none runs
    fire_next = False  # the countdown ran out on this tick: play the next episode (answered once)

class Skip(object):
    # one per playback: the once-per-segment auto-skip memory and the countdown live here.
    # segments is lookup()'s answer; modes maps intro/recap/credits to auto, button or off.

    def __init__(self, segments, modes, has_next):
        self.segments = []
        for kind in ('recap', 'intro'):
            s = segments.get(kind)
            if s and num(s.get('start')) is not None and num(s.get('end')) is not None and s['end'] > s['start']:
                self.segments.append({'kind': kind, 'start': s['start'], 'end': s['end'], 'confident': bool(s.get('confident')),
                                      'mode': modes.get(kind, 'auto'), 'skipped': False})
        credits = segments.get('credits') or {}
        self.credits = num(credits.get('start'))
        self.credits_mode = modes.get('credits', 'auto')
        self.has_next = has_next
        self.length = num(segments.get('length'))
        self.countdown_start = None
        self.last_tick = None
        self.cancelled = False
        self.fired = False

    def length_matches(self, duration):
        return self.length is None or (duration > 0 and abs(self.length - duration) <= LENGTH_TOLERANCE)

    def tick(self, pos, duration, playing, now):
        # duration <= 0 is unknown; playing False holds the countdown, so a paused credits screen never moves on
        t = Tick()
        since_last = 0 if self.last_tick is None else now - self.last_tick
        self.last_tick = now
        # out of the credits on every path, a segment hit included: a later entry counts the full 10 s again
        if self.credits is None or pos < self.credits:
            self.countdown_start = None
        for s in self.segments:
            if s['mode'] == 'off' or pos < s['start'] or pos >= s['end'] - 1:
                continue
            if (not s['skipped'] and s['mode'] == 'auto' and s['confident']
                    and (s['start'] <= START_ANCHOR or self.length_matches(duration))):
                s['skipped'] = True
                t.seek_to, t.toast = s['end'], s['kind']
            else:
                t.button, t.button_seek = s['kind'], s['end']
            return t
        if not self.has_next or self.credits is None or self.credits_mode == 'off' or pos < self.credits:
            return t
        t.button = 'next'
        if self.credits_mode == 'auto' and not self.cancelled and not self.fired:
            if self.countdown_start is None:
                self.countdown_start = now
            elif not playing:
                self.countdown_start += since_last
            left = COUNTDOWN - (now - self.countdown_start)
            if left <= 0:
                self.fired = t.fire_next = True
                left = 0
            t.countdown = int(math.ceil(left))
        return t

    def countdown_active(self):
        return self.countdown_start is not None and not self.cancelled and not self.fired

    def next_on_natural_end(self):
        # the end reached with the auto countdown running counts as Next episode
        return self.countdown_active()

    def cancel_countdown(self):
        # any key or Back: the countdown stops for this playback, the button stays
        self.cancelled = True
