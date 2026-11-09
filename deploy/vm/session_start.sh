#!/bin/bash
# CPS session start on the Dot's VM, after every reset and at the start of every new chat (deploy/vm/README.md, S4).
# Usage: bash ~/cps/repo/deploy/vm/session_start.sh --operator-model "<your model name>"
# It checks the layout and the clean checkout, runs the no-root setup once per boot (CPS_WITH_LIBREOFFICE=host),
# checks the environment, writes BASE/vm.sh and hands over to "cps_vm.py session" (kit, listings, fingerprint, restore,
# SESSION note). Exit 10 means: do the UPLOAD lines it printed, then its SAVE_DRIVE_LISTING and DOWNLOAD lines, then run
# this command again.
set -euo pipefail
umask 022

OPERATOR_MODEL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --operator-model) OPERATOR_MODEL="${2-}"; shift 2 || shift ;;
    *) echo "RESULT: {\"status\":\"REFUSED\",\"code\":\"SESSION_USAGE\"}"; echo "REFUSED: SESSION_USAGE"; exit 2 ;;
  esac
done

refuse() { echo "RESULT: {\"status\":\"REFUSED\",\"code\":\"$1\"}"; echo "REFUSED: $1"; exit 4; }

# 1. HOME, BASE, TOOLS
case "${HOME:-}" in
  /*) ;;
  *) refuse SESSION_HOME ;;
esac
case "$HOME" in *[[:space:]]*) refuse SESSION_HOME ;; esac
BASE="${CPS_VM_BASE:-$HOME/cps}"
TOOLS="${CPS_TOOLS:-$HOME/cps-tools}"
case "$BASE" in /*) ;; *) refuse SESSION_HOME ;; esac
case "$BASE$TOOLS" in *[[:space:]]*) refuse SESSION_HOME ;; esac
if [ -e "$BASE/.git" ]; then refuse SESSION_BASE_IS_REPOSITORY; fi
case "$OPERATOR_MODEL" in
  ""|"<"*|*"'"*) refuse SESSION_OPERATOR_MODEL ;;
esac
if [ -z "${OPERATOR_MODEL//[[:space:]]/}" ]; then refuse SESSION_OPERATOR_MODEL; fi

# 2. this script runs from BASE/repo, a clean checkout
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
if [ ! -d "$BASE/repo" ] || [ "$REPO" != "$(cd "$BASE/repo" && pwd -P)" ]; then refuse SESSION_REPO_NOT_AT_BASE; fi
if [ -n "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]; then refuse SESSION_REPO_DIRTY; fi

# 3. folders (never BASE/ledger). Leftovers of a killed earlier attempt (staging folders, outbox temporary files) are
# removed by "cps_vm.py session" under the helper lock, never here: a detached worker may still be writing (T-23).
mkdir -p "$BASE"/runtime "$BASE"/jobs "$BASE"/transcripts "$BASE"/outbox "$BASE"/qual "$BASE"/inbox "$BASE"/everyday_inputs

# 4. boot, commit, marker
BOOT=$(cat "${CPS_VM_BOOT_ID_PATH:-/proc/sys/kernel/random/boot_id}")
COMMIT=$(git -C "$REPO" rev-parse HEAD)
MARK="$TOOLS/var/cps_vm_session_ok"
UTC=$(date -u +%Y%m%dT%H%M%SZ)

# 5./6. setup and the environment check, once per boot and commit
if [ -f "$TOOLS/env.sh" ] && [ -f "$MARK" ] && [ "$(cat "$MARK")" = "$BOOT $COMMIT" ]; then
  echo "setup: already done in this boot"
else
  LOG="$BASE/outbox/setup_$UTC.log"
  if ! CPS_WITH_LIBREOFFICE=host bash "$REPO/deploy/setup_vm_user.sh" > "$LOG" 2>&1; then
    tail -n 40 "$LOG" || true
    echo "RESULT: {\"status\":\"STOP\",\"code\":\"SETUP_FAILED\"}"
    echo "UPLOAD $LOG -> CPS/reports"
    echo "STOP: SETUP_FAILED the no-root setup failed: upload the log and hand back case C"
    exit 3
  fi
  # shellcheck disable=SC1091
  . "$TOOLS/env.sh"
  OUT=$(python3 "$REPO/deploy/check_env.py" --out "$BASE/outbox/ENV_REPORT_$UTC.json") || true
  case "$OUT" in
    *'"all_met": true'*) ;;
    *)
      echo "RESULT: {\"status\":\"STOP\",\"code\":\"CHECK_ENV_FAILED\"}"
      echo "UPLOAD $BASE/outbox/ENV_REPORT_$UTC.json -> CPS/reports"
      echo "STOP: CHECK_ENV_FAILED the environment check failed: upload the report and hand back case C"
      exit 3 ;;
  esac
  mkdir -p "$TOOLS/var"
  printf '%s %s' "$BOOT" "$COMMIT" > "$MARK.new"
  mv "$MARK.new" "$MARK"
fi

# 7. the launcher BASE/vm.sh ($V in every printed RUN line)
cat > "$BASE/vm.sh.new" <<EOF
#!/bin/bash
. "$TOOLS/env.sh"
export TMPDIR=/tmp
exec python3 -I -B "$BASE/repo/deploy/vm/cps_vm.py" "\$@"
EOF
chmod 0755 "$BASE/vm.sh.new"
mv "$BASE/vm.sh.new" "$BASE/vm.sh"

# 8. the session itself (kit, listings, fingerprint, restore, SESSION note)
exec "$BASE/vm.sh" session --inbox "$BASE/inbox" --operator-model "$OPERATOR_MODEL"
