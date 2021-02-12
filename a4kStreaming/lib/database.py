# -*- coding: utf-8 -*-

import hashlib
from . import kodi
from .utils import open_file_wrapper, os, re, json, time, provider_temp_dir

def __cache_key_path(key):
    path = ''.join([x if x.isalnum() else '_' for x in key]) + '.json'
    return os.path.join(provider_temp_dir, path)

def __cache_save(key, data):
    path = __cache_key_path(key)
    with open_file_wrapper(path, mode='w')() as f:
        f.write(json.dumps(data, indent=4))

def __cache_get(key):
    path = __cache_key_path(key)
    if not os.path.exists(path):
        return {}
    try:
        with open_file_wrapper(path)() as f:
            return json.load(f)
    except:
        return {}

def __generate_md5(*args):
    md5_hash = hashlib.md5()
    try:
        [md5_hash.update(str(arg)) for arg in args]
    except:
        [md5_hash.update(str(arg).encode('utf-8')) for arg in args]
    return str(md5_hash.hexdigest())

def __get_function_name(function_instance):
    return re.sub(r'.+?\s*method\s*|.+function\s*|\sat\s*?.+|\s*?of\s*?.+', '', repr(function_instance))

def __hash_function(function_instance, *args):
    return __get_function_name(function_instance) + __generate_md5(args)

def __get_or_add(key, value, fn, duration, *args, **kwargs):
    key = __hash_function(fn, *args) if not key else key
    if not value:
        data = __cache_get(key)
        if data:
            if not duration or time.time() - data['t'] < (duration * 60):
                return data['v']

    if not value and not fn:
        return None

    value = fn(*args, **kwargs) if not value else value
    data = { 't': time.time(), 'v': value }
    __cache_save(key, data)
    return value

database = lambda: None
def db_get(fn, duration, *args, **kwargs):
    return __get_or_add(None, None, fn, duration, *args, **kwargs)
database.get = db_get
database.cache_get = lambda key: __get_or_add(key, None, None, None)
database.cache_insert = lambda key, value: __get_or_add(key, value, None, None)
