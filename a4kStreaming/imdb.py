# -*- coding: utf-8 -*-

from .listing import (
    __action_menu_style,
    __handle_request_error,
    __add_lists,
    __add_seasons,
    __add_episodes,
    __add_title,
    __add_titles,
)

def __check_imdb_auth_config(core, params):
    if core.kodi.get_setting('imdb.at-main') == '':
        if not params.silent:
            core.kodi.notification('Missing IMDb authentication cookies')
            core.utils.end_action(core, True)
        return False
    return True

# public list pages: fresh for 30 min (IMDb cursors are not trusted past that), a first page older than that is shown
# at once and fetched again after the listing renders. Per-user lists (watchlist, lists, top picks) are never kept;
# the userRating these pages carry with a token is dropped with the whole IMDb cache by any IMDb write.
gallery_types = ['popularMovies', 'popularTVShows', 'popularAnimations', 'popularAnimationTVShows', 'popularRealityTVShows', 'popular', 'year', 'fan_picks', 'more_like_this']
cursor_ttl = 30 * 60

def __find_cursor(data):
    if isinstance(data, dict):
        for key in ['endCursor', 'paginationToken']:
            if data.get(key, None):
                return data[key]
        data = list(data.values())
    if isinstance(data, list):
        for item in data:
            cursor = __find_cursor(item)
            if cursor:
                return cursor
    return None

def __fresh_cursor(core, params, build):
    # the cursor in a Next item is older than 30 min: walk from the first page to a fresh cursor at the same position
    # (one cached or fresh request for page 2, more only after idling deep in a list)
    expired = params.paginationToken
    token = None
    for _ in range(max(int(params.page or 2) - 1, 1)):
        params.paginationToken = token
        response = core.request.execute(core, build(), cursor_ttl)
        token = __find_cursor(core.json.loads(response.content)) if response.status_code == 200 else None
        if not token:
            return expired
    return token

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

def __episodes_by_season(core, id, seasons):
    # a show past one 250-episode page: every season in one aliased request instead of walking the cursor page by page.
    # None (walk instead) for a single-season show or when a season itself needs a second page.
    if len(seasons) < 2:
        return None
    aliases = '\n'.join([
        's%s: episodes(first: 250, filter: { includeSeasons: ["%s"] }) { edges { node { ...SeasonsNode\n } } pageInfo { hasNextPage } }' % (i, season)
        for i, season in enumerate(seasons)
    ])
    request = core.utils.get_graphql_query({
        'query': 'query fn($id: ID!) { title(id: $id) { episodes { %s } } }' % aliases,
        'operationName': 'fn',
        'variables': { 'id': id },
    })
    response = core.request.execute(core, request)
    if response.status_code != 200 or core.request.graphql_failed(response.content):
        return None
    try:
        pages = core.json.loads(response.content)['data']['title']['episodes']
        pages = [pages['s%s' % i] for i in range(len(seasons))]
    except Exception:
        return None
    if any(page['pageInfo']['hasNextPage'] for page in pages):
        return None
    return [episode for page in pages for episode in core.utils.sanitize_response(page['edges'])]

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

def query(core, params):
    no_auth_required_actions = ['popularMovies', 'popularTVShows', 'popularAnimations', 'popularAnimationTVShows', 'popularRealityTVShows', 'popular', 'year', 'fan_picks', 'more_like_this', 'seasons', 'episodes', 'browse']
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
        'popularMovies': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($limit: Int!, $paginationToken: String, $endDate: Date!, $EXTRA_PARAMS) {
                    advancedTitleSearch(
                        first: $limit
                        after: $paginationToken
                        constraints: { genreConstraint: { allGenreIds: [], excludeGenreIds: ["Animation","Reality-TV","Game-Show"] }, releaseDateConstraint: { releaseDateRange: { end: $endDate }}, titleTypeConstraint: { anyTitleTypeIds: ["movie", "tvMovie"], excludeTitleTypeIds: [] } }
                        sort: { sortBy: POPULARITY, sortOrder: ASC }
                    ) {
                        titles: edges {
                            node {
                                title {
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
            ''',
            'operationName': 'fn',
            'variables': {
                'limit': page_size,
                'paginationToken': params.paginationToken,
                'endDate': '%s-%s-%s' % (now.year, str(now.month).zfill(2), str(now.day).zfill(2))
            }
        }),
        'popularTVShows': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($limit: Int!, $paginationToken: String, $endDate: Date!, $EXTRA_PARAMS) {
                    advancedTitleSearch(
                        first: $limit
                        after: $paginationToken
                        constraints: { genreConstraint: { allGenreIds: [], excludeGenreIds: ["Animation","Reality-TV","Game-Show"] }, releaseDateConstraint: { releaseDateRange: { end: $endDate }}, titleTypeConstraint: { anyTitleTypeIds: ["tvSeries","tvMiniSeries"], excludeTitleTypeIds: [] } }
                        sort: { sortBy: POPULARITY, sortOrder: ASC }
                    ) {
                        titles: edges {
                            node {
                                title {
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
            ''',
            'operationName': 'fn',
            'variables': {
                'limit': page_size,
                'paginationToken': params.paginationToken,
                'endDate': '%s-%s-%s' % (now.year, str(now.month).zfill(2), str(now.day).zfill(2))
            }
        }),
        'popularAnimations': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($limit: Int!, $paginationToken: String, $endDate: Date!, $EXTRA_PARAMS) {
                    advancedTitleSearch(
                        first: $limit
                        after: $paginationToken
                        constraints: { genreConstraint: { allGenreIds: ["Animation"], excludeGenreIds: ["Reality-TV","Game-Show"] }, releaseDateConstraint: { releaseDateRange: { end: $endDate }}, titleTypeConstraint: { anyTitleTypeIds: ["movie", "tvMovie"], excludeTitleTypeIds: [] } }
                        sort: { sortBy: POPULARITY, sortOrder: ASC }
                    ) {
                        titles: edges {
                            node {
                                title {
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
            ''',
            'operationName': 'fn',
            'variables': {
                'limit': page_size,
                'paginationToken': params.paginationToken,
                'endDate': '%s-%s-%s' % (now.year, str(now.month).zfill(2), str(now.day).zfill(2))
            }
        }),
        'popularAnimationTVShows': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($limit: Int!, $paginationToken: String, $endDate: Date!, $EXTRA_PARAMS) {
                    advancedTitleSearch(
                        first: $limit
                        after: $paginationToken
                        constraints: { genreConstraint: { allGenreIds: ["Animation"], excludeGenreIds: ["Reality-TV","Game-Show"] }, releaseDateConstraint: { releaseDateRange: { end: $endDate }}, titleTypeConstraint: { anyTitleTypeIds: ["tvSeries","tvMiniSeries"], excludeTitleTypeIds: [] } }
                        sort: { sortBy: POPULARITY, sortOrder: ASC }
                    ) {
                        titles: edges {
                            node {
                                title {
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
            ''',
            'operationName': 'fn',
            'variables': {
                'limit': page_size,
                'paginationToken': params.paginationToken,
                'endDate': '%s-%s-%s' % (now.year, str(now.month).zfill(2), str(now.day).zfill(2))
            }
        }),
        'popularRealityTVShows': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($limit: Int!, $paginationToken: String, $endDate: Date!, $EXTRA_PARAMS) {
                    advancedTitleSearch(
                        first: $limit
                        after: $paginationToken
                        constraints: { genreConstraint: { allGenreIds: ["Reality-TV","Game-Show"], excludeGenreIds: [] }, releaseDateConstraint: { releaseDateRange: { end: $endDate }}, titleTypeConstraint: { anyTitleTypeIds: ["tvSeries","tvMiniSeries"], excludeTitleTypeIds: [] } }
                        sort: { sortBy: POPULARITY, sortOrder: ASC }
                    ) {
                        titles: edges {
                            node {
                                title {
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
            ''',
            'operationName': 'fn',
            'variables': {
                'limit': page_size,
                'paginationToken': params.paginationToken,
                'endDate': '%s-%s-%s' % (now.year, str(now.month).zfill(2), str(now.day).zfill(2))
            }
        }),
        'popular': lambda: core.utils.get_graphql_query({
            'query': '''
                query fn($limit: Int!, $paginationToken: String, $popularTitlesQueryFilter: PopularTitlesQueryFilter!, $EXTRA_PARAMS) {
                    popularTitles(
                        limit: $limit,
                        paginationToken: $paginationToken,
                        queryFilter: $popularTitlesQueryFilter
                    ) {
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
                    popularTitles(
                        limit: $limit,
                        paginationToken: $paginationToken,
                        queryFilter: $popularTitlesQueryFilter
                    ) {
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
                query fn($first: Int!, $paginationToken: ID, $EXTRA_PARAMS) {
                    fanPicksTitles(
                        first: $first,
                        after: $paginationToken
                    ) {
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
                'paginationToken': params.paginationToken
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
                'limit': 250,  # every page is fetched before anything renders, so take IMDb's largest page
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

    if params.paginationToken and params.cursor_time and core.time.time() - float(params.cursor_time) > cursor_ttl:
        params.paginationToken = __fresh_cursor(core, params, requests[params.type])

    request = requests[params.type]()
    gallery = params.type in gallery_types
    response = core.request.execute(core, request, cursor_ttl if gallery else True, stale_ok=gallery and not params.paginationToken)
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
            if core.request.graphql_failed(response.content):
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

        all_episodes = __episodes_by_season(core, params.id, data['episodes'].get('seasons', [])) if hasNextPage and not params.paginationToken else None
        if all_episodes is not None:
            episodes = all_episodes
        elif hasNextPage:
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
        core.kodi.set_info_tag(next_list_item, {'mediatype': 'video'})

        paginationToken = data.get('paginationToken', None)
        if not paginationToken:
            paginationToken = data['pageInfo']['endCursor']

        url = '%s?action=query&type=%s&paginationToken=%s&page=%s&cursor_time=%s' % (core.url, params.type, core.utils.quote_plus(paginationToken), int(params.page or 1) + 1, int(response.fetched_at))
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

    videos = params.vi.split('_')
    vi = videos[0]

    if len(videos) > 1:
        selection = core.kodi.xbmcgui.Dialog().select(
            'Choose trailer',
            ['%s. %s' % (i + 1, v) for i, v in enumerate(videos)],
        )

        if selection == -1:
            core.kodi.close_busy_dialog()
            core.utils.end_action(core, False)
            return

        vi = videos[selection]

    request = {
        'method': 'POST',
        'url': 'https://graphql.imdb.com',
        'data': core.json.dumps({
            'query': '''
                query fn($videoId: ID!) {
                    video(id: $videoId) {
                        playbackURLs {
                            url
                            displayName { value }
                            videoDefinition
                        }
                    }
                }
            ''',
            'operationName': 'fn',
            'variables': {
                'videoId': vi,
            }
        }),
    }
    request.update(core.utils.imdb_auth_request_props())

    response = core.request.execute(core, request, False)
    if response.status_code != 200:
        core.kodi.close_busy_dialog()
        core.utils.end_action(core, False)
        core.logger.notice(response.text)
        core.kodi.notification('Trailer not found')
        return

    parsed_response = core.json.loads(response.content)
    try:
        all = parsed_response['data']['video']['playbackURLs']
        filtered = filter(lambda v: v['displayName']['value'] != 'AUTO', all)
        trailerUrl = next(iter(filtered), iter(all))['url']
    except:
        core.kodi.close_busy_dialog()
        core.utils.end_action(core, False)
        core.kodi.notification('Trailer not found')
        return []

    item = core.kodi.xbmcgui.ListItem(path=trailerUrl, offscreen=True)
    core.kodi.set_info_tag(item, {'mediatype': 'video'})
    if params.play == 'true':
        core.kodi.close_busy_dialog()
        core.kodi.xbmc.Player().play(item=trailerUrl, listitem=item)
    else:
        core.utils.end_action(core, True, item)

    return [trailerUrl]
