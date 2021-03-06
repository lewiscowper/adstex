"""
Find all citation keys in your LaTeX documents and search NASA ADS 
to generate corresponding bibtex entries. 

Project website: https://github.com/yymao/adstex

The MIT License (MIT)
Copyright (c) 2015 Yao-Yuan Mao (yymao)
http://opensource.org/licenses/MIT
"""

import os
import re
from argparse import ArgumentParser
from datetime import date
from urllib import unquote
from collections import defaultdict
import ads
import bibtexparser

_this_year = date.today().year % 100
_this_cent = date.today().year / 100

_re_cite = re.compile(r'\\cite(?:[pt]|author|year|alt)?\*?(?:\[.*\])?{([\w\s/&.:,-]+)}')
_re_fayear = re.compile(r'([A-Za-z_-]+):?((?:\d{2})?\d{2})')
_re_id = {}
_re_id['doi'] = re.compile(r'10\.\d{4,}(?:\.\d+)*\/(?:(?![\'"&<>])\S)+')
_re_id['bibcode'] = re.compile(r'\d{4}\D\S{13}[A-Z.:]$')
_re_id['arxiv'] = re.compile(r'(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Za-z-]+)?\/\d{7})')

_name_prefix = ('van', 'de', 'den', 'der', 'van de', 'van den', 'van der', 'von der')
_name_prefix = sorted(_name_prefix, key=len, reverse=True)


def _match_name_prefix(name):
    for prefix in _name_prefix:
        p = prefix.replace(' ', '')
        if name.lower().startswith(p):
            return ' '.join((prefix, name[len(p):]))


def _y2toy4(y2):
    y2 = int(y2)
    k = int(y2 > _this_year)
    return str((_this_cent - k) * 100 + y2)


def _is_like_string(s):
    try:
        s + ''
    except TypeError:
        return False
    return True


def _headerize(msg):
    return '\n{0}\n{1}\n{0}'.format('-'*60, msg)


def search_keys(files):
    if _is_like_string(files):
        files = [files]
    keys = set()
    for f in files:
        with open(f) as fp:
           text = fp.read()
        for m in _re_cite.finditer(text):
            for k in m.groups()[0].split(','):
                keys.add(k.strip())
    return keys


def format_author(authors, max_char):
    s = authors[0]
    for author in authors[1:]:
        if len(s) + len(author) + 2 < max_char-7:
            s = u'{}; {}'.format(s, author)
        else:
            break
    else:
        return s
    return s + u' et al.'


def format_ads_entry(i, entry, max_char=78):
    title = entry.title[0][:max_char-4] if entry.title else '<no title>'
    return u'[{}] {} (cited {} times)\n    {}\n    {}\n'.format(i+1, entry.bibcode, 
            entry.citation_count, format_author(entry.author, max_char-4), 
            title)


def id2bibcode(id):
    for id_type in ('bibcode', 'arxiv', 'doi'):
        m = _re_id[id_type].match(id)
        if m:
            s = ads.SearchQuery(q=':'.join((id_type, m.group())), fl=['bibcode'])
            try:
                return s.next().bibcode
            except StopIteration:
                return


def authoryear2bibcode(author, year, key):
    q = 'author:"^{}" year:{} database:("astronomy" OR "physics")'.format(author, year)
    entries = list(ads.SearchQuery(q=q, fl=['id', 'author', 'bibcode', 'title', 'citation_count'], 
            sort='citation_count desc', rows=20, max_pages=0))
    if entries:
        print _headerize('Choose an entry for {}'.format(key))
        print u'\n'.join(format_ads_entry(*a) for a in enumerate(entries))
        choices = range(0, len(entries)+1)
        c = -1
        while c not in choices:
            c = raw_input('Choice (if no one matches, enter 0 to skip or enter an identifier): ')
            bibcode = id2bibcode(c)
            if bibcode:
                return bibcode
            try:
                c = int(c)
            except (TypeError, ValueError):
                pass
        if not c:
            return
        return entries[c-1].bibcode
    elif ' ' not in author:
        new_author = _match_name_prefix(author)
        if new_author:
            return authoryear2bibcode(new_author, year, key)


def find_bibcode(key):
    bibcode = id2bibcode(key)
    if bibcode:
        return bibcode

    m = _re_fayear.match(key)
    if m:
        fa, y = m.groups()
        if len(y) == 2:
            y = _y2toy4(y)
        bibcode = authoryear2bibcode(fa, y, key)
        if bibcode:
            return bibcode

    print _headerize('Enter an identifier (bibcode, arxiv, doi) for {}'.format(key))
    c = True
    while c:
        c = raw_input('Identifier (or press ENTER to skip): ')
        bibcode = id2bibcode(c)
        if bibcode:
            return bibcode


def extract_bibcode(entry):
    return unquote(entry.get('adsurl', '').rpartition('/')[-1])


def entry2bibcode(entry):
    if 'adsurl' in entry:
        s = ads.SearchQuery(bibcode=extract_bibcode(entry), fl=['bibcode'])
        try:
            return s.next().bibcode
        except StopIteration:
            pass

    if 'doi' in entry:
        s = ads.SearchQuery(doi=entry['doi'], fl=['bibcode'])
        try:
            return s.next().bibcode
        except StopIteration:
            pass

    if 'eprint' in entry:
        s = ads.SearchQuery(arxiv=entry['eprint'], fl=['bibcode'])
        try:
            return s.next().bibcode
        except StopIteration:
            pass


def update_bib(b1, b2):
    b1._entries_dict.clear()
    b2._entries_dict.clear()
    b1.entries_dict.update(b2.entries_dict)
    b1.entries = b1.entries_dict.values()
    return b1


def main():
    parser = ArgumentParser()
    parser.add_argument('files', metavar='TEX', nargs='+', help='tex files to search citation keys')
    parser.add_argument('-o', '--output', metavar='BIB', required=True, help='output bibtex file')
    parser.add_argument('--no-update', dest='update', action='store_false')
    args = parser.parse_args()

    keys = search_keys(args.files)
    
    if os.path.isfile(args.output):
        with open(args.output) as fp:
            bib = bibtexparser.load(fp)
    else:
        bib = bibtexparser.loads('')

    not_found = list()
    to_retrieve = defaultdict(list)
    try:
        for key in keys:
            if key in bib.entries_dict:
                if args.update:
                    bibcode = extract_bibcode(bib.entries_dict[key])
                    bibcode_new = entry2bibcode(bib.entries_dict[key])
                    if bibcode_new and bibcode_new != bibcode:
                        to_retrieve[bibcode_new].append(key)
                        print '{}: UPDATE => {}'.format(key, bibcode_new)
                        continue
                print '{}: EXISTING'.format(key)
                continue
            bibcode = find_bibcode(key)
            if bibcode:
                to_retrieve[bibcode].append(key)
                print '{}: NEW ENTRY => {}'.format(key, bibcode)
            else:
                not_found.append(key)
                print '{}: NOT FOUND'.format(key)
    except KeyboardInterrupt:
        print

    if not_found:
        print _headerize('Please check the following keys')
        for key in not_found:
            print key

    if to_retrieve:
        repeated_keys = [t for t in to_retrieve.iteritems() if len(t[1]) > 1]
        if repeated_keys:
            print _headerize('The following keys refer to the same entry')
            for b, k in repeated_keys:
                print '{} refers to {}.\n  Keep only {}\n'.format(', '.join(k), b, k[0])

        print _headerize('Building new bibtex file, please wait...')
        bib_new = bibtexparser.loads(ads.ExportQuery(to_retrieve.keys(), 'bibtex').execute())
        for entry in bib_new.entries:
            entry['ID'] = to_retrieve[entry['ID']][0]
        bib = update_bib(bib, bib_new)
        with open(args.output, 'w') as fp:
            bibtexparser.dump(bib, fp)

    print _headerize('Done!')


if __name__ == "__main__":
    main()
