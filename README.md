# Smartlead Weekly Mailbox Analytics

A production-ready FastAPI application that integrates with the [Smartlead API](https://api.smartlead.ai) to generate weekly mailbox-level email delivery reports.

**Business question answered:** *For every client, how many emails did each mailbox send last week, how many bounced, and what was the bounce rate?*

```
Client A
    john@company.com       → Sent: 500  Bounced: 8   Rate: 1.60%
    sales@company.com      → Sent: 700  Bounced: 14  Rate: 2.00%

Client B
    hello@example.com      → Sent: 350  Bounced: 4   Rate: 1.14%
```

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Smartlead API Setup](#3-smartlead-api-setup)
4. [API Key Setup](#4-api-key-setup)
5. [.env Configuration](#5-env-configuration)
6. [PostgreSQL Setup](#6-postgresql-setup)
7. [Installation](#7-installation)
8. [Running the Server](#8-running-the-server)
9. [Testing Smartlead Connection](#9-testing-smartlead-connection)
10. [Generating Reports](#10-generating-reports)
11. [Excel Report Structure](#11-excel-report-structure)
12. [Date Calculation](#12-date-calculation)
13. [Mailbox Aggregation Logic](#13-mailbox-aggregation-logic)
14. [Duplicate Prevention](#14-duplicate-prevention)
15. [Rate Limiting](#15-rate-limiting)
16. [Error Handling](#16-error-handling)
17. [Scheduler](#17-scheduler)
18. [API Endpoints](#18-api-endpoints)
19. [Security](#19-security)
20. [Smartlead API Limitations](#20-smartlead-api-limitations)
21. [Troubleshooting](#21-troubleshooting)

---

## 1. Project Overview

This application:

- Connects to the **Smartlead API v1** (`https://server.smartlead.ai/api/v1`)
- Discovers all clients (agency accounts) and their campaigns
- For each campaign, fetches which mailboxes (email accounts) are assigned
- Fetches campaign-level analytics for the previous Monday–Sunday
- **Aggregates stats at the mailbox level**, deduplicating mailboxes that appear in multiple campaigns
- Persists results to **PostgreSQL**
- Generates an **Excel report** (`exports/weekly_mailbox_report_*.xlsx`)
- Exposes a **REST API** for on-demand and scheduled report generation

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      FastAPI App                         │
│  /api/reports/weekly  /api/reports/generate  /health    │
└────────────────────────┬────────────────────────────────┘
                         │
              WeeklyReportService (orchestrator)
                         │
        ┌────────────────┼──────────────────┐
        │                │                  │
  ClientService   CampaignService    MailboxService
        │                │                  │
  AnalyticsService  AggregationService  ExportUtils
        │
  SmartleadApiClient (httpx + retry + semaphore)
        │
  Smartlead API v1
        │
  PostgreSQL (via SQLAlchemy async)
```

**Stack:**
| Component | Technology |
|-----------|-----------|
| Backend | Python 3.11+, FastAPI |
| Database | PostgreSQL (via SQLAlchemy async + asyncpg) |
| HTTP Client | httpx (async) |
| Config | pydantic-settings |
| Excel | openpyxl |
| Scheduler | APScheduler |
| Testing | pytest + respx (HTTP mocking) |

---

## 3. Smartlead API Setup

1. Log in to your [Smartlead](https://smartlead.ai) account
2. Go to **Settings**
3. Click **Activate API**
4. Copy your API key — **keep it secret**

> The Smartlead API uses key-as-query-parameter authentication:
> `?api_key=YOUR_KEY` (not Bearer tokens)

---

## 4. API Key Setup

**Never hardcode the API key.** Store it exclusively in `.env`:

```env
SMARTLEAD_API_KEY=your_actual_key_here
```

The `.env` file is in `.gitignore` and will **never be committed**.

---

## 5. .env Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
copy .env.example .env   # Windows
```

```env
# Required
SMARTLEAD_API_KEY=your_api_key_here
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/smartlead_reports

# Optional — defaults shown
API_BASE_URL=https://server.smartlead.ai/api/v1
SMARTLEAD_MAX_CONCURRENCY=5
SMARTLEAD_REQUEST_TIMEOUT=30
SMARTLEAD_MAX_RETRIES=3

REPORT_DAY=MONDAY
REPORT_HOUR=9
REPORT_MINUTE=0

DRY_RUN=false
LOG_LEVEL=INFO
```

### Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `SMARTLEAD_API_KEY` | *(required)* | Your Smartlead API key |
| `DATABASE_URL` | *(required)* | PostgreSQL connection string |
| `API_BASE_URL` | `https://server.smartlead.ai/api/v1` | Smartlead API base URL |
| `SMARTLEAD_MAX_CONCURRENCY` | `5` | Max parallel API requests |
| `SMARTLEAD_REQUEST_TIMEOUT` | `30` | HTTP timeout in seconds |
| `SMARTLEAD_MAX_RETRIES` | `3` | Retry attempts for transient errors |
| `REPORT_DAY` | `MONDAY` | Day of week for scheduled reports |
| `REPORT_HOUR` | `9` | Hour for scheduled reports (UTC) |
| `REPORT_MINUTE` | `0` | Minute for scheduled reports |
| `DRY_RUN` | `false` | Read-only mode (no writes) |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## 6. PostgreSQL Setup

### Install PostgreSQL (Windows)

Download from https://www.postgresql.org/download/windows/

### Create database

```sql
CREATE DATABASE smartlead_reports;
CREATE USER smartlead_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE smartlead_reports TO smartlead_user;
```

### Update DATABASE_URL in .env

```env
DATABASE_URL=postgresql+asyncpg://smartlead_user:your_password@localhost:5432/smartlead_reports
```

Tables are created automatically on startup via `Base.metadata.create_all()`.

---

## 7. Installation

### Create and activate virtual environment

```bash
python -m venv venv

# Windows:
venv\Scripts\activate

# macOS/Linux:
source venv/bin/activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```

---

## 8. Running the Web UI Dashboard & Server

Start the web server:

```bash
python run.py --server
```

Open your browser at:
- **Interactive Web UI Dashboard**: `http://localhost:8000` (live preview, presets, client filter, 1-click Excel download)
- **Interactive API Docs (Swagger)**: `http://localhost:8000/docs`
- **ReDoc Documentation**: `http://localhost:8000/redoc`
- **Health Check**: `http://localhost:8000/health`


---

## 9. Testing Smartlead Connection

```bash
python run.py --test-smartlead
```

This will:
1. Load `SMARTLEAD_API_KEY` from `.env`
2. Make a safe GET request to `/campaigns/`
3. Print connection status and a sample campaign list
4. **Never print the API key** (shows masked version only: `abcd****wxyz`)

---

## 10. Generating Reports

### Previous calendar week (Monday–Sunday)

```bash
python run.py --generate-weekly-report
```

### Strictly Active Campaigns only (1,104 mailboxes)

```bash
# Filter only currently ACTIVE campaigns
python run.py --generate-report --start-date 2026-09-25 --end-date 2026-10-02 --only-active --concurrency 5

# Or for previous calendar week with only active campaigns
python run.py --generate-weekly-report --only-active
```

### Custom date range

```bash
python run.py --generate-report --start-date 2026-09-21 --end-date 2026-09-27
```

### Custom Concurrency & Status Filter

```bash
# Override concurrency (default 5) and filter by specific status
python run.py --generate-report --start-date 2026-09-21 --end-date 2026-09-27 --status-filter ACTIVE --concurrency 4
```

### Via API

```bash
# Previous week (automatic date calculation)
curl http://localhost:8000/api/reports/weekly

# Custom range
curl "http://localhost:8000/api/reports/weekly?start_date=2026-09-21&end_date=2026-09-27"

# Download Excel
curl "http://localhost:8000/api/reports/weekly/export" --output report.xlsx

# Manual trigger via POST
curl -X POST http://localhost:8000/api/reports/generate \
  -H "Content-Type: application/json" \
  -d '{"start_date": "2026-09-21", "end_date": "2026-09-27"}'
```

---

## 11. Excel Report Structure

Generated file: `exports/weekly_mailbox_report_YYYY-MM-DD_to_YYYY-MM-DD.xlsx`

### Sheet 1: Weekly Mailbox Report

| Client Name | Client ID | Mailbox Email | Mailbox ID | Sent | Bounced | Bounce Rate (%) | Period Start | Period End |
|-------------|-----------|---------------|------------|------|---------|-----------------|-------------|-----------|
| Client A | 123 | sales@abc.com | 987 | 500 | 8 | 1.60 | 2026-09-21 | 2026-09-27 |

### Sheet 2: Client Summary

| Client Name | Client ID | Total Mailboxes | Total Sent | Total Bounced | Overall Bounce Rate (%) |

### Sheet 3: Report Metadata

| Generated At | 2026-09-30 09:00:00 |
| Period Start | 2026-09-21 |
| Period End | 2026-09-27 |
| API Source | Smartlead API v1 |
| Number of Clients | 5 |
| Number of Mailboxes | 47 |

**Formatting:** Frozen header rows, auto-sized columns, bold headers (white on dark blue), alternating row highlighting, Excel filters.

---

## 12. Date Calculation

The system uses **ISO calendar-week logic** — **NOT** a rolling 7×24-hour window.

| Term | Definition |
|------|-----------|
| Week start | **Monday** at 00:00:00 |
| Week end | **Sunday** at 23:59:59 |
| "Previous week" | The full Mon–Sun block before the current Mon–Sun block |

### Examples

| Today (reference) | Report Period |
|-------------------|---------------|
| Wednesday, Sep 30, 2026 | Sep 21 (Mon) → Sep 27 (Sun) |
| Monday, Sep 28, 2026 | Sep 21 (Mon) → Sep 27 (Sun) |
| Sunday, Sep 27, 2026 | Sep 14 (Mon) → Sep 20 (Sun) |

**Why not rolling window?**
> Rolling 7 days from Wednesday Sep 30 would give Sep 23–29, which crosses week boundaries and makes reports inconsistent. Calendar weeks give consistent, auditable results.

---

## 13. Mailbox Aggregation Logic

```
Client A
  Campaign 1 (sent=300, bounced=5)
    → sales@company.com (id=42)
    → info@company.com  (id=43)

  Campaign 2 (sent=500, bounced=8)
    → sales@company.com (id=42)    ← same mailbox!
    → support@company.com (id=44)

Result:
  sales@company.com (id=42):   sent=300, bounced=5+??  ← see API limitation below
  info@company.com (id=43):    ...
  support@company.com (id=44): ...
```

**Deduplication key:** Smartlead email account ID (numeric, preferred) or normalized email address (lowercase, fallback).

**Aggregation:** When the same mailbox appears in multiple campaigns, its stats from each campaign are summed.

---

## 14. Duplicate Prevention

The system prevents duplicates at three levels:

1. **Mailbox deduplication** — `MailboxKey` prefers Smartlead ID; falls back to normalized email
2. **Campaign deduplication** — each campaign ID is tracked; counted only once per mailbox
3. **Database constraints** — unique constraints on `smartlead_email_account_id` and `normalized_email` in `mailboxes` table; unique constraint on `(campaign_id, mailbox_id)` in `campaign_mailboxes`

---

## 15. Rate Limiting & Cooldown Protection

Smartlead enforces strict rate limits (**10 requests per 2 seconds**). To guarantee smooth report generation even across hundreds of campaigns:

1. **Inter-Request Pacing:** All outgoing requests pass through a token-bucket rate limiter with `SMARTLEAD_REQUEST_INTERVAL=0.35`s (~2.8 req/sec max), preventing sudden bursts.
2. **Controlled Concurrency:** `SMARTLEAD_MAX_CONCURRENCY=2` (configurable) limits parallel campaign processing.
3. **Global 429 Barrier:** If a 429 is ever encountered, all workers automatically pause for the exact duration specified in the `Retry-After` header (e.g. 60 seconds) plus a safety buffer. No workers send requests during this period.
4. **Retry-After Backoff:** Retries dynamically honor the `Retry-After` duration instead of fixed exponential backoffs that would otherwise fail before the cooldown expires.
5. **Campaign Filtering:** By default, `ARCHIVED` and `DRAFTED` campaigns are skipped to avoid hundreds of useless API calls. Use `--include-archived` or set `SMARTLEAD_INCLUDE_ARCHIVED=true` if you need to include them.

---

## 16. Error Handling

| Error Type | Behavior |
|-----------|---------|
| `SmartleadAuthError` (401/403) | Raised immediately, not retried |
| `SmartleadRateLimitError` (429) | Retried with exponential backoff |
| `SmartleadServerError` (5xx) | Retried with exponential backoff |
| `SmartleadNetworkError` | Retried with exponential backoff |
| `SmartleadNotFoundError` (404) | Logged, campaign skipped |
| `SmartleadValidationError` | Logged as warning, processing continues |

All errors are logged. The API key is **never logged** — a sensitive data filter strips it from all log messages.

---

## 17. Scheduler

The APScheduler runs automatically in the background when the server starts.

Default: **Every Monday at 09:00 UTC**

Configure via `.env`:

```env
REPORT_DAY=MONDAY
REPORT_HOUR=9
REPORT_MINUTE=0
```

The scheduler generates the previous Mon–Sun report automatically. To disable, set an invalid day name (it logs a warning and skips).

---

## 18. API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | App info |
| `GET` | `/health` | Health check |
| `GET` | `/api/reports/weekly` | Previous week report (JSON) |
| `GET` | `/api/reports/weekly?start_date=&end_date=` | Custom date range report |
| `GET` | `/api/reports/weekly/export` | Download Excel file |
| `POST` | `/api/reports/generate` | Generate for custom period |
| `GET` | `/api/clients/` | List Smartlead clients |
| `GET` | `/api/campaigns/` | List campaigns |
| `GET` | `/api/campaigns/{id}/email-accounts` | Campaign mailboxes |
| `GET` | `/api/analytics/overview` | Global analytics |
| `GET` | `/api/analytics/{id}/by-date` | Campaign analytics by date |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/redoc` | ReDoc |

---

## 19. Security

| Rule | Implementation |
|------|---------------|
| API key never committed | `.env` in `.gitignore` |
| API key never logged | `SensitiveDataFilter` on all log handlers |
| API key never in exceptions | URL sanitized before inclusion in error messages |
| API key never in API responses | No endpoint returns config or credentials |
| API key never exposed to frontend | Backend-only communication with Smartlead |
| Dry run mode | `DRY_RUN=true` — read-only, no Smartlead writes |

---

## 20. Official Smartlead Email Health Metrics Integration

The generator connects directly to Smartlead's official **Email Health Metrics** endpoint:

```
GET /analytics/mailbox/name-wise-health-metrics?full_data=true
```

### What this provides:
- **100% Exact Metric Match** with Smartlead UI's **"Email Health Metrics"** dashboard table.
- **Unique Leads Contacted**: True deduplicated count of unique leads reached by each mailbox across the date range.
- **Total Emails Sent**: Total outgoing emails delivered by each mailbox.
- **Bounces & Bounce Rate**: Exact bounces and true bounce percentage (calculated as `bounced / unique_lead_count`).
- **High Performance**: Fetches all mailboxes for an active client in a single fast call (under 3 seconds per client), completely eliminating rate limit risks.


---

## 21. Troubleshooting

### `SMARTLEAD_API_KEY must be set`

Copy `.env.example` to `.env` and add your key.

### `Authentication failed (401)`

- Verify your API key in Smartlead Settings → API
- Ensure the key is in `.env`, not hardcoded

### `Database connection refused`

- Ensure PostgreSQL is running: `pg_ctl status`
- Check `DATABASE_URL` in `.env`
- For local dev without PostgreSQL, database persistence is skipped automatically

### `Rate limit exceeded (429)`

Reduce `SMARTLEAD_MAX_CONCURRENCY` in `.env`. The default of 5 should stay below Smartlead's 10 req/2 sec limit, but be conservative with large datasets.

### `Excel file not generated`

Check the `exports/` directory. Ensure it exists (created automatically) and you have write permissions.

### Tests fail

```bash
pytest tests/ -v
```

Tests do **not** require a real API key — all HTTP calls are mocked with `respx`.

---

## Running Tests

```bash
# All tests
pytest

# With verbose output
pytest -v

# Specific test file
pytest tests/test_date_utils.py -v
pytest tests/test_aggregation.py -v
pytest tests/test_bounce_rate.py -v
pytest tests/test_duplicate_prevention.py -v
pytest tests/test_smartlead_client.py -v
```

---

## Project Structure

```
smart-mailbox-weekly-report-generator/
├── app/
│   ├── main.py                    # FastAPI app + lifespan
│   ├── scheduler.py               # APScheduler weekly job
│   ├── core/
│   │   ├── config.py              # pydantic-settings configuration
│   │   ├── logging.py             # Structured logging + secret filter
│   │   └── security.py            # URL sanitization, key masking
│   ├── clients/
│   │   ├── smartlead_client.py    # Async Smartlead API client
│   │   └── smartlead_exceptions.py
│   ├── services/
│   │   ├── weekly_report_service.py  # Main orchestrator
│   │   ├── aggregation_service.py    # Mailbox deduplication + stats
│   │   ├── analytics_service.py      # Campaign analytics fetching
│   │   ├── client_service.py
│   │   ├── campaign_service.py
│   │   ├── mailbox_service.py
│   │   └── report_service.py
│   ├── models/                    # SQLAlchemy ORM models
│   ├── schemas/                   # Pydantic request/response schemas
│   ├── api/                       # FastAPI routers
│   └── utils/
│       ├── date_utils.py          # Calendar-week logic
│       ├── email_utils.py         # Normalization
│       └── export_utils.py        # Excel generation
├── tests/
│   ├── test_date_utils.py
│   ├── test_aggregation.py
│   ├── test_bounce_rate.py
│   ├── test_duplicate_prevention.py
│   └── test_smartlead_client.py
├── exports/                       # Generated Excel reports
├── logs/                          # Daily log files
├── .env.example                   # Configuration template
├── .gitignore                     # .env excluded
├── requirements.txt
├── pyproject.toml                 # pytest config
├── run.py                         # CLI entry point
└── README.md
```
