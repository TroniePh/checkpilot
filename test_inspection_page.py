from html import escape
from unittest.mock import patch

from playwright.sync_api import sync_playwright

from automation import AutomationEngine
from data_loader import InspectionData, InspectionItem, filter_inspections_for_run_time, load_data


BASE = "https://app.safetyculture.com"
TEMPLATE = "ACE Daily Food Safety Log"
LIST = "/templates/index"
NEW = "/inspection/new"
AUDIT = "/inspection/audit_test"
LIST_HTML = (
    f'<main><h1>{TEMPLATE}</h1><p>You have 1 scheduled inspection due for this template.</p>'
    f'<a href="{NEW}">Start inspection</a></main>'
)
FORM_HTML = f"<main><h1>{TEMPLATE}</h1><label>Select Your Store</label></main>"


def test_inspection_stays_in_editor():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.route("**/*", lambda route: route.fulfill(
            content_type="text/html",
            body=LIST_HTML if route.request.url == BASE + LIST else FORM_HTML,
        ))
        engine = AutomationEngine(account_name="test_profile")
        engine.page = page
        data = InspectionData(
            "", "", TEMPLATE,
            items=[InspectionItem("", "Mock reading", "3.87")],
        )

        def open_templates(*_args):
            page.goto(BASE + LIST)

        def enter_answer(item):
            assert item.answer == "3.87"
            page.goto(BASE + AUDIT + "?page=1")
            return True

        with (
            patch("automation.time.sleep"),
            patch("automation.send_error_alert") as alert,
            patch.object(engine, "_screenshot_error"),
            patch.object(engine, "_save_html_dump"),
            patch.object(engine, "_go_to_inspections", side_effect=open_templates),
            patch.object(engine, "_fill_header") as header,
            patch.object(engine, "_answer_question", side_effect=enter_answer) as answer,
            patch.object(engine, "_complete_inspection") as complete,
        ):
            open_templates()
            assert not engine._is_inspection_form_open(TEMPLATE)
            assert engine.run_inspection(data)
            answer.assert_called_once()
            complete.assert_called_once()
            alert.assert_not_called()

            answer.reset_mock()
            complete.reset_mock()
            header.side_effect = open_templates
            assert not engine.run_inspection(data)
            answer.assert_not_called()
            complete.assert_not_called()
            alert.assert_called_once()
            assert "scheduled inspection choice" in engine.item_errors[0]

            def answer_then_leave(_item):
                open_templates()
                return True

            answer.side_effect = answer_then_leave
            header.side_effect = None
            alert.reset_mock()
            assert not engine.run_inspection(data)
            answer.assert_called_once()
            complete.assert_not_called()
            alert.assert_called_once()


def test_bundled_ace_schedule_keeps_both_profiles():
    inspections = load_data("YUMMI SAFETY CULTURE/customer_schedule_data.csv")
    for slot, profile, site in [
        ("17:00", "ace_vons_02090", "VONS 02090 (Main)"),
        ("17:30", "von02041", "VONS 02041 (Main)"),
    ]:
        ace = [i for i in filter_inspections_for_run_time(inspections, slot)
               if i.template_name == TEMPLATE]
        assert [(i.account_name, i.site_location) for i in ace] == [(profile, site)]


def test_templates_opens_assigned_ace_and_refuses_duplicate_matches():
    title = TEMPLATE + " \u2013 Complete Daily"
    row = f'<button onclick="document.querySelector(\'#panel\').hidden=false">{title}</button>'
    panel = (
        f'<aside id="panel" hidden><h2>{title}</h2><p>{TEMPLATE}</p>'
        f'<button onclick="location.href=\'{AUDIT}?page=1\'">Start inspection</button></aside>'
    )

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        duplicate = False
        visits = []

        def serve(route):
            path = route.request.url.removeprefix(BASE)
            visits.append(path)
            html = {
                NEW: (
                    f'<h1>{TEMPLATE}</h1><p>You have {2 if duplicate else 1} scheduled inspection'
                    f'{"s" if duplicate else ""} due for this template.</p>'
                    + row + (row if duplicate else "") + panel
                    + '<a href="/adhoc">Start an unscheduled inspection</a>'
                ),
                AUDIT + "?page=1": FORM_HTML,
            }.get(path, LIST_HTML)
            route.fulfill(content_type="text/html; charset=utf-8", body=html)

        page.route("**/*", serve)
        engine = AutomationEngine(account_name="von02041")
        engine.page = page
        data = InspectionData("VONS 02041 (Main)", "", TEMPLATE)
        with (
            patch("automation.time.sleep"),
            patch("automation.send_error_alert") as alert,
            patch.object(engine, "_screenshot_error"),
            patch.object(engine, "_save_html_dump"),
            patch.object(engine, "_go_to_inspections", side_effect=lambda: page.goto(BASE + LIST)),
            patch.object(engine, "_fill_header") as header,
            patch.object(engine, "_scroll_to_bottom", side_effect=lambda: engine.stop()),
            patch.object(engine, "_complete_inspection") as complete,
        ):
            for account, store in [
                ("von02041", "VONS 02041 (Main)"),
                ("ace_vons_02090", "VONS 02090 (Main)"),
                ("von02090", "VONS 02090 (Main)"),
            ]:
                engine.account_name = account
                data.site_location = store
                engine._stopped = False
                visits.clear()
                header.reset_mock()
                assert engine.run_inspection(data, auto_submit=False), (visits, engine.item_errors)
                assert visits == [LIST, NEW, AUDIT + "?page=1"]
                header.assert_called_once()
                complete.assert_not_called()
                alert.assert_not_called()

            visits.clear()
            duplicate = True
            engine._stopped = False
            header.reset_mock()
            assert not engine.run_inspection(data, auto_submit=False)
            assert visits == [LIST, NEW]
            assert "More than one matching ACE assignment" in engine.item_errors[0]
            header.assert_not_called()
            complete.assert_not_called()
            alert.assert_called_once()


def test_ace_fills_controls_for_both_profiles_without_submitting():
    inspections = load_data("YUMMI SAFETY CULTURE/customer_schedule_data.csv")
    cases = [i for i in inspections if i.account_name in {"ace_vons_02090", "von02041"} and i.template_name == TEMPLATE]
    assert len(cases) == 2
    options = "".join(
        f'<div role="option" onclick="pickStore(this)">{escape(i.site_location)}</div>' for i in cases
    )
    form = f"""
        <main style="max-width: 760px">
        <h1>{TEMPLATE}</h1>
        <div id="part1">
          <div class="question"><p>Select Your Store</p>
            <button id="store" role="combobox" onclick="storeMenu.hidden=false">Select</button>
          </div>
          <div id="storeMenu" role="listbox" hidden>{options}</div>
          <div class="question"><p>Mock sanitation checkbox</p><input id="sanitation" type="checkbox"></div>
          <button onclick="part1.hidden=true; part2.hidden=false">Next Page</button>
        </div>
        <div id="part2" hidden>
          <div class="question"><p>Mock temperature</p><input id="temperature" type="number" step="0.1"></div>
          <div class="question"><p>Mock confirmation</p>
            <button id="answer" aria-pressed="false" onclick="this.setAttribute('aria-pressed','true')">Yes</button>
          </div>
        </div>
        </main>
        <script>
          function pickStore(option) {{
            document.querySelector('#store').textContent = option.textContent;
            document.querySelector('#storeMenu').hidden = true;
          }}
        </script>
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for case in cases:
            page = browser.new_page()
            page.route("**/*", lambda route: route.fulfill(
                content_type="text/html; charset=utf-8",
                body=LIST_HTML if route.request.url == BASE + LIST else form,
            ))
            engine = AutomationEngine(account_name=case.account_name)
            engine.page = page
            case.items = [
                InspectionItem("", "Select Your Store", case.site_location),
                InspectionItem("", "Mock sanitation checkbox", "TRUE"),
                InspectionItem("", "NEXTPAGE", "NEXTPAGE"),
                InspectionItem("", "Mock temperature", "37.4"),
                InspectionItem("", "Mock confirmation", "Yes"),
            ]
            with (
                patch("automation.time.sleep"),
                patch("automation.send_error_alert") as alert,
                patch.object(engine, "_go_to_inspections", side_effect=lambda: page.goto(BASE + LIST)),
                patch.object(engine, "_fill_header"),
                patch.object(engine, "_scroll_to_bottom", side_effect=lambda: engine.stop()),
                patch.object(engine, "_complete_inspection") as complete,
            ):
                assert engine.run_inspection(case, auto_submit=False), (case.account_name, engine.item_errors)
                assert engine._items_ok == len(case.items)
                assert page.locator("#store").text_content() == case.site_location
                assert page.locator("#sanitation").is_checked()
                assert page.locator("#part2").is_visible()
                assert page.locator("#temperature").input_value() == "37.4"
                assert page.locator("#answer").get_attribute("aria-pressed") == "true"
                alert.assert_not_called()

                engine._stopped = False
                with patch.object(engine, "_answer_question", return_value=False):
                    case.items = [case.items[0]]
                    assert not engine.run_inspection(case, auto_submit=False)
                assert engine.item_errors == ["Answer failed: Select Your Store"]
                complete.assert_not_called()
            page.close()


if __name__ == "__main__":
    test_inspection_stays_in_editor()
    test_bundled_ace_schedule_keeps_both_profiles()
    test_templates_opens_assigned_ace_and_refuses_duplicate_matches()
    test_ace_fills_controls_for_both_profiles_without_submitting()
