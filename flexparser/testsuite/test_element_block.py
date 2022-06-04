import pytest

from flexparser import flexparser as fp
from flexparser.testsuite.common import (
    CannotParseToFloat,
    Close,
    Comment,
    EqualFloat,
    MyBlock,
    MyRoot,
    NotAValidIdentifier,
    Open,
)

MyBlock2 = fp.Block.subclass_with(
    opening=Open, body=(Comment, EqualFloat), closing=Close
)

MyRoot2 = fp.RootBlock.subclass_with(body=(Comment, EqualFloat))


def test_formatting():
    obj = EqualFloat.from_string("a = 3.1")
    assert obj.format_line_col == "(line: -1, col: -1)"
    obj.set_line_col(10, 3)
    assert obj.format_line_col == "(line: 10, col: 3)"
    assert str(obj) == "EqualFloat(lineno=10, colno=3, a='a', b=3.1)"

    obj = EqualFloat.from_string("%a = 3.1")
    assert obj.origin == ""
    assert obj.format_line_col == "(line: -1, col: -1)"
    obj.set_line_col(10, 3)
    assert obj.format_line_col == "(line: 10, col: 3)"

    obj1 = obj.copy_with(("pack", "nam"))
    assert obj1.origin_ == "resource (package: pack, name: nam)"

    obj2 = obj.copy_with("/util/bla.txt")
    assert obj2.origin_ == "/util/bla.txt"


def test_parse_equal_float():
    assert EqualFloat.from_string("a = 3.1") == EqualFloat("a", 3.1)
    assert EqualFloat.from_string("a") is None

    assert EqualFloat.from_string("%a = 3.1") == NotAValidIdentifier("%a")
    assert EqualFloat.from_string("a = 3f1") == CannotParseToFloat("3f1")

    obj = EqualFloat.from_string("a = 3f1")
    assert str(obj) == "CannotParseToFloat(lineno=-1, colno=-1, origin='', value='3f1')"


def test_consume_equal_float():
    f = lambda s: fp.SequenceIterator(iter(((3, 4, s),)))
    assert EqualFloat.consume(f("a = 3.1"), None) == EqualFloat("a", 3.1).set_line_col(
        3, 4
    )
    assert EqualFloat.consume(f("a"), None) is None

    assert EqualFloat.consume(f("%a = 3.1"), None) == NotAValidIdentifier(
        "%a"
    ).set_line_col(3, 4)
    assert EqualFloat.consume(f("a = 3f1"), None) == CannotParseToFloat(
        "3f1"
    ).set_line_col(3, 4)


@pytest.mark.parametrize("klass", (MyRoot, MyRoot2))
def test_stream_block(klass):
    lines = "# hola\nx=1.0".split("\n")
    si = fp.SequenceIterator.from_lines(lines)

    mb = klass.consume(si, None)
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


@pytest.mark.parametrize("klass", (MyRoot, MyRoot2))
def test_stream_block_error(klass):
    lines = "# hola\nx=1f0".split("\n")
    si = fp.SequenceIterator.from_lines(lines)

    mb = klass.consume(si, None)
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
    assert mb.errors == (CannotParseToFloat("1f0").set_line_col(1, 0),)


@pytest.mark.parametrize("klass", (MyBlock, MyBlock2))
def test_block(klass):
    lines = "@begin\n# hola\nx=1.0\n@end".split("\n")
    si = fp.SequenceIterator.from_lines(lines)

    mb = klass.consume(si, None)
    assert mb.opening == Open().set_line_col(0, 0)
    assert mb.closing == Close().set_line_col(3, 0)
    body = tuple(mb.body)
    assert len(body) == 2
    assert mb.body == (
        Comment("# hola").set_line_col(1, 0),
        EqualFloat("x", 1.0).set_line_col(2, 0),
    )

    assert tuple(mb) == (mb.opening, *mb.body, mb.closing)
    assert not mb.has_errors


@pytest.mark.parametrize("klass", (MyBlock, MyBlock2))
def test_unfinished_block(klass):
    lines = "@begin\n# hola\nx=1.0".split("\n")
    si = fp.SequenceIterator.from_lines(lines)

    mb = klass.consume(si, None)
    assert mb.opening == Open().set_line_col(0, 0)
    assert mb.closing == fp.UnexpectedEOF().set_line_col(-1, -1)
    body = tuple(mb.body)
    assert len(body) == 2
    assert mb.body == (
        Comment("# hola").set_line_col(1, 0),
        EqualFloat("x", 1.0).set_line_col(2, 0),
    )

    assert tuple(mb) == (mb.opening, *mb.body, mb.closing)
    assert mb.has_errors


def test_not_proper_statement():
    class MySt(fp.ParsedStatement):
        pass

    with pytest.raises(NotImplementedError):
        MySt.from_string("a = 1")

    with pytest.raises(NotImplementedError):
        MySt.from_string_and_config("a = 1", None)
