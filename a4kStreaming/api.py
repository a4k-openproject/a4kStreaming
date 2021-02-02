# -*- coding: utf-8 -*-

import os
import json
import importlib

api_mode_env_name = 'A4KSTREAMING_API_MODE'

class A4kStreamingApi(object):
    def __init__(self, mocks=None):
        if mocks is None:
            mocks = {}

        api_mode = {
            'kodi': False,
            'xbmc': False,
            'xbmcaddon': False,
            'xbmcplugin': False,
            'xbmcgui': False,
            'xbmcvfs': False,
        }

        api_mode.update(mocks)
        os.environ[api_mode_env_name] = json.dumps(api_mode)
        self.core = importlib.import_module('a4kStreaming.core')

    def __mock_settings(self, settings):
        default = self.core.kodi.addon.getSetting

        def get_setting(id):
            setting = settings.get(id, None)
            if setting is None:
                setting = default(id)
            return setting

        self.core.kodi.addon.getSetting = get_setting

        def restore():
            self.core.kodi.addon.getSetting = default
        return restore

    def __execute(self, action, params, settings):
        restore_settings = None

        try:
            if settings:
                restore_settings = self.__mock_settings(settings)

            return getattr(self.core, action)(self.core, params)
        finally:
            if restore_settings:
                restore_settings()

    def __getattr__(self, name):
        return lambda params, settings: self.__execute(name, params, settings)
