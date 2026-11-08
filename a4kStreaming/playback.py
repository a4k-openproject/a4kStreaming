# -*- coding: utf-8 -*-

from .listing import (
    __action_menu_style,
    __handle_request_error,
)
from .imdb import (
    query,
)
from .ui import sheets, skip

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

def filter_keys(core, results, keys, mediatype, strict=False):
    # the quality, movie size and Dolby Vision limits; a limit that leaves nothing is lifted with a notice, unless strict
    def narrow(keys, keep, notice):
        kept = [key for key in keys if keep(results[key])]
        if kept or strict:
            return kept
        core.kodi.notification(notice)
        return keys

    max_quality = core.kodi.get_int_setting('general.max_quality') + 1
    quality_list = ['4K', '1080P', '720P', 'SD']
    excluded_quality = quality_list[:len(quality_list) - max_quality]
    if len(excluded_quality) > 0:
        keys = narrow(keys, lambda result: result['quality'] not in excluded_quality, 'No results for specified quality. Showing all results.')

    if mediatype == 'movie':
        max_movie_size = core.kodi.get_int_setting('general.max_movie_size')
        keys = narrow(keys, lambda result: result['size'] <= max_movie_size, 'No results for specified movie size. Showing all results.')

    if not core.kodi.get_bool_setting('general.dolby_vision_allowed'):
        return [key for key in keys if results[key]['hdr'] != 'DV']
    return [key for key in keys if not (results[key]['hdr'] == 'DV' and 'mkv' in results[key])]

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

def sheet_actions(core, params, provider, uncached):
    # [(key, label, detail)]: the rows after the sources, in the TV skin's order: the file pick toggle, then Search all
    # providers (quick sources) or Search again (a full list from the remembered searches), then the uncached sources
    on = bool(params.force_fileselect)
    rows = [('files', core.kodi.string(33144, 'Pick file manually: %s') % ('On' if on else 'Off'),
             core.kodi.string(33146, 'Select a source above to list its files') if on
             else core.kodi.string(33145, 'Select a source, then choose which file inside it to stream'))]
    if provider.quick:
        rows.append(('all', core.kodi.string(33141, 'Search all providers'), ''))
    elif provider.from_cache:
        rows.append(('again', core.kodi.string(33147, 'Search again'), core.kodi.string(33148, 'These results are from an earlier search')))
    if uncached and not provider.quick:
        rows.append(('uncached', core.kodi.string(33142, 'Show uncached sources (%s)') % len(uncached),
                     core.kodi.string(33149, 'Download one to Premiumize, then stream')))
    return rows

def uncached_row(result):
    # an uncached source as the TV skin draws it: a cached row's layout, marked as a download
    label, label2 = sheets.source_row(result)
    return '\u2193  %s' % label, '  ·  '.join(part for part in ('Not cached', 'download to Premiumize', label2) if part)

def uncached_sources(core, uncached, apikey):
    # the uncached list: a pick goes to Premiumize, which is waited on (transfer); the key of the source once it is
    # there, None on Back
    keys = sorted(uncached.keys(), key=lambda key: result_sort_key(uncached[key]))
    selection = 0
    while keys:
        rows = [uncached_row(uncached[key]) for key in keys]
        selection = sheets.select('Uncached sources', ['%s  %s' % row for row in rows], preselect=selection, rows=rows)
        if selection is None or selection < 0:
            return None
        if transfer(core, apikey, uncached[keys[selection]]):
            return keys[selection]
    return None

TRANSFER_POLL = 4  # seconds between the readiness checks
TRANSFER_MAX = 20 * 60  # seconds the wait lasts; the transfer itself stays in Premiumize
TRANSFER_FAILED = ('error', 'banned', 'deleted', 'timeout')

def __pm_json(core, request):
    # Premiumize's answer as a dict, never cached (the progress must be live); {} when it fails
    try:
        response = core.request.execute(core, request, False)
        return core.json.loads(response.content) or {}
    except Exception:
        core.logger.notice(core.traceback.format_exc())
        return {}

def transfer(core, apikey, result):
    # the TV skin's uncached pick: add the source to Premiumize and wait for it with a progress dialog. Ready is a
    # resolve that answers (directdl lists the files only once the cloud copy exists), not the transfer status, which
    # is only the progress text. Cancel asks to keep the transfer or remove it. True once ready
    link = result[core.utils.result_link_key]
    progress = core.kodi.xbmcgui.DialogProgress()
    progress.create('Premiumize', 'Adding to Premiumize…')
    try:
        created = __pm_json(core, core.debrid.premiumize_cache(apikey, link))
        id = created.get('id', None)
        if created.get('status', None) != 'success' and not id and 'already' not in (created.get('message', None) or '').lower() \
                and created.get('error', None) != 'duplicate':
            core.kodi.notification(created.get('message', None) or 'Failed to add to Premiumize')
            return False

        started = core.time.time()
        while True:
            if __pm_json(core, core.debrid.premiumize_resolve(apikey, link)).get('content', None):
                return True
            text, percent = 'Downloading to Premiumize…', 0
            state = next((t for t in __pm_json(core, core.debrid.premiumize_transfers(apikey)).get('transfers', None) or []
                          if id and t.get('id', None) == id), None)
            if state:
                if state.get('status', None) in TRANSFER_FAILED:
                    core.kodi.notification(state.get('message', None) or 'Transfer %s' % state['status'])
                    return False
                percent = int(round(float(state.get('progress', None) or 0) * 100))
                status = 'Premiumize: %s' % state['status'] if state.get('status', None) else text
                text = '\n'.join(part for part in (status, state.get('message', None) or '') if part)
            progress.update(percent, text)

            waited = 0.0
            while waited < TRANSFER_POLL and not progress.iscanceled():
                core.kodi.xbmc.sleep(250)
                waited += 0.25
            if progress.iscanceled():
                progress.close()
                keep = sheets.select('Premiumize', ['Keep downloading in Premiumize', 'Remove from Premiumize'])
                if keep == 1 and id:
                    __pm_json(core, core.debrid.premiumize_transfer_delete(apikey, id))
                    core.kodi.notification('Removed from Premiumize')
                return False
            if core.time.time() - started > TRANSFER_MAX:
                core.kodi.notification('Still downloading in Premiumize: try again later')
                return False
    finally:
        progress.close()

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
    provider_params.full = params.full_search or params.cache_sources
    provider = core.provider(core, provider_params)
    mediatype = provider_params.title.mediatype

    # quick sources with nothing that passes the quality and size limits: the full search takes over
    if provider.quick and not filter_keys(core, provider.cached, list(provider.cached.keys()), mediatype, strict=True):
        provider_params.full = True
        provider = core.provider(core, provider_params)

    if params.cache_sources:
        return provider.results

    uncached = dict((hash, result) for hash, result in provider.results.items() if 'PM%s' % hash not in provider.cached)
    if len(provider.cached) == 0 and not uncached:
        core.kodi.notification('No sources found')
        general.last_action_time = core.utils.time_ms()
        core.cache.save_general(general)
        core.utils.end_action(core, True)
        return

    results = provider.cached

    results_keys = sorted(results.keys(), key=lambda key: result_sort_key(results[key]))
    results_keys = filter_keys(core, results, results_keys, mediatype)

    result_style = '[LIGHT]%s[/LIGHT]'
    autoplay = core.kodi.get_bool_setting('general.autoplay') and not params.force_sourceselect and bool(results_keys)

    last_selected_result = core.cache.get_last_selected_result()
    result_keys_hash = core.utils.hash_data(''.join(results_keys))
    selection = last_selected_result.get(result_keys_hash, 0)

    video_ext = list(map(lambda v: '.%s' % v.upper(), core.utils.video_containers()))
    size = 1048576 * 100

    def resolve_pm():
        request = core.debrid.premiumize_resolve(pm_apikey, result[core.utils.result_link_key])
        response = core.request.execute(core, request)
        parsed_response = core.json.loads(response.content)
        return parsed_response.get('content', [])

    def again():
        general.last_action_time = None
        core.cache.save_general(general)
        return play(core, params)

    # nothing cached: straight to the uncached sources, as the TV skin's picker
    pick = None if results_keys else 'uncached'
    if pick and len(provider.cached) == 0:
        core.kodi.notification('No cached sources found')

    while True:
        if not autoplay and not pick:
            extra = sheet_actions(core, params, provider, uncached)
            selection = sheets.select(
                'Choose source',
                [result_style % results[key].get('title_with_debrid', results[key]['title']) for key in results_keys]
                + [__action_menu_style % label for _, label, _ in extra],
                preselect=selection,
                rows=[sheets.source_row(results[key]) for key in results_keys] + [(label, detail) for _, label, detail in extra],
            )
            if selection is None or selection < 0:
                general.last_action_time = core.utils.time_ms()
                core.cache.save_general(general)
                core.utils.end_action(core, True)
                return
            if selection >= len(results_keys):
                pick = extra[selection - len(results_keys)][0]
            else:
                core.cache.save_last_selected_result({ result_keys_hash: selection })

        if pick == 'files':
            # the toggle row: its label flips in place and keeps the focus
            params.force_fileselect = None if params.force_fileselect else 'true'
            pick = None
            continue
        elif pick == 'all':
            # the full results replace the quick ones
            params.full_search = True
            return again()
        elif pick == 'again':
            # every provider again, past the quick sources and the remembered search, whose entry it rewrites
            params.full_search = True
            params.refresh = True
            return again()
        elif pick == 'uncached':
            pick = None
            key = uncached_sources(core, uncached, pm_apikey)
            if key is None:
                if results_keys:
                    selection = len(results_keys)  # back on the sheet, at its first action row
                    continue
                general.last_action_time = core.utils.time_ms()
                core.cache.save_general(general)
                core.utils.end_action(core, True)
                return
            # in Premiumize now: it plays as a cached source, and stays on the sheet as one
            results = dict(results)
            results[key] = uncached.pop(key)
            results_keys = [key] + results_keys
            selection = 0
            autoplay = False

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

                if len(files) > 1 or (len(files) == 1 and (params.force_fileselect or not filtered and result['package'] in ['show', 'season'])):
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
        selection %= len(results_keys)  # past the last source: the sheet opens on the first

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

    skip.hand_off(provider_params.title)
    core.utils.end_action(core, True, item)
    return link
