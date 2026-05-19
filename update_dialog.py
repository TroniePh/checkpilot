"""
Update dialog for CheckPilot.
Shows update notification with changelog, download progress, and install button.
"""
import sys
import logging
import threading
import customtkinter as ctk
from typing import Optional

from updater import (
    get_current_version, check_for_update,
    download_and_install, install_update, cleanup_old_updates,
)

logger = logging.getLogger(__name__)

# Palette (match gui.py)
BG = "#F7F9FC"
CARD = "#FFFFFF"
BORDER = "#D7DEE8"
TXT = "#172033"
DIM = "#44546A"
MUTED = "#7A8699"
TEAL = "#0F766E"
TEAL_H = "#0B5F59"
GREEN = "#15803D"
RED = "#B91C1C"
F = "Segoe UI"


class UpdateDialog(ctk.CTkToplevel):
    """Modal dialog showing update available with download + install."""

    def __init__(self, parent, latest_version: str, download_url: str, changelog: str = ""):
        super().__init__(parent)
        self.title("Cập nhật CheckPilot")
        self.geometry("480x380")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.transient(parent)
        self.grab_set()

        self._parent = parent
        self._download_url = download_url
        self._installer_path: Optional[str] = None
        self._downloading = False

        # Center on parent
        self.after(50, self._center)

        # ── Header ──
        ctk.CTkLabel(
            self, text="🔄  Có bản cập nhật mới!",
            font=ctk.CTkFont(family=F, size=16, weight="bold"),
            text_color=TEAL,
        ).pack(pady=(20, 5))

        # Version info
        ver_frame = ctk.CTkFrame(self, fg_color="transparent")
        ver_frame.pack(pady=(0, 10))
        ctk.CTkLabel(
            ver_frame,
            text=f"Phiên bản hiện tại:  {get_current_version()}",
            font=ctk.CTkFont(family=F, size=11),
            text_color=MUTED,
        ).pack()
        ctk.CTkLabel(
            ver_frame,
            text=f"Phiên bản mới:  {latest_version}",
            font=ctk.CTkFont(family=F, size=12, weight="bold"),
            text_color=GREEN,
        ).pack()

        # ── Changelog ──
        if changelog:
            cl_frame = ctk.CTkFrame(self, corner_radius=8, fg_color=CARD,
                                     border_width=1, border_color=BORDER)
            cl_frame.pack(fill="x", padx=24, pady=(0, 10))
            ctk.CTkLabel(
                cl_frame, text="Thay đổi:", anchor="w",
                font=ctk.CTkFont(family=F, size=10, weight="bold"),
                text_color=DIM,
            ).pack(anchor="w", padx=10, pady=(8, 2))
            cl_text = ctk.CTkTextbox(
                cl_frame, height=80, font=ctk.CTkFont(family=F, size=10),
                fg_color=BG, text_color=DIM, corner_radius=4, border_width=0,
            )
            cl_text.pack(fill="x", padx=10, pady=(0, 8))
            cl_text.insert("1.0", changelog)
            cl_text.configure(state="disabled")

        # ── Progress bar (hidden initially) ──
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.pack(fill="x", padx=24, pady=(0, 5))

        self.progress_label = ctk.CTkLabel(
            self.progress_frame, text="",
            font=ctk.CTkFont(family=F, size=10), text_color=DIM,
        )
        self.progress_label.pack(anchor="w")

        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame, height=6, corner_radius=3,
            progress_color=TEAL, fg_color=BORDER,
        )
        self.progress_bar.pack(fill="x", pady=(2, 0))
        self.progress_bar.set(0)

        # Hide progress initially
        self.progress_frame.pack_forget()

        # ── Buttons ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(10, 20))

        self.btn_update = ctk.CTkButton(
            btn_frame, text="Cập nhật ngay", width=140, height=36,
            corner_radius=7, fg_color=TEAL, hover_color=TEAL_H,
            font=ctk.CTkFont(family=F, size=12, weight="bold"),
            command=self._start_download,
        )
        self.btn_update.pack(side="left", padx=(0, 10))

        self.btn_later = ctk.CTkButton(
            btn_frame, text="Để sau", width=100, height=36,
            corner_radius=7, fg_color="transparent", hover_color="#EEF2F7",
            border_width=1, border_color=BORDER, text_color=DIM,
            font=ctk.CTkFont(family=F, size=11),
            command=self._dismiss,
        )
        self.btn_later.pack(side="left")

        # Install button (hidden until download complete)
        self.btn_install = ctk.CTkButton(
            btn_frame, text="Cài đặt & Khởi động lại", width=180, height=36,
            corner_radius=7, fg_color=GREEN, hover_color="#16A34A",
            font=ctk.CTkFont(family=F, size=12, weight="bold"),
            command=self._do_install,
        )

        self.protocol("WM_DELETE_WINDOW", self._dismiss)

    def _center(self):
        self.update_idletasks()
        pw = self._parent.winfo_x() + self._parent.winfo_width() // 2
        ph = self._parent.winfo_y() + self._parent.winfo_height() // 2
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{pw - w // 2}+{ph - h // 2}")

    def _start_download(self):
        if self._downloading:
            return
        self._downloading = True

        # Show progress, disable buttons
        self.progress_frame.pack(fill="x", padx=24, pady=(0, 5))
        self.btn_update.configure(state="disabled", text="Đang tải...")
        self.btn_later.configure(state="disabled")

        # Start background download
        download_and_install(
            url=self._download_url,
            progress_callback=self._on_progress,
            done_callback=self._on_download_done,
        )

    def _on_progress(self, progress: float, status: str):
        """Called from background thread — schedule UI update."""
        self.after(0, lambda: self._update_progress(progress, status))

    def _update_progress(self, progress: float, status: str):
        if not self.winfo_exists():
            return
        self.progress_bar.set(progress)
        self.progress_label.configure(text=status)

    def _on_download_done(self, success: bool, result: str):
        """Called from background thread when download finishes."""
        self.after(0, lambda: self._handle_download_result(success, result))

    def _handle_download_result(self, success: bool, result: str):
        if not self.winfo_exists():
            return

        if success:
            self._installer_path = result
            self.progress_label.configure(text="✓ Tải xong! Nhấn để cài đặt.", text_color=GREEN)
            self.progress_bar.set(1.0)

            # Swap buttons
            self.btn_update.pack_forget()
            self.btn_later.pack_forget()
            self.btn_install.pack(side="left", padx=(0, 10))

            # Re-show "later" button
            self.btn_later.configure(state="normal")
            self.btn_later.pack(side="left")
        else:
            self.progress_label.configure(text=f"✗ Lỗi: {result}", text_color=RED)
            self.btn_update.configure(state="normal", text="Thử lại")
            self.btn_later.configure(state="normal")
            self._downloading = False

    def _do_install(self):
        """Launch installer and quit app."""
        if self._installer_path:
            self.progress_label.configure(text="Đang khởi chạy trình cài đặt...")
            self.btn_install.configure(state="disabled")
            self.btn_later.configure(state="disabled")

            success = install_update(self._installer_path)
            if success:
                # Give installer a moment to start, then quit
                self.after(1000, self._quit_app)
            else:
                self.progress_label.configure(
                    text="✗ Không thể chạy installer. Thử cài thủ công.",
                    text_color=RED,
                )
                self.btn_later.configure(state="normal")

    def _quit_app(self):
        """Quit the application so installer can replace files."""
        try:
            self._parent.destroy()
        except:
            pass
        sys.exit(0)

    def _dismiss(self):
        if self._downloading:
            # Don't close while downloading — just minimize
            return
        self.grab_release()
        self.destroy()


def check_and_show_update(parent, force: bool = False, silent: bool = True):
    """
    Check for updates and show dialog if available.
    Supports both full updates (installer) and patch updates (individual files).
    Call this on app startup (silent=True won't show "no update" message).
    Call from button click with force=True, silent=False.
    """
    def _check():
        import requests
        from updater import VERSION_CHECK_URL, CURRENT_VERSION, _version_newer, _checked_recently, _save_check_time

        if not force and _checked_recently():
            return

        try:
            resp = requests.get(VERSION_CHECK_URL, timeout=10)
            if resp.status_code != 200:
                return
            data = resp.json()
            _save_check_time()

            latest = data.get("version", CURRENT_VERSION)
            if not _version_newer(latest, CURRENT_VERSION):
                if not silent:
                    from tkinter import messagebox
                    parent.after(0, lambda: messagebox.showinfo(
                        "Cập nhật",
                        f"Bạn đang dùng phiên bản mới nhất ({get_current_version()})"
                    ))
                return

            update_type = data.get("update_type", "full")
            changelog = data.get("changelog", "")
            download_url = data.get("download_url", "")

            if update_type == "patch" and data.get("patches"):
                # Patch mode: show patch dialog
                parent.after(0, lambda: PatchDialog(parent, latest, data.get("patches", []), changelog))
            elif download_url:
                # Full update mode
                parent.after(0, lambda: UpdateDialog(parent, latest, download_url, changelog))

        except Exception as e:
            logger.debug(f"Update check error: {e}")

    # Run check in background to not block UI startup
    thread = threading.Thread(target=_check, daemon=True)
    thread.start()

    # Also cleanup old downloads
    threading.Thread(target=cleanup_old_updates, daemon=True).start()


class PatchDialog(ctk.CTkToplevel):
    """Dialog for applying patch updates (small file replacements)."""

    def __init__(self, parent, latest_version: str, patches: list, changelog: str = ""):
        super().__init__(parent)
        self.title("Bản vá CheckPilot")
        self.geometry("450x320")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.transient(parent)
        self.grab_set()

        self._parent = parent
        self._patches = patches
        self._patching = False

        self.after(50, self._center)

        # Header
        ctk.CTkLabel(
            self, text="Có bản vá mới (hotfix)",
            font=ctk.CTkFont(family=F, size=15, weight="bold"),
            text_color=TEAL,
        ).pack(pady=(20, 5))

        ctk.CTkLabel(
            self, text=f"v{get_current_version()} → v{latest_version}",
            font=ctk.CTkFont(family=F, size=11),
            text_color=GREEN,
        ).pack(pady=(0, 5))

        # Patch info
        info_frame = ctk.CTkFrame(self, fg_color=CARD, corner_radius=8,
                                   border_width=1, border_color=BORDER)
        info_frame.pack(fill="x", padx=24, pady=(5, 8))

        file_list = ", ".join([p.get("file", "?") for p in patches[:5]])
        if len(patches) > 5:
            file_list += f" (+{len(patches)-5} file khác)"

        ctk.CTkLabel(info_frame, text=f"File cập nhật: {file_list}",
                     font=ctk.CTkFont(family=F, size=10), text_color=DIM,
                     wraplength=380).pack(padx=10, pady=(8, 2), anchor="w")
        ctk.CTkLabel(info_frame, text="Không cần tải lại toàn bộ phần mềm.",
                     font=ctk.CTkFont(family=F, size=9), text_color=MUTED).pack(padx=10, pady=(0, 8), anchor="w")

        if changelog:
            ctk.CTkLabel(info_frame, text=f"Thay đổi: {changelog}",
                         font=ctk.CTkFont(family=F, size=9), text_color=DIM,
                         wraplength=380).pack(padx=10, pady=(0, 8), anchor="w")

        # Progress
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.pack(fill="x", padx=24, pady=(0, 5))
        self.progress_label = ctk.CTkLabel(self.progress_frame, text="",
                                            font=ctk.CTkFont(family=F, size=10), text_color=DIM)
        self.progress_label.pack(anchor="w")
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, height=5,
                                                progress_color=TEAL, fg_color=BORDER)
        self.progress_bar.pack(fill="x", pady=(2, 0))
        self.progress_bar.set(0)
        self.progress_frame.pack_forget()

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(10, 20))

        self.btn_patch = ctk.CTkButton(
            btn_frame, text="Cập nhật ngay", width=130, height=34,
            corner_radius=7, fg_color=TEAL, hover_color=TEAL_H,
            font=ctk.CTkFont(family=F, size=11, weight="bold"),
            command=self._start_patch,
        )
        self.btn_patch.pack(side="left", padx=(0, 8))

        self.btn_later = ctk.CTkButton(
            btn_frame, text="Để sau", width=80, height=34,
            corner_radius=7, fg_color="transparent", hover_color="#EEF2F7",
            border_width=1, border_color=BORDER, text_color=DIM,
            font=ctk.CTkFont(family=F, size=11),
            command=self._dismiss,
        )
        self.btn_later.pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self._dismiss)

    def _center(self):
        self.update_idletasks()
        pw = self._parent.winfo_x() + self._parent.winfo_width() // 2
        ph = self._parent.winfo_y() + self._parent.winfo_height() // 2
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{pw - w // 2}+{ph - h // 2}")

    def _start_patch(self):
        if self._patching:
            return
        self._patching = True
        self.progress_frame.pack(fill="x", padx=24, pady=(0, 5))
        self.btn_patch.configure(state="disabled", text="Đang vá...")
        self.btn_later.configure(state="disabled")

        from patcher import apply_patches_and_restart
        apply_patches_and_restart(
            self._patches,
            progress_callback=self._on_progress,
            done_callback=self._on_done,
        )

    def _on_progress(self, progress: float, status: str):
        self.after(0, lambda: self._update_ui(progress, status))

    def _update_ui(self, progress: float, status: str):
        if not self.winfo_exists():
            return
        self.progress_bar.set(progress)
        self.progress_label.configure(text=status)

    def _on_done(self, success: bool, message: str):
        self.after(0, lambda: self._handle_done(success, message))

    def _handle_done(self, success: bool, message: str):
        if not self.winfo_exists():
            return

        if success:
            self.progress_label.configure(text=f"✓ {message}", text_color=GREEN)
            self.progress_bar.set(1.0)
            self.btn_patch.configure(text="Khởi động lại", state="normal",
                                     command=self._restart)
            self.btn_later.configure(state="normal")
        else:
            self.progress_label.configure(text=f"✗ {message}", text_color=RED)
            self.btn_patch.configure(state="normal", text="Thử lại")
            self.btn_later.configure(state="normal")
            self._patching = False

    def _restart(self):
        from patcher import restart_app
        restart_app()
        self.after(500, lambda: sys.exit(0))

    def _dismiss(self):
        if self._patching:
            return
        self.grab_release()
        self.destroy()
