"""
CheckPilot - Inspection Automation Assistant
Designed by Pham Duy | 0868609901
Full-featured SaaS UI with dashboard, validation, history, test run
"""
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from typing import Optional
from datetime import datetime, date

import customtkinter as ctk

from data_loader import load_data, validate_data, validate_detailed, InspectionData
from automation import AutomationEngine
from auth import (
    authenticate, init_default_admin, get_saved_session, logout,
    get_license_info, activate_license, change_password,
)
from session_manager import (
    has_saved_credentials, save_credentials, load_credentials,
    has_saved_session as has_sc_session, clear_all as clear_sc_login,
)
from notifier import (
    load_telegram_config, save_telegram_config, test_connection as test_telegram,
    send_daily_summary, send_error_alert,
)
from runlock import is_already_run_today, mark_completed, get_remaining, reset_today
from template_lock import is_template_tested, mark_template_tested, get_untested_templates
from scheduler import (
    Scheduler, load_schedule, save_schedule,
    get_next_run_datetime, is_schedule_due_now, mark_schedule_run,
)
from history import add_record, get_records, get_stats, export_csv
from reporter import generate_report
from tray import TrayIcon
from config import BASE_DIR
from autostart import (
    save_last_config, get_last_data_file, get_last_image_folder,
    load_autostart_config, save_autostart_config,
    register_windows_startup, is_registered_startup,
    register_prelogin_task, is_prelogin_task_registered,
    build_validation_state, save_validation_state, is_validation_current,
)

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
        self.selected_inspection_index = None

        # Persistent StringVars (survive tab switches)
        self.fv = tk.StringVar()
        self.iv = tk.StringVar()
        _acfg = load_autostart_config()
        self.fv.set(_acfg.get("last_data_file", ""))
        self.iv.set(_acfg.get("last_image_folder", ""))
        self._validation_state = _acfg.get("validation_state") or None

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
        self.after(0, lambda: (self.deiconify(), self.lift(), self.focus_force()))

    def _quit(self):
        if self.scheduler: self.scheduler.stop()
        if self.tray: self.tray.hide()
        self.after(0, self.destroy)

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
        self._lu = ctk.CTkEntry(card, placeholder_text="Username", width=260, height=38,
                                 corner_radius=7, border_color=BORDER, font=ctk.CTkFont(family=F, size=12))
        self._lu.pack(pady=(0,8))
        self._lp = ctk.CTkEntry(card, placeholder_text="Password", show="*", width=260, height=38,
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

    # â•â•â•â•â•â•â•â•â•â•â• MAIN LAYOUT â•â•â•â•â•â•â•â•â•â•â•
    def _main(self):
        self._wipe()
        # Topbar
        top = ctk.CTkFrame(self, height=46, corner_radius=0, fg_color=CARD)
        top.pack(fill="x"); top.pack_propagate(False)
        ctk.CTkLabel(top, text="  CheckPilot", font=ctk.CTkFont(family=F, size=14, weight="bold"),
                     text_color=TEAL).pack(side="left", padx=10)
        rt = ctk.CTkFrame(top, fg_color="transparent"); rt.pack(side="right", padx=12)
        ctk.CTkButton(rt, text="Ẩn", width=55, height=24, corner_radius=4,
                      font=ctk.CTkFont(family=F, size=9), fg_color="transparent",
                      border_width=1, border_color=BORDER, hover_color=ELEVATED, text_color=DIM,
                      command=self._to_tray).pack(side="left", padx=(0,6))
        ctk.CTkLabel(rt, text=self.current_user, font=ctk.CTkFont(family=F, size=10),
                     text_color=DIM).pack(side="left", padx=(0,6))
        ctk.CTkButton(rt, text="Logout", width=55, height=24, corner_radius=4,
                      font=ctk.CTkFont(family=F, size=9), fg_color="transparent",
                      border_width=1, border_color=BORDER, hover_color=RED, text_color=DIM,
                      command=self._logout).pack(side="left", padx=(0,6))
        ctk.CTkButton(rt, text="Đóng", width=55, height=24, corner_radius=4,
                      fg_color="transparent", hover_color=ELEVATED, border_width=1,
                      border_color=BORDER, text_color=RED, font=ctk.CTkFont(family=F, size=9),
                      command=self._quit).pack(side="left")

        body = ctk.CTkFrame(self, fg_color="transparent"); body.pack(fill="both", expand=True)
        # Sidebar
        sb = ctk.CTkFrame(body, width=170, corner_radius=0, fg_color=CARD)
        sb.pack(side="left", fill="y"); sb.pack_propagate(False)
        navs = [("Automation", self._pg_auto), ("Lịch hẹn", self._pg_sched),
                ("Lịch sử", self._pg_history), ("Cài đặt", self._pg_settings),
                ("Diagnostics", self._pg_diag), ("Thông tin", self._pg_about)]
        for i,(lbl,cmd) in enumerate(navs):
            ctk.CTkButton(sb, text=lbl, width=150, height=34, anchor="w", corner_radius=7,
                          font=ctk.CTkFont(family=F, size=11), fg_color="transparent",
                          hover_color=ELEVATED, text_color=DIM, command=cmd
                          ).pack(padx=10, pady=(12 if i==0 else 2, 0))
        lic = get_license_info()
        badge_txt = lic.get('plan','trial').title()
        if badge_txt == "Lifetime": badge_txt = "Lifetime"
        badge_col = GREEN if lic.get("valid") else RED
        self.lic_badge = ctk.CTkLabel(sb, text=f"{badge_txt}",
                     font=ctk.CTkFont(family=F, size=10, weight="bold"),
                     text_color=badge_col)
        self.lic_badge.pack(side="bottom", pady=12)

        # Right side: content + persistent log
        right_side = ctk.CTkFrame(body, fg_color="transparent")
        right_side.pack(side="left", fill="both", expand=True, padx=14, pady=12)

        # Tab content (top, scrollable area)
        self.pg = ctk.CTkFrame(right_side, fg_color="transparent")
        self.pg.pack(fill="both", expand=True)

        # Persistent log panel (bottom, never destroyed)
        log_frame = ctk.CTkFrame(right_side, corner_radius=8, fg_color=CARD,
                                  border_width=1, border_color=BORDER, height=160)
        log_frame.pack(fill="x", pady=(8, 0))
        log_frame.pack_propagate(False)

        log_top = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_top.pack(fill="x", padx=10, pady=(6, 2))
        ctk.CTkLabel(log_top, text="Log", font=ctk.CTkFont(family=F, size=10, weight="bold"),
                     text_color=DIM).pack(side="left")
        ctk.CTkButton(log_top, text="Clear", width=42, height=18, corner_radius=3,
                      font=ctk.CTkFont(family=F, size=9), fg_color="transparent",
                      border_width=1, border_color=BORDER, hover_color=ELEVATED, text_color=MUTED,
                      command=self._clog).pack(side="right")

        self.logbox = ctk.CTkTextbox(log_frame, font=ctk.CTkFont(family="Consolas", size=10),
                                      state="disabled", corner_radius=5, fg_color=BG,
                                      text_color=DIM, border_width=0)
        self.logbox.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        sc = load_schedule()
        if sc.get("enabled"):
            self.scheduler = Scheduler(run_callback=self._sched_run, log_callback=self._log)
            self.scheduler.start()
        self._pg_auto()

        # Auto-load last used config
        self.after(500, self._auto_load_last_config)

        # Auto-check for updates on startup (silent, non-blocking)
        self.after(2000, self._startup_update_check)

    # â•â•â•â•â•â•â•â•â•â•â• PAGE: AUTOMATION â•â•â•â•â•â•â•â•â•â•â•
    def _pg_auto(self):
        self._cls()
        # Dashboard stats
        stats = get_stats()
        dash = ctk.CTkFrame(self.pg, fg_color="transparent")
        dash.pack(fill="x", pady=(0,8))
        for i,(lbl,val,col) in enumerate([
            ("Tổng chạy", str(stats["total"]), DIM),
            ("Hôm nay", str(stats["today"]), TEAL),
            ("Thành công", str(stats["success"]), GREEN),
            ("Lỗi", str(stats["failed"]), RED),
        ]):
            box = ctk.CTkFrame(dash, corner_radius=8, fg_color=CARD, border_width=1, border_color=BORDER)
            box.grid(row=0, column=i, padx=4, sticky="nsew")
            dash.grid_columnconfigure(i, weight=1)
            ctk.CTkLabel(box, text=val, font=ctk.CTkFont(family=F, size=18, weight="bold"),
                         text_color=col).pack(pady=(8,0))
            ctk.CTkLabel(box, text=lbl, font=ctk.CTkFont(family=F, size=9),
                         text_color=MUTED).pack(pady=(0,8))

        # Data input
        c1 = self._card("Dữ liệu đầu vào")
        r1 = ctk.CTkFrame(c1, fg_color="transparent"); r1.pack(fill="x", padx=12, pady=3)
        ctk.CTkLabel(r1, text="File", width=70, anchor="w", font=ctk.CTkFont(family=F, size=11),
                     text_color=DIM).pack(side="left")
        ctk.CTkEntry(r1, textvariable=self.fv, width=370, height=32, corner_radius=6,
                     border_color=BORDER, font=ctk.CTkFont(family=F, size=11)).pack(side="left", padx=4)
        ctk.CTkButton(r1, text="Browse", width=65, height=32, corner_radius=6,
                      fg_color=ELEVATED, hover_color=TEAL, border_width=1, border_color=BORDER,
                      font=ctk.CTkFont(family=F, size=10), command=self._pick_f).pack(side="left")

        r2 = ctk.CTkFrame(c1, fg_color="transparent"); r2.pack(fill="x", padx=12, pady=3)
        ctk.CTkLabel(r2, text="Ảnh", width=70, anchor="w", font=ctk.CTkFont(family=F, size=11),
                     text_color=DIM).pack(side="left")
        ctk.CTkEntry(r2, textvariable=self.iv, width=370, height=32, corner_radius=6,
                     border_color=BORDER, font=ctk.CTkFont(family=F, size=11)).pack(side="left", padx=4)
        ctk.CTkButton(r2, text="Browse", width=65, height=32, corner_radius=6,
                      fg_color=ELEVATED, hover_color=TEAL, border_width=1, border_color=BORDER,
                      font=ctk.CTkFont(family=F, size=10), command=self._pick_d).pack(side="left")

        r3 = ctk.CTkFrame(c1, fg_color="transparent"); r3.pack(fill="x", padx=12, pady=(6,10))
        ctk.CTkButton(r3, text="Validate", width=90, height=32, corner_radius=6,
                      fg_color="transparent", hover_color=ELEVATED, border_width=1, border_color=TEAL,
                      text_color=TEAL, font=ctk.CTkFont(family=F, size=11),
                      command=self._validate).pack(side="left", padx=(0,6))
        ctk.CTkButton(r3, text="Load", width=70, height=32, corner_radius=6,
                      fg_color="transparent", hover_color=ELEVATED, border_width=1, border_color=BORDER,
                      text_color=DIM, font=ctk.CTkFont(family=F, size=11), command=self._load).pack(side="left", padx=(0,6))
        self.btest = ctk.CTkButton(r3, text="Test mục đã chọn", width=130, height=32, corner_radius=6,
                      fg_color="transparent", hover_color=ELEVATED, border_width=1, border_color=BORDER,
                      text_color=DIM, font=ctk.CTkFont(family=F, size=11),
                      state="disabled", command=self._test_run)
        self.btest.pack(side="left")
        self.load_lbl = ctk.CTkLabel(r3, text="", font=ctk.CTkFont(family=F, size=10))
        self.load_lbl.pack(side="left", padx=10)

        list_hdr = ctk.CTkFrame(c1, fg_color="transparent")
        list_hdr.pack(fill="x", padx=12, pady=(0, 3))
        ctk.CTkLabel(
            list_hdr,
            text="Template / inspection trong CSV",
            font=ctk.CTkFont(family=F, size=10, weight="bold"),
            text_color=DIM,
        ).pack(side="left")
        self.selected_insp_lbl = ctk.CTkLabel(
            list_hdr,
            text="",
            font=ctk.CTkFont(family=F, size=9),
            text_color=MUTED,
        )
        self.selected_insp_lbl.pack(side="right")
        self.inspection_list_frame = ctk.CTkScrollableFrame(
            c1,
            height=112,
            fg_color=BG,
            corner_radius=7,
            border_width=1,
            border_color=BORDER,
        )
        self.inspection_list_frame.pack(fill="x", padx=12, pady=(0, 10))
        self._render_inspection_list()

        # Options
        c2 = self._card("Tùy chọn")
        orow = ctk.CTkFrame(c2, fg_color="transparent"); orow.pack(fill="x", padx=12, pady=8)
        self.rv = ctk.BooleanVar(value=False)
        self.av = ctk.BooleanVar(value=True)
        self.sv = ctk.BooleanVar(value=True)
        self.adv = ctk.BooleanVar(value=True)
        self.rv.trace_add("write", lambda *_: self._on_test_mode_changed())
        self.av.trace_add("write", lambda *_: self._update_auto_submit_warning())
        for txt, var in [("Test mode - không auto submit", self.rv), ("Auto submit sau khi hoàn tất", self.av), ("Từng inspection", self.sv), ("Ngày = hôm nay", self.adv)]:
            ctk.CTkCheckBox(orow, text=txt, variable=var, font=ctk.CTkFont(family=F, size=11),
                           text_color=DIM, border_color=BORDER, checkmark_color=TEAL).pack(side="left", padx=(0,14))
        self.auto_warn_lbl = ctk.CTkLabel(
            c2,
            text="Auto mode sẽ tự Complete/Submit inspection.",
            font=ctk.CTkFont(family=F, size=10),
            text_color=AMBER,
        )
        self.auto_warn_lbl.pack(anchor="w", padx=12, pady=(0,8))

        # Controls
        c3 = self._card("Điều khiển")
        cr = ctk.CTkFrame(c3, fg_color="transparent"); cr.pack(fill="x", padx=12, pady=8)
        self.brun_now = ctk.CTkButton(cr, text="Chạy ngay", width=100, height=36, corner_radius=7,
                                       fg_color="#0F766E", hover_color="#115E59", state="disabled",
                                       font=ctk.CTkFont(family=F, size=12, weight="bold"), command=self._run_now)
        self.brun_now.pack(side="left", padx=(0,5))
        self.bstart = ctk.CTkButton(cr, text="Chờ lịch", width=90, height=36, corner_radius=7,
                                     fg_color="transparent", hover_color=ELEVATED,
                                     border_width=1, border_color=TEAL, text_color=TEAL, state="disabled",
                                     font=ctk.CTkFont(family=F, size=11), command=self._start_scheduled)
        self.bstart.pack(side="left", padx=(0,5))
        self.bpause = ctk.CTkButton(cr, text="Pause", width=80, height=36, corner_radius=7,
                                     fg_color="transparent", hover_color=ELEVATED,
                                     border_width=1, border_color=BORDER, text_color=DIM,
                                     state="disabled", font=ctk.CTkFont(family=F, size=11), command=self._pause)
        self.bpause.pack(side="left", padx=(0,5))
        self.bstop = ctk.CTkButton(cr, text="Stop", width=80, height=36, corner_radius=7,
                                    fg_color="transparent", hover_color=ELEVATED,
                                    border_width=1, border_color=BORDER, text_color=RED,
                                    state="disabled", font=ctk.CTkFont(family=F, size=11), command=self._stop)
        self.bstop.pack(side="left", padx=(0,6))
        ctk.CTkButton(cr, text="Retry", width=70, height=36, corner_radius=7,
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      hover_color=ELEVATED, text_color=DIM,
                      font=ctk.CTkFont(family=F, size=10), command=self._retry_failed).pack(side="left", padx=(0,12))
        self.slbl = ctk.CTkLabel(cr, text="Sẵn sàng", font=ctk.CTkFont(family=F, size=11, weight="bold"),
                                  text_color=TEAL)
        self.slbl.pack(side="left")
        self.run_stat_lbl = ctk.CTkLabel(
            c3,
            text="Tổng inspection: 0 | Đã chạy: 0 | Thành công: 0 | Lỗi: 0 | Còn lại: 0",
            font=ctk.CTkFont(family=F, size=10),
            text_color=DIM,
        )
        self.run_stat_lbl.pack(anchor="w", padx=12, pady=(0,6))
        self.prog = ctk.CTkProgressBar(c3, height=4, corner_radius=2, progress_color=TEAL, fg_color=BORDER)
        self.prog.pack(fill="x", padx=12, pady=(0,10)); self.prog.set(0)


    def _pg_history(self):
        self._cls()
        ctk.CTkLabel(self.pg, text="Lịch sử chạy", font=ctk.CTkFont(family=F, size=16, weight="bold"),
                     text_color=TXT).pack(anchor="w", pady=(0,10))

        # Export button
        top_row = ctk.CTkFrame(self.pg, fg_color="transparent"); top_row.pack(fill="x", pady=(0,8))
        ctk.CTkButton(top_row, text="Xuất CSV", width=90, height=30, corner_radius=6,
                      fg_color=TEAL, hover_color=TEAL_H, font=ctk.CTkFont(family=F, size=10),
                      command=self._export_history).pack(side="left", padx=(0,6))
        ctk.CTkButton(top_row, text="Xóa lịch sử", width=95, height=30, corner_radius=6,
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      hover_color=ELEVATED, text_color=DIM, font=ctk.CTkFont(family=F, size=10),
                      command=self._clear_history).pack(side="left")
        stats = get_stats()
        ctk.CTkLabel(top_row, text=f"Tổng: {stats['total']} | OK: {stats['success']} | Lỗi: {stats['failed']}",
                     font=ctk.CTkFont(family=F, size=10), text_color=DIM).pack(side="left", padx=14)

        # Records list
        records = get_records(30)
        scroll = ctk.CTkScrollableFrame(self.pg, fg_color=CARD, corner_radius=8,
                                         border_width=1, border_color=BORDER)
        scroll.pack(fill="both", expand=True)

        if not records:
            ctk.CTkLabel(scroll, text="Chưa có lịch sử", font=ctk.CTkFont(family=F, size=11),
                         text_color=MUTED).pack(pady=20)
        else:
            for r in records:
                row = ctk.CTkFrame(scroll, fg_color="transparent", height=32)
                row.pack(fill="x", padx=8, pady=2)
                ts = r.get("timestamp","")[:16].replace("T"," ")
                icon = "OK" if r.get("success") else "ERR"
                ic = GREEN if r.get("success") else RED
                ctk.CTkLabel(row, text=icon, width=20, text_color=ic,
                             font=ctk.CTkFont(size=12)).pack(side="left")
                ctk.CTkLabel(row, text=ts, width=110, font=ctk.CTkFont(family=F, size=10),
                             text_color=DIM).pack(side="left")
                ctk.CTkLabel(row, text=r.get("template","")[:25], width=180,
                             font=ctk.CTkFont(family=F, size=10), text_color=TXT).pack(side="left")
                ctk.CTkLabel(row, text=r.get("site","")[:20], width=140,
                             font=ctk.CTkFont(family=F, size=10), text_color=DIM).pack(side="left")
                errs = r.get("errors",[])
                if errs:
                    ctk.CTkLabel(row, text=errs[0][:30], font=ctk.CTkFont(family=F, size=9),
                                 text_color=RED).pack(side="left", padx=6)

    # ═══════════ PAGE: SCHEDULER ═══════════
    def _pg_sched(self):
        self._cls()
        sched = load_schedule()
        ctk.CTkLabel(self.pg, text="Lịch hẹn tự động", font=ctk.CTkFont(family=F, size=16, weight="bold"),
                     text_color=TXT).pack(anchor="w", pady=(0,3))
        ctk.CTkLabel(self.pg, text="Máy bật 24/7 - tự chạy inspection đúng giờ. Hỗ trợ nhiều lần/ngày.",
                     font=ctk.CTkFont(family=F, size=10), text_color=MUTED).pack(anchor="w", pady=(0,12))

        # Enable switch
        c1 = self._card(None)
        r = ctk.CTkFrame(c1, fg_color="transparent"); r.pack(fill="x", padx=12, pady=10)
        self.se = ctk.BooleanVar(value=sched.get("enabled", False))
        ctk.CTkSwitch(r, text="  Bật lịch hẹn", variable=self.se, font=ctk.CTkFont(family=F, size=12),
                      text_color=TXT, progress_color=TEAL).pack(side="left")

        # Multi-time section
        c2 = self._card("Giờ chạy (nhiều giờ/ngày)")
        self._sched_times = list(sched.get("times", [sched.get("time", "05:00")]))
        if isinstance(self._sched_times, str):
            self._sched_times = [self._sched_times]

        self._times_frame = ctk.CTkFrame(c2, fg_color="transparent")
        self._times_frame.pack(fill="x", padx=12, pady=(4, 0))
        self._render_times_list()

        # Add time row
        add_row = ctk.CTkFrame(c2, fg_color="transparent"); add_row.pack(fill="x", padx=12, pady=(6, 10))
        self._new_hour = ctk.CTkOptionMenu(add_row, values=[f"{h:02d}" for h in range(24)], width=60,
                                            fg_color=ELEVATED, button_color=BORDER, button_hover_color=TEAL)
        self._new_hour.set("08"); self._new_hour.pack(side="left", padx=(0, 3))
        ctk.CTkLabel(add_row, text=":", text_color=TXT).pack(side="left")
        self._new_min = ctk.CTkOptionMenu(add_row, values=[f"{m:02d}" for m in range(0, 60, 5)], width=60,
                                           fg_color=ELEVATED, button_color=BORDER, button_hover_color=TEAL)
        self._new_min.set("00"); self._new_min.pack(side="left", padx=(3, 8))
        ctk.CTkButton(add_row, text="+ Thêm giờ", width=90, height=28, corner_radius=5,
                      fg_color=TEAL, hover_color=TEAL_H, font=ctk.CTkFont(family=F, size=10),
                      command=self._add_sched_time).pack(side="left")

        # Days
        c3 = self._card("Ngày trong tuần")
        dr = ctk.CTkFrame(c3, fg_color="transparent"); dr.pack(fill="x", padx=12, pady=8)
        ad = sched.get("days", ["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
        self.dvs = {}
        for lbl, k in [("T2","mon"),("T3","tue"),("T4","wed"),("T5","thu"),("T6","fri"),("T7","sat"),("CN","sun")]:
            v = ctk.BooleanVar(value=k in ad); self.dvs[k] = v
            ctk.CTkCheckBox(dr, text=lbl, variable=v, width=48, font=ctk.CTkFont(family=F, size=10),
                           text_color=DIM, border_color=BORDER, checkmark_color=TEAL).pack(side="left", padx=3)

        # Next run info
        if self.scheduler:
            next_run = self.scheduler.get_next_run()
            ctk.CTkLabel(self.pg, text=f"Lần chạy tiếp: {next_run}",
                         font=ctk.CTkFont(family=F, size=10), text_color=TEAL).pack(anchor="w", pady=(8, 0))

        ctk.CTkButton(self.pg, text="Lưu", width=100, height=34, corner_radius=7,
                      fg_color=TEAL, hover_color=TEAL_H, font=ctk.CTkFont(family=F, size=11, weight="bold"),
                      command=self._save_sched).pack(anchor="w", pady=(10,0))

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

    # â•â•â•â•â•â•â•â•â•â•â• PAGE: SETTINGS â•â•â•â•â•â•â•â•â•â•â•
    def _pg_settings(self):
        self._cls()
        ctk.CTkLabel(self.pg, text="Cài đặt", font=ctk.CTkFont(family=F, size=16, weight="bold"),
                     text_color=TXT).pack(anchor="w", pady=(0,12))

        # SC Login
        c1 = self._card("Đăng nhập SafetyCulture")
        hc, hs = has_saved_credentials(), has_sc_session()
        if hs and hc: st,sc = "Auto-login ready", GREEN
        elif hc: st,sc = "Credentials saved", AMBER
        else: st,sc = "Chưa cấu hình", MUTED
        ctk.CTkLabel(c1, text=st, font=ctk.CTkFont(family=F, size=10), text_color=sc).pack(anchor="w", padx=12, pady=(0,6))
        row = ctk.CTkFrame(c1, fg_color="transparent"); row.pack(fill="x", padx=12, pady=(0,10))
        self.sce = ctk.CTkEntry(row, placeholder_text="Email", width=180, height=32, corner_radius=6, border_color=BORDER)
        self.sce.pack(side="left", padx=(0,4))
        self.scp = ctk.CTkEntry(row, placeholder_text="Password", show="*", width=160, height=32, corner_radius=6, border_color=BORDER)
        self.scp.pack(side="left", padx=(0,5))
        ctk.CTkButton(row, text="Lưu", width=50, height=32, corner_radius=6, fg_color=GREEN,
                      hover_color="#16A34A", font=ctk.CTkFont(family=F, size=10), command=self._save_sc).pack(side="left", padx=(0,3))
        ctk.CTkButton(row, text="Xóa", width=50, height=32, corner_radius=6, fg_color=RED,
                      hover_color=RED_H, font=ctk.CTkFont(family=F, size=10), command=self._del_sc).pack(side="left")
        if hc:
            cr = load_credentials()
            if cr: self.sce.insert(0, cr[0])

        # License
        c2 = self._card("License")
        lic = get_license_info()
        plan = lic.get("plan","trial").title()
        valid = lic.get("valid", False)
        days = lic.get("days_remaining",0)
        lt = f"{plan} - {'Vĩnh viễn' if plan=='Lifetime' else f'{days} ngày'}"
        ctk.CTkLabel(c2, text=lt, font=ctk.CTkFont(family=F, size=11, weight="bold"),
                     text_color=GREEN if valid else RED).pack(anchor="w", padx=12, pady=(0,6))
        lr = ctk.CTkFrame(c2, fg_color="transparent"); lr.pack(fill="x", padx=12, pady=(0,10))
        self.lke = ctk.CTkEntry(lr, placeholder_text="License key", width=260, height=32, corner_radius=6, border_color=BORDER)
        self.lke.pack(side="left", padx=(0,5))
        ctk.CTkButton(lr, text="Kích hoạt", width=80, height=32, corner_radius=6,
                      fg_color=TEAL, hover_color=TEAL_H, font=ctk.CTkFont(family=F, size=10, weight="bold"),
                      command=self._act_lic).pack(side="left")

        # Template folder
        c_tpl = self._card("Templates")
        ctk.CTkLabel(
            c_tpl,
            text="Để trống nếu dùng trang Templates mặc định.",
            font=ctk.CTkFont(family=F, size=10),
            text_color=MUTED,
        ).pack(anchor="w", padx=12, pady=(0,6))
        tpl_row = ctk.CTkFrame(c_tpl, fg_color="transparent"); tpl_row.pack(fill="x", padx=12, pady=(0,10))
        self.tpl_url = ctk.CTkEntry(
            tpl_row,
            placeholder_text="Template folder URL",
            width=420,
            height=32,
            corner_radius=6,
            border_color=BORDER,
        )
        self.tpl_url.pack(side="left", padx=(0,5))
        saved_tpl_url = load_autostart_config().get("template_folder_url", "")
        if saved_tpl_url:
            self.tpl_url.insert(0, saved_tpl_url)
        ctk.CTkButton(
            tpl_row,
            text="Lưu",
            width=55,
            height=32,
            corner_radius=6,
            fg_color=TEAL,
            hover_color=TEAL_H,
            font=ctk.CTkFont(family=F, size=10),
            command=self._save_template_url,
        ).pack(side="left")

        # Windows startup
        c_startup = self._card("Windows")
        startup_row = ctk.CTkFrame(c_startup, fg_color="transparent")
        startup_row.pack(fill="x", padx=12, pady=(0,10))
        self.win_startup_enabled = ctk.BooleanVar(value=is_registered_startup())
        ctk.CTkCheckBox(
            startup_row,
            text="Mở app sau khi user login",
            variable=self.win_startup_enabled,
            font=ctk.CTkFont(family=F, size=10),
            text_color=DIM,
            border_color=BORDER,
            checkmark_color=TEAL,
        ).pack(side="left", padx=(0,10))

        startup_row2 = ctk.CTkFrame(c_startup, fg_color="transparent")
        startup_row2.pack(fill="x", padx=12, pady=(0,6))
        self.prelogin_task_enabled = ctk.BooleanVar(value=is_prelogin_task_registered())
        ctk.CTkCheckBox(
            startup_row2,
            text="Runner nền trước login (headless)",
            variable=self.prelogin_task_enabled,
            font=ctk.CTkFont(family=F, size=10),
            text_color=DIM,
            border_color=BORDER,
            checkmark_color=TEAL,
        ).pack(side="left", padx=(0,10))
        ctk.CTkLabel(
            startup_row2,
            text="Dùng Task Scheduler, cần session/credentials SafetyCulture đã lưu.",
            font=ctk.CTkFont(family=F, size=9),
            text_color=MUTED,
        ).pack(side="left")

        startup_save_row = ctk.CTkFrame(c_startup, fg_color="transparent")
        startup_save_row.pack(fill="x", padx=12, pady=(0,10))
        ctk.CTkButton(
            startup_save_row,
            text="Lưu",
            width=55,
            height=28,
            corner_radius=5,
            fg_color=TEAL,
            hover_color=TEAL_H,
            font=ctk.CTkFont(family=F, size=10),
            command=self._save_windows_startup,
        ).pack(side="left")

        # Telegram
        c3 = self._card("Telegram Alerts")
        tg_cfg = load_telegram_config()
        tg_st = "Enabled" if tg_cfg.get("enabled") else "Disabled"
        tg_col = GREEN if tg_cfg.get("enabled") else MUTED
        ctk.CTkLabel(c3, text=f"Status: {tg_st}", font=ctk.CTkFont(family=F, size=10),
                     text_color=tg_col).pack(anchor="w", padx=12, pady=(0,6))

        tr1 = ctk.CTkFrame(c3, fg_color="transparent"); tr1.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(tr1, text="Bot Token:", width=75, anchor="w", font=ctk.CTkFont(family=F, size=10),
                     text_color=DIM).pack(side="left")
        self.tg_token = ctk.CTkEntry(tr1, width=320, height=30, corner_radius=6, border_color=BORDER,
                                      font=ctk.CTkFont(family=F, size=10))
        self.tg_token.pack(side="left", padx=4)
        if tg_cfg.get("bot_token"): self.tg_token.insert(0, tg_cfg["bot_token"])

        tr2 = ctk.CTkFrame(c3, fg_color="transparent"); tr2.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(tr2, text="Chat IDs:", width=75, anchor="w", font=ctk.CTkFont(family=F, size=10),
                     text_color=DIM).pack(side="left")
        self.tg_chat = ctk.CTkEntry(tr2, width=320, height=30, corner_radius=6, border_color=BORDER,
                                     placeholder_text="Nhiều Chat ID: cách nhau bằng dấu phẩy",
                                     font=ctk.CTkFont(family=F, size=10))
        self.tg_chat.pack(side="left", padx=4)
        chat_ids = tg_cfg.get("chat_ids") or ([tg_cfg.get("chat_id")] if tg_cfg.get("chat_id") else [])
        if chat_ids: self.tg_chat.insert(0, ", ".join(chat_ids))

        tr3 = ctk.CTkFrame(c3, fg_color="transparent"); tr3.pack(fill="x", padx=12, pady=(6,10))
        self.tg_enabled = ctk.BooleanVar(value=tg_cfg.get("enabled", False))
        ctk.CTkCheckBox(tr3, text="Bật thông báo", variable=self.tg_enabled,
                        font=ctk.CTkFont(family=F, size=10), text_color=DIM,
                        border_color=BORDER, checkmark_color=TEAL).pack(side="left", padx=(0,10))
        ctk.CTkButton(tr3, text="Lưu", width=55, height=28, corner_radius=5,
                      fg_color=TEAL, hover_color=TEAL_H, font=ctk.CTkFont(family=F, size=10),
                      command=self._save_tg).pack(side="left", padx=(0,5))
        ctk.CTkButton(tr3, text="Test", width=55, height=28, corner_radius=5,
                      fg_color="transparent", hover_color=ELEVATED, border_width=1, border_color=BORDER,
                      text_color=DIM, font=ctk.CTkFont(family=F, size=10),
                      command=self._test_tg).pack(side="left")

    # â•â•â•â•â•â•â•â•â•â•â• PAGE: ABOUT â•â•â•â•â•â•â•â•â•â•â•
    # ═══ DIAGNOSTICS ═══
    def _pg_diag(self):
        self._cls()
        ctk.CTkLabel(self.pg, text="Diagnostics", font=ctk.CTkFont(family=F, size=16, weight="bold"),
                     text_color=TXT).pack(anchor="w", pady=(0,12))

        c = self._card("System Info")
        from config import SCREENSHOT_DIR, LOG_DIR, DATA_DIR, BROWSERS_DIR
        from runlock import get_today_completed
        from reporter import get_reports_dir
        from updater import get_current_version, check_for_update
        from template_lock import get_all_locks

        items = [("App version", get_current_version()),
                 ("Python", f"{sys.version_info.major}.{sys.version_info.minor}"),
                 ("Data folder", DATA_DIR), ("Reports", get_reports_dir()),
                 ("Session", "Yes" if has_sc_session() else "No"),
                 ("Credentials", "Yes" if has_saved_credentials() else "No"),
                 ("Telegram", "On" if load_telegram_config().get("enabled") else "Off"),
                 ("Today done", str(len(get_today_completed()))),
                 ("Templates tested", str(len(get_all_locks()))),
                 ("Scheduler", "Running" if (self.scheduler and self.scheduler.is_running()) else "Off")]
        for k, v in items:
            row = ctk.CTkFrame(c, fg_color="transparent"); row.pack(fill="x", padx=12, pady=2)
            ctk.CTkLabel(row, text=k, width=130, anchor="w", font=ctk.CTkFont(family=F, size=10), text_color=MUTED).pack(side="left")
            ctk.CTkLabel(row, text=v, font=ctk.CTkFont(family=F, size=10), text_color=DIM).pack(side="left")

        # Actions
        c2 = self._card("Actions")
        ar = ctk.CTkFrame(c2, fg_color="transparent"); ar.pack(fill="x", padx=12, pady=8)
        btns = [
            ("Reset run lock", self._reset_lock),
            ("Reset template locks", self._reset_tmpl_locks),
            ("Check update", self._check_update),
            ("Export config", self._export_cfg),
            ("Import config", self._import_cfg),
        ]
        for txt, cmd in btns:
            ctk.CTkButton(ar, text=txt, width=115, height=26, corner_radius=5,
                          fg_color="transparent", border_width=1, border_color=BORDER,
                          hover_color=ELEVATED, text_color=DIM,
                          font=ctk.CTkFont(family=F, size=9), command=cmd).pack(side="left", padx=(0,4))

        # Open folders
        c3 = self._card("Folders")
        fr = ctk.CTkFrame(c3, fg_color="transparent"); fr.pack(fill="x", padx=12, pady=8)
        for lbl, path in [("Reports", get_reports_dir()), ("Logs", LOG_DIR), ("Screenshots", SCREENSHOT_DIR)]:
            ctk.CTkButton(fr, text=lbl, width=85, height=24, corner_radius=4,
                          fg_color="transparent", border_width=1, border_color=BORDER,
                          hover_color=ELEVATED, text_color=DIM, font=ctk.CTkFont(family=F, size=9),
                          command=lambda p=path: os.startfile(p) if sys.platform=="win32" else None
                          ).pack(side="left", padx=(0,4))

    def _reset_lock(self):
        reset_today()
        messagebox.showinfo("OK", "Run lock cleared")
        self._pg_diag()

    def _reset_tmpl_locks(self):
        from template_lock import reset_all
        if messagebox.askyesno("Confirm", "Reset all template locks?\nAll templates will require re-testing."):
            reset_all()
            messagebox.showinfo("OK", "Template locks cleared")
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
                messagebox.showinfo("OK", f"Config exported to:\n{p}")
            else:
                messagebox.showerror("Error", "Export failed")

    def _import_cfg(self):
        from backup import import_config, get_backup_info
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not p: return
        info = get_backup_info(p)
        if not info:
            messagebox.showerror("Error", "Invalid backup file")
            return
        if messagebox.askyesno("Import Config",
            f"Backup from: {info.get('exported_at','?')}\n"
            f"Version: {info.get('version','?')}\n"
            f"Files: {len(info.get('files',[]))}\n\nImport and overwrite current config?"):
            ok, msg, _ = import_config(p)
            if ok:
                messagebox.showinfo("OK", msg + "\nRestart app to apply.")
            else:
                messagebox.showerror("Error", msg)

    def _pg_about(self):
        self._cls()
        w = ctk.CTkFrame(self.pg, fg_color="transparent")
        w.place(relx=0.5, rely=0.38, anchor="center")
        ctk.CTkLabel(w, text="CheckPilot", font=ctk.CTkFont(family=F, size=24, weight="bold"),
                     text_color=TEAL).pack(pady=(0,2))
        ctk.CTkLabel(w, text="Inspection Automation Assistant",
                     font=ctk.CTkFont(family=F, size=11), text_color=DIM).pack(pady=(0,16))
        info = ctk.CTkFrame(w, corner_radius=10, fg_color=CARD, border_width=1, border_color=BORDER, width=320)
        info.pack()
        from updater import get_current_version
        for i,(k,v) in enumerate([("Version",get_current_version()),("Developer","Phạm Duy"),("Contact","0868609901"),
                                   ("Stack","Python / Playwright"),("Platform","Windows / macOS")]):
            r = ctk.CTkFrame(info, fg_color="transparent"); r.pack(fill="x", padx=16, pady=(8 if i==0 else 3, 3 if i<4 else 8))
            ctk.CTkLabel(r, text=k, width=80, anchor="w", font=ctk.CTkFont(family=F, size=10), text_color=MUTED).pack(side="left")
            ctk.CTkLabel(r, text=v, font=ctk.CTkFont(family=F, size=10, weight="bold"), text_color=TXT).pack(side="left")
        ctk.CTkLabel(w, text="Licensed software - Single client use only",
                     font=ctk.CTkFont(family=F, size=9), text_color=MUTED).pack(pady=(12,0))

    # â•â•â•â•â•â•â•â•â•â•â• ACTIONS â•â•â•â•â•â•â•â•â•â•â•
    def _on_test_mode_changed(self):
        if hasattr(self, "av") and self.rv.get():
            self.av.set(False)
        self._update_auto_submit_warning()

    def _update_auto_submit_warning(self):
        if not hasattr(self, "auto_warn_lbl"):
            return
        if self.rv.get() and self.av.get():
            self.av.set(False)
            return
        if self.av.get() and not self.rv.get():
            self.auto_warn_lbl.configure(text="Auto mode sẽ tự Complete/Submit inspection.", text_color=AMBER)
        else:
            self.auto_warn_lbl.configure(text="", text_color=MUTED)

    def _set_run_stats(self, total=0, done=0, success=0, failed=0):
        remaining = max(total - done, 0)
        text = f"Tổng inspection: {total} | Đã chạy: {done} | Thành công: {success} | Lỗi: {failed} | Còn lại: {remaining}"
        self._log(text)
        if hasattr(self, "run_stat_lbl"):
            self.after(0, lambda: self.run_stat_lbl.configure(text=text))

    def _render_inspection_list(self):
        if not hasattr(self, "inspection_list_frame"):
            return
        for w in self.inspection_list_frame.winfo_children():
            w.destroy()

        if not self.inspections:
            ctk.CTkLabel(
                self.inspection_list_frame,
                text="Load file CSV/Excel để hiện danh sách test.",
                font=ctk.CTkFont(family=F, size=10),
                text_color=MUTED,
            ).pack(anchor="w", padx=8, pady=8)
            if hasattr(self, "selected_insp_lbl"):
                self.selected_insp_lbl.configure(text="")
            if hasattr(self, "btest"):
                self.btest.configure(state="disabled")
            return

        if self.selected_inspection_index is None or self.selected_inspection_index >= len(self.inspections):
            self.selected_inspection_index = 0

        selected = self.selected_inspection_index
        if hasattr(self, "selected_insp_lbl"):
            self.selected_insp_lbl.configure(text=f"Đang chọn: {selected + 1}/{len(self.inspections)}")
        if hasattr(self, "btest"):
            self.btest.configure(state="normal")

        for idx, insp in enumerate(self.inspections):
            is_selected = idx == selected
            row = ctk.CTkFrame(
                self.inspection_list_frame,
                fg_color="#E6F4F1" if is_selected else "transparent",
                corner_radius=5,
                height=32,
            )
            row.pack(fill="x", padx=4, pady=2)
            row.pack_propagate(False)

            title = f"{idx + 1}. {insp.template_name}"
            if len(title) > 54:
                title = title[:51] + "..."
            ctk.CTkLabel(
                row,
                text=title,
                width=330,
                anchor="w",
                font=ctk.CTkFont(family=F, size=10, weight="bold" if is_selected else "normal"),
                text_color=TEAL if is_selected else TXT,
            ).pack(side="left", padx=(8, 4))

            meta = f"{insp.site_location[:24]} | {len(insp.items)} câu"
            ctk.CTkLabel(
                row,
                text=meta,
                width=170,
                anchor="w",
                font=ctk.CTkFont(family=F, size=9),
                text_color=MUTED,
            ).pack(side="left", padx=(0, 4))

            ctk.CTkButton(
                row,
                text="Đã chọn" if is_selected else "Chọn",
                width=62,
                height=24,
                corner_radius=5,
                fg_color=TEAL if is_selected else "transparent",
                hover_color=TEAL_H if is_selected else ELEVATED,
                border_width=0 if is_selected else 1,
                border_color=BORDER,
                text_color="#FFFFFF" if is_selected else DIM,
                font=ctk.CTkFont(family=F, size=9),
                command=lambda i=idx: self._select_inspection(i),
            ).pack(side="left", padx=(0, 4))

            ctk.CTkButton(
                row,
                text="Test",
                width=54,
                height=24,
                corner_radius=5,
                fg_color="transparent",
                hover_color=ELEVATED,
                border_width=1,
                border_color=TEAL,
                text_color=TEAL,
                font=ctk.CTkFont(family=F, size=9),
                command=lambda i=idx: self._test_run_index(i),
            ).pack(side="left")

    def _select_inspection(self, idx: int):
        if idx < 0 or idx >= len(self.inspections):
            return
        self.selected_inspection_index = idx
        insp = self.inspections[idx]
        self._log(f"Đã chọn test: {idx + 1}. {insp.template_name} | {len(insp.items)} câu")
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
            self.bstart.configure(state="disabled")
            if hasattr(self, "brun_now"):
                self.brun_now.configure(state="disabled")
            if hasattr(self, "btest"):
                self.btest.configure(state="disabled")
    def _pick_d(self):
        p = filedialog.askdirectory()
        if p:
            self.iv.set(p)
            self._validation_state = None
            self._save_current_settings()
            self.bstart.configure(state="disabled")

    def _validate(self):
        """Detailed data validation."""
        fp = self.fv.get().strip()
        if not fp: self.load_lbl.configure(text="Chọn file", text_color=AMBER); return
        if not os.path.exists(fp): self.load_lbl.configure(text="File không tồn tại", text_color=RED); return
        img = self.iv.get().strip()
        report = validate_detailed(fp, img)
        self._log("--- Validate Report ---")
        s = report["stats"]
        self._log(f"  Rows: {s.get('total_rows',0)} | Templates: {s.get('templates',0)} | Sites: {s.get('sites',0)}")
        if s.get("images_total"): self._log(f"  Ảnh: {s['images_total']} tổng, {s.get('images_missing',0)} thiếu")
        if report["errors"]:
            self.load_lbl.configure(text=f"{len(report['errors'])} lỗi", text_color=RED)
            for e in report["errors"]: self._log(f"  ERROR: {e}")
        if report["warnings"]:
            for w in report["warnings"]: self._log(f"  WARNING: {w}")
        missing_images = report.get("stats", {}).get("images_missing", 0)
        missing_accepted = False
        if report["ok"] and missing_images:
            missing_accepted = messagebox.askyesno(
                "Cảnh báo ảnh",
                "Có ảnh không tìm thấy. Bạn có muốn tiếp tục không?"
            )
            if not missing_accepted:
                report["ok"] = False
                self.load_lbl.configure(text="Chưa chấp nhận ảnh thiếu", text_color=AMBER)
                self._log("  Dừng vì có ảnh không tìm thấy")
        self._validation_state = build_validation_state(
            fp, img, bool(report["ok"]), missing_images, missing_accepted
        )
        save_validation_state(self._validation_state)
        self._save_current_settings()
        if report["ok"]:
            self.load_lbl.configure(text="Dữ liệu hợp lệ", text_color=GREEN)
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
            self.load_lbl.configure(text="Chọn file", text_color=AMBER)
            self._log("Validate failed: chưa chọn file")
            return False
        if not os.path.exists(fp):
            self.load_lbl.configure(text="File không tồn tại", text_color=RED)
            self._log("Validate failed: file không tồn tại")
            return False

        img = self.iv.get().strip()
        report = validate_detailed(fp, img)
        missing_images = report.get("stats", {}).get("images_missing", 0)
        missing_accepted = False

        if report["errors"]:
            self.load_lbl.configure(text=f"{len(report['errors'])} lỗi", text_color=RED)
            for e in report["errors"]:
                self._log(f"Validate failed: {e}")
            self._validation_state = build_validation_state(fp, img, False, missing_images, False)
            save_validation_state(self._validation_state)
            return False

        if missing_images:
            if not allow_prompt:
                self.load_lbl.configure(text="Có ảnh không tìm thấy", text_color=AMBER)
                self._log("Validate failed: Có ảnh không tìm thấy. Cần Validate và xác nhận thủ công trước khi chạy lịch.")
                return False
            missing_accepted = messagebox.askyesno(
                "Cảnh báo ảnh",
                "Có ảnh không tìm thấy. Bạn có muốn tiếp tục không?"
            )
            if not missing_accepted:
                self.load_lbl.configure(text="Chưa chấp nhận ảnh thiếu", text_color=AMBER)
                self._log("Validate failed: người dùng không tiếp tục khi thiếu ảnh")
                return False

        self._validation_state = build_validation_state(fp, img, True, missing_images, missing_accepted)
        save_validation_state(self._validation_state)
        self._save_current_settings()
        return True

    def _load(self):
        fp = self.fv.get().strip()
        if not fp: self.load_lbl.configure(text="Chọn file", text_color=AMBER); return
        if not os.path.exists(fp): self.load_lbl.configure(text="Không tồn tại", text_color=RED); return
        try:
            self._data_file = fp
            img = self.iv.get().strip()
            self._image_folder = img
            self._save_current_settings()
            self.inspections = load_data(fp, img)
            if self.adv.get():
                for i in self.inspections: i.inspection_date = date.today().isoformat()
            if self.selected_inspection_index is None or self.selected_inspection_index >= len(self.inspections):
                self.selected_inspection_index = 0 if self.inspections else None
            n, items = len(self.inspections), sum(len(i.items) for i in self.inspections)
            self.load_lbl.configure(text=f"{n} insp - {items} items", text_color=GREEN)
            self._log(f"Loaded {n} inspection(s), {items} items")
            self._render_inspection_list()
            self.bstart.configure(state="normal")
            if hasattr(self, 'brun_now'):
                self.brun_now.configure(state="normal")
            if hasattr(self, 'btest'):
                self.btest.configure(state="normal")
        except Exception as e:
            self.load_lbl.configure(text=str(e)[:40], text_color=RED)
            self._render_inspection_list()

    def _test_run(self):
        """Run selected inspection as a test - show preview first."""
        if not self.inspections:
            self._load()
            if not self.inspections:
                messagebox.showwarning("", "Load dữ liệu trước")
                return
        idx = self.selected_inspection_index
        if idx is None or idx >= len(self.inspections):
            idx = 0
        self._test_run_index(idx)

    def _test_run_index(self, idx: int):
        if not self.inspections:
            self._load()
            if not self.inspections:
                messagebox.showwarning("", "Load dữ liệu trước")
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
            messagebox.showwarning("", "Load dữ liệu trước")
            return
        if idx is None:
            idx = self.selected_inspection_index if self.selected_inspection_index is not None else 0
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
        pw.title("Preview - Xem trước dữ liệu")
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
        """Run immediately — bypass schedule AND template lock."""
        if not self.inspections:
            if self.fv.get().strip():
                self._load()
            if not self.inspections:
                self._log("Chưa có dữ liệu. Load file trước.")
                return
        if self.worker_thread and self.worker_thread.is_alive():
            self._log("Đang chạy rồi!")
            return
        if not self._ensure_validated_before_start(allow_prompt=True):
            return
        self._log("\n=== CHẠY NGAY ===")
        self._scheduled_run = False
        self._bypass_template_lock = True  # Bypass lock for manual run
        self.brun_now.configure(state="disabled")
        self.bstart.configure(state="disabled")
        if hasattr(self, "btest"):
            self.btest.configure(state="disabled")
        self.bpause.configure(state="normal")
        self.bstop.configure(state="normal")
        self.slbl.configure(text="Đang chạy", text_color=TEAL)
        self._run_errors = []
        self.worker_thread = threading.Thread(target=self._run, daemon=True)
        self.worker_thread.start()

    def _start_scheduled(self):
        """Activate scheduler mode — wait for scheduled time then auto-run."""
        if not self.inspections:
            if self.fv.get().strip():
                self._load()
            if not self.inspections:
                self._log("Chưa có dữ liệu. Load file trước.")
                return
        self._start(scheduled=False)

    def _start(self, scheduled=False):
        self._force_scheduled_start = False
        self._schedule_slot_to_mark = ""
        if not self.inspections:
            if self.fv.get().strip():
                self._load()
            if not self.inspections:
                self._log("Start cancelled: chưa có dữ liệu")
                return
        if self.worker_thread and self.worker_thread.is_alive():
            self._log("Start ignored: automation đang chạy")
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
        self.bstart.configure(state="disabled")
        if hasattr(self, "brun_now"):
            self.brun_now.configure(state="disabled")
        if hasattr(self, "btest"):
            self.btest.configure(state="disabled")
        self.bpause.configure(state="normal")
        self.bstop.configure(state="normal")
        self.slbl.configure(text="Đang chạy", text_color=TEAL)
        self._run_errors = []
        self.worker_thread = threading.Thread(target=self._run, daemon=True)
        self.worker_thread.start()

    def _should_wait_for_schedule(self) -> bool:
        """Manual Auto Mode respects the enabled scheduler instead of running early."""
        cfg = load_schedule()
        if not cfg.get("enabled"):
            return False

        due, scheduled_time, reason = is_schedule_due_now(cfg)
        if due:
            self._log(f"Đúng giờ lịch {scheduled_time}. Bắt đầu Auto Mode.")
            self._force_scheduled_start = True
            self._schedule_slot_to_mark = scheduled_time
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
            self.slbl.configure(text=f"Chờ lịch {target.strftime('%H:%M')}", text_color=AMBER)
        else:
            self._log("Không tìm được giờ chạy tiếp theo. Kiểm tra lại lịch hẹn.")
            self.slbl.configure(text="Chờ lịch", text_color=AMBER)
        self._save_current_settings()
        return True

    def _ensure_scheduler_running(self, cfg=None):
        cfg = cfg or load_schedule()
        if not self.scheduler:
            self.scheduler = Scheduler(run_callback=self._sched_run, log_callback=self._log)
        self.scheduler.update_config(cfg)
        if cfg.get("enabled") and not self.scheduler.is_running():
            self.scheduler.start()

    def _pause(self):
        if not self.engine: return
        if self.engine._paused:
            self.engine.resume(); self.bpause.configure(text="Pause")
            self.slbl.configure(text="Đang chạy", text_color=TEAL)
        else:
            self.engine.pause(); self.bpause.configure(text="Resume")
            self.slbl.configure(text="Tạm dừng", text_color=AMBER)

    def _stop(self):
        if self.engine: self.engine.stop()
        self.slbl.configure(text="Stopping", text_color=RED)

    def _run(self):
        self.engine = AutomationEngine(log_callback=self._log)
        total = 0
        skipped_count = 0
        run_success = 0
        run_failed = 0
        try:
            self.engine.start_browser()
            self.engine.wait_for_login()

            # Health check
            self._log("Running health check...")
            hc_ok, hc_msg = self.engine.health_check()
            if not hc_ok:
                self._log(f"Health check FAILED: {hc_msg}")
                screenshot = None
                try:
                    screenshot = self.engine._screenshot_error("health_check_failed")
                except Exception:
                    screenshot = None
                send_error_alert(f"Health check failed: {hc_msg}", screenshot)
                return

            self._log("Health check OK")

            # Filter already-completed today
            auto_submit = self.av.get() and not self.rv.get()

            # Template lock: block auto-submit for untested templates (skip if manual "Chạy ngay")
            bypass_lock = getattr(self, '_bypass_template_lock', False)
            if auto_submit and not bypass_lock:
                templates = list(set(i.template_name for i in self.inspections))
                untested = get_untested_templates(templates)
                if untested:
                    self._log(f"BLOCKED: {len(untested)} untested template(s):")
                    for t in untested:
                        self._log(f"  - {t}")
                    self._log("Run in Test mode first, then retry in Auto mode.")
                    return
            self._bypass_template_lock = False  # Reset

            if auto_submit:
                remaining = get_remaining(self.inspections)
                skipped_count = len(self.inspections) - len(remaining)
                if skipped_count > 0:
                    self._log(f"Skipping {skipped_count} already completed today")
                run_list = remaining
            else:
                run_list = self.inspections

            total = len(run_list)
            if total == 0:
                self._log("All inspections already completed today")
                return

            run_success = 0
            run_failed = 0
            self._set_run_stats(total, 0, 0, 0)

            for idx, insp in enumerate(run_list):
                if self.engine._stopped: break
                if self.adv.get(): insp.inspection_date = date.today().isoformat()
                self._log(f"\n[{idx+1}/{total}] {insp.template_name} | {insp.site_location}")
                run_started = datetime.now()

                if auto_submit:
                    self._log("  Mode: AUTO - submit if no errors")
                else:
                    self._log("  Mode: TEST - fill only, no submit")

                ok = self.engine.run_inspection(insp, auto_submit=auto_submit)
                errs = []
                if ok:
                    if auto_submit:
                        verified = self.engine.verify_inspection_saved(insp.template_name)
                        if not verified:
                            self._log("  Warning: submitted but not verified in list yet")
                        mark_completed(insp.template_name, insp.site_location)
                    else:
                        # Test mode success marks the template as tested.
                        mark_template_tested(insp.template_name, len(insp.items))
                        self._log(f"  Template '{insp.template_name}' marked as tested")
                    run_success += 1
                else:
                    errs = self.engine.item_errors or [f"Failed: {insp.template_name}"]
                    self._run_errors.extend(errs)
                    run_failed += 1

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
                p = (idx+1)/total
                self.after(0, lambda v=p: self.prog.set(v))
                self.after(0, lambda i=idx: self.slbl.configure(text=f"{i+1}/{total}", text_color=GREEN))

                if self.sv.get() and idx < total-1 and not self.engine._stopped:
                    self._log("  Waiting"); self.engine.pause()
                    self.after(0, lambda: self.bpause.configure(text="Resume"))
                    self.after(0, lambda: self.slbl.configure(text="Waiting", text_color=AMBER))
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
            self.engine.close_browser()
            self.after(0, self._done)

    def _sched_run(self):
        self.after(0, self._start_scheduled_run)

    def _start_scheduled_run(self):
        if not self.inspections and self.fv.get().strip():
            self._log("Scheduled: loading saved data file")
            self._load()
        if not self.inspections:
            self._log("Scheduled: no data loaded")
            return
        self.adv.set(True); self.rv.set(False); self.av.set(True); self.sv.set(False)
        self._save_current_settings()
        self._start(scheduled=True)

    def _done(self):
        self._scheduled_run = False
        # Restore full inspection list if was test/retry run
        if hasattr(self, '_full_inspections') and self._full_inspections:
            self.inspections = self._full_inspections
            self._full_inspections = None
            self._render_inspection_list()
        if hasattr(self, 'brun_now'):
            self.brun_now.configure(state="normal")
        if hasattr(self, 'btest') and self.inspections:
            self.btest.configure(state="normal")
        self.bstart.configure(state="normal")
        self.bpause.configure(state="disabled", text="Pause")
        self.bstop.configure(state="disabled")
        if self._run_errors:
            self.slbl.configure(text=f"Lỗi: {len(self._run_errors)}", text_color=RED)
        else:
            self.slbl.configure(text="Hoàn tất", text_color=GREEN)

    def _retry_failed(self):
        """Retry only inspections that failed in the last run."""
        if not self.inspections:
            messagebox.showwarning("", "Load dữ liệu trước")
            return
        # Get today's completed to find what failed
        from runlock import get_today_completed
        completed = get_today_completed()
        failed = [i for i in self.inspections
                  if f"{i.template_name}|{i.site_location}" not in completed]
        if not failed:
            messagebox.showinfo("OK", "Không có inspection nào cần retry (tất cả đã OK)")
            return
        self._log(f"\nRETRY: {len(failed)} failed inspection(s)")
        orig = self.inspections
        self._full_inspections = list(self.inspections)
        self.inspections = failed
        self._start()

    def _save_sched(self):
        times = sorted(self._sched_times) if hasattr(self, '_sched_times') else ["05:00"]
        if not times:
            messagebox.showwarning("", "Thêm ít nhất 1 giờ chạy")
            return
        cfg = {
            "enabled": self.se.get(),
            "times": times,
            "days": [k for k, v in self.dvs.items() if v.get()],
            "auto_date_today": True,
            "runs_today": load_schedule().get("runs_today", []),
        }
        save_schedule(cfg)
        if cfg["enabled"]:
            if not self.scheduler:
                self.scheduler = Scheduler(run_callback=self._sched_run, log_callback=self._log)
            self.scheduler.update_config(cfg)
            self.scheduler.start()
            times_str = ", ".join(times)
            messagebox.showinfo("OK", f"Lịch: [{times_str}] hằng ngày")
        else:
            if self.scheduler:
                self.scheduler.stop()
            messagebox.showinfo("OK", "Tắt lịch hẹn")
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

    def _export_history(self):
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")])
        if p:
            if export_csv(p): messagebox.showinfo("OK", f"Exported: {p}")
            else: messagebox.showerror("Error", "Export failed")

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
            messagebox.showinfo("OK","Saved"); self.scp.delete(0,"end")

    def _del_sc(self):
        if messagebox.askyesno("","Xóa credentials?"): clear_sc_login(); self._pg_settings()

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
            messagebox.showerror("Error", msg)

    def _save_tg(self):
        chat_ids = [
            value.strip()
            for value in self.tg_chat.get().replace("\n", ",").replace(";", ",").split(",")
            if value.strip()
        ]
        cfg = {
            "bot_token": self.tg_token.get().strip(),
            "chat_ids": chat_ids,
            "enabled": self.tg_enabled.get(),
        }
        save_telegram_config(cfg)
        messagebox.showinfo("OK", f"Telegram config saved ({len(chat_ids)} chat)")

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
            messagebox.showerror("Error", f"Lỗi: {e}")

    def _test_tg(self):
        self._save_tg()
        ok, msg = test_telegram()
        if ok:
            messagebox.showinfo("OK", msg)
        else:
            messagebox.showerror("Error", msg)

    def _logout(self):
        logout(); self.current_user = None; self._login()

    def _startup_update_check(self):
        """Silent update check on app startup."""
        from update_dialog import check_and_show_update
        check_and_show_update(self, force=False, silent=True)

    # â”€â”€ Helpers â”€â”€
    def _card(self, title=None):
        c = ctk.CTkFrame(self.pg, corner_radius=8, fg_color=CARD, border_width=1, border_color=BORDER)
        c.pack(fill="x", pady=(0,6))
        if title:
            ctk.CTkLabel(c, text=title, font=ctk.CTkFont(family=F, size=11, weight="bold"),
                         text_color=TXT).pack(anchor="w", padx=12, pady=(8,4))
        return c

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        def d():
            if hasattr(self,'logbox') and self.logbox.winfo_exists():
                self.logbox.configure(state="normal")
                self.logbox.insert("end", line+"\n")
                self.logbox.see("end")
                self.logbox.configure(state="disabled")
        self.after(0, d)

    def _clog(self):
        self.logbox.configure(state="normal"); self.logbox.delete("1.0","end"); self.logbox.configure(state="disabled")

    def _wipe(self):
        for w in self.winfo_children(): w.destroy()

    def _cls(self):
        if hasattr(self,'pg'):
            for w in self.pg.winfo_children(): w.destroy()


def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()

