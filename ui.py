# -*- coding: utf-8 -*-

import os
from a4kStreaming import api

if __name__ == '__main__':
    os.environ.pop(api.api_mode_env_name, '')
    from a4kStreaming.ui import app
    app.run()
