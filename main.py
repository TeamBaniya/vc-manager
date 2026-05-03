import requests
import time
import json
import asyncio
import os
import re
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired
from pytgcalls import GroupCallFactory
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID

TOKEN = BOT_TOKEN
API_URL = f"https://api.telegram.org/bot{TOKEN}"


user_sessions = []
user_clients = {}
active_vc = {}
groups_list = []
current_group = None
last_update_id = 0
user_states = {}
leave_selected_group = {}
temp_session_data = {}

print("="*60)
print("🤖 VC BOT - WITH OTP AUTO READ")
print("="*60)
print("Bot started! Send /start on Telegram\n")

def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(f"{API_URL}/sendMessage", json=data, timeout=5)
    except Exception as e:
        print(f"Send error: {e}")

def extract_otp(text):
    """Extract OTP from text (removes spaces, special characters)"""
    # Remove spaces and special characters
    cleaned = re.sub(r'[\s\-_]+', '', text)
    # Extract only digits
    digits = re.sub(r'\D', '', cleaned)
    return digits

async def test_session(session_string):
    try:
        client = Client("test_temp", api_id=API_ID, api_hash=API_HASH, session_string=session_string)
        await client.start()
        me = await client.get_me()
        await client.stop()
        return {"success": True, "name": me.first_name, "id": me.id, "username": me.username}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def create_new_session(phone_number, chat_id):
    try:
        client = Client(f"new_session_{phone_number}", api_id=API_ID, api_hash=API_HASH)
        await client.connect()
        sent_code = await client.send_code(phone_number)
        temp_session_data[chat_id] = {
            "client": client,
            "phone": phone_number,
            "phone_code_hash": sent_code.phone_code_hash,
            "step": "waiting_otp"
        }
        send_message(chat_id, f"📨 **OTP Sent!**\n\nPhone: `{phone_number}`\n\nPlease send the OTP code you received on Telegram.\n\nExample: `1 2 3 4 5` or `12345`\n\n⏰ OTP expires in 60 seconds.")
        print(f"OTP sent to {phone_number} for chat {chat_id}")
        return True
    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}")
        return False

async def verify_session_otp(chat_id, raw_code):
    if chat_id not in temp_session_data:
        send_message(chat_id, "❌ Session expired! Please start over with /start")
        return False
    
    # Extract OTP from text (remove spaces, special chars)
    code = extract_otp(raw_code)
    print(f"📱 Extracted OTP: {code} from: {raw_code}")
    
    if not code or len(code) < 5:
        send_message(chat_id, f"❌ **Invalid OTP Format!**\n\nYou sent: `{raw_code}`\nExtracted: `{code}`\n\nOTP should be 5-6 digits.\n\nPlease send again:")
        return False
    
    data = temp_session_data[chat_id]
    client = data["client"]
    
    try:
        send_message(chat_id, f"⏳ Verifying OTP `{code}`...")
        print(f"Verifying OTP: {code} for {data['phone']}")
        
        await client.sign_in(data["phone"], code, phone_code_hash=data["phone_code_hash"])
        me = await client.get_me()
        
        session_string = await client.export_session_string()
        
        user_sessions.append({
            "string": session_string,
            "name": me.first_name,
            "id": me.id,
            "username": me.username or ""
        })
        
        kb = {"inline_keyboard": [
            [{"text": "✅ Tap to Connect", "callback_data": f"connect_session_{len(user_sessions)-1}"}]
        ]}
        
        send_message(chat_id, f"✅ **Session Created Successfully!**\n\n👤 **Name:** {me.first_name}\n🆔 **ID:** `{me.id}`\n🔖 **Username:** @{me.username or 'None'}\n\n📊 **Total Sessions:** `{len(user_sessions)}`\n\nTap below to connect this session:", kb)
        
        await client.stop()
        del temp_session_data[chat_id]
        return True
        
    except SessionPasswordNeeded:
        temp_session_data[chat_id]["step"] = "waiting_2fa"
        send_message(chat_id, "🔐 **2FA Enabled**\n\nPlease send your 2FA password:")
        return False
    except PhoneCodeInvalid:
        send_message(chat_id, f"❌ **Invalid OTP!** `{code}` is not correct.\n\nPlease check your Telegram app and send the correct OTP code again:")
        return False
    except PhoneCodeExpired:
        send_message(chat_id, "❌ **OTP Expired!** Please start over with /start")
        del temp_session_data[chat_id]
        return False
    except Exception as e:
        error_msg = str(e)
        send_message(chat_id, f"❌ Error: {error_msg[:100]}\n\nPlease try again with /start")
        print(f"Verification error: {error_msg}")
        return False

async def verify_session_2fa(chat_id, password):
    if chat_id not in temp_session_data:
        send_message(chat_id, "❌ Session expired! Please start over.")
        return False
    
    data = temp_session_data[chat_id]
    client = data["client"]
    
    try:
        await client.check_password(password)
        me = await client.get_me()
        
        session_string = await client.export_session_string()
        
        user_sessions.append({
            "string": session_string,
            "name": me.first_name,
            "id": me.id,
            "username": me.username or ""
        })
        
        kb = {"inline_keyboard": [
            [{"text": "✅ Tap to Connect", "callback_data": f"connect_session_{len(user_sessions)-1}"}]
        ]}
        
        send_message(chat_id, f"✅ **Session Created Successfully!**\n\n👤 **Name:** {me.first_name}\n🆔 **ID:** `{me.id}`\n🔖 **Username:** @{me.username or 'None'}\n\n📊 **Total Sessions:** `{len(user_sessions)}`\n\nTap below to connect this session:", kb)
        
        await client.stop()
        del temp_session_data[chat_id]
        return True
    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}\n\nPlease send 2FA password again:")
        return False

async def connect_session(chat_id, session_index):
    if session_index >= len(user_sessions):
        send_message(chat_id, "❌ Session not found!")
        return
    
    session_data = user_sessions[session_index]
    acc_name = session_data["name"]
    
    try:
        if acc_name not in user_clients:
            send_message(chat_id, f"⏳ Connecting {acc_name}...")
            client = Client(f"sessions/{acc_name}", api_id=API_ID, api_hash=API_HASH, session_string=session_data["string"])
            await client.start()
            user_clients[acc_name] = client
            
            factory = GroupCallFactory(client)
            vc = factory.get_file_group_call()
            await vc.start()
            user_clients[f"{acc_name}_vc"] = vc
            
            send_message(chat_id, f"✅ **Connected!**\n\n👤 {acc_name} is now online!\n\nUse `/joinvc <count>` to join voice chat.")
        else:
            send_message(chat_id, f"✅ {acc_name} is already connected!")
    except Exception as e:
        send_message(chat_id, f"❌ Failed to connect {acc_name}: {str(e)[:100]}")

async def join_voice_chat(chat_id, group_name, count):
    results = []
    
    for i, session_data in enumerate(user_sessions[:count]):
        acc_name = session_data["name"]
        acc_id = session_data["id"]
        
        try:
            if acc_name not in user_clients:
                client = Client(f"sessions/{acc_name}", api_id=API_ID, api_hash=API_HASH, session_string=session_data["string"])
                await client.start()
                user_clients[acc_name] = client
                factory = GroupCallFactory(client)
                vc = factory.get_file_group_call()
                await vc.start()
                user_clients[f"{acc_name}_vc"] = vc
            
            vc = user_clients.get(f"{acc_name}_vc")
            if not vc:
                results.append({"success": False, "name": acc_name, "id": acc_id, "error": "Not connected!"})
                continue
                
            await vc.join(current_group["chat_id"])
            active_vc[acc_name] = {"vc": vc, "group_id": current_group["chat_id"], "group_name": group_name}
            results.append({"success": True, "name": acc_name, "id": acc_id})
            print(f"  ✅ {acc_name} joined {group_name}")
        except Exception as e:
            error_msg = str(e)
            if "not active" in error_msg.lower():
                results.append({"success": False, "name": acc_name, "id": acc_id, "error": "Voice chat not active!"})
            else:
                results.append({"success": False, "name": acc_name, "id": acc_id, "error": error_msg[:50]})
            print(f"  ❌ {acc_name} failed")
        
        await asyncio.sleep(2)
    return results

async def leave_specific_accounts(group_id, count):
    results = []
    accounts_to_leave = []
    for name, data in active_vc.items():
        if data["group_id"] == group_id:
            accounts_to_leave.append(name)
    for name in accounts_to_leave[:count]:
        try:
            await active_vc[name]["vc"].stop()
            results.append({"success": True, "name": name})
            print(f"  ✅ {name} left")
        except Exception as e:
            results.append({"success": False, "name": name, "error": str(e)[:30]})
        if name in active_vc:
            del active_vc[name]
        await asyncio.sleep(1)
    return results

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

async def handle_callback(chat_id, user_id, data_cb):
    if data_cb.startswith("connect_session_"):
        idx = int(data_cb.split("_")[2])
        await connect_session(chat_id, idx)
    
    elif data_cb == "connect_existing":
        user_states[user_id] = {"step": "awaiting_session"}
        send_message(chat_id, "📱 **Send Pyrogram String Session**\n\nGet from @StringSessionBot\nType `/done` when finished")
    
    elif data_cb == "create_new_session":
        send_message(chat_id, "📱 **Create New Session**\n\nSend your phone number with country code:\nExample: `+919876543210`")
        user_states[user_id] = {"step": "waiting_phone"}
    
    elif data_cb == "status":
        status_text = f"**📊 Status**\nSessions: {len(user_sessions)}\nActive VC: {len(active_vc)}\nGroups: {len(groups_list)}"
        send_message(chat_id, status_text)
    
    elif data_cb == "public_group":
        user_states[user_id] = {"step": "public_username"}
        send_message(chat_id, "📝 Send group @username")
    
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
    
    elif data_cb.startswith("select_group_"):
        idx = int(data_cb.split("_")[2])
        if idx < len(groups_list):
            global current_group
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
            send_message(chat_id, f"🎤 Group: {gname}\n👥 Active accounts: {tcount}\n\n📝 **Send number of accounts to leave** (1 to {tcount})")
    
    elif data_cb == "cancel_leave":
        send_message(chat_id, "❌ Cancelled")
        if user_id in leave_selected_group:
            del leave_selected_group[user_id]

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
                    
                    if user_id != OWNER_ID:
                        send_message(chat_id, "❌ Access Denied! Only bot owner can use this bot.")
                        requests.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": callback["id"]})
                        continue
                    
                    await handle_callback(chat_id, user_id, data_cb)
                    requests.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": callback["id"]})
                
                elif "message" in update:
                    msg = update["message"]
                    user_id = msg["from"]["id"]
                    chat_id = msg["chat"]["id"]
                    text = msg.get("text", "")
                    print(f"\n📨 Message: {text}")
                    
                    if user_id != OWNER_ID:
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
                                send_message(chat_id, f"✅ Left {scount} accounts from {group_info['group_name']}")
                                del leave_selected_group[user_id]
                        except ValueError:
                            send_message(chat_id, "❌ Please send a valid number!")
                        continue
                    
                    # Handle phone number input
                    if user_id in user_states and user_states[user_id].get("step") == "waiting_phone":
                        phone = text.strip()
                        if phone.startswith("+") and len(phone) > 8:
                            send_message(chat_id, "⏳ Creating session...")
                            await create_new_session(phone, chat_id)
                            del user_states[user_id]
                        else:
                            send_message(chat_id, "❌ Invalid phone number! Example: +919876543210")
                        continue
                    
                    # Handle OTP input
                    if chat_id in temp_session_data and temp_session_data[chat_id].get("step") == "waiting_otp":
                        await verify_session_otp(chat_id, text)
                        continue
                    
                    # Handle 2FA input
                    if chat_id in temp_session_data and temp_session_data[chat_id].get("step") == "waiting_2fa":
                        await verify_session_2fa(chat_id, text.strip())
                        continue
                    
                    # Handle existing session string
                    if user_id in user_states and user_states[user_id].get("step") == "awaiting_session":
                        if len(text) > 50:
                            send_message(chat_id, "⏳ Testing session...")
                            result = await test_session(text)
                            if result["success"]:
                                user_sessions.append({
                                    "string": text,
                                    "name": result["name"],
                                    "id": result["id"],
                                    "username": result["username"]
                                })
                                kb = {"inline_keyboard": [
                                    [{"text": "✅ Tap to Connect", "callback_data": f"connect_session_{len(user_sessions)-1}"}]
                                ]}
                                send_message(chat_id, f"✅ **Session Added!**\n\n👤 {result['name']}\n🆔 `{result['id']}`\n📊 Total: `{len(user_sessions)}`\n\nTap below to connect:", kb)
                                del user_states[user_id]
                            else:
                                send_message(chat_id, f"❌ Invalid session: {result['error']}")
                        else:
                            send_message(chat_id, "❌ Invalid session string!")
                        continue
                    
                    # Regular commands
                    if text == "/start":
                        kb = {"inline_keyboard": [
                            [{"text": "🔌 Connect Existing Session", "callback_data": "connect_existing"}],
                            [{"text": "✨ Create New Session", "callback_data": "create_new_session"}],
                            [{"text": "📊 Status", "callback_data": "status"}],
                            [{"text": "➕ Add Group", "callback_data": "public_group"}],
                            [{"text": "📋 Groups", "callback_data": "show_groups"}],
                            [{"text": "🚪 Leave VC", "callback_data": "leave_vc"}]
                        ]}
                        send_message(chat_id, "**🎵 VC Manager Bot**\n\nChoose an option below:", kb)
                    
                    elif text == "/add":
                        kb = {"inline_keyboard": [
                            [{"text": "🌐 Public", "callback_data": "public_group"}],
                            [{"text": "🔒 Private", "callback_data": "private_group"}]
                        ]}
                        send_message(chat_id, "Select type:", kb)
                    
                    elif text == "/groups":
                        if not groups_list:
                            send_message(chat_id, "No groups added!")
                        else:
                            kb = {"inline_keyboard": []}
                            for i, grp in enumerate(groups_list):
                                kb["inline_keyboard"].append([{"text": f"📌 {grp['name']}", "callback_data": f"select_group_{i}"}])
                            send_message(chat_id, "Your Groups:", kb)
                    
                    elif text == "/leavevc":
                        show_leave_groups(chat_id)
                    
                    elif text.startswith("/joinvc"):
                        parts = text.split()
                        if len(parts) != 2:
                            send_message(chat_id, "Usage: /joinvc <count>")
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
                            send_message(chat_id, "No sessions added!")
                            continue
                        if count > len(user_sessions):
                            send_message(chat_id, f"Only {len(user_sessions)} sessions available")
                            continue
                        send_message(chat_id, f"🎤 Joining {count} accounts to {current_group['name']}...")
                        results = await join_voice_chat(chat_id, current_group["name"], count)
                        scount = sum(1 for r in results if r["success"])
                        msg_text = f"✅ Joined: {scount}/{count}\n"
                        for r in results:
                            if r["success"]:
                                msg_text += f"✅ {r['name']}\n"
                            else:
                                msg_text += f"❌ {r['name']}: {r['error']}\n"
                        send_message(chat_id, msg_text)
                    
                    elif text == "/status":
                        status_text = f"**📊 Status**\nSessions: {len(user_sessions)}\nActive VC: {len(active_vc)}\nGroups: {len(groups_list)}"
                        if current_group:
                            status_text += f"\nCurrent: {current_group['name']}"
                        send_message(chat_id, status_text)
                    
                    elif text == "/done":
                        send_message(chat_id, f"✅ Done! Total sessions: {len(user_sessions)}")
                        if user_id in user_states:
                            del user_states[user_id]
                    
                    elif user_id in user_states and user_states[user_id].get("step") == "public_username":
                        username = text.replace("@", "")
                        try:
                            resp = requests.get(f"{API_URL}/getChat", params={"chat_id": f"@{username}"}, timeout=10)
                            if resp.ok:
                                ci = resp.json()["result"]
                                gtitle = ci.get("title", username)
                                gcid = ci["id"]
                                groups_list.append({"name": gtitle, "chat_id": gcid, "username": username})
                                current_group = groups_list[-1]
                                send_message(chat_id, f"✅ Added: {gtitle}\nUse /joinvc")
                            else:
                                send_message(chat_id, f"❌ Could not resolve @{username}")
                        except Exception as e:
                            send_message(chat_id, f"❌ Error: {e}")
                        del user_states[user_id]
                    
                    elif user_id in user_states and user_states[user_id].get("step") == "private_link":
                        user_states[user_id] = {"step": "private_chatid", "link": text}
                        send_message(chat_id, "Send Chat ID")
                    
                    elif user_id in user_states and user_states[user_id].get("step") == "private_chatid":
                        try:
                            cid = int(text)
                            groups_list.append({"name": f"Private_{cid}", "chat_id": cid, "invite_link": user_states[user_id]["link"]})
                            current_group = groups_list[-1]
                            send_message(chat_id, f"✅ Added Private Group\nUse /joinvc")
                            del user_states[user_id]
                        except:
                            send_message(chat_id, "Invalid Chat ID!")
        
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
