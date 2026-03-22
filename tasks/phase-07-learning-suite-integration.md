# Phase 07: Learning Suite Integration (Bookmarklet + Backend)

## Objective
Ingest BYU Learning Suite assignments into the same Google Sheet as Canvas assignments, via a browser bookmarklet that extracts embedded JS data and POSTs it to a new backend endpoint.

## Background & Problem Statement
BYU Learning Suite has no public API. However, the `/schedule` page embeds a `courseInformation` JavaScript variable directly in the HTML that contains all course titles and their nested assignments. Since this variable is already a parsed JS object in the browser's scope, a bookmarklet can extract and forward it to the backend with a single click — no scraping, no auth to solve.

Canvas assignments and Learning Suite assignments will live in the same sheet. A new `source` column distinguishes them (`Canvas` vs `Learning Suite`).

## Data Source

**Page:** `https://learningsuite.byu.edu/.{userID}/student/top/schedule`

**JS variable available in scope:**
```js
courseInformation = [
  {
    "id": "F-3tmGmykPx6",       // courseID
    "title": "C S 270",          // human-readable course name
    "assignments": [
      {
        "id": "kKBQV5Dkama5",
        "name": "Perceptron Quiz",
        "dueDate": "2026-03-03 17:00:00",  // local Mountain Time, no tz suffix
        "type": "Exam",
        "courseID": "F-3tmGmykPx6",
        ...
      }
    ],
    "completedItems": [          // assignments the student has marked done
      { "assignmentID": "...", "completed": true }
    ]
  }
]
```

Key notes:
- `dueDate` is **local Mountain Time** (no UTC offset). Do not apply timezone conversion when parsing — treat as MT directly.
- Assignment IDs must be prefixed with `ls_` before storage to avoid collision with Canvas IDs.
- `completedItems` can optionally pre-check the "Done" checkbox in the sheet (stretch goal).

## Deliverables

### 1. `app/ls_adapter.py`
A new adapter mirroring `adapter.py` but for Learning Suite's data shape.

- Input: list of `courseInformation` dicts (the raw JS variable)
- For each course, iterate `course["assignments"]`
- Map to `Assignment` model:
  - `assignment_id` → `"ls_" + assignment["id"]`
  - `course_name` → `course["title"]` (apply `_normalize_course_name` from `adapter.py`)
  - `assignment_name` → `assignment["name"]`
  - `due_at` → parse `assignment["dueDate"]` as MT naive datetime → attach `America/Denver` tz → convert to UTC
  - `url` → `""` (Learning Suite assignments have no deep-link URL)
- Skip assignments where `dueDate` is null
- Return `list[Assignment]`

### 2. `app/models.py` — add `source` field
```python
class Assignment(BaseModel):
    assignment_id: str
    course_name: str
    assignment_name: str
    due_at: datetime | None
    url: str
    source: str = "Canvas"   # "Canvas" | "Learning Suite"
```

### 3. `app/sheets_client.py` — add Source column
- Add `"source"` to `COLUMNS` and `"Source"` to `HEADERS` (append at end)
- Update `_to_row` to include `assignment.source` as the last value
- Update all range-based formatting (e.g. `endColumnIndex`, `data_range`, course color ranges) to account for the extra column
- `_LAST_SYNCED_CELL` may need to shift right if Source is column G

### 4. `app/main.py` — new endpoint
```
POST /sync/learning-suite
```
- Accepts: `{"courses": [...courseInformation array...]}`
- Runs `LearningSuiteAdapter().adapt_many(courses)`
- Runs idempotency check (same `IdempotencyService` as Canvas sync)
- Calls `SheetsClient().append_rows(new_assignments)`
- Returns: `{"synced": N, "skipped": M}`
- Auth: protected by `X-Sync-Token` header (same pattern as `/sync` if one exists, otherwise add a simple shared secret check using a new `SYNC_TOKEN` env var)

### 5. Bookmarklet (`docs/bookmarklet.js`)
A JS snippet the user saves as a browser bookmark. When clicked on the Learning Suite `/schedule` page, it:
1. Reads `courseInformation` from the page scope
2. Filters out assignments with no `dueDate`
3. POSTs `{"courses": courseInformation}` to the backend `/sync/learning-suite`
4. Shows a brief `alert()` with the result (`"Synced N assignments"`)

```js
javascript:(function(){
  if (typeof courseInformation === 'undefined') {
    alert('Not on the Learning Suite schedule page.');
    return;
  }
  fetch('https://YOUR_BACKEND_URL/sync/learning-suite', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Sync-Token': 'YOUR_SYNC_TOKEN'
    },
    body: JSON.stringify({ courses: courseInformation })
  })
  .then(r => r.json())
  .then(d => alert('Learning Suite sync done. Synced: ' + d.synced + ', Skipped: ' + d.skipped))
  .catch(e => alert('Sync failed: ' + e));
})();
```

User must replace `YOUR_BACKEND_URL` and `YOUR_SYNC_TOKEN` before saving.

## Design Choices and Tradeoffs

- **Choice:** Use the `/schedule` page (not `/prioritizer`) as the data source.
  - **Why:** `courseInformation` on `/schedule` contains both course titles and nested assignments, giving us course names without any secondary lookup.
  - **Tradeoff:** User must navigate to `/schedule` to trigger sync, not any LS page.

- **Choice:** Bookmarklet instead of a browser extension or Playwright scraper.
  - **Why:** Zero install friction; BYU CAS + Duo 2FA makes automated login impractical. The browser is already authenticated.
  - **Tradeoff:** Manual trigger — cannot be automated via CRON.

- **Choice:** Prefix LS assignment IDs with `ls_`.
  - **Why:** Canvas and LS IDs are both opaque strings; namespacing prevents silent idempotency collisions.
  - **Tradeoff:** None meaningful.

- **Choice:** Add `source` column at the end of the sheet.
  - **Why:** Appending avoids shifting existing column indices and breaking current formatting/formulas.
  - **Tradeoff:** Source is the rightmost column, which is less visually prominent.

- **Choice:** `dueDate` treated as local Mountain Time.
  - **Why:** Learning Suite dates have no UTC offset and empirically match local class/assignment times (e.g., quizzes listed at 2:00–5:00 PM match scheduled class periods).
  - **Tradeoff:** Breaks if the user is in a different timezone or if BYU ever changes their date storage convention.

## Out of Scope (Future)
- Auto-checking "Done" from `completedItems` (stretch goal)
- Full automation via cookie-based scraper (blocked by CAS/Duo)
- Per-semester courseID-to-name mapping cache (not needed — title is in the payload)

## File Change Summary
| File | Change |
|------|--------|
| `app/ls_adapter.py` | New file |
| `app/models.py` | Add `source` field |
| `app/sheets_client.py` | Add Source column, update formatting |
| `app/main.py` | Add `POST /sync/learning-suite` endpoint |
| `docs/bookmarklet.js` | New file — bookmarklet snippet |
| `app/config.py` | Add `sync_token` env var (if not already present) |
