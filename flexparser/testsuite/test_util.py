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

    o = tuple[float, X]
    assert tuple(fp._yield_types(o)) == (float, X)

    o = tuple[float, ...]
    assert tuple(fp._yield_types(o)) == (float,)

    o = tuple[typing.Union[float, X], ...]
    assert tuple(fp._yield_types(o)) == (float, X)


def test_yield_types_union():
    class X:
        pass

    o = typing.Union[float, X]
    assert tuple(fp._yield_types(o)) == (float, X)


def test_yield_types_list():
    o = list[float]
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
