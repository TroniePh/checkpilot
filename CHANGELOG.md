# Changelog — CheckPilot™

## v2.6.5 (2026-09-13)

- Added a SafetyCulture account table in Settings with double-click editing.
- Saving a renamed account moves its saved session and updates account/profile columns in the selected CSV.
- Account details now support editing the login email, password, and template folder URL.

---

## v2.6.4 (2026-09-13)

- Retry ACE Daily Food Safety Log when SafetyCulture shows the full-page `Something went wrong` error.
- Added SafetyCulture profile rename in Settings.
- Renaming a profile now moves saved session data and updates matching account/profile columns in the selected CSV.

---

## v2.6.3 (2026-06-09)

- Fixed ACE Daily Food Safety Log Hot Food question matching when SafetyCulture renders the same visible question through nested DOM containers.
- Keeps duplicate-question protection active for repeated ACE fields across `2.1`, `2.2`, `2.3`, `4.1`, and `4.2`.
- Re-verified ACE regression coverage for hidden `Conducted on`, unique visible fallback questions, duplicate-question blocking, and section-scoped temperature fields.

---

## v2.6.2 (2026-06-08)

- Fixed ACE Daily Food Safety Log Auto Mode blocking before `Complete inspection` when SafetyCulture does not render the `Conducted on` field.
- Added a safe fallback for visible unique questions when SafetyCulture omits the CSV section heading, fixing `Does This Store Prepare and Sell Any Foods Under TPHC?`.
- Kept duplicate-question protection in place so repeated ACE sections such as `2.1`, `2.2`, and `2.3` are not answered in the wrong section.

---

## v2.6.1 (2026-06-06)

- Fixed ACE Daily Food Safety Log section matching so repeated questions in `2.1`, `2.2`, and `2.3` are filled only in the intended section.
- Kept `Title Page` questions discoverable when SafetyCulture renders them under the page heading instead of a literal `Title Page` section, including `What Type of Operation Will Occur Today?`.
- Hardened final signature handling so CheckPilot opens `Draw signature`, draws on the actual signature pad, and confirms the dialog.

---

## v2.6.0 (2026-06-06)

- Fixed ACE Daily Food Safety Log store selection so `Select Your Store` chooses the real `VONS 02090 (Main)` dropdown option instead of only typing text into the field.
- Added automatic handling for final signature questions: CheckPilot fills the name and draws on the SafetyCulture signature pad when required.
- Corrected the ACE VONS 02090 CSV page navigation by removing the extra `NEXTPAGE` before the temperature sections.
- Added ACE VONS 02090 customer schedule/test CSV handoff files to the packaged installer.

---

## v2.5.9 (2026-05-28)

- Added Telegram success evidence: after each template submits and verifies in SafetyCulture, CheckPilot captures a success screenshot and sends it to all configured Telegram recipients.
- Success alerts now include template, site, item count, schedule slot, verification status, current URL, and the proof screenshot.
- Removed pre-verify success alerts so Telegram success evidence is only sent after the save/verify step.

---

## v2.5.8 (2026-05-27)

- Fixed always-on scheduled operation: after a scheduled template slot completes, the GUI automatically returns to waiting for the next slot instead of showing final completion.
- On startup/reboot, if schedule is enabled and saved data is valid, CheckPilot automatically enters schedule wait mode without requiring a manual click.
- Scheduler no longer marks a slot as run until the GUI actually accepts and starts that slot; if automation is still busy, the slot remains eligible for catch-up.

---

## v2.5.7 (2026-05-27)

- Fixed missed-slot catch-up order so restart recovery runs older missed template slots before newer ones.
- Hardened GUI updates from scheduler/worker threads so tab switching or closing the app does not trigger Tk widget errors.
- Re-verified Yummi Sushi CSV: 11 templates, 137 items, 9 images, template-time schedule, and `SKIP` for Closing Checklist Sushi Rolling Machine.

---

## v2.5.6 (2026-05-27)

- Added template-time scheduler mode: Auto Mode can run only the inspections assigned to the current template time instead of the full CSV every slot.
- Scheduler now derives template times from CSV `run_time` / `schedule_time` / `run_at`, falling back to each template's `Conducted on` answer.
- Updated Yummi Sushi schedule groups: 6AM opening, 7AM hot food/batch/pH, 9AM/10AM/11AM/1PM/4PM, and 5PM closing/case photos.
- Added `SKIP` answer support for questions that should be present but not clicked, including Closing Checklist `Sushi Rolling Machine (If Applicable)`.

---

## v2.5.5 (2026-05-27)

- Added missed-schedule catch-up: if Windows boots or the GUI starts shortly after a configured run time, Auto Mode runs the missed slot instead of waiting until the next day.
- Kept the catch-up window bounded to 180 minutes by default to avoid very late accidental submissions.

---

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
