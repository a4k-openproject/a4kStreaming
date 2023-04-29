# -*- coding: utf-8 -*-

import requests
import urllib3

from requests.adapters import HTTPAdapter
from urllib3 import Retry

from . import logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"

def __retry_on_503(core, request, response, retry=True):
    if not retry:
        return None

    if response.status_code == 503:
        core.time.sleep(2)
        request['validate'] = lambda response: __retry_on_503(core, request, response, retry=False)
        return request

def execute(core, request, session=None):
    if not session:
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
        session.mount("https://", HTTPAdapter(max_retries=retries, pool_maxsize=100))

    request.setdefault('timeout', 10)
    headers = request.setdefault('headers', {})
    headers.setdefault('User-Agent', user_agent)

    validate = request.pop('validate', None)
    next = request.pop('next', None)

    if not validate:
        validate = lambda response: __retry_on_503(core, request, response)

    if next:
        request.pop('stream', None)

    logger.debug('%s ^ - %s' % (request['method'], request['url']))
    try:
        response = session.request(verify=False, **request)
        exc = ''
    except:
        exc = core.traceback.format_exc()
        response = lambda: None
        response.text = ''
        response.content = ''
        response.status_code = 500
    logger.debug('%s $ - %s - %s, %s' % (request['method'], request['url'], response.status_code, exc))

    alt_request = validate(response)
    if alt_request:
        return execute(core, alt_request)

    if next and response.status_code == 200:
        next_request = next(response)
        if next_request:
            return execute(core, next_request)
        else:
            return None

    return response
