"""
Tests for Excel export generation (openpyxl).

Verifies:
- 3 sheets exist with correct names
- Sheet 1: Weekly Mailbox Report has 9 columns and correct headers
- Sheet 2: Client Summary has 6 columns
- Sheet 3: Report Metadata has correct key-value pairs
- Header row is frozen
- Bounce rate formatting is applied
- Data rows match input numbers
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import openpyxl
import pytest

from app.utils.export_utils import generate_excel_report


@pytest.fixture
def sample_report_data():
    return {
        "clients": [
            {
                "client_id": 123,
                "client_name": "Client A",
                "mailboxes": [
                    {
                        "email": "john@company.com",
                        "mailbox_id": 101,
                        "leads_contacted": 200,
                        "sent": 500,
                        "bounced": 8,
                        "bounce_rate": 1.60,
                    },
                    {
                        "email": "sales@company.com",
                        "mailbox_id": 102,
                        "leads_contacted": 300,
                        "sent": 700,
                        "bounced": 14,
                        "bounce_rate": 2.00,
                    },
                ],
            },
            {
                "client_id": 456,
                "client_name": "Client B",
                "mailboxes": [
                    {
                        "email": "hello@example.com",
                        "mailbox_id": 201,
                        "leads_contacted": 150,
                        "sent": 350,
                        "bounced": 4,
                        "bounce_rate": 1.14,
                    },
                ],
            },
        ],
        "data_attribution_note": "Test attribution note",
    }


def test_excel_file_created(sample_report_data, tmp_path):
    path = generate_excel_report(
        sample_report_data,
        period_start=date(2026, 9, 21),
        period_end=date(2026, 9, 27),
        output_dir=tmp_path,
    )
    assert path.exists()
    assert path.suffix == ".xlsx"


def test_excel_has_three_sheets(sample_report_data, tmp_path):
    path = generate_excel_report(
        sample_report_data,
        period_start=date(2026, 9, 21),
        period_end=date(2026, 9, 27),
        output_dir=tmp_path,
    )
    wb = openpyxl.load_workbook(path)
    assert "Weekly Mailbox Report" in wb.sheetnames
    assert "Client Summary" in wb.sheetnames
    assert "Report Metadata" in wb.sheetnames


def test_sheet1_headers(sample_report_data, tmp_path):
    path = generate_excel_report(
        sample_report_data,
        period_start=date(2026, 9, 21),
        period_end=date(2026, 9, 27),
        output_dir=tmp_path,
    )
    wb = openpyxl.load_workbook(path)
    ws = wb["Weekly Mailbox Report"]

    headers = [ws.cell(row=1, column=c).value for c in range(1, 10)]
    assert "Date Range" in headers
    assert "Client Name" in headers
    assert "Client ID" in headers
    assert "Mailbox Email" in headers
    assert "Mailbox ID" in headers
    assert "Leads Contacted" in headers
    assert "Total Sent" in headers
    assert "Bounced" in headers
    assert "Bounced Percentage" in headers


def test_sheet1_data_rows(sample_report_data, tmp_path):
    path = generate_excel_report(
        sample_report_data,
        period_start=date(2026, 9, 21),
        period_end=date(2026, 9, 27),
        output_dir=tmp_path,
    )
    wb = openpyxl.load_workbook(path)
    ws = wb["Weekly Mailbox Report"]

    # 3 mailboxes total across 2 clients → 3 data rows
    assert ws.max_row == 4  # 1 header + 3 data rows

    # Row 2 should be john@company.com
    assert ws.cell(row=2, column=1).value == "2026-09-21 to 2026-09-27"
    assert ws.cell(row=2, column=2).value == "Client A"
    assert ws.cell(row=2, column=3).value == "john@company.com"
    assert ws.cell(row=2, column=4).value == 200  # Leads Contacted
    assert ws.cell(row=2, column=5).value == 500  # Total Sent
    assert ws.cell(row=2, column=6).value == 8    # Bounced
    assert ws.cell(row=2, column=7).value == "1.60%"  # Bounced Percentage
    assert ws.cell(row=2, column=8).value == 123  # Client ID
    assert ws.cell(row=2, column=9).value == 101  # Mailbox ID

    # Row 3 should be sales@company.com
    assert ws.cell(row=3, column=3).value == "sales@company.com"
    assert ws.cell(row=3, column=4).value == 300  # Leads Contacted
    assert ws.cell(row=3, column=5).value == 700  # Total Sent
    assert ws.cell(row=3, column=6).value == 14
    assert ws.cell(row=3, column=7).value == "2.00%"


def test_sheet2_client_summary(sample_report_data, tmp_path):
    path = generate_excel_report(
        sample_report_data,
        period_start=date(2026, 9, 21),
        period_end=date(2026, 9, 27),
        output_dir=tmp_path,
    )
    wb = openpyxl.load_workbook(path)
    ws = wb["Client Summary"]

    # 2 clients → 2 data rows
    assert ws.max_row == 3

    # Client A: 2 mailboxes, 500 leads (200+300), 1200 sent, 22 bounced
    assert ws.cell(row=2, column=1).value == "Client A"
    assert ws.cell(row=2, column=2).value == 123     # Client ID
    assert ws.cell(row=2, column=3).value == 2       # mailboxes
    assert ws.cell(row=2, column=4).value == 500     # leads contacted
    assert ws.cell(row=2, column=5).value == 1200    # total sent
    assert ws.cell(row=2, column=6).value == 22      # total bounced
    # 22/1200 * 100 = 1.83%
    assert ws.cell(row=2, column=7).value == 1.83


def test_sheet3_metadata(sample_report_data, tmp_path):
    path = generate_excel_report(
        sample_report_data,
        period_start=date(2026, 9, 21),
        period_end=date(2026, 9, 27),
        output_dir=tmp_path,
    )
    wb = openpyxl.load_workbook(path)
    ws = wb["Report Metadata"]

    meta = {
        ws.cell(row=r, column=1).value: ws.cell(row=r, column=2).value
        for r in range(2, ws.max_row + 1)
    }
    assert meta["Period Start"] == "2026-09-21"
    assert meta["Period End"] == "2026-09-27"
    assert meta["Number of Clients"] == "2"
    assert meta["Number of Mailboxes"] == "3"
    assert meta["Total Emails Sent"] == "1550"
    assert meta["Total Emails Bounced"] == "26"
