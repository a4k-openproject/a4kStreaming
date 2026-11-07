# -*- coding: utf-8 -*-

__action_menu_style = '[COLOR white][B]%s[/B][/COLOR]'

def __get_season_title(season_template, season, year, episodes):
    if season_template == '1':
        return 'Season %s (%s)' % (season, year)
    if season_template == '2':
        return 'Season %s' % season
    if season_template == '3':
        return 'Season %s - %s Episodes' % (season, episodes)
    return 'Season %s (%s) - %s Episodes' % (season, year, episodes)

def __get_episode_title(season_template, season, episode, title):
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

def __set_wide_image_as_primary(title):
    title_images = title.get('images', None)
    if title_images and len(title_images) > 0:
        if title['primaryImage']:
            title_images.insert(0, title['primaryImage'])
        wide_images = list(filter(lambda v: v['width'] > v['height'] and v.get('type', None) != 'poster', title_images))
        if len(wide_images) > 0:
            title['primaryImage'] = wide_images[0]

def title_context_menu(core, title, autoplay=None):
    # [(label, builtin)] for a title's context menu; autoplay is the general.autoplay setting, read once per listing
    titleType = title['titleType']
    if titleType == 'person':
        return []

    trailer = ''
    all_trailers = ''
    if title.get('primaryVideos', None) and len(title['primaryVideos']) > 0:
        trailer = title['primaryVideos'][0]
        all_trailers = '_'.join(title['primaryVideos'])

    tvseries = titleType == 'tvSeries'
    has_rating = title.get('userRating', None) is not None
    context_menu_items = [
        ('IMDb: %s rating' % ('Update' if has_rating else 'Set'), 'RunPlugin(%s?action=profile&type=rate&id=%s)' % (core.url, title['id'])),
        ('IMDb: Trailer', 'RunPlugin(%s?action=trailer&id=%s&vi=%s&play=true)' % (core.url, title['id'], trailer)),
        ('IMDb: Choose Trailer', 'RunPlugin(%s?action=trailer&id=%s&vi=%s&play=true)' % (core.url, title['id'], all_trailers)),
        ('IMDb: Cast & Crew', 'ActivateWindow(Videos,%s?action=query&type=browse&id=%s,return)' % (core.url, title['id'])),
    ]

    if titleType != 'tvEpisode':
        context_menu_items.append(
            ('IMDb: More like this', 'ActivateWindow(Videos,%s?action=query&type=more_like_this&id=%s,return)' % (core.url, title['id']))
        )

    if not tvseries:
        if has_rating:
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
        context_menu_items.extend([
            ('Force file select', 'PlayMedia(%s?action=play&id=%s&force_fileselect=true)' % (core.url, title['id'])),
            ('Refresh sources', 'PlayMedia(%s?action=play&id=%s&refresh=true)' % (core.url, title['id'])),
        ])
        if core.kodi.get_bool_setting('general.autoplay') if autoplay is None else autoplay:
            context_menu_items.extend([
                ('Force source select', 'PlayMedia(%s?action=play&id=%s&force_sourceselect=true)' % (core.url, title['id']))
            ])

    return context_menu_items

def __set_title_contextmenu(core, title, list_item, autoplay):
    if title['titleType'] == 'person':
        return
    if title['titleType'] != 'tvSeries' and title.get('userRating', None) is not None:
        core.kodi.set_info_tag(list_item, {
            'overlay': 5,
            'playcount': 1
        })
    list_item.addContextMenuItems(title_context_menu(core, title, autoplay))

def __title_type(title):
    titleType = title['titleType']
    return 'movie' if titleType in ['tvMovie', 'tvSpecial', 'video'] else titleType

def __still(title):
    return next(iter(title.get('stillFrame', None) or []), None)

def __wide_art(core, image):
    # still frame art for a tvOS-style skin: the full-screen backdrop, the focused-row landscape and a tiny one to blur
    return {
        'fanart': core.utils.fix_fanart_size(image),
        'landscape': core.utils.fix_landscape_size(image),
        'blur': core.utils.fix_blur_size(image),
    }

def __poster_and_thumb(core, title):
    primary_image = title.get('primaryImage', None)
    poster_image = title.get('poster', None)
    if poster_image:
        poster_image = core.utils.fix_poster_size(poster_image)
        return poster_image, core.utils.fix_thumb_size(primary_image) if primary_image else poster_image
    poster_image = core.utils.fix_poster_size(primary_image)
    return poster_image, poster_image

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
    core.utils.add_directory_items(core, list_items)
    core.kodi.xbmcplugin.addSortMethod(core.handle, core.kodi.xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)

def group_seasons(core, episodes):
    # {season number: season} in first-aired order, each with its episode count and ids and the release-date window
    # its episodes query asks for (season_url). The directory and the detail window share it. Mutates the release dates.
    seasons = {}

    episodes = list(filter(lambda ep: ep['releaseDate'], episodes))

    prev_rld = None
    for index, episode in enumerate(episodes):
        try:
            if not episode['series']:
                continue

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

    return seasons

def season_url(core, title_id, key, season):
    url = '%s?action=query&type=episodes&id=%s&season=%s' % (core.url, title_id, key)
    for param in ('year', 'month', 'day', 'year_end', 'month_end', 'day_end'):
        if season[param]:
            url += '&%s=%s' % (param, season[param])
    return url

def __add_seasons(core, title):
    seasons = group_seasons(core, title['episodes']['episodes'])
    list_items = []
    season_template = core.kodi.get_setting('general.season_title_template')
    poster = core.utils.fix_poster_size(title['primaryImage'])
    wide_art = __wide_art(core, __still(title))
    for key in seasons:
        season = seasons[key]
        season.key = key
        season.title = __get_season_title(season_template, key, season.first_episode_year if season.first_episode_year else 'N/A', season.episodes)

        list_item = core.kodi.xbmcgui.ListItem(label=season.title, offscreen=True)
        list_item.setArt({
            'thumb': poster,
            'poster': poster,
            'fanart': wide_art['fanart'],
            'blur': wide_art['blur'],
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
        core.kodi.set_info_tag(list_item, video_meta)

        url = season_url(core, title['id'], key, season)

        context_menu_items = []
        last_episode_has_rating = season.last_episode and season.last_episode.get('userRating', None) is not None
        if last_episode_has_rating:
            core.kodi.set_info_tag(list_item, {
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

    core.utils.add_directory_items(core, list_items)

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
    episode_template = core.kodi.get_setting('general.episode_title_template')
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
        if len(seasons) > 0:
            episode['no_seasons'] = seasons[-1]

        episode['seasons'] = seasons
        episode['titleText'] = __get_episode_title(episode_template, season, episodeNumber, episode['titleText'])

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

def __video_meta(core, title, titleType):
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

    if title.get('episodes', None):
        episodes = title['episodes']
        if episodes.get('isOngoing', None) is not None:
            video_meta.update({ 'status': 'Continuing' if episodes['isOngoing'] else 'Ended' })
        if core.utils.safe_list_get(episodes.get('seasons', [None]), -1, None):
            if not video_meta.get('season', None):
                video_meta.update({ 'season': episodes['seasons'][-1] })
        if episodes.get('totalEpisodes', None):
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

    return video_meta

def __play_type(core, title, video_meta, poster):
    # the play URL's type param: the title's metadata for the player, base64 JSON ('' without a release year)
    if title.get('releaseYear', None) is None:
        return ''
    title_meta = video_meta.copy()
    title_meta.update({
        'tvshowid': title.get('tvshowid', None),
        'seasons': title.get('seasons', None),
        'is_airing': title_meta.get('season', None) == title.get('nextEpisodeSeasonNumber', -1),
        'poster': poster,
    })
    return core.base64.b64encode(core.json.dumps(title_meta).encode()).decode('ascii')

def play_url(core, title):
    # the URL a movie or an episode plays from, the same one its list item carries; None for anything else
    titleType = __title_type(title)
    if titleType not in ['movie', 'tvEpisode']:
        return None
    poster_image, thumb_image = __poster_and_thumb(core, title)
    type = __play_type(core, title, __video_meta(core, title, titleType), thumb_image or poster_image)
    return '%s?action=play&type=%s' % (core.url, type) if type else '%s?action=play&type=&id=%s' % (core.url, title['id'])

def __add_titles(core, titles, browse, silent=False):
    list_items = []
    autoplay = core.kodi.get_bool_setting('general.autoplay')

    for title in titles:
        titleType = __title_type(title)
        if titleType not in ['movie', 'tvSeries', 'tvEpisode', 'person']:
            continue

        list_item = core.kodi.xbmcgui.ListItem(label=title['titleTextStyled'] if title.get('titleTextStyled', None) else title['titleText'], offscreen=True)
        video_info_tag = list_item.getVideoInfoTag()

        poster_image, thumb_image = __poster_and_thumb(core, title)
        art = {
            'thumb': thumb_image,
            'poster': poster_image,
        }
        # an episode's primary image is already its still; movies and series bring one in stillFrame
        art.update(__wide_art(core, title.get('primaryImage', None) if titleType == 'tvEpisode' else __still(title)))
        list_item.setArt(art)

        list_item.setProperty('a4k.id', title['id'])
        list_item.setProperty('a4k.type', titleType)
        list_item.setProperty('a4k.rated', 'true' if title.get('userRating', None) is not None else 'false')
        list_item.setProperty('a4k.trailers', '_'.join(title.get('primaryVideos', None) or []))

        video_meta = __video_meta(core, title, titleType)
        mediatype = video_meta['mediatype']

        if title.get('ratingsSummary', None):
            ratingsSummary = title['ratingsSummary']
            if ratingsSummary.get('aggregateRating', None) and ratingsSummary.get('voteCount', None):
                video_info_tag.setRating(ratingsSummary['aggregateRating'], ratingsSummary['voteCount'], "imdb", True)

        if title.get('episodes', None):
            episodes = title['episodes']
            if core.utils.safe_list_get(episodes.get('seasons', [None]), -1, None):
                seasons = str(episodes['seasons'][-1])
                list_item.setProperty('TotalSeasons', seasons)
                if mediatype == 'tvshow':
                    list_item.setProperty('WatchedEpisodes', '*')
                    list_item.setProperty('TotalEpisodes', seasons)
            if episodes.get('totalEpisodes', None):
                total_episodes = episodes['totalEpisodes']
                list_item.setProperty('WatchedEpisodes', '*')
                list_item.setProperty('UnWatchedEpisodes', '*')
                list_item.setProperty('TotalEpisodes', str(total_episodes))
                list_item.setProperty('NumEpisodes', str(total_episodes))

        info_tag = core.kodi.set_info_tag(list_item, video_meta)

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
                'thumbnail': core.utils.fix_cast_size(member.get('primaryImage', member.get('name', {}).get('primaryImage', None)))
            })
        info_tag.set_cast(cast_meta)

        if titleType in ['movie', 'tvEpisode']:
            if browse:
                action = 'query'
                type = 'browse'
            else:
                list_item.setProperty('IsPlayable', 'true')
                action = 'play'
                type = __play_type(core, title, video_meta, thumb_image or poster_image)
                if silent and type:
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
        __set_title_contextmenu(core, title, list_item, autoplay)
        list_items.append((url, list_item, action != 'play'))

    core.utils.add_directory_items(core, list_items)

def root(core):
    items = [
        {
            'label': 'Trending Movies',
            'action': 'query',
            'type': 'popularMovies',
            'info': 'IMDb\'s latest trending movies.',
            'subitems': True
        },
        {
            'label': 'Trending TV Series',
            'action': 'query',
            'type': 'popularTVShows',
            'info': 'IMDb\'s latest trending TV series.',
            'subitems': True
        },
        {
            'label': 'Trending Animations',
            'action': 'query',
            'type': 'popularAnimations',
            'info': 'IMDb\'s latest trending animations.',
            'subitems': True
        },
        {
            'label': 'Trending Animation TV Series',
            'action': 'query',
            'type': 'popularAnimationTVShows',
            'info': 'IMDb\'s latest trending animation TV series.',
            'subitems': True
        },
        {
            'label': 'Trending Reality TV Series',
            'action': 'query',
            'type': 'popularRealityTVShows',
            'info': 'IMDb\'s latest trending reality TV series.',
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
    core.utils.add_directory_items(core, list_items)

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
    core.utils.add_directory_items(core, list_items)
