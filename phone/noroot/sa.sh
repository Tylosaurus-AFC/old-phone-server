#!/data/data/com.termux/files/usr/bin/bash
# sa.sh 'commands' -> runs them as Android's "shell" user (through Shizuku/rish) and prints
# their output. rish randomly loses lines of output and does not return the exit code, so
# the shell side writes to a file on shared storage (one per call) and it is read from here.
# `cmd` commands (settings, pm, cmd wifi...) fail if their output is that file: put them
# inside $(...) or a pipe with 2>&1. rish reads stdin: inside a script it needs </dev/null
# (otherwise it eats the rest of the script).
export RISH_APPLICATION_ID=com.termux     # rish only sets it if empty
X=/sdcard/Download/.srv-shell-$$-$RANDOM
rm -f $X
timeout ${SA_TIMEOUT:-30} $HOME/server/rish -c "( $1 ) > $X.tmp 2>&1 </dev/null; mv $X.tmp $X" </dev/null >/dev/null 2>&1
n=0
while [ ! -f $X ] && [ $n -lt 20 ]; do sleep 0.5; n=$((n + 1)); done
cat $X 2>/dev/null
rm -f $X $X.tmp
