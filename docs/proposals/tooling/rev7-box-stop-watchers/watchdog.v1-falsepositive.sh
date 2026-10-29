#!/bin/bash
# Usage: watchdog.sh <max_probe> <max_fast>   (step plan caps; hard cap rev7 total 111 = 120 global - 9 rev6)
C=xswap-tcg-kbench-rev7-2026-10-29
P=/workspace/Swap-Next-main/campaigns/$C; STOPF=$P/STOP; B=$P/ledger/budget.json
R=/workspace/runs/grok-cloud-tcg-rev7-20261029; LOG=$R/watchdog.log; OFF=$R/watchdog.off
MAXP=$1; MAXF=$2; HARD=111; seen=""
echo "$(date '+%F %T %Z') watchdog start pid=$$ maxprobe=$MAXP maxfast=$MAXF hard_total=$HARD" >> $LOG
while [ ! -e "$OFF" ]; do
  pids=$(pgrep -f '^qemu-system'); n=$(echo -n "$pids" | grep -c .); why=""
  [ "$n" -gt 1 ] && why="$n QEMU processes coexist"
  for p in $pids; do c=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null)
    case " $seen " in *" $p "*) ;; *) seen="$seen $p"; echo "$(date '+%F %T %Z') qemu pid $p: $(echo "$c" | grep -oE -- '-accel [^ ]+')" >> $LOG;; esac
    if echo "$c" | grep -qi 'kvm' || ! echo "$c" | grep -q -- '-accel tcg'; then why="non-TCG QEMU pid $p: $c"; kill -TERM $p; fi; done
  if [ -f $B ]; then read pg fg < <(python3 -c "import json;b=json.load(open('$B'));print(b.get('probe_guests',0),b.get('guests',0))" 2>/dev/null)
    if [ -n "$pg" ]; then
      [ "$pg" -gt "$MAXP" ] && why="probe guests $pg > plan $MAXP"
      [ "$fg" -gt "$MAXF" ] && why="fast guests $fg > plan $MAXF"
      [ $((pg+fg)) -gt $HARD ] && why="rev7 total $((pg+fg)) > $HARD (global $((pg+fg+9)) > 120)"
    fi; fi
  if [ -n "$why" ] && [ ! -e $STOPF ]; then touch $STOPF; echo "$(date '+%F %T %Z') STOP touched: $why" >> $LOG; fi
  sleep 1
done
echo "$(date '+%F %T %Z') watchdog exit (watchdog.off)" >> $LOG
