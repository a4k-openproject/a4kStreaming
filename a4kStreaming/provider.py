# -*- coding: utf-8 -*-

__meta_data = None

def __meta(core):
    global __meta_data

    if not __meta_data:
        meta = core.utils.get_json(core.utils.provider_data_dir, 'meta.json')
        __meta_data = core.utils.DictAsObject(meta)

    return __meta_data

def __new_version_check(core, params):
    global __meta_data

    __meta_data = None
    if not __meta(core).name:
        if not params.silent:
            core.kodi.notification('Provider not installed')
        return

    local_meta = __meta(core)
    request = {
        'method': 'GET',
        'url': local_meta.remote_meta
    }
    response = core.request.execute(core, request)
    if response.status_code != 200:
        if not params.silent:
            core.kodi.notification('Something went wrong. Check logs')
            core.logger.notice(response.text)
        return
    remote_meta = core.utils.DictAsObject(core.json.loads(response.content))
    if core.utils.versiontuple(remote_meta.version) <= core.utils.versiontuple(local_meta.version):
        if not params.silent:
            core.kodi.notification('Latest version already installed')
        return
    if not params.silent:
        core.kodi.notification('Installing new version v%s' % remote_meta.version)
    __install(core, core.utils.DictAsObject({ 'install': 1, 'zip_url': '%s%s-%s.zip' % (remote_meta.update_directory, remote_meta.name, remote_meta.version) }))

def __sources_module_name(core):
    return 'providers.%s.en.%s' % (__meta(core).name, 'torrent')

def __update_config(core):
    provider = core.cache.get_provider()
    try: sources = core.importlib.import_module(__sources_module_name(core)).__all__
    except: sources = []
    sources = [source.upper() for source in sources]

    provider_sources = list(provider.keys())
    for source in provider_sources:
        if source not in sources:
            provider.pop(source)

    for source in sources:
        if provider.get(source, None) is None:
            provider[source] = True

    core.cache.save_provider(provider)

def __install(core, params):
    global __meta_data

    if params.init:
        if core.os.path.exists(core.utils.provider_data_dir) and core.os.path.exists(core.utils.provider_sources_dir) and core.os.path.exists(core.utils.provider_modules_dir):
            __update_config(core)
            return

    zip_name = 'provider.zip'
    zip_perm_path = core.os.path.join(core.kodi.addon_profile, zip_name)

    try:
        if not params.init:
            if params.install:
                selection = params.install
            else:
                selection = core.kodi.xbmcgui.Dialog().select(
                    'Install provider',
                    ['From File', 'From URL'],
                )

            zip_path = None
            if selection == 0:
                if params.zip_path:
                    zip_path = params.zip_path
                else:
                    zip_path = core.kodi.xbmcgui.Dialog().browse(1, 'Choose provider zip', '', '.zip', True, False)
                    if zip_path.startswith('ftp://'):
                        zip_path = core.utils.download_zip(core, zip_path, zip_name)
                if not zip_path:
                    return
            elif selection == 1:
                if params.zip_url:
                    zip_url = params.zip_url
                else:
                    keyboard = core.kodi.xbmc.Keyboard('', 'Enter provider zip URL')
                    keyboard.doModal()
                    if not keyboard.isConfirmed():
                        return
                    zip_url = keyboard.getText()

                zip_path = core.utils.download_zip(core, zip_url, zip_name)
            else:
                return

            if zip_path != zip_perm_path:
                core.utils.shutil.copyfile(zip_path, zip_perm_path)

        elif not core.os.path.exists(zip_perm_path):
            return

        core.utils.extract_zip(zip_perm_path, core.utils.provider_data_dir)
        try:
            core.utils.shutil.rmtree(core.utils.provider_sources_dir, ignore_errors=True)
            core.os.rename(core.os.path.join(core.utils.provider_data_dir, core.os.path.basename(core.utils.provider_sources_dir)), core.utils.provider_sources_dir)
            core.utils.shutil.rmtree(core.utils.provider_modules_dir, ignore_errors=True)
            core.os.rename(core.os.path.join(core.utils.provider_data_dir, core.os.path.basename(core.utils.provider_modules_dir)), core.utils.provider_modules_dir)
        except:
            if not params.init:
                core.kodi.notification('Unsupported provider')
            return

        __meta_data = None
        __update_config(core)

        if not params.init:
            core.kodi.notification('%s installed v%s' % (__meta(core).name, __meta(core).version))
    except Exception as e:
        if not params.init:
            core.kodi.notification('Something went wrong. Check logs')
        core.logger.notice(e)
        return

def __manage(core, params):
    if not __meta(core).name:
        core.kodi.notification('Provider not installed')
        return

    provider = core.cache.get_provider()
    sources = list(provider.keys())
    sources.sort()

    multiselect = core.kodi.xbmcgui.Dialog().multiselect(
        '%s v%s' % (__meta(core).name, __meta(core).version),
        sources,
        preselect=[i for i, key in enumerate(sources) if provider[key]]
    )

    if not multiselect:
        return

    for i, key in enumerate(sources):
        provider[key] = True if i in multiselect else False

    core.cache.save_provider(provider)

def __search(core, params):
    provider = core.cache.get_provider()
    if len(provider) == 0:
        return {}

    sources = {}

    use_recommended = core.kodi.get_bool_setting('provider.use_recommended')
    recommended = core.utils.recommended

    if use_recommended:
        try:
            source = core.importlib.import_module(__sources_module_name(core) + ('.%s' % recommended.lower()))
            sources[recommended] = source.sources()
        except: pass

    if len(sources) == 0 or not use_recommended:
        use_recommended = False
        for key in provider:
            if not provider[key] or sources.get(key, None):
                continue

            try:
                source = core.importlib.import_module(__sources_module_name(core) + ('.%s' % key.lower()))
                sources[key] = source.sources()
            except: pass

    threads = []
    search = lambda: None
    search.results = {}
    search.cached = {}

    premiumize_apikey = core.utils.get_premiumize_apikey(core)
    realdebrid_apikey = core.utils.get_realdebrid_apikey(core)
    alldebrid_apikey = core.utils.get_alldebrid_apikey(core)
    use_direct_urls = False

    for key in sources.keys():
        def get_sources(key):
            source = sources[key]
            results = []
            try:
                apikeys = {}
                if use_direct_urls:
                    apikeys = {
                        'pm': premiumize_apikey,
                        'rd': realdebrid_apikey,
                        'ad': alldebrid_apikey
                    }

                if params.title.mediatype == 'movie':
                    try:
                        results += source.movie(params.title.title, params.title.year, params.title.imdbnumber, apikeys=apikeys)
                    except Exception as e:
                        if 'movie() takes' in str(e):
                            results += source.movie(params.title.title, params.title.year, apikeys=apikeys)
                        else:
                            core.logger.notice(core.traceback.format_exc())
                else:
                    simple_info = {
                        'show_title': params.title.tvshowtitle,
                        'show_aliases': [],
                        'year': params.title.year,
                        'country': params.title.country,
                        'episode_title': params.title.title,
                        'season_number': str(params.title.season),
                        'episode_number': str(params.title.episode),
                        'no_seasons': str(params.title.seasons[-1]),
                        'is_airing': params.title.is_airing
                    }
                    all_info = { 'info': { 'tvshow.imdb_id': params.title.tvshowid } }
                    results += source.episode(simple_info, all_info, apikeys=apikeys)

                if len(results) <= 0:
                    return

                hashes = [item['hash'].lower().strip('"\'\\/') for item in results]

                def check_pm(apikey):
                    try:
                        request = core.debrid.premiumize_check(apikey, hashes)
                        response = core.request.execute(core, request)
                        parsed_response = core.json.loads(response.content)
                        return { 'status': parsed_response['response'], 'filesize': parsed_response['filesize'], 'files': None }
                    except:
                        return { 'status': [], 'filesize': [], 'files': None }

                def check_rd(apikey):
                    check_result = { 'status': [], 'filesize': [], 'files': [] }
                    try:
                        auth = core.utils.rd_auth_query_params(core, apikey)
                        hashes_path = '/'.join(hashes)
                        request = core.debrid.realdebrid_check(auth, hashes_path)
                        response = core.request.execute(core, request)
                        if response.status_code == 500:
                            response = core.request.execute(core, request)
                        parsed_response = core.json.loads(response.content)

                        for key in parsed_response.keys():
                            parsed_response[key.lower()] = parsed_response[key]

                        for key in hashes:
                            parsed_result = parsed_response.get(key, {})
                            if isinstance(parsed_result, list):
                                parsed_result = {}
                            status = len(parsed_result.get('rd', [])) > 0
                            filesize = 0
                            files = None
                            if status:
                                try:
                                    files = {}
                                    for file_result in parsed_result['rd']:
                                        for file_id in file_result.keys():
                                            files[file_id] = file_result[file_id]
                                    filesize = sum(f.get('filesize', 0) for f in files.values())
                                except:
                                    status = False
                            check_result['status'].append(status)
                            check_result['filesize'].append(filesize)
                            check_result['files'].append(files)

                        return check_result
                    except:
                        return check_result

                def check_ad(apikey):
                    try:
                        auth = core.utils.ad_auth_query_params(core, apikey)
                        request = core.debrid.alldebrid_check(auth, hashes)
                        response = core.request.execute(core, request)
                        parsed_response = core.json.loads(response.content)
                        response_status = {}
                        for magnet in parsed_response.get('data', parsed_response)['magnets']:
                            response_status[magnet['hash'].lower()] = magnet['instant']

                        return { 'status': [response_status[hash] for hash in hashes], 'filesize': None, 'files': None }
                    except:
                        return { 'status': [], 'filesize': None, 'files': None }

                def sanitize_results(check, debrid):
                    for i, status in enumerate(check['status']):
                        result = results[i].copy()
                        result['ref'] = params.title

                        size = 0
                        if not use_recommended and status and check['filesize']:
                            tmpsize = float(check['filesize'][i]) / 1024 / 1024 / 1024
                            if result['package'] == 'single':
                                size = tmpsize
                            elif check['files'] and check['files'][i]:
                                size = tmpsize / len(check['files'][i])
                        if size <= 0:
                            size = float(result['size']) / 1024
                        result['size'] = round(size, 1)

                        core.utils.cleanup_result(result)
                        result['hash'] = result['hash'].lower()
                        if search.results.get(result['hash'], None) is None:
                            search.results[result['hash']] = result

                        if status:
                            result_copy = result
                            result_copy['title_with_debrid'] = '%s  |  %s' % (debrid, result['title'])
                            result_copy['debrid'] = debrid
                            if check['files'] and len(check['files']) > i:
                                result_copy['debrid_files'] = check['files'][i]
                            search.cached['%s%s' % (debrid, result['hash'])] = result_copy

                def pm(apikey):
                    sanitize_results(check_pm(apikey), 'PM')
                def rd(apikey):
                    sanitize_results(check_rd(apikey), 'RD')
                def ad(apikey):
                    sanitize_results(check_ad(apikey), 'AD')

                def sanitize_direct_url_results():
                    for result in results:
                        result = result.copy()
                        result['ref'] = params.title
                        size = float(result['size']) / 1024
                        result['size'] = round(size, 1)
                        core.utils.cleanup_result(result)
                        if search.results.get(result['url'], None) is None:
                            search.results[result['url']] = result
                        result['title_with_debrid'] = '%s  |  %s' % (result['debrid'], result['title'])
                        search.cached['%s%s' % (result['debrid'], result['url'])] = result

                if use_direct_urls:
                    sanitize_direct_url_results()
                else:
                    threads = []
                    if premiumize_apikey:
                        threads.append(core.threading.Thread(target=pm, args=(premiumize_apikey,)))
                    if realdebrid_apikey:
                        threads.append(core.threading.Thread(target=rd, args=(realdebrid_apikey,)))
                    if alldebrid_apikey:
                        threads.append(core.threading.Thread(target=ad, args=(alldebrid_apikey,)))

                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join()

            except Exception as e:
                core.logger.notice(e)
            finally:
                sources.pop(key)

        thread = core.threading.Thread(target=get_sources, args=(key,))
        threads.append(thread)

    progress = core.kodi.xbmcgui.DialogProgress()
    progress_total = len(sources)

    def progress_msg():
        quality = core.OrderedDict([('4K', 0), ('1080P', 0), ('720P', 0), ('SD', 0), ('CAM', 0 )])
        for key in list(search.cached.keys()):
            quality[search.cached[key]['quality']] += 1

        line1 = '[COLOR gray]Total[/COLOR]: [B]%s[/B] [COLOR gray]|[/COLOR] [COLOR gray]Cached[/COLOR]: [B]%s[/B]' % (len(search.results), len(search.cached))
        line2 = ' [COLOR gray]|[/COLOR] '.join(['[COLOR gray]%s:[/COLOR] [B]%s[/B]' % (key, quality[key]) for key in quality])

        pending = sorted(list(sources.keys()))
        max_visible = 2
        pending_names = ' [COLOR gray]|[/COLOR] '.join(pending[:max_visible])
        if len(sources) > max_visible:
            pending_names += '[COLOR gray]...[/COLOR]'

        line3 = '[COLOR gray]Pending:[/COLOR] [B]%s[/B] [COLOR gray](%s)[/COLOR]' % (len(pending), pending_names)

        if core.utils.py2:
            msg = [line1, line2, line3]
        else:
            msg = [line1 + '\n' + line2 + '\n' + line3]

        msg = [core.utils.re.sub(r' ', '  ', line) for line in msg]
        return msg

    search.dialog = False
    def canceled():
        return search.dialog and progress.iscanceled()

    def update_progress():
        if search.dialog:
            progress.update(int(float(progress_total - len(sources)) / progress_total * 100), *progress_msg())

    def close_progress():
        if search.dialog:
            progress.close()

    search.done = False
    def execute():
        time_after_start = core.utils.time_ms() - params.start_time
        if time_after_start < 1000:
            core.kodi.xbmc.sleep(int(round(1000 - time_after_start)))
        if not use_recommended:
            progress.create(core.kodi.addon_name, *progress_msg())
            search.dialog = True

        chunk_size = len(sources)
        for chunk in core.utils.chunk(threads, chunk_size):
            if canceled():
                break

            for thread in chunk:
                thread.start()
                if canceled():
                    break

            for thread in chunk:
                thread.join()
                if canceled():
                    break
        search.done = True

    exec_thread = core.threading.Thread(target=execute)
    exec_thread.start()

    while (not canceled() and not search.done):
        core.kodi.xbmc.sleep(1000)
        update_progress()

    try:
        for source in sources:
            source.cancel_operations()
    except:
        pass

    close_progress()
    return core.utils.DictAsObject({ 'results': search.results, 'cached': search.cached })

def provider_meta(core):
    return __meta(core)

def provider(core, params):
    if params.type == 'install':
        return __install(core, params)
    elif params.type == 'new_version_check':
        return __new_version_check(core, params)
    elif params.type == 'manage':
        return __manage(core, params)
    elif params.type == 'search':
        return __search(core, params)
    else:
        core.not_supported()
