# -*- coding: utf-8 -*-
# The Debrid window (a4k-debrid.xml): the Premiumize account in the header, then two tabs. Downloads lists the
# transfers and refreshes them while the window is on screen: every ACTIVE s while one is queued or downloading, every
# IDLE s otherwise, never while a dialog, the player or the loader covers it. Cloud browses the folders, newest first.
# Rows are repainted in place by position (setLabel / setProperty on the items already there), and the focused row's id
# keeps the focus: a list is never reset, as a reset near a running plugin call crashes Kodi 21. A failed request
# keeps the last list and shows a Retry banner; without a key the banner opens Settings. Plays go through the plugin's
# play URL (cloud.py), so Kodi's player asks to resume and gets the subtitle files.

import json
import math
import time
import threading
import traceback
from datetime import datetime

from ..lib import kodi, logger
from . import app, home
from .home import ACTION_PREVIOUS_MENU, ACTION_NAV_BACK, ACTION_CONTEXT_MENU, NO_DIALOG

TABS = 100
CLEAR = 110
BANNER = 120
DOWNLOADS = 200
CLOUD = 300
FAIR_USE = 701
LEFT, RIGHT, UP, DOWN = 1, 2, 3, 4  # Kodi's ACTION_MOVE_*
TAB_NAMES = ((DOWNLOADS, 'Downloads'), (CLOUD, 'Cloud'))

ACTIVE = 2  # s between transfer refreshes while one is queued or downloading
IDLE = 15  # s between them otherwise, and after a failure
TICK = 0.25  # s between looks whether the window is on screen and a refresh is due
TIMEOUT = home.TIMEOUT  # s a Premiumize request may take, so a closing window waits for its threads a bounded time

# the status chips, as the reference app draws them; any other status shows as it comes
CHIPS = {'queued': 'Queued', 'running': 'Downloading', 'waiting': 'Downloading', 'seeding': 'Downloading',
         'finished': 'Finished', 'error': 'Error', 'timeout': 'Error', 'deleted': 'Error'}
BUSY_CHIPS = ('Queued', 'Downloading')
SUBTITLES = ('srt', 'sub', 'ass', 'ssa', 'smi')

UNREACHABLE = 'Premiumize did not answer.'
NO_KEY = 'Add your Premiumize API key in Settings to see your downloads and cloud.'
HELP = {DOWNLOADS: 'OK for Play, Open and Delete.', CLOUD: 'OK opens or plays. Hold OK to delete.'}

class Failure(Exception):
    pass

# what the rows show (pure, tested)

def rounded(fraction):
    # a 0-1 fraction as a whole percent, halves up as the reference app rounds (Python's round() goes to even)
    return min(max(int(math.floor(float(fraction) * 100 + 0.5)), 0), 100)

def chip(status):
    return CHIPS.get(status, status or '')

def percent(transfer):
    # Premiumize's progress is 0-1; a finished transfer without one is done
    progress = transfer.get('progress')
    if progress is None:
        return 100 if transfer.get('status') == 'finished' else 0
    try:
        return rounded(progress)
    except (TypeError, ValueError):
        return 0

def transfer_row(transfer):
    label = chip(transfer.get('status'))
    return {'id': str(transfer.get('id') or ''), 'label': transfer.get('name') or '', 'chip': label,
            'state': label.lower() if label in CHIPS.values() else 'other', 'pct': percent(transfer),
            'msg': transfer.get('message') or '', 'folder': transfer.get('folder_id') or '',
            'file': transfer.get('file_id') or ''}

def size(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return ''
    gb = value / 1024 ** 3
    return '%.1f GB' % gb if gb >= 1 else '%d MB' % round(value / 1024 ** 2)

def day(timestamp):
    try:
        moment = datetime.fromtimestamp(int(timestamp))
    except (TypeError, ValueError, OverflowError, OSError):
        return ''
    return '%s %s' % (moment.day, moment.strftime('%b %Y'))

def is_video(name, containers):
    return '.' in name and name.rsplit('.', 1)[1].upper() in containers

def cloud_rows(content, containers):
    # a folder's items, newest first
    rows = []
    for entry in sorted(content, key=lambda entry: -(entry.get('created_at') or 0)):
        folder = entry.get('type') == 'folder'
        name = entry.get('name') or ''
        rows.append({'id': str(entry.get('id') or ''), 'label': name,
                     'kind': 'folder' if folder else 'video' if is_video(name, containers) else 'file',
                     'meta': 'Folder  ›' if folder else '  ·  '.join(part for part in (size(entry.get('size')),
                                                                                    day(entry.get('created_at'))) if part)})
    return rows

def crumb(body):
    # Cloud › a folder › its subfolder; the root has no parent
    names = [entry.get('name') for entry in body.get('breadcrumbs') or [] if entry.get('parent_id') and entry.get('name')]
    if body.get('parent_id') and body.get('name') and (not names or names[-1] != body['name']):
        names.append(body['name'])
    return '  ›  '.join(['Cloud'] + names)

def account(body, now):
    # (pill text, expired, fair use percent or None, storage text)
    try:
        days = int(math.ceil((float(body.get('premium_until') or 0) - now) / 86400))
    except (TypeError, ValueError):
        days = 0
    pill = 'Premium  ·  %s day%s left' % (days, '' if days == 1 else 's') if days > 0 else 'Expired'
    try:
        fair = rounded(body['limit_used'])
    except (KeyError, TypeError, ValueError):
        fair = None
    stored = size(body.get('space_used'))
    return pill, days <= 0, fair, '%s stored' % stored if stored else ''

def ready(seen, rows):
    # the transfers that turned Finished since the last refresh (seen: id -> chip); none on the first one
    if seen is None:
        return []
    return [row['label'] for row in rows if row['chip'] == 'Finished' and seen.get(row['id'], 'Finished') != 'Finished']

def diff(old, new, focused):
    # what turns the painted rows old into new in place: the positions to repaint, how many items to add (or, negative,
    # drop at the end), and the new position of the focused id (None when it is gone)
    paint = [index for index, row in enumerate(new) if index >= len(old) or old[index] != row]
    ids = [row['id'] for row in new]
    return paint, len(new) - len(old), ids.index(focused) if focused in ids else None

class Schedule(object):
    # when the transfers refresh: at once when the window comes (back) into view, then every ACTIVE s while one runs
    # and IDLE s otherwise; never while hidden
    def __init__(self):
        self.next = 0
        self.hidden = True

    def due(self, now, visible):
        if not visible:
            self.hidden = True
            return False
        if self.hidden:
            self.hidden = False
            return True
        return now >= self.next

    def done(self, now, active):
        self.next = now + (ACTIVE if active else IDLE)

    def soon(self):
        self.next = 0

def plugin_core():
    from .detail import plugin_core
    return plugin_core()

def fetch(core, request):
    # Premiumize's answer as a dict, never from the cache; Failure carries the line the banner shows
    request.setdefault('timeout', TIMEOUT)
    response = core.request.execute(core, request, False)
    try:
        body = json.loads(response.content)
    except (TypeError, ValueError):
        body = None
    if not isinstance(body, dict):
        raise Failure(UNREACHABLE)
    if body.get('status') == 'error':
        raise Failure('Premiumize: %s' % (body.get('message') or 'request failed'))
    return body

def confirm(heading, yes):
    from .settings import confirm
    return confirm(heading, yes)

def select(heading, labels):
    from . import sheets
    return sheets.select(heading, labels)

class Debrid(kodi.xbmcgui.WindowXML):
    error = None
    started = False
    closed = False
    own_id = None
    tab = DOWNLOADS
    folder = ''  # the Cloud folder shown ('' = the root)
    parent = None
    cloud_loaded = False
    cloud_seq = 0  # the last Cloud load started: an older one that answers later is dropped
    account_due = True
    seen = None
    fair = None
    threads = ()
    stopped = None
    over_call = False  # opened from a running play call (the uncached wait): its loader stamp is not ours

    def onInit(self):
        # runs again on every return (after playback, a sheet, Settings): no network here
        try:
            self.getControl(DOWNLOADS)  # raises when the XML did not load
            self.own_id = kodi.xbmcgui.getCurrentWindowId()
            kodi.xbmcgui.Window(app.HOME_WINDOW).setProperty(app.OPEN_WINDOW, str(self.own_id))
            if self.started:
                if self.fair is not None:  # the XML reloads on return (after playback): the bar starts at 0 again
                    self.getControl(FAIR_USE).setPercent(self.fair)
                return
            self.started = True
            self.threads = []
            self.lock = threading.RLock()
            self.stopped = threading.Event()
            self.schedule = Schedule()
            self.rows = {DOWNLOADS: [], CLOUD: []}
            self.tabs = self.getControl(TABS)
            self.tabs.addItems([kodi.xbmcgui.ListItem(label=label, offscreen=True) for _, label in TAB_NAMES])
            self.show_tab(self.tab)
            self.setFocusId(TABS)
            home.spawn(self, self.poll)
        except Exception:
            self.__fail()

    # the refresh thread, alive as long as the window

    def visible(self):
        return kodi.xbmcgui.getCurrentWindowId() == self.own_id and \
            kodi.xbmcgui.getCurrentWindowDialogId() == NO_DIALOG and (self.over_call or not kodi.busy_live())

    def poll(self):
        while not self.stopped.wait(TICK):
            try:
                if self.schedule.due(time.time(), self.visible()):
                    active = False
                    try:
                        active = self.refresh()
                    finally:
                        self.setProperty('a4k.loading', '')  # the loader of the window's first refresh
                        self.schedule.done(time.time(), active)
            except Exception:  # logged; the next tick tries again
                logger.error('debrid refresh failed: %s' % traceback.format_exc())

    def refresh(self):
        # the account (when due) and the transfers; True while one is queued or downloading
        core = plugin_core()
        key = core.utils.get_premiumize_apikey(core)
        if not key:
            self.banner(NO_KEY, 'settings')
            return False
        # the window may close while a request is out: no second request, paint or toast after that
        try:
            if self.account_due:
                body = fetch(core, core.debrid.premiumize_account(key))
                if self.stopped.is_set():
                    return False
                self.paint_account(body)
                self.account_due = False
            rows = [transfer_row(transfer) for transfer in fetch(core, core.debrid.premiumize_transfers(key)).get('transfers') or []]
        except Failure as failure:
            if not self.stopped.is_set():
                self.banner(str(failure), 'retry')
            return False
        if self.stopped.is_set():
            return False
        names = ready(self.seen, rows)
        if names:
            kodi.notification('Ready: %s' % ', '.join(names))
        self.seen = {row['id']: row['chip'] for row in rows}
        if self.getProperty('a4k.banner.kind') != 'cloud':
            self.banner('')
        self.apply(DOWNLOADS, rows)
        self.setProperty('a4k.finished', 'true' if any(row['chip'] == 'Finished' for row in rows) else '')
        if self.tab == CLOUD and not self.cloud_loaded and not self.getProperty('a4k.loading.cloud'):
            self.load_cloud(self.folder)  # the first load failed or had no key
        return any(row['chip'] in BUSY_CHIPS for row in rows)

    def paint_account(self, body):
        pill, expired, fair, stored = account(body, time.time())
        self.setProperty('a4k.account', pill)
        self.setProperty('a4k.expired', 'true' if expired else '')
        self.setProperty('a4k.fairuse', '' if fair is None else '%s%%' % fair)
        self.setProperty('a4k.storage', stored)
        if fair is not None:
            self.fair = fair
            self.getControl(FAIR_USE).setPercent(fair)

    def banner(self, text, kind=''):
        self.setProperty('a4k.banner', text)
        self.setProperty('a4k.banner.kind', kind if text else '')
        self.setProperty('a4k.banner.act', ('Open Settings' if kind == 'settings' else 'Retry') if text else '')
        if not text and self.getFocusId() == BANNER:
            self.setFocusId(TABS)

    # the lists, painted in place

    def apply(self, list_id, rows, select=None):
        with self.lock:
            control = self.getControl(list_id)
            old = self.rows[list_id]
            position = control.getSelectedPosition()
            focused = old[position]['id'] if 0 <= position < len(old) else None
            paint, added, focus = diff(old, rows, focused)
            if added > 0:
                control.addItems([kodi.xbmcgui.ListItem(label='', offscreen=True) for _ in range(added)])
            for _ in range(-added):
                control.removeItem(control.size() - 1)
            for index in paint:
                self.paint(list_id, control.getListItem(index), rows[index])
            self.rows[list_id] = rows
            if select is None and focus is None and position >= len(rows) > 0:
                select = len(rows) - 1  # the focused row went away from the end: the row now last
            elif select is None and focus is not None and focus != position:
                select = focus
            if select is not None and rows:
                control.selectItem(select)
            self.setProperty('a4k.empty.%s' % list_id, '' if rows else 'true')
            if not rows and self.getFocusId() == list_id:
                self.setFocusId(TABS)

    def paint(self, list_id, item, row):
        item.setLabel(row['label'])
        item.setProperty('a4k.id', row['id'])
        if list_id == CLOUD:
            item.setLabel2(row['meta'])
            item.setProperty('a4k.kind', row['kind'])
            return
        item.setLabel2('%s%%' % row['pct'])
        item.setProperty('a4k.chip', row['chip'])
        item.setProperty('a4k.state', row['state'])
        item.setProperty('a4k.msg', row['msg'])
        # the bar is ListItem.PercentPlayed (a progress control cannot read a property): a resume point of pct / 100,
        # never quite 0, which Kodi would skip and leave the slot's last bar drawn
        item.getVideoInfoTag().setResumePoint(max(row['pct'], 0.01), 100)

    def selected(self, list_id):
        position = self.getControl(list_id).getSelectedPosition()
        rows = self.rows[list_id]
        return rows[position] if 0 <= position < len(rows) else None

    # tabs

    def show_tab(self, tab, focus=False):
        self.tab = tab
        self.setProperty('a4k.tab', 'cloud' if tab == CLOUD else 'downloads')
        self.setProperty('a4k.help', HELP[tab])
        for index, (list_id, _) in enumerate(TAB_NAMES):
            self.tabs.getListItem(index).setProperty('on', 'true' if list_id == tab else '')
        self.tabs.selectItem([list_id for list_id, _ in TAB_NAMES].index(tab))
        if tab == CLOUD and not self.cloud_loaded:
            self.load_cloud_later(self.folder, focus=focus)

    # Cloud

    def load_cloud_later(self, folder, back_to=None, focus=False):
        home.spawn(self, self.load_cloud, folder, back_to, focus)

    def load_cloud(self, folder, back_to=None, focus=False):
        try:
            core = plugin_core()
            key = core.utils.get_premiumize_apikey(core)
            if not key:
                return self.banner(NO_KEY, 'settings')
            with self.lock:
                self.cloud_seq += 1
                seq = self.cloud_seq
            self.setProperty('a4k.loading.cloud', 'true')
            try:
                body = fetch(core, core.debrid.premiumize_files(key, folder))
            except Failure as failure:
                body = failure
            finally:
                self.setProperty('a4k.loading.cloud', '')
            with self.lock:
                if seq != self.cloud_seq or self.stopped.is_set():
                    return  # a later load, or the close, came first: this answer paints nothing
                if isinstance(body, Failure):
                    return self.banner(str(body), 'cloud')  # the last list stays; Retry loads the folder again
                rows = cloud_rows(body.get('content') or [], core.utils.video_containers())
                self.folder, self.parent, self.cloud_loaded = folder, body.get('parent_id') or None, True
                self.setProperty('a4k.crumb', crumb(body))
                ids = [row['id'] for row in rows]
                self.apply(CLOUD, rows, select=ids.index(back_to) if back_to in ids else 0)
                if focus and rows and self.tab == CLOUD:
                    self.setFocusId(CLOUD)
            if self.getProperty('a4k.banner.kind') == 'cloud':
                self.banner('')
        except Exception:
            logger.debug(traceback.format_exc())

    def open_folder(self, folder, back_to=None):
        self.load_cloud_later(folder, back_to)

    # input

    def onAction(self, action):
        try:
            action_id = action.getId()
            focus = self.getFocusId()
            if action_id in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
                return self.back(focus)
            if focus == TABS and action_id in (LEFT, RIGHT):  # Kodi moved the tabs already: the list follows at once
                tab = TAB_NAMES[self.tabs.getSelectedPosition()][0]
                if tab != self.tab:
                    self.show_tab(tab)
            elif focus in (TABS, CLEAR) and action_id == DOWN and self.rows[self.tab]:
                self.setFocusId(self.tab)
            elif action_id == ACTION_CONTEXT_MENU and focus == DOWNLOADS:
                self.transfer_actions(self.selected(DOWNLOADS))
            elif action_id == ACTION_CONTEXT_MENU and focus == CLOUD:
                self.cloud_actions(self.selected(CLOUD))
        except Exception:
            self.__fail()

    def back(self, focus):
        # a Cloud folder goes up to its parent, a list or button to the tabs, the tabs close
        if focus == CLOUD and self.parent:
            return self.open_folder(self.parent, back_to=self.folder)
        if focus != TABS:
            return self.setFocusId(TABS)
        self.close()

    def onClick(self, control_id):
        try:
            if control_id == TABS and self.rows[self.tab]:
                self.setFocusId(self.tab)
            elif control_id == CLEAR:
                self.clear_finished()
            elif control_id == BANNER:
                self.banner_click()
            elif control_id == DOWNLOADS:
                self.transfer_actions(self.selected(DOWNLOADS))
            elif control_id == CLOUD:
                row = self.selected(CLOUD)
                if row and row['kind'] == 'folder':
                    self.open_folder(row['id'])
                elif row and row['kind'] == 'video':
                    self.play(row['id'])
                else:
                    self.cloud_actions(row)
        except Exception:
            self.__fail()

    def banner_click(self):
        kind = self.getProperty('a4k.banner.kind')
        if kind == 'settings':
            home.run('RunScript(%s,settings)' % kodi.addon_id)  # back in view, the next refresh reads the key again
        elif kind == 'cloud':
            self.load_cloud_later(self.folder)
        else:
            self.account_due = True
            self.schedule.soon()
            if self.tab == CLOUD:
                self.load_cloud_later(self.folder)

    def play(self, file_id):
        if self.over_call:  # a second play inside the waiting one: Back to the sources, which play it once it is ready
            return kodi.notification('Go back and pick the source again to play it')
        home.run('PlayMedia(%s?action=cloud&type=play&id=%s)' % (app.PLUGIN, file_id))

    def transfer_actions(self, row):
        # Open (its folder in Cloud) or Play (a single file) once finished, Delete always
        if not row:
            return
        actions = []
        if row['chip'] == 'Finished' and row['folder']:
            actions.append('Open in Cloud')
        elif row['chip'] == 'Finished' and row['file']:
            actions.append('Play')
        actions.append('Delete')
        choice = select(row['label'], actions)
        if choice is None or choice < 0:
            return
        action = actions[choice]
        if action == 'Open in Cloud':
            with self.lock:
                self.folder, self.cloud_loaded = row['folder'], False
            self.setFocusId(TABS)  # the Downloads list hides; the Cloud list takes the focus once loaded
            self.show_tab(CLOUD, focus=True)
        elif action == 'Play':
            self.play(row['file'])
        elif confirm('Delete this download?', 'Delete'):
            self.write(lambda core, key: core.debrid.premiumize_transfer_delete(key, row['id']))

    def cloud_actions(self, row):
        if not row:
            return
        actions = (['Open'] if row['kind'] == 'folder' else ['Play'] if row['kind'] == 'video' else []) + ['Delete']
        choice = select(row['label'], actions)
        if choice is None or choice < 0:
            return
        action = actions[choice]
        if action == 'Open':
            self.open_folder(row['id'])
        elif action == 'Play':
            self.play(row['id'])
        elif confirm('Delete this %s?' % ('folder' if row['kind'] == 'folder' else 'file'), 'Delete'):
            folder = row['kind'] == 'folder'
            if self.write(lambda core, key: (core.debrid.premiumize_folder_delete if folder else core.debrid.premiumize_file_delete)(key, row['id'])):
                self.load_cloud_later(self.folder)

    def clear_finished(self):
        self.write(lambda core, key: core.debrid.premiumize_transfer_clearfinished(key))

    def write(self, request):
        # a POST; the transfers and the account refresh right after. True when Premiumize took it
        core = plugin_core()
        key = core.utils.get_premiumize_apikey(core)
        if not key:
            return False
        try:
            fetch(core, request(core, key))
        except Failure as failure:
            kodi.notification(str(failure))
            return False
        self.account_due = True
        self.schedule.soon()
        return True

    def stop(self):
        if self.started:
            self.stopped.set()

    def close(self):
        self.stop()
        super(Debrid, self).close()

    def __fail(self):
        self.error = traceback.format_exc()
        self.close()

def open(tab='downloads', folder='', over_call=False, root=False):
    # the Browse row's Debrid tile, action=cloud (cloud.py) and the uncached wait's Open Downloads (playback.transfer,
    # over_call); a window error is logged and closes the window. root: action=cloud's own window, the call's last step
    try:
        window = Debrid('a4k-debrid.xml', kodi.addon_path, 'Default', '1080i')
        # a reopened add-on (after the Home key) comes back to this window, not to the one under it
        window.setProperty('a4k.home', 'true')
        window.setProperty('a4k.loading', 'true')
        window.over_call = over_call
        window.setProperty('a4k.overcall', 'true' if over_call else '')  # the play call's loader is not drawn
        window.tab = CLOUD if tab == 'cloud' else DOWNLOADS
        window.folder = folder or ''
        home.modal(window, home.ROOT_JOIN if root else home.JOIN)  # joins the window's threads before it is freed
        error = window.error
        del window
        if error:
            raise RuntimeError(error)
    except Exception:
        logger.error('debrid window failed: %s' % traceback.format_exc())
