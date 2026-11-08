# -*- coding: utf-8 -*-
# Regenerates a4kStreaming/anime_map.json: IMDb id -> [[MAL id, tvdb season, tmdb season], ...] for TV and ONA anime,
# read by a4kStreaming/segments.py to ask the anime timestamp database by MAL id.
# Usage: python scripts/anime_map.py [path or URL of anime-list-full.json]

import json
import os
import sys
from urllib.request import urlopen

SOURCE = 'https://raw.githubusercontent.com/Fribb/anime-lists/master/anime-list-full.json'
OUT = os.path.join(os.path.dirname(__file__), '..', 'a4kStreaming', 'anime_map.json')

def build(entries):
    mapping = {}
    for entry in entries:
        if entry.get('type') not in ('TV', 'ONA') or not isinstance(entry.get('imdb_id'), list) or not entry.get('mal_id'):
            continue
        season = entry.get('season') or {}
        row = [entry['mal_id'], season.get('tvdb'), season.get('tmdb')]
        for imdb_id in entry['imdb_id']:
            mapping.setdefault(imdb_id, []).append(row)
    return mapping

if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else SOURCE
    if src.startswith('http'):
        entries = json.loads(urlopen(src).read())
    else:
        with open(src) as f:
            entries = json.load(f)
    mapping = build(entries)
    with open(OUT, 'w') as f:
        json.dump(mapping, f, separators=(',', ':'), sort_keys=True)
        f.write('\n')
    print('%s imdb ids -> %s' % (len(mapping), os.path.normpath(OUT)))
