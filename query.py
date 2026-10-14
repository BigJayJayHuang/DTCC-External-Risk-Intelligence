"""Read-only command-line queries for teammates; Python standard library only."""
import argparse, csv, json, sqlite3, sys
from pathlib import Path
import db

def readonly(path):
    c=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    c.execute('PRAGMA query_only=ON');return c

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,default=db.DEFAULT_DB)
    p.add_argument('--sql',default='SELECT dataset_id,count(*) AS records,max(measurement_date) AS latest_period FROM records GROUP BY dataset_id ORDER BY dataset_id')
    p.add_argument('--csv',action='store_true');args=p.parse_args();db.restore(args.db)
    with readonly(args.db) as c:
        result=c.execute(args.sql);columns=[x[0] for x in result.description]
        if args.csv:
            w=csv.writer(sys.stdout);w.writerow(columns);w.writerows(result)
        else:print(json.dumps([dict(zip(columns,r)) for r in result],ensure_ascii=False,indent=2))
