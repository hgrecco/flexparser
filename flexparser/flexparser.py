"""
    flexparser.flexparser
    ~~~~~~~~~~~~~~~~~~~~~

    Classes and functions to create parsers.

    The idea is quite simple. You write a class for every type of content
    (called here ``ParsedStatement``) you need to parse. Each class should
    have a ``from_string`` constructor. We used extensively the ``typing``
    module to make the output structure easy to use and less error prone.

    For more information, take a look at https://github.com/hgrecco/flexparser

    :copyright: 2022 by flexparser Authors, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""

from __future__ import annotations

import collections
import dataclasses
import enum
import functools
import hashlib
import inspect
import logging
import pathlib
import pickle
import re
import typing as ty
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from functools import cached_property
from importlib import resources
from typing import Dict, Optional, Tuple, Type

_LOGGER = logging.getLogger("flexparser")

_SENTINEL = object()


################
# Exceptions
################


@dataclass(frozen=True)
class Element:
    """Base class for elements within a source file to be parsed."""

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
    """Base class for all exceptions in this package."""

    def __str__(self):
        return Element.__str__(self)


@dataclass(frozen=True)
class UnknownStatement(ParsingError):
    """A string statement could not bee parsed."""

    statement: str

    def __str__(self):
        return f"Could not parse '{self.statement}' (line: {self.lineno}, col: {self.colno})"

    @classmethod
    def from_line_col_statement(cls, lineno, colno, statement):
        obj = cls(statement)
        obj.set_line_col(lineno, colno)
        return obj


@dataclass(frozen=True)
class UnexpectedEOF(ParsingError):
    """End of file was found within an open block."""


#################
# Useful methods
#################


def _yield_types(
    obj, valid_subclasses=(object,), recurse_origin=(tuple, list, ty.Union)
):
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


class classproperty:  # noqa N801
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


def isplit(
    pattern: str | re.Pattern, line: str
) -> Iterator[tuple[int, str, Optional[str]]]:
    """Yield position, strings between matches and match group (delimiter)
    in a regex pattern applied to a line.

    Returns None as delimiter for last element.
    """
    col = 0
    if not is_empty_pattern(pattern):
        for m in re.finditer(pattern, line):
            part = line[col : m.start()]
            yield col, part, m.group(0)
            col = m.end()

    yield col, line[col:], None


class DelimiterMode(enum.Enum):
    """Specifies how to deal with delimiters while parsing."""

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


def isplit_mode(
    delimiters: Dict[str, Tuple[DelimiterMode, bool]], line: str
) -> Iterator[tuple[int, str]]:
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


class BaseIterator(ty.Generic[T], Iterator[T]):
    """Base class for iterator that provides the ability to peek."""

    _cache: ty.Deque[T]

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
            it = iter(((0, line),))

        if cls._strip_spaces:
            it = ((colno, s.strip()) for colno, s in it)

        return cls(it)

    @classmethod
    def subclass_with(cls, *, strip_spaces=True, delimiters: dict = None):
        """Creates a new subclass in one line."""

        return type(
            "CustomStatementIterator",
            (cls,),
            dict(_strip_spaces=strip_spaces, _delimiters=delimiters or {}),
        )


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
        it = (
            (lineno, colno, s)
            for lineno, line in enumerate(lines)
            for (colno, s) in cls._statement_iterator_class.from_line(line)
            if s
        )

        return cls(it)

    @classmethod
    def subclass_with(cls, *, statement_iterator_class):
        """Creates a new subclass in one line."""

        return type(
            "CustomSequenceIterator",
            (cls,),
            dict(_statement_iterator_class=statement_iterator_class),
        )


class HashIterator(BaseIterator[T]):
    """Iterates through an interator while hashing the content."""

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
CT = ty.TypeVar("CT")
PST = ty.TypeVar("PST", bound="ParsedStatement")
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
    def from_string(cls: Type[PST], s: str) -> FromString[PST]:
        """Parse a string into a ParsedStatement.

        Return files and their meaning:
        1. None: the string cannot be parsed with this class.
        2. A subclass of ParsedStatement: the string was parsed successfully
        3. A subclass of ParsingError the string could be parsed with this class but there is
           an error.
        """
        raise NotImplementedError(
            "ParsedStatement subclasses must implement "
            "'from_string' or 'from_string_and_config'"
        )

    @classmethod
    def from_string_and_config(cls: Type[PST], s: str, config: CT) -> FromString[PST]:
        """Parse a string into a ParsedStatement.

        Return files and their meaning:
        1. None: the string cannot be parsed with this class.
        2. A subclass of ParsedStatement: the string was parsed successfully
        3. A subclass of ParsingError the string could be parsed with this class but there is
           an error.
        """
        return cls.from_string(s)

    @classmethod
    def consume(
        cls: Type[PST], sequence_iterator: SequenceIterator, config: CT
    ) -> NullableConsume[PST]:
        """Peek into the iterator and try to parse.

        Return files and their meaning:
        1. None: the string cannot be parsed with this class, the iterator is kept an the current place.
        2. a subclass of ParsedStatement: the string was parsed successfully, advance the iterator.
        3. a subclass of ParsingError: the string could be parsed with this class but there is
           an error, advance the iterator.
        """
        lineno, colno, statement = sequence_iterator.peek()
        parsed_statement = cls.from_string_and_config(statement, config)
        if parsed_statement is None:
            return None
        next(sequence_iterator)
        parsed_statement.set_line_col(lineno, colno)
        return parsed_statement


OPST = ty.TypeVar("OPST", bound="ParsedStatement")
IPST = ty.TypeVar("IPST", bound="ParsedStatement")
CPST = ty.TypeVar("CPST", bound="ParsedStatement")
BT = ty.TypeVar("BT", bound="Block")
RBT = ty.TypeVar("RBT", bound="RootBlock")


@dataclass(frozen=True)
class Block(ty.Generic[OPST, IPST, CPST, CT]):
    """A sequence of statements with an opening, body and closing."""

    opening: Consume[OPST]
    body: Tuple[Consume[IPST], ...]
    closing: Consume[CPST]

    @classmethod
    def subclass_with(cls, *, opening=None, body=None, closing=None):
        @dataclass(frozen=True)
        class CustomBlock(Block):
            pass

        if opening:
            CustomBlock.__annotations__["opening"] = Single[ty.Union[opening]]
        if body:
            CustomBlock.__annotations__["body"] = Multi[ty.Union[body]]
        if closing:
            CustomBlock.__annotations__["closing"] = Single[ty.Union[closing]]

        return CustomBlock

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

    _ElementT = ty.TypeVar("_ElementT", bound=Element)

    def filter_by(self, *klass: Type[_ElementT]) -> Iterator[_ElementT]:
        """Yield elements of a given class or classes."""
        yield from (el for el in self if isinstance(el, klass))  # noqa Bug in pycharm.

    @cached_property
    def errors(self) -> ty.Tuple[ParsingError, ...]:
        """Tuple of errors found."""
        return tuple(self.filter_by(ParsingError))

    @property
    def has_errors(self) -> bool:
        """True if errors were found during parsing."""
        return bool(self.errors)

    ####################
    # Statement classes
    ####################

    @classproperty
    def opening_classes(cls) -> Iterator[Type[OPST]]:
        """Classes representing any of the parsed statement that can open this block."""
        opening = ty.get_type_hints(cls)["opening"]
        yield from _yield_types(opening, ParsedStatement)

    @classproperty
    def body_classes(cls) -> Iterator[Type[IPST]]:
        """Classes representing any of the parsed statement that can be in the body."""
        body = ty.get_type_hints(cls)["body"]
        yield from _yield_types(body, (ParsedStatement, Block))

    @classproperty
    def closing_classes(cls) -> Iterator[Type[CPST]]:
        """Classes representing any of the parsed statement that can close this block."""
        closing = ty.get_type_hints(cls)["closing"]
        yield from _yield_types(closing, ParsedStatement)

    ##########
    # Consume
    ##########

    @classmethod
    def consume_opening(
        cls: Type[BT], sequence_iterator: SequenceIterator, config: CT
    ) -> NullableConsume[OPST]:
        """Peek into the iterator and try to parse with any of the opening classes.

        See `ParsedStatement.consume` for more details.
        """
        for c in cls.opening_classes:
            el = c.consume(sequence_iterator, config)
            if el is not None:
                return el
        return None

    @classmethod
    def consume_body(
        cls, sequence_iterator: SequenceIterator, config: CT
    ) -> Consume[IPST]:
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
    def consume_closing(
        cls: Type[BT], sequence_iterator: SequenceIterator, config: CT
    ) -> NullableConsume[CPST]:
        """Peek into the iterator and try to parse with any of the opening classes.

        See `ParsedStatement.consume` for more details.
        """
        for c in cls.closing_classes:
            el = c.consume(sequence_iterator, config)
            if el is not None:
                return el
        return None

    @classmethod
    def consume(
        cls: Type[BT], sequence_iterator: SequenceIterator, config: CT
    ) -> Optional[BT]:
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


@dataclass(frozen=True)
class BOS(ParsedStatement[CT]):
    """Beginning of sequence."""

    @classmethod
    def from_string_and_config(cls: Type[PST], s: str, config: CT) -> FromString[PST]:
        return cls()


class EOS(ParsedStatement[CT]):
    """End of sequence."""

    @classmethod
    def from_string_and_config(cls: Type[PST], s: str, config: CT) -> FromString[PST]:
        return cls()


class RootBlock(ty.Generic[IPST, CT], Block[BOS, IPST, EOS, CT]):
    """A sequence of statement flanked by the beginning and ending of stream."""

    opening: Single[BOS]
    closing: Single[EOS]

    @classmethod
    def subclass_with(cls, *, body=None):
        @dataclass(frozen=True)
        class CustomRootBlock(RootBlock):
            pass

        if body:
            CustomRootBlock.__annotations__["body"] = Multi[ty.Union[body]]

        return CustomRootBlock

    @classmethod
    def consume_opening(
        cls: Type[RBT], sequence_iterator: SequenceIterator, config: CT
    ) -> NullableConsume[BOS]:
        return BOS().set_line_col(0, 0)

    @classmethod
    def consume(cls: Type[RBT], sequence_iterator: SequenceIterator, config: CT) -> RBT:
        block = super().consume(sequence_iterator, config)
        if block is None:
            raise ValueError(
                "Implementation error, 'RootBlock.consume' should never return None"
            )
        return block

    @classmethod
    def consume_closing(
        cls: Type[RBT], sequence_iterator: SequenceIterator, config: CT
    ) -> NullableConsume[EOS]:
        return None

    @classmethod
    def on_stop_iteration(cls, config):
        return EOS()


#################
# Source parsing
#################

ResourceT = ty.Tuple[str, str]  # package name, resource name
StrictLocationT = ty.Union[pathlib.Path, ResourceT]
SourceLocationT = ty.Union[str, StrictLocationT]


@dataclass(frozen=True)
class _ParsedCommon(ty.Generic[RBT, CT]):

    parsed_source: RBT

    # SHA-1 hash.
    content_hash: str

    # Parser configuration.
    config: CT

    @property
    def origin(self) -> StrictLocationT:
        raise NotImplementedError

    @cached_property
    def has_errors(self) -> bool:
        return self.parsed_source.has_errors

    def localized_errors(self):
        for err in self.parsed_source.errors:
            yield err

    #
    # @property
    # def origin(self) -> ResourceT:
    #     return self.package, self.resource_name


@dataclass(frozen=True)
class ParsedSourceFile(_ParsedCommon[RBT, CT], ty.Generic[RBT, CT]):
    """The parsed representation of a file."""

    # Fullpath of the original file.
    filename: pathlib.Path

    # Modification time of the file.
    mtime: float

    @property
    def origin(self) -> pathlib.Path:
        return self.filename


@dataclass(frozen=True)
class ParsedResource(_ParsedCommon[RBT, CT], ty.Generic[RBT, CT]):
    """The parsed representation of a python resource."""

    # Fullpath of the original file, None if a text was provided
    package: str
    resource_name: str

    @property
    def origin(self) -> ResourceT:
        return self.package, self.resource_name


@dataclass(frozen=True)
class CannotParseResourceAsFile(Exception):
    """The requested python package resource cannot be located as a file
    in the file system.
    """

    package: str
    resource_name: str


class Parser(ty.Generic[RBT, CT]):
    """Parser class."""

    #: class to iterate through statements in a source unit.
    _sequence_iterator_class: Type[SequenceIterator] = SequenceIterator

    #: root block class containing statements and blocks can be parsed.
    _root_block_class: Type[RBT]

    #: source file text encoding.
    _encoding = "utf-8"

    #: configuration passed to from_string functions.
    _config: CT

    #: try to open resources as files.
    _prefer_resource_as_file: bool

    def __init__(self, config: CT, prefer_resource_as_file=True):
        self._config = config
        self._prefer_resource_as_file = prefer_resource_as_file

    def consume(self, sequence_iterator: SequenceIterator) -> RBT:
        return self._root_block_class.consume(sequence_iterator, self._config)

    def parse(
        self, source_location: SourceLocationT
    ) -> ty.Union[ParsedSourceFile[RBT, CT], ParsedResource[RBT, CT]]:
        """Parse a file into a ParsedSourceFile or ParsedResource.

        Parameters
        ----------
        source_location:
            if str or pathlib.Path is interpreted as a file.
            if (str, str) is interpreted as (package, resource) using the resource python api.
        """
        if isinstance(source_location, tuple) and len(source_location) == 2:
            if self._prefer_resource_as_file:
                try:
                    return self.parse_resource_from_file(*source_location)
                except CannotParseResourceAsFile:
                    pass
            return self.parse_resource(*source_location)

        if isinstance(source_location, str):
            return self.parse_file(pathlib.Path(source_location))

        if isinstance(source_location, pathlib.Path):
            return self.parse_file(source_location)

        raise TypeError(
            f"Unknown type {type(source_location)}, "
            "use str or pathlib.Path for files or "
            "(package: str, resource_name: str) tuple "
            "for a resource."
        )

    def parse_file(self, path: pathlib.Path) -> ParsedSourceFile[RBT, CT]:
        """Parse a file into a ParsedSourceFile.

        Parameters
        ----------
        path
            path of the file.
        """
        with path.open(mode="r", encoding=self._encoding) as fi:
            sic = self._sequence_iterator_class.from_lines(
                map(lambda s: s.strip("\r\n"), fi)
            )
            hsi = HashSequenceIterator(sic)
            body = self.consume(hsi)
            return ParsedSourceFile(
                body,
                hsi.hexdigest(),
                self._config,
                path,
                path.stat().st_mtime,
            )

    def parse_resource_from_file(
        self, package: str, resource_name: str
    ) -> ParsedSourceFile[RBT, CT]:
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

    def parse_resource(
        self, package: str, resource_name: str
    ) -> ParsedResource[RBT, CT]:
        """Parse a resource into a ParsedResource.

        Parameters
        ----------
        package
            package name where the resource is located.
        resource_name
            name of the resource
        """
        with resources.open_text(package, resource_name, encoding=self._encoding) as fi:
            sic = self._sequence_iterator_class.from_lines(
                map(lambda s: s.strip("\r\n"), fi)
            )
            hsi = HashSequenceIterator(sic)
            body = self.consume(hsi)
        return ParsedResource(
            body,
            hsi.hexdigest(),
            self._config,
            package,
            resource_name,
        )


##########
# Project
##########


class IncludeStatement(ParsedStatement):
    """ "Include statements allow to merge files."""

    @property
    def target(self) -> str:
        raise NotImplementedError(
            "IncludeStatement subclasses must implement target property."
        )


class ParsedProject(
    ty.Dict[
        ty.Optional[ty.Tuple[StrictLocationT, str]],
        ty.Union[ParsedSourceFile, ParsedResource],
    ]
):
    """Collection of files, independent or connected via IncludeStatement.

    Keys are either an absolute pathname  or a tuple package name, resource name.

    None is the name of the root.

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
                        raise ValueError(f"{location} was already included.")
                    yield from self._iter_statements(
                        ((location, self[location]),), seen, include_only_once
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
        yield from self._iter_statements([(None, self[None])], set(), include_only_once)


def default_locator(source_location: StrictLocationT, target: str) -> StrictLocationT:
    """Return a new location from current_location and target."""

    if isinstance(source_location, pathlib.Path):
        current_location = pathlib.Path(source_location).resolve()

        if current_location.is_file():
            current_path = source_location.parent
        else:
            current_path = source_location

        target_path = pathlib.Path(target)
        if target_path.is_absolute():
            raise ValueError(
                f"Cannot refer to absolute paths in import statements ({source_location}, {target})."
            )

        tmp = (current_path / target_path).resolve()
        if not tmp.is_relative_to(current_path):
            raise ValueError(
                f"Cannot refer to locations above the current location ({source_location}, {target})"
            )

        return tmp.absolute()

    elif isinstance(source_location, tuple) and len(source_location) == 2:
        return source_location[0], target

    raise TypeError(
        f"Cannot handle type {type(source_location)}, "
        "use str or pathlib.Path for files or "
        "(package: str, resource_name: str) tuple "
        "for a resource."
    )


SpecT = ty.Union[
    ty.Type[Parser],
    ty.Union[ty.Type[Block], ty.Type[ParsedStatement]],
    ty.Iterable[ty.Union[ty.Type[Block], ty.Type[ParsedStatement]]],
    ty.Type[RootBlock],
]


def parse(
    entry_point: SourceLocationT,
    spec: SpecT,
    config=None,
    *,
    strip_spaces: bool = True,
    delimiters=None,
    locator: ty.Callable[[StrictLocationT, str], StrictLocationT] = default_locator,
    prefer_resource_as_file: bool = True,
) -> ParsedProject:
    """Parse sources into a ParsedProject dictionary.

    Parameters
    ----------
    entry_point
        file or resource, given as (package_name, resource_name).
    spec
        specification of the content to parse. Can be one of the following things:
        - Parser class.
        - Block or ParsedStatement derived class.
        - Iterable of Block or ParsedStatement derived class.
        - RootBlock derived class.
    config
        a configuration object that will be passed to `from_string_and_config`
        classmethod.
    strip_spaces : bool
        if True, spaces will be stripped for each statement before calling
        ``from_string_and_config``.
    delimiters : dict
        Sepecify how the source file is split into statements (See below).
    locator : Callable
        function that takes the current location and a target of an IncludeStatement
        and returns a new location.
    prefer_resource_as_file : bool
        if True, resources will try to be located in the filesystem if
        available.


    Delimiters dictionary
    ---------------------
        The delimiters are specified with the keys of the delimiters dict.
    The dict files can be used to further customize the iterator. Each
    consist of a tuple of two elements:
      1. A value of the DelimiterMode to indicate what to do with the
         delimiter string: skip it, attach keep it with previous or next string
      2. A boolean indicating if parsing should stop after fiSBT
         encountering this delimiter.


    """

    if isinstance(spec, type) and issubclass(spec, Parser):
        CustomParser = spec
    else:
        if isinstance(spec, (tuple, list)):

            for el in spec:
                if not issubclass(el, (Block, ParsedStatement)):
                    raise TypeError(
                        "Elements in root_block_class must be of type Block or ParsedStatement, "
                        f"not {el}"
                    )

            @dataclass(frozen=True)
            class CustomRootBlock(RootBlock):
                pass

            CustomRootBlock.__annotations__["body"] = Multi[ty.Union[spec]]

        elif isinstance(spec, type) and issubclass(spec, RootBlock):

            CustomRootBlock = spec

        elif isinstance(spec, type) and issubclass(spec, (Block, ParsedStatement)):

            @dataclass(frozen=True)
            class CustomRootBlock(RootBlock):
                pass

            CustomRootBlock.__annotations__["body"] = Multi[spec]

        else:
            raise TypeError(
                "`spec` must be of type RootBlock or tuple of type Block or ParsedStatement, "
                f"not {type(spec)}"
            )

        class CustomParser(Parser):

            _sequence_iterator_class = SequenceIterator.subclass_with(
                statement_iterator_class=StatementIterator.subclass_with(
                    strip_spaces=strip_spaces, delimiters=delimiters
                )
            )
            _root_block_class = CustomRootBlock

    parser = CustomParser(config, prefer_resource_as_file=prefer_resource_as_file)

    pp = ParsedProject()

    # : ty.List[Optional[ty.Union[LocatorT, str]], ...]
    pending: ty.List[ty.Tuple[StrictLocationT, str]] = []
    if isinstance(entry_point, (str, pathlib.Path)):
        entry_point = pathlib.Path(entry_point)
        if not entry_point.is_absolute():
            entry_point = pathlib.Path.cwd() / entry_point

    elif not (isinstance(entry_point, tuple) and len(entry_point) == 2):
        raise TypeError(
            f"Cannot handle type {type(entry_point)}, "
            "use str or pathlib.Path for files or "
            "(package: str, resource_name: str) tuple "
            "for a resource."
        )

    pp[None] = parsed = parser.parse(entry_point)
    pending.extend(
        (parsed.origin, el.target)
        for el in parsed.parsed_source.filter_by(IncludeStatement)
    )

    while pending:
        source_location, target = pending.pop(0)
        pp[(source_location, target)] = parsed = parser.parse(
            locator(source_location, target)
        )
        pending.extend(
            (parsed.origin, el.target)
            for el in parsed.parsed_source.filter_by(IncludeStatement)
        )

    return pp
