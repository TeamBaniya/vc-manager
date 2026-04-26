import requests
import time
import json
import asyncio
from pyrogram import Client
from pytgcalls import GroupCallFactory
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID

TOKEN = BOT_TOKEN
API_URL = f"https://api.telegram.org/bot{TOKEN}"

# Data storage
user_sessions = []
user_clients = {}
active_vc = {}  # {account_name: {"vc": vc_obj, "group_id": chat_id, "group_name": name}}
groups_list = []
current_group = None
last_update_id = 0
user_states = {}
leave_temp = {}  # Temporary storage for leave group info

print("="*60)
print("🤖 VC BOT - MULTI GROUP SUPPORT WITH SMART LEAVE")
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
                    results.append({"success": False, "name": acc_name, "id": acc_id, "error": "Voice chat not active! Start VC first."})
                else:
                    results.append({"success": False, "name": acc_name, "id": acc_id, "error": error_msg[:50]})
                print(f"  ❌ {acc_name} failed: {error_msg[:50]}")
            
        except Exception as e:
            results.append({"success": False, "name": acc_name, "id": acc_id, "error": str(e)[:50]})
            print(f"  ❌ {acc_name} error: {e}")
        
        await asyncio.sleep(2)
    return results

async def leave_specific_accounts(group_id, count):
    """Leave specific number of accounts from a group"""
    results = []
    accounts_to_leave = []
    
    # Find accounts in the specified group
    for name, data in active_vc.items():
        if data["group_id"] == group_id:
            accounts_to_leave.append(name)
    
    # Leave only 'count' accounts
    for name in accounts_to_leave[:count]:
        try:
            await active_vc[name]["vc"].stop()
            results.append({"success": True, "name": name})
            print(f"  ✅ {name} left")
        except Exception as e:
            results.append({"success": False, "name": name, "error": str(e)[:30]})
            print(f"  ❌ {name} failed to leave: {e}")
        
        # Remove from active_vc
        del active_vc[name]
        await asyncio.sleep(1)
    
    return results

def show_leave_groups(chat_id):
    """Show groups with active VC for leave selection"""
    groups_with_vc = {}
    for name, data in active_vc.items():
        group_name = data["group_name"]
        group_id = data["group_id"]
        if group_id not in groups_with_vc:
            groups_with_vc[group_id] = {"name": group_name, "count": 0}
        groups_with_vc[group_id]["count"] += 1
    
    if not groups_with_vc:
        send_message(chat_id, "❌ **No active voice chats!**")
        return
    
    keyboard = {"inline_keyboard": []}
    for group_id, info in groups_with_vc.items():
        keyboard["inline_keyboard"].append([
            {"text": f"🎤 {info['name']} ({info['count']} accounts)", "callback_data": f"leave_group_{group_id}"}
        ])
    keyboard["inline_keyboard"].append([
        {"text": "❌ Cancel", "callback_data": "cancel_leave"}
    ])
    
    send_message(chat_id, "**📋 Select group to leave:**\n\nChoose which group's accounts you want to leave:", keyboard)

def show_leave_count(chat_id, group_id, group_name, total_count):
    """Show count selection for leave"""
    keyboard = {"inline_keyboard": []}
    
    # Add count buttons in rows of 3
    counts = [1, 2, 3, 4, 5, 10, 15, 20, total_count]
    row = []
    for count in counts:
        if count <= total_count:
            row.append({"text": f"{count}", "callback_data": f"leave_count_{group_id}_{count}"})
        if len(row) == 3:
            keyboard["inline_keyboard"].append(row)
            row = []
    if row:
        keyboard["inline_keyboard"].append(row)
    
    keyboard["inline_keyboard"].append([
        {"text": "🔙 Back", "callback_data": "back_to_groups"}
    ])
    
    send_message(chat_id, f"**🎤 Group:** `{group_name}`\n**👥 Active accounts:** `{total_count}`\n\n**How many accounts do you want to leave?**", keyboard)

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
            
            # Handle callback queries
            if "callback_query" in update:
                callback = update["callback_query"]
                user_id = callback["from"]["id"]
                chat_id = callback["message"]["chat"]["id"]
                data_cb = callback["data"]
                
                print(f"\n📞 Callback: {data_cb}")
                
                # Connection
                if data_cb == "connect":
                    user_states[user_id] = {"step": "awaiting_session"}
                    send_message(chat_id, "📱 **Send Pyrogram String Session**\n\nGet from @StringSessionBot\nType `/done` when finished")
                
                # Status
                elif data_cb == "status":
                    status_text = f"**📊 Bot Status**\n\n"
                    status_text += f"📱 Total Sessions: `{len(user_sessions)}`\n"
                    status_text += f"🎤 Active in VC: `{len(active_vc)}`\n"
                    status_text += f"📋 Groups Added: `{len(groups_list)}`\n\n"
                    
                    if current_group:
                        status_text += f"**📍 Current Active Group:**\n"
                        status_text += f"   Name: `{current_group['name']}`\n"
                        status_text += f"   Chat ID: `{current_group['chat_id']}`\n\n"
                    
                    if active_vc:
                        status_text += f"**🎤 Accounts in Voice Chat:**\n"
                        group_summary = {}
                        for name, data in active_vc.items():
                            gname = data['group_name']
                            if gname not in group_summary:
                                group_summary[gname] = []
                            group_summary[gname].append(name)
                        for gname, accounts in group_summary.items():
                            status_text += f"   📍 `{gname}`: {len(accounts)} accounts\n"
                            for acc in accounts:
                                status_text += f"      • `{acc}`\n"
                    else:
                        status_text += f"**🎤 Accounts in Voice Chat:**\n   None\n"
                    
                    send_message(chat_id, status_text)
                
                # Add group
                elif data_cb == "public_group":
                    user_states[user_id] = {"step": "public_username"}
                    send_message(chat_id, "📝 **Send group @username**\nExample: `@mygroup`")
                
                elif data_cb == "private_group":
                    user_states[user_id] = {"step": "private_link"}
                    send_message(chat_id, "🔗 **Send group invite link**")
                
                # Show groups list
                elif data_cb == "show_groups":
                    if not groups_list:
                        send_message(chat_id, "❌ No groups added! Use `/add` first")
                    else:
                        keyboard = {"inline_keyboard": []}
                        for i, group in enumerate(groups_list):
                            keyboard["inline_keyboard"].append([
                                {"text": f"📌 {group['name']}", "callback_data": f"select_group_{i}"}
                            ])
                        keyboard["inline_keyboard"].append([
                            {"text": "📊 Status", "callback_data": "status"}
                        ])
                        send_message(chat_id, "**📋 Your Groups:**\n\nSelect a group to make it active:", keyboard)
                
                # Select group
                elif data_cb.startswith("select_group_"):
                    index = int(data_cb.split("_")[2])
                    if index < len(groups_list):
                        current_group = groups_list[index]
                        send_message(chat_id, f"✅ **Switched to group:** `{current_group['name']}`\n\nNow use `/joinvc <count>` to join voice chat")
                    else:
                        send_message(chat_id, "❌ Group not found!")
                
                # Leave VC - Show groups with active VC
                elif data_cb == "leave_vc":
                    show_leave_groups(chat_id)
                
                # Leave group selected
                elif data_cb.startswith("leave_group_"):
                    group_id = int(data_cb.split("_")[2])
                    # Find group name and count
                    group_name = None
                    total_count = 0
                    for name, data in active_vc.items():
                        if data["group_id"] == group_id:
                            group_name = data["group_name"]
                            total_count += 1
                    
                    if group_name:
                        leave_temp[user_id] = {"group_id": group_id, "group_name": group_name}
                        show_leave_count(chat_id, group_id, group_name, total_count)
                    else:
                        send_message(chat_id, "❌ No active accounts in this group!")
                
                # Leave count selected
                elif data_cb.startswith("leave_count_"):
                    parts = data_cb.split("_")
                    group_id = int(parts[2])
                    count = int(parts[3])
                    
                    send_message(chat_id, f"🚪 **Leaving {count} accounts from group...**")
                    print(f"  🚪 Leaving {count} accounts from group {group_id}")
                    
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    results = loop.run_until_complete(leave_specific_accounts(group_id, count))
                    loop.close()
                    
                    success_count = sum(1 for r in results if r["success"])
                    
                    if success_count > 0:
                        send_message(chat_id, f"✅ **Left {success_count} accounts from voice chat**")
                    else:
                        send_message(chat_id, f"❌ Failed to leave accounts")
                    
                    if user_id in leave_temp:
                        del leave_temp[user_id]
                
                # Back to groups
                elif data_cb == "back_to_groups":
                    show_leave_groups(chat_id)
                
                # Cancel leave
                elif data_cb == "cancel_leave":
                    send_message(chat_id, "❌ Cancelled")
                    if user_id in leave_temp:
                        del leave_temp[user_id]
                
                requests.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": callback["id"]})
            
            # Handle messages
            elif "message" in update:
                msg = update["message"]
                user_id = msg["from"]["id"]
                chat_id = msg["chat"]["id"]
                text = msg.get("text", "")
                
                print(f"\n📨 Message: {text}")
                
                if user_id != OWNER_ID:
                    continue
                
                # Start command
                if text == "/start":
                    keyboard = {
                        "inline_keyboard": [
                            [{"text": "🔌 Connect Session", "callback_data": "connect"}],
                            [{"text": "📊 Status", "callback_data": "status"}],
                            [{"text": "➕ Add Group", "callback_data": "public_group"}],
                            [{"text": "📋 My Groups", "callback_data": "show_groups"}],
                            [{"text": "🚪 Leave VC", "callback_data": "leave_vc"}]
                        ]
                    }
                    send_message(chat_id, "**🎵 VC Manager Bot**\n\nManage multiple accounts in voice chats!\n\n**Commands:**\n/add - Add new group\n/joinvc <count> - Join VC\n/leavevc - Leave VC (smart leave)\n/groups - Show all groups\n/status - Bot status\n/done - Finish adding sessions", keyboard)
                
                # Add command
                elif text == "/add":
                    keyboard = {
                        "inline_keyboard": [
                            [{"text": "🌐 Public Group", "callback_data": "public_group"}],
                            [{"text": "🔒 Private Group", "callback_data": "private_group"}]
                        ]
                    }
                    send_message(chat_id, "**Select group type:**", keyboard)
                
                # Groups command
                elif text == "/groups":
                    if not groups_list:
                        send_message(chat_id, "❌ No groups added! Use `/add` first")
                    else:
                        keyboard = {"inline_keyboard": []}
                        for i, group in enumerate(groups_list):
                            keyboard["inline_keyboard"].append([
                                {"text": f"📌 {group['name']}", "callback_data": f"select_group_{i}"}
                            ])
                        send_message(chat_id, "**📋 Your Groups:**\n\nSelect a group to make it active:", keyboard)
                
                # Leavevc command - smart leave
                elif text == "/leavevc":
                    show_leave_groups(chat_id)
                
                # Joinvc command
                elif text.startswith("/joinvc"):
                    parts = text.split()
                    if len(parts) != 2:
                        send_message(chat_id, "❌ **Usage:** `/joinvc <count>`\nExample: `/joinvc 5`")
                        continue
                    
                    try:
                        count = int(parts[1])
                    except:
                        send_message(chat_id, "❌ Count must be a number!")
                        continue
                    
                    if not current_group:
                        send_message(chat_id, "❌ **No group selected!**\nUse `/groups` to select a group or `/add` to add a new group")
                        continue
                    
                    if len(user_sessions) == 0:
                        send_message(chat_id, "❌ **No sessions added!** Use `/start` and connect sessions")
                        continue
                    
                    if count > len(user_sessions):
                        send_message(chat_id, f"❌ Only `{len(user_sessions)}` sessions available")
                        continue
                    
                    group_name = current_group["name"]
                    group_chat_id = current_group["chat_id"]
                    
                    send_message(chat_id, f"🎤 **Joining {count} accounts to {group_name}...**\n⏳ Please wait...")
                    print(f"  🎤 Joining {count} accounts to {group_name}")
                    
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    results = loop.run_until_complete(join_voice_chat(group_chat_id, group_name, count))
                    loop.close()
                    
                    success_count = sum(1 for r in results if r["success"])
                    
                    result_text = f"**🎉 Voice Chat Join Result**\n\n"
                    result_text += f"📍 **Group:** `{group_name}`\n"
                    result_text += f"✅ **Joined:** `{success_count}/{count}`\n\n"
                    result_text += f"**📋 Details:**\n"
                    
                    for r in results:
                        if r["success"]:
                            result_text += f"✅ `{r['name']}` (ID: `{r['id']}`)\n"
                        else:
                            result_text += f"❌ `{r['name']}`: `{r['error']}`\n"
                    
                    if success_count == 0:
                        result_text += f"\n⚠️ **Note:** Voice chat must be active in the group first!"
                    
                    send_message(chat_id, result_text)
                    print(f"  ✅ Join completed: {success_count} joined")
                
                # Status command
                elif text == "/status":
                    status_text = f"**📊 Bot Status**\n\n"
                    status_text += f"📱 **Sessions:** `{len(user_sessions)}`\n"
                    status_text += f"🎤 **Active VCs:** `{len(active_vc)}`\n"
                    status_text += f"📋 **Groups:** `{len(groups_list)}`\n\n"
                    
                    if current_group:
                        status_text += f"**📍 Current Group:**\n"
                        status_text += f"   Name: `{current_group['name']}`\n"
                        status_text += f"   Chat ID: `{current_group['chat_id']}`\n\n"
                    
                    if groups_list:
                        status_text += f"**📋 All Groups:**\n"
                        for i, g in enumerate(groups_list, 1):
                            status_text += f"{i}. `{g['name']}`\n"
                    else:
                        status_text += f"**📋 All Groups:**\n   No groups added\n"
                    
                    status_text += f"\n**📋 Sessions:**\n"
                    for i, s in enumerate(user_sessions, 1):
                        status_text += f"{i}. `{s['name']}` (ID: `{s['id']}`)\n"
                    
                    if active_vc:
                        status_text += f"\n**🎤 Currently in VC:**\n"
                        group_summary = {}
                        for name, data in active_vc.items():
                            gname = data['group_name']
                            if gname not in group_summary:
                                group_summary[gname] = []
                            group_summary[gname].append(name)
                        for gname, accounts in group_summary.items():
                            status_text += f"   📍 `{gname}`: {len(accounts)} accounts\n"
                    
                    send_message(chat_id, status_text)
                
                # Done command
                elif text == "/done":
                    send_message(chat_id, f"✅ **Done!**\n\nTotal sessions saved: `{len(user_sessions)}`\n\nUse `/add` to add a group\nUse `/joinvc <count>` to join voice chat")
                    if user_id in user_states:
                        del user_states[user_id]
                
                # Handle session input
                elif user_id in user_states and user_states[user_id].get("step") == "awaiting_session":
                    if len(text) > 50:
                        send_message(chat_id, "⏳ **Testing session...**")
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
                            send_message(chat_id, f"✅ **Session Added!**\n👤 `{result['name']}`\n🆔 `{result['id']}`\n📊 Total: `{len(user_sessions)}`\n\nSend more or type `/done`")
                        else:
                            send_message(chat_id, f"❌ **Invalid Session!**\n`{result['error']}`")
                    else:
                        send_message(chat_id, "❌ Invalid session string!")
                
                # Handle public group username
                elif user_id in user_states and user_states[user_id].get("step") == "public_username":
                    username = text.replace("@", "")
                    send_message(chat_id, f"⏳ **Resolving @{username}...**")
                    
                    try:
                        resp = requests.get(f"{API_URL}/getChat", params={"chat_id": f"@{username}"}, timeout=10)
                        if resp.ok:
                            chat_info = resp.json()["result"]
                            group_title = chat_info.get("title", username)
                            group_chat_id = chat_info["id"]
                            
                            new_group = {"name": group_title, "chat_id": group_chat_id, "username": username}
                            groups_list.append(new_group)
                            current_group = new_group
                            
                            send_message(chat_id, f"✅ **Group Added!**\n📌 `{group_title}`\n🆔 `{group_chat_id}`\n\nUse `/joinvc <count>` to join voice chat\nUse `/groups` to see all groups")
                        else:
                            send_message(chat_id, f"❌ Could not resolve @{username}\nMake sure bot is in the group")
                    except Exception as e:
                        send_message(chat_id, f"❌ Error: `{e}`")
                    del user_states[user_id]
                
                # Handle private group link
                elif user_id in user_states and user_states[user_id].get("step") == "private_link":
                    user_states[user_id] = {"step": "private_chatid", "link": text}
                    send_message(chat_id, "📝 **Send Chat ID**\nExample: `-1001234567890`")
                
                # Handle private group chat_id
                elif user_id in user_states and user_states[user_id].get("step") == "private_chatid":
                    try:
                        chat_id_val = int(text)
                        invite_link = user_states[user_id]["link"]
                        
                        new_group = {"name": f"Private_{chat_id_val}", "chat_id": chat_id_val, "invite_link": invite_link}
                        groups_list.append(new_group)
                        current_group = new_group
                        
                        send_message(chat_id, f"✅ **Private Group Added!**\n🆔 `{chat_id_val}`\n\nUse `/joinvc <count>` to join voice chat")
                        del user_states[user_id]
                    except:
                        send_message(chat_id, "❌ **Invalid Chat ID!**")
        
        time.sleep(1)
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Bot stopped")
        break
    except Exception as e:
        print(f"❌ Error: {e}")
        time.sleep(5)

print("Bot stopped")
EOF

echo ""
echo "=========================================="
echo "✅ FINAL main.py created successfully!"
echo "=========================================="
