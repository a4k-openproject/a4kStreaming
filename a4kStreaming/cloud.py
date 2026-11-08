# -*- coding: utf-8 -*-
# action=cloud. type=play plays a Premiumize cloud file: its link / stream_link straight to Kodi's player, with the
# subtitle files next to it. Kodi keeps the resume point against this play URL, which names the file by id, so
# resume survives a new link. Any other type (the old listing's URLs, the widget menu's Debrid) opens the Debrid
# window (ui/debrid.py): Downloads for the transfers, Cloud (at the folder id, if given) otherwise.

from .ui.debrid import SUBTITLES, fetch, Failure

BUSY_LOOKS = 50
BUSY_LOOK = 20  # ms

def cloud(core, params):
    if params.type == 'play':
        # Kodi waits on this call (PlayMedia of the play URL); over the add-on's windows the loader stands in for its
        # busy dialog until the stream plays
        with core.kodi.busy_dialog(native=False):
            if play(core, params.id):
                core.kodi.wait_for_playback()
        return core.skip_end_of_dir

    # a directory Kodi asked for: none, then the window once Kodi's busy dialog for it has closed (Kodi refuses to
    # open a window under a modal dialog)
    core.kodi.xbmcplugin.endOfDirectory(core.handle, succeeded=False)
    for _ in range(BUSY_LOOKS):
        if not core.kodi.xbmc.getCondVisibility('Window.IsActive(busydialog)'):
            break
        core.kodi.xbmc.sleep(BUSY_LOOK)
    from .ui import debrid
    debrid.open('downloads' if params.type == 'premiumize_transfers' else 'cloud', params.id or '')
    return core.skip_end_of_dir

def subtitles(core, apikey, file):
    # the links of the subtitle files beside a cloud file that share its name
    if not file.get('folder_id'):
        return []
    stem = core.os.path.splitext(file.get('name') or '')[0].lower()
    try:
        content = fetch(core, core.debrid.premiumize_files(apikey, file['folder_id'])).get('content') or []
    except Failure:
        return []  # it plays without them
    return [entry['link'] for entry in content
            if entry.get('link') and (entry.get('name') or '').lower().startswith(stem)
            and (entry.get('name') or '').rsplit('.', 1)[-1].lower() in SUBTITLES]

def play(core, id):
    apikey = core.utils.get_premiumize_apikey(core)
    if not apikey or not id:
        core.kodi.notification('Missing Premiumize API key' if not apikey else 'Missing file id')
        core.utils.end_action(core, False)
        return False
    try:
        file = fetch(core, core.debrid.premiumize_item(apikey, id))
        link = file.get('link') or file.get('stream_link')
        if not link:
            raise Failure('This file has no link to play')
        found = subtitles(core, apikey, file)
    except Failure as failure:
        core.kodi.notification(str(failure))
        core.utils.end_action(core, False)
        return False

    name = file.get('name') or ''
    item = core.kodi.xbmcgui.ListItem(label=name, path=link, offscreen=True)
    item.setProperty('IsPlayable', 'true')
    item.setContentLookup(False)
    core.kodi.set_info_tag(item, {'title': core.os.path.splitext(name)[0], 'mediatype': 'video'})
    if found:
        item.setSubtitles(found)
    core.utils.end_action(core, True, item)
    return True
