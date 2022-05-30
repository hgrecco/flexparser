from flexparser import flexparser as fp
from flexparser.testsuite.common import Comment, EqualFloat, MyParser


def test_consume():
    myparser = MyParser(None)

    lines = "# hola\nx=1.0".split("\n")
    si = fp.SequenceIterator.from_lines(lines)
    pf = myparser.consume(si)
    assert isinstance(pf.opening, fp.BOS)
    assert isinstance(pf.closing, fp.EOS)
    body = tuple(pf.body)
    assert len(body) == 2
    assert body == (
        Comment("# hola").set_line_col(0, 0),
        EqualFloat("x", 1.0).set_line_col(1, 0),
    )
    assert tuple(pf) == (pf.opening, *body, pf.closing)
    assert not pf.has_errors


def test_parse(tmp_path):
    content = "# hola\nx=1.0"
    tmp_file = tmp_path / "bla.txt"
    tmp_file.write_text(content)
    myparser = MyParser(None)

    psf = myparser.parse(tmp_file)
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
