# -*- coding: utf-8 -*-

import os
import sys
from a4kStreaming import api

if __name__ == '__main__':
    os.environ.pop(api.api_mode_env_name, '')
    action = sys.argv[1] if len(sys.argv) > 1 else ''
    if action in ('order', 'my_list'):  # the Appearance settings actions (resources/settings.xml)
        from a4kStreaming.ui import appearance
        appearance.edit_order() if action == 'order' else appearance.pick_my_list()
    else:
        from a4kStreaming.ui import app
        app.run()
