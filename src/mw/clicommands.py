###
# mw - VCS-like nonsense for MediaWiki websites
# Copyright (C) 2009  Ian Weller <ian@ianweller.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
###

import getpass
import mw.api
import mw.metadir
from optparse import OptionParser, OptionGroup
import os
import sys

class CommandBase(object):
    def __init__(self, name, description, usage=None):
        self.me = os.path.basename(sys.argv[0])
        self.description = description
        if usage is None:
            usage = '%prog ' + name
        self.parser = OptionParser(usage=usage, description=description)
        self.name = name
        self.metadir = mw.metadir.Metadir()
        global_options = OptionGroup(self.parser, "Global Options")
        global_options.add_option('-u', '--use-auth', action='store_true',
                                  dest='use_auth', help='force authentication '
                                  'even if not required')
        self.parser.add_option_group(global_options)
        self.shortcuts = []

    def main(self):
        (self.options, self.args) = self.parser.parse_args()
        self.args = self.args[1:] # don't need the first thing
        self._do_command()

    def _login(self):
        user = raw_input('Username: ')
        passwd = getpass.getpass()

    def _die_if_no_init(self):
        if self.metadir.config is None:
            print '%s: not a mw repo' % self.me
            sys.exit(1)

    def _api_setup(self):
        self.api_url = self.metadir.config.get('remote', 'api_url')
        self.api = mw.api.API(self.api_url)


class InitCommand(CommandBase):
    def __init__(self):
        usage = '%prog init API_URL'
        CommandBase.__init__(self, 'init', 'start a mw repo', usage)

    def _do_command(self):
        if len(self.args) < 1:
            self.parser.error('must have URL to remote api.php')
        elif len(self.args) > 1:
            self.parser.error('too many arguments')
        self.metadir.create(self.args[0])


class FetchCommand(CommandBase):
    def __init__(self):
        usage = '%prog fetch [options] PAGENAME ...'
        CommandBase.__init__(self, 'fetch', 'fetch remote pages', usage)
        self.shortcuts.append('ft')

    def _do_command(self):
        self._die_if_no_init()
        self._api_setup()
        pages = []
        pages += self.args
        for these_pages in [pages[i:i+25] for i in range(0, len(pages), 25)]:
            data = {
                    'action': 'query',
                    'titles': '|'.join(these_pages),
                    'prop': 'info|revisions',
                    'rvprop': 'ids|flags|timestamp|user|comment|content',
            }
            response = self.api.call(data)['query']['pages']
            for pageid in response.keys():
                revid = [x['revid'] for x in response[pageid]['revisions']]
                self.metadir.add_page_info(int(pageid),
                                           response[pageid]['title'],
                                           revid)
                self.metadir.add_rv_info(response[pageid]['revisions'][0])
                fd = file(os.path.join(self.metadir.root, \
                        response[pageid]['title'].replace(' ', '_') + \
                        '.wiki'), 'w')
                fd.write(response[pageid]['revisions'][0]['*'].encode('utf-8'))
