[![Latest Version](https://img.shields.io/pypi/v/flexparser.svg)](https://pypi.python.org/pypi/flexparser)
[![License](https://img.shields.io/pypi/l/flexparser.svg)](https://pypi.python.org/pypi/flexparser)
[![Python Versions](https://img.shields.io/pypi/pyversions/flexparser.svg)](https://pypi.python.org/pypi/flexparser)
[![CI](https://github.com/hgrecco/flexparser/workflows/CI/badge.svg)](https://github.com/hgrecco/flexparser/actions?query=workflow%3ACI)
[![Coverage](https://coveralls.io/repos/github/hgrecco/flexparser/badge.svg?branch=main)](https://coveralls.io/github/hgrecco/flexparser?branch=main)

# flexparser

Why write another parser? I have asked myself the same question while working on this project. It is clear that there are excellent parsers out there, but I wanted to experiment with another way of writing them.

The idea is quite simple. You write a class for every type of content (called here `ParsedStatement`) you need to parse. Each class should have a `from_string` constructor. We used the `typing` module extensively to make the output structure easy to use and less error-prone.

For example:

```python
from dataclasses import dataclass
import flexparser as fp


@dataclass(frozen=True)
class Assigment(fp.ParsedStatement):
    """Parses the following `this <- other`"""

    lhs: str
    rhs: str

    @classmethod
    def from_string(cls, s):
        lhs, rhs = s.split("<-")
        return cls(lhs.strip(), rhs.strip())
```

(Using a frozen dataclass is not necessary but is convenient. Being a dataclass, you get `__init__`, `__str__`, `__repr__`, etc. for free. Being frozen, sort of immutable, makes them easier to reason around.)

In certain cases, you might want to signal the parser that this class is not appropriate to parse the statement.

```python
@dataclass(frozen=True)
class Assigment(fp.ParsedStatement):
    """Parses the following `this <- other`"""

    lhs: str
    rhs: str

    @classmethod
    def from_string(cls, s):
        if "<-" not in s:
            return None  # This means: I do not know how to parse it
        lhs, rhs = s.split("<-")
        return cls(lhs.strip(), rhs.strip())
```

You might also want to indicate that this is the right `ParsedStatement` but something is not right:

```python
@dataclass(frozen=True)
class InvalidIdentifier(fp.ParsingError):
    value: str


@dataclass(frozen=True)
class Assigment(fp.ParsedStatement):
    """Parses the following `this <- other`"""

    lhs: str
    rhs: str

    @classmethod
    def from_string(cls, s):
        if "<-" not in s:
            return None
        lhs, rhs = (p.strip() for p in s.split("<-"))
        if not str.isidentifier(lhs):
            return InvalidIdentifier(lhs)
        return cls(lhs, rhs)
```

Put this into `source.txt`:

```text
one <- other
2two <- new
three <- newvalue
one == three
```

and then run the following code:

```python
parsed = fp.parse("source.txt", Assigment)
for el in parsed.iter_statements():
    print(repr(el))
```

will produce the following output:

```text
BOF(start_line=0, ...)
Assigment(start_line=1, ..., lhs='one', rhs='other')
InvalidIdentifier(start_line=2, ..., value='2two')
Assigment(start_line=3, ..., lhs='three', rhs='newvalue')
UnknownStatement(start_line=4, ..., raw='one == three')
EOS(start_line=5, ...)
```

Now let's say we want to support equality comparison:

```python
@dataclass(frozen=True)
class EqualityComparison(fp.ParsedStatement):
    """Parses the following `this == other`"""

    lhs: str
    rhs: str

    @classmethod
    def from_string(cls, s):
        if "==" not in s:
            return None
        lhs, rhs = (p.strip() for p in s.split("=="))
        return cls(lhs, rhs)


parsed = fp.parse("source.txt", (Assigment, EqualityComparison))
for el in parsed.iter_statements():
    print(repr(el))
```

and run it again:

```text
BOF(start_line=0, ...)
Assigment(start_line=1, ..., lhs='one', rhs='other')
InvalidIdentifier(start_line=2, ..., value='2two')
Assigment(start_line=3, ..., lhs='three', rhs='newvalue')
EqualityComparison(start_line=4, ..., lhs='one', rhs='three')
EOS(start_line=5, ...)
```

For multiple source files, **flexparser** provides the `IncludeStatement` base class:

```python
@dataclass(frozen=True)
class Include(fp.IncludeStatement):
    """A naive implementation of #include "file" """

    value: str

    @classmethod
    def from_string(cls, s):
        if s.startwith("#include "):
            return None
        value = s[len("#include ") :].strip().strip('"')
        return cls(value)

    @property
    def target(self):
        return self.value
```

This project was started as part of [Pint](https://github.com/hgrecco/pint), the Python units package.

See [AUTHORS](https://github.com/hgrecco/flexparser/blob/main/AUTHORS) for a list of maintainers.

To review an ordered list of notable changes for each version, see [CHANGES](https://github.com/hgrecco/flexparser/blob/main/CHANGES).
