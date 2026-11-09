# CPS deployment helpers

These files are for the CPS operator's VM. They contain no case data.

| File | Purpose |
|---|---|
| `setup_vm.sh` | Installs the toolchain on Debian/Ubuntu. That is Python 3.11+ in a venv (openpyxl 3.1.5, xlrd 2.0.2, lxml), Node v22, LibreOffice with `pdftoppm`, Noto CJK fonts, and Playwright Chromium. |
| `check_env.py` | Writes `ENV_REPORT.json`: tool versions and paths, the node binary's sha256, and which requirements are met. |
| `render_examples.py` | Renders the interview example excerpts (.xlsx) to PNG on the VM (LibreOffice, pdftoppm 120 dpi, trimmed and stacked), as the kit did. |
| `setup_vm_user.sh` | The same toolchain without root or sudo, under one prefix, every download pinned by version and sha256. See "No-root setup". |
| `lok_convert.py` | Runs `soffice --convert-to pdf` through LibreOfficeKit, in-process, without soffice's IPC socket. `setup_vm_user.sh` installs it. The `soffice` wrapper uses it only on a host where `soffice` itself cannot convert (see "PDF conversion without the IPC socket"). |
| `conda-lock-linux-64.txt`, `conda-lock-python-linux-64.txt` | Explicit conda-forge locks (`@EXPLICIT`, URL + sha256) for `setup_vm_user.sh`: poppler, fontconfig tools, zstd, unzip, git, curl; and the fallback Python 3.12. |
| `requirements-user.txt` | Hash-pinned pip requirements (`--require-hashes`) for the no-root venv. |
| `deb-lock-fonts-noble.txt`, `deb-lock-libreoffice-noble-amd64.txt`, `deb-lock-libreoffice-jammy-amd64.txt` | Ubuntu package locks (sha256, size, pool path): the Noto CJK fonts and LibreOffice 24.2.7 (24.04) with its library closure; LibreOffice 7.3.7 (22.04) for hosts with glibc 2.35–2.37. |
| `writer_route/` | A writer directory for the export tools. It holds the public writer copy (`writer004.mjs` 70d7f664…, `validate_carrier_v4.mjs`, `receipt_bytes.mjs`) and the CPS validation stub `node_modules/@oai/artifact-tool` (67134aca…). Pass `--writer-dir <repo>/deploy/writer_route/writer`. |

## Export self-test on a new VM

```bash
python3 -I -B research/export/tests/run_export_tests.py --writer-dir "$PWD/deploy/writer_route/writer" --work /tmp/cps_selftest
```

It uses invented fixtures only, and every test must pass. On a no-root VM, source `~/cps-tools/env.sh` first (next section). The export admission (`research/export/ADMISSION_WRITER_V27.json`) pins the checker's node binary by sha256. A VM's node binary becomes admitted evidence only after the maintainer records it there, and only after a fully passing self-test on that VM.

## No-root setup

Tested 2026-11-06 as an unprivileged user with no sudo, in a clean HOME, with a Node 24 first on PATH: fresh install exit 0 (173 s), re-run 7 s, `check_env.py` all met, export self-test with visual tests 579/579 (three runs, including a second prefix with the 22.04 LibreOffice lock and a conda Python). The installed node v22.23.4 (official nodejs.org build, sha256 `94efd062…9a90`) must be admitted separately after the VM's own self-test.

For a VM where the operator is an ordinary user without sudo. `setup_vm_user.sh` installs what `setup_vm.sh` installs, under one prefix (default `~/cps-tools`, or `CPS_TOOLS=/abs/dir`). It needs no root, no sudo and no `apt-get install`, and it never pipes a download into a shell. Every download is pinned by version and sha256, either in the script or in the lock files next to it, and the script also pins the lock files' own sha256. Each file is verified before it is unpacked.

```bash
cd <repo>                                   # a checkout with deploy/ and its lock files
bash deploy/setup_vm_user.sh                # idempotent: a re-run checks each part and skips what is done
source ~/cps-tools/env.sh                   # in every new shell before CPS tools
command -v node soffice pdftoppm python3    # all inside ~/cps-tools; node --version is v22.23.4
python3 deploy/check_env.py --out ENV_REPORT.json
python3 -I -B research/export/tests/run_export_tests.py --writer-dir "$PWD/deploy/writer_route/writer" --work /tmp/cps_selftest
```

What goes where:

| Part | Source (pinned) | Installed as |
|---|---|---|
| Node v22.23.4 | nodejs.org official `node-v22.23.4-linux-x64.tar.xz` (sha256 from `SHASUMS256.txt`; that file is signed by a listed Node releaser). The `.tar.gz` is used if `xz` is missing. | `~/cps-tools/node/bin/node`. Its sha256 (`94efd062…9a90`) is written to `~/cps-tools/NODE_SHA256.txt` for the maintainer's admission. |
| micromamba 2.9.0 | the conda-forge package `micromamba-2.9.0-0.tar.bz2` from conda.anaconda.org | `~/cps-tools/micromamba/bin/micromamba` (needs only glibc) |
| poppler, fontconfig tools, zstd, unzip, git, curl | `conda-lock-linux-64.txt` (micromamba checks each package's sha256) | `~/cps-tools/conda`. `pdftoppm`, `pdfinfo`, `pdftotext` and `fc-*` are linked into `~/cps-tools/bin`. git, unzip, curl and zstd are fallbacks at the end of `PATH`. |
| Python venv | the system `python3` if it is 3.11 or newer (`venv --without-pip`, so `python3-venv` is not needed); otherwise Python 3.12 from `conda-lock-python-linux-64.txt`. pip runs from its pinned wheel. | `~/cps-tools/venv`: openpyxl 3.1.5, et-xmlfile 2.0.0, xlrd 2.0.2, lxml 6.1.3, pillow 12.3.0, pip 26.2.2, from `requirements-user.txt` with `--require-hashes` |
| Noto CJK fonts | `deb-lock-fonts-noble.txt`: Ubuntu 24.04 `fonts-noto-cjk` and `fonts-noto-cjk-extra` (as in `setup_vm.sh`), DejaVu, and `fontconfig-config`'s rules. conda-forge's `font-ttf-noto-cjk` was not used: it has Sans only, as variable fonts, and fontconfig picked its KR face for `zh-tw`. | `~/cps-tools/fonts/root`. `~/cps-tools/etc/fonts/fonts.conf` (`FONTCONFIG_FILE`) reads only the prefix's fonts, so `sans-serif:lang=zh-tw` resolves to Noto Sans CJK TC. |
| LibreOffice 24.2.7 | `deb-lock-libreoffice-noble-amd64.txt`: `libreoffice-calc`, `libreoffice-core` and their library closure from Ubuntu 24.04 (195 packages, no `libc6`). conda-forge has no LibreOffice, and download.documentfoundation.org was not reachable when the lock was made. | `~/cps-tools/libreoffice/root`, extracted with `dpkg-deb -x`, so no maintainer scripts run. The script makes absolute symlinks relative, points `share/registry` at `.registry`, and uses upstream's relative paths in `fundamentalrc`/`sofficerc`. `~/cps-tools/bin/soffice` sets `LD_LIBRARY_PATH` only for LibreOffice's own processes. On a host where `soffice` cannot convert, it runs `--convert-to pdf` through `lok_convert.py` (next section). The install fails if any LibreOffice library would load from outside the bundle (glibc excepted). **Needs host glibc 2.38 or newer** (Ubuntu 24.04+, Debian 13+). On glibc 2.35–2.37 (Ubuntu 22.04, Debian 12) the script uses `deb-lock-libreoffice-jammy-amd64.txt` instead (LibreOffice 7.3.7, 197 packages); force either with `CPS_LO_LOCK=noble` or `CPS_LO_LOCK=jammy`. Below 2.35 there is no LibreOffice. |
| Playwright 1.63.0 + Chromium 1243 | npm tarballs `playwright`/`playwright-core` 1.63.0 (sha256; they match npm's sha512 integrity). Chrome for Testing 153.0.8010.12 `chrome-headless-shell-linux64.zip` and `chrome-linux64.zip` from storage.googleapis.com, with cdn.playwright.dev as a fallback that must give the same sha256. | `~/cps-tools/playwright/node_modules` and `~/cps-tools/ms-playwright` (`PLAYWRIGHT_BROWSERS_PATH`). There is no `--with-deps`: the script lists the system libraries Chromium lacks (`ldd`) and tries one headless launch. |

`env.sh` puts `~/cps-tools/venv/bin`, `~/cps-tools/node/bin` and `~/cps-tools/bin` first on `PATH`, so a Node 24 elsewhere on `PATH` is no longer used. It sets `FONTCONFIG_FILE` and `PLAYWRIGHT_BROWSERS_PATH`, and it sets `NODE_PATH` to `~/cps-tools/playwright/node_modules`, so `source_prep/screenshot_views.cjs` (via `render_views.py`) resolves `require('playwright')`. The export writer and saved QA remove every `NODE_*` variable from node's environment, so `NODE_PATH` does not reach them. `env.sh` sets no `LD_LIBRARY_PATH`.

### The host's own LibreOffice (`CPS_WITH_LIBREOFFICE=host`): the Dot's light setup

Some agent VMs already ship a LibreOffice that works in their sandbox, and lose everything else at each reset. The Dot's VM is one (Debian 13, glibc 2.41; `soffice` is the Codex runtime's LibreOfficeDev 26.8). The owner chose this light setup on 2026-11-09.

With `CPS_WITH_LIBREOFFICE=host`, the setup installs everything else as usual (pinned) and does not install LibreOffice:
- the checker's Node v22;
- the Python packages;
- the Noto CJK fonts and their `fonts.conf`;
- poppler;
- Chromium and Playwright.

Instead it uses the first `soffice` on `PATH` outside the prefix:
- **Wrappers.** It writes `~/cps-tools/bin/soffice` and `libreoffice` as wrappers that run it, with the prefix's `FONTCONFIG_FILE` when none is set.
- **Check.** It runs the same LibreOffice check: an invented workbook with Chinese text to PDF, the text extractable, Noto Sans CJK embedded, and `--version`. It records the route `host` and the path.
- **Failure.** If the check fails, the setup stops with exit 1 and keeps the evidence in `~/cps-tools/var/lo_smoke/host/`. It does not switch to another route by itself.

The runner records the LibreOffice version of every job (`external_tools`) but does not pin it. The checker's Node is pinned by sha256 as before.

**Checked on 2026-11-09:**
- **On the Dot's VM** (with `CPS_WITH_LIBREOFFICE=0`, so the Codex `soffice` was used from `PATH`):
  - setup in 73 s;
  - `check_env.py` all met;
  - export self-test 600/600 with visual tests, run on LibreOfficeDev 26.8.
- **Here, as an unprivileged user:**
  - `host` mode with the machine's LibreOffice 24.2: setup exit 0 in 72 s (cached downloads), the check passes, Chromium checks pass, `check_env.py` all met;
  - under the bind-blocking filter, the same mode fails the check with exit 1 and keeps the evidence.

### PDF conversion without the IPC socket

`soffice` starts by binding a Unix socket in `/tmp` (`OSL_PIPE_<uid>_SingleOfficeIPC_<hash>`), so that a second start can pass its arguments to the first. Some agent sandboxes refuse `bind()` for every process. LibreOffice then exits 1 at once, prints nothing and writes no file, while `soffice --version` still works. That happened on the Dot's VM on 2026-11-09 (Debian 13, glibc 2.41), and it was reproduced here with a seccomp filter that refuses `bind`, `listen` and `accept`.

**Which route the host uses.** The installer's LibreOffice check decides it once per host.
1. It converts an invented workbook with Chinese text through `soffice` itself. If the PDF is right, the host keeps the `soffice` route, which is exactly as before.
2. Only if that fails does it run the next steps:
   - it records why, including whether a Unix socket in `/tmp` can be bound;
   - it switches the `soffice`/`libreoffice` wrappers to the LibreOfficeKit route;
   - it checks again, through `~/cps-tools/share/cps/lok_convert.py`, a copy of `deploy/lok_convert.py`.

The route is recorded in `INSTALL_SUMMARY.txt` (`libreoffice pdf route:`), in `RELEASE_PATHS.json` (`libreoffice_pdf_route`), in each wrapper's header, and in `~/cps-tools/var/lo_smoke/ROUTE.txt`. The check keeps its files in `~/cps-tools/var/lo_smoke/`: per route, `lo.status`, `lo.out` and `lo.err`, plus `ipc_probe.txt`. A failure therefore keeps its evidence. Before this fix, the check's files were in `.tmp`, which the script removed before exiting.

On the LibreOfficeKit route:
- **How it works.** `lok_convert.py` loads the same LibreOffice libraries in-process through LibreOfficeKit and saves with the same PDF export filter. It needs no socket.
- **Arguments.** It accepts the arguments the CPS tools pass: `--headless`, `--norestore`, `--nolockcheck`, `-env:UserInstallation=file:///...`, `--convert-to pdf`, `--outdir` and the input files. It refuses anything else with exit 2.
- **Results.** It writes `<outdir>/<stem>.pdf`, creating `<outdir>` if needed. One file's failure does not stop the others. It exits 0 only when every PDF was written.
- **Housekeeping.** LibreOffice's temporary files go to a private folder that is removed. If the locale's encoding is not UTF-8, it uses `C.UTF-8` for character handling, so paths with Chinese characters load as they do with `soffice`.
- **Other calls.** `--version`, and `--convert-to png` (used only by visual QA's no-`pdftoppm` fallback, which the setup rules out), still go to LibreOffice's own launcher. LibreOfficeKit's PNG export does not work for spreadsheets in this build.
- **Known differences.**
  - LibreOfficeKit runs with an en-US configuration, so a sheet without its own page setup prints on Letter instead of A4. Visual QA in fit-width mode, the mode the job runner uses, sets the page setup itself. Unpatched renders, such as the interview example images, may break pages differently.
  - Automatic row heights of long wrapped text can come out slightly smaller.

**Checked on 2026-11-09:**
- Visual QA's page and tile PNGs of 11 delivered 未填 files (9 real development-trial files, 2 invented) are pixel-identical through the two routes.
- In 2 `INTERNAL_QA_WORKBOOK.xlsx` files, the long wrapped review text gets slightly smaller automatic row heights through LibreOfficeKit, so later page breaks move. 7 of 242 pages differ in one file, and the other has 207 pages instead of 208. The text and its line breaks are the same, and nothing is cut.
- Two runs as an unprivileged user:
  - **Normally:** the installer keeps the `soffice` route.
  - **Under the filter:** it chooses LibreOfficeKit. In each run, `check_env.py`, the export self-test (600/600, visual tests included) and `render_examples.py` pass.
- Without the fix, the conversion fails under that filter.
- An independent review of the first version (LibreOfficeKit on every host) found the paper-size difference. That finding led to the per-host route.

Source-prep builders: `build_inventory_xlsx_v2.py` and `build_inventory_v2.py` run with `python3 -I -S -B` and import openpyxl and xlrd from `<bundle>/private/deps`. The script creates `~/cps-tools/builder-deps/private/deps`, a symlink to the venv's site-packages, and checks it under `-S`. Use `~/cps-tools/builder-deps` as `--bundle`, or as the job runner's `source_prep.deps_bundle`. `~/cps-tools/RELEASE_PATHS.json` records the paths the runner's release file needs: `source_prep.deps_bundle` with its site-packages target, `source_prep.node_path`, and `checker_node` (path and sha256).

Hosts used: nodejs.org, conda.anaconda.org, pypi.org, files.pythonhosted.org, archive.ubuntu.com, security.ubuntu.com, registry.npmjs.org and storage.googleapis.com. Fallbacks, used only when a file is missing: snapshot.ubuntu.com (the dated snapshot in the deb locks), launchpad.net (which redirects to launchpadlibrarian.net) and cdn.playwright.dev. The Ubuntu archive drops superseded package versions, so after an Ubuntu update the dated snapshot or Launchpad supplies the locked file, with the same sha256. To re-lock, re-run the apt resolution and micromamba solve recorded in each lock's header, then update the lock hashes pinned in the script.

Options: `CPS_TOOLS`, `CPS_DOWNLOADS` (download cache, default `~/cps-tools/downloads`; safe to delete after a successful run), `CPS_PYTHON=/abs/python3`, `CPS_PYTHON_FROM=conda`, `CPS_LO_LOCK=noble|jammy`, `CPS_WITH_LIBREOFFICE=0` or `=host` (next section), `CPS_WITH_CHROMIUM=0` (the phase-1 self-test does not use Chromium; source prep does), `CPS_DEB_EXTRACT=python` (no `dpkg-deb`). The script ends with `~/cps-tools/INSTALL_SUMMARY.txt`. It lists each tool's path and version, the node sha256, the builder deps bundle, `NODE_PATH`, the LibreOffice smoke test and the `lok_convert.py` sha256, the Chromium checks (one headless launch, plus `screenshot_views.cjs` on an invented page), any missing system libraries, the hosts contacted and the sizes. Outside the prefix it writes only micromamba's `~/.conda/environments.txt` and LibreOffice's and Chromium's usual per-user caches.
