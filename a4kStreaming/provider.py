# -*- coding: utf-8 -*-

__meta_data = None
# source package type, named by the provider package
__sources_type = 'torrent'

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
    return 'providers.%s.en.%s' % (__meta(core).name, __sources_type)

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
            try:  # install=0/1 from a plugin URL arrives as a string
                selection = int(params.install)
            except (TypeError, ValueError):
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

def __search_timeout(core):
    return int(core.kodi.get_setting('general.search_timeout') or 40)

# seconds the quick sources get before the full search takes over
quick_wait = 5

def __aligned(values, count, fill):
    values = list(values or [])[:count]
    return values + [fill] * (count - len(values))

def __check_pm(core, apikey, hashes):
    # one batched call for every hash; a short answer is padded so it can never mark the wrong row, any failure means nothing is cached
    try:
        response = core.request.execute(core, core.debrid.premiumize_check(apikey, hashes))
        parsed = core.json.loads(response.content)
        return {
            'status': [status is True for status in __aligned(parsed['response'], len(hashes), False)],
            'filesize': __aligned(parsed.get('filesize'), len(hashes), 0),
        }
    except:
        return { 'status': [False] * len(hashes), 'filesize': [0] * len(hashes) }

def __split(core, title, raw, quick=False):
    hashes = list(raw.keys())
    # on the calling thread, so the check reuses its keep-alive session; quick sources list cached rows only
    apikey = core.utils.get_premiumize_apikey(core)
    if quick:
        pm = { 'status': [True] * len(hashes), 'filesize': [0] * len(hashes) }
    else:
        pm = __check_pm(core, apikey, hashes) if apikey and hashes else None

    results = {}
    cached = {}
    for i, hash in enumerate(hashes):
        result = raw[hash].copy()
        result['ref'] = title

        size = 0
        if pm and pm['status'][i] and result['package'] == 'single':
            try: size = float(pm['filesize'][i]) / 1024 / 1024 / 1024
            except: pass
        if size <= 0:
            size = float(result['size'] or 0) / 1024
        result['size'] = round(size, 1)

        result['title_mismatch'], result['episode_title_hit'] = core.utils.rank_guards(result['release_title'], title)
        core.utils.cleanup_result(result)
        results[hash] = result

        if pm and pm['status'][i]:
            cached_result = result.copy()
            cached_result['debrid'] = 'PM'
            cached_result['title_with_debrid'] = 'PM  |  %s' % result['title']
            cached['PM%s' % hash] = cached_result

    return core.utils.DictAsObject({ 'results': results, 'cached': cached, 'quick': quick })

def __call_source(core, source, title, apikeys):
    if title.mediatype == 'movie':
        try:
            return source.movie(title.title, title.year, title.imdbnumber, apikeys=apikeys)
        except Exception as e:
            if 'movie() takes' in str(e):
                return source.movie(title.title, title.year, apikeys=apikeys)
            core.logger.notice(core.traceback.format_exc())
            return []
    simple_info = {
        'show_title': title.tvshowtitle,
        'show_aliases': [],
        'year': title.year,
        'country': title.country,
        'episode_title': title.title,
        'season_number': str(title.season),
        'episode_number': str(title.episode),
        'no_seasons': str(title.seasons[-1]),
        'is_airing': title.is_airing
    }
    all_info = { 'info': { 'tvshow.imdb_id': title.tvshowid } }
    return source.episode(simple_info, all_info, apikeys=apikeys)

def __quick_sources(core):
    # the provider package's quick sources (fast, debrid-aware, cached rows only), minus the ones switched off in
    # Manage; older packages have no such list
    try: names = core.importlib.import_module('providers.%s.en' % __meta(core).name).get_quick()
    except Exception: return []
    provider = core.cache.get_provider()
    return [name for name in names if provider.get(name.upper(), False)]

def __query_quick(core, params, names, apikey):
    # each quick source in its own thread for at most quick_wait seconds; None when one fails or the time runs out,
    # and a late answer lands in a dict nobody reads
    rows = {}
    failed = []

    def get_sources(name):
        try:
            source = core.importlib.import_module(__sources_module_name(core) + ('.%s' % name.lower())).sources()
            for result in __call_source(core, source, params.title, { 'pm': apikey }):
                hash = (result.get('hash', None) or '').lower().strip('"\'\\/')
                if hash and result.get('debrid', None):
                    # the source's own link embeds the debrid key: play through the debrid service by hash instead
                    result.pop('url', None)
                    result['hash'] = hash
                    result[core.utils.result_link_key] = core.utils.source_link(hash)
                    rows.setdefault(hash, result)
        except Exception:
            failed.append(name)

    threads = [core.threading.Thread(target=get_sources, args=(name,)) for name in names]
    deadline = core.time.time() + quick_wait
    for thread in threads:
        thread.daemon = True
        thread.start()
    for thread in threads:
        thread.join(max(0, deadline - core.time.time()))

    if failed or any(thread.is_alive() for thread in threads):
        return None
    return dict(rows)

def __query_providers(core, params):
    provider = core.cache.get_provider()

    sources = {}
    for key in provider:
        if not provider[key] or sources.get(key, None):
            continue

        try:
            source = core.importlib.import_module(__sources_module_name(core) + ('.%s' % key.lower()))
            sources[key] = source.sources()
        except: pass

    if len(sources) == 0:
        return {}

    threads = []
    search = lambda: None
    search.raw = {}
    search.counts = {}

    for key in sources.keys():
        def get_sources(key):
            source = sources[key]
            results = []
            try:
                results += __call_source(core, source, params.title, {})

                for result in results:
                    result['hash'] = (result.get('hash', None) or '').lower().strip('"\'\\/')
                    if result['hash']:
                        search.raw.setdefault(result['hash'], result)

            except Exception as e:
                core.logger.notice(e)
            finally:
                search.counts[key] = len(results)
                sources.pop(key)

        thread = core.threading.Thread(target=get_sources, args=(key,))
        threads.append(thread)

    from .ui import sheets
    progress = sheets.progress()
    progress_total = len(sources)

    def progress_msg():
        line1 = '[COLOR gray]Results[/COLOR]: [B]%s[/B] [COLOR gray]|[/COLOR] [COLOR gray]Time left[/COLOR]: [B]%ss[/B]' % (len(search.raw), max(0, int((deadline - core.utils.time_ms()) / 1000)))

        done = sorted(list(search.counts.items()), key=lambda kv: (-kv[1], kv[0]))
        pending = sorted(list(sources.keys()))
        max_visible = 3
        done_names = ' [COLOR gray]|[/COLOR] '.join(['%s [B]%s[/B]' % kv for kv in done[:max_visible]])
        if len(done) > max_visible:
            done_names += '[COLOR gray]...[/COLOR]'
        pending_names = ' [COLOR gray]|[/COLOR] '.join(pending[:max_visible])
        if len(pending) > max_visible:
            pending_names += '[COLOR gray]...[/COLOR]'

        line2 = '[COLOR gray]Done:[/COLOR] [B]%s/%s[/B] %s' % (len(done), progress_total, done_names)
        line3 = '[COLOR gray]Pending:[/COLOR] [B]%s[/B] %s' % (len(pending), pending_names)

        msg = [line1 + '\n' + line2 + '\n' + line3]

        msg = [core.utils.re.sub(r' ', '  ', line) for line in msg]
        return msg

    search.dialog = False
    def canceled():
        return search.dialog and progress.iscanceled()

    def update_progress():
        if search.dialog:
            done = float(progress_total - len(sources)) / progress_total
            elapsed = float(core.utils.time_ms() - search_start) / (deadline - search_start)
            progress.update(int(min(1, max(done, elapsed)) * 100), *progress_msg())

    running = dict(sources)
    start_time = params.start_time or core.utils.time_ms()
    search_start = core.utils.time_ms()
    deadline = search_start + __search_timeout(core) * 1000
    for thread in threads:
        thread.daemon = True
        thread.start()

    # past the deadline or on cancel, return what is in and let the stragglers finish in the background
    while not canceled() and core.utils.time_ms() < deadline and any(thread.is_alive() for thread in threads):
        # the dialog waits 1 s so fast searches do not flash it; the provider searches do not wait
        if not search.dialog and core.utils.time_ms() - start_time >= 1000:
            progress.create(core.kodi.addon_name, *progress_msg())
            search.dialog = True
        core.kodi.xbmc.sleep(150)
        update_progress()

    for key in list(sources.keys()):
        try: running[key].cancel_operations()
        except: pass

    if search.dialog:
        progress.close()
    # a copy: threads still running write into search.raw after this returns
    return dict(search.raw)

def __read_search_cache(core, title):
    cache = core.cache.get_last_results()
    raw = {}
    try:
        # packs found for a sibling episode are stored under the season and show ids
        for key in [title.imdbnumber, title.tvshowseasonid, title.tvshowid]:
            if key and key in cache:
                raw.update(cache[key]['results'])
                cache[key]['time'] = core.time.time()
    except:
        return {}
    if raw:
        core.cache.save_last_results(cache)
    return raw

def __write_search_cache(core, title, raw):
    cache = core.cache.get_last_results()
    now = core.time.time()
    cache[title.imdbnumber] = { 'time': now, 'results': raw }
    if title.tvshowid:
        for key, package in [(title.tvshowseasonid, 'season'), (title.tvshowid, 'show')]:
            packs = dict((hash, result) for hash, result in raw.items() if result.get('package', None) == package)
            if packs:
                cache[key] = { 'time': now, 'results': packs }
    while len(cache) > 20:
        cache.pop(min(cache, key=lambda key: cache[key].get('time', 0)))
    core.cache.save_last_results(cache)

def __search(core, params):
    # quick sources first unless the full search is asked for, by the caller or by the setting; nothing from them
    # in time means the full search
    apikey = core.utils.get_premiumize_apikey(core)
    if apikey and not params.full and not core.kodi.get_bool_setting('general.search_all_providers'):
        names = __quick_sources(core)
        if names:
            with core.kodi.busy_dialog():
                raw = __query_quick(core, params, names, apikey)
                if raw:
                    return __split(core, params.title, raw, quick=True)

    # the slow provider search is cached, the cheap debrid split is redone on every read so cached rows never go stale
    raw = {} if params.refresh else __read_search_cache(core, params.title)
    if not raw:
        raw = __query_providers(core, params)
        if raw:
            __write_search_cache(core, params.title, raw)
    with core.kodi.busy_dialog():
        return __split(core, params.title, raw)

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
