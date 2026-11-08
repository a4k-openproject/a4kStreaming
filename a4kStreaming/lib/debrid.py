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
    # the settings window's key check: answers status success for a working key
    return {
        'method': 'GET',
        'url': 'https://www.premiumize.me/api/account/info?apikey=%s' % apikey,
        'timeout': 10,
    }
