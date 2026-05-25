"""System tray icon for CheckPilot background mode."""
import os
import threading
from typing import Callable

from PIL import Image
import pystray
from pystray import MenuItem, Icon
from config import BASE_DIR

ICON_PATH = os.path.join(BASE_DIR, "assets", "icon.png")


class TrayIcon:
    """Manages system tray icon with menu."""

    def __init__(self, on_show: Callable, on_quit: Callable):
        self.on_show = on_show
        self.on_quit = on_quit
        self.icon: Icon = None
        self._thread: threading.Thread = None

    def show(self):
        """Show tray icon."""
        image = Image.open(ICON_PATH) if os.path.exists(ICON_PATH) else self._default_icon()

        menu = pystray.Menu(
            MenuItem("Mở CheckPilot", self._on_show, default=True),
            MenuItem("─────────────", None, enabled=False),
            MenuItem("Thoát hoàn toàn", self._on_quit),
        )

        self.icon = Icon(
            name="CheckPilot",
            icon=image,
            title="CheckPilot - Đang chạy nền",
            menu=menu,
        )

        self._thread = threading.Thread(target=self.icon.run, daemon=True)
        self._thread.start()

    def hide(self):
        """Remove tray icon."""
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass

    def _on_show(self, icon=None, item=None):
        """Restore main window."""
        self.on_show()

    def _on_quit(self, icon=None, item=None):
        """Quit app entirely."""
        self.hide()
        self.on_quit()

    def _default_icon(self) -> Image.Image:
        """Fallback icon if PNG not found."""
        img = Image.new("RGBA", (64, 64), (13, 110, 253, 255))
        return img
