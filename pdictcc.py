#!/usr/bin/env python
# -*- coding: utf-8 -*-

__version__ = ('0', '1')

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
