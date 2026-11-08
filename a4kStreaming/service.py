# -*- coding: utf-8 -*-

FULLSCREEN_VIDEO = 12005
# windows a play may show in place of the video without the user leaving it: the screensaver (dim on pause)
STILL_WATCHING = (FULLSCREEN_VIDEO, 12900)
TICK = 0.5  # s between looks while a play the add-on started is on
IDLE = 2  # s otherwise
SAVE_EVERY = 15  # s between progress writes during a play

class BackStop(object):
    # Back from the video goes to the windows and leaves the play running behind them. With the Back stops playback
    # setting on, a play the add-on started stops once its video window has been on screen and another window took its
    # place for two looks in a row. Dialogs over the video (the OSD, the info, the skip button) keep the video window
    # the current one, so they never count.
    def __init__(self):
        self.seen = False
        self.away = 0

    def step(self, window_id, enabled):
        # True when the play should stop now
        if window_id in STILL_WATCHING:
            self.seen = self.seen or window_id == FULLSCREEN_VIDEO
            self.away = 0
            return False
        if not enabled or not self.seen:
            return False
        self.away += 1
        return self.away == 2

def start(api):
    core = api.core
    from .imdb import cursor_ttl
    from .ui import app as ui_app
    from .ui import skip
    from . import kodi_mode, progress
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
    # the play the add-on started (the hand-off's Continue Watching entry), None for any other
    ours = lambda: None
    ours.meta = None
    ours.start = 0  # Resume from: seconds to seek to once the stream plays (Kodi starts a resolved plugin play at 0)
    ours.saved = 0
    ours.back = BackStop()

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
        core.kodi.xbmc.sleep(5000)
        try:
            video_meta = player.getVideoInfoTag()
            watched.playing_imdb_id = video_meta.getIMDBNumber()
            watched.play_count = video_meta.getPlayCount()
        except: update_playing_imdb_id(retry=False) if retry else None
        if ours.meta and ours.meta.get('id') != watched.playing_imdb_id:
            ours.meta = None  # a hand-off whose stream never started, taken by another play

    def save_progress(finished=False):
        if not ours.meta or not watched.total_time or ours.start:  # a resume not reached yet keeps the old position
            return
        ours.saved = core.time.time()
        store = progress.record(progress.load(), ours.meta, watched.time_played or 0, watched.total_time, progress.now(), finished)
        progress.save(store)

    def mark_as_watched(finished=False):
        # finished: the next episode starts from the credits, which counts as watching to the end. A title already
        # rated (watched) is not rated again.
        try:
            save_progress(finished)
            if not watched.playing_imdb_id or watched.play_count:
                return
            if not finished and (not watched.time_played or not watched.total_time or watched.time_played / watched.total_time < 0.90):
                return
            core.profile(core, core.utils.DictAsObject({ 'type': 'mark_as_watched', 'id': watched.playing_imdb_id, 'silent': True }))
        finally:
            reset_vars()
            ours.meta, ours.start = None, 0

    # intro / recap skip and the next episode for the playing episode (ui/skip.py)
    skip_watch = lambda: None
    skip_watch.current = None

    def started():
        if skip_watch.current:
            skip_watch.current.stopped = True
        handoff = skip.take()
        skip_watch.current = skip.start(core, player, monitor, handoff, on_next=lambda: mark_as_watched(finished=True))
        reset_vars()
        ours.meta, ours.saved, ours.back = handoff.get('progress'), core.time.time(), BackStop()
        ours.start = (ours.meta or {}).get('start', 0)
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

    kodi_mode.autoopen(monitor)  # Kodi setup mode: the add-on opens once Kodi's Home is up

    while not monitor.abortRequested():
        if monitor.waitForAbort(TICK if ours.meta else IDLE):
            break

        if not update.last_check or core.time.time() - update.last_check >= 3600:
            update.last_check = core.time.time()
            thread = core.threading.Thread(target=core.provider, args=(core, core.utils.DictAsObject({ 'type': 'new_version_check', 'silent': True })))
            thread.start()

        if core.time.time() - update.last_prewarm >= cursor_ttl:
            update.last_prewarm = core.time.time()
            core.threading.Thread(target=ui_app.prewarm).start()

        has_video = (core.kodi.xbmc.getCondVisibility('VideoPlayer.Content(movies)') or core.kodi.xbmc.getCondVisibility('VideoPlayer.Content(episodes)'))
        has_video_duration = core.kodi.xbmc.getCondVisibility('Player.HasDuration')
        if not has_video or not has_video_duration:
            continue

        if not watched.total_time:
            try: watched.total_time = player.getTotalTime()
            except: pass

        try: watched.time_played = player.getTime()
        except: pass

        if not ours.meta:
            continue
        if ours.start:
            try:
                if player.getVideoInfoTag().getIMDBNumber() == ours.meta.get('id'):
                    player.seekTime(ours.start)
            except Exception:
                pass
            ours.start = 0
            continue
        if ours.back.step(core.kodi.xbmcgui.getCurrentWindowId(), core.kodi.get_setting('general.back_stops') != 'false'):
            player.stop()  # onPlayBackStopped records the position
        elif core.time.time() - ours.saved >= SAVE_EVERY:
            save_progress()
