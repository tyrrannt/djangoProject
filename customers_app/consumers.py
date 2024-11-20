# consumers.py
import random
from asyncio import sleep

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
import json

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
        username = self.scope['user'].username  # Получаем имя пользователя)

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