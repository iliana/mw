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
# with this program.  If not, see <http://www.gnu.org/licenses/>.
###

import ConfigParser
import json
import os
import sys
import time

class Metadir(object):
    def __init__(self):
        self.me = os.path.basename(sys.argv[0])
        root = os.getcwd()
        while True:
            if '.mw' in os.listdir(root):
                self.root = root
                break
            (head, tail) = os.path.split(root)
            if head == root:
                self.root = os.getcwd()
                break
            root = head
        self.location = os.path.join(self.root, '.mw')
        self.config_loc = os.path.join(self.location, 'config')
        if os.path.isdir(self.location) and \
           os.path.isfile(self.config_loc):
            self.config = ConfigParser.RawConfigParser()
            self.config.read(self.config_loc)
        else:
            self.config = None

    def create(self, api_url):
        # create the directory
        if os.path.isdir(self.location):
            print '%s: you are already in a mw repo' % self.me
            sys.exit(1)
        else:
            os.mkdir(self.location, 0755)
        # metadir versioning
        fd = file(os.path.join(self.location, 'version'))
        fd.write('1')
        fd.close()
        # create config
        self.config = ConfigParser.RawConfigParser()
        self.config.add_section('remote')
        self.config.set('remote', 'api_url', api_url)
        with open(self.config_loc, 'wb') as config_file:
            self.config.write(config_file)
        # create cache/
        os.mkdir(os.path.join(self.location, 'cache'))
        # create cache/pagedict
        fd = file(os.path.join(self.location, 'cache', 'pagedict'), 'w')
        fd.write(json.dumps({}))
        fd.close()
        # create cache/pages/
        os.mkdir(os.path.join(self.location, 'cache', 'pages'), 0755)

    def pagedict_add(self, pagename, pageid):
        fd = file(os.path.join(self.location, 'cache', 'pagedict'), 'r+')
        pagedict = json.loads(fd.read())
        pagedict[pagename] = int(pageid)
        fd.seek(0)
        fd.write(json.dumps(pagedict))
        fd.truncate()
        fd.close()

    def pages_add_rev(self, pageid, rv):
        pagefile = os.path.join(self.location, 'cache', 'pages', str(pageid))
        fd = file(pagefile, 'w+')
        pagedata = json.loads(fd.read())
        rvid = int(rv['revid'])
        if pageid not in pagedata.keys():
            pagedata[pageid] = {}
        pagedata[pageid][rvid] = {
                'user': rv['user'], 'timestamp': rv['timestamp'],
                'content': rv['*'],
        }
        fd.seek(0)
        fd.write(json.dumps(pagedata))
        fd.truncate()
        fd.close()
