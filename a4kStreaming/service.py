# -*- coding: utf-8 -*-

def start(api):
    core = api.core
    from .imdb import cursor_ttl
    from .ui import app as ui_app
    from .ui import skip
    monitor = core.kodi.xbmc.Monitor()

    class XBMCPlayer(core.kodi.xbmc.Player):
        def onPlayBackStarted(): pass
        def onPlayBackEnded(): pass
        def onPlayBackStopped(): pass

    player = XBMCPlayer()
    watched = lambda: None
    watched.playing_imdb_id = None
    watched.play_count = None
    watched.time_played = None
    watched.total_time = None

    update = lambda: None
    update.last_check = None
    # the first pre-warm of the home rows waits for Kodi to settle, then repeats once per gallery cache TTL
    update.last_prewarm = core.time.time() - cursor_ttl + 10

    def reset_vars():
        watched.playing_imdb_id = None
        watched.play_count = None
        watched.time_played = None
        watched.total_time = None

    def update_playing_imdb_id(retry):
        reset_vars()
        core.kodi.xbmc.sleep(5000)
        try:
            video_meta = player.getVideoInfoTag()
            watched.playing_imdb_id = video_meta.getIMDBNumber()
            watched.play_count = video_meta.getPlayCount()
        except: update_playing_imdb_id(retry=False) if retry else None

    def mark_as_watched(finished=False):
        # finished: the next episode starts from the credits, which counts as watching to the end
        try:
            if not watched.playing_imdb_id or (finished and watched.play_count):
                return
            if not finished and (not watched.time_played or not watched.total_time or watched.time_played / watched.total_time < 0.90):
                return
            core.profile(core, core.utils.DictAsObject({ 'type': 'mark_as_watched', 'id': watched.playing_imdb_id, 'silent': True }))
        finally:
            reset_vars()

    # intro / recap skip and the next episode for the playing episode (ui/skip.py)
    skip_watch = lambda: None
    skip_watch.current = None

    def started():
        if skip_watch.current:
            skip_watch.current.stopped = True
        skip_watch.current = skip.start(core, player, monitor, on_next=lambda: mark_as_watched(finished=True))
        update_playing_imdb_id(retry=True)

    def ended(natural):
        current, skip_watch.current = skip_watch.current, None
        if current and natural:
            current.ended()
        elif current:
            current.stopped = True
        mark_as_watched()

    player.onPlayBackStarted = started
    player.onPlayBackEnded = lambda: ended(natural=True)
    player.onPlayBackStopped = lambda: ended(natural=False)

    while not monitor.abortRequested():
        if monitor.waitForAbort(2):
            break

        if not update.last_check or core.time.time() - update.last_check >= 3600:
            update.last_check = core.time.time()
            thread = core.threading.Thread(target=core.provider, args=(core, core.utils.DictAsObject({ 'type': 'new_version_check', 'silent': True })))
            thread.start()

        if core.time.time() - update.last_prewarm >= cursor_ttl:
            update.last_prewarm = core.time.time()
            core.threading.Thread(target=ui_app.prewarm).start()

        if watched.play_count and watched.play_count > 0:
            continue

        has_video = (core.kodi.xbmc.getCondVisibility('VideoPlayer.Content(movies)') or core.kodi.xbmc.getCondVisibility('VideoPlayer.Content(episodes)'))
        has_video_duration = core.kodi.xbmc.getCondVisibility('Player.HasDuration')
        if not has_video or not has_video_duration:
            continue

        if not watched.total_time:
            try: watched.total_time = player.getTotalTime()
            except: pass

        try: watched.time_played = player.getTime()
        except: pass
