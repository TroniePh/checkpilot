# Changelog — CheckPilot™

## v2.5.4 (2026-05-27)

- Hotfix: Auto Mode and scheduler no longer block on stale template locks after CSV/app updates.
- Template locks now warn only; validation and item/upload submit guards still prevent unsafe submit.

---

## v2.5.3 (2026-05-26)

- Added same-template retry when SafetyCulture shows the transient "An error has occurred" popup.
- Added safer draft cleanup after blocked/fatal automation errors so the next template starts from a clean page.
- Added Telegram error context: template, site, current question, current URL, and recent item errors.
- Added Auto Mode circuit breaker: GUI and headless runner stop after 3 consecutive template failures.
- Fixed Yummi Sushi data so `sushi temperature.jpeg` targets the photo question instead of the initials field.
- Fixed photo upload question resolution for 9AM/5PM case photos when CSV text differs from SafetyCulture's visible question text.
- Verified live fill-only run: 10/10 Yummi Sushi templates completed with uploads, no submit.

---

## v2.5.2 (2026-05-25)

- Replaced the always-visible CSV template list with a compact "Mục template CSV" picker dialog.
- Added explicit "Bỏ chọn" support for the selected Test Mode template.
- Fixed "Chờ lịch" so it waits for the scheduled time instead of starting immediately when Test Mode is enabled.
- Scheduled runs now force real Auto Mode, use the full loaded CSV, and auto-submit according to the configured schedule.

---

## v2.5.1 (2026-05-25)

- Fixed Automation layout so run controls stay visible after the CSV template picker loads.
- Fixed template start matching to click the Start button scoped to the selected template row/card.
- Added a form-title guard so automation stops if SafetyCulture opens the wrong template.

---

## v2.5.0 (2026-05-25)

- Added a CSV template/inspection picker in Automation after loading data.
- Users can select a specific template/site from the loaded CSV and run Test Mode only for that item.
- Targeted test runs always disable Auto Submit and stop before Complete/Submit.

---

## v2.4.9 (2026-05-25)

- Fixed SafetyCulture question matching after page navigation.
- Handles required questions rendered as split text or with leading `*`, for example `Did you Produce Hot Food Today?`.
- Added retry/debug output for visible questions when matching still fails.
- Improved Complete/Submit confirmation handling so hidden/stale modals do not block valid submit flow.

---

## v2.4.8 (2026-05-25)

- Added headless runner for Windows Task Scheduler boot/pre-login operation.
- Added persistent validation fingerprint so edited CSV/Excel files must be revalidated.
- Hardened Auto Mode submit guards for missing template/folder/start button/form and uncertain dropdown answers.
- Added light UI tone and clearer Windows startup settings.
- Updated release metadata and customer documentation.

---

## v2.2.0 (2026-05-25)

### New Features
- **Chạy ngay** button — run all inspections immediately, bypass schedule
- **Chờ lịch** button — wait for scheduled time
- **Auto-login SafetyCulture** — saved credentials, auto-fill Auth0 login
- **Telegram alerts** — error notifications + daily summary
- **Scheduler** — auto-run at configured time (e.g. 5:00 AM daily)
- **System tray** — minimize to tray, run in background
- **Watchdog** — auto-restart if app hangs
- **Template lock** — force test before auto-submit new templates
- **Daily run lock** — prevent duplicate submissions
- **HTML reports** — per-inspection report with full details
- **Diagnostics page** — system info, reset locks, open folders
- **Config backup/restore** — export/import all settings
- **Auto-update checker** — notify when new version available
- **Windows startup** — auto-start with Windows
- **Singleton lock** — prevent multiple instances
- **Auto-load last config** — remember file/folder between sessions

### Improvements
- Health check before each run (no more half-started inspections)
- Per-item timeout (30s) — skip stuck items
- Popup/dialog auto-dismiss (session expired, cookie consent, etc.)
- Network retry with controlled backoff
- Strict mode: image_required, question_alias columns
- Persistent log panel (survives tab switches)
- Regional URL support (app.au.safetyculture.com, etc.)

### Bug Fixes
- Fixed login detection for Auth0 pages
- Fixed template search (now uses Inspections → Start → Search flow)
- Fixed file/image path lost when switching tabs
- Fixed license badge not updating after activation
- Fixed daily summary always reporting 0
- Fixed race condition in test/retry runs

---

## v2.0.0 (2026-05-18)

- Initial release
- SafetyCulture inspection automation
- Excel/CSV data input
- Auto-fill answers, notes, images
- Review/Test mode
- Dark theme UI (CustomTkinter)

---

*Designed by Phạm Duy | 0868609901*
