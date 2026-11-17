# Agent Robert

A local-first, multi-agent desktop assistant for running AI workflows on your own machine with Ollama.

Agent Robert combines local language models, agent delegation, and desktop automation to help with reading, writing, planning, debugging, and file workflows—without requiring a hosted LLM API for the core experience.

## Your personal assistant

Choose a local model, use the desktop chat interface, and let the orchestrator delegate specialized work to agents. Generated outputs live in an isolated session workspace, and network-sensitive Git and SSH actions require approval.

### Agent in action

The orchestrator delegates a writing request to a specialized document agent, which creates a Word document and returns the result to Agent Robert.

<img width="2126" height="2046" alt="Agent Robert orchestrating a document-writing task" src="https://github.com/user-attachments/assets/533275d8-e068-47d4-8869-925651fec01f" />

## Features

- Local LLM inference through Ollama, with model selection in the app
- Multi-agent orchestration and task delegation
- Desktop UI for chat, session work, and tool visibility
- File reading, writing, and document generation
- Code comprehension, verification, execution, and debugging
- Git and SSH workflows with approval checks for network-sensitive actions
- Optional email, Telegram, and WhatsApp integrations
- Session workspaces and guardrails for generated outputs and external actions

## Quick start

### Requirements

- Python 3.10 or later
- [Ollama](https://ollama.com/download) installed and running locally
- Tkinter, usually included with Python (some Linux distributions provide it as a separate OS package)

### Install Python dependencies

From the repository root:

```bash
python -m pip install -r requirements.txt
```

### Choose and download a model

Start with a smaller tool-calling model for a quick local test. Resource use depends on quantization and context size; 7B/8B models are typically much more approachable on a standard laptop than 31B models.

```bash
ollama pull qwen2.5:7b
```

Other options include `llama3.1:8b` and `gemma4:31b`. The 31B model is a larger option and can require substantial memory; it is not the recommended starting point. The app discovers installed Ollama models and lets you select one in the **Model** menu. For a tool-using workflow, choose a model/version that supports tool calling.

### Run Agent Robert

```bash
python -m src.ui.agent_ui
```

## Typical usage

1. Start Ollama and make sure a compatible model is installed.
2. Launch Agent Robert and select a model from the **Model** menu.
3. Ask the assistant to perform a task; the orchestrator can delegate specialized work to sub-agents.
4. Attach files or ask the assistant to work within the configured search space.
5. Review generated outputs and artifacts in the session workspace shown in the app.

## Integrations

Email and Telegram setup is optional; the core assistant works with Ollama alone. See [Integration setup](docs/SETUP.md) for detailed Ollama, Gmail, Telegram, and credentials instructions.

## Data and security

At startup, the app creates a session-specific directory beneath `workspace/` and configures it as `AGENT_WORKSPACE`. Relative file writes are directed there. The application may create local credential files under `config/`; keep these private and do not commit them. Optional communication integrations and network tools may connect to external services, so review permissions carefully and treat credentials as secrets.

## License

This project is distributed under the Apache License 2.0. See [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome. If you have ideas, bug fixes, or feature improvements, please open an issue or submit a pull request with a clear description of the change.
