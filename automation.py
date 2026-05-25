"""
CheckPilot - Automation Engine
Features: Auto/Test mode, health check, error tracking, Telegram alerts, HTML dump
"""
import os
import re
import time
import logging
from datetime import datetime
from typing import Callable, Optional, List

from playwright.sync_api import (
    sync_playwright, Page, Browser, BrowserContext,
    TimeoutError as PWTimeout, Locator,
)

from config import (
    BROWSER_HEADLESS, BROWSER_SLOW_MO, DEFAULT_TIMEOUT,
    NAVIGATION_TIMEOUT, SC_BASE_URL, SC_INSPECTIONS_URL, SC_LOGIN_URL,
    SC_TEMPLATE_FOLDER_URL,
    MAX_RETRIES, RETRY_DELAY, SCREENSHOT_DIR, LOG_DIR, BROWSERS_DIR,
)
from data_loader import InspectionData, InspectionItem
from session_manager import (
    has_saved_session, save_session_state, get_session_state_path,
    has_saved_credentials, load_credentials,
)
from notifier import send_error_alert, send_success_report
from app_settings import load_app_settings

logger = logging.getLogger(__name__)

STEP_DELAY = 0.8
SCROLL_DELAY = 1.0
UPLOAD_WAIT = 5.0
PAGE_LOAD_WAIT = 2.0
SECTION_SCROLL_STEP = 300
ITEM_TIMEOUT = 30  # seconds max per item before skip
RUN_RETRY_MAX = 3  # max retries for a failed inspection
POPUP_DISMISS_SELECTORS = [
    'button:has-text("Dismiss")', 'button:has-text("Close")',
    'button:has-text("Got it")', 'button:has-text("OK")',
    'button:has-text("Accept")', 'button:has-text("Later")',
    'button[aria-label="Close"]', '[data-testid="close-button"]',
    'button:has-text("Not now")', 'button:has-text("Skip")',
]


class AutomationEngine:
    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.log_callback = log_callback or (lambda msg: None)
        self._paused = False
        self._stopped = False
        self.item_errors: List[str] = []
        self._items_ok = 0
        self._images_uploaded = 0
        self._images_failed = 0

    # ── Lifecycle ──
    def start_browser(self):
        self._log("Launching browser...")
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=BROWSER_HEADLESS, slow_mo=BROWSER_SLOW_MO,
            args=["--start-maximized", "--force-device-scale-factor=1", "--disable-extensions"],
        )
        session_path = get_session_state_path()
        ctx_args = {"viewport": {"width": 1366, "height": 900}, "locale": "en-US"}
        if session_path:
            self._log("Restoring saved session...")
            ctx_args["storage_state"] = session_path
        self.context = self.browser.new_context(**ctx_args)
        self.context.set_default_timeout(DEFAULT_TIMEOUT)
        # Grant permissions to avoid popups blocking automation
        self.context.grant_permissions(["geolocation"])
        self.page = self.context.new_page()
        self.page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)
        self._log("Browser ready")

    def close_browser(self):
        try:
            if self.page and self._is_logged_in():
                save_session_state(self.page)
        except: pass
        try:
            if self.context: self.context.close()
            if self.browser: self.browser.close()
            if self.playwright: self.playwright.stop()
        except: pass
        self._log("Browser closed")

    def pause(self): self._paused = True; self._log("Paused")
    def resume(self): self._paused = False; self._log("Resumed")
    def stop(self): self._stopped = True; self._log("Stop requested")

    # ── Health Check ──
    def health_check(self) -> tuple:
        """Pre-run health check. Returns (ok, message)."""
        current_url = self.page.url

        # Check if on login page (session expired on initial load)
        if "auth." in current_url or "/login" in current_url:
            self._log("  Session expired on load - need login")
            return False, "Not logged in"

        # Verify we're on SafetyCulture
        if "safetyculture" not in current_url:
            try:
                self.page.goto(SC_BASE_URL, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)
            except:
                return False, "Cannot access SafetyCulture"

        # Verify we're logged in
        if not self._is_logged_in():
            return False, "Not logged in"

        return True, "OK"

    # ── Login ──
    def wait_for_login(self):
        self._log("Opening SafetyCulture login...")

        # Always go to login page directly - don't rely on saved session
        self.page.goto(SC_LOGIN_URL, wait_until="domcontentloaded")
        time.sleep(5)

        current_url = self.page.url
        self._log(f"  URL: {current_url}")

        # If redirected to app (already logged in), we're done
        if "safetyculture.com" in current_url and "auth." not in current_url and "/login" not in current_url and "/logout" not in current_url:
            self._log("Already logged in")
            return

        # We're on login page - login with credentials
        self._log("Logging in to SafetyCulture...")

        if has_saved_credentials():
            creds = load_credentials()
            if creds:
                self._log(f"  Using saved credentials: {creds[0][:3]}***")
                if self._auto_fill_login(creds[0], creds[1]):
                    try:
                        self.page.wait_for_url(
                            lambda url: "safetyculture.com" in url and "auth." not in url and "/login" not in url and "/logout" not in url,
                            timeout=30000)
                        time.sleep(3)
                        self._log("Login OK!")
                        save_session_state(self.page)
                        return
                    except PWTimeout:
                        current = self.page.url
                        if "safetyculture.com" in current and "auth." not in current and "/login" not in current:
                            self._log("Login OK (delayed)")
                            save_session_state(self.page)
                            return
                        self._log("Auto-login failed.")

        # Manual login fallback
        self._log("Please login manually in the browser (5 min timeout)...")
        try:
            self.page.wait_for_url(
                lambda url: "safetyculture.com" in url and "auth." not in url and "/login" not in url and "/logout" not in url,
                timeout=300000)
            time.sleep(3)
            self._log("Login OK")
            save_session_state(self.page)
        except PWTimeout:
            raise RuntimeError("Login timeout")

    def _is_logged_in(self) -> bool:
        url = self.page.url
        # Not logged in if on auth page or login page
        if "auth.safetyculture" in url:
            return False
        if "/login" in url:
            return False
        # Logged in if on any safetyculture app domain (app.safetyculture, app.au.safetyculture, etc.)
        if "safetyculture.com" in url and "auth." not in url and "/login" not in url:
            return True
        return False

    def _is_on_login_page(self) -> bool:
        """Check if the current page is actually a login page by looking at content."""
        url = self.page.url
        if "auth.safetyculture" in url or "/login" in url:
            return True
        # Sometimes URL doesn't update but page shows login form
        try:
            login_form = self.page.locator('input[name="email"], input[type="email"], input[id="email"]').first
            if login_form.count() > 0 and login_form.is_visible():
                # Check there's also a Continue/Login button
                btn = self.page.locator('button:has-text("Continue"), button:has-text("Log in")').first
                if btn.count() > 0:
                    return True
        except:
            pass
        return False

    def _auto_fill_login(self, email: str, password: str) -> bool:
        try:
            time.sleep(2)  # Wait for auth page to fully load
            self._log(f"  Login page URL: {self.page.url}")

            # SafetyCulture uses auth.safetyculture.com (Auth0-style)
            # Step 1: Find and fill email
            e_sel = [
                'input[name="email"]', 'input[type="email"]',
                'input[id="email"]', 'input[id="username"]',
                'input[name="username"]', 'input[placeholder*="email" i]',
                'input[placeholder*="Email"]', 'input[autocomplete="email"]',
                'input[autocomplete="username"]',
            ]
            ei = self._find_first(e_sel, timeout=8000)
            if not ei:
                self._log("  Email field not found")
                return False

            ei.click()
            time.sleep(0.3)
            ei.fill("")
            ei.type(email, delay=30)
            time.sleep(0.5)
            self._log(f"  Email filled: {email[:3]}***")

            # Step 2: Check if password field is visible or need to click Continue/Next
            p_sel = [
                'input[name="password"]', 'input[type="password"]',
                'input[id="password"]', 'input[placeholder*="password" i]',
                'input[placeholder*="Password"]',
            ]
            pi = self._find_first(p_sel, timeout=3000)

            if not pi:
                # Click Continue/Next/Submit to go to password step
                next_sel = [
                    'button[type="submit"]',
                    'button:has-text("Continue")',
                    'button:has-text("Next")',
                    'button:has-text("Log in")',
                    'button:has-text("Sign in")',
                    'input[type="submit"]',
                    'button[name="action"]',
                ]
                next_btn = self._find_first(next_sel, timeout=5000)
                if next_btn:
                    next_btn.click()
                    self._log("  Clicked Continue/Next")
                    time.sleep(2.5)
                else:
                    self.page.keyboard.press("Enter")
                    time.sleep(2.5)

                # Now find password field
                pi = self._find_first(p_sel, timeout=8000)

            if not pi:
                self._log("  Password field not found")
                return False

            # Step 3: Fill password
            pi.click()
            time.sleep(0.3)
            pi.fill("")
            pi.type(password, delay=30)
            time.sleep(0.5)
            self._log("  Password filled")

            # Step 4: Click login button
            login_sel = [
                'button[type="submit"]',
                'button:has-text("Log in")',
                'button:has-text("Log In")',
                'button:has-text("Login")',
                'button:has-text("Sign in")',
                'button:has-text("Continue")',
                'button[name="action"]',
                'input[type="submit"]',
            ]
            login_btn = self._find_first(login_sel, timeout=5000)
            if login_btn:
                login_btn.click()
                self._log("  Clicked Login button")
            else:
                self.page.keyboard.press("Enter")
                self._log("  Pressed Enter to submit")

            time.sleep(3.0)
            return True

        except Exception as e:
            self._log(f"  Auto-fill error: {str(e)[:60]}")
            return False

    # ── Main Run ──
    def run_inspection(self, data: InspectionData, auto_submit: bool = True) -> bool:
        """
        Run full inspection with retry on network errors.
        auto_submit=True: Complete/Submit if no errors (Auto Mode)
        auto_submit=False: Fill only, don't submit (Test Mode)
        """
        self.item_errors = []
        self._items_ok = 0
        self._images_uploaded = 0
        self._images_failed = 0

        try:
            self._check_state()
            self._dismiss_popups()

            # Navigate with retry
            self._with_retry("go_to_inspections", self._go_to_inspections)
            self._check_state()

            # Start inspection with retry
            self._with_retry("start_inspection", lambda: self._start_new_inspection(data.template_name))
            self._check_state()

            self._fill_header(data)
            self._check_state()

            self._fill_all_items(data.items)
            self._check_state()

            if not auto_submit:
                self._scroll_to_bottom()
                self._log("Đã nhập xong. Vui lòng kiểm tra rồi submit thủ công.")
                self._log("  Test mode: không bấm Complete/Submit. Bấm Stop sau khi kiểm tra xong.")
                # Keep browser open; wait for user to stop.
                while not self._stopped:
                    time.sleep(1)
                return True

            # Auto submit: check errors first
            if self.item_errors:
                err_msg = f"{len(self.item_errors)} error(s) - NOT submitting"
                self._log(f"BLOCKED: {err_msg}")
                for e in self.item_errors[:5]:
                    self._log(f"  - {e}")
                ss = self._screenshot_error("blocked_submit")
                self._save_html_dump("blocked_submit")
                send_error_alert(err_msg, ss, data.template_name, data.site_location)
                return False

            # Safe to submit
            self._complete_inspection()
            self._log("Submitted OK")
            send_success_report(data.template_name, data.site_location,
                              len(data.items), len(self.item_errors))
            return True

        except StopRequested:
            self._log("Stopped by user")
            return False
        except Exception as e:
            ss = self._screenshot_error(f"fatal_{datetime.now().strftime('%H%M%S')}")
            self._save_html_dump(f"fatal_{datetime.now().strftime('%H%M%S')}")
            self._log(f"FATAL: {str(e)}")
            send_error_alert(str(e), ss, data.template_name, data.site_location)
            logger.exception("Inspection failed")
            return False

    def verify_inspection_saved(self, template_name: str) -> bool:
        self._log("Verifying saved...")
        time.sleep(2.0)
        self._go_to_inspections()
        time.sleep(PAGE_LOAD_WAIT)
        found = self.page.locator(f'text="{template_name}"').first
        if found.count() > 0:
            self._log("Verified in list")
            return True
        self._log("Not found in list (may sync later)")
        return False

    # ── Navigation ──
    def _go_to_inspections(self):
        """Navigate to Templates page and open the correct folder."""
        from config import SC_TEMPLATES_URL
        from autostart import load_autostart_config

        # Get folder name from config
        acfg = load_autostart_config()
        folder_name = acfg.get("template_folder_name", "")

        # If a direct folder URL is saved, use it
        folder_url = acfg.get("template_folder_url", "").strip()
        if folder_url and "safetyculture.com" in folder_url:
            self._log(f"Navigating to saved folder URL...")
            self.page.goto(folder_url, timeout=30000)
        else:
            self._log("Navigating to Templates...")
            self.page.goto(SC_TEMPLATES_URL, timeout=30000)

        try:
            self.page.wait_for_load_state("networkidle", timeout=15000)
        except:
            pass
        time.sleep(PAGE_LOAD_WAIT + 1)

        # Check login redirect
        if "auth." in self.page.url or "/login" in self.page.url:
            self._log("  Session expired - re-logging in...")
            self.wait_for_login()
            self.page.goto(SC_TEMPLATES_URL, timeout=30000)
            time.sleep(PAGE_LOAD_WAIT + 1)

        # If we need to click into a folder
        if folder_name and "/templates" in self.page.url:
            self._log(f"  Opening folder: {folder_name}")
            folder_el = self.page.locator(f'text="{folder_name}"').first
            if folder_el.count() == 0:
                # Try partial match
                folder_el = self.page.locator(f'//*[contains(text(), "{folder_name[:20]}")]').first
            if folder_el.count() > 0:
                folder_el.click()
                time.sleep(PAGE_LOAD_WAIT + 1)
                try:
                    self.page.wait_for_load_state("networkidle", timeout=10000)
                except:
                    pass
                self._log(f"  Folder opened")
            else:
                self._log(f"  WARNING: Folder '{folder_name}' not found, continuing on current page")

        self._log(f"  URL: {self.page.url}")

    def _start_new_inspection(self, template_name: str):
        """
        On Templates page (inside folder): find template -> click Start inspection
        """
        self._log(f"Starting: {template_name}")
        self._log(f"  URL: {self.page.url}")

        # Wait for template list to load
        time.sleep(2)

        # Find the template by name
        tmpl = None
        for attempt in range(5):
            tmpl = self.page.locator(f'text="{template_name}"').first
            if tmpl.count() > 0:
                break
            # Try partial
            short = template_name[:25]
            tmpl = self.page.locator(f'//*[contains(text(), "{short}")]').first
            if tmpl.count() > 0:
                break
            time.sleep(2)

        if not tmpl or tmpl.count() == 0:
            ss = self._screenshot_error("template_not_found")
            self._save_html_dump("template_not_found")
            raise RuntimeError(f"Template not found: '{template_name}'")

        # Scroll template into view
        tmpl.scroll_into_view_if_needed()
        time.sleep(0.5)

        # Find "Start inspection" button near this template
        # Try: same row/card, or hover to reveal button
        row = tmpl.locator("xpath=ancestor::*[contains(@class,'row') or contains(@class,'item') or contains(@class,'card') or contains(@class,'template')]").first
        if row.count() == 0:
            row = tmpl.locator("xpath=ancestor::tr").first
        if row.count() == 0:
            row = tmpl.locator("xpath=../..").first

        start_btn = None
        if row.count() > 0:
            start_btn = row.locator('a:has-text("Start"), button:has-text("Start"), a:has-text("Start inspection")').first

        clicked = False
        if start_btn and start_btn.count() > 0:
            try:
                start_btn.click()
                clicked = True
                self._log("  Clicked Start inspection (in row)")
            except:
                pass

        if not clicked:
            # Try clicking template name first (may open detail/start dialog)
            tmpl.click()
            time.sleep(2)
            # Look for Start button in popup/dialog or page
            start_sels = [
                'button:has-text("Start inspection")',
                'a:has-text("Start inspection")',
                'button:has-text("Start")',
                'button:has-text("Begin")',
            ]
            if not self._click_first_found(start_sels, timeout=8000):
                ss = self._screenshot_error("no_start_button")
                self._save_html_dump("no_start_button")
                raise RuntimeError(f"Cannot find Start button for '{template_name}'")
            self._log("  Clicked Start inspection (after template click)")

        # Wait for inspection form to load
        time.sleep(PAGE_LOAD_WAIT + 3)
        try:
            self.page.wait_for_load_state("networkidle", timeout=15000)
        except:
            pass

        self._log(f"  Form URL: {self.page.url}")
        self._log("Form opened")

    def _is_inspection_form_open(self, template_name: str) -> bool:
        """Best-effort guard to prevent filling on the template list or wrong page."""
        if not self.page:
            return False
        url = self.page.url.lower()
        if "auth." in url or "/login" in url or "/logout" in url:
            return False
        form_indicators = [
            'button:has-text("Complete inspection")',
            'button:has-text("Complete")',
            'button:has-text("Submit")',
            'button:has-text("Add note")',
            'text="Conducted on"',
            'text="Site conducted"',
            '[data-testid*="inspection"]',
        ]
        for selector in form_indicators:
            try:
                loc = self.page.locator(selector).first
                if loc.count() > 0 and loc.is_visible():
                    return True
            except:
                continue
        return False

    # ── Fill Header ──
    def _fill_header(self, data: InspectionData):
        self._log(f"Header: {data.site_location} | {data.inspection_date}")
        if data.inspection_date:
            self._fill_date(data.inspection_date)
        if data.site_location:
            self._fill_site(data.site_location)
        time.sleep(STEP_DELAY)

    def _fill_date(self, date_str: str):
        di = self._find_first(['input[type="date"]', 'input[aria-label*="date" i]',
                               'input[placeholder*="date" i]'], timeout=3000)
        if di:
            try: di.click(); time.sleep(0.2); di.fill(date_str)
            except: pass

    def _fill_site(self, site: str):
        si = self._find_first(['input[aria-label*="site" i]', 'input[aria-label*="location" i]',
                               'input[placeholder*="site" i]', 'input[placeholder*="location" i]'], timeout=3000)
        if si:
            si.click(); time.sleep(0.2); si.fill(site); time.sleep(0.5)
            opt = self.page.locator(f'[role="option"]:has-text("{site}")').first
            if opt.count() > 0: opt.click()
            else: self.page.keyboard.press("Enter")
            time.sleep(0.3)

    # ── Fill Items ──
    def _fill_all_items(self, items: List[InspectionItem]):
        current_section = ""
        total = len(items)
        self._items_ok = 0
        self._images_uploaded = 0
        self._images_failed = 0

        for idx, item in enumerate(items):
            self._check_state()
            self._dismiss_popups()

            # Special command: navigate to next page
            if item.answer.strip().upper() == "NEXTPAGE" or item.question.strip().upper() == "NEXTPAGE":
                self._log(f"  [{idx+1}/{total}] >>> Next Page")
                self._go_next_page()
                self._items_ok += 1
                continue

            if item.section and item.section != current_section:
                current_section = item.section
                self._log(f"  Section: {current_section}")
                self._scroll_to_section(current_section)
                time.sleep(SCROLL_DELAY)

            self._log(f"  [{idx+1}/{total}] {item.question[:40]}... -> {item.answer}")

            # Per-item timeout wrapper
            item_start = time.time()
            item_ok = True

            try:
                if not self._answer_question(item):
                    self.item_errors.append(f"Answer failed: {item.question[:50]}")
                    item_ok = False
            except Exception as e:
                elapsed = time.time() - item_start
                if elapsed > ITEM_TIMEOUT:
                    self._log(f"    TIMEOUT ({ITEM_TIMEOUT}s) - skipping item")
                else:
                    self._log(f"    Error: {str(e)[:50]}")
                self.item_errors.append(f"Error: {item.question[:40]}: {str(e)[:30]}")
                item_ok = False

            if item.notes:
                try:
                    self._add_note(item)
                except:
                    pass

            if item.image_paths:
                for img in item.image_paths:
                    try:
                        ok = self._upload_image_for_question(img, item.question)
                        if ok:
                            self._images_uploaded += 1
                        elif item.image_required:
                            self.item_errors.append(f"Required image failed: {os.path.basename(img)}")
                            self._images_failed += 1
                            item_ok = False
                        else:
                            self._log(f"    WARN: Optional image skipped")
                            self._images_failed += 1
                    except Exception as e:
                        self._log(f"    Upload exception: {str(e)[:40]}")
                        self._images_failed += 1
                        if item.image_required:
                            self.item_errors.append(f"Image error: {os.path.basename(img)}")
                            item_ok = False

            if item_ok:
                self._items_ok += 1

            # Check if item took too long
            if time.time() - item_start > ITEM_TIMEOUT:
                self._log(f"    Item took {time.time()-item_start:.0f}s (slow)")

            time.sleep(STEP_DELAY)

    def _answer_question(self, item: InspectionItem) -> bool:
        """
        Find question and answer it. Supports multiple field types:
        - Button (Yes/No/N/A/Safe/etc.): click
        - Text input / number input: type value
        - Dropdown/select: choose option
        - Textarea: fill text
        - Checkbox: tick
        - Datetime picker: set time
        Returns True if successful.
        """
        if not item.answer.strip():
            return True  # No answer needed

        # Special handling for "Site conducted" SafetyCulture site picker.
        if "site conducted" in item.question.lower():
            return self._select_site(item.answer)

        # Special handling for "Conducted on" datetime picker.
        if "conducted on" in item.question.lower():
            return self._set_conducted_time(item.answer)

        # Special handling for checkbox items (answer = TRUE means tick the checkbox)
        if item.answer.strip().upper() == "TRUE":
            return self._tick_checkbox(item.question)

        container = self._find_question_container(item.question)
        # Fallback: try alias
        if not container and item.question_alias:
            container = self._find_question_container(item.question_alias)

        if not container:
            self._log(f"    WARN: Question not found on page")
            return False

        # Strategy 1: Try clicking a button answer (Yes/No/N/A etc.)
        if self._try_click_answer(container, item.answer):
            return True

        # Strategy 2: If answer is a number, fill input directly (skip dropdown)
        answer_stripped = item.answer.strip()
        is_numeric = False
        try:
            float(answer_stripped)
            is_numeric = True
        except ValueError:
            pass

        if is_numeric:
            if self._try_fill_input(container, item.answer):
                return True

        # Strategy 3: Try selecting from dropdown
        if not is_numeric and self._try_select_dropdown(container, item.answer):
            return True

        # Strategy 4: Try filling an input field (text)
        if not is_numeric and self._try_fill_input(container, item.answer):
            return True

        # Strategy 5: Try filling a textarea
        if self._try_fill_textarea(container, item.answer):
            return True

        self._log(f"    WARN: Could not answer '{item.question[:40]}' with '{item.answer}'")
        return False

    def _set_conducted_time(self, time_value: str) -> bool:
        """
        Handle SafetyCulture's 'Conducted on' datetime field.
        Click the field to open calendar+time picker, then click the time value.
        time_value format: "6:00 AM" or "1:00 PM" etc.
        """
        try:
            # Find and click the Conducted on input to open picker
            conducted = self.page.locator('text="Conducted on"').first
            if conducted.count() == 0:
                self._log("    WARN: Conducted on field not found")
                return False

            conducted.scroll_into_view_if_needed()
            time.sleep(0.3)

            # Click the input field to open the date/time picker
            dt_input = conducted.locator("xpath=following::input[1]").first
            if dt_input.count() == 0:
                dt_input = self.page.locator('input[placeholder*="date"], input[placeholder*="Enter date"]').first

            if dt_input.count() > 0:
                dt_input.click()
                time.sleep(1)

                # Time picker is a list on the right side; find and click the time.
                # Format in picker: "6:00 AM" or "6:00 PM"
                time_option = self.page.locator(f'text="{time_value}"').first
                if time_option.count() == 0:
                    # Try without space: "6:00AM"
                    time_option = self.page.locator(f'text=/{time_value.replace(" ", "")}/i').first

                if time_option.count() > 0:
                    time_option.click()
                    time.sleep(0.5)
                    # Click somewhere else to close picker
                    self.page.keyboard.press("Escape")
                    time.sleep(0.3)
                    self._log(f"    Set time: {time_value}")
                    return True
                else:
                    # Close picker without selecting
                    self.page.keyboard.press("Escape")
                    self._log(f"    WARN: Time '{time_value}' not found in picker")
                    return False

            self._log("    WARN: Conducted on input not found")
            return False
        except Exception as e:
            self._log(f"    Conducted on error: {str(e)[:40]}")
            try:
                self.page.keyboard.press("Escape")
            except:
                pass
            return False

    def _tick_checkbox(self, question: str) -> bool:
        """Tick a checkbox next to a question text."""
        try:
            q_el = self.page.locator(f'text="{question[:50]}"').first
            if q_el.count() == 0:
                short = question[:30]
                q_el = self.page.locator(f'text=/{short}/i').first
            if q_el.count() == 0:
                self._log(f"    WARN: Checkbox question not found")
                return False

            q_el.scroll_into_view_if_needed()
            time.sleep(0.3)

            # Look for checkbox near the question
            # Try: checkbox before the text (common pattern)
            checkbox = q_el.locator("xpath=preceding-sibling::input[@type='checkbox']").first
            if checkbox.count() == 0:
                checkbox = q_el.locator("xpath=../input[@type='checkbox']").first
            if checkbox.count() == 0:
                checkbox = q_el.locator("xpath=ancestor::label//input[@type='checkbox']").first
            if checkbox.count() == 0:
                # SafetyCulture uses custom checkboxes; look for clickable container.
                checkbox = q_el.locator("xpath=preceding-sibling::*[contains(@class,'check') or @role='checkbox']").first
            if checkbox.count() == 0:
                checkbox = q_el.locator("xpath=../*[contains(@class,'check') or @role='checkbox']").first
            if checkbox.count() == 0:
                # Try clicking the label/text itself (some checkboxes toggle on label click)
                parent = q_el.locator("xpath=ancestor::*[contains(@class,'check') or @role='checkbox']").first
                if parent.count() > 0:
                    parent.click()
                    time.sleep(0.3)
                    self._log(f"    Checkbox ticked (parent)")
                    return True
                # Last resort: click the text element itself
                q_el.click()
                time.sleep(0.3)
                self._log(f"    Checkbox ticked (text click)")
                return True

            if checkbox.count() > 0:
                checkbox.click()
                time.sleep(0.3)
                self._log(f"    Checkbox ticked")
                return True

            return False
        except Exception as e:
            self._log(f"    Checkbox error: {str(e)[:40]}")
            return False

    def _select_site(self, site_name: str) -> bool:
        """Handle SafetyCulture's site picker dropdown."""
        try:
            # Click the "Select" placeholder or the site conducted field
            select_btn = self.page.locator('text="Site conducted"').locator("xpath=following::*[contains(@class,'select') or contains(text(),'Select') or @role='combobox']").first
            if select_btn.count() == 0:
                select_btn = self.page.locator('[placeholder="Select"], [class*="site-select"], [aria-label*="Site"]').first
            if select_btn.count() == 0:
                select_btn = self.page.locator('text="Select"').first

            if select_btn.count() > 0:
                select_btn.click()
                time.sleep(1)

            # Type in search box if visible
            search = self.page.locator('input[placeholder*="Search"], input[placeholder*="search"], input[type="search"]').first
            if search.count() > 0 and search.is_visible():
                search.fill("")
                search.type(site_name[:15], delay=30)
                time.sleep(1.5)

            # Click the matching option
            option = self.page.locator(f'text="{site_name}"').first
            if option.count() == 0:
                option = self.page.locator(f'//*[contains(text(), "{site_name[:20]}")]').first

            if option.count() > 0:
                option.click()
                time.sleep(0.5)
                self._log(f"    Site selected: {site_name}")
                return True

            self._log(f"    WARN: Site option not found: {site_name}")
            return False
        except Exception as e:
            self._log(f"    Site select error: {str(e)[:40]}")
            return False

    def _try_click_answer(self, container: Locator, answer: str) -> bool:
        """Try to click a button/radio answer in the container."""
        al = answer.lower().strip()
        label_map = {
            "yes": ["Yes", "YES"], "no": ["No", "NO"],
            "n/a": ["N/A", "NA", "Not Applicable"], "not applicable": ["N/A", "NA"],
            "safe": ["Safe", "SAFE"], "unsafe": ["Unsafe", "UNSAFE", "At Risk", "Fail"],
            "at risk": ["At Risk", "Unsafe", "Fail"],
            "compliant": ["Compliant", "COMPLIANT", "Pass"],
            "non-compliant": ["Non-Compliant", "Non-compliant", "Fail"],
            "pass": ["Pass", "PASS", "Yes"], "fail": ["Fail", "FAIL", "No"],
            "good": ["Good", "Satisfactory"], "satisfactory": ["Satisfactory", "Good"],
            "unsatisfactory": ["Unsatisfactory", "Fail"],
            "acceptable": ["Acceptable", "Pass"], "not acceptable": ["Not Acceptable", "Fail"],
        }
        labels = label_map.get(al, [answer])
        for label in labels:
            btn = container.locator(
                f'button:has-text("{label}"), [role="button"]:has-text("{label}"), '
                f'[role="radio"]:has-text("{label}"), label:has-text("{label}")').first
            if btn.count() > 0:
                try:
                    btn.scroll_into_view_if_needed()
                    btn.click()
                    time.sleep(0.3)
                    self._log(f"    Clicked: {label}")
                    return True
                except:
                    continue
        return False

    def _try_fill_input(self, container: Locator, value: str) -> bool:
        """Try to fill a text/number input field in the container."""
        input_sels = [
            'input[type="number"]',
            'input[type="text"]',
            'input[type="tel"]',
            'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="file"])',
        ]
        for sel in input_sels:
            inp = container.locator(sel).first
            if inp.count() > 0:
                try:
                    if not inp.is_visible():
                        continue
                    inp.scroll_into_view_if_needed()
                    inp.click()
                    time.sleep(0.2)
                    inp.fill("")
                    inp.type(value, delay=30)
                    time.sleep(0.3)
                    # Press Tab to trigger validation/blur
                    self.page.keyboard.press("Tab")
                    time.sleep(0.2)
                    self._log(f"    Filled input: {value}")
                    return True
                except:
                    continue
        return False

    def _try_select_dropdown(self, container: Locator, value: str) -> bool:
        """Try to select a value from a dropdown/select in the container."""
        # Native select
        sel = container.locator('select').first
        if sel.count() > 0:
            try:
                sel.select_option(label=value)
                self._log(f"    Selected: {value}")
                return True
            except:
                pass

        # Custom dropdown: look for input with search/select behavior.
        # SafetyCulture uses inputs that open dropdown on click
        dropdown_inputs = container.locator('input[role="combobox"], input[aria-autocomplete], input[placeholder*="Select"], input[placeholder*="Search"]')
        if dropdown_inputs.count() > 0:
            inp = dropdown_inputs.first
            try:
                inp.click()
                time.sleep(0.5)
                inp.fill("")
                inp.type(value, delay=30)
                time.sleep(1.5)
                # Click the matching option
                option = self.page.locator(f'[role="option"]:has-text("{value}"), li:has-text("{value}"), [class*="option"]:has-text("{value}")').first
                if option.count() > 0:
                    option.click()
                    time.sleep(0.3)
                    self._log(f"    Dropdown selected: {value}")
                    return True
                # Try shorter match
                short_val = value[:20]
                option2 = self.page.locator(f'[role="option"]:has-text("{short_val}")').first
                if option2.count() > 0:
                    option2.click()
                    time.sleep(0.3)
                    self._log(f"    Dropdown selected (partial): {value}")
                    return True
                # Press Enter as fallback
                self.page.keyboard.press("Enter")
                time.sleep(0.3)
                return True
            except:
                pass

        # Custom dropdown (click trigger to open)
        dropdown_triggers = [
            '[role="combobox"]',
            '[class*="dropdown"]',
            '[class*="select"]',
            'button[aria-haspopup]',
        ]
        for trigger_sel in dropdown_triggers:
            trigger = container.locator(trigger_sel).first
            if trigger.count() > 0 and trigger.is_visible():
                try:
                    trigger.click()
                    time.sleep(0.5)
                    option = self.page.locator(
                        f'[role="option"]:has-text("{value}"), '
                        f'li:has-text("{value}"), '
                        f'[class*="option"]:has-text("{value}")'
                    ).first
                    if option.count() > 0:
                        option.click()
                        time.sleep(0.3)
                        self._log(f"    Dropdown trigger selected: {value}")
                        return True
                    # Type to search
                    self.page.keyboard.type(value, delay=30)
                    time.sleep(1)
                    option2 = self.page.locator(f'[role="option"]:has-text("{value[:15]}")').first
                    if option2.count() > 0:
                        option2.click()
                        time.sleep(0.3)
                        return True
                    self.page.keyboard.press("Enter")
                    time.sleep(0.3)
                    return True
                except:
                    continue
        return False

    def _try_fill_textarea(self, container: Locator, value: str) -> bool:
        """Try to fill a textarea in the container."""
        ta = container.locator('textarea').first
        if ta.count() > 0:
            try:
                if not ta.is_visible():
                    return False
                ta.scroll_into_view_if_needed()
                ta.click()
                time.sleep(0.2)
                ta.fill(value)
                time.sleep(0.2)
                self._log(f"    Filled textarea: {value[:30]}")
                return True
            except:
                pass
        return False

    def _try_fill_nearby_input(self, question: str, value: str) -> bool:
        """
        Last resort: find the question text, then look for the nearest
        input/textarea that follows it in the DOM.
        """
        try:
            q_el = self.page.locator(f'text="{question}"').first
            if q_el.count() == 0:
                short = question[:35].replace('"', '\\"')
                q_el = self.page.locator(f'text=/{short}/i').first
            if q_el.count() == 0:
                return False

            q_el.scroll_into_view_if_needed()
            time.sleep(0.3)

            # Look for input/textarea following the question text
            # Try sibling, parent's next sibling, etc.
            for xpath in [
                'xpath=following::input[1]',
                'xpath=following::textarea[1]',
                'xpath=../following-sibling::*//input[1]',
                'xpath=../..//input[not(@type="hidden")][1]',
                'xpath=../..//textarea[1]',
            ]:
                inp = q_el.locator(xpath).first
                if inp.count() > 0:
                    try:
                        if not inp.is_visible():
                            continue
                        tag = inp.evaluate("el => el.tagName.toLowerCase()")
                        input_type = inp.get_attribute("type") or "text"
                        # Skip buttons, checkboxes, radios, hidden, file
                        if input_type in ("hidden", "checkbox", "radio", "file", "submit"):
                            continue
                        inp.scroll_into_view_if_needed()
                        inp.click()
                        time.sleep(0.2)
                        inp.fill("")
                        inp.type(value, delay=30)
                        self.page.keyboard.press("Tab")
                        time.sleep(0.3)
                        self._log(f"    Filled nearby input: {value}")
                        return True
                    except:
                        continue
        except:
            pass
        return False

    def _find_question_container(self, question: str) -> Optional[Locator]:
        """Find the container element that wraps a question and its answer controls."""
        # Try exact match first
        q_el = self.page.locator(f'text="{question}"').first
        if q_el.count() == 0:
            # Try partial/case-insensitive match
            short = question[:35].replace('"', '\\"')
            q_el = self.page.locator(f'text=/{short}/i').first
        if q_el.count() == 0:
            # Try contains match for longer questions
            words = question.split()[:5]
            partial = " ".join(words)
            q_el = self.page.locator(f'//*[contains(text(), "{partial}")]').first
        if q_el.count() == 0:
            return None

        q_el.scroll_into_view_if_needed()
        time.sleep(0.3)

        # Walk up the DOM to find a meaningful container
        container_selectors = [
            'xpath=ancestor::*[contains(@class,"question")]',
            'xpath=ancestor::*[contains(@class,"item")]',
            'xpath=ancestor::*[contains(@class,"field")]',
            'xpath=ancestor::*[contains(@class,"response")]',
            'xpath=ancestor::*[@role="group"]',
            'xpath=ancestor::*[contains(@class,"sc-")]',
            'xpath=../../../..',
            'xpath=../../..',
            'xpath=../..',
        ]
        for sel in container_selectors:
            c = q_el.locator(sel).first
            if c.count() > 0:
                return c
        return q_el.locator("xpath=../..")

    def _go_next_page(self):
        """Click Next/Continue button to go to next page of the inspection form."""
        next_sels = [
            'button:has-text("Next")',
            'button:has-text("Next page")',
            'button:has-text("Continue")',
            'button[aria-label*="Next"]',
            'button[aria-label*="next"]',
            '[data-testid="next-page"]',
            'a:has-text("Next")',
        ]
        clicked = self._click_first_found(next_sels, timeout=5000)
        if clicked:
            time.sleep(PAGE_LOAD_WAIT)
            try:
                self.page.wait_for_load_state("networkidle", timeout=10000)
            except:
                pass
            self._log("    Page navigated")
        else:
            self._log("    WARN: Next page button not found")

    def _add_note(self, item: InspectionItem):
        nb = self._find_first(['button:has-text("Add note")', 'button:has-text("Note")',
                               '[aria-label*="note" i]'], timeout=2000)
        if nb:
            try: nb.click(); time.sleep(0.4)
            except: pass
        ni = self._find_first(['textarea[placeholder*="note" i]', 'textarea[placeholder*="comment" i]',
                               'textarea:visible'], timeout=2000)
        if ni: ni.fill(item.notes); time.sleep(0.2)

    def _upload_image_for_question(self, img_path: str, question: str) -> bool:
        """Upload image to the media control that belongs to the given question."""
        if not os.path.exists(img_path):
            img_path = self._find_image_file(img_path)
            if not img_path:
                return False

        self._log(f"    Upload: {os.path.basename(img_path)}")
        self._scroll_question_into_view(question)

        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                media_btn = self._find_media_button_for_question(question)
                if not media_btn:
                    self._log(f"    No media button for this question")
                    return False

                media_btn.scroll_into_view_if_needed()
                time.sleep(0.6)
                btn_text = self._media_button_debug_text(media_btn)
                media_before = self._count_question_media(question)

                if "add media" in (btn_text or "").lower():
                    try:
                        with self.page.expect_file_chooser(timeout=12000) as fc_info:
                            self._click_media_button(media_btn)
                            self._log(f"    Clicked media button: {btn_text or '(no label)'}")
                            time.sleep(0.8)

                            if self._click_upload_source_option():
                                self._log(f"    Clicked Upload option in popup")
                            else:
                                self._log(f"    No upload source option after Add media ({self._upload_source_debug_texts()})")

                        file_chooser = fc_info.value
                        file_chooser.set_files(img_path)
                        time.sleep(5)
                        self._wait_upload()
                        if self._wait_question_media_added(question, media_before, timeout=30):
                            self._log(f"    Upload OK (Add media -> Attach files): {os.path.basename(img_path)}")
                            return True
                        raise RuntimeError("Add media file chooser did not attach to this question")
                    except PWTimeout:
                        self._log("    Add media file chooser not triggered; trying input fallback")

                    if self._upload_via_active_file_input(img_path, question, media_before):
                        return True
                    raise RuntimeError("Add media input did not attach to this question")

                # Wrap the entire SafetyCulture source menu flow. The shared file
                # input must only be set after the question-specific media button
                # has opened the chooser, otherwise uploads attach to Signature.
                try:
                    with self.page.expect_file_chooser(timeout=10000) as fc_info:
                        self._click_media_button(media_btn)
                        self._log(f"    Clicked media button: {btn_text or '(no label)'}")
                        time.sleep(0.8)

                        if self._click_upload_source_option():
                            self._log(f"    Clicked Upload option in popup")

                    file_chooser = fc_info.value
                    file_chooser.set_files(img_path)
                    time.sleep(5)
                    self._wait_upload()
                    self._log(f"    Upload OK: {os.path.basename(img_path)}")
                    return True
                except PWTimeout:
                    raise

            except Exception as e:
                self._log(f"    Attempt {attempt+1}/{max_attempts}: {str(e)[:60]}")
                try:
                    self.page.keyboard.press("Escape")
                    time.sleep(0.5)
                except:
                    pass

        self._log(f"    Upload FAILED")
        return False

    def _click_media_button(self, media_btn):
        try:
            media_btn.click(timeout=5000)
        except Exception:
            box = media_btn.bounding_box()
            if not box:
                raise
            self.page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

    def _upload_via_active_file_input(self, img_path: str, question: str, media_before: int) -> bool:
        """
        SafetyCulture's dedicated Add media rows may not emit Playwright's file
        chooser event. After clicking Add media, set the shared input only if
        the resulting thumbnail appears in the same question card.
        """
        file_input = None
        input_deadline = time.time() + 8
        while time.time() < input_deadline and not file_input:
            file_input = self._find_file_input_for_question(question)
            if file_input:
                break
            time.sleep(0.5)
        if not file_input:
            self._log(f"    No question-scoped Add media input ({self._file_input_debug_text(question)})")
            return False

        try:
            file_input.set_input_files(img_path)
            self._wait_upload()
            deadline = time.time() + 30
            while time.time() < deadline:
                media_after = self._count_question_media(question)
                if media_after > media_before:
                    self._log(f"    Upload OK (Add media input): {os.path.basename(img_path)}")
                    return True
                time.sleep(1)
            self._log(f"    Question-scoped file input did not attach to this question (media {media_before}->{self._count_question_media(question)})")
        except Exception as e:
            self._log(f"    File input attempt failed: {str(e)[:40]}")
        return False

    def _wait_question_media_added(self, question: str, media_before: int, timeout: int = 30) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._count_question_media(question) > media_before:
                return True
            time.sleep(1)
        return False

    def _scroll_question_into_view(self, question: str):
        try:
            q_el = self.page.get_by_text(question[:60], exact=False).first
            if q_el.count() == 0:
                short = re.escape(question[:35])
                q_el = self.page.locator(f'text=/{short}/i').first
            if q_el.count() > 0:
                q_el.scroll_into_view_if_needed()
                time.sleep(1.0)
        except:
            pass

    def _find_media_button_for_question(self, question: str):
        """
        Return the Add/Attach media control scoped to a question.

        SafetyCulture keeps one shared file input on the page. Searching for the
        last visible media button or setting that input directly can attach the
        file to the Signature section. This uses browser-side geometry and the
        smallest useful ancestor containing the question to pick the nearby
        media control instead.
        """
        handle = self.page.evaluate_handle(
            """
            (question) => {
                const normalize = (s) => (s || "").replace(/\\s+/g, " ").trim().toLowerCase();
                const wanted = normalize(question);
                const words = wanted.split(" ").filter(Boolean);
                const partial = words.slice(0, Math.min(6, words.length)).join(" ");
                const isVisible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.visibility !== "hidden" &&
                        style.display !== "none" &&
                        rect.width > 0 &&
                        rect.height > 0;
                };
                const textOf = (el) => normalize([
                    el.innerText,
                    el.textContent,
                    el.getAttribute("aria-label"),
                    el.getAttribute("title"),
                    el.getAttribute("data-testid"),
                    el.getAttribute("name"),
                ].filter(Boolean).join(" "));
                const mediaSelector = [
                    "button", "a", "[role='button']", "[role='menuitem']",
                    "[aria-label]", "[data-testid]", "[tabindex]"
                ].join(",");
                const isMediaControl = (el) => {
                    const tag = el.tagName.toLowerCase();
                    const role = normalize(el.getAttribute("role"));
                    const interactive = tag === "button" ||
                        tag === "a" ||
                        role === "button" ||
                        role === "menuitem" ||
                        el.hasAttribute("tabindex") ||
                        el.onclick ||
                        normalize(el.getAttribute("aria-label")) ||
                        normalize(el.getAttribute("data-testid"));
                    if (!interactive) return false;
                    const text = textOf(el);
                    if (!text || text === wanted || text.includes(wanted)) return false;
                    if (/\\b(add note|create action)\\b/.test(text)) return false;
                    return /\\b(add|attach|upload)\\b/.test(text) &&
                        /\\b(media|photo|picture|image|file|attachment|upload)\\b/.test(text);
                };

                const qMatches = Array.from(document.querySelectorAll("body *"))
                    .filter((el) => {
                        if (!isVisible(el)) return false;
                        const text = textOf(el);
                        return text && (text.includes(wanted) || (partial && text.includes(partial)));
                    })
                    .map((el) => {
                        const rect = el.getBoundingClientRect();
                        return { el, len: textOf(el).length, area: rect.width * rect.height };
                    })
                    .sort((a, b) => (a.len - b.len) || (a.area - b.area));

                for (const match of qMatches) {
                    const qRect = match.el.getBoundingClientRect();
                    let node = match.el;
                    while (node && node !== document.body) {
                        const rootRect = node.getBoundingClientRect();
                        const candidates = Array.from(node.querySelectorAll(mediaSelector))
                            .filter((el) => isVisible(el) && isMediaControl(el))
                            .map((el) => {
                                const rect = el.getBoundingClientRect();
                                const text = textOf(el);
                                const priority =
                                    /\\badd media\\b/.test(text) ? 0 :
                                    /\\b(upload media|upload photo|upload image|add photo|add image)\\b/.test(text) ? 1 :
                                    /\\battach media\\b/.test(text) ? 2 :
                                    3;
                                const vertical = Math.abs((rect.top + rect.bottom) / 2 - (qRect.top + qRect.bottom) / 2);
                                const distance = vertical + Math.max(0, rect.left - qRect.right) / 3;
                                return { el, rect, priority, distance };
                            })
                            .filter((c) => c.rect.bottom >= qRect.top - 20)
                            .sort((a, b) => (a.priority - b.priority) || (a.distance - b.distance));

                        if (candidates.length) return candidates[0].el;

                        if (rootRect.height > 900) break;
                        node = node.parentElement;
                    }
                }
                return null;
            }
            """,
            question,
        )
        return handle.as_element()

    def _count_question_media(self, question: str) -> int:
        try:
            return int(self.page.evaluate(
                """
                (question) => {
                    const normalize = (s) => (s || "").replace(/\\s+/g, " ").trim().toLowerCase();
                    const wanted = normalize(question);
                    const partial = wanted.split(" ").filter(Boolean).slice(0, 6).join(" ");
                    const visible = (el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== "none" &&
                            style.visibility !== "hidden" &&
                            rect.width > 0 &&
                            rect.height > 0;
                    };
                    const textOf = (el) => normalize(el.innerText || el.textContent || "");
                    const hasQuestion = (el) => {
                        const text = textOf(el);
                        return text && (text.includes(wanted) || (partial && text.includes(partial)));
                    };
                    const hasMediaButton = (el) => /\\b(add media|attach media)\\b/i.test(el.innerText || "");
                    const mediaCountIn = (root) => Array.from(root.querySelectorAll("img, video, canvas, [data-testid*='media'], [data-testid*='attachment'], [class*='thumbnail'], [class*='attachment']"))
                        .filter((el) => {
                            const rect = el.getBoundingClientRect();
                            const style = window.getComputedStyle(el);
                            if (style.display === "none" || style.visibility === "hidden") return false;
                            if (rect.width <= 8 || rect.height <= 8) return false;
                            if (el.tagName.toLowerCase() === "img" && !el.getAttribute("src")) return false;
                            return true;
                        }).length;
                    const matches = Array.from(document.querySelectorAll("body *"))
                        .filter((el) => visible(el))
                        .filter(hasQuestion)
                        .map((el) => {
                            const rect = el.getBoundingClientRect();
                            return { el, len: textOf(el).length, area: rect.width * rect.height };
                        })
                        .sort((a, b) => (a.len - b.len) || (a.area - b.area));
                    if (!matches.length) return 0;

                    for (const match of matches) {
                        let node = match.el;
                        while (node && node !== document.body) {
                            const rect = node.getBoundingClientRect();
                            if (hasQuestion(node) && hasMediaButton(node) && rect.height <= 420) {
                                return mediaCountIn(node);
                            }
                            if (rect.height > 700) break;
                            node = node.parentElement;
                        }
                    }
                    return 0;
                }
                """,
                question,
            ))
        except:
            return 0

    def _find_file_input_for_question(self, question: str):
        try:
            handle = self.page.evaluate_handle(
                """
                (question) => {
                    const normalize = (s) => (s || "").replace(/\\s+/g, " ").trim().toLowerCase();
                    const wanted = normalize(question);
                    const partial = wanted.split(" ").filter(Boolean).slice(0, 6).join(" ");
                    const inputMatchesQuestion = (input) => {
                        let node = input.parentElement;
                        for (let depth = 0; node && node !== document.body && depth < 8; depth++, node = node.parentElement) {
                            const text = normalize(node.innerText || node.textContent || "");
                            if (text && (text.includes(wanted) || (partial && text.includes(partial)))) {
                                return true;
                            }
                        }
                        return false;
                    };
                    const scoreInput = (input) => {
                        const anchor = normalize(input.getAttribute("data-anchor"));
                        const cls = normalize(input.className || "");
                        const parentText = normalize(input.parentElement ? input.parentElement.innerText : "");
                        let score = 0;
                        if (anchor === "inline-file-ipt") score += 100;
                        if (anchor === "add-media-input") score -= 20;
                        if (parentText.includes("add media")) score += 50;
                        if (parentText.includes("attach media")) score -= 30;
                        if (cls.includes("hiddenfileinput")) score += 5;
                        const rect = input.getBoundingClientRect();
                        if (rect.top >= -50 && rect.top <= window.innerHeight + 50) score += 10;
                        return score;
                    };
                    const inputs = Array.from(document.querySelectorAll('input[type="file"]'))
                        .filter(inputMatchesQuestion)
                        .map((input) => ({ input, score: scoreInput(input) }))
                        .sort((a, b) => b.score - a.score);
                    return inputs.length ? inputs[0].input : null;
                }
                """,
                question,
            )
            return handle.as_element()
        except:
            return None

    def _file_input_debug_text(self, question: str) -> str:
        try:
            return self.page.evaluate(
                """
                (question) => {
                    const normalize = (s) => (s || "").replace(/\\s+/g, " ").trim().toLowerCase();
                    const wanted = normalize(question);
                    const partial = wanted.split(" ").filter(Boolean).slice(0, 6).join(" ");
                    const inputs = Array.from(document.querySelectorAll('input[type="file"]'));
                    const scoped = inputs.filter((input) => {
                        let node = input.parentElement;
                        for (let depth = 0; node && node !== document.body && depth < 8; depth++, node = node.parentElement) {
                            const text = normalize(node.innerText || node.textContent || "");
                            if (text && (text.includes(wanted) || (partial && text.includes(partial)))) {
                                return true;
                            }
                        }
                        return false;
                    });
                    return `file inputs: ${inputs.length}, question scoped: ${scoped.length}`;
                }
                """,
                question,
            )
        except:
            return "file input debug unavailable"

    def _media_button_debug_text(self, media_btn) -> str:
        try:
            return media_btn.evaluate(
                """el => [
                    el.innerText,
                    el.getAttribute('aria-label'),
                    el.getAttribute('title'),
                    el.getAttribute('data-testid')
                ].filter(Boolean).join(' ').replace(/\\s+/g, ' ').trim().slice(0, 80)"""
            )
        except:
            return ""

    def _click_upload_source_option(self) -> bool:
        handle = self.page.evaluate_handle(
            """
            () => {
                const normalize = (s) => (s || "").replace(/\\s+/g, " ").trim();
                const lower = (s) => normalize(s).toLowerCase();
                const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== "none" &&
                        style.visibility !== "hidden" &&
                        rect.width > 0 &&
                        rect.height > 0 &&
                        rect.bottom >= 0 &&
                        rect.top <= window.innerHeight &&
                        rect.right >= 0 &&
                        rect.left <= window.innerWidth;
                };
                const textOf = (el) => normalize([
                    el.getAttribute("aria-label"),
                    el.getAttribute("title"),
                    el.getAttribute("data-testid"),
                    el.getAttribute("name"),
                    el.innerText,
                ].filter(Boolean).join(" "));
                const directTextOf = (el) => normalize([
                    el.getAttribute("aria-label"),
                    el.getAttribute("title"),
                    el.getAttribute("data-testid"),
                    el.getAttribute("name"),
                    Array.from(el.childNodes)
                        .filter((node) => node.nodeType === Node.TEXT_NODE)
                        .map((node) => node.textContent)
                        .join(" "),
                    el.matches("button,a,li,[role='button'],[role='menuitem'],[role='option']")
                        ? el.innerText
                        : "",
                ].filter(Boolean).join(" "));
                const selector = [
                    "button", "a", "li", "div", "span", "[role='button']", "[role='menuitem']",
                    "[role='option']", "[aria-label]", "[data-testid]", "[tabindex]"
                ].join(",");
                const candidates = Array.from(document.querySelectorAll(selector))
                    .filter((el) => {
                        if (!visible(el)) return false;
                        if (el.hasAttribute("disabled") || el.getAttribute("aria-disabled") === "true") return false;
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 360 || rect.height > 140 || rect.width * rect.height > 45000) return false;
                        const text = lower(directTextOf(el));
                        if (!text) return false;
                        if (text.length > 120) return false;
                        if (/upload a picture of the chemicals|sanitizer bucket within range|signature to complete|yummi sushi opening checklist/.test(text)) return false;
                        if (/\\b(add media|attach media|add note|create action|take photo|camera)\\b/.test(text)) return false;
                        return /\\b(upload|browse|choose|select|from device|from computer|computer|device|file|files)\\b/.test(text) &&
                            /\\b(upload|browse|choose|select|device|computer|file|files|photo|image|media)\\b/.test(text);
                    })
                    .map((el) => {
                        const rect = el.getBoundingClientRect();
                        const text = lower(directTextOf(el));
                        const priority =
                            /upload.*(device|computer|file|files|media|photo|image)/.test(text) ? 0 :
                            /(from device|from computer|computer|device)/.test(text) ? 1 :
                            /(browse|choose|select).*(file|files|photo|image|media)/.test(text) ? 2 :
                            /\\bupload\\b/.test(text) ? 3 :
                            4;
                        const z = Number(window.getComputedStyle(el).zIndex) || 0;
                        return { el, priority, z, top: rect.top };
                    })
                    .sort((a, b) => (a.priority - b.priority) || (b.z - a.z) || (a.top - b.top));
                return candidates.length ? candidates[0].el : null;
            }
            """
        )
        opt = handle.as_element()
        if opt:
            try:
                label = self._media_button_debug_text(opt)
                try:
                    opt.click(timeout=3000)
                except Exception:
                    box = opt.bounding_box()
                    if not box:
                        raise
                    self.page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                self._log(f"    Clicked upload source: {label or '(no label)'}")
                return True
            except:
                pass
        return False

    def _upload_source_debug_texts(self) -> str:
        try:
            values = self.page.evaluate(
                """
                () => {
                    const normalize = (s) => (s || "").replace(/\\s+/g, " ").trim();
                    const visible = (el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== "none" &&
                            style.visibility !== "hidden" &&
                            rect.width > 0 &&
                            rect.height > 0 &&
                            rect.bottom >= 0 &&
                            rect.top <= window.innerHeight &&
                            rect.right >= 0 &&
                            rect.left <= window.innerWidth;
                    };
                    return Array.from(document.querySelectorAll("button,a,li,div,span,[role='button'],[role='menuitem'],[role='option']"))
                        .filter(visible)
                        .map((el) => normalize([el.innerText, el.getAttribute("aria-label"), el.getAttribute("title")].filter(Boolean).join(" ")))
                        .filter((text) => /upload|browse|choose|device|computer|file|photo|image|media/i.test(text))
                        .filter((text, index, arr) => text && arr.indexOf(text) === index)
                        .slice(0, 8);
                }
                """
            )
            return " | ".join(values)
        except:
            return ""

    def _upload_image(self, img_path: str) -> bool:
        self._log("    Upload skipped: question context is required")
        return False

    def _find_image_file(self, img_path: str) -> str:
        """Find image file regardless of extension. Handles cases like
        'chemical.jpeg' matching 'chemical.jpeg.png' or 'chemical.jpg'."""
        if os.path.exists(img_path):
            return img_path

        folder = os.path.dirname(img_path)
        filename = os.path.basename(img_path)
        name_no_ext = os.path.splitext(filename)[0]

        if not os.path.isdir(folder):
            self._log(f"    File missing: {img_path}")
            return ""

        # Search folder for matching file
        for f in os.listdir(folder):
            f_lower = f.lower()
            filename_lower = filename.lower()

            # Exact match (case insensitive)
            if f_lower == filename_lower:
                found = os.path.join(folder, f)
                return found

            # File starts with our filename (handles chemical.jpeg -> chemical.jpeg.png)
            if f_lower.startswith(filename_lower):
                found = os.path.join(folder, f)
                self._log(f"    Found image: {f}")
                return found

            # File starts with name without extension (handles chemical.jpeg -> chemical.png)
            if f_lower.startswith(name_no_ext.lower()) and f_lower != filename_lower:
                # Make sure it's an image file
                if any(f_lower.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.heic', '.gif', '.bmp']):
                    found = os.path.join(folder, f)
                    self._log(f"    Found image: {f}")
                    return found

        self._log(f"    File missing: {img_path}")
        return ""

    def _wait_upload(self):
        for sel in ['[class*="progress"]', '[role="progressbar"]', '[class*="uploading"]']:
            ind = self.page.locator(sel)
            if ind.count() > 0:
                try: ind.first.wait_for(state="hidden", timeout=30000)
                except: pass
        time.sleep(0.5)

    # ── Complete/Submit ──
    def _complete_inspection(self):
        self._log("Submitting...")
        self._scroll_to_bottom()
        time.sleep(SCROLL_DELAY)
        clicked_complete = self._click_first_found([
            'button:has-text("Complete inspection")', 'button:has-text("Complete")',
            'button:has-text("Submit")', 'button:has-text("Finish")',
        ])
        if not clicked_complete:
            ss = self._screenshot_error("complete_button_not_found")
            self._save_html_dump("complete_button_not_found")
            raise RuntimeError(f"Complete/Submit button not found. url='{self.page.url}', screenshot='{ss}'")
        time.sleep(2.0)
        # Confirm popup
        dialog = self.page.locator('[role="dialog"], [class*="modal"]')
        confirmed = False
        if dialog.count() > 0:
            for sel in ['button:has-text("Complete")', 'button:has-text("Confirm")',
                        'button:has-text("Yes")', 'button:has-text("Submit")']:
                btn = dialog.first.locator(sel).first
                if btn.count() > 0:
                    try:
                        btn.click()
                        confirmed = True
                        break
                    except: continue
        else:
            confirmed = self._click_first_found(['button:has-text("Confirm")', 'button:has-text("Complete")'], timeout=3000)
        if dialog.count() > 0 and not confirmed:
            ss = self._screenshot_error("confirm_submit_button_not_found")
            self._save_html_dump("confirm_submit_button_not_found")
            raise RuntimeError(f"Confirm submit button not found. url='{self.page.url}', screenshot='{ss}'")
        time.sleep(PAGE_LOAD_WAIT)
        self.page.wait_for_load_state("networkidle")

    def _scroll_to_section(self, name: str):
        el = self.page.locator(f'text="{name}"').first
        if el.count() > 0:
            el.scroll_into_view_if_needed(); time.sleep(SCROLL_DELAY)
        else:
            self._slow_scroll(3)

    def _slow_scroll(self, steps=3):
        for _ in range(steps):
            self.page.evaluate(f"window.scrollBy(0, {SECTION_SCROLL_STEP})")
            time.sleep(0.3)

    def _scroll_to_bottom(self):
        prev = 0
        for _ in range(50):
            self.page.evaluate(f"window.scrollBy(0, {SECTION_SCROLL_STEP})")
            time.sleep(0.2)
            cur = self.page.evaluate("window.scrollY")
            if cur == prev: break
            prev = cur

    # ── Utilities ──
    def _safe_click(self, loc: Locator, retries=MAX_RETRIES):
        for i in range(retries):
            try:
                loc.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
                loc.scroll_into_view_if_needed(); time.sleep(0.2)
                loc.click(); return
            except PWTimeout:
                if i < retries - 1: time.sleep(RETRY_DELAY)
                else: raise RuntimeError("Element not clickable")

    def _find_first(self, sels: list, timeout=3000) -> Optional[Locator]:
        for s in sels:
            try:
                el = self.page.locator(s).first
                el.wait_for(state="visible", timeout=timeout)
                return el
            except: continue
        return None

    def _click_first_found(self, sels: list, timeout=None) -> bool:
        t = timeout or DEFAULT_TIMEOUT
        for s in sels:
            try:
                el = self.page.locator(s).first
                el.wait_for(state="visible", timeout=t)
                el.scroll_into_view_if_needed(); el.click()
                return True
            except: continue
        return False

    def _check_state(self):
        if self._stopped: raise StopRequested()
        while self._paused:
            time.sleep(0.5)
            if self._stopped: raise StopRequested()

    def _screenshot_error(self, name: str) -> Optional[str]:
        try:
            os.makedirs(SCREENSHOT_DIR, exist_ok=True)
            path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
            self.page.screenshot(path=path)
            self._log(f"    Screenshot: {path}")
            return path
        except: return None

    def _save_html_dump(self, name: str):
        try:
            os.makedirs(SCREENSHOT_DIR, exist_ok=True)
            path = os.path.join(SCREENSHOT_DIR, f"{name}.html")
            html = self.page.content()
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
        except: pass

    # ── Popup Dismiss ──
    def _dismiss_popups(self):
        """Detect and close unexpected popups/dialogs."""
        try:
            for sel in POPUP_DISMISS_SELECTORS:
                btn = self.page.locator(sel)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click(timeout=2000)
                    self._log("    Dismissed popup")
                    time.sleep(0.5)
                    return True
        except:
            pass
        # Check session expired
        if self._detect_session_expired():
            self._handle_session_expired()
            return True
        return False

    def _detect_session_expired(self) -> bool:
        """Check if session expired dialog appeared."""
        try:
            expired = self.page.locator('text=/session.*expired/i, text=/logged.*out/i, text=/sign.*in.*again/i')
            return expired.count() > 0 and expired.first.is_visible()
        except:
            return False

    def _handle_session_expired(self):
        """Re-login when session expires mid-run."""
        self._log("  Session expired - re-logging in...")
        try:
            self.page.goto(SC_LOGIN_URL)
            time.sleep(PAGE_LOAD_WAIT)
            if has_saved_credentials():
                creds = load_credentials()
                if creds and self._auto_fill_login(creds[0], creds[1]):
                    self.page.wait_for_url(
                        lambda url: "/login" not in url and "safetyculture" in url, timeout=30000)
                    time.sleep(PAGE_LOAD_WAIT)
                    save_session_state(self.page)
                    self._log("  Re-login OK")
                    return
            self._log("  Re-login failed - manual intervention needed")
        except Exception as e:
            self._log(f"  Re-login error: {e}")

    # ── Network Retry Wrapper ──
    def _with_retry(self, action_name: str, fn, max_retries=RUN_RETRY_MAX):
        """Execute fn with retry on network/page errors."""
        for attempt in range(max_retries):
            try:
                return fn()
            except PWTimeout:
                if attempt < max_retries - 1:
                    self._log(f"    Retry {action_name} ({attempt+1}/{max_retries})...")
                    self._dismiss_popups()
                    time.sleep(RETRY_DELAY)
                else:
                    raise
            except Exception as e:
                err_str = str(e).lower()
                if any(k in err_str for k in ["net::", "navigation", "target closed", "crashed"]):
                    if attempt < max_retries - 1:
                        self._log(f"    Network error in {action_name}, retry ({attempt+1})...")
                        time.sleep(RETRY_DELAY * 2)
                        # Try to recover page
                        try:
                            self.page.reload()
                            time.sleep(PAGE_LOAD_WAIT)
                        except:
                            pass
                    else:
                        raise
                else:
                    raise

    # ── Dry Run (validate template on SC) ──
    def dry_run_validate(self, data: InspectionData) -> dict:
        """
        Open SC and check template + questions exist without submitting.
        Returns: {ok: bool, missing_questions: [], template_found: bool}
        """
        result = {"ok": True, "template_found": False, "missing_questions": []}
        try:
            self._go_to_inspections()
            # Check template exists
            start_sels = ['button:has-text("Start inspection")', 'button:has-text("New inspection")']
            self._click_first_found(start_sels)
            time.sleep(PAGE_LOAD_WAIT)

            search = self._find_first(['input[placeholder*="Search"]', 'input[type="search"]'], timeout=5000)
            if search:
                search.fill(""); time.sleep(0.2)
                search.type(data.template_name, delay=50)
                time.sleep(PAGE_LOAD_WAIT)

            tmpl = self.page.locator(f'text="{data.template_name}"').first
            if tmpl.count() == 0:
                result["ok"] = False
                result["template_found"] = False
                self._log(f"  DRY RUN: Template NOT found: {data.template_name}")
                # Close the dialog
                self.page.keyboard.press("Escape")
                return result

            result["template_found"] = True
            tmpl.click()
            time.sleep(STEP_DELAY)
            self._click_first_found(['button:has-text("Start")', 'button:has-text("Begin")'], timeout=5000)
            time.sleep(PAGE_LOAD_WAIT)
            self.page.wait_for_load_state("networkidle")

            # Check questions
            for item in data.items[:10]:  # Check first 10 questions
                q_el = self.page.locator(f'text="{item.question}"').first
                if q_el.count() == 0:
                    short = item.question[:35]
                    q_el = self.page.locator(f'text=/{short}/i').first
                if q_el.count() == 0:
                    result["missing_questions"].append(item.question[:50])

            if result["missing_questions"]:
                result["ok"] = False

            # Discard the inspection (don't submit)
            self.page.goto(SC_INSPECTIONS_URL)
            time.sleep(PAGE_LOAD_WAIT)
            # Handle "discard" popup if any
            discard = self.page.locator('button:has-text("Discard"), button:has-text("Leave")')
            if discard.count() > 0:
                discard.first.click()
                time.sleep(1)

        except Exception as e:
            result["ok"] = False
            self._log(f"  DRY RUN error: {e}")

        return result

    # ── Heartbeat ──
    def _heartbeat(self):
        """Update watchdog heartbeat."""
        try:
            from watchdog import beat
            beat()
        except:
            pass

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        full = f"[{ts}] {msg}"
        logger.info(msg)
        self.log_callback(full)
        self._heartbeat()


class StopRequested(Exception):
    pass
