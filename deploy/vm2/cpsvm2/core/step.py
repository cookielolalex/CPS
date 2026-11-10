"""Step objects: the pure instructions core/ returns and vio/ carries out (spec §1.3). vio/ may import only this module
from core/. Every field is plain data (str, int, bool, None, tuple, dict, list); a Step decides nothing further.

Conventions shared by the builders of cli.py, worker.py and vio/:
- PrintBlock.do is (ACTION, args): ACTION is one of the §6.4 terminal actions RUN, OPEN_CONVERSATION,
  AWAIT_CONVERSATION, CONTINUE_CONVERSATION, END_CONVERSATION, EXPORT_TRANSCRIPT, WAIT, STOP; args is a dict of the
  action's key=value arguments in print order. Two more ACTIONs name an ATTEST line the glue renders with `--at`:
  ATTEST_FOUND {'names': [...]} (or {'list': True} for a LIST answer), and the Ask step (ATTEST ... answer). `--at` is never in a Step: vio computes it (names.at_string).
  uploads: ((abs_path, folder, name), ...); finds: ((folder, 'NAME'|'PREFIX', value), ...);
  lists: ((folder, prefix, newest_k), ...); downloads: ((folder, drive_id, abs_path), ...).
  mark: a §2.3 mark key that vio writes durably into STATE.marks BEFORE printing the block, or None.
- Ask.keys is {key: PATTERN} (§6.3/§6.5, insertion order = print order); Ask.context is a dict naming what the answer
  is for: context['action'] in OPERATOR, OPENED, AI, IDLE, NOTIFY_OWNER, ASK_USER, DELIVER_COPY, DELIVER_USER,
  DELIVER_SENT, RESTORE_ROLE, LIST_SHOWS_NONE; plus 'window' {key: [lo_utc, hi_utc]} and the ids the glue needs.
- Commit.entry is an entry draft {'kind': K, 'body': dict or None, ...}; body None means "build the body from I/O as
  the spec section for K says" (GENESIS §7.12, CLEAR §13.5); a partial body names the values core decided and the glue
  adds the I/O facts listed in the docstring of the function that returned it.
- Halt(code, commit): commit True = a committed HALT entry (§13.3); False = a local sticky STOP (§13.2).
- Stop(code, handback): handback 'C' or 'B' (§6.4), or None for `STOP IDLE`.
- Reupload(names, entry_seq): re-upload these parts of entry `entry_seq` from its own members through the setup-file
  loop (§8.5 C3, C4; not in §1.3's list, added for those two rows).
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PrintBlock:
    state_code: str
    uploads: tuple = ()
    finds: tuple = ()
    lists: tuple = ()
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
class Evict:
    run: str


@dataclass(frozen=True)
class Wait:
    seconds: int


@dataclass(frozen=True)
class Reupload:
    names: tuple
    entry_seq: int
