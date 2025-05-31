import logging
import logging.config
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Union, Optional, AsyncGenerator
from datetime import date, datetime
import pytz
import asyncio

# Logging config (your original)
logging.config.fileConfig('logging.conf')
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("imdbpy").setLevel(logging.ERROR)
logging.getLogger("asyncio").setLevel(logging.CRITICAL -1)

import tgcrypto
from pyrogram import Client, __version__
from pyrogram.raw.all import layer
from database.ia_filterdb import Media
from database.users_chats_db import db
from info import SESSION, API_ID, API_HASH, BOT_TOKEN, LOG_STR, LOG_CHANNEL, AUTH_CHANNEL
from utils import temp, is_subscribed, get_poster  # <-- added these utils
from pyrogram import types
from Script import script

# peer id invalid fix
from pyrogram import utils as pyroutils
pyroutils.MIN_CHAT_ID = -999999999999
pyroutils.MIN_CHANNEL_ID = -100999999999999

from plugins.webcode import bot_run
from os import environ
from aiohttp import web as webserver

PORT_CODE = environ.get("PORT", "8080")


class Bot(Client):

    def __init__(self):
        super().__init__(
            name=SESSION,
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=50,
            plugins={"root": "plugins"},
            sleep_threshold=5,
        )

    async def start(self):
        b_users, b_chats = await db.get_banned()
        temp.BANNED_USERS = b_users
        temp.BANNED_CHATS = b_chats
        await super().start()
        await Media.ensure_indexes()
        me = await self.get_me()
        temp.ME = me.id
        temp.U_NAME = me.username
        temp.B_NAME = me.first_name
        self.username = '@' + me.username
        logging.info(f"{me.first_name} with for Pyrogram v{__version__} (Layer {layer}) started on {me.username}.")
        logging.info(LOG_STR)
        await self.send_message(chat_id=LOG_CHANNEL, text=script.RESTART_TXT)
        print("Goutham SER own Bot</>")

        tz = pytz.timezone('Asia/Kolkata')
        today = date.today()
        now = datetime.now(tz)
        time = now.strftime("%H:%M:%S %p")
        await self.send_message(chat_id=LOG_CHANNEL, text=script.RESTART_GC_TXT.format(today, time))
        client = webserver.AppRunner(await bot_run())
        await client.setup()
        bind_address = "0.0.0.0"
        await webserver.TCPSite(client, bind_address, int(PORT_CODE)).start()

        # Register handlers after startup
        self.add_handler(self.start_handler)
        self.add_handler(self.help_handler)
        self.add_handler(self.movie_details_handler)

    async def stop(self, *args):
        await super().stop()
        logging.info("Bot stopped. Bye.")

    async def iter_messages(
        self,
        chat_id: Union[int, str],
        limit: int,
        offset: int = 0,
    ) -> Optional[AsyncGenerator["types.Message", None]]:
        current = offset
        while True:
            new_diff = min(200, limit - current)
            if new_diff <= 0:
                return
            messages = await self.get_messages(chat_id, list(range(current, current + new_diff + 1)))
            for message in messages:
                yield message
                current += 1

    # Handler definitions below
    @Client.on_message(filters.command("start") & filters.private)
    async def start_handler(self, client, message):
        text = (
            "👋 Hello! Welcome to the bot.\n\n"
            "You can send me an IMDb movie name or ID to get details."
        )
        await message.reply_text(text)

    @Client.on_message(filters.command("help") & filters.private)
    async def help_handler(self, client, message):
        text = (
            "ℹ️ *Help Menu*\n\n"
            "• Send me a movie name or IMDb ID to get details.\n"
            "• You must be subscribed to the updates channel to use me.\n"
            f"• Channel: https://t.me/{AUTH_CHANNEL.lstrip('@')}"
        )
        await message.reply_text(text, parse_mode="markdown")

  @Client.on_message(filters.private & filters.text & ~filters.command([]))
    async def movie_details_handler(self, client, message):
        # Check subscription first
        subscribed = await is_subscribed(client, message)
        if not subscribed:
            await message.reply_text(
                f"❌ You must join the channel first: https://t.me/{AUTH_CHANNEL.lstrip('@')}"
            )
            return

        query = message.text.strip()
        await message.reply_chat_action("typing")

        movie = await get_poster(query)
        if not movie:
            await message.reply_text("❌ Sorry, no movie found for your query.")
            return

        text = (
            f"🎬 *{movie['title']}* ({movie.get('year', 'N/A')})\n"
            f"⭐ Rating: {movie.get('rating', 'N/A')}\n"
            f"📅 Released: {movie.get('release_date', 'N/A')}\n"
            f"🎭 Genre: {movie.get('genres', 'N/A')}\n\n"
            f"📝 Plot:\n{movie.get('plot', 'N/A')}\n\n"
            f"[IMDb Link]({movie['url']})"
        )
        buttons = InlineKeyboardMarkup(
            [[InlineKeyboardButton("IMDb Link", url=movie['url'])]]
        )

        if movie.get('poster'):
            await message.reply_photo(photo=movie['poster'], caption=text, parse_mode="markdown", reply_markup=buttons)
        else:
            await message.reply_text(text, parse_mode="markdown", reply_markup=buttons)


app = Bot()
from pyrogram.types import Message
from pyrogram import filters

@app.on_message(filters.private & filters.text & ~filters.command([]))
async def handle_user_messages(client, message: Message):
    await message.reply("Hi! You sent a normal message.")
app.run()