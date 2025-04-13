import asyncio
import os
import random
import json
import logging
import zipfile
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import aiohttp
from aiohttp import web
import discord
from discord.ext import commands
from discord import app_commands
import paramiko

# Импорт Py-SPW и моделей
import pyspw
from pyspw.models import User

# Настройка логирования
logging.basicConfig(
    filename='../backup_log.txt',
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

# Инициализация интентов
intents = discord.Intents.all()
intents.message_content = True
intents.members = True
intents.reactions = True

# Глобальные переменные и константы
AUTHORIZED_ROLE_ID = 1285274559477583907  # Роль для доступа к командам
OWNER_ID = 548076652857524244  # ID владельца
USER_IDS_TO_DELETE: List[int] = []  # ID пользователей для удаления сообщений
TARGET_MESSAGE_ID = 0  # ID сообщения для отслеживания реакций
LOG_FILE = "reaction_log.txt"
warnings: Dict[int, List[str]] = {}  # Словарь предупреждений

# Инициализация бота
bot = commands.Bot(command_prefix="$", intents=intents)

# Инициализация Py-SPW API
CARD_ID = "3a7d44ad-2b22-4e06-9a69-c48abfb0c3c6"
CARD_TOKEN = "uhsC+wHJJPBg0Cakt40FOu3ozK0e360l"
api = pyspw.SpApi(card_id=CARD_ID, card_token=CARD_TOKEN)

# Значения UUID по умолчанию, которые всегда должны присутствовать
DEFAULT_UUIDS = {
    "bafb0345bb574539a41b2a60117bf54e",
    "e2f3cb0fc74243ffbf4cc6dcef30879e",
    "c24a5dd5b50b4f7eac736ee8669e263b"
}

# -------------------------------
# SFTP-загрузка файла
# -------------------------------
def sftp_upload_file(local_filepath: str, remote_filepath: str) -> None:
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname="sosmark.ru",
            username="u3085459",
            password="VJQh12Rg7Sp0VNey"
        )
        with ssh.open_sftp() as sftp:
            sftp.put(local_filepath, remote_filepath)
        ssh.close()
        logging.info("Файл успешно загружен по SFTP.")
    except Exception as e:
        logging.error("Ошибка SFTP: %s", e)

# -------------------------------
# События бота
# -------------------------------
@bot.event
async def on_member_join(member: discord.Member) -> None:
    """При входе пользователя обновляем ник из SPWorlds и назначаем роль 'игрок'."""
    try:
        sp_user = await get_sp_user(str(member.id))
    except Exception as e:
        logging.error("Ошибка при получении SPUser для %s: %s", member.id, e)
        sp_user = None

    if sp_user and sp_user.nickname:
        try:
            await member.edit(nick=sp_user.nickname)
            logging.info("Ник для пользователя %s изменён на %s", member.id, sp_user.nickname)
        except discord.Forbidden:
            logging.error("Нет прав для изменения ника пользователя %s", member.id)
        except Exception as e:
            logging.error("Ошибка при изменении ника для %s: %s", member.id, e)

    role = discord.utils.get(member.guild.roles, name="игрок")
    if role:
        try:
            await member.add_roles(role)
            logging.info("Роль 'игрок' назначена пользователю %s", member.id)
        except discord.Forbidden:
            logging.error("Нет прав для назначения роли 'игрок' пользователю %s", member.id)
        except Exception as e:
            logging.error("Ошибка при назначении роли 'игрок' для %s: %s", member.id, e)
    else:
        logging.info("Роль 'игрок' не найдена. Пользователь %s остается без роли.", member.id)

@bot.event
async def on_ready() -> None:
    logging.info("Бот готов к работе!")
    await bot.change_presence(activity=discord.Game(name="Сосмарк"))
    await bot.tree.sync()  # Синхронизация slash-команд
    bot.loop.create_task(check_time())

@bot.event
async def on_message(message: discord.Message) -> None:
    # Пересылка личных сообщений владельцу
    if isinstance(message.channel, discord.DMChannel) and message.author != bot.user:
        owner = bot.get_user(OWNER_ID)
        if owner:
            embed = discord.Embed(title="Новое личное сообщение", color=discord.Color.blue())
            embed.add_field(name="Отправитель", value=message.author.name, inline=True)
            embed.add_field(name="Содержание", value=message.content, inline=False)
            if message.author.avatar:
                embed.set_thumbnail(url=message.author.avatar.url)
            embed.timestamp = datetime.now()
            try:
                await owner.send(embed=embed)
            except Exception as e:
                logging.error("Ошибка при пересылке ЛС: %s", e)
        else:
            logging.error("Владелец не найден для пересылки сообщения")

    # Удаление сообщений от пользователей, указанных в списке
    if message.author.id in USER_IDS_TO_DELETE:
        try:
            await message.delete()
            logging.info("Сообщение пользователя %s удалено.", message.author.name)
        except discord.Forbidden:
            logging.warning("Не удалось удалить сообщение пользователя %s (Запрещено).", message.author.name)
        except discord.HTTPException as e:
            logging.error("Ошибка при удалении сообщения пользователя %s: %s", message.author.name, e)

    await bot.process_commands(message)

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent) -> None:
    if payload.message_id == TARGET_MESSAGE_ID:
        user = bot.get_user(payload.user_id)
        emoji = payload.emoji
        log_entry = f"{user} добавил реакцию {emoji} на сообщение ID {TARGET_MESSAGE_ID}\n"
        with open(LOG_FILE, "a") as log:
            log.write(log_entry)
        logging.info(log_entry.strip())

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent) -> None:
    if payload.message_id == TARGET_MESSAGE_ID:
        user = bot.get_user(payload.user_id)
        emoji = payload.emoji
        log_entry = f"{user} удалил реакцию {emoji} с сообщения ID {TARGET_MESSAGE_ID}\n"
        with open(LOG_FILE, "a") as log:
            log.write(log_entry)
        logging.info(log_entry.strip())

# -------------------------------
# Вспомогательные функции
# -------------------------------
async def send_gif(channel: discord.abc.Messageable, gif_url: str) -> None:
    try:
        await channel.send(gif_url)
    except Exception as e:
        logging.error("Ошибка при отправке GIF: %s", e)

async def send_picture(channel: discord.abc.Messageable) -> None:
    picture_folder = 'aska'
    try:
        pictures = os.listdir(picture_folder)
        if pictures:
            picture_file = random.choice(pictures)
            picture_path = os.path.join(picture_folder, picture_file)
            await channel.send(file=discord.File(picture_path))
        else:
            logging.warning("Папка '%s' пуста.", picture_folder)
    except Exception as e:
        logging.error("Ошибка при отправке изображения: %s", e)

async def send_random_message(channel: discord.abc.Messageable) -> None:
    messages = [
        "Ave Sos, Ave Olus, Deus UwU!",
        "Слава нашему кайзеру!",
        "Брунчик я тебя люблю",
        "UwU",
        "OwO",
        "Наш кайзер самый лучший",
        "Кайзер пойдём нашиться под пледиком?",
        "Брунчик давай в танки поиграем",
        "Брунчик я купила водочки",
        "Gott mit uns",
        "Ты заставляешь мое сердце биться чаще.",
        "Строить корабли - важно",
        ":heart:",
        "Ня",
        "Мурр",
        "Трогать можно только бруно!",
        "Мяу",
        "Я делаю кущац",
        "https://cdn.discordapp.com/attachments/1220093141714206793/1237403955823120434/60.mov",
        "Очень жду вечный сон! :heart:",
        "Бомбить бомбить бомбить бомбить!",
        "Я думаю о Бруно с утра до вечера…",
        "Бруно такой мужественный и сильный, что мне всегда хочется скорее прижаться к нему…",
        "Моя жизнь сияет с того момента, как ты появился в ней!",
        "Ты принес свет в мою жизнь.",
        "Ты стал благословением в моей жизни.",
        "От тебя в груди трепещет всё — да так, что глаз не отвести.",
        "Гоп стоп, он подошёл из-за угла..."
    ]
    try:
        message = random.choice(messages)
        await channel.send(message)
    except Exception as e:
        logging.error("Ошибка при отправке случайного сообщения: %s", e)

async def check_time() -> None:
    while True:
        current_time = datetime.now(timezone.utc) + timedelta(hours=3)
        current_hour = current_time.hour
        current_minute = current_time.minute
        logging.info("Проверка времени: %s", current_time.isoformat())

        channel1 = bot.get_channel(1285274560102404199)
        channel2 = bot.get_channel(1285274562090766445)

        # 7:00 — отправка GIF-сообщения
        if current_hour == 7 and current_minute == 0 and channel1:
            await send_gif(channel1, 'https://tenor.com/view/asuka-langley-langley-asuka-evangelion-neon-genesis-evangelion-gif-8796834862117941782')
            logging.info("Отправлена гифка в 7:00")

        # Каждые 2 часа с 8 до 20:00 (на четных часах)
        if 8 <= current_hour <= 20 and current_hour % 2 == 0 and current_minute == 0 and channel1:
            await send_random_message(channel1)
            logging.info("Отправлено случайное сообщение в %s:00", current_hour)

        # 22:00 — отправка изображения
        if current_hour == 22 and current_minute == 0 and channel2:
            await send_picture(channel2)
            logging.info("Отправлено изображение в 22:00")

        # 23:00 — отправка GIF-сообщения
        if current_hour == 23 and current_minute == 0 and channel1:
            await send_gif(channel1, 'https://tenor.com/view/asuka-langley-gif-26114337')
            logging.info("Отправлена гифка в 23:00")

        await asyncio.sleep(60)

async def get_channel_messages(channel: discord.TextChannel, limit: int = 100) -> List[Dict[str, Any]]:
    messages = []
    try:
        async for msg in channel.history(limit=limit, oldest_first=True):
            messages.append({
                "id": msg.id,
                "author": {"name": msg.author.name, "id": msg.author.id},
                "content": msg.content,
                "timestamp": msg.created_at.isoformat(),
                "attachments": [attachment.url for attachment in msg.attachments]
            })
    except Exception as e:
        logging.error("Ошибка при получении сообщений для канала %s: %s", channel.id, e)
    return messages

async def get_sp_user(discord_user_id: str) -> User:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, api.get_user, discord_user_id)

# -------------------------------
# Проверка прав для команд
# -------------------------------
def has_authorized_role(interaction: discord.Interaction) -> bool:
    if interaction.user.id == OWNER_ID:
        return True
    return any(role.id == AUTHORIZED_ROLE_ID for role in interaction.user.roles)

# -------------------------------
# Slash-команды
# -------------------------------
@bot.tree.command(name="skhnotify", description="Уведомить пользователей в указанных ролях с сообщением")
@app_commands.describe(roles="Роли (через запятую, можно упоминания)", message="Сообщение")
@app_commands.check(has_authorized_role)
async def skhnotify(interaction: discord.Interaction, roles: str, message: str) -> None:
    roles_list = [role_str.strip() for role_str in roles.split(",")]
    found_roles = []
    for role_str in roles_list:
        if role_str.startswith("<@&") and role_str.endswith(">"):
            try:
                role_id = int(role_str[3:-1])
            except ValueError:
                role = None
            else:
                role = discord.utils.get(interaction.guild.roles, id=role_id)
        else:
            role = discord.utils.get(interaction.guild.roles, name=role_str)
        if role:
            found_roles.append(role)
        else:
            await interaction.response.send_message(f"Роль '{role_str}' не найдена.", ephemeral=True)
            logging.warning("Роль '%s' не найдена", role_str)
            return
    await interaction.response.send_message("Уведомление отправлено.", ephemeral=True)
    for role in found_roles:
        for member in role.members:
            try:
                await member.send(message)
                logging.info("Сообщение отправлено %s: %s", member.name, message)
            except discord.Forbidden:
                await interaction.followup.send(f"Не удалось отправить сообщение {member.name} (Запрещено)", ephemeral=True)
                logging.warning("Не удалось отправить сообщение %s (Запрещено)", member.name)
            except discord.HTTPException as e:
                await interaction.followup.send(f"Ошибка при отправке сообщения {member.name}: {e}", ephemeral=True)
                logging.error("Ошибка при отправке сообщения %s: %s", member.name, e)
            await asyncio.sleep(1)

@skhnotify.error
async def skhnotify_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("У вас нет прав для использования этой команды.", ephemeral=True)

@bot.tree.command(name="ban", description="Забанить пользователя на сервере.")
@app_commands.describe(user="Пользователь", reason="Причина бана")
@app_commands.check(has_authorized_role)
async def ban(interaction: discord.Interaction, user: discord.Member, reason: str = "Причина не указана") -> None:
    try:
        try:
            await user.send(f"Вы были забанены на сервере. Причина: {reason}")
        except discord.Forbidden:
            logging.warning("Не удалось отправить сообщение пользователю %s (Запрещено).", user.name)
        await user.ban(reason=reason)
        await interaction.response.send_message(f"Пользователь {user.mention} был забанен. Причина: {reason}")
    except discord.Forbidden:
        await interaction.response.send_message(f"У меня нет прав банить {user.mention}.", ephemeral=True)
    except discord.HTTPException as e:
        await interaction.response.send_message(f"Не удалось забанить {user.mention}. Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="send_message", description="Отправить сообщение в указанный канал")
@app_commands.describe(channel="Канал", message="Сообщение")
@app_commands.check(has_authorized_role)
async def send_message(interaction: discord.Interaction, channel: discord.TextChannel, message: str) -> None:
    try:
        await channel.send(message)
        await interaction.response.send_message(f"Сообщение отправлено в канал {channel.name}.", ephemeral=True)
        logging.info("Сообщение отправлено в канал %s", channel.name)
    except discord.HTTPException as e:
        await interaction.response.send_message(f"Ошибка при отправке сообщения в канал {channel.name}: {e}", ephemeral=True)
        logging.error("Ошибка при отправке сообщения в канал %s: %s", channel.name, e)

@bot.tree.command(name="reply", description="Переслать сообщение пользователю")
@app_commands.describe(user="Пользователь", message="Сообщение")
async def forward_message(interaction: discord.Interaction, user: discord.User, message: str) -> None:
    try:
        await user.send(message)
        await interaction.response.send_message(f"Сообщение отправлено {user.name}.", ephemeral=True)
        logging.info("Сообщение отправлено %s", user.name)
    except discord.Forbidden:
        await interaction.response.send_message(f"Не удалось отправить сообщение {user.name} (Запрещено).", ephemeral=True)
        logging.warning("Не удалось отправить сообщение %s (Запрещено).", user.name)
    except discord.HTTPException as e:
        await interaction.response.send_message(f"Ошибка при отправке сообщения {user.name}: {e}", ephemeral=True)
        logging.error("Ошибка при отправке сообщения %s: %s", user.name, e)

@forward_message.error
async def forward_message_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("У вас нет прав для использования этой команды.", ephemeral=True)

@bot.tree.command(name="backup", description="Создать резервную копию данных сервера с сообщениями.")
@app_commands.check(has_authorized_role)
async def backup(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    backup_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{guild.name}_{guild.id}_backup_{backup_time}.json"
    backup_dir = "../backups"
    os.makedirs(backup_dir, exist_ok=True)
    backup_filepath = os.path.join(backup_dir, backup_filename)

    channels_data = []
    for channel in guild.channels:
        channel_data: Dict[str, Any] = {
            "name": channel.name,
            "id": channel.id,
            "type": str(channel.type),
            "category": channel.category.name if channel.category else None,
            "position": channel.position
        }
        if isinstance(channel, discord.TextChannel):
            channel_data["topic"] = channel.topic
            channel_data["nsfw"] = channel.is_nsfw()
            channel_data["slowmode_delay"] = channel.slowmode_delay
            channel_data["messages"] = await get_channel_messages(channel, limit=100)
        channels_data.append(channel_data)

    guild_data = {
        "backup_created": backup_time,
        "guild_name": guild.name,
        "guild_id": guild.id,
        "owner_id": guild.owner_id,
        "roles": [
            {"name": role.name, "id": role.id, "permissions": role.permissions.value, "position": role.position}
            for role in guild.roles
        ],
        "channels": channels_data,
        "members": [
            {"name": member.name, "id": member.id, "roles": [role.name for role in member.roles]}
            for member in guild.members
        ]
    }

    try:
        with open(backup_filepath, "w", encoding='utf-8') as backup_file:
            json.dump(guild_data, backup_file, ensure_ascii=False, indent=4)
        logging.info("Backup JSON создан для сервера: %s (ID: %s)", guild.name, guild.id)
    except Exception as e:
        logging.error("Ошибка при создании JSON резервной копии: %s", e)
        await interaction.response.send_message("Ошибка при создании резервной копии.", ephemeral=True)
        return

    zip_filename = backup_filename.replace(".json", ".zip")
    zip_filepath = os.path.join(backup_dir, zip_filename)
    try:
        with zipfile.ZipFile(zip_filepath, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(backup_filepath, arcname=backup_filename)
        logging.info("Backup сжат в архив: %s", zip_filename)
    except Exception as e:
        logging.error("Ошибка при сжатии резервной копии: %s", e)
        await interaction.response.send_message("Ошибка при сжатии резервной копии.", ephemeral=True)
        return

    try:
        file_to_send = discord.File(zip_filepath, filename=zip_filename)
        await interaction.response.send_message("Резервная копия данных сервера успешно создана.", file=file_to_send, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Резервная копия создана, но не удалось отправить файл: {e}", ephemeral=True)
        logging.error("Ошибка при отправке файла резервной копии: %s", e)
    finally:
        logging.info("Backup process completed successfully.")

@backup.error
async def backup_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("У вас нет разрешения для выполнения этой команды.", ephemeral=True)
        logging.warning("Unauthorized backup attempt by %s (ID: %s)", interaction.user.name, interaction.user.id)
    else:
        await interaction.response.send_message("Произошла ошибка при создании резервной копии.", ephemeral=True)
        logging.error("Error during backup: %s", error)

@bot.tree.command(name="mcskin", description="Показать скин игрока Minecraft по его нику.")
async def mcskin(interaction: discord.Interaction, nickname: str) -> None:
    skin_url = f"https://minotar.net/avatar/{nickname}.png"
    embed = discord.Embed(title=f"Скин игрока {nickname}", color=discord.Color.green())
    embed.set_image(url=skin_url)
    embed.set_footer(text=f"Скин игрока {nickname} предоставлен Minotar")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="warn", description="Выдать предупреждение пользователю.")
@app_commands.describe(user="Пользователь", reason="Причина предупреждения")
@app_commands.check(has_authorized_role)
async def warn(interaction: discord.Interaction, user: discord.Member, reason: str) -> None:
    warnings.setdefault(user.id, []).append(reason)
    try:
        await user.send(f"Вы получили предупреждение на сервере. Причина: {reason}")
    except Exception as e:
        logging.warning("Не удалось отправить предупреждение %s: %s", user.name, e)
    await interaction.response.send_message(f"Пользователю {user.mention} выдано предупреждение. Причина: {reason}", ephemeral=True)
    if len(warnings[user.id]) >= 3:
        try:
            await user.ban(reason="Получено 3 предупреждения.")
            await interaction.followup.send(f"Пользователь {user.mention} был забанен за 3 предупреждения.", ephemeral=True)
        except Exception as e:
            logging.error("Ошибка при бане пользователя %s: %s", user.name, e)

@bot.tree.command(name="spam_user", description="Spam a user with a specified message.")
@app_commands.describe(user="Пользователь", message="Сообщение", count="Количество повторов")
@app_commands.check(has_authorized_role)
async def spam_user(interaction: discord.Interaction, user: discord.User, message: str, count: int) -> None:
    if count <= 0:
        await interaction.response.send_message("Количество должно быть больше 0.", ephemeral=True)
        return
    for _ in range(count):
        try:
            await user.send(message)
            logging.info("Spam сообщение отправлено %s", user.name)
            await asyncio.sleep(1)
        except discord.Forbidden:
            await interaction.response.send_message(f"Невозможно отправить сообщение {user.name} (Запрещено).", ephemeral=True)
            logging.warning("Невозможно отправить сообщение %s (Запрещено).", user.name)
            break
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Ошибка при отправке сообщения {user.name}: {e}", ephemeral=True)
            logging.error("Ошибка при отправке сообщения %s: %s", user.name, e)
            break
    await interaction.response.send_message(f"Отправлено {count} сообщений пользователю {user.name}.", ephemeral=True)

# -------------------------------
# Команды для Py-SPW
# -------------------------------
@bot.tree.command(name="set_nick", description="Изменить ник пользователя на основе данных SPWorlds.")
@app_commands.describe(discord_id="Discord ID пользователя")
@app_commands.check(has_authorized_role)
async def set_nick(interaction: discord.Interaction, discord_id: str) -> None:
    member = interaction.guild.get_member(int(discord_id))
    if member is None:
        await interaction.response.send_message("Пользователь с таким ID не найден.", ephemeral=True)
        return
    try:
        sp_user = await get_sp_user(discord_id)
    except Exception as e:
        await interaction.response.send_message(f"Ошибка при обращении к SP API: {e}", ephemeral=True)
        return
    nickname = sp_user.nickname if sp_user else None
    if not nickname:
        await interaction.response.send_message("Не удалось получить ник из SPWorlds.", ephemeral=True)
        return
    try:
        await member.edit(nick=nickname)
        await interaction.response.send_message(f"Ник {member.mention} изменён на **{nickname}**.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("Нет прав для изменения ника.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Ошибка при изменении ника: {e}", ephemeral=True)

@bot.tree.command(name="mcinfo", description="Получить информацию о игроке Minecraft через API Ashcon")
@app_commands.describe(username="Никнейм игрока")
async def mcinfo(interaction: discord.Interaction, username: str) -> None:
    url = f"https://api.ashcon.app/mojang/v2/user/{username}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    uuid_val = data.get("uuid", "Не найден")
                    username_resp = data.get("username", "Не найден")
                    textures = data.get("textures", {})
                    skin_url = textures.get("skin", {}).get("url", "Не найден")
                    embed = discord.Embed(title=f"Информация о {username_resp}", color=discord.Color.blue())
                    embed.add_field(name="UUID", value=uuid_val, inline=False)
                    embed.add_field(name="Скин", value=skin_url, inline=False)
                    embed.set_footer(text="Данные получены через API Ashcon")
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message("Не удалось получить информацию о пользователе.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Ошибка при запросе: {e}", ephemeral=True)
        logging.error("Ошибка в команде mcinfo: %s", e)

@bot.tree.command(name="update_all", description="Обновить ники всех участников на основе данных SPWorlds.")
@app_commands.check(has_authorized_role)
async def update_all(interaction: discord.Interaction) -> None:
    updated, failed = 0, 0
    await interaction.response.send_message("Начинаю обновление ников...", ephemeral=True)
    for member in interaction.guild.members:
        if member.bot:
            continue
        try:
            sp_user = await get_sp_user(str(member.id))
            nickname = sp_user.nickname if sp_user else None
            if nickname:
                await member.edit(nick=nickname)
                updated += 1
            else:
                failed += 1
        except Exception as e:
            logging.error("Ошибка при обновлении ника для %s: %s", member.id, e)
            failed += 1
        await asyncio.sleep(0.2)
    await interaction.followup.send(f"Обновление завершено. Успешно обновлено: {updated}, не обновлено: {failed}.", ephemeral=True)

async def get_minecraft_uuid(session: aiohttp.ClientSession, username: str) -> Optional[str]:
    await asyncio.sleep(1)  # Соблюдаем лимиты запросов
    url = f"https://api.mojang.com/users/profiles/minecraft/{username}"
    try:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("id")
            else:
                logging.info("Mojang API не нашел аккаунт %s (HTTP %s).", username, response.status)
                return None
    except Exception as e:
        logging.error("Ошибка при получении UUID для %s: %s", username, e)
        return None

@bot.tree.command(name="list_uuids", description="Собирает UUID игроков с целевыми ролями и загружает их по SFTP")
@app_commands.check(has_authorized_role)
async def list_uuids(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    target_role_ids = {1285274559498682547, 1285274559477583910}
    members = [m for m in interaction.guild.members if any(r.id in target_role_ids for r in m.roles)]
    uuids: List[str] = []
    async with aiohttp.ClientSession() as session:
        tasks = [get_minecraft_uuid(session, member.display_name) for member in members]
        results = await asyncio.gather(*tasks)
        for uuid_val in results:
            if uuid_val:
                uuids.append(uuid_val)
    uuid_list_json = json.dumps(uuids, indent=2, ensure_ascii=False)
    local_filename = "uuid_list.json"
    with open(local_filename, "w", encoding="utf-8") as f:
        f.write(uuid_list_json)
    remote_filepath = "/var/www/u3085459/data/www/sosmark.ru/uuid_list.json"
    await asyncio.get_running_loop().run_in_executor(None, sftp_upload_file, local_filename, remote_filepath)
    await interaction.followup.send(
        f"Список UUID:\n```json\n{uuid_list_json}\n``` \nФайл успешно загружен по SFTP на `{remote_filepath}`.",
        ephemeral=True
    )

# -------------------------------
# Запуск бота
# -------------------------------
async def main() -> None:
    await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен вручную.")
