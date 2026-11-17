"""Explicit manual refresh/rebuild/import. Does not schedule jobs or call AWS."""
import argparse
from datetime import datetime,timedelta
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--refresh',action='store_true',help='Fetch public source URLs before building')
p.add_argument('--as-of',default=datetime.now(ZoneInfo('America/New_York')).date().isoformat())
p.add_argument('--window-start')
p.add_argument('--orders',type=Path)
p.add_argument('--target-db',type=Path)
a=p.parse_args()
if a.refresh: subprocess.run([sys.executable,str(ROOT/'src/collect_public.py')],check=True)
build=[sys.executable,str(ROOT/'src/build_monitor.py'),'--as-of',a.as_of]
if a.window_start: build+=['--window-start',a.window_start]
if a.orders: build+=['--orders',str(a.orders.resolve())]
subprocess.run(build,check=True)
command=[sys.executable,str(ROOT/'src/import_monitor_db.py')]
if a.target_db: command+=['--target-db',str(a.target_db.resolve())]
subprocess.run(command,check=True)
