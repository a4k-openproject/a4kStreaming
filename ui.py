# -*- coding: utf-8 -*-

import os
import sys
from a4kStreaming import api

if __name__ == '__main__':
    os.environ.pop(api.api_mode_env_name, '')
    action = sys.argv[1] if len(sys.argv) > 1 else ''
    # the settings window (the home window's Settings), or its Home order editor alone (the action in Kodi's own
    # settings dialog, resources/settings.xml)
    if action in ('settings', 'order'):
        from a4kStreaming.ui import settings
        settings.run(only_order=action == 'order')
    elif action == 'my_list':
        from a4kStreaming.ui import appearance
        appearance.pick_my_list()
    elif action in ('kodi_mode', 'kodi_mode_prompt'):  # its row in Kodi's own dialog; the home window's one-time question
        from a4kStreaming import kodi_mode
        kodi_mode.sheet() if action == 'kodi_mode' else kodi_mode.prompt()
    elif action == 'autoopen':  # Kodi setup mode at Kodi start (service.py): not over a play that began meanwhile
        from a4kStreaming.lib import kodi
        if not kodi.xbmc.getCondVisibility('Player.HasMedia'):
            from a4kStreaming.ui import app
            app.run()
    else:
        from a4kStreaming.ui import app
        app.run()
