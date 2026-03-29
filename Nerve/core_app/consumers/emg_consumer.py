"""
consumers/emg_consumer.py
--------------------------
AsyncWebsocketConsumer that joins the "emg_stream" channel group and
forwards every EMG sample broadcast by the serial reader thread to the
connected browser client.
"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer

GROUP_NAME = "emg_stream"


class EMGConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add(GROUP_NAME, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(GROUP_NAME, self.channel_name)

    # NEW: Handle incoming data from the client (WebSerial source)
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            # Broadcast this to EVERYONE in the group (including the sender, or not)
            # This allows other monitoring dashboards to see the WebSerial data too.
            await self.channel_layer.group_send(
                GROUP_NAME,
                {
                    "type": "emg_sample",
                    "data": data,
                }
            )
        except Exception:
            pass

    # Called by the channel layer to forward group messages to the browser
    async def emg_sample(self, event):
        await self.send(text_data=json.dumps(event["data"]))
