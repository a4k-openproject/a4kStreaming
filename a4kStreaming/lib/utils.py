# -*- coding: utf-8 -*-

import os
import sys
import re
import json
import random
import string
import zipfile
import shutil
import time
import base64
from datetime import datetime
from io import BytesIO
from itertools import islice
from contextlib import closing
from . import kodi, logger

try:
    from urlparse import unquote, parse_qsl
    from urllib import quote_plus
    import urllib2 as urllib
    from StringIO import StringIO
    import Queue as queue
except ImportError:
    from urllib.parse import quote_plus, unquote, parse_qsl
    import urllib
    from io import StringIO
    import queue
    unicode = lambda v: v

py2 = sys.version_info[0] == 2
py3 = not py2

default_encoding = 'utf-8'
zip_utf8_flag = 0x800
py3_zip_missing_utf8_flag_fallback_encoding = 'cp437'
recommended = base64.b64decode('VE9SUkVOVElP')
if py3:
    recommended = recommended.decode('ascii')

temp_dir = os.path.join(kodi.addon_profile, 'temp')
provider_temp_dir = os.path.join(kodi.addon_profile, 'provider-temp')
provider_data_dir = os.path.join(kodi.addon_path, 'providerData')
provider_sources_dir = os.path.join(kodi.addon_path, 'providers')
provider_modules_dir = os.path.join(kodi.addon_path, 'providerModules')

kodi.xbmcvfs.mkdirs(temp_dir)
kodi.xbmcvfs.mkdirs(provider_temp_dir)
kodi.xbmcvfs.mkdirs(provider_data_dir)

class DictAsObject(dict):
    def __getattr__(self, name):
        item = self.get(name, None)
        if isinstance(item, DictAsObject):
            return item
        if isinstance(item, dict):
            return DictAsObject(item)
        return item

    def __setattr__(self, name, value):
        self[name] = value

def safe_list_get(list_items, index, default):
    try:
        return list_items[index]
    except IndexError:
        return default

def versiontuple(v):
    if not v: return (0, 0, 0)
    version_parts = v.split('.')
    while len(version_parts) < 3: version_parts.append('0')
    version_parts = [(int(v_part) if v_part.isdigit() else 0) for v_part in version_parts]
    return tuple(map(int, version_parts))

def chunk(it, size):
    it = iter(it)
    return iter(lambda: tuple(islice(it, size)), ())

def open_file_wrapper(file, mode='r', encoding='utf-8'):
    if py2:
        return lambda: open(file, mode)
    return lambda: open(file, mode, encoding=encoding)

def get_json(path, filename):
    path = path if os.path.isdir(path) else os.path.dirname(path)
    if not filename.endswith('.json'):
        filename += '.json'

    json_path = os.path.join(path, filename)
    if not os.path.exists(json_path):
        return {}

    with open_file_wrapper(json_path)() as json_result:
        return json.load(json_result)

def imdb_auth_request_props():
    return {
        'headers': {
            'content-type': 'application/json',
            'x-amzn-sessionid': '%s-%s-%s' % (random_digit_str(3), random_digit_str(7), random_digit_str(7)),
            'x-imdb-client-name': 'imdb-web-next',
            'x-imdb-user-language': 'en-US',
            'x-imdb-user-country': 'US'
        },
        'cookies': {
            'ubid-main': '%s-%s-%s' % (random_digit_str(3), random_digit_str(7), random_digit_str(7)),
            'at-main': kodi.get_setting('imdb.at-main'),
        }
    }

def rd_auth_query_params(core, rd_api_key=None):
    rd_apikey = rd_api_key if rd_api_key else get_realdebrid_apikey(core)
    return '?client_id=X245A4XAIBGVM&auth_token=%s' % rd_apikey

def ad_auth_query_params(core, ad_api_key=None):
    ad_apikey = ad_api_key if ad_api_key else get_alldebrid_apikey(core)
    return '&agent=%s&apikey=%s' % (core.kodi.addon_name, ad_apikey)

def time_ms():
    return int(round(time.time() * 1000))

def download_zip(core, zip_url, zip_name):
    filepath = os.path.join(temp_dir, zip_name)

    if zip_url.startswith('ftp://'):
        with closing(urllib.urlopen(zip_url)) as r:
            with open(filepath, 'wb') as f:
                shutil.copyfileobj(r, f)
        return filepath

    request = {
        'method': 'GET',
        'url': zip_url,
        'stream': True,
        'timeout': 15
    }

    with core.request.execute(core, request) as r:
        with open(filepath, 'wb') as f:
            shutil.copyfileobj(r.raw, f)

    return filepath

def extract_zip_member(zip, member, dest):
    if py2:
        zip.extract(member.encode(default_encoding), dest)
    else:
        try:
            zip.extract(member, dest)
        except:
            member = member.encode(default_encoding).decode(py3_zip_missing_utf8_flag_fallback_encoding)
            zip.extract(member, dest)

def extract_zip(src, dest):
    with open(src, 'rb') as f:
        zip = zipfile.ZipFile(BytesIO(f.read()))

    shutil.rmtree(dest, ignore_errors=True)

    infolist = zip.infolist()
    if infolist[0].filename.endswith('/'):
        extract_dir = os.path.dirname(dest)
        zip_root = infolist[0].filename
        rename = True
    else:
        extract_dir = dest
        zip_root = ''
        rename = False

    if py2:
        for info in infolist:
            filename = info.filename.decode(default_encoding)
            extract_zip_member(zip, filename, extract_dir)
    else:
        for info in infolist:
            filename = info.filename
            if not info.flag_bits & zip_utf8_flag:
                filename = info.filename.encode(py3_zip_missing_utf8_flag_fallback_encoding).decode(default_encoding)
            extract_zip_member(zip, filename, extract_dir)

    if rename:
        os.rename(os.path.join(extract_dir, zip_root), dest)

def random_digit_str(length):
    return ''.join(random.choice(string.digits) for _ in range(length))

def get_premiumize_apikey(core):
    return core.kodi.get_setting('premiumize.apikey')

def get_realdebrid_apikey(core):
    return core.kodi.get_setting('realdebrid.apikey')

def get_alldebrid_apikey(core):
    return core.kodi.get_setting('alldebrid.apikey')

def get_color_string(string, color):
    return '[B][COLOR %s]%s[/COLOR][/B]' % (color, string)

def video_containers():
    return ['3GP', '3G2', 'ASF', 'WMV', 'AVI', 'DIVX', 'EVO', 'F4V', 'FLV', 'MKV', 'MK3D', 'MP4', 'M4V', 'MPG', 'MPEG', 'M2P', 'PS', 'TS', 'M2TS', 'MXF', 'OGG', 'OGV', 'OGX', 'MOV', 'QT', 'RMVB', 'VOB', 'WEBM']

def clean_release_title(title):
    return re.sub(r'\s+', ' ', re.sub(r'\-|\_|\.|\,|\?|\!|\[|\]|\{|\}|\(|\)|\||\'|\"|\|\\|\/|\`|\~|\^|\<|\>', ' ', title))

def cleanup_result(result, no_meta=False):
    title = result['release_title'].upper()

    containers = list(map(lambda v: re.escape(' %s ' % v), video_containers()))
    videocodec = ''
    for container in containers:
        if container in title:
            videocodec = container
    if 'HEVC' in title: videocodec = 'H265'
    if 'AVC' in title: videocodec = 'H264'
    if 'X265' in title: videocodec = 'H265'
    if 'X.265' in title: videocodec = 'H265'
    if 'H265' in title: videocodec = 'H265'
    if 'H.265' in title: videocodec = 'H265'
    if 'H264' in title: videocodec = 'H264'
    if 'H.264' in title: videocodec = 'H265'
    if 'X264' in title: videocodec = 'H264'
    if 'X.264' in title: videocodec = 'H264'

    result['videocodec'] = videocodec

    hdr = ''
    if 'HDR' in title: hdr = 'HDR'
    if 'HDR10' in title: hdr = 'HDR10'
    if 'HDR10+' in title: hdr = 'HDR10+'
    if 'DV' in title: hdr = 'DV'
    if 'DOLBY VISION' in title: hdr = 'DV'
    if 'SDR' in title: hdr = 'SDR'

    bits = ''
    if '12BIT' in title: bits = ' 12BIT'
    if '10BIT' in title: bits = ' 10BIT'
    if '8BIT' in title: bits = ' 8BIT'

    result['hdr'] = hdr + bits

    if 'MKV' in title:
        result['mkv'] = True

    rip = ''
    if 'WEBRIP' in title: rip = 'WEBRIP'
    if 'WEB-DL' in title: rip = 'WEB-DL'
    if 'WEB.DL' in title: rip = 'WEB-DL'
    if 'WEBDL' in title: rip = 'WEB-DL'
    if 'WEB' in title: rip = 'WEB'
    if 'DVD-RIP' in title: rip = 'DVD'
    if 'DVD.RIP' in title: rip = 'DVD'
    if 'DVDRIP' in title: rip = 'DVD'
    if 'BLURAY' in title: rip = 'BLURAY'
    if 'BD-RIP' in title: rip = 'BLURAY'
    if 'BD.RIP' in title: rip = 'BLURAY'
    if 'BDRIP' in title: rip = 'BLURAY'
    if 'HDTV' in title: rip = 'HDTV'
    if 'UHD' in title: rip = 'UHD'

    result['rip'] = rip

    audiocodec = ''
    if 'AAC' in title: audiocodec = 'AAC'
    if 'DTS' in title: audiocodec = 'DTS'
    if 'HDMA' in title: audiocodec = 'HD-MA'
    if 'HD-MA' in title: audiocodec = 'HD-MA'
    if 'HD.MA' in title: audiocodec = 'HD-MA'
    if 'ATMOS' in title: audiocodec = 'ATMOS'
    if 'TRUEHD' in title: audiocodec = 'TRUEHD'
    if 'TRUE-HD' in title: audiocodec = 'TRUEHD'
    if 'TRUE.HD' in title: audiocodec = 'TRUEHD'
    if 'DD' in title: audiocodec = 'DD'
    if 'DD2' in title: audiocodec = 'DD'
    if 'DD5' in title: audiocodec = 'DD'
    if 'DD7' in title: audiocodec = 'DD'
    if 'AC3' in title: audiocodec = 'DD'
    if 'DD+' in title: audiocodec = 'DD+'
    if 'DDP' in title: audiocodec = 'DD+'
    if 'EAC3' in title: audiocodec = 'DD+'
    if 'MP3' in title: audiocodec = 'MP3'
    if 'WMA' in title: audiocodec = 'WMA'

    result['audiocodec'] = audiocodec

    title = re.sub(r'\'|\’', '', title)
    title = re.sub(r'COMPLETE|INTERNAL|AUHDTV|SUB', ' ', title)
    title = re.sub(r'HEVC|X265|X\.265|H265|H\.265|X264|X\.264|H264|H\.264|AVC|XVID|DIVX|WMV|MKV', ' ', title)
    title = re.sub(r'HDR10\+|HDR10|HDR|12BIT|10BIT|8BIT|SDR|DOLBY VISION', ' ', title)
    title = re.sub(r'WEBRIP|WEB\-DL|WEB\.DL|WEBDL|WEB|DVD\-RIP|DVD\.RIP|DVDRIP|DVD|BLURAY|BD\-RIP|BD\.RIP|BDRIP|HDTV|UHD|FULLHD', ' ', title)
    title = re.sub(r'AAC|DTS|HDMA|HD\-MA|HD\.MA|ATMOS|TRUEHD|TRUE\-HD|TRUE\.HD|DD\+|DDP|DD|EAC3|AC3|MP3|WMA', ' ', title)
    title = re.sub(r'HD|SD|DV', ' ', title)
    title = re.sub(r'\:|\\|\/|\,|\||\!|\?|\(|\)|\"|\+|\[|\]|\_|\.|\{|\}', ' ', title)

    if result['ref'].season:
        season = str(result['ref'].season)
        if ('S%s' % season.zfill(2)) in title or ('S%s' % season) in title:
            title = re.sub(r'SEASON ' + season.zfill(2) + r' ', ' ', title)
            title = re.sub(r'SEASON ' + season + r' ', ' ', title)

    title = re.sub(r'\-', ' ', title)
    title = re.sub(r'|'.join(containers), ' ', title)

    audiochannel = ''
    if '2 0 ' in title: audiocodec = ' 2.0'
    if '2 0CH' in title: audiocodec = ' 2.0'
    if '2CH' in title: audiocodec = ' 2.0'
    if '5 1 ' in title: audiocodec = ' 5.1'
    if '5 1CH' in title: audiocodec = ' 5.1'
    if '6CH' in title: audiocodec = ' 5.1'
    if '7 1 ' in title: audiocodec = ' 7.1'
    if '7 1CH' in title: audiocodec = ' 7.1'
    if '8CH' in title: audiocodec = ' 7.1'

    if audiochannel:
        if result['audiocodec'] == '':
            result['audiocodec'] = audiochannel
        else:
            result['audiocodec'] += ' %s' % audiochannel

    title = re.sub(r'2 0 |2 0CH|2CH|5 1 |5 1CH|6CH|7 1 |7 1CH|8CH', ' ', title)

    quality = 'SD'
    if '4K' in title: quality = '4K'
    if '2160' in title: quality = '4K'
    if '1080' in title: quality = '1080P'
    if '720' in title: quality = '720P'

    bad_quality_indicators = [' CAM ', 'CAMRIP', 'HDCAM', 'HD CAM', ' TS ', 'HD TS', 'HDTS', 'TELESYNC', ' TC ', 'HD TC', 'HDTC', 'TELECINE']
    if any(i in title for i in bad_quality_indicators):
        quality = "CAM"

    result['quality'] = quality
    title = re.sub(r'4K|2160P|2160|1080P|1080|720P|720|480P|480', ' ', title)

    targets_to_remove = [result['ref'].title, result['ref'].tvshowtitle, result['ref'].year] + bad_quality_indicators
    if isinstance(result['ref'].country, list):
        targets_to_remove += result['ref'].country
    else:
        targets_to_remove.append(result['ref'].country)

    for target in targets_to_remove:
        if not target:
            continue

        target = str(target).strip().upper()
        if target == '':
            continue

        title = re.sub(re.escape(target.upper()), ' ', title)

    title = re.sub(r'\s+', ' ', title)
    title = re.sub(r'\&', 'AND', title)

    result['release_title'] = title.strip()
    result['title'] = '%s GB' % result['size']

    if not no_meta:
        result['title'] += '  |  %s' % get_color_string(result['quality'], 'white')

    if not no_meta:
        if result['hdr'] != '':
            result['title'] += ' %s' % get_color_string(result['hdr'], 'white')
        if result['videocodec'] != '':
            result['title'] += '  |  %s' % result['videocodec']
        if result['audiocodec'] != '':
            result['title'] += '  |  %s' % result['audiocodec']
        # if result['rip'] != '':
        #     result['title'] += '  |  %s' % result['rip']

    result['title'] += '  |  %s' % result['release_title']

def end_action(core, success, item=None):
    if not item:
        item = core.kodi.xbmcgui.ListItem(offscreen=True)
    core.kodi.xbmcplugin.setResolvedUrl(core.handle, success, item)

def generic_list_items(core, items):
    list_items = []
    for item in items:
        list_item = core.kodi.xbmcgui.ListItem(label=item['label'], offscreen=True)
        list_item.setArt({
            'icon': core.kodi.addon_icon,
            'thumb': core.kodi.addon_icon,
            'poster': core.kodi.addon_icon,
            'landscape': core.kodi.addon_icon,
        })

        if item.get('url', None) is not None:
            url = item['url']
        else:
            list_item.setInfo('video', {'mediatype': 'video', 'plot': item['info']})
            url = '%s?action=%s&type=%s' % (core.url, item['action'], item['type'])

            params = item.get('params', {})
            for param in params:
                url += '&%s=%s' % (param, params[param])

        list_item.setContentLookup(False)
        if item.get('subfile', None):
            list_item.setSubtitles([item['subfile']])

        context_menu_items = []
        contextmenu = item.get('contextmenu', {})
        for key in contextmenu:
            context_menu_items.append((key, contextmenu[key]))

        list_item.addContextMenuItems(context_menu_items)
        list_items.append((url, list_item, item['subitems']))

    return list_items

def get_image_params(image, desired_width, desired_height):
    if not image.get('width', None) or not image.get('height', None):
        return 'UX%s' % desired_width

    width = image['width']
    height = image['height']
    ratio = max(float(width) / height, 0.1)
    scaled_width = int(round(desired_height * ratio))
    scaled_height = int(round(desired_width / ratio))
    target_width = desired_width if scaled_height >= desired_height else scaled_width
    target_height = desired_height if scaled_width >= desired_width else scaled_height

    aspect_change = (width > height and desired_width < desired_height)
    cx = 0

    if aspect_change or target_width < desired_width or scaled_height < desired_height:
        params = 'UY%s' % target_height
        if aspect_change:
            cx = (scaled_width - desired_width) / 2
    else:
        params = 'UX%s' % target_width

    return '_V1_%s_CR%s,0,%s,%s_AL_.' % (params, cx, desired_width, desired_height)

def fix_thumb_size(image):
    if image and image.get('url', None):
        return image['url'].replace('_V1_.', get_image_params(image, 480, 270))

def fix_fanart_size(image):
    if image and image.get('url', None):
        return image['url'].replace('_V1_.', get_image_params(image, 900, 506))

def fix_poster_size(image):
    if image and image.get('url', None):
        return image['url'].replace('_V1_.', get_image_params(image, 528, 781))

def apply_viewtype(core):
    kodi.xbmc.executebuiltin('Container.SetViewMode(%s)' % core.viewTypes[int(core.viewType)])

def get_graphql_query(body):
    now = datetime.now()

    fragments = {
        'Title': '''
            fragment Title on Title {
                id
                titleType {
                    id
                }
                titleText {
                    text
                }
                originalTitleText {
                    text
                }
                primaryImage {
                    url
                    width
                    height
                    type
                }
                releaseYear {
                    year
                }
                releaseDate {
                    day
                    month
                    year
                }
                ratingsSummary {
                    aggregateRating
                    voteCount
                }
                certificate {
                    rating
                }
                runtime {
                    seconds
                }
                plot {
                    plotText {
                        plainText
                    }
                }
                genres {
                    genres(limit: $genresLimit) {
                        text
                    }
                }
                primaryVideos(first: 1) {
                    edges {
                        node {
                            id
                        }
                    }
                }
                principalCredits {
                    category {
                        text
                    }
                    credits {
                        name {
                            id
                            nameText {
                                text
                            }
                            primaryImage {
                                url
                                width
                                height
                                type
                            }
                        }
                        ... on Cast {
                            characters {
                                name
                            }
                        }
                    }
                }
                countriesOfOrigin {
                    countries(limit: $countriesLimit) {
                        text
                    }
                }
                companyCredits(first: $companiesLimit) {
                    edges {
                        node {
                            company {
                                companyText {
                                    text
                                }
                            }
                            category {
                                text
                            }
                        }
                    }
                }
                taglines(first: 1) {
                    edges {
                        node {
                            text
                        }
                    }
                },
                episodes {
                    isOngoing
                    seasons {
                        number
                    }
                }
                isAdult
                %s
            }
        ''' % ('userRating { value }' if kodi.get_setting('imdb.at-main') != '' else ''),
        'TitleFull': '''
            fragment TitleFull on Title {
                ...Title
                ...TitleCredits
                images(first: 10, filter: { types: ["still_frame"] }) {
                    edges {
                        node {
                            url
                            width
                            height
                            type
                        }
                    }
                }
                series {
                    series {
                        id
                        titleText {
                            text
                        }
                        primaryImage {
                            url
                            width
                            height
                            type
                        }
                        seasons: episodes {
                            seasons {
                                number
                            }
                        }
                        countriesOfOrigin {
                            countries(limit: $countriesLimit) {
                                text
                            }
                        }
                        nextEpisodeSeasonNumber: episodes {
                            episodes(first: 1, filter: { releasedOnOrAfter: { day: %s, month: %s, year: %s } }) {
                                edges {
                                    node {
                                        series {
                                            episodeNumber {
                                                seasonNumber
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    episodeNumber {
                        episodeNumber
                        seasonNumber
                    }
                }
            }
        ''' % (now.day + 1, now.month, now.year),
        'Episode': '''
            fragment Episode on Title {
                id
                titleType {
                    id
                }
                titleText {
                    text
                }
                originalTitleText {
                    text
                }
                primaryImage {
                    url
                    width
                    height
                    type
                }
                images(first: 10, filter: { types: ["still_frame"] }) {
                    edges {
                        node {
                            url
                            width
                            height
                            type
                        }
                    }
                }
                releaseDate {
                    day
                    month
                    year
                }
                runtime {
                    seconds
                }
                plot {
                    plotText {
                        plainText
                    }
                }
                certificate {
                    rating
                }
                ratingsSummary {
                    aggregateRating
                    voteCount
                }
                %s
            }
        ''' % ('userRating { value }' if kodi.get_setting('imdb.at-main') != '' else ''),
        'TitleCredits': '''
            fragment TitleCredits on Title {
                credits(first: $castLimit, filter: { categories: ["cast"] }) {
                    edges {
                        node {
                            name {
                                id
                                nameText {
                                    text
                                }
                                primaryImage {
                                    url
                                    width
                                    height
                                    type
                                }
                            }
                            ... on Cast {
                                characters {
                                    name
                                }
                            }
                        }
                    }
                }
            }
        ''',
        'Seasons': '''
            fragment Seasons on Title {
                episodes {
                    ... on Episodes {
                        episodes(first: 250, after: $paginationToken) {
                            edges {
                                node {
                                    ... on Title {
                                        id
                                        releaseDate {
                                            day
                                            month
                                            year
                                        }
                                        series {
                                            episodeNumber {
                                                seasonNumber
                                                episodeNumber
                                            }
                                        }
                                        %s
                                    }
                                }
                            }
                            pageInfo {
                                hasNextPage
                                endCursor
                            }
                        }
                    }
                }
            }
        ''' % ('userRating { value }' if kodi.get_setting('imdb.at-main') != '' else ''),
        'Episodes': '''
            fragment Episodes on Title {
                ...Title
                episodes {
                    seasons {
                        number
                    }
                    ... on Episodes {
                        episodes(first: 100, filter: $episodesFilter) {
                            edges {
                                node {
                                    ... on Title {
                                        ...Episode
                                        series {
                                            episodeNumber {
                                                seasonNumber
                                                episodeNumber
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        '''
    }

    def add_fragments(items):
        left = []
        has_added = False

        for key in items:
            if '%s\n' % key in body['query']:
                body['query'] += fragments[key]
                has_added = True
            else:
                left.append(key)

        return (has_added, left)

    has_work = True
    items = fragments.keys()
    while (has_work):
        (has_added, left) = add_fragments(items)
        has_work = has_added
        items = left

    body['variables'].update({
        'genresLimit': 3,
        'castLimit': 20,
        'companiesLimit': 3,
        'countriesLimit': 1
    })

    extra_params = []
    if '$genresLimit' in body['query']:
        extra_params.append('$genresLimit')
    if '$castLimit' in body['query']:
        extra_params.append('$castLimit')
    if '$companiesLimit' in body['query']:
        extra_params.append('$companiesLimit')
    if '$countriesLimit' in body['query']:
        extra_params.append('$countriesLimit')

    extra_params_string = ''
    for param in extra_params:
        extra_params_string += ', %s: Int!' % param

    body['query'] = body['query'].replace(', $EXTRA_PARAMS', extra_params_string)

    request = {
        'method': 'POST',
        'url': 'https://graphql.imdb.com',
        'data': json.dumps(body),
    }
    request.update(imdb_auth_request_props())
    return request

def sanitize_response(response):
    if isinstance(response, list):
        result = []
        for item in response:
            result.append(sanitize_response(item))
        response = result
    elif isinstance(response, dict):
        keys = list(response.keys())
        edges = response.get('edges', None)
        node = response.get('node', None)
        text = response.get('text', None)

        titleType = response.get('titleType', None)
        if titleType is not None:
            response['titleType'] = response['titleType']['id']
            if response['titleType'] == 'tvMiniSeries':
                response['titleType'] = 'tvSeries'

        if edges is not None:
            edges = sanitize_response(edges)
            if len(response) == 1:
                response = edges
            else:
                response['edges'] = edges
        elif node is not None:
            response = sanitize_response(node)
        elif text is not None:
            response = text
        elif len(keys) == 1:
            response = sanitize_response(response[keys[0]])
        else:
            for key in keys:
                response[key] = sanitize_response(response[key])

    return response
