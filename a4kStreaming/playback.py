# -*- coding: utf-8 -*-

from .listing import (
    __action_menu_style,
    __handle_request_error,
)
from .imdb import (
    query,
)

def cache_sources(core, params, results=None):
    pm_apikey = core.utils.get_premiumize_apikey(core)
    if not pm_apikey:
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

    selection = None

    while (selection != -1):
        results_keys = list(results.keys())
        def sorter():
            return lambda x: (
                -int(results[x].get(core.utils.result_rank_key, 0)),
                not results[x]['quality'] == '4K',
                not results[x]['quality'] == '1080P',
                not results[x]['quality'] == '720P',
                not results[x]['quality'] == 'SD',
                not results[x]['quality'] == 'CAM',
                not results[x]['hdr'] == 'DV',
                not results[x]['hdr'].startswith('HDR'),
                not results[x]['videocodec'] == 'H265',
                -results[x]['size'],
                'TRUEHD' not in results[x]['audiocodec'],
                'DTS' not in results[x]['audiocodec'],
                'ATMOS' not in results[x]['audiocodec'],
                'HD-MA' not in results[x]['audiocodec'],
                results[x]['release_title'],
            )
        results_keys = sorted(results_keys, key=sorter())

        selection = core.kodi.xbmcgui.Dialog().select(
            'Choose source to cache',
            ['Availability: %s  |  %s' % (results[key][core.utils.result_rank_key], results[key]['title']) for key in results_keys],
        )

        if selection > -1:
            result = results[results_keys[selection]]

            def cache():
                request = core.debrid.premiumize_cache(pm_apikey, result[core.utils.result_link_key])
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
                    core.kodi.notification('PM transfer is already added')
                else:
                    core.kodi.notification('PM transfer created: %s' % result['hash'])
                return True

            if not cache():
                continue

            results.pop(results_keys[selection])

def result_sort_key(result):
    return (
        result.get('title_mismatch', False),
        not result.get('episode_title_hit', False),
        not result['quality'] == '4K',
        not result['quality'] == '1080P',
        not result['quality'] == '720P',
        not result['quality'] == 'SD',
        not result['quality'] == 'CAM',
        'DV' not in result['hdr'],
        'HDR10+' not in result['hdr'],
        'HDR10' not in result['hdr'],
        'HDR' not in result['hdr'],
        not result['videocodec'] == 'H265',
        -result['size'],
        '12BIT' not in result['hdr'],
        '10BIT' not in result['hdr'],
        'TRUEHD' not in result['audiocodec'],
        'ATMOS' not in result['audiocodec'],
        'HD-MA' not in result['audiocodec'],
        'DTS' not in result['audiocodec'],
        'DD' not in result['audiocodec'],
        result['release_title'],
    )

def util_filter_episodes(core, result, files, prop_name):
    season_nozfill = str(result['ref'].season)
    season_zfill = season_nozfill.zfill(2)
    episode_nozfill = str(result['ref'].episode)
    episode_zfill = episode_nozfill.zfill(2)
    episode_zfill_3 = episode_zfill.zfill(3)
    episode_prev_nozfill = str(int(result['ref'].episode) - 1)
    episode_prev_zfill = episode_prev_nozfill.zfill(2)
    episode_prev_zfill_3 = episode_prev_zfill.zfill(3)
    episode_next_nozfill = str(int(result['ref'].episode) + 1)
    episode_next_zfill = episode_next_nozfill.zfill(2)
    episode_next_zfill_3 = episode_next_zfill.zfill(3)
    season = 's%s' % season_nozfill
    season_0 = 's%s' % season_zfill
    episode = 'e%s' % episode_nozfill
    episode_0 = 'e%s' % episode_zfill
    episode_00 = 'e%s' % episode_zfill_3
    episode_prev = 'e%s' % episode_prev_nozfill
    episode_prev_0 = 'e%s' % episode_prev_zfill
    episode_prev_00 = 'e%s' % episode_prev_zfill_3
    episode_next = 'e%s' % episode_next_nozfill
    episode_next_0 = 'e%s' % episode_next_zfill
    episode_next_00 = 'e%s' % episode_next_zfill_3
    matchesx = [
        ' %sx%s ' % (season, episode),
        ' %sx%s ' % (season, episode_0),
        ' %sx%s ' % (season, episode_00),
        ' %sx%s ' % (season, episode_zfill),
        ' %sx%s ' % (season, episode_zfill_3),
        ' %sx%s%s ' % (season, episode_prev, episode),
        ' %sx%s%s ' % (season, episode_prev_0, episode_0),
        ' %sx%s%s ' % (season, episode_prev_00, episode_00),
        ' %sx%s%s ' % (season, episode_prev_zfill, episode_zfill),
        ' %sx%s%s ' % (season, episode_prev_zfill_3, episode_zfill_3),
        ' %sx%s%s ' % (season, episode, episode_next),
        ' %sx%s%s ' % (season, episode_0, episode_next_0),
        ' %sx%s%s ' % (season, episode_00, episode_next_00),
        ' %sx%s%s ' % (season, episode_zfill, episode_next_zfill),
        ' %sx%s%s ' % (season, episode_zfill_3, episode_next_zfill_3),
        ' %sx%s ' % (season_0, episode),
        ' %sx%s ' % (season_0, episode_0),
        ' %sx%s ' % (season_0, episode_00),
        ' %sx%s ' % (season_0, episode_zfill),
        ' %sx%s ' % (season_0, episode_zfill_3),
        ' %sx%s%s ' % (season_0, episode_prev, episode),
        ' %sx%s%s ' % (season_0, episode_prev_0, episode_0),
        ' %sx%s%s ' % (season_0, episode_prev_00, episode_00),
        ' %sx%s%s ' % (season_0, episode_prev_zfill, episode_zfill),
        ' %sx%s%s ' % (season_0, episode_prev_zfill_3, episode_zfill_3),
        ' %sx%s%s ' % (season_0, episode, episode_next),
        ' %sx%s%s ' % (season_0, episode_0, episode_next_0),
        ' %sx%s%s ' % (season_0, episode_00, episode_next_00),
        ' %sx%s%s ' % (season_0, episode_zfill, episode_next_zfill),
        ' %sx%s%s ' % (season_0, episode_zfill_3, episode_next_zfill_3),
        ' %sx%s ' % (season_zfill, episode),
        ' %sx%s ' % (season_zfill, episode_0),
        ' %sx%s ' % (season_zfill, episode_00),
        ' %sx%s ' % (season_zfill, episode_zfill),
        ' %sx%s ' % (season_zfill, episode_zfill_3),
        ' %sx%s%s ' % (season_zfill, episode_prev, episode),
        ' %sx%s%s ' % (season_zfill, episode_prev_0, episode_0),
        ' %sx%s%s ' % (season_zfill, episode_prev_00, episode_00),
        ' %sx%s%s ' % (season_zfill, episode_prev_zfill, episode_zfill),
        ' %sx%s%s ' % (season_zfill, episode_prev_zfill_3, episode_zfill_3),
        ' %sx%s%s ' % (season_zfill, episode, episode_next),
        ' %sx%s%s ' % (season_zfill, episode_0, episode_next_0),
        ' %sx%s%s ' % (season_zfill, episode_00, episode_next_00),
        ' %sx%s%s ' % (season_zfill, episode_zfill, episode_next_zfill),
        ' %sx%s%s ' % (season_zfill, episode_zfill_3, episode_next_zfill_3),
        ' %sx%s ' % (season_nozfill, episode),
        ' %sx%s ' % (season_nozfill, episode_0),
        ' %sx%s ' % (season_nozfill, episode_00),
        ' %sx%s ' % (season_nozfill, episode_zfill),
        ' %sx%s ' % (season_nozfill, episode_zfill_3),
        ' %sx%s%s ' % (season_nozfill, episode_prev, episode),
        ' %sx%s%s ' % (season_nozfill, episode_prev_0, episode_0),
        ' %sx%s%s ' % (season_nozfill, episode_prev_00, episode_00),
        ' %sx%s%s ' % (season_nozfill, episode_prev_zfill, episode_zfill),
        ' %sx%s%s ' % (season_nozfill, episode_prev_zfill_3, episode_zfill_3),
        ' %sx%s%s ' % (season_nozfill, episode, episode_next),
        ' %sx%s%s ' % (season_nozfill, episode_0, episode_next_0),
        ' %sx%s%s ' % (season_nozfill, episode_00, episode_next_00),
        ' %sx%s%s ' % (season_nozfill, episode_zfill, episode_next_zfill),
        ' %sx%s%s ' % (season_nozfill, episode_zfill_3, episode_next_zfill_3),
    ]

    clean_name = 'clean_%s' % prop_name
    for file in files:
        file[clean_name] = ' %s ' % core.utils.clean_release_title(file[prop_name]).lower()

    if result['package'] in ['season'] and all([' s0' not in f[clean_name] and ' s1' not in f[clean_name] for f in files]):
        matchesx.append(' %s ' % episode)
        matchesx.append(' %s ' % episode_0)
        matchesx.append(' %s ' % episode_00)
        matchesx.append(' %s ' % episode_zfill)
        matchesx.append(' %s ' % episode_zfill_3)

    matches = []
    for match in matchesx:
        matches.append(match)
        matches.append(match.replace('x', ''))
        matches.append(match.replace('x', ' '))

    return list(filter(lambda file: any(match in file[clean_name] for match in matches), files))

def __link_alive(core, link):
    # a dead or expired debrid link fails here, where the next source can be tried, instead of in the player
    return core.request.probe(link)

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
    if not pm_apikey:
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

    provider_params.refresh = params.refresh
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

    results_keys = sorted(results.keys(), key=lambda key: result_sort_key(results[key]))

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
    last_selected_result = core.cache.get_last_selected_result()
    result_keys_hash = core.utils.hash_data(''.join(results_keys))
    if result_keys_hash in last_selected_result:
        selection = last_selected_result[result_keys_hash]

    video_ext = list(map(lambda v: '.%s' % v.upper(), core.utils.video_containers()))
    size = 1048576 * 100

    def resolve_pm():
        request = core.debrid.premiumize_resolve(pm_apikey, result[core.utils.result_link_key])
        response = core.request.execute(core, request)
        parsed_response = core.json.loads(response.content)
        return parsed_response.get('content', [])

    while True:
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
            params.refresh = True
            general.last_action_time = None
            core.cache.save_general(general)
            return play(core, params)
        else:
            core.cache.save_last_selected_result({ result_keys_hash: selection })
            selection -= 1

        while True:
            result = results[results_keys[selection]]
            link = result.get('url', None)
            if link:
                break

            files = []
            try: files = resolve_pm()
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
                    if len(files) > 1 and result['ref'].mediatype == 'episode' and not params.force_fileselect:
                        episodes = util_filter_episodes(core, result, files, 'path')
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
                        autoplay = False
                        break

                elif len(files) == 1:
                    file = files[0]
                    link = file.get('link', file.get('stream_link', None))

            if link:
                if __link_alive(core, link):
                    break
                core.logger.notice('Dead link: %s' % result['release_title'])
                link = None

            selection += 1
            if selection < len(results_keys) and autoplay:
                continue

            core.kodi.notification('Failed to resolve debrid')
            autoplay = False
            break

        if link:
            break

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

    info_tag = core.kodi.set_info_tag(item, video_meta)
    info_tag.add_stream_info('video', { 'codec': result['videocodec'], 'duration': result['ref'].duration })

    core.utils.end_action(core, True, item)
    return link
