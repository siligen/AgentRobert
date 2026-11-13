# Agent Robert

Agent Robert is a local, multi-agent AI workspace built around a Python/Tkinter frontend and an Ollama-backed orchestration engine. It is designed to act as a cognitive operating environment for reading, annotating, searching, generating, and executing code and documents inside an isolated workspace while coordinating specialized sub-agents for different tasks.

## Overview

The project combines:

- a desktop chat-style interface for interacting with local LLM models
- a master orchestrator that delegates work to specialized sub-agents
- a sandboxed workspace for file generation and task isolation
- local document ingestion for common formats
- code analysis and execution tools for Python and related tasks
- optional communication integrations for email, Telegram, and WhatsApp
- Git, SSH, and filesystem operations behind approval gates

This repo is primarily implemented in Python and uses local model inference via Ollama rather than a hosted cloud API.

## Main capabilities

- Multi-agent orchestration and task delegation
- Local workspace/session isolation with `AGENT_WORKSPACE` and `APP_START_DIR`
- Reading PDFs, Word documents, CSV, markdown, code files, and image metadata
- Writing generated documents and other files into the sandboxed workspace
- Code search, mapping, AST verification, and Python execution tools
- Git status/repository workflows and SSH command execution
- Skill discovery via `skills/` directories and RAG indexing support
- Communication credential management and message drafting helpers

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
- Tkinter for the desktop UI
- LangChain + LangChain Ollama integration
- Ollama local model serving
- Python libraries such as:
  - `markdown`
  - `python-docx`
  - `pypdf`
  - `tkhtmlview`
  - `Pillow`
  - `pandas`
  - `python-pptx`

## Getting started

### Prerequisites

- Python 3.10+
- Ollama installed and running locally
- An available local model such as `gemma4:31b` or another compatible model

### Install dependencies

```bash
pip install markdown tkhtmlview python-docx pypdf langchain langchain-ollama pillow pandas python-pptx
```

If needed, pull a model into Ollama:

```bash
ollama pull gemma4:31b
```

### Run the application

From the repository root:

```bash
python src/ui/agent_ui.py
```

or:

```bash
python -m src.ui.agent_ui
```

## Typical usage

1. Launch the app.
2. Select or let the app detect a compatible Ollama model.
3. Use the chat interface to ask the orchestrator to read, write, analyze, or create files.
4. The master orchestrator delegates specialized work to sub-agents.
5. Generated outputs and logs are kept in the session workspace for safe isolation.

## Security and sandboxing

The application enforces a local workspace sandbox and includes approval checks for network-sensitive operations such as:

- `git clone`
- `git pull`
- `git push`
- SSH commands
- communication actions that require external credentials

This protects the system from unintended network access and ensures local work remains contained to the project workspace unless explicitly approved.

## Notes

- The project is designed for local experimentation and advanced agent workflows.
- Some features depend on optional libraries and external tools that may need to be installed on the host machine.
- Communication integrations are intentionally guarded by credential checks and authorization rules.

## License

This project is distributed under the MIT License. See the `LICENSE` file for details.

## Project status

This repository is a research/developer workspace for a local multi-agent coding and document assistant. It is best suited for environments where a local model runtime, Python tooling, and sandboxed execution are available.
