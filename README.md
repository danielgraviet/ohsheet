# OhSheet

Turn Canvas chaos into one calm Google Sheet. OhSheet watches your classes, pulls upcoming assignments, and drops them into a spreadsheet so you and your study group always know what’s due next.

## What students get
- One living spreadsheet of all assignments across courses
- Auto-deduped entries (no more duplicate tasks)
- Built for teams: share the sheet, add filters, sort by due date
- Free during early access — just star the repo and follow along

## How to try it locally
If you’re comfortable running Python, you can spin up the service in a few minutes:

1) Install prerequisites
- `uv`
- Python `3.13` (managed via `.python-version`)

2) Install dependencies and start the API

```bash
uv sync               # create/update virtualenv
uv run python main.py # run FastAPI with reload
# or
uv run uvicorn app.main:app --reload
```

3) Point it at your accounts with a `.env` file

```
CANVAS_TOKEN=...
CANVAS_DOMAIN=...
SPREADSHEET_ID=...
REDIS_URL=...
GOOGLE_CREDS_JSON=...
```

That’s it — your assignments will start flowing into the sheet you specify.

## Want to contribute?
- Star the repo to follow updates and cheer the project on.
- Open an issue if you hit a snag or have a student-life feature idea.

## For developers

- Dependency management (uv):

```bash
uv add <package>
uv remove <package>
```

### How it works
1. Fetch upcoming assignments from Canvas.
2. Normalize payloads through an adapter layer.
3. Deduplicate by `assignment_id` using Upstash Redis.
4. Append new rows to Google Sheets.
5. Run automatically on a Railway CRON schedule.
