from __future__ import annotations

import re
import typing as ty
from dataclasses import dataclass

import flexparser.flexparser as fp

from . import common, plain


@dataclass(frozen=True)
class BeginGroup(fp.ParsedStatement):
    """Being of a group directive.

    @group <name> [using <group 1>, ..., <group N>]
    """

    #: Regex to match the header parts of a definition.
    _header_re = re.compile(r"@group\s+(?P<name>\w+)\s*(using\s(?P<used_groups>.*))*")

    name: str
    using_group_names: ty.Tuple[str, ...]

    @classmethod
    def from_string(cls, s: str) -> fp.FromString[BeginGroup]:
        if not s.startswith("@group"):
            return None

        r = cls._header_re.search(s)

        if r is None:
            raise ValueError("Invalid Group header syntax: '%s'" % s)

        name = r.groupdict()["name"].strip()
        groups = r.groupdict()["used_groups"]
        if groups:
            parent_group_names = tuple(a.strip() for a in groups.split(","))
        else:
            parent_group_names = ()

        return cls(name, parent_group_names)


@dataclass(frozen=True)
class GroupDefinition(common.DirectiveBlock):
    """Definition of a group.

        @group <name> [using <group 1>, ..., <group N>]
            <definition 1>
            ...
            <definition N>
        @end

    See UnitDefinition and Comment for more parsing related information.

    Example::

        @group AvoirdupoisUS using Avoirdupois
            US_hundredweight = hundredweight = US_cwt
            US_ton = ton
            US_force_ton = force_ton = _ = US_ton_force
        @end

    """

    opening: fp.Single[BeginGroup]
    body: fp.Multi[
        ty.Tuple[
            plain.UnitDefinition,
            common.Comment,
        ]
    ]

    @property
    def unit_names(self) -> ty.Tuple[str, ...]:
        return tuple(
            el.name for el in self.body if isinstance(el, plain.UnitDefinition)
        )
