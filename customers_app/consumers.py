# consumers.py
import random
from asyncio import sleep

from channels.generic.websocket import AsyncWebsocketConsumer
# from channels.auth import
import json


class EchoConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()

        for i in range(1000):
            num = random.randint(0,1000)
            await self.send(json.dumps({"value": num}))
            await sleep(1)

    def disconnect(self, close_code):
        pass

    # def receive(self, text_data):
    #     data = json.loads(text_data)
    #     self.send(text_data=json.dumps({
    #         'message': data['message']
    #     }))
