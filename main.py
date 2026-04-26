from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import SessionRevoked, AuthKeyInvalid
import asyncio
import traceback
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
user_states = {}
active_vc_groups = {}

# PRINT: Bot starting
print("=" * 50)
print("🤖 BOT IS INITIALIZING...")
print("=" * 50)

# SUDO FILTER
def sudo_only(func):
    async def wrapper(client, message):
        user_id = message.from_user.id
        print(f"🔐 Sudo check for user: {user_id}")
        print(f"   Owner ID: {OWNER_ID}")
        print(f"   Is Sudo: {db.is_sudo(user_id)}")
        
        if user_id == OWNER_ID or db.is_sudo(user_id):
            print(f"   ✅ User {user_id} authorized")
            return await func(client, message)
        else:
            print(f"   ❌ User {user_id} NOT authorized")
            await message.reply("❌ You are not authorized to use this command!")
    return wrapper

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    try:
        print(f"\n📨 START command received from user: {message.from_user.id}")
        print(f"   Message text: {message.text}")
        
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
        print(f"   ✅ Start command response sent")
        
    except Exception as e:
        print(f"   ❌ Error in start command: {e}")
        print(traceback.format_exc())
        await message.reply(f"❌ Error: {str(e)}")

@bot.on_callback_query()
async def handle_callbacks(client, callback_query: CallbackQuery):
    try:
        data = callback_query.data
        user_id = callback_query.from_user.id
        print(f"\n📞 Callback query received from user: {user_id}")
        print(f"   Callback data: {data}")
        
        if data == "connect":
            print(f"   📱 Setting up connect session for user {user_id}")
            user_states[user_id] = {"step": "awaiting_session"}
            await callback_query.message.reply(
                "📱 **Send your Pyrogram String Session**\n\n"
                "How to get string session:\n"
                "1. Use @StringSessionBot on Telegram\n"
                "2. Generate your session string\n"
                "3. Send it here\n\n"
                "Type /done when you finish adding all sessions"
            )
            print(f"   ✅ Connect message sent")
        
        elif data == "status":
            print(f"   📊 Getting status for user {user_id}")
            total = db.get_session_count()
            sessions = db.get_all_sessions()
            print(f"   Total sessions in DB: {total}")
            print(f"   Active clients: {len(user_clients)}")
            
            status_text = f"**📊 Status Report**\n\n"
            status_text += f"**Total Sessions:** {total}\n"
            status_text += f"**Active Connections:** {len(user_clients)}\n\n"
            
            if sessions:
                status_text += "**📱 Session List:**\n"
                for idx, session in enumerate(sessions, 1):
                    status_text += f"{idx}. {session[3]} (@{session[4] or 'No username'})\n"
                    print(f"   Session {idx}: {session[3]}")
            
            group = db.get_active_group()
            if group:
                status_text += f"\n**🎯 Active Group:** {group[2]}\n"
                status_text += f"**Type:** {group[3]}\n"
                print(f"   Active group: {group[2]} ({group[3]})")
            
            await callback_query.message.reply(status_text)
            print(f"   ✅ Status response sent")
        
        elif data == "help":
            print(f"   ℹ️ Sending help to user {user_id}")
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
"""
            await callback_query.message.reply(help_text)
            print(f"   ✅ Help sent")
        
        elif data == "public_group":
            print(f"   🌐 Setting up public group for user {user_id}")
            user_states[user_id] = {"step": "public_username", "type": "public"}
            await callback_query.message.reply("📝 Send the group **@username** (example: @mygroup)")
            print(f"   ✅ Waiting for username")
        
        elif data == "private_group":
            print(f"   🔒 Setting up private group for user {user_id}")
            user_states[user_id] = {"step": "private_link", "type": "private"}
            await callback_query.message.reply("🔗 Send the group **invite link**")
            print(f"   ✅ Waiting for invite link")
        
    except Exception as e:
        print(f"   ❌ Error in callback: {e}")
        print(traceback.format_exc())
        await callback_query.message.reply(f"❌ Error: {str(e)}")

@bot.on_message(filters.command("done") & filters.private)
async def done_command(client, message):
    try:
        print(f"\n✅ DONE command from user {message.from_user.id}")
        total = db.get_session_count()
        print(f"   Total sessions: {total}")
        
        await message.reply(f"✅ **Done!**\n\nTotal sessions saved: **{total}**\n\nUse /status to see all sessions\nUse /add to add a group")
        
        if message.from_user.id in user_states:
            del user_states[message.from_user.id]
            print(f"   Cleared user state")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        await message.reply(f"❌ Error: {str(e)}")

@bot.on_message(filters.command("add") & filters.private)
@sudo_only
async def add_group_command(client, message):
    try:
        print(f"\n➕ ADD command from user {message.from_user.id}")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 Public Group", callback_data="public_group")],
            [InlineKeyboardButton("🔒 Private Group", callback_data="private_group")]
        ])
        await message.reply("**Select group type:**", reply_markup=keyboard)
        print(f"   ✅ Group type selection sent")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        await message.reply(f"❌ Error: {str(e)}")

@bot.on_message(filters.command("joinvc") & filters.private)
@sudo_only
async def join_vc_command(client, message):
    try:
        print(f"\n🎤 JOINVC command from user {message.from_user.id}")
        print(f"   Full command: {message.text}")
        
        args = message.text.split()
        print(f"   Args: {args}")
        
        if len(args) != 2:
            print(f"   ❌ Invalid argument count")
            await message.reply("❌ Usage: /joinvc <count>\nExample: /joinvc 5")
            return
        
        try:
            count = int(args[1])
            print(f"   Count to join: {count}")
        except ValueError:
            print(f"   ❌ Count is not a number")
            await message.reply("❌ Count must be a number!")
            return
        
        # Get active group
        group = db.get_active_group()
        print(f"   Active group from DB: {group}")
        
        if not group:
            print(f"   ❌ No group found")
            await message.reply("❌ No group added! Use /add first.")
            return
        
        # Get chat_id correctly
        if group[3] == "public":
            username = group[4]
            print(f"   Public group username: {username}")
            try:
                chat = await client.get_chat(username)
                chat_id = chat.id
                print(f"   Resolved chat_id: {chat_id}")
            except Exception as e:
                print(f"   ❌ Failed to resolve group: {e}")
                await message.reply("❌ Failed to resolve group! Make sure username is correct.")
                return
        else:
            chat_id = group[6]
            print(f"   Private group chat_id: {chat_id}")
        
        group_name = group[2]
        print(f"   Group name: {group_name}")
        
        # Get all sessions
        sessions = db.get_all_sessions()
        print(f"   Total sessions in DB: {len(sessions)}")
        
        if len(sessions) == 0:
            print(f"   ❌ No sessions found")
            await message.reply("❌ No sessions found! Use /start and connect sessions first.")
            return
        
        if count > len(sessions):
            print(f"   ❌ Count exceeds available sessions")
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
            print(f"   Processing account {idx}: {user_name}")
            
            try:
                # Create client if not exists
                if user_name not in user_clients:
                    print(f"      Creating new client for {user_name}")
                    client_obj = Client(f"sessions/active_{user_name}", 
                                       api_id=API_ID, 
                                       api_hash=API_HASH, 
                                       session_string=session_string)
                    await client_obj.start()
                    user_clients[user_name] = client_obj
                    print(f"      Client started for {user_name}")
                    
                    # Initialize voice call
                    print(f"      Initializing PyTgCalls for {user_name}")
                    vc = PyTgCalls(client_obj)
                    await vc.start()
                    voice_calls[user_name] = vc
                    print(f"      Voice call initialized for {user_name}")
                
                # Join the voice chat
                print(f"      Joining voice chat for {user_name} in chat_id: {chat_id}")
                vc_obj = voice_calls[user_name]
                await vc_obj.join_group_call(chat_id)
                joined += 1
                print(f"      ✅ {user_name} joined successfully")
                
                await message.reply(f"✅ {idx}. {user_name} joined VC")
                
            except Exception as e:
                failed += 1
                print(f"      ❌ {user_name} failed: {e}")
                print(traceback.format_exc())
                await message.reply(f"❌ {user_name} failed: {str(e)[:50]}")
            
            await asyncio.sleep(2)
        
        active_vc_groups[message.from_user.id] = chat_id
        
        final_msg = f"**🎉 Voice Chat Joined!**\n\n"
        final_msg += f"✅ Successfully joined: {joined}\n"
        final_msg += f"❌ Failed: {failed}\n"
        final_msg += f"📍 Group: {group_name}\n\n"
        final_msg += f"Use /play to play audio\nUse /leavevc to leave"
        
        await message.reply(final_msg)
        print(f"   ✅ JoinVC completed: {joined} joined, {failed} failed")
        
    except Exception as e:
        print(f"   ❌ Exception in joinvc: {e}")
        print(traceback.format_exc())
        await message.reply(f"❌ Error: {str(e)}")

@bot.on_message(filters.command("status") & filters.private)
@sudo_only
async def status_command(client, message):
    try:
        print(f"\n📊 STATUS command from user {message.from_user.id}")
        
        total_sessions = db.get_session_count()
        active_sessions = len(user_clients)
        active_vc = len(voice_calls)
        group = db.get_active_group()
        
        print(f"   Total sessions: {total_sessions}")
        print(f"   Active clients: {active_sessions}")
        print(f"   Active VCs: {active_vc}")
        
        status_text = f"**📊 Bot Status**\n\n"
        status_text += f"📱 Total sessions: {total_sessions}\n"
        status_text += f"🟢 Active clients: {active_sessions}\n"
        status_text += f"🎤 Active VCs: {active_vc}\n"
        
        if group:
            status_text += f"\n**Current Group:**\n"
            status_text += f"📌 Name: {group[2]}\n"
            status_text += f"🔒 Type: {group[3]}\n"
            print(f"   Current group: {group[2]}")
        
        await message.reply(status_text)
        print(f"   ✅ Status response sent")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        await message.reply(f"❌ Error: {str(e)}")

@bot.on_message(filters.command("play") & filters.private)
@sudo_only
async def play_audio_command(client, message):
    try:
        print(f"\n🎵 PLAY command from user {message.from_user.id}")
        
        if not message.reply_to_message:
            print(f"   ❌ No reply to message")
            await message.reply("❌ Reply to an audio file with /play command")
            return
        
        if not message.reply_to_message.audio:
            print(f"   ❌ No audio found in reply")
            await message.reply("❌ Reply to an audio file only!")
            return
        
        if len(voice_calls) == 0:
            print(f"   ❌ No active voice calls")
            await message.reply("❌ No active voice calls! Use /joinvc first.")
            return
        
        print(f"   Downloading audio...")
        msg = await message.reply("📥 Downloading audio...")
        audio_path = await message.reply_to_message.download("audio/")
        print(f"   Audio downloaded to: {audio_path}")
        
        await msg.edit_text("🎵 Playing audio in all connected VCs...")
        
        played = 0
        for name, vc in voice_calls.items():
            try:
                print(f"   Playing audio in {name}'s VC")
                await vc.change_stream(MediaStream(audio_path))
                played += 1
                print(f"   ✅ Audio playing in {name}")
            except Exception as e:
                print(f"   ❌ Failed on {name}: {e}")
                await message.reply(f"❌ Failed on {name}: {str(e)[:50]}")
        
        await msg.edit_text(f"✅ Audio playing in {played}/{len(voice_calls)} voice chats!")
        print(f"   ✅ Play completed: {played} success")
        
    except Exception as e:
        print(f"   ❌ Error in play: {e}")
        print(traceback.format_exc())
        await message.reply(f"❌ Error: {str(e)}")

@bot.on_message(filters.command("leavevc") & filters.private)
@sudo_only
async def leave_vc_command(client, message):
    try:
        print(f"\n🚪 LEAVEVC command from user {message.from_user.id}")
        
        if len(voice_calls) == 0:
            print(f"   ❌ No active voice chats")
            await message.reply("❌ No active voice chats!")
            return
        
        left = 0
        for name, vc in voice_calls.items():
            try:
                print(f"   Leaving VC for {name}")
                await vc.leave_group_call()
                left += 1
                print(f"   ✅ {name} left")
            except Exception as e:
                print(f"   ❌ {name} failed to leave: {e}")
        
        voice_calls.clear()
        print(f"   Total left: {left}")
        await message.reply(f"✅ {left} accounts left the voice chat!")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        await message.reply(f"❌ Error: {str(e)}")

@bot.on_message(filters.command("stop") & filters.private)
@sudo_only
async def stop_audio_command(client, message):
    try:
        print(f"\n⏹️ STOP command from user {message.from_user.id}")
        
        if len(voice_calls) == 0:
            print(f"   ❌ No active voice calls")
            await message.reply("❌ No active voice calls!")
            return
        
        stopped = 0
        for name, vc in voice_calls.items():
            try:
                print(f"   Stopping audio for {name}")
                await vc.stop_stream()
                stopped += 1
                print(f"   ✅ Stopped for {name}")
            except Exception as e:
                print(f"   ❌ Failed to stop for {name}: {e}")
        
        await message.reply(f"⏹️ Stopped audio in {stopped} voice chats!")
        print(f"   Stopped: {stopped}")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        await message.reply(f"❌ Error: {str(e)}")

@bot.on_message(filters.command("addsudo") & filters.private)
async def add_sudo_command(client, message):
    try:
        print(f"\n👑 ADDSUDO command from user {message.from_user.id}")
        
        if message.from_user.id != OWNER_ID:
            print(f"   ❌ Not owner")
            await message.reply("❌ Only bot owner can add sudo users!")
            return
        
        args = message.text.split()
        if len(args) != 2:
            print(f"   ❌ Invalid args")
            await message.reply("❌ Usage: /addsudo <user_id>")
            return
        
        sudo_id = int(args[1])
        print(f"   Adding sudo user: {sudo_id}")
        db.add_sudo(sudo_id, OWNER_ID)
        await message.reply(f"✅ User {sudo_id} added as sudo user!")
        print(f"   ✅ Sudo user added")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        await message.reply(f"❌ Error: {str(e)}")

@bot.on_message(filters.command("rmsudo") & filters.private)
async def remove_sudo_command(client, message):
    try:
        print(f"\n👑 RMSSUDO command from user {message.from_user.id}")
        
        if message.from_user.id != OWNER_ID:
            print(f"   ❌ Not owner")
            await message.reply("❌ Only bot owner can remove sudo users!")
            return
        
        args = message.text.split()
        if len(args) != 2:
            print(f"   ❌ Invalid args")
            await message.reply("❌ Usage: /rmsudo <user_id>")
            return
        
        sudo_id = int(args[1])
        print(f"   Removing sudo user: {sudo_id}")
        db.remove_sudo(sudo_id)
        await message.reply(f"✅ User {sudo_id} removed from sudo!")
        print(f"   ✅ Sudo user removed")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        await message.reply(f"❌ Error: {str(e)}")

@bot.on_message(filters.private & filters.text)
async def handle_messages(client, message):
    try:
        user_id = message.from_user.id
        text = message.text
        
        # Skip if it's a command
        if text.startswith('/'):
            print(f"\n📝 Skipping command in handle_messages: {text}")
            return
        
        print(f"\n📨 Private message from {user_id}: {text[:50]}...")
        print(f"   User state: {user_states.get(user_id)}")
        
        # Handle session string input
        if user_id in user_states and user_states[user_id].get("step") == "awaiting_session":
            print(f"   Processing session string...")
            if len(text) > 100:
                try:
                    print(f"   Testing session string...")
                    test_client = Client(f"sessions/user_{user_id}_{len(user_clients)}", 
                                        api_id=API_ID, 
                                        api_hash=API_HASH, 
                                        session_string=text)
                    await test_client.start()
                    me = await test_client.get_me()
                    await test_client.stop()
                    
                    print(f"   Session valid! User: {me.first_name} (ID: {me.id})")
                    db.add_session(text, me.id, me.first_name, me.username or "")
                    await message.reply(f"✅ **Session added successfully!**\n\n"
                                       f"Name: {me.first_name}\n"
                                       f"ID: {me.id}\n"
                                       f"Username: @{me.username or 'None'}\n\n"
                                       f"Total sessions: {db.get_session_count()}\n"
                                       f"Send more sessions or type /done")
                    print(f"   ✅ Session saved")
                    
                except Exception as e:
                    print(f"   ❌ Invalid session: {e}")
                    await message.reply(f"❌ **Invalid session!**\nError: {str(e)}\n\nPlease send a valid Pyrogram string session.")
            else:
                print(f"   ❌ String too short: {len(text)} chars")
                await message.reply("❌ Invalid session string format!\n\nUse @StringSessionBot to get valid string.")
            
            return
        
    except Exception as e:
        print(f"   ❌ Error in handle_messages: {e}")
        print(traceback.format_exc())

async def main():
    print("\n" + "=" * 50)
    print("🚀 STARTING BOT...")
    print("=" * 50)
    
    # Create necessary directories
    os.makedirs("sessions", exist_ok=True)
    os.makedirs("audio", exist_ok=True)
    print("📁 Directories created: sessions/, audio/")
    
    print("🔌 Connecting to Telegram...")
    await bot.start()
    
    bot_info = await bot.get_me()
    print(f"✅ Bot started as: @{bot_info.username}")
    print(f"   Bot ID: {bot_info.id}")
    print(f"📊 Total sessions in DB: {db.get_session_count()}")
    
    print("\n" + "=" * 50)
    print("🤖 BOT IS RUNNING!")
    print("📝 Check Telegram: Send /start to your bot")
    print("🐛 Debug logs will appear here")
    print("=" * 50 + "\n")
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        print(traceback.format_exc())
