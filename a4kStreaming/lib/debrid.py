# -*- coding: utf-8 -*-

def premiumize_transfers(apikey):
    return {
        'method': 'GET',
        'url': 'https://www.premiumize.me/api/transfer/list?apikey=%s' % apikey,
        'headers': {
            'content-type': 'application/json',
        },
    }

def premiumize_files(apikey, id):
    if id != '':
        id = 'id=%s&' % id

    return {
        'method': 'GET',
        'url': 'https://www.premiumize.me/api/folder/list?%sincludebreadcrumbs=false&apikey=%s' % (id, apikey),
        'headers': {
            'content-type': 'application/json',
        },
    }

def premiumize_check(apikey, hashes):
    return {
        'method': 'POST',
        'url': 'https://www.premiumize.me/api/cache/check?apikey=%s' % apikey,
        'data': {
            'items[]': hashes
        },
    }

def premiumize_cache(apikey, magnet):
    return {
        'method': 'POST',
        'url': 'https://www.premiumize.me/api/transfer/create?apikey=%s' % apikey,
        'data': {
            'src': magnet
        }
    }

def premiumize_file_delete(apikey, id):
    return {
        'method': 'POST',
        'url': 'https://www.premiumize.me/api/item/delete?apikey=%s' % apikey,
        'data': {
            'id': id
        }
    }

def premiumize_folder_delete(apikey, id):
    return {
        'method': 'POST',
        'url': 'https://www.premiumize.me/api/folder/delete?apikey=%s' % apikey,
        'data': {
            'id': id
        }
    }

def premiumize_transfer_delete(apikey, id):
    return {
        'method': 'POST',
        'url': 'https://www.premiumize.me/api/transfer/delete?apikey=%s' % apikey,
        'data': {
            'id': id
        }
    }

def premiumize_transfer_clearfinished(apikey):
    return {
        'method': 'POST',
        'url': 'https://www.premiumize.me/api/transfer/clearfinished?apikey=%s' % apikey,
    }

def premiumize_resolve(apikey, magnet):
    return {
        'method': 'POST',
        'url': 'https://www.premiumize.me/api/transfer/directdl?apikey=%s' % apikey,
        'data': {
            'src': magnet
        },
    }

def realdebrid_transfers(auth):
    return {
        'method': 'GET',
        'url': 'https://api.real-debrid.com/rest/1.0/torrents%s' % auth,
    }

def realdebrid_files(auth, id):
    return {
        'method': 'GET',
        'url': 'https://api.real-debrid.com/rest/1.0/torrents/info/%s%s' % (id, auth),
    }

def realdebrid_check(auth, hashes):
    return {
        'method': 'GET',
        'url': 'https://api.real-debrid.com/rest/1.0/torrents/instantAvailability/%s%s' % (hashes, auth)
    }

def realdebrid_cache(auth, magnet):
    return {
        'method': 'POST',
        'url': 'https://api.real-debrid.com/rest/1.0/torrents/addMagnet%s' % auth,
        'data': {
            'magnet': magnet
        },
    }

def realdebrid_select(auth, id, files='all'):
    return {
        'method': 'POST',
        'url': 'https://api.real-debrid.com/rest/1.0/torrents/selectFiles/%s%s' % (id, auth),
        'data': {
            'files': files
        },
    }

def realdebrid_delete(auth, id):
    return {
        'method': 'DELETE',
        'url': 'https://api.real-debrid.com/rest/1.0/torrents/delete/%s%s' % (id, auth),
    }

def realdebrid_resolve(auth, link):
    return {
        'method': 'POST',
        'url': 'https://api.real-debrid.com/rest/1.0/unrestrict/link%s' % auth,
        'data': {
            'link': link
        },
    }

def alldebrid_transfers(auth):
    return {
        'method': 'GET',
        'url': 'https://api.alldebrid.com/v4/magnet/status?%s' % auth,
    }

def alldebrid_files(auth, id):
    return {
        'method': 'GET',
        'url': 'https://api.alldebrid.com/v4/magnet/status?id=%s%s' % (id, auth),
    }

def alldebrid_check(auth, hashes):
    return {
        'method': 'POST',
        'url': 'https://api.alldebrid.com/v4/magnet/instant?%s' % auth,
        'data': {
            'magnets[]': hashes
        },
    }

def alldebrid_cache(auth, hash):
    return {
        'method': 'GET',
        'url': 'https://api.alldebrid.com/v4/magnet/upload?&magnets[]=%s%s' % (hash, auth),
    }

def alldebrid_delete(auth, id):
    return {
        'method': 'GET',
        'url': 'https://api.alldebrid.com/v4/magnet/delete?id=%s%s' % (id, auth),
    }

def alldebrid_resolve(auth, link):
    return {
        'method': 'GET',
        'url': 'https://api.alldebrid.com/v4/link/unlock?link=%s%s' % (link, auth),
    }
