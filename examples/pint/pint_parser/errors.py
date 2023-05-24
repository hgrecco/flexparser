from __future__ import annotations

import typing as ty
from dataclasses import dataclass

from flexparser import flexparser as fp


@dataclass(frozen=True)
class DefinitionSyntaxError(fp.ParsingError):
    msg: str
    base_exception: ty.Optional[Exception] = None


@dataclass(frozen=True)
class UnexpectedScaleInContainer(fp.ParsingError):
    msg: str
