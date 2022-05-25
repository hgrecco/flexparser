import hashlib
import pickle

import pytest

import flexparser.flexparser as fp

_TEST = [
        "testing",
        "# this is a comment",
        "  # this is also a comment",
        "123",
        "456 # this is a comment",
    ]


def test_base_iterator():
    bi = fp.BaseIterator(iter(("spam", "ham")))
    assert bi.peek() == "spam"
    assert next(bi) == "spam"
    assert bi.peek() == "ham"
    assert next(bi) == "ham"
    with pytest.raises(StopIteration):
        bi.peek()
    with pytest.raises(StopIteration):
        next(bi)


def test_statement_iterator_default():
    si = fp.StatementIterator.from_line("spam")
    assert si.peek() == (0, "spam")
    assert tuple(si) == ((0, "spam"), )

    with pytest.raises(Exception):
        fp.StatementIterator.from_line("spam").delimiter_pattern()


def test_statement_iterator_subclass():
    class S1a(fp.StatementIterator):
        _strip_spaces = False
        _delimiters = ("#", "!")

    S1b = fp.StatementIterator.subclass_with(strip_spaces=False, delimiters=("#", "!"))
    assert S1a is not S1b
    assert S1a._strip_spaces == S1b._strip_spaces
    assert S1b._delimiters == S1b._delimiters


def test_statement_iterator_strip_spaces():
    NewStatementIterator = fp.StatementIterator.subclass_with(strip_spaces=True)

    assert tuple(NewStatementIterator.from_line("spam ")) == ((0, "spam"), )
    assert tuple(NewStatementIterator.from_line(" spam")) == ((0, "spam"), )
    assert tuple(NewStatementIterator.from_line(" spam ")) == ((0, "spam"), )

    NewStatementIterator = fp.StatementIterator.subclass_with(strip_spaces=False)

    assert tuple(NewStatementIterator.from_line("spam ")) == ((0, "spam "), )
    assert tuple(NewStatementIterator.from_line(" spam")) == ((0, " spam"), )
    assert tuple(NewStatementIterator.from_line(" spam ")) == ((0, " spam "), )

    dlm = {
        "#": (fp.DelimiterMode.SKIP, False),
    }
    NewStatementIterator = fp.StatementIterator.subclass_with(strip_spaces=False, delimiters=dlm)

    assert tuple(NewStatementIterator.from_line("spam# ham")) == ((0, "spam"), (5, " ham"))
    assert tuple(NewStatementIterator.from_line("spam #ham")) == ((0, "spam "), (6, "ham"))


def test_statement_iterator_single_splitter():
    dlm = {
        "#": (fp.DelimiterMode.SKIP, False),
    }
    NewStatementIterator = fp.StatementIterator.subclass_with(delimiters=dlm)

    assert tuple(NewStatementIterator.from_line("spam")) == ((0, "spam"),)
    assert tuple(NewStatementIterator.from_line("spam#ham")) == ((0, "spam"), (5, "ham"))


def test_statement_iterator_multiple_splitter():
    dlm = {
        "#": (fp.DelimiterMode.SKIP, False),
        "!": (fp.DelimiterMode.SKIP, False),
    }
    NewStatementIterator = fp.StatementIterator.subclass_with(delimiters=dlm)

    assert tuple(NewStatementIterator.from_line("spam")) == ((0, "spam"),)
    assert tuple(NewStatementIterator.from_line("spam#ham!cheese")) == ((0, "spam"), (5, "ham"), (9, "cheese"))
    assert tuple(NewStatementIterator.from_line("spam!ham#cheese")) == ((0, "spam"), (5, "ham"), (9, "cheese"))


def test_sequence_iterator():
    si = fp.SequenceIterator.from_lines("spam \n ham".split("\n"))
    assert si.peek() == (0, 0, "spam")
    assert tuple(si) == ((0, 0, "spam"), (1, 0, "ham"))


def test_hash_sequence_iterator():
    content = "spam \n ham"
    si = fp.SequenceIterator.from_lines(content.split("\n"))
    hsi = fp.HashSequenceIterator(si)
    out = ((0, 0, "spam"), (1, 0, "ham"))
    assert tuple(hsi) == ((0, 0, "spam"), (1, 0, "ham"))
    hasher = hashlib.sha1()
    for o in out:
        hasher.update(pickle.dumps(o))
    assert hsi.hexdigest() == hasher.hexdigest()
