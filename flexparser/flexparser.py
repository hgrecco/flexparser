"""
    flexparser.flexparser
    ~~~~~~~~~~~~~~~~~~~~~

    There are three type of

    - statements: single lines handled by the Definition.from_string method.
    - line directives
    - block directives:


    :copyright: 2022 by flexcache Authors, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""

from __future__ import annotations

import abc
import collections
import copy
import enum
import functools
import hashlib
import pathlib
import pickle
import re
import logging
import typing
import typing as ty
import inspect
import dataclasses
from dataclasses import dataclass
from collections.abc import Iterator, Iterable
from importlib import resources
from typing import Optional, Tuple, Type, Dict
from functools import cached_property

_LOGGER = logging.getLogger("flexparser")

_SENTINEL = object()


################
# Exceptions
################

@dataclass(frozen=True)
class Element:
    """Base class for elements within a source file to be parsed.
    """

    lineno: int = dataclasses.field(init=False, default=-1)
    colno: int = dataclasses.field(init=False, default=-1)

    @property
    def format_line_col(self):
        return f"(line: {self.lineno}, col: {self.colno})"

    def set_line_col(self, lineno, colno):
        object.__setattr__(self, "lineno", lineno)
        object.__setattr__(self, "colno", colno)
        return self


@dataclass(frozen=True)
class ParsingError(Element, Exception):
    """Base class for all exceptions in this package.
    """

    origin: typing.Union[str, typing.Tuple[str, str], pathlib.Path] = dataclasses.field(init=False, default="")

    @property
    def origin_(self) -> str:
        if isinstance(self.origin, tuple):
            return f"resource (package: {self.origin[0]}, name: {self.origin[1]})"
        return str(self.origin)

    def copy_with(self, origin):
        d = dataclasses.asdict(self)
        d.pop("lineno")
        d.pop("colno")
        d.pop("origin")
        obj = self.__class__(**d)
        obj.set_line_col(self.lineno, self.colno)
        object.__setattr__(obj, "origin", origin)
        return obj

    def __str__(self):
        return Element.__str__(self)


@dataclass(frozen=True)
class UnknownStatement(ParsingError):
    """A string statement could not bee parsed.
    """

    statement: str

    def __str__(self):
        return f"Could not parse '{self.statement}' in {self.origin_} (line: {self.lineno}, col: {self.colno})"

    @classmethod
    def from_line_col_statement(cls, lineno, colno, statement):
        obj = cls(statement)
        obj.set_line_col(lineno, colno)
        return obj


@dataclass(frozen=True)
class UnexpectedEOF(ParsingError):
    """End of file was found within an open block.
    """


#################
# Useful methods
#################

def _yield_types(obj, valid_subclasses=(object, ), recurse_origin=(tuple, list, ty.Union)):
    """Recursively transverse type annotation if the
    origin is any of the types in `recurse_origin`
    and yield those type which are subclasses of `valid_subclasses`.

    """
    if ty.get_origin(obj) in recurse_origin:
        for el in ty.get_args(obj):
            yield from _yield_types(el, valid_subclasses, recurse_origin)
    else:
        if inspect.isclass(obj) and issubclass(obj, valid_subclasses):
            yield obj


class classproperty: # noqa N801
    """Decorator for a class property

    In Python 3.9+ can be replaced by

        @classmethod
        @property
        def myprop(self):
            return 42

    """

    def __init__(self, fget):
        self.fget = fget

    def __get__(self, owner_self, owner_cls):
        return self.fget(owner_cls)


def is_empty_pattern(pattern: str | re.Pattern) -> bool:
    """True if the regex pattern string is empty
    or the compiled version comes from an empty string.
    """
    if isinstance(pattern, str):
        return not bool(pattern)
    return not bool(getattr(pattern, "pattern", ""))


def isplit(pattern: str | re.Pattern, line: str) -> Iterator[tuple[int, str, Optional[str]]]:
    """Yield position, strings between matches and match group (delimiter)
    in a regex pattern applied to a line.

    Returns None as delimiter for last element.
    """
    col = 0
    if not is_empty_pattern(pattern):
        for m in re.finditer(pattern, line):
            part = line[col:m.start()]
            yield col, part, m.group(0)
            col = m.end()

    yield col, line[col:], None


class DelimiterMode(enum.Enum):
    """Specifies how to deal with delimiters while parsing.
    """

    #: Skip delimiter in output string
    SKIP = 0

    #: Keep delimiter with previous string.
    WITH_PREVIOUS = 1

    #: Keep delimiter with next string.
    WITH_NEXT = 2


@functools.lru_cache
def _build_delimiter_pattern(pattern_tuple: Tuple[str, ...]) -> re.Pattern:
    """Compile a tuple of delimiters into a regex expression with a capture group
    around the delimiter.
    """
    return re.compile("|".join(f"({re.escape(el)})" for el in pattern_tuple))


def isplit_mode(delimiters: Dict[str, Tuple[DelimiterMode, bool]], line: str) -> Iterator[tuple[int, str]]:
    """Yield position and strings between delimiters.

    The delimiters are specified with the keys of the delimiters dict.
    The dict files can be used to further customize the iterator. Each
    consist of a tuple of two elements:
      1. A value of the DelimiterMode to indicate what to do with the
         delimiter string: skip it, attach keep it with previous or next string
      2. A boolean indicating if parsing should stop after fiSBT
         encountering this delimiter.

    Empty strings are not yielded.
    """
    pattern = _build_delimiter_pattern(tuple(delimiters.keys()))
    dragged = ""
    break_next = False
    for col, part, dlm in isplit(pattern, line):
        if break_next:
            yield col - len(dragged), dragged + line[col:]
            break

        next_drag = ""
        if dlm is None:
            delimiter_mode, break_next = DelimiterMode.SKIP, False
        else:
            delimiter_mode, break_next = delimiters[dlm]

            if delimiter_mode == DelimiterMode.WITH_PREVIOUS:
                part = part + dlm
            elif delimiter_mode == DelimiterMode.WITH_NEXT:
                next_drag = dlm

        if part:
            yield col - len(dragged), dragged + part

        dragged = next_drag


############
# Iterators
############

T = ty.TypeVar("T")


class BaseIterator(typing.Generic[T], Iterator[T]):
    """Base class for iterator that provides the ability to peek.
    """

    _cache: typing.Deque[T]

    def __init__(self, iterator: Iterator[T]):
        self._it = iterator
        self._cache = collections.deque()

    def __iter__(self):
        return self

    def peek(self, default=_SENTINEL) -> T:
        """Return the item that will be next returned from ``next()``.

        Return ``default`` if there are no items left. If ``default`` is not
        provided, raise ``StopIteration``.

        """
        if not self._cache:
            try:
                self._cache.append(next(self._it))
            except StopIteration:
                if default is _SENTINEL:
                    raise
                return default
        return self._cache[0]

    def __next__(self) -> T:
        if self._cache:
            return self._cache.popleft()

        return next(self._it)


class StatementIterator(BaseIterator[Tuple[int, str]]):
    """Yield position and statement within a string,
    ending when all the line is consumed.

    Elements are separated by delimiter/s and leading and trailing spaces
    are (optionally) removed.

    By default, spaces are removed and no delimiter is defined.

    >>> si = StatementIterator(" spam ")
    >>> si.peek()
    0, "spam"
    >>> tuple(si)
    ((0, "spam"), )

    The behavior can be customized by subclassing

    >>> class CustomStatementIterator(StatementIterator):
    ...     _strip_spaces = False
    ...     _delimiters = {"#": (DelimiterMode.WITH_NEXT, True)}

    or equivalent:

    >>> CustomStatementIterator = StatementIterator.subclass_with(strip_spaces=False,
    ...                                                           delimiters = {"#": (DelimiterMode.WITH_NEXT, True)})

    """

    _strip_spaces: bool = True
    _delimiters: Optional[Dict[str, Tuple[DelimiterMode, bool]]] = None

    @classmethod
    def from_line(cls, line: str):
        if cls._delimiters:
            it = iter(isplit_mode(cls._delimiters, line))
        else:
            it = iter(((0, line), ))

        if cls._strip_spaces:
            it = ((colno, s.strip()) for colno, s in it)

        return cls(it)

    @classmethod
    def subclass_with(cls, *, strip_spaces=True, delimiters: dict = None):
        """Creates a new subclass in one line.
        """

        return type("CustomStatementIterator", (cls, ),
                    dict(_strip_spaces=strip_spaces, _delimiters=delimiters or {}))


class SequenceIterator(BaseIterator[Tuple[int, int, str]]):
    """Yield line, position and statement within elements of a sequence.

    These sub-elements are parsed from the elements used a StatementIterator,
    and it can be customized by subclassing this class.

    >>> CustomStatementIterator = StatementIterator.subclass_with(strip_spaces=False)
    >>> class CustomSequenceIterator(SequenceIterator):
    ...     _statement_iterator_class = CustomStatementIterator
    """

    _statement_iterator_class: Type[StatementIterator] = StatementIterator

    @classmethod
    def from_lines(cls, lines: Iterable[str]):
        it = ((lineno, colno, s)
              for lineno, line in enumerate(lines)
              for (colno, s) in cls._statement_iterator_class.from_line(line)
              if s
              )

        return cls(it)

    @classmethod
    def subclass_with(cls, *, statement_iterator_class):
        """Creates a new subclass in one line.
        """

        return type("CustomSequenceIterator", (cls, ),
                    dict(_statement_iterator_class=statement_iterator_class))


class HashIterator(BaseIterator[T]):
    """Iterates through an interator while hashing the content.
    """

    def __init__(self, iterator: Iterator[T]):
        super().__init__(iterator)
        self._hasher = hashlib.sha1()

    def __iter__(self):
        return self

    def __next__(self):
        el = super().__next__()
        self._hasher.update(pickle.dumps(el))
        return el

    def hexdigest(self):
        return self._hasher.hexdigest()


class HashSequenceIterator(HashIterator, SequenceIterator):
    pass


###########
# Parsing
###########

# Configuration type
CT = ty.TypeVar('CT')
PST = ty.TypeVar('PST', bound='ParsedStatement')
LineColStr = Tuple[int, int, str]
FromString = ty.Union[None, PST, ParsingError]
Consume = ty.Union[PST, ParsingError]
NullableConsume = ty.Union[None, PST, ParsingError]

Single = ty.Union[PST, ParsingError]
Multi = ty.Tuple[ty.Union[PST, ParsingError], ...]


@dataclass(frozen=True)
class ParsedStatement(ty.Generic[CT], Element):
    """A single parsed statement.

    In order to write your own, you need to subclass it as a
    frozen dataclass and implement the parsing logic by overriding
    `from_string` classmethod.

    Takes two arguments: the string to parse and an object given
    by the parser which can be used to store configuration information.

    It should return an instance of this class if parsing
    was successful or None otherwise
    """

    @classmethod
    @abc.abstractmethod
    def from_string(cls: Type[PST], s: str, config: CT) -> FromString[PST]:
        """Parse a string into a ParsedStatement.

        Return files and their meaning:
        1. None: the string cannot be parsed with this class.
        2. A subclass of ParsedStatement: the string was parsed successfully
        3. A subclass of ParsingError the string could be parsed with this class but there is
           an error.
        """

    @classmethod
    def consume(cls: Type[PST], sequence_iterator: SequenceIterator, config: CT) -> NullableConsume[PST]:
        """Peek into the iterator and try to parse.

        Return files and their meaning:
        1. None: the string cannot be parsed with this class, the iterator is kept an the current place.
        2. a subclass of ParsedStatement: the string was parsed successfully, advance the iterator.
        3. a subclass of ParsingError: the string could be parsed with this class but there is
           an error, advance the iterator.
        """
        lineno, colno, statement = sequence_iterator.peek()
        parsed_statement = cls.from_string(statement, config)
        if parsed_statement is None:
            return None
        next(sequence_iterator)
        parsed_statement.set_line_col(lineno, colno)
        return parsed_statement


OPST = ty.TypeVar('OPST', bound='ParsedStatement')
IPST = ty.TypeVar('IPST', bound='ParsedStatement')
CPST = ty.TypeVar('CPST', bound='ParsedStatement')
BT = ty.TypeVar('BT', bound='Block')
RBT = typing.TypeVar("RBT", bound="RootBlock")


@dataclass(frozen=True)
class Block(ty.Generic[OPST, IPST, CPST, CT]):
    """A sequence of statements with an opening, body and closing.
    """

    opening: Consume[OPST]
    body: Tuple[Consume[IPST], ...]
    closing: Consume[CPST]

    def __iter__(self) -> Iterator[Element]:
        yield self.opening
        for el in self.body:
            if isinstance(el, Block):
                yield from el
            else:
                yield el
        yield self.closing

    ###################################################
    # Convenience methods to iterate parsed statements
    ###################################################

    def filter_by(self, *klass) -> Iterator[Element]:
        """Yield elements of a given class or classes.
        """
        yield from (
            el for el in self if isinstance(el, klass)
        )

    @cached_property
    def errors(self) -> ty.Tuple[Element, ...]:
        """Tuple of errors found.
        """
        return tuple(self.filter_by(ParsingError))

    @property
    def has_errors(self) -> bool:
        """True if errors were found during parsing.
        """
        return bool(self.errors)

    ####################
    # Statement classes
    ####################

    @classproperty
    def opening_classes(cls) -> Iterator[Type[OPST]]:
        """Classes representing any of the parsed statement that can open this block.
        """
        opening = ty.get_type_hints(cls)["opening"]
        yield from _yield_types(opening, ParsedStatement)

    @classproperty
    def body_classes(cls) -> Iterator[Type[IPST]]:
        """Classes representing any of the parsed statement that can be in the body.
        """
        body = ty.get_type_hints(cls)["body"]
        yield from _yield_types(body, (ParsedStatement, Block))

    @classproperty
    def closing_classes(cls) -> Iterator[Type[CPST]]:
        """Classes representing any of the parsed statement that can close this block.
        """
        closing = ty.get_type_hints(cls)["closing"]
        yield from _yield_types(closing, ParsedStatement)

    ##########
    # Consume
    ##########

    @classmethod
    def consume_opening(cls: Type[BT], sequence_iterator: SequenceIterator, config: CT) -> NullableConsume[OPST]:
        """Peek into the iterator and try to parse with any of the opening classes.

        See `ParsedStatement.consume` for more details.
        """
        for c in cls.opening_classes:
            el = c.consume(sequence_iterator, config)
            if el is not None:
                return el
        return None

    @classmethod
    def consume_body(cls, sequence_iterator: SequenceIterator, config: CT) -> Consume[IPST]:
        """Peek into the iterator and try to parse with any of the body classes.

        If the statement cannot be parsed, a UnknownStatement is returned.
        """
        for c in cls.body_classes:
            el = c.consume(sequence_iterator, config)
            if el is not None:
                return el
        el = next(sequence_iterator)
        return UnknownStatement.from_line_col_statement(*el)

    @classmethod
    def consume_closing(cls: Type[BT], sequence_iterator: SequenceIterator, config: CT) -> NullableConsume[CPST]:
        """Peek into the iterator and try to parse with any of the opening classes.

        See `ParsedStatement.consume` for more details.
        """
        for c in cls.closing_classes:
            el = c.consume(sequence_iterator, config)
            if el is not None:
                return el
        return None

    @classmethod
    def consume(cls: Type[BT], sequence_iterator: SequenceIterator, config: CT) -> Optional[BT]:
        """Try consume the block.

        Possible outcomes:
        1. The opening was not matched, return None.
        2. A subclass of Block, where body and closing migh contain errors.
        """
        opening = cls.consume_opening(sequence_iterator, config)
        if opening is None:
            return None
        body = []
        closing = None
        while closing is None:
            try:
                closing = cls.consume_closing(sequence_iterator, config)
                if closing is not None:
                    continue
                el = cls.consume_body(sequence_iterator, config)
                body.append(el)
            except StopIteration:
                closing = cls.on_stop_iteration(config)

        return cls(opening, tuple(body), closing)

    @classmethod
    def on_stop_iteration(cls, config):
        return UnexpectedEOF()


class BOS(ParsedStatement[CT]):
    """Beginning of sequence.
    """

    @classmethod
    def from_string(cls: Type[PST], s: str, config: CT) -> FromString[PST]:
        return cls()


class EOS(ParsedStatement[CT]):
    """End of sequence.
    """

    @classmethod
    def from_string(cls: Type[PST], s: str, config: CT) -> FromString[PST]:
        return cls()


class RootBlock(typing.Generic[IPST, CT], Block[BOS, IPST, EOS, CT]):
    """A sequence of statement flanked by the beginning and ending of stream.
    """
    opening: Single[BOS]
    closing: Single[EOS]

    @classmethod
    def consume_opening(cls: Type[RBT], sequence_iterator: SequenceIterator, config: CT) -> NullableConsume[BOS]:
        return BOS().set_line_col(0, 0)

    @classmethod
    def consume(cls: Type[RBT], sequence_iterator: SequenceIterator, config: CT) -> RBT:
        block = super().consume(sequence_iterator, config)
        if block is None:
            raise ValueError("Implementation error, 'RootBlock.consume' should never return None")
        return block

    @classmethod
    def consume_closing(cls: Type[RBT], sequence_iterator: SequenceIterator, config: CT) -> NullableConsume[EOS]:
        return None

    @classmethod
    def on_stop_iteration(cls, config):
        return EOS()


#################
# Source parsing
#################


SourceLocationT = ty.Union[str, pathlib.Path, ty.Tuple[str, str]]


@dataclass(frozen=True)
class ParsedSourceFile(typing.Generic[RBT, CT]):
    """The parsed representation of a file.
    """

    parsed_source: RBT

    # Fullpath of the original file.
    filename: pathlib.Path

    # Modification time of the file.
    mtime: float

    # SHA-1 hash.
    content_hash: str

    # Parser configuration.
    config: CT

    @property
    def origin(self) -> SourceLocationT:
        return self.filename

    @cached_property
    def has_errors(self) -> bool:
        return self.parsed_source.has_errors

    def localized_errors(self):
        for err in self.parsed_source.errors:
            yield err.copy_with(self.origin)


@dataclass(frozen=True)
class ParsedResource(typing.Generic[RBT, CT]):
    """The parsed representation of a python resource.
    """

    parsed_source: RBT

    # Fullpath of the original file, None if a text was provided
    package: str
    resource_name: str

    # SHA-1 hash
    content_hash: str

    # Parser configuration.
    config: CT

    @property
    def origin(self) -> SourceLocationT:
        return self.package, self.resource_name

    @cached_property
    def has_errors(self) -> bool:
        return self.parsed_source.has_errors

    def localized_errors(self):
        for lineno, colno, err in self.parsed_source.errors:
            yield err.copy_with(self.origin)


@dataclass(frozen=True)
class CannotParseResourceAsFile(Exception):
    """The requested python package resource cannot be located as a file
    in the file system.
    """

    package: str
    resource: str


class Parser(ty.Generic[RBT, CT]):
    """Parser class.
    """

    #: class to iterate through statements in a source unit.
    _sequence_iterator_class: Type[SequenceIterator] = SequenceIterator

    #: root block class containing statements and blocks can be parsed.
    _root_block_class: Type[RBT]

    #: source file text encoding.
    _encoding = "utf-8"

    #: configuration passed to from_string functions.
    _config: CT

    #: try to open resources as files.
    _prefer_resource_as_file: bool = True

    def __init__(self, config: CT):
        self._config = config

    def consume(self, sequence_iterator: SequenceIterator) -> RBT:
        return self._root_block_class.consume(sequence_iterator, self._config)

    def parse(self, source_location: SourceLocationT) -> ty.Union[ParsedSourceFile[RBT, CT], ParsedResource[RBT, CT]]:
        """Parse a file into a ParsedSourceFile or ParsedResource.

        Parameters
        ----------
        source_location:
            if str or pathlib.Path is interpreted as a file.
            if (str, str) is interpreted as (package, resource) using the resource python api.
        """
        if isinstance(source_location, tuple):
            if self._prefer_resource_as_file:
                try:
                    return self.parse_resource_from_file(*source_location)
                except CannotParseResourceAsFile:
                    pass
            return self.parse_resource(*source_location)

        if isinstance(source_location, str):
            source_location = pathlib.Path(source_location)
        elif not isinstance(source_location, pathlib.Path):
            raise TypeError(f"Unknown type {type(source_location)}, "
                            "use str or pathlib.Path for files or "
                            "(package: str, resource_name: str) tuple "
                            "for a resource.")

        return self.parse_file(source_location)

    def parse_file(self, path: pathlib.Path) -> ParsedSourceFile[RBT, CT]:
        """Parse a file into a ParsedSourceFile.

        Parameters
        ----------
        path
            path of the file.
        """
        with path.open(mode="r", encoding=self._encoding) as fi:
            sic = self._sequence_iterator_class.from_lines(map(lambda s: s.strip("\r\n"), fi))
            hsi = HashSequenceIterator(sic)
            body = self.consume(hsi)
            return ParsedSourceFile(body, path,
                                    path.stat().st_mtime, hsi.hexdigest(),
                                    self._config)

    def parse_resource_from_file(self, package: str, resource_name: str) -> ParsedSourceFile[RBT, CT]:
        """Parse a resource into a ParsedSourceFile, opening as a file.

        Parameters
        ----------
        package
            package name where the resource is located.
        resource_name
            name of the resource
        """
        with resources.path(package, resource_name) as p:
            path = p.resolve()

        if path.exists():
            return self.parse_file(path)

        raise CannotParseResourceAsFile(package, resource_name)

    def parse_resource(self, package: str, resource_name: str) -> ParsedResource[RBT, CT]:
        """Parse a resource into a ParsedResource.

        Parameters
        ----------
        package
            package name where the resource is located.
        resource_name
            name of the resource
        """
        with resources.open_text(package, resource_name, encoding=self._encoding) as fi:
            sic = self._sequence_iterator_class.from_lines(map(lambda s: s.strip("\r\n"), fi))
            hsi = HashSequenceIterator(sic)
            body = self.consume(hsi)
        return ParsedResource(body, package, resource_name, hsi.hexdigest(), self._config)


##########
# Project
##########


class IncludeStatement(ParsedStatement):
    """"Include statements allow to merge files.
    """

    @property
    def target(self) -> str:
        raise ValueError


class ParsedProject(dict[SourceLocationT, ty.Union[ParsedSourceFile, ParsedResource]]):
    """Collection of files, independent or connected via IncludeStatement/
    """

    @cached_property
    def has_errors(self) -> bool:
        return any(el.has_errors for el in self.values())

    def localized_errors(self):
        for el in self.values():
            yield from el.localized_errors()

    def _iter_statements(self, items, seen, include_only_once):
        """Iter all definitions in the order they appear,
        going into the included files.
        """
        for source_location, parsed in items:
            seen.add(source_location)
            for parsed_statement in parsed.parsed_source:
                if isinstance(parsed_statement, IncludeStatement):
                    location = parsed.origin, parsed_statement.target
                    if location in seen and include_only_once:
                        raise ValueError(
                            f"{location} was already included."
                        )
                    yield from self._iter_statements(
                        ((location, self[location]),),
                        seen,
                        include_only_once
                    )
                else:
                    yield parsed_statement

    def iter_statements(self, include_only_once=True):
        """Iter all definitions in the order they appear,
        going into the included files.

        Parameters
        ----------
        include_only_once
            if true, each file cannot be included more than once.
        """
        yield from self._iter_statements(self.items(), set(), include_only_once)


def default_locator(current_location: SourceLocationT, target: str) -> SourceLocationT:
    """Return a new location from current_location and target.
    """

    if isinstance(current_location, (pathlib.Path, str)):
        current_location = pathlib.Path(current_location).resolve()

        target = pathlib.Path(target)
        if target.is_absolute():
            raise ValueError(f"Cannot refer to absolute paths in import statements ({current_location}, {target}).")

        if current_location.is_file():
            tmp = current_location.parent / target
        else:
            tmp = current_location / target

        if not tmp.is_relative_to(current_location.parent):
            raise ValueError(f"Cannot refer to locations above the root ({current_location}, {target})")

        return tmp

    elif isinstance(current_location, tuple) and len(current_location) == 2:
        return current_location[0], target

    raise TypeError(f"Unknown type {type(current_location)}, "
                    "use str or pathlib.Path for files or "
                    "(package: str, resource_name: str) tuple "
                    "for a resource.")


def parse_project(parser: Parser, source_locations, *, locator=default_locator) -> ParsedProject:
    """Parse a collection of files into a ParsedProject,
    following the import statements in each of them
    """

    pending = []
    for source_location in source_locations:
        if isinstance(source_location, (pathlib.Path, str)):
            pending.append((pathlib.Path.cwd(), source_location))
        else:
            pending.append(source_location)

    out = {}
    while pending:
        origin, target = pending.pop()
        out[(origin, target)] = parsed = parser.parse(locator(origin, target))
        pending.extend(((parsed.origin, el.target)
                        for el in parsed.parsed_source.filter_by(IncludeStatement)
                       ))
    return ParsedProject(out)


def parse(source_locations, root_block_class, config, *, strip_spaces=True, delimiters=None, locator=default_locator) -> ParsedProject:
    """Parse sources into a ParsedProject.
    """
    class CustomParser(Parser):

        _sequence_iterator_class = SequenceIterator.subclass_with(
            statement_iterator_class=StatementIterator.subclass_with(strip_spaces=strip_spaces,
                                                                     delimiters=delimiters)
        )
        _root_block_class = root_block_class

    parser = CustomParser(config)

    if isinstance(source_locations, (str, pathlib.Path)):
        return parse_project(parser, [source_locations], locator=locator)
    else:
        return parse_project(parser, source_locations, locator=locator)