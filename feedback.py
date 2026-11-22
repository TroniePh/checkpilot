"""A minimal support report without raw logs, form answers, or credentials."""
from datetime import datetime


def _label(value):
    return " ".join(str(value or "").split())[:140]


def build_report(version, run, question, records, inspections):
    lines = [
        f"CheckPilot feedback | v{_label(version)}",
        f"Customer time: {datetime.now().astimezone().isoformat(timespec='seconds')}",
    ]
    if run.get("current_template"):
        lines += [
            f"Current: {_label(run.get('status'))} | {_label(run.get('scheduled_time'))}",
            f"{_label(run.get('current_template'))} | {_label(run.get('current_site'))}"
            f" | {_label(run.get('current_account')) or 'default'}",
            f"Current question: {_label(question) or '-'}",
        ]
    lines += ["", "Recent jobs:"]
    for record in records[:6]:
        errors = record.get("errors") or []
        kinds = set()
        for err in errors:
            err = str(err).lower()
            if "scheduled inspection" in err or "inspection editor" in err:
                kinds.add("inspection not open")
            elif "next page" in err:
                kinds.add("page navigation")
            elif "answer failed" in err:
                kinds.add("answer not filled")
            elif "image" in err or "upload" in err:
                kinds.add("media upload")
            else:
                kinds.add("other error")
        status = "OK" if record.get("success") else "FAILED"
        suffix = " - " + ", ".join(sorted(kinds)) if kinds else ""
        lines.append(
            f"{_label(record.get('timestamp'))} | {status} ({len(errors)}) | "
            f"{_label(record.get('template'))} | {_label(record.get('site'))}{suffix}"
        )
    lines += ["", "Loaded schedule (customer time):"]
    for i in inspections[:16]:
        lines.append(
            f"{_label(i.run_time) or '-'} | {_label(i.account_name) or 'default'} | "
            f"{_label(i.site_location)} | {_label(i.template_name)}"
        )
    return "\n".join(lines)[:3600]
