# Integration setup

This guide covers installing and choosing an Ollama model, then configuring optional Gmail and Telegram integrations. Gmail and Telegram are not required to use the core assistant.

## Ollama and local models

1. Install [Ollama](https://ollama.com/download) and start the Ollama service.
2. Pull a smaller model first for a faster, lower-resource trial. These examples are tool-capable model families; compatibility can vary by specific model/version.

   ```bash
   ollama pull qwen2.5:7b
   # Or: ollama pull llama3.1:8b
   ```

   `gemma4:31b` is also available for systems with substantially more memory, but it is not the recommended starting point.
3. Install the Python packages from the repository root with `python -m pip install -r requirements.txt`, then launch with `python -m src.ui.agent_ui`.
4. The app connects to Ollama at `http://localhost:11434`, discovers installed models, and lists them in the **Model** selector. Select the model you want to use. No Ollama API token is required for the local setup.

## Configure credentials in the app

The **Config Comm Cred** button opens configuration forms for Email, Telegram, and WhatsApp. Configure only integrations you intend to use; choose **Skip** for anything you do not need. Settings are saved in plain text at `config/credentials.md` in the directory from which the app is launched. Protect this file like a password file: do not commit it, publish it, or include it in screenshots or logs. Revoke or rotate any exposed password or token.

## Gmail

The Gmail integration connects over IMAP and SMTP. Use a Google **App Password**, not your regular Google account password.

1. Sign in to the Google Account you want Agent Robert to use and enable **2-Step Verification**.
2. Create and copy an [App Password](https://myaccount.google.com/apppasswords). App Passwords may not be available for some account types or security settings; follow Google's current account guidance.
3. In **Config Comm Cred → Email**, enter:
   - **IMAP_SERVER**: `imap.gmail.com`
   - **SMTP_SERVER**: `smtp.gmail.com`
   - **EMAIL_ADDRESS**: the full Gmail address used by the app
   - **EMAIL_PASSWORD**: the Google App Password
   - **AUTHORIZED_OWNER**: the single email address to which the assistant may send directly (usually your own address)
   - **AUTHORIZED_SENDERS**: optional, comma-separated email addresses allowed to trigger the incoming-email listener
4. Save the settings. To listen for incoming messages, enable **Email Client** in the main window. The listener processes unread messages only from addresses in `AUTHORIZED_SENDERS`; other senders are ignored. The assistant can also fetch unread messages when asked.

`AUTHORIZED_OWNER` is the outbound recipient guard. If the assistant is asked to send to another address, the app switches to draft mode and appends the message to Gmail's Drafts folder rather than sending it. `AUTHORIZED_SENDERS` is a separate inbound sender allowlist. Keep it narrow; messages that pass this check are submitted to the assistant for processing.

## Telegram

Telegram setup uses a bot token plus API credentials for the Telethon client.

1. In Telegram, open the official **@BotFather** account and send `/newbot`. Follow the prompts and keep the returned bot token secret.
2. Sign in at [my.telegram.org](https://my.telegram.org), open **API development tools**, and create an application if prompted. Copy the numeric **api_id** and **api_hash**. These are separate from the bot token.
3. In **Config Comm Cred → Telegram**, enter:
   - **TELEGRAM_API_ID**: the numeric `api_id`
   - **TELEGRAM_API_HASH**: the `api_hash`
   - **TELEGRAM_BOT_TOKEN**: the token from BotFather
   - **AUTHORIZED_TELEGRAM_USERS**: comma-separated numeric Telegram chat IDs allowed to send incoming messages to the assistant
4. Start a private chat with your bot and press **Start** or send `/start`; bots cannot initiate a private conversation before the user starts it.
5. Find the numeric chat ID and add it to `AUTHORIZED_TELEGRAM_USERS`. To identify it using this app, you can temporarily leave the allowlist empty, enable **Telegram Client**, and send a test message in a private chat you control; the app logs the incoming chat ID. Add that exact ID to the allowlist promptly, then restart/reenable the listener. An empty allowlist does not restrict incoming chats in the current listener, so do not leave it empty where untrusted users can contact the bot.
6. Enable **Telegram Client**. Messages from allowed chats are passed to Agent Robert, and the assistant can reply to the originating chat.

Despite the setting name, `AUTHORIZED_TELEGRAM_USERS` is checked against `event.chat_id`; it authorizes **chat IDs**, not usernames or display names. In a private chat, the chat ID is typically the user's ID. Group chat IDs may be negative; authorizing a group allows the group chat as a whole, not only a particular member. Use a private bot conversation for personal access and separate multiple IDs with commas.

## Manual credentials file (optional)

Instead of using the configuration dialogs, create `config/credentials.md` with one `KEY: value` entry per line. Include only services you intend to use and replace all placeholders with your own values. The file is stored as plain text, not encrypted.

```text
# Communication Credentials

IMAP_SERVER: imap.gmail.com
SMTP_SERVER: smtp.gmail.com
EMAIL_ADDRESS: you@gmail.com
EMAIL_PASSWORD: replace-with-google-app-password
AUTHORIZED_OWNER: you@gmail.com
AUTHORIZED_SENDERS: trusted-sender@example.com
TELEGRAM_API_ID: replace-with-numeric-api-id
TELEGRAM_API_HASH: replace-with-api-hash
TELEGRAM_BOT_TOKEN: replace-with-botfather-token
AUTHORIZED_TELEGRAM_USERS: replace-with-chat-id
```

## Integration behavior and safety notes

- Ollama inference is local by default; Gmail and Telegram connect to external services.
- Email listener access is filtered by `AUTHORIZED_SENDERS`. Direct email transmission is restricted to `AUTHORIZED_OWNER`; messages to other recipients are saved as drafts.
- Telegram incoming access is filtered by chat ID only when `AUTHORIZED_TELEGRAM_USERS` is populated. A blank value means no chat-ID filtering in the current listener code.
- Review incoming messages, keep credentials private, and disable the Email Client or Telegram Client toggles when you do not need their listeners.
- WhatsApp configuration is also present in the communication dialog but is not required for Ollama, Gmail, or Telegram use.
