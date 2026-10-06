"""
Command-line runner for Smartlead Weekly Mailbox Analytics.

Usage:
    python run.py --test-smartlead
    python run.py --generate-weekly-report
    python run.py --generate-report --start-date 2026-09-21 --end-date 2026-09-27
    python run.py --server          (starts uvicorn)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smartlead Weekly Mailbox Analytics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py --test-smartlead
  python run.py --generate-weekly-report
  python run.py --generate-report --start-date 2026-09-21 --end-date 2026-09-27
  python run.py --server
""",
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--test-smartlead",
        action="store_true",
        help="Test Smartlead API connection and print safe diagnostics",
    )
    mode.add_argument(
        "--generate-weekly-report",
        action="store_true",
        help="Generate report for the previous calendar week (Mon–Sun)",
    )
    mode.add_argument(
        "--generate-report",
        action="store_true",
        help="Generate report for a custom date range",
    )
    mode.add_argument(
        "--server",
        action="store_true",
        help="Start the FastAPI server via uvicorn",
    )

    parser.add_argument(
        "--include-archived",
        action="store_true",
        help="Include ARCHIVED and DRAFTED campaigns (default: False, only active/paused/stopped)",
    )
    parser.add_argument(
        "--only-active",
        action="store_true",
        help="Filter ONLY campaigns that are currently ACTIVE (skips paused, stopped, completed)",
    )
    parser.add_argument(
        "--status-filter",
        metavar="STATUS",
        help="Filter campaigns by specific status (e.g. ACTIVE, PAUSED)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="Override max API concurrency (default: from settings, 2)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable detailed progress logging (INFO level)",
    )
    parser.add_argument(
        "--start-date",
        metavar="YYYY-MM-DD",
        help="Report start date (required with --generate-report)",
    )
    parser.add_argument(
        "--end-date",
        metavar="YYYY-MM-DD",
        help="Report end date (required with --generate-report)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Server host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port (default: 8000)",
    )

    return parser.parse_args()


async def cmd_test_smartlead() -> None:
    """Verify Smartlead API connection safely (never prints the key)."""
    from app.clients.smartlead_client import SmartleadApiClient
    from app.clients.smartlead_exceptions import SmartleadAuthError, SmartleadError
    from app.core.config import get_settings
    from app.core.security import mask_api_key

    settings = get_settings()
    print("\n=== Smartlead Connection Test ===")
    print(f"API Base URL : {settings.api_base_url}")
    print(f"API Key      : {mask_api_key(settings.smartlead_api_key)}")
    print()

    try:
        async with SmartleadApiClient(settings) as client:
            result = await client.verify_connection()
            print(f"Status       : {result['status']}")
            print(f"Campaigns    : {result['campaigns_found']}")

            # Fetch a few campaigns for additional verification
            campaigns = await client.get_campaigns()
            if campaigns:
                print(f"\nSample campaigns ({min(3, len(campaigns))}):")
                for c in campaigns[:3]:
                    print(f"  - [{c.get('id')}] {c.get('name')} ({c.get('status')})")

            print("\n✓ Connection successful!")

    except SmartleadAuthError:
        print("\n✗ Authentication FAILED")
        print("  Check SMARTLEAD_API_KEY in your .env file")
        print("  Go to Settings → Activate API in Smartlead dashboard")
        sys.exit(1)
    except SmartleadError as exc:
        print(f"\n✗ API Error: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"\n✗ Unexpected Error: {exc}")
        sys.exit(1)


async def cmd_generate_report(
    start_date: date,
    end_date: date,
    include_archived: bool = False,
    status_filter: str | None = None,
    concurrency: int | None = None,
) -> None:
    """Generate a report for the given date range."""
    from app.clients.smartlead_client import SmartleadApiClient
    from app.core.config import get_settings
    from app.services.weekly_report_service import WeeklyReportService

    settings = get_settings()
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if include_archived:
        settings.smartlead_include_archived = True
        settings.smartlead_include_drafted = True
    if concurrency:
        settings.smartlead_max_concurrency = concurrency

    print(f"\n=== Generating Report: {start_date} -> {end_date} ===")
    print(f"Max Concurrency: {settings.smartlead_max_concurrency}")
    print(f"Request Pacing : {settings.smartlead_request_interval}s")
    if status_filter:
        print(f"Campaign Filter: ONLY {status_filter.upper()} campaigns")
    elif not settings.smartlead_include_archived:
        print("Campaign Filter: Active/Paused/Stopped only (Archived skipped)")
    else:
        print("Campaign Filter: ALL campaigns including Archived & Drafted")
    if settings.dry_run:
        print("DRY RUN mode   : data will be read but not written to Smartlead")
    print()

    async with SmartleadApiClient(settings) as api_client:
        service = WeeklyReportService(
            api_client=api_client,
            db_session=None,
            dry_run=settings.dry_run,
        )
        report = await service.generate_report(start_date, end_date, status_filter=status_filter)

    print("\n=== Report Summary ===")
    print(f"Period       : {report.period_start} -> {report.period_end}")
    print(f"Clients      : {report.total_clients}")
    print(f"Mailboxes    : {report.total_mailboxes}")
    print(f"Total Sent   : {report.total_sent:,}")
    print(f"Total Bounced: {report.total_bounced:,}")
    print(f"Bounce Rate  : {report.overall_bounce_rate:.2f}%")
    print()

    # Print detailed breakdown
    for client in report.clients:
        print(f"\nClient: {client.client_name} (ID: {client.client_id})")
        print(f"{'Mailbox':<40} {'Sent':>10} {'Bounced':>10} {'Rate':>10}")
        print("-" * 74)
        for mailbox in client.mailboxes:
            print(
                f"{mailbox.email:<40} "
                f"{mailbox.sent:>10,} "
                f"{mailbox.bounced:>10,} "
                f"{mailbox.bounce_rate:>9.2f}%"
            )

    print(f"\n\nNote: {report.data_attribution_note[:120]}...")
    print(f"\nExcel report saved to: {report.excel_file_path or 'exports/'}")


def cmd_server(host: str, port: int) -> None:
    """Start the FastAPI server."""
    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install uvicorn[standard]")
        sys.exit(1)

    print(f"\n=== Starting server at http://{host}:{port} ===")
    print(f"Docs: http://{host}:{port}/docs")
    print()
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info",
    )


def main() -> None:
    args = parse_args()

    # Setup application logging with security filter and quiet third-party libraries
    from app.core.logging import setup_logging
    log_level = "INFO" if (args.verbose or args.generate_report or args.generate_weekly_report) else "WARNING"
    setup_logging(log_level)

    status_filter = "ACTIVE" if args.only_active else args.status_filter

    if args.test_smartlead:
        asyncio.run(cmd_test_smartlead())

    elif args.generate_weekly_report:
        from app.utils.date_utils import get_previous_calendar_week
        date_range = get_previous_calendar_week()
        asyncio.run(cmd_generate_report(
            date_range.start,
            date_range.end,
            include_archived=args.include_archived,
            status_filter=status_filter,
            concurrency=args.concurrency,
        ))

    elif args.generate_report:
        if not args.start_date or not args.end_date:
            print("Error: --generate-report requires --start-date and --end-date")
            sys.exit(1)

        from app.utils.date_utils import parse_date
        try:
            start = parse_date(args.start_date)
            end = parse_date(args.end_date)
        except ValueError as exc:
            print(f"Error: {exc}")
            sys.exit(1)

        asyncio.run(cmd_generate_report(
            start,
            end,
            include_archived=args.include_archived,
            status_filter=status_filter,
            concurrency=args.concurrency,
        ))

    elif args.server:
        cmd_server(args.host, args.port)


if __name__ == "__main__":
    main()
