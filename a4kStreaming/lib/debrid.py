# -*- coding: utf-8 -*-

from urllib.parse import urlencode

def premiumize_transfers(apikey):
    return {
        'method': 'GET',
        'url': 'https://www.premiumize.me/api/transfer/list?apikey=%s' % apikey,
        'headers': {
            'content-type': 'application/json',
        },
    }

def premiumize_files(apikey, id):
    # a cloud folder (the root without an id) with its breadcrumbs
    query = {'id': id} if id else {}
    query.update(includebreadcrumbs='true', apikey=apikey)
    return {
        'method': 'GET',
        'url': 'https://www.premiumize.me/api/folder/list?%s' % urlencode(query),
        'headers': {
            'content-type': 'application/json',
        },
    }

def premiumize_item(apikey, id):
    # one cloud file: its name, folder and link / stream_link
    return {
        'method': 'GET',
        'url': 'https://www.premiumize.me/api/item/details?%s' % urlencode({'id': id, 'apikey': apikey}),
    }

def premiumize_check(apikey, hashes):
    return {
        'method': 'POST',
        'url': 'https://www.premiumize.me/api/cache/check?%s' % urlencode({ 'apikey': apikey }),
        'data': {
            'items[]': hashes
        },
    }

def premiumize_cache(apikey, link):
    return {
        'method': 'POST',
        'url': 'https://www.premiumize.me/api/transfer/create?apikey=%s' % apikey,
        'data': {
            'src': link
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

def premiumize_resolve(apikey, link):
    return {
        'method': 'POST',
        'url': 'https://www.premiumize.me/api/transfer/directdl?apikey=%s' % apikey,
        'data': {
            'src': link
        },
    }

def premiumize_account(apikey):
    # the settings window's key check (status success for a working key) and the Debrid window's header
    return {
        'method': 'GET',
        'url': 'https://www.premiumize.me/api/account/info?apikey=%s' % apikey,
        'timeout': 10,
    }
