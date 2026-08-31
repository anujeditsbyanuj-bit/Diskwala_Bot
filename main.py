import os
import asyncio
import logging
import time
import requests
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

from config import API_ID, API_HASH, BOT_TOKEN, SESSION, OWNER_ID, TG_BOT_WORKERS, DOWNLOAD_DIR, MAX_CONCURRENT_DOWNLOADS
from diskwala import fetch_diskwala_video, extract_diskwala_links

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("diskwala_bot")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Client(
    "diskwala_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=TG_BOT_WORKERS,
)

download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

_auth_cache = {"token": None, "expires": 0}


def human_size(n: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"


def human_speed(n: float) -> str:
    for unit in ["B/s", "KB/s", "MB/s", "GB/s"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB/s"


async def get_auth_token() -> str:
    if _auth_cache["token"] and time.time() < _auth_cache["expires"]:
        return _auth_cache["token"]

    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.functions.messages import RequestAppWebViewRequest
    from telethon.tl.types import InputBotAppShortName, InputPeerSelf, DataJSON
    from urllib.parse import urlparse, unquote

    client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    try:
        await client.connect()
        bot = await client.get_input_entity("sky577bot")
        r = await client(RequestAppWebViewRequest(
            peer=InputPeerSelf(),
            app=InputBotAppShortName(bot_id=bot, short_name="open"),
            platform="android",
            write_allowed=True,
            start_param="",
            theme_params=DataJSON("{}"),
        ))
        token = unquote(urlparse(r.url).fragment.split("tgWebAppData=", 1)[1].split("&tgWebAppVersion=", 1)[0])
        _auth_cache["token"] = token
        _auth_cache["expires"] = time.time() + 1800
        return token
    finally:
        await client.disconnect()


@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, m: Message):
    await m.reply(
        "<b>Welcome to Diskwala Bot!</b>\n\n"
        "Send me a Diskwala link and I'll:\n"
        "1. Download the video file\n"
        "2. Or give you a streamable link",
        parse_mode=ParseMode.HTML,
    )


@app.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, m: Message):
    await m.reply(
        "<b>How to use:</b>\n\n"
        "1. Copy a Diskwala link\n"
        "2. Send it here\n"
        "3. Choose: Download or Stream",
        parse_mode=ParseMode.HTML,
    )


@app.on_message(filters.private & ~filters.command(["start", "help"]))
async def link_handler(client: Client, m: Message):
    text = m.text or m.caption or ""
    links = extract_diskwala_links(text)
    if not links:
        return
    for i, link in enumerate(links):
        tag = f"[{i+1}/{len(links)}]"
        await process_link(client, m, link, tag)


async def process_link(client: Client, m: Message, link: str, tag: str):
    status = await m.reply(
        f"<b>Fetching video info {tag}...</b>\n<code>{link}</code>",
        parse_mode=ParseMode.HTML,
    )
    try:
        auth = await get_auth_token()
        video_info = fetch_diskwala_video(link, auth)

        name = video_info.get("name", "video.mp4")
        size = video_info.get("size", 0)
        download_url = video_info.get("downloadUrl")

        if not download_url:
            await status.edit_text(f"<b>No download URL found {tag}</b>")
            return

        size_str = human_size(size) if size else "Unknown"
        await status.edit_text(
            f"<b>Video found {tag}</b>\n\n"
            f"Name: <code>{name}</code>\n"
            f"Size: <code>{size_str}</code>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Download File", callback_data=f"dl|{link}")],
                [InlineKeyboardButton("Stream Link", callback_data=f"stream|{link}")],
            ]),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Error processing {link}: {e}")
        await status.edit_text(
            f"<b>Error {tag}</b>\n<code>{str(e)[:500]}</code>",
            parse_mode=ParseMode.HTML,
        )


@app.on_callback_query(filters.regex(r"^(dl|stream)\|"))
async def callback_handler(client: Client, query):
    action, link = query.data.split("|", 1)
    if action == "dl":
        await download_video(client, query, link)
    else:
        await send_stream_link(client, query, link)


async def download_video(client: Client, query, link: str):
    async with download_semaphore:
        status_msg = query.message
        await status_msg.edit_text("<b>Starting download...</b>", parse_mode=ParseMode.HTML)
        try:
            auth = await get_auth_token()
            video_info = fetch_diskwala_video(link, auth)

            name = video_info.get("name", "video.mp4")
            download_url = video_info.get("downloadUrl")

            if not download_url:
                await status_msg.edit_text("<b>No download URL found</b>")
                return

            if "." not in name:
                name += ".mp4"
            name = "".join(c for c in name if c.isalnum() or c in " ._-"[:])
            out_path = os.path.join(DOWNLOAD_DIR, name)

            await status_msg.edit_text(f"<b>Downloading...</b>\n<code>{name}</code>", parse_mode=ParseMode.HTML)

            r = requests.get(download_url, stream=True, timeout=300, allow_redirects=True)
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            start_time = time.time()

            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        elapsed = time.time() - start_time
                        if elapsed > 0 and downloaded % (5 * 1024 * 1024) < 1024 * 1024:
                            speed = downloaded / elapsed
                            pct = (downloaded / total * 100) if total else 0
                            try:
                                await status_msg.edit_text(
                                    f"<b>Downloading...</b>\n<code>{name}</code>\n\n"
                                    f"Progress: {pct:.1f}%\n"
                                    f"Speed: {human_speed(speed)}\n"
                                    f"Size: {human_size(downloaded)} / {human_size(total)}",
                                    parse_mode=ParseMode.HTML,
                                )
                            except Exception:
                                pass

            await status_msg.edit_text("<b>Uploading to Telegram...</b>", parse_mode=ParseMode.HTML)
            await client.send_video(
                query.from_user.id, out_path,
                caption=f"<b>{name}</b>",
                parse_mode=ParseMode.HTML,
                supports_streaming=True,
            )
            await status_msg.delete()
            try:
                os.remove(out_path)
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Download error: {e}")
            await status_msg.edit_text(
                f"<b>Download failed</b>\n<code>{str(e)[:500]}</code>",
                parse_mode=ParseMode.HTML,
            )


async def send_stream_link(client: Client, query, link: str):
    try:
        auth = await get_auth_token()
        video_info = fetch_diskwala_video(link, auth)

        name = video_info.get("name", "video.mp4")
        size = video_info.get("size", 0)
        stream_url = video_info.get("streamUrl") or video_info.get("downloadUrl")

        if not stream_url:
            await query.message.edit_text("<b>No stream URL found</b>")
            return

        size_str = human_size(size) if size else "Unknown"
        await query.message.edit_text(
            f"<b>Stream Link Ready</b>\n\n"
            f"Name: <code>{name}</code>\n"
            f"Size: <code>{size_str}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Open Stream", url=stream_url)],
            ]),
        )
    except Exception as e:
        logger.error(f"Stream error: {e}")
        await query.message.edit_text(
            f"<b>Stream link failed</b>\n<code>{str(e)[:500]}</code>",
            parse_mode=ParseMode.HTML,
        )


if __name__ == "__main__":
    logger.info("Starting Diskwala Bot...")
    app.run()
