# -*- coding: utf-8 -*-

import sys
import os
import importlib
from a4kStreaming import api

if __name__ == '__main__':
    os.environ.pop(api.api_mode_env_name, '')
    core = importlib.import_module('a4kStreaming.core')
    core.main(sys.argv[0], int(sys.argv[1]), sys.argv[2][1:])
