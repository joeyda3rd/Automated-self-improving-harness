"""Command line interface.

    python3 -m ledger STORE ingest EVENTS.jsonl   # one JSON event per line
    python3 -m ledger STORE balances
    python3 -m ledger STORE statement ACCOUNT
"""
import argparse
import json
import sys

from .errors import LedgerError
from .reports import statement, trial_balance
from .service import Ledger


def _ingest(ledger, path, out):
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                print(f"line {n}: not JSON", file=out)
                return 1
            try:
                status = ledger.ingest(event)
            except LedgerError as exc:
                print(f"{event.get('key')} {type(exc).__name__}", file=out)
                return 1
            print(f"{event['key']} {status}", file=out)
    return 0


def main(argv=None, out=None):
    out = out or sys.stdout
    parser = argparse.ArgumentParser(prog="ledger")
    parser.add_argument("store")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest")
    p.add_argument("events")
    sub.add_parser("balances")
    p = sub.add_parser("statement")
    p.add_argument("account")
    args = parser.parse_args(argv)

    ledger = Ledger(args.store)
    if args.cmd == "ingest":
        return _ingest(ledger, args.events, out)
    if args.cmd == "balances":
        print(trial_balance(ledger), file=out)
        return 0
    print(statement(ledger, args.account), file=out)
    return 0
