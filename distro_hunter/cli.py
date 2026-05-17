from __future__ import annotations

import argparse
import csv
import io
import json
from contextlib import nullcontext
from pathlib import Path

from distro_hunter.backup import create_source_backup
from distro_hunter.config import load_settings
from distro_hunter.core import (
    DistroHunter,
    discovery_rows,
    doctor_rows,
    doctor_summary,
    validate_rows,
    validate_summary,
)
from distro_hunter.journal import RunJournal
from distro_hunter.models import VALID_STATUS_NO_RECORD, VALID_STATUS_UP_TO_DATE
from distro_hunter.plugin_generator import (
    build_generated_plugin,
    review_generated_plugin,
    validate_generated_plugin,
    write_generated_plugin,
    write_generated_test,
)
from distro_hunter.plugin_loader import DiscoveryContext
from distro_hunter.run_lock import RunLockError, default_lock_path, run_lock


LOCKED_COMMANDS = {"doctor", "health", "discover", "run", "sync", "tui", "validate"}
REPORT_FIELDS = [
    "plugin_slug",
    "plugin_name",
    "plugin_family",
    "plugin_architecture",
    "plugin_edition_type",
    "plugin_source_kind",
    "plugin_ventoy_subdir",
    "selection_version",
    "selection_filename",
    "selection_url",
    "selection_selected_at",
    "download_path",
    "download_filename",
    "download_downloaded",
    "download_skipped_reason",
    "download_updated_at",
    "remote_url",
    "remote_final_url",
    "remote_filename",
    "remote_size",
    "remote_etag",
    "remote_last_modified",
    "checksum_status",
    "checksum_algorithm",
    "checksum_expected",
    "checksum_actual",
    "checksum_source",
    "health_healthy",
    "health_last_status",
    "health_last_checked_at",
    "health_last_success_at",
    "health_last_failure_at",
    "health_failure_count",
    "health_last_error",
]


def render_report(records: list[dict[str, object]], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(records, indent=2)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=REPORT_FIELDS)
    writer.writeheader()
    for record in records:
        writer.writerow(record)
    return buffer.getvalue().rstrip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discover Linux ISOs, download them, and sync to Ventoy.")
    parser.add_argument("--config", default="config.example.json", help="Path to the JSON config file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-plugins", help="List built-in and external plugins.")
    subparsers.add_parser("backup", help="Create a timestamped source backup zip.")
    subparsers.add_parser("sync", help="Copy local library files to Ventoy without running discovery.")
    report = subparsers.add_parser("report", help="Export the current selection, download, and health snapshot.")
    report.add_argument("--plugin", action="append", default=[], help="Only include selected plugin slug(s).")
    report.add_argument("--format", choices=("json", "csv"), default="json", help="Output format.")
    report.add_argument("--output", help="Optional file path for the exported report.")
    doctor = subparsers.add_parser("doctor", aliases=["health"], help="Run health checks against enabled plugins.")
    doctor.add_argument("--plugin", action="append", default=[], help="Only run selected plugin slug(s).")
    subparsers.add_parser("tui", help="Launch the interactive terminal UI.")

    discover = subparsers.add_parser("discover", help="Discover the latest candidate from each enabled plugin.")
    discover.add_argument("--plugin", action="append", default=[], help="Only run selected plugin slug(s).")

    run = subparsers.add_parser("run", help="Discover, download, and sync.")
    run.add_argument("--plugin", action="append", default=[], help="Only run selected plugin slug(s).")
    run.add_argument("--dry-run", action="store_true", help="Show what would happen without downloading or copying.")
    run.add_argument("--skip-sync", action="store_true", help="Do not copy files to a Ventoy USB.")

    validate = subparsers.add_parser("validate", help="Check downloaded ISOs against current plugin discoveries.")
    validate.add_argument("--plugin", action="append", default=[], help="Only validate selected plugin slug(s).")

    generate = subparsers.add_parser("generate-plugin", help="Generate a plugin from a discovered page pattern.")
    generate.add_argument("--name", required=True, help="Plugin display name.")
    generate.add_argument("--page-url", required=True, help="Page to scan for links.")
    generate.add_argument("--include", action="append", default=[], help="Keyword that must appear in a link.")
    generate.add_argument("--exclude", action="append", default=[], help="Keyword to reject from a link.")
    generate.add_argument("--preview", action="store_true", help="Show the inferred pattern and sample matches without writing files.")
    generate.add_argument("--validate", action="store_true", help="Run the generated plugin against the current page before writing it.")
    generate.add_argument("--review", action="store_true", help="Print review warnings and tightening suggestions for the generated plugin.")
    generate.add_argument("--with-test", action="store_true", help="Also write a starter generated test file.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    journal = RunJournal(settings.logging)
    command_guard = nullcontext()
    if args.command in LOCKED_COMMANDS:
        command_guard = run_lock(default_lock_path(settings.state_file), args.command)

    try:
        with command_guard:
            if args.command == "generate-plugin":
                context = DiscoveryContext(settings)
                preview = build_generated_plugin(
                    context=context,
                    name=args.name,
                    page_url=args.page_url,
                    include=args.include,
                    exclude=args.exclude,
                )
                print(f"Pattern: {preview.pattern}")
                print(f"Regex: {preview.regex}")
                for example in preview.examples:
                    print(f"Example: {example}")

                validated_candidates = None
                if args.validate:
                    validated_candidates = validate_generated_plugin(preview, context)
                    print(f"Validated candidates: {len(validated_candidates)}")
                    for candidate in validated_candidates[:5]:
                        print(f"Candidate: {candidate.url}")

                if args.review:
                    review = review_generated_plugin(preview, validated_candidates)
                    print("Review:")
                    for warning in review.warnings:
                        print(f"Warning: {warning}")
                    for note in review.notes:
                        print(f"Note: {note}")
                    for suggestion in review.suggestions:
                        print(f"Suggestion: {suggestion}")

                if args.preview:
                    journal.info(f"Previewed generated plugin: {preview.slug}")
                    return 0

                path = write_generated_plugin(preview, settings.generator.output_dir)
                print(f"Generated plugin: {path}")
                journal.info(f"Generated plugin: {path}")
                if args.with_test:
                    test_path = write_generated_test(preview, path, settings.generator.test_output_dir)
                    print(f"Generated test: {test_path}")
                    journal.info(f"Generated test: {test_path}")
                return 0

            if args.command == "backup":
                path = create_source_backup(settings.config_path.parent)
                print(f"Backup created: {path}")
                journal.info(f"Backup created: {path}")
                return 0

            if args.command == "tui":
                from distro_hunter.tui import run_tui

                run_tui(str(settings.config_path))
                return 0

            hunter = DistroHunter(settings)
            hunter.journal.info(f"Starting command: {args.command}")
            for warning in hunter.startup_warnings():
                message = f"Startup warning: {warning}"
                print(message)
                hunter.journal.warning(message)

            if args.command == "list-plugins":
                for plugin in hunter.list_plugins():
                    message = f"{plugin.slug}: {plugin.name}"
                    print(message)
                    hunter.journal.info(message)
                return 0

            if args.command == "sync":
                drive, copied = hunter.sync_ventoy()
                if drive is None:
                    message = "Ventoy drive not detected; local library was not copied."
                    print(message)
                    hunter.journal.warning(message)
                elif copied:
                    message = f"Ventoy synced to {drive} with {len(copied)} copied file(s)."
                    print(message)
                    hunter.journal.info(message)
                else:
                    message = f"Ventoy detected at {drive}; nothing needed copying."
                    print(message)
                    hunter.journal.info(message)
                hunter.journal.info(f"Finished command: {args.command}")
                return 0

            if args.command == "validate":
                selected = set(args.plugin) if getattr(args, "plugin", None) else None
                results = hunter.validate(selected_plugins=selected)
                for row in validate_rows(results):
                    print(row)
                    hunter.journal.info(row)
                summary = validate_summary(results)
                print(summary)
                hunter.journal.info(summary)
                hunter.journal.info(f"Finished command: {args.command}")
                unhealthy = [r for r in results if r.status not in (VALID_STATUS_UP_TO_DATE, VALID_STATUS_NO_RECORD)]
                return 0 if not unhealthy else 1

            selected = set(args.plugin) if getattr(args, "plugin", None) else None
            if args.command == "report":
                report_text = render_report(hunter.report_records(selected_plugins=selected), args.format)
                if args.output:
                    output_path = Path(args.output).resolve()
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(report_text + ("\n" if report_text and not report_text.endswith("\n") else ""), encoding="utf-8")
                    message = f"Report written: {output_path}"
                    print(message)
                    hunter.journal.info(message)
                else:
                    print(report_text)
                    hunter.journal.info(f"Report generated in {args.format} format.")
                hunter.journal.info(f"Finished command: {args.command}")
                return 0

            if args.command in {"doctor", "health"}:
                results = hunter.doctor(selected_plugins=selected)
                for row in doctor_rows(results):
                    print(row)
                    hunter.journal.info(row)
                summary = doctor_summary(results)
                print(summary)
                if all(result.healthy for result in results):
                    hunter.journal.info(summary)
                else:
                    hunter.journal.warning(summary)
                hunter.journal.info(f"Finished command: {args.command}")
                return 0 if all(result.healthy for result in results) else 1

            discoveries = hunter.discover(selected_plugins=selected)
            for row in discovery_rows(discoveries):
                print(row)
                hunter.journal.info(row)

            if args.command == "discover":
                return 0

            download_results = hunter.download_discoveries(discoveries, dry_run=args.dry_run)
            for result in download_results:
                if result.downloaded:
                    message = f"{result.plugin_slug}: downloaded {result.path}"
                    print(message)
                    hunter.journal.info(message)
                else:
                    message = f"{result.plugin_slug}: skipped {result.skipped_reason}"
                    print(message)
                    hunter.journal.warning(message)
                if result.pruned_paths:
                    pruned = ", ".join(path.name for path in result.pruned_paths)
                    prune_message = f"{result.plugin_slug}: pruned {len(result.pruned_paths)} old file(s): {pruned}"
                    print(prune_message)
                    hunter.journal.info(prune_message)
                if result.checksum and result.checksum.status == "verified":
                    checksum_message = f"{result.plugin_slug}: checksum verified ({result.checksum.algorithm})"
                    print(checksum_message)
                    hunter.journal.info(checksum_message)
                elif result.checksum and result.checksum.status == "unavailable" and settings.download.verify_checksums:
                    checksum_message = f"{result.plugin_slug}: checksum unavailable"
                    print(checksum_message)
                    hunter.journal.warning(checksum_message)
                if not args.skip_sync and not args.dry_run and result.path and result.path.exists():
                    drive, copied = hunter.sync_download_result(result)
                    if drive is not None and copied:
                        sync_message = f"{result.plugin_slug}: synced {len(copied)} file(s) to Ventoy at {drive}"
                        print(sync_message)
                        hunter.journal.info(sync_message)

            if not args.skip_sync and not args.dry_run:
                drive, copied = hunter.sync_ventoy()
                if drive is None:
                    message = "Ventoy drive not detected; downloads remain in the local library."
                    print(message)
                    hunter.journal.warning(message)
                elif copied:
                    message = f"Ventoy synced to {drive} with {len(copied)} copied file(s)."
                    print(message)
                    hunter.journal.info(message)
                else:
                    message = f"Ventoy detected at {drive}; nothing needed copying."
                    print(message)
                    hunter.journal.info(message)
            hunter.journal.info(f"Finished command: {args.command}")
            return 0
    except RunLockError as exc:
        message = str(exc)
        print(message)
        journal.warning(message)
        return 1
