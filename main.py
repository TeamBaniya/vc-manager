import requests
import time
import json
import asyncio
from pyrogram import Client
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

print("="*60)
print("🤖 VC BOT - SMART LEAVE SYSTEM")
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
                print(f"  Creating client for {acc_name}...")
                client = Client(f"sessions/{acc_name}", api_id=API_ID, api_hash=API_HASH, session_string=session_string)
                await client.start()
                user_clients[acc_name] = client
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
                else:
                    results.append({"success": False, "name": acc_name, "id": acc_id, "error": error_msg[:50]})
                print(f"  ❌ {acc_name} failed")
        except Exception as e:
            results.append({"success": False, "name": acc_name, "id": acc_id, "error": str(e)[:50]})
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
                if data_cb == "connect":
                    user_states[user_id] = {"step": "awaiting_session"}
                    send_message(chat_id, "📱 Send Pyrogram String Session\nType /done when finished")
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
                            send_message(chat_id, f"❌ Only {group_info['total']} accounts active! Send smaller number.")
                        else:
                            send_message(chat_id, f"🚪 Leaving {count} accounts from {group_info['group_name']}...")
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            results = loop.run_until_complete(leave_specific_accounts(group_info["group_id"], count))
                            loop.close()
                            scount = sum(1 for r in results if r["success"])
                            send_message(chat_id, f"✅ Left {scount} accounts from {group_info['group_name']}")
                            del leave_selected_group[user_id]
                    except ValueError:
                        send_message(chat_id, "❌ Please send a valid number!")
                    continue
                if text == "/start":
                    kb = {"inline_keyboard": [
                        [{"text": "🔌 Connect", "callback_data": "connect"}],
                        [{"text": "📊 Status", "callback_data": "status"}],
                        [{"text": "➕ Add Group", "callback_data": "public_group"}],
                        [{"text": "📋 Groups", "callback_data": "show_groups"}],
                        [{"text": "🚪 Leave VC", "callback_data": "leave_vc"}]
                    ]}
                    send_message(chat_id, "**🎵 VC Manager Bot**\n\n/add - Add group\n/joinvc <count> - Join VC\n/leavevc - Smart leave\n/groups - All groups\n/status - Status\n/done - Done", kb)
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
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    results = loop.run_until_complete(join_voice_chat(current_group["chat_id"], current_group["name"], count))
                    loop.close()
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
                elif user_id in user_states and user_states[user_id].get("step") == "awaiting_session":
                    if len(text) > 50:
                        send_message(chat_id, "⏳ Testing session...")
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        result = loop.run_until_complete(test_session(text))
                        loop.close()
                        if result["success"]:
                            user_sessions.append({
                                "string": text,
                                "name": result["name"],
                                "id": result["id"],
                                "username": result["username"]
                            })
                            send_message(chat_id, f"✅ Added: {result['name']}\nTotal: {len(user_sessions)}")
                        else:
                            send_message(chat_id, f"❌ Invalid: {result['error']}")
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
        time.sleep(1)
    except KeyboardInterrupt:
        print("\nBot stopped")
        break
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(5)
