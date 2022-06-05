from __future__ import annotations

import typing as ty
from dataclasses import dataclass

import flexparser.flexparser as fp

from . import common


@dataclass(frozen=True)
class BeginDefaults(fp.ParsedStatement):
    """Being of a defaults directive.

    @defaults
    """

    @classmethod
    def from_string(cls, s: str) -> fp.FromString[BeginDefaults]:
        if s.strip() == "@defaults":
            return cls()
        return None


@dataclass(frozen=True)
class DefaultsDefinition(common.DirectiveBlock):
    """Directive to store values.

        @defaults
            system = mks
        @end

    See Equality and Comment for more parsing related information.
    """

    opening: fp.Single[BeginDefaults]
    body: fp.Multi[
        ty.Union[
            common.Equality,
            common.Comment,
        ]
    ]
