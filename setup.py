#!/usr/bin/env python

from distutils.core import setup

setup(name='mw',
      version='0.1',
      description='VCS-like nonsense for MediaWiki websites',
      author='Ian Weller',
      author_email='ian@ianweller.org',
      url='https://github.com/ianweller/mw',
      package_dir = {'': 'src'},
      packages=['mw'],
      scripts=['bin/mw'])

