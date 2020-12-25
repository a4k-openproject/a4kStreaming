# -*- coding: utf-8 -*-

import sys
import os
import json
import re
import pytest
import time

dir_name = os.path.dirname(__file__)
main = os.path.join(dir_name, '..')
a4kStreaming = os.path.join(main, '..', 'a4kStreaming')
lib = os.path.join(a4kStreaming, 'lib')
services = os.path.join(a4kStreaming, 'services')

sys.path.append(dir_name)
sys.path.append(main)
sys.path.append(a4kStreaming)
sys.path.append(lib)
sys.path.append(services)

from a4kStreaming import api
from tests import utils
