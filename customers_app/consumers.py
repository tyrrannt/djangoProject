# consumers.py
import os
import random
from asyncio import sleep
import psutil

import emoji
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
import json

from django.contrib.auth.models import AnonymousUser

from chat_app.models import Message
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
                self.online_users.add((FIO_format(user.title), user.pk))  # Добавляем имя пользователя в множество online_users
                await self.channel_layer.group_add('online_users', self.channel_name)  # Добавляем соединение в группу online_users
                await self.send_online_users()  # Отправляем список онлайн пользователей

    async def disconnect(self, close_code):
        """Метод для обработки разрыва соединения и удаления пользователя из списка онлайн пользователей."""
        user = self.scope['user']  # Получаем объект пользователя из scope
        if user.is_authenticated:  # Проверяем, авторизован ли пользователь
            self.online_users.discard((FIO_format(user.title), user.pk))  # Удаляем имя пользователя из множества online_users
            await self.channel_layer.group_discard('online_users', self.channel_name)  # Удаляем соединение из группы online_users
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




# class ChatConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         self.room_name = self.scope['url_route']['kwargs']['room_name']
#         self.room_group_name = 'chat_%s' % self.room_name
#
#         # Присоединение к группе
#         await self.channel_layer.group_add(
#             self.room_group_name,
#             self.channel_name
#         )
#
#         await self.accept()
#
#     async def disconnect(self, close_code):
#         # Покидание группы
#         await self.channel_layer.group_discard(
#             self.room_group_name,
#             self.channel_name
#         )
#
#     # Получение сообщения от WebSocket
#     async def receive(self, text_data):
#         text_data_json = json.loads(text_data)
#         message = text_data_json['message']
#         username = FIO_format(self.scope['user'].title)  # Получаем имя пользователя)
#
#         # Отправка сообщения в группу
#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'chat_message',
#                 'message': message,
#                 'username': username,
#             }
#         )
#
#     # Получение сообщения от группы
#     async def chat_message(self, event):
#         message = event['message']
#         username = event['username']
#
#         # Отправка сообщения в WebSocket
#         await self.send(text_data=json.dumps({
#             'message': message,
#             'username': username,
#         }))

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"] == AnonymousUser():
            await self.close()
        else:
            self.room_name = self.scope['url_route']['kwargs']['room_name']
            self.room_group_name = 'chat_%s' % self.room_name

            # Присоединение к группе
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )

            await self.accept()

            # Отправка уведомления о подключении пользователя
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_notification',
                    'message': f'{self.scope["user"].username} подключился к чату',
                    'username': 'Система',
                }
            )

            # # Загрузка истории чата
            # await self.load_chat_history()

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
        message = text_data_json['message']
        username = self.scope['user'].username  # Получаем имя пользователя

        # # Сохранение сообщения в базе данных
        # await self.save_message(username, message)

        # Отправка сообщения в группу
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'username': username,
            }
        )

    # Получение сообщения от группы
    async def chat_message(self, event):
        message = event['message']
        username = event['username']

        # Отправка сообщения в WebSocket
        await self.send(text_data=json.dumps({
            'message': message,
            'username': username,
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

    # @database_sync_to_async
    # def save_message(self, username, message):
    #     Message.objects.create(room_name=self.room_name, username=username, message=message)
    #
    # @database_sync_to_async
    # def load_chat_history(self):
    #     messages = Message.objects.filter(room_name=self.room_name).order_by('timestamp')
    #     for message in messages:
    #         self.send(text_data=json.dumps({
    #             'message': message.message,
    #             'username': message.username,
    #         }))

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
        user_id = text_data_json['user_id']

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'send_signal',
                'signal': signal,
                'user_id': user_id
            }
        )

    async def send_signal(self, event):
        signal = event['signal']
        user_id = event['user_id']

        await self.send(text_data=json.dumps({
            'signal': signal,
            'user_id': user_id
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
        print(f'WebSocket connected to room {self.room_name}')

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        print(f'WebSocket disconnected from room {self.room_name}')

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        signal = text_data_json['signal']
        user_id = text_data_json['user_id']

        print(f'Received signal from user {user_id}')

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'send_signal',
                'signal': signal,
                'user_id': user_id
            }
        )

    async def send_signal(self, event):
        signal = event['signal']
        user_id = event['user_id']

        print(f'Sending signal to user {user_id}')

        await self.send(text_data=json.dumps({
            'signal': signal,
            'user_id': user_id
        }))