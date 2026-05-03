# Configuration File for VC Manager Bot
# ======================================

# Get these from https://my.telegram.org
API_ID = 24168862
API_HASH = "916a9424dd1e58ab7955001ccc0172b3"

# Bot Token from @BotFather
BOT_TOKEN = "8751426759:AAEfSeFAAbM1tMZXWIoF8bRc56DRxBrry-4"

# Your Telegram user ID (owner) - Bot sirf aapke commands sunega
OWNER_ID = 8593970102

# Logger group ID (optional - for logging bot activities)
LOGGER_GROUP_ID = -1003957347260

# Sessions folder - Yahan saare .session files store hongi
SESSION_FOLDER = "sessions"

# Database file - Groups ki info store hogi
DATABASE_FILE = "groups_config.json"

# Voice Chat Settings
# ===================
# Auto join delay (seconds) - Har account ke beech mein delay (rate limit avoid karne ke liye)
AUTO_JOIN_DELAY = 2

# Max retries agar VC join fail ho
MAX_RETRIES = 3

# Audio settings (optional)
# Agar silent audio stream karna ho toh True rakho, False karo toh bot mic capture karega
USE_SILENT_STREAM = True

# Stream audio file path (optional - agar koi specific audio file play karni ho)
# Example: "audio.mp3" ya None for silent stream
AUDIO_FILE = None

# Logging
# ========
DEBUG_MODE = True  # True karne se console mein details dikhenge

# Pyrogram session string support (optional)
# Agar session string use karni ho toh True karo
ALLOW_SESSION_STRINGS = False

# Auto restart on disconnect
AUTO_RESTART = True

# Voice chat settings
VOICE_CHAT_SETTINGS = {
    "join_as_voice": True,  # Voice chat mein join karna hai ya video call mein
    "mute_self": False,      # Apne mic ko mute karna hai?
    "volume": 100,           # Volume percentage (0-200)
}

# Command prefixes (default: /)
COMMAND_PREFIXES = ["/", "!"]

# Rate limiting (commands per minute)
RATE_LIMIT = 30

# Health check interval (seconds)
HEALTH_CHECK_INTERVAL = 60

# Reconnect attempts on failure
RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY = 10

# Logging configuration
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR

# Allowed users (jab tak Owner ID set hai, sirf owner use kar sakta hai)
# Agar multiple users ko allow karna hai toh neeche list mein daalo
ALLOWED_USERS = [OWNER_ID]  # Sirf owner ko allow hai

# Welcome message when bot starts
WELCOME_MESSAGE = """
🎵 **VC Manager Bot Started!**

📊 **Status:**
• Bot is running
• Owner ID: `{owner_id}`
• Debug Mode: {debug_mode}

**Commands:**
/add_account - Add new Telegram account
/add_group - Add group for VC management
/start_vc - Start voice chat
/stop_vc - Stop voice chat
/status - Check bot status
"""

# Error messages
ERROR_MESSAGES = {
    "not_owner": "❌ You are not authorized to use this bot!",
    "no_accounts": "❌ No accounts loaded! Use /add_account first.",
    "no_groups": "❌ No groups configured! Use /add_group first.",
    "invalid_group": "❌ Invalid group ID!",
    "no_active_vc": "⚠️ No active voice chat found in the group!",
    "join_failed": "❌ Failed to join voice chat!",
    "leave_failed": "❌ Failed to leave voice chat!",
}
