# consumers.py
import random
from asyncio import sleep

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
import json


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
        channel_layer = get_channel_layer()
        user = self.scope['user']
        if user.is_authenticated:
            self.online_users.add(user.title)
            await channel_layer.group_add('online_users', self.channel_name)
            await self.send_online_users()

    async def disconnect(self, close_code):
        channel_layer = get_channel_layer()
        user = self.scope['user']
        if user.is_authenticated:
            self.online_users.discard(user.username)
            await channel_layer.group_discard('online_users', self.channel_name)
            await self.send_online_users()

    async def send_online_users(self):
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
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