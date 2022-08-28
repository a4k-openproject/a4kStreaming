# -*- coding: utf-8 -*-

def __trakt_request(core, endpoint, type):
    headers = {
        'content-type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': core.kodi.get_setting('trakt.clientid')
    }

    request = {
        'method': 'GET',
        'url': 'https://api.trakt.tv/users/%s/%s/%s' % (core.kodi.get_setting('trakt.username'), endpoint, type),
        'headers': headers
    }

    response = core.request.execute(core, request)
    if response.status_code != 200:
        core.kodi.notification('Something went wrong. Check logs')
        core.logger.notice(response.text)
        return False

    return core.json.loads(response.content)

def __migrate_status(core, params):
    if core.kodi.get_setting('imdb.at-main') == '':
        core.kodi.notification('Missing IMDb authentication cookies')
        return

    if core.kodi.get_setting('trakt.clientid') == '':
        core.kodi.notification('Missing Trakt API key (Client ID)')
        return

    if core.kodi.get_setting('trakt.username') == '':
        core.kodi.notification('Missing Trakt username (User slug)')
        return

    mark_as_watched_rating = core.kodi.get_int_setting('general.mark_as_watched_rating')
    confirmed = core.kodi.xbmcgui.Dialog().yesno(
        'Migrate Trakt.tv watched state to IMDb',
        'This is a slow operation and will effectively rate every watched title with a rating "%s" in IMDb in order to mark it as watched. (All rated titles cannot be reverted)' % mark_as_watched_rating,
        nolabel='Cancel',
        yeslabel='Start'
    )

    if not confirmed:
        return

    progress = core.kodi.xbmcgui.DialogProgress()
    progress.create(core.kodi.addon_name, '')
    try:
        state = lambda: None
        state.target = None

        def update_progress():
            msg = [state.progress_msg]
            if state.target:
                target = 'Show: %s' % state.target
                if core.utils.py2:
                    msg.append(target)
                else:
                    msg = [state.progress_msg + '\n' + target]

            progress.update(int(float(state.current) / state.total * 100), *msg)

        def mark_ids(ids, increment=True):
            ratings = []
            for chunk in core.utils.chunk(ids, 50):
                if progress.iscanceled():
                    break
                ratings += core.query(core, core.utils.DictAsObject({ 'type': 'ratings', 'ids': chunk }))
                if increment:
                    state.current += float(len(chunk)) / 2
                core.kodi.xbmc.sleep(1000)

            unrated_ids = []
            for i, id in enumerate(ids):
                if progress.iscanceled():
                    break
                try:
                    if not ratings[i]:
                        unrated_ids.append(id)
                except:
                    core.logger.notice('error transfering set of ids starting with %s' % id)
                    return

            for chunk in core.utils.chunk(unrated_ids, 50):
                if progress.iscanceled():
                    break
                core.profile(core, core.utils.DictAsObject({ 'type': 'mark_as_watched', 'ids': '__'.join(chunk), 'silent': True }))
                if increment:
                    state.current += float(len(chunk)) / 2
                core.kodi.xbmc.sleep(1000)

        def mark_show_ids(shows):
            for show in shows:
                if progress.iscanceled():
                    break
                state.target = show['show']['title']
                imdb_episodes = core.query(core, core.utils.DictAsObject({ 'type': 'seasons', 'id': show['show']['ids']['imdb'], 'silent': True }))
                core.kodi.xbmc.sleep(1000)

                imdb_season_episodes = {}
                for imdb_episode in imdb_episodes:
                    if progress.iscanceled():
                        break
                    try:
                        imdb_episode_series = imdb_episode['series']

                        imdb_episode_season = imdb_episode_series['seasonNumber']
                        imdb_season_episodes.setdefault(imdb_episode_season, {})

                        imdb_episode_number = imdb_episode_series['episodeNumber']
                        imdb_season_episodes[imdb_episode_season].setdefault(imdb_episode_number, {})
                        imdb_season_episodes[imdb_episode_season][imdb_episode_number]['id'] = imdb_episode['id']
                    except: pass

                episode_ids = []
                episodes_count = 0
                for season in show['seasons']:
                    if progress.iscanceled():
                        break
                    season_number = season['number']
                    if season_number == 0:
                        continue

                    for episode in season['episodes']:
                        if progress.iscanceled():
                            break
                        episodes_count += 1
                        episode_number = episode['number']
                        try: episode_ids.append(imdb_season_episodes[season_number][episode_number]['id'])
                        except: pass

                mark_ids(episode_ids, increment=False)
                state.current += 1

        def execute():
            for chunk in core.utils.chunk(state.threads, 8):
                for thread in chunk:
                    thread.start()
                    if progress.iscanceled():
                        break

                for thread in chunk:
                    thread.join()
                    if progress.iscanceled():
                        break
            state.done = True

        results = __trakt_request(core, 'watched', 'movies')
        ids = [result['movie']['ids']['imdb'] for result in results]
        state.total = len(ids)
        state.current = 0
        state.threads = []
        state.done = False
        state.progress_msg = 'Transfering movies watched status from Trakt.tv to IMDb...'
        update_progress()

        for chunk in core.utils.chunk(ids, 10000):
            state.threads.append(core.threading.Thread(target=mark_ids, args=(chunk,)))

        exec_thread = core.threading.Thread(target=execute)
        exec_thread.start()

        while (not progress.iscanceled() and not state.done):
            core.kodi.xbmc.sleep(1000)
            update_progress()

        if progress.iscanceled():
            return

        results = __trakt_request(core, 'watched', 'shows')
        state.total = len(results)
        state.current = 0
        state.threads = []
        state.done = False
        state.progress_msg = 'Transfering TV shows watched status from Trakt.tv to IMDb...'
        update_progress()

        for chunk in core.utils.chunk(results, 10000):
            state.threads.append(core.threading.Thread(target=mark_show_ids, args=(results,)))

        exec_thread = core.threading.Thread(target=execute)
        exec_thread.start()

        while (not progress.iscanceled() and not state.done):
            core.kodi.xbmc.sleep(1000)
            update_progress()

        if progress.iscanceled():
            return

        core.kodi.notification('Migration completed')

    except Exception as e:
        core.kodi.notification('Something went wrong. Check logs')
        core.logger.notice(e)
    finally:
        try: progress.close()
        except: pass

def __migrate_collections(core, params):
    if core.kodi.get_setting('imdb.at-main') == '':
        core.kodi.notification('Missing IMDb authentication cookies')
        return

    if core.kodi.get_setting('trakt.clientid') == '':
        core.kodi.notification('Missing Trakt API key (Client ID)')
        return

    if core.kodi.get_setting('trakt.username') == '':
        core.kodi.notification('Missing Trakt username (User slug)')
        return

    confirmed = core.kodi.xbmcgui.Dialog().yesno(
        'Migrate Trakt.tv collections to IMDb',
        'The lists "Movies Collection" and "Shows Collection" must be created in IMDb prior starting. In addition, if this operation is done more than ones, duplicates will be added to the lists.',
        nolabel='Cancel',
        yeslabel='Start'
    )

    if not confirmed:
        return

    progress = core.kodi.xbmcgui.DialogProgress()
    progress.create(core.kodi.addon_name, '')
    try:
        imdb_lists = core.query(core, core.utils.DictAsObject({ 'type': 'lists', 'silent': True }))
        required_lists = {
            'movies': 'Movies Collection',
            'shows': 'Shows Collection'
        }

        target_lists = {}
        for key in required_lists.keys():
            required_list = required_lists[key]
            matching_imdb_lists = [imdb_list for imdb_list in imdb_lists if required_list.lower() == imdb_list['name'].lower()]
            if len(matching_imdb_lists) == 0:
                core.kodi.notification('No matching lists in IMDb for %s' % required_list)
                return
            elif len(matching_imdb_lists) > 1:
                core.kodi.notification('More than one matching lists found in IMDb for %s' % required_list)
                return

            target_lists[key] = matching_imdb_lists[0]

        def add_to_list(type):
            type_plural = type + 's'
            trakt_collection = __trakt_request(core, 'collection', type_plural)
            ids = [title[type]['ids']['imdb'] for title in trakt_collection]
            current = 0

            for chunk in core.utils.chunk(ids, 50):
                if progress.iscanceled():
                    break
                core.profile(core, core.utils.DictAsObject({ 'type': 'list_add', 'imdb_list': target_lists[type_plural], 'ids': '__'.join(chunk), 'silent': True }))
                current += len(chunk)
                progress.update(int(float(current) / len(ids) * 100))
                core.kodi.xbmc.sleep(1000)

        if progress.iscanceled():
            return

        progress.update(0, 'Transfering Movies Collection...')
        add_to_list('movie')

        if progress.iscanceled():
            return

        progress.update(0, 'Transfering Shows Collection...')
        add_to_list('show')

        if progress.iscanceled():
            return

        core.kodi.notification('Migration completed')
    finally:
        progress.close()

def trakt(core, params):
    if params.type == 'migrate_status':
        return __migrate_status(core, params)
    if params.type == 'migrate_collections':
        return __migrate_collections(core, params)
    else:
        core.not_supported()
