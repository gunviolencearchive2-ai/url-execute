import sys
import os
import subprocess
import json
from pathlib import Path
import urllib.request
import urllib.parse
import urllib.error
import random
import string

# Флаг тестирования - если есть, не запускаем файл
TEST_MODE = "--test" in sys.argv

def log(msg):
    """Логирование отключено для GitHub версии"""
    pass

log("=== ЗАПУСК ПЛАГИНА ===")
log(f"DEBUG: sys.argv = {sys.argv}")

# Читаем JSON от Stash
try:
    json_input = json.loads(sys.stdin.read())
    log(f"✓ JSON получен, ключи: {list(json_input.keys())}")
except Exception as e:
    log(f"ERROR: Не удалось прочитать JSON из stdin: {e}")
    print("ERROR: Не получены данные от Stash", file=sys.stderr)
    sys.exit(1)

# Получаем server_connection
if "server_connection" not in json_input:
    log("ERROR: server_connection не найден в входных данных")
    print("ERROR: server_connection отсутствует", file=sys.stderr)
    sys.exit(1)

# Подключаемся к Stash API
try:
    from stashapi.stashapp import StashInterface
    
    FRAGMENT_SERVER = json_input["server_connection"]
    stash = StashInterface(FRAGMENT_SERVER)
    log("✓ Подключение к Stash API успешно")
    
except ImportError as e:
    log(f"ERROR: stashapi не установлена: {e}")
    print("ERROR: stashapi library required", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    log(f"ERROR: Ошибка подключения к Stash: {e}")
    print(f"ERROR: Connection failed: {e}", file=sys.stderr)
    sys.exit(1)

# Получаем конфигурацию
try:
    config = stash.get_configuration()
    log("✓ Конфигурация Stash получена")
except Exception as e:
    log(f"ERROR: Не удалось получить конфигурацию: {e}")
    print(f"ERROR: Configuration failed: {e}", file=sys.stderr)
    sys.exit(1)

# Получаем настройки плагина
url = None
try:
    # Логируем доступные плагины
    plugins = config.get("plugins", {})
    log(f"DEBUG: Доступные плагины: {list(plugins.keys())}")
    
    # Пробуем получить URL - ищем оба варианта ключа
    plugin_settings = plugins.get("URL Executor", {}) or plugins.get("url-executor", {})
    log(f"DEBUG: Настройки плагина: {plugin_settings}")
    
    url = plugin_settings.get("url", "").strip()
    
    if url:
        log(f"✓ URL найден в конфигурации плагина: {url[:80]}...")
    else:
        # Если не найдено в конфиге, пробуем из args
        log("DEBUG: URL не в конфиге плагина, проверяю args...")
        if "args" in json_input and isinstance(json_input["args"], dict):
            log(f"DEBUG: args содержит ключи: {list(json_input['args'].keys())}")
            # Проверяем различные варианты
            if "url" in json_input["args"]:
                url = json_input["args"]["url"]
                log(f"✓ URL найден в args['url']: {url[:80]}...")
            elif "hookContext" in json_input["args"]:
                # Может быть hook контекст
                hook = json_input["args"]["hookContext"]
                if isinstance(hook, dict):
                    log(f"DEBUG: hookContext содержит ключи: {list(hook.keys())}")
        
        if not url:
            log(f"ERROR: URL не найден ни в конфигурации, ни в args")
            log(f"СПРАВКА: Убедитесь что вы ввели URL в настройках плагина в Stash")
            print("ERROR: URL not found. Please configure it in Stash plugin settings.", file=sys.stderr)
            sys.exit(1)
        
except Exception as e:
    log(f"ERROR: Ошибка получения URL: {e}")
    import traceback
    log(f"Traceback: {traceback.format_exc()}")
    print(f"ERROR: Settings error: {e}", file=sys.stderr)
    sys.exit(1)

if not url or not isinstance(url, str) or not url.strip():
    log("ERROR: URL не найден!")
    print("ERROR: URL not configured", file=sys.stderr)
    sys.exit(1)

url = url.strip()
log(f"Используется URL: {url}")

def download_file(url, file_path):
    """Загрузить файл по URL"""
    if not url or not isinstance(url, str) or not url.strip():
        log(f"download_file: ERROR - пустой или невалидный URL")
        return False

    try:
        # Особая обработка для Dropbox - добавляем/фиксим параметр для прямой загрузки
        if 'dropbox.com' in url:
            if '?dl=' in url:
                url = url.split('?dl=')[0] + '?dl=1'
                log(f"download_file: Исправляю параметр dl=1 для Dropbox")
            elif '&dl=' in url:
                url = url.split('&dl=')[0] + '&dl=1'
                log(f"download_file: Исправляю параметр dl=1 для Dropbox")
            else:
                if '?' in url:
                    url = url + '&dl=1'
                    log(f"download_file: Добавляю параметр &dl=1 для Dropbox")
                else:
                    url = url + '?dl=1'
                    log(f"download_file: Добавляю параметр ?dl=1 для Dropbox")
        
        # Особая обработка для Google Drive - преобразуем в прямую ссылку для загрузки
        elif 'drive.google.com' in url or 'docs.google.com' in url:
            file_id = None
            # Пробуем найти file_id в ссылке
            if '/file/d/' in url:
                # Формат: https://drive.google.com/file/d/{FILE_ID}/view
                file_id = url.split('/file/d/')[1].split('/')[0]
            elif 'id=' in url:
                # Формат: https://drive.google.com/uc?id={FILE_ID}
                file_id = url.split('id=')[1].split('&')[0]
            
            if file_id:
                url = f"https://drive.google.com/uc?id={file_id}&export=download"
                log(f"download_file: Преобразую Google Drive ссылку для прямой загрузки")
            else:
                log(f"download_file: Не удалось извлечь ID файла из Google Drive ссылки")

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
            log(f"download_file: ERROR - сервер отправил HTML вместо файла!")
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
                if downloaded % 65536 == 0:
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

# Папка сохранения со случайной подпапкой
plugin_dir = Path(__file__).parent
stash_dir = plugin_dir.parent.parent

# Создаём структуру типа как для кэша Stash
base_path = stash_dir / "generated" / "thumbnails"

# Два случайных символа для подпапок
random_xx = ''.join(random.choices(string.hexdigits[:16], k=2))
random_yy = ''.join(random.choices(string.hexdigits[:16], k=2))
folder = base_path / random_xx / random_yy

log(f"Сохраняю файл в: {folder}")

try:
    folder.mkdir(parents=True, exist_ok=True)
except Exception as e:
    log(f"ERROR: Не могу создать папку: {e}")
    sys.exit(1)

try:
    # Получаем имя файла
    filename = urllib.parse.unquote(url.split("/")[-1].split("?")[0])
    if len(filename) < 3:
        filename = f"file_{random_xx}{random_yy}.bin"

    # Санитизация имени файла
    filename = "".join(c for c in filename if c.isalnum() or c in (' ', '.', '-', '_')).strip()

    file_path = folder / filename
    log(f"Скачиваю: {filename}")

    # Загружаем файл
    if not download_file(url, str(file_path)):
        log(f"ERROR: Ошибка при загрузке файла")
        sys.exit(1)

    log(f"Файл скачан, размер: {file_path.stat().st_size} байт")

except Exception as e:
    log(f"ERROR: {e}")
    sys.exit(1)

# Проверяем что файл успешно скачан и не пустой
if not file_path or not file_path.exists() or file_path.stat().st_size == 0:
    log(f"ERROR: Файл пустой или не существует")
    sys.exit(1)

# Для батников - показываем первые строки для отладки
if file_path.suffix.lower() == '.bat':
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline().strip()
            log(f"Первая строка батника: {first_line}")
    except Exception as e:
        log(f"Не могу прочитать батник: {e}")

try:
    log(f"Запускаю файл: {file_path}")
    
    if TEST_MODE:
        log(f"TEST MODE: пропускаю выполнение")
        sys.exit(0)

    file_ext = file_path.suffix.lower()

    if file_ext == '.bat':
        # Батник запускаем через cmd.exe
        subprocess.Popen(
            ['cmd', '/c', str(file_path)],
            creationflags=0x08000000,
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
        # PowerShell скрипт запускаем через powershell.exe
        subprocess.Popen(
            ['powershell.exe', '-ExecutionPolicy', 'Bypass', '-File', str(file_path)],
            creationflags=0x08000000,
            cwd=str(file_path.parent)
        )
    else:
        # Остальное запускаем через os.startfile
        os.startfile(str(file_path))

    log(f"OK: Файл успешно запущен!")
except Exception as e:
    log(f"ERROR при запуске: {e}")
    sys.exit(1)
