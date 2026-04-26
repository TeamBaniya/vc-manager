# test.py
from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN

print("API_ID:", API_ID)
print("BOT_TOKEN:", BOT_TOKEN[:10] + "...")

bot = Client("test_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def main():
    print("Connecting to Telegram...")
    await bot.start()
    me = await bot.get_me()
    print(f"✅ Bot connected! Username: @{me.username}")
    print(f"Bot ID: {me.id}")
    await bot.stop()
    print("Done!")

import asyncio
asyncio.run(main())
