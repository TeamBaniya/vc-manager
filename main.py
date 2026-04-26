from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import SessionRevoked, AuthKeyInvalid
import asyncio
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID
from database import db
import os

# Bot client
bot = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Store user sessions and voice calls
user_clients = {}
voice_calls = {}
user_states = {}  # For storing temporary data during group add
active_vc_groups = {}  # Store which group has active VC

# SUDO FILTER
def sudo_only(func):
    async def wrapper(client, message):
        user_id = message.from_user.id
        if user_id == OWNER_ID or db.is_sudo(user_id):
            return await func(client, message)
        else:
            await message.reply("❌ You are not authorized to use this command!")
    return wrapper

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔌 Connect Session", callback_data="connect")],
        [InlineKeyboardButton("📊 Status", callback_data="status")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ])
    await message.reply(
        "**🎵 VC Manager Bot**\n\n"
        "I can manage multiple accounts to join voice chats!\n\n"
        "🔹 Click 'Connect Session' to add your pyrogram string sessions\n"
        "🔹 Use /add to add a group for VC\n"
        "🔹 Use /joinvc <count> to join voice chat\n\n"
        f"**Total sessions added:** {db.get_session_count()}",
        reply_markup=keyboard
    )

@bot.on_callback_query()
async def handle_callbacks(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if data == "connect":
        user_states[user_id] = {"step": "awaiting_session"}
        await callback_query.message.reply(
            "📱 **Send your Pyrogram String Session**\n\n"
            "How to get string session:\n"
            "1. Use @StringSessionBot on Telegram\n"
            "2. Generate your session string\n"
            "3. Send it here\n\n"
            "Type /done when you finish adding all sessions"
        )
    
    elif data == "status":
        total = db.get_session_count()
        sessions = db.get_all_sessions()
        status_text = f"**📊 Status Report**\n\n"
        status_text += f"**Total Sessions:** {total}\n"
        status_text += f"**Active Connections:** {len(user_clients)}\n\n"
        
        if sessions:
            status_text += "**📱 Session List:**\n"
            for idx, session in enumerate(sessions, 1):
                status_text += f"{idx}. {session[3]} (@{session[4] or 'No username'})\n"
        
        group = db.get_active_group()
        if group:
            status_text += f"\n**🎯 Active Group:** {group[2]}\n"
            status_text += f"**Type:** {group[3]}\n"
        
        await callback_query.message.reply(status_text)
    
    elif data == "help":
        help_text = """
**🤖 Bot Commands:**

/start - Start the bot
/add - Add a group for voice chat
/joinvc <count> - Join voice chat with X accounts
/leavevc - Leave current voice chat
/play - Reply to an audio to play in VC
/stop - Stop playing audio
/status - Check sessions and group status
/done - Finish adding sessions

**Sudo Commands:**
/addsudo <user_id> - Add sudo user
/rmsudo <user_id> - Remove sudo user

**Private Group Process:**
1. Use /add command
2. Select 'Private Group'
3. Send invite link
4. Send chat_id for confirmation
"""
        await callback_query.message.reply(help_text)
    
    elif data == "public_group":
        user_states[user_id] = {"step": "public_username", "type": "public"}
        await callback_query.message.reply("📝 Send the group **@username** (example: @mygroup)")
    
    elif data == "private_group":
        user_states[user_id] = {"step": "private_link", "type": "private"}
        await callback_query.message.reply("🔗 Send the group **invite link**")

@bot.on_message(filters.command("done") & filters.private)
async def done_command(client, message):
    total = db.get_session_count()
    await message.reply(f"✅ **Done!**\n\nTotal sessions saved: **{total}**\n\nUse /status to see all sessions\nUse /add to add a group")
    
    # Clean up user state
    if message.from_user.id in user_states:
        del user_states[message.from_user.id]

@bot.on_message(filters.private & filters.text)
async def handle_messages(client, message):
    user_id = message.from_user.id
    text = message.text
    
    # Handle session string input
    if user_id in user_states and user_states[user_id].get("step") == "awaiting_session":
        if len(text) > 100:  # Pyrogram session string check
            try:
                # Try to create client with session
                test_client = Client(f"sessions/user_{user_id}_{len(user_clients)}", 
                                    api_id=API_ID, 
                                    api_hash=API_HASH, 
                                    session_string=text)
                await test_client.start()
                me = await test_client.get_me()
                await test_client.stop()
                
                # Save to database
                db.add_session(text, me.id, me.first_name, me.username or "")
                await message.reply(f"✅ **Session added successfully!**\n\n"
                                   f"Name: {me.first_name}\n"
                                   f"ID: {me.id}\n"
                                   f"Username: @{me.username or 'None'}\n\n"
                                   f"Total sessions: {db.get_session_count()}\n"
                                   f"Send more sessions or type /done")
                
            except Exception as e:
                await message.reply(f"❌ **Invalid session!**\nError: {str(e)}\n\nPlease send a valid Pyrogram string session.")
        else:
            await message.reply("❌ Invalid session string format!\n\nUse @StringSessionBot to get valid string.")
        
        return
    
    # Handle public group username
    if user_id in user_states and user_states[user_id].get("step") == "public_username":
        username = text.strip()
        if username.startswith("@"):
            username = username[1:]
        
        try:
            # Resolve username to get group info
            group = await client.get_chat(username)
            if group.type in ["group", "supergroup"]:
                db.add_group(group.id, group.title, "public", username, None, group.id, user_id)
                await message.reply(f"✅ **Group connected successfully!**\n\n"
                                   f"📌 Name: {group.title}\n"
                                   f"🔗 Username: @{username}\n"
                                   f"🆔 Chat ID: {group.id}\n\n"
                                   f"Now use /joinvc <count> to join voice chat")
                if user_id in user_states:
                    del user_states[user_id]
            else:
                await message.reply("❌ This is not a group!")
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}\n\nMake sure the username is correct and group is accessible.")
        
        return
    
    # Handle private group invite link
    if user_id in user_states and user_states[user_id].get("step") == "private_link":
        invite_link = text.strip()
        await message.reply("📝 Now send the **Chat ID** of the group\n\nGet chat ID from @chatIDBot or any id bot\n\nExample: -1001234567890")
        user_states[user_id] = {"step": "private_chatid", "type": "private", "link": invite_link}
        return
    
    # Handle private group chat_id
    if user_id in user_states and user_states[user_id].get("step") == "private_chatid":
        chat_id = int(text)
        invite_link = user_states[user_id]["link"]
        
        try:
            # Try to get group info using chat_id
            group = await client.get_chat(chat_id)
            if group.type in ["group", "supergroup"]:
                db.add_group(group.id, group.title, "private", None, invite_link, chat_id, user_id)
                await message.reply(f"✅ **Private group connected!**\n\n"
                                   f"📌 Name: {group.title}\n"
                                   f"🆔 Chat ID: {group.id}\n"
                                   f"🔗 Link: {invite_link}\n\n"
                                   f"Now use /joinvc <count> to join voice chat")
                if user_id in user_states:
                    del user_states[user_id]
            else:
                await message.reply("❌ Invalid chat ID or not a group!")
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}\n\nMake sure chat_id is correct and bot is in group.")
        
        return

@bot.on_message(filters.command("add") & filters.private)
@sudo_only
async def add_group_command(client, message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Public Group", callback_data="public_group")],
        [InlineKeyboardButton("🔒 Private Group", callback_data="private_group")]
    ])
    await message.reply("**Select group type:**", reply_markup=keyboard)

@bot.on_message(filters.command("joinvc") & filters.private)
@sudo_only
async def join_vc_command(client, message):
    args = message.text.split()
    if len(args) != 2:
        await message.reply("❌ Usage: /joinvc <count>\nExample: /joinvc 5")
        return
    
    try:
        count = int(args[1])
    except ValueError:
        await message.reply("❌ Count must be a number!")
        return
    
    # Get active group
    group = db.get_active_group()
    if not group:
        await message.reply("❌ No group added! Use /add first.")
        return
    
    # Get chat_id correctly
    if group[3] == "public":
        # Public group - resolve username to chat_id
        username = group[4]
        try:
            chat = await client.get_chat(username)
            chat_id = chat.id
        except:
            await message.reply("❌ Failed to resolve group! Make sure username is correct.")
            return
    else:
        # Private group - use stored chat_id
        chat_id = group[6]
    
    group_name = group[2]
    
    # Get all sessions
    sessions = db.get_all_sessions()
    if len(sessions) == 0:
        await message.reply("❌ No sessions found! Use /start and connect sessions first.")
        return
    
    if count > len(sessions):
        await message.reply(f"❌ Only {len(sessions)} sessions available. Can't join {count} accounts.")
        return
    
    await message.reply(f"🎤 **Joining voice chat...**\n\n"
                       f"📌 Group: {group_name}\n"
                       f"👥 Accounts: {count}/{len(sessions)}\n"
                       f"⏳ Please wait...")
    
    joined = 0
    failed = 0
    
    for idx, session_data in enumerate(sessions[:count], 1):
        session_string = session_data[1]
        user_name = session_data[3]
        
        try:
            # Create client if not exists
            if user_name not in user_clients:
                client_obj = Client(f"sessions/active_{user_name}", 
                                   api_id=API_ID, 
                                   api_hash=API_HASH, 
                                   session_string=session_string)
                await client_obj.start()
                user_clients[user_name] = client_obj
                
                # Initialize voice call
                vc = PyTgCalls(client_obj)
                await vc.start()
                voice_calls[user_name] = vc
            
            # Join the voice chat
            vc_obj = voice_calls[user_name]
            await vc_obj.join_group_call(chat_id)
            joined += 1
            
            await message.reply(f"✅ {idx}. {user_name} joined VC")
            
        except Exception as e:
            failed += 1
            await message.reply(f"❌ {user_name} failed: {str(e)[:50]}")
        
        await asyncio.sleep(2)  # Delay to avoid flood wait
    
    active_vc_groups[message.from_user.id] = chat_id
    
    final_msg = f"**🎉 Voice Chat Joined!**\n\n"
    final_msg += f"✅ Successfully joined: {joined}\n"
    final_msg += f"❌ Failed: {failed}\n"
    final_msg += f"📍 Group: {group_name}\n\n"
    final_msg += f"Use /play to play audio\nUse /leavevc to leave"
    
    await message.reply(final_msg)

@bot.on_message(filters.command("leavevc") & filters.private)
@sudo_only
async def leave_vc_command(client, message):
    if len(voice_calls) == 0:
        await message.reply("❌ No active voice chats!")
        return
    
    left = 0
    for name, vc in voice_calls.items():
        try:
            await vc.leave_group_call()
            left += 1
        except:
            pass
    
    await message.reply(f"✅ {left} accounts left the voice chat!")

@bot.on_message(filters.command("play") & filters.private)
@sudo_only
async def play_audio_command(client, message):
    if not message.reply_to_message:
        await message.reply("❌ Reply to an audio file with /play command")
        return
    
    if not message.reply_to_message.audio:
        await message.reply("❌ Reply to an audio file only!")
        return
    
    if len(voice_calls) == 0:
        await message.reply("❌ No active voice calls! Use /joinvc first.")
        return
    
    # Download audio
    msg = await message.reply("📥 Downloading audio...")
    audio_path = await message.reply_to_message.download("audio/")
    
    await msg.edit_text("🎵 Playing audio in all connected VCs...")
    
    played = 0
    for name, vc in voice_calls.items():
        try:
            # For py-tgcalls 2.2.8 - using MediaStream
            await vc.change_stream(MediaStream(audio_path))
            played += 1
        except Exception as e:
            await message.reply(f"❌ Failed on {name}: {str(e)[:50]}")
    
    await msg.edit_text(f"✅ Audio playing in {played}/{len(voice_calls)} voice chats!")

@bot.on_message(filters.command("stop") & filters.private)
@sudo_only
async def stop_audio_command(client, message):
    if len(voice_calls) == 0:
        await message.reply("❌ No active voice calls!")
        return
    
    stopped = 0
    for name, vc in voice_calls.items():
        try:
            await vc.stop_stream()
            stopped += 1
        except:
            pass
    
    await message.reply(f"⏹️ Stopped audio in {stopped} voice chats!")

@bot.on_message(filters.command("status") & filters.private)
@sudo_only
async def status_command(client, message):
    total_sessions = db.get_session_count()
    active_sessions = len(user_clients)
    active_vc = len(voice_calls)
    group = db.get_active_group()
    
    status_text = f"**📊 Bot Status**\n\n"
    status_text += f"📱 Total sessions: {total_sessions}\n"
    status_text += f"🟢 Active clients: {active_sessions}\n"
    status_text += f"🎤 Active VCs: {active_vc}\n"
    
    if group:
        status_text += f"\n**Current Group:**\n"
        status_text += f"📌 Name: {group[2]}\n"
        status_text += f"🔒 Type: {group[3]}\n"
    
    await message.reply(status_text)

@bot.on_message(filters.command("addsudo") & filters.private)
async def add_sudo_command(client, message):
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ Only bot owner can add sudo users!")
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.reply("❌ Usage: /addsudo <user_id>")
        return
    
    try:
        sudo_id = int(args[1])
        db.add_sudo(sudo_id, OWNER_ID)
        await message.reply(f"✅ User {sudo_id} added as sudo user!")
    except:
        await message.reply("❌ Invalid user ID!")

@bot.on_message(filters.command("rmsudo") & filters.private)
async def remove_sudo_command(client, message):
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ Only bot owner can remove sudo users!")
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.reply("❌ Usage: /rmsudo <user_id>")
        return
    
    try:
        sudo_id = int(args[1])
        db.remove_sudo(sudo_id)
        await message.reply(f"✅ User {sudo_id} removed from sudo!")
    except:
        await message.reply("❌ Invalid user ID!")

async def main():
    # Create necessary directories
    os.makedirs("sessions", exist_ok=True)
    os.makedirs("audio", exist_ok=True)
    
    print("🚀 Bot is starting...")
    await bot.start()
    print(f"✅ Bot started as @{(await bot.get_me()).username}")
    print(f"📊 Total sessions in DB: {db.get_session_count()}")
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
