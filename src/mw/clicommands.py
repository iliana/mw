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

import codecs
import cookielib
import getpass
import hashlib
import mw.metadir
from optparse import OptionParser, OptionGroup
import os
import simplemediawiki
import sys
import time


class CommandBase(object):

    def __init__(self, name, description, usage=None):
        self.me = os.path.basename(sys.argv[0])
        self.description = description
        if usage is None:
            usage = '%prog ' + name
        else:
            usage = '%%prog %s %s' % (name, usage)
        self.parser = OptionParser(usage=usage, description=description)
        self.name = name
        self.metadir = mw.metadir.Metadir()
        self.shortcuts = []

    def main(self):
        (self.options, self.args) = self.parser.parse_args()
        self.args = self.args[1:]  # don't need the first thing
        self._do_command()

    def _do_command(self):
        pass

    def _login(self):
        user = raw_input('Username: ')
        passwd = getpass.getpass()
        result = self.api.call({'action': 'login',
                                'lgname': user,
                                'lgpassword': passwd})
        if result['login']['result'] == 'Success':
            # cookies are saved to a file
            print 'Login successful! (yay)'
        elif result['login']['result'] == 'NeedToken':
            print 'Login with token'
            result = self.api.call({'action': 'login',
                                    'lgname': user,
                                    'lgpassword': passwd,
                                    'lgtoken': result['login']['token']})
            if result['login']['result'] == 'Success':
                print 'Login successful! (yay)'
            else:
                print 'Login failed: %s' % result['login']['result']
        else:
            print 'Login failed: %s' % result['login']['result']

    def _die_if_no_init(self):
        if self.metadir.config is None:
            print '%s: not a mw repo' % self.me
            sys.exit(1)

    def _api_setup(self):
        cookie_filename = os.path.join(self.metadir.location, 'cookies')
        self.api_url = self.metadir.config.get('remote', 'api_url')
        self.api = simplemediawiki.MediaWiki(self.api_url,
                                             cookie_file=cookie_filename)


class InitCommand(CommandBase):

    def __init__(self):
        usage = 'API_URL'
        CommandBase.__init__(self, 'init', 'start a mw repo', usage)

    def _do_command(self):
        if len(self.args) < 1:
            self.parser.error('must have URL to remote api.php')
        elif len(self.args) > 1:
            self.parser.error('too many arguments')
        self.metadir.create(self.args[0])


class LoginCommand(CommandBase):

    def __init__(self):
        CommandBase.__init__(self, 'login', 'authenticate with wiki')

    def _do_command(self):
        self._die_if_no_init()
        self._api_setup()
        self._login()


class LogoutCommand(CommandBase):

    def __init__(self):
        CommandBase.__init__(self, 'logout', 'forget authentication')

    def _do_command(self):
        self._die_if_no_init()
        try:
            os.unlink(os.path.join(self.metadir.location, 'cookies'))
        except OSError:
            pass


class PullCategoryMembersCommand(CommandBase):

    def __init__(self):
        usage = '[options] PAGENAME ...'
        CommandBase.__init__(self, 'pullcat', 'add remote pages to repo '
                             'belonging to the given category', usage)

    def _do_command(self):
        self._die_if_no_init()
        self._api_setup()
        pages = []
        pages += self.args
        for these_pages in [pages[i:i + 25] for i in range(0, len(pages), 25)]:
            data = {
                'action': 'query',
                'gcmtitle': '|'.join(these_pages),
                'generator': 'categorymembers',
                'gcmlimit': 500
            }
        response = self.api.call(data)['query']['pages']
        for pageid in response.keys():
            pagename = response[pageid]['title']
            print pagename
            pullc = PullCommand()
            pullc.args = [pagename.encode('utf-8')]
            pullc._do_command()


class PullCommand(CommandBase):
    
    def __init__(self):
        usage = '[options] PAGENAME ...'
        CommandBase.__init__(self, 'pull', 'add remote pages to repo', usage)

    def _do_command(self):
        self._die_if_no_init()
        self._api_setup()
        pages = []
        pages += self.args

        # Pull should work with pagename, filename, or working directory
        converted_pages = []
        if pages == []:
            pages = self.metadir.working_dir_status().keys()
        for pagename in pages:
            if '.wiki' in pagename:
                converted_pages.append(
                    mw.metadir.filename_to_pagename(pagename[:-5]))
            else:
                converted_pages.append(pagename)
        pages = converted_pages

        for these_pages in [pages[i:i + 25] for i in range(0, len(pages), 25)]: # ?
            data = {
                    'action': 'query',
                    'titles': '|'.join(these_pages),
                    'prop': 'info|revisions',
                    'rvprop': 'ids|flags|timestamp|user|comment|content',
            }
            response = self.api.call(data)['query']['pages']
            for pageid in response.keys():
                pagename = response[pageid]['title']
                # if pagename exists as file and its status is 'M' warn not pulled
                status = self.metadir.working_dir_status()
                filename = mw.metadir.pagename_to_filename(pagename)
                if filename + '.wiki' in status and \
                    status[filename + '.wiki' ] in ['M']:
                    print('%s: "%s" has uncommitted modifications ' 
                        '-- skipping!' % (self.me, pagename))
                    continue
                if 'missing' in response[pageid].keys():
                    print '%s: %s: page does not exist, file not created' % \
                            (self.me, pagename)
                    continue
                revids = [x['revid'] for x in response[pageid]['revisions']]
                revids.sort()
                self.metadir.pagedict_add(pagename, pageid, revids[-1])
                self.metadir.pages_add_rv(int(pageid),
                                          response[pageid]['revisions'][0])
                with file(os.path.join(self.metadir.root, filename + '.wiki'),
                          'w') as fd:
                    data = response[pageid]['revisions'][0]['*']
                    data = data.encode('utf-8')
                    fd.write(data)


class StatusCommand(CommandBase):

    def __init__(self):
        CommandBase.__init__(self, 'status', 'check repo status')
        self.shortcuts.append('st')

    def _do_command(self):
        self._die_if_no_init()
        status = self.metadir.working_dir_status()
        for filename in status:
            print '%s %s' % (status[filename], filename)


class DiffCommand(CommandBase):

    def __init__(self):
        CommandBase.__init__(self, 'diff', 'diff wiki to working directory')

    def _do_command(self):
        self._die_if_no_init()
        status = self.metadir.working_dir_status()
        for filename in status:
            if status[filename] == 'M':
                print self.metadir.diff_rv_to_working(
                        mw.metadir.filename_to_pagename(filename[:-5])),


class CommitCommand(CommandBase):

    def __init__(self):
        usage = '[FILES]'
        CommandBase.__init__(self, 'commit', 'commit changes to wiki', usage)
        self.shortcuts.append('ci')
        self.parser.add_option('-m', '--message', dest='edit_summary',
                               help='don\'t prompt for edit summary and '
                               'use this instead')
        self.parser.add_option('-b', '--bot', dest='bot', action='store_true',
                               help='mark actions as a bot (won\'t affect '
                               'anything if you don\'t have the bot right',
                               default=False)

    def _do_command(self):
        self._die_if_no_init()
        self._api_setup()
        status = self.metadir.working_dir_status(files=self.args)
        nothing_to_commit = True
        for filename in status:
            print '%s %s' % (status[filename], filename)
            if status[filename] in ['M']:
                nothing_to_commit = False
        if nothing_to_commit:
            print 'nothing to commit'
            sys.exit()
        if self.options.edit_summary == None:
            print 'Edit summary:',
            edit_summary = raw_input()
        else:
            edit_summary = self.options.edit_summary
        for file_num, filename in enumerate(status):
            if status[filename] in ['M']:
                # get edit token
                data = {
                        'action': 'query',
                        'prop': 'info|revisions',
                        'intoken': 'edit',
                        'titles': mw.metadir.filename_to_pagename(filename[:-5]),
                }
                response = self.api.call(data)
                pages = response['query']['pages']
                pageid = pages.keys()[0]
                revid = pages[pageid]['revisions'][0]['revid']
                awaitedrevid = \
                        self.metadir.pages_get_rv_list({'id': pageid})[0]
                if revid != awaitedrevid:
                    print 'warning: edit conflict detected on %s (%s -> %s) ' \
                            '-- skipping!' % (file, awaitedrevid, revid)
                    continue
                edittoken = pages[pageid]['edittoken']
                filename = os.path.join(self.metadir.root, filename)
                text = codecs.open(filename, 'r', 'utf-8').read()
                text = text.encode('utf-8')
                if (len(text) != 0) and (text[-1] == '\n'):
                    text = text[:-1]
                md5 = hashlib.md5()
                md5.update(text)
                textmd5 = md5.hexdigest()
                data = {
                        'action': 'edit',
                        'title': mw.metadir.filename_to_pagename(filename[:-5]),
                        'token': edittoken,
                        'text': text,
                        'md5': textmd5,
                        'summary': edit_summary,
                }
                if self.options.bot:
                    data['bot'] = 'bot'
                response = self.api.call(data)
                if response['edit']['result'] == 'Success':
                    if 'nochange' in response['edit']:
                        print 'warning: no changes detected in %s - ' \
                                'skipping and removing ending LF' % filename
                        self.metadir.clean_page(filename[:-5])
                        continue
                    if response['edit']['oldrevid'] != revid:
                        print 'warning: edit conflict detected on %s -- ' \
                                'skipping!' % filename
                        continue
                    data = {
                            'action': 'query',
                            'revids': response['edit']['newrevid'],
                            'prop': 'info|revisions',
                            'rvprop':
                                    'ids|flags|timestamp|user|comment|content',
                    }
                    response = self.api.call(data)['query']['pages']
                    self.metadir.pages_add_rv(int(pageid),
                                              response[pageid]['revisions'][0])
                    if file_num != len(status) - 1:
                        print 'waiting 3s before processing the next file'
                        time.sleep(3)
                else:
                    print 'error: committing %s failed: %s' % \
                            (filename, response['edit']['result'])
