# -*- coding: utf-8 -*-
# The repository add-on: its zip (scripts/make_repository.py) and its listing in packages/addons.xml, so Kodi updates it.

import importlib.util
import os
import zipfile
from xml.etree import ElementTree

from .common import pytest, api

@pytest.fixture(scope='module', autouse=True)
def kodi_mock():
    # conftest's autouse fixture imports the add-on, which needs the Kodi mock even though these tests do not
    api.A4kStreamingApi({'kodi': True})

ROOT = os.path.join(os.path.dirname(__file__), '..')
PACKAGES = os.path.join(ROOT, 'packages')
SRC = os.path.join(PACKAGES, 'repository.a4kstreaming')

def _builder():
    spec = importlib.util.spec_from_file_location('make_repository', os.path.join(ROOT, 'scripts', 'make_repository.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _read(path):
    with open(path, 'rb') as f:
        return f.read()

def test_the_repository_zip_is_deterministic_and_matches_its_source(tmp_path):
    make = _builder()
    a, b = str(tmp_path / 'a.zip'), str(tmp_path / 'b.zip')
    make.build(a)
    make.build(b)
    assert _read(a) == _read(b)
    z = zipfile.ZipFile(a)
    names = sorted(os.listdir(SRC), key=str.lower)
    assert z.namelist() == ['a4kStreaming-repository/'] + ['a4kStreaming-repository/' + n for n in names]
    for n in names:
        assert z.read('a4kStreaming-repository/' + n) == _read(os.path.join(SRC, n))
    assert {i.date_time for i in z.infolist()} == {(2026, 1, 1, 0, 0, 0)} and not any(i.extra for i in z.infolist())

def test_the_committed_repository_zip_is_a_fresh_build(tmp_path):
    out = str(tmp_path / 'r.zip')
    _builder().build(out)
    assert _read(out) == _read(os.path.join(PACKAGES, 'a4kStreaming-repository.zip')), 'run scripts/make_repository.py'

def test_addons_xml_lists_the_plugin_and_the_repository_at_their_versions():
    listed = {a.get('id'): a.get('version') for a in ElementTree.parse(os.path.join(PACKAGES, 'addons.xml')).getroot()}
    own = [ElementTree.parse(p).getroot() for p in (os.path.join(ROOT, 'addon.xml'), os.path.join(SRC, 'addon.xml'))]
    assert listed == {a.get('id'): a.get('version') for a in own}
    assert set(listed) == {'plugin.video.a4kstreaming', 'repository.a4kstreaming'}

def test_the_repository_add_on_has_both_dirs():
    addon = ElementTree.parse(os.path.join(SRC, 'addon.xml')).getroot()
    dirs = list(addon.iter('dir'))
    assert [d.findtext('info').split('/')[4] for d in dirs] == ['a4kStreaming', 'a4kSubtitles']
    assert [d.findtext('datadir') for d in dirs] == ['https://github.com/a4k-openproject/a4kStreaming/archive',
                                                     'https://github.com/a4k-openproject/a4kSubtitles/archive']
    urls = [u.text for d in dirs for u in d]  # all on the projects' owner, never through a rename redirect
    assert len(urls) == 8 and all(u.split('/')[3] == 'a4k-openproject' for u in urls)
