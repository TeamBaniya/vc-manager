cat > main.py << 'EOF'
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
voice_calls = {}
current_group = None
last_update_id = 0
user_states = {}

print("="*60)
print("🤖 VC BOT - FULLY WORKING")
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
                voice_calls[acc_name] = vc
                results.append({"success": True, "name": acc_name, "id": acc_id})
                print(f"  ✅ {acc_name} joined")
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

async def leave_voice_chat():
    for name, vc in voice_calls.items():
        try:
            await vc.stop()
        except:
            pass
    voice_calls.clear()
    return True

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
                    send_message(chat_id, "📱 **Send Pyrogram String Session**\n\nGet from @StringSessionBot\nType `/done` when finished")
                
                elif data_cb == "status":
                    status_text = f"**📊 Bot Status**\n\n"
                    status_text += f"📱 Sessions: `{len(user_sessions)}`\n"
                    status_text += f"🎤 Active VCs: `{len(voice_calls)}`\n"
                    if current_group:
                        status_text += f"📍 Group: `{current_group[2]}`\n"
                        status_text += f"🆔 Chat ID: `{current_group[1]}`\n"
                    status_text += f"\n**Sessions List:**\n"
                    for i, s in enumerate(user_sessions, 1):
                        status_text += f"{i}. `{s['name']}` (ID: `{s['id']}`)\n"
                    send_message(chat_id, status_text)
                
                elif data_cb == "public_group":
                    user_states[user_id] = {"step": "public_username"}
                    send_message(chat_id, "📝 **Send group @username**\nExample: `@mygroup`\n\n⚠️ Voice chat must be active in group!")
                
                elif data_cb == "private_group":
                    user_states[user_id] = {"step": "private_link"}
                    send_message(chat_id, "🔗 **Send group invite link**")
                
                requests.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": callback["id"]})
            
            elif "message" in update:
                msg = update["message"]
                user_id = msg["from"]["id"]
                chat_id = msg["chat"]["id"]
                text = msg.get("text", "")
                
                print(f"\n📨 Message: {text}")
                
                if user_id != OWNER_ID:
                    continue
                
                if text == "/start":
                    keyboard = {
                        "inline_keyboard": [
                            [{"text": "🔌 Connect Session", "callback_data": "connect"}],
                            [{"text": "📊 Status", "callback_data": "status"}],
                            [{"text": "➕ Add Group", "callback_data": "public_group"}]
                        ]
                    }
                    send_message(chat_id, "**🎵 VC Manager Bot**\n\nManage multiple accounts in voice chats!\n\n⚠️ Voice chat must be started by someone in the group first!", keyboard)
                
                elif text == "/add":
                    keyboard = {
                        "inline_keyboard": [
                            [{"text": "🌐 Public Group", "callback_data": "public_group"}],
                            [{"text": "🔒 Private Group", "callback_data": "private_group"}]
                        ]
                    }
                    send_message(chat_id, "**Select group type:**", keyboard)
                
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
                        send_message(chat_id, "❌ **No group added!** Use `/add` first")
                        continue
                    
                    if len(user_sessions) == 0:
                        send_message(chat_id, "❌ **No sessions added!**")
                        continue
                    
                    if count > len(user_sessions):
                        send_message(chat_id, f"❌ Only `{len(user_sessions)}` sessions available")
                        continue
                    
                    group_name = current_group[2]
                    group_chat_id = current_group[1]
                    
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
                        result_text += f"\n⚠️ **Troubleshooting:**\n"
                        result_text += f"1. Someone must start voice chat in {group_name} first\n"
                        result_text += f"2. Click the 📞 phone icon in the group\n"
                        result_text += f"3. Then try `/joinvc {count}` again"
                    
                    send_message(chat_id, result_text)
                    print(f"  ✅ Join completed: {success_count} joined")
                
                elif text == "/leavevc":
                    if len(voice_calls) == 0:
                        send_message(chat_id, "❌ **No active voice chats!**")
                        continue
                    
                    send_message(chat_id, "🚪 **Leaving voice chats...**")
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(leave_voice_chat())
                    loop.close()
                    send_message(chat_id, f"✅ **Left voice chat**")
                
                elif text == "/status":
                    status_text = f"**📊 Bot Status**\n\n"
                    status_text += f"📱 **Sessions:** `{len(user_sessions)}`\n"
                    status_text += f"🎤 **Active VCs:** `{len(voice_calls)}`\n"
                    if current_group:
                        status_text += f"📍 **Group:** `{current_group[2]}`\n"
                        status_text += f"🆔 **Chat ID:** `{current_group[1]}`\n"
                    status_text += f"\n**📋 Sessions:**\n"
                    for i, s in enumerate(user_sessions, 1):
                        status_text += f"{i}. `{s['name']}` (ID: `{s['id']}`)\n"
                    send_message(chat_id, status_text)
                
                elif text == "/done":
                    send_message(chat_id, f"✅ **Done!**\n\nTotal sessions saved: `{len(user_sessions)}`")
                    if user_id in user_states:
                        del user_states[user_id]
                
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
                            send_message(chat_id, f"✅ **Session Added!**\n👤 `{result['name']}`\n🆔 `{result['id']}`\n📊 Total: `{len(user_sessions)}`")
                        else:
                            send_message(chat_id, f"❌ **Invalid Session!**\n`{result['error']}`")
                
                elif user_id in user_states and user_states[user_id].get("step") == "public_username":
                    username = text.replace("@", "")
                    send_message(chat_id, f"⏳ **Resolving @{username}...**")
                    
                    try:
                        resp = requests.get(f"{API_URL}/getChat", params={"chat_id": f"@{username}"}, timeout=10)
                        if resp.ok:
                            chat_info = resp.json()["result"]
                            group_title = chat_info.get("title", username)
                            group_chat_id = chat_info["id"]
                            current_group = (f"@{username}", group_chat_id, group_title)
                            send_message(chat_id, f"✅ **Group Added!**\n📌 `{group_title}`\n🆔 `{group_chat_id}`\n\n⚠️ Start voice chat in group first, then use `/joinvc`")
                        else:
                            send_message(chat_id, f"❌ Could not resolve @{username}\nMake sure bot is in the group")
                    except Exception as e:
                        send_message(chat_id, f"❌ Error: `{e}`")
                    del user_states[user_id]
                
                elif user_id in user_states and user_states[user_id].get("step") == "private_link":
                    user_states[user_id] = {"step": "private_chatid", "link": text}
                    send_message(chat_id, "📝 **Send Chat ID**\nExample: `-1001234567890`")
                
                elif user_id in user_states and user_states[user_id].get("step") == "private_chatid":
                    try:
                        chat_id_val = int(text)
                        current_group = (user_states[user_id]["link"], chat_id_val, f"Private_{chat_id_val}")
                        send_message(chat_id, f"✅ **Private Group Added!**\n🆔 `{chat_id_val}`")
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
echo ""
echo "Run the bot with:"
echo "python3 main.py"
echo ""
