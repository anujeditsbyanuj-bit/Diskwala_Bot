from telethon.sync import TelegramClient
from telethon.sessions import StringSession

api_id = 37998813
api_hash = "49b0f0677294b1918b255d3b16a21027"

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print(client.session.save())