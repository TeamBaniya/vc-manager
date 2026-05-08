import requests
import time
import json
import asyncio
import os
import re
from datetime import datetime, timedelta
from pyrogram import Client
from pytgcalls import GroupCallFactory
from database import db
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID

TOKEN = BOT_TOKEN
API_URL = f"https://api.telegram.org/bot{TOKEN}"

# Get image URL from environment variable
IMAGE_URL = os.environ.get("IMAGE_URL", "https://telegra.ph/file/default-image.jpg")

# Data storage
user_sessions = []
user_clients = {}
active_vc = {}
groups_list = []
current_group = None
last_update_id = 0
user_states = {}
leave_selected_group = {}

# Sudo users storage
sudo_users = {}  # {user_id: {"expiry": datetime, "username": username, "approved_by": owner_id}}
pending_approvals = {}  # {user_id: {"request_time": datetime, "username": username}}

print("="*60)
print("🤖 VC MANAGER BOT - FINAL")
print("="*60)
print("Bot started! Send /start on Telegram\n")

def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(f"{API_URL}/sendMessage", json=data, timeout=5)
    except:
        pass

def send_photo(chat_id, photo_url, caption, reply_markup=None):
    data = {"chat_id": chat_id, "photo": photo_url, "caption": caption, "parse_mode": "Markdown"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(f"{API_URL}/sendPhoto", json=data, timeout=5)
    except:
        # Fallback to send message if photo fails
        send_message(chat_id, caption, reply_markup)

def is_sudo_user(user_id):
    """Check if user is sudo user and not expired"""
    if user_id == OWNER_ID:
        return True  # Owner is always sudo
    
    if user_id in sudo_users:
        expiry = sudo_users[user_id]["expiry"]
        if datetime.now() < expiry:
            return True
        else:
            # Remove expired sudo user
            del sudo_users[user_id]
    return False

def parse_time_duration(duration_str):
    """Parse time duration like '10 min', '1 hour', '2 days', '1 year'"""
    duration_str = duration_str.lower().strip()
    
    # Handle numbers and words
    match = re.match(r'(\d+)\s*(min|minute|hour|day|week|month|year)s?', duration_str)
    if not match:
        return None
    
    value = int(match.group(1))
    unit = match.group(2)
    
    if unit in ['min', 'minute']:
        return timedelta(minutes=value)
    elif unit == 'hour':
        return timedelta(hours=value)
    elif unit == 'day':
        return timedelta(days=value)
    elif unit == 'week':
        return timedelta(weeks=value)
    elif unit == 'month':
        return timedelta(days=value * 30)
    elif unit == 'year':
        return timedelta(days=value * 365)
    
    return None

async def test_session(session_string):
    try:
        client = Client("test_temp", api_id=API_ID, api_hash=API_HASH, session_string=session_string)
        await client.start()
        me = await client.get_me()
        await client.stop()
        return {"success": True, "name": me.first_name, "id": me.id, "username": me.username}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def join_voice_chat(chat_id, group_name, count):
    results = []
    for i, session_data in enumerate(user_sessions[:count]):
        session_string = session_data["string"]
        acc_name = session_data["name"]
        acc_id = session_data["id"]
        try:
            if acc_name not in user_clients:
                print(f"  🔌 Creating client for {acc_name}...")
                client = Client(f"sessions/{acc_name}", api_id=API_ID, api_hash=API_HASH, session_string=session_string)
                await client.start()
                user_clients[acc_name] = client
                print(f"  ✅ Client created for {acc_name}")
            
            client = user_clients[acc_name]
            factory = GroupCallFactory(client)
            vc = factory.get_file_group_call()
            
            try:
                await vc.start(chat_id)
                active_vc[acc_name] = {"vc": vc, "group_id": chat_id, "group_name": group_name}
                results.append({"success": True, "name": acc_name, "id": acc_id})
                print(f"  ✅ {acc_name} joined {group_name}")
            except Exception as e:
                error_msg = str(e)
                if "not active" in error_msg.lower():
                    results.append({"success": False, "name": acc_name, "id": acc_id, "error": "Voice chat not active!"})
                elif "already" in error_msg.lower():
                    results.append({"success": True, "name": acc_name, "id": acc_id})
                    print(f"  ⚠️ {acc_name} already in VC")
                else:
                    results.append({"success": False, "name": acc_name, "id": acc_id, "error": error_msg[:50]})
                print(f"  ❌ {acc_name} failed: {error_msg[:50]}")
        except Exception as e:
            results.append({"success": False, "name": acc_name, "id": acc_id, "error": str(e)[:50]})
            print(f"  ❌ {acc_name} error: {e}")
        await asyncio.sleep(2)
    return results

# ========== WORKING LEAVE FUNCTION ==========
async def leave_specific_accounts(group_id, count):
    results = []
    accounts_to_leave = []
    for name, data in active_vc.items():
        if data["group_id"] == group_id:
            accounts_to_leave.append(name)
    
    if not accounts_to_leave:
        return results
    
    for name in accounts_to_leave[:count]:
        try:
            # Try stop() first
            await active_vc[name]["vc"].stop()
            results.append({"success": True, "name": name})
            print(f"  ✅ {name} left")
        except AttributeError:
            # If stop fails, try leave
            try:
                await active_vc[name]["vc"].leave()
                results.append({"success": True, "name": name})
                print(f"  ✅ {name} left")
            except AttributeError:
                # Force remove from tracking
                results.append({"success": True, "name": name})
                print(f"  ✅ {name} removed from tracking")
        except Exception as e:
            error_str = str(e)
            if "GROUPCALL_FORBIDDEN" in error_str or "already ended" in error_str:
                results.append({"success": True, "name": name})
                print(f"  ✅ {name} left (VC already ended)")
            else:
                results.append({"success": False, "name": name, "error": error_str[:50]})
                print(f"  ❌ {name} failed: {error_str[:50]}")
        
        # Remove from active_vc
        if name in active_vc:
            del active_vc[name]
        await asyncio.sleep(1)
    
    return results
# ===========================================

def show_leave_groups(chat_id):
    groups_with_vc = {}
    for name, data in active_vc.items():
        group_name = data["group_name"]
        group_id = data["group_id"]
        if group_id not in groups_with_vc:
            groups_with_vc[group_id] = {"name": group_name, "count": 0}
        groups_with_vc[group_id]["count"] += 1
    if not groups_with_vc:
        send_message(chat_id, "❌ No active voice chats!")
        return
    keyboard = {"inline_keyboard": []}
    for group_id, info in groups_with_vc.items():
        keyboard["inline_keyboard"].append([
            {"text": f"🎤 {info['name']} ({info['count']} accounts)", "callback_data": f"leave_group_{group_id}"}
        ])
    keyboard["inline_keyboard"].append([{"text": "❌ Cancel", "callback_data": "cancel_leave"}])
    send_message(chat_id, "Select group to leave:", keyboard)

def show_all_sessions(chat_id):
    if not user_sessions:
        send_message(chat_id, "❌ No sessions added!")
        return
    text = "**📱 Your Sessions:**\n\n"
    for i, s in enumerate(user_sessions, 1):
        status = "✅ Connected" if s['name'] in user_clients else "⭕ Not Connected"
        text += f"{i}. **{s['name']}**\n"
        text += f"   🆔 ID: `{s['id']}`\n"
        text += f"   📊 Status: {status}\n\n"
    send_message(chat_id, text)

def show_sudo_users(chat_id):
    if not sudo_users:
        send_message(chat_id, "❌ No sudo users found!")
        return
    
    text = "**👑 Sudo Users List:**\n\n"
    for user_id, data in sudo_users.items():
        expiry = data["expiry"].strftime("%Y-%m-%d %H:%M:%S")
        username = data.get("username", "Unknown")
        approved_by = data.get("approved_by", "System")
        text += f"**User:** `{user_id}`\n"
        text += f"**Username:** @{username}\n"
        text += f"**Expiry:** {expiry}\n"
        text += f"**Approved by:** `{approved_by}`\n\n"
    send_message(chat_id, text)

async def main():
    global last_update_id, current_group
    while True:
        try:
            response = requests.get(f"{API_URL}/getUpdates", params={"offset": last_update_id + 1, "timeout": 30}, timeout=35)
            if response.status_code != 200:
                time.sleep(5)
                continue
            data = response.json()
            if not data.get("ok"):
                time.sleep(5)
                continue
            for update in data.get("result", []):
                last_update_id = update["update_id"]
                
                if "callback_query" in update:
                    callback = update["callback_query"]
                    user_id = callback["from"]["id"]
                    chat_id = callback["message"]["chat"]["id"]
                    data_cb = callback["data"]
                    print(f"\n📞 Callback: {data_cb}")
                    
                    # Callback query access check
                    if user_id != OWNER_ID and not is_sudo_user(user_id):
                        send_message(chat_id, "❌ Access Denied! Only sudo users can use this bot.\nContact owner for approval.")
                        requests.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": callback["id"]})
                        continue
                    
                    if data_cb == "connect":
                        user_states[user_id] = {"step": "awaiting_session"}
                        send_message(chat_id, "📱 **Send Pyrogram String Session**\n\nGet from @StringSessionBot\nType `/done` when finished")
                    
                    elif data_cb == "status":
                        status_text = f"**📊 Status**\n\n"
                        status_text += f"📱 Sessions: {len(user_sessions)}\n"
                        status_text += f"🔌 Connected: {len(user_clients)}\n"
                        status_text += f"🎤 Active VC: {len(active_vc)}\n"
                        status_text += f"📋 Groups: {len(groups_list)}\n"
                        status_text += f"👑 Sudo Users: {len(sudo_users)}\n\n"
                        if user_sessions:
                            status_text += "**Sessions:**\n"
                            for s in user_sessions:
                                status = "✅" if s['name'] in user_clients else "⭕"
                                status_text += f"{status} `{s['name']}`\n"
                        if active_vc:
                            status_text += "\n**Active in VC:**\n"
                            for name, d in active_vc.items():
                                status_text += f"🎤 `{name}` in `{d['group_name']}`\n"
                        send_message(chat_id, status_text)
                    
                    elif data_cb == "public_group":
                        user_states[user_id] = {"step": "public_username"}
                        send_message(chat_id, "📝 Send group @username\nExample: `@mygroup`")
                    
                    elif data_cb == "private_group":
                        user_states[user_id] = {"step": "private_link"}
                        send_message(chat_id, "🔗 Send invite link")
                    
                    elif data_cb == "show_groups":
                        if not groups_list:
                            send_message(chat_id, "No groups added! Use /add")
                        else:
                            keyboard = {"inline_keyboard": []}
                            for i, grp in enumerate(groups_list):
                                keyboard["inline_keyboard"].append([
                                    {"text": f"📌 {grp['name']}", "callback_data": f"select_group_{i}"}
                                ])
                            send_message(chat_id, "Your Groups:", keyboard)
                    
                    elif data_cb == "show_sessions":
                        show_all_sessions(chat_id)
                    
                    elif data_cb.startswith("select_group_"):
                        idx = int(data_cb.split("_")[2])
                        if idx < len(groups_list):
                            current_group = groups_list[idx]
                            send_message(chat_id, f"✅ Switched to: {current_group['name']}")
                    
                    elif data_cb == "leave_vc":
                        show_leave_groups(chat_id)
                    
                    elif data_cb.startswith("leave_group_"):
                        gid = int(data_cb.split("_")[2])
                        gname = None
                        tcount = 0
                        for name, d in active_vc.items():
                            if d["group_id"] == gid:
                                gname = d["group_name"]
                                tcount += 1
                        if gname:
                            leave_selected_group[user_id] = {"group_id": gid, "group_name": gname, "total": tcount}
                            send_message(chat_id, f"🎤 Group: {gname}\n👥 Active: {tcount}\n\nSend number of accounts to leave (1-{tcount}):")
                    
                    elif data_cb == "cancel_leave":
                        send_message(chat_id, "❌ Cancelled")
                        if user_id in leave_selected_group:
                            del leave_selected_group[user_id]
                    
                    elif data_cb == "show_sudo":
                        show_sudo_users(chat_id)
                    
                    requests.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": callback["id"]})
                
                elif "message" in update:
                    msg = update["message"]
                    user_id = msg["from"]["id"]
                    chat_id = msg["chat"]["id"]
                    text = msg.get("text", "")
                    username = msg["from"].get("username", "NoUsername")
                    print(f"\n📨 Message from {username} ({user_id}): {text}")
                    
                    # Handle approval requests from non-sudo users
                    if user_id != OWNER_ID and not is_sudo_user(user_id):
                        if text == "/start":
                            # Check if already requested
                            if user_id in pending_approvals:
                                send_message(chat_id, f"⏳ Your request is already pending! Owner will approve you soon.\n\nUser ID: `{user_id}`\nUsername: @{username}")
                            else:
                                # Store pending approval
                                pending_approvals[user_id] = {
                                    "request_time": datetime.now(),
                                    "username": username,
                                    "chat_id": chat_id
                                }
                                # Notify owner
                                owner_msg = f"**🆕 New Sudo Request!**\n\n"
                                owner_msg += f"**User ID:** `{user_id}`\n"
                                owner_msg += f"**Username:** @{username}\n"
                                owner_msg += f"**Chat ID:** `{chat_id}`\n\n"
                                owner_msg += f"Use: `/approve {user_id} 10 min` to approve\n"
                                owner_msg += f"Examples:\n"
                                owner_msg += f"`/approve {user_id} 10 min`\n"
                                owner_msg += f"`/approve {user_id} 1 hour`\n"
                                owner_msg += f"`/approve {user_id} 2 days`\n"
                                owner_msg += f"`/approve {user_id} 1 year`"
                                
                                send_message(OWNER_ID, owner_msg)
                                
                                # Send message to user
                                send_message(chat_id, f"❌ **Access Denied!**\n\nYou are not authorized to use this bot.\n\n📢 **Request sent to owner!**\n🆔 Your ID: `{user_id}`\n👤 Username: @{username}\n\n⏳ Please wait for owner approval.\n\n_You will be notified when approved._")
                        else:
                            send_message(chat_id, f"❌ Access Denied! You are not a sudo user.\n\nUse /start to request access from owner.\n\nYour ID: `{user_id}`")
                        continue
                    
                    # Owner commands for sudo management
                    if user_id == OWNER_ID and text.startswith("/approve"):
                        parts = text.split()
                        if len(parts) >= 3:
                            try:
                                target_user_id = int(parts[1])
                                duration_str = ' '.join(parts[2:])
                                
                                duration = parse_time_duration(duration_str)
                                if duration:
                                    expiry_time = datetime.now() + duration
                                    
                                    # Get username
                                    target_username = "Unknown"
                                    try:
                                        resp = requests.get(f"{API_URL}/getChat", params={"chat_id": target_user_id}, timeout=5)
                                        if resp.ok:
                                            target_username = resp.json()["result"].get("username", "Unknown")
                                    except:
                                        pass
                                    
                                    sudo_users[target_user_id] = {
                                        "expiry": expiry_time,
                                        "username": target_username,
                                        "approved_by": OWNER_ID
                                    }
                                    
                                    # Remove from pending if exists
                                    if target_user_id in pending_approvals:
                                        user_chat_id = pending_approvals[target_user_id].get("chat_id")
                                        if user_chat_id:
                                            send_message(user_chat_id, f"✅ **Access Granted!**\n\nYou have been approved as sudo user!\n⏰ Duration: {duration_str}\n📅 Expires: {expiry_time.strftime('%Y-%m-%d %H:%M:%S')}\n\nUse /start to access the bot.")
                                        del pending_approvals[target_user_id]
                                    
                                    send_message(chat_id, f"✅ User `{target_user_id}` approved as sudo user for {duration_str}!")
                                    send_message(chat_id, f"📅 Expires on: {expiry_time.strftime('%Y-%m-%d %H:%M:%S')}")
                                else:
                                    send_message(chat_id, "❌ Invalid duration! Use format: `/approve user_id 10 min`\nExamples: `10 min`, `1 hour`, `2 days`, `1 year`")
                            except ValueError:
                                send_message(chat_id, "❌ Invalid user ID! Use numeric ID only.")
                        else:
                            send_message(chat_id, "❌ Usage: `/approve user_id duration`\n\nExamples:\n`/approve 123456789 10 min`\n`/approve 123456789 1 hour`\n`/approve 123456789 2 days`\n`/approve 123456789 1 year`")
                        
                        continue
                    
                    # Remove sudo user
                    if user_id == OWNER_ID and text.startswith("/removesudo"):
                        parts = text.split()
                        if len(parts) == 2:
                            try:
                                target_user_id = int(parts[1])
                                if target_user_id in sudo_users:
                                    del sudo_users[target_user_id]
                                    send_message(chat_id, f"✅ Removed sudo access for user `{target_user_id}`")
                                else:
                                    send_message(chat_id, f"❌ User `{target_user_id}` is not a sudo user")
                            except ValueError:
                                send_message(chat_id, "❌ Invalid user ID!")
                        else:
                            send_message(chat_id, "❌ Usage: `/removesudo user_id`")
                        continue
                    
                    # List sudo users
                    if user_id == OWNER_ID and text == "/listsudo":
                        show_sudo_users(chat_id)
                        continue
                    
                    # Handle leave count input
                    if user_id in leave_selected_group:
                        try:
                            count = int(text)
                            group_info = leave_selected_group[user_id]
                            if count <= 0:
                                send_message(chat_id, "❌ Count must be greater than 0!")
                            elif count > group_info["total"]:
                                send_message(chat_id, f"❌ Only {group_info['total']} accounts active!")
                            else:
                                send_message(chat_id, f"🚪 Leaving {count} accounts...")
                                results = await leave_specific_accounts(group_info["group_id"], count)
                                scount = sum(1 for r in results if r["success"])
                                if scount > 0:
                                    send_message(chat_id, f"✅ Left {scount} accounts from {group_info['group_name']}")
                                else:
                                    send_message(chat_id, f"❌ Failed to leave accounts!")
                                del leave_selected_group[user_id]
                        except ValueError:
                            send_message(chat_id, "❌ Please send a valid number!")
                        continue
                    
                    # Regular commands for sudo users
                    if text == "/start":
                        # Caption for the image
                        caption = """**🎵 VC Manager Bot** 

Welcome to VC Manager Bot! I can help you manage multiple accounts in voice chats.

**Commands:**
/add - Add group
/joinvc <count> - Join VC
/leavevc - Smart leave
/groups - All groups
/sessions - All sessions
/status - Status
/done - Done

**Sudo Commands (Owner only):**
/approve <user_id> <duration> - Approve user
/removesudo <user_id> - Remove sudo user
/listsudo - List all sudo users"""
                        
                        # Keyboard with 2 buttons per row
                        kb = {"inline_keyboard": [
                            [{"text": "🔌 Connect Session", "callback_data": "connect"}, {"text": "📊 Status", "callback_data": "status"}],
                            [{"text": "📱 My Sessions", "callback_data": "show_sessions"}, {"text": "➕ Add Group", "callback_data": "public_group"}],
                            [{"text": "📋 Groups", "callback_data": "show_groups"}, {"text": "🚪 Leave VC", "callback_data": "leave_vc"}]
                        ]}
                        
                        # Add sudo button for owner
                        if user_id == OWNER_ID:
                            kb["inline_keyboard"].append([{"text": "👑 Manage Sudo Users", "callback_data": "show_sudo"}])
                        
                        # Send image with caption and buttons
                        send_photo(chat_id, IMAGE_URL, caption, kb)
                    
                    elif text == "/add":
                        kb = {"inline_keyboard": [
                            [{"text": "🌐 Public", "callback_data": "public_group"}, {"text": "🔒 Private", "callback_data": "private_group"}]
                        ]}
                        send_message(chat_id, "Select type:", kb)
                    
                    elif text == "/groups":
                        if not groups_list:
                            send_message(chat_id, "No groups added! Use /add")
                        else:
                            kb = {"inline_keyboard": []}
                            for i, grp in enumerate(groups_list):
                                kb["inline_keyboard"].append([{"text": f"📌 {grp['name']}", "callback_data": f"select_group_{i}"}])
                            send_message(chat_id, "Your Groups:", kb)
                    
                    elif text == "/sessions":
                        show_all_sessions(chat_id)
                    
                    elif text == "/leavevc":
                        show_leave_groups(chat_id)
                    
                    elif text.startswith("/joinvc"):
                        parts = text.split()
                        if len(parts) != 2:
                            send_message(chat_id, "Usage: /joinvc <count>\nExample: /joinvc 5")
                            continue
                        try:
                            count = int(parts[1])
                        except:
                            send_message(chat_id, "Invalid count!")
                            continue
                        
                        if not current_group:
                            send_message(chat_id, "No group selected! Use /groups")
                            continue
                        if len(user_sessions) == 0:
                            send_message(chat_id, "No sessions added! Use /start to add sessions")
                            continue
                        if count > len(user_sessions):
                            send_message(chat_id, f"Only {len(user_sessions)} sessions available!")
                            continue
                        
                        send_message(chat_id, f"🎤 Joining {count} accounts to {current_group['name']}...")
                        results = await join_voice_chat(current_group["chat_id"], current_group["name"], count)
                        
                        scount = sum(1 for r in results if r["success"])
                        msg_text = f"**✅ Joined: {scount}/{count}**\n\n"
                        for r in results:
                            if r["success"]:
                                msg_text += f"✅ {r['name']}\n"
                            else:
                                msg_text += f"❌ {r['name']}: {r['error']}\n"
                        send_message(chat_id, msg_text)
                    
                    elif text == "/status":
                        status_text = f"**📊 Status**\n\n"
                        status_text += f"📱 Sessions: {len(user_sessions)}\n"
                        status_text += f"🔌 Connected: {len(user_clients)}\n"
                        status_text += f"🎤 Active VC: {len(active_vc)}\n"
                        status_text += f"📋 Groups: {len(groups_list)}\n"
                        status_text += f"👑 Sudo Users: {len(sudo_users)}\n"
                        if current_group:
                            status_text += f"\n📍 Current: {current_group['name']}"
                        send_message(chat_id, status_text)
                    
                    elif text == "/done":
                        send_message(chat_id, f"✅ Done! Total sessions: {len(user_sessions)}")
                        if user_id in user_states:
                            del user_states[user_id]
                    
                    # Handle session string input
                    elif user_id in user_states and user_states[user_id].get("step") == "awaiting_session":
                        if len(text) > 50:
                            send_message(chat_id, "⏳ Testing session...")
                            result = await test_session(text)
                            if result["success"]:
                                exists = False
                                for s in user_sessions:
                                    if s["id"] == result["id"]:
                                        exists = True
                                        break
                                if exists:
                                    send_message(chat_id, f"⚠️ Session for {result['name']} already exists!")
                                else:
                                    user_sessions.append({
                                        "string": text,
                                        "name": result["name"],
                                        "id": result["id"],
                                        "username": result["username"]
                                    })
                                    send_message(chat_id, f"✅ **Session Added!**\n\n👤 {result['name']}\n🆔 `{result['id']}`\n📊 Total: {len(user_sessions)}\n\nSend more or type /done")
                            else:
                                send_message(chat_id, f"❌ Invalid session: {result['error']}")
                        else:
                            send_message(chat_id, "❌ Invalid session string!")
                    
                    # Handle public group username
                    elif user_id in user_states and user_states[user_id].get("step") == "public_username":
                        username = text.replace("@", "")
                        send_message(chat_id, f"⏳ Resolving @{username}...")
                        try:
                            resp = requests.get(f"{API_URL}/getChat", params={"chat_id": f"@{username}"}, timeout=10)
                            if resp.ok:
                                ci = resp.json()["result"]
                                gtitle = ci.get("title", username)
                                gcid = ci["id"]
                                groups_list.append({"name": gtitle, "chat_id": gcid, "username": username})
                                current_group = groups_list[-1]
                                send_message(chat_id, f"✅ **Group Added!**\n\n📌 {gtitle}\n🆔 `{gcid}`\n\nUse /joinvc <count> to join voice chat")
                            else:
                                send_message(chat_id, f"❌ Could not resolve @{username}\n\nMake sure the username is correct and accounts are added to the group.")
                        except Exception as e:
                            send_message(chat_id, f"❌ Error: {e}")
                        del user_states[user_id]
                    
                    # Handle private group link
                    elif user_id in user_states and user_states[user_id].get("step") == "private_link":
                        user_states[user_id] = {"step": "private_chatid", "link": text}
                        send_message(chat_id, "Send Chat ID (example: -1001234567890)")
                    
                    # Handle private group chat_id
                    elif user_id in user_states and user_states[user_id].get("step") == "private_chatid":
                        try:
                            cid = int(text)
                            groups_list.append({"name": f"Private_{cid}", "chat_id": cid, "invite_link": user_states[user_id]["link"]})
                            current_group = groups_list[-1]
                            send_message(chat_id, f"✅ **Private Group Added!**\n\n🆔 `{cid}`\n\nUse /joinvc <count> to join voice chat")
                            del user_states[user_id]
                        except:
                            send_message(chat_id, "Invalid Chat ID!")
        
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
