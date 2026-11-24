"""
CheckPilot - Inspection Automation Assistant
Designed by Pham Duy | 0868609901
Full-featured SaaS UI with dashboard, validation, history, test run
"""
import logging
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional
from datetime import datetime, date

import customtkinter as ctk

from data_loader import (
    load_data,
    validate_data,
    validate_detailed,
    InspectionData,
    rename_account_in_csv,
    filter_inspections_for_run_time,
    get_inspection_schedule_times,
)
from automation import AutomationEngine
from auth import (
    authenticate, init_default_admin, get_saved_session, logout,
    get_license_info, activate_license, change_password,
)
from session_manager import (
    has_saved_credentials, save_credentials, load_credentials,
    has_saved_session as has_sc_session, clear_all as clear_sc_login,
    list_account_profiles, get_account_profile_details, save_account_profile,
    delete_account_profile, rename_account_profile,
)
from notifier import (
    load_telegram_config, save_telegram_config, test_connection as test_telegram,
    send_daily_summary, send_error_alert, send_feedback, send_inspection_status, send_success_report,
)
from feedback import build_report
from runlock import (
    is_already_run_today, mark_completed, get_remaining, reset_today,
    inspection_run_key,
)
from template_lock import (
    fingerprint_inspection,
    get_invalid_templates,
    mark_template_tested,
)
from scheduler import (
    Scheduler, load_schedule, save_schedule,
    get_next_run_datetime, is_schedule_due_now, mark_schedule_run,
)
from history import add_record, get_records, get_stats, export_csv
from reporter import generate_report
from run_state import (
    clear_run_state,
    is_interrupted_auto_run,
    load_run_state,
    start_run_state,
    update_run_state,
)
from tray import TrayIcon
from config import BASE_DIR
from autostart import (
    save_last_config, get_last_data_file, get_last_image_folder,
    load_autostart_config, save_autostart_config,
    register_windows_startup, is_registered_startup,
    register_prelogin_task, is_prelogin_task_registered,
    build_validation_state, save_validation_state, is_validation_current,
)

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# â”€â”€ Palette â”€â”€
BG = "#F7F9FC"
CARD = "#FFFFFF"
ELEVATED = "#EEF2F7"
BORDER = "#D7DEE8"
TXT = "#172033"
DIM = "#44546A"
MUTED = "#7A8699"
TEAL = "#0F766E"
TEAL_H = "#0B5F59"
GREEN = "#15803D"
AMBER = "#B45309"
RED = "#B91C1C"
RED_H = "#991B1B"
F = "Segoe UI"
MAX_CONSECUTIVE_FAILURES = 3
LOG_OPEN_H = 130

BUTTON_STYLES = {
    "primary": dict(fg_color=TEAL, hover_color=TEAL_H, text_color="#FFFFFF",
                    text_color_disabled="#B9DCD8", border_width=0),
    "secondary": dict(fg_color=CARD, hover_color=ELEVATED, text_color=TXT,
                      text_color_disabled=MUTED, border_width=1, border_color=BORDER),
    "danger": dict(fg_color=CARD, hover_color="#FDECEC", text_color=RED,
                   text_color_disabled="#E3A6A6", border_width=1, border_color="#EBC3C3"),
    "ghost": dict(fg_color="transparent", hover_color=ELEVATED, text_color=DIM,
                  text_color_disabled=MUTED, border_width=0),
}


def _font(size=11, bold=False):
    return ctk.CTkFont(family=F, size=size, weight="bold" if bold else "normal")


def _apply_theme():
    """Teal accents for every themed widget (the stock "blue" theme otherwise leaks through)."""
    pair = lambda c: [c, c]
    t = ctk.ThemeManager.theme
    t["CTkButton"].update(fg_color=pair(TEAL), hover_color=pair(TEAL_H))
    t["CTkCheckBox"].update(fg_color=pair(TEAL), hover_color=pair(TEAL_H), border_color=pair("#A9B4C4"),
                            checkmark_color=pair("#FFFFFF"), text_color=pair(DIM), corner_radius=4, border_width=2)
    t["CTkSwitch"].update(progress_color=pair(TEAL), fg_color=pair("#A9B4C4"), button_color=pair("#FFFFFF"),
                          button_hover_color=pair("#F1F5F9"), text_color=pair(TXT))
    t["CTkProgressBar"].update(progress_color=pair(TEAL), fg_color=pair(BORDER))
    t["CTkOptionMenu"].update(fg_color=pair(ELEVATED), button_color=pair(ELEVATED),
                              button_hover_color=pair(BORDER), text_color=pair(TXT))
    t["CTkEntry"].update(border_color=pair(BORDER), fg_color=pair(CARD), text_color=pair(TXT))
    t["CTkLabel"].update(text_color=pair(TXT))
    t["CTkScrollbar"].update(button_color=pair(BORDER), button_hover_color=pair(MUTED))
    t["CTkFont"].update(family=F, size=12)  # ThemeManager already picked the platform entry


_apply_theme()


def _inspection_account(insp) -> str:
    return str(getattr(insp, "account_name", "") or "").strip()


def _account_label(account_name: str) -> str:
    return account_name or "default"


def _group_by_account(inspections: list) -> list:
    order = []
    groups = {}
    for insp in inspections:
        account = _inspection_account(insp)
        if account not in groups:
            groups[account] = []
            order.append(account)
        groups[account].append(insp)
    return [insp for account in order for insp in groups[account]]


def _missing_login_accounts(inspections: list) -> list:
    missing = []
    seen = set()
    for insp in inspections:
        account = _inspection_account(insp)
        if account in seen:
            continue
        seen.add(account)
        if not has_sc_session(account) and not has_saved_credentials(account):
            missing.append(_account_label(account))
    return missing


def _filter_login_ready(inspections: list) -> tuple:
    ready = []
    missing = []
    seen = set()
    for insp in inspections:
        account = _inspection_account(insp)
        if has_sc_session(account) or has_saved_credentials(account):
            ready.append(insp)
            continue
        label = _account_label(account)
        if label not in seen:
            missing.append(label)
            seen.add(label)
    return ready, missing


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("CheckPilot")
        self.geometry("1100x760")
        self.minsize(1000, 680)
        self.configure(fg_color=BG)
        ico = os.path.join(BASE_DIR, "assets", "icon.ico")
        if os.path.exists(ico):
            try: self.iconbitmap(ico)
            except: pass

        self.current_user = None
        self.engine: Optional[AutomationEngine] = None
        self.inspections = []
        self.worker_thread = None
        self.scheduler: Optional[Scheduler] = None
        self.tray: Optional[TrayIcon] = None
        self._data_file = ""
        self._image_folder = ""
        self._scheduled_run = False
        self._run_errors = []
        self._full_inspections = None
        self._schedule_full_inspections = None
        self._active_schedule_time = ""
        self.selected_inspection_index = None
        self._run_active = False
        self._waiting_for_schedule = False
        self._run_state_text = "Sẵn sàng"
        self._run_state_color = TEAL
        self._run_stats_text = "0/0 inspection · Thành công 0 · Lỗi 0 · Còn lại 0"
        self._run_progress = 0.0

        # Persistent StringVars (survive tab switches)
        self.fv = tk.StringVar()
        self.iv = tk.StringVar()
        _acfg = load_autostart_config()
        self.fv.set(_acfg.get("last_data_file", ""))
        self.iv.set(_acfg.get("last_image_folder", ""))
        self._validation_state = _acfg.get("validation_state") or None

        # Run options (also survive tab switches)
        self.rv = ctk.BooleanVar(value=False)   # test mode
        self.av = ctk.BooleanVar(value=True)    # auto submit
        self.sv = ctk.BooleanVar(value=True)    # pause after each inspection
        self.adv = ctk.BooleanVar(value=True)   # inspection date = today
        self.rv.trace_add("write", lambda *_: self._on_test_mode_changed())
        self.av.trace_add("write", lambda *_: self._update_auto_submit_warning())
        self._log_open = True
        self._last_log_line = ""

        self.protocol("WM_DELETE_WINDOW", self._to_tray)
        init_default_admin()

        s = get_saved_session()
        if s:
            self.current_user = s.get("username")
            self._main()
        else:
            self._login()

    def _to_tray(self):
        self.withdraw()
        if not self.tray:
            self.tray = TrayIcon(on_show=self._from_tray, on_quit=self._quit)
        self.tray.show()

    def _from_tray(self):
        if self.tray: self.tray.hide()
        self._safe_after(0, lambda: (self.deiconify(), self.lift(), self.focus_force()))

    def _quit(self):
        if self.scheduler: self.scheduler.stop()
        if self.tray: self.tray.hide()
        self._safe_after(0, self.destroy)

    # â•â•â•â•â•â•â•â•â•â•â• LOGIN â•â•â•â•â•â•â•â•â•â•â•
    def _login(self):
        self._wipe()
        c = ctk.CTkFrame(self, fg_color="transparent")
        c.place(relx=0.5, rely=0.48, anchor="center")
        ctk.CTkLabel(c, text="CheckPilot", font=ctk.CTkFont(family=F, size=32, weight="bold"),
                     text_color=TEAL).pack(pady=(0,2))
        ctk.CTkLabel(c, text="Inspection Automation Assistant",
                     font=ctk.CTkFont(family=F, size=12), text_color=DIM).pack(pady=(0,26))
        card = ctk.CTkFrame(c, corner_radius=14, fg_color=CARD, border_width=1,
                            border_color=BORDER, width=360, height=270)
        card.pack(); card.pack_propagate(False)
        ctk.CTkLabel(card, text="Đăng nhập", font=ctk.CTkFont(family=F, size=15, weight="bold"),
                     text_color=TXT).pack(pady=(26,16))
        self._lu = ctk.CTkEntry(card, placeholder_text="Tên đăng nhập", width=260, height=38,
                                 corner_radius=7, border_color=BORDER, font=ctk.CTkFont(family=F, size=12))
        self._lu.pack(pady=(0,8))
        self._lp = ctk.CTkEntry(card, placeholder_text="Mật khẩu", show="*", width=260, height=38,
                                 corner_radius=7, border_color=BORDER, font=ctk.CTkFont(family=F, size=12))
        self._lp.pack(pady=(0,16))
        ctk.CTkButton(card, text="Đăng nhập", width=260, height=38, corner_radius=7,
                      fg_color=TEAL, hover_color=TEAL_H, font=ctk.CTkFont(family=F, size=12, weight="bold"),
                      command=self._do_login).pack()
        self._lerr = ctk.CTkLabel(card, text="", font=ctk.CTkFont(family=F, size=10), text_color=RED)
        self._lerr.pack(pady=(8,0))
        ctk.CTkLabel(c, text="by Phạm Duy - 0868609901", font=ctk.CTkFont(family=F, size=9),
                     text_color=MUTED).pack(pady=(20,0))
        self._lp.bind("<Return>", lambda e: self._do_login())

    def _do_login(self):
        u, p = self._lu.get().strip(), self._lp.get().strip()
        if not u or not p: self._lerr.configure(text="Nhập đầy đủ"); return
        ok, msg, user = authenticate(u, p)
        if ok:
            if user.get("must_change_password"):
                if not self._force_password_change(u, p):
                    self._lp.delete(0, "end")
                    return
            self.current_user = u
            self._main()
        else: self._lerr.configure(text=msg); self._lp.delete(0,"end")

    def _force_password_change(self, username, old_password):
        messagebox.showwarning(
            "Đổi mật khẩu",
            "Tài khoản admin mặc định phải đổi mật khẩu trước khi sử dụng."
        )
        new_password = simpledialog.askstring("Đổi mật khẩu", "Nhập mật khẩu mới:", show="*")
        if not new_password:
            self._lerr.configure(text="Cần đổi mật khẩu mặc định")
            logout()
            return False
        confirm = simpledialog.askstring("Đổi mật khẩu", "Nhập lại mật khẩu mới:", show="*")
        if new_password != confirm:
            self._lerr.configure(text="Mật khẩu nhập lại không khớp")
            logout()
            return False
        ok, msg = change_password(username, old_password, new_password)
        if not ok:
            self._lerr.configure(text=msg)
            logout()
            return False
        messagebox.showinfo("OK", "Đã đổi mật khẩu. Vui lòng đăng nhập bằng mật khẩu mới.")
        logout()
        return False

    # ═══════════ MAIN LAYOUT ═══════════
    PAGES = {
        "auto": ("Tự động", "Chuẩn bị dữ liệu, chọn chế độ rồi chạy inspection"),
        "sched": ("Lịch chạy", "Máy bật 24/7 - tự chạy inspection đúng giờ, nhiều lần mỗi ngày"),
        "history": ("Lịch sử", "Kết quả các lần chạy gần đây"),
        "accounts": ("Tài khoản", "Tài khoản SafetyCulture dùng để đăng nhập và chạy template"),
        "settings": ("Cài đặt", "License, thư mục template, khởi động cùng Windows và Telegram"),
        "diag": ("Chẩn đoán", "Thông tin hệ thống và công cụ xử lý sự cố"),
        "about": ("Thông tin", "CheckPilot - Inspection Automation Assistant"),
    }

    def _main(self):
        self._wipe()
        self._apply_ttk_style()
        self._nav_btns = {}

        # Sidebar
        sb = ctk.CTkFrame(self, width=200, corner_radius=0, fg_color=CARD)
        sb.pack(side="left", fill="y"); sb.pack_propagate(False)
        ctk.CTkFrame(self, width=1, corner_radius=0, fg_color=BORDER).pack(side="left", fill="y")
        brand = ctk.CTkFrame(sb, fg_color="transparent"); brand.pack(fill="x", padx=20, pady=(20, 18))
        ctk.CTkLabel(brand, text="CheckPilot", font=_font(18, True), text_color=TEAL).pack(anchor="w")
        ctk.CTkLabel(brand, text="Inspection Automation", font=_font(10), text_color=MUTED).pack(anchor="w")
        for key, cmd in [("auto", self._pg_auto), ("sched", self._pg_sched),
                         ("history", self._pg_history), ("accounts", self._pg_accounts),
                         ("settings", self._pg_settings), ("diag", self._pg_diag)]:
            b = ctk.CTkButton(sb, text=self.PAGES[key][0], width=172, height=38, anchor="w",
                              corner_radius=7, font=_font(12), fg_color="transparent",
                              hover_color=ELEVATED, text_color=DIM, command=cmd)
            b.pack(padx=14, pady=2)
            self._nav_btns[key] = b

        from updater import get_current_version
        foot = ctk.CTkFrame(sb, fg_color="transparent"); foot.pack(side="bottom", fill="x", padx=20, pady=16)
        lic = get_license_info()
        lic_row = ctk.CTkFrame(foot, fg_color="transparent"); lic_row.pack(fill="x")
        ctk.CTkLabel(lic_row, text="License", font=_font(10), text_color=MUTED).pack(side="left")
        self.lic_badge = ctk.CTkLabel(lic_row, text=lic.get("plan", "trial").title(), font=_font(10, True),
                                      text_color=GREEN if lic.get("valid") else RED)
        self.lic_badge.pack(side="left", padx=(6, 0))
        ver_row = ctk.CTkFrame(foot, fg_color="transparent"); ver_row.pack(fill="x", pady=(2, 0))
        ctk.CTkLabel(ver_row, text=f"Phiên bản {get_current_version()}", font=_font(10),
                     text_color=MUTED).pack(side="left")
        about = ctk.CTkButton(ver_row, text="Thông tin", width=60, height=22, corner_radius=5,
                              font=_font(10), fg_color="transparent", hover_color=ELEVATED,
                              text_color=TEAL, command=self._pg_about)
        about.pack(side="right")
        self._nav_btns["about"] = about

        # Main column: topbar, page, log
        main = ctk.CTkFrame(self, fg_color="transparent"); main.pack(side="left", fill="both", expand=True)
        top = ctk.CTkFrame(main, height=62, corner_radius=0, fg_color=CARD)
        top.pack(fill="x"); top.pack_propagate(False)
        ctk.CTkFrame(main, height=1, corner_radius=0, fg_color=BORDER).pack(fill="x")
        tl = ctk.CTkFrame(top, fg_color="transparent"); tl.pack(side="left", padx=24)
        self.page_title_lbl = ctk.CTkLabel(tl, text="", font=_font(16, True), text_color=TXT)
        self.page_title_lbl.pack(anchor="w")
        self.page_sub_lbl = ctk.CTkLabel(tl, text="", font=_font(10), text_color=MUTED)
        self.page_sub_lbl.pack(anchor="w")
        rt = ctk.CTkFrame(top, fg_color="transparent"); rt.pack(side="right", padx=20)
        ctk.CTkLabel(rt, text=self.current_user or "", font=_font(11, True),
                     text_color=DIM).pack(side="left", padx=(0, 12))
        self._btn(rt, "Thu nhỏ", self._to_tray, "secondary", width=72, height=28).pack(side="left", padx=(0, 6))
        self._btn(rt, "Đăng xuất", self._logout, "secondary", width=80, height=28).pack(side="left", padx=(0, 6))
        self._btn(rt, "Thoát", self._quit, "danger", width=60, height=28).pack(side="left")

        content = ctk.CTkFrame(main, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24, pady=(16, 14))
        self.pg_host = ctk.CTkFrame(content, fg_color="transparent")
        self.pg_host.pack(fill="both", expand=True)

        # Persistent log panel (bottom, never destroyed, collapsible)
        self.log_frame = ctk.CTkFrame(content, corner_radius=10, fg_color=CARD,
                                      border_width=1, border_color=BORDER, height=LOG_OPEN_H)
        self.log_frame.pack(fill="x", pady=(10, 0))
        self.log_frame.pack_propagate(False)
        log_top = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        log_top.pack(fill="x", padx=14, pady=(7, 4))
        ctk.CTkLabel(log_top, text="Nhật ký", font=_font(11, True), text_color=TXT).pack(side="left")
        self.log_toggle_btn = self._btn(log_top, "Thu gọn", self._toggle_log, "ghost", width=70, height=24)
        self.log_toggle_btn.pack(side="right")
        self._btn(log_top, "Xóa", self._clog, "ghost", width=46, height=24).pack(side="right", padx=(0, 4))
        self.log_last_lbl = ctk.CTkLabel(log_top, text="", font=_font(10), text_color=MUTED, anchor="w")
        self.log_last_lbl.pack(side="left", fill="x", expand=True, padx=(12, 8))
        self.logbox = ctk.CTkTextbox(self.log_frame, font=ctk.CTkFont(family="Consolas", size=10),
                                     state="disabled", corner_radius=6, fg_color=BG,
                                     text_color=DIM, border_width=0)
        self._log_open = True
        self.logbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        sc = load_schedule()
        if sc.get("enabled"):
            self.scheduler = Scheduler(run_callback=self._sched_run, log_callback=self._log)
            self.scheduler.start()
        self._pg_auto()

        # Auto-load last used config
        self._safe_after(500, self._auto_load_last_config)

        # Auto-check for updates on startup (silent, non-blocking)
        self._safe_after(2000, self._startup_update_check)

    def _toggle_log(self):
        self._log_open = not self._log_open
        if self._log_open:
            self.logbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            self.log_frame.configure(height=LOG_OPEN_H)
            self._safe_config("log_toggle_btn", text="Thu gọn")
            self._safe_config("log_last_lbl", text="")
        else:
            self.logbox.pack_forget()
            self.log_frame.configure(height=40)
            self._safe_config("log_toggle_btn", text="Mở rộng")
            self._safe_config("log_last_lbl", text=self._last_log_line)

    # ═══════════ PAGE: AUTOMATION ═══════════
    def _pg_auto(self):
        self._cls("auto", scroll=True)
        # Step 1: data
        c1 = self._card("Dữ liệu", "File CSV/Excel và thư mục ảnh", step=1)
        for label, var, cmd in [("File dữ liệu", self.fv, self._pick_f), ("Thư mục ảnh", self.iv, self._pick_d)]:
            r = self._row(c1, label)
            self._btn(r, "Đổi…", cmd, "secondary", width=70).pack(side="right")
            ctk.CTkEntry(r, textvariable=var, height=32, corner_radius=6, border_color=BORDER,
                         font=_font(11)).pack(side="left", fill="x", expand=True, padx=(0, 8))
        r3 = self._row(c1, "", pady=(8, 4))
        self._btn(r3, "Kiểm tra", self._validate, "secondary", width=90).pack(side="left", padx=(0, 6))
        self._btn(r3, "Tải dữ liệu", self._load, "secondary", width=100).pack(side="left")
        self.load_lbl = ctk.CTkLabel(r3, text="", font=_font(11, True))
        self.load_lbl.pack(side="left", padx=12)
        if self.inspections:
            items = sum(len(i.items) for i in self.inspections)
            self.load_lbl.configure(text=f"✓ {len(self.inspections)} inspection · {items} mục", text_color=GREEN)
        elif self._has_validated_current_file():
            self.load_lbl.configure(text="Dữ liệu hợp lệ", text_color=GREEN)
        else:
            self.load_lbl.configure(text="Chưa tải dữ liệu", text_color=MUTED)

        ctk.CTkFrame(c1, height=1, fg_color=BORDER).pack(fill="x", padx=16, pady=(8, 8))
        pr = self._row(c1, "Chạy thử", pady=(0, 14))
        self.template_picker_btn = self._btn(pr, "Chọn mục…", self._open_inspection_picker,
                                             "secondary", width=96, state="disabled")
        self.template_picker_btn.pack(side="left", padx=(0, 6))
        self.btest = self._btn(pr, "Chạy thử mục đã chọn", self._test_run, "secondary", width=150, state="disabled")
        self.btest.pack(side="left", padx=(0, 6))
        self.clear_template_btn = self._btn(pr, "Bỏ chọn", self._clear_inspection_selection,
                                            "ghost", width=70, state="disabled")
        self.clear_template_btn.pack(side="left")
        self.selected_insp_lbl = ctk.CTkLabel(pr, text="", font=_font(10), text_color=MUTED, anchor="w")
        self.selected_insp_lbl.pack(side="left", fill="x", expand=True, padx=(12, 0))
        self._render_inspection_list()

        # Step 2: mode
        c2 = self._card("Chế độ", step=2)
        mr = self._row(c2, "Khi chạy")
        seg = ctk.CTkFrame(mr, fg_color=ELEVATED, corner_radius=8)
        seg.pack(side="left")
        self.mode_test_btn = ctk.CTkButton(seg, text="Thử – không submit", width=150, height=30,
                                           corner_radius=6, font=_font(11),
                                           command=lambda: self._set_auto_submit(False))
        self.mode_test_btn.pack(side="left", padx=(3, 0), pady=3)
        self.mode_auto_btn = ctk.CTkButton(seg, text="Tự động submit", width=150, height=30,
                                           corner_radius=6, font=_font(11),
                                           command=lambda: self._set_auto_submit(True))
        self.mode_auto_btn.pack(side="left", padx=3, pady=3)
        self.auto_warn_lbl = ctk.CTkLabel(mr, text="", font=_font(10), text_color=AMBER, anchor="w")
        self.auto_warn_lbl.pack(side="left", padx=(14, 0))
        orow = self._row(c2, "", pady=(8, 14))
        ctk.CTkCheckBox(orow, text="Ngày = hôm nay", variable=self.adv, font=_font(11),
                        checkbox_width=18, checkbox_height=18).pack(side="left", padx=(0, 20))
        ctk.CTkCheckBox(orow, text="Tạm dừng sau mỗi inspection", variable=self.sv, font=_font(11),
                        checkbox_width=18, checkbox_height=18).pack(side="left")

        # Step 3: run
        c3 = self._card("Chạy", step=3)
        cr = ctk.CTkFrame(c3, fg_color="transparent"); cr.pack(fill="x", padx=16, pady=(0, 8))
        self.brun_now = self._btn(cr, "▶  Chạy ngay", self._run_now, "primary", width=124, height=36, state="disabled")
        self.brun_now.pack(side="left", padx=(0, 6))
        self.bstart = self._btn(cr, "Chờ lịch", self._start_scheduled, "secondary", width=92, height=36, state="disabled")
        self.bstart.pack(side="left", padx=(0, 18))
        self.bpause = self._btn(cr, "Tạm dừng", self._pause, "secondary", width=92, height=36, state="disabled")
        self.bpause.pack(side="left", padx=(0, 6))
        self.bstop = self._btn(cr, "Dừng", self._stop, "danger", width=72, height=36, state="disabled")
        self.bstop.pack(side="left")
        self._btn(cr, "Chạy lại lỗi", self._retry_failed, "ghost", width=100, height=36).pack(side="right")
        sr = ctk.CTkFrame(c3, fg_color="transparent"); sr.pack(fill="x", padx=16, pady=(4, 4))
        self.slbl = ctk.CTkLabel(sr, text="Sẵn sàng", font=_font(12, True), text_color=TEAL)
        self.slbl.pack(side="left")
        self.run_stat_lbl = ctk.CTkLabel(sr, text=self._run_stats_text, font=_font(10), text_color=DIM)
        self.run_stat_lbl.pack(side="right")
        self.prog = ctk.CTkProgressBar(c3, height=6, corner_radius=3)
        self.prog.pack(fill="x", padx=16, pady=(2, 16)); self.prog.set(0)
        self._sync_run_controls()

    def _set_auto_submit(self, auto: bool):
        # Clear test mode first so the auto-submit trace does not undo the change.
        self.rv.set(not auto)
        self.av.set(auto)

    def _refresh_mode_buttons(self):
        auto = bool(self.av.get()) and not bool(self.rv.get())
        for name, active in [("mode_auto_btn", auto), ("mode_test_btn", not auto)]:
            self._safe_config(name, fg_color=TEAL if active else "transparent",
                              hover_color=TEAL_H if active else BORDER,
                              text_color="#FFFFFF" if active else DIM)

    def _pg_history(self):
        self._cls("history")
        stats = get_stats()
        dash = ctk.CTkFrame(self.pg, fg_color="transparent")
        dash.pack(fill="x", pady=(0, 10))
        tiles = [("Hôm nay", stats["today"], TEAL), ("Thành công", stats["success"], GREEN),
                 ("Lỗi", stats["failed"], RED), ("Tổng số lần chạy", stats["total"], TXT)]
        for i, (lbl, val, col) in enumerate(tiles):
            box = ctk.CTkFrame(dash, corner_radius=10, fg_color=CARD, border_width=1, border_color=BORDER)
            box.grid(row=0, column=i, padx=(0 if i == 0 else 5, 0 if i == len(tiles) - 1 else 5), sticky="nsew")
            dash.grid_columnconfigure(i, weight=1, uniform="stat")
            ctk.CTkLabel(box, text=lbl, font=_font(10), text_color=MUTED).pack(anchor="w", padx=14, pady=(8, 0))
            ctk.CTkLabel(box, text=str(val), font=_font(18, True), text_color=col).pack(anchor="w", padx=14, pady=(0, 8))

        top_row = ctk.CTkFrame(self.pg, fg_color="transparent"); top_row.pack(fill="x", pady=(0, 10))
        self._btn(top_row, "Xuất CSV", self._export_history, "primary", width=96).pack(side="left", padx=(0, 6))
        self._btn(top_row, "Xóa lịch sử", self._clear_history, "danger", width=100).pack(side="left")

        records = get_records(100)
        box = ctk.CTkFrame(self.pg, corner_radius=10, fg_color=CARD, border_width=1, border_color=BORDER)
        box.pack(fill="both", expand=True)
        if not records:
            ctk.CTkLabel(box, text="Chưa có lịch sử chạy", font=_font(11), text_color=MUTED).pack(pady=30)
            return
        inner = ctk.CTkFrame(box, fg_color="transparent"); inner.pack(fill="both", expand=True, padx=8, pady=8)
        cols = ("status", "time", "template", "site", "error")
        tree = ttk.Treeview(inner, columns=cols, show="headings")
        for col, text, width, stretch in [("status", "Kết quả", 100, False), ("time", "Thời gian", 130, False),
                                          ("template", "Template", 260, True), ("site", "Site", 170, True),
                                          ("error", "Lỗi", 260, True)]:
            tree.heading(col, text=text, anchor="w")
            tree.column(col, width=width, minwidth=60, stretch=stretch, anchor="w")
        tree.tag_configure("err", foreground=RED)
        for r in records:
            ok = r.get("success")
            errs = r.get("errors", [])
            tree.insert("", "end", tags=() if ok else ("err",), values=(
                "✓ Thành công" if ok else "✗ Lỗi",
                r.get("timestamp", "")[:16].replace("T", " "),
                r.get("template", ""), r.get("site", ""),
                errs[0] if errs else "",
            ))
        ys = ttk.Scrollbar(inner, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=ys.set)
        ys.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)

    # ═══════════ PAGE: SCHEDULER ═══════════
    def _pg_sched(self):
        self._cls("sched", scroll=True)
        sched = load_schedule()

        c1 = self._card("Trạng thái")
        r = ctk.CTkFrame(c1, fg_color="transparent"); r.pack(fill="x", padx=16, pady=(0, 14))
        self.se = ctk.BooleanVar(value=sched.get("enabled", False))
        ctk.CTkSwitch(r, text="Bật lịch chạy", variable=self.se, font=_font(12, True)).pack(side="left")
        self.template_times_var = ctk.BooleanVar(value=sched.get("template_times", True))
        ctk.CTkCheckBox(r, text="Dùng giờ theo từng template trong CSV", variable=self.template_times_var,
                        font=_font(11), checkbox_width=18, checkbox_height=18).pack(side="left", padx=(24, 0))
        if self.scheduler:
            ctk.CTkLabel(c1, text=f"Lần chạy tiếp: {self.scheduler.get_next_run()}", font=_font(11),
                         text_color=TEAL).pack(anchor="w", padx=16, pady=(0, 12))

        # Multi-time section
        c2 = self._card("Giờ chạy", "Có thể đặt nhiều giờ mỗi ngày")
        self._sched_times = list(sched.get("times", [sched.get("time", "05:00")]))
        if isinstance(self._sched_times, str):
            self._sched_times = [self._sched_times]
        self._times_frame = ctk.CTkFrame(c2, fg_color="transparent")
        self._times_frame.pack(fill="x", padx=16, pady=(0, 4))
        self._render_times_list()

        add_row = ctk.CTkFrame(c2, fg_color="transparent"); add_row.pack(fill="x", padx=16, pady=(6, 14))
        self._new_hour = ctk.CTkOptionMenu(add_row, values=[f"{h:02d}" for h in range(24)], width=64)
        self._new_hour.set("08"); self._new_hour.pack(side="left", padx=(0, 3))
        ctk.CTkLabel(add_row, text=":", text_color=TXT).pack(side="left")
        self._new_min = ctk.CTkOptionMenu(add_row, values=[f"{m:02d}" for m in range(0, 60, 5)], width=64)
        self._new_min.set("00"); self._new_min.pack(side="left", padx=(3, 10))
        self._btn(add_row, "+ Thêm giờ", self._add_sched_time, "secondary", width=96).pack(side="left")
        self._btn(add_row, "Lấy giờ từ CSV", self._load_times_from_csv, "secondary",
                  width=116).pack(side="left", padx=(6, 0))
        if self.inspections and sched.get("template_times", True):
            preview = []
            for insp in self.inspections:
                if getattr(insp, "run_time", ""):
                    account = getattr(insp, "account_name", "")
                    suffix = f" ({account})" if account else ""
                    preview.append(f"{insp.run_time} - {insp.template_name}{suffix}")
            if preview:
                ctk.CTkLabel(
                    c2,
                    text="\n".join(preview[:8]) + ("\n…" if len(preview) > 8 else ""),
                    font=_font(10), text_color=MUTED, justify="left",
                ).pack(anchor="w", padx=16, pady=(0, 14))

        # Days
        c3 = self._card("Ngày trong tuần")
        dr = ctk.CTkFrame(c3, fg_color="transparent"); dr.pack(fill="x", padx=16, pady=(0, 14))
        ad = sched.get("days", ["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
        self.dvs = {}
        for lbl, k in [("T2","mon"),("T3","tue"),("T4","wed"),("T5","thu"),("T6","fri"),("T7","sat"),("CN","sun")]:
            v = ctk.BooleanVar(value=k in ad); self.dvs[k] = v
            ctk.CTkCheckBox(dr, text=lbl, variable=v, width=60, font=_font(11),
                            checkbox_width=18, checkbox_height=18).pack(side="left", padx=(0, 4))

        self._btn(self.pg, "Lưu lịch", self._save_sched, "primary", width=110, height=36).pack(anchor="w", pady=(4, 0))

    def _render_times_list(self):
        """Render the list of scheduled times with remove buttons."""
        for w in self._times_frame.winfo_children():
            w.destroy()
        if not self._sched_times:
            ctk.CTkLabel(self._times_frame, text="Chưa có giờ nào", font=ctk.CTkFont(family=F, size=10),
                         text_color=MUTED).pack(anchor="w")
            return
        for t in sorted(self._sched_times):
            row = ctk.CTkFrame(self._times_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=f"  {t}", font=ctk.CTkFont(family=F, size=11, weight="bold"),
                         text_color=TXT).pack(side="left")
            ctk.CTkButton(row, text="x", width=24, height=24, corner_radius=4,
                          fg_color="transparent", hover_color=RED, text_color=RED,
                          font=ctk.CTkFont(size=11),
                          command=lambda time_val=t: self._remove_sched_time(time_val)).pack(side="left", padx=6)

    def _add_sched_time(self):
        """Add a new time to the schedule."""
        new_time = f"{self._new_hour.get()}:{self._new_min.get()}"
        if new_time not in self._sched_times:
            self._sched_times.append(new_time)
            self._render_times_list()

    def _remove_sched_time(self, time_val: str):
        """Remove a time from the schedule."""
        if time_val in self._sched_times:
            self._sched_times.remove(time_val)
            self._render_times_list()

    def _load_times_from_csv(self):
        if not self.inspections:
            self._load()
        times = get_inspection_schedule_times(self.inspections)
        if not times:
            messagebox.showwarning("Lịch", "Không tìm thấy giờ chạy trong CSV.")
            return
        self._sched_times = times
        if hasattr(self, "template_times_var"):
            self.template_times_var.set(True)
        self._render_times_list()

    # ═══════════ PAGE: ACCOUNTS ═══════════
    def _pg_accounts(self):
        self._cls("accounts", scroll=True)

        c1 = self._card("Tài khoản mặc định", "Dùng cho các dòng CSV không ghi tên account.")
        hc, hs = has_saved_credentials(), has_sc_session()
        if hs and hc: st, sc = "Sẵn sàng tự đăng nhập", GREEN
        elif hc: st, sc = "Đã lưu thông tin đăng nhập", AMBER
        else: st, sc = "Chưa cấu hình", MUTED
        ctk.CTkLabel(c1, text=st, font=_font(11, True), text_color=sc).pack(anchor="w", padx=16, pady=(0, 6))
        row = ctk.CTkFrame(c1, fg_color="transparent"); row.pack(fill="x", padx=16, pady=(0, 14))
        self.sce = ctk.CTkEntry(row, placeholder_text="Email", width=230, height=32, corner_radius=6, border_color=BORDER)
        self.sce.pack(side="left", padx=(0, 6))
        self.scp = ctk.CTkEntry(row, placeholder_text="Mật khẩu", show="*", width=180, height=32, corner_radius=6, border_color=BORDER)
        self.scp.pack(side="left", padx=(0, 8))
        self._btn(row, "Lưu", self._save_sc, "primary", width=64).pack(side="left", padx=(0, 6))
        self._btn(row, "Xóa", self._del_sc, "danger", width=56).pack(side="left")
        if hc:
            cr = load_credentials()
            if cr: self.sce.insert(0, cr[0])

        # Named SafetyCulture account profiles. Double-click a row to edit it.
        c_profiles = self._card("Danh sách tài khoản", "Nhấp đúp vào một dòng để xem hoặc sửa thông tin.")
        table_frame = ctk.CTkFrame(c_profiles, fg_color="transparent")
        table_frame.pack(fill="x", padx=16, pady=(0, 8))
        columns = ("account", "email", "template_count", "templates", "folder")
        self.sc_profile_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=7)
        self.sc_profile_tree.heading("account", text="Tài khoản", anchor="w")
        self.sc_profile_tree.heading("email", text="Email", anchor="w")
        self.sc_profile_tree.heading("template_count", text="Số template")
        self.sc_profile_tree.heading("templates", text="Template đang chạy", anchor="w")
        self.sc_profile_tree.heading("folder", text="Thư mục template", anchor="w")
        self.sc_profile_tree.column("account", width=125, anchor="w")
        self.sc_profile_tree.column("email", width=180, anchor="w")
        self.sc_profile_tree.column("template_count", width=110, anchor="center", stretch=False)
        self.sc_profile_tree.column("templates", width=240, anchor="w")
        self.sc_profile_tree.column("folder", width=200, anchor="w")
        self.sc_profile_tree.pack(fill="x", side="left", expand=True)
        tree_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.sc_profile_tree.yview)
        tree_scroll.pack(side="right", fill="y")
        self.sc_profile_tree.configure(yscrollcommand=tree_scroll.set)
        self.sc_profile_tree.bind("<Double-1>", self._edit_sc_profile_from_table)
        self._fill_sc_profile_table()
        profile_actions = ctk.CTkFrame(c_profiles, fg_color="transparent")
        profile_actions.pack(fill="x", padx=16, pady=(0, 14))
        self._btn(profile_actions, "+ Thêm tài khoản", self._new_sc_profile, "primary",
                  width=130).pack(side="left", padx=(0, 6))
        self._btn(profile_actions, "Xóa tài khoản", self._del_sc_profile_from_table, "danger",
                  width=110).pack(side="left")

    # ═══════════ PAGE: SETTINGS ═══════════
    def _pg_settings(self):
        self._cls("settings", scroll=True)

        # License
        c2 = self._card("License")
        lic = get_license_info()
        plan = lic.get("plan","trial").title()
        valid = lic.get("valid", False)
        days = lic.get("days_remaining",0)
        lt = f"{plan} - {'Vĩnh viễn' if plan=='Lifetime' else f'còn {days} ngày'}"
        ctk.CTkLabel(c2, text=lt, font=_font(11, True),
                     text_color=GREEN if valid else RED).pack(anchor="w", padx=16, pady=(0, 6))
        lr = ctk.CTkFrame(c2, fg_color="transparent"); lr.pack(fill="x", padx=16, pady=(0, 14))
        self.lke = ctk.CTkEntry(lr, placeholder_text="License key", width=300, height=32, corner_radius=6, border_color=BORDER)
        self.lke.pack(side="left", padx=(0, 8))
        self._btn(lr, "Kích hoạt", self._act_lic, "primary", width=90).pack(side="left")

        # Template folder
        c_tpl = self._card("Thư mục template", "Để trống nếu dùng trang Templates mặc định.")
        tpl_row = ctk.CTkFrame(c_tpl, fg_color="transparent"); tpl_row.pack(fill="x", padx=16, pady=(0, 14))
        self._btn(tpl_row, "Lưu", self._save_template_url, "primary", width=64).pack(side="right")
        self.tpl_url = ctk.CTkEntry(tpl_row, placeholder_text="URL thư mục template SafetyCulture",
                                    height=32, corner_radius=6, border_color=BORDER)
        self.tpl_url.pack(side="left", fill="x", expand=True, padx=(0, 8))
        saved_tpl_url = load_autostart_config().get("template_folder_url", "")
        if saved_tpl_url:
            self.tpl_url.insert(0, saved_tpl_url)

        # Windows startup
        c_startup = self._card("Khởi động cùng Windows")
        self.win_startup_enabled = ctk.BooleanVar(value=is_registered_startup())
        ctk.CTkCheckBox(c_startup, text="Mở app sau khi đăng nhập Windows", variable=self.win_startup_enabled,
                        font=_font(11), checkbox_width=18, checkbox_height=18).pack(anchor="w", padx=16, pady=(0, 8))
        self.prelogin_task_enabled = ctk.BooleanVar(value=is_prelogin_task_registered())
        ctk.CTkCheckBox(c_startup, text="Chạy nền trước khi đăng nhập (headless)", variable=self.prelogin_task_enabled,
                        font=_font(11), checkbox_width=18, checkbox_height=18).pack(anchor="w", padx=16)
        ctk.CTkLabel(c_startup, text="Dùng Task Scheduler, cần phiên hoặc thông tin đăng nhập SafetyCulture đã lưu.",
                     font=_font(10), text_color=MUTED).pack(anchor="w", padx=44, pady=(0, 8))
        self._btn(c_startup, "Lưu", self._save_windows_startup, "primary", width=64).pack(anchor="w", padx=16, pady=(0, 14))

        # Telegram
        tg_cfg = load_telegram_config()
        c3 = self._card("Thông báo Telegram")
        ctk.CTkLabel(c3, text="Đang bật" if tg_cfg.get("enabled") else "Đang tắt", font=_font(11, True),
                     text_color=GREEN if tg_cfg.get("enabled") else MUTED).pack(anchor="w", padx=16, pady=(0, 6))
        tr1 = self._row(c3, "Bot token", width=130)
        self.tg_token = ctk.CTkEntry(tr1, width=360, height=32, corner_radius=6, border_color=BORDER, font=_font(11))
        self.tg_token.pack(side="left")
        if tg_cfg.get("bot_token"): self.tg_token.insert(0, tg_cfg["bot_token"])

        tr2 = self._row(c3, "Chat ID", width=130)
        self.tg_chat = ctk.CTkEntry(tr2, width=360, height=32, corner_radius=6, border_color=BORDER,
                                    placeholder_text="Nhiều Chat ID: cách nhau bằng dấu phẩy", font=_font(11))
        self.tg_chat.pack(side="left")
        chat_ids = tg_cfg.get("chat_ids") or ([tg_cfg.get("chat_id")] if tg_cfg.get("chat_id") else [])
        if chat_ids: self.tg_chat.insert(0, ", ".join(chat_ids))

        vons_tok = self._row(c3, "VONS bot token", width=130)
        self.tg_vons_token = ctk.CTkEntry(vons_tok, width=360, height=32, corner_radius=6, border_color=BORDER,
                                          placeholder_text="Để trống = dùng chung Bot token ở trên", font=_font(11))
        self.tg_vons_token.pack(side="left")
        if tg_cfg.get("vons_bot_token"): self.tg_vons_token.insert(0, tg_cfg["vons_bot_token"])

        vons_chat = self._row(c3, "VONS Chat ID", width=130)
        self.tg_vons_chat = ctk.CTkEntry(vons_chat, width=360, height=32, corner_radius=6, border_color=BORDER,
                                         placeholder_text="VONS 02041/02090 chỉ báo vào đây", font=_font(11))
        self.tg_vons_chat.pack(side="left")
        if tg_cfg.get("vons_chat_ids"): self.tg_vons_chat.insert(0, ", ".join(tg_cfg["vons_chat_ids"]))

        support = self._row(c3, "Chat ID hỗ trợ", width=130)
        self.tg_feedback_chat = ctk.CTkEntry(support, width=200, height=32, corner_radius=6,
                                             border_color=BORDER, font=_font(11))
        self.tg_feedback_chat.pack(side="left", padx=(0, 12))
        self.tg_feedback_chat.insert(0, tg_cfg.get("feedback_chat_id", ""))
        self.tg_support_errors = ctk.BooleanVar(value=tg_cfg.get("auto_support_errors", False))
        ctk.CTkCheckBox(support, text="Tự gửi lỗi tới ID này", variable=self.tg_support_errors,
                        font=_font(11), checkbox_width=18, checkbox_height=18).pack(side="left")

        tr3 = self._row(c3, "", width=130, pady=(8, 14))
        self.tg_enabled = ctk.BooleanVar(value=tg_cfg.get("enabled", False))
        ctk.CTkCheckBox(tr3, text="Bật thông báo", variable=self.tg_enabled, font=_font(11),
                        checkbox_width=18, checkbox_height=18).pack(side="left", padx=(0, 14))
        self._btn(tr3, "Lưu", self._save_tg, "primary", width=64).pack(side="left", padx=(0, 6))
        self._btn(tr3, "Gửi thử", self._test_tg, "secondary", width=76).pack(side="left")

    # ═══════════ PAGE: DIAGNOSTICS ═══════════
    def _pg_diag(self):
        self._cls("diag", scroll=True)
        from config import SCREENSHOT_DIR, LOG_DIR, DATA_DIR
        from runlock import get_today_completed
        from reporter import get_reports_dir
        from updater import get_current_version
        from template_lock import get_all_locks

        c = self._card("Thông tin hệ thống")
        yes_no = lambda v: "Có" if v else "Không"
        items = [("Phiên bản", get_current_version()),
                 ("Python", f"{sys.version_info.major}.{sys.version_info.minor}"),
                 ("Thư mục dữ liệu", DATA_DIR), ("Thư mục báo cáo", get_reports_dir()),
                 ("Phiên SafetyCulture", yes_no(has_sc_session())),
                 ("Thông tin đăng nhập", yes_no(has_saved_credentials())),
                 ("Telegram", "Bật" if load_telegram_config().get("enabled") else "Tắt"),
                 ("Đã chạy hôm nay", str(len(get_today_completed()))),
                 ("Template đã test", str(len(get_all_locks()))),
                 ("Lịch chạy", "Đang chạy" if (self.scheduler and self.scheduler.is_running()) else "Tắt")]
        grid = ctk.CTkFrame(c, fg_color="transparent"); grid.pack(fill="x", padx=16, pady=(0, 14))
        for i, (k, v) in enumerate(items):
            ctk.CTkLabel(grid, text=k, font=_font(11), text_color=MUTED, anchor="w").grid(
                row=i, column=0, sticky="w", padx=(0, 24), pady=1)
            ctk.CTkLabel(grid, text=v, font=_font(11), text_color=TXT, anchor="w").grid(
                row=i, column=1, sticky="w", pady=1)

        c2 = self._card("Công cụ")
        ar = ctk.CTkFrame(c2, fg_color="transparent"); ar.pack(fill="x", padx=16, pady=(0, 14))
        btns = [
            ("Xóa khóa chạy hôm nay", self._reset_lock),
            ("Xóa khóa template", self._reset_tmpl_locks),
            ("Kiểm tra cập nhật", self._check_update),
            ("Xuất cấu hình", self._export_cfg),
            ("Nhập cấu hình", self._import_cfg),
            ("Gửi báo lỗi", self._show_feedback),
        ]
        for i, (txt, cmd) in enumerate(btns):
            self._btn(ar, txt, cmd, "secondary", width=180).grid(row=i // 3, column=i % 3, sticky="w",
                                                                padx=(0, 8), pady=3)

        c3 = self._card("Mở thư mục")
        fr = ctk.CTkFrame(c3, fg_color="transparent"); fr.pack(fill="x", padx=16, pady=(0, 14))
        for lbl, path in [("Báo cáo", get_reports_dir()), ("Nhật ký", LOG_DIR), ("Ảnh chụp màn hình", SCREENSHOT_DIR)]:
            self._btn(fr, lbl, lambda p=path: os.startfile(p) if sys.platform=="win32" else None,
                      "secondary", width=130).pack(side="left", padx=(0, 8))

    def _reset_lock(self):
        reset_today()
        messagebox.showinfo("OK", "Đã xóa khóa chạy hôm nay")
        self._pg_diag()

    def _show_feedback(self):
        from updater import get_current_version

        cfg = load_telegram_config()
        chat = cfg.get("feedback_chat_id", "")
        inspections = self._schedule_full_inspections or self._full_inspections or self.inspections or []
        try:
            records = get_records(limit=6)
        except (OSError, ValueError):
            records = []
        report = build_report(
            get_current_version(), load_run_state(),
            getattr(self.engine, "current_question", ""),
            records, inspections,
        )
        dialog = ctk.CTkToplevel(self)
        dialog.title("Gửi lỗi CheckPilot")
        dialog.geometry("650x470")
        dialog.transient(self)
        text = ctk.CTkTextbox(dialog, wrap="word")
        text.pack(fill="both", expand=True, padx=14, pady=(14, 8))
        text.insert("1.0", report)
        text.configure(state="disabled")
        actions = ctk.CTkFrame(dialog, fg_color="transparent")
        actions.pack(fill="x", padx=14, pady=(0, 10))
        status = ctk.CTkLabel(
            dialog, text=f"Telegram hỗ trợ: …{chat[-4:]}" if chat else "Chưa cấu hình Chat ID hỗ trợ.",
        )
        status.pack(anchor="w", padx=14, pady=(0, 10))

        def copy_report():
            self.clipboard_clear()
            self.clipboard_append(report)
            status.configure(text="Đã sao chép báo cáo.")

        def finish(ok):
            if not dialog.winfo_exists():
                return
            status.configure(text="Đã gửi Telegram." if ok else "Không gửi được. Kiểm tra mạng hoặc sao chép báo cáo.")
            if not ok:
                send.configure(state="normal")

        def send_report():
            send.configure(state="disabled")
            status.configure(text="Đang gửi Telegram…")

            def worker():
                ok = send_feedback(report, chat)
                self._safe_after(0, lambda: finish(ok))

            threading.Thread(target=worker, daemon=True).start()

        send = ctk.CTkButton(actions, text="Gửi Telegram", command=send_report,
                             state="normal" if chat and cfg.get("bot_token") else "disabled")
        send.pack(side="left", padx=(0, 8))
        ctk.CTkButton(actions, text="Sao chép", command=copy_report).pack(side="left")

    def _reset_tmpl_locks(self):
        from template_lock import reset_all
        if messagebox.askyesno("Xác nhận", "Xóa toàn bộ khóa template?\nTất cả template sẽ phải chạy thử lại."):
            reset_all()
            messagebox.showinfo("OK", "Đã xóa khóa template")
            self._pg_diag()

    def _check_update(self):
        from update_dialog import check_and_show_update
        check_and_show_update(self, force=True, silent=False)

    def _export_cfg(self):
        from backup import export_config
        p = filedialog.asksaveasfilename(defaultextension=".json",
                                          filetypes=[("JSON", "*.json")],
                                          initialfile="checkpilot_backup.json")
        if p:
            if export_config(p):
                messagebox.showinfo("OK", f"Đã xuất cấu hình ra:\n{p}")
            else:
                messagebox.showerror("Lỗi", "Xuất file thất bại")

    def _import_cfg(self):
        from backup import import_config, get_backup_info
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not p: return
        info = get_backup_info(p)
        if not info:
            messagebox.showerror("Lỗi", "File sao lưu không hợp lệ")
            return
        if messagebox.askyesno("Nhập cấu hình",
            f"Sao lưu lúc: {info.get('exported_at','?')}\n"
            f"Phiên bản: {info.get('version','?')}\n"
            f"Số file: {len(info.get('files',[]))}\n\nNhập và ghi đè cấu hình hiện tại?"):
            ok, msg, _ = import_config(p)
            if ok:
                messagebox.showinfo("OK", msg + "\nKhởi động lại app để áp dụng.")
            else:
                messagebox.showerror("Lỗi", msg)

    def _pg_about(self):
        self._cls("about")
        w = ctk.CTkFrame(self.pg, fg_color="transparent")
        w.place(relx=0.5, rely=0.42, anchor="center")
        ctk.CTkLabel(w, text="CheckPilot", font=_font(24, True), text_color=TEAL).pack(pady=(0, 2))
        ctk.CTkLabel(w, text="Inspection Automation Assistant", font=_font(11), text_color=DIM).pack(pady=(0, 16))
        info = ctk.CTkFrame(w, corner_radius=10, fg_color=CARD, border_width=1, border_color=BORDER)
        info.pack()
        from updater import get_current_version
        rows = [("Phiên bản", get_current_version()), ("Phát triển", "Phạm Duy"), ("Liên hệ", "0868609901"),
                ("Công nghệ", "Python / Playwright"), ("Nền tảng", "Windows / macOS")]
        for i, (k, v) in enumerate(rows):
            r = ctk.CTkFrame(info, fg_color="transparent")
            r.pack(fill="x", padx=20, pady=(12 if i == 0 else 3, 12 if i == len(rows) - 1 else 3))
            ctk.CTkLabel(r, text=k, width=100, anchor="w", font=_font(11), text_color=MUTED).pack(side="left")
            ctk.CTkLabel(r, text=v, font=_font(11, True), text_color=TXT).pack(side="left")
        ctk.CTkLabel(w, text="Phần mềm có bản quyền - chỉ dùng cho một khách hàng",
                     font=_font(10), text_color=MUTED).pack(pady=(12, 0))

    # â•â•â•â•â•â•â•â•â•â•â• ACTIONS â•â•â•â•â•â•â•â•â•â•â•
    def _on_test_mode_changed(self):
        if hasattr(self, "av") and self.rv.get():
            self.av.set(False)
        self._update_auto_submit_warning()

    def _update_auto_submit_warning(self):
        if not self._live_widget("auto_warn_lbl"):
            return
        if self.rv.get() and self.av.get():
            self.av.set(False)
            return
        self._refresh_mode_buttons()
        if self.av.get() and not self.rv.get():
            self._safe_config("auto_warn_lbl", text="Tự Complete/Submit sau khi điền xong.",
                              text_color=AMBER)
        else:
            self._safe_config("auto_warn_lbl", text="Chỉ điền form, không Complete/Submit.", text_color=MUTED)

    def _set_run_stats(self, total=0, done=0, success=0, failed=0):
        remaining = max(total - done, 0)
        text = f"{done}/{total} inspection · Thành công {success} · Lỗi {failed} · Còn lại {remaining}"
        self._run_stats_text = text
        self._log(text)
        self._safe_after(0, lambda: self._safe_config("run_stat_lbl", text=text))

    def _render_inspection_list(self):
        if not self.inspections:
            self._safe_config("selected_insp_lbl", text="Tải dữ liệu để chọn mục chạy thử", text_color=MUTED)
            self._safe_config("template_picker_btn", state="disabled")
            self._safe_config("clear_template_btn", state="disabled")
            self._safe_config("btest", state="disabled")
            self._sync_run_controls()
            return

        if self.selected_inspection_index is not None and self.selected_inspection_index >= len(self.inspections):
            self.selected_inspection_index = None

        self._safe_config("template_picker_btn", state="normal")

        selected = self.selected_inspection_index
        if selected is None:
            self._safe_config(
                "selected_insp_lbl",
                text=f"Chưa chọn mục ({len(self.inspections)} inspection)",
                text_color=MUTED,
            )
        else:
            insp = self.inspections[selected]
            title = insp.template_name
            if len(title) > 40:
                title = title[:37] + "..."
            self._safe_config(
                "selected_insp_lbl",
                text=f"Đang chọn: {selected + 1}/{len(self.inspections)} - {title}",
                text_color=TEAL,
            )
        self._safe_config("clear_template_btn", state="normal" if selected is not None else "disabled")
        self._sync_run_controls()

    def _open_inspection_picker(self):
        if not self.inspections:
            self._load()
            if not self.inspections:
                messagebox.showwarning("", "Tải dữ liệu trước")
                return

        pw = ctk.CTkToplevel(self)
        pw.title("Chọn mục template CSV để test")
        pw.geometry("820x520")
        pw.resizable(True, True)
        pw.configure(fg_color=BG)
        pw.transient(self)
        pw.grab_set()
        pw.after(50, lambda: self._center_window(pw))

        hdr = ctk.CTkFrame(pw, fg_color=CARD, corner_radius=8, border_width=1, border_color=BORDER)
        hdr.pack(fill="x", padx=16, pady=(12, 8))
        ctk.CTkLabel(
            hdr,
            text="Chọn 1 inspection để chạy thử. Chờ lịch và Chạy ngay vẫn dùng toàn bộ CSV.",
            font=ctk.CTkFont(family=F, size=11, weight="bold"),
            text_color=TXT,
        ).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(
            hdr,
            text=f"Tổng: {len(self.inspections)} inspection | Chạy thử sẽ không Complete/Submit.",
            font=ctk.CTkFont(family=F, size=10),
            text_color=MUTED,
        ).pack(anchor="w", padx=12, pady=(0, 10))

        list_frame = ctk.CTkScrollableFrame(
            pw,
            fg_color=CARD,
            corner_radius=8,
            border_width=1,
            border_color=BORDER,
        )
        list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        def close_dialog():
            pw.grab_release()
            pw.destroy()

        pw.protocol("WM_DELETE_WINDOW", close_dialog)

        def select_and_refresh(idx):
            self._select_inspection(idx)
            render_rows()

        def clear_and_refresh():
            self._clear_inspection_selection()
            render_rows()

        def test_and_close(idx):
            close_dialog()
            self._test_run_index(idx)

        def render_rows():
            for child in list_frame.winfo_children():
                child.destroy()
            for idx, insp in enumerate(self.inspections):
                is_selected = idx == self.selected_inspection_index
                row = ctk.CTkFrame(
                    list_frame,
                    fg_color="#E6F4F1" if is_selected else "transparent",
                    corner_radius=5,
                    height=36,
                )
                row.pack(fill="x", padx=6, pady=3)
                row.pack_propagate(False)

                title = f"{idx + 1}. {insp.template_name}"
                if len(title) > 64:
                    title = title[:61] + "..."
                ctk.CTkLabel(
                    row,
                    text=title,
                    width=390,
                    anchor="w",
                    font=ctk.CTkFont(family=F, size=10, weight="bold" if is_selected else "normal"),
                    text_color=TEAL if is_selected else TXT,
                ).pack(side="left", padx=(10, 6))

                meta = f"{insp.site_location[:28]} | {len(insp.items)} câu"
                if getattr(insp, "account_name", ""):
                    meta += f" | {insp.account_name[:18]}"
                ctk.CTkLabel(
                    row,
                    text=meta,
                    width=210,
                    anchor="w",
                    font=ctk.CTkFont(family=F, size=9),
                    text_color=MUTED,
                ).pack(side="left", padx=(0, 6))

                select_cmd = clear_and_refresh if is_selected else (lambda i=idx: select_and_refresh(i))
                ctk.CTkButton(
                    row,
                    text="Bỏ chọn" if is_selected else "Chọn",
                    width=76,
                    height=26,
                    corner_radius=5,
                    fg_color=TEAL if is_selected else "transparent",
                    hover_color=TEAL_H if is_selected else ELEVATED,
                    border_width=0 if is_selected else 1,
                    border_color=BORDER,
                    text_color="#FFFFFF" if is_selected else DIM,
                    font=ctk.CTkFont(family=F, size=9),
                    command=select_cmd,
                ).pack(side="left", padx=(0, 6))

                ctk.CTkButton(
                    row,
                    text="Test",
                    width=58,
                    height=26,
                    corner_radius=5,
                    fg_color="transparent",
                    hover_color=ELEVATED,
                    border_width=1,
                    border_color=TEAL,
                    text_color=TEAL,
                    font=ctk.CTkFont(family=F, size=9),
                    command=lambda i=idx: test_and_close(i),
                ).pack(side="left")

        render_rows()

        btn_frame = ctk.CTkFrame(pw, fg_color="transparent")
        btn_frame.pack(pady=(2, 12))
        ctk.CTkButton(
            btn_frame,
            text="Bỏ chọn",
            width=90,
            height=32,
            corner_radius=6,
            fg_color="transparent",
            hover_color=ELEVATED,
            border_width=1,
            border_color=BORDER,
            text_color=DIM,
            font=ctk.CTkFont(family=F, size=10),
            command=clear_and_refresh,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_frame,
            text="Đóng",
            width=80,
            height=32,
            corner_radius=6,
            fg_color=TEAL,
            hover_color=TEAL_H,
            font=ctk.CTkFont(family=F, size=10, weight="bold"),
            command=close_dialog,
        ).pack(side="left")

    def _select_inspection(self, idx: int):
        if idx < 0 or idx >= len(self.inspections):
            return
        self.selected_inspection_index = idx
        insp = self.inspections[idx]
        self._log(f"Đã chọn test: {idx + 1}. {insp.template_name} | {len(insp.items)} câu")
        self._render_inspection_list()

    def _clear_inspection_selection(self):
        self.selected_inspection_index = None
        self._log("Đã bỏ chọn mục test CSV")
        self._render_inspection_list()

    def _pick_f(self):
        p = filedialog.askopenfilename(filetypes=[("Excel/CSV","*.xlsx *.xls *.csv")])
        if p:
            self.fv.set(p)
            self._validation_state = None
            self.selected_inspection_index = None
            self.inspections = []
            self._render_inspection_list()
            self._save_current_settings()
            self._sync_run_controls()
    def _pick_d(self):
        p = filedialog.askdirectory()
        if p:
            self.iv.set(p)
            self._validation_state = None
            self._save_current_settings()
            self._sync_run_controls()

    def _validate(self):
        """Detailed data validation."""
        fp = self.fv.get().strip()
        if not fp: self._safe_config("load_lbl", text="Chọn file", text_color=AMBER); return
        if not os.path.exists(fp): self._safe_config("load_lbl", text="File không tồn tại", text_color=RED); return
        img = self.iv.get().strip()
        report = validate_detailed(fp, img)
        self._log("--- Kết quả kiểm tra ---")
        s = report["stats"]
        self._log(f"  Dòng: {s.get('total_rows',0)} | Template: {s.get('templates',0)} | Site: {s.get('sites',0)}")
        if s.get("images_total"): self._log(f"  Ảnh: {s['images_total']} tổng, {s.get('images_missing',0)} thiếu")
        if report["errors"]:
            self._safe_config("load_lbl", text=f"{len(report['errors'])} lỗi", text_color=RED)
            for e in report["errors"]: self._log(f"  LỖI: {e}")
        if report["warnings"]:
            for w in report["warnings"]: self._log(f"  CẢNH BÁO: {w}")
        missing_images = report.get("stats", {}).get("images_missing", 0)
        missing_accepted = False
        if report["ok"] and missing_images:
            missing_accepted = messagebox.askyesno(
                "Cảnh báo ảnh",
                "Có ảnh không tìm thấy. Bạn có muốn tiếp tục không?"
            )
            if not missing_accepted:
                report["ok"] = False
                self._safe_config("load_lbl", text="Chưa chấp nhận ảnh thiếu", text_color=AMBER)
                self._log("  Dừng vì có ảnh không tìm thấy")
        self._validation_state = build_validation_state(
            fp, img, bool(report["ok"]), missing_images, missing_accepted
        )
        save_validation_state(self._validation_state)
        self._save_current_settings()
        if report["ok"]:
            self._safe_config("load_lbl", text="Dữ liệu hợp lệ", text_color=GREEN)
            self._log("  OK - sẵn sàng chạy")
        self._log("-----------------------")

    def _has_validated_current_file(self):
        fp = self.fv.get().strip()
        img = self.iv.get().strip()
        return is_validation_current(fp, img, self._validation_state or {})

    def _ensure_validated_before_start(self, allow_prompt=True):
        """Validate the current CSV/Excel before any run starts."""
        if self._has_validated_current_file():
            return True

        fp = self.fv.get().strip()
        if not fp:
            self._safe_config("load_lbl", text="Chọn file", text_color=AMBER)
            self._log("Kiểm tra lỗi: chưa chọn file")
            return False
        if not os.path.exists(fp):
            self._safe_config("load_lbl", text="File không tồn tại", text_color=RED)
            self._log("Kiểm tra lỗi: file không tồn tại")
            return False

        img = self.iv.get().strip()
        report = validate_detailed(fp, img)
        missing_images = report.get("stats", {}).get("images_missing", 0)
        missing_accepted = False

        if report["errors"]:
            self._safe_config("load_lbl", text=f"{len(report['errors'])} lỗi", text_color=RED)
            for e in report["errors"]:
                self._log(f"Kiểm tra lỗi: {e}")
            self._validation_state = build_validation_state(fp, img, False, missing_images, False)
            save_validation_state(self._validation_state)
            return False

        if missing_images:
            if not allow_prompt:
                self._safe_config("load_lbl", text="Có ảnh không tìm thấy", text_color=AMBER)
                self._log("Kiểm tra lỗi: Có ảnh không tìm thấy. Cần bấm Kiểm tra và xác nhận thủ công trước khi chạy lịch.")
                return False
            missing_accepted = messagebox.askyesno(
                "Cảnh báo ảnh",
                "Có ảnh không tìm thấy. Bạn có muốn tiếp tục không?"
            )
            if not missing_accepted:
                self._safe_config("load_lbl", text="Chưa chấp nhận ảnh thiếu", text_color=AMBER)
                self._log("Kiểm tra lỗi: người dùng không tiếp tục khi thiếu ảnh")
                return False

        self._validation_state = build_validation_state(fp, img, True, missing_images, missing_accepted)
        save_validation_state(self._validation_state)
        self._save_current_settings()
        return True

    def _load(self):
        fp = self.fv.get().strip()
        if not fp: self._safe_config("load_lbl", text="Chọn file", text_color=AMBER); return
        if not os.path.exists(fp): self._safe_config("load_lbl", text="Không tồn tại", text_color=RED); return
        try:
            self._data_file = fp
            img = self.iv.get().strip()
            self._image_folder = img
            self._save_current_settings()
            self.inspections = load_data(fp, img)
            if self.adv.get():
                for i in self.inspections: i.inspection_date = date.today().isoformat()
            if self.selected_inspection_index is not None and self.selected_inspection_index >= len(self.inspections):
                self.selected_inspection_index = None
            n, items = len(self.inspections), sum(len(i.items) for i in self.inspections)
            self._safe_config("load_lbl", text=f"✓ {n} inspection · {items} mục", text_color=GREEN)
            self._log(f"Đã tải {n} inspection, {items} mục")
            self._sync_template_schedule_from_data()
            self._render_inspection_list()
            self._sync_run_controls()
        except Exception as e:
            self._safe_config("load_lbl", text=str(e)[:40], text_color=RED)
            self._render_inspection_list()

    def _sync_template_schedule_from_data(self):
        cfg = load_schedule()
        if not cfg.get("template_times", True) or not self.inspections:
            return
        times = get_inspection_schedule_times(self.inspections)
        if not times:
            return
        cfg["times"] = times
        cfg["template_times"] = True
        save_schedule(cfg)
        if self.scheduler:
            self.scheduler.update_config(cfg)
        self._log(f"Template schedule: {', '.join(times)}")

    def _prepare_scheduled_subset(self, scheduled_time: str) -> bool:
        cfg = load_schedule()
        if not scheduled_time or not cfg.get("template_times", True):
            return True
        source = self._full_inspections or self.inspections
        matched = filter_inspections_for_run_time(source, scheduled_time)
        if not matched:
            self._log(f"Không có template nào đặt giờ {scheduled_time}; bỏ qua slot này.")
            return False
        self._schedule_full_inspections = list(source)
        self.inspections = matched
        names = ", ".join(
            f"{_account_label(_inspection_account(i))}/{i.template_name} ({i.site_location})"
            for i in matched
        )
        msg = f"Lịch {scheduled_time} | CSV: {self._data_file} | {len(matched)} template: {names}"
        logger.info(msg)
        self._log(msg)
        self._render_inspection_list()
        return True

    def _restore_scheduled_subset(self):
        if self._schedule_full_inspections:
            self.inspections = self._schedule_full_inspections
            self._schedule_full_inspections = None
            self._active_schedule_time = ""
            self._render_inspection_list()

    def _test_run(self):
        """Run selected inspection as a test - show preview first."""
        if not self.inspections:
            self._load()
            if not self.inspections:
                messagebox.showwarning("", "Tải dữ liệu trước")
                return
        idx = self.selected_inspection_index
        if idx is None or idx >= len(self.inspections):
            messagebox.showwarning("", "Chọn mục template CSV để chạy test")
            self._open_inspection_picker()
            return
        self._test_run_index(idx)

    def _test_run_index(self, idx: int):
        if not self.inspections:
            self._load()
            if not self.inspections:
                messagebox.showwarning("", "Tải dữ liệu trước")
                return
        if self.worker_thread and self.worker_thread.is_alive():
            self._log("Đang chạy rồi!")
            return
        if idx < 0 or idx >= len(self.inspections):
            messagebox.showwarning("", "Mục test không hợp lệ")
            return
        self.selected_inspection_index = idx
        self._render_inspection_list()
        self._show_preview(
            self.inspections[idx],
            on_confirm=lambda i=idx: self._execute_test_run(i),
        )

    def _execute_test_run(self, idx=None):
        """Actually run the test after preview confirmation."""
        if not self.inspections:
            messagebox.showwarning("", "Tải dữ liệu trước")
            return
        if idx is None:
            idx = self.selected_inspection_index
        if idx is None:
            messagebox.showwarning("", "Chọn mục template CSV để chạy test")
            return
        if idx < 0 or idx >= len(self.inspections):
            messagebox.showwarning("", "Mục test không hợp lệ")
            return
        insp = self.inspections[idx]
        self._log(f"\nTEST RUN ({idx + 1}/{len(self.inspections)}) - {insp.template_name}")
        self._full_inspections = list(self.inspections)
        self.inspections = [self._full_inspections[idx]]
        self.rv.set(True)  # Force test mode
        self.av.set(False)
        self.sv.set(False)
        self._start()

    def _show_preview(self, inspection, on_confirm=None):
        """Show a preview table of inspection data before running."""
        from data_loader import InspectionData
        pw = ctk.CTkToplevel(self)
        pw.title("Xem trước dữ liệu")
        pw.geometry("750x520")
        pw.resizable(True, True)
        pw.configure(fg_color=BG)
        pw.transient(self)
        pw.grab_set()
        pw.after(50, lambda: self._center_window(pw))

        # Header info
        hdr = ctk.CTkFrame(pw, fg_color=CARD, corner_radius=8, border_width=1, border_color=BORDER)
        hdr.pack(fill="x", padx=16, pady=(12, 6))
        ctk.CTkLabel(hdr, text="Thông tin Inspection", font=ctk.CTkFont(family=F, size=12, weight="bold"),
                     text_color=TXT).pack(anchor="w", padx=12, pady=(8, 4))
        info_items = [
            ("Template:", inspection.template_name),
            ("Site:", inspection.site_location),
            ("Ngày:", inspection.inspection_date or "(hôm nay)"),
            ("Số câu hỏi:", str(len(inspection.items))),
        ]
        for label, value in info_items:
            row = ctk.CTkFrame(hdr, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=1)
            ctk.CTkLabel(row, text=label, width=90, anchor="w",
                         font=ctk.CTkFont(family=F, size=10), text_color=MUTED).pack(side="left")
            ctk.CTkLabel(row, text=value, font=ctk.CTkFont(family=F, size=10, weight="bold"),
                         text_color=TXT).pack(side="left")
        ctk.CTkFrame(hdr, height=6, fg_color="transparent").pack()

        # Table header
        tbl_hdr = ctk.CTkFrame(pw, fg_color=ELEVATED, corner_radius=0)
        tbl_hdr.pack(fill="x", padx=16, pady=(6, 0))
        cols = [("STT", 40), ("Section", 120), ("Câu hỏi", 250), ("Đáp án", 80), ("Ghi chú", 100), ("Ảnh", 40)]
        for col_name, col_w in cols:
            ctk.CTkLabel(tbl_hdr, text=col_name, width=col_w, anchor="w",
                         font=ctk.CTkFont(family=F, size=9, weight="bold"),
                         text_color=DIM).pack(side="left", padx=4, pady=4)

        # Scrollable table body
        scroll = ctk.CTkScrollableFrame(pw, fg_color=CARD, corner_radius=8,
                                         border_width=1, border_color=BORDER)
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 6))

        for idx, item in enumerate(inspection.items):
            row_bg = "transparent" if idx % 2 == 0 else ELEVATED
            row = ctk.CTkFrame(scroll, fg_color=row_bg, height=26)
            row.pack(fill="x", pady=0)
            row.pack_propagate(False)

            # STT
            ctk.CTkLabel(row, text=str(idx + 1), width=40, anchor="w",
                         font=ctk.CTkFont(family=F, size=9), text_color=DIM).pack(side="left", padx=4)
            # Section
            ctk.CTkLabel(row, text=item.section[:18], width=120, anchor="w",
                         font=ctk.CTkFont(family=F, size=9), text_color=MUTED).pack(side="left", padx=4)
            # Question
            ctk.CTkLabel(row, text=item.question[:38], width=250, anchor="w",
                         font=ctk.CTkFont(family=F, size=9), text_color=TXT).pack(side="left", padx=4)
            # Answer
            ans_color = GREEN if item.answer.lower() in ("yes", "safe", "pass", "compliant", "good") else (
                RED if item.answer.lower() in ("no", "unsafe", "fail", "non-compliant", "at risk") else DIM)
            ctk.CTkLabel(row, text=item.answer, width=80, anchor="w",
                         font=ctk.CTkFont(family=F, size=9, weight="bold"),
                         text_color=ans_color).pack(side="left", padx=4)
            # Notes
            ctk.CTkLabel(row, text=(item.notes[:14] + "..." if len(item.notes) > 14 else item.notes),
                         width=100, anchor="w",
                         font=ctk.CTkFont(family=F, size=9), text_color=MUTED).pack(side="left", padx=4)
            # Images
            img_count = len(item.image_paths)
            img_txt = str(img_count) if img_count > 0 else ""
            ctk.CTkLabel(row, text=img_txt, width=40, anchor="w",
                         font=ctk.CTkFont(family=F, size=9),
                         text_color=TEAL if img_count else MUTED).pack(side="left", padx=4)

        # Buttons
        btn_frame = ctk.CTkFrame(pw, fg_color="transparent")
        btn_frame.pack(pady=(6, 12))

        def _confirm():
            pw.grab_release()
            pw.destroy()
            if on_confirm:
                on_confirm()

        ctk.CTkButton(btn_frame, text="Chạy thử", width=120, height=34, corner_radius=7,
                      fg_color=TEAL, hover_color=TEAL_H,
                      font=ctk.CTkFont(family=F, size=11, weight="bold"),
                      command=_confirm).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_frame, text="Đóng", width=80, height=34, corner_radius=7,
                      fg_color="transparent", hover_color=ELEVATED, border_width=1, border_color=BORDER,
                      text_color=DIM, font=ctk.CTkFont(family=F, size=11),
                      command=lambda: (pw.grab_release(), pw.destroy())).pack(side="left")

    def _center_window(self, window):
        """Center a toplevel window on the parent."""
        window.update_idletasks()
        pw = self.winfo_x() + self.winfo_width() // 2
        ph = self.winfo_y() + self.winfo_height() // 2
        w, h = window.winfo_width(), window.winfo_height()
        window.geometry(f"+{pw - w // 2}+{ph - h // 2}")

    def _run_now(self):
        """Run immediately. Auto submit still requires tested/current templates."""
        if getattr(self, "_full_inspections", None):
            self.inspections = self._full_inspections
            self._full_inspections = None
            self._render_inspection_list()
        if not self.inspections:
            if self.fv.get().strip():
                self._load()
            if not self.inspections:
                self._log("Chưa có dữ liệu. Bấm Tải dữ liệu trước.")
                return
        if self.worker_thread and self.worker_thread.is_alive():
            self._log("Đang chạy rồi!")
            return
        if not self._ensure_validated_before_start(allow_prompt=True):
            return
        self._log("\n=== CHẠY NGAY ===")
        self._scheduled_run = False
        self._waiting_for_schedule = False
        self._run_active = True
        self._set_run_status("Đang chạy", TEAL, 0)
        self._sync_run_controls()
        self._run_errors = []
        self.worker_thread = threading.Thread(target=self._run, daemon=True)
        self.worker_thread.start()

    def _start_scheduled(self):
        """Activate scheduler mode — wait for scheduled time then auto-run."""
        if self.worker_thread and self.worker_thread.is_alive():
            self._log("Bỏ qua Chờ lịch: đang chạy")
            return
        if getattr(self, "_full_inspections", None):
            self.inspections = self._full_inspections
            self._full_inspections = None
            self._render_inspection_list()
        if not self.inspections:
            if self.fv.get().strip():
                self._load()
            if not self.inspections:
                self._log("Chưa có dữ liệu. Bấm Tải dữ liệu trước.")
                return
        if not self._ensure_validated_before_start(allow_prompt=True):
            return

        cfg = load_schedule()
        if cfg.get("template_times", True):
            self._sync_template_schedule_from_data()
            cfg = load_schedule()
        if not cfg.get("enabled"):
            self._log("Chưa bật lịch chạy. Vào trang Lịch chạy, bật lịch và lưu giờ chạy trước.")
            messagebox.showwarning("Lịch chạy", "Chưa bật lịch chạy. Vào trang Lịch chạy, bật lịch và lưu giờ chạy trước.")
            return

        # Chờ lịch is always real Auto Mode for the full loaded CSV.
        self.rv.set(False)
        self.av.set(True)
        self.sv.set(False)
        self.adv.set(True)
        self._save_current_settings()

        due, scheduled_time, reason = is_schedule_due_now(cfg)
        if due:
            if reason == "missed":
                self._log(f"Đã trễ lịch {scheduled_time}; chạy bù Auto Mode full CSV.")
            else:
                self._log(f"Đúng giờ lịch {scheduled_time}. Bắt đầu Auto Mode full CSV.")
            if not self._prepare_scheduled_subset(scheduled_time):
                mark_schedule_run(cfg, scheduled_time)
                if self.scheduler:
                    self.scheduler.update_config(cfg)
                self._set_waiting_for_next_schedule("Chờ lịch")
                return
            self._active_schedule_time = scheduled_time
            self._start(scheduled=True, schedule_slot_to_mark=scheduled_time)
            return

        self._ensure_scheduler_running(cfg)
        self._log("Đã bật chế độ chờ lịch. Không chạy ngay.")
        if reason == "already ran" and scheduled_time:
            self._log(f"Lịch {scheduled_time} hôm nay đã chạy.")
        target = get_next_run_datetime(cfg)
        if target:
            wait_text = target.strftime("%d/%m/%Y %H:%M")
            self._log(f"Sẽ tự chạy full CSV vào: {wait_text}")
            self._waiting_for_schedule = True
            self._set_run_status(f"Chờ lịch {target.strftime('%H:%M')}", AMBER)
        else:
            self._log("Không tìm được giờ chạy tiếp theo. Kiểm tra lại trang Lịch chạy.")
            self._waiting_for_schedule = True
            self._set_run_status("Chờ lịch", AMBER)
        self._set_run_stats(len(self.inspections), 0, 0, 0)
        self._sync_run_controls()

    def _start(self, scheduled=False, schedule_slot_to_mark=""):
        self._force_scheduled_start = False
        self._schedule_slot_to_mark = schedule_slot_to_mark or ""
        if not self.inspections:
            if self.fv.get().strip():
                self._load()
            if not self.inspections:
                self._log("Không chạy: chưa có dữ liệu")
                return
        if self.worker_thread and self.worker_thread.is_alive():
            self._log("Bỏ qua: đang chạy")
            return
        auto_submit = bool(self.av.get()) and not bool(self.rv.get()) if hasattr(self, "av") and hasattr(self, "rv") else False
        if not scheduled and auto_submit and self._should_wait_for_schedule():
            return
        effective_scheduled = scheduled or bool(getattr(self, "_force_scheduled_start", False))
        if not self._ensure_validated_before_start(allow_prompt=not effective_scheduled):
            return
        if self._schedule_slot_to_mark:
            cfg = load_schedule()
            mark_schedule_run(cfg, self._schedule_slot_to_mark)
            if self.scheduler:
                self.scheduler.update_config(cfg)
        self._scheduled_run = effective_scheduled
        self._waiting_for_schedule = False
        self._run_active = True
        self._set_run_status("Đang chạy", TEAL, 0)
        self._sync_run_controls()
        self._run_errors = []
        self.worker_thread = threading.Thread(target=self._run, daemon=True)
        self.worker_thread.start()

    def _should_wait_for_schedule(self) -> bool:
        """Manual Auto Mode respects the enabled scheduler instead of running early."""
        cfg = load_schedule()
        if not cfg.get("enabled"):
            return False
        if cfg.get("template_times", True):
            self._sync_template_schedule_from_data()
            cfg = load_schedule()

        due, scheduled_time, reason = is_schedule_due_now(cfg)
        if due:
            if reason == "missed":
                self._log(f"Đã trễ lịch {scheduled_time}; chạy bù Auto Mode.")
            else:
                self._log(f"Đúng giờ lịch {scheduled_time}. Bắt đầu Auto Mode.")
            self._force_scheduled_start = True
            self._schedule_slot_to_mark = scheduled_time
            self._active_schedule_time = scheduled_time
            if not self._prepare_scheduled_subset(scheduled_time):
                mark_schedule_run(cfg, scheduled_time)
                if self.scheduler:
                    self.scheduler.update_config(cfg)
                self._set_waiting_for_next_schedule()
                return True
            return False

        if reason == "already ran":
            self._log(f"Lịch {scheduled_time} hôm nay đã chạy. Chuyển sang chờ lịch tiếp theo.")
        else:
            self._log("Chưa tới giờ lịch. Không chạy ngay, chuyển sang chế độ chờ.")

        self._ensure_scheduler_running(cfg)
        target = get_next_run_datetime(cfg)
        if target:
            wait_text = target.strftime("%d/%m/%Y %H:%M")
            self._log(f"Sẽ tự chạy vào: {wait_text}")
            self._waiting_for_schedule = True
            self._set_run_status(f"Chờ lịch {target.strftime('%H:%M')}", AMBER)
        else:
            self._log("Không tìm được giờ chạy tiếp theo. Kiểm tra lại Lịch chạy.")
            self._waiting_for_schedule = True
            self._set_run_status("Chờ lịch", AMBER)
        self._save_current_settings()
        self._sync_run_controls()
        return True

    def _ensure_scheduler_running(self, cfg=None):
        cfg = cfg or load_schedule()
        if not self.scheduler:
            self.scheduler = Scheduler(run_callback=self._sched_run, log_callback=self._log)
        self.scheduler.update_config(cfg)
        if cfg.get("enabled") and not self.scheduler.is_running():
            self.scheduler.start()

    def _set_waiting_for_next_schedule(self, context: str = "") -> bool:
        cfg = load_schedule()
        if not cfg.get("enabled"):
            return False
        if cfg.get("template_times", True) and self.inspections:
            self._sync_template_schedule_from_data()
            cfg = load_schedule()
        self._ensure_scheduler_running(cfg)
        target = get_next_run_datetime(cfg)
        self._waiting_for_schedule = True
        if target:
            self._set_run_status(f"Chờ lịch {target.strftime('%H:%M')}", AMBER)
            prefix = f"{context} " if context else ""
            self._log(f"{prefix}Tiếp tục chờ lịch kế tiếp: {target.strftime('%d/%m/%Y %H:%M')}")
        else:
            self._set_run_status("Chờ lịch", AMBER)
            prefix = f"{context} " if context else ""
            self._log(f"{prefix}Đang chờ lịch, nhưng chưa tìm được giờ chạy kế tiếp.")
        self._sync_run_controls()
        return True

    def _auto_enter_schedule_mode(self, reason: str = "Startup"):
        """Enter always-on schedule mode without requiring a button click."""
        if self._is_worker_running():
            return
        cfg = load_schedule()
        if not cfg.get("enabled"):
            return
        if not self.inspections and self.fv.get().strip():
            self._load()
        if not self.inspections:
            self._log(f"{reason}: chưa có dữ liệu để chờ lịch.")
            self._set_waiting_for_next_schedule(reason)
            return
        if not self._ensure_validated_before_start(allow_prompt=False):
            self._log(f"{reason}: dữ liệu chưa validate OK, chưa tự chạy lịch.")
            self._set_waiting_for_next_schedule(reason)
            return

        self.rv.set(False)
        self.av.set(True)
        self.sv.set(False)
        self.adv.set(True)
        self._save_current_settings()

        if cfg.get("template_times", True):
            self._sync_template_schedule_from_data()
            cfg = load_schedule()
        due, scheduled_time, due_reason = is_schedule_due_now(cfg)
        if due:
            if due_reason == "missed":
                self._log(f"{reason}: chạy bù lịch {scheduled_time}.")
            else:
                self._log(f"{reason}: đúng giờ lịch {scheduled_time}, bắt đầu Auto Mode.")
            if not self._prepare_scheduled_subset(scheduled_time):
                mark_schedule_run(cfg, scheduled_time)
                if self.scheduler:
                    self.scheduler.update_config(cfg)
                self._set_waiting_for_next_schedule(reason)
                return
            self._active_schedule_time = scheduled_time
            self._start(scheduled=True, schedule_slot_to_mark=scheduled_time)
            return

        self._set_waiting_for_next_schedule(reason)

    def _pause(self):
        if not self.engine: return
        if self.engine._paused:
            self.engine.resume()
            self._safe_config("bpause", text="Tạm dừng")
            self._set_run_status("Đang chạy", TEAL)
        else:
            self.engine.pause()
            self._safe_config("bpause", text="Tiếp tục")
            self._set_run_status("Tạm dừng", AMBER)

    def _stop(self):
        if self.engine: self.engine.stop()
        self._set_run_status("Đang dừng…", RED)

    def _run(self):
        self.engine = None
        current_account = None
        total = 0
        skipped_count = 0
        run_success = 0
        run_failed = 0
        consecutive_failures = 0
        auto_submit = self.av.get() and not self.rv.get()
        if auto_submit:
            start_run_state(
                data_file=self._data_file or self.fv.get().strip(),
                image_folder=self._image_folder or self.iv.get().strip(),
                total=len(self.inspections),
                auto_submit=True,
                scheduled=self._scheduled_run,
            )
        try:
            # Template locks are setup warnings only. Production Auto Mode must
            # not stop just because the CSV fingerprint changed after an app or
            # customer data update; validation and per-item submit guards still
            # block unsafe runs.
            if auto_submit:
                invalid_templates = get_invalid_templates(self.inspections)
                if invalid_templates:
                    self._log(f"WARN: {len(invalid_templates)} template(s) chưa test hoặc CSV đã đổi:")
                    for t in invalid_templates:
                        self._log(f"  - {t}")
                    self._log("Auto Mode vẫn tiếp tục sau khi Kiểm tra OK; sẽ không submit nếu có lỗi item/upload.")

            if auto_submit:
                remaining = get_remaining(self.inspections)
                skipped_count = len(self.inspections) - len(remaining)
                if skipped_count > 0:
                    self._log(f"Skipping {skipped_count} already completed today")
                run_list = _group_by_account(remaining)
            else:
                run_list = self.inspections

            total = len(run_list)
            if total == 0:
                self._log("All inspections already completed today")
                return
            if self._scheduled_run:
                before_login_filter = len(run_list)
                run_list, missing_accounts = _filter_login_ready(run_list)
                if missing_accounts:
                    msg = (
                        "Scheduled run skipped account without SafetyCulture session/credentials: "
                        + ", ".join(missing_accounts)
                    )
                    self._log(msg)
                    logger.warning(msg)
                    send_error_alert(msg)
                    skipped_count += before_login_filter - len(run_list)
                    total = len(run_list)
                    if total == 0:
                        return
            account_blocks = []
            for insp in run_list:
                label = _account_label(_inspection_account(insp))
                if label not in account_blocks:
                    account_blocks.append(label)
            if auto_submit and len(account_blocks) > 1:
                self._log("Account blocks for this run: " + " -> ".join(account_blocks))

            run_success = 0
            run_failed = 0
            self._set_run_stats(total, 0, 0, 0)

            for idx, insp in enumerate(run_list):
                if self.engine and self.engine._stopped:
                    break
                account = _inspection_account(insp)
                if self.engine is None or account != current_account:
                    if self.engine is not None:
                        try:
                            self.engine.close_browser()
                        except Exception:
                            pass
                    current_account = account
                    self._log(f"Switching SafetyCulture account: {_account_label(account)}")
                    self.engine = AutomationEngine(
                        log_callback=self._log,
                        account_name=account,
                        allow_manual_login=not self._scheduled_run,
                    )
                    self.engine.start_browser()
                    self.engine.wait_for_login()

                    self._log("Running health check...")
                    hc_ok, hc_msg = self.engine.health_check()
                    if not hc_ok:
                        self._log(f"Health check FAILED: {hc_msg}")
                        screenshot = None
                        try:
                            screenshot = self.engine._screenshot_error("health_check_failed")
                        except Exception:
                            screenshot = None
                        send_error_alert(f"Health check failed: {hc_msg}", screenshot, account=account)
                        return
                    self._log("Health check OK")
                if self.adv.get(): insp.inspection_date = date.today().isoformat()
                self._log(
                    f"\n[{idx+1}/{total}] {insp.template_name} | {insp.site_location}"
                    + (f" | account={account}" if account else "")
                )
                if auto_submit:
                    send_inspection_status(
                        "RUNNING", insp.template_name, insp.site_location,
                        account=account, scheduled_time=self._active_schedule_time,
                    )
                if auto_submit:
                    update_run_state(
                        status="running",
                        current_index=idx + 1,
                        current_template=insp.template_name,
                        current_site=insp.site_location,
                        current_account=account,
                        scheduled_time=self._active_schedule_time,
                        total=total,
                        done=idx,
                        success=run_success,
                        failed=run_failed,
                    )
                run_started = datetime.now()

                if auto_submit:
                    self._log("  Mode: AUTO - submit if no errors")
                else:
                    self._log("  Mode: TEST - fill only, no submit")

                ok = self.engine.run_inspection(insp, auto_submit=auto_submit)
                errs = []
                if ok:
                    consecutive_failures = 0
                    if auto_submit:
                        verified = self.engine.verify_inspection_saved(insp.template_name, insp)
                        if not verified:
                            self._log("  Warning: submitted but not verified in list yet")
                        success_ss = self.engine.capture_success_screenshot(insp.template_name)
                        send_success_report(
                            insp.template_name,
                            insp.site_location,
                            len(insp.items),
                            len(self.engine.item_errors),
                            screenshot_path=success_ss,
                            verified=verified,
                            scheduled_time=self._active_schedule_time if self._scheduled_run else "",
                            url=self.engine.page.url if self.engine and self.engine.page else "",
                            account=account,
                        )
                        mark_completed(
                            insp.template_name,
                            insp.site_location,
                            getattr(insp, "account_name", ""),
                        )
                    else:
                        # Test mode success marks the template as tested.
                        mark_template_tested(
                            insp.template_name,
                            len(insp.items),
                            fingerprint_inspection(insp),
                        )
                        self._log(f"  Template '{insp.template_name}' marked as tested")
                    run_success += 1
                else:
                    errs = self.engine.item_errors or [f"Failed: {insp.template_name}"]
                    self._run_errors.extend(errs)
                    run_failed += 1
                    if auto_submit:
                        consecutive_failures += 1
                        send_inspection_status(
                            "BLOCKED", insp.template_name, insp.site_location,
                            account=account,
                            scheduled_time=self._active_schedule_time,
                            details="; ".join(errs[:3]),
                        )

                add_record(insp.template_name, insp.site_location, insp.inspection_date,
                           len(insp.items), ok, errs, self._data_file)

                # Generate report
                mode = "auto" if auto_submit else "test"
                img_total = sum(len(it.image_paths) for it in insp.items)
                items_ok = getattr(self.engine, "_items_ok", max(0, len(insp.items) - len(self.engine.item_errors)))
                img_failed = getattr(self.engine, "_images_failed", 0)
                img_uploaded = getattr(self.engine, "_images_uploaded", max(0, img_total - img_failed))
                duration_sec = (datetime.now() - run_started).total_seconds()
                rpt = generate_report(
                    template=insp.template_name, site=insp.site_location,
                    inspection_date=insp.inspection_date, total_items=len(insp.items),
                    items_ok=items_ok, items_failed=len(self.engine.item_errors),
                    errors=self.engine.item_errors, images_uploaded=img_uploaded,
                    images_failed=img_failed, submitted=ok and auto_submit,
                    mode=mode, duration_sec=duration_sec, data_file=self._data_file,
                )
                self._log(f"  Report: {os.path.basename(rpt)}")

                self._set_run_stats(total, idx + 1, run_success, run_failed)
                if auto_submit:
                    update_run_state(
                        status="running",
                        current_index=idx + 1,
                        current_template=insp.template_name,
                        total=total,
                        done=idx + 1,
                        success=run_success,
                        failed=run_failed,
                    )
                p = (idx+1)/total
                self._set_run_status(f"{idx+1}/{total}", GREEN, p)

                if auto_submit and consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    msg = (
                        f"Auto Mode stopped after {consecutive_failures} consecutive failures. "
                        "No more inspections will run until this is checked."
                    )
                    self._log(msg)
                    screenshot = None
                    try:
                        screenshot = self.engine._screenshot_error("consecutive_failures")
                    except Exception:
                        screenshot = None
                    send_error_alert(
                        msg, screenshot, insp.template_name, insp.site_location,
                        question=getattr(self.engine, "current_question", ""),
                        url=self.engine.page.url if self.engine and self.engine.page else "",
                        details=self._run_errors[-8:],
                        account=account,
                        scheduled_time=self._active_schedule_time,
                    )
                    update_run_state(status="blocked")
                    break

                if self.sv.get() and idx < total-1 and not self.engine._stopped:
                    self._log("  Waiting"); self.engine.pause()
                    self._safe_after(0, lambda: self._safe_config("bpause", text="Tiếp tục"))
                    self._set_run_status("Đang chờ - bấm Tiếp tục", AMBER)
                    while self.engine._paused and not self.engine._stopped:
                        import time; time.sleep(0.5)
        except Exception as e:
            self._log(f"Fatal: {e}")
            self._run_errors.append(str(e))
            screenshot = None
            try:
                if self.engine:
                    screenshot = self.engine._screenshot_error("gui_fatal")
            except Exception:
                screenshot = None
            send_error_alert(str(e), screenshot)
        finally:
            # Send daily summary
            try:
                send_daily_summary(
                    total=total, success=run_success,
                    failed=run_failed, skipped=skipped_count,
                )
            except: pass
            if self.engine:
                self.engine.close_browser()
            clear_run_state()
            self._safe_after(0, self._done)

    def _sched_run(self, scheduled_time=None):
        self._safe_after(0, lambda: self._start_scheduled_run(scheduled_time))

    def _start_scheduled_run(self, scheduled_time=None):
        if self.worker_thread and self.worker_thread.is_alive():
            self._log(f"Scheduled {scheduled_time or ''}: automation đang chạy, giữ slot để chạy bù sau.")
            return
        if getattr(self, "_full_inspections", None):
            self.inspections = self._full_inspections
            self._full_inspections = None
            self._render_inspection_list()
        if not self.inspections and self.fv.get().strip():
            self._log("Lịch: đang tải file dữ liệu đã lưu")
            self._load()
        if not self.inspections:
            self._log("Lịch: chưa có dữ liệu")
            return
        if scheduled_time and not self._prepare_scheduled_subset(scheduled_time):
            cfg = load_schedule()
            mark_schedule_run(cfg, scheduled_time)
            if self.scheduler:
                self.scheduler.update_config(cfg)
            self._set_waiting_for_next_schedule("Scheduled")
            return
        self._active_schedule_time = scheduled_time or ""
        self.adv.set(True); self.rv.set(False); self.av.set(True); self.sv.set(False)
        self._save_current_settings()
        self._start(scheduled=True, schedule_slot_to_mark=scheduled_time or "")

    def _done(self):
        was_scheduled = self._scheduled_run
        had_errors = bool(self._run_errors)
        self._scheduled_run = False
        self._run_active = False
        self._restore_scheduled_subset()
        # Restore full inspection list if was test/retry run
        if hasattr(self, '_full_inspections') and self._full_inspections:
            self.inspections = self._full_inspections
            self._full_inspections = None
            self._render_inspection_list()
        if was_scheduled and load_schedule().get("enabled"):
            if had_errors:
                self._log(f"Scheduled run kết thúc với {len(self._run_errors)} lỗi; vẫn tiếp tục chờ lịch kế tiếp.")
            else:
                self._log("Scheduled run hoàn tất; tự chuyển sang chờ lịch kế tiếp.")
            self._set_waiting_for_next_schedule()
            return
        if had_errors:
            self._run_state_text = f"Lỗi: {len(self._run_errors)}"
            self._run_state_color = RED
        else:
            self._run_state_text = "Hoàn tất"
            self._run_state_color = GREEN
        self._sync_run_controls()

    def _retry_failed(self):
        """Retry only inspections that failed in the last run."""
        if not self.inspections:
            messagebox.showwarning("", "Tải dữ liệu trước")
            return
        # Get today's completed to find what failed
        from runlock import get_today_completed
        completed = get_today_completed()
        failed = [i for i in self.inspections
                  if inspection_run_key(i) not in completed]
        if not failed:
            messagebox.showinfo("OK", "Không có inspection lỗi cần chạy lại")
            return
        self._log(f"\nRETRY: {len(failed)} failed inspection(s)")
        orig = self.inspections
        self._full_inspections = list(self.inspections)
        self.inspections = failed
        self._start()

    def _save_sched(self):
        template_times = self.template_times_var.get() if hasattr(self, "template_times_var") else True
        times = sorted(self._sched_times) if hasattr(self, '_sched_times') else ["05:00"]
        if template_times:
            if not self.inspections and self.fv.get().strip():
                self._load()
            derived = get_inspection_schedule_times(self.inspections)
            if derived:
                times = derived
        if not times:
            messagebox.showwarning("", "Thêm ít nhất 1 giờ chạy")
            return
        cfg = {
            "enabled": self.se.get(),
            "times": times,
            "days": [k for k, v in self.dvs.items() if v.get()],
            "auto_date_today": True,
            "template_times": template_times,
            "runs_today": load_schedule().get("runs_today", []),
        }
        save_schedule(cfg)
        if cfg["enabled"]:
            if not self.scheduler:
                self.scheduler = Scheduler(run_callback=self._sched_run, log_callback=self._log)
            self.scheduler.update_config(cfg)
            self.scheduler.start()
            times_str = ", ".join(times)
            mode = "theo template CSV" if template_times else "full CSV"
            messagebox.showinfo("OK", f"Lịch {mode}: [{times_str}] hằng ngày")
        else:
            if self.scheduler:
                self.scheduler.stop()
            messagebox.showinfo("OK", "Đã tắt lịch chạy")
        self._pg_sched()

    def _save_current_settings(self):
        save_last_config(
            data_file=self.fv.get().strip() if hasattr(self, "fv") else "",
            image_folder=self.iv.get().strip() if hasattr(self, "iv") else "",
        )

    def _auto_load_last_config(self):
        """Auto-load last used data file and image folder on startup."""
        last_file = get_last_data_file()
        last_img = get_last_image_folder()
        if last_file and os.path.exists(last_file):
            self.fv.set(last_file)
            self._log(f"Auto-loaded file: {os.path.basename(last_file)}")
        if last_img and os.path.exists(last_img):
            self.iv.set(last_img)
        # Auto-load data if file exists
        if last_file and os.path.exists(last_file):
            self._load()
            self._log("Data auto-loaded from last session")
            self._safe_after(1500, self._resume_interrupted_auto_run)
            self._safe_after(2500, lambda: self._auto_enter_schedule_mode("Startup"))

    def _resume_interrupted_auto_run(self):
        state = load_run_state()
        data_file = self.fv.get().strip()
        if not is_interrupted_auto_run(state, data_file):
            if state and state.get("date") != date.today().isoformat():
                clear_run_state()
            return
        if self._is_worker_running():
            return
        if not self.inspections:
            self._load()
        if not self.inspections:
            return
        self._log(
            "Phát hiện Auto run bị gián đoạn. "
            "Tự chạy tiếp các inspection còn lại, không chạy trùng mục đã submit."
        )
        if state.get("current_template"):
            self._log(f"  Lần trước dừng ở: {state.get('current_template')}")
        self.rv.set(False)
        self.av.set(True)
        self.sv.set(False)
        self.adv.set(True)
        self._save_current_settings()
        self._start(scheduled=True)

    def _export_history(self):
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")])
        if p:
            if export_csv(p): messagebox.showinfo("OK", f"Đã xuất: {p}")
            else: messagebox.showerror("Lỗi", "Xuất file thất bại")

    def _clear_history(self):
        if messagebox.askyesno("Xác nhận", "Xóa toàn bộ lịch sử chạy?"):
            from history import HISTORY_FILE
            import os
            if os.path.exists(HISTORY_FILE):
                os.remove(HISTORY_FILE)
            messagebox.showinfo("OK", "Đã xóa lịch sử")
            self._pg_history()

    def _save_sc(self):
        e, p = self.sce.get().strip(), self.scp.get().strip()
        if not e or not p: messagebox.showwarning("","Nhập email + password"); return
        if save_credentials(e, p):
            messagebox.showinfo("OK", "Đã lưu"); self.scp.delete(0,"end")

    def _del_sc(self):
        if messagebox.askyesno("Xác nhận", "Xóa thông tin đăng nhập mặc định?"): clear_sc_login(); self._pg_accounts()

    def _fill_sc_profile_table(self):
        tree = getattr(self, "sc_profile_tree", None)
        if not tree:
            return
        for item in tree.get_children():
            tree.delete(item)
        template_summary = self._sc_profile_template_summary()
        for name, profile in list_account_profiles().items():
            templates = template_summary.get(name, [])
            template_text = ", ".join(templates)
            if len(template_text) > 70:
                template_text = template_text[:67] + "..."
            tree.insert("", "end", iid=name, values=(
                name,
                profile.get("email", ""),
                len(templates),
                template_text or "Chưa có trong CSV đang chọn",
                profile.get("template_folder_url", ""),
            ))

    def _sc_profile_template_summary(self):
        """Read-only mapping of saved accounts to distinct templates in the selected CSV."""
        summary = {}
        inspections = getattr(self, "inspections", None) or []
        file_path = self.fv.get().strip() if hasattr(self, "fv") else ""
        if file_path and os.path.exists(file_path):
            try:
                inspections = load_data(file_path)
            except Exception:
                pass
        for inspection in inspections:
            account = str(getattr(inspection, "account_name", "") or "").strip()
            template = str(getattr(inspection, "template_name", "") or "").strip()
            if account and template:
                summary.setdefault(account, set()).add(template)
        return {account: sorted(names) for account, names in summary.items()}

    def _edit_sc_profile_from_table(self, _event=None):
        tree = getattr(self, "sc_profile_tree", None)
        if not tree:
            return
        selected = tree.selection()
        if selected:
            self._open_sc_profile_editor(selected[0])

    def _new_sc_profile(self):
        self._open_sc_profile_editor("")

    def _open_sc_profile_editor(self, old_name):
        details = get_account_profile_details(old_name) if old_name else {}
        dialog = ctk.CTkToplevel(self)
        dialog.title("Thông tin account" if old_name else "Thêm account")
        dialog.geometry("520x500")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog, text="Thông tin SafetyCulture account",
            font=ctk.CTkFont(family=F, size=15, weight="bold"), text_color=TXT,
        ).pack(anchor="w", padx=22, pady=(18, 14))
        form = ctk.CTkFrame(dialog, fg_color="transparent")
        form.pack(fill="x", padx=22)

        entries = {}
        fields = (
            ("Tên account / user", "name", old_name, False),
            ("Email / Username đăng nhập", "email", details.get("email", ""), False),
            ("Password", "password", details.get("password", ""), True),
            ("Template folder URL", "folder", details.get("template_folder_url", ""), False),
        )
        for label, key, value, masked in fields:
            ctk.CTkLabel(form, text=label, width=145, anchor="w", text_color=DIM,
                         font=ctk.CTkFont(family=F, size=10)).pack(anchor="w", pady=(0, 2))
            entry = ctk.CTkEntry(form, height=32, show="*" if masked else "")
            entry.pack(fill="x", pady=(0, 8))
            if value:
                entry.insert(0, value)
            entries[key] = entry

        def save_from_dialog():
            name = entries["name"].get().strip()
            email = entries["email"].get().strip()
            password = entries["password"].get()
            folder_url = entries["folder"].get().strip()
            if not name or not email or not password:
                messagebox.showwarning("Thiếu thông tin", "Nhập tên account, email và password.", parent=dialog)
                return
            if folder_url and "safetyculture.com" not in folder_url:
                messagebox.showwarning("URL", "Folder URL phải là link SafetyCulture hoặc để trống.", parent=dialog)
                return

            renamed = bool(old_name and old_name != name)
            if renamed and not rename_account_profile(old_name, name):
                messagebox.showwarning("Không lưu được", "Tên account mới đã tồn tại hoặc tên cũ không còn.", parent=dialog)
                return
            if not save_account_profile(name, email, password, template_folder_url=folder_url):
                messagebox.showerror("Lỗi", "Không lưu được thông tin account.", parent=dialog)
                return

            csv_changed = 0
            fp = self.fv.get().strip() if hasattr(self, "fv") else ""
            if renamed and fp:
                csv_changed = rename_account_in_csv(fp, old_name, name)
                if csv_changed and os.path.exists(fp):
                    self._load()
            dialog.destroy()
            self._pg_accounts()
            extra = f" Đã đổi {csv_changed} ô account trong CSV đang chọn." if renamed and fp else ""
            messagebox.showinfo("Đã lưu", f"Account '{name}' đã được cập nhật.{extra}", parent=self)

        actions = ctk.CTkFrame(dialog, fg_color="transparent")
        actions.pack(fill="x", padx=22, pady=(6, 16))
        ctk.CTkButton(actions, text="Hủy", width=80, height=32, command=dialog.destroy,
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      text_color=DIM).pack(side="right", padx=(6, 0))
        ctk.CTkButton(actions, text="Lưu", width=80, height=32, command=save_from_dialog,
                      fg_color=GREEN, hover_color="#16A34A").pack(side="right")

    def _del_sc_profile_from_table(self):
        tree = getattr(self, "sc_profile_tree", None)
        selected = tree.selection() if tree else ()
        if not selected:
            messagebox.showwarning("Account", "Chọn account cần xóa.")
            return
        name = selected[0]
        if messagebox.askyesno("Xác nhận", f"Xóa SafetyCulture account '{name}'?"):
            if delete_account_profile(name):
                self._pg_accounts()
                messagebox.showinfo("Đã xóa", f"Đã xóa account: {name}")
            else:
                messagebox.showwarning("Account", "Không tìm thấy account.")

    def _act_lic(self):
        k = self.lke.get().strip()
        if not k: return
        ok, msg = activate_license(k)
        if ok:
            messagebox.showinfo("OK", msg)
            lic = get_license_info()
            badge_txt = lic.get('plan','trial').title()
            if badge_txt == "Lifetime": badge_txt = "Lifetime"
            if hasattr(self, 'lic_badge'):
                self.lic_badge.configure(text=f"{badge_txt}", text_color=GREEN if lic.get("valid") else RED)
            self._pg_settings()
        else:
            messagebox.showerror("Lỗi", msg)

    def _save_tg(self):
        feedback_chat_id = self.tg_feedback_chat.get().strip()
        if self.tg_support_errors.get() and not feedback_chat_id:
            messagebox.showwarning("Telegram", "Nhập Chat ID hỗ trợ trước khi bật tự gửi lỗi.")
            return False
        if feedback_chat_id and (not feedback_chat_id.isascii() or not feedback_chat_id.isdecimal()
                                 or feedback_chat_id.startswith("0") or len(feedback_chat_id) > 20):
            messagebox.showwarning("Telegram", "Chat ID hỗ trợ phải là ID cá nhân (số dương).")
            return False
        chat_ids = [
            value.strip()
            for value in self.tg_chat.get().replace("\n", ",").replace(";", ",").split(",")
            if value.strip()
        ]
        cfg = {
            "bot_token": self.tg_token.get().strip(),
            "chat_ids": chat_ids,
            "vons_bot_token": self.tg_vons_token.get().strip(),
            "vons_chat_ids": self.tg_vons_chat.get(),
            "enabled": self.tg_enabled.get(),
            "feedback_chat_id": feedback_chat_id,
            "auto_support_errors": self.tg_support_errors.get(),
        }
        save_telegram_config(cfg)
        messagebox.showinfo("OK", f"Đã lưu cấu hình Telegram ({len(chat_ids)} chat)")
        return True

    def _save_template_url(self):
        url = self.tpl_url.get().strip() if hasattr(self, "tpl_url") else ""
        if url and "safetyculture.com" not in url:
            messagebox.showwarning("URL", "URL phải là link SafetyCulture Templates hoặc để trống.")
            return
        cfg = load_autostart_config()
        cfg["template_folder_url"] = url
        save_autostart_config(cfg)
        messagebox.showinfo("OK", "Đã lưu Template folder URL")

    def _save_windows_startup(self):
        try:
            register_windows_startup(self.win_startup_enabled.get())
            prelogin_msg = ""
            if hasattr(self, "prelogin_task_enabled"):
                ok, prelogin_msg = register_prelogin_task(self.prelogin_task_enabled.get())
                if not ok:
                    messagebox.showerror(
                        "Task Scheduler",
                        "Không tạo được runner trước login.\n\n"
                        f"{prelogin_msg}\n\n"
                        "Hãy chạy CheckPilot bằng quyền Administrator rồi thử lại."
                    )
                    return

            parts = []
            parts.append("Sau login: bật" if self.win_startup_enabled.get() else "Sau login: tắt")
            if hasattr(self, "prelogin_task_enabled"):
                parts.append("Trước login: bật" if self.prelogin_task_enabled.get() else "Trước login: tắt")
            if prelogin_msg:
                parts.append(prelogin_msg)
            messagebox.showinfo("OK", "\n".join(parts))
        except Exception as e:
            messagebox.showerror("Lỗi", f"Lỗi: {e}")

    def _test_tg(self):
        if not self._save_tg():
            return
        ok, msg = test_telegram()
        if ok:
            messagebox.showinfo("OK", msg)
        else:
            messagebox.showerror("Lỗi", msg)

    def _logout(self):
        logout(); self.current_user = None; self._login()

    def _startup_update_check(self):
        """Silent update check on app startup."""
        from update_dialog import check_and_show_update
        check_and_show_update(self, force=False, silent=True)

    # ── Helpers ──
    def _card(self, title=None, hint=None, step=None):
        c = ctk.CTkFrame(self.pg, corner_radius=10, fg_color=CARD, border_width=1, border_color=BORDER)
        c.pack(fill="x", pady=(0, 10))
        if title:
            head = ctk.CTkFrame(c, fg_color="transparent"); head.pack(fill="x", padx=16, pady=(12, 8))
            if step is not None:
                ctk.CTkLabel(head, text=str(step), width=24, height=24, corner_radius=12, fg_color=TEAL,
                             text_color="#FFFFFF", font=_font(11, True)).pack(side="left", padx=(0, 10))
            ctk.CTkLabel(head, text=title, font=_font(13, True), text_color=TXT).pack(side="left")
            if hint:
                ctk.CTkLabel(head, text=hint, font=_font(10), text_color=MUTED).pack(side="left", padx=(10, 0))
        return c

    def _row(self, parent, label="", width=96, pady=3):
        """Card row with a fixed-width caption so controls line up."""
        r = ctk.CTkFrame(parent, fg_color="transparent"); r.pack(fill="x", padx=16, pady=pady)
        ctk.CTkLabel(r, text=label, width=width, anchor="w", font=_font(11), text_color=DIM).pack(side="left")
        return r

    def _btn(self, parent, text, command, kind="secondary", width=90, height=32, **kw):
        opts = dict(BUTTON_STYLES[kind])
        opts.update(kw)
        font = opts.pop("font", _font(11, kind == "primary"))
        return ctk.CTkButton(parent, text=text, command=command, width=width, height=height,
                             corner_radius=6, font=font, **opts)

    def _apply_ttk_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", font=(F, 10), rowheight=28, background=CARD, fieldbackground=CARD,
                        foreground=TXT, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, borderwidth=1)
        style.configure("Treeview.Heading", font=(F, 10, "bold"), background=ELEVATED, foreground=DIM,
                        relief="flat", bordercolor=BORDER, lightcolor=ELEVATED, darkcolor=BORDER, padding=(8, 6))
        style.map("Treeview", background=[("selected", "#D5ECE9")], foreground=[("selected", TXT)])
        style.map("Treeview.Heading", background=[("active", BORDER)])
        style.configure("Vertical.TScrollbar", background=ELEVATED, troughcolor=CARD, bordercolor=CARD,
                        lightcolor=ELEVATED, darkcolor=ELEVATED, arrowcolor=MUTED)

    def _live_widget(self, name):
        widget = getattr(self, name, None)
        if widget is None:
            return None
        try:
            return widget if widget.winfo_exists() else None
        except tk.TclError:
            return None

    def _safe_config(self, name, **kwargs):
        widget = self._live_widget(name)
        if not widget:
            return
        try:
            widget.configure(**kwargs)
        except tk.TclError:
            pass

    def _safe_after(self, delay_ms, callback):
        try:
            if not self.winfo_exists():
                return None
            return self.after(delay_ms, callback)
        except (tk.TclError, RuntimeError):
            return None

    def _safe_progress_set(self, value):
        self._run_progress = max(0.0, min(1.0, float(value or 0)))
        widget = self._live_widget("prog")
        if not widget:
            return
        try:
            widget.set(self._run_progress)
        except tk.TclError:
            pass

    def _set_run_status(self, text, color=TEAL, progress=None):
        self._run_state_text = text
        self._run_state_color = color
        if progress is not None:
            self._run_progress = max(0.0, min(1.0, float(progress or 0)))

        def apply():
            self._safe_config("slbl", text=self._run_state_text, text_color=self._run_state_color)
            if progress is not None:
                self._safe_progress_set(self._run_progress)
        self._safe_after(0, apply)

    def _is_worker_running(self):
        return bool(self.worker_thread and self.worker_thread.is_alive())

    def _sync_run_controls(self):
        running = self._is_worker_running() or self._run_active
        has_data = bool(self.inspections)
        selected = self.selected_inspection_index is not None

        if running:
            self._safe_config("brun_now", state="disabled")
            self._safe_config("bstart", state="disabled")
            self._safe_config("btest", state="disabled")
            self._safe_config("bpause", state="normal")
            self._safe_config("bstop", state="normal")
        else:
            state = "normal" if has_data else "disabled"
            self._safe_config("brun_now", state=state)
            self._safe_config("bstart", state=state)
            self._safe_config("btest", state="normal" if has_data and selected else "disabled")
            self._safe_config("bpause", state="disabled", text="Tạm dừng")
            self._safe_config("bstop", state="disabled")

        self._safe_config("slbl", text=self._run_state_text, text_color=self._run_state_color)
        self._safe_config("run_stat_lbl", text=self._run_stats_text)
        self._safe_progress_set(self._run_progress)
        self._update_auto_submit_warning()

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        def d():
            if msg.strip():
                self._last_log_line = " ".join(line.split())
                if not self._log_open:
                    self._safe_config("log_last_lbl", text=self._last_log_line[:120])
            if hasattr(self,'logbox') and self.logbox.winfo_exists():
                self.logbox.configure(state="normal")
                self.logbox.insert("end", line+"\n")
                self.logbox.see("end")
                self.logbox.configure(state="disabled")
        self._safe_after(0, d)

    def _clog(self):
        self.logbox.configure(state="normal"); self.logbox.delete("1.0","end"); self.logbox.configure(state="disabled")

    def _wipe(self):
        for w in self.winfo_children(): w.destroy()

    def _cls(self, key=None, scroll=False):
        """Swap in a fresh page frame and mark `key` active in the sidebar/topbar."""
        host = self._live_widget("pg_host")
        if not host:
            return
        for w in host.winfo_children(): w.destroy()
        if scroll:
            self.pg = ctk.CTkScrollableFrame(host, fg_color="transparent", corner_radius=0)
        else:
            self.pg = ctk.CTkFrame(host, fg_color="transparent")
        self.pg.pack(fill="both", expand=True)
        if key:
            title, sub = self.PAGES[key]
            self._safe_config("page_title_lbl", text=title)
            self._safe_config("page_sub_lbl", text=sub)
            for k, b in getattr(self, "_nav_btns", {}).items():
                if k == "about":
                    continue
                active = k == key
                b.configure(fg_color="#E3F1EF" if active else "transparent",
                            text_color=TEAL if active else DIM, font=_font(12, active))


def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()

