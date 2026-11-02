"""CLI: python -m jpnumground SOURCE.txt SUMMARY.txt     (exit 1 when a fact is unsupported)
     python -m jpnumground --extract FILE.txt"""
import argparse
import json
import sys

from .ground import check, extract


def main(argv=None):
    p = argparse.ArgumentParser(prog="jpnumground", description="Check numbers and dates in a Japanese summary against its source.")
    p.add_argument("source", nargs="?", help="source text file")
    p.add_argument("summary", nargs="?", help="summary text file (- for stdin)")
    p.add_argument("--extract", metavar="FILE", help="only list the quantities in FILE")
    p.add_argument("--tolerance", type=float, default=0.1)
    a = p.parse_args(argv)
    for s in (sys.stdin, sys.stdout):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")

    def read(path):
        return sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()

    if a.extract:
        print(json.dumps(extract(read(a.extract)), ensure_ascii=False, indent=2))
        return 0
    if not (a.source and a.summary):
        p.error("give SOURCE and SUMMARY files, or --extract FILE")
    r = check(read(a.source), read(a.summary), a.tolerance)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
