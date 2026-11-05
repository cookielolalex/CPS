#!/usr/bin/env bash
# CPS VM setup (Debian/Ubuntu). Installs the toolchain the CPS tools need; prints versions at the end.
# Usage: bash deploy/setup_vm.sh            (run as a user with sudo, or as root)
set -euo pipefail
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
$SUDO apt-get update -y
$SUDO apt-get install -y --no-install-recommends python3 python3-venv python3-pip git unzip curl ca-certificates \
  libreoffice-calc libreoffice-core poppler-utils fonts-noto-cjk fonts-noto-cjk-extra
# Node.js v22 (NodeSource). Any v22 build works for the self-test; the export admission pins the exact binary by sha256,
# so the maintainer must admit this VM's binary after a passing self-test.
if ! command -v node >/dev/null || ! node --version | grep -q '^v22\.'; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | $SUDO bash -
  $SUDO apt-get install -y nodejs
fi
# Python packages in a venv (openpyxl is pinned: the export pins docProps/app.xml as written by openpyxl 3.1.5)
python3 -m venv "${CPS_VENV:-$HOME/cps-venv}"
"${CPS_VENV:-$HOME/cps-venv}/bin/pip" install --upgrade pip
"${CPS_VENV:-$HOME/cps-venv}/bin/pip" install 'openpyxl==3.1.5' 'xlrd==2.0.2' 'lxml>=5' 'pillow>=10'
# Chromium for source view images (Playwright)
if ! command -v npx >/dev/null; then echo "npx missing"; exit 1; fi
mkdir -p "$HOME/cps-playwright" && cd "$HOME/cps-playwright" && npm init -y >/dev/null && npm install playwright@1 >/dev/null && npx playwright install --with-deps chromium
echo "--- versions"
"${CPS_VENV:-$HOME/cps-venv}/bin/python" --version; node --version; soffice --version | head -1; pdftoppm -v 2>&1 | head -1
echo "Activate the venv before running CPS tools: source ${CPS_VENV:-$HOME/cps-venv}/bin/activate"
