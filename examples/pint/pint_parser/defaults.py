from __future__ import annotations

from dataclasses import dataclass

import flexparser.flexparser as fp

from . import common


@dataclass(frozen=True)
class BeginDefaults(fp.ParsedStatement):
    """Being of a defaults directive.

    @defaults
    """

    @classmethod
    def from_string(cls, s: str) -> fp.NullableParsedResult[BeginDefaults]:
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
