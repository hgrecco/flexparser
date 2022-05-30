import typing
from dataclasses import dataclass

from flexparser import flexparser as fp


@dataclass(frozen=True)
class NotAValidIdentifier(fp.ParsingError):

    value: str


@dataclass(frozen=True)
class CannotParseToFloat(fp.ParsingError):

    value: str


@dataclass(frozen=True)
class Open(fp.ParsedStatement):
    @classmethod
    def from_string(cls, s: str):
        if s == "@begin":
            return cls()
        return None


@dataclass(frozen=True)
class Close(fp.ParsedStatement):
    @classmethod
    def from_string(cls, s: str):
        if s == "@end":
            return cls()
        return None


@dataclass(frozen=True)
class Comment(fp.ParsedStatement):

    s: str

    @classmethod
    def from_string(cls, s: str):
        if s.startswith("#"):
            return cls(s)
        return None


@dataclass(frozen=True)
class EqualFloat(fp.ParsedStatement):

    a: str
    b: float

    @classmethod
    def from_string(cls, s: str) -> fp.FromString["EqualFloat"]:
        if "=" not in s:
            return None

        a, b = s.split("=")
        a = a.strip()
        b = b.strip()

        if not str.isidentifier(a):
            return NotAValidIdentifier(a)

        try:
            b = float(b)
        except Exception:
            return CannotParseToFloat(b)

        return cls(a, b)


class MyBlock(fp.Block):

    opening: fp.Single[Open]
    body: fp.Multi[typing.Union[Comment, EqualFloat]]
    closing: fp.Single[Close]


class MyRoot(fp.RootBlock):

    body: fp.Multi[typing.Union[Comment, EqualFloat]]


class MyParser(fp.Parser):

    _root_block_class = MyRoot
