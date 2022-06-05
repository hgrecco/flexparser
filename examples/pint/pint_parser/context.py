from __future__ import annotations

import numbers
import re
import typing as ty
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, Set, Tuple

from flexparser import flexparser as fp

from . import common, errors

if TYPE_CHECKING:
    from pint import Quantity, UnitsContainer


class ParserHelper:
    @classmethod
    def from_string(cls, s, *args):
        return s


@dataclass(frozen=True)
class _Relation:

    _varname_re = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

    src: UnitsContainer
    dst: UnitsContainer
    equation: str

    @classmethod
    def _from_string_and_context_sep(
        cls, s: str, config: common.Config, separator: str
    ) -> fp.FromString[_Relation]:
        if separator not in s:
            return None
        if ":" not in s:
            return None

        rel, eq = s.split(":")

        parts = rel.split(separator)

        try:
            src, dst = (config.to_dimension_container(s) for s in parts)
        except errors.DefinitionSyntaxError as ex:
            return ex

        return cls(src, dst, eq.strip())

    @property
    def variables(self) -> Set[str, ...]:
        """Find all variables names in the equation."""
        return set(self._varname_re.findall(self.equation))

    @property
    def transformation(self) -> Callable[..., Quantity[Any]]:
        """Return a transformation callable that uses the registry
        to parse the transformation equation.
        """
        return lambda ureg, value, **kwargs: ureg.parse_expression(
            self.equation, value=value, **kwargs
        )


@dataclass(frozen=True)
class ForwardRelation(fp.ParsedStatement, _Relation):
    """A relation connecting a dimension to another via a transformation function.

    <source dimension> -> <target dimension>: <transformation function>
    """

    @property
    def bidirectional(self):
        return False

    @classmethod
    def from_string_and_config(
        cls, s: str, config: common.Config
    ) -> fp.FromString[ForwardRelation]:
        return super()._from_string_and_context_sep(s, config, "->")


@dataclass(frozen=True)
class BidirectionalRelation(fp.ParsedStatement, _Relation):
    """A bidirectional relation connecting a dimension to another
    via a simple transformation function.

        <source dimension> <-> <target dimension>: <transformation function>

    """

    @property
    def bidirectional(self):
        return True

    @classmethod
    def from_string_and_config(
        cls, s: str, config: common.Config
    ) -> fp.FromString[BidirectionalRelation]:
        return super()._from_string_and_context_sep(s, config, "<->")


@dataclass(frozen=True)
class BeginContext(fp.ParsedStatement):
    """Being of a context directive.

    @context[(defaults)] <canonical name> [= <alias>] [= <alias>]
    """

    _header_re = re.compile(
        r"@context\s*(?P<defaults>\(.*\))?\s+(?P<name>\w+)\s*(=(?P<aliases>.*))*"
    )

    name: str
    aliases: Tuple[str, ...]
    defaults: Dict[str, numbers.Number]

    @classmethod
    def from_string_and_config(
        cls, s: str, config: common.Config
    ) -> fp.FromString[BeginContext]:
        try:
            r = cls._header_re.search(s)
            if r is None:
                return None
            name = r.groupdict()["name"].strip()
            aliases = r.groupdict()["aliases"]
            if aliases:
                aliases = tuple(a.strip() for a in r.groupdict()["aliases"].split("="))
            else:
                aliases = ()
            defaults = r.groupdict()["defaults"]
        except Exception as ex:
            return errors.DefinitionSyntaxError(
                "Could not parse the Context header", ex
            )

        if defaults:
            # TODO: Use config non_int_type
            def to_num(val):
                val = complex(val)
                if not val.imag:
                    return val.real
                return val

            txt = defaults
            try:
                defaults = (part.split("=") for part in defaults.strip("()").split(","))
                defaults = {str(k).strip(): to_num(v) for k, v in defaults}
            except (ValueError, TypeError) as exc:
                return errors.DefinitionSyntaxError(
                    f"Could not parse Context definition defaults: '{txt}'", exc
                )
        else:
            defaults = {}

        return cls(name, tuple(aliases), defaults)


@dataclass(frozen=True)
class ContextDefinition(common.DirectiveBlock):
    """Definition of a Context

        @context[(defaults)] <canonical name> [= <alias>] [= <alias>]
            # units can be redefined within the context
            <redefined unit> = <relation to another unit>

            # can establish unidirectional relationships between dimensions
            <dimension 1> -> <dimension 2>: <transformation function>

            # can establish bidirectionl relationships between dimensions
            <dimension 3> <-> <dimension 4>: <transformation function>
        @end

    See BeginContext, Equality, ForwardRelation, BidirectionalRelation and
    Comment for more parsing related information.

    Example::

        @context(n=1) spectroscopy = sp
            # n index of refraction of the medium.
            [length] <-> [frequency]: speed_of_light / n / value
            [frequency] -> [energy]: planck_constant * value
            [energy] -> [frequency]: value / planck_constant
            # allow wavenumber / kayser
            [wavenumber] <-> [length]: 1 / value
        @end
    """

    opening: fp.Single[BeginContext]
    body: fp.Multi[
        ty.Union[
            common.Comment,
            BidirectionalRelation,
            ForwardRelation,
            common.Equality,
        ]
    ]

    @property
    def variables(self) -> Set[str, ...]:
        """Return all variable names in all transformations."""
        return set.union(*(r.variables for r in self.body if isinstance(r, _Relation)))

    # TODO: some checks are missing

    # @staticmethod
    # def parse_definition(line, non_int_type) -> UnitDefinition:
    #     definition = Definition.from_string(line, non_int_type)
    #     if not isinstance(definition, UnitDefinition):
    #         raise DefinitionSyntaxError(
    #             "Expected <unit> = <converter>; got %s" % line.strip()
    #         )
    #     if definition.symbol != definition.name or definition.aliases:
    #         raise DefinitionSyntaxError(
    #             "Can't change a unit's symbol or aliases within a context"
    #         )
    #     if definition.is_base:
    #         raise DefinitionSyntaxError("Can't define plain units within a context")
    #     return definition

    # def __post_init__(self):
    #     missing_pars = self.opening.defaults.keys() - self.variables
    #     if missing_pars:
    #         raise DefinitionSyntaxError(
    #             f"Context parameters {missing_pars} not found in any equation"
    #         )
