import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import BOT_TOKEN, API_ID, API_HASH
from account_manager import AccountManager
from vc_manager import VCManager
from database import Database

# Bot client
bot = Client("bot_session", API_ID, API_HASH, bot_token=BOT_TOKEN)

# Global objects
acc_mgr = AccountManager()
db = Database()
vc_mgr = None
accounts_loaded = False

async def initialize_vc():
    global vc_mgr, accounts_loaded
    if vc_mgr is None:
        clients = await acc_mgr.load_all_sessions()
        if clients:
            vc_mgr = VCManager(clients)
            accounts_loaded = True
            print(f"✅ {len(clients)} accounts loaded")
        else:
            print("❌ No accounts found! Use /add_account first")
            accounts_loaded = False

@bot.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    await message.reply_text(
        "🎵 **VC Manager Bot**\n\n"
        "**Commands:**\n"
        "/add_account - Add new Telegram account\n"
        "/add_group - Add group for VC management\n"
        "/list_groups - Show all configured groups\n"
        "/start_vc [group_id] - Start VC for a group\n"
        "/stop_vc [group_id] - Stop VC for a group\n"
        "/status - Check accounts status\n"
        "/remove_group [group_id] - Remove group config\n\n"
        "**First time setup:**\n"
        "1. Add accounts using /add_account\n"
        "2. Add groups using /add_group\n"
        "3. Start VC using /start_vc"
    )

@bot.on_message(filters.command("add_account"))
async def add_account_command(client: Client, message: Message):
    await message.reply_text("📱 **Send phone number with country code:**\nExample: `+91XXXXXXXXXX`")
    
    response = await bot.wait_for_message(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        timeout=60
    )
    
    if response and response.text:
        phone = response.text.strip()
        status_msg = await message.reply_text(f"🔄 Processing `{phone}`...\nCheck console for OTP prompt.")
        
        session_file = await acc_mgr.create_new_session(phone)
        if session_file:
            await status_msg.edit_text(f"✅ Account `{phone}` added successfully!\nUse `/reset` to reload accounts.")
        else:
            await status_msg.edit_text(f"❌ Failed to add `{phone}`. Check console logs.")
    else:
        await message.reply_text("⏰ Timeout or invalid input.")

@bot.on_message(filters.command("add_group"))
async def add_group_command(client: Client, message: Message):
    """Inline buttons ke saath group add karna"""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌍 Public Group", callback_data="group_type_public"),
            InlineKeyboardButton("🔒 Private Group", callback_data="group_type_private")
        ]
    ])
    
    await message.reply_text(
        "**Select group type:**\n\n"
        "• **Public Group** - Group username se connect (e.g., @mygroup)\n"
        "• **Private Group** - Invite link se connect",
        reply_markup=keyboard
    )

@bot.on_callback_query()
async def handle_callback(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    
    if data.startswith("group_type_"):
        group_type = data.replace("group_type_", "")
        
        # Store in temporary user data
        if not hasattr(bot, "temp_data"):
            bot.temp_data = {}
        
        bot.temp_data[callback_query.from_user.id] = {"group_type": group_type}
        
        if group_type == "public":
            await callback_query.message.edit_text(
                "📢 **Public Group Setup**\n\n"
                "Send the **group username** (without @):\n"
                "Example: `my_public_group`\n\n"
                "Or send the invite link if it's a public channel."
            )
        else:
            await callback_query.message.edit_text(
                "🔒 **Private Group Setup**\n\n"
                "Send the **invite link**:\n"
                "Example: `https://t.me/+abc123xyz`\n\n"
                "Bot accounts will join the group using this link."
            )
        
        # Wait for user input
        response = await bot.wait_for_message(
            chat_id=callback_query.message.chat.id,
            user_id=callback_query.from_user.id,
            timeout=120
        )
        
        if response and response.text:
            identifier = response.text.strip()
            group_id = f"group_{callback_query.from_user.id}_{int(asyncio.get_event_loop().time())}"
            
            # Save to database
            db.add_group(group_id, group_type, identifier)
            
            await response.reply_text(
                f"✅ **Group added successfully!**\n\n"
                f"**Group ID:** `{group_id}`\n"
                f"**Type:** {group_type.upper()}\n"
                f"**Identifier:** `{identifier}`\n\n"
                f"Use `/start_vc {group_id}` to start voice chat."
            )
        else:
            await callback_query.message.reply_text("⏰ Timeout or invalid input.")
        
        await callback_query.answer()

@bot.on_message(filters.command("list_groups"))
async def list_groups_command(client: Client, message: Message):
    groups = db.get_all_groups()
    
    if not groups:
        await message.reply_text("❌ No groups configured. Use `/add_group` first.")
        return
    
    text = "**📋 Configured Groups:**\n\n"
    for group_id, config in groups.items():
        text += f"**ID:** `{group_id}`\n"
        text += f"**Type:** {config['type'].upper()}\n"
        text += f"**Identifier:** `{config['identifier']}`\n"
        text += f"**Status:** {'🟢 Active' if config.get('active', True) else '🔴 Inactive'}\n"
        text += "──────────────────\n"
    
    text += "\nUse `/start_vc <group_id>` to start VC\n"
    text += "Use `/stop_vc <group_id>` to stop VC"
    
    await message.reply_text(text)

@bot.on_message(filters.command("start_vc"))
async def start_vc_command(client: Client, message: Message):
    if not accounts_loaded:
        await initialize_vc()
    
    if vc_mgr is None or not vc_mgr.clients:
        await message.reply_text("❌ No accounts loaded! Use `/add_account` first.")
        return
    
    # Get group ID from command
    parts = message.text.split()
    if len(parts) < 2:
        # Show list of available groups
        groups = db.get_all_groups()
        if not groups:
            await message.reply_text("❌ No groups configured. Use `/add_group` first.")
            return
        
        keyboard = []
        for group_id, config in groups.items():
            keyboard.append([
                InlineKeyboardButton(
                    f"{config['type'].upper()}: {config['identifier'][:20]}", 
                    callback_data=f"start_vc_{group_id}"
                )
            ])
        
        await message.reply_text(
            "**Select group to start VC:**",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    group_id = parts[1]
    group_config = db.get_group(group_id)
    
    if not group_config:
        await message.reply_text(f"❌ Group `{group_id}` not found. Use `/add_group` first.")
        return
    
    await message.reply_text(f"🎙️ Starting all accounts in VC for group `{group_id}`...")
    success_count = await vc_mgr.start_all_for_group(group_config, group_id)
    await message.reply_text(f"✅ {success_count} accounts joined the VC!")

@bot.on_message(filters.command("stop_vc"))
async def stop_vc_command(client: Client, message: Message):
    parts = message.text.split()
    
    if len(parts) < 2:
        # Show list of active groups
        if not vc_mgr or not vc_mgr.active_sessions:
            await message.reply_text("❌ No active VC sessions.")
            return
        
        keyboard = []
        for group_id in vc_mgr.active_sessions.keys():
            if vc_mgr.active_sessions[group_id]:
                config = db.get_group(group_id)
                if config:
                    keyboard.append([
                        InlineKeyboardButton(
                            f"{config['type'].upper()}: {config['identifier'][:20]}", 
                            callback_data=f"stop_vc_{group_id}"
                        )
                    ])
        
        if not keyboard:
            await message.reply_text("❌ No active VC sessions.")
            return
        
        await message.reply_text(
            "**Select group to stop VC:**",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    group_id = parts[1]
    
    if vc_mgr and group_id in vc_mgr.active_sessions:
        await vc_mgr.stop_all_for_group(group_id)
        await message.reply_text(f"✅ All accounts left VC for group `{group_id}`.")
    else:
        await message.reply_text(f"❌ No active VC session for group `{group_id}`.")

@bot.on_message(filters.command("status"))
async def status_command(client: Client, message: Message):
    if vc_mgr and vc_mgr.clients:
        text = f"📊 **Bot Status**\n\n"
        text += f"**Total accounts loaded:** {len(vc_mgr.clients)}\n"
        
        active_groups = len([g for g in vc_mgr.active_sessions if vc_mgr.active_sessions[g]])
        text += f"**Active groups:** {active_groups}\n\n"
        
        if active_groups > 0:
            text += "**Active VC Sessions:**\n"
            for group_id, sessions in vc_mgr.active_sessions.items():
                if sessions:
                    config = db.get_group(group_id)
                    if config:
                        text += f"• `{group_id}` - {config['type'].upper()}: {config['identifier'][:30]}\n"
                        text += f"  👥 {len(sessions)} accounts in VC\n"
        
        text += "\n**Loaded Accounts:**\n"
        for idx, c in enumerate(vc_mgr.clients, 1):
            try:
                me = await c.get_me()
                text += f"{idx}. {me.first_name} (@{me.username or 'no username'})\n"
            except:
                text += f"{idx}. Unknown account\n"
        
        await message.reply_text(text)
    else:
        await message.reply_text("❌ No active accounts. Use `/add_account` first.")

@bot.on_message(filters.command("remove_group"))
async def remove_group_command(client: Client, message: Message):
    parts = message.text.split()
    
    if len(parts) < 2:
        # Show list of groups
        groups = db.get_all_groups()
        if not groups:
            await message.reply_text("❌ No groups configured.")
            return
        
        keyboard = []
        for group_id, config in groups.items():
            keyboard.append([
                InlineKeyboardButton(
                    f"{config['type'].upper()}: {config['identifier'][:20]}", 
                    callback_data=f"remove_group_{group_id}"
                )
            ])
        
        await message.reply_text(
            "**Select group to remove:**",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    group_id = parts[1]
    
    # Stop VC if active
    if vc_mgr and group_id in vc_mgr.active_sessions:
        await vc_mgr.stop_all_for_group(group_id)
    
    # Remove from database
    db.remove_group(group_id)
    await message.reply_text(f"✅ Group `{group_id}` removed successfully.")

@bot.on_message(filters.command("reset"))
async def reset_command(client: Client, message: Message):
    global vc_mgr, accounts_loaded
    await message.reply_text("🔄 Reloading all accounts...")
    
    if vc_mgr:
        # Stop all active sessions
        for group_id in list(vc_mgr.active_sessions.keys()):
            await vc_mgr.stop_all_for_group(group_id)
    
    vc_mgr = None
    accounts_loaded = False
    await initialize_vc()
    
    if accounts_loaded:
        await message.reply_text(f"✅ Reloaded {len(acc_mgr.accounts)} accounts.")
    else:
        await message.reply_text("⚠️ No sessions found. Use `/add_account` first.")

# Handle callback for start/stop/remove
@bot.on_callback_query()
async def handle_vc_callbacks(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    
    if data.startswith("start_vc_"):
        group_id = data.replace("start_vc_", "")
        group_config = db.get_group(group_id)
        
        if not group_config:
            await callback_query.answer("Group not found!", show_alert=True)
            return
        
        if not accounts_loaded:
            await initialize_vc()
        
        if not vc_mgr or not vc_mgr.clients:
            await callback_query.answer("No accounts loaded!", show_alert=True)
            return
        
        await callback_query.message.reply_text(f"🎙️ Starting VC for group `{group_id}`...")
        success_count = await vc_mgr.start_all_for_group(group_config, group_id)
        await callback_query.message.reply_text(f"✅ {success_count} accounts joined the VC!")
        await callback_query.answer()
    
    elif data.startswith("stop_vc_"):
        group_id = data.replace("stop_vc_", "")
        
        if vc_mgr and group_id in vc_mgr.active_sessions:
            await vc_mgr.stop_all_for_group(group_id)
            await callback_query.message.reply_text(f"✅ Stopped VC for group `{group_id}`.")
        else:
            await callback_query.answer("No active session for this group!", show_alert=True)
        await callback_query.answer()
    
    elif data.startswith("remove_group_"):
        group_id = data.replace("remove_group_", "")
        
        if vc_mgr and group_id in vc_mgr.active_sessions:
            await vc_mgr.stop_all_for_group(group_id)
        
        db.remove_group(group_id)
        await callback_query.message.reply_text(f"✅ Group `{group_id}` removed.")
        await callback_query.answer()

async def main():
    print("🤖 Starting Bot...")
    await bot.start()
    print("✅ Bot is running!")
    await initialize_vc()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
