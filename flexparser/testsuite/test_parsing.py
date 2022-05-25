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
    def from_string(cls, s: str, config):
        if s == "@begin":
            return cls()
        return None


@dataclass(frozen=True)
class Close(fp.ParsedStatement):

    @classmethod
    def from_string(cls, s: str, config):
        if s == "@end":
            return cls()
        return None


@dataclass(frozen=True)
class Comment(fp.ParsedStatement):

    s: str

    @classmethod
    def from_string(cls, s: str, config):
        if s.startswith("#"):
            return cls(s)
        return None


@dataclass(frozen=True)
class EqualFloat(fp.ParsedStatement):

    a: str
    b: float

    @classmethod
    def from_string(cls, s: str, config) -> fp.FromString['EqualFloat']:
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


def test_parse_equal_float():
    assert EqualFloat.from_string("a = 3.1", None) == EqualFloat("a", 3.1)
    assert EqualFloat.from_string("a", None) is None

    assert EqualFloat.from_string("%a = 3.1", None) == NotAValidIdentifier("%a")
    assert EqualFloat.from_string("a = 3f1", None) == CannotParseToFloat("3f1")


def test_consume_equal_float():
    f = lambda s: fp.SequenceIterator(iter(((3, 4, s), )))
    assert EqualFloat.consume(f("a = 3.1"), None) == EqualFloat("a", 3.1).set_line_col(3, 4)
    assert EqualFloat.consume(f("a"), None) is None

    assert EqualFloat.consume(f("%a = 3.1"), None) == NotAValidIdentifier("%a").set_line_col(3, 4)
    assert EqualFloat.consume(f("a = 3f1"), None) == CannotParseToFloat("3f1").set_line_col(3, 4)


def test_stream_block():
    lines = "# hola\nx=1.0".split("\n")
    si = fp.SequenceIterator.from_lines(lines)

    mb = MyRoot.consume(si, None)
    assert isinstance(mb.opening, fp.BOS)
    assert isinstance(mb.closing, fp.EOS)
    body = tuple(mb.body)
    assert len(body) == 2
    assert body == (
        Comment("# hola").set_line_col(0, 0),
        EqualFloat("x", 1.0).set_line_col(1, 0),
    )
    assert tuple(mb) == (mb.opening, *body, mb.closing)
    assert not mb.has_errors


def test_stream_block_error():
    lines = "# hola\nx=1f0".split("\n")
    si = fp.SequenceIterator.from_lines(lines)

    mb = MyRoot.consume(si, None)
    assert isinstance(mb.opening, fp.BOS)
    assert isinstance(mb.closing, fp.EOS)
    body = tuple(mb.body)
    assert len(body) == 2
    assert body == (
        Comment("# hola").set_line_col(0, 0),
        CannotParseToFloat("1f0").set_line_col(1, 0),
    )
    assert tuple(mb) == (mb.opening, *body, mb.closing)
    assert mb.has_errors
    assert mb.errors == (CannotParseToFloat("1f0").set_line_col(1, 0), )


def test_block():
    lines = "@begin\n# hola\nx=1.0\n@end".split("\n")
    si = fp.SequenceIterator.from_lines(lines)

    mb = MyBlock.consume(si, None)
    assert mb.opening == Open().set_line_col(0, 0)
    assert mb.closing == Close().set_line_col(3, 0)
    body = tuple(mb.body)
    assert len(body) == 2
    assert mb.body == (
        Comment("# hola").set_line_col(1, 0),
        EqualFloat("x", 1.).set_line_col(2, 0),
    )

    assert tuple(mb) == (mb.opening, *mb.body, mb.closing)
    assert not mb.has_errors