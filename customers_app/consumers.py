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
        # for i in range(1000):
        #     num = random.randint(0,1000)
        #     await self.send(json.dumps({"value": num}))
        #     channel_layer.group_send('notifications', {})
        #     await sleep(1)

    def disconnect(self, close_code):
        pass

    # def receive(self, text_data):
    #     data = json.loads(text_data)
    #     self.send(text_data=json.dumps({
    #         'message': data['message']
    #     }))
