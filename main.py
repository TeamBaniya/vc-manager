import asyncio
import os
import re
import json
import random
import string
from datetime import datetime
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.errors import (
    PhoneCodeInvalid, PhoneCodeExpired, SessionPasswordNeeded,
    PasswordHashInvalid, UserAlreadyParticipant, FloodWait
)
from pytgcalls import GroupCallFactory, PyTgCalls
from pytgcalls.types import MediaStream

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
try:
    from config import API_ID, API_HASH, BOT_TOKEN
except ImportError:
    print("[!] config.py not found!")
    API_ID = 0
    API_HASH = ""
    BOT_TOKEN = ""

if not API_ID or not API_HASH or not BOT_TOKEN:
    print("[!] ERROR: Set API_ID, API_HASH, BOT_TOKEN in config.py")
    exit(1)

IMAGE_URL = os.environ.get("IMAGE_URL", "https://files.catbox.moe/pv9i5b.jpg")

# ─────────────────────────────────────────────────────────────
# DATA PERSISTENCE
# ─────────────────────────────────────────────────────────────
DATA_FILE = "vc_bot_data.json"
accounts_db = {}       # user_id_str -> account info
groups_info = {}       # chat_id_str -> group info
user_sessions_store = {}  # telegram_user_id -> list of session strings (for old code compat)
active_vc = {}         # account_name -> {"vc": group_call, "group_id": int, "group_name": str}
user_clients = {}      # account_name -> pyrogram Client

def load_data():
    global accounts_db, groups_info, user_sessions_store
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            accounts_db = data.get("accounts", {})
            groups_info = data.get("groups_info", {})
            user_sessions_store = data.get("sessions_store", {})
    except (FileNotFoundError, json.JSONDecodeError):
        save_data()

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump({
            "accounts": accounts_db,
            "groups_info": groups_info,
            "sessions_store": user_sessions_store,
        }, f, indent=2)

load_data()

# ─────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────

def get_user_accounts(tg_user_id: int) -> dict:
    return {uid: acc for uid, acc in accounts_db.items() if acc.get("added_by") == tg_user_id}

def count_owned_in_group(tg_user_id: int, chat_id: int) -> int:
    return sum(1 for acc in accounts_db.values()
               if acc.get("added_by") == tg_user_id and acc.get("in_group") == chat_id)

def count_accounts_in_group(chat_id: int) -> int:
    return sum(1 for acc in accounts_db.values() if acc.get("in_group") == chat_id)

def create_silent_raw():
    silent_file = "silent.raw"
    if os.path.exists(silent_file):
        return silent_file
    sample_rate = 48000
    duration = 2
    num_samples = sample_rate * duration
    silent_data = b'\x00\x00' * num_samples * 2
    with open(silent_file, 'wb') as f:
        f.write(silent_data)
    return silent_file

# ─────────────────────────────────────────────────────────────
# CALLBACK CONSTANTS
# ─────────────────────────────────────────────────────────────
CB_MAIN_MENU       = "main_menu"
CB_ADD_SESSION     = "add_session"
CB_MY_ACCOUNTS     = "my_accounts"
CB_REMOVE_ACCOUNT  = "rm_acc"
CB_CONFIRM_REMOVE  = "confirm_rm"
CB_SHOW_GROUPS     = "show_groups"
CB_ADD_GROUP       = "add_group"
CB_ADD_PUBLIC      = "add_public"
CB_ADD_PRIVATE     = "add_private"
CB_GROUP_SETTINGS  = "grp_set"
CB_JOIN_VC         = "join_vc"
CB_LEAVE_VC        = "leave_vc"
CB_SELECT_JOIN     = "sel_join"
CB_SELECT_LEAVE    = "sel_leave"
CB_STATUS          = "status"
CB_CANCEL          = "cancel"

# ─────────────────────────────────────────────────────────────
# BUTTON BUILDERS
# ─────────────────────────────────────────────────────────────

def main_menu_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔌 Add Session", callback_data=CB_ADD_SESSION)],
        [InlineKeyboardButton("📱 My Accounts", callback_data=CB_MY_ACCOUNTS)],
        [InlineKeyboardButton("👥 Groups", callback_data=CB_SHOW_GROUPS)],
        [InlineKeyboardButton("➕ Add Group", callback_data=CB_ADD_GROUP)],
        [InlineKeyboardButton("📊 Status", callback_data=CB_STATUS)],
    ])

def back_main_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Main Menu", callback_data=CB_MAIN_MENU)]
    ])

def cancel_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data=CB_CANCEL)]
    ])

# ─────────────────────────────────────────────────────────────
# APPLICATION CLASS
# ─────────────────────────────────────────────────────────────

class VCApplication:
    def __init__(self):
        self.bot = None
        self.waiting_input = {}     # user_id -> callback
        self.pending_sessions = {}  # user_id -> list of sessions being added
        self.leave_selected = {}    # user_id -> {"group_id": int, "group_name": str, "total": int}

    async def start(self):
        print("[*] Bot is starting...")
        
        self.bot = Client("vc_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
        await self.bot.start()
        print("[+] Bot started successfully!")
        
        self._register_handlers()
        
        # Restore saved account clients
        if accounts_db:
            print(f"[*] Restoring {len(accounts_db)} accounts...")
            for uid, acc in accounts_db.items():
                try:
                    await self._start_client_for_account(uid, acc["session"])
                except Exception as e:
                    print(f"[!] Failed to restore {uid}: {e}")
        
        print("[+] All systems ready!")
        await idle()

    async def stop(self):
        print("[*] Shutting down...")
        for name in list(active_vc.keys()):
            try:
                await active_vc[name]["vc"].stop()
            except:
                pass
        for name in list(user_clients.keys()):
            try:
                await user_clients[name].stop()
            except:
                pass
        if self.bot:
            await self.bot.stop()

    async def _start_client_for_account(self, user_id_str, session_str):
        """Start Pyrogram client for an account (for VC joining)"""
        try:
            client = Client(
                f"acc_{user_id_str}",
                session_string=session_str,
                api_id=API_ID,
                api_hash=API_HASH
            )
            await client.start()
            me = await client.get_me()
            name = me.first_name or f"User_{user_id_str}"
            user_clients[name] = client
            
            # Also store in accounts_db name if missing
            if user_id_str in accounts_db:
                accounts_db[user_id_str]["name"] = name
                if me.username:
                    accounts_db[user_id_str]["username"] = me.username
                save_data()
            
            print(f"[+] Client started for {name}")
            return name
        except Exception as e:
            print(f"[!] Failed to start client for {user_id_str}: {e}")
            return None

    def _register_handlers(self):
        bot = self.bot

        @bot.on_message(filters.command("start") & filters.private)
        async def start_cmd(client, msg):
            user_id = msg.from_user.id
            self.waiting_input.pop(user_id, None)
            self.pending_sessions.pop(user_id, None)
            
            caption = (
                "**🎵 VC Manager Bot**\n\n"
                "Welcome! I can manage multiple Telegram accounts in voice chats.\n\n"
                "**Features:**\n"
                "✅ Add accounts via Pyrogram String Session\n"
                "✅ Join/Leave voice chats\n"
                "✅ Multiple groups support\n"
                "✅ See which accounts are where\n"
                "✅ Muted mic, no audio issues\n\n"
                "Use the buttons below to get started!"
            )
            
            await msg.reply_photo(
                IMAGE_URL,
                caption=caption,
                reply_markup=main_menu_buttons()
            )

        # ── TEXT INPUT HANDLER ──
        @bot.on_message(filters.text & filters.private & ~filters.command("start"))
        async def handle_text(client, msg):
            user_id = msg.from_user.id
            
            if user_id in self.waiting_input:
                callback = self.waiting_input.pop(user_id)
                await callback(client, msg)
            else:
                await msg.reply(
                    "🤖 Use the buttons below:",
                    reply_markup=main_menu_buttons()
                )

        # ── CALLBACK HANDLER ──
        @bot.on_callback_query()
        async def handle_callback(client, cb_query):
            user_id = cb_query.from_user.id
            chat_id = cb_query.message.chat.id
            data = cb_query.data
            await cb_query.answer()
            
            if data == CB_MAIN_MENU:
                self.waiting_input.pop(user_id, None)
                self.pending_sessions.pop(user_id, None)
                await cb_query.message.edit_text(
                    "🤖 **VC Bot — Main Menu**\n\nChoose an option below:",
                    reply_markup=main_menu_buttons()
                )
            
            elif data == CB_CANCEL:
                self.waiting_input.pop(user_id, None)
                self.pending_sessions.pop(user_id, None)
                await cb_query.message.edit_text(
                    "❌ Cancelled.",
                    reply_markup=main_menu_buttons()
                )
            
            elif data == CB_ADD_SESSION:
                self.pending_sessions[user_id] = []
                await cb_query.message.edit_text(
                    "📱 **Add Account — Send String Session**\n\n"
                    "Send your Pyrogram **String Session**.\n"
                    "Get it from @StringSessionBot\n\n"
                    "Type **/done** when you're finished.\n"
                    "Type **/cancel** to cancel.",
                    reply_markup=cancel_button()
                )
                self.waiting_input[user_id] = self._handle_session_input
            
            elif data == CB_STATUS:
                await self._show_status(client, cb_query, user_id)
            
            elif data == CB_MY_ACCOUNTS:
                await self._show_my_accounts(client, cb_query, user_id)
            
            elif data.startswith(CB_REMOVE_ACCOUNT + ":"):
                acc_index = int(data.split(":")[1])
                await self._confirm_remove(client, cb_query, user_id, acc_index)
            
            elif data.startswith(CB_CONFIRM_REMOVE + ":"):
                acc_index = int(data.split(":")[1])
                await self._remove_account(client, cb_query, user_id, acc_index)
            
            elif data == CB_SHOW_GROUPS:
                await self._show_group_list(client, cb_query, user_id)
            
            elif data == CB_ADD_GROUP:
                await cb_query.message.edit_text(
                    "➕ **Add Group**\n\n"
                    "Choose group type:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🌐 Public Group", callback_data=CB_ADD_PUBLIC)],
                        [InlineKeyboardButton("🔒 Private Group", callback_data=CB_ADD_PRIVATE)],
                        [InlineKeyboardButton("🔙 Main Menu", callback_data=CB_MAIN_MENU)],
                    ])
                )
            
            elif data == CB_ADD_PUBLIC:
                await cb_query.message.edit_text(
                    "🌐 **Add Public Group**\n\n"
                    "Send the group's **@username**\n"
                    "Example: `@mygroup`",
                    reply_markup=cancel_button()
                )
                self.waiting_input[user_id] = self._handle_public_group
            
            elif data == CB_ADD_PRIVATE:
                await cb_query.message.edit_text(
                    "🔒 **Add Private Group**\n\n"
                    "Send the group's **invite link**\n"
                    "Example: `https://t.me/+abc123xyz`",
                    reply_markup=cancel_button()
                )
                self.waiting_input[user_id] = lambda c, m: self._handle_private_link(c, m, user_id)
            
            elif data.startswith(CB_GROUP_SETTINGS + ":"):
                target_chat = int(data.split(":")[1])
                await self._show_group_settings(client, cb_query, user_id, target_chat)
            
            elif data.startswith(CB_JOIN_VC + ":"):
                target_chat = int(data.split(":")[1])
                await self._show_joinable_accounts(client, cb_query, user_id, target_chat)
            
            elif data.startswith(CB_SELECT_JOIN + ":"):
                parts = data.split(":")
                target_chat = int(parts[1])
                acc_index = int(parts[2])
                await self._execute_join(client, cb_query, user_id, target_chat, acc_index)
            
            elif data.startswith(CB_LEAVE_VC + ":"):
                target_chat = int(data.split(":")[1])
                await self._show_leavable_accounts(client, cb_query, user_id, target_chat)
            
            elif data.startswith(CB_SELECT_LEAVE + ":"):
                parts = data.split(":")
                target_chat = int(parts[1])
                acc_index = int(parts[2])
                await self._execute_leave(client, cb_query, user_id, target_chat, acc_index)

    # ═════════════════════════════════════════════════════════
    # SESSION INPUT HANDLER
    # ═════════════════════════════════════════════════════════

    async def _handle_session_input(self, client, msg):
        user_id = msg.from_user.id
        text = msg.text.strip()
        
        if text == "/done":
            count = len(self.pending_sessions.get(user_id, []))
            await msg.reply(
                f"✅ **Done!** Added {count} session(s).\n\n"
                f"Use **Groups** to join a voice chat.",
                reply_markup=main_menu_buttons()
            )
            self.pending_sessions.pop(user_id, None)
            return
        
        if text == "/cancel":
            self.pending_sessions.pop(user_id, None)
            await msg.reply("❌ Cancelled.", reply_markup=main_menu_buttons())
            return
        
        # Validate session string
        if len(text) < 50:
            await msg.reply("❌ Invalid session string! Send a valid Pyrogram string session.", reply_markup=cancel_button())
            self.waiting_input[user_id] = self._handle_session_input
            return
        
        await msg.reply("⏳ Testing session...")
        
        try:
            # Test the session
            temp_client = Client(
                f"test_{user_id}_{random.randint(1000,9999)}",
                session_string=text,
                api_id=API_ID,
                api_hash=API_HASH,
                in_memory=True
            )
            await temp_client.start()
            me = await temp_client.get_me()
            session_str = await temp_client.export_session_string()
            await temp_client.stop()
            
            uid = str(me.id)
            name = me.first_name or f"User_{uid}"
            
            # Check if already exists
            if uid in accounts_db:
                await msg.reply(f"⚠️ Account **{name}** already exists!", reply_markup=cancel_button())
                self.waiting_input[user_id] = self._handle_session_input
                return
            
            # Save to DB
            accounts_db[uid] = {
                "session": session_str,
                "added_by": user_id,
                "name": name,
                "username": me.username or "",
                "phone": "",
                "in_group": None,
                "added_at": datetime.utcnow().isoformat()
            }
            save_data()
            
            # Start client for this account
            client_name = await self._start_client_for_account(uid, session_str)
            
            # Track in pending
            if user_id not in self.pending_sessions:
                self.pending_sessions[user_id] = []
            self.pending_sessions[user_id].append(name)
            
            total = len(self.pending_sessions[user_id])
            await msg.reply(
                f"✅ **Account Added!**\n\n"
                f"👤 **{name}**\n"
                f"🆔 `{uid}`\n"
                f"📊 Total this session: {total}\n\n"
                f"Send another session or type **/done**",
                reply_markup=cancel_button()
            )
            
        except Exception as e:
            await msg.reply(f"❌ Error: `{e}`\n\nTry again or type **/cancel**", reply_markup=cancel_button())
        
        self.waiting_input[user_id] = self._handle_session_input

    # ═════════════════════════════════════════════════════════
    # STATUS
    # ═════════════════════════════════════════════════════════

    async def _show_status(self, client, cb_query, user_id):
        text = "**📊 Status**\n\n"
        text += f"📱 Total Accounts: `{len(accounts_db)}`\n"
        text += f"🔌 Clients Online: `{len(user_clients)}`\n"
        text += f"🎤 Active in VC: `{len(active_vc)}`\n"
        text += f"📋 Groups: `{len(groups_info)}`\n\n"
        
        user_accs = get_user_accounts(user_id)
        text += f"**Your Accounts: {len(user_accs)}**\n"
        if user_accs:
            for uid, acc in user_accs.items():
                name = acc.get("name", "Unknown")
                in_vc = "🎧 In VC" if acc.get("in_group") else "💤 Idle"
                text += f"• `{name}` — {in_vc}\n"
        
        if active_vc:
            text += "\n**All Active in VC:**\n"
            for name, d in active_vc.items():
                text += f"🎤 `{name}` → `{d['group_name']}`\n"
        
        await cb_query.message.edit_text(text, reply_markup=back_main_button())

    # ═════════════════════════════════════════════════════════
    # MY ACCOUNTS
    # ═════════════════════════════════════════════════════════

    async def _show_my_accounts(self, client, cb_query, user_id):
        user_accs = get_user_accounts(user_id)
        
        if not user_accs:
            await cb_query.message.edit_text(
                "📱 **My Accounts**\n\nYou haven't added any accounts yet.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔌 Add Session", callback_data=CB_ADD_SESSION)],
                    [InlineKeyboardButton("🔙 Main Menu", callback_data=CB_MAIN_MENU)],
                ])
            )
            return
        
        text = f"📱 **My Accounts ({len(user_accs)})**\n\n"
        buttons = []
        acc_list = list(user_accs.items())
        
        for idx, (uid, acc) in enumerate(acc_list):
            name = acc.get("name", "Unknown")
            uname = f"@{acc['username']}" if acc.get("username") else "N/A"
            status = "🎧 In VC" if acc.get("in_group") else "💤 Idle"
            group_info = f" → `{acc['in_group']}`" if acc.get("in_group") else ""
            text += f"**{idx+1}.** `{name}` — {status}{group_info}\n"
            text += f"   `{uid}` | {uname}\n\n"
            buttons.append([
                InlineKeyboardButton(f"🗑 Remove {name}", callback_data=f"{CB_REMOVE_ACCOUNT}:{idx}")
            ])
        
        buttons.append([InlineKeyboardButton("🔙 Main Menu", callback_data=CB_MAIN_MENU)])
        await cb_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    async def _confirm_remove(self, client, cb_query, user_id, acc_index):
        user_accs = list(get_user_accounts(user_id).items())
        
        if acc_index < 0 or acc_index >= len(user_accs):
            await cb_query.message.edit_text("❌ Invalid account.", reply_markup=back_main_button())
            return
        
        uid, acc = user_accs[acc_index]
        name = acc.get("name", "Unknown")
        
        await cb_query.message.edit_text(
            f"🗑 **Remove Account?**\n\n"
            f"Remove **{name}** (`{uid}`)?\n"
            f"It will leave any active voice chat.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Yes, Remove", callback_data=f"{CB_CONFIRM_REMOVE}:{acc_index}")],
                [InlineKeyboardButton("🔙 Back", callback_data=CB_MY_ACCOUNTS)],
            ])
        )

    async def _remove_account(self, client, cb_query, user_id, acc_index):
        user_accs = list(get_user_accounts(user_id).items())
        
        if acc_index < 0 or acc_index >= len(user_accs):
            return
        
        uid, acc = user_accs[acc_index]
        name = acc.get("name", "Unknown")
        
        # Leave VC if in one
        if acc.get("in_group"):
            if name in active_vc:
                try:
                    await active_vc[name]["vc"].stop()
                except:
                    try:
                        await active_vc[name]["vc"].leave()
                    except:
                        pass
                del active_vc[name]
        
        # Stop and remove client
        if name in user_clients:
            try:
                await user_clients[name].stop()
            except:
                pass
            del user_clients[name]
        
        # Remove from DB
        del accounts_db[uid]
        save_data()
        
        await cb_query.message.edit_text(
            f"✅ **{name}** removed successfully.",
            reply_markup=main_menu_buttons()
        )

    # ═════════════════════════════════════════════════════════
    # ADD GROUP
    # ═════════════════════════════════════════════════════════

    async def _handle_public_group(self, client, msg):
        user_id = msg.from_user.id
        username = msg.text.strip().replace("@", "")
        
        await msg.reply(f"⏳ Resolving @{username}...")
        
        try:
            resp = await self.bot.get_chat(f"@{username}")
            gtitle = resp.title or username
            gcid = resp.id
            
            gid_str = str(gcid)
            groups_info[gid_str] = {
                "title": gtitle,
                "username": username,
                "added_by": user_id
            }
            save_data()
            
            await msg.reply(
                f"✅ **Group Added!**\n\n"
                f"📌 **{gtitle}**\n"
                f"🆔 `{gcid}`\n"
                f"🌐 @{username}\n\n"
                f"Now go to **Groups** to manage voice chat.",
                reply_markup=main_menu_buttons()
            )
        except Exception as e:
            await msg.reply(
                f"❌ Error: `{e}`\n\n"
                f"Make sure the username is correct and the bot is in the group.",
                reply_markup=back_main_button()
            )

    async def _handle_private_link(self, client, msg, user_id):
        link = msg.text.strip()
        
        await msg.reply(f"⏳ Processing invite link...")
        
        # We need chat_id for private groups
        # Store the link and ask for chat_id
        self.waiting_input[user_id] = lambda c, m: self._handle_private_chatid(c, m, user_id, link)
        
        await msg.reply(
            "🔑 **Send the Chat ID**\n\n"
            "Example: `-1001234567890`\n\n"
            "You can get it from @getidsbot or forward a message from the group.",
            reply_markup=cancel_button()
        )

    async def _handle_private_chatid(self, client, msg, user_id, link):
        try:
            cid = int(msg.text.strip())
        except ValueError:
            await msg.reply("❌ Invalid Chat ID! Send numeric ID only.", reply_markup=cancel_button())
            self.waiting_input[user_id] = lambda c, m: self._handle_private_chatid(c, m, user_id, link)
            return
        
        # Try to get group info
        try:
            resp = await self.bot.get_chat(cid)
            title = resp.title or f"Private_{cid}"
        except:
            title = f"Private_{cid}"
        
        gid_str = str(cid)
        groups_info[gid_str] = {
            "title": title,
            "invite_link": link,
            "added_by": user_id
        }
        save_data()
        
        await msg.reply(
            f"✅ **Private Group Added!**\n\n"
            f"📌 **{title}**\n"
            f"🆔 `{cid}`\n\n"
            f"Now go to **Groups** to manage voice chat.",
            reply_markup=main_menu_buttons()
        )

    # ═════════════════════════════════════════════════════════
    # SHOW GROUPS
    # ═════════════════════════════════════════════════════════

    async def _show_group_list(self, client, cb_query, user_id):
        if not groups_info:
            await cb_query.message.edit_text(
                "👥 **Groups**\n\nNo groups added yet.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Add Group", callback_data=CB_ADD_GROUP)],
                    [InlineKeyboardButton("🔙 Main Menu", callback_data=CB_MAIN_MENU)],
                ])
            )
            return
        
        text = "👥 **Groups**\n\n"
        buttons = []
        
        for gid_str, ginfo in groups_info.items():
            gid = int(gid_str)
            title = ginfo.get("title", f"Group {gid}")
            total = count_accounts_in_group(gid)
            mine = count_owned_in_group(user_id, gid)
            
            text += f"📌 **{title}**\n"
            text += f"🆔 `{gid}` | 👤 Yours: {mine} | 📊 Total: {total}\n\n"
            
            buttons.append([
                InlineKeyboardButton(f"⚙️ {title}", callback_data=f"{CB_GROUP_SETTINGS}:{gid}")
            ])
        
        buttons.append([InlineKeyboardButton("➕ Add Group", callback_data=CB_ADD_GROUP)])
        buttons.append([InlineKeyboardButton("🔙 Main Menu", callback_data=CB_MAIN_MENU)])
        await cb_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    # ═════════════════════════════════════════════════════════
    # GROUP SETTINGS
    # ═════════════════════════════════════════════════════════

    async def _show_group_settings(self, client, cb_query, user_id, target_chat):
        gid_str = str(target_chat)
        ginfo = groups_info.get(gid_str, {"title": f"Group {target_chat}"})
        title = ginfo.get("title", f"Group {target_chat}")
        total = count_accounts_in_group(target_chat)
        mine = count_owned_in_group(user_id, target_chat)
        
        # Count accounts that are idle (available to join)
        user_accs = get_user_accounts(user_id)
        idle_count = sum(1 for acc in user_accs.values() if acc.get("in_group") is None)
        
        text = (
            f"⚙️ **{title}**\n\n"
            f"**Statistics:**\n"
            f"📊 Total in VC: `{total}`\n"
            f"👤 Your accounts: `{mine}`\n"
            f"💤 Your idle accounts: `{idle_count}`\n\n"
            f"**Actions:**"
        )
        
        buttons = [
            [InlineKeyboardButton("📈 Join VC", callback_data=f"{CB_JOIN_VC}:{target_chat}")],
            [InlineKeyboardButton("📉 Leave VC", callback_data=f"{CB_LEAVE_VC}:{target_chat}")],
            [InlineKeyboardButton("🔙 Groups", callback_data=CB_SHOW_GROUPS)],
            [InlineKeyboardButton("🔙 Main Menu", callback_data=CB_MAIN_MENU)],
        ]
        await cb_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    # ═════════════════════════════════════════════════════════
    # JOIN VC
    # ═════════════════════════════════════════════════════════

    async def _show_joinable_accounts(self, client, cb_query, user_id, target_chat):
        user_accs = get_user_accounts(user_id)
        idle_accs = {uid: acc for uid, acc in user_accs.items() if acc.get("in_group") is None}
        
        if not idle_accs:
            await cb_query.message.edit_text(
                "❌ **No idle accounts!**\n\n"
                "Add an account first via **Add Session**.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Group Settings", callback_data=f"{CB_GROUP_SETTINGS}:{target_chat}")]
                ])
            )
            return
        
        text = f"📈 **Join VC**\nSelect account to join:\n\n"
        buttons = []
        idle_list = list(idle_accs.items())
        
        for idx, (uid, acc) in enumerate(idle_list):
            name = acc.get("name", "Unknown")
            buttons.append([
                InlineKeyboardButton(f"➕ {name}", callback_data=f"{CB_SELECT_JOIN}:{target_chat}:{idx}")
            ])
        
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"{CB_GROUP_SETTINGS}:{target_chat}")])
        await cb_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    async def _execute_join(self, client, cb_query, user_id, target_chat, acc_index):
        user_accs = get_user_accounts(user_id)
        idle_accs = list({uid: acc for uid, acc in user_accs.items() if acc.get("in_group") is None}.items())
        
        if acc_index < 0 or acc_index >= len(idle_accs):
            return
        
        uid, acc = idle_accs[acc_index]
        name = acc.get("name", "Unknown")
        
        # Check if name has a client
        if name not in user_clients:
            await cb_query.message.edit_text(
                f"❌ Client for **{name}** not available. Try re-adding the session.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data=f"{CB_GROUP_SETTINGS}:{target_chat}")]
                ])
            )
            return
        
        try:
            silent_raw = create_silent_raw()
            client_obj = user_clients[name]
            
            # Create group call using GroupCallFactory (old method as requested)
            factory = GroupCallFactory(client_obj)
            vc_call = factory.get_file_group_call()
            
            await vc_call.start(target_chat)
            
            # Store in active_vc
            gname = groups_info.get(str(target_chat), {}).get("title", f"Group_{target_chat}")
            active_vc[name] = {
                "vc": vc_call,
                "group_id": target_chat,
                "group_name": gname
            }
            
            # Update DB
            accounts_db[uid]["in_group"] = target_chat
            save_data()
            
            await cb_query.message.edit_text(
                f"✅ **{name} joined VC!**\n\n"
                f"📍 Group: `{gname}`\n"
                f"🎤 Account: `{name}`\n"
                f"🔇 Mic is muted (silent stream)",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Group Settings", callback_data=f"{CB_GROUP_SETTINGS}:{target_chat}")],
                    [InlineKeyboardButton("🔙 Main Menu", callback_data=CB_MAIN_MENU)],
                ])
            )
            
        except UserAlreadyParticipant:
            accounts_db[uid]["in_group"] = target_chat
            save_data()
            await cb_query.message.edit_text(
                f"✅ **{name}** is already in the VC! (Status updated)",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Group Settings", callback_data=f"{CB_GROUP_SETTINGS}:{target_chat}")],
                    [InlineKeyboardButton("🔙 Main Menu", callback_data=CB_MAIN_MENU)],
                ])
            )
            
        except Exception as e:
            error_msg = str(e)
            if "not active" in error_msg.lower():
                await cb_query.message.edit_text(
                    f"❌ Voice chat not active in this group!\n\nStart a voice chat first.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Back", callback_data=f"{CB_GROUP_SETTINGS}:{target_chat}")]
                    ])
                )
            else:
                await cb_query.message.edit_text(
                    f"❌ Failed: `{error_msg[:100]}`",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Back", callback_data=f"{CB_GROUP_SETTINGS}:{target_chat}")]
                    ])
                )

    # ═════════════════════════════════════════════════════════
    # LEAVE VC
    # ═════════════════════════════════════════════════════════

    async def _show_leavable_accounts(self, client, cb_query, user_id, target_chat):
        user_accs = get_user_accounts(user_id)
        in_group_accs = {uid: acc for uid, acc in user_accs.items() if acc.get("in_group") == target_chat}
        
        if not in_group_accs:
            await cb_query.message.edit_text(
                "❌ **No accounts in this group.**",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Group Settings", callback_data=f"{CB_GROUP_SETTINGS}:{target_chat}")]
                ])
            )
            return
        
        text = f"📉 **Leave VC**\nSelect account to remove:\n\n"
        buttons = []
        in_group_list = list(in_group_accs.items())
        
        for idx, (uid, acc) in enumerate(in_group_list):
            name = acc.get("name", "Unknown")
            buttons.append([
                InlineKeyboardButton(f"➖ {name}", callback_data=f"{CB_SELECT_LEAVE}:{target_chat}:{idx}")
            ])
        
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"{CB_GROUP_SETTINGS}:{target_chat}")])
        await cb_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    async def _execute_leave(self, client, cb_query, user_id, target_chat, acc_index):
        user_accs = get_user_accounts(user_id)
        in_group_accs = list({uid: acc for uid, acc in user_accs.items() if acc.get("in_group") == target_chat}.items())
        
        if acc_index < 0 or acc_index >= len(in_group_accs):
            return
        
        uid, acc = in_group_accs[acc_index]
        name = acc.get("name", "Unknown")
        
        try:
            if name in active_vc:
                vc_data = active_vc[name]
                try:
                    await vc_data["vc"].stop()
                except AttributeError:
                    try:
                        await vc_data["vc"].leave()
                    except:
                        pass
                del active_vc[name]
            
            accounts_db[uid]["in_group"] = None
            save_data()
            
            await cb_query.message.edit_text(
                f"✅ **{name} left VC!**",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Group Settings", callback_data=f"{CB_GROUP_SETTINGS}:{target_chat}")],
                    [InlineKeyboardButton("🔙 Main Menu", callback_data=CB_MAIN_MENU)],
                ])
            )
            
        except Exception as e:
            await cb_query.message.edit_text(
                f"❌ Failed: `{e}`",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data=f"{CB_GROUP_SETTINGS}:{target_chat}")]
                ])
            )


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

async def main():
    app = VCApplication()
    try:
        await app.start()
    finally:
        await app.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Bot stopped by user.")
    except Exception as e:
        print(f"[!] Fatal error: {e}")
        import traceback
        traceback.print_exc()
