# -*- coding: utf-8 -*-

def start(api):
    core = api.core
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

    def mark_as_watched():
        try:
            if not watched.playing_imdb_id or not watched.time_played or not watched.total_time:
                return
            percent_played = watched.time_played / watched.total_time
            if percent_played < 0.90:
                return
            core.profile(core, core.utils.DictAsObject({ 'type': 'mark_as_watched', 'id': watched.playing_imdb_id, 'silent': True }))
        finally:
            reset_vars()

    player.onPlayBackStarted = lambda: update_playing_imdb_id(retry=True)
    player.onPlayBackEnded = lambda: mark_as_watched()
    player.onPlayBackStopped = lambda: mark_as_watched()

    while not monitor.abortRequested():
        if monitor.waitForAbort(2):
            break

        if not update.last_check or core.time.time() - update.last_check >= 3600:
            update.last_check = core.time.time()
            thread = core.threading.Thread(target=core.provider, args=(core, core.utils.DictAsObject({ 'type': 'new_version_check', 'silent': True })))
            thread.start()

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
