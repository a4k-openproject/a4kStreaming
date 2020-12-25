# -*- coding: utf-8 -*-

import os
import json
from . import kodi
from . import utils

__search_filepath = os.path.join(kodi.addon_profile, 'search.json')
__provider_filepath = os.path.join(kodi.addon_profile, 'provider.json')
__last_results_filepath = os.path.join(kodi.addon_profile, 'last_results.json')
__general_filepath = os.path.join(kodi.addon_profile, 'general.json')

def __get_cache(filepath):
    try:
        with open(filepath, 'r') as f:
            data = json.loads(f.read())
            return utils.DictAsObject(data)
    except:
        return utils.DictAsObject({})

def __save_cache(filepath, cache):
    try:
        json_data = json.dumps(cache, indent=2)
        with open(filepath, 'w') as f:
            f.write(json_data)
    except: pass

def save_search(data):
    return __save_cache(__search_filepath, data)
def get_search():
    return __get_cache(__search_filepath)

def save_provider(data):
    return __save_cache(__provider_filepath, data)
def get_provider():
    return __get_cache(__provider_filepath)

def save_last_results(data):
    return __save_cache(__last_results_filepath, data)
def get_last_results():
    return __get_cache(__last_results_filepath)

def save_general(data):
    return __save_cache(__general_filepath, data)
def get_general():
    return __get_cache(__general_filepath)
