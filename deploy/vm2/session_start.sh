#!/bin/bash
# cps-vm-helper.v2 bootstrap after a reset or in a new operator chat (spec section 6.6).
# Usage: bash ~/cps/repo/deploy/vm2/session_start.sh --commit <40 hex> [--hint <seq6> --kit <hex12>]
# Every failure prints a full block (no set -e). The setup runs detached, never in the foreground (SAFE-07).
umask 022
HDR='CPSV series=none head=000000 kit=none at=000000-0000-000000 mode=setup'
stop() { echo "$HDR state=STOP"; echo "DO: STOP $1 HANDBACK C"; exit 3; }
COMMIT="" HINT="" KIT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --commit) COMMIT="${2-}"; shift 2 || exit 2 ;;
    --hint) HINT="${2-}"; shift 2 || exit 2 ;;
    --kit) KIT="${2-}"; shift 2 || exit 2 ;;
    *) echo "usage: session_start.sh --commit <40 hex> [--hint <seq6> --kit <hex12>]"; exit 2 ;;
  esac
done
[[ "$COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "usage: --commit <40 hex>"; exit 2; }
if [ -n "$HINT$KIT" ]; then
  [[ "$HINT" =~ ^[0-9]{6}$ && "$KIT" =~ ^[0-9a-f]{12}$ ]] || { echo "usage: --hint <seq6> --kit <hex12>"; exit 2; }
fi

# 1. HOME, BASE, TOOLS: absolute, no whitespace; BASE is not a git checkout
case "${HOME:-}" in /*) ;; *) stop SESSION_LAYOUT ;; esac
BASE="${CPS_VM_BASE:-$HOME/cps}"
TOOLS="${CPS_TOOLS:-$HOME/cps-tools}"
case "$BASE" in /*) ;; *) stop SESSION_LAYOUT ;; esac
case "$TOOLS" in /*) ;; *) stop SESSION_LAYOUT ;; esac
case "$HOME$BASE$TOOLS" in *[[:space:]]*) stop SESSION_LAYOUT ;; esac
[ -e "$BASE/.git" ] && stop SESSION_LAYOUT

# 2. this script runs from BASE/repo, a clean checkout; a git error is a STOP, never a pass (SAFE-06)
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd -P) || stop SESSION_LAYOUT
[ -d "$BASE/repo" ] && [ "$REPO" = "$(cd "$BASE/repo" && pwd -P)" ] || stop SESSION_LAYOUT
ST=$(git -C "$BASE/repo" status --porcelain --untracked-files=no 2>/dev/null) || stop SESSION_GIT_ERROR
[ -z "$ST" ] || stop SESSION_REPO_DIRTY

# 3. folders (never BASE/ledger)
mkdir -p "$BASE"/runtime "$BASE"/jobs "$BASE"/qual "$BASE"/transcripts "$BASE"/everyday_inputs "$BASE"/inbox \
  "$BASE"/outbox/v2 "$BASE"/outbox/journal "$BASE"/attest "$BASE"/deliver "$TOOLS"/var || stop SESSION_LAYOUT

# 4. setup once per boot and commit, detached; the detached job writes the marker (or the failure marker)
BOOT=$(cat "${CPS_VM_BOOT_ID_PATH:-/proc/sys/kernel/random/boot_id}") || stop SESSION_LAYOUT
UTC=$(date -u +%Y%m%dT%H%M%SZ)
OK="$TOOLS/var/cps_vm2_setup_ok"
if [ "$(cat "$OK" 2>/dev/null)" != "$BOOT $COMMIT" ] && [ ! -f "$BASE/outbox/SETUP.json.$BOOT" ]; then
  rm -f "$TOOLS/var/cps_vm2_setup_failed"
  LOG="$BASE/outbox/setup_$UTC.log"
  setsid nohup bash -c 'if CPS_WITH_LIBREOFFICE=host bash "$1/deploy/setup_vm_user.sh" && . "$2/env.sh" &&
      python3 "$1/deploy/check_env.py" --out "$3" | grep -q "\"all_met\": true"; then
      echo "$4 $5" > "$2/var/cps_vm2_setup_ok"; else echo "$4 $5" > "$2/var/cps_vm2_setup_failed"; fi' \
    _ "$REPO" "$TOOLS" "$BASE/outbox/ENV_REPORT_$UTC.json" "$BOOT" "$COMMIT" > "$LOG" 2>&1 < /dev/null &
  PID=$!
  printf '{"boot_id": "%s", "log": "%s", "pid": %d, "started_utc": "%s"}\n' "$BOOT" "$LOG" "$PID" "$UTC" \
    > "$BASE/outbox/.SETUP.json.tmp" && mv "$BASE/outbox/.SETUP.json.tmp" "$BASE/outbox/SETUP.json" || stop SESSION_LAYOUT
  : > "$BASE/outbox/SETUP.json.$BOOT"
fi

# 5. the launcher (atomically, 0755) and the hint
printf '#!/bin/bash\n[ -f %q ] && . %q\nexec python3 -I -B %q "$@"\n' "$TOOLS/env.sh" "$TOOLS/env.sh" \
  "$BASE/repo/deploy/vm2/vm2.py" > "$BASE/.vm.sh.tmp" && chmod 0755 "$BASE/.vm.sh.tmp" &&
  mv "$BASE/.vm.sh.tmp" "$BASE/vm.sh" || stop SESSION_LAYOUT
if [ -n "$HINT" ]; then
  printf '{"kit": "%s", "seq": %d}\n' "$KIT" "$((10#$HINT))" > "$BASE/outbox/v2/.HINT.json.tmp" &&
    mv "$BASE/outbox/v2/.HINT.json.tmp" "$BASE/outbox/v2/HINT.json" || stop SESSION_LAYOUT
fi

# 6. the checked-out commit is the one named
HEAD=$(git -C "$BASE/repo" rev-parse HEAD 2>/dev/null) || stop SESSION_GIT_ERROR
[ "$HEAD" = "$COMMIT" ] || stop SESSION_COMMIT_MISMATCH
echo "CPSV-REPO commit=$COMMIT"
echo "$HDR state=SETUP"
echo "DO: RUN bash $BASE/vm.sh go"
exit 0
