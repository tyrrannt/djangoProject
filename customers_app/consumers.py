# consumers.py
import os
from asyncio import sleep
import psutil

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
import json

from django.contrib.auth.models import AnonymousUser
from chat_app.models import Message
from administration_app.utils import transliterate

from contracts_app.templatetags.custom import FIO_format


class OnlineUsersConsumer(AsyncWebsocketConsumer):
    """Класс для обработки соединений с веб-сокетами и отправки списка онлайн пользователей."""

    online_users = set()  # Множество для хранения имен пользователей, которые в данный момент онлайн

    async def connect(self):
        """Метод для установки соединения и добавления пользователя в список онлайн пользователей."""
        if self.scope["user"] == AnonymousUser():
            await self.close()
        else:
            await self.accept()  # Принимаем соединение
            user = self.scope['user']  # Получаем объект пользователя из scope
            if user.is_authenticated:  # Проверяем, авторизован ли пользователь
                self.online_users.add(
                    (FIO_format(user.title), user.pk))  # Добавляем имя пользователя в множество online_users
                await self.channel_layer.group_add('online_users',
                                                   self.channel_name)  # Добавляем соединение в группу online_users
                await self.send_online_users()  # Отправляем список онлайн пользователей

    async def disconnect(self, close_code):
        """Метод для обработки разрыва соединения и удаления пользователя из списка онлайн пользователей."""
        user = self.scope['user']  # Получаем объект пользователя из scope
        if user.is_authenticated:  # Проверяем, авторизован ли пользователь
            self.online_users.discard(
                (FIO_format(user.title), user.pk))  # Удаляем имя пользователя из множества online_users
            await self.channel_layer.group_discard('online_users',
                                                   self.channel_name)  # Удаляем соединение из группы online_users
            await self.send_online_users()  # Отправляем список онлайн пользователей

    async def send_online_users(self):
        """Метод для отправки списка онлайн пользователей."""
        await self.channel_layer.group_send(
            'online_users',
            {
                'type': 'online_users_message',  # Тип сообщения
                'users': list(self.online_users),  # Список онлайн пользователей
            }
        )

    async def online_users_message(self, event):
        """Метод для обработки сообщения о списке онлайн пользователей."""
        users = event['users']  # Получаем список онлайн пользователей из события
        user = self.scope['user']
        await self.send(text_data=json.dumps({
            'type': 'online_users',  # Тип сообщения
            'users': users,  # Список онлайн пользователей
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
    """Класс для обработки соединений с веб-сокетами и отправки данных о загрузке процессора, памяти, диска, сетевого трафика, количества процессов и сетевых соединений."""

    async def connect(self):
        """Метод для установки соединения и отправки данных о загрузке процессора, памяти, диска, сетевого трафика, количества процессов и сетевых соединений каждую секунду."""
        if self.scope["user"] == AnonymousUser():
            await self.close()
        else:
            await self.accept()  # Принимаем соединение
            while True:
                cpu_percent = psutil.cpu_percent(interval=1)  # Получаем процент загрузки процессора
                memory_percent = psutil.virtual_memory().percent  # Получаем процент загрузки памяти
                disk_percent = psutil.disk_usage('/').percent  # Получаем процент загрузки диска
                net_io = psutil.net_io_counters()  # Получаем информацию о сетевом трафике
                net_sent = net_io.bytes_sent  # Получаем количество отправленных байт
                net_recv = net_io.bytes_recv  # Получаем количество полученных байт
                processes = len(psutil.pids())  # Получаем количество процессов
                connections = len(psutil.net_connections())  # Получаем количество сетевых соединений

                # Получение температуры процессора (работает на Linux)
                if os.name == 'posix':
                    temps = psutil.sensors_temperatures()
                    cpu_temp = temps['coretemp'][0].current if 'coretemp' in temps else None
                else:
                    cpu_temp = None

                await self.send(text_data=json.dumps({
                    'cpu_percent': cpu_percent,  # Отправляем данные о загрузке процессора
                    'memory_percent': memory_percent,  # Отправляем данные о загрузке памяти
                    'disk_percent': disk_percent,  # Отправляем данные о загрузке диска
                    'net_sent': converter(net_sent),  # Отправляем данные о количестве отправленных байт
                    'net_recv': converter(net_recv),  # Отправляем данные о количестве полученных байт
                    'processes': processes,  # Отправляем данные о количестве процессов
                    'connections': connections,  # Отправляем данные о количестве сетевых соединений
                    'cpu_temp': cpu_temp,  # Отправляем данные о температуре процессора
                }))
                await sleep(1)  # Ждем 1 секунду перед отправкой следующих данных

    async def disconnect(self, close_code):
        """Метод для обработки разрыва соединения."""
        pass  # Ничего не делаем при разрыве соединения


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
