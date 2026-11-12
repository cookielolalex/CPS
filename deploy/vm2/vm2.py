#!/usr/bin/env python3
"""cps-vm-helper.v2.1 entry point (spec §1.3): python3 -I -B deploy/vm2/vm2.py <go|found|answer|audit|assemble|
score_check> [args]. The Dot runs it through BASE/vm.sh; audit, assemble and score_check run on the maintainer's machine."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main(argv):
    if argv and argv[0] in ('audit', 'assemble', 'score_check'):
        import importlib
        return importlib.import_module('cpsvm2.maint.' + argv[0]).main(argv[1:])
    from cpsvm2 import cli
    return cli.main(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
