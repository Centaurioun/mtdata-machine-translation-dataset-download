#!/usr/bin/env python
#
# Author: Thamme Gowda [tg (at) isi (dot) edu] 
# Created: 4/8/20

from typing import Tuple, List, Optional, Set, Union
from dataclasses import dataclass, field
from mtdata.iso.bcp47 import BCP47Tag, bcp47

DID_DELIM = '-'  # I  wanted to use ":", but Windows, they dont like ":" in path! :(

LangPair = Tuple[BCP47Tag, BCP47Tag]


@dataclass(frozen=True)
class DatasetId:
    group: str
    name: str
    version: str
    langs: Union[Tuple[str, str], LangPair]  # one=monolingual, two=bitext; many=multi

    def __post_init__(self):
        assert self.group
        assert self.name
        assert self.version
        assert self.name.islower(), f'name {self.name} has to be lower cased for consistency'
        for name in [self.group, self.version, self.name]:
            for ch in '-/*|[](){}<>?&:;,!^$"\' ':
                assert ch not in name, f"Character '{ch}' is not permitted in name {name}"
        # ensure lang ID is BCP47 tag
        assert isinstance(self.langs, tuple), f'Expected tuple (l1, l2); given={self.langs}'
        langs = tuple(lang if isinstance(lang, BCP47Tag) else bcp47(lang) for lang in self.langs)
        if langs != self.langs:
            object.__setattr__(self, 'langs', langs)  # bypass frozen=True

    @property
    def lang_str(self):
        return DID_DELIM.join(str(lang) for lang in self.langs)

    def format(self, delim=DID_DELIM):
        return delim.join([self.group, self.name, self.version, self.lang_str])

    def __str__(self):
        return self.format()

    @classmethod
    def parse(cls, string, delim=DID_DELIM) -> 'DatasetId':
        expected_format = f"<group>{delim}<name>{delim}<version>{delim}<l1>{delim}<l2>"
        parts = string.strip().split(delim)
        if len(parts) != 5:
            raise Exception(f'Dataset ID expected in format: {expected_format}; but given {string}.'
                            f' If you are unsure, run "mtdata list | cut -f1 | grep -i <name>" and copy its id.')
        group, name, version, lang1, lang2 = parts
        return cls(group=group, name=name, version=version, langs=(lang1, lang2))


class Entry:
    __slots__ = ('did', 'url', 'filename', 'ext', 'in_paths', 'in_ext', 'cite', 'cols', 'is_archive')

    def __init__(self, did: DatasetId,
                 url: str,
                 filename: Optional[str] = None,
                 ext: Optional[str] = None,
                 in_paths: Optional[List[str]] = None,
                 in_ext: Optional[str] = None,
                 cite: Optional[str] = None,
                 cols: Optional[Tuple[int, int]] = None):

        assert isinstance(did, DatasetId)
        self.did = did
        self.url = url
        self.filename = filename
        orig_name = self.url.split('/')[-1]
        self.ext = ext
        if not self.ext:
            from mtdata.parser import detect_extension
            self.ext = detect_extension(filename or orig_name)
        self.filename = self.filename or f'{self.did.name}.{self.ext}'

        self.in_paths = in_paths
        self.in_ext = in_ext
        self.cite = cite
        self.cols = cols

        assert not self.ext.startswith("."), f'ext {self.ext} should not start with a dot (.)'
        self.is_archive = self.ext in ('zip', 'tar', 'tar.gz', 'tgz')
        if self.is_archive:
            assert self.in_paths and len(self.in_paths) > 0, 'Archive entries must have in_paths'
            if not self.in_ext:
                raise Exception('in_ext is required for archive files')
        else:
            if self.in_ext != 'opus_xces':
                assert not self.in_paths, f"in_paths is not applicable for non archive format {self.ext}"

    def is_swap(self, langs):
        if self.in_ext == 'tmx':
            return False
        return tuple(reversed(langs)) == tuple(self.lang_str)

    def __str__(self):
        return self.format(delim=' ')

    @property
    def lang_str(self):
        return self.did.lang_str

    def format(self, delim: str = ' '):
        msg = f'{self.did}{delim}{self.url}{delim}{",".join(self.in_paths or [])}'
        return msg

    def is_noisy(self, seg1, seg2) -> bool:
        # None or Empty
        noisy = seg1 is None or seg2 is None or not seg1.strip() or not seg2.strip()
        return noisy


class JW300Entry(Entry):
    url: Tuple[str, str, str]  # (align.xml, src.xml, tgt.xml)


@dataclass
class Experiment:
    langs: Tuple[BCP47Tag, BCP47Tag]  # (lang1 , lang2)  lang1 -> lang2
    train: List[Entry]  # training should be merged from all these
    tests: List[Entry]  # multiple tests; one of them can be validation set
    papers: Set['Paper'] = field(default_factory=set)

    def __post_init__(self):
        if any(not isinstance(lang, BCP47Tag) for lang in self.langs):
            self.langs = tuple(bcp47(l) for l in self.langs)
        for t in self.tests:
            assert t
        for t in self.train:
            assert t

    @classmethod
    def make(cls, index, langs: Tuple[str, str], train: List[str], tests: List[str]):
        train = [index.get_entry(name, langs) for name in train]
        tests = [index.get_entry(name, langs) for name in tests]
        return cls(langs, train=train, tests=tests)


@dataclass(eq=False)  # see for hash related issues: https://stackoverflow.com/a/52390734/1506477
class Paper:  # or Article

    name: str  # author1-etal-year
    title: str  # title
    url: str  # Paper url to be sure
    cite: str  # bibtex would be nice to display
    experiments: List[Experiment]

    langs: Set[Tuple[str, str]] = None

    def __post_init__(self):
        self.langs = self.langs or set(exp.langs for exp in self.experiments)
        for exp in self.experiments:
            exp.papers.add(self)
