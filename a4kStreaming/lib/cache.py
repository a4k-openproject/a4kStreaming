# -*- coding: utf-8 -*-

import os
import json
from . import kodi
from .utils import DictAsObject, open_file_wrapper

__search_filepath = os.path.join(kodi.addon_profile, 'search.json')
__provider_filepath = os.path.join(kodi.addon_profile, 'provider.json')
__last_results_filepath = os.path.join(kodi.addon_profile, 'last_results.json')
__last_title_filepath = os.path.join(kodi.addon_profile, 'last_title.json')
__general_filepath = os.path.join(kodi.addon_profile, 'general.json')

def __get_cache(filepath):
    try:
        with open_file_wrapper(filepath)() as f:
            data = json.loads(f.read())
            return DictAsObject(data)
    except:
        return DictAsObject({})

def __save_cache(filepath, cache):
    try:
        json_data = json.dumps(cache, indent=2)
        with open_file_wrapper(filepath, mode='w')() as f:
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

def save_last_title(data):
    return __save_cache(__last_title_filepath, data)
def get_last_title():
    return __get_cache(__last_title_filepath)

def save_general(data):
    return __save_cache(__general_filepath, data)
def get_general():
    return __get_cache(__general_filepath)
