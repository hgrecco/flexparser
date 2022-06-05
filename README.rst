.. image:: https://img.shields.io/pypi/v/flexparser.svg
    :target: https://pypi.python.org/pypi/flexparser
    :alt: Latest Version

.. image:: https://img.shields.io/pypi/l/flexparser.svg
    :target: https://pypi.python.org/pypi/flexparser
    :alt: License

.. image:: https://img.shields.io/pypi/pyversions/flexparser.svg
    :target: https://pypi.python.org/pypi/flexparser
    :alt: Python Versions

.. image:: https://github.com/hgrecco/flexparser/workflows/CI/badge.svg
    :target: https://github.com/hgrecco/flexparser/actions?query=workflow%3ACI
    :alt: CI

.. image:: https://github.com/hgrecco/flexparser/workflows/Lint/badge.svg
    :target: https://github.com/hgrecco/flexparser/actions?query=workflow%3ALint
    :alt: LINTER

.. image:: https://coveralls.io/repos/github/hgrecco/flexparser/badge.svg?branch=main
    :target: https://coveralls.io/github/hgrecco/flexparser?branch=main
    :alt: Coverage


flexparser
==========

Why writing another parser? I have asked myself the same question while
working in this project. It is clear that there are excellent parsers out
there but I wanted to experiment with another way of writing them.

The idea is quite simple. You write a class for every type of content
(called here ``ParsedStatement``) you need to parse. Each class should
have a ``from_string`` constructor. We used extensively the ``typing``
module to make the output structure easy to use and less error prone.

For example:

.. code-block:: python

    from dataclasses import dataclass

    import flexparser as fp

    @dataclass(frozen=True)
    class Assigment(fp.ParsedStatement):
        """Parses the following `this <- other`
        """

        lhs: str
        rhs: str

        @classmethod
        def from_string(cls, s):
            lhs, rhs = s.split("<-")
            return cls(lhs.strip(), rhs.strip())

(using a frozen dataclass is not necessary but I found it very useful)

In certain cases you might want to signal the parser
that his class is not appropriate to parse the statement.

.. code-block:: python

    @dataclass(frozen=True)
    class Assigment(fp.ParsedStatement):
        """Parses the following `this <- other`
        """

        lhs: str
        rhs: str

        @classmethod
        def from_string(cls, s):
            if "<-" not in s:
                # This means: I do not know how to parse it
                # try with another ParsedStatement class.
                return None
            lhs, rhs = s.split("<-")
            return cls(lhs.strip(), rhs.strip())


You might also want to indicate that this is the right ``ParsedStatement``
but something is not right:

.. code-block:: python

    @dataclass(frozen=True)
    class InvalidIdentifier(fp.ParsingError):
        value: str


    @dataclass(frozen=True)
    class Assigment(fp.ParsedStatement):
        """Parses the following `this <- other`
        """

        lhs: str
        rhs: str

        @classmethod
        def from_string(cls, s):
            if "<-" not in s:
                # This means: I do not know how to parse it
                # try with another ParsedStatement class.
                return None
            lhs, rhs = (p.strip() for p in s.split("<-"))

            if not str.isidentifier(lhs):
                return InvalidIdentifier(lhs)

            return cls(lhs, rhs)


Put this into ``source.txt``

.. code-block:: text

    one <- other
    2two <- new
    three <- newvalue
    one == three

and then run the following code:

.. code-block:: python

    parsed = fp.parse("source.txt", Assigment)
    for el in parsed.iter_statements():
        print(repr(el))

will produce the following output:

.. code-block:: text

    BOS(lineno=0, colno=0)
    Assigment(lineno=1, colno=0, lhs='one', rhs='other')
    InvalidIdentifier(lineno=2, colno=0, origin='', value='2two')
    Assigment(lineno=3, colno=0, lhs='three', rhs='newvalue')
    UnknownStatement(lineno=4, colno=0, origin='', statement='one == three')
    EOS(lineno=-1, colno=-1)

The result is a collection of ``ParsedStatement`` or ``ParsingError`` (flanked by
``BOS`` and ``EOS`` indicating beginning and ending of stream respectively).
Notice that there are two correctly parsed statements (``Assigment``), one
error found (``InvalidIdentifier``) and one unknown (``UnknownStatement``).

Cool, right? Just writing a ``from_string`` method that outputs a datastructure
produces a usable structure of parsed objects.

Now what? Let's say we want to support equality comparison. Simply do:

.. code-block:: python

    @dataclass(frozen=True)
    class EqualityComparison(fp.ParsedStatement):
        """Parses the following `this == other`
        """

        lhs: str
        rhs: str

        @classmethod
        def from_string(cls, s):
            if "==" not in s:
                return None
            lhs, rhs = (p.strip() for p in s.split("=="))

            return cls(lhs, rhs)

    parsed = fp.parse("source.txt", (Assigment, Equality))
    for el in parsed.iter_statements():
        print(repr(el))

and run it again:

.. code-block:: text

    BOS(lineno=0, colno=0)
    Assigment(lineno=1, colno=0, lhs='one', rhs='other')
    InvalidIdentifier(lineno=2, colno=0, origin='', value='2two')
    Assigment(lineno=3, colno=0, lhs='three', rhs='newvalue')
    EqualityComparison(lineno=4, colno=0,  lhs='one', rhs='three')
    EOS(lineno=-1, colno=-1)

You need to group certain statements together: welcome to ``Block``
This construct allows you to group

.. code-block:: python

    class Begin(fp.ParsedStatement):

        @classmethod
        def from_string(cls, s):
            if s == "begin":
                return cls()

            return None

    class End(fp.ParsedStatement):

        @classmethod
        def from_string(cls, s):
            if s == "end":
                return cls()

            return None

    AssigmentBlock = fp.Block.build(
        Begin,
        (Assigment, ),
        End,
    )

    parsed = fp.parse("source.txt", (AssigmentBlock, Equality))

Run the code:

.. code-block:: text

    BOS(lineno=0, colno=0)
    UnknownStatement(lineno=1, colno=0, origin='', statement='one <- other')
    UnknownStatement(lineno=2, colno=0, origin='', statement='2two <- new')
    UnknownStatement(lineno=3, colno=0, origin='', statement='three <- newvalue')
    Equality(lineno=4, colno=0, lhs='one', rhs='three')
    EOS(lineno=-1, colno=-1)


Notice that there are a lot of ``UnknownStatement`` now, because we instructed
the parser to only look for assignment within a block. So change your text file to:

.. code-block:: text

    begin
    one <- other
    2two <- new
    three <- newvalue
    end
    one == three

and try again:

.. code-block:: text

    BOS(lineno=0, colno=0)
    Begin(lineno=1, colno=0)
    Assigment(lineno=2, colno=0, lhs='one', rhs='other')
    InvalidIdentifier(lineno=3, colno=0, origin='', value='2two')
    Assigment(lineno=4, colno=0, lhs='three', rhs='newvalue')
    End(lineno=5, colno=0)
    Equality(lineno=6, colno=0, lhs='one', rhs='three')
    EOS(lineno=-1, colno=-1)


Until now we have used ``parsed.iter_statements`` to iterate over all parsed statements.
But let's look inside ``parsed``, an object of ``ParsedProject`` type. It is a thin wrapper
over a dictionary mapping files to parsed content. Because we have provided a single file
and this does not contain a link another, our ``parsed`` object contains a single element.
The key is something like ``(None, 'source.txt')`` indicating that the file 'source.txt'
was loaded from the root location (None). The content is a ``ParsedSourceFile`` object with
the following attributes:

- **filename**: full path of the source file
- **mtime**: modification file of the source file
- **content_hash**: sha1 hash of the pickled content
  (this is currently not the same as hashing the file)
- **config**: extra parameters that can be given to the parser (see below).

.. code-block:: text

    parse.<locals>.CustomRootBlock(
        opening=BOS(lineno=0, colno=0),
        body=(
            Block.subclass_with.<locals>.CustomBlock(
                opening=Begin(lineno=1, colno=0),
                body=(
                    Assigment(lineno=2, colno=0, lhs='one', rhs='other'),
                    InvalidIdentifier(lineno=3, colno=0, origin='', value='2two'),
                    Assigment(lineno=4, colno=0, lhs='three', rhs='newvalue')
                ),
                closing=End(lineno=5, colno=0)
              ),
            Equality(lineno=6, colno=0, lhs='one', rhs='three')
        ),
        closing=EOS(lineno=-1, colno=-1)
    )

A few things to notice:

1. We were using a block before without knowing. The ``RootBlock`` is a
   special type of Block that starts and ends automatically with the
   file.
2. ``opening``, ``body``, ``closing`` are automatically annotated with the
   possible ``ParsedStatement`` (plus `ParsingError`),
   therefore autocompletes works in most IDEs.
3. The same is true for the defined ``ParsedStatement`` (we have use
   ``dataclass`` for a reason). This makes using the actual
   result of the parsing a charm!.
4. That annoying ``subclass_with.<locals>`` is because we have built
   a class on the fly when we used ``Block.subclass_with``. You can
   get rid of it (which is actually useful for pickling) by explicit
   subclassing Block in your code (see below).


Multiple source files
---------------------

Most projects have more than one source file internally connected.
A file might refer to another that also need to be parsed (e.g. an
`#include` statement in c). **flexparser** provides the ``IncludeStatement``
base class specially for this purpose.

.. code-block:: python

    @dataclass(frozen=True)
    class Include(fp.IncludeStatement):
        """A naive implementation of #include "file"
        """

        value: str

        @classmethod
        def from_string(cls, s):
            if s.startwith("#include "):
                return None

            value = s[len("#include "):].strip().strip('"')

            return cls(value)

        @propery
        def target(self):
            return self.value

The only difference is that you need to implement a ``target`` property
that returns the file name or resource that this statement refers to.


Customizing statementization
----------------------------

statementi ... what? **flexparser** works by trying to parse each statement with
one of the known classes. So it is fair to ask what is an statement in this
context and how can you configure it to your needs. A text file is split into
non overlapping strings called **statements**. Parsing work as follows:

1. each file is split in lines.
2. each line is split into statements.
3. each statement is parsed with the first of the contextually
   available ParsedStatement or Block subclassed that returns
   a ``ParsedStatement`` or ``ParsingError``

You can customize how to split each line into statements with two arguments:

- **strip_spaces** (`bool`): indicates that leading and trailing spaces must
  be removed before attempting to parse.
  (default: True)
- **delimiters** (`dict`): indicates how each line must be subsplit.
  (default: do not divide)

An delimiter example might be ``{";": (fp.DelimiterMode.SKIP, False)}`` which
tells the statementizer (sorry) that when a ";" is found a new statement should
begin. ``DelimiterMode.SKIP`` tells that ";" should not be added to the previous
statement nor to the next. Other valid values are ``WITH_PREVIOUS`` and ``WITH_NEXT``
to append or prepend the delimiter character to the previous or next statement.
The boolean tells the statementizer (sorry again) if it should
stop split the line. If True, the rest of the line will be captured in the next
statement. This is useful with comments. For example,
``{"#": (fp.DelimiterMode.WITH_NEXT, True)}`` tells the statementizer (it is not
funny anymore) that after the first "#" it should stop splitting and capture all.
This allows

.. code-block:: text

    ## This will work as a single statement
    # This will work as a single statement #
    # This will work as # a single statement #
    a = 3 # this will produce two statements (a=3, and the rest)


Explicit Block classes
----------------------

.. code-block:: python

    class AssigmentBlock:

        opening: fp.Single[Begin]
        body: fp.Multi[Assigment]
        closing: fp.Single[End]

    class EntryBlock(fp.RootBlock):

        body: fp.Multi[typing.Union[AssigmentBlock, Equality]]

    parsed = fp.parse("source.txt", EntryBlock)


Customizing parsing
-------------------

In certain cases you might want to leave to the user some configuration
details. We have method for that!. Instead of overriding ``from_string``
override ``from_string_and_config``. The second argument is an object
that can be given to the parser, which in turn will be passed to each
``ParsedStatement`` class.

.. code-block:: python

    @dataclass(frozen=True)
    class NumericAssigment(fp.ParsedStatement):
        """Parses the following `this <- other`
        """

        lhs: str
        rhs: numbers.Number

        @classmethod
        def from_string_and_config(cls, s, config):
            if "==" not in s:
                # This means: I do not know how to parse it
                # try with another ParsedStatement class.
                return None
            lhs, rhs = s.split("==")
            return cls(lhs.strip(), config.numeric_type(rhs.strip()))

    class Config:

        numeric_type = float

    parsed = fp.parse("source.txt", NumericAssigment, Config)

----

This project was started as a part of Pint_, the python units package.

See AUTHORS_ for a list of the maintainers.

To review an ordered list of notable changes for each version of a project,
see CHANGES_

.. _`AUTHORS`: https://github.com/hgrecco/flexparser/blob/main/AUTHORS
.. _`CHANGES`: https://github.com/hgrecco/flexparser/blob/main/CHANGES
.. _`Pint`: https://github.com/hgrecco/pint
