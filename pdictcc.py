#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2012 by Michael Markert
#
# Author: Michael Markert <markert.michael@googlemail.com>
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 3, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program ; see the file COPYING.  If not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.

from __future__ import print_function, unicode_literals

import anydbm
import codecs
import os
import re
import sys
from itertools import chain
from textwrap import dedent
from collections import defaultdict


__version__ = ('0', '2')

class DBException(Exception):
    pass

class DB(object):
    databases = [('a', 'A => B'), ('b', 'B => A')]
    DICT_DIR = os.path.expanduser('~/.rdictcc')
    FILE_SCHEME = 'dict_{0}.dir'
    LANG_DIR_KEY = '__dictcc_lang_dir'
    def __init__(self, lang, importing=False):
        self.path = os.path.join(DB.DICT_DIR, DB.FILE_SCHEME.format(lang))
        self._open_flags = 'n' if importing else 'c'
        if not os.path.exists(DB.DICT_DIR):
            if not importing:
                raise DBException(dedent(
                    """\
                    There's no "{0}" directory!
                    You have to import an dict.cc database file first.
                    See --help for information.
                    """.format(DB.DICT_DIR)))
            else:
                os.mkdir(DB.DICT_DIR)
        else:
            if os.path.exists(self.path) and importing:
                print('Will overwrite "{0}"'.format(self.path))

        self.db = None
        self._accessors = 0

    def __enter__(self):
        if not os.path.exists(self.path):
            print('Path "{0}" does not exist, will create it.'.format(self.path))
        if self._accessors == 0:
            self.db = anydbm.open(self.path, self._open_flags)
        self._accessors += 1
        return self

    def __exit__(self, type, value, traceback):
        self._accessors -= 1
        if self._accessors == 0:
            self.db.close()
            self.db = None

    def __iter__(self):
        if self.db is None:
            raise StopIteration()
        key = self.db.firstkey()
        while key is not None:
            yield key, self.db[key]
            key = self.db.nextkey(key)

    def __setitem__(self, key, value):
        self.db[key.encode('utf-8')] = value.encode('utf-8')

    def get(self, key, default=False):
        try:
            return self.db[key].decode('utf-8')
        except KeyError:
            if default is False:
                raise
            else:
                return default

    def size(self):
        with self:
            return sum(1 for _ in self)

    def header(self):
        with self:
            return self.get(DB.LANG_DIR_KEY, None)

def execute_query(query, compact=False):
    qfun = {':r:' : query_regexp,
            ':f:' : query_fulltext}.get(query[:3], query_simple)
    query = query.lower() if query[:3] not in [':r:', ':f:'] else query[3:].lower()
    header_fmt = 15 * '=' + ' [ {0} ] ' + 15 * '='
    result = []
    for lang, dir_default in DB.databases:
        with DB(lang) as db:
            result.append(header_fmt.format(db.header() or dir_default))
            result.append(format_entry(qfun(query, db), compact))
    return '\n'.join(result)

def format_entry(entry, compact=False):
    if compact:
        fmt = '- {0}: {1}'
        joint = ' / '
    else:
        fmt ='{0}:\n    - {1}'
        joint = '\n    - '
    parts = list(chain.from_iterable(e.strip().split('#<>#') for e in entry))
    res = []
    for p in parts:
        if not p:
            continue
        e = p.split('=<>')
        head, tails = e[0], (t.split(':<>:') for t in e[1:])
        res.append(fmt.format(head, joint.join(chain.from_iterable(tails))))

    return '\n'.join(res)

def query_simple(query, db):
    return [db.get(query, '')]

def query_regexp(query, db):
    rx = re.compile(query)
    return [v for k, v in db if rx.match(k)]

def query_fulltext(query, db):
    rx = re.compile(query, re.IGNORECASE)
    return [v for k, v in db if rx.search(k)]

def interactive_mode():
    try:
        while True:
            query = raw_input('=> ').strip()
            print(execute_query(query))

    except EOFError:
        pass

class Entry(object):
    def __init__(self):
        self.dictionary = defaultdict(list)

    def add(self, phrase, translation):
        self.dictionary[phrase.strip()].append(translation.strip())

    def format(self):
        parts = []
        for phrase, translations in self.dictionary.iteritems():
            parts.append('{0}=<>{1}'.format(phrase, ':<>:'.join(translations)))
        return "#<>#".join(parts)

def import_dictionary(path):
    a = defaultdict(Entry)
    b = defaultdict(Entry)
    with codecs.open(path, encoding='utf-8') as f:
        head = re.match('# ([A-Z]{2})-([A-Z]{2}) vocabulary database', next(f))
        if not head:
            raise ValueError('"{0}" is not a dict.cc database'.format(path))
        a[DB.LANG_DIR_KEY] = ' => '.join(head.groups())
        b[DB.LANG_DIR_KEY] = ' => '.join(reversed(head.groups()))

        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            phrase, translation, word_type = line.split('\t')
            for d in [a, b]:
                key = extract_key(phrase)
                if key:
                    d[key].add(phrase, translation)
                phrase, translation = translation.split('\t')[0], phrase

        for d, db_name in [(a, 'a'), (b, 'b')]:
            with DB(db_name, True) as db:
                for key, value in d.iteritems():
                    if key == DB.LANG_DIR_KEY:
                        db[key] = value
                    else:
                        db[key] = value.format()
        return len(a), len(b)

def extract_key(phrase):
    key = re.sub(r'(\([^(]*\)|\{[^{]*\}|\[[^\[]*\])', '', phrase.lower())
    if key:
        keys = [key.strip() for key in re.sub(r'[.,<>]', ' ', key).strip().split()]
        if keys:
            longest_key = sorted(keys, key=len)[-1]
            return longest_key
    return ''

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(add_help=False,
                                     usage='\n       '
                                           .join('%(prog)s [-d] {0}'
                                                 .format(opts)
                                                 for opts in
                                                 ['[-i DICTCC_FILE]',
                                                  '[-v] [-S] [-h]',
                                                  '[-c] [-s | -r | -f] QUERY']))

    db = parser.add_argument_group('Database building options')
    db.add_argument('-i', '--import', metavar='DICTCC_FILE', dest='imp',
                    help='Import dict files from dict.cc')

    formatting = parser.add_argument_group('Format options')
    formatting.add_argument('-c', '--compact', action='store_true',
                            help='Use compact output format')

    misc = parser.add_argument_group('Misc options')
    misc.add_argument('-v', '--version', action='version', help='Show version',
                      version='%(prog)s {0}'.format('.'.join(__version__)))
    misc.add_argument('-S', '--size', action='store_true',
                      help='Show the number of entries in the databases')
    misc.add_argument('-d', '--directory', metavar='PATH',
                      help='Use PATH instead of ~/.rdictcc')
    misc.add_argument('-h', '--help', action='help',
                      help='Show this help message and exit')

    query = parser.add_argument_group('Query options')
    query_mutex = query.add_mutually_exclusive_group()
    query_mutex.add_argument('-s', '--simple', action='store_true',
                       help='Translate the word given as QUERY (default)')
    query_mutex.add_argument('-r', '--regexp', action='store_true',
                       help='Translate all the words mathing the regexp QUERY')
    query_mutex.add_argument('-f', '--fulltext', action='store_true',
                       help='Translate all sentences matching the regexp QUERY')
    parser.add_argument('query', metavar='QUERY', nargs='*',
                        help='the query to search')

    args = parser.parse_args()

    if args.directory:
        DB.DICT_DIR = os.path.expanduser(args.directory)
    try:
        if args.size:
            for lang, lang_desc in DB.databases:
                with DB(lang) as db:
                    print('{0}: {1} entries'.format(db.header() or lang_desc,
                                                    db.size()))
        elif args.imp:
            path = args.imp
            print('Importing from "{0}"'.format(path))
            counts = import_dictionary(path)
            print('Imported {0} (A => B) and {1} (B => A) entries'.format(*counts))

        elif args.query:
            for q in args.query:
                if args.regexp:
                    q = ':r:' + q
                elif args.fulltext:
                    q = ':f:' + q
                print(execute_query(q, args.compact))

        else:
            interactive_mode()

    except Exception as e:
        print(e)
        sys.exit(1)
