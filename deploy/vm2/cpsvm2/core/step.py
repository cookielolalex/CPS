"""Step objects (spec §1.3): plain-data instructions core/ returns and vio/ carries out; vio/ imports only this
module from core/. PrintBlock.do is (ACTION, args) with ACTION a §6.4 action or ATTEST_FOUND; `--at` is never in a
Step. Ask.keys is {key: PATTERN} in print order, Ask.context names what the answer is for (context['action']).
Commit.entry is a draft {'kind', 'body'} the glue completes. Halt(code, commit): commit True is a committed HALT
(§13.3), False a local sticky STOP (§13.2). Stop(code, handback). Reupload(names, entry_seq) (§8.5 C3, C4)."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PrintBlock:
    state_code: str
    uploads: tuple = ()
    finds: tuple = ()
    downloads: tuple = ()
    do: tuple = ('RUN', {})
    mark: object = None


@dataclass(frozen=True)
class RunChain:
    run: object                 # RUN_KEY, or the key of the run the chain creates
    first: str                  # first runner sub-command (§7.4)
    info: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Place:
    plan: dict


@dataclass(frozen=True)
class Ask:
    keys: dict
    context: dict


@dataclass(frozen=True)
class Stop:
    code: str
    handback: object = 'C'


@dataclass(frozen=True)
class Halt:
    code: str
    commit: bool = True


@dataclass(frozen=True)
class Commit:
    entry: dict
    parts: tuple = ()


@dataclass(frozen=True)
class Reupload:
    names: tuple
    entry_seq: int
