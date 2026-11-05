# CPS deployment helpers

These files are for the CPS operator's VM. They contain no case data.

| File | Purpose |
|---|---|
| `setup_vm.sh` | Installs the toolchain on Debian/Ubuntu. That is Python 3.11+ in a venv (openpyxl 3.1.5, xlrd 2.0.2, lxml), Node v22, LibreOffice with `pdftoppm`, Noto CJK fonts, and Playwright Chromium. |
| `check_env.py` | Writes `ENV_REPORT.json`: tool versions and paths, the node binary's sha256, and which requirements are met. |
| `writer_route/` | A writer directory for the export tools. It holds the public writer copy (`writer004.mjs` 70d7f664…, `validate_carrier_v4.mjs`, `receipt_bytes.mjs`) and the CPS validation stub `node_modules/@oai/artifact-tool` (67134aca…). Pass `--writer-dir <repo>/deploy/writer_route/writer`. |

## Export self-test on a new VM

```bash
python3 -I -B research/export/tests/run_export_tests.py --writer-dir "$PWD/deploy/writer_route/writer" --work /tmp/cps_selftest
```

It uses invented fixtures only, and every test must pass. The export admission (`research/export/ADMISSION_WRITER_V25.json` or its successor) pins the checker's node binary by sha256. A VM's node binary becomes admitted evidence only after the maintainer records it there, and only after a fully passing self-test on that VM.
