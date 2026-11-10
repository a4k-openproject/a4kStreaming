# -*- coding: utf-8 -*-

import json
import requests
import threading
import urllib3

from http.cookiejar import DefaultCookiePolicy
from urllib.parse import urlparse

from requests.adapters import HTTPAdapter

from . import logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"

retry_statuses = (408, 429, 500, 502, 503, 504)
attempts = 3
stale_max_age = 24 * 60 * 60
# stale reads served this call, fetched again after the listing is shown (core.main)
pending_revalidation = []

__local = threading.local()

def get_session():
    # one Session per thread keeps connections alive across calls without sharing a Session between threads
    session = getattr(__local, 'session', None)
    if session is None:
        session = requests.Session()
        # never keep response cookies: each call sends exactly the cookies it passes, as with a fresh Session
        session.cookies.set_policy(DefaultCookiePolicy(allowed_domains=[]))
        # no adapter retries: execute() owns retrying, so attempts never multiply across layers
        session.mount("https://", HTTPAdapter(pool_maxsize=100))
        __local.session = session
    return session

def probe(url, timeout=5):
    # one attempt, no retry adapter or 503 re-run: a dead host costs a single timeout
    try:
        response = requests.get(url, headers={'User-Agent': user_agent, 'Range': 'bytes=0-0'}, timeout=timeout, stream=True, verify=False)
        response.close()
        return 200 <= response.status_code < 400
    except Exception:
        return False

def graphql_failed(content):
    # IMDb answers 200 with an `errors` array and no data (an expired cursor, a bad id): that is a failure, not a page
    if (b'"errors"' if isinstance(content, bytes) else '"errors"') not in content:
        return False
    try:
        body = json.loads(content)
    except Exception:
        return False
    data = body.get('data', None)
    return bool(body.get('errors', None)) and (not data or all(v is None for v in data.values()))

def __send(core, session, request):
    response = None
    stopped = getattr(threading.current_thread(), 'stopped', None)  # an a4k window's thread (ui/home.py spawn)
    for attempt in range(attempts):
        if attempt:
            if stopped is not None and stopped.is_set():
                break  # its window closed: no retry, so the thread ends soon after
            if response is not None:
                response.close()
            core.time.sleep(0.35 * 2 ** (attempt - 1))
        try:
            response = session.request(verify=False, **request)
            exc = ''
        except Exception:
            exc = core.traceback.format_exc()
            response = None
        if response is not None and response.status_code not in retry_statuses:
            break
        logger.debug('%s ! - %s - attempt %s: %s' % (request['method'], request['url'], attempt + 1, response.status_code if response is not None else exc))

    if response is None:
        response = lambda: None
        response.text = ''
        response.content = ''
        response.status_code = 500
    return response

def __is_read(request):
    # only GETs and GraphQL queries are cached; a GraphQL mutation or any other POST may change server state
    if request['method'] == 'GET':
        return True
    if 'graphql.imdb.com' not in request['url']:
        return False
    try:
        return not json.loads(request.get('data', '{}'))['query'].lstrip().startswith('mutation')
    except Exception:
        return False

def execute(core, request, cache=True, stale_ok=False):
    # cache: True = the 5 s de-duplication, a number = seconds a read stays fresh.
    # stale_ok: an older read (up to a day) is answered at once and fetched again after the listing renders.
    session = get_session()

    # a thread of an a4k window carries a shorter one (ui/home.py spawn): a closed window's thread ends sooner
    request.setdefault('timeout', getattr(threading.current_thread(), 'request_timeout', 60))
    headers = request.setdefault('headers', {})
    headers.setdefault('User-Agent', user_agent)

    logger.debug('%s ^ - %s' % (request['method'], request['url']))
    read = __is_read(request)
    ttl = 5 if cache is True else cache
    cache = cache and read
    # cache keys start with the host, so a write clears exactly what it can make stale; the token is part of the
    # key so one account never reads another's ratings
    host = urlparse(request['url']).hostname or ''
    request_hash = '%s_%s' % (host, core.utils.hash({
        'url': request['url'], 'method': request['method'], 'data': request.get('data', ''),
        'token': request.get('cookies', {}).get('at-main', ''),
    }))
    age = core.db.age(request_hash) if cache else None
    fresh = age is not None and age < ttl
    stale = not fresh and stale_ok and age is not None and age < stale_max_age and not core.api_mode_enabled
    if fresh or stale:
        core.logger.debug('Cache hit%s: %s' % (' (stale)' if stale else '', request_hash))
        response = lambda: None
        response.text = ''
        response.content = core.db.get(request_hash)
        response.status_code = 200
        response.fetched_at = core.time.time() - age
        if stale:
            pending_revalidation.append((request, ttl))
    else:
        if cache:
            core.logger.debug('Cache miss: %s' % request_hash)
        response = __send(core, session, request)
        response.fetched_at = core.time.time()
        if response.status_code == 200 and cache and not graphql_failed(response.content):
            core.db.set(request_hash, response.content)
        if not read:
            # even a failed write may have landed: drop every cached read from that host
            core.db.clear(host)
    logger.debug('%s $ - %s - %s' % (request['method'], request['url'], response.status_code))

    return response

def revalidate(core):
    # the home window's row threads run this side by side (core.listing_items): each takes what is left
    while True:
        try:
            request, ttl = pending_revalidation.pop(0)
        except IndexError:
            return
        execute(core, request, ttl)
