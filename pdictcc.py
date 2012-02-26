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

# PDictCC is a tool for offline dictionary lookup based on dict.cc databases
# that tries to be a compatible replacement of Tassilo Horn's RDictCC:
# http://www.tsdh.de/cgi-bin/wiki.pl/RDictCc
from __future__ import print_function, unicode_literals

import codecs
import gdbm
import os
import re
import sys
from collections import defaultdict
from itertools import chain
from textwrap import dedent


__version__ = ('0', '2')
ENCODING = 'utf-8'


# Data representation

class DBException(Exception):
    """Signal that a DB related exception happened."""
    pass


class DB(object):
    """
    Gdbm wrapper that tries to cover the deficiencies of gdbm database
    objects.

    DB is a context manager that opens its database on entry and closes it on
    exit.

    DB is an iterator that returns key value pairs if it is iterated on (DB
    needs to be opened).
    """
    databases = [('a', 'A => B'), ('b', 'B => A')]
    DICT_DIR = os.path.expanduser('~/.pdictcc')
    FILE_SCHEME = 'dict_{0}.dbm'
    LANG_DIR_KEY = '__dictcc_lang_dir'

    def __init__(self, lang, importing=False):
        """
        :param lang: language identifier, db file path is constructed with it
        :type lang: unicode
        :param importing: flag that indicates if DB is used for importing
        :type importing: bool
        """
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
            self.db = gdbm.open(self.path, self._open_flags)
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
            yield key.decode(ENCODING), self.db[key].decode(ENCODING)
            key = self.db.nextkey(key)

    def __setitem__(self, key, value):
        self.db[key.encode(ENCODING)] = value.encode(ENCODING)

    def __getitem__(self, key):
        return self.get(key)

    def get(self, key, default=False):
        """
        Return the value stored in key. If key is not found return ``default``.

        :raises: :exc:`KeyError` if key is not found and ``default`` is ``False``.

        :param key: the key to lookup
        :type key: unicode
        :param default: the value to return if lookup failed
        :type default: unicode
        """
        try:
            return self.db[key.encode(ENCODING)].decode(ENCODING)
        except KeyError:
            if default is False:
                raise
            else:
                return default

    def size(self):
        """
        Return the number of entries in the db.
        """
        with self:
            return sum(1 for _ in self)

    def header(self):
        """
        Return the language header stored in the DB or ``None`` if there is none.
        """
        with self:
            return self.get(DB.LANG_DIR_KEY, None)


class Entry(object):
    """
    An entry is the collaction of all phrases and corresponding translations
    that share a key.
    """
    def __init__(self):
        self.dictionary = defaultdict(list)

    @staticmethod
    def from_serialized(serialized):
        entry = Entry()
        if not serialized:
            return entry
        phrase_groups = serialized.split('#<>#')
        for pg in phrase_groups:
            phrase, translations = pg.split('=<>')
            entry.dictionary[phrase] = translations.split(':<>:')

        return entry

    def add(self, phrase, translation):
        """
        Add phrase and its translation to this entry.
        """
        self.dictionary[phrase.strip()].append(translation.strip())

    def format(self, compact=False):
        """
        Return the entry formatted for output.

        :param compact: flag to format results compact
        :type compact: bool
        """
        if compact:
            fmt = '- {0}: {1}'
            sep = ' / '
        else:
            fmt = '{0}:\n    - {1}'
            sep = '\n    - '

        return '\n'.join(fmt.format(phrase, sep.join(translations))
                         for phrase, translations in self.dictionary.iteritems())

    def serialize(self):
        """
        Return this entry formatted suitable for storage in database.

        Different phrases are separated by '#<>#' phrases from translations by
        '=<>' and translations from each other by ':<>:'.
        """
        parts = []
        for phrase, translations in self.dictionary.iteritems():
            parts.append('{0}=<>{1}'.format(phrase, ':<>:'.join(translations)))
        return "#<>#".join(parts)


# importing data

def import_dictionary(path):
    """
    Import dictionary from dict.cc TSV file and return the count of entries.

    :param path: file name of TSV to import
    :type path: str
    """
    a = defaultdict(Entry)
    b = defaultdict(Entry)
    with codecs.open(path, encoding=ENCODING) as f:
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
                        db[key] = value.serialize()
        return len(a), len(b)


def extract_key(phrase):
    """
    Extract word form phrasethat looks most important as key.

    Ignores everything that is enclosed in parenthesis and chooses the longest
    left over word.

    :param phrase: phrase to extract key from
    :type phrase: unicode
    """
    key = re.sub(r'(\([^(]*\)|\{[^{]*\}|\[[^\[]*\])', '', phrase.lower())
    if key:
        keys = [key.strip() for key in re.sub(r'[.,<>]', ' ', key).strip().split()]
        if keys:
            longest_key = sorted(keys, key=len, reverse=True)[0]
            return longest_key
    return ''


# querying

def execute_query(query, compact=False):
    """
    Execute a query and return the formatted results.

    A query may be prefixed by :r: or :f: which stands for evaluation as a
    regular expression and evaluation as a fulltext search which has both linear
    complexity (O(n); n = entries in DB.)

    :param query: the query
    :type query: unicode
    :param compact: flag to format results compact
    :type compact: bool
    """
    qfun = {':r:': query_regexp,
            ':f:': query_fulltext}.get(query[:3], query_simple)
    query = query.lower() if query[:3] not in [':r:', ':f:'] else query[3:].lower()
    header_fmt = 15 * '=' + ' [ {0} ] ' + 15 * '='
    result = []
    for lang, dir_default in DB.databases:
        with DB(lang) as db:
            result.append(header_fmt.format(db.header() or dir_default))
            query_result = [entry.format(compact) for entry in qfun(query, db)]
            # remove header if there are no results or only empty in this direction
            if query_result and not all(not q for q in query_result):
                result.extend(query_result)
            else:
                result.pop()
    return '\n'.join(result) if result else 'No results.'


def query_simple(query, db):
    """
    Query the database for exact matches of key with query.

    Runs in constant complexity (O(1)).

    :param query: key to lookup
    :type query: unicode
    :param db: the database object to query
    :type db: :class:`DB`
    """
    return [Entry.from_serialized(db.get(query, ''))]


def query_regexp(query, db):
    """
    Query the database for matches of key with query.

    Runs in linear complexity (O(n); n = number of entries).

    :param query: regular expression for key lookup
    :type query: unicode
    :param db: the database object to query
    :type db: :class:`DB`
    """
    rx = re.compile(query)
    return [Entry.from_serialized(v) for k, v in db if rx.match(k)]


def query_fulltext(query, db):
    """
    Query the database for matches of value with query.

    Runs in linear complexity (O(n); n = number of entries).

    :param query: regular expression for value lookup
    :type query: unicode
    :param db: the database object to query
    :type db: :class:`DB`
    """
    rx = re.compile(query, re.IGNORECASE)
    return [Entry.from_serialized(v) for k, v in db if rx.search(v)]


def interactive_mode():
    """
    Interactive mode for repeated queries against the database.

    See :func:`execute_query`.
    """
    print('Welcome to the interactive mode: You can type queries here.\n'
          'Prefix your query with `:r:` to issue a regular expression query and'
          'with `:f:` for a fulltext query.\n'
          'Enter C-d (Ctrl + d) to exit.')
    try:
        while True:
            query = raw_input('=> ').strip().decode(sys.stdin.encoding)
            print(execute_query(query))

    except EOFError:
        pass


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
                q = q.decode(sys.stdin.encoding)
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
