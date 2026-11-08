# -*- coding: utf-8 -*-
# flake8: noqa

import os
import shutil
import time

from zipfile import ZipFile
from xml.etree import ElementTree

from urllib.parse import unquote

# xbmc
xbmc = lambda: None
xbmc.getInfoLabel = lambda t: ''
xbmc.executeJSONRPC = lambda _: '{ "result": { "value": [] } }'
xbmc.executebuiltin = lambda *_: None
xbmc.getCleanMovieTitle = lambda t: t
xbmc.getCondVisibility = lambda _: False
xbmc.sleep = lambda ms: time.sleep(ms / 1000)

xbmc.convertLanguage = lambda l, f: l[:f].lower()
xbmc.ISO_639_1 = 2
xbmc.ISO_639_2 = 3

__player = lambda: None
__player.getPlayingFile = lambda: ''
__player.setSubtitles = lambda s: None
xbmc.Player = lambda: __player

__monitor = lambda: None
__monitor.abortRequested = lambda: False
__monitor.waitForAbort = lambda _: False
xbmc.Monitor = lambda: __monitor

__keyboard = lambda: None
__keyboard.doModal = lambda: None
__keyboard.isConfirmed = lambda: False
__keyboard.getText = lambda: False
xbmc.Keyboard = lambda _, __: __keyboard

def __log(msg, label):
    print(msg)
xbmc.log = __log
xbmc.LOGDEBUG = 'debug'
xbmc.LOGINFO = 'info'
xbmc.LOGERROR = 'error'
xbmc.LOGNOTICE = 'notice'

# xbmcaddon
xbmcaddon = lambda: None
__addon = lambda: None
def __get_addon_info(name):
    if name == 'id':
        return 'plugin.video.a4kstreaming'
    elif name == 'name':
        return 'a4kstreaming'
    elif name == 'version':
        tree = ElementTree.parse(os.path.join(os.path.dirname(__file__), '..', '..', 'addon.xml'))
        root = tree.getroot()
        return root.get('version')
    elif name == 'profile':
        return os.path.join(os.path.dirname(__file__), '../../tmp')
    elif name == 'path':
        return os.path.join(os.path.dirname(__file__), '../..')
__addon.getAddonInfo = __get_addon_info
__addon.getSetting = lambda _: ''
xbmcaddon.Addon = lambda _: __addon

# xbmcplugin
xbmcplugin = lambda: None
def __add_directory_item(*args, **kwargs): return None
xbmcplugin.addDirectoryItem = __add_directory_item
xbmcplugin.addDirectoryItems = __add_directory_item
xbmcplugin.setResolvedUrl = lambda _, __, listitem: None
xbmcplugin.setContent = lambda _, __: None
xbmcplugin.addSortMethod = lambda _, __: None
xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE = None

# xbmcgui
xbmcgui = lambda: None

__video_info_tag = lambda: None
__video_info_tag.setRating = lambda _, __, ___, ____: None

__list_info_tag = lambda: None
__list_info_tag.set_cast = lambda _: None
__list_info_tag.add_stream_info = lambda _, __: None
def set_info_tag(*args, **kwargs): return __list_info_tag

def __create_listitem(*args, **kwargs):
    # each item records its art, properties and context menu so tests can read what a listing set
    listitem = lambda: None
    listitem.label = kwargs.get('label', args[0] if args else '')
    listitem.label2 = kwargs.get('label2', args[1] if len(args) > 1 else '')
    listitem.art = {}
    listitem.properties = {}
    listitem.context_menu = []
    listitem.setArt = listitem.art.update
    listitem.setProperty = listitem.properties.__setitem__
    listitem.getProperty = lambda key: listitem.properties.get(key, '')
    listitem.addContextMenuItems = listitem.context_menu.extend
    listitem.setInfo = lambda _, __: None
    listitem.setLabel = lambda _: None
    listitem.getLabel = lambda: listitem.label
    listitem.setCast = lambda _: None
    listitem.setRating = lambda n, r, v, d: None
    listitem.setSubtitles = lambda _: None
    listitem.setContentLookup = lambda _: None
    listitem.addStreamInfo = lambda _, __: None
    listitem.resume = None
    tag = lambda: None
    tag.setRating = __video_info_tag.setRating
    tag.setResumePoint = lambda time, totalTime=0.0: setattr(listitem, 'resume', (time, totalTime))
    listitem.getVideoInfoTag = lambda: tag
    return listitem
xbmcgui.ListItem = __create_listitem

__dialog = lambda: None
def browse(*args, **kwargs): return None
__dialog.browse = browse
def select(*args, **kwargs): return None
__dialog.select = select
def multiselect(*args, **kwargs): return None
__dialog.multiselect = multiselect
__dialog.contextmenu = lambda _: -1
__dialog.textviewer = lambda heading, text, usemono=False: None
def __create_dialog(*args, **kwargs): return __dialog
xbmcgui.Dialog = __create_dialog

__dialogprogress = lambda: None
def create(*args, **kwargs): return None
__dialogprogress.create = create
def update(*args, **kwargs): return None
__dialogprogress.update = update
__dialogprogress.close = lambda: None
__dialogprogress.iscanceled = lambda: False
def __create_dialogprogress(*args, **kwargs): return __dialogprogress
xbmcgui.DialogProgress = __create_dialogprogress

# windows: properties are kept per window id, like Kodi's, so tests can read what one invocation left for the next
_window_properties = {}

class _Window(object):
    def __init__(self, id=-1):
        self.properties = _window_properties.setdefault(id, {})
    def setProperty(self, key, value): self.properties[key] = value
    def getProperty(self, key): return self.properties.get(key, '')
    def clearProperty(self, key): self.properties.pop(key, None)
    def clearProperties(self): self.properties.clear()
xbmcgui.Window = _Window
xbmcgui.getCurrentWindowId = lambda: 10025
xbmcgui.getCurrentWindowDialogId = lambda: 9999  # no dialog up

class ControlList(object):
    def __init__(self, *args, **kwargs): self.items = []
    def addItems(self, items): self.items.extend(items)
    def reset(self): self.items = []
    def size(self): return len(self.items)
    def getSelectedPosition(self): return 0 if self.items else -1
    def getSelectedItem(self): return self.items[0] if self.items else None
    def getListItem(self, index): return self.items[index]
    def controlDown(self, control): self.down = control
    def selectItem(self, index): pass
    def setPercent(self, percent): self.percent = percent
xbmcgui.ControlList = ControlList

class WindowXML(_Window):
    # doModal runs onInit once and returns, as if the user pressed Back right away
    def __init__(self, xmlFilename, scriptPath, defaultSkin='Default', defaultRes='720p', isMedia=False):
        # registered under the first free script window id, as Kodi does
        self.properties = _window_properties.setdefault(next(i for i in range(13000, 13100) if not _window_properties.get(i)), {})
        self.controls = {}
        self.focus_id = 0
    def doModal(self): self.onInit()
    def show(self): self.onInit()
    def close(self): pass
    def onInit(self): pass
    def getControl(self, id): return self.controls.setdefault(id, ControlList())
    def getFocusId(self): return self.focus_id
    def setFocusId(self, id): self.focus_id = id
xbmcgui.WindowXML = WindowXML

class WindowXMLDialog(WindowXML): pass
xbmcgui.WindowXMLDialog = WindowXMLDialog

# xbmcvfs
xbmcvfs = lambda: None
def __mkdirs(f):
    try: os.makedirs(f)
    except Exception: pass
xbmcvfs.mkdirs = __mkdirs
xbmcvfs.translatePath = lambda p: p

__archive_proto = 'archive://'
def __listdir(archive_uri):
    archive_path = unquote(archive_uri).replace(__archive_proto, '')
    with ZipFile(archive_path, 'r') as zip_obj:
        return ([], zip_obj.namelist())
xbmcvfs.listdir = __listdir

def __copy(src_uri, dest):
    archive_path = unquote(src_uri[:src_uri.find('.zip') + 4]).replace(__archive_proto, '')
    member = unquote(src_uri[src_uri.find('.zip') + 5:]).replace(__archive_proto, '')
    with ZipFile(archive_path, 'r') as zip_obj:
        dest_dir = os.path.dirname(dest)
        zip_obj.extract(member, dest_dir)
        os.rename(os.path.join(dest_dir, member), dest)
xbmcvfs.copy = __copy

def __File(_):
    return __File
__File.size = lambda: 0
__File.hash = lambda: 0
__File.subdb_hash = lambda: 0
__File.close = lambda: None
xbmcvfs.File = __File
