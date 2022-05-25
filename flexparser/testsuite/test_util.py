
import typing
import re

import flexparser.flexparser as fp


def test_yield_types():
    class X:
        pass

    assert tuple(fp._yield_types(float)) == (float, )
    assert tuple(fp._yield_types(X)) == (X, )
    assert tuple(fp._yield_types(X())) == ()


def test_yield_types_container():
    class X:
        pass

    o = typing.Tuple[float, X]
    assert tuple(fp._yield_types(o)) == (float, X)

    o = typing.Tuple[float, ...]
    assert tuple(fp._yield_types(o)) == (float, )

    o = typing.Tuple[typing.Union[float, X], ...]
    assert tuple(fp._yield_types(o)) == (float, X)


def test_yield_types_union():
    class X:
        pass

    o = typing.Union[float, X]
    assert tuple(fp._yield_types(o)) == (float, X)


def test_yield_types_list():
    o = typing.List[float]
    assert tuple(fp._yield_types(o)) == (float, )


def test_is_empty_pattern():
    assert fp.is_empty_pattern("")
    assert fp.is_empty_pattern(re.compile(""))
    assert not fp.is_empty_pattern("!")
    assert not fp.is_empty_pattern(re.compile("!"))


def test_isplit():
    assert tuple(fp.isplit("", "spam!is#ham")) == ((0, "spam!is#ham", None), )
    assert tuple(fp.isplit("#", "spamis#ham")) == ((0, "spamis", "#"), (7, "ham", None))
    assert tuple(fp.isplit("!|#", "spam!is#ham")) == ((0, "spam", "!"), (5, "is", "#"), (8, "ham", None))
    assert tuple(fp.isplit("#", "#spamisham")) == ((0, "", "#"), (1, "spamisham", None), )


def test_isplit_mode():
    delimiters = {
        "!": (fp.DelimiterMode.SKIP, False),
        "#": (fp.DelimiterMode.SKIP, False)
    }
    assert tuple(fp.isplit_mode(delimiters, "spam!is#ham")) == ((0, "spam"), (5, "is"), (8, "ham"))
    assert tuple(fp.isplit_mode(delimiters, "#spam!is#ham")) == ((1, "spam"), (6, "is"), (9, "ham"))

    delimiters = {
        "!": (fp.DelimiterMode.WITH_NEXT, False),
        "#": (fp.DelimiterMode.WITH_NEXT, False)
    }
    assert tuple(fp.isplit_mode(delimiters, "spam!is#ham")) == ((0, "spam"), (4, "!is"), (7, "#ham"))

    delimiters = {
        "!": (fp.DelimiterMode.WITH_PREVIOUS, False),
        "#": (fp.DelimiterMode.WITH_PREVIOUS, False)
    }
    assert tuple(fp.isplit_mode(delimiters, "spam!is#ham")) == ((0, "spam!"), (5, "is#"), (8, "ham"))


def test_isplit_mode_break():
    delimiters = {
        "!": (fp.DelimiterMode.SKIP, True),
        "#": (fp.DelimiterMode.SKIP, True)
    }
    assert tuple(fp.isplit_mode(delimiters, "spam!is#ham")) == ((0, "spam"), (5, "is#ham"))

    delimiters = {
        "!": (fp.DelimiterMode.WITH_NEXT, True),
        "#": (fp.DelimiterMode.WITH_NEXT, True)
    }
    assert tuple(fp.isplit_mode(delimiters, "spam!is#ham")) == ((0, "spam"), (4, "!is#ham"))

    delimiters = {
        "!": (fp.DelimiterMode.WITH_PREVIOUS, True),
        "#": (fp.DelimiterMode.WITH_PREVIOUS, True)
    }
    assert tuple(fp.isplit_mode(delimiters, "spam!is#ham")) == ((0, "spam!"), (5, "is#ham"))

