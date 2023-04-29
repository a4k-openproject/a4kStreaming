# -*- coding: utf-8 -*-

import sys
from .lib.goto import with_goto

__action_menu_style = '[COLOR white][B]%s[/B][/COLOR]'

def __get_season_title(core, season, year, episodes):
    season_template = core.kodi.get_setting('general.season_title_template')
    if season_template == '1':
        return 'Season %s (%s)' % (season, year)
    if season_template == '2':
        return 'Season %s' % season
    if season_template == '3':
        return 'Season %s - %s Episodes' % (season, episodes)
    return 'Season %s (%s) - %s Episodes' % (season, year, episodes)

def __get_episode_title(core, season, episode, title):
    season_template = core.kodi.get_setting('general.episode_title_template')
    season_zfill = str(season).zfill(2)
    episode_zfill = str(episode).zfill(2)
    if season_template == '1':
        return '%s. %s' % (episode, title)
    if season_template == '2':
        return 'E%s. %s' % (episode_zfill, title)
    if season_template == '3':
        return '%sx%s. %s' % (season_zfill, episode_zfill, title)
    if season_template == '4':
        return 'S%sE%s. %s' % (season_zfill, episode_zfill, title)
    return '%s' % title

def __handle_request_error(core, params, response=None):
    if not params.silent:
        core.kodi.notification('Something went wrong. Check logs')
    if response:
        core.logger.notice(response.text)

def __check_imdb_auth_config(core, params):
    if core.kodi.get_setting('imdb.at-main') == '':
        if not params.silent:
            core.kodi.notification('Missing IMDb authentication cookies')
            core.utils.end_action(core, True)
        return False
    return True

def __set_wide_image_as_primary(title):
    title_images = title.get('images', None)
    if title_images and len(title_images) > 0:
        if title['primaryImage']:
            title_images.insert(0, title['primaryImage'])
        wide_images = list(filter(lambda v: v['width'] > v['height'] and v.get('type', None) != 'poster', title_images))
        if len(wide_images) > 0:
            title['primaryImage'] = wide_images[0]

def __set_title_contextmenu(core, title, list_item):
    titleType = title['titleType']
    if titleType == 'person':
        return

    trailer = ''
    if title.get('primaryVideos', None) and len(title['primaryVideos']) > 0:
        trailer = title['primaryVideos'][0]

    tvseries = titleType == 'tvSeries'
    has_rating = title.get('userRating', None) is not None
    context_menu_items = [
        ('IMDb: %s rating' % ('Update' if has_rating else 'Set'), 'RunPlugin(%s?action=profile&type=rate&id=%s)' % (core.url, title['id'])),
        ('IMDb: Trailer', 'RunPlugin(%s?action=trailer&id=%s&vi=%s&play=true)' % (core.url, title['id'], trailer)),
        ('IMDb: Cast & Crew', 'ActivateWindow(Videos,%s?action=query&type=browse&id=%s,return)' % (core.url, title['id'])),
    ]

    if titleType != 'tvEpisode':
        context_menu_items.append(
            ('IMDb: More like this', 'ActivateWindow(Videos,%s?action=query&type=more_like_this&id=%s,return)' % (core.url, title['id']))
        )

    if not tvseries:
        if has_rating:
            list_item.setInfo('video', {
                'overlay': 5,
                'playcount': 1
            })
            context_menu_items.append(
                ('IMDb: Mark as unwatched', 'RunPlugin(%s?action=profile&type=mark_as_unwatched&id=%s)' % (core.url, title['id']))
            )
        else:
            context_menu_items.append(
                ('IMDb: Mark as watched', 'RunPlugin(%s?action=profile&type=mark_as_watched&id=%s)' % (core.url, title['id']))
            )

    context_menu_items.extend([
        ('IMDb: Add to watchlist', 'RunPlugin(%s?action=profile&type=watchlist_add&id=%s)' % (core.url, title['id'])),
        ('IMDb: Remove from watchlist', 'RunPlugin(%s?action=profile&type=watchlist_remove&id=%s)' % (core.url, title['id'])),
        ('IMDb: Add to list', 'RunPlugin(%s?action=profile&type=list_add&id=%s)' % (core.url, title['id'])),
        ('IMDb: Remove from list', 'RunPlugin(%s?action=profile&type=list_remove&id=%s)' % (core.url, title['id'])),
    ])

    if not tvseries:
        context_menu_items.extend([
            ('Debrid: Add sources', 'RunPlugin(%s?action=cache_sources&id=%s)' % (core.url, title['id']))
        ])
        if core.kodi.get_bool_setting('general.autoplay'):
            context_menu_items.extend([
                ('Force source select', 'PlayMedia(%s?action=play&id=%s&force_sourceselect=true)' % (core.url, title['id']))
            ])

    list_item.addContextMenuItems(context_menu_items)

def __generate_mutation_query(action, ids, vars=''):
    vars = 'fn(%s) ' % vars if vars else 'fn'
    result = '''
                    '''.join([action % (id, id) for id in ids])
    result = '''
                mutation %s {
                    %s
                }
    ''' % (vars, result)
    return result

def __add_lists(core, data):
    items = []
    for imdb_list in data['lists']:
        if imdb_list['listType'] not in ['TITLES', 'PEOPLE']:
            continue

        titles_label = 'Movie or TV Series from '
        peoples_label = 'Stars, Directors or Writers from '

        items.append({
            'label': imdb_list['name'],
            'type': 'list',
            'info': (titles_label if imdb_list['listType'] == 'TITLES' else peoples_label) + imdb_list['name'],
            'action': 'query',
            'subitems': True,
            'params': {
                'id': imdb_list['id']
            }
        })

    list_items = core.utils.generic_list_items(core, items)
    core.kodi.xbmcplugin.addDirectoryItems(core.handle, list_items, len(list_items))
    core.kodi.xbmcplugin.addSortMethod(core.handle, core.kodi.xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)

def __add_seasons(core, title):
    seasons = {}

    episodes = title['episodes']['episodes']
    episodes = list(filter(lambda ep: ep['releaseDate'], episodes))

    prev_rld = None
    for index, episode in enumerate(episodes):
        try:
            current_rld = episode['releaseDate']
            if prev_rld:
                if current_rld['year'] <= prev_rld['year'] and current_rld['month'] <= prev_rld['month'] and current_rld['day'] <= prev_rld['day']:
                    prev_rld['year'] = current_rld['year']
                    prev_rld['month'] = max(current_rld['month'] - 1, 1)
                    prev_rld['day'] = 1

            prev_rld = current_rld
        except:
            pass

    for _, episode in enumerate(episodes):
        try:
            episode_number = episode['series']
            episode_season = episode_number['seasonNumber']
            episode_number = episode_number['episodeNumber']
            episode_rld = episode['releaseDate']

            if not seasons.get(episode_season, None) and episode_number <= 1:
                seasons[episode_season] = core.utils.DictAsObject({
                    'episodes': 0,
                    'episode_ids': [],
                    'first_episode_year': episode_rld['year'],
                    'year': episode_rld['year'],
                    'month': episode_rld['month'],
                    'day': episode_rld['day'],
                    'year_end': episode_rld['year'],
                    'month_end': min(int(episode_rld['month']) + 1, 12),
                    'day_end': episode_rld['day'],
                    'last_episode': episode,
                })

                if (episode_season - 1) in seasons:
                    prev_season_last_ep_release_date = seasons[episode_season - 1].last_episode['releaseDate']
                    seasons[episode_season].update({
                        'year': prev_season_last_ep_release_date['year'],
                        'month': prev_season_last_ep_release_date['month'],
                        'day': prev_season_last_ep_release_date['day'],
                    })
            else:
                try:
                    d1 = core.datetime(seasons[episode_season]['year'], seasons[episode_season]['month'], seasons[episode_season]['day'])
                    d2 = core.datetime(episode_rld['year'], episode_rld['month'], episode_rld['day'])
                    if d1 > d2:
                        seasons[episode_season]['year'] = d2.year
                        seasons[episode_season]['month'] = d2.month
                        seasons[episode_season]['day'] = d2.day
                except:
                    pass

                try:
                    day_end = seasons[episode_season]['day_end']
                    while True:
                        try:
                            d1 = core.datetime(seasons[episode_season]['year_end'], seasons[episode_season]['month_end'], day_end)
                            seasons[episode_season]['day_end'] = day_end
                            break
                        except: day_end -= 1

                    d2 = core.datetime(episode_rld['year'], episode_rld['month'], episode_rld['day'])
                    if d1 < d2:
                        seasons[episode_season]['year_end'] = d2.year
                        seasons[episode_season]['month_end'] = d2.month
                        seasons[episode_season]['day_end'] = d2.day
                except:
                    pass

                try: seasons[episode_season].last_episode = episode
                except: pass

            seasons[episode_season].episodes += 1
            seasons[episode_season].episode_ids.append(episode['id'])
        except:
            pass

    list_items = []
    for key in seasons:
        season = seasons[key]
        season.key = key
        season.title = __get_season_title(core, key, season.first_episode_year if season.first_episode_year else 'N/A', season.episodes)

        list_item = core.kodi.xbmcgui.ListItem(label=season.title, offscreen=True)
        poster = core.utils.fix_poster_size(title['primaryImage'])
        list_item.setArt({
            'thumb': poster,
            'poster': poster,
        })

        video_meta = {
            'mediatype': 'season',
            'imdbnumber': title['id'],
            'title': season.title,
            'tvshowtitle': season.title,
            'year': season.year,
            'season': key,
            'episode': season.episodes,
            'plot': title.get('plot', None)
        }
        list_item.setInfo('video', video_meta)

        url = '%s?action=query&type=episodes&id=%s&season=%s' % (core.url, title['id'], key)
        if season.year:
            url += '&year=%s' % season.year
        if season.month:
            url += '&month=%s' % season.month
        if season.day:
            url += '&day=%s' % season.day
        if season.year_end:
            url += '&year_end=%s' % season.year_end
        if season.month_end:
            url += '&month_end=%s' % season.month_end
        if season.day_end:
            url += '&day_end=%s' % season.day_end

        context_menu_items = []
        last_episode_has_rating = season.last_episode and season.last_episode.get('userRating', None) is not None
        if last_episode_has_rating:
            list_item.setInfo('video', {
                'overlay': 5,
                'playcount': 1
            })
            context_menu_items.append(
                ('IMDb: Mark as unwatched', 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=profile&type=mark_as_unwatched&id=%s&ids=%s)' % ('Season %s' % season.key, '__'.join(season.episode_ids)))
            )
        else:
            context_menu_items.append(
                ('IMDb: Mark as watched', 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=profile&type=mark_as_watched&id=%s&ids=%s)' % ('Season %s' % season.key, '__'.join(season.episode_ids)))
            )

        list_item.addContextMenuItems(context_menu_items)
        list_item.setContentLookup(False)
        list_items.append((url, list_item, True))

    core.kodi.xbmcplugin.addDirectoryItems(core.handle, list_items, len(list_items))

def __add_episodes(core, title, season):
    seasons = []
    if isinstance(title, list):
        raw_episodes = title
        title = {}
    else:
        raw_episodes = title['episodes']
        if not isinstance(raw_episodes, list):
            seasons = raw_episodes['seasons']
            raw_episodes = raw_episodes['episodes']

    episodes = []
    for episode in raw_episodes:
        if not episode or not episode.get('series', None) or episode['series'].get('seasonNumber', None) != season or episode['series'].get('episodeNumber', None) is None:
            continue

        episodeNumber = episode['series']['episodeNumber']

        if title.get('id', None):
            episode['tvshowid'] = title['id']
        if title.get('titleText', None):
            episode['tvshowtitle'] = title['titleText']
        if title.get('primaryImage', None):
            episode['poster'] = title['primaryImage']
        if title.get('certificate', None):
            episode['certificate'] = title['certificate']
        if title.get('isAdult', None):
            episode['isAdult'] = title['isAdult']
        if title.get('plot', None) and not episode.get('plot', None):
            episode['plot'] = title['plot']
        if title.get('genres', None):
            episode['genres'] = title['genres']
        if title.get('countriesOfOrigin', None):
            episode['countriesOfOrigin'] = title['countriesOfOrigin']
        if title.get('principalCredits', None):
            episode['principalCredits'] = title['principalCredits']
        if title.get('credits', None):
            episode['credits'] = title['credits']
        if title.get('credits', None):
            episode['credits'] = title['credits']
        if len(seasons) > 0:
            episode['no_seasons'] = seasons[-1]

        episode['seasons'] = seasons
        episode['titleText'] = __get_episode_title(core, season, episodeNumber, episode['titleText'])

        if episode.get('releaseDate', None):
            release_date = episode['releaseDate']
            now = core.datetime.now()
            year = release_date.get('year', None)
            month = release_date.get('month', None)
            day = release_date.get('day', None)

            released = False
            if year and month and day and core.date(now.year, now.month, now.day) >= core.date(year, month, day):
                released = True
            if not released:
                episode['titleTextStyled'] = '[COLOR red][I]%s[/I][/COLOR]' % episode['titleText']

        __set_wide_image_as_primary(episode)
        episodes.append(episode)

    return __add_titles(core, episodes, browse=False)

def __add_title(core, title, silent=False):
    items = []

    if title.get('series', None):
        if title['series'].get('series', None):
            series = title['series']['series']
            if series.get('id', None):
                title['tvshowid'] = series['id']
            if series.get('primaryImage', None):
                title['seriesPoster'] = series['primaryImage']
            if series.get('seasons', None):
                title['seasons'] = series['seasons']
            if series.get('nextEpisodeSeasonNumber', None):
                title['nextEpisodeSeasonNumber'] = next(iter(series['nextEpisodeSeasonNumber']), -1)
            if not title.get('countriesOfOrigin', None) and series.get('countriesOfOrigin', None):
                title['countriesOfOrigin'] = series['countriesOfOrigin']

    if not title.get('poster', None) and title.get('seriesPoster', None):
        title['poster'] = title['seriesPoster']
        __set_wide_image_as_primary(title)

    if silent:
        return __add_titles(core, [title], False, silent)

    items.append(title)
    ids = {}

    def add_person(category, credit):
        person = credit
        if credit.get('name', None):
            person = credit['name']
            if credit.get('characters', None):
                person['characters'] = credit['characters']

        if person['id'] in ids:
            return
        ids[person['id']] = True

        items.append({
            'id': person['id'],
            'titleType': 'person',
            'titleText': '(%s) %s' % (category, person['nameText']),
            'primaryImage': person.get('primaryImage', None),
            'plot': ', '.join(person['characters']) if person.get('characters', None) else None
        })

    if title.get('principalCredits', None):
        for credits in title['principalCredits']:
            if credits['category'] == 'Stars':
                for credit in credits['credits']:
                    add_person(credits['category'], credit)

    if title.get('credits', None):
        for credit in title['credits']:
            add_person('Cast', credit)

    if title.get('principalCredits', None):
        for credits in title['principalCredits']:
            if credits['category'] != 'Stars':
                for credit in credits['credits']:
                    add_person(credits['category'], credit)

    return __add_titles(core, items, False)

def __add_titles(core, titles, browse, silent=False):
    list_items = []

    for title in titles:
        titleType = title['titleType']
        if titleType in ['tvMovie', 'tvSpecial', 'video']:
            titleType = 'movie'
        if titleType not in ['movie', 'tvSeries', 'tvEpisode', 'person']:
            continue

        list_item = core.kodi.xbmcgui.ListItem(label=title['titleTextStyled'] if title.get('titleTextStyled', None) else title['titleText'], offscreen=True)

        primary_image = title.get('primaryImage', None)
        poster_image = title.get('poster', None)
        if poster_image:
            poster_image = core.utils.fix_poster_size(poster_image)
            thumb_image = core.utils.fix_thumb_size(primary_image) if primary_image else poster_image
        else:
            poster_image = core.utils.fix_poster_size(primary_image)
            thumb_image = poster_image

        fanart_image = title.get('fanart', None)
        if fanart_image:
            fanart_image = core.utils.fix_fanart_size(fanart_image)
        elif titleType in ['tvEpisode']:
            fanart_image = core.utils.fix_fanart_size(primary_image)

        list_item.setArt({
            'thumb': thumb_image,
            'poster': poster_image,
            'fanart': fanart_image,
        })

        releaseDate = title.get('releaseDate', {})
        mediatypes = {
            'movie': 'movie',
            'tvSeries': 'tvshow',
            'tvEpisode': 'episode',
            'person': 'movie'
        }
        mediatype = mediatypes[titleType]

        overlay = 0 if title.get('userRating', 'unknown') == 'unknown' else (4 if not title.get('userRating', None) else 5)
        if mediatype == 'tvshow':
            overlay = 5 if title.get('tvshow_watched', False) else 0

        video_meta = {
            'mediatype': mediatype,
            'imdbnumber': title['id'],
            'title': title['titleText'],
            'originaltitle': title.get('originalTitleText', title['titleText']),
            'tvshowtitle': title.get('tvshowtitle', title['titleText'] if titleType in ['tvSeries'] else ''),
            'year': title.get('releaseYear', None),
            'premiered': '%s-%s-%s' % (releaseDate['year'], str(releaseDate['month']).zfill(2), str(releaseDate['day']).zfill(2)) if isinstance(releaseDate, dict) and len(releaseDate) == 3 else None,
            'duration': title.get('runtime', None),
            'mpaa': title.get('certificate', None),
            'genre': title.get('genres', None),
            'country': title.get('countriesOfOrigin', None),
            'trailer': '%s?action=trailer&id=%s&vi=%s' % (core.url, title['id'], title['primaryVideos'][0]) if title.get('primaryVideos', None) else None,
            'plot': title.get('plot', None),
            'tagline': next(iter(title.get('taglines', [])), None),
            'overlay': overlay,
            'playcount': 1 if overlay == 5 else (None if overlay == 0 else 0),
            'userrating': title.get('userRating', None)
        }

        if title.get('ratingsSummary', None):
            ratingsSummary = title['ratingsSummary']
            if ratingsSummary.get('aggregateRating', None) and ratingsSummary.get('voteCount', None):
                list_item.setRating("imdb", ratingsSummary['aggregateRating'], ratingsSummary['voteCount'], True)

        if title.get('episodes', None):
            episodes = title['episodes']
            if episodes.get('isOngoing', None) is not None:
                video_meta.update({ 'status': 'Continuing' if episodes['isOngoing'] else 'Ended' })
            if core.utils.safe_list_get(episodes.get('seasons', [None]), -1, None):
                list_item.setProperty('TotalSeasons', str(episodes['seasons'][-1]))
                if not video_meta.get('season', None):
                    video_meta.update({ 'season': episodes['seasons'][-1] })
            if episodes.get('totalEpisodes', None):
                total_episodes = episodes['totalEpisodes']
                list_item.setProperty('WatchedEpisodes', '*')
                list_item.setProperty('UnWatchedEpisodes', '*')
                list_item.setProperty('TotalEpisodes', str(total_episodes))
                list_item.setProperty('NumEpisodes', str(total_episodes))
                video_meta.update({ 'episode': total_episodes })

        if title.get('series', None):
            series = title['series']
            if series.get('series', None):
                if series['series'].get('titleText', None) and not video_meta.get('tvshowtitle', None):
                    video_meta.update({ 'tvshowtitle': series['series']['titleText'] })
            if isinstance(series.get('episodeNumber', None), dict):
                series = series.get('episodeNumber', None)
            if series.get('episodeNumber', None):
                video_meta.update({ 'episode': series['episodeNumber'] })
            if series.get('seasonNumber', None):
                video_meta.update({ 'season': series['seasonNumber'] })

        if title.get('companyCredits', None):
            video_meta.update({
                'studio': [item['company'] for item in title['companyCredits']],
            })

        if title.get('principalCredits', None):
            director = [item['credits'] if item['category'] in ['Director', 'Creator'] else None for item in title['principalCredits']]
            director = next(iter(filter(lambda v: v, director)), None)
            if director is None:
                director = [item['credits'] if item['category'] in ['Directors', 'Creators'] else None for item in title['principalCredits']]
                director = next(iter(filter(lambda v: v, director)), {'nameText': None})

            writers = [item['credits'] if item['category'] == 'Writer' else None for item in title['principalCredits']]
            writers = next(iter(filter(lambda v: v, writers)), None)
            if writers is None:
                writers = [item['credits'] if item['category'] == 'Writers' else None for item in title['principalCredits']]
                writers = next(iter(filter(lambda v: v, writers)), {'nameText': None})

            video_meta.update({
                'director': [item['nameText'] for item in director] if isinstance(director, list) else director['nameText'],
                'writer': [item['nameText'] for item in writers] if isinstance(writers, list) else writers['nameText'],
            })

        list_item.setInfo('video', video_meta)

        cast = []
        if 'principalCredits' in title:
            cast = [item['credits'] if item['category'] == 'Stars' else None for item in title['principalCredits']]
            cast = next(iter(filter(lambda v: v, cast)), [])
        cast_ids = [c.get('name', c)['id'] for c in cast]

        if 'credits' in title and title['credits']:
            for credit in title['credits']:
                credit_id = credit.get('name', credit)['id']
                if credit_id not in cast_ids:
                    cast.append(credit)

        cast_meta = []
        for member in cast:
            characters = member.get('characters', [''])
            cast_meta.append({
                'name': member.get('nameText', member.get('name', {}).get('nameText', None)),
                'role': ' / '.join(characters) if characters else None,
                'thumbnail': core.utils.fix_poster_size(member.get('primaryImage', member.get('name', {}).get('primaryImage', None)))
            })
        list_item.setCast(cast_meta)

        if titleType in ['movie', 'tvEpisode']:
            if browse:
                action = 'query'
                type = 'browse'
            else:
                list_item.setProperty('IsPlayable', 'true')
                action = 'play'
                if title.get('releaseYear', None) is None:
                    type = ''
                else:
                    title_meta = video_meta.copy()
                    title_meta.update({
                        'tvshowid': title.get('tvshowid', None),
                        'seasons': title.get('seasons', None),
                        'is_airing': title_meta.get('season', None) == title.get('nextEpisodeSeasonNumber', -1),
                        'poster': thumb_image if thumb_image else poster_image,
                    })
                    type = core.base64.b64encode(core.json.dumps(title_meta).encode())
                    if core.utils.py3:
                        type = type.decode('ascii')
                    if silent:
                        return type
        elif titleType in ['person']:
            action = 'query'
            type = 'knownfor'
        else:  # tvSeries
            if browse or browse is None:
                action = 'query'
                type = 'seasons'
            else:
                action = 'play'
                type = titleType
                list_item.setProperty('IsPlayable', 'false')

        url = '%s?action=%s&type=%s' % (core.url, action, type)
        if action != 'play' or type == '':
            url += '&id=%s' % title['id']

        list_item.setContentLookup(False)
        __set_title_contextmenu(core, title, list_item)
        list_items.append((url, list_item, action != 'play'))

    core.kodi.xbmcplugin.addDirectoryItems(core.handle, list_items, len(list_items))

def root(core):
    items = [
        {
            'label': 'Trending',
            'action': 'query',
            'type': 'popular',
            'info': 'IMDb\'s latest trending movie or TV series.',
            'subitems': True
        },
        {
            'label': 'Fan Favorites',
            'action': 'query',
            'type': 'fan_picks',
            'info': 'IMDb\'s fan favorites for movie or TV series.',
            'subitems': True
        },
        {
            'label': 'Recommended',
            'action': 'query',
            'type': 'top_picks',
            'info': 'IMDb\'s personalized recommendations for movie or TV series.\n(Requires authentication)',
            'subitems': True
        },
        {
            'label': 'Watchlist',
            'action': 'query',
            'type': 'watchlist',
            'info': 'Your IMDb watchlist for movie or TV series.\n(Requires authentication)',
            'subitems': True
        },
        {
            'label': 'Lists',
            'action': 'query',
            'type': 'lists',
            'info': 'Your IMDb lists for movie or TV series.\n(Requires authentication)',
            'subitems': True
        },
        {
            'label': 'Discover by Year',
            'action': 'years',
            'type': 'root',
            'info': 'Find a movie or TV series from a specific year.',
            'subitems': True
        },
        {
            'label': 'Debrid',
            'action': 'cloud',
            'type': 'root',
            'info': 'Browse debrid files.',
            'subitems': True,
        },
        {
            'label': 'Search...',
            'action': 'search',
            'type': 'input',
            'info': 'Find movie or TV series by name.',
            'subitems': True,
        },
    ]

    list_items = core.utils.generic_list_items(core, items)
    core.kodi.xbmcplugin.addDirectoryItems(core.handle, list_items, len(list_items))

def years(core, params):
    items = []
    now = core.datetime.now().year

    if params.type == 'root':
        start = 1900
        end = now + 1

        while (start < end):
            items.append({
                'label': '%s-%s' % (start, start + 9),
                'type': start,
                'info': 'Between %s and %s' % (start, start + 9),
                'action': 'years',
                'subitems': True
            })
            start += 10
    else:
        start = int(params.type)
        end = start + 10

        while (start < end):
            if start > now:
                break

            items.append({
                'label': '%s' % start,
                'type': 'year',
                'info': 'Movie or TV Series from %s' % start,
                'action': 'query',
                'subitems': True,
                'params': {
                    'target_year': start
                }
            })
            start += 1

    items.reverse()
    list_items = core.utils.generic_list_items(core, items)
    core.kodi.xbmcplugin.addDirectoryItems(core.handle, list_items, len(list_items))

def search(core, params):
    query = params.query
    confirmed = True if query else False
    search = core.cache.get_search()

    if params.type == 'input':
        if search.history:
            selection = core.kodi.xbmcgui.Dialog().select(
                'Search for title or person',
                [__action_menu_style % 'New Search'] + list(map(lambda v: str(v), search.history)),
            )

            confirmed = True
            selection = int(selection)
            if selection > 0:
                query = search.history[selection - 1]
            elif selection == 0:
                confirmed = False

        if not confirmed and not query:
            keyboard = core.kodi.xbmc.Keyboard('', 'Enter part of title or person\'s name')
            keyboard.doModal()
            query = keyboard.getText()
            confirmed = keyboard.isConfirmed()

    if not confirmed or not query:
        core.utils.end_action(core, True)

    if not query:
        return

    if not search.history:
        search.history = []

    search.history.insert(0, query)
    temp_history = set()
    search.history = [item for item in search.history if item not in temp_history and (temp_history.add(item) or True)]

    if len(search.history) > 5:
        search.history.pop()
    core.cache.save_search(search)

    request = {
        'method': 'GET',
        'url': 'https://v2.sg.media-imdb.com/suggestion/%s/%s.json' % (query[:1].lower(), query),
    }

    response = core.request.execute(core, request)
    if response.status_code != 200:
        __handle_request_error(core, params, response)
        return []

    results = core.json.loads(response.content)
    if 'd' not in results or len(results['d']) == 0:
        return []

    items = []
    for result in results['d']:
        titleType = result.get('q', 'person' if result['id'].startswith('nm') else None)
        if not titleType:
            continue

        titleType = titleType.lower()
        types = {
            'tv series': 'tvSeries',
            'tv mini-series': 'tvSeries',
            'tv movie': 'movie',
            'tv special': 'movie',
            'feature': 'movie',
            'video': 'movie',
        }

        if types.get(titleType, None):
            titleType = types[titleType]

        try:
            items.append({
                'id': result['id'],
                'titleType': titleType,
                'titleText': '%s' % result['l'],
                'primaryImage': { 'url': result['i']['imageUrl'], 'width': result['i']['width'], 'height': result['i']['height'] }
            })
        except:
            pass

    __add_titles(core, items, browse=None)
    return items

def cloud(core, params):
    items = []
    video_ext = list(map(lambda v: '.%s' % v.upper(), core.utils.video_containers()))

    if params.type == 'root':
        items.extend([
            {
                'label': 'Premiumize - Files',
                'action': 'cloud',
                'type': 'premiumize_files',
                'info': 'Browse Premiumize files.',
                'subitems': True
            },
            {
                'label': 'Premiumize - Transfers',
                'action': 'cloud',
                'type': 'premiumize_transfers',
                'info': 'See Premiumize transfers.',
                'subitems': True
            },
            {
                'label': 'RealDebrid - Transfers',
                'action': 'cloud',
                'type': 'realdebrid_transfers',
                'info': 'See RealDebrid transfers.',
                'subitems': True
            },
            {
                'label': 'AllDebrid - Transfers',
                'action': 'cloud',
                'type': 'alldebrid_transfers',
                'info': 'See AllDebrid transfers.',
                'subitems': True
            }
        ])

    elif params.type.startswith('premiumize_'):
        apikey = core.utils.get_premiumize_apikey(core)
        if not apikey or apikey == '':
            core.kodi.notification('Missing Premiumize service API key')
            return

        if params.type == 'premiumize_files':
            id = params.id if params.id else ''
            request = core.debrid.premiumize_files(apikey, id)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
                return

            parsed_response = core.json.loads(response.content)

            files = parsed_response.get('content', [])
            for file in files:
                if not file.get('type', None):
                    continue

                if file['type'] == 'file':
                    isvideo = core.os.path.splitext(file['name'])[1].upper() in video_ext
                    subfile = None

                    if not isvideo and not params.force_allfiles:
                        continue

                    filename_without_ext = core.os.path.splitext(file['name'])[0]
                    subfile_ext = ['srt', 'sub', 'ass', 'smi', 'ssa']
                    subfile_names = ['%s.%s' % (filename_without_ext, ext) for ext in subfile_ext]
                    subfiles = [f for f in files if any(subfile_name in f['name'] for subfile_name in subfile_names)]
                    subfile = next(iter(subfiles), None)

                    items.append({
                        'label': file['name'],
                        'subitems': False,
                        'url': file.get('link', file.get('stream_link', None)) if isvideo else '',
                        'subfile': subfile.get('link', None) if subfile else None,
                        'contextmenu': {
                            'Premiumize: Delete': 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=cloud&type=premiumize_file_delete&id=%s)' % file['id']
                        }
                    })
                elif file['type'] == 'folder':
                    items.append({
                        'label': file['name'],
                        'action': 'cloud',
                        'type': 'premiumize_files',
                        'info': '',
                        'subitems': True,
                        'params': {
                            'id': file['id'],
                        },
                        'contextmenu': {
                            'Premiumize: All Files': 'ActivateWindow(Videos,plugin://plugin.video.a4kstreaming/?action=cloud&type=premiumize_files&id=%s&force_allfiles=true,return)' % file['id'],
                            'Premiumize: Delete': 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=cloud&type=premiumize_folder_delete&id=%s)' % file['id'],
                        }
                    })

        elif params.type == 'premiumize_transfers':
            request = core.debrid.premiumize_transfers(apikey)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
                return

            parsed_response = core.json.loads(response.content)

            transfers = parsed_response.get('transfers', [])
            for transfer in transfers:
                isfinished = transfer['status'] == 'finished'
                label = '[%s] %s' % (('Completed' if isfinished else transfer.get('message', ('%s%%' % transfer['progress']))), transfer['name'])

                items.append({
                    'label': label,
                    'action': 'cloud',
                    'type': 'premiumize_files',
                    'info': '',
                    'subitems': isfinished if transfer['file_id'] is None else False,
                    'url': None if isfinished and transfer['file_id'] is None else '',
                    'params': {
                        'id': transfer['folder_id'],
                    },
                    'contextmenu': {
                        'Premiumize: Delete': 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=cloud&type=premiumize_transfer_delete&id=%s)' % transfer['id'],
                        'Premiumize: Clear Finished': 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=cloud&type=premiumize_transfer_clearfinished&id=%s)' % transfer['id']
                    }
                })

        elif params.type == 'premiumize_file_delete':
            request = core.debrid.premiumize_file_delete(apikey, params.id)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
            else:
                core.kodi.notification('PM file removed: %s' % params.id)

            core.utils.end_action(core, True)
            return core.skip_end_of_dir

        elif params.type == 'premiumize_folder_delete':
            request = core.debrid.premiumize_folder_delete(apikey, params.id)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
            else:
                core.kodi.notification('PM folder removed: %s' % params.id)

            core.utils.end_action(core, True)
            return core.skip_end_of_dir

        elif params.type == 'premiumize_transfer_delete':
            request = core.debrid.premiumize_transfer_delete(apikey, params.id)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
            else:
                core.kodi.notification('PM transfer removed: %s' % params.id)

            core.utils.end_action(core, True)
            return core.skip_end_of_dir

        elif params.type == 'premiumize_transfer_clearfinished':
            request = core.debrid.premiumize_transfer_clearfinished(apikey)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
            else:
                core.kodi.notification('PM cleared finished transfers')

            core.utils.end_action(core, True)
            return core.skip_end_of_dir

        else:
            core.not_supported()
            return

    elif params.type.startswith('realdebrid_'):
        apikey = core.utils.get_realdebrid_apikey(core)
        if not apikey or apikey == '':
            core.kodi.notification('Missing RealDebrid service API key')
            return

        auth = core.utils.rd_auth_query_params(core, apikey)
        if params.type == 'realdebrid_transfers':
            request = core.debrid.realdebrid_transfers(auth)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
                return

            parsed_response = core.json.loads(response.content)
            for transfer in parsed_response:
                isfinished = transfer['status'] == 'downloaded'
                label = '[%s] %s' % (('Completed' if isfinished else '%s%%' % transfer['progress']), transfer['filename'])

                items.append({
                    'label': label,
                    'action': 'cloud',
                    'type': 'realdebrid_files',
                    'info': '',
                    'subitems': isfinished,
                    'url': None if isfinished else '',
                    'params': {
                        'id': transfer['id'],
                    },
                    'contextmenu': {
                        'RealDebrid: Delete': 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=cloud&type=realdebrid_delete&id=%s)' % transfer['id']
                    }
                })

        elif params.type == 'realdebrid_files':
            request = core.debrid.realdebrid_files(auth, params.id)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
                return

            parsed_response = core.json.loads(response.content)
            selected_files = []
            for file in parsed_response['files']:
                if file.get('selected', None):
                    selected_files.append(file)

            for i, file in enumerate(selected_files):
                items.append({
                    'label': file['path'].strip('/'),
                    'action': 'cloud',
                    'type': 'realdebrid_file',
                    'info': '',
                    'subitems': False,
                    'params': {
                        'id': parsed_response['links'][i],
                    }
                })

        elif params.type == 'realdebrid_file':
            request = core.debrid.realdebrid_resolve(auth, params.id)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
                return

            parsed_response = core.json.loads(response.content)
            link = parsed_response['download']
            item = core.kodi.xbmcgui.ListItem(path=link, offscreen=True)
            item.setInfo('video', {'mediatype': 'video'})
            core.utils.end_action(core, True, item)
            return core.skip_end_of_dir

        elif params.type == 'realdebrid_delete':
            request = core.debrid.realdebrid_delete(auth, params.id)
            response = core.request.execute(core, request)
            if response.status_code != 204:
                __handle_request_error(core, params, response)
            else:
                core.kodi.notification('RD transfer removed: %s' % params.id)

            core.utils.end_action(core, True)
            return core.skip_end_of_dir

        else:
            core.not_supported()
            return

    elif params.type.startswith('alldebrid_'):
        apikey = core.utils.get_alldebrid_apikey(core)
        if not apikey or apikey == '':
            core.kodi.notification('Missing AllDebrid service API key')
            return

        auth = core.utils.ad_auth_query_params(core, apikey)
        if params.type == 'alldebrid_transfers':
            request = core.debrid.alldebrid_transfers(auth)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
                return

            parsed_response = core.json.loads(response.content)
            for transfer in parsed_response.get('data', parsed_response)['magnets']:
                isfinished = transfer['status'] == 'Ready'
                progress = transfer['downloaded'] / transfer['size'] * 100 if not isfinished else 100
                label = '[%s] %s' % (('Completed' if isfinished else '%s%%' % progress), transfer['filename'])

                items.append({
                    'label': label,
                    'action': 'cloud',
                    'type': 'alldebrid_files',
                    'info': '',
                    'subitems': isfinished,
                    'url': None if isfinished else '',
                    'params': {
                        'id': transfer['id'],
                    },
                    'contextmenu': {
                        'AllDebrid: Delete': 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=cloud&type=alldebrid_delete&id=%s)' % transfer['id']
                    }
                })

        elif params.type == 'alldebrid_files':
            request = core.debrid.alldebrid_files(auth, params.id)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
                return

            parsed_response = core.json.loads(response.content)
            magnet = parsed_response.get('data', parsed_response)['magnets']
            if isinstance(magnet, list):
                magnet = magnet[0]

            for file in magnet['links']:
                items.append({
                    'label': file['filename'],
                    'action': 'cloud',
                    'type': 'alldebrid_file',
                    'info': '',
                    'subitems': False,
                    'params': {
                        'id': file['link'],
                    }
                })

        elif params.type == 'alldebrid_file':
            request = core.debrid.alldebrid_resolve(auth, params.id)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
                return

            parsed_response = core.json.loads(response.content)
            status = parsed_response.get('status', None)
            if status != 'success':
                __handle_request_error(core, params, response)
                return

            link = parsed_response.get('data', parsed_response)['link']
            item = core.kodi.xbmcgui.ListItem(path=link, offscreen=True)
            item.setInfo('video', {'mediatype': 'video'})
            core.utils.end_action(core, True, item)
            return core.skip_end_of_dir

        elif params.type == 'alldebrid_delete':
            request = core.debrid.alldebrid_delete(auth, params.id)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
            else:
                core.kodi.notification('AD transfer removed: %s' % params.id)

            core.utils.end_action(core, True)
            return core.skip_end_of_dir

        else:
            core.not_supported()
            return

    else:
        core.not_supported()
        return

    list_items = core.utils.generic_list_items(core, items)
    core.kodi.xbmcplugin.addDirectoryItems(core.handle, list_items, len(list_items))
    return items

def query(core, params):
    no_auth_required_actions = ['popular', 'year', 'fan_picks', 'more_like_this', 'seasons', 'episodes', 'browse']
    bool_response_actions = ['rate', 'unrate', 'add_to_list', 'remove_from_list', 'add_to_predefined_list', 'remove_from_predefined_list']

    if params.type not in no_auth_required_actions and not __check_imdb_auth_config(core, params):
        return

    now = core.datetime.now()

    releasedOnOrAfter = {}
    if params.year:
        releasedOnOrAfter['year'] = int(params.year)
    if params.month:
        releasedOnOrAfter['month'] = int(params.month)
    if params.day:
        releasedOnOrAfter['day'] = int(params.day)

    releasedOnOrBefore = {}
    if params.year_end:
        releasedOnOrBefore['year'] = int(params.year_end)
    elif params.year:
        releasedOnOrBefore['year'] = int(params.year) + 1
    if params.month_end:
        releasedOnOrBefore['month'] = int(params.month_end)
    if params.day_end:
        releasedOnOrBefore['day'] = int(params.day_end)

    try:
        d1 = core.datetime(releasedOnOrAfter['year'], releasedOnOrAfter['month'], releasedOnOrAfter['day'])
        d2 = core.datetime(releasedOnOrBefore['year'], releasedOnOrBefore['month'], releasedOnOrBefore['day'])
        if d1 > d2:
            releasedOnOrAfter['year'] = d2.year
            releasedOnOrAfter['month'] = 1
            releasedOnOrAfter['day'] = 1
            releasedOnOrBefore['year'] = d1.year
            releasedOnOrBefore['month'] = d1.month
            releasedOnOrBefore['day'] = d1.day
    except:
        pass

    page_size = core.kodi.get_int_setting('general.page_size')
    lists_page_size = core.kodi.get_int_setting('general.lists_page_size')

    requests = {
        'popular': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($limit: Int!, $paginationToken: String, $popularTitlesQueryFilter: PopularTitlesQueryFilter!, $EXTRA_PARAMS) {
                    popularTitles(limit: $limit, paginationToken: $paginationToken, queryFilter: $popularTitlesQueryFilter) {
                        titles {
                            ...Title
                        }
                        paginationToken
                    }
                }
            ''',
            'operationName': 'fn',
            'variables': {
                'limit': page_size,
                'popularTitlesQueryFilter': {
                    'releaseDateRange': {'end': '%s-%s-%s' % (now.year, str(now.month).zfill(2), str(now.day).zfill(2))}
                },
                'paginationToken': params.paginationToken
            }
        }),
        'year': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($limit: Int!, $paginationToken: String, $popularTitlesQueryFilter: PopularTitlesQueryFilter!, $EXTRA_PARAMS) {
                    popularTitles(limit: $limit, paginationToken: $paginationToken, queryFilter: $popularTitlesQueryFilter) {
                        titles {
                            ...Title
                        }
                        paginationToken
                    }
                }
            ''',
            'operationName': 'fn',
            'variables': {
                'limit': page_size,
                'popularTitlesQueryFilter': {
                    'releaseDateRange': {'start': '%s-01-01' % params.target_year, 'end': '%s-12-31' % params.target_year }
                },
                'paginationToken': params.paginationToken
            }
        }),
        'fan_picks': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($first: Int!, $EXTRA_PARAMS) {
                    fanPicksTitles(first: $first) {
                        titles: edges {
                            node {
                                ...Title
                            }
                        }
                    }
                }
            ''',
            'operationName': 'fn',
            'variables': {
                'first': 100,
            }
        }),
        'more_like_this': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($id: ID!, $paginationToken: ID, $first: Int!, $EXTRA_PARAMS) {
                    title(id: $id) {
                        moreLikeThisTitles(first: $first, after: $paginationToken) {
                            titles: edges {
                                node {
                                    ...Title
                                }
                            }
                            pageInfo {
                                hasNextPage
                                endCursor
                            }
                        }
                    }
                }
            ''',
            'operationName': 'fn',
            'variables': {
                'id': params.id,
                'paginationToken': params.paginationToken,
                'first': page_size,
            }
        }),
        'seasons': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($id: ID!, $paginationToken: ID, $EXTRA_PARAMS) {
                    title(id: $id) {
                        %s
                        ...Seasons
                    }
                }
            ''' % ('...TitleFull' if not params.paginationToken else ''),
            'operationName': 'fn',
            'variables': {
                'id': params.id,
                'paginationToken': params.paginationToken,
            }
        }),
        'episodes': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($id: ID!, $episodesFilter: EpisodesFilter!, $EXTRA_PARAMS) {
                    title(id: $id) {
                        ...Episodes
                    }
                }
            ''',
            'operationName': 'fn',
            'variables': {
                'id': params.id,
                'episodesFilter': {
                    'releasedOnOrAfter': releasedOnOrAfter if len(releasedOnOrAfter) > 0 else None,
                    'releasedOnOrBefore': releasedOnOrBefore if len(releasedOnOrBefore) > 0 else None
                }
            }
        }),
        'knownfor': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($id: ID!, $limit: Int!, $paginationToken: ID, $EXTRA_PARAMS) {
                    name(id: $id) {
                        credits(first: $limit, after: $paginationToken, filter: { categories: ["actor", "actress", "director", "writer"], credited: CREDITED_ONLY }) {
                            titles: edges {
                                node {
                                    title {
                                        ...Title
                                        series {
                                            series {
                                                id
                                                titleType {
                                                    id
                                                }
                                                titleText {
                                                    text
                                                }
                                                primaryImage {
                                                    url
                                                    width
                                                    height
                                                    type
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            pageInfo {
                                hasNextPage
                                endCursor
                            }
                        }
                    }
                }
            ''',
            'operationName': 'fn',
            'variables': {
                'id': params.id,
                'limit': page_size,
                'paginationToken': params.paginationToken,
            }
        }),
        'browse': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($id: ID!, $EXTRA_PARAMS) {
                    title(id: $id) {
                        ...TitleFull
                    }
                }
            ''',
            'operationName': 'fn',
            'variables': {
                'id': params.id,
            }
        }),
        'top_picks': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($first: Int!, $paginationToken: ID, $EXTRA_PARAMS) {
                    topPicksTitles(first: $first, after: $paginationToken) {
                        titles: edges {
                            node {
                                ...Title
                            }
                        }
                        pageInfo {
                            hasNextPage
                            endCursor
                        }
                    }
                }
            ''',
            'operationName': 'fn',
            'variables': {
                'first': page_size,
                'paginationToken': params.paginationToken,
            }
        }),
        'ratings': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($ids: [ID!]!, $EXTRA_PARAMS) {
                    titles(ids: $ids) {
                        userRating {
                            value
                        }
                    }
                }
            ''',
            'operationName': 'fn',
            'variables': {
                'ids': params.ids
            }
        }),
        'watchlist': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($first: Int!, $paginationToken: ID, $EXTRA_PARAMS) {
                    predefinedList(classType: WATCH_LIST) {
                        items(first: $first, after: $paginationToken, sort: { by: CREATED_DATE, order: DESC }) {
                            titles: edges {
                                node {
                                    item {
                                        ...Title
                                    }
                                }
                            }
                            pageInfo {
                                hasNextPage
                                endCursor
                            }
                        }
                    }
                }
            ''',
            'operationName': 'fn',
            'variables': {
                'first': lists_page_size,
                'paginationToken': params.paginationToken,
            }
        }),
        'listid': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($classType: ListClassId!) {
                    predefinedList(classType: $classType) {
                        id
                    }
                }
            ''',
            'operationName': 'fn',
            'variables': {
                'classType': params.class_type,
            }
        }),
        'lists': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($first: Int!, $paginationToken: ID, $EXTRA_PARAMS) {
                    lists(first: $first, after: $paginationToken, filter: { classTypes: [LIST] }) {
                        lists: edges {
                            node {
                                id
                                name {
                                    originalText
                                }
                                listType {
                                    id
                                }
                            }
                        }
                        pageInfo {
                            hasNextPage
                            endCursor
                        }
                    }
                }
            ''',
            'operationName': 'fn',
            'variables': {
                'first': page_size,
                'paginationToken': params.paginationToken,
            }
        }),
        'list': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($id: ID!, $first: Int!, $paginationToken: ID, $EXTRA_PARAMS) {
                    list(id: $id) {
                        items(first: $first, after: $paginationToken, sort: { by: CREATED_DATE, order: DESC }) {
                            titles: edges {
                                node {
                                    item {
                                        ...Title
                                    }
                                }
                            }
                            pageInfo {
                                hasNextPage
                                endCursor
                            }
                        }
                    }
                }
            ''',
            'operationName': 'fn',
            'variables': {
                'id': params.id,
                'first': lists_page_size,
                'paginationToken': params.paginationToken,
            }
        }),
        'status': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($classTypes: [ListClassId!]!, $EXTRA_PARAMS) {
                    lists(first: 2, filter: { listElementType: TITLES, classTypes: $classTypes }) {
                        edges {
                            node {
                                %s
                                listClass {
                                    id
                                }
                            }
                        }
                    }
                }
            ''' % ('\n'.join(['%s: isElementInList(itemElementId: "%s")' % (id, id) for id in params.ids])),
            'variables': {
                'classTypes': params.class_types if params.class_types else ['WATCH_LIST']
            }
        }),
        'rate': lambda: core.utils.get_graphql_query({
            'query': __generate_mutation_query(
                '%s: rateTitle(input: { rating: $rating, titleId: "%s" }) { rating { value } }',
                params.titleids if params.titleids else [params.titleid],
                vars='$rating: Int!'
            ),
            'operationName': 'fn',
            'variables': {
                'rating': params.rating,
            }
        }),
        'unrate': lambda: core.utils.get_graphql_query({
            'query': __generate_mutation_query(
                '%s: deleteTitleRating(input: { titleId: "%s" }) { date }',
                params.titleids if params.titleids else [params.titleid]
            ),
            'operationName': 'fn',
            'variables': {}
        }),
        'add_to_list': lambda: core.utils.get_graphql_query({
            'query': __generate_mutation_query(
                '%s: addItemToList(input: { listId: $listId, item: { itemElementId: "%s" } }) { listId }',
                params.titleids if params.titleids else [params.titleid],
                vars='$listId: ID!'
            ),
            'operationName': 'fn',
            'variables': {
                'listId': params.listid,
            }
        }),
        'remove_from_list': lambda: core.utils.get_graphql_query({
            'query': '''
                mutation fn($listId: ID!, $titleId: ID!, $EXTRA_PARAMS) {
                    removeElementFromList(input: { listId: $listId, itemElementId: $titleId }) {
                        listId
                    }
                }
            ''',
            'operationName': 'fn',
            'variables': {
                'listId': params.listid,
                'titleId': params.titleid,
            }
        }),
        'add_to_predefined_list': lambda: core.utils.get_graphql_query({
            'query': __generate_mutation_query(
                '%s: addItemToPredefinedList(input: { classType: $classType, item: { itemElementId: "%s" } }) { listId }',
                params.titleids if params.titleids else [params.titleid],
                vars='$classType: ListClassId!'
            ),
            'operationName': 'fn',
            'variables': {
                'classType': params.class_type,
            }
        }),
        'remove_from_predefined_list': lambda: core.utils.get_graphql_query({
            'query': __generate_mutation_query(
                '%s: removeElementFromPredefinedList(input: { classType: $classType, itemElementId: "%s" }) { listId }',
                params.titleids if params.titleids else [params.titleid],
                vars='$classType: ListClassId!'
            ),
            'operationName': 'fn',
            'variables': {
                'classType': params.class_type,
            }
        }),
    }

    if not requests.get(params.type, None):
        core.not_supported()
        return

    request = requests[params.type]()
    response = core.request.execute(core, request)
    if response.status_code != 200:
        if params.type in bool_response_actions:
            return False
        else:
            __handle_request_error(core, params, response)
            return []

    parsed_response = core.json.loads(response.content)
    if parsed_response.get('errors', None) is not None and isinstance(parsed_response['errors'], list):
        errors = parsed_response['errors']
        try: invalid_creds = params.type not in no_auth_required_actions and 'authenticat' in ' '.join(map(lambda v: v['message'].lower(), errors))
        except: invalid_creds = False

        if invalid_creds:
            if params.type in bool_response_actions:
                return False
            else:
                if not params.silent:
                    core.kodi.notification('Invalid IMDb authentication cookies')
                    core.utils.end_action(core, True)
                return []
        else:
            if 'data' not in parsed_response:
                if not params.retry and len(errors) > 0:
                    params.retry = True
                    return query(core, params)
                else:
                    __handle_request_error(core, params, response)
                    return []
            else:
                core.logger.notice(errors)

    if params.type in bool_response_actions:
        return True

    data = parsed_response['data']
    typeKey = '%sTitles' % params.type
    try:
        if typeKey in data:
            data = data[typeKey]
    except:
        __handle_request_error(core, params, response)
        return []

    data = core.utils.sanitize_response(data)
    if data is None:
        if not params.retry:
            params.retry = True
            return query(core, params)
        else:
            __handle_request_error(core, params)
            return []

    if params.type in ['status', 'listid', 'ratings']:
        return data
    elif params.type == 'lists':
        if params.silent:
            return data['lists']
        core.viewType = core.kodi.get_setting('views.menu')
        core.contentType = 'videos'
        __add_lists(core, data)
    elif params.type == 'seasons':
        episodesData = data.get('episodes', data).get('episodes', data)
        episodes = episodesData.get('edges', [])
        pageInfo = episodesData.get('pageInfo', {})
        hasNextPage = pageInfo.get('hasNextPage', None)
        paginationToken = pageInfo.get('endCursor', None)

        if hasNextPage:
            params_copy = core.utils.DictAsObject(params.copy())
            params_copy.paginationToken = paginationToken
            nextEpisodes = query(core, params_copy)
            episodes = episodes + nextEpisodes

        if params.paginationToken:
            return episodes

        data['episodes']['episodes'] = episodes

        if params.silent:
            return data['episodes']['episodes']

        core.contentType = 'seasons'
        __add_seasons(core, data)
    elif params.type == 'episodes':
        core.contentType = 'episodes'
        __add_episodes(core, data, int(params.season))
    elif params.type == 'browse':
        if data['titleType'] in ['tvEpisode']:
            core.viewType = core.kodi.get_setting('views.episode')
        if data['titleType'] in ['movie', 'tvMovie', 'tvEpisode', 'video']:
            core.contentType = 'movies'
        result = __add_title(core, data, params.silent)
        if params.silent:
            return result
    else:
        core.contentType = 'movies'
        titles = data if isinstance(data, list) else data.get('titles', [])
        if params.type == 'knownfor':
            title_ids = {}
            temp_titles = []
            for title in titles:
                if title['titleType'] == 'tvEpisode':
                    title = title['series']
                if title_ids.get(title['id'], True):
                    title_ids[title['id']] = False
                    temp_titles.append(title)

            titles = list(filter(lambda t: (t['titleType'] in ['movie', 'tvSeries']) and t.get('primaryImage', None), temp_titles))
            pageInfo = data.get('pageInfo', {})
            hasNextPage = pageInfo.get('hasNextPage', None)
            paginationToken = pageInfo.get('endCursor', None)

            if hasNextPage:
                params_copy = core.utils.DictAsObject(params.copy())
                params_copy.paginationToken = paginationToken
                nextTitles = query(core, params_copy)
                titles = titles + nextTitles

            if params.paginationToken:
                return titles

            title_ids = {}
            temp_titles = titles
            titles = []
            for title in temp_titles:
                if title_ids.get(title['id'], True):
                    title_ids[title['id']] = False
                    titles.append(title)

            data['pageInfo'] = None

        __add_titles(core, titles, browse=None)

    if isinstance(data, dict) and (data.get('paginationToken', None) or data.get('pageInfo', None) and data['pageInfo'].get('hasNextPage', False)):
        next_list_item = core.kodi.xbmcgui.ListItem(label='Next', offscreen=True)
        next_list_item.setInfo('video', {'mediatype': 'video'})

        paginationToken = data.get('paginationToken', None)
        if not paginationToken:
            paginationToken = data['pageInfo']['endCursor']

        url = '%s?action=query&type=%s&paginationToken=%s' % (core.url, params.type, paginationToken)
        if params.id:
            url += '&id=%s' % params.id
        if params.target_year:
            url += '&target_year=%s' % params.target_year

        core.kodi.xbmcplugin.addDirectoryItem(core.handle, url, next_list_item, True)

    return data if isinstance(data, list) else [data]

def profile(core, params):
    if not __check_imdb_auth_config(core, params):
        return

    if params.type == 'check_imdb_auth':
        request = {
            'method': 'GET',
            'url': 'https://www.imdb.com/registration/is-user-recognized',
        }
        request.update(core.utils.imdb_auth_request_props())
        response = core.request.execute(core, request)
        if response.status_code != 200:
            core.utils.end_action(core, False)
            core.kodi.notification('Failed to authenticate')
            return

        parsed_response = core.json.loads(response.content)
        if not parsed_response.get('isUserRecognized', False):
            core.utils.end_action(core, False)
            core.kodi.notification('Failed to authenticate')
            return

        core.kodi.notification('Successfully authenticated')

    elif params.type.startswith('watchlist_'):
        params.ids = params.ids.split('__') if params.ids else None
        if params.type == 'watchlist_add':
            result = query(core, core.utils.DictAsObject({
                'type': 'add_to_predefined_list',
                'class_type': 'WATCH_LIST',
                'titleid': params.id,
                'titleids': params.ids,
                'silent': params.silent,
            }))
            if result is True:
                if not params.silent:
                    core.kodi.notification('%s added to watchlist' % params.id)
            else:
                if not params.silent:
                    core.kodi.notification('Failed to add %s to watchlist' % params.id)
                    core.utils.end_action(core, True)
                return

        elif params.type == 'watchlist_remove':
            result = query(core, core.utils.DictAsObject({
                'type': 'remove_from_predefined_list',
                'class_type': 'WATCH_LIST',
                'titleid': params.id,
                'titleids': params.ids,
                'silent': params.silent,
            }))
            if result is True:
                if not params.silent:
                    core.kodi.notification('%s removed from watchlist' % params.id)
            else:
                if not params.silent:
                    core.kodi.notification('Failed to remove %s from watchlist' % params.id)
                    core.utils.end_action(core, True)
                return

        else:
            core.not_supported()
            return

    elif params.type.startswith('mark_'):
        params.ids = params.ids.split('__') if params.ids else None
        if params.type == 'mark_as_watched':
            mark_as_watched_rating = core.kodi.get_int_setting('general.mark_as_watched_rating')
            result = query(core, core.utils.DictAsObject({
                'type': 'rate',
                'rating': mark_as_watched_rating,
                'titleid': params.id,
                'titleids': params.ids,
                'silent': params.silent,
            }))
            if result is True:
                if not params.silent:
                    core.kodi.notification('%s marked as watched' % params.id)
            else:
                if not params.silent:
                    core.kodi.notification('Failed to mark %s as watched' % params.id)
                    core.utils.end_action(core, True)
                return

        elif params.type == 'mark_as_unwatched':
            result = query(core, core.utils.DictAsObject({
                'type': 'unrate',
                'titleid': params.id,
                'titleids': params.ids,
                'silent': params.silent,
            }))
            if result is True:
                if not params.silent:
                    core.kodi.notification('%s marked as unwatched' % params.id)
            else:
                if not params.silent:
                    core.kodi.notification('Failed to mark %s as unwatched' % params.id)
                    core.utils.end_action(core, True)
                return

        else:
            core.not_supported()
            return

    elif params.type == 'rate':
        rating_selection = list(map(lambda v: str(v), range(1, 11)))
        rating_selection.reverse()
        selection = core.kodi.xbmcgui.Dialog().select(
            'IMDb rating',
            ['Remove'] + rating_selection,
        )

        if selection == -1:
            core.utils.end_action(core, True)
            return
        elif selection == 0:
            result = query(core, core.utils.DictAsObject({
                'type': 'unrate',
                'titleid': params.id,
                'silent': params.silent,
            }))
            if result is True:
                if not params.silent:
                    core.kodi.notification('Rating removed for %s' % params.id)
            else:
                if not params.silent:
                    core.kodi.notification('Failed to remove rating for %s' % params.id)
                    core.utils.end_action(core, True)
                return
        else:
            result = query(core, core.utils.DictAsObject({
                'type': 'rate',
                'rating': int(rating_selection[selection - 1]),
                'titleid': params.id,
                'silent': params.silent,
            }))
            if result is True:
                if not params.silent:
                    core.kodi.notification('Rating set for %s' % params.id)
            else:
                if not params.silent:
                    core.kodi.notification('Failed to set rating for %s' % params.id)
                    core.utils.end_action(core, True)
                return

    elif params.type.startswith('list_'):
        params.ids = params.ids.split('__') if params.ids else None
        if params.imdb_list:
            imdb_list = params.imdb_list
        else:
            lists = query(core, core.utils.DictAsObject({ 'type': 'lists', 'silent': True }))
            lists.sort(key=lambda v: v['name'])

            selection = core.kodi.xbmcgui.Dialog().select(
                'IMDb lists',
                [imdb_list['name'] for imdb_list in lists],
            )

            if selection == -1:
                core.utils.end_action(core, True)
                return

            imdb_list = lists[selection]

        if params.type == 'list_add':
            result = query(core, core.utils.DictAsObject({
                'type': 'add_to_list',
                'listid': imdb_list['id'],
                'titleid': params.id,
                'titleids': params.ids,
                'silent': params.silent,
            }))
            if result is True:
                if not params.silent:
                    core.kodi.notification('%s added to %s' % (params.id, imdb_list['name']))
            else:
                if not params.silent:
                    core.kodi.notification('Failed to add %s to %s' % (params.id, imdb_list['name']))
                    core.utils.end_action(core, True)
                return

        elif params.type == 'list_remove':
            result = query(core, core.utils.DictAsObject({
                'type': 'remove_from_list',
                'listid': imdb_list['id'],
                'titleid': params.id,
                'silent': params.silent,
            }))
            if result is True:
                if not params.silent:
                    core.kodi.notification('%s removed from %s' % (params.id, imdb_list['name']))
            else:
                if not params.silent:
                    core.kodi.notification('Failed to remove %s from %s' % (params.id, imdb_list['name']))
                    core.utils.end_action(core, True)
                return

        else:
            core.not_supported()
            return

    else:
        core.not_supported()
        return

    if not params.silent:
        core.utils.end_action(core, True)
    return True

def trailer(core, params):
    if not params.id or not params.vi:
        core.kodi.notification('Trailer not found')
        core.utils.end_action(core, False)
        return

    if params.play == 'true':
        core.kodi.open_busy_dialog()

    request = {
        'method': 'GET',
        'url': 'https://www.imdb.com/video/vi4240746009'
    }

    response = core.request.execute(core, request)
    if response.status_code != 200:
        core.kodi.close_busy_dialog()
        core.utils.end_action(core, False)
        core.logger.notice(response.text)
        core.kodi.notification('Trailer not found')
        return

    __build_id = core.utils.re.search(r'"buildId":"(.*?)"', response.text)
    if __build_id:
        __build_id = __build_id.group(1).strip()
    else:
        core.kodi.close_busy_dialog()
        core.utils.end_action(core, False)
        core.logger.notice(response.text)
        core.kodi.notification('Trailer not found')
        return

    request = {
        'method': 'GET',
        'url': 'https://www.imdb.com/_next/data/%s/video/%s.json' % (__build_id, params.vi),
        'params': {
            'playlistId': params.id,
            'viconst': params.vi,
        },
        'headers': {
            'content-type': 'application/json',
        },
    }

    response = core.request.execute(core, request)
    if response.status_code != 200:
        core.kodi.close_busy_dialog()
        core.utils.end_action(core, False)
        core.logger.notice(response.text)
        core.kodi.notification('Trailer not found')
        return

    parsed_response = core.json.loads(response.content)
    try:
        all = parsed_response['pageProps']['videoPlaybackData']['video']['playbackURLs']
        filtered = filter(lambda v: v['displayName']['value'] != 'AUTO', all)
        trailerUrl = next(iter(filtered), iter(all))['url']
    except:
        core.kodi.close_busy_dialog()
        core.utils.end_action(core, False)
        core.kodi.notification('Trailer not found')
        return []

    item = core.kodi.xbmcgui.ListItem(path=trailerUrl, offscreen=True)
    item.setInfo('video', {'mediatype': 'video'})
    if params.play == 'true':
        core.kodi.close_busy_dialog()
        core.kodi.xbmc.Player().play(item=trailerUrl, listitem=item)
    else:
        core.utils.end_action(core, True, item)

    return [trailerUrl]

def cache_sources(core, params, results=None):
    pm_apikey = core.utils.get_premiumize_apikey(core)
    rd_apikey = core.utils.get_realdebrid_apikey(core)
    ad_apikey = core.utils.get_alldebrid_apikey(core)
    if (not pm_apikey or pm_apikey == '') and (not rd_apikey or rd_apikey == '') and (not ad_apikey or ad_apikey == ''):
        core.kodi.notification('Missing debrid service API key')
        core.utils.end_action(core, True)
        return

    if not results:
        results = play(core, core.utils.DictAsObject({ 'id': params.id, 'cache_sources': True }))

    if not results:
        core.kodi.notification('Something went wrong. Check logs')
        return

    if len(results) == 0:
        core.kodi.notification('No sources found')
        return

    debrid = []
    debrid_map = {
        'Premiumize': 'PM',
        'RealDebrid': 'RD',
        'AllDebrid': 'AD',
    }
    if pm_apikey:
        debrid.append('Premiumize')
    if rd_apikey:
        debrid.append('RealDebrid')
    if ad_apikey:
        debrid.append('AllDebrid')

    if len(debrid) == 1:
        selection = 0
    else:
        selection = core.kodi.xbmcgui.Dialog().select(
            'Choose Debrid',
            debrid,
        )

        if selection == -1:
            return

    debrid = debrid_map[debrid[selection]]
    selection = None

    while (selection != -1):
        results_keys = list(results.keys())
        def sorter():
            return lambda x: (
                -int(results[x].get('seeds', 0)),
                not results[x]['quality'] == '4K',
                not results[x]['quality'] == '1080P',
                not results[x]['quality'] == '720P',
                not results[x]['quality'] == 'SD',
                not results[x]['quality'] == 'CAM',
                -results[x]['size'],
                not results[x]['hdr'] == 'HDR',
                not results[x]['videocodec'] == 'H265',
                'TRUEHD' not in results[x]['audiocodec'],
                'DTS' not in results[x]['audiocodec'],
                'ATMOS' not in results[x]['audiocodec'],
                'HD-MA' not in results[x]['audiocodec'],
                results[x]['release_title'],
            )
        results_keys = sorted(results_keys, key=sorter())

        selection = core.kodi.xbmcgui.Dialog().select(
            'Choose source to cache',
            ['Seeds: %s  |  %s' % (results[key]['seeds'], results[key]['title']) for key in results_keys],
        )

        if selection > -1:
            result = results[results_keys[selection]]

            def cache_to_pm():
                request = core.debrid.premiumize_cache(pm_apikey, result['magnet'])
                response = core.request.execute(core, request)
                if response.status_code != 200:
                    __handle_request_error(core, params, response)
                    return False

                parsed_response = core.json.loads(response.content)
                status = parsed_response.get('status', None)
                error = parsed_response.get('error', None)
                if status != 'success' and (status != 'error' or error != 'duplicate'):
                    __handle_request_error(core, params, response)
                    return False

                if error == 'duplicate':
                    core.kodi.notification('%s transfer is already added' % debrid)
                else:
                    core.kodi.notification('%s transfer created: %s' % (debrid, result['hash']))
                return True

            def cache_to_rd():
                auth = core.utils.rd_auth_query_params(core, rd_apikey)
                request = core.debrid.realdebrid_cache(auth, result['magnet'])
                response = core.request.execute(core, request)
                if response.status_code != 201:
                    __handle_request_error(core, params, response)
                    return False

                parsed_response = core.json.loads(response.content)
                id = parsed_response['id']
                request = core.debrid.realdebrid_select(auth, id)
                response = core.request.execute(core, request)
                if response.status_code != 204:
                    __handle_request_error(core, params, response)
                    return False

                core.kodi.notification('%s transfer created: %s' % (debrid, result['hash']))

                return True

            def cache_to_ad():
                auth = core.utils.ad_auth_query_params(core, ad_apikey)
                request = core.debrid.alldebrid_cache(auth, result['hash'])
                response = core.request.execute(core, request)
                if response.status_code != 200:
                    __handle_request_error(core, params, response)
                    return False

                parsed_response = core.json.loads(response.content)
                status = parsed_response.get('status', None)
                if status != 'success':
                    __handle_request_error(core, params, response)
                    return False

                core.kodi.notification('%s transfer created: %s' % (debrid, result['hash']))

                return True

            def cache():
                if debrid == 'PM':
                    return cache_to_pm()
                elif debrid == 'RD':
                    return cache_to_rd()
                elif debrid == 'AD':
                    return cache_to_ad()

            if not cache():
                continue

            results.pop(results_keys[selection])

@with_goto
def play(core, params):
    general = core.cache.get_general()

    if not params.cache_sources and (general.last_action_time and (core.utils.time_ms() - general.last_action_time) < 2000):
        general.last_action_time = core.utils.time_ms()
        core.cache.save_general(general)
        core.utils.end_action(core, True)
        return
    else:
        general.last_action_time = core.utils.time_ms()
        core.cache.save_general(general)

    if params.type == 'tvSeries':
        core.kodi.notification('Select season instead')
        core.utils.end_action(core, True)
        return

    provider_meta = core.provider_meta(core)
    if not provider_meta.name:
        core.kodi.notification('Provider not installed')
        core.utils.end_action(core, True)
        return

    pm_apikey = core.utils.get_premiumize_apikey(core)
    rd_apikey = core.utils.get_realdebrid_apikey(core)
    ad_apikey = core.utils.get_alldebrid_apikey(core)
    if (not pm_apikey or pm_apikey == '') and (not rd_apikey or rd_apikey == '') and (not ad_apikey or ad_apikey == ''):
        core.kodi.notification('Missing debrid service API key')
        core.utils.end_action(core, True)
        return

    provider_params = core.utils.DictAsObject({})
    provider_params.type = 'search'
    if not params.type:
        if not params.id:
            core.kodi.notification('Missing title id')
            core.utils.end_action(core, True)
            return
        last_title = core.cache.get_last_title()
        if params.id in last_title and last_title[params.id]:
            params.type = last_title[params.id]
        else:
            params.type = query(core, core.utils.DictAsObject({ 'type': 'browse', 'id': params.id, 'silent': True }))
            last_title = {}
            last_title[params.id] = params.type
            core.cache.save_last_title(last_title)

    provider_params.title = core.utils.DictAsObject(core.json.loads(core.base64.b64decode(params.type)))
    if not provider_params.title:
        core.kodi.notification('Something went wrong. Check logs')
        core.utils.end_action(core, True)
        return

    if provider_params.title.tvshowid:
        provider_params.title.tvshowseasonid = '%s_%s' % (provider_params.title.tvshowid, provider_params.title.season)
    provider_params.start_time = core.utils.time_ms()

    last_results = core.cache.get_last_results()
    results = {}

    if not params.cache_sources:
        try:
            if provider_params.title.imdbnumber in last_results:
                results.update(last_results[provider_params.title.imdbnumber]['results'])
                last_results[provider_params.title.imdbnumber]['time'] = core.time.time()
            if provider_params.title.tvshowseasonid in last_results:
                results.update(last_results[provider_params.title.tvshowseasonid]['results'])
                last_results[provider_params.title.tvshowseasonid]['time'] = core.time.time()
            if provider_params.title.tvshowid in last_results:
                results.update(last_results[provider_params.title.tvshowid]['results'])
                last_results[provider_params.title.tvshowid]['time'] = core.time.time()

            core.cache.save_last_results(last_results)
        except:
            if provider_params.title.imdbnumber in last_results:
                last_results.pop(provider_params.title.imdbnumber)
            if provider_params.title.tvshowseasonid in last_results:
                last_results.pop(provider_params.title.tvshowseasonid)
            if provider_params.title.tvshowid in last_results:
                last_results.pop(provider_params.title.tvshowid)

    if len(results) > 0:
        for key in results:
            results[key]['ref'] = provider_params.title
    else:
        provider = core.provider(core, provider_params)

        if params.cache_sources:
            return provider.results

        if len(provider.cached) == 0:
            core.kodi.notification('No sources found')

            if len(provider.results) > 0 and pm_apikey:
                confirmed = core.kodi.xbmcgui.Dialog().yesno(
                    'Uncached sources found',
                    'Found %s uncached sources. Do you want to some of them to debrid?' % len(provider.results),
                    nolabel='No',
                    yeslabel='Yes'
                )

                if confirmed:
                    cache_sources(core, params, provider.results)

            general.last_action_time = core.utils.time_ms()
            core.cache.save_general(general)
            core.utils.end_action(core, True)
            return

        results = provider.cached
        all_results = {}
        season_results = {}
        pack_results = {}
        for key in results:
            result = results[key].copy()
            result.pop('ref')

            all_results[key] = result
            if result['package'] == 'season':
                season_results[key] = result
            elif result['package'] == 'show':
                pack_results[key] = result

        last_results[provider_params.title.imdbnumber] = {
            'time': core.time.time(),
            'results': all_results
        }

        if provider_params.title.tvshowid:
            if len(season_results) > 0:
                last_results[provider_params.title.tvshowseasonid] = {
                    'time': core.time.time(),
                    'results': season_results
                }

            if len(pack_results) > 0:
                last_results[provider_params.title.tvshowid] = {
                    'time': core.time.time(),
                    'results': pack_results
                }

        all_results = None
        season_results = None
        pack_results = None

        while len(last_results) > 10:
            oldest_key = list(last_results.keys())[0]
            for key in last_results:
                if last_results[key]['time'] < last_results[oldest_key]['time']:
                    oldest_key = key
            last_results.pop(oldest_key)

        core.cache.save_last_results(last_results)

    results_keys = list(results.keys())
    def sorter():
        return lambda x: (
            not results[x]['quality'] == '4K',
            not results[x]['quality'] == '1080P',
            not results[x]['quality'] == '720P',
            not results[x]['quality'] == 'SD',
            not results[x]['quality'] == 'CAM',
            -results[x]['size'],
            'DV' not in results[x]['hdr'],
            'HDR10+' not in results[x]['hdr'],
            'HDR10' not in results[x]['hdr'],
            'HDR' not in results[x]['hdr'],
            '12BIT' not in results[x]['hdr'],
            '10BIT' not in results[x]['hdr'],
            '8BIT' not in results[x]['hdr'],
            not results[x]['videocodec'] == 'H265',
            'TRUEHD' not in results[x]['audiocodec'],
            'ATMOS' not in results[x]['audiocodec'],
            'HD-MA' not in results[x]['audiocodec'],
            'DTS' not in results[x]['audiocodec'],
            'DD' not in results[x]['audiocodec'],
            results[x]['release_title'],
        )

    results_keys = sorted(results_keys, key=sorter())

    max_quality = core.kodi.get_int_setting('general.max_quality') + 1
    quality_list = ['4K', '1080P', '720P', 'SD']
    excluded_quality = quality_list[:len(quality_list) - max_quality]
    if len(excluded_quality) > 0:
        results_keys_filtered = [key for key in results_keys if results[key]['quality'] not in excluded_quality]
        if len(results_keys_filtered) > 0:
            results_keys = results_keys_filtered
        else:
            core.kodi.notification('No results for specified quality. Showing all results.')

    if provider_params.title.mediatype == 'movie':
        max_movie_size = core.kodi.get_int_setting('general.max_movie_size')
        results_keys_filtered = [key for key in results_keys if results[key]['size'] <= max_movie_size]
        if len(results_keys_filtered) > 0:
            results_keys = results_keys_filtered
        else:
            core.kodi.notification('No results for specified movie size. Showing all results.')

    if not core.kodi.get_bool_setting('general.dolby_vision_allowed'):
        results_keys = [key for key in results_keys if results[key]['hdr'] != 'DV']
    else:
        results_keys = [key for key in results_keys if not (results[key]['hdr'] == 'DV' and 'mkv' in results[key])]

    result_style = '[LIGHT]%s[/LIGHT]'
    autoplay = core.kodi.get_bool_setting('general.autoplay') and not params.force_sourceselect

    selection = 1
    label .selection  # type: ignore # noqa: F821
    if not autoplay:
        selection = core.kodi.xbmcgui.Dialog().select(
            'Choose source',
            [__action_menu_style % 'New Search'] + [result_style % results[key].get('title_with_debrid', results[key]['title']) for key in results_keys],
            preselect=selection
        )

    if selection == -1:
        general.last_action_time = core.utils.time_ms()
        core.cache.save_general(general)
        core.utils.end_action(core, True)
        return
    elif selection == 0:
        if provider_params.title.imdbnumber in last_results:
            last_results.pop(provider_params.title.imdbnumber)
        if provider_params.title.tvshowseasonid in last_results:
            last_results.pop(provider_params.title.tvshowseasonid)
        if provider_params.title.tvshowid in last_results:
            last_results.pop(provider_params.title.tvshowid)

        core.cache.save_last_results(last_results)
        general.last_action_time = None
        core.cache.save_general(general)
        return play(core, params)
    else:
        selection -= 1

    label .afterselection  # type: ignore # noqa: F821
    result = results[results_keys[selection]]
    video_ext = list(map(lambda v: '.%s' % v.upper(), core.utils.video_containers()))
    size = 1048576 * 100

    def util_filter_episodes(files, propName):
        season_zfill = str(result['ref'].season).zfill(2)
        episode_zfill = str(result['ref'].episode).zfill(2)
        episode_zfill_3 = episode_zfill.zfill(3)
        season = 'S%s' % season_zfill
        episode = 'E%s' % episode_zfill
        episode_0 = 'E0%s' % episode_zfill
        matches = [
            ' %s%s ' % (season, episode),
            ' %s%s ' % (season, episode_0),
            ' %s %s ' % (season, episode),
            ' %s %s ' % (season, episode_0),
            ' %sX%s ' % (season_zfill, episode_zfill),
            ' %sX%s ' % (season_zfill, episode_zfill_3),
            ' %sX%s ' % (season, episode_zfill),
            ' %sX%s ' % (season, episode_zfill_3),
            ' %s%s ' % (result['ref'].season, episode_zfill),
            ' %s%s ' % (result['ref'].season, episode_zfill_3),
            ' %s%s ' % (season_zfill, episode_zfill),
            ' %s%s ' % (season_zfill, episode_zfill_3),
            ' %s %s ' % (result['ref'].season, episode_zfill),
            ' %s %s ' % (result['ref'].season, episode_zfill_3),
            ' %s %s ' % (season_zfill, episode_zfill),
            ' %s %s ' % (season_zfill, episode_zfill_3),
        ]
        return list(filter(lambda file: any(match in core.utils.clean_release_title(file[propName]) for match in matches), files))

    def resolve_pm():
        request = core.debrid.premiumize_resolve(pm_apikey, result['magnet'])
        response = core.request.execute(core, request)
        parsed_response = core.json.loads(response.content)
        return parsed_response.get('content', [])

    def resolve_rd(resolve_files='videos'):
        auth = core.utils.rd_auth_query_params(core, rd_apikey)
        request = core.debrid.realdebrid_cache(auth, result['magnet'])
        response = core.request.execute(core, request)
        parsed_response = core.json.loads(response.content)

        if 'id' not in parsed_response:
            if 'error' in parsed_response and parsed_response['error'] == 'permission_denied':
                core.kodi.notification('RD subscription expired')
            return []

        id = parsed_response['id']
        uri = parsed_response['uri']

        files = []
        try:
            all_files = result['debrid_files'].keys()
            file_ids = [] if resolve_files != 'all' else all_files

            if resolve_files == 'videos':
                title_name = provider_params.title.title.lower()
                has_mt2s = False
                for file_id in result['debrid_files'].keys():
                    file = result['debrid_files'][file_id]
                    ext = core.os.path.splitext(file['filename'])[1].upper()
                    is_video = ext in video_ext
                    if ext == '.M2TS':
                        has_mt2s = True
                        break
                    is_enough_size = int(file['filesize']) > size
                    is_sample = 'sample' not in title_name and 'sample' in file['filename'].lower()
                    if is_video and is_enough_size and not is_sample:
                        file_ids.append(file_id)
                if has_mt2s:
                    fsize = None
                    fid = None
                    for file_id in result['debrid_files'].keys():
                        file = result['debrid_files'][file_id]
                        if fsize is None or fsize < int(file['filesize']):
                            fsize = int(file['filesize'])
                            fid = file_id
                    if fid:
                        file_ids = [fid]

            if result['ref'].mediatype == 'episode' and (len(file_ids) == 0 or resolve_files == 'exact'):
                resolve_files = 'exact'
                episodes = []
                for file_id in result['debrid_files'].keys():
                    episodes.append({
                        'id': file_id,
                        'filename': result['debrid_files'][file_id]['filename']
                    })
                episodes = util_filter_episodes(episodes, 'filename')
                for ep in episodes:
                    file_ids.append(ep['id'])

            if len(file_ids) == 0:
                return files

            request = core.debrid.realdebrid_select(auth, id, files=','.join(file_ids))
            response = core.request.execute(core, request)

            request = {
                'method': 'GET',
                'url': '%s%s' % (uri, auth)
            }
            response = core.request.execute(core, request)
            parsed_response = core.json.loads(response.content)

            if len(parsed_response['links']) == 0:
                if resolve_files == 'videos':
                    request = core.debrid.realdebrid_delete(auth, id)
                    core.request.execute(core, request)
                    if len(file_ids) < len(all_files):
                        return resolve_rd(resolve_files='all')
                    elif result['ref'].mediatype == 'episode':
                        return resolve_rd(resolve_files='exact')
                    else:
                        return files
                elif resolve_files == 'all' and result['ref'].mediatype == 'episode':
                    request = core.debrid.realdebrid_delete(auth, id)
                    core.request.execute(core, request)
                    return resolve_rd(resolve_files='exact')
                else:
                    return files

            selected_files = []
            for file in parsed_response['files']:
                if file.get('selected', None):
                    selected_files.append(file)

            for i, file in enumerate(selected_files):
                if i < len(parsed_response['links']):
                    files.append({
                        'path': file['path'],
                        'size': file['bytes'],
                        'link': parsed_response['links'][i]
                    })

        finally:
            def delete_magnet():
                request = core.debrid.realdebrid_delete(auth, id)
                core.request.execute(core, request)
            core.threading.Thread(target=delete_magnet).start()
        return files

    def resolve_ad():
        auth = core.utils.ad_auth_query_params(core, ad_apikey)
        request = core.debrid.alldebrid_cache(auth, result['hash'])
        response = core.request.execute(core, request)
        parsed_response = core.json.loads(response.content)
        id = parsed_response.get('data', parsed_response)['magnets'][0]['id']
        files = []
        try:
            request = core.debrid.alldebrid_files(auth, id)
            response = core.request.execute(core, request)
            parsed_response = core.json.loads(response.content)
            magnet = parsed_response.get('data', parsed_response)['magnets']
            if isinstance(magnet, list):
                magnet = magnet[0]
            links = magnet['links']
            if not links:
                links = []

            for file in links:
                files.append({
                    'path': file['filename'],
                    'size': file['size'],
                    'link': file['link']
                })

        finally:
            def delete_magnet():
                request = core.debrid.alldebrid_delete(auth, id)
                core.request.execute(core, request)
            core.threading.Thread(target=delete_magnet).start()
        return files

    link = result.get('url', None)
    if link:
        goto .play  # type: ignore # noqa: F821

    files = []
    if result.get('debrid', 'PM') == 'PM':
        try: files = resolve_pm()
        except:
            core.logger.notice(core.traceback.format_exc())
    elif result['debrid'] == 'RD':
        try: files = resolve_rd()
        except:
            core.logger.notice(core.traceback.format_exc())
    elif result['debrid'] == 'AD':
        try: files = resolve_ad()
        except:
            core.logger.notice(core.traceback.format_exc())

    if len(files) > 0:
        for file in files:
            if file.get('path', None):
                file['path'] = core.os.path.basename(file['path']).upper()

        video_files = list(filter(lambda v: core.os.path.splitext(v['path'])[1] in video_ext and int(v['size']) > size, files))
        if len(video_files) > 0:
            files = video_files

        filtered = False
        try:
            if len(files) > 1 and result['ref'].mediatype == 'episode':
                episodes = util_filter_episodes(files, 'path')
                if len(episodes) > 0:
                    files = episodes
                    filtered = True
        except Exception as e:
            core.logger.notice(e)

        if len(files) > 1 or (len(files) == 1 and not filtered and result['package'] in ['show', 'season']):
            file_results = {}
            for file in files:
                file_result = {
                    'ref': core.utils.DictAsObject(result['ref']),
                    'release_title': core.os.path.basename(file['path']),
                    'size': round(float(file['size']) / 1024 / 1024 / 1024, 1),
                    'link': file.get('link', file.get('stream_link', None)),
                }
                core.utils.cleanup_result(file_result, no_meta=True)
                file_results[file_result['title']] = file_result

            file_result_keys = list(file_results.keys())
            file_result_keys.sort()
            file_result_keys = sorted(file_result_keys, key=lambda v: file_results[v]['release_title'])

            file_selection = core.kodi.xbmcgui.Dialog().select(
                'Choose file',
                [result_style % key for key in file_result_keys],
            )

            if file_selection > -1:
                file = file_results[file_result_keys[file_selection]]
                link = file['link']
            elif file_selection == -1:
                selection += 1
                goto .selection  # type: ignore # noqa: F821

        elif len(files) == 1:
            file = files[0]
            link = file.get('link', file.get('stream_link', None))

    if not link:
        selection += 1
        if selection < len(results_keys) and autoplay:
            goto .afterselection  # type: ignore # noqa: F821
        else:
            core.kodi.notification('Failed to resolve debrid')
            autoplay = False
            goto .selection  # type: ignore # noqa: F821

    if result.get('debrid', 'PM') == 'RD':
        try:
            auth = core.utils.rd_auth_query_params(core, rd_apikey)
            request = core.debrid.realdebrid_resolve(auth, link)
            response = core.request.execute(core, request)
            parsed_response = core.json.loads(response.content)
            link = parsed_response['download']
        except:
            core.logger.notice(core.traceback.format_exc())

    elif result.get('debrid', 'PM') == 'AD':
        try:
            auth = core.utils.ad_auth_query_params(core, ad_apikey)
            request = core.debrid.alldebrid_resolve(auth, link)
            response = core.request.execute(core, request)
            parsed_response = core.json.loads(response.content)
            link = parsed_response['data']['link']
        except:
            core.logger.notice(core.traceback.format_exc())

    label .play  # type: ignore # noqa: F821
    item = core.kodi.xbmcgui.ListItem(path=link, offscreen=True)
    item.setProperty('IsPlayable', 'true')
    item.setContentLookup(False)

    video_meta = provider_params.title.copy()
    video_meta.pop('tvshowseasonid', None)
    video_meta.pop('tvshowid', None)
    video_meta.pop('seasons', None)
    video_meta.pop('is_airing', None)
    video_meta.pop('poster', None)

    if provider_params.title.poster:
        item.setArt({ 'poster': provider_params.title.poster })

    item.setInfo('video', video_meta)
    item.addStreamInfo('video', { 'codec': result['videocodec'], 'duration': result['ref'].duration })

    core.utils.end_action(core, True, item)
    return link
