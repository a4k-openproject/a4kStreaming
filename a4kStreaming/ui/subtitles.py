# -*- coding: utf-8 -*-
# The settings window's Subtitles category: Kodi's own subtitle settings (JSON-RPC) and a4kSubtitles' settings (its
# Addon object) as rows of the window. A row's id says where its value lives: kodi:<Kodi setting id>,
# a4ksubtitles:<its setting id>, or subtitles:<name> for a value made of several (the On / Forced only / Off switch, the
# preferred and alternative languages, the default service). Values cross the window as strings, as our own settings
# do. Missing or disabled, a4kSubtitles is one Install or Enable row, and its own rows show once it is ready.
# The Kodi ids, types and options are those of Kodi 21's system/settings/settings.xml (tests/test_subtitles.py pins
# them); a Kodi write is saved to disk at once (kodi_mode.save), since Kodi on Android is often killed, not quit.

from ..lib import kodi, logger
from .. import kodi_mode

SUBS = 'service.subtitles.a4ksubtitles'
ADDON, ON, PREFERRED, ALTERNATIVE, SERVICE = ('subtitles:addon', 'subtitles:on', 'subtitles:preferred',
                                              'subtitles:alternative', 'subtitles:service')
LANGUAGE, LANGUAGES = 'locale.subtitlelanguage', 'subtitles.languages'
SWITCH = {'none': 'off', 'forced_only': 'forced'}  # the preferred language's values that are the Subtitles switch
NOT_A_LANGUAGE = ('original', 'default')  # audio and interface language: never in the download list
RESHAPE = ('kodi:subtitles.backgroundtype', ON)  # rows show or hide with the background, the switch writes Find subtitles
BOX = ('subtitles.backgroundtype', ('2', '3'))  # Kodi shows the background colour and opacity for a box only
KEPT = 'subtitles.auto_search'  # our hidden setting: a4kSubtitles' automatic search as it was before the switch's Off

def enum(*labels):
    return {'options': list(labels), 'values': [str(i) for i in range(len(labels))]}

COLOURS = {'options': ['White', 'Yellow', 'Grey', 'Black', 'Cyan', 'Green'],
           'values': ['FFFFFFFF', 'FFFFFF00', 'FF808080', 'FF000000', 'FF00FFFF', 'FF00FF00']}
PERCENT = {'min': 0, 'max': 100, 'step': 5, 'format': lambda n: '%s %%' % n}

# a group name, then its rows: (id, kind, label, help, extra). extra: kodi (the Kodi setting it needs), dynamic (its
# options come from Kodi; drop leaves some out), when (shown only while a Kodi setting has one of these values)
ROWS = (
    'a4kSubtitles',
    (ADDON, 'action', 'a4kSubtitles', ''),  # label and help follow its state
    (SERVICE, 'bool', 'Use for movies and episodes', "Kodi's subtitle search opens a4kSubtitles first.",
     {'kodi': 'subtitles.movie'}),
    'Language',
    (ON, 'enum', 'Subtitles', 'Forced only shows the forced subtitles in the audio language. Off loads none.',
     {'kodi': LANGUAGE, 'options': ['On', 'Forced only', 'Off'], 'values': ['on', 'forced', 'off']}),
    (PREFERRED, 'enum', 'Preferred language', 'Loaded first. The download list starts with it.',
     {'kodi': LANGUAGE, 'dynamic': True, 'drop': tuple(SWITCH)}),
    (ALTERNATIVE, 'enum', 'Alternative language', 'Loaded when the preferred language has none.',
     {'kodi': LANGUAGE, 'dynamic': True, 'drop': tuple(SWITCH) + NOT_A_LANGUAGE, 'none': 'None'}),
    ('kodi:accessibility.subhearing', 'bool', 'Prefer hearing impaired', 'Picks subtitles for the hearing impaired first.'),
    ('kodi:locale.audiolanguage', 'enum', 'Audio language', 'The audio track picked first. Forced only follows it.',
     {'dynamic': True}),
    'Auto download',
    ('a4ksubtitles:general.auto_search', 'bool', 'Find subtitles when a video starts',
     'Turns everything below on or off.'),
    ('a4ksubtitles:general.auto_download', 'bool', 'Load the best one silently', 'Off opens the list of found subtitles.'),
    ('a4ksubtitles:general.auto_select', 'bool', 'Use subtitles inside the video first',
     'A subtitle track of the video in the preferred language, before any download.'),
    ('a4ksubtitles:general.prefer_sdh', 'bool', 'Prefer hearing impaired tracks', 'Inside the video only.'),
    ('a4ksubtitles:general.prefer_forced', 'bool', 'Prefer forced tracks', 'Inside the video only.'),
    'AI translation',
    ('a4ksubtitles:general.use_ai', 'bool', 'Translate', 'Downloads English subtitles and translates them into the preferred language.'),
    ('a4ksubtitles:general.ai_provider', 'enum', 'Service', 'The AI service the key belongs to.',
     {'options': ['OpenAI', 'NexosAI'], 'values': ['0', '1']}),
    ('a4ksubtitles:general.ai_api_key', 'secret', 'API key', "The AI service's API key."),
    ('a4ksubtitles:general.ai_model', 'text', 'Model', 'The model the service translates with.'),
    'Providers',
    ('a4ksubtitles:opensubtitles.enabled', 'bool', 'OpenSubtitles', ''),
    ('a4ksubtitles:opensubtitles_quick.enabled', 'bool', 'OpenSubtitles quick', 'Its quick search, tried first.'),
    ('a4ksubtitles:addic7ed.enabled', 'bool', 'Addic7ed', ''),
    ('a4ksubtitles:bsplayer.enabled', 'bool', 'BSPlayer', ''),
    ('a4ksubtitles:podnadpisi.enabled', 'bool', 'Podnadpisi', ''),
    ('a4ksubtitles:subdl.enabled', 'bool', 'SubDL', 'Needs its API key, below.'),
    ('a4ksubtitles:subsource.enabled', 'bool', 'SubSource', 'Needs its API key, below.'),
    'Accounts',
    ('a4ksubtitles:opensubtitles.username', 'secret', 'OpenSubtitles username', 'Optional: more downloads a day.'),
    ('a4ksubtitles:opensubtitles.password', 'secret', 'OpenSubtitles password', 'The password of that username.'),
    ('a4ksubtitles:subdl.apikey', 'secret', 'SubDL API key', 'The key from your subdl.com account.'),
    ('a4ksubtitles:subsource.apikey', 'secret', 'SubSource API key', 'The key from your subsource.net account.'),
    'Search',
    ('a4ksubtitles:general.timeout', 'number', 'Time limit', 'How long a search waits for the providers.',
     {'min': 5, 'max': 20, 'step': 1, 'default': '15', 'format': lambda n: '%s s' % n}),
    ('a4ksubtitles:general.results_limit', 'number', 'Results', 'The most subtitles a search lists.',
     {'min': 10, 'max': 100, 'step': 10, 'default': '20'}),
    ('a4ksubtitles:general.use_chardet', 'bool', 'Detect the file encoding', 'Fixes garbled letters in old files.'),
    'Appearance',
    ('kodi:subtitles.fontname', 'enum', 'Font', 'The typeface.', {'dynamic': True}),
    ('kodi:subtitles.fontsize', 'number', 'Size', 'The text height.', {'min': 12, 'max': 74, 'step': 2, 'default': '42'}),
    ('kodi:subtitles.style', 'enum', 'Style', 'Bold, italics or both.', enum('Normal', 'Bold', 'Italics', 'Bold italics')),
    ('kodi:subtitles.colorpick', 'enum', 'Colour', 'The text colour.', COLOURS),
    ('kodi:subtitles.opacity', 'number', 'Opacity', 'How solid the text is.', dict(PERCENT, default='100')),
    ('kodi:subtitles.bordersize', 'number', 'Border size', 'The outline around the letters.', dict(PERCENT, default='25')),
    ('kodi:subtitles.bordercolorpick', 'enum', 'Border colour', 'The outline colour.', COLOURS),
    ('kodi:subtitles.backgroundtype', 'enum', 'Background', 'Shadow, or a box behind the text.',
     enum('None', 'Shadow', 'Box', 'Square box')),
    ('kodi:subtitles.bgcolorpick', 'enum', 'Background colour', "The box's colour.", dict(COLOURS, when=BOX)),
    ('kodi:subtitles.bgopacity', 'number', 'Background opacity', 'How solid the box is.',
     dict(PERCENT, step=10, default='80', when=BOX)),
    ('kodi:subtitles.align', 'enum', 'Position', 'Where the text sits.',
     enum('Manual', 'Bottom of video', 'Bottom of screen', 'Top of video', 'Top of screen')),
    ('kodi:subtitles.charset', 'enum', 'Character set', 'For files that are not Unicode.', {'dynamic': True}),
    'More',
    ('', 'native', "Kodi's subtitle settings", "Every subtitle setting, in Kodi's own window.",
     {'action': 'ActivateWindow(playersettings,subtitles)'}),
)
ACCOUNTS = 'Accounts'  # their labels name the provider already: a dialog heading drops the group

# a4kSubtitles

def state():
    # ('missing' | 'disabled' | 'ready', its version)
    found = (kodi_mode.rpc('Addons.GetAddons', type='xbmc.subtitle.module', properties=['enabled', 'version']) or {})
    addon = next((a for a in found.get('addons') or [] if a.get('addonid') == SUBS), None)
    if not addon:
        return 'missing', ''
    return 'ready' if addon.get('enabled') else 'disabled', addon.get('version', '')

def act():
    # the a4kSubtitles row's OK: Kodi installs it (its own yes / no, from any installed repository that has it) or it
    # is enabled. True when the section should be rebuilt.
    status, _ = state()
    if status == 'missing':
        offered = kodi_mode.rpc('Addons.GetAddons', type='xbmc.subtitle.module', installed=False)
        if offered is not None and all(a.get('addonid') != SUBS for a in offered.get('addons') or []):
            kodi.notification('a4kSubtitles not found: update the a4kStreaming repository and retry')
        else:  # modal: back once it is installed or declined (Kodi's own prompt, nothing to add)
            kodi.xbmc.executebuiltin('InstallAddon(%s)' % SUBS, True)
    elif status == 'disabled':
        kodi_mode.rpc('Addons.SetAddonEnabled', addonid=SUBS, enabled=True)
    return status != 'ready'

def subs():
    return kodi.xbmcaddon.Addon(SUBS)

# Kodi

def known():
    # Kodi's player language and subtitle settings by id, with their options (the language lists are Kodi's own)
    found = {}
    for category in ('language', 'subtitles'):
        answer = kodi_mode.rpc('Settings.GetSettings', level='expert', filter={'section': 'player', 'category': category})
        found.update((setting['id'], setting) for setting in (answer or {}).get('settings') or [])
    return found

def put(id, value):
    # a Kodi setting, typed as Kodi has it (JSON-RPC refuses '2' for an integer), then saved to disk
    current = kodi_mode.get(id)
    if isinstance(current, bool):
        value = value == 'true'
    elif isinstance(current, (int, float)) and not isinstance(value, list):
        value = type(current)(value)
    kodi_mode.rpc('Settings.SetSettingValue', setting=id, value=value)
    kodi_mode.save()

def languages():
    return kodi_mode.get(LANGUAGES) or []

def text(value):
    return '' if value is None else ('true' if value else 'false') if isinstance(value, bool) else str(value)

# the rows

def rows():
    status, version = state()
    settings, rows, group = known(), [], ''
    for entry in ROWS:
        if not isinstance(entry, tuple):
            group = entry
            continue
        id, kind, label, help = entry[:4]
        extra = dict(entry[4]) if len(entry) > 4 else {}
        source = id.partition(':')[0] or 'ours'
        needs = extra.pop('kodi', id[5:] if source == 'kodi' else None)
        when = extra.pop('when', None)
        # Kodi 21's GetSettings leaves its colour buttons out (seen on the TV box): those few are asked one by one,
        # after the box check (Kodi rejects a hidden setting); a colour is never empty
        if source == 'a4ksubtitles' and status != 'ready' or id == SERVICE and status != 'ready' \
                or when and text(kodi_mode.get(when[0])) not in when[1] \
                or needs and needs not in settings and not kodi_mode.get(needs):
            continue
        row = dict(id=id, kind=kind, label=label, help=help, group=group, source=source, default=None, action=None)
        if extra.pop('dynamic', False):
            drop, none = extra.pop('drop', ()), extra.pop('none', None)
            options = [o for o in settings[needs].get('options') or [] if o.get('value') not in drop]
            if not options:
                continue
            extra.update(options=[o['label'] for o in options], values=[str(o['value']) for o in options])
            if none:
                extra.update(options=[none] + extra['options'], values=[''] + extra['values'])
        row.update(extra)
        if group == ACCOUNTS:
            row['title'] = label
        if id == ADDON:
            row.update(version=version if status == 'ready' else '', label={
                'missing': 'Install a4kSubtitles', 'disabled': 'Enable a4kSubtitles'}.get(status, label), help={
                'missing': 'From your add-on repositories. Its settings then show here.',
                'disabled': 'It is installed but turned off.'}.get(status, 'Finds and loads subtitles when a video starts.'))
        rows.append(row)
    return rows

def get(id):
    source, _, key = id.partition(':')
    if source == 'a4ksubtitles':
        return subs().getSetting(key)
    if source == 'kodi':
        return text(kodi_mode.get(key))
    if id == SERVICE:
        return text(kodi_mode.get('subtitles.movie') == SUBS == kodi_mode.get('subtitles.tv'))
    if id == ALTERNATIVE:
        return (languages()[1:2] or [''])[0]
    if id not in (ON, PREFERRED):
        logger.debug('subtitles: no setting %s' % id)
        return ''
    language = kodi_mode.get(LANGUAGE)
    if id == ON:
        return SWITCH.get(language, 'on')
    # the preferred language; while subtitles are off, the one On turns back on: the first to download
    return (languages()[:1] or [''])[0] if language in SWITCH else text(language)

def set(id, value):
    # True when the rows that show depend on it
    source, _, key = id.partition(':')
    if source == 'a4ksubtitles':
        subs().setSetting(key, value)
    elif source == 'kodi':
        put(key, value)
    elif id == SERVICE:
        for service in ('subtitles.movie', 'subtitles.tv'):
            put(service, SUBS if value == 'true' else '')
    elif id == ALTERNATIVE:  # the download list is the fallback order: the first stays, this one is second
        listed = languages()
        first = listed[:1] or [x for x in [text(kodi_mode.get(LANGUAGE))] if x and x not in tuple(SWITCH) + NOT_A_LANGUAGE]
        if not value:
            put(LANGUAGES, listed[:1] + listed[2:])
        elif value in first or not first:
            kodi.notification('That is already the preferred language' if first else 'Pick the preferred language first')
        else:
            put(LANGUAGES, first + [value] + [x for x in listed[1:] if x != value])
    elif id == ON:
        was = kodi_mode.get(LANGUAGE)
        put(LANGUAGE, {'off': 'none', 'forced': 'forced_only'}.get(value) or (languages()[:1] or ['original'])[0])
        if state()[0] == 'ready':  # Off loads none: a4kSubtitles' search stops, and leaving Off puts it back as it was
            own = kodi.xbmcaddon.Addon(kodi.addon_id)  # Forced only needs no write: a4kSubtitles reads forced_only itself
            if value == 'off' and was != 'none':
                own.setSetting(KEPT, subs().getSetting('general.auto_search'))
                subs().setSetting('general.auto_search', 'false')
            elif value != 'off' and was == 'none' and own.getSetting(KEPT):
                subs().setSetting('general.auto_search', own.getSetting(KEPT))
                own.setSetting(KEPT, '')
    elif id == PREFERRED:  # first in the download list too: a4kSubtitles finds only what that list has
        if kodi_mode.get(LANGUAGE) not in SWITCH:
            put(LANGUAGE, value)
        if value not in NOT_A_LANGUAGE:  # already listed: it swaps places with the first, so no entry is lost
            listed = languages()
            if value in listed:
                listed[listed.index(value)] = listed[0]
            put(LANGUAGES, [value] + listed[1:])
    else:
        logger.debug('subtitles: no setting %s' % id)
    return id in RESHAPE
