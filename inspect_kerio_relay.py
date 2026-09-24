#!/usr/bin/env python3
"""Диагностический скрипт для получения и безопасного вывода правил «Доставка SMTP» (Smtp.getRelayDeliveryRuleList) из Kerio Connect API.

Скрипт:
1. Читает настройки из .env (или переменных окружения / аргументов).
2. Авторизуется в Kerio Connect WebAdmin API (Session.login).
3. Запрашивает текущий список правил исходящей ретрансляции (Smtp.getRelayDeliveryRuleList).
4. Автоматически маскирует пароли (заменяет на '***') во избежание утечки секретов.
5. Выводит структурированный JSON в stdout.
6. Корректно завершает сессию администратора (Session.logout).
"""

import json
import os
import sys
from pathlib import Path
import urllib3
import requests

# Отключаем предупреждения о самоподписанном SSL-сертификате Kerio
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def load_env(env_path: Path) -> dict:
    """Загружает переменные из .env файла."""
    env = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main():
    base_dir = Path(__file__).resolve().parent
    env_file = base_dir / ".env"
    env = load_env(env_file)

    # Параметры подключения к Kerio Connect API
    api_url = os.getenv("KERIO_API_URL", env.get("KERIO_API_URL", "https://192.168.10.242:4040/admin/api/jsonrpc/"))
    username = os.getenv("KERIO_API_USER", env.get("KERIO_API_USER", "admin"))
    password = os.getenv("KERIO_API_PASSWORD", env.get("KERIO_API_PASSWORD", ""))

    if not password:
        print("[-] Ошибка: пароль администратора Kerio (KERIO_API_PASSWORD) не найден в .env или переменных окружения.", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Подключение к Kerio Connect API ({api_url}) под пользователем '{username}'...", file=sys.stderr)

    session = requests.Session()
    req_id = 1

    # 1. Авторизация (Session.login)
    login_payload = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "Session.login",
        "params": {
            "userName": username,
            "password": password,
            "application": {
                "name": "Kerio Relay Inspector",
                "vendor": "Barkol",
                "version": "1.0.0",
            },
        },
    }

    try:
        resp = session.post(api_url, json=login_payload, verify=False, timeout=15)
        resp.raise_for_status()
        login_res = resp.json()
    except Exception as exc:
        print(f"[-] Ошибка подключения/авторизации в Kerio Connect: {exc}", file=sys.stderr)
        sys.exit(1)

    if "error" in login_res and login_res["error"]:
        print(f"[-] Kerio вернул ошибку авторизации: {login_res['error']}", file=sys.stderr)
        sys.exit(1)

    token = login_res.get("result", {}).get("token")
    if not token:
        print("[-] Kerio не вернул токен сессии.", file=sys.stderr)
        sys.exit(1)

    headers = {
        "Content-Type": "application/json",
        "X-Token": token,
    }

    try:
        # 2. Получение правил доставки SMTP (Smtp.getRelayDeliveryRuleList)
        req_id += 1
        get_payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "Smtp.getRelayDeliveryRuleList",
            "params": {},
            "token": token,
        }

        resp = session.post(api_url, json=get_payload, headers=headers, verify=False, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if "error" in data and data["error"]:
            print(f"[-] Ошибка при вызове Smtp.getRelayDeliveryRuleList: {data['error']}", file=sys.stderr)
            sys.exit(1)

        result = data.get("result", {})

        # Маскируем пароли для безопасного вывода
        if isinstance(result, dict) and "list" in result:
            for rule in result["list"]:
                if isinstance(rule, dict) and "authentication" in rule:
                    auth = rule["authentication"]
                    if isinstance(auth, dict) and "password" in auth:
                        pwd_val = auth["password"]
                        if pwd_val:
                            auth["password"] = "***"
                        else:
                            auth["password"] = ""  # сохраняем индикацию, если строка пустая

        # Выводим чистый красивый JSON
        print(json.dumps(result, indent=2, ensure_ascii=False))

    finally:
        # 3. Закрытие сессии (Session.logout)
        try:
            req_id += 1
            logout_payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "Session.logout",
                "params": {},
                "token": token,
            }
            session.post(api_url, json=logout_payload, headers=headers, verify=False, timeout=5)
        except Exception:
            pass


if __name__ == "__main__":
    main()
