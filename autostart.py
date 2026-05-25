"""
Auto-start configuration for CheckPilot.
- Saves last used data file + image folder
- Auto-loads on startup
- Registers app to run on Windows startup (optional)
- Registers a headless Task Scheduler runner for boot/pre-login operation
"""
import os
import sys
import json
import logging
import subprocess
import tempfile
from datetime import datetime
from html import escape
from config import DATA_DIR

logger = logging.getLogger(__name__)
AUTOSTART_CONFIG = os.path.join(DATA_DIR, "autostart.json")
PRELOGIN_TASK_NAME = "CheckPilotPreLoginRunner"

DEFAULT_AUTOSTART_CONFIG = {
    "last_data_file": "",
    "last_image_folder": "",
    "auto_load_on_start": True,
    "run_on_windows_startup": False,
    "prelogin_task_enabled": False,
    "template_folder_name": "Yummi Sushi - Daily Required Checklists",
    "template_folder_url": "",
    "validation_state": {},
}


def save_last_config(data_file: str, image_folder: str):
    """Save last used file paths for auto-reload."""
    os.makedirs(DATA_DIR, exist_ok=True)
    cfg = load_autostart_config()
    cfg["last_data_file"] = data_file
    cfg["last_image_folder"] = image_folder
    with open(AUTOSTART_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def load_autostart_config() -> dict:
    """Load auto-start config."""
    cfg = dict(DEFAULT_AUTOSTART_CONFIG)
    if os.path.exists(AUTOSTART_CONFIG):
        try:
            with open(AUTOSTART_CONFIG, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update(data)
        except Exception as e:
            logger.warning("Failed to load autostart config: %s", e)
    return cfg


def save_autostart_config(cfg: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(AUTOSTART_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_last_data_file() -> str:
    return load_autostart_config().get("last_data_file", "")


def get_last_image_folder() -> str:
    return load_autostart_config().get("last_image_folder", "")


def _norm_path(path: str) -> str:
    if not path:
        return ""
    try:
        return os.path.normcase(os.path.abspath(path))
    except Exception:
        return path


def file_fingerprint(file_path: str) -> dict:
    """Return stable file identity data used by validation state."""
    try:
        stat = os.stat(file_path)
        return {
            "file": file_path,
            "file_norm": _norm_path(file_path),
            "file_size": stat.st_size,
            "file_mtime": stat.st_mtime,
        }
    except OSError:
        return {
            "file": file_path,
            "file_norm": _norm_path(file_path),
            "file_size": None,
            "file_mtime": None,
        }


def build_validation_state(
    file_path: str,
    image_folder: str,
    ok: bool,
    missing_images: int = 0,
    missing_accepted: bool = False,
) -> dict:
    state = file_fingerprint(file_path)
    state.update({
        "image_folder": image_folder,
        "image_folder_norm": _norm_path(image_folder),
        "ok": bool(ok),
        "missing_images": int(missing_images or 0),
        "missing_accepted": bool(missing_accepted),
        "validated_at": datetime.now().isoformat(),
    })
    return state


def save_validation_state(state: dict):
    cfg = load_autostart_config()
    cfg["validation_state"] = state or {}
    save_autostart_config(cfg)


def get_validation_state() -> dict:
    state = load_autostart_config().get("validation_state", {})
    return state if isinstance(state, dict) else {}


def is_validation_current(file_path: str, image_folder: str, state: dict = None) -> bool:
    state = state if state is not None else get_validation_state()
    if not state or not state.get("ok"):
        return False
    current = file_fingerprint(file_path)
    if state.get("file_norm") != current.get("file_norm"):
        return False
    if state.get("image_folder_norm") != _norm_path(image_folder):
        return False
    if state.get("file_size") != current.get("file_size"):
        return False
    if state.get("file_mtime") != current.get("file_mtime"):
        return False
    if state.get("missing_images", 0) and not state.get("missing_accepted"):
        return False
    return True


def register_windows_startup(enable: bool = True):
    """Add/remove app from Windows startup registry."""
    if sys.platform != "win32":
        return

    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "CheckPilot"

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enable:
            # Get the path to run
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
            python = sys.executable
            cmd = f'"{python}" "{script}"'
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            logger.info("Registered for Windows startup")
        else:
            try:
                winreg.DeleteValue(key, app_name)
                logger.info("Removed from Windows startup")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        logger.warning(f"Startup registry error: {e}")


def is_registered_startup() -> bool:
    """Check if app is in Windows startup."""
    if sys.platform != "win32":
        return False
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, "CheckPilot")
        winreg.CloseKey(key)
        return True
    except:
        return False


def _project_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _runner_command_parts() -> tuple:
    """
    Return (command, arguments, cwd) for the headless runner.
    Frozen builds call the executable with --runner; source builds call main.py.
    """
    cwd = _project_dir()
    if getattr(sys, "frozen", False):
        return sys.executable, "--runner --watch", cwd
    main_py = os.path.join(cwd, "main.py")
    return sys.executable, f'"{main_py}" --runner --watch', cwd


def runner_command_display() -> str:
    cmd, args, _ = _runner_command_parts()
    return f'"{cmd}" {args}'.strip()


def _current_user() -> str:
    try:
        completed = subprocess.run(
            ["whoami"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        user = completed.stdout.strip()
        if user:
            return user
    except Exception:
        pass
    return os.environ.get("USERNAME", "")


def _prelogin_task_xml(command: str, arguments: str, cwd: str) -> str:
    user = _current_user()
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>CheckPilot headless runner. Starts at Windows boot and waits for the configured inspection schedule.</Description>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
      <Delay>PT30S</Delay>
    </BootTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{escape(user)}</UserId>
      <LogonType>S4U</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT5M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(command)}</Command>
      <Arguments>{escape(arguments)}</Arguments>
      <WorkingDirectory>{escape(cwd)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def register_prelogin_task(enable: bool = True) -> tuple:
    """
    Create/remove a Windows Task Scheduler boot runner.

    This is intentionally headless. Windows cannot show or drive a desktop GUI
    before an interactive user session exists.
    """
    if sys.platform != "win32":
        return False, "Task Scheduler chỉ hỗ trợ trên Windows."

    try:
        if not enable:
            subprocess.run(
                ["schtasks", "/Delete", "/TN", PRELOGIN_TASK_NAME, "/F"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            cfg = load_autostart_config()
            cfg["prelogin_task_enabled"] = False
            save_autostart_config(cfg)
            return True, "Đã tắt runner trước login."

        command, arguments, cwd = _runner_command_parts()
        xml = _prelogin_task_xml(command, arguments, cwd)
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".xml", encoding="utf-16") as f:
            f.write(xml)
            xml_path = f.name

        try:
            completed = subprocess.run(
                ["schtasks", "/Create", "/TN", PRELOGIN_TASK_NAME, "/XML", xml_path, "/F"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        finally:
            try:
                os.remove(xml_path)
            except OSError:
                pass

        if completed.returncode != 0:
            msg = (completed.stderr or completed.stdout or "").strip()
            return False, msg or "Không tạo được Task Scheduler runner."

        cfg = load_autostart_config()
        cfg["prelogin_task_enabled"] = True
        save_autostart_config(cfg)
        return True, "Đã bật runner trước login bằng Windows Task Scheduler."
    except Exception as e:
        return False, str(e)


def is_prelogin_task_registered() -> bool:
    if sys.platform != "win32":
        return False
    try:
        completed = subprocess.run(
            ["schtasks", "/Query", "/TN", PRELOGIN_TASK_NAME],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return completed.returncode == 0
    except Exception:
        return False
