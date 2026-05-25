"""SafetyCulture image upload helper.

SafetyCulture keeps a shared file input for the page. Setting that input
directly is unsafe because the active upload target can be the final Signature
section. The safe path is:

1. Find the media control that belongs to the requested question/section.
2. Click that exact control.
3. Click Upload in SafetyCulture's source menu.
4. Set the file on the file chooser opened by that flow.
"""
import os
import re
import time

from playwright.sync_api import Page


def upload_to_section(page: Page, section_keyword: str, file_path: str, log_fn=None) -> bool:
    """Upload a file to the SafetyCulture media control near section_keyword."""

    def _log(msg):
        if log_fn:
            log_fn(msg)

    if not os.path.exists(file_path):
        _log(f"    File not found: {file_path}")
        return False

    _scroll_text_into_view(page, section_keyword)

    for attempt in range(3):
        try:
            media_btn = _find_media_button_for_text(page, section_keyword)
            if not media_btn:
                _log(f"    No media button for: {section_keyword[:40]}")
                return False

            media_btn.scroll_into_view_if_needed()
            time.sleep(0.6)
            btn_text = _media_button_debug_text(media_btn)

            with page.expect_file_chooser(timeout=10000) as fc_info:
                try:
                    media_btn.click(timeout=5000)
                except Exception:
                    box = media_btn.bounding_box()
                    if not box:
                        raise
                    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                _log(f"    Clicked media button: {btn_text or '(no label)'}")
                time.sleep(0.8)
                _click_upload_source_option(page)

            fc_info.value.set_files(file_path)
            _wait_upload(page)
            _log(f"    Upload OK: {os.path.basename(file_path)}")
            return True
        except Exception as exc:
            _log(f"    Attempt {attempt + 1}: {str(exc)[:60]}")
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            time.sleep(0.5)

    _log("    Upload FAILED")
    return False


def _scroll_text_into_view(page: Page, text: str):
    try:
        el = page.get_by_text(text[:60], exact=False).first
        if el.count() == 0:
            el = page.locator(f'text=/{re.escape(text[:35])}/i').first
        if el.count() > 0:
            el.scroll_into_view_if_needed()
            time.sleep(1.0)
    except Exception:
        pass


def _find_media_button_for_text(page: Page, text: str):
    handle = page.evaluate_handle(
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
                const txt = textOf(el);
                if (!txt || txt === wanted || txt.includes(wanted)) return false;
                if (/\\b(add note|create action)\\b/.test(txt)) return false;
                return /\\b(add|attach|upload)\\b/.test(txt) &&
                    /\\b(media|photo|picture|image|file|attachment|upload)\\b/.test(txt);
            };

            const qMatches = Array.from(document.querySelectorAll("body *"))
                .filter((el) => {
                    if (!isVisible(el)) return false;
                    const txt = textOf(el);
                    return txt && (txt.includes(wanted) || (partial && txt.includes(partial)));
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
                            const txt = textOf(el);
                            const priority =
                                /\\badd media\\b/.test(txt) ? 0 :
                                /\\b(upload media|upload photo|upload image|add photo|add image)\\b/.test(txt) ? 1 :
                                /\\battach media\\b/.test(txt) ? 2 :
                                3;
                            const vertical = Math.abs((rect.top + rect.bottom) / 2 - (qRect.top + qRect.bottom) / 2);
                            const distance = vertical + Math.max(0, rect.left - qRect.right) / 3;
                            return { el, rect, priority, distance };
                        })
                        .filter((candidate) => candidate.rect.bottom >= qRect.top - 20)
                        .sort((a, b) => (a.priority - b.priority) || (a.distance - b.distance));

                    if (candidates.length) return candidates[0].el;
                    if (rootRect.height > 900) break;
                    node = node.parentElement;
                }
            }
            return null;
        }
        """,
        text,
    )
    return handle.as_element()


def _media_button_debug_text(media_btn) -> str:
    try:
        return media_btn.evaluate(
            """el => [
                el.innerText,
                el.getAttribute('aria-label'),
                el.getAttribute('title'),
                el.getAttribute('data-testid')
            ].filter(Boolean).join(' ').replace(/\\s+/g, ' ').trim().slice(0, 80)"""
        )
    except Exception:
        return ""


def _click_upload_source_option(page: Page) -> bool:
    handle = page.evaluate_handle(
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
                el.innerText,
                el.textContent,
                el.getAttribute("aria-label"),
                el.getAttribute("title"),
                el.getAttribute("data-testid"),
                el.getAttribute("name"),
            ].filter(Boolean).join(" "));
            const selector = [
                "button", "a", "li", "div", "span", "[role='button']", "[role='menuitem']",
                "[role='option']", "[aria-label]", "[data-testid]", "[tabindex]"
            ].join(",");
            const candidates = Array.from(document.querySelectorAll(selector))
                .filter((el) => {
                    if (!visible(el)) return false;
                    if (el.hasAttribute("disabled") || el.getAttribute("aria-disabled") === "true") return false;
                    const text = lower(textOf(el));
                    if (!text) return false;
                    if (/\\b(add media|attach media|add note|create action|take photo|camera)\\b/.test(text)) return false;
                    return /\\b(upload|browse|choose|select|from device|from computer|computer|device|file|files)\\b/.test(text) &&
                        /\\b(upload|browse|choose|select|device|computer|file|files|photo|image|media)\\b/.test(text);
                })
                .map((el) => {
                    const rect = el.getBoundingClientRect();
                    const text = lower(textOf(el));
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
    option = handle.as_element()
    if option:
        try:
            try:
                option.click(timeout=3000)
            except Exception:
                box = option.bounding_box()
                if not box:
                    raise
                page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            return True
        except Exception:
            pass
    return False


def _wait_upload(page: Page):
    for selector in ['[class*="progress"]', '[role="progressbar"]', '[class*="uploading"]']:
        indicator = page.locator(selector)
        if indicator.count() > 0:
            try:
                indicator.first.wait_for(state="hidden", timeout=30000)
            except Exception:
                pass
    time.sleep(0.5)
