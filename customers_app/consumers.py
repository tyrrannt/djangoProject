# consumers.py
import os
from asyncio import sleep
import psutil

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
import json

from django.contrib.auth.models import AnonymousUser
from chat_app.models import Message
from administration_app.utils import transliterate
from administration_app.system_monitor_service import get_system_monitor_payload

from contracts_app.templatetags.custom import FIO_format


class OnlineUsersConsumer(AsyncWebsocketConsumer):
    """Асинхронный потребитель WebSockets для отслеживания и трансляции списка пользователей онлайн.

    Attributes:
        online_users (set): Множество кортежей (форматированное ФИО, primary key) активных пользователей.
    """

    online_users = set()

    async def connect(self):
        """Обрабатывает входящее WebSocket-подключение и регистрирует авторизованного пользователя.

        Raises:
            Exception: При ошибках взаимодействия с Channel Layer.
        """
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close()
            return

        await self.accept()
        username = FIO_format(getattr(user, 'title', '') or getattr(user, 'username', '') or str(user))
        self.online_users.add((username, user.pk))
        await self.channel_layer.group_add('online_users', self.channel_name)
        await self.send_online_users()

    async def disconnect(self, close_code):
        """Обрабатывает отключение клиента и удаляет пользователя из группы онлайн.

        Args:
            close_code (int): Код закрытия соединения.
        """
        user = self.scope.get('user')
        if user and user.is_authenticated:
            username = FIO_format(getattr(user, 'title', '') or getattr(user, 'username', '') or str(user))
            self.online_users.discard((username, user.pk))
            await self.channel_layer.group_discard('online_users', self.channel_name)
            await self.send_online_users()

    async def send_online_users(self):
        """Отправляет актуальный список пользователей всем участникам группы online_users."""
        await self.channel_layer.group_send(
            'online_users',
            {
                'type': 'online_users_message',
                'users': list(self.online_users),
            }
        )

    async def online_users_message(self, event):
        """Принимает групповое событие со списком пользователей и отправляет JSON клиенту.

        Args:
            event (dict): Словарь события с ключами 'type' и 'users'.
        """
        users = event['users']
        user = self.scope['user']
        await self.send(text_data=json.dumps({
            'type': 'online_users',
            'users': users,
            'is_admin': user.is_superuser,
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
