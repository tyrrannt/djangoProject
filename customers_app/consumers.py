# consumers.py
import os
import time
from asyncio import sleep
import psutil
from typing import Any, Dict, List, Optional, Set, Tuple

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
import json

from django.core.cache import cache
from django.contrib.auth.models import AnonymousUser
from chat_app.models import Message
from administration_app.utils import transliterate, get_device_info
from administration_app.system_monitor_service import get_system_monitor_payload

from contracts_app.templatetags.custom import FIO_format
from customers_app.models import DataBaseUser

ONLINE_HEARTBEAT_TIMEOUT = 70  # Секунды: таймаут неактивности сессии без heartbeat
REGISTRY_CACHE_KEY = "portal_online_users_registry"
REGISTRY_CACHE_TIMEOUT = 300  # Секунды: время жизни кэша реестра (5 минут)


def get_scope_user_agent(scope: dict) -> str:
    """Извлекает строку заголовка User-Agent из ASGI scope WebSocket-подключения.

    Args:
        scope (dict): Словарь ASGI scope с метаданными WebSocket-соединения.

    Returns:
        str: Значение HTTP-заголовка User-Agent или пустая строка при отсутствии.
    """
    for name, value in scope.get('headers', []):
        if name.lower() == b'user-agent':
            try:
                return value.decode('utf-8')
            except UnicodeDecodeError:
                return value.decode('latin1', errors='ignore')
    return ''


def _prune_registry(registry: dict) -> dict:
    """Очищает реестр соединений от устаревших сессий, превысивших таймаут неактивности.

    Args:
        registry (dict): Словарь активных соединений вида {channel_name: conn_data}.

    Returns:
        dict: Очищенный словарь актуальных соединений.
    """
    if not isinstance(registry, dict):
        return {}
    now = time.time()
    valid_registry = {}
    for ch_name, data in registry.items():
        if not isinstance(data, dict):
            continue
        last_seen = data.get('last_seen', 0)
        # Исключаем сессии без отметки времени или старше таймаута неактивности
        if last_seen and (now - last_seen) > ONLINE_HEARTBEAT_TIMEOUT:
            continue
        valid_registry[ch_name] = data
    return valid_registry


def _format_online_users(registry: dict) -> List[Dict[str, Any]]:
    """Группирует активные WebSocket-подключения по пользователям и формирует список устройств.

    Выполняет строгую верификацию статуса пользователя в БД, исключая деактивированных/уволенных
    сотрудников (is_active=False), технические терминалы МПД (is_ppa=True) и сессии без heartbeat.
    Обеспечивает обратную совместимость как с кортежным форматом (user[0], user[1]),
    так и со структурированными объектами, агрегируя все клиентские устройства
    пользователя (например, ПК и мобильный телефон) без дублирования одинаковых сессий.

    Args:
        registry (dict): Словарь активных соединений вида {channel_name: session_dict}.

    Returns:
        List[Dict[str, Any]]: Отсортированный по ФИО список словарей с параметрами активных пользователей.
    """
    active_channels = _prune_registry(registry)
    if not active_channels:
        return []

    # Собираем уникальные идентификаторы пользователей для валидации
    candidate_user_ids = {
        data.get('user_id')
        for data in active_channels.values()
        if data.get('user_id')
    }
    if not candidate_user_ids:
        return []

    # Проверяем реальный статус пользователей в БД
    try:
        valid_active_user_ids = set(
            DataBaseUser.objects.filter(
                id__in=candidate_user_ids,
                is_active=True,
                is_ppa=False
            ).values_list('id', flat=True)
        )
    except Exception:
        # Резервный режим фильтрации по метаданным сессии при временной недоступности БД
        valid_active_user_ids = {
            data.get('user_id')
            for data in active_channels.values()
            if data.get('user_id') and data.get('is_active', True) and not data.get('is_ppa', False)
        }

    users_map: Dict[int, Dict[str, Any]] = {}
    for ch_name, data in active_channels.items():
        uid = data.get('user_id')
        if not uid or uid not in valid_active_user_ids:
            continue

        username = data.get('username', '')
        if uid not in users_map:
            users_map[uid] = {
                # Строковые ключи '0'...'5' для совместимости с JS user[0], user[1] и защиты от ValueError в Channels/msgpack
                '0': username,
                '1': uid,
                '2': data.get('device_type', 'Компьютер / Ноутбук'),
                '3': data.get('device_icon', 'bx bx-laptop'),
                '4': data.get('os_name', ''),
                '5': data.get('browser_name', ''),
                'user_id': uid,
                'username': username,
                'devices': [],
                'device_type': data.get('device_type', 'Компьютер / Ноутбук'),
                'device_icon': data.get('device_icon', 'bx bx-laptop'),
                'device_category': data.get('device_category', 'desktop'),
                'os_name': data.get('os_name', ''),
                'browser_name': data.get('browser_name', ''),
            }

        dev = {
            'device_type': data.get('device_type', 'Компьютер / Ноутбук'),
            'device_icon': data.get('device_icon', 'bx bx-laptop'),
            'device_category': data.get('device_category', 'desktop'),
            'os_name': data.get('os_name', ''),
            'browser_name': data.get('browser_name', ''),
        }
        # Исключаем дубликаты идентичных устройств (например, 2 открытые вкладки на одном ПК)
        if dev not in users_map[uid]['devices']:
            users_map[uid]['devices'].append(dev)

    result = list(users_map.values())
    result.sort(key=lambda u: u.get('username', ''))
    return result


@sync_to_async(thread_sensitive=True)
def add_user_connection(channel_name: str, conn_data: dict) -> list:
    """Регистрирует активное подключение в распределенном кэше и возвращает обновленный список онлайн.

    Args:
        channel_name (str): Уникальный идентификатор канала Channels.
        conn_data (dict): Словарь параметров сессии (user_id, username, device_info, last_seen).

    Returns:
        list: Актуальный список пользователей онлайн.
    """
    now = time.time()
    conn_data['last_seen'] = now
    try:
        registry = cache.get(REGISTRY_CACHE_KEY) or {}
        registry = _prune_registry(registry)
        registry[channel_name] = conn_data
        cache.set(REGISTRY_CACHE_KEY, registry, timeout=REGISTRY_CACHE_TIMEOUT)
        return _format_online_users(registry)
    except Exception:
        OnlineUsersConsumer._local_registry = _prune_registry(OnlineUsersConsumer._local_registry)
        OnlineUsersConsumer._local_registry[channel_name] = conn_data
        return _format_online_users(OnlineUsersConsumer._local_registry)


@sync_to_async(thread_sensitive=True)
def update_user_heartbeat(channel_name: str) -> None:
    """Обновляет отметку времени последней активности (heartbeat) для указанного канала.

    Args:
        channel_name (str): Уникальный идентификатор канала Channels.
    """
    now = time.time()
    try:
        registry = cache.get(REGISTRY_CACHE_KEY) or {}
        if channel_name in registry:
            registry[channel_name]['last_seen'] = now
            registry = _prune_registry(registry)
            cache.set(REGISTRY_CACHE_KEY, registry, timeout=REGISTRY_CACHE_TIMEOUT)
    except Exception:
        if channel_name in OnlineUsersConsumer._local_registry:
            OnlineUsersConsumer._local_registry[channel_name]['last_seen'] = now
            OnlineUsersConsumer._local_registry = _prune_registry(OnlineUsersConsumer._local_registry)


@sync_to_async(thread_sensitive=True)
def remove_user_connection(channel_name: str) -> list:
    """Удаляет завершенное подключение из реестра и возвращает обновленный список онлайн.

    Args:
        channel_name (str): Уникальный идентификатор закрытого канала Channels.

    Returns:
        list: Актуальный список пользователей онлайн.
    """
    try:
        registry = cache.get(REGISTRY_CACHE_KEY) or {}
        registry.pop(channel_name, None)
        registry = _prune_registry(registry)
        cache.set(REGISTRY_CACHE_KEY, registry, timeout=REGISTRY_CACHE_TIMEOUT)
        return _format_online_users(registry)
    except Exception:
        OnlineUsersConsumer._local_registry.pop(channel_name, None)
        OnlineUsersConsumer._local_registry = _prune_registry(OnlineUsersConsumer._local_registry)
        return _format_online_users(OnlineUsersConsumer._local_registry)


@sync_to_async(thread_sensitive=True)
def get_current_online_users() -> list:
    """Считывает текущий агрегированный список пользователей онлайн из реестра.

    Returns:
        list: Список словарей активных пользователей.
    """
    try:
        registry = cache.get(REGISTRY_CACHE_KEY) or {}
        registry = _prune_registry(registry)
        cache.set(REGISTRY_CACHE_KEY, registry, timeout=REGISTRY_CACHE_TIMEOUT)
        if not registry and OnlineUsersConsumer._local_registry:
            registry = _prune_registry(OnlineUsersConsumer._local_registry)
        return _format_online_users(registry)
    except Exception:
        OnlineUsersConsumer._local_registry = _prune_registry(OnlineUsersConsumer._local_registry)
        return _format_online_users(OnlineUsersConsumer._local_registry)


class OnlineUsersConsumer(AsyncWebsocketConsumer):
    """Асинхронный потребитель WebSockets для отслеживания и трансляции списка пользователей онлайн.

    Определяет устройство каждого пользователя (ПК, планшет, смартфон) через User-Agent,
    поддерживает проверку активности учетной записи, фильтрацию недействующих сотрудников
    и технических терминалов МПД, очистку зависших соединений по heartbeat-таймауту
    и мультипроцессную синхронизацию сессий через распределенный кэш.

    Attributes:
        online_users (set): Набор кортежей (username, user_id) для обратной совместимости.
        _local_registry (dict): Локальный fallback-реестр активных каналов на уровне процесса.
    """

    online_users = set()
    _local_registry = {}

    async def connect(self):
        """Обрабатывает входящее WebSocket-подключение, выполняет проверки и регистрирует сессию.

        Raises:
            Exception: При непредвиденных ошибках регистрации канала в Channel Layer.
        """
        user = self.scope.get('user')
        if not user or not user.is_authenticated or not user.is_active or getattr(user, 'is_ppa', False):
            await self.close()
            return

        await self.accept()
        username = FIO_format(getattr(user, 'title', '') or getattr(user, 'username', '') or str(user))
        ua_string = get_scope_user_agent(self.scope)
        device_info = get_device_info(ua_string)

        conn_data = {
            'user_id': user.pk,
            'username': username,
            'device_type': device_info.get('device_type', 'Компьютер / Ноутбук'),
            'device_category': device_info.get('device_category', 'desktop'),
            'device_icon': device_info.get('device_icon', 'bx bx-laptop'),
            'os_name': device_info.get('os_name', ''),
            'browser_name': device_info.get('browser_name', ''),
            'is_active': bool(user.is_active),
            'is_ppa': bool(getattr(user, 'is_ppa', False)),
            'last_seen': time.time(),
        }

        self.online_users.add((username, user.pk))
        users_list = await add_user_connection(self.channel_name, conn_data)

        await self.channel_layer.group_add('online_users', self.channel_name)
        await self.send_online_users(users_list)

    async def disconnect(self, close_code):
        """Обрабатывает отключение WebSocket-клиента и удаляет сессию из общего реестра.

        Args:
            close_code (int): Код закрытия WebSocket-соединения.
        """
        user = self.scope.get('user')
        if user and user.is_authenticated:
            username = FIO_format(getattr(user, 'title', '') or getattr(user, 'username', '') or str(user))
            self.online_users.discard((username, user.pk))
        users_list = await remove_user_connection(self.channel_name)
        await self.channel_layer.group_discard('online_users', self.channel_name)
        await self.send_online_users(users_list)

    async def receive(self, text_data=None, bytes_data=None):
        """Обрабатывает входящие сообщения WebSocket, включая регулярный heartbeat (ping).

        Args:
            text_data (str, optional): Текстовые данные JSON от клиента.
            bytes_data (bytes, optional): Бинарные данные.
        """
        if not text_data:
            return
        try:
            data = json.loads(text_data)
            msg_type = data.get('type')
            if msg_type in ('ping', 'heartbeat'):
                await update_user_heartbeat(self.channel_name)
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': int(time.time()),
                }))
        except Exception:
            pass

    async def send_online_users(self, users_list=None):
        """Отправляет актуальный перечень пользователей всем участникам группы online_users.

        Args:
            users_list (list, optional): Предварительно сформированный список пользователей.
                Если не передан, считывается из реестра кэша.
        """
        if users_list is None:
            users_list = await get_current_online_users()

        await self.channel_layer.group_send(
            'online_users',
            {
                'type': 'online_users_message',
                'users': users_list,
            }
        )

    async def online_users_message(self, event):
        """Принимает групповое событие со списком пользователей и отправляет JSON клиенту.

        Args:
            event (dict): Словарь события Channels с ключами 'type' и 'users'.
        """
        users = event['users']
        user = self.scope.get('user')
        is_admin = bool(user and getattr(user, 'is_superuser', False))
        await self.send(text_data=json.dumps({
            'type': 'online_users',
            'users': users,
            'is_admin': is_admin,
        }))


class PrivateMessageConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope['user']
        if not user.is_authenticated:
            await self.close()
        else:
            self.user_group_name = f"user_{user.pk}"
            await self.channel_layer.group_add(
                self.user_group_name,
                self.channel_name
            )
            await self.accept()

    async def disconnect(self, close_code):
        user = self.scope['user']
        if user.is_authenticated and hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        data = json.loads(text_data)

        recipient_id = data.get('to')
        message = data.get('message')
        sender = self.scope['user']

        if recipient_id:
            target_group = f"user_{recipient_id}"
            await self.channel_layer.group_send(
                target_group,
                {
                    "type": "private_message",
                    "message": message,
                    "from": sender.pk,
                    "from_name": sender.title
                }
            )

    async def private_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "private_message",
            "message": event["message"],
            "from": event["from"],
            "from_name": event["from_name"],
        }))


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"] == AnonymousUser():
            await self.close()
        else:
            self.room_name = self.scope['url_route']['kwargs']['room_name']
            self.room_group_name = ('chat_%s' % transliterate(self.room_name))[:100]

            # Присоединение к группе
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )

            await self.accept()

            # Загрузка истории чата
            await self.load_chat_history()

            # Отправка уведомления о подключении пользователя
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_notification',
                    'message': f'{self.scope["user"].username} подключился к чату',
                    'username': 'Система',
                }
            )

    async def disconnect(self, close_code):
        # Отправка уведомления об отключении пользователя
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_notification',
                'message': f'{self.scope["user"].username} покинул чат',
                'username': 'Система',
            }
        )

        # Покидание группы
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Получение сообщения от WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_type = text_data_json.get('type', 'chat_message')
        user = self.scope['user']

        if message_type == 'chat_message':
            message = text_data_json['message']
            username = user.username

            # Сохранение сообщения в БД
            await self.save_message(username, self.room_name, message)

            # Отправка сообщения в группу
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'username': username,
                    'user_id': user.pk,
                }
            )
        elif message_type == 'signal':
            # Пересылка сигналов WebRTC (offer, answer, ice candidates)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'send_signal',
                    'signal': text_data_json['signal'],
                    'target_id': text_data_json.get('target_id'),
                    'sender_channel_name': self.channel_name,
                    'user_id': user.pk,
                    'username': user.username
                }
            )

    # Получение сообщения от группы
    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message'],
            'username': event['username'],
            'user_id': event.get('user_id'),
        }))

    async def send_signal(self, event):
        # Отправляем сигнал всем, кроме отправителя
        if self.channel_name != event['sender_channel_name']:
            target_id = event.get('target_id')
            current_user_id = self.scope['user'].pk

            # Если указан target_id, проверяем, что он совпадает с текущим пользователем
            if target_id and int(target_id) != current_user_id:
                return

            await self.send(text_data=json.dumps({
                'type': 'signal',
                'signal': event['signal'],
                'user_id': event['user_id'],
                'username': event['username']
            }))

    # Получение уведомления от группы
    async def user_notification(self, event):
        message = event['message']
        username = event['username']

        # Отправка уведомления в WebSocket
        await self.send(text_data=json.dumps({
            'message': message,
            'username': username,
        }))

    async def load_chat_history(self):
        """Загрузка последних 50 сообщений из истории."""
        messages = await self.get_messages()
        for msg in messages:
            await self.send(text_data=json.dumps({
                'type': 'chat_message',
                'message': msg['message'],
                'username': msg['username'],
                'timestamp': msg['timestamp'].strftime('%d.%m.%Y %H:%M:%S')
            }))

    @database_sync_to_async
    def get_messages(self):
        return list(Message.objects.filter(room_name=self.room_name).order_by('timestamp')[:50].values('username', 'message', 'timestamp'))

    @database_sync_to_async
    def save_message(self, username, room_name, message):
        Message.objects.create(username=username, room_name=room_name, message=message)


def converter(x):
    result = (x / 1024) / 1024
    return round(result, 2)


class MonitorConsumer(AsyncWebsocketConsumer):
    """Асинхронный потребитель WebSockets для потоковой трансляции метрик и рекомендаций сервера.

    Передает в реальном времени телеметрические данные о состоянии CPU, памяти, дисков,
    сетевого трафика, температуре и базы данных MariaDB, а также структурированные
    интеллектуальные рекомендации администраторам портала.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_running = False

    async def connect(self):
        """Устанавливает WebSocket-соединение с проверкой аутентификации и запускает цикл трансляции."""
        user = self.scope.get("user")
        if not user or not user.is_authenticated or not (user.is_staff or user.is_superuser):
            await self.close()
            return

        await self.accept()
        self.is_running = True

        prev_sent = None
        prev_recv = None
        prev_time = None

        try:
            while self.is_running:
                payload = await sync_to_async(get_system_monitor_payload, thread_sensitive=True)(
                    prev_sent, prev_recv, prev_time
                )
                prev_sent = payload.get("net_sent_raw")
                prev_recv = payload.get("net_recv_raw")
                prev_time = payload.get("timestamp")

                # Обратная совместимость со старыми полями шаблона
                payload["net_sent"] = payload.get("net_sent_total_mb", 0.0)
                payload["net_recv"] = payload.get("net_recv_total_mb", 0.0)
                payload["processes"] = payload.get("processes_count", 0)
                payload["connections"] = payload.get("connections_count") or 0

                await self.send(text_data=json.dumps(payload))
                await sleep(2)
        except Exception:
            self.is_running = False

    async def disconnect(self, close_code):
        """Корректно останавливает цикл трансляции метрик при разрыве соединения."""
        self.is_running = False


class VideoConferenceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = 'video_conference_%s' % self.room_name

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        signal = text_data_json['signal']
        user_id = self.scope['user'].pk
        username = self.scope['user'].username

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'send_signal',
                'signal': signal,
                'target_id': text_data_json.get('target_id'),
                'sender_channel_name': self.channel_name,
                'user_id': user_id,
                'username': username
            }
        )

    async def send_signal(self, event):
        if self.channel_name != event['sender_channel_name']:
            target_id = event.get('target_id')
            current_user_id = self.scope['user'].pk

            if target_id and int(target_id) != current_user_id:
                return

            await self.send(text_data=json.dumps({
                'type': 'signal',
                'signal': event['signal'],
                'user_id': event['user_id'],
                'username': event['username']
            }))


class AudioConferenceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = 'audio_conference_%s' % self.room_name

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        signal = text_data_json['signal']
        user_id = self.scope['user'].pk
        username = self.scope['user'].username

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'send_signal',
                'signal': signal,
                'target_id': text_data_json.get('target_id'),
                'sender_channel_name': self.channel_name,
                'user_id': user_id,
                'username': username
            }
        )

    async def send_signal(self, event):
        if self.channel_name != event['sender_channel_name']:
            target_id = event.get('target_id')
            current_user_id = self.scope['user'].pk

            if target_id and int(target_id) != current_user_id:
                return

            await self.send(text_data=json.dumps({
                'type': 'signal',
                'signal': event['signal'],
                'user_id': event['user_id'],
                'username': event['username']
            }))
