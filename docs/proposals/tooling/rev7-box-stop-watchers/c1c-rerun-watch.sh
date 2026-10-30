#!/bin/bash
# Round-2 (c1c) C3 budget watcher: at most 1 validity rerun total across probe+fast,
# and at most 102 rev7 guests (81 + 21). Fires campaigns/<c>/STOP (runbook marker:
# campaigns/STOP or campaigns/<c>/STOP) on the 2nd INVALID attempt, before loop.py's 2nd rerun.
C=xswap-tcg-kbench-rev7-2026-10-29; P=/workspace/Swap-Next-main/campaigns/$C
STOPF=$P/STOP; B=$P/ledger/budget.json; E=$P/runs/evaluations
R=/workspace/runs/grok-cloud-tcg-rev7-20261029; LOG=$R/c1c-rerun-watch.log; OFF=$R/c1c-rerun-watch.off; M=$R/c1c-round.marker
CAP=102
echo "$(date '+%F %T %Z') rerun-watch start pid=$$ cap=$CAP max_invalid=1" >> $LOG
last=""
while [ ! -e "$OFF" ]; do
  out=$(python3 - "$E" "$M" "$B" <<'PY'
import json,os,sys,glob
E,M,B=sys.argv[1:4]; t=os.path.getmtime(M); inv=[]
for f in glob.glob(E+"/*/report.json"):
    if os.path.getmtime(os.path.dirname(f))<t: continue
    try: r=json.load(open(f))
    except Exception: continue
    inv+=[a["id"]+":"+str(a.get("invalid_reason")) for a in r.get("runs",[]) if a.get("status")=="INVALID"]
try: b=json.load(open(B)); tot=b.get("guests",0)+b.get("probe_guests",0)
except Exception: tot=-1
print(len(inv), tot, ";".join(inv))
PY
)
  read n tot ids <<< "$out"
  [ "$out" != "$last" ] && { echo "$(date '+%F %T %Z') invalid=$n rev7_total=$tot $ids" >> $LOG; last=$out; }
  why=""
  [ "${n:-0}" -ge 2 ] && why="INTENTIONAL C3 budget stop: 2nd INVALID attempt ($ids); coordinator limit is 1 rerun total in round 2"
  [ "${tot:-0}" -gt $CAP ] && why="INTENTIONAL C3 budget stop: rev7 guests $tot > round cap $CAP"
  if [ -n "$why" ] && [ ! -e $STOPF ]; then echo "$why" > $STOPF; echo "$(date '+%F %T %Z') STOP written: $why" >> $LOG; fi
  sleep 0.2
done
echo "$(date '+%F %T %Z') rerun-watch exit" >> $LOG
