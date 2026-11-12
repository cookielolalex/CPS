#!/bin/bash
# cps-vm-helper.v2.1 bootstrap after a reset or in a new operator chat (spec section 6.6, delta v2.1 2.10.3-2.10.7).
# Usage: CPS_VM_BASE=/tmp/cps bash /tmp/cps/repo/deploy/vm2/session_start.sh --commit <40hex> [--hint <seq6> --kit <hex12>]
# Every failure prints a full block (no set -e). The setup runs in the foreground (delta X.6.6: no detached process).
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
[ "$KIT" = none ] && HINT="" KIT=""
if [ -n "$HINT$KIT" ]; then
  [[ "$HINT" =~ ^[0-9]{6}$ && "$KIT" =~ ^[0-9a-f]{12}$ ]] || { echo "usage: --hint <seq6> --kit <hex12>"; exit 2; }
fi

# 1. HOME, BASE, TOOLS: absolute, no whitespace or quote; BASE is set (no default), outside HOME, not a git checkout
case "${HOME:-}" in /*) ;; *) stop SESSION_LAYOUT ;; esac
BASE="${CPS_VM_BASE:-}"
TOOLS="${CPS_TOOLS:-$HOME/cps-tools}"
case "$BASE" in /*) ;; *) stop SESSION_LAYOUT ;; esac
case "$TOOLS" in /*) ;; *) stop SESSION_LAYOUT ;; esac
case "$HOME$BASE$TOOLS" in *[[:space:]\'\"\\\$\`]*) stop SESSION_LAYOUT ;; esac
case "$BASE/" in "$HOME"/*) stop SESSION_LAYOUT ;; esac
[ -e "$BASE/.git" ] && stop SESSION_LAYOUT

# 2. this script runs from BASE/repo, a clean checkout; a git error is a STOP, never a pass (SAFE-06)
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd -P) || stop SESSION_LAYOUT
[ -d "$BASE/repo" ] && [ "$REPO" = "$(cd "$BASE/repo" && pwd -P)" ] || stop SESSION_LAYOUT
ST=$(git -C "$BASE/repo" status --porcelain --untracked-files=no 2>/dev/null) || stop SESSION_GIT_ERROR
[ -z "$ST" ] || stop SESSION_REPO_DIRTY

# 3. folders (never BASE/ledger)
mkdir -p "$BASE"/runtime "$BASE"/jobs "$BASE"/qual "$BASE"/transcripts "$BASE"/everyday_inputs "$BASE"/inbox \
  "$BASE"/outbox/v2 "$BASE"/outbox/journal "$BASE"/attest "$BASE"/deliver "$BASE"/tmp "$TOOLS"/var || stop SESSION_LAYOUT

# 6. the checked-out commit is the one named, before anything runs from it (S-08)
HEAD=$(git -C "$BASE/repo" rev-parse HEAD 2>/dev/null) || stop SESSION_GIT_ERROR
[ "$HEAD" = "$COMMIT" ] || stop SESSION_COMMIT_MISMATCH

# 5. no bytecode (S-07, SD-63), the launcher (atomic, 0755, no .pyc, BASE and TOOLS exported) and the hint
find "$REPO" -name __pycache__ -type d -prune -exec rm -rf {} + || stop SESSION_LAYOUT
printf '#!/bin/bash\nexport CPS_VM_BASE='\''%s'\'' CPS_TOOLS='\''%s'\''\n[ -f %q ] && . %q\nexec python3 -I -B -X pycache_prefix=/dev/null %q "$@"\n' \
  "$BASE" "$TOOLS" "$TOOLS/env.sh" "$TOOLS/env.sh" "$BASE/repo/deploy/vm2/vm2.py" > "$BASE/.vm.sh.tmp" && chmod 0755 "$BASE/.vm.sh.tmp" &&
  mv "$BASE/.vm.sh.tmp" "$BASE/vm.sh" || stop SESSION_LAYOUT
if [ -n "$HINT" ]; then
  printf '{"kit": "%s", "seq": %d}\n' "$KIT" "$((10#$HINT))" > "$BASE/outbox/v2/.HINT.json.tmp" &&
    mv "$BASE/outbox/v2/.HINT.json.tmp" "$BASE/outbox/v2/HINT.json" || stop SESSION_LAYOUT
else
  rm -f "$BASE/outbox/v2/HINT.json" || stop SESSION_LAYOUT
fi

# 4. setup once per boot and commit, in the foreground (SAFE-07 with the probe results: setup takes about 130 s, well
#    inside the polled foreground hold); the marker records the outcome for `go`
BOOT=$(cat "${CPS_VM_BOOT_ID_PATH:-/proc/sys/kernel/random/boot_id}") || stop SESSION_LAYOUT
OK="$TOOLS/var/cps_vm2_setup_ok"
if [ "$(cat "$OK" 2>/dev/null)" != "$BOOT $COMMIT" ]; then
  rm -f "$TOOLS/var/cps_vm2_setup_failed"
  UTC=$(date -u +%Y%m%dT%H%M%SZ)
  echo "CPSV-RUNNING kind=setup since=$(date -u +%Y-%m-%dT%H:%M:%SZ) max=600"
  LOG="$BASE/outbox/setup_$UTC.log"
  if ( CPS_WITH_LIBREOFFICE=host bash "$REPO/deploy/setup_vm_user.sh" && . "$TOOLS/env.sh" &&
       python3 -B "$REPO/deploy/check_env.py" --out "$BASE/outbox/ENV_REPORT_$UTC.json" | grep -q '"all_met": true'
     ) > "$LOG" 2>&1 < /dev/null; then
    echo "$BOOT $COMMIT" > "$TOOLS/var/cps_vm2_setup_ok" || stop SESSION_LAYOUT
  else
    echo "$BOOT $COMMIT" > "$TOOLS/var/cps_vm2_setup_failed" || stop SESSION_LAYOUT
  fi
fi

echo "CPSV-REPO commit=$COMMIT"
echo "$HDR state=SETUP"
echo "DO: RUN bash $BASE/vm.sh go"
exit 0
