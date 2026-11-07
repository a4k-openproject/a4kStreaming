# -*- coding: utf-8 -*-
# Sheets for the play flow, run in the plugin process: the source picker / generic select (a4k-sheet.xml) and the
# source search progress card (a4k-progress.xml). They follow ui.mode: classic mode gets the stock dialogs exactly as
# before. Any window error falls back to the stock dialog, logged once per session, so a broken XML never blocks
# playback.

import re
import traceback

from ..lib import kodi, logger
from . import app
from .home import ACTION_PREVIOUS_MENU, ACTION_NAV_BACK

LIST = 600
BAR = 700

FAILED = 'a4k.ui.sheets.failed'

def enabled():
    return app.windows_mode() and not kodi.xbmcgui.Window(app.HOME_WINDOW).getProperty(FAILED)

def fail(reason):
    home = kodi.xbmcgui.Window(app.HOME_WINDOW)
    if home.getProperty(FAILED):
        return
    home.setProperty(FAILED, 'true')
    logger.error('sheet window failed, using the stock dialog: %s' % reason)

def source_row(result):
    # a search result as a sheet row: quality and formats, then debrid, size and release title
    label = '  '.join(part for part in (result['quality'], result['hdr'], result['videocodec'], result['audiocodec']) if part)
    label2 = '  ·  '.join(part for part in (result.get('debrid', ''), '%s GB' % result['size'], result['release_title']) if part)
    return label, label2

# select sheet

class Sheet(kodi.xbmcgui.WindowXMLDialog):
    error = None
    choice = -1
    rows = ()
    preselect = -1

    def onInit(self):
        try:
            control = self.getControl(LIST)
            if not control.size():
                ListItem = kodi.xbmcgui.ListItem
                control.addItems([ListItem(label=label, label2=label2, offscreen=True) for label, label2 in self.rows])
            if 0 <= self.preselect < len(self.rows):
                control.selectItem(self.preselect)
            self.setFocusId(LIST)
        except Exception:
            self.__fail()

    def onClick(self, control_id):
        try:
            if control_id == LIST:
                self.choice = self.getControl(LIST).getSelectedPosition()
                self.close()
        except Exception:
            self.__fail()

    def onAction(self, action):
        if action.getId() in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self.choice = -1
            self.close()

    def __fail(self):
        self.error = traceback.format_exc()
        self.close()

def select(heading, labels, preselect=-1, rows=None):
    # Dialog().select's contract: the chosen index, -1 on cancel. labels are the stock dialog's items; rows are the
    # sheet's (label, label2) per item, the labels themselves when not given (without colours: the focused row is white)
    if enabled():
        try:
            window = Sheet('a4k-sheet.xml', kodi.addon_path, 'Default', '1080i')
            window.setProperty('a4k.heading', heading)
            window.rows = rows or [(re.sub(r'\[/?COLOR[^\]]*\]', '', label), '') for label in labels]
            window.preselect = preselect
            window.doModal()
            choice, error = window.choice, window.error
            del window
            if error:
                raise RuntimeError(error)
            return choice
        except Exception:
            fail(traceback.format_exc())
    return kodi.xbmcgui.Dialog().select(heading, labels, preselect=preselect)

# source search progress

class ProgressWindow(kodi.xbmcgui.WindowXMLDialog):
    canceled = False

    def onAction(self, action):
        # Back cancels: the search returns the results it already has
        if action.getId() in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self.canceled = True
            self.close()

class Progress(object):
    # DialogProgress's methods (create, update, iscanceled, close) over the non-modal a4k-progress.xml card; a window
    # error moves the rest of the search to the stock dialog
    def __init__(self):
        self.window = None
        self.bar = None
        self.stock = None
        self.heading = ''

    def __show(self, message):
        # the message is the stock dialog's text: up to three lines
        lines = (message.split('\n') + ['', '', ''])[:3]
        for i, line in enumerate(lines):
            self.window.setProperty('a4k.line%s' % (i + 1), line)

    def __fallback(self, message, percent=0):
        fail(traceback.format_exc())
        try:
            self.window.close()
        except Exception:
            pass
        self.window = None
        self.stock = kodi.xbmcgui.DialogProgress()
        self.stock.create(self.heading, message)
        if percent:
            self.stock.update(percent, message)

    def create(self, heading, message=''):
        self.heading = heading
        try:
            self.window = ProgressWindow('a4k-progress.xml', kodi.addon_path, 'Default', '1080i')
            self.window.setProperty('a4k.heading', heading)
            self.__show(message)
            self.window.show()
            self.bar = self.window.getControl(BAR)  # raises when the XML did not load
            self.bar.setPercent(0)
        except Exception:
            self.__fallback(message)

    def update(self, percent, message=''):
        if self.stock:
            return self.stock.update(percent, message)
        try:
            self.bar.setPercent(percent)
            self.__show(message)
        except Exception:
            self.__fallback(message, percent)

    def iscanceled(self):
        if self.stock:
            return self.stock.iscanceled()
        return bool(self.window and self.window.canceled)

    def close(self):
        if self.stock:
            return self.stock.close()
        if self.window:
            self.window.close()

def progress():
    # what the source search shows after its first second: the card in windows mode, the stock dialog in classic mode
    return Progress() if enabled() else kodi.xbmcgui.DialogProgress()
