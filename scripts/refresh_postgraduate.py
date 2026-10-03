"""Configure continuous discovery and process due persistent jobs.
The regular app.worker polls columns every 12h and details every 24h.
"""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.database import SessionLocal
from app.migrate import check_schema
from app.notice_watch import install, monitor_status, run_cycle

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install',action='store_true')
    parser.add_argument('--actor',default='local-operator')
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--batches',type=int,default=1,choices=range(1,51))
    args=parser.parse_args()
    check_schema()
    if args.install:
        with SessionLocal() as db: print(json.dumps(install(db,args.actor)))
    if args.run:
        for _ in range(args.batches): print(json.dumps(run_cycle(),ensure_ascii=False,default=str),flush=True)
    with SessionLocal() as db: print(json.dumps(monitor_status(db),ensure_ascii=False,default=str))

if __name__=='__main__':main()
