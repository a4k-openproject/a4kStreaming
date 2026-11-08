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
    else:
        from a4kStreaming.ui import app
        app.run()
