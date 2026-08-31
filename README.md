# Diskwala Bot

Telegram bot that downloads and streams videos from Diskwala links.

## Features

- Download Diskwala/Flezen videos directly to Telegram
- Get streamable links for in-app viewing
- Multi-link support (send multiple links at once)
- Progress tracking with speed display

## Prerequisites

- Python 3.10+
- A Telegram bot token (from @BotFather)
- Telegram API credentials (from my.telegram.org)

## Setup

### 1. Get Telegram Bot Token

1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the instructions
3. Copy the bot token

### 2. Get Telegram API Credentials

1. Go to [my.telegram.org](https://my.telegram.org)
2. Log in with your phone number
3. Go to "API development tools"
4. Create an app and copy `api_id` and `api_hash`

### 3. Generate Telethon Session String

Create a file called `gen_session.py`:

```python
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

api_id = 12345678          # your api_id
api_hash = "your_api_hash"

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print(client.session.save())
```

Run it: `python gen_session.py`

Log in when prompted. Copy the printed session string.

**IMPORTANT:** Keep this session string secret - it's like a password to your Telegram account.

### 4. Install and Run

```bash
cd diskwala_bot
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
python main.py
```

### 5. Set Environment Variables

Edit `.env` file:

```
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
SESSION=your_session_string
OWNER_ID=your_telegram_user_id
```

## Usage

1. Start a chat with your bot on Telegram
2. Send a Diskwala link (e.g., `https://www.diskwala.com/app/xxxxx`)
3. Choose: Download File or Get Stream Link

## Commands

- `/start` - Welcome message
- `/help` - Show usage instructions
- `/auth` - Refresh auth token (owner only)

## File Structure

```
diskwala_bot/
├── main.py           # Telegram bot handlers
├── diskwala.py       # Diskwala API extraction logic
├── config.py         # Configuration
├── requirements.txt  # Python dependencies
├── .env.example      # Environment template
└── README.md         # This file
```

## Notes

- The bot requires a Telethon user session to authenticate with Diskwala's API
- Session string is equivalent to your Telegram login - keep it safe
- Videos are temporarily downloaded then deleted after sending
