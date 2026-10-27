#!/usr/bin/env bash
# NO-ROOT mode: check, from the PC, everything the server needs to keep running by itself
# (Android version, Termux:Boot, battery restrictions, Shizuku, processes, free space...).
# Read-only. Each problem comes with what to do. Same as running ~/server/doctor.sh in Termux.
#   tools/noroot-doctor.sh
set -uo pipefail
source "$(dirname "$0")/noroot-common.sh"
need_phone
ph 'bash ~/server/doctor.sh' </dev/null
RC=$?
[ $RC = 127 ] && echo "~/server/doctor.sh is missing: run tools/noroot-install.sh scripts (or tools/noroot-deploy.sh)."
exit $RC
