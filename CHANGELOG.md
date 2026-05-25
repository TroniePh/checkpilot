# Changelog — CheckPilot™

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
