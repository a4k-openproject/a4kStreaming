__action_menu_style = '[COLOR white][B]%s[/B][/COLOR]'

def __handle_request_error(core, params, response):
    if not params.silent:
        core.kodi.notification('Something went wrong. Check logs')
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
        wide_images = list(filter(lambda v: v['width'] > v['height'], title_images))
        if len(wide_images) > 0:
            title['primaryImage'] = wide_images[0]

def __set_titles_contextmenu(title, list_item):
    tvseries = title['titleType'] == 'tvSeries'
    has_rating = title.get('userRating', None) is not None
    context_menu_items = [
        ('IMDb: %s rating' % ('Update' if has_rating else 'Set'), 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=profile&type=rate&id=%s)' % title['id'])
    ]

    if not tvseries:
        if has_rating:
            list_item.setInfo('video', {
                'overlay': 5,
                'playcount': 1
            })
            context_menu_items.append(
                ('IMDb: Mark as unwatched', 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=profile&type=mark_as_unwatched&id=%s)' % title['id'])
            )
        else:
            context_menu_items.append(
                ('IMDb: Mark as watched', 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=profile&type=mark_as_watched&id=%s)' % title['id'])
            )

    context_menu_items.extend([
        ('IMDb: Add to watchlist', 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=profile&type=watchlist_add&id=%s)' % title['id']),
        ('IMDb: Remove from watchlist', 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=profile&type=watchlist_remove&id=%s)' % title['id']),
        ('IMDb: Add to list', 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=profile&type=list_add&id=%s)' % title['id']),
        ('IMDb: Remove from list', 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=profile&type=list_remove&id=%s)' % title['id']),
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

    for index, episode in enumerate(episodes):
        try:
            episodeNumber = episode['series']
            episodeSeason = episodeNumber['seasonNumber']
            episodeNumber = episodeNumber['episodeNumber']
            episodeReleaseDate = episode['releaseDate']

            if not seasons.get(episodeSeason, None) and episodeNumber == 1:
                seasons[episodeSeason] = core.utils.DictAsObject({
                    'episodes': 0,
                    'episode_ids': [],
                    'year': episodeReleaseDate['year'],
                    'month': episodeReleaseDate['month'],
                    'day': episodeReleaseDate['day'],
                })

            seasons[episodeSeason].episodes += 1
            seasons[episodeSeason].episode_ids.append(episode['id'])
            seasons[episodeSeason].last_episode = episode

            if index > 0:
                seasonToUpdate = None
                releaseDate = None
                if episodes[index - 1]['series']['seasonNumber'] + 1 == episodeSeason:
                    seasonToUpdate = episodeSeason - 1
                    releaseDate = episodes[index - 1]['releaseDate']

                if index + 1 == len(episodes):
                    seasonToUpdate = episodeSeason
                    releaseDate = episodeReleaseDate

                if seasonToUpdate:
                    seasons[seasonToUpdate].update({
                        'year_end': releaseDate['year'],
                        'month_end': releaseDate['month'],
                        'day_end': releaseDate['day'],
                    })
        except:
            pass

    list_items = []
    for key in seasons:
        season = seasons[key]
        season.key = key
        season.title = 'Season %s  (%s) - %s Episodes' % (key, season.year if season.year else 'N/A', season.episodes)

        list_item = core.kodi.xbmcgui.ListItem(label=season.title)
        list_item.setArt({
            'poster': core.utils.fix_poster_size(title['primaryImage']),
        })

        video_meta = {
            'mediatype': 'season',
            'imdbnumber': title['id'],
            'title': season.title,
            'tvshowtitle': season.title,
            'year': season.year,
            'season': key,
            'episode': season.episodes
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
        last_episode_has_rating = season.last_episode.get('userRating', None) is not None
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

    __add_titles(core, [title], False)
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
        if not episode or not episode.get('series', None) or episode['series'].get('seasonNumber', None) != season:
            continue

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

    return __add_titles(core, episodes, True)

def __add_title(core, title):
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

    if not title.get('poster', None) and title.get('seriesPoster', None):
        title['poster'] = title['seriesPoster']

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

def __add_titles(core, titles, browse):
    list_items = []

    for title in titles:
        titleType = title['titleType']
        if titleType in ['tvMovie', 'video']:
            titleType = 'movie'
        if titleType not in ['movie', 'tvSeries', 'tvEpisode', 'person']:
            continue

        list_item = core.kodi.xbmcgui.ListItem(label=title['titleTextStyled'] if title.get('titleTextStyled', None) else title['titleText'])

        primary_image = title.get('primaryImage', None)
        poster_image = title.get('poster', None)
        fanart_image = title.get('fanart', None)
        if poster_image:
            thumb = core.utils.fix_thumb_size(primary_image) if primary_image else core.utils.fix_poster_size(poster_image)
            poster = core.utils.fix_poster_size(poster_image)
            list_item.setArt({
                'thumb': thumb,
                'poster': poster,
                'fanart': core.utils.fix_fanart_size(primary_image) if primary_image else None,
            })
        else:
            thumb = None
            poster = core.utils.fix_poster_size(primary_image)
            list_item.setArt({
                'poster': core.utils.fix_poster_size(primary_image),
                'fanart': core.utils.fix_fanart_size(fanart_image) if fanart_image else None,
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
            overlay = 0

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
            'trailer': '%s?action=trailer&id=%s' % (core.url, title['primaryVideos'][0]) if title.get('primaryVideos', None) else None,
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
                list_item.setProperty('WatchedEpisodes', '*')
                list_item.setProperty('UnWatchedEpisodes', '*')
                list_item.setProperty('TotalEpisodes', str(episodes['totalEpisodes']))
                list_item.setProperty('NumEpisodes', str(episodes['totalEpisodes']))
                video_meta.update({ 'episode': episodes['totalEpisodes'] })

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
                title_meta = video_meta.copy()
                title_meta.update({
                    'tvshowid': title.get('tvshowid', None),
                    'seasons': title.get('seasons', None),
                    'poster': thumb if thumb else poster,
                })
                type = core.base64.b64encode(core.json.dumps(title_meta).encode())
        elif titleType in ['person']:
            action = 'query'
            type = 'person'
        else:  # tvSeries
            if browse:
                action = 'query'
                type = 'seasons'
            else:
                action = 'play'
                type = titleType
                list_item.setProperty('IsPlayable', 'false')

        url = '%s?action=%s&type=%s' % (core.url, action, type)
        if action != 'play':
            url += '&id=%s' % title['id']

        list_item.setContentLookup(False)
        __set_titles_contextmenu(title, list_item)
        list_items.append((url, list_item, action != 'play'))

    core.kodi.xbmcplugin.addDirectoryItems(core.handle, list_items, len(list_items))

def root(core):
    items = [
        {
            'label': 'Trending',
            'type': 'popular',
            'info': 'IMDb\'s latest trending movie or TV series.',
            'action': 'query',
            'subitems': True
        },
        {
            'label': 'Fan Favorites',
            'type': 'fan_picks',
            'info': 'IMDb\'s fan favorites for movie or TV series.',
            'action': 'query',
            'subitems': True
        },
        {
            'label': 'Recommended',
            'type': 'top_picks',
            'info': 'IMDb\'s personalized recommendations for movie or TV series.\n(Requires authentication)',
            'action': 'query',
            'subitems': True
        },
        {
            'label': 'Watchlist',
            'type': 'watchlist',
            'info': 'Your IMDb watchlist for movie or TV series.\n(Requires authentication)',
            'action': 'query',
            'subitems': True
        },
        {
            'label': 'Lists',
            'type': 'lists',
            'info': 'Your IMDb lists for movie or TV series.\n(Requires authentication)',
            'action': 'query',
            'subitems': True
        },
        {
            'label': 'Discover by Year',
            'type': 'root',
            'info': 'Find a movie or TV series from a specific year.',
            'action': 'years',
            'subitems': True
        },
        {
            'label': 'Search...',
            'type': 'input',
            'info': 'Find movie or TV series by name.',
            'action': 'search',
            'subitems': True,
        }
    ]

    list_items = core.utils.generic_list_items(core, items)
    core.kodi.xbmcplugin.addDirectoryItems(core.handle, list_items, len(list_items))

def years(core, params):
    items = []
    now = core.datetime.now().year

    if params.type == 'root':
        start = 1900
        end = now + 1

        while(start < end):
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

        while(start < end):
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
        'url': 'https://v2.sg.media-imdb.com/suggestion/%s/%s.json' % (query[:1], query),
    }

    response = core.request.execute(core, request)
    if response.status_code != 200:
        __handle_request_error(core, params, response)
        return []

    results = core.json.loads(response.text)
    if len(results['d']) == 0:
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

    __add_titles(core, items, browse=True)
    return items

def query(core, params):
    no_auth_required_actions = ['popular', 'year', 'fan_picks', 'seasons', 'episodes', 'browse']
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

    parsed_response = core.json.loads(response.text)
    if parsed_response.get('errors', None) is not None and isinstance(parsed_response['errors'], list):
        errors = parsed_response['errors']
        try: invalid_creds = params.type in ['top_picks', 'watchlist'] and 'authenticat' in ' '.join(map(lambda v: v['message'].lower(), errors))
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
                if not params.retry and len(errors) > 0 and 'The channel was closed before the send operation began' in errors[0]['message']:
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
    if typeKey in data:
        data = data[typeKey]

    data = core.utils.sanitize_response(data)

    if params.type in ['status', 'listid', 'ratings']:
        return data
    elif params.type == 'lists':
        if params.silent:
            return data['lists']
        core.viewType = core.kodi.get_setting('views.menu')
        core.kodi.xbmcplugin.setContent(core.handle, 'videos')
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

        core.kodi.xbmcplugin.setContent(core.handle, 'seasons')
        __add_seasons(core, data)
    elif params.type == 'episodes':
        core.kodi.xbmcplugin.setContent(core.handle, 'episodes')
        __add_episodes(core, data, int(params.season))
    elif params.type == 'browse':
        if data['titleType'] in ['tvEpisode']:
            core.viewType = core.kodi.get_setting('views.episode')
        if data['titleType'] in ['movie', 'tvMovie', 'tvEpisode', 'video']:
            core.kodi.xbmcplugin.setContent(core.handle, 'movies')
        __add_title(core, data)
    else:
        core.kodi.xbmcplugin.setContent(core.handle, 'movies')
        __add_titles(core, data if isinstance(data, list) else data.get('titles', []), browse=True)

    if isinstance(data, dict) and (data.get('paginationToken', None) or data.get('pageInfo', None) and data['pageInfo'].get('hasNextPage', False)):
        next_list_item = core.kodi.xbmcgui.ListItem(label='Next')
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

    if params.type.startswith('watchlist_'):
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
    if not params.id:
        core.kodi.notification('Trailer not found')
        core.utils.end_action(core, False)
        return

    request = {
        'method': 'GET',
        'url': 'https://www.imdb.com/ve/data/VIDEO_PLAYBACK_DATA',
        'params': {
            'key': core.base64.b64encode(core.json.dumps({ 'type': 'VIDEO_PLAYER', 'subType': 'FORCE_LEGACY', 'id': params.id }).encode('ascii'))
        },
        'headers': {
            'content-type': 'application/json',
        },
    }

    response = core.request.execute(core, request)
    if response.status_code != 200:
        core.utils.end_action(core, False)
        core.logger.notice(response.text)
        core.kodi.notification('Trailer not found')
        return

    parsed_response = core.json.loads(response.text)
    try:
        all = parsed_response[0]['videoLegacyEncodings']
        filtered = filter(lambda v: v['definition'] != 'AUTO', all)
        trailerUrl = next(iter(filtered), iter(all))['url']
    except:
        core.utils.end_action(core, False)
        core.kodi.notification('Trailer not found')
        return []

    item = core.kodi.xbmcgui.ListItem(path=trailerUrl, offscreen=True)
    item.setInfo('video', {'mediatype': 'video'})
    core.utils.end_action(core, True, item)

    return [trailerUrl]

def play(core, params):
    general = core.cache.get_general()

    if general.last_action_time and (core.utils.time_ms() - general.last_action_time) < 2000:
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

    apikey = core.utils.get_debrid_apikey(core)
    if not apikey or apikey == '':
        core.kodi.notification('Missing debrid service API key')
        core.utils.end_action(core, True)
        return

    provider_params = core.utils.DictAsObject({})
    provider_params.type = 'search'
    provider_params.title = core.utils.DictAsObject(core.json.loads(core.base64.b64decode(params.type)))
    if provider_params.title.tvshowid:
        provider_params.title.tvshowseasonid = '%s_%s' % (provider_params.title.tvshowid, provider_params.title.season)
    provider_params.start_time = core.utils.time_ms()

    last_results = core.cache.get_last_results()
    results = {}
    try:
        if provider_params.title.imdbnumber in last_results:
            results.update(last_results[provider_params.title.imdbnumber]['results'])
        if provider_params.title.tvshowseasonid in last_results:
            results.update(last_results[provider_params.title.tvshowseasonid]['results'])
        if provider_params.title.tvshowid in last_results:
            results.update(last_results[provider_params.title.tvshowid]['results'])
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
        results = core.provider(core, provider_params)

        if len(results) == 0:
            core.kodi.notification('No sources found')
            general.last_action_time = core.utils.time_ms()
            core.cache.save_general(general)
            core.utils.end_action(core, True)
            return

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

        if len(last_results) >= 50:
            oldest_key = last_results.keys()[0]
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
            not results[x]['hdr'] == 'HDR',
            not results[x]['videocodec'] == 'H265',
            'TRUEHD' not in results[x]['audiocodec'],
            'DTS' not in results[x]['audiocodec'],
            'ATMOS' not in results[x]['audiocodec'],
            'HD-MA' not in results[x]['audiocodec'],
            results[x]['release_title'],
        )

    results_keys = sorted(results_keys, key=sorter())
    result_style = '[LIGHT]%s[/LIGHT]'
    selection = core.kodi.xbmcgui.Dialog().select(
        'Choose source',
        [__action_menu_style % 'New Search'] + [result_style % results[key]['title'] for key in results_keys],
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

    result = results[results_keys[selection]]

    request = {
        'method': 'POST',
        'url': 'https://www.premiumize.me/api/transfer/directdl?apikey=%s' % apikey,
        'data': {
            'src': result['magnet']
        },
    }

    response = core.request.execute(core, request)
    link = None
    if response.status_code == 200:
        parsed_response = core.json.loads(response.text)
        video_ext = map(lambda v: '.%s' % v.upper(), core.utils.video_containers())
        size = 1048576 * 200

        files = parsed_response.get('content', [])
        for file in files:
            if file.get('path', None):
                file['path'] = core.os.path.basename(file['path']).upper()

        video_files = list(filter(lambda v: core.os.path.splitext(v['path'])[1] in video_ext and int(v['size']) > size, files))
        if len(video_files) > 0:
            files = video_files

        try:
            if len(files) > 1 and result['package'] in ['show', 'season'] and result['ref'].mediatype == 'episode':
                episode_number = 'S%sE%s' % (str(result['ref'].season).zfill(2), str(result['ref'].episode).zfill(2))
                episodes = list(filter(lambda v: episode_number in v['path'], files))
                if len(episodes) == 1:
                    files = episodes
        except Exception as e:
            core.logger.notice(e)

        if len(files) > 1:
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

            selection = core.kodi.xbmcgui.Dialog().select(
                'Choose file',
                [result_style % key for key in file_result_keys],
            )

            if selection > -1:
                file = file_results[file_result_keys[selection]]
                link = file['link']
            elif selection == -1:
                general.last_action_time = core.utils.time_ms()
                core.cache.save_general(general)
                core.utils.end_action(core, True)
                return

        elif len(files) == 1:
            file = files[0]
            link = file.get('link', file.get('stream_link', None))

    if not link:
        general.last_action_time = core.utils.time_ms()
        core.cache.save_general(general)
        core.kodi.notification('Failed to resolve debrid')
        core.utils.end_action(core, True)
        return

    item = core.kodi.xbmcgui.ListItem(path=link, offscreen=True)

    video_meta = provider_params.title.copy()
    video_meta.pop('tvshowseasonid', None)
    video_meta.pop('tvshowid', None)
    video_meta.pop('seasons', None)
    video_meta.pop('poster', None)

    if provider_params.title.poster:
        item.setArt({ 'poster': provider_params.title.poster })

    item.setInfo('video', video_meta)
    item.addStreamInfo('video', { 'codec': result['videocodec'], 'duration': result['ref'].duration })

    core.utils.end_action(core, True, item)
    return link
