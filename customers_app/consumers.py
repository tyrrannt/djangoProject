# consumers.py
import random
from asyncio import sleep
import psutil

import emoji
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
import json

from chat_app.models import Message
from contracts_app.templatetags.custom import FIO_format


class EchoConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        channel_layer = get_channel_layer()
        for i in range(1000):
            num = random.randint(0,1000)
            await self.send(json.dumps({"value": num}))
            channel_layer.group_send('notifications', {})
            await sleep(1)

    def disconnect(self, close_code):
        pass

    # def receive(self, text_data):
    #     data = json.loads(text_data)
    #     self.send(text_data=json.dumps({
    #         'message': data['message']
    #     }))

class OnlineUsersConsumer(AsyncWebsocketConsumer):
    online_users = set()

    async def connect(self):
        await self.accept()
        user = self.scope['user']
        if user.is_authenticated:
            self.online_users.add(FIO_format(user.title))
            await self.channel_layer.group_add('online_users', self.channel_name)
            await self.send_online_users()

    async def disconnect(self, close_code):
        user = self.scope['user']
        if user.is_authenticated:
            self.online_users.discard(FIO_format(user.title))
            await self.channel_layer.group_discard('online_users', self.channel_name)
            await self.send_online_users()

    async def send_online_users(self):
        await self.channel_layer.group_send(
            'online_users',
            {
                'type': 'online_users_message',
                'users': list(self.online_users)
            }
        )

    async def online_users_message(self, event):
        users = event['users']
        await self.send(text_data=json.dumps({
            'type': 'online_users',
            'users': users
        }))


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = 'chat_%s' % self.room_name

        # Присоединение к группе
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Покидание группы
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Получение сообщения от WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json['message']
        username = FIO_format(self.scope['user'].title)  # Получаем имя пользователя)

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

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
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


class MonitorConsumer(AsyncWebsocketConsumer):
    """Класс для обработки соединений с веб-сокетами и отправки данных о загрузке процессора и памяти.
    В этом коде определен класс MonitorConsumer, который наследуется от AsyncWebsocketConsumer.
    Этот класс используется для обработки соединений с веб-сокетами и отправки данных о загрузке
    процессора и памяти каждую секунду. В методе connect происходит установка соединения и отправка
    данных о загрузке процессора и памяти каждую секунду. В методе disconnect происходит обработка
    разрыва соединения.
    """

    async def connect(self):
        """Метод для установки соединения и отправки данных о загрузке процессора и памяти каждую секунду."""
        await self.accept()  # Принимаем соединение
        while True:
            cpu_percent = psutil.cpu_percent(interval=1)  # Получаем процент загрузки процессора
            memory_percent = psutil.virtual_memory().percent  # Получаем процент загрузки памяти
            await self.send(text_data=json.dumps({
                'cpu_percent': cpu_percent,  # Отправляем данные о загрузке процессора
                'memory_percent': memory_percent,  # Отправляем данные о загрузке памяти
            }))
            await sleep(1)  # Ждем 1 секунду перед отправкой следующих данных

    async def disconnect(self, close_code):
        """Метод для обработки разрыва соединения."""
        pass  # Ничего не делаем при разрыве соединения
