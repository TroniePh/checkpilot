from html import escape
from unittest.mock import patch

from playwright.sync_api import sync_playwright

from automation import AutomationEngine, InspectionPageLost
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
    ace = [i for i in inspections if i.template_name == TEMPLATE]
    assert {(i.account_name, i.site_location) for i in ace} == {
        ("ace_vons_02090", "VONS 02090 (Main)"), ("von02041", "VONS 02041 (Main)")
    }
    assert len(ace) == 2 and len({i.run_time for i in ace if i.run_time}) == 2
    for expected in ace:
        assert [i for i in filter_inspections_for_run_time(inspections, expected.run_time)
                if i.template_name == TEMPLATE] == [expected]


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
        in_progress = False
        draft_html = """<main><h1>ACE Daily Food Safety Log</h1>
            <div><p>Select Your Store</p><button role="combobox">{site}</button></div>
            <div><p>Conducted on</p><input value="11/21/2026"></div>
            <div><p>Prior reading</p><input id="prior" value="existing answer"></div>
            <div><p>Missing reading</p><input id="missing" type="number" step="0.1"></div>
            <div><p>Item checked</p><input id="check" type="checkbox"></div>
            </main>"""
        visits = []

        def serve(route):
            path = route.request.url.removeprefix(BASE)
            visits.append(path)
            html = {
                NEW: (
                    f'<h1>{TEMPLATE}</h1><p>You have {2 if duplicate else 1} scheduled inspection'
                    f'{"s" if duplicate else ""} due for this template.</p>'
                    + row + (row if duplicate else "")
                    + (panel.replace("Start inspection", "Continue inspection").replace(AUDIT, AUDIT + "_draft")
                       if in_progress else panel)
                    + '<button onclick="location.href=\'/adhoc\'">Start inspection</button>'
                    + '<a href="/adhoc">Start an unscheduled inspection</a>'
                ),
                AUDIT + "?page=1": FORM_HTML,
                AUDIT + "_draft?page=1": draft_html.format(site=data.site_location),
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

            in_progress = True
            data.inspection_date = data.source_date = "2026-11-21"
            data.items = [InspectionItem("", "Prior reading", "different"),
                          InspectionItem("", "Missing reading", "12.5"),
                          InspectionItem("", "Item checked", "TRUE")]
            for account, store in [("von02090", "VONS 02090 (Main)"), ("von02041", "VONS 02041 (Main)")]:
                engine.account_name, data.site_location = account, store
                for auto in (False, True):
                    engine._stopped = False
                    visits.clear()
                    header.reset_mock()
                    alert.reset_mock()
                    complete.reset_mock()
                    with patch.object(engine, "_abandon_current_inspection") as abandon:
                        assert engine.run_inspection(data, auto_submit=auto), engine.item_errors
                        abandon.assert_not_called()
                    assert visits == [LIST, NEW, AUDIT + "_draft?page=1"]
                    assert page.locator("#prior").input_value() == "existing answer"
                    assert page.locator("#missing").input_value() == "12.5"
                    assert page.locator("#check").is_checked()
                    header.assert_not_called()
                    assert complete.call_count == int(auto)
                    alert.assert_not_called()
            data.source_date = "2026-11-03"
            complete.reset_mock()
            engine._stopped = False
            with patch.object(engine, "_abandon_current_inspection") as abandon:
                assert not engine.run_inspection(data, auto_submit=True)
                abandon.assert_not_called()
            assert page.locator("#missing").input_value() == ""
            assert not page.locator("#check").is_checked()
            complete.assert_not_called()
            data.source_date = data.inspection_date
            for changed, reason in [("site", "draft store"), ("date", "draft date"), ("signature", "missing signed")]:
                original = draft_html
                if changed == "site":
                    draft_html = original.replace("{site}", "VONS 09999 (Main)")
                elif changed == "date":
                    draft_html = original.replace("11/21/2026", "11/20/2026")
                else:
                    draft_html = original.replace("</main>", '<div><p>PIC Signature</p><button>Draw signature</button></div></main>')
                    data.items.append(InspectionItem("", "PIC Signature", "skip"))
                with patch.object(engine, "_abandon_current_inspection") as abandon:
                    assert not engine.run_inspection(data, auto_submit=True)
                    assert any(reason in e for e in engine.item_errors), engine.item_errors
                    assert page.locator("#prior").input_value() == "existing answer"
                    if changed != "signature":
                        assert page.locator("#missing").input_value() == ""
                    abandon.assert_not_called()
                complete.assert_not_called()
                draft_html = original
            in_progress = False
            alert.reset_mock()
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


def test_von_resume_all_seven_pages():
    cases = [x for x in load_data("YUMMI SAFETY CULTURE/customer_schedule_data.csv")
             if x.template_name == TEMPLATE]
    assert len(cases) == 2
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for case in cases:
            assert len(case.items) == 42
            case.source_date = case.inspection_date = "2026-11-21"
            pages = [[]]
            expected = {}
            last_section = ""
            for i, item in enumerate(case.items):
                if item.question == "NEXTPAGE":
                    pages[-1].append(f'<button onclick="location.search=\'?page={len(pages)+1}\'">Next Page</button>')
                    pages.append([])
                    last_section = ""
                    continue
                if item.section != last_section:
                    pages[-1].append(f"<h2>{escape(item.section)}</h2>")
                    last_section = item.section
                if item.question == "Conducted on":
                    control = '<input value="Nov 21, 2026">'
                elif item.question == "Select Your Store":
                    control = f'<select><option selected>{case.site_location}</option><option>VONS 09999 (Main)</option></select>'
                elif item.question.startswith("What Type of Operation"):
                    expected[f"q{i}"] = item.answer
                    control = f"""
                        <div tabindex="0" class="select-selected-container" onclick="menu.hidden=false">
                            <div class="select-value" id="choice"><span class="Placeholder">Select...</span></div>
                        </div><div class="select-menu" id="menu" hidden><input placeholder="Search">
                            <div class="option" onclick="menu.dataset.chosen=this.innerText.trim()"><span>{escape(item.answer)}</span></div>
                            <button hidden data-testid="select-menu-primary-button">Done</button>
                            <button data-testid="select-menu-primary-button" onclick="choice.firstElementChild.textContent=menu.dataset.chosen;
                              menu.hidden=true;console.log('q{i}='+menu.dataset.chosen)">Done</button></div>"""
                elif "signature" in item.question.lower():
                    control = '<button>View</button><span data-testid="saved-signature">Signed</span>'
                else:
                    item.answer = f"fixture-{i}"
                    saved = "keep" if i % 2 else ""
                    control = f'<input id="q{i}" value="{saved}" onchange="console.log(this.id + \'=\' + this.value)">'
                    if not saved:
                        expected[f"q{i}"] = item.answer
                pages[-1].append(f'<div class="QuestionCard"><p>{escape(item.question)}</p>{control}</div>')
            assert len(pages) == 7
            visits, writes = [], {}
            page = browser.new_page()
            page.on("console", lambda msg: writes.update([msg.text.split("=", 1)]) if msg.text.startswith("q") and "=" in msg.text else None)
            def serve(route):
                number = int(route.request.url.split("?page=")[-1])
                visits.append(number)
                route.fulfill(content_type="text/html; charset=utf-8",
                              body="<main><h1>" + TEMPLATE + "</h1>" + "".join(pages[number-1]) + "</main>")
            page.route("**/*", serve)
            engine = AutomationEngine(account_name=case.account_name)
            engine.page = page
            def open_existing(*args, **kwargs):
                assert kwargs["use_assigned_schedule"]
                page.goto(BASE + AUDIT + "?page=4")
                engine._resume_path = AUDIT
            with (patch("automation.time.sleep"), patch.object(engine, "_go_to_inspections"),
                  patch.object(engine, "_start_new_inspection", side_effect=open_existing),
                  patch.object(engine, "_scroll_to_bottom", side_effect=engine.stop),
                  patch.object(engine, "_complete_inspection") as submit,
                  patch("automation.send_error_alert") as alert):
                assert engine.run_inspection(case, auto_submit=False), engine.item_errors
                assert visits == [4, 1, 2, 3, 4, 5, 6, 7], visits
                assert engine._items_ok == 42
                assert writes == expected, (writes, expected)
                submit.assert_not_called()
                alert.assert_not_called()
            page.close()
        browser.close()


def test_completion_needs_receipt_on_same_audit():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.route("**/*", lambda route: route.fulfill(content_type="text/html", body="<main></main>"))
        page.goto(BASE + AUDIT)
        engine = AutomationEngine(account_name="test")
        engine.page = page
        engine.current_template, engine.current_site = TEMPLATE, "test site"
        engine._assigned_ace = True
        with patch.object(engine, "_scroll_to_bottom"), patch("automation.time") as clock:
            for button, path, valid in [
                ("Save and close", AUDIT, False),
                ("View &amp; export report", AUDIT + "other", False),
                ("View &amp; export report", AUDIT, True),
            ]:
                page.goto(BASE + AUDIT)
                page.set_content(f"""<button onclick="receipt.hidden=false;history.replaceState(null,'','{path}')">Complete inspection</button>
                    <div role="dialog" id="receipt" hidden><button>{button}</button></div>""")
                clock.monotonic.side_effect = [0, 9]
                try:
                    engine._complete_inspection()
                except InspectionPageLost:
                    assert not valid
                else:
                    assert valid
                assert engine.verify_inspection_saved(TEMPLATE) == valid
            engine._assigned_ace = False
            page.goto(BASE + AUDIT)
            page.set_content("""<button onclick="receipt.hidden=false">Complete inspection</button>
                <div role="dialog" id="receipt" hidden><button>Save and close</button></div>""")
            engine._complete_inspection()
        browser.close()


if __name__ == "__main__":
    test_von_resume_all_seven_pages()
    test_completion_needs_receipt_on_same_audit()
    test_inspection_stays_in_editor()
    test_bundled_ace_schedule_keeps_both_profiles()
    test_templates_opens_assigned_ace_and_refuses_duplicate_matches()
    test_ace_fills_controls_for_both_profiles_without_submitting()
