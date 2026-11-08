# -*- coding: utf-8 -*-
# Sheets for the play flow, run in the plugin process: the source picker / generic select (a4k-sheet.xml) and the
# source search progress card (a4k-progress.xml). A window error is logged: the select reads it as a cancel, the
# search goes on without its card.

import re
import traceback

from ..lib import kodi, logger
from .home import ACTION_PREVIOUS_MENU, ACTION_NAV_BACK

LIST = 600
BAR = 700

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
    actions = 0  # when set, only the first rows act; the rest are lines to read

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
                position = self.getControl(LIST).getSelectedPosition()
                if self.actions and position >= self.actions:
                    return
                self.choice = position
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

def select(heading, labels, preselect=-1, rows=None, actions=0):
    # Dialog().select's contract: the chosen index, -1 on cancel. rows are the sheet's (label, label2) per item, the
    # labels themselves when not given (without colours: the focused row is white). actions: only the first rows can be
    # chosen, OK on a later one does nothing
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
        logger.error('sheet window failed: %s' % traceback.format_exc())
        return -1

# source search progress

class ProgressWindow(kodi.xbmcgui.WindowXMLDialog):
    canceled = False

    def onAction(self, action):
        # Back cancels: the search returns the results it already has
        if action.getId() in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self.canceled = True
            self.close()

class Progress(object):
    # DialogProgress's methods (create, update, iscanceled, close) over the non-modal a4k-progress.xml card
    def __init__(self):
        self.window = None
        self.bar = None

    def __show(self, message):
        # the message is the stock dialog's text: up to three lines
        lines = (message.split('\n') + ['', '', ''])[:3]
        for i, line in enumerate(lines):
            self.window.setProperty('a4k.line%s' % (i + 1), line)

    def __drop(self):
        # a window error: logged, and the rest of the search runs without the card
        logger.error('progress window failed: %s' % traceback.format_exc())
        self.close()
        self.window = None

    def create(self, heading, message=''):
        try:
            self.window = ProgressWindow('a4k-progress.xml', kodi.addon_path, 'Default', '1080i')
            self.window.setProperty('a4k.heading', heading)
            self.__show(message)
            self.window.show()
            self.bar = self.window.getControl(BAR)  # raises when the XML did not load
            self.bar.setPercent(0)
        except Exception:
            self.__drop()

    def update(self, percent, message=''):
        if not self.window:
            return
        try:
            self.bar.setPercent(percent)
            self.__show(message)
        except Exception:
            self.__drop()

    def iscanceled(self):
        return bool(self.window and self.window.canceled)

    def close(self):
        if self.window:
            try:
                self.window.close()
            except Exception:
                pass

def progress():
    # what the source search shows after its first second
    return Progress()
