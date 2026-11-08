# -*- coding: utf-8 -*-
# The player side of intro / recap skip and the next episode (segments.py decides): play() hands the episode over on
# Kodi's Home window, the service starts a Watch when playback starts, and the Watch ticks every 0.5 s on its own thread,
# seeking, notifying and showing the a4k-skip.xml button. Any error ends the Watch and never touches playback.

import json
import threading
import time
import traceback

from ..lib import kodi, logger
from .. import segments
from . import app

HANDOFF = 'a4k.skip'
BUTTON = 800
TICK = 0.5
MODES = ('auto', 'button', 'off')  # the general.skip_* enum values
ACTION_SELECT_ITEM = 7
ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92
ACTION_SHOW_OSD = 24  # OK under the fullscreen video keymap, if Kodi maps keys there and not on this dialog
# actions that leave the countdown alone: play/pause (pause holds it anyway), mouse moves, no action
PASSIVE = (0, 12, 68, 107, 229, 999, ACTION_SELECT_ITEM)

def labels():
    return {
        'intro': kodi.string(33156, 'Skip intro'),
        'recap': kodi.string(33157, 'Skip recap'),
        'next': kodi.string(33158, 'Next episode'),
        'next_in': kodi.string(33161, 'Next episode in %s'),
        'skipped_intro': kodi.string(33159, 'Skipped intro'),
        'skipped_recap': kodi.string(33160, 'Skipped recap'),
    }

def modes():
    out = {}
    for kind in ('intro', 'recap', 'credits'):
        value = kodi.get_setting('general.skip_%s' % kind)
        out[kind] = MODES[int(value)] if value in ('0', '1', '2') else 'auto'
    return out

def hand_off(title):
    # play(): the episode about to play, for the service; anything else clears it
    handoff = {}
    try:
        if title.mediatype == 'episode' and title.tvshowid and title.season and title.episode:
            handoff = {'id': title.imdbnumber, 'tvshowid': title.tvshowid, 'season': int(title.season), 'episode': int(title.episode)}
    except Exception:
        pass
    kodi.xbmcgui.Window(app.HOME_WINDOW).setProperty(HANDOFF, json.dumps(handoff))

def take():
    home = kodi.xbmcgui.Window(app.HOME_WINDOW)
    try: handoff = json.loads(home.getProperty(HANDOFF) or '{}')
    except Exception: handoff = {}
    home.clearProperty(HANDOFF)
    return handoff

class Button(kodi.xbmcgui.WindowXMLDialog):
    # set by Kodi's callbacks, read by the Watch on its next tick
    pressed = False
    back = False
    key = False

    def onClick(self, control_id):
        if control_id == BUTTON:
            self.pressed = True

    def onAction(self, action):
        action_id = action.getId()
        if action_id in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self.back = True
        elif action_id == ACTION_SHOW_OSD:
            self.pressed = True
        elif action_id not in PASSIVE:
            self.key = True

class Watch(object):
    def __init__(self, core, player, monitor, handoff, on_next=None):
        self.core, self.player, self.monitor, self.handoff, self.on_next = core, player, monitor, handoff, on_next
        self.model = None
        self.next_id = None
        self.stopped = False
        self.done = False
        self.dismissed = None
        self.window = None
        self.shown = False
        self.labels = labels()

    def run(self):
        try:
            self.__run()
        except Exception:
            logger.error('skip: %s' % traceback.format_exc())
        finally:
            self.hide()

    def __playing(self):
        # the playing item is the episode play() handed off
        for _ in range(40):
            if self.stopped or self.monitor.abortRequested():
                return False
            try:
                if self.player.isPlayingVideo() and self.player.getVideoInfoTag().getIMDBNumber() == self.handoff['id']:
                    return True
            except Exception:
                pass
            self.monitor.waitForAbort(TICK)
        return False

    def __run(self):
        mode = modes()
        if set(mode.values()) == {'off'} or not self.__playing():
            return
        found = segments.lookup(self.core.db, self.handoff['tvshowid'], self.handoff['season'], self.handoff['episode'])
        if found['credits'] and mode['credits'] != 'off':
            self.next_id = self.find_next()
        self.model = segments.Skip(found, mode, bool(self.next_id))
        if not self.model.segments and not self.next_id:
            return
        while not self.stopped and not self.monitor.abortRequested() and self.player.isPlayingVideo():
            try:
                self.step(time.monotonic())
            except RuntimeError:  # the player stopped between the check and the call
                break
            if self.monitor.waitForAbort(TICK):
                break

    def find_next(self):
        try:
            core = self.core
            episodes = core.query(core, core.utils.DictAsObject({'type': 'seasons', 'id': self.handoff['tvshowid'], 'silent': True}))
            return segments.next_episode(episodes if isinstance(episodes, list) else [], self.handoff['season'],
                                         self.handoff['episode'], core.date.today())
        except Exception:
            logger.notice('skip: no next episode: %s' % traceback.format_exc())
            return None

    def step(self, now):
        xbmc = kodi.xbmc
        tick = self.model.tick(self.player.getTime(), self.player.getTotalTime(), not xbmc.getCondVisibility('Player.Paused'), now)
        if tick.seek_to is not None:
            self.player.seekTime(tick.seek_to)
            kodi.notification(self.labels['skipped_%s' % tick.toast])
        if tick.fire_next:
            return self.play_next()

        window = self.window
        if window and (window.pressed or window.back or window.key):
            pressed, back, key = window.pressed, window.back, window.key
            window.pressed = window.back = window.key = False
            if back or key:
                self.model.cancel_countdown()
            if back and tick.button in ('intro', 'recap'):
                self.dismissed = tick.button
            if pressed and tick.button == 'next':
                return self.play_next()
            if pressed and tick.button_seek is not None:
                self.player.seekTime(tick.button_seek)
                return self.hide()

        if tick.button != self.dismissed:
            self.dismissed = None
        if not tick.button or tick.button == self.dismissed or xbmc.getCondVisibility('Window.IsVisible(videoosd)'):
            return self.hide()
        if tick.button == 'next' and self.model.countdown_active() and tick.countdown is not None:
            label = self.labels['next_in'] % tick.countdown
        else:
            label = self.labels[tick.button]
        self.show(label)

    def show(self, label):
        if not self.window:
            self.window = Button('a4k-skip.xml', kodi.addon_path, 'Default', '1080i')
        self.window.setProperty('a4k.label', label)
        if not self.shown:
            self.shown = True
            self.window.show()

    def hide(self):
        if self.window and self.shown:
            self.shown = False
            self.window.close()

    def play_next(self):
        if self.done or not self.next_id:
            return
        self.done = self.stopped = True
        self.hide()
        if self.on_next:
            self.on_next()
        kodi.xbmc.executebuiltin('PlayMedia(%s?action=play&type=&id=%s)' % (app.PLUGIN, self.next_id))

    def ended(self):
        # the natural end: with the auto countdown running it counts as Next episode
        self.stopped = True
        if self.model and self.model.next_on_natural_end():
            self.play_next()

def start(core, player, monitor, on_next=None):
    # onPlayBackStarted: a Watch for the handed-off episode, None for anything else
    handoff = take()
    if not handoff.get('tvshowid'):
        return None
    watch = Watch(core, player, monitor, handoff, on_next)
    threading.Thread(target=watch.run).start()
    return watch
