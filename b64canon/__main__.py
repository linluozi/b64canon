"""Command line interface: ``python -m b64canon``.

Exit codes
----------
0   the input is canonical base64
1   the input is not canonical base64
2   usage or I/O error
"""

from __future__ import annotations

import argparse
import json
import sys

from . import REASONS, diagnose, normalize


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="b64canon",
        description="Check whether base64 input is in strict RFC 4648 canonical form.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        default="-",
        help="file to read, or '-' / omitted to read standard input",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print a machine readable diagnostic",
    )
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="print the canonical spelling instead of a verdict",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.file == "-":
            data = sys.stdin.buffer.read()
        else:
            with open(args.file, "rb") as handle:
                data = handle.read()
    except OSError as exc:
        print(f"b64canon: {exc}", file=sys.stderr)
        return 2

    if args.normalize:
        try:
            print(normalize(data))
        except ValueError as exc:
            print(f"b64canon: {exc}", file=sys.stderr)
            return 1
        return 0

    diag = diagnose(data)
    if args.json:
        print(
            json.dumps(
                {
                    "ok": diag.ok,
                    "reason": diag.reason,
                    "index": diag.index,
                    "detail": diag.detail,
                    "message": REASONS[diag.reason],
                }
            )
        )
    elif diag.ok:
        print("ok: canonical base64")
    else:
        print(str(diag), file=sys.stderr)
    return 0 if diag.ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
