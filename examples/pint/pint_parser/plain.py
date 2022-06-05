from __future__ import annotations

import numbers
import typing as ty
from dataclasses import dataclass
from functools import cached_property
from typing import Callable, Optional

from flexparser import flexparser as fp

from . import common, errors
from .pintimports import Converter, UnitsContainer


@dataclass(frozen=True)
class PrefixDefinition(fp.ParsedStatement):
    """Definition of a prefix::

        <prefix>- = <value> [= <symbol>] [= <alias>] [ = <alias> ] [...]

    Example::

        deca- =  1e+1  = da- = deka-
    """

    name: str
    value: numbers.Number
    defined_symbol: Optional[str]
    aliases: ty.Tuple[str, ...]

    @classmethod
    def from_string_and_config(
        cls, s: str, config: common.Config
    ) -> fp.FromString[PrefixDefinition]:
        if "=" not in s:
            return None

        name, value, *aliases = s.split("=")

        name = name.strip()
        if not name.endswith("-"):
            return None

        aliases = tuple(alias.strip().rstrip("-") for alias in aliases)

        if aliases and aliases[0].strip() != "_":
            defined_symbol, *aliases = aliases
        else:
            defined_symbol = None

        try:
            value = config.to_number(value)
        except common.NotNumeric as ex:
            return errors.DefinitionSyntaxError(
                f"Prefix definition ('{name}') must contain only numbers, not {ex.value}"
            )

        return cls(name, value, defined_symbol, aliases)

    @property
    def symbol(self) -> str:
        return self.defined_symbol or self.name

    @property
    def has_symbol(self) -> bool:
        return bool(self.defined_symbol)

    @cached_property
    def converter(self):
        return Converter.from_arguments(scale=self.value)


@dataclass(frozen=True)
class UnitDefinition(fp.ParsedStatement):
    """Definition of a unit::

        <canonical name> = <relation to another unit or dimension> [= <symbol>] [= <alias>] [ = <alias> ] [...]

    Example::

        millennium = 1e3 * year = _ = millennia

    Parameters
    ----------
    reference : UnitsContainer
        Reference units.
    is_base : bool
        Indicates if it is a base unit.

    """

    name: str
    defined_symbol: ty.Optional[str]
    aliases: ty.Tuple[str, ...]
    converter: ty.Optional[ty.Union[Callable, Converter]]

    reference: ty.Optional[UnitsContainer]
    is_base: bool

    @classmethod
    def from_string_and_config(
        cls, s: str, config: common.Config
    ) -> fp.FromString[UnitDefinition]:
        if "=" not in s:
            return None

        name, value, *aliases = (p.strip() for p in s.split("="))

        if aliases and aliases[0].strip() == "_":
            defined_symbol, *aliases = aliases
        else:
            defined_symbol = None

        if ";" in value:
            [converter, modifiers] = value.split(";", 1)

            try:
                modifiers = dict(
                    (key.strip(), config.to_number(value))
                    for key, value in (part.split(":") for part in modifiers.split(";"))
                )
            except common.NotNumeric as ex:
                return errors.DefinitionSyntaxError(
                    f"Unit definition ('{name}') must contain only numbers in modifier, not {ex.value}"
                )

        else:
            converter = value
            modifiers = {}

        converter = config.to_scaled_units_container(converter)
        if not any(common.is_dim(key) for key in converter.keys()):
            is_base = False
        elif all(common.is_dim(key) for key in converter.keys()):
            is_base = True
            if converter.scale != 1:
                return errors.DefinitionSyntaxError(
                    "Base unit definitions cannot have a scale different to 1. "
                    f"(`{converter.scale}` found)"
                )
        else:
            return errors.DefinitionSyntaxError(
                "Cannot mix dimensions and units in the same definition. "
                "Base units must be referenced only to dimensions. "
                "Derived units must be referenced only to units."
            )

        try:
            from pint.util import UnitsContainer

            reference = UnitsContainer(converter)
            # reference = converter.to_units_container()
        except errors.DefinitionSyntaxError as ex:
            return errors.DefinitionSyntaxError(f"While defining {name}", ex)

        try:
            converter = Converter.from_arguments(scale=converter.scale, **modifiers)
        except Exception as ex:
            return errors.DefinitionSyntaxError(
                "Unable to assign a converter to the unit", ex
            )

        return cls(
            name,
            defined_symbol,
            aliases,
            converter,
            reference,
            is_base,
        )

    @property
    def is_multiplicative(self) -> bool:
        return self.converter.is_multiplicative

    @property
    def is_logarithmic(self) -> bool:
        return self.converter.is_logarithmic

    @property
    def symbol(self) -> str:
        return self.defined_symbol or self.name

    @property
    def has_symbol(self) -> bool:
        return bool(self.defined_symbol)


@dataclass(frozen=True)
class DimensionDefinition(fp.ParsedStatement):
    """Definition of a root dimension::

        [dimension name]

    Example::

        [volume]
    """

    name: str

    @property
    def is_base(self):
        return False

    @classmethod
    def from_string(cls, s: str) -> fp.FromString[DimensionDefinition]:
        s = s.strip()

        if not (s.startswith("[") and "=" not in s):
            return None

        try:
            s = common.check_dim(s)
        except errors.DefinitionSyntaxError as ex:
            return ex

        return cls(s)


@dataclass(frozen=True)
class DerivedDimensionDefinition(fp.ParsedStatement):
    """Definition of a derived dimension::

        [dimension name] = <relation to other dimensions>

    Example::

        [density] = [mass] / [volume]
    """

    name: str
    reference: UnitsContainer

    @property
    def is_base(self):
        return False

    @classmethod
    def from_string_and_config(
        cls, s: str, config: common.Config
    ) -> fp.FromString[DerivedDimensionDefinition]:
        if not (s.startswith("[") and "=" in s):
            return None

        name, value, *aliases = s.split("=")

        if not (s.startswith("[") and "=" not in s):
            return None

        try:
            name = common.check_dim(name)
        except errors.DefinitionSyntaxError as ex:
            return ex

        if aliases:
            return errors.DefinitionSyntaxError(
                "Derived dimensions cannot have aliases."
            )

        try:
            reference = config.to_dimension_container(value)
        except errors.DefinitionSyntaxError as ex:
            return errors.DefinitionSyntaxError(
                f"In {name} derived dimensions must only be referenced "
                "to dimensions.",
                ex,
            )

        return cls(name.strip(), reference)


@dataclass(frozen=True)
class AliasDefinition(fp.ParsedStatement):
    """Additional alias(es) for an already existing unit::

        @alias <canonical name or previous alias> = <alias> [ = <alias> ] [...]

    Example::

        @alias meter = my_meter
    """

    name: str
    aliases: ty.Tuple[str, ...]

    @classmethod
    def from_string(cls, s: str) -> fp.FromString[AliasDefinition]:
        if not s.startswith("@alias "):
            return None
        name, *aliases = s[len("@alias ") :].split("=")

        name = name.strip()
        if name.startswith("["):
            return errors.DefinitionSyntaxError(
                "Derived dimensions cannot have aliases."
            )
        if name.endswith("-"):
            return errors.DefinitionSyntaxError(
                "Prefixes aliases cannot be added after initial definition."
            )

        return cls(name.strip(), tuple(alias.strip() for alias in aliases))
