import pathlib

import pytest

from flexparser import flexparser as fp
from flexparser.testsuite.common import (
    Close,
    Comment,
    EqualFloat,
    MyBlock,
    MyParser,
    MyRoot,
    Open,
)


def test_locator():
    assert fp.default_locator(None, "bla.txt") == "bla.txt"

    this_file = pathlib.Path(__file__)

    with pytest.raises(ValueError):
        assert fp.default_locator(this_file, "/temp/bla.txt")
    with pytest.raises(ValueError):
        assert fp.default_locator(str(this_file), "/temp/bla.txt")

    assert fp.default_locator(this_file, "bla.txt") == this_file.parent / "bla.txt"
    assert (
        fp.default_locator(this_file.parent, "bla.txt") == this_file.parent / "bla.txt"
    )
    assert fp.default_locator(str(this_file), "bla.txt") == this_file.parent / "bla.txt"
    assert (
        fp.default_locator(str(this_file.parent), "bla.txt")
        == this_file.parent / "bla.txt"
    )

    with pytest.raises(ValueError):
        assert (
            fp.default_locator(this_file.parent, "../bla.txt")
            == this_file.parent / "bla.txt"
        )

    assert fp.default_locator(("pack", "nam"), "bla") == ("pack", "bla")


@pytest.mark.parametrize("definition", [MyRoot, (Comment, EqualFloat), MyParser])
def test_parse1(tmp_path, definition):
    content = "# hola\nx=1.0"
    tmp_file = tmp_path / "bla.txt"
    tmp_file.write_text(content)

    pp = fp.parse(tmp_file, definition)

    assert len(pp) == 1

    psf = pp[list(pp.keys())[0]]
    assert not psf.has_errors
    assert psf.config is None
    assert psf.mtime == tmp_file.stat().st_mtime
    assert psf.filename == tmp_file
    assert tuple(psf.localized_errors()) == ()
    assert psf.origin == psf.filename

    # TODO:
    # assert psf.content_hash == hashlib.sha1(content.encode("utf-8")).hexdigest()

    mb = psf.parsed_source
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

    assert tuple(pp.iter_statements()) == (
        fp.BOS().set_line_col(0, 0),
        Comment("# hola").set_line_col(0, 0),
        EqualFloat("x", 1.0).set_line_col(1, 0),
        fp.EOS().set_line_col(-1, -1),
    )


@pytest.mark.parametrize("definition", [MyRoot, EqualFloat, MyParser])
def test_parse2(tmp_path, definition):
    content = "y = 2.0\nx=1.0"
    tmp_file = tmp_path / "bla.txt"
    tmp_file.write_text(content)

    pp = fp.parse(tmp_file, definition)

    assert len(pp) == 1

    psf = pp[list(pp.keys())[0]]
    assert not psf.has_errors
    assert psf.config is None
    assert psf.mtime == tmp_file.stat().st_mtime
    assert psf.filename == tmp_file
    assert tuple(psf.localized_errors()) == ()
    assert psf.origin == psf.filename

    # TODO:
    # assert psf.content_hash == hashlib.sha1(content.encode("utf-8")).hexdigest()

    mb = psf.parsed_source
    assert isinstance(mb.opening, fp.BOS)
    assert isinstance(mb.closing, fp.EOS)
    body = tuple(mb.body)
    assert len(body) == 2
    assert body == (
        EqualFloat("y", 2.0).set_line_col(0, 0),
        EqualFloat("x", 1.0).set_line_col(1, 0),
    )
    assert tuple(mb) == (mb.opening, *body, mb.closing)
    assert not mb.has_errors

    assert tuple(pp.iter_statements()) == (
        fp.BOS().set_line_col(0, 0),
        EqualFloat("y", 2.0).set_line_col(0, 0),
        EqualFloat("x", 1.0).set_line_col(1, 0),
        fp.EOS().set_line_col(-1, -1),
    )


@pytest.mark.parametrize(
    "definition",
    [
        MyBlock,
    ],
)
def test_parse3(tmp_path, definition):
    content = "@begin\ny = 2.0\nx=1.0\n@end"
    tmp_file = tmp_path / "bla.txt"
    tmp_file.write_text(content)

    pp = fp.parse(tmp_file, definition)
    assert not pp.has_errors
    assert len(pp) == 1
    assert tuple(pp.localized_errors()) == ()

    psf = pp[list(pp.keys())[0]]
    assert not psf.has_errors
    assert psf.config is None
    assert psf.mtime == tmp_file.stat().st_mtime
    assert psf.filename == tmp_file
    assert tuple(psf.localized_errors()) == ()
    assert psf.origin == psf.filename

    # TODO:
    # assert psf.content_hash == hashlib.sha1(content.encode("utf-8")).hexdigest()

    mb = psf.parsed_source
    assert isinstance(mb.opening, fp.BOS)
    assert isinstance(mb.closing, fp.EOS)
    body = tuple(mb.body)
    assert len(body) == 1
    mb = body[0]
    assert mb.opening == Open().set_line_col(0, 0)
    assert tuple(mb.body) == (
        EqualFloat("y", 2.0).set_line_col(1, 0),
        EqualFloat("x", 1.0).set_line_col(2, 0),
    )
    assert mb.closing == Close().set_line_col(3, 0)
    assert not mb.has_errors

    assert tuple(pp.iter_statements()) == (
        fp.BOS().set_line_col(0, 0),
        Open().set_line_col(0, 0),
        EqualFloat("y", 2.0).set_line_col(1, 0),
        EqualFloat("x", 1.0).set_line_col(2, 0),
        Close().set_line_col(3, 0),
        fp.EOS().set_line_col(-1, -1),
    )
