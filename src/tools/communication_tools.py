import os
import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from langchain_core.tools import tool
import asyncio
import socket
import time
from telethon import TelegramClient, events

def get_credential(key: str) -> str:
    """Safely retrieves a named configuration key from the global session credentials storage mapping."""
    cred_path = os.path.abspath("config/credentials.md")
    if os.path.exists(cred_path):
        with open(cred_path, "r") as f:
            for line in f:
                if ":" in line and not line.startswith("#"):
                    k, v = line.split(":", 1)
                    if k.strip().replace("**", "") == key:
                        return v.strip()
    return ""

# =============================================================================
# CORE LOGIC FUNCTIONS (Plain Python functions, callable by UI)
# =============================================================================

def run_push_email_client(callback_fn, is_enabled_func):
    """Push-based background daemon utilizing the IMAP IDLE protocol for real-time notifications."""
    while True:
        try:
            if not is_enabled_func():
                time.sleep(5)
                continue

            imap_server = get_credential("IMAP_SERVER")
            email_address = get_credential("EMAIL_ADDRESS")
            password = get_credential("EMAIL_PASSWORD")
            auth_senders_str = get_credential("AUTHORIZED_SENDERS")

            if not (imap_server and email_address and password and auth_senders_str):
                time.sleep(30)
                continue

            authorized_senders = [s.strip().lower() for s in auth_senders_str.split(",") if s.strip()]

            mail = imaplib.IMAP4_SSL(imap_server)
            mail.login(email_address, password)
            mail.select("INBOX")

            def fetch_and_trigger():
                status, response = mail.search(None, 'UNSEEN')
                if status != 'OK' or not response[0]: return
                for mail_id in response[0].split():
                    status, data = mail.fetch(mail_id, '(RFC822)')
                    if status != 'OK': continue
                    msg = email.message_from_bytes(data[0][1])
                    subject = msg.get("Subject", "[No Subject]")
                    sender = msg.get("From", "")
                    
                    if "<" in sender: sender = sender[sender.find("<")+1:sender.find(">")]
                    sender = sender.strip().lower()
                    
                    if sender in authorized_senders:
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                    break
                        else:
                            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                        
                        callback_fn(body, sender, subject)

            # Fetch any pending unread emails initially before idling
            fetch_and_trigger()

            # Maintain active Push/IDLE connection
            while is_enabled_func():
                tag = mail._new_tag().decode()
                mail.send(f"{tag} IDLE\r\n".encode())
                mail.readline() # Consume '+ idling' confirmation
                
                mail.sock.settimeout(5.0) # Allows periodically breaking to check if user unchecked the setting
                idle_active = True
                
                while idle_active and is_enabled_func():
                    try:
                        line = mail.readline()
                        if not line:
                            idle_active = False # Connection dropped
                            break
                        if b"EXISTS" in line or b"RECENT" in line:
                            mail.sock.settimeout(None)
                            mail.send(b"DONE\r\n")
                            mail.readline() # Consume OK
                            fetch_and_trigger()
                            idle_active = False # Breaks inner loop to safely re-establish IDLE tag
                    except (socket.timeout, TimeoutError):
                        pass # Timeout allows the thread to evaluate `is_enabled_func()`

                if idle_active:
                    # Loop broke because user disabled the UI toggle. Gracefully close IDLE mode.
                    mail.sock.settimeout(None)
                    mail.send(b"DONE\r\n")
                    mail.readline()

            mail.sock.settimeout(None)
            try: mail.close()
            except: pass
            try: mail.logout()
            except: pass

        except Exception as e:
            print(f"Push Email Listener Error: {str(e)}")
            time.sleep(30) # Cool-off before reconnect attempting

def register_email_credentials(imap_server: str, smtp_server: str, email_address: str, password: str, authorized_owner: str = "") -> str:
    """Registers SMTP and IMAP mailbox credential profiles securely in application memory."""
    try:
        cred_path = os.path.abspath("config/credentials.md")
        os.makedirs(os.path.dirname(cred_path), exist_ok=True)
        
        creds = {}
        if os.path.exists(cred_path):
            with open(cred_path, "r") as f:
                for line in f:
                    if ":" in line and not line.startswith("#"):
                        k, v = line.split(":", 1)
                        creds[k.strip().replace("**", "")] = v.strip()
                        
        creds["IMAP_SERVER"] = imap_server.strip()
        creds["SMTP_SERVER"] = smtp_server.strip()
        creds["EMAIL_ADDRESS"] = email_address.strip()
        creds["EMAIL_PASSWORD"] = password.strip()
        if authorized_owner.strip():
            creds["AUTHORIZED_OWNER"] = authorized_owner.strip()
            
        with open(cred_path, "w") as f:
            f.write("# Communication Credentials\n\n")
            for k, v in creds.items():
                if v: f.write(f"**{k}**: {v}\n")
        return "SUCCESS: Email credentials and recipient guard boundaries registered successfully."
    except Exception as e:
        return f"ERROR: Failed to save email credential context: {str(e)}"

def fetch_unopened_emails(folder: str = "INBOX", limit: int = 5) -> list:
    """Retrieves unseen email headers and messages securely from the configured IMAP environment."""
    imap_server = get_credential("IMAP_SERVER")
    email_address = get_credential("EMAIL_ADDRESS")
    password = get_credential("EMAIL_PASSWORD")
    
    if not email_address or not password or not imap_server:
        return [{"error": "Missing IMAP credentials configurations."}]
    try:
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_address, password)
        mail.select(folder)
        
        status, response = mail.search(None, 'UNSEEN')
        if status != 'OK':
            return [{"error": "Failed to search unread messages."}]
        mail_ids = response[0].split()
        if not mail_ids:
            return []
        results = []
        for index in reversed(mail_ids[-limit:]):
            status, data = mail.fetch(index, '(RFC822)')
            if status != 'OK':
                continue
                
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            subject = msg["Subject"] or "[No Subject]"
            sender = msg["From"] or "[Unknown Sender]"
            date = msg["Date"] or ""
            
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        break
            else:
                body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
            results.append({"id": index.decode(), "from": sender, "date": date, "subject": subject, "body": body})
        mail.close()
        mail.logout()
        return results
    except Exception as e:
        return [{"error": f"Connection transaction to {imap_server} failed: {str(e)}"}]

def draft_or_send_email(to_address: str, subject: str, body: str, draft_only: bool = False, attachments: list = None) -> str:
    """Sends an email to the user, OR constructs a draft based on permissions."""
    imap_server = get_credential("IMAP_SERVER")
    smtp_server = get_credential("SMTP_SERVER")
    email_address = get_credential("EMAIL_ADDRESS")
    password = get_credential("EMAIL_PASSWORD")
    owner_mail = get_credential("AUTHORIZED_OWNER")
    
    target_clean = to_address.strip().lower()
    sec_warning = ""
    
    if owner_mail and target_clean != owner_mail.strip().lower():
        draft_only = True
        sec_warning = f"⚠️ SECURITY POLICY ACTION: Recipient '{to_address}' is NOT the authorized user email. Direct outbound transmission has been safely blocked."
    if not email_address or not password:
        return f"ERROR: Insufficient credentials loaded. {sec_warning}"

    try:
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = email_address
        msg['To'] = to_address
        msg.attach(MIMEText(body, 'plain'))
        if attachments:
            for file_path in attachments:
                if os.path.exists(file_path):
                    with open(file_path, "rb") as attachment_file:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(attachment_file.read())
                        encoders.encode_base64(part)
                        part.add_header("Content-Disposition", f"attachment; filename=\"{os.path.basename(file_path)}\"")
                        msg.attach(part)
        if draft_only:
            mail = imaplib.IMAP4_SSL(imap_server)
            mail.login(email_address, password)
            
            draft_folder = "Drafts"
            status, folders = mail.list()
            for f in folders:
                f_name = f.decode()
                if "Drafts" in f_name or "Draft" in f_name:
                    draft_folder = f_name.split(' "/" ')[-1].replace('"', '')
                    break
                    
            mail.append(draft_folder, '', None, msg.as_bytes())
            mail.logout()
            return f"SUCCESS (DRAFT MODE): {sec_warning}\nDraft successfully appended."
        else:
            server = smtplib.SMTP(smtp_server, 587)
            server.starttls()
            server.login(email_address, password)
            server.send_message(msg)
            server.quit()
            return f"SUCCESS: Outbound email successfully sent."
    except Exception as e:
        return f"ERROR: Failed to interact with mail services: {str(e)}"

def whatsapp_send_or_draft(phone_number: str, message: str, draft_only: bool = False) -> str:
    """Saves a WhatsApp draft or executes Cloud API message transmission."""
    try:
        wa_token = get_credential("WHATSAPP_API_TOKEN")
        wa_phone_id = get_credential("WHATSAPP_PHONE_ID")
        
        if draft_only or not (wa_token and wa_phone_id):
            workspace_dir = os.environ.get("AGENT_WORKSPACE", "workspace")
            draft_name = f"whatsapp_draft_{str(phone_number).strip().replace('+', '')}_{int(time.time())}.txt"
            draft_path = os.path.join(workspace_dir, draft_name)
            os.makedirs(workspace_dir, exist_ok=True)
            with open(draft_path, "w", encoding="utf-8") as f:
                f.write(f"Recipient: {phone_number}\nChannel: WhatsApp\nMessage:\n{message}")
            return f"SUCCESS: WhatsApp message draft saved at '{draft_path}'."
        import urllib.request
        import json
        url = f"https://graph.facebook.com/v17.0/{wa_phone_id.strip()}/messages"
        headers = {"Authorization": f"Bearer {wa_token.strip()}", "Content-Type": "application/json"}
        payload = {"messaging_product": "whatsapp", "to": str(phone_number).strip().replace("+", ""), "type": "text", "text": {"body": str(message)}}
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=10) as response:
            res = response.read()
        return f"SUCCESS: WhatsApp message triggered via Cloud API."
    except Exception as e:
        return f"ERROR: WhatsApp process failed: {str(e)}"

def telegram_send_or_draft(chat_id: str, message: str, draft_only: bool = False) -> str:
    """Queues a Telegram message using Telethon (MTProto) or generates offline draft."""
    api_id = get_credential("TELEGRAM_API_ID")
    api_hash = get_credential("TELEGRAM_API_HASH")
    bot_token = get_credential("TELEGRAM_BOT_TOKEN")
    
    try:
        if draft_only or not (api_id and api_hash and bot_token):
            workspace_dir = os.environ.get("AGENT_WORKSPACE", "workspace")
            draft_name = f"telegram_draft_{str(chat_id).strip()}_{int(time.time())}.txt"
            draft_path = os.path.join(workspace_dir, draft_name)
            os.makedirs(workspace_dir, exist_ok=True)
            with open(draft_path, "w", encoding="utf-8") as f:
                f.write(f"Chat ID: {chat_id}\nChannel: Telegram\nMessage:\n{message}")
            return f"SUCCESS: Telegram message draft created at '{draft_path}'."
        
        async def send_tg_msg():
            # Use a separate session file for outbound messages to avoid lock conflicts with the listener
            session_path = os.path.join(os.environ.get("AGENT_WORKSPACE", "workspace"), "tg_outbound_session")
            client = TelegramClient(session_path, int(api_id), api_hash)
            await client.start(bot_token=bot_token)
            try:
                target = int(chat_id)
            except (ValueError, TypeError):
                target = str(chat_id).strip()
            await client.send_message(target, str(message))
            await client.disconnect()

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(send_tg_msg())
            return f"SUCCESS: Telegram transmission queued."
        except RuntimeError:
            asyncio.run(send_tg_msg())
            return f"SUCCESS: Telegram transmission triggered."
    except Exception as e:
        return f"ERROR: Telegram transmission failed: {str(e)}"

async def _telegram_message_handler(event, callback_fn=None, log_callback=None):
    """
    Handles incoming messages via Telethon events.
    """
    if event.message and event.message.text:
        chat_id = event.chat_id
        
        # --- SECURITY FILTERING START ---
        auth_users_str = get_credential("AUTHORIZED_TELEGRAM_USERS")
        if auth_users_str:
            authorized_users = [u.strip() for u in auth_users_str.split(",") if u.strip()]
            if str(chat_id) not in authorized_users:
                sec_msg = f"[SECURITY BLOCK] Telegram message from unauthorized Chat ID {chat_id} blocked."
                if log_callback:
                    log_callback(sec_msg)
                else:
                    print(sec_msg)
                return
        # --- SECURITY FILTERING END ---

        message_text = event.message.text
        sender = event.sender.first_name if event.sender else "Unknown"
        
        log_msg = f"[Telegram Push Received] Chat {chat_id} from {sender}: {message_text}"
        if log_callback:
            log_callback(log_msg)
        else:
            print(log_msg)
        
        if callback_fn:
            # Inject into UI via callback
            callback_fn(message_text, sender, chat_id)
        
        # Real response is handled by the agent via telegram_send_or_draft_tool

def run_push_telegram_client(callback_fn, log_callback=None):
    """
    Runs a bidirectional Telegram client using Telethon (MTProto).
    """
    api_id = get_credential("TELEGRAM_API_ID")
    api_hash = get_credential("TELEGRAM_API_HASH")
    bot_token = get_credential("TELEGRAM_BOT_TOKEN")
    
    if not (api_id and api_hash and bot_token):
        err_msg = "Telegram Client Error: Missing API_ID, API_HASH, or BOT_TOKEN."
        if log_callback: log_callback(err_msg)
        else: print(err_msg)
        return

    async def main():
        session_path = os.path.join(os.environ.get("AGENT_WORKSPACE", "workspace"), "tg_bot_session")
        client = TelegramClient(session_path, int(api_id), api_hash)
        
        @client.on(events.NewMessage(incoming=True))
        async def handler(event):
            await _telegram_message_handler(event, callback_fn, log_callback)
            
        await client.start(bot_token=bot_token)
        start_msg = "Starting Telegram MTProto Listener..."
        if log_callback: log_callback(start_msg)
        else: print(start_msg)
        await client.run_until_disconnected()

    try:
        asyncio.run(main())
    except Exception as e:
        err_msg = f"Telegram Client Error: {str(e)}"
        if log_callback: log_callback(err_msg)
        else: print(err_msg)

# =============================================================================
# LANGCHAIN TOOL WRAPPERS
# =============================================================================

@tool
def register_email_credentials_tool(imap_server: str, smtp_server: str, email_address: str, password: str, authorized_owner: str = "") -> str:
    """Registers SMTP and IMAP mailbox credential profiles securely in application memory."""
    return register_email_credentials(imap_server, smtp_server, email_address, password, authorized_owner)

@tool
def fetch_unopened_emails_tool(folder: str = "INBOX", limit: int = 5) -> list:
    """Retrieves unseen email headers and messages securely from the configured IMAP environment."""
    return fetch_unopened_emails(folder, limit)

@tool
def draft_or_send_email_tool(to_address: str, subject: str, body: str, draft_only: bool = False, attachments: list = None) -> str:
    """Sends an email to the user, OR constructs a draft based on permissions."""
    return draft_or_send_email(to_address, subject, body, draft_only, attachments)

@tool
def whatsapp_send_or_draft_tool(phone_number: str, message: str, draft_only: bool = False) -> str:
    """Saves a WhatsApp draft or executes Cloud API message transmission dynamically."""
    return whatsapp_send_or_draft(phone_number, message, draft_only)

@tool
def telegram_send_or_draft_tool(chat_id: str, message: str, draft_only: bool = False) -> str:
    """Queues a Telegram message using Telethon (MTProto) or generates offline draft securely."""
    return telegram_send_or_draft(chat_id, message, draft_only)

COMMUNICATION_TOOLS = [
    register_email_credentials_tool,
    fetch_unopened_emails_tool,
    draft_or_send_email_tool,
    whatsapp_send_or_draft_tool,
    telegram_send_or_draft_tool
]
