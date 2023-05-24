from __future__ import annotations

import pathlib
import typing as ty
from dataclasses import dataclass

from pint_parser import common, context, defaults, group, plain, system

from flexparser import flexparser as fp


@dataclass(frozen=True)
class ImportDefinition(fp.IncludeStatement):
    value: str

    @property
    def target(self):
        return self.value

    @classmethod
    def from_string(cls, s: str) -> fp.FromString[ImportDefinition]:
        if s.startswith("@import"):
            return ImportDefinition(s[len("@import") :].strip())
        return None


@dataclass(frozen=True)
class EntryBlock(fp.RootBlock):
    body: fp.Multi[
        ty.Union[
            common.Comment,
            ImportDefinition,
            defaults.DefaultsDefinition,
            context.ContextDefinition,
            group.GroupDefinition,
            system.SystemDefinition,
            plain.DimensionDefinition,
            plain.PrefixDefinition,
            plain.UnitDefinition,
        ]
    ]


cfg = common.Config()
p = pathlib.Path("files/default_en.txt")

parsed = fp.parse(
    p,
    EntryBlock,
    cfg,
    delimiters={
        "#": (
            fp.DelimiterInclude.SPLIT_BEFORE,
            fp.DelimiterAction.CAPTURE_NEXT_TIL_EOL,
        ),
        **fp.SPLIT_EOL,
    },
)


def pprint(objs, indent=1):
    TT = "  "
    print(TT * (indent - 1), objs.opening)
    for p in objs.body:
        if isinstance(p, fp.Block):
            pprint(p, indent + 1)
        else:
            print(TT * indent, p)
    print(TT * (indent - 1), objs.closing)


print("Keys")
print("----")
for k in parsed.keys():
    print(k)

print("\n\n----\n\n")
for x in parsed.iter_blocks():
    print(x)

print("\n")
print("Errors")
print("------")
for p in parsed.errors():
    print(p)
