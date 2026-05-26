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
    # Временно включаем логирование для отладки
    try:
        log_file = Path(__file__).parent / "executor_debug.log"
        with open(log_file, 'a', encoding='utf-8') as f:
            timestamp = __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            f.write(f"[{timestamp}] {msg}\n")
            f.flush()
    except:
        pass

log("=== ЗАПУСК ПЛАГИНА ===")
log(f"DEBUG: sys.argv = {sys.argv}")

# Читаем JSON от Stash
try:
    json_input = json.loads(sys.stdin.read())
    log(f"✓ JSON получен, ключи: {list(json_input.keys())}")
    # Логируем структуру для отладки
    log(f"DEBUG: Full JSON structure: {json.dumps(json_input, ensure_ascii=False, indent=2)[:1000]}...")
except Exception as e:
    log(f"ERROR: Не удалось прочитать JSON из stdin: {e}")
    print("ERROR: Не получены данные от Stash", file=sys.stderr)
    sys.exit(1)

# Получаем URL из конфигурации плагина
url = None

# Функция для получения plugin settings через GraphQL
def get_plugin_settings_from_stash(json_input):
    """Получить settings плагина через GraphQL API Stash"""
    try:
        log("=== Попытка получить settings через GraphQL ===")
        server_conn = json_input.get("server_connection", {})
        log(f"DEBUG: server_connection ключи: {list(server_conn.keys())}")
        
        scheme = server_conn.get("Scheme", "http")
        host = server_conn.get("Host", "localhost")
        port = server_conn.get("Port", 9999)
        
        log(f"DEBUG: Scheme={scheme}, Host={host}, Port={port}")
        
        # Используем loopback address если получен 0.0.0.0
        if host == "0.0.0.0":
            host = "localhost"
            log(f"DEBUG: Заменил 0.0.0.0 на localhost")
        
        server_url = f"{scheme}://{host}:{port}/graphql"
        log(f"DEBUG: Server URL: {server_url}")
        
        # GraphQL query для получения конфигурации плагина
        query = """
        query {
            configuration {
                plugins
            }
        }
        """
        log(f"DEBUG: GraphQL query готов (first attempt - just plugins list)")
        
        # Подготавливаем запрос
        request_data = json.dumps({"query": query})
        log(f"DEBUG: Request data размер: {len(request_data)} байт")
        
        # Получаем session cookie если есть
        session_cookie = ""
        cookie_obj = server_conn.get("SessionCookie", {})
        log(f"DEBUG: SessionCookie object: {type(cookie_obj)}")
        
        if cookie_obj:
            cookie_name = cookie_obj.get("Name", "session")
            cookie_value = cookie_obj.get("Value", "")
            log(f"DEBUG: Cookie Name={cookie_name}, Value length={len(cookie_value) if cookie_value else 0}")
            if cookie_value:
                session_cookie = f"{cookie_name}={cookie_value}"
                log(f"DEBUG: Session cookie установлен")
        
        req = urllib.request.Request(
            server_url,
            data=request_data.encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Cookie': session_cookie if session_cookie else '',
                'User-Agent': 'URL Executor Plugin'
            },
            method='POST'
        )
        
        log(f"DEBUG: HTTP Request подготовлен")
        log(f"DEBUG: Отправляю запрос к {server_url}...")
        
        try:
            response = urllib.request.urlopen(req, timeout=10)
            log(f"DEBUG: Получен ответ, статус код: {response.status}")
            
            response_text = response.read().decode('utf-8')
            log(f"DEBUG: Response размер: {len(response_text)} байт")
            log(f"DEBUG: Response текст: {response_text[:300]}...")
            
            response_data = json.loads(response_text)
            log(f"DEBUG: JSON распарсен успешно")
            
            # Логируем всю структуру ответа
            log(f"DEBUG: Response структура: {json.dumps(response_data, ensure_ascii=False, indent=2)[:500]}...")
            
            # Извлекаем URL из ответа
            if response_data.get("data"):
                log(f"DEBUG: 'data' найден в ответе")
                config = response_data["data"].get("configuration", {})
                log(f"DEBUG: 'configuration' структура: {json.dumps(config, ensure_ascii=False, indent=2)[:800]}")
                
                plugins = config.get("plugins", {})
                
                # plugins может быть dict или string в зависимости от версии Stash
                if isinstance(plugins, dict):
                    log(f"DEBUG: 'plugins' это dict, ключи: {list(plugins.keys())}")
                    
                    # Пробуем получить url_executor или url-executor (с дефисом!)
                    url_executor = None
                    for key in ["url-executor", "url_executor"]:
                        if key in plugins:
                            url_executor = plugins[key]
                            log(f"DEBUG: Найден ключ '{key}' в plugins")
                            break
                    
                    if url_executor and isinstance(url_executor, dict):
                        url = url_executor.get("url", "").strip()
                        if url:
                            log(f"✓ URL получен через GraphQL (method 1): {url[:80]}...")
                            return url
                        else:
                            log(f"DEBUG: URL пусто в {key}")
                    else:
                        log(f"DEBUG: url_executor не найден или не dict")
                else:
                    log(f"DEBUG: 'plugins' это не dict: {type(plugins)} = {str(plugins)[:200]}")
                    # Если это строка, может быть JSON строкой
                    try:
                        plugins_parsed = json.loads(plugins) if isinstance(plugins, str) else plugins
                        log(f"DEBUG: Распарсил plugins: {plugins_parsed}")
                        if isinstance(plugins_parsed, dict) and "url_executor" in plugins_parsed:
                            url_executor_data = plugins_parsed.get("url_executor", {})
                            if isinstance(url_executor_data, dict):
                                url = url_executor_data.get("url", "").strip()
                                if url:
                                    log(f"✓ URL получен через GraphQL (method 2): {url[:80]}...")
                                    return url
                    except Exception as parse_err:
                        log(f"DEBUG: Не удалось распарсить plugins как JSON: {parse_err}")
                
                log(f"DEBUG: URL не найден в plugins структуре")
            else:
                log(f"DEBUG: 'data' НЕ найден в ответе")
                errors = response_data.get("errors", [])
                log(f"DEBUG: GraphQL ошибки: {errors}")
                
        except urllib.error.HTTPError as e:
            error_response = e.read().decode('utf-8')
            log(f"ERROR: HTTPError: код {e.code}")
            log(f"ERROR: Response: {error_response[:500]}")
            
            # Пробуем распарсить JSON ошибку
            try:
                error_data = json.loads(error_response)
                if error_data.get("errors"):
                    for error in error_data.get("errors", []):
                        log(f"ERROR: GraphQL error: {error}")
            except:
                pass
            
    except Exception as e:
        log(f"ERROR: Ошибка при запросе к GraphQL (outer): {e}")
        import traceback
        log(f"ERROR: Traceback: {traceback.format_exc()}")
    
    log("DEBUG: GraphQL метод не вернул URL")
    return None

# Пробуем получить URL различными способами
try:
    # 1. Прямо из корня JSON
    if "url" in json_input:
        url = json_input.get("url", "").strip()
        log(f"✓ URL найден в корне JSON: {url[:80] if url else 'пусто'}...")
    
    # 2. Из args (входные аргументы задачи)
    if not url:
        log("DEBUG: Способ 1 (корень JSON) не помог, проверяю args...")
        if "args" in json_input and isinstance(json_input["args"], dict):
            log(f"DEBUG: args содержит ключи: {list(json_input['args'].keys())}")
            url = json_input["args"].get("url", "").strip()
            if url:
                log(f"✓ URL найден в args: {url[:80]}...")
            else:
                log("DEBUG: URL не найден в args")
        else:
            log(f"DEBUG: 'args' отсутствует или не dict: {type(json_input.get('args'))}")
    
    # 3. Пробуем hookContext
    if not url:
        log("DEBUG: Способ 2 (args) не помог, проверяю hookContext...")
        if "hookContext" in json_input:
            hook = json_input.get("hookContext", {})
            if isinstance(hook, dict):
                log(f"DEBUG: hookContext содержит ключи: {list(hook.keys())}")
                url = hook.get("url", "").strip()
                if url:
                    log(f"✓ URL найден в hookContext: {url[:80]}...")
                else:
                    log("DEBUG: URL не найден в hookContext")
            else:
                log(f"DEBUG: hookContext не dict: {type(hook)}")
        else:
            log("DEBUG: 'hookContext' отсутствует")
    
    # 4. Пробуем pluginSettings (стандартный способ передачи настроек в Stash)
    if not url:
        log("DEBUG: Способ 3 (hookContext) не помог, проверяю pluginSettings...")
        if "pluginSettings" in json_input:
            settings = json_input.get("pluginSettings", {})
            if isinstance(settings, dict):
                log(f"DEBUG: pluginSettings содержит ключи: {list(settings.keys())}")
                url = settings.get("url", "").strip()
                if url:
                    log(f"✓ URL найден в pluginSettings: {url[:80]}...")
                else:
                    log("DEBUG: URL не найден в pluginSettings")
            else:
                log(f"DEBUG: pluginSettings не dict: {type(settings)}")
        else:
            log("DEBUG: 'pluginSettings' отсутствует")
    
    # 5. Получаем через GraphQL API (основной способ для Stash)
    if not url:
        log("DEBUG: Способ 4 (pluginSettings) не помог, пытаюсь GraphQL API...")
        if "server_connection" in json_input:
            log("DEBUG: 'server_connection' найден, вызываю get_plugin_settings_from_stash()...")
            url = get_plugin_settings_from_stash(json_input)
            if url:
                log(f"✓ GraphQL успешно вернул URL: {url[:80]}...")
            else:
                log("DEBUG: GraphQL вернул None")
        else:
            log("DEBUG: 'server_connection' отсутствует в json_input")
    
    # 6. Читаем из конфига Stash (файл с настройками плагина)
    if not url:
        log("DEBUG: Способ 5 (GraphQL) не помог, проверяю config файлы...")
        try:
            script_dir = Path(__file__).parent
            log(f"DEBUG: script_dir = {script_dir}")
            config_paths = [
                script_dir / "url_executor-settings.json",
                script_dir / "settings.json",
                script_dir / "config.json",
                script_dir.parent / "url_executor-settings.json",
            ]
            
            log(f"DEBUG: Проверяю {len(config_paths)} конфиг файлов...")
            for config_path in config_paths:
                log(f"DEBUG: Проверяю {config_path}...")
                if config_path.exists():
                    log(f"DEBUG: {config_path} существует, читаю...")
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            config_data = json.load(f)
                            if isinstance(config_data, dict):
                                url = config_data.get("url", "").strip()
                                if url:
                                    log(f"✓ URL найден в {config_path}: {url[:80]}...")
                                    break
                                else:
                                    log(f"DEBUG: URL пусто или отсутствует в {config_path}")
                            else:
                                log(f"DEBUG: config_data не dict: {type(config_data)}")
                    except Exception as e:
                        log(f"DEBUG: Ошибка при чтении {config_path}: {e}")
                else:
                    log(f"DEBUG: {config_path} НЕ существует")
        except Exception as e:
            log(f"DEBUG: Ошибка при поиске конфига: {e}")
            import traceback
            log(f"DEBUG: Traceback: {traceback.format_exc()}")
    
    # 7. Пробуем переменную окружения
    if not url:
        log("DEBUG: Способ 6 (config файлы) не помог, проверяю переменные окружения...")
        try:
            url = os.environ.get('STASH_PLUGIN_URL_EXECUTOR_URL', '').strip()
            if url:
                log(f"✓ URL найден в переменной окружения: {url[:80]}...")
            else:
                log("DEBUG: Переменная окружения пуста")
        except Exception as e:
            log(f"DEBUG: Ошибка при чтении переменной окружения: {e}")
    
    # Итоговая проверка
    if not url:
        log(f"=== КРИТИЧЕСКАЯ ОШИБКА ===")
        log(f"Все 7 способов получения URL не сработали!")
        log(f"ERROR: URL не найден в конфигурации")
        log(f"СПРАВКА: Введите URL в настройках плагина в Stash")
        print("ERROR: URL not found. Please configure it in Stash plugin settings.", file=sys.stderr)
        sys.exit(1)
    else:
        log(f"=== УСПЕШНО ===")
        log(f"URL получен: {url[:80]}...")
        
except Exception as e:
    log(f"ERROR: Ошибка получения URL: {e}")
    import traceback
    log(f"Traceback: {traceback.format_exc()}")
    print(f"ERROR: Configuration error: {e}", file=sys.stderr)
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
