###
# mw - VCS-like nonsense for MediaWiki websites
# Copyright (C) 2011  Ian Weller <ian@ianweller.org> and others
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

import bzrlib.diff
import codecs
import ConfigParser
import json
import os
from StringIO import StringIO
import sys


class Metadir(object):

    def __init__(self):
        self.me = os.path.basename(sys.argv[0])
        root = os.getcwd()
        while True:
            if '.mw' in os.listdir(root):
                self.root = root
                break
            head = os.path.split(root)[0]
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
        self.pagedict_loaded = False

    def pagedict_load(self):
        if not self.pagedict_loaded:
            fd = file(os.path.join(self.location, 'cache', 'pagedict'), 'r+')
            self.pagedict = json.loads(fd.read())
            fd.close
            self.pagedict_loaded = True

    def save_config(self):
        with open(self.config_loc, 'wb') as config_file:
            self.config.write(config_file)

    def create(self, api_url):
        # create the directory
        if os.path.isdir(self.location):
            print '%s: you are already in a mw repo' % self.me
            sys.exit(1)
        else:
            os.mkdir(self.location, 0755)
        # metadir versioning
        fd = file(os.path.join(self.location, 'version'), 'w')
        fd.write('1')  # XXX THIS API VERSION NOT LOCKED IN YET
        fd.close()
        # create config
        self.config = ConfigParser.RawConfigParser()
        self.config.add_section('remote')
        self.config.set('remote', 'api_url', api_url)
        self.config.add_section('merge')
        self.config.set('merge', 'tool', 'kidff3 %s %s -o %s')
        self.save_config()
        # create cache/
        os.mkdir(os.path.join(self.location, 'cache'))
        # create cache/pagedict
        fd = file(os.path.join(self.location, 'cache', 'pagedict'), 'w')
        fd.write(json.dumps({}))
        fd.close()
        # create cache/pages/
        os.mkdir(os.path.join(self.location, 'cache', 'pages'), 0755)

    def clean_page(self, pagename):
        filename = pagename_to_filename(pagename) + '.wiki'
        cur_content = codecs.open(filename, 'r', 'utf-8').read()
        if len(cur_content) != 0 and cur_content[-1] == '\n':
            cur_content = cur_content[:-1]
        fd = file(filename, 'w')
        fd.write(cur_content.encode('utf-8'))
        fd.close()

    def pagedict_add(self, pagename, pageid, currentrv):
        self.pagedict_load()
        self.pagedict[pagename] = {'id': int(pageid), 'currentrv': int(currentrv)}
        fd = file(os.path.join(self.location, 'cache', 'pagedict'), 'w')
        fd.write(json.dumps(self.pagedict))
        fd.truncate()
        fd.close()

    def get_pageid_from_pagename(self, pagename):
        self.pagedict_load()
        pagename = pagename.decode('utf-8')
        if pagename in self.pagedict.keys():
            return self.pagedict[pagename]
        else:
            return None

    def pages_add_rv(self, pageid, rv):
        pagefile = os.path.join(self.location, 'cache', 'pages', str(pageid))
        fd = file(pagefile, 'w+')
        pagedata_raw = fd.read()
        if pagedata_raw == '':
            pagedata = {}
        else:
            pagedata = json.loads(pagedata_raw)
        rvid = int(rv['revid'])
        pagedata[rvid] = {
                'user': rv['user'],
                'timestamp': rv['timestamp'],
        }
        if '*' in rv.keys():
            pagedata[rvid]['content'] = rv['*']
        fd.seek(0)
        fd.write(json.dumps(pagedata))
        fd.truncate()
        fd.close()

    def pages_get_rv_list(self, pageid):
        pagefile = os.path.join(self.location, 'cache', 'pages',
                                str(pageid['id']))
        if os.path.exists(pagefile):
            fd = file(pagefile, 'r')
            pagedata = json.loads(fd.read())
            rvs = [int(x) for x in pagedata.keys()]
            rvs.sort()
            return rvs
        else:
            return [None,]

    def pages_get_rv(self, pageid, rvid):
        pagefile = os.path.join(self.location, 'cache', 'pages',
                                str(pageid['id']))
        if os.path.exists(pagefile):
            fd = file(pagefile, 'r')
            pagedata = json.loads(fd.read())
            return pagedata[str(rvid)]
        else:
            return None
            
    def working_dir_status(self, files=None):
        status = {}
        check = []
        if files == None or files == []:
            for root, dirs, files in os.walk(self.root):
                if root == self.root:
                    dirs.remove('.mw')
                for name in files:
                    check.append(os.path.join(root, name))
        else:
            for file in files:
                check.append(os.path.join(os.getcwd(), file))
        check.sort()
        for full in check:
            name = os.path.split(full)[1]
            if name[-5:] == '.wiki':
                pagename = filename_to_pagename(name[:-5])
                pageid = self.get_pageid_from_pagename(pagename)
                if not pageid:
                    status[os.path.relpath(full, self.root)] = '?'
                else:
                    rvid = self.pages_get_rv_list(pageid)[-1]
                    rv = self.pages_get_rv(pageid, rvid)
                    cur_content = codecs.open(full, 'r', 'utf-8').read()
                    if (len(cur_content) != 0) and (cur_content[-1] == '\n'):
                        cur_content = cur_content[:-1]
                    if cur_content != rv['content']:
                        status[os.path.relpath(full, self.root)] = 'M' # modified
                    else:
                        status[os.path.relpath(full, self.root)] = 'C' # clean
        return status

    def diff_rv_to_working(self, pagename, oldrvid=0, newrvid=0):
        # oldrvid=0 means latest fetched revision
        # newrvid=0 means working copy
        filename = pagename_to_filename(pagename) + '.wiki'
        filename = filename.decode('utf-8')
        pageid = self.get_pageid_from_pagename(pagename)
        if not pageid:
            raise ValueError('page named %s has not been fetched' % pagename)
        else:
            if oldrvid == 0:
                oldrvid = self.pages_get_rv_list(pageid)[-1]
            oldrv = self.pages_get_rv(pageid, oldrvid)
            oldname = 'a/%s (revision %i)' % (filename, oldrvid)
            old = [i + '\n' for i in \
                   oldrv['content'].encode('utf-8').split('\n')]
            if newrvid == 0:
                cur_content = codecs.open(filename, 'r', 'utf-8').read()
                cur_content = cur_content.encode('utf-8')
                if (len(cur_content) != 0) and (cur_content[-1] == '\n'):
                    cur_content = cur_content[:-1]
                newname = 'b/%s (working copy)' % filename
                new = [i + '\n' for i in cur_content.split('\n')]
            else:
                newrv = self.pages_get_rv(pageid, newrvid)
                newname = 'b/%s (revision %i)' % (filename, newrvid)
                new = [i + '\n' for i in newrv['content'].split('\n')]
            diff_fd = StringIO()
            bzrlib.diff.internal_diff(oldname, old, newname, new, diff_fd)
            diff = diff_fd.getvalue()
            if diff[-1] == '\n':
                diff = diff[:-1]
            return diff


def pagename_to_filename(name):
    name = name.replace(' ', '_')
    name = name.replace('/', '!')
    return name


def filename_to_pagename(name):
    name = name.replace('!', '/')
    name = name.replace('_', ' ')
    return name
