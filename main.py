# main.py - FINAL WORKING VERSION
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
import asyncio
import logging
import traceback
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID
from database import db
import os
import signal
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Bot client
bot = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Store user sessions and voice calls
user_clients = {}
voice_calls = {}
user_states = {}
active_vc_groups = {}

print("\n" + "="*50)
print("🤖 BOT IS STARTING...")
print("="*50)

# SUDO FILTER
def sudo_only(func):
    async def wrapper(client, message):
        user_id = message.from_user.id
        if user_id == OWNER_ID or db.is_sudo(user_id):
            return await func(client, message)
        else:
            await message.reply("❌ You are not authorized!")
    return wrapper

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    try:
        print(f"✅ Start command from {message.from_user.id}")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔌 Connect Session", callback_data="connect")],
            [InlineKeyboardButton("📊 Status", callback_data="status")],
            [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
        ])
        await message.reply(
            "**🎵 VC Manager Bot**\n\n"
            "🔹 Click 'Connect Session' to add pyrogram sessions\n"
            "🔹 Use /add to add a group\n"
            "🔹 Use /joinvc <count> to join voice chat\n\n"
            f"**Total sessions:** {db.get_session_count()}",
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"Error: {e}")
        await message.reply(f"Error: {e}")

@bot.on_callback_query()
async def handle_callbacks(client, callback_query: CallbackQuery):
    try:
        data = callback_query.data
        user_id = callback_query.from_user.id
        print(f"Callback: {data} from {user_id}")
        
        if data == "connect":
            user_states[user_id] = {"step": "awaiting_session"}
            await callback_query.message.reply(
                "📱 **Send Pyrogram String Session**\n\n"
                "Get from @StringSessionBot\n"
                "Type /done when finished"
            )
        
        elif data == "status":
            total = db.get_session_count()
            sessions = db.get_all_sessions()
            status_text = f"**📊 Status**\n\nTotal: {total}\nActive: {len(user_clients)}\n\n"
            if sessions:
                for idx, s in enumerate(sessions, 1):
                    status_text += f"{idx}. {s[3]}\n"
            await callback_query.message.reply(status_text)
        
        elif data == "help":
            help_text = """
**Commands:**
/start - Start bot
/add - Add group
/joinvc <count> - Join VC
/leavevc - Leave VC
/play - Play audio (reply to audio)
/stop - Stop audio
/status - Check status
/done - Finish adding sessions
"""
            await callback_query.message.reply(help_text)
        
        elif data == "public_group":
            user_states[user_id] = {"step": "public_username"}
            await callback_query.message.reply("Send group @username")
        
        elif data == "private_group":
            user_states[user_id] = {"step": "private_link"}
            await callback_query.message.reply("Send invite link")
            
    except Exception as e:
        print(f"Callback error: {e}")
        await callback_query.message.reply(f"Error: {e}")

@bot.on_message(filters.command("done") & filters.private)
async def done_command(client, message):
    total = db.get_session_count()
    await message.reply(f"✅ Done! Total sessions: {total}")
    if message.from_user.id in user_states:
        del user_states[message.from_user.id]

@bot.on_message(filters.command("add") & filters.private)
@sudo_only
async def add_group_command(client, message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Public", callback_data="public_group")],
        [InlineKeyboardButton("🔒 Private", callback_data="private_group")]
    ])
    await message.reply("Select group type:", reply_markup=keyboard)

@bot.on_message(filters.command("joinvc") & filters.private)
@sudo_only
async def join_vc_command(client, message):
    try:
        args = message.text.split()
        if len(args) != 2:
            await message.reply("Usage: /joinvc <count>")
            return
        
        count = int(args[1])
        group = db.get_active_group()
        
        if not group:
            await message.reply("No group added! Use /add")
            return
        
        # Get chat_id
        if group[3] == "public":
            username = group[4]
            chat = await client.get_chat(username)
            chat_id = chat.id
        else:
            chat_id = group[6]
        
        group_name = group[2]
        sessions = db.get_all_sessions()
        
        if count > len(sessions):
            await message.reply(f"Only {len(sessions)} sessions available")
            return
        
        await message.reply(f"Joining {count} accounts to {group_name}...")
        
        joined = 0
        for idx, session_data in enumerate(sessions[:count], 1):
            session_string = session_data[1]
            user_name = session_data[3]
            
            try:
                if user_name not in user_clients:
                    client_obj = Client(f"sessions/{user_name}", 
                                       api_id=API_ID, 
                                       api_hash=API_HASH, 
                                       session_string=session_string)
                    await client_obj.start()
                    user_clients[user_name] = client_obj
                    
                    vc = PyTgCalls(client_obj)
                    await vc.start()
                    voice_calls[user_name] = vc
                
                await voice_calls[user_name].join_group_call(chat_id)
                joined += 1
                await message.reply(f"✅ {idx}. {user_name} joined")
                
            except Exception as e:
                await message.reply(f"❌ {user_name}: {str(e)[:30]}")
            
            await asyncio.sleep(1)
        
        await message.reply(f"✅ Joined: {joined}/{count}")
        
    except Exception as e:
        print(f"JoinVC error: {e}")
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("leavevc") & filters.private)
@sudo_only
async def leave_vc_command(client, message):
    left = 0
    for name, vc in voice_calls.items():
        try:
            await vc.leave_group_call()
            left += 1
        except:
            pass
    voice_calls.clear()
    await message.reply(f"✅ {left} accounts left")

@bot.on_message(filters.command("play") & filters.private)
@sudo_only
async def play_audio_command(client, message):
    if not message.reply_to_message or not message.reply_to_message.audio:
        await message.reply("Reply to an audio with /play")
        return
    
    if not voice_calls:
        await message.reply("No active VC! Use /joinvc first")
        return
    
    msg = await message.reply("Downloading audio...")
    audio_path = await message.reply_to_message.download("audio/")
    
    await msg.edit_text("Playing audio...")
    played = 0
    
    for name, vc in voice_calls.items():
        try:
            await vc.change_stream(MediaStream(audio_path))
            played += 1
        except Exception as e:
            await message.reply(f"Failed on {name}: {str(e)[:30]}")
    
    await msg.edit_text(f"✅ Playing in {played}/{len(voice_calls)} VCs")

@bot.on_message(filters.command("stop") & filters.private)
@sudo_only
async def stop_audio_command(client, message):
    stopped = 0
    for name, vc in voice_calls.items():
        try:
            await vc.stop_stream()
            stopped += 1
        except:
            pass
    await message.reply(f"⏹️ Stopped in {stopped} VCs")

@bot.on_message(filters.command("status") & filters.private)
@sudo_only
async def status_command(client, message):
    status_text = f"""
**Bot Status**
📱 Sessions: {db.get_session_count()}
🟢 Active: {len(user_clients)}
🎤 In VC: {len(voice_calls)}
"""
    await message.reply(status_text)

@bot.on_message(filters.command("addsudo") & filters.private)
async def add_sudo_command(client, message):
    if message.from_user.id != OWNER_ID:
        await message.reply("Only owner can use this")
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.reply("Usage: /addsudo <user_id>")
        return
    
    db.add_sudo(int(args[1]), OWNER_ID)
    await message.reply(f"✅ Sudo user added")

@bot.on_message(filters.command("rmsudo") & filters.private)
async def remove_sudo_command(client, message):
    if message.from_user.id != OWNER_ID:
        await message.reply("Only owner can use this")
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.reply("Usage: /rmsudo <user_id>")
        return
    
    db.remove_sudo(int(args[1]))
    await message.reply(f"✅ Sudo user removed")

@bot.on_message(filters.private & filters.text)
async def handle_messages(client, message):
    user_id = message.from_user.id
    text = message.text
    
    if text.startswith('/'):
        return
    
    # Handle session input
    if user_id in user_states and user_states[user_id].get("step") == "awaiting_session":
        if len(text) > 50:
            try:
                test_client = Client(f"temp_{user_id}", 
                                   api_id=API_ID, 
                                   api_hash=API_HASH, 
                                   session_string=text)
                await test_client.start()
                me = await test_client.get_me()
                await test_client.stop()
                
                db.add_session(text, me.id, me.first_name, me.username or "")
                await message.reply(f"✅ Added: {me.first_name}\nTotal: {db.get_session_count()}")
                
            except Exception as e:
                await message.reply(f"❌ Invalid session: {e}")
    
    # Handle public username
    elif user_id in user_states and user_states[user_id].get("step") == "public_username":
        username = text.replace('@', '')
        try:
            group = await client.get_chat(username)
            db.add_group(group.id, group.title, "public", username, None, group.id, user_id)
            await message.reply(f"✅ Added: {group.title}\nUse /joinvc <count>")
            del user_states[user_id]
        except Exception as e:
            await message.reply(f"❌ Error: {e}")
    
    # Handle private link
    elif user_id in user_states and user_states[user_id].get("step") == "private_link":
        user_states[user_id] = {"step": "private_chatid", "link": text}
        await message.reply("Send chat_id (example: -1001234567890)")
    
    # Handle private chat_id
    elif user_id in user_states and user_states[user_id].get("step") == "private_chatid":
        try:
            chat_id = int(text)
            invite_link = user_states[user_id]["link"]
            group = await client.get_chat(chat_id)
            db.add_group(group.id, group.title, "private", None, invite_link, chat_id, user_id)
            await message.reply(f"✅ Added: {group.title}\nUse /joinvc <count>")
            del user_states[user_id]
        except Exception as e:
            await message.reply(f"❌ Error: {e}")

def signal_handler(sig, frame):
    print("\n\n⚠️ Stopping bot...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

async def main():
    os.makedirs("sessions", exist_ok=True)
    os.makedirs("audio", exist_ok=True)
    
    print("🚀 Starting bot...")
    await bot.start()
    
    me = await bot.get_me()
    print(f"✅ Bot running as @{me.username}")
    print(f"📊 Sessions in DB: {db.get_session_count()}")
    print("\n Waiting for commands...\n")
    
    # Keep bot running
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n Bot stopped")
