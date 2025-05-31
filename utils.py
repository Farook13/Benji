import logging
import re
import os
import asyncio
from typing import Union, List
from pyrogram import enums
from pyrogram.types import Message
from pyrogram.errors import InputUserDeactivated, UserNotParticipant, FloodWait, UserIsBlocked, PeerIdInvalid
from imdb import IMDb
from bs4 import BeautifulSoup
import requests

from info import AUTH_CHANNEL, LONG_IMDB_DESCRIPTION, MAX_LIST_ELM
from database.users_chats_db import db

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BTN_URL_REGEX = re.compile(
    r"(\[([^\[]+?)\]\((buttonurl|buttonalert):(?:/{0,2})(.+?)(:same)?\))"
)

imdb = IMDb()

SMART_OPEN = '“'
SMART_CLOSE = '”'
START_CHAR = ('\'', '"', SMART_OPEN)


class temp(object):
    BANNED_USERS = []
    BANNED_CHATS = []
    ME = None
    CURRENT = int(os.environ.get("SKIP", 2))
    CANCEL = False
    MELCOW = {}
    U_NAME = None
    B_NAME = None
    SETTINGS = {}


async def is_subscribed(bot, query):
    try:
        user = await bot.get_chat_member(AUTH_CHANNEL, query.from_user.id)
        return user.status != 'kicked'
    except UserNotParticipant:
        logger.info(f"User {query.from_user.id} is not a participant in the channel.")
    except PeerIdInvalid:
        logger.error(f"AUTH_CHANNEL ID invalid or no access: {AUTH_CHANNEL}")
    except Exception as e:
        logger.exception(f"Unexpected error checking subscription status for user {query.from_user.id}: {e}")
    return False


async def get_poster(query, bulk=False, id=False, file=None):
    if not id:
        query = (query.strip()).lower()
        title = query
        year = re.findall(r'[1-2]\d{3}$', query, re.IGNORECASE)
        if year:
            year = year[0]
            title = (query.replace(year, "")).strip()
        elif file is not None:
            year = re.findall(r'[1-2]\d{3}', file, re.IGNORECASE)
            year = year[0] if year else None
        else:
            year = None
        movieid = imdb.search_movie(title.lower(), results=10)
        if not movieid:
            return None
        if year:
            filtered = list(filter(lambda k: str(k.get('year')) == str(year), movieid))
            if not filtered:
                filtered = movieid
        else:
            filtered = movieid
        movieid = list(filter(lambda k: k.get('kind') in ['movie', 'tv series'], filtered))
        if not movieid:
            movieid = filtered
        if bulk:
            return movieid
        movieid = movieid[0].movieID
    else:
        movieid = query
    movie = imdb.get_movie(movieid)
    if movie.get("original air date"):
        date = movie["original air date"]
    elif movie.get("year"):
        date = movie.get("year")
    else:
        date = "N/A"
    plot = ""
    if not LONG_IMDB_DESCRIPTION:
        plot = movie.get('plot')
        if plot and len(plot) > 0:
            plot = plot[0]
    else:
        plot = movie.get('plot outline')
    if plot and len(plot) > 800:
        plot = plot[0:800] + "..."

    return {
        'title': movie.get('title'),
        'votes': movie.get('votes'),
        "aka": list_to_str(movie.get("akas")),
        "seasons": movie.get("number of seasons"),
        "box_office": movie.get('box office'),
        'localized_title': movie.get('localized title'),
        'kind': movie.get("kind"),
        "imdb_id": f"tt{movie.get('imdbID')}",
        "cast": list_to_str(movie.get("cast")),
        "runtime": list_to_str(movie.get("runtimes")),
        "countries": list_to_str(movie.get("countries")),
        "certificates": list_to_str(movie.get("certificates")),
        "languages": list_to_str(movie.get("languages")),
        "director": list_to_str(movie.get("director")),
        "writer": list_to_str(movie.get("writer")),
        "producer": list_to_str(movie.get("producer")),
        "composer": list_to_str(movie.get("composer")),
        "cinematographer": list_to_str(movie.get("cinematographer")),
        "music_team": list_to_str(movie.get("music department")),
        "distributors": list_to_str(movie.get("distributors")),
        'release_date': date,
        'year': movie.get('year'),
        'genres': list_to_str(movie.get("genres")),
        'poster': movie.get('full-size cover url'),
        'plot': plot,
        'rating': str(movie.get("rating")),
        'url': f'https://www.imdb.com/title/tt{movieid}'
    }


async def broadcast_messages(user_id, message):
    while True:
        try:
            await message.copy(chat_id=user_id)
            return True, "Success"
        except FloodWait as e:
            await asyncio.sleep(e.x)
        except InputUserDeactivated:
            await db.delete_user(int(user_id))
            logger.info(f"{user_id} removed from DB: deleted account.")
            return False, "Deleted"
        except UserIsBlocked:
            logger.info(f"{user_id} blocked the bot.")
            return False, "Blocked"
        except PeerIdInvalid:
            await db.delete_user(int(user_id))
            logger.info(f"{user_id} invalid peer ID.")
            return False, "Error"
        except Exception as e:
            logger.error(f"Error broadcasting to {user_id}: {e}")
            return False, "Error"


async def search_gagala(text):
    usr_agent = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/61.0.3163.100 Safari/537.36'
    }
    text = text.replace(" ", '+')
    url = f'https://www.google.com/search?q={text}'
    response = requests.get(url, headers=usr_agent)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    titles = soup.find_all('h3')
    return [title.getText() for title in titles]


async def get_settings(group_id):
    settings = temp.SETTINGS.get(group_id)
    if not settings:
        settings = await db.get_settings(group_id)
        temp.SETTINGS[group_id] = settings
    return settings


async def save_group_settings(group_id, key, value):
    current = await get_settings(group_id)
    current[key] = value
    temp.SETTINGS[group_id] = current
    await db.update_settings(group_id, current)


def get_size(size):
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units) - 1:
        size /= 1024.0
        i += 1
    return "%.2f %s" % (size, units[i])


def split_list(l, n):
    for i in range(0, len(l), n):
        yield l[i:i + n]


def get_file_id(msg: Message):
    if msg.media:
        for message_type in (
            "photo",
            "animation",
            "audio",
            "document",
            "video",
            "video_note",
            "voice",
            "sticker"
        ):
            obj = getattr(msg, message_type)
            if obj:
                setattr(obj, "message_type", message_type)
                return obj


def extract_user(message: Message) -> Union[int, str]:
    user_id = None
    user_first_name = None
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        user_first_name = message.reply_to_message.from_user.first_name

    elif len(message.command) > 1:
        if len(message.entities) > 1 and message.entities[1].type == enums.MessageEntityType.TEXT_MENTION:
            required_entity = message.entities[1]
            user_id = required_entity.user.id
            user_first_name = required_entity.user.first_name
        else:
            user_id = message.command[1]
            user_first_name = user_id
        try:
            user_id = int(user_id)
        except ValueError:
            pass
    else:
        user_id = message.from_user.id
        user_first_name = message.from_user.first_name
    return user_id, user_first_name


def list_to_str(k):
    if not k:
        return "N/A"
    if len(k) == 1:
        return str(k[0])
    if MAX_LIST_ELM:
        k = k[:int(MAX_LIST_ELM)]
    return ', '.join(str(elem) for elem in k)


def last_online(from_user):
    if from_user.is_bot:
        return "🤖 Bot"
    if from_user.status is None:
        return "Unknown"
    # from_user.status is a ChatMemberStatus or similar, we want the last seen time
    # Unfortunately pyrogram User object does not expose last_online directly,
    # so we often can't get this info without extra calls.
    # So let's try to access the 'last_online_date' attribute if exists (pyrogram 2.x)
    last_seen = getattr(from_user, "last_online_date", None)
    if last_seen:
        from datetime import datetime
        delta = datetime.utcnow() - last_seen
        if delta.days > 0:
            return f"Last seen {delta.days} day(s) ago"
        elif delta.seconds >= 3600:
            return f"Last seen {delta.seconds // 3600} hour(s) ago"
        elif delta.seconds >= 60:
            return f"Last seen {delta.seconds // 60} minute(s) ago"
        else:
            return "Last seen just now"
    return "Last seen info unavailable"