# -*- coding: utf-8 -*-
# flake8: noqa

import os
import shutil
import time

from zipfile import ZipFile
from xml.etree import ElementTree

try:
    from urlparse import unquote
except ImportError:
    from urllib.parse import unquote

# xbmc
xbmc = lambda: None
xbmc.getInfoLabel = lambda t: ''
xbmc.executeJSONRPC = lambda _: '{ "result": { "value": [] } }'
xbmc.executebuiltin = lambda _: None
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
__listitem = lambda: None
__listitem.setProperty = lambda _, __: None
__listitem.setArt = lambda _: None
__listitem.setInfo = lambda _, __: None
__listitem.setLabel = lambda _: None
__listitem.setCast = lambda _: None
__listitem.setRating = lambda n, r, v, d: None
__listitem.setSubtitles = lambda _: None
__listitem.addContextMenuItems = lambda _: None
__listitem.setContentLookup = lambda _: None
__listitem.addStreamInfo = lambda _, __: None
def __create_listitem(*args, **kwargs): return __listitem
xbmcgui.ListItem = __create_listitem

__dialog = lambda: None
def browse(*args, **kwargs): return None
__dialog.browse = browse
def select(*args, **kwargs): return None
__dialog.select = select
def multiselect(*args, **kwargs): return None
__dialog.multiselect = multiselect
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
