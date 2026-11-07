# -*- coding: utf-8 -*-

from .listing import (
    __handle_request_error,
)

def cloud(core, params):
    items = []
    video_ext = list(map(lambda v: '.%s' % v.upper(), core.utils.video_containers()))

    if params.type == 'root':
        items.extend([
            {
                'label': 'Premiumize - Files',
                'action': 'cloud',
                'type': 'premiumize_files',
                'info': 'Browse Premiumize files.',
                'subitems': True
            },
            {
                'label': 'Premiumize - Transfers',
                'action': 'cloud',
                'type': 'premiumize_transfers',
                'info': 'See Premiumize transfers.',
                'subitems': True
            }
        ])

    elif params.type.startswith('premiumize_'):
        apikey = core.utils.get_premiumize_apikey(core)
        if not apikey or apikey == '':
            core.kodi.notification('Missing Premiumize service API key')
            return

        if params.type == 'premiumize_files':
            id = params.id if params.id else ''
            request = core.debrid.premiumize_files(apikey, id)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
                return

            parsed_response = core.json.loads(response.content)

            files = parsed_response.get('content', [])
            for file in files:
                if not file.get('type', None):
                    continue

                if file['type'] == 'file':
                    isvideo = core.os.path.splitext(file['name'])[1].upper() in video_ext
                    subfile = None

                    if not isvideo and not params.force_allfiles:
                        continue

                    filename_without_ext = core.os.path.splitext(file['name'])[0]
                    subfile_ext = ['srt', 'sub', 'ass', 'smi', 'ssa']
                    subfile_names = ['%s.%s' % (filename_without_ext, ext) for ext in subfile_ext]
                    subfiles = [f for f in files if any(subfile_name in f['name'] for subfile_name in subfile_names)]
                    subfile = next(iter(subfiles), None)

                    items.append({
                        'label': file['name'],
                        'subitems': False,
                        'url': file.get('link', file.get('stream_link', None)) if isvideo else '',
                        'subfile': subfile.get('link', None) if subfile else None,
                        'contextmenu': {
                            'Premiumize: Delete': 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=cloud&type=premiumize_file_delete&id=%s)' % file['id']
                        }
                    })
                elif file['type'] == 'folder':
                    items.append({
                        'label': file['name'],
                        'action': 'cloud',
                        'type': 'premiumize_files',
                        'info': '',
                        'subitems': True,
                        'params': {
                            'id': file['id'],
                        },
                        'contextmenu': {
                            'Premiumize: All Files': 'ActivateWindow(Videos,plugin://plugin.video.a4kstreaming/?action=cloud&type=premiumize_files&id=%s&force_allfiles=true,return)' % file['id'],
                            'Premiumize: Delete': 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=cloud&type=premiumize_folder_delete&id=%s)' % file['id'],
                        }
                    })

        elif params.type == 'premiumize_transfers':
            request = core.debrid.premiumize_transfers(apikey)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
                return

            parsed_response = core.json.loads(response.content)

            transfers = parsed_response.get('transfers', [])
            for transfer in transfers:
                isfinished = transfer['status'] == 'finished'
                label = '[%s] %s' % (('Completed' if isfinished else transfer.get('message', ('%s%%' % transfer['progress']))), transfer['name'])

                items.append({
                    'label': label,
                    'action': 'cloud',
                    'type': 'premiumize_files',
                    'info': '',
                    'subitems': isfinished if transfer['file_id'] is None else False,
                    'url': None if isfinished and transfer['file_id'] is None else '',
                    'params': {
                        'id': transfer['folder_id'],
                    },
                    'contextmenu': {
                        'Premiumize: Delete': 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=cloud&type=premiumize_transfer_delete&id=%s)' % transfer['id'],
                        'Premiumize: Clear Finished': 'RunPlugin(plugin://plugin.video.a4kstreaming/?action=cloud&type=premiumize_transfer_clearfinished&id=%s)' % transfer['id']
                    }
                })

        elif params.type == 'premiumize_file_delete':
            request = core.debrid.premiumize_file_delete(apikey, params.id)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
            else:
                core.kodi.notification('PM file removed: %s' % params.id)

            core.utils.end_action(core, True)
            return core.skip_end_of_dir

        elif params.type == 'premiumize_folder_delete':
            request = core.debrid.premiumize_folder_delete(apikey, params.id)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
            else:
                core.kodi.notification('PM folder removed: %s' % params.id)

            core.utils.end_action(core, True)
            return core.skip_end_of_dir

        elif params.type == 'premiumize_transfer_delete':
            request = core.debrid.premiumize_transfer_delete(apikey, params.id)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
            else:
                core.kodi.notification('PM transfer removed: %s' % params.id)

            core.utils.end_action(core, True)
            return core.skip_end_of_dir

        elif params.type == 'premiumize_transfer_clearfinished':
            request = core.debrid.premiumize_transfer_clearfinished(apikey)
            response = core.request.execute(core, request)
            if response.status_code != 200:
                __handle_request_error(core, params, response)
            else:
                core.kodi.notification('PM cleared finished transfers')

            core.utils.end_action(core, True)
            return core.skip_end_of_dir

        else:
            core.not_supported()
            return

    else:
        core.not_supported()
        return

    list_items = core.utils.generic_list_items(core, items)
    core.kodi.xbmcplugin.addDirectoryItems(core.handle, list_items, len(list_items))
    return items
