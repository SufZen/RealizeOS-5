"""
RealizeOS Desktop Launcher — double-click to start.

Starts the server in the background, waits for it to be ready,
then opens the dashboard in your default browser.
No terminal window is shown (.pyw = windowless on Windows).
"""
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

# Configuration
HOST = "127.0.0.1"
PORT = int(os.environ.get("REALIZE_PORT", "8080"))
URL = f"http://{HOST}:{PORT}"
HEALTH_URL = f"{URL}/health"
MAX_WAIT_SECONDS = 30

# Resolve project root (same directory as this script)
PROJECT_ROOT = Path(__file__).parent.resolve()
os.chdir(str(PROJECT_ROOT))

# Log file for errors
LOG_DIR = PROJECT_ROOT / "data"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "launcher.log"


def get_python_exe():
    """
    Get the path to python.exe (not pythonw.exe).

    When this script runs as .pyw, sys.executable is pythonw.exe.
    Uvicorn needs python.exe to function correctly.
    """
    exe = sys.executable
    if not exe:
        return "python"

    exe_path = Path(exe)

    # If running as pythonw, swap to python
    if exe_path.stem.lower() == "pythonw":
        python_exe = exe_path.parent / exe_path.name.replace("pythonw", "python")
        if python_exe.exists():
            return str(python_exe)

    return exe


def log(msg):
    """Append a timestamped message to the launcher log."""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


def show_error(title, message):
    """Show an error message box."""
    log(f"ERROR: {message}")
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        pass


def is_port_in_use():
    """Check if the port is already in use."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((HOST, PORT)) == 0


def wait_for_server(timeout=MAX_WAIT_SECONDS):
    """Poll the health endpoint until the server is ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = urlopen(HEALTH_URL, timeout=2)
            if resp.status == 200:
                return True
        except (URLError, OSError):
            pass
        time.sleep(0.5)
    return False


def main():
    log("Launcher starting...")

    # Check if server is already running
    if is_port_in_use():
        log(f"Port {PORT} already in use — opening browser")
        webbrowser.open(URL)
        return

    # Find Python executable (python.exe, not pythonw.exe)
    python = get_python_exe()
    log(f"Using Python: {python}")

    # Start uvicorn server
    env = os.environ.copy()
    env["REALIZE_HOST"] = HOST
    env["REALIZE_PORT"] = str(PORT)

    # Log stderr to file for debugging
    log_handle = open(LOG_FILE, "a", encoding="utf-8")

    cmd = [python, "-m", "uvicorn", "realize_api.main:app",
           "--host", HOST, "--port", str(PORT), "--log-level", "info"]

    # Hide subprocess console window on Windows
    creation_flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW

    try:
        server_process = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=log_handle,
            stderr=log_handle,
            creationflags=creation_flags,
        )
    except Exception as e:
        show_error("RealizeOS", f"Failed to start server:\n{e}")
        log_handle.close()
        return

    log(f"Server process started (PID {server_process.pid})")

    # Wait for server to be ready
    if not wait_for_server():
        show_error(
            "RealizeOS",
            f"Server did not start within {MAX_WAIT_SECONDS}s.\n\n"
            f"Check data/launcher.log for details.\n"
            f"Make sure dependencies are installed:\n"
            f"  pip install -r requirements.txt"
        )
        server_process.terminate()
        log_handle.close()
        return

    log("Server ready — opening browser")
    webbrowser.open(URL)

    # Keep running until the server process exits
    try:
        server_process.wait()
    except KeyboardInterrupt:
        server_process.terminate()
        server_process.wait(timeout=5)
    finally:
        log("Launcher exiting")
        log_handle.close()


if __name__ == "__main__":
    main()
