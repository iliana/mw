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
import subprocess
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
        CommandBase.__init__(self, 'pull_commandat', 'add remote pages to repo '
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
            pull_command = PullCommand()
            pull_command.args = [pagename.encode('utf-8')]
            pull_command._do_command()


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

        for these_pages in [pages[i:i + 25] for i in range(0, len(pages), 25)]: # XXX ?
            data = {
                    'action': 'query',
                    'titles': '|'.join(these_pages),
                    'prop': 'info|revisions',
                    'rvprop': 'ids|flags|timestamp|user|comment|content',
            }
            response = self.api.call(data)['query']['pages']
            # for every pageid, returns dict.keys() = {'lastrevid', 'pageid', 'title', 'counter', 'length', 'touched': u'2011-02-02T19:32:04Z', 'ns', 'revisions' {...}}
            for pageid in response.keys():
                pagename = response[pageid]['title']
                
                # If no revisions, then error, perhaps page deleted
                if 'revisions' not in response[pageid]:
                    print 'skipping:       "%s" -- cannot find page, perhaps deleted' % (pagename)
                    continue
                
                # Is the revisions list a sorted one, should I use [0] or [-1]? -- reagle
                if 'comment' in response[pageid]['revisions'][0]:
                    last_wiki_rev_comment = response[pageid]['revisions'][0]['comment']
                else:
                    last_wiki_rev_comment = ''
                last_wiki_rev_user = response[pageid]['revisions'][0]['user']
                
                # check if working file is modified or if wiki page doesn't exists
                status = self.metadir.working_dir_status()
                filename = mw.metadir.pagename_to_filename(pagename)
                full_filename = os.path.join(self.metadir.root, filename + '.wiki')
                if filename + '.wiki' in status and \
                    status[filename + '.wiki' ] in ['M']:
                    print 'skipping:       "%s" -- uncommitted modifications ' % (pagename)
                    continue
                if 'missing' in response[pageid].keys():
                    print 'error:          "%s": -- page does not exist, file not created' % \
                            (self.me, pagename)
                    continue

                wiki_revids = sorted([x['revid'] for x in response[pageid]['revisions']])
                last_wiki_revid = wiki_revids[-1]
                working_revids = sorted(self.metadir.pages_get_rv_list({'id' : pageid}))
                last_working_revid = working_revids[-1]
                if ( os.path.exists(full_filename) and 
                        last_wiki_revid == last_working_revid):
                    print 'wiki unchanged: "%s"' % (pagename)
                else:
                    print 'pulling:        "%s" : "%s" by "%s"' % (
                        pagename, last_wiki_rev_comment, last_wiki_rev_user)
                    self.metadir.pagedict_add(pagename, pageid, last_wiki_revid)
                    self.metadir.pages_add_rv(int(pageid),
                                              response[pageid]['revisions'][0])
                    with file(full_filename, 'w') as fd:
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


class MergeCommand(CommandBase):
    def __init__(self):
        usage = '[FILES]'
        CommandBase.__init__(self, 'merge', 'merge local and wiki copies', usage)

    def _do_command(self):
        self._die_if_no_init()
        self.merge_tool = self.metadir.config.get('merge', 'tool')
        status = self.metadir.working_dir_status()
        for filename in status:
            if status[filename] == 'M':
                full_filename = os.path.join(self.metadir.root, filename)
                pagename = mw.metadir.filename_to_pagename(filename[:-5])
                # mv local to filename.wiki.local
                os.rename(full_filename, full_filename + '.local')
                # pull wiki copy
                pull_command = PullCommand()
                pull_command.args = [pagename.encode('utf-8')]
                pull_command._do_command()
                # mv remote to filename.wiki.remote
                os.rename(full_filename, full_filename + '.remote')
                # Open merge tool
                merge_command = self.merge_tool % (full_filename + '.local', 
                    full_filename + '.remote', full_filename + '.merge')
                subprocess.call(merge_command.split(' '))
                # mv filename.merge filename and delete tmp files
                os.rename(full_filename + '.merge', full_filename)
                os.remove(full_filename + '.local')
                os.remove(full_filename + '.remote')
                # mw ci pagename
                commit_command = CommitCommand()
                commit_command.args = [pagename.encode('utf-8')]
                commit_command._do_command()


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
        files_to_commit = 0 # how many files to process
        status = self.metadir.working_dir_status(files=self.args)
        for filename in status:
            print '%s %s' % (status[filename], filename)
            if status[filename] in ['M']:
                files_to_commit += 1
        if not files_to_commit:
            print 'nothing to commit'
            sys.exit()
        if self.options.edit_summary == None:
            print 'Edit summary:',
            edit_summary = raw_input()
        else:
            edit_summary = self.options.edit_summary
        for filename in status:
            if status[filename] in ['M']:
                files_to_commit -= 1
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
                    print 'warning: edit conflict detected on "%s" (%s -> %s) ' \
                            '-- skipping! (try merge)' % (filename, awaitedrevid, revid)
                    continue
                edittoken = pages[pageid]['edittoken']
                full_filename = os.path.join(self.metadir.root, filename)
                text = codecs.open(full_filename, 'r', 'utf-8').read()
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
                if 'error' in response:
                    if 'code' in response['error']:
                        if response['error']['code'] == 'permissiondenied':
                            print 'Permission denied -- try running "mw login"'
                            return
                if response['edit']['result'] == 'Success':
                    if 'nochange' in response['edit']:
                        print 'warning: no changes detected in %s - ' \
                                'skipping and removing ending LF' % filename
                        pagename = mw.metadir.filename_to_pagename(filename[:-5])
                        self.metadir.clean_page(pagename)
                        continue
                    if response['edit']['oldrevid'] != revid:
                        print 'warning: edit conflict detected on %s (%s -> %s) ' \
                                '-- skipping!' % (file, 
                                response['edit']['oldrevid'], revid)
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
                    # need to write latest rev to file too, as text may be changed
                    #such as a sig, e.g., -~ =>  -[[User:Reagle|Reagle]]
                    with file(full_filename, 'w') as fd:
                        data = response[pageid]['revisions'][0]['*']
                        data = data.encode('utf-8')
                        fd.write(data)
                    if files_to_commit :
                        print 'waiting 3s before processing the next file'
                        time.sleep(3)
                else:
                    print 'error: committing %s failed: %s' % \
                            (filename, response['edit']['result'])
