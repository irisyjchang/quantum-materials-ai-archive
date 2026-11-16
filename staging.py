"""Staging tool for the Local Growth Log MVP.

    python staging.py risk-assess <packet.json> --source-pdf <local path> [--acceptance-run] <database.sqlite>
    python staging.py check-gate <drive_file_id> <file_hash> <database.sqlite>
    python staging.py stage-drafts <packet.json> [--acceptance-run] <database.sqlite>

Each command exits 0 on success and 1 on any failure, including bad arguments.
Command logic lives in staging_lib/; this file only parses arguments.
"""

import argparse
import sys

from staging_lib import cmd_check_gate, cmd_risk_assess, cmd_stage_drafts


class ArgumentParser(argparse.ArgumentParser):
    """Argument errors exit with code 1 (argparse's default is 2)."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def build_parser():
    parser = ArgumentParser(prog="staging.py", description="Local Growth Log MVP staging tool.")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=ArgumentParser)

    risk = commands.add_parser("risk-assess", help="register a source PDF version and record its assessment result")
    risk.add_argument("packet", help="risk JSON packet")
    risk.add_argument("--source-pdf", required=True, help="local path of the source PDF that was assessed")
    risk.add_argument("--acceptance-run", action="store_true", help="allow a reserved acceptance PDF (Test only)")
    risk.add_argument("database", help="SQLite database (test.sqlite or archive.sqlite)")
    risk.set_defaults(run=cmd_risk_assess.run)

    gate = commands.add_parser("check-gate", help="read-only check that extraction may proceed")
    gate.add_argument("drive_file_id")
    gate.add_argument("file_hash")
    gate.add_argument("database")
    gate.set_defaults(run=cmd_check_gate.run)

    drafts = commands.add_parser("stage-drafts", help="stage extracted drafts as Pending review")
    drafts.add_argument("packet", help="extraction JSON packet")
    drafts.add_argument("--acceptance-run", action="store_true", help="allow a reserved acceptance PDF (Test only)")
    drafts.add_argument("database", help="SQLite database (test.sqlite or archive.sqlite)")
    drafts.set_defaults(run=cmd_stage_drafts.run)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
