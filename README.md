# Agent Robert

A local-first, multi-agent desktop assistant for running AI workflows on your own machine with Ollama.

Agent Robert is a configurable personal assistant and orchestration system that uses local large language models, agent delegation, and desktop automation to help with reading, writing, planning, debugging, and file workflows without depending on a hosted LLM API for the core experience.

## Your personal assistant

Agent Robert is designed to be approachable and configurable: choose a local model, set up the communication integrations you want to use, and work with the assistant through a straightforward desktop interface.

### Agent in action

The snapshot shows the orchestrator delegating a writing request to a specialized document agent, which creates a Word document and returns the result to Agent Robert.

<img width="2126" height="2046" alt="Agent Robert orchestrating a document-writing task" src="https://github.com/user-attachments/assets/533275d8-e068-47d4-8869-925651fec01f" />

## Why this project matters

- Local-first AI: keep your data on-device and control model choice
- Multi-agent orchestration: a master orchestrator delegates tasks to specialized agents
- Desktop workflow: built for interactive work with files, documents, and code
- Flexible integrations: email, Telegram, and optional external tooling with approval checks
- Workspaces and guardrails: generated outputs and network-sensitive actions are isolated and reviewed

## Highlights

- Multi-agent orchestration and task delegation
- Local LLM inference through Ollama
- Desktop UI for chat, session work, and tool visibility
- File reading, writing, and document generation
- Code comprehension, verification, execution, and debugging
- Git and SSH workflows with approval checks for network-sensitive actions
- Optional communication integrations for email and Telegram

## Repository layout

```text
.
├── LICENSE
├── README.md
├── src/
│   ├── core/
│   │   └── document_engine.py
│   ├── tools/
│   │   ├── code_exec_tools.py
│   │   ├── code_map_tools.py
│   │   ├── communication_tools.py
│   │   ├── rag_manager.py
│   │   ├── skill_manager.py
│   │   ├── system_tools.py
│   │   └── vcs_network_tools.py
│   └── ui/
│       └── agent_ui.py
└── workspace/
```

## Technology stack

- Python 3.10+
- Tkinter desktop UI
- Ollama for local model serving
- LangChain and LangChain Ollama integration
- Libraries including `markdown`, `python-docx`, `pypdf`, `tkhtmlview`, `Pillow`, `pandas`, and `python-pptx`

## Getting started

### Prerequisites

- Python 3.10 or later
- Ollama installed and running locally
- A model available in Ollama that supports tool calling; the app defaults to `gemma4:31b`

### Install dependencies

Install the Python packages used by the application and optional document features:

```bash
pip install markdown tkhtmlview python-docx pypdf langchain langchain-ollama pillow pandas python-pptx
```

Install and start Ollama using the official instructions for your platform. Then pull the model if it is not already available:

```bash
ollama pull gemma4:31b
```

### Run the application

From the repository root:

```bash
python -m src.ui.agent_ui
```

## Typical usage

1. Start Ollama and confirm a compatible local model is available.
2. Launch Agent Robert and choose a model from the application model selector.
3. Use the chat interface to ask the assistant to perform tasks.
4. Let the master orchestrator delegate specialized work to sub-agents as needed.
5. Attach files or ask the assistant to work within the configured search space.
6. Review generated outputs and task artifacts in the session workspace shown in the app.

## Workspace and data

At startup, the app creates a session-specific directory beneath `workspace/` and configures it as `AGENT_WORKSPACE`. Relative file writes are directed there. Generated execution logs, outputs, and artifacts remain in the workspace so the working area stays isolated and organized.

The application may also create local configuration files for credentials under `config/`, and those values should remain private and not be committed to source control.

## Security and external services

This project is designed to run with local LLMs, but optional communication integrations and network tools may connect to external services. Review permissions carefully, keep secrets out of version control, and treat any network operation as an explicit trust boundary.

## License

This project is distributed under the Apache License 2.0. See [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome. If you have ideas, bug fixes, or feature improvements, please open an issue or submit a pull request with a clear description of the change.

## Suggested GitHub topics

Use these in the repository’s “About” section for better discoverability:

```text
local-ai ollama multi-agent python desktop-assistant ai-agent assistant automation llm
```

## Project overview

Agent Robert is intended as a personal AI workspace that helps with document work, coding, planning, debugging, and tool-backed task execution while staying local-first and user-controlled.

## Ollama, Gmail, and Telegram setup

This section adds setup details for the services the app uses. Gmail and Telegram are optional; the core assistant runs with Ollama alone.

### Ollama (required)

1. Install Ollama using the [official download page](https://ollama.com/download) and start the Ollama service.
2. Pull the default model, or another model that supports tool calling:

   ```bash
   ollama pull gemma4:31b
   ```

3. Launch Agent Robert from the repository root using the command above. The app connects to Ollama at `http://localhost:11434`, discovers installed models, and lists them in the **Model** selector. Select the model you want to use.

No Ollama API token is required for the default local setup. The selected model must be installed locally and available to the Ollama service.

### Configure credentials in the app

The **Config Comm Cred** button opens a sequence of configuration forms: Email, Telegram, and WhatsApp. Configure only the integrations you plan to use; choose **Skip** to leave an integration unset. Saved settings are stored in the plain-text file `config/credentials.md` in the directory from which the app is launched. The application creates the `config/` directory when saving settings.

Protect this file as you would a password file. Do not commit it, publish it, or include it in screenshots or logs. Revoke or rotate any password or token that is exposed.

### Gmail: app password and authorized addresses

The Gmail integration connects over IMAP and SMTP. For Gmail, use a Google **App Password**, not your regular Google account password.

1. Sign in to the Google Account you want Agent Robert to use and enable **2-Step Verification**.
2. Open [Google Account App Passwords](https://myaccount.google.com/apppasswords), create an app password, and copy it. App Passwords may not be available for some account types or security settings; follow Google's current account guidance rather than disabling security protections.
3. In **Config Comm Cred → Email**, enter:
   - **IMAP_SERVER**: `imap.gmail.com`
   - **SMTP_SERVER**: `smtp.gmail.com`
   - **EMAIL_ADDRESS**: the full Gmail address used by the app
   - **EMAIL_PASSWORD**: the Google App Password
   - **AUTHORIZED_OWNER**: the single email address to which the assistant may send directly (usually your own address)
   - **AUTHORIZED_SENDERS**: optional, comma-separated email addresses allowed to trigger the incoming-email listener
4. Save the settings. To listen for incoming messages, enable **Email Client** in the main window. The listener processes unread messages from addresses in `AUTHORIZED_SENDERS`; other senders are ignored. The assistant can also fetch unread messages when asked.

**What the authorized Gmail fields mean**

- `AUTHORIZED_OWNER` is the outbound recipient guard. If the assistant is asked to send to an address other than this value, the app switches the message to draft mode and appends it to Gmail's Drafts folder instead of sending it. This is not your Gmail login name; it is the permitted direct-send recipient.
- `AUTHORIZED_SENDERS` is an inbound sender allowlist used by the background email listener. Enter complete sender addresses separated by commas, for example `trusted@example.com,alerts@example.org`. It is independent of `AUTHORIZED_OWNER`.
- Keep the allowlist narrow. Incoming messages that pass this check are submitted to the assistant for processing.

### Telegram: bot token, API credentials, and authorized chat IDs

Telegram setup uses a Telegram bot token and Telegram API credentials for the Telethon client. The app requires all three values for the Telegram listener and actual bot messaging.

1. In Telegram, open the official **@BotFather** account and send `/newbot`. Follow the prompts and copy the bot token it returns. Keep this token secret; it controls your bot.
2. Sign in at [my.telegram.org](https://my.telegram.org), open **API development tools**, and create an application if prompted. Copy the numeric **api_id** and **api_hash**. These identify your Telegram application and are different from the bot token.
3. In **Config Comm Cred → Telegram**, enter:
   - **TELEGRAM_API_ID**: the numeric `api_id`
   - **TELEGRAM_API_HASH**: the `api_hash`
   - **TELEGRAM_BOT_TOKEN**: the token from BotFather
   - **AUTHORIZED_TELEGRAM_USERS**: optional comma-separated Telegram chat IDs allowed to send incoming messages to the assistant
4. Start a private chat with your bot and press **Start** or send `/start`; bots cannot initiate a private conversation before the user starts it.
5. Find the numeric chat ID for the conversation and add it to `AUTHORIZED_TELEGRAM_USERS`. To identify it using this app, you can temporarily leave the allowlist empty, enable **Telegram Client**, and send a test message in a private chat you control. The app logs the incoming chat ID. Add that exact value to the allowlist promptly. An empty allowlist does not restrict incoming chats, so do not leave it empty when enabling the listener in an environment where untrusted users can contact the bot. You can also use a trusted method to inspect the bot's updates and find the chat ID.
6. Enable **Telegram Client** in the main window. Messages from allowed chats are passed to Agent Robert, and the assistant can reply to the originating chat.

**What `AUTHORIZED_TELEGRAM_USERS` means in this code**

The setting name says “users,” but the current listener compares each entry with `event.chat_id`. It therefore authorizes **chat IDs**, not Telegram usernames, display names, or necessarily a person's user ID. In a private chat, the chat ID is typically the user's ID; use the exact ID observed for your conversation. Group chat IDs may be negative. Allowlisting a group authorizes that chat as a whole; it does not limit access to a particular group member. For personal access, use a private bot conversation. Separate multiple IDs with commas, for example `123456789,-1001234567890`.

### Credentials file (manual setup)

Instead of using the configuration dialogs, you may create `config/credentials.md` with one `KEY: value` entry per line. Replace placeholders with your own values; never commit real credentials:

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

Only include settings for services you intend to use. The values in this file are stored as plain text, not encrypted.

### Integration behavior and safety notes

- Gmail and Telegram connections are external services; Ollama inference is local by default.
- Email listener access is filtered by `AUTHORIZED_SENDERS`. Direct email transmission is restricted to `AUTHORIZED_OWNER`; messages to other recipients are saved as drafts.
- Telegram incoming access is filtered by chat ID only when `AUTHORIZED_TELEGRAM_USERS` is populated. A blank value means no chat-ID filtering in the current listener code.
- Review incoming messages before relying on them, keep credentials private, and disable the Email Client or Telegram Client toggles when you do not need their listeners.
- WhatsApp configuration is also present in the app's communication dialog but is not required for Ollama, Gmail, or Telegram use.
