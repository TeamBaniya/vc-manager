from pyrogram import Client
from pyrogram.errors import InviteHashExpired, UserNotParticipant, UsernameInvalid
from pytgcalls import PyTgCalls
from pytgcalls.exceptions import NoActiveGroupCall

class VCManager:
    def __init__(self, clients):
        self.clients = clients
        self.call_clients = {}  # {client_index: PyTgCalls instance}
        self.active_sessions = {}  # {group_id: {client: call_client}}
        
    async def ensure_user_in_private_group(self, client: Client, invite_link: str):
        """Join private group using invite link"""
        try:
            # Check if already member
            await client.get_chat(invite_link)
            return True
        except UserNotParticipant:
            print(f"Joining private group with invite link...")
            try:
                await client.join_chat(invite_link)
                print(f"Successfully joined private group")
                return True
            except Exception as e:
                print(f"Failed to join: {e}")
                return False
        except Exception as e:
            print(f"Error checking membership: {e}")
            return False
    
    async def get_chat_id(self, client: Client, identifier: str, group_type: str):
        """Get chat ID from username or invite link"""
        try:
            if group_type == "public":
                # Public group: username se direct chat object
                chat = await client.get_chat(identifier)
                return chat.id
            else:
                # Private group: invite link se join karke phir ID lo
                chat = await client.get_chat(identifier)
                return chat.id
        except UsernameInvalid:
            print(f"Invalid username: {identifier}")
            return None
        except Exception as e:
            print(f"Error getting chat: {e}")
            return None
    
    async def join_vc_for_group(self, client: Client, group_id: str, group_type: str, identifier: str):
        """Join voice chat for a specific group"""
        try:
            # For private groups, ensure user is member
            if group_type == "private":
                if not await self.ensure_user_in_private_group(client, identifier):
                    print(f"Failed to join private group: {identifier}")
                    return False
            
            # Get chat ID
            chat = await client.get_chat(identifier)
            chat_id = chat.id
            
            # Check if PyTgCalls already exists for this client
            call_client = self.call_clients.get(id(client))
            if not call_client:
                call_client = PyTgCalls(client)
                await call_client.start()
                self.call_clients[id(client)] = call_client
            
            # Join voice chat
            await call_client.join_group_call(chat_id)
            me = await client.get_me()
            print(f"🎙️ {me.first_name} joined VC in group: {identifier}")
            
            # Store active session
            if group_id not in self.active_sessions:
                self.active_sessions[group_id] = []
            self.active_sessions[group_id].append({
                "client": client,
                "call_client": call_client,
                "chat_id": chat_id
            })
            
            return True
            
        except NoActiveGroupCall:
            print(f"⚠️ No active voice chat in group: {identifier}")
            return False
        except Exception as e:
            print(f"❌ Error joining VC: {e}")
            return False
    
    async def leave_vc_for_group(self, group_id: str):
        """Leave voice chat for all clients in a specific group"""
        if group_id not in self.active_sessions:
            print(f"No active session for group: {group_id}")
            return False
        
        for session in self.active_sessions[group_id]:
            try:
                await session["call_client"].leave_group_call(session["chat_id"])
                me = await session["client"].get_me()
                print(f"👋 {me.first_name} left VC for group {group_id}")
            except Exception as e:
                print(f"Error leaving: {e}")
        
        self.active_sessions[group_id] = []
        return True
    
    async def start_all_for_group(self, group_configs, group_id):
        """Start all accounts for a specific group"""
        if group_id in self.active_sessions:
            await self.leave_vc_for_group(group_id)
        
        success_count = 0
        for client in self.clients:
            try:
                result = await self.join_vc_for_group(
                    client, 
                    group_id,
                    group_configs["type"],
                    group_configs["identifier"]
                )
                if result:
                    success_count += 1
                await asyncio.sleep(1)  # Rate limit avoid karne ke liye
            except Exception as e:
                print(f"Error with client: {e}")
        
        print(f"✅ {success_count}/{len(self.clients)} accounts joined VC for group {group_id}")
        return success_count
    
    async def stop_all_for_group(self, group_id):
        """Stop all VC connections for a specific group"""
        await self.leave_vc_for_group(group_id)
        print(f"✅ All accounts left VC for group {group_id}")
