import hashlib
import typing

import flexparser.flexparser as fp


def test_yield_types():
    class X:
        pass

    assert tuple(fp._yield_types(float)) == (float,)
    assert tuple(fp._yield_types(X)) == (X,)
    assert tuple(fp._yield_types(X())) == ()


def test_yield_types_container():
    class X:
        pass

    o = typing.Tuple[float, X]
    assert tuple(fp._yield_types(o)) == (float, X)

    o = typing.Tuple[float, ...]
    assert tuple(fp._yield_types(o)) == (float,)

    o = typing.Tuple[typing.Union[float, X], ...]
    assert tuple(fp._yield_types(o)) == (float, X)


def test_yield_types_union():
    class X:
        pass

    o = typing.Union[float, X]
    assert tuple(fp._yield_types(o)) == (float, X)


def test_yield_types_list():
    o = typing.List[float]
    assert tuple(fp._yield_types(o)) == (float,)


def test_hash_object():
    content = b"spam \n ham"
    hasher = hashlib.sha1

    ho = fp.Hash.from_bytes(hashlib.sha1, content)
    hd = hasher(content).hexdigest()
    assert ho.algorithm_name == "sha1"
    assert ho.hexdigest == hd
    assert ho != hd
    assert ho != fp.Hash.from_bytes(hashlib.md5, content)
    assert ho == fp.Hash.from_bytes(hashlib.sha1, content)
