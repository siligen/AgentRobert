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
