# -*- coding: utf-8 -*-

from .utils import open_file_wrapper, os, time, provider_temp_dir

def __cache_key_path(key):
    path = ''.join([x if x.isalnum() else '_' for x in key])
    return os.path.join(provider_temp_dir, path)

def __cache_save(key, data):
    path = __cache_key_path(key)
    with open_file_wrapper(path, mode='wb')() as f:
        f.write(data)

def __cache_get(key):
    path = __cache_key_path(key)
    if not os.path.exists(path):
        return {}
    try:
        with open_file_wrapper(path, mode='rb')() as f:
            return f.read()
    except:
        return {}

def __cache_check(key):
    try:
        path = __cache_key_path(key)
        if os.path.exists(path):
            ttl = os.path.getmtime(path)
            if time.time() - ttl < 5:
                return True
            os.remove(path)
    except:
        pass

def __cache_cleanup():
    try:
        # while temp dir bigger than 5MiB, remove files sorted by age (oldest first)
        max_size = 5 * 1024 * 1024
        files = []
        size = 0

        for file in os.listdir(provider_temp_dir):
            path = os.path.join(provider_temp_dir, file)
            if os.path.isfile(path):
                files.append((path, os.path.getmtime(path)))
                size += os.path.getsize(path)

        if size < max_size:
            return

        original_size = size

        files.sort(key=lambda x: x[1])
        for file, _ in files:
            if size < max_size:
                break
            size -= os.path.getsize(file)
            os.remove(file)

        return original_size - size
    except:
        pass

db = lambda: None
db.set = lambda key, value: __cache_save(key, value)
db.get = lambda key: __cache_get(key)
db.check = lambda key: __cache_check(key)
db.cleanup = lambda: __cache_cleanup()
