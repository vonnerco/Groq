# Groq2.py

A Streamlit-based chat app using Groq's API with token-optimized features.

## Prerequisites

- Python 3.10+
- A Groq API key

## Setup

### 1. Install dependencies

```bash
pip install groq streamlit python-dotenv
```

### 2. Set your API key

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_api_key_here
```

Or export it directly:

```bash
export GROQ_API_KEY=your_api_key_here
```

### 3. Run the app

```bash
streamlit run Groq2.py
```

The app will open in your browser at `http://localhost:8501`.

## Features

- **7 Groq models** to choose from (llama, qwen, kimi, allam, etc.)
- **Model switching** clears chat and resets metrics
- **Max token slider** adjusts response length per model
- **Session metrics** — request count, prompt/completion/total tokens
- **Auto file features** — use `> filename` to read a file, `>! filename` to write
- **Code execution** — paste or type Python code to run it inline
- **Streaming responses** for real-time output

## API Parameters

The following parameters are used for every chat completion:

| Parameter | Value |
|-----------|-------|
| `temperature` | 0.2 |
| `max_completion_tokens` | 8192 |
| `top_p` | 0.9 |
| `stream` | True |
| `stop` | None |

Note: `reasoning_effort` is currently **not supported** by any of the available models. It is noted in the code for future use when model support is added.

## Available Models

1. `llama-3.1-8b-instant` — High-volume chat (30 RPM, 14,400 RPD)
2. `allam-2-7b` — Arabic workloads, lightweight
3. `llama-3.3-70b-versatile` — Higher-quality chat and reasoning
4. `meta-llama/llama-4-scout-17b-16e-instruct` — Multimodal text/image
5. `qwen/qwen3-32b` — Higher RPM ceiling (60 RPM)
6. `moonshotai/kimi-k2-instruct` — Agentic/reasoning-heavy tasks
7. `moonshotai/kimi-k2-instruct-0905` — Newer version of kimi-k2

## Commands (in chat input)

- `> filename` — Read a local file
- `>! filename` — Write to a local file
- Type `clear` — Reset conversation and metrics
- Type `stats` — View session statistics
- Type `models` — List all available models