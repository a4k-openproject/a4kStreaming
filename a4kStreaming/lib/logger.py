# -*- coding: utf-8 -*-

import re

from .kodi import xbmc, addon_id, get_kodi_setting, get_setting

# debrid keys ride in request and provider urls: as a query or config value, or as the path segment after /resolve/<service>/
__key_values = re.compile(r'((?:apikey|premiumize|realdebrid|alldebrid)(?:=|%3D))[^&|/?\s\'"%]+|(/resolve/[^/\s]+/)[^/\s\'"]+', re.I)

def redact(message):
    message = __key_values.sub(lambda m: (m.group(1) or m.group(2)) + '***', str(message))
    # and whatever shape a url takes, the configured key itself never reaches the log
    try: key = get_setting('premiumize.apikey')
    except Exception: key = ''
    return message.replace(key, '***') if key else message

__get_debug_logenabled_err = False
def __get_debug_logenabled():
    global __get_debug_logenabled_err
    if __get_debug_logenabled_err:
        return False

    try:
        return get_kodi_setting("debug.showloginfo", log_error=False)
    except:
        __get_debug_logenabled_err = True

    return False

def __log(message, level=xbmc.LOGDEBUG):
    is_lazy_msg = callable(message)
    if is_lazy_msg and level == xbmc.LOGDEBUG and not __get_debug_logenabled():
        return

    if is_lazy_msg:
        message = message()

    xbmc.log('{0}: {1}'.format(addon_id, redact(message)), level)

def notice(message):
    __log(message, xbmc.LOGINFO)

def error(message):
    __log(message, xbmc.LOGERROR)

def debug(message):
    __log(message, xbmc.LOGDEBUG)
