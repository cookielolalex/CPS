#!/usr/bin/env bash
# CPS VM setup without root: installs what deploy/setup_vm.sh installs, under one prefix, as an ordinary user.
# No sudo, no apt-get install, no curl-pipe-to-shell. Every download is pinned by version and sha256 (in this script
# or in the lock files next to it), and is verified before it is unpacked.
#
# Usage:   bash deploy/setup_vm_user.sh            # prefix $HOME/cps-tools (override: CPS_TOOLS=/abs/dir)
#          source ~/cps-tools/env.sh               # then node, python3, soffice, pdftoppm ... come from the prefix
#
# Components (see deploy/README.md, "No-root setup"):
#   node      Node.js v22.23.4, official nodejs.org tarball (sha256 from SHASUMS256.txt, signed by a Node releaser)
#   conda     micromamba 2.9.0 (conda-forge package) + conda-lock-linux-64.txt: poppler, fontconfig tools, zstd,
#             unzip, git, curl; conda-lock-python-linux-64.txt: Python 3.12, only if no system python3 >= 3.11
#   venv      a venv from the system python3 (or the conda Python); pip packages from requirements-user.txt with
#             --require-hashes (openpyxl 3.1.5, xlrd 2.0.2, lxml, pillow)
#   fonts     deb-lock-fonts-noble.txt: fonts-noto-cjk, fonts-noto-cjk-extra, DejaVu, fontconfig rules (Ubuntu debs)
#   soffice   deb-lock-libreoffice-noble-amd64.txt: LibreOffice 24.2.7 (libreoffice-calc, libreoffice-core and their
#             library closure from Ubuntu 24.04), extracted with dpkg-deb -x; needs host glibc >= 2.38. On a host with
#             glibc 2.35-2.37 (Ubuntu 22.04, Debian 12): deb-lock-libreoffice-jammy-amd64.txt, LibreOffice 7.3.7 from 22.04
#   chromium  Playwright 1.63.0 (npm tarballs) and its Chromium build 1243 = Chrome for Testing 153.0.8010.12
#             (headless shell and chrome), without --with-deps; system libraries are checked, not installed
# Also: builder-deps/private/deps -> the venv's site-packages (for the -S inventory builders), NODE_PATH -> Playwright
# in env.sh (for source_prep/screenshot_views.cjs), and RELEASE_PATHS.json with the paths a job-runner release needs.
#
# Options (environment): CPS_TOOLS=<prefix>   CPS_DOWNLOADS=<dir> (default <prefix>/downloads, kept for re-runs)
#   CPS_PYTHON=/abs/python3 (use this base Python)   CPS_PYTHON_FROM=conda (force the conda Python)
#   CPS_WITH_LIBREOFFICE=0 (skip)   CPS_LO_LOCK=noble|jammy (default: by host glibc)   CPS_WITH_CHROMIUM=0 (skip)   CPS_DEB_EXTRACT=python (no dpkg-deb)
# The script is idempotent: a finished component (stamp = sha256 of its pins) is checked and skipped.
set -euo pipefail
umask 022

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
START_EPOCH=$(date +%s)

# ---------------------------------------------------------------- pins
NODE_VERSION=v22.23.4
NODE_XZ_SHA256=1805bcd35e6815559bd2eb97db438d3fdb0eb3a5e6a977b7c1badca76337e9ce   # node-v22.23.4-linux-x64.tar.xz
NODE_GZ_SHA256=b8492284c76a54baf58d61668dd0e41ee0fc98adabf9503d30f05d08f55b4406   # node-v22.23.4-linux-x64.tar.gz
NODE_BIN_SHA256=94efd062ed066c1a0b332e18249859c905e920eeada5df55d24c99b919629a90  # bin/node inside both tarballs
MICROMAMBA_URL=https://conda.anaconda.org/conda-forge/linux-64/micromamba-2.9.0-0.tar.bz2
MICROMAMBA_SHA256=8761c382127e6363bd9e0a2451aa3ef90d071a79133f736e2f759a3bf13040dd
PIP_WHEEL=pip-26.2.2-py3-none-any.whl
PIP_WHEEL_URL=https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/$PIP_WHEEL
PIP_WHEEL_SHA256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70
PLAYWRIGHT_VERSION=1.63.0
PLAYWRIGHT_SHA256=195a5ee9bfed7c6e9c03965950e32e5e4dbedaa02e740e5a530eb4b87dae050c        # npm integrity sha512-+7ziBLid...
PLAYWRIGHT_CORE_SHA256=208593d4e1bcd8f8fe5f869cad1cc332dc7f1d70dc1d58c102dc3ac36e30f26c   # npm integrity sha512-rYCsBF/M...
CHROMIUM_REVISION=1243                 # playwright-core 1.63.0 browsers.json: chromium and chromium-headless-shell
CFT_VERSION=153.0.8010.12
CFT_HEADLESS_SHA256=a9da028861a0cf789ff25c2fed45f5f1aaf969ed9247835b6a7821a4f7af9d1d     # chrome-headless-shell-linux64.zip
CFT_CHROME_SHA256=8aac35011c18f6e2d10696154af89a5728ac2ddd6dc6fad24ffdf243c3fcfd5a       # chrome-linux64.zip
LO_NOBLE_GLIBC_MIN=2.38               # GLIBC_2.38 is the newest symbol version in the noble bundle
LO_JAMMY_GLIBC_MIN=2.35               # GLIBC_2.35 in the jammy bundle
# The lock files are pinned too, so an edited lock is refused rather than installed.
LOCK_CONDA=conda-lock-linux-64.txt;                LOCK_CONDA_SHA256=0c4545635fd0d6560b5863add75394ff5a9fb621ad2b02a35126cb3d4ea841bd
LOCK_PYTHON=conda-lock-python-linux-64.txt;        LOCK_PYTHON_SHA256=c56203bd3cf9b5c2061393fccb01a237df9a6c31c162aaad20dca2e0fe52c5c0
LOCK_PIP=requirements-user.txt;                    LOCK_PIP_SHA256=bcb945e194489b18d12bed30ea693cc03bdd93c7c5ba803bb3c3abe05a032e6b
LOCK_FONTS=deb-lock-fonts-noble.txt;               LOCK_FONTS_SHA256=84021b29db65f4d14ee1a4051c77a448d8fd1b9df33f0ae6fdb1e233dd921f9a
LOCK_LO=deb-lock-libreoffice-noble-amd64.txt;      LOCK_LO_SHA256=db03b94bf0ff128e258286fd7ebd41f80e3c2c491a16bdf8ea005ca3dd58a94e
LOCK_LO_JAMMY=deb-lock-libreoffice-jammy-amd64.txt; LOCK_LO_JAMMY_SHA256=4e9603cd99b6e05f0c5f53fc90e641d2769d581f38b877044e4910a2c55a1eee

# ---------------------------------------------------------------- helpers
log() { printf '[setup_vm_user] %s\n' "$*"; }
warn() { printf '[setup_vm_user] WARNING: %s\n' "$*" >&2; }
die() { printf '[setup_vm_user] ERROR: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

sha256_of() {
  if have sha256sum; then sha256sum "$1" | cut -d' ' -f1
  else python3 -c 'import hashlib,sys;h=hashlib.sha256();f=open(sys.argv[1],"rb");[h.update(b) for b in iter(lambda:f.read(1<<20),b"")];print(h.hexdigest())' "$1"
  fi
}

[ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ] || die "this script supports Linux x86-64 only"
[ "$(id -u)" -ne 0 ] || warn "running as root; nothing here needs root (the prefix is ${CPS_TOOLS:-$HOME/cps-tools})"
for t in tar gzip find ln mv cp rm sed grep awk cut sort tr paste head tail stat du tee uname date realpath readlink timeout sha1sum ldd; do have "$t" || die "required tool missing: $t"; done
have curl || have python3 || die "need curl or python3 to download"
have sha256sum || have python3 || die "need sha256sum or python3"

P=${CPS_TOOLS:-$HOME/cps-tools}
case "$P" in /*) ;; *) die "CPS_TOOLS must be an absolute path: $P" ;; esac
mkdir -p "$P"
P=$(cd "$P" && pwd -P)
case "$P" in *[[:space:]:\&\<\>\'\"\\]*) die "the prefix path must not contain spaces or any of : & < > ' \" \\ ($P)" ;; esac
DL=${CPS_DOWNLOADS:-$P/downloads}
mkdir -p "$DL" "$P/var" "$P/bin" "$P/bin-fallback" "$P/etc/fonts" "$P/share/cps" "$P/.tmp"
HOSTS_LOG=$P/var/hosts_contacted.txt
DL_LOG=$P/var/downloads.log
: > "$P/var/last_run_components.txt"

# The prefix's own entries must not be picked up as "system" tools on a re-run from a sourced shell.
CLEAN_PATH=$(printf '%s' "${PATH:-/usr/bin:/bin}" | tr ':' '\n' | grep -v -x -F -e "$P/venv/bin" -e "$P/node/bin" -e "$P/bin" -e "$P/bin-fallback" | paste -sd: -)
[ -n "$CLEAN_PATH" ] || CLEAN_PATH=/usr/local/bin:/usr/bin:/bin
PATH=$CLEAN_PATH
export PATH

check_lock() {   # check_lock <file> <sha256>
  local f="$SCRIPT_DIR/$1"
  [ -f "$f" ] || die "lock file missing: $f"
  [ "$(sha256_of "$f")" = "$2" ] || die "lock file $1 does not match the sha256 pinned in this script ($2)"
}
check_lock "$LOCK_CONDA" "$LOCK_CONDA_SHA256"
check_lock "$LOCK_PYTHON" "$LOCK_PYTHON_SHA256"
check_lock "$LOCK_PIP" "$LOCK_PIP_SHA256"
check_lock "$LOCK_FONTS" "$LOCK_FONTS_SHA256"
check_lock "$LOCK_LO" "$LOCK_LO_SHA256"
check_lock "$LOCK_LO_JAMMY" "$LOCK_LO_JAMMY_SHA256"

download() {     # download <url> <out>
  local host=${1#*://}; host=${host%%/*}
  grep -qxF "$host" "$HOSTS_LOG" 2>/dev/null || echo "$host" >> "$HOSTS_LOG"
  if have curl; then
    curl -fsSL --proto '=https' --proto-redir '=https' --connect-timeout 30 --retry 4 --retry-delay 5 -o "$2" "$1" </dev/null
  else
    python3 -I -c 'import shutil,sys,urllib.request
with urllib.request.urlopen(sys.argv[1], timeout=120) as r, open(sys.argv[2], "wb") as o: shutil.copyfileobj(r, o)' "$1" "$2" </dev/null
  fi
}

fetch() {        # fetch <sha256> <dest> <url> [mirror urls...]; verified before use, kept for re-runs
  local sha=$1 dest=$2; shift 2
  if [ -f "$dest" ] && [ "$(sha256_of "$dest")" = "$sha" ]; then return 0; fi
  rm -f "$dest" "$dest.part"
  local url got
  for url in "$@"; do
    if download "$url" "$dest.part" 2>"$P/.tmp/fetch.err"; then
      got=$(sha256_of "$dest.part")
      if [ "$got" = "$sha" ]; then mv "$dest.part" "$dest"; printf '%s %s\n' "$sha" "$url" >> "$DL_LOG"; return 0; fi
      warn "sha256 mismatch for $url (got $got, want $sha); trying the next mirror"
    else
      warn "download failed: $url ($(tail -n1 "$P/.tmp/fetch.err" 2>/dev/null))"
    fi
    rm -f "$dest.part"
  done
  die "could not download $(basename "$dest") with sha256 $sha from: $*"
}

stamp_ok() { [ -f "$1" ] && [ "$(cat "$1")" = "$2" ]; }   # stamp_ok <file> <expected content>
component() { log "== $*"; echo "$*" >> "$P/var/last_run_components.txt"; }

# ---------------------------------------------------------------- 1. Node.js v22
component "node $NODE_VERSION"
NODE_DIR=$P/node-$NODE_VERSION-linux-x64
if [ -x "$NODE_DIR/bin/node" ] && [ "$(sha256_of "$NODE_DIR/bin/node")" = "$NODE_BIN_SHA256" ]; then
  log "node already installed: $NODE_DIR"
else
  rm -rf "$NODE_DIR" "$P/.tmp/node"; mkdir -p "$P/.tmp/node"
  base=https://nodejs.org/dist/$NODE_VERSION
  if have xz; then
    fetch "$NODE_XZ_SHA256" "$DL/node-$NODE_VERSION-linux-x64.tar.xz" "$base/node-$NODE_VERSION-linux-x64.tar.xz"
    tar -xJf "$DL/node-$NODE_VERSION-linux-x64.tar.xz" -C "$P/.tmp/node"
  else
    fetch "$NODE_GZ_SHA256" "$DL/node-$NODE_VERSION-linux-x64.tar.gz" "$base/node-$NODE_VERSION-linux-x64.tar.gz"
    tar -xzf "$DL/node-$NODE_VERSION-linux-x64.tar.gz" -C "$P/.tmp/node"
  fi
  mv "$P/.tmp/node/node-$NODE_VERSION-linux-x64" "$NODE_DIR"
  [ "$(sha256_of "$NODE_DIR/bin/node")" = "$NODE_BIN_SHA256" ] || die "unexpected node binary in the tarball"
fi
ln -sfn "node-$NODE_VERSION-linux-x64" "$P/node"
[ "$("$P/node/bin/node" --version)" = "$NODE_VERSION" ] || die "node does not run or is not $NODE_VERSION"
NODE_REAL=$(realpath "$P/node/bin/node")
printf '%s  %s\n' "$NODE_BIN_SHA256" "$NODE_REAL" > "$P/NODE_SHA256.txt"

# ---------------------------------------------------------------- 2. micromamba and the conda-forge environment
component "micromamba 2.9.0 and conda env ($LOCK_CONDA)"
MM=$P/micromamba/bin/micromamba
export MAMBA_ROOT_PREFIX=$P/micromamba/root
if ! stamp_ok "$P/micromamba/.cps-stamp" "$MICROMAMBA_SHA256" || [ ! -x "$MM" ]; then
  fetch "$MICROMAMBA_SHA256" "$DL/micromamba-2.9.0-0.tar.bz2" "$MICROMAMBA_URL"
  rm -rf "$P/micromamba" "$P/.tmp/mm"; mkdir -p "$P/.tmp/mm"
  if ! tar -xjf "$DL/micromamba-2.9.0-0.tar.bz2" -C "$P/.tmp/mm" bin/micromamba 2>/dev/null; then
    python3 -I -c 'import sys,tarfile; tarfile.open(sys.argv[1]).extract("bin/micromamba", sys.argv[2], filter="data")' \
      "$DL/micromamba-2.9.0-0.tar.bz2" "$P/.tmp/mm"
  fi
  mkdir -p "$P/micromamba/bin"; mv "$P/.tmp/mm/bin/micromamba" "$MM"; chmod 755 "$MM"
  echo "$MICROMAMBA_SHA256" > "$P/micromamba/.cps-stamp"
fi
"$MM" --version >/dev/null || die "micromamba does not run"
grep -qxF conda.anaconda.org "$HOSTS_LOG" 2>/dev/null || echo conda.anaconda.org >> "$HOSTS_LOG"

conda_env() {    # conda_env <prefix> <lock file> <lock sha256>
  if stamp_ok "$1/.cps-lock-sha256" "$3"; then log "conda env up to date: $1"; return 0; fi
  rm -rf "$1"
  "$MM" create --yes --quiet --no-rc --prefix "$1" --file "$SCRIPT_DIR/$2" || die "micromamba could not create $1 from $2"
  echo "$3" > "$1/.cps-lock-sha256"
}
conda_env "$P/conda" "$LOCK_CONDA" "$LOCK_CONDA_SHA256"
C=$P/conda

# ---------------------------------------------------------------- 3. Python venv with hash-pinned packages
component "python venv ($LOCK_PIP)"
py_ok() {        # py_ok <python>: >= 3.11, has ssl/zlib/pyexpat/sqlite-free basics and can make a venv without pip
  "$1" -I -c 'import sys, ssl, zlib, pyexpat, venv; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null || return 1
  rm -rf "$P/.tmp/venvprobe"
  "$1" -I -m venv --without-pip "$P/.tmp/venvprobe" >/dev/null 2>&1 && "$P/.tmp/venvprobe/bin/python" -I -c 'import sys' 2>/dev/null
  local rc=$?; rm -rf "$P/.tmp/venvprobe"; return $rc
}
BASE_PY=""
if [ "${CPS_PYTHON_FROM:-}" != conda ]; then
  for cand in ${CPS_PYTHON:-} python3 python3.13 python3.12 python3.11 python3.14; do
    p=$(command -v "$cand" 2>/dev/null) || continue
    if py_ok "$p"; then BASE_PY=$p; break; fi
    log "not usable as base Python: $p"
  done
  [ -z "${CPS_PYTHON:-}" ] || [ "$BASE_PY" = "$(command -v "$CPS_PYTHON")" ] || die "CPS_PYTHON=$CPS_PYTHON is not usable (needs >= 3.11 with venv)"
fi
if [ -z "$BASE_PY" ]; then
  log "no usable system python3 >= 3.11; using the conda-forge Python from $LOCK_PYTHON"
  conda_env "$P/conda-python" "$LOCK_PYTHON" "$LOCK_PYTHON_SHA256"
  BASE_PY=$P/conda-python/bin/python3.12
  py_ok "$BASE_PY" || die "the conda Python is not usable"
fi
BASE_PY_REAL=$(realpath "$BASE_PY")
BASE_PY_VER=$("$BASE_PY" -I -c 'import sys; print(sys.version.split()[0])')
VENV=$P/venv
VENV_STAMP="$BASE_PY_REAL $BASE_PY_VER $LOCK_PIP_SHA256 $PIP_WHEEL_SHA256"
if stamp_ok "$VENV/.cps-stamp" "$VENV_STAMP" && "$VENV/bin/python" -I -c 'import openpyxl, xlrd, lxml, PIL' 2>/dev/null; then
  log "venv up to date: $VENV (base $BASE_PY_REAL $BASE_PY_VER)"
else
  fetch "$PIP_WHEEL_SHA256" "$DL/$PIP_WHEEL" "$PIP_WHEEL_URL"
  rm -rf "$VENV"
  "$BASE_PY" -I -m venv --without-pip "$VENV"
  grep -qxF pypi.org "$HOSTS_LOG" 2>/dev/null || echo pypi.org >> "$HOSTS_LOG"
  grep -qxF files.pythonhosted.org "$HOSTS_LOG" 2>/dev/null || echo files.pythonhosted.org >> "$HOSTS_LOG"
  # The conda Python's OpenSSL trusts only conda's CA bundle; let pip use the host's trust store, as curl does
  PIP_CA=()
  case "$BASE_PY_REAL" in "$P"/conda-python/*)
    if [ -z "${PIP_CERT:-}${SSL_CERT_FILE:-}${REQUESTS_CA_BUNDLE:-}" ]; then
      for ca in /etc/ssl/certs/ca-certificates.crt /etc/pki/tls/certs/ca-bundle.crt /etc/ssl/cert.pem; do
        if [ -r "$ca" ]; then PIP_CA=(--cert "$ca"); break; fi
      done
    fi ;;
  esac
  # pip runs from its verified wheel; it installs itself and the packages, every file checked against the lock's hashes
  "$VENV/bin/python" "$DL/$PIP_WHEEL/pip" install ${PIP_CA[@]+"${PIP_CA[@]}"} --disable-pip-version-check --no-input --no-cache-dir \
    --require-hashes --only-binary=:all: --no-deps -r "$SCRIPT_DIR/$LOCK_PIP"
  echo "$VENV_STAMP" > "$VENV/.cps-stamp"
fi
"$VENV/bin/python" -I -c '
import sys, openpyxl, xlrd, PIL
from lxml import etree
assert openpyxl.__version__ == "3.1.5" and xlrd.__version__ == "2.0.2", (openpyxl.__version__, xlrd.__version__)
assert sys.version_info >= (3, 11)' || die "venv packages are not as pinned"
# The source-prep inventory builders run with python3 -I -S -B and import openpyxl/xlrd from <bundle>/private/deps;
# builder-deps is such a bundle: private/deps is a symlink to this venv's site-packages (release: source_prep.deps_bundle)
SITE_PACKAGES=$("$VENV/bin/python" -I -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
SITE_PACKAGES=$(realpath "$SITE_PACKAGES")
mkdir -p "$P/builder-deps/private"
ln -sfn "$SITE_PACKAGES" "$P/builder-deps/private/deps"
"$VENV/bin/python" -I -S -B - "$P/builder-deps" <<'PYEOF' || die "builder-deps does not provide openpyxl 3.1.5 and xlrd 2.0.2 under -S"
import sys
from pathlib import Path
dep = (Path(sys.argv[1]) / 'private/deps').resolve()
sys.path.insert(0, str(dep))
import openpyxl, xlrd
assert Path(openpyxl.__file__).resolve().is_relative_to(dep / 'openpyxl') and openpyxl.__version__ == '3.1.5'
assert Path(xlrd.__file__).resolve().is_relative_to(dep / 'xlrd') and xlrd.__version__ == '2.0.2'
PYEOF

# ---------------------------------------------------------------- deb helpers (fonts, LibreOffice)
UBUNTU_SNAPSHOT=https://snapshot.ubuntu.com/ubuntu/20261106T050000Z
extract_deb() {  # extract_deb <deb> <dest>: data only, no maintainer scripts
  if [ "${CPS_DEB_EXTRACT:-}" != python ] && have dpkg-deb; then dpkg-deb -x "$1" "$2"; return; fi
  "$VENV/bin/python" -I - "$1" "$2" "$C/bin/zstd" <<'PYEOF'
import gzip, lzma, subprocess, sys
deb, dest, zstd = sys.argv[1:4]
with open(deb, 'rb') as f:
    if f.read(8) != b'!<arch>\n':
        sys.exit(f'not a deb: {deb}')
    while True:
        hdr = f.read(60)
        if len(hdr) < 60:
            sys.exit(f'no data.tar member in {deb}')
        name, size = hdr[:16].decode().strip().rstrip('/'), int(hdr[48:58].decode().strip())
        data = f.read(size)
        if size % 2:
            f.read(1)
        if name.startswith('data.tar'):
            break
if name.endswith('.zst'):
    data = subprocess.run([zstd, '-dc', '-q'], input=data, stdout=subprocess.PIPE, check=True).stdout
elif name.endswith('.xz'):
    data = lzma.decompress(data)
elif name.endswith('.gz'):
    data = gzip.decompress(data)
elif name != 'data.tar':
    sys.exit(f'unsupported member {name} in {deb}')
subprocess.run(['tar', '-x', '--no-same-owner', '-C', dest, '-f', '-'], input=data, check=True)
PYEOF
}
relativize_symlinks() {  # absolute symlinks inside an extracted root point into the root, never at host paths
  local root=$1 l t
  find "$root" -type l -lname '/*' -print0 | while IFS= read -r -d '' l; do
    t=$(readlink "$l")
    ln -sfn "$(realpath -m -s --relative-to="$(dirname "$l")" "$root$t")" "$l"
  done
}
install_debs() { # install_debs <lock file> <lock sha256> <root dir>
  local lock=$1 lsha=$2 root=$3 sha size path f n=0
  if stamp_ok "$root/.cps-lock-sha256" "$lsha"; then log "up to date: $root"; return 0; fi
  mkdir -p "$DL/debs"
  while read -r sha size path <&3; do
    case "$sha" in ''|'#'*) continue ;; esac
    f=$DL/debs/$(basename "$path")
    fetch "$sha" "$f" "https://archive.ubuntu.com/ubuntu/$path" "https://security.ubuntu.com/ubuntu/$path" \
      "$UBUNTU_SNAPSHOT/$path" "https://launchpad.net/ubuntu/+archive/primary/+files/$(basename "$path")"
    [ "$(stat -c %s "$f")" = "$size" ] || die "size mismatch for $f"
    n=$((n + 1))
  done 3< "$SCRIPT_DIR/$lock"
  rm -rf "$root.tmp" "$root"; mkdir -p "$root.tmp/root"
  while read -r sha size path <&3; do
    case "$sha" in ''|'#'*) continue ;; esac
    extract_deb "$DL/debs/$(basename "$path")" "$root.tmp/root" </dev/null
  done 3< "$SCRIPT_DIR/$lock"
  relativize_symlinks "$root.tmp/root"
  mv "$root.tmp" "$root"
  echo "$lsha" > "$root/.cps-lock-sha256"
  log "extracted $n packages into $root/root"
}

# ---------------------------------------------------------------- 4. fonts (Noto CJK as in setup_vm.sh)
component "fonts ($LOCK_FONTS)"
install_debs "$LOCK_FONTS" "$LOCK_FONTS_SHA256" "$P/fonts"
FR=$P/fonts/root

# ---------------------------------------------------------------- 5. LibreOffice (Ubuntu 24.04 debs, or 22.04 on older glibc)
LO_STATUS="not installed"
LR=$P/libreoffice/root
glibc_version() { getconf GNU_LIBC_VERSION 2>/dev/null | awk '{print $2}' || ldd --version 2>/dev/null | head -n1 | awk '{print $NF}'; }
version_ge() { [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]; }
if [ "${CPS_WITH_LIBREOFFICE:-1}" = 0 ]; then
  LO_STATUS="skipped (CPS_WITH_LIBREOFFICE=0)"
else
  GLIBC=$(glibc_version)
  LO_LOCK="" LO_LOCK_SHA256="" LO_MIN=""
  case "${CPS_LO_LOCK:-auto}" in
    noble) LO_LOCK=$LOCK_LO LO_LOCK_SHA256=$LOCK_LO_SHA256 LO_MIN=$LO_NOBLE_GLIBC_MIN ;;
    jammy) LO_LOCK=$LOCK_LO_JAMMY LO_LOCK_SHA256=$LOCK_LO_JAMMY_SHA256 LO_MIN=$LO_JAMMY_GLIBC_MIN ;;
    auto)
      if [ -n "$GLIBC" ] && version_ge "$GLIBC" "$LO_NOBLE_GLIBC_MIN"; then
        LO_LOCK=$LOCK_LO LO_LOCK_SHA256=$LOCK_LO_SHA256 LO_MIN=$LO_NOBLE_GLIBC_MIN
      else
        LO_LOCK=$LOCK_LO_JAMMY LO_LOCK_SHA256=$LOCK_LO_JAMMY_SHA256 LO_MIN=$LO_JAMMY_GLIBC_MIN
      fi ;;
    *) die "CPS_LO_LOCK must be noble or jammy" ;;
  esac
  component "libreoffice ($LO_LOCK; host glibc ${GLIBC:-unknown})"
  if [ -z "$GLIBC" ] || ! version_ge "$GLIBC" "$LO_MIN"; then
    LO_STATUS="FAILED: host glibc ${GLIBC:-unknown} < $LO_MIN, which $LO_LOCK needs"
    warn "$LO_STATUS"
  else
    install_debs "$LO_LOCK" "$LO_LOCK_SHA256" "$P/libreoffice"
    # Debian's postinst copies share/.registry/*.xcd to /etc/libreoffice/registry; here share/registry is .registry
    PROG=$LR/usr/lib/libreoffice/program
    if [ "$(readlink "$LR/usr/lib/libreoffice/share/registry")" != .registry ]; then
      rm -f "$LR/usr/lib/libreoffice/share/registry"; ln -s .registry "$LR/usr/lib/libreoffice/share/registry"
    fi
    # Debian hard-codes /usr/lib/libreoffice and /etc/libreoffice in two bootstrap files; use upstream's relative form
    "$VENV/bin/python" -I - "$PROG/fundamentalrc" "$PROG/sofficerc" <<'PYEOF'
import sys
edits = {sys.argv[1]: [('BRAND_BASE_DIR=file:///usr/lib/libreoffice\n', 'BRAND_BASE_DIR=${ORIGIN}/..\n'),
                       ('xcsxcu:file:///etc/libreoffice/registry res:file:///etc/libreoffice/registry ',
                        'xcsxcu:${BRAND_BASE_DIR}/share/registry res:${BRAND_BASE_DIR}/share/registry ')],
         sys.argv[2]: [('FHS_CONFIG_FILE=file:///etc/libreoffice/sofficerc\n',
                        'FHS_CONFIG_FILE=${ORIGIN}/../../../../etc/libreoffice/sofficerc\n')]}
for path, pairs in edits.items():
    text = open(path, encoding='utf-8').read()
    for old, new in pairs:
        if new in text:
            continue
        if text.count(old) != 1:
            sys.exit(f'unexpected content in {path}: {old!r}')
        text = text.replace(old, new)
    open(path, 'w', encoding='utf-8').write(text)
PYEOF
    LO_LIBPATH="$PROG:$LR/usr/lib/x86_64-linux-gnu:$LR/lib/x86_64-linux-gnu:$LR/usr/lib/lp_solve"
    for name in soffice libreoffice; do
      cat > "$P/bin/$name.new" <<EOF
#!/bin/sh
# CPS no-root LibreOffice (Ubuntu packages from deploy/$LO_LOCK, extracted by deploy/setup_vm_user.sh).
# Does what program/soffice does (SAL_ENABLE_FILE_LOCKING=1, then oosplash) without its debug options.
# The bundled libraries are visible only to LibreOffice's own processes, not to the calling shell.
LD_LIBRARY_PATH="$LO_LIBPATH\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
export LD_LIBRARY_PATH
SAL_ENABLE_FILE_LOCKING=1
export SAL_ENABLE_FILE_LOCKING
if [ -z "\${FONTCONFIG_FILE:-}" ]; then FONTCONFIG_FILE="$P/etc/fonts/fonts.conf"; export FONTCONFIG_FILE; fi
exec "$PROG/oosplash" "\$@"
EOF
      chmod 755 "$P/bin/$name.new"; mv "$P/bin/$name.new" "$P/bin/$name"
    done
    # every library LibreOffice loads must come from the bundle, except glibc's own
    outside=$(for f in "$PROG/soffice.bin" "$PROG/oosplash" "$PROG"/*.so*; do LD_LIBRARY_PATH="$LO_LIBPATH" ldd "$f" 2>/dev/null; done \
      | awk '/=>/ {print $1, $3}' | grep -v -F "$LR/" \
      | grep -v -E '^(libc|libm|libdl|libpthread|librt|libresolv|libutil|libanl|libnsl)\.so|^linux-vdso' | sort -u || true)
    [ -z "$outside" ] || die "LibreOffice would load libraries from outside the bundle: $outside"
    LO_STATUS="installed"
  fi
fi

# ---------------------------------------------------------------- 6. fontconfig: only the prefix's fonts
component "fontconfig"
LO_FONT_DIR=""
[ -d "$LR/usr/share/fonts" ] && LO_FONT_DIR="  <dir>$LR/usr/share/fonts</dir>"
cat > "$P/etc/fonts/fonts.conf.new" <<EOF
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<!-- CPS no-root toolchain (generated by deploy/setup_vm_user.sh). Only the prefix's fonts are used: Noto CJK and
     DejaVu (deploy/$LOCK_FONTS) and OpenSymbol (LibreOffice). Rules: fontconfig-config 2.15 conf.d with
     70-fonts-noto-cjk.conf (zh-tw -> Noto Sans/Serif CJK TC). Host fonts are not read. -->
<fontconfig>
  <dir>$FR/usr/share/fonts</dir>
$LO_FONT_DIR
  <cachedir>$P/var/cache/fontconfig</cachedir>
  <include ignore_missing="yes">$FR/etc/fonts/conf.d</include>
</fontconfig>
EOF
mv "$P/etc/fonts/fonts.conf.new" "$P/etc/fonts/fonts.conf"
export FONTCONFIG_FILE=$P/etc/fonts/fonts.conf
"$C/bin/fc-cache" -f >/dev/null 2>&1 || warn "fc-cache reported an error"
[ -n "$("$C/bin/fc-list" ':lang=zh-tw' family)" ] || die "no zh-tw font found by fontconfig"

# ---------------------------------------------------------------- 7. Playwright + Chromium (no --with-deps)
CHROMIUM_STATUS="not installed"
PWM=$P/playwright/node_modules
BR=$P/ms-playwright
if [ "${CPS_WITH_CHROMIUM:-1}" = 0 ]; then
  CHROMIUM_STATUS="skipped (CPS_WITH_CHROMIUM=0)"
else
  component "playwright $PLAYWRIGHT_VERSION and chromium $CHROMIUM_REVISION (Chrome for Testing $CFT_VERSION)"
  PW_STAMP="$PLAYWRIGHT_SHA256 $PLAYWRIGHT_CORE_SHA256"
  if ! stamp_ok "$P/playwright/.cps-stamp" "$PW_STAMP"; then
    rm -rf "$P/playwright"; mkdir -p "$PWM"
    for pkg in playwright playwright-core; do
      sha=$PLAYWRIGHT_SHA256; [ "$pkg" = playwright-core ] && sha=$PLAYWRIGHT_CORE_SHA256
      fetch "$sha" "$DL/$pkg-$PLAYWRIGHT_VERSION.tgz" "https://registry.npmjs.org/$pkg/-/$pkg-$PLAYWRIGHT_VERSION.tgz"
      rm -rf "$P/.tmp/npm"; mkdir -p "$P/.tmp/npm"
      tar -xzf "$DL/$pkg-$PLAYWRIGHT_VERSION.tgz" -C "$P/.tmp/npm" --no-same-owner
      mv "$P/.tmp/npm/package" "$PWM/$pkg"
    done
    echo "$PW_STAMP" > "$P/playwright/.cps-stamp"
  fi
  UNZIP=unzip; have unzip || UNZIP=$C/bin/unzip
  cft_install() {   # cft_install <dir name> <zip> <sha256>
    local d=$BR/$1
    if stamp_ok "$d/.cps-stamp" "$3" && [ -f "$d/INSTALLATION_COMPLETE" ]; then return 0; fi
    fetch "$3" "$DL/cft-$CFT_VERSION-$2" "https://storage.googleapis.com/chrome-for-testing-public/$CFT_VERSION/linux64/$2" \
      "https://cdn.playwright.dev/builds/cft/$CFT_VERSION/linux64/$2"
    rm -rf "$d" "$d.tmp"; mkdir -p "$d.tmp"
    "$UNZIP" -q "$DL/cft-$CFT_VERSION-$2" -d "$d.tmp"
    : > "$d.tmp/INSTALLATION_COMPLETE"; echo "$3" > "$d.tmp/.cps-stamp"
    mv "$d.tmp" "$d"
  }
  mkdir -p "$BR"
  cft_install "chromium_headless_shell-$CHROMIUM_REVISION" chrome-headless-shell-linux64.zip "$CFT_HEADLESS_SHA256"
  cft_install "chromium-$CHROMIUM_REVISION" chrome-linux64.zip "$CFT_CHROME_SHA256"
  # register the install the way "playwright install" does, so a later "playwright install" keeps these browsers
  mkdir -p "$BR/.links"
  printf '%s' "$PWM/playwright-core" > "$BR/.links/$(printf '%s' "$PWM/playwright-core" | sha1sum | cut -c1-40)"
  CHROMIUM_STATUS="installed"
fi

# ---------------------------------------------------------------- 8. bin directories and env.sh
component "env.sh"
for t in pdftoppm pdfinfo pdftotext pdffonts pdftocairo pdfimages pdfseparate pdfunite pdfattach pdfdetach \
         fc-list fc-match fc-cache fc-query fc-scan fc-pattern fc-cat fc-validate fc-conflist; do
  [ -x "$C/bin/$t" ] && ln -sfn "$C/bin/$t" "$P/bin/$t"
done
for t in git unzip curl zstd; do [ -x "$C/bin/$t" ] && ln -sfn "$C/bin/$t" "$P/bin-fallback/$t"; done
cat > "$P/env.sh.new" <<EOF
# CPS no-root toolchain environment (generated by deploy/setup_vm_user.sh). Usage: source $P/env.sh
# Puts the prefix's python (venv), node v22, soffice, poppler and fontconfig tools first on PATH; git, unzip, curl and
# zstd from the prefix are only fallbacks at the end of PATH. Sets NODE_PATH (Playwright) and no LD_LIBRARY_PATH.
CPS_TOOLS='$P'
export CPS_TOOLS
_cps_rest=""
_cps_old_ifs=\$IFS; IFS=:
for _cps_d in \${PATH:-}; do
  case "\$_cps_d" in
    "\$CPS_TOOLS/venv/bin"|"\$CPS_TOOLS/node/bin"|"\$CPS_TOOLS/bin"|"\$CPS_TOOLS/bin-fallback"|"") ;;
    *) _cps_rest="\${_cps_rest:+\$_cps_rest:}\$_cps_d" ;;
  esac
done
IFS=\$_cps_old_ifs
PATH="\$CPS_TOOLS/venv/bin:\$CPS_TOOLS/node/bin:\$CPS_TOOLS/bin\${_cps_rest:+:\$_cps_rest}:\$CPS_TOOLS/bin-fallback"
export PATH
unset _cps_rest _cps_old_ifs _cps_d PYTHONHOME
FONTCONFIG_FILE="\$CPS_TOOLS/etc/fonts/fonts.conf"
export FONTCONFIG_FILE
PLAYWRIGHT_BROWSERS_PATH="\$CPS_TOOLS/ms-playwright"
export PLAYWRIGHT_BROWSERS_PATH
# Playwright for the view screenshots (source_prep/screenshot_views.cjs: require('playwright')). The export writer and
# saved QA remove every NODE_* variable from node's environment, so NODE_PATH does not reach them.
CPS_PLAYWRIGHT_NODE_PATH="\$CPS_TOOLS/playwright/node_modules"
export CPS_PLAYWRIGHT_NODE_PATH
case ":\${NODE_PATH:-}:" in
  *":\$CPS_PLAYWRIGHT_NODE_PATH:"*) ;;
  *) NODE_PATH="\$CPS_PLAYWRIGHT_NODE_PATH\${NODE_PATH:+:\$NODE_PATH}" ;;
esac
export NODE_PATH
# For the job runner's release file (source_prep.deps_bundle): see \$CPS_TOOLS/RELEASE_PATHS.json
CPS_BUILDER_DEPS_BUNDLE="\$CPS_TOOLS/builder-deps"
export CPS_BUILDER_DEPS_BUNDLE
hash -r 2>/dev/null || true
EOF
mv "$P/env.sh.new" "$P/env.sh"

# ---------------------------------------------------------------- 9. checks and summary
component "checks"
# shellcheck disable=SC1091
. "$P/env.sh"
SMOKE=$P/.tmp/smoke; rm -rf "$SMOKE"; mkdir -p "$SMOKE/home"
LO_SMOKE="not run"
if [ "$LO_STATUS" = installed ]; then
  "$VENV/bin/python" -I -c 'import sys, openpyxl
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "測試"
ws.append(["品名", "規格"]); ws.append(["控制盤 箱體", "不鏽鋼 600x800"]); wb.save(sys.argv[1])' "$SMOKE/cjk.xlsx"
  lo_txt="" lo_fonts=""
  if HOME=$SMOKE/home SAL_USE_VCLPLUGIN=svp timeout 300 soffice --headless --convert-to pdf --outdir "$SMOKE" "$SMOKE/cjk.xlsx" >/dev/null 2>"$SMOKE/lo.err"; then
    lo_txt=$(pdftotext "$SMOKE/cjk.pdf" - 2>/dev/null || true); lo_fonts=$(pdffonts "$SMOKE/cjk.pdf" 2>/dev/null || true)
  fi
  if [[ "$lo_txt" == *控制盤* && "$lo_fonts" == *NotoSansCJK* ]]; then
    LO_SMOKE="ok (invented xlsx with Chinese text -> PDF, text extractable, Noto Sans CJK embedded)"
  else
    LO_SMOKE="FAILED (see $SMOKE/lo.err)"; LO_STATUS="FAILED: smoke test"
  fi
fi
CHROMIUM_CHECK="not run"
if [ "$CHROMIUM_STATUS" = installed ]; then
  missing=""
  for exe in "$BR/chromium_headless_shell-$CHROMIUM_REVISION/chrome-headless-shell-linux64/chrome-headless-shell" \
             "$BR/chromium-$CHROMIUM_REVISION/chrome-linux64/chrome"; do
    m=$(ldd "$exe" 2>/dev/null | awk '/not found/ {print $1}' | sort -u | paste -sd' ' - || true)
    [ -z "$m" ] || missing="$missing $(basename "$exe"): $m;"
  done
  cat > "$P/share/cps/chromium_check.cjs" <<'EOF'
// CPS: launch Playwright's headless Chromium once and screenshot a line of Chinese text.
// require('playwright') is resolved through NODE_PATH from env.sh, as source_prep/screenshot_views.cjs resolves it.
const {chromium} = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({viewport: {width: 720, height: 120}, deviceScaleFactor: 1});
  await page.setContent('<!doctype html><meta charset="utf-8"><body style="margin:16px;font-family:sans-serif;font-size:28px;background:#fff">CPS 控制盤 箱體 繁體中文 Chromium</body>');
  await page.screenshot({path: process.argv[3]});
  console.log(browser.version());
  await browser.close();
})().catch(e => { console.error(String((e && e.message) || e).split('\n').slice(0, 15).join('\n')); process.exit(1); });
EOF
  if ver=$(cd "$P/share/cps" && timeout 180 node chromium_check.cjs "$P/var/chromium_check.png" 2>"$P/var/chromium_check.err"); then
    CHROMIUM_CHECK="headless launch ok (Chromium $ver; screenshot $P/var/chromium_check.png)"
  else
    CHROMIUM_CHECK="headless launch FAILED (see $P/var/chromium_check.err)"
  fi
  # the CPS screenshot script itself, on an invented page like the ones render_views.py writes
  SV=$SCRIPT_DIR/../research/guideline046_003/source_prep/screenshot_views.cjs
  if [ -f "$SV" ]; then
    printf '%s\n' '<!doctype html><html><head><meta charset="utf-8"><style>body{margin:8px;font-family:'"'"'WenQuanYi Zen Hei'"'"',sans-serif;font-size:13px;background:#fff;color:#111} td,th{border:1px solid #9aa;padding:2px 4px}</style></head><body><h1 style="font-size:13px">Invented view (setup check)</h1><table><tr><th></th><th>A</th><th>B</th></tr><tr><th>1</th><td>品名</td><td>規格</td></tr><tr><th>2</th><td>控制盤 箱體</td><td>不鏽鋼 600x800</td></tr></table></body></html>' > "$SMOKE/view_01.html"
    if timeout 180 node "$SV" "$SMOKE" view_01.html >/dev/null 2>"$P/var/screenshot_views_check.err" && [ -s "$SMOKE/view_01.png" ]; then
      cp "$SMOKE/view_01.png" "$P/var/screenshot_views_check.png"
      CHROMIUM_CHECK="$CHROMIUM_CHECK; source_prep/screenshot_views.cjs ok (NODE_PATH; $P/var/screenshot_views_check.png)"
    else
      CHROMIUM_CHECK="$CHROMIUM_CHECK; source_prep/screenshot_views.cjs FAILED (see $P/var/screenshot_views_check.err)"
    fi
  fi
  [ -z "$missing" ] || CHROMIUM_CHECK="$CHROMIUM_CHECK; missing system libraries:$missing"
fi

"$VENV/bin/python" -I - "$P/RELEASE_PATHS.json" "$P" "$SITE_PACKAGES" "$PWM" "$NODE_REAL" "$NODE_BIN_SHA256" "$BR" <<'PYEOF'
import json, sys
out, p, site, pwm, node, nsha, br = sys.argv[1:8]
rec = {'schema': 'cps.no-root-setup.release-paths.v1',
       'meaning': 'Paths and pins this no-root setup created, for the job runner release file (deploy/run). Not a release.',
       'prefix': p, 'env_sh': p + '/env.sh',
       'source_prep': {'deps_bundle': p + '/builder-deps', 'deps_bundle_private_deps_target': site, 'node_path': pwm},
       'checker_node': {'path': node, 'sha256': nsha},
       'python': p + '/venv/bin/python3', 'venv_site_packages': site,
       'playwright_browsers_path': br, 'fontconfig_file': p + '/etc/fonts/fonts.conf'}
open(out, 'w', encoding='utf-8').write(json.dumps(rec, indent=1) + '\n')
PYEOF
{
  echo "CPS no-root toolchain, prefix $P (source $P/env.sh)"
  echo "finished $(date -u +%Y-%m-%dT%H:%M:%SZ) in $(( $(date +%s) - START_EPOCH )) s"
  echo "tools (after sourcing env.sh):"
  printf '  %-10s %s  [%s]\n' node "$(command -v node)" "$(node --version)"
  printf '  %-10s %s  [%s]\n' npm "$(command -v npm)" "$(npm --version 2>/dev/null)"
  printf '  %-10s %s  [%s]\n' python3 "$(command -v python3)" "$(python3 --version 2>&1) (base: $BASE_PY_REAL)"
  printf '  %-10s %s\n' packages "$(python3 -I -c 'import openpyxl, xlrd, PIL, lxml.etree as e; print("openpyxl", openpyxl.__version__, "xlrd", xlrd.__version__, "lxml", ".".join(map(str, e.LXML_VERSION)), "pillow", PIL.__version__)')"
  if [ "$LO_STATUS" = installed ]; then
    printf '  %-10s %s  [%s] (%s)\n' soffice "$(command -v soffice)" "$(soffice --version 2>/dev/null | head -n1)" "$LO_LOCK"
  else
    printf '  %-10s %s\n' soffice "$LO_STATUS"
  fi
  printf '  %-10s %s  [%s]\n' pdftoppm "$(command -v pdftoppm)" "$(pdftoppm -v 2>&1 | head -n1)"
  printf '  %-10s %s  [%s]\n' pdfinfo "$(command -v pdfinfo)" "$(pdfinfo -v 2>&1 | head -n1)"
  printf '  %-10s %s  [%s]\n' pdftotext "$(command -v pdftotext)" "$(pdftotext -v 2>&1 | head -n1)"
  printf '  %-10s %s  [%s]\n' fc-match "$(command -v fc-match)" "sans-serif:lang=zh-tw -> $(fc-match 'sans-serif:lang=zh-tw')"
  printf '  %-10s %s  [%s]\n' micromamba "$MM" "$("$MM" --version)"
  if [ "$CHROMIUM_STATUS" = installed ]; then
    printf '  %-10s %s\n' playwright "$PWM/playwright $PLAYWRIGHT_VERSION, Chromium $CHROMIUM_REVISION in $BR"
  else
    printf '  %-10s %s\n' playwright "$CHROMIUM_STATUS"
  fi
  printf '  %-10s %s\n' fallback "$(for t in git unzip curl zstd; do printf '%s=%s ' "$t" "$(command -v "$t" || echo MISSING)"; done)"
  echo "node binary (admit this one): sha256 $(sha256_of "$NODE_REAL")  $NODE_REAL"
  echo "builder deps bundle (release source_prep.deps_bundle): $P/builder-deps  (private/deps -> $SITE_PACKAGES)"
  echo "NODE_PATH (release source_prep.node_path): $PWM"
  echo "release paths recorded in: $P/RELEASE_PATHS.json"
  echo "libreoffice smoke test: $LO_SMOKE"
  echo "chromium: $CHROMIUM_CHECK"
  echo "hosts contacted by this and earlier runs: $(sort -u "$HOSTS_LOG" 2>/dev/null | paste -sd' ' -)"
  echo "size: $(du -sh "$P" 2>/dev/null | cut -f1) total; downloads $(du -sh "$DL" 2>/dev/null | cut -f1) (kept for re-runs, safe to delete); without downloads $(du -sh --exclude=downloads "$P" 2>/dev/null | cut -f1)"
} | tee "$P/INSTALL_SUMMARY.txt"
rm -rf "$P/.tmp"
case "$LO_STATUS" in installed|skipped*) ;; *) die "LibreOffice: $LO_STATUS" ;; esac
log "done. Next: source $P/env.sh"
