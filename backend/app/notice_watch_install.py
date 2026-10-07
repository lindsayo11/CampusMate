"""Explicit one-shot installation for the production collection profile."""
import argparse
import json
from .database import SessionLocal
from .migrate import check_schema
from .notice_watch import install


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actor',required=True)
    args=parser.parse_args()
    if not args.actor.strip() or len(args.actor)>80:
        parser.error('Provide a nonempty operator name of at most 80 characters')
    check_schema()
    with SessionLocal() as db:
        print(json.dumps(install(db,args.actor)))


if __name__=='__main__':
    main()
