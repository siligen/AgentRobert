# Agent Robert

**Agent Robert is your configurable, user-friendly AI personal assistant and multi-agent orchestration system, powered by local large language models (LLMs).** It uses Ollama to run models on your computer and coordinates specialized AI sub-agents to help with coding, documents, research, and everyday digital tasks. You can interact with it through its desktop chat interface, and—with email or Telegram configured—you can also contact your assistant through those channels.

## Your personal assistant

Agent Robert is designed to be approachable and configurable: choose a local model, set up the communication integrations you want to use, and work with the assistant through a straightforward desktop interface. When enabled and configured, it can receive email and Telegram messages and return responses through those channels. WhatsApp integration is also available as an optional capability.

## Overview

Agent Robert combines:

- A master AI orchestrator that plans work and delegates tasks to specialized sub-agents
- Local LLM inference through Ollama, with model selection in the desktop app
- A user-friendly chat-style desktop interface and live visualization of agents and tools
- Configurable email and Telegram access, plus optional WhatsApp integration
- An isolated workspace for generated files and task outputs
- Document reading, creation, and analysis tools
- Code mapping, verification, execution, and debugging tools
- Git, SSH, and filesystem tools, with approval checks for network-sensitive operations

The project is primarily implemented in Python. Its orchestration engine uses LangChain's Ollama integration; it does not require a hosted LLM API for its core model inference.

## Main capabilities

- Multi-agent orchestration and task delegation
- Local workspace/session isolation with `AGENT_WORKSPACE` and `APP_START_DIR`
- Reading PDFs, Word documents, CSV, markdown, code files, presentations, spreadsheets, and image metadata
- Writing documents and other generated files into the workspace
- Code mapping and Python AST/compile verification
- Python and other supported script execution and debugging tools
- Git workflows and SSH commands subject to network approval
- Skill discovery from `skills/` directories and retrieval-augmented generation (RAG) indexing
- Communication credential configuration and email/Telegram message handling

## Repository layout

```text
.
├── LICENSE
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
└── README.md
```

## Technology stack

- Python 3
- Tkinter desktop UI
- Ollama for local model serving
- LangChain and LangChain Ollama integration
- Supporting libraries including `markdown`, `python-docx`, `pypdf`, `tkhtmlview`, `Pillow`, `pandas`, and `python-pptx`

## Getting started

### Prerequisites

- Python 3.10 or later
- Ollama installed and running locally
- A model available in Ollama that supports tool calling; the application defaults to `gemma4:31b`

### Install dependencies

Install the Python packages used by the application and its optional document features:

```bash
pip install markdown tkhtmlview python-docx pypdf langchain langchain-ollama pillow pandas python-pptx
```

Install and start Ollama using its platform-specific instructions. Then pull a model if it is not already available:

```bash
ollama pull gemma4:31b
```

### Run the application

From the repository root, launch the desktop app with:

```bash
python -m src.ui.agent_ui
```

## Typical usage

1. Start Ollama and make sure a compatible local model is available.
2. Launch Agent Robert and choose a model from the model selector.
3. Use the chat interface to ask the assistant for help. The master orchestrator delegates specialized work to sub-agents as needed.
4. Optionally configure email or Telegram credentials in the app to contact the assistant through those channels. Enable the corresponding client when you want to use it.
5. Attach reference files with **Read File**, or ask the agents to work with files in the configured search space.
6. Find generated outputs and task artifacts in the session workspace shown in the application.

## Workspace and data

At startup, the app creates a session-specific directory beneath `workspace/` and sets it as `AGENT_WORKSPACE`. Relative file writes are directed to this workspace. The application startup directory is also available for supported read and search operations through `APP_START_DIR`.

Sub-agents can create execution logs in the workspace. Communication credentials are stored locally under `config/credentials.md` when configured. Keep credentials private and do not commit them to version control.

## Security and external services

Agent Robert is intended to run with local LLMs, but optional communication integrations and network tools can access external services. Email and Telegram require appropriate configuration and credentials; the application includes credential checks and authorization controls. Selected network-sensitive operations, such as Git pull/push/clone and SSH, require approval. Review tool actions and credentials carefully before enabling integrations. Local execution and workspace isolation do not make arbitrary generated code risk-free; only run tasks and scripts you trust.

## License

This project is distributed under the MIT License. See [`LICENSE`](LICENSE) for details.
