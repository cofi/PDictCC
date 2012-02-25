#!/usr/bin/env python
# -*- coding: utf-8 -*-
import anydbm
import os.path
import re

__version__ = ('0', '1')


class DB(object):
    databases = [('a', 'A => B'), ('b', 'B => A')]
    DICT_DIR = os.path.expanduser('~/.rdictcc')
    FILE_SCHEME = 'dict_{0}.dir'
    LANG_DIR_KEY = '__dictcc_lang_dir'
    def __init__(self, lang):
        self.path = os.path.join(DB.DICT_DIR, DB.FILE_SCHEME.format(lang))
        self.db = None

    def __enter__(self):
        if not os.path.exists(self.path):
            print('Path "{0}" does not exist, will create it.'.format(self.path))
        self.db = anydbm.open(self.path, 'c')
        return self

    def __exit__(self, type, value, traceback):
        self.db.close()
        self.db = None

    def __iter__(self):
        if self.db is None:
            raise StopIteration()
        key = self.db.firstkey()
        while key is not None:
            yield key, self.db[key]
            key = self.db.nextkey(key)

    def get(self, key, default=False):
        try:
            return self.db[key]
        except KeyError:
            if default is False:
                raise
            else:
                return default

    def size(self):
        if self.db is not None:
            return sum(1 for _ in self)
        else:
            with self:
                return sum(1 for _ in self)

    def header(self):
        if self.db is not None:
            return self.get(DB.LANG_DIR_KEY, None)
        else:
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
            result.append(format_entry(qfun(query.lower(), db)))
    return '\n'.join(result)

def format_entry(entry, compact=False):
    return ' \n'.join(entry)

def query_simple(query, db):
    return [db.get(query, '')]

def query_regexp(query, db):
    rx = re.compile(query)
    return [v for k, v in db if rx.match(k)]

def query_fulltext(query, db):
    pass

def interactive_mode():
    try:
        while True:
            query = raw_input('=> ').strip()
            print(execute_query(query))

    except EOFError:
        pass

if __name__ == '__main__':
    import sys
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
    db.add_argument('-i', '--import', metavar='DICTCC_FILE',
                    help='Import the dict file from dict.cc')

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

    if args.size:
        for lang, lang_desc in DB.databases:
            with DB(lang) as db:
                print('{0}: {1} entries'.format(db.header() or lang_desc,
                                                db.size()))

    elif args.query:
        for q in args.query:
            execute_query(q, args.compact)

    else:
        interactive_mode()
