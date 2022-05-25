from __future__ import annotations

import numbers
import typing as ty
from dataclasses import dataclass

from flexparser import flexparser as fp

from . import errors
from .pintimports import ParserHelper, UnitsContainer


@dataclass(frozen=True)
class Config:
    """Configuration used by the parser."""

    #: Indicates the output type of non integer numbers.
    non_int_type: ty.Type[numbers.Number] = float

    def to_scaled_units_container(self, s: str):
        return ParserHelper.from_string(s, self.non_int_type)

    def to_units_container(self, s: str):
        v = self.to_scaled_units_container(s)
        if v.scale != 1:
            raise errors.UnexpectedScaleInContainer(str(v.scale))
        return UnitsContainer(v)

    def to_dimension_container(self, s: str):
        v = self.to_units_container(s)
        _ = [check_dim(el) for el in v.keys()]
        return v

    def to_number(self, s: str) -> numbers.Number:
        """Try parse a string into a number (without using eval).

        The string can contain a number or a simple equation (3 + 4)

        Raises
        ------
        _NotNumeric
            If the string cannot be parsed as a number.
        """
        val = self.to_scaled_units_container(s)
        if len(val):
            raise NotNumeric(s)
        return val.scale


@dataclass(frozen=True)
class Equality(fp.ParsedStatement):
    """An equality statement contains a left and right hand separated
    by and equal (=) sign.

        lhs = rhs

    lhs and rhs are space stripped.
    """

    lhs: str
    rhs: str

    @classmethod
    def from_string(cls, s: str, config: Config) -> fp.FromString[Equality]:
        if "=" not in s:
            return None
        parts = [p.strip() for p in s.split("=")]
        if len(parts) != 2:
            return errors.DefinitionSyntaxError(
                f"Exactly two terms expected, not {len(parts)} (`{s}`)"
            )
        return cls(*parts)


@dataclass(frozen=True)
class Comment(fp.ParsedStatement):
    """Comments start with a # character.

        # This is a comment.
        ## This is also a comment.

    Captured value does not include the leading # character and space stripped.
    """

    comment: str

    @classmethod
    def from_string(cls, s: str, config: Config) -> fp.FromString[fp.ParsedStatement]:
        if not s.startswith("#"):
            return None
        return cls(s[1:].strip())


@dataclass(frozen=True)
class EndDirectiveBlock(fp.ParsedStatement):
    """An EndDirectiveBlock is simply an "@end" statement."""

    @classmethod
    def from_string(cls, s: str, config: Config) -> fp.FromString[EndDirectiveBlock]:
        if s == "@end":
            return cls()
        return None


@dataclass(frozen=True)
class DirectiveBlock(fp.Block):
    """Directive blocks have beginning statement starting with a @ character.
    and ending with a "@end" (captured using a EndDirectiveBlock).

    Subclass this class for convenience.
    """

    closing: EndDirectiveBlock


class NotNumeric(Exception):
    """Internal exception. Do not expose outside Pint"""

    def __init__(self, value):
        self.value = value


def is_dim(name: str) -> bool:
    return name[0] == "[" and name[-1] == "]"


def check_dim(name: str) -> ty.Union[errors.DefinitionSyntaxError, str]:
    name = name.strip()
    if not is_dim(name):
        raise errors.DefinitionSyntaxError(
            f"Dimension definition `{name}` must be enclosed by []."
        )

    if not str.isidentifier(name[1:-1]):
        raise errors.DefinitionSyntaxError(
            f"`{name[1:-1]}` is not a valid dimension name (must follow Python identifier rules)."
        )

    return name
