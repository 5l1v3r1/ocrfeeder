#!/usr/bin/env python

import sys
import os
local_src = os.path.dirname(os.path.abspath(__file__)) + '/src'
if os.path.exists(local_src):
    sys.path = [local_src] + sys.path

from distutils.core import setup
from ocrfeeder.util import constants
import glob

def get_locale_files():
    files = glob.glob('locale/*/*/*.mo')
    locale_dir = os.path.split(constants.LOCALE_DIR)[0]
    file_list = []
    for file in files:
        file_list.append((os.path.dirname(os.path.join(locale_dir, file)), [file]))
    return file_list

setup(name = 'ocrfeeder',
     version = constants.OCRFEEDER_STUDIO_VERSION,
     description = '''A complete Optical Character Recognition and
                      Document Analysis and Recognition program.''',
     author = 'Joaquim Rocha',
     author_email = 'joaquimrocha1@gmail.com',
     url = constants.OCRFEEDER_WEBSITE,
     license = 'GPL v3',
     packages = ['ocrfeeder', 'ocrfeeder.feeder', 'ocrfeeder.studio',
                 'ocrfeeder.util', 'ocrfeeder.odf',
                 ],
     package_dir = {'': 'src'},
     scripts = ['ocrfeeder', 'ocrfeeder-cli'],
     data_files = [(constants.DEFAULT_SYSTEM_APP_DIR +
                    '/icons', ['resources/icons/detect_icon.svg',
                               'resources/icons/ocr.svg',
                               'resources/icons/window_icon.png']
                   ),
                   ('/usr/share/icons/hicolor/scalable/apps', ['resources/icons/ocrfeeder.svg']
                   ),
                   ('/usr/share/applications', ['resources/ocrfeeder.desktop']
                   ),
                   ('/usr/share/man/man1', ['resources/ocrfeeder.1',
                                            'resources/ocrfeeder-cli.1']
                   ),
                   ('/usr/share/ocrfeeder', ['resources/spell-checker.ui']),
                   ] + get_locale_files()
     )
