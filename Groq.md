# Groq Setup Guide

This guide uses the official Groq rate-limits page as the source of truth:

- [Groq Rate Limits](https://console.groq.com/docs/rate-limits)
- [Groq OpenAI Compatibility](https://console.groq.com/docs/openai)
- [Groq Supported Models](https://console.groq.com/docs/models)

I’m ranking the models below by free-tier daily request allowance (`RPD`), then using `TPM` as a tie-breaker. That means this is the best-fit list for chat/text apps on the free plan, not audio-only models.

---

## Quick Start

1. Create a Groq account.
2. Open the Groq console and generate an API key.
3. Save the key as `GROQ_API_KEY`.
4. Pick one of the models below.
5. Send requests to the OpenAI-compatible Groq endpoint.

### Base URL
`https://api.groq.com/openai/v1`

### Key rule
Groq rate limits apply at the organization level, not per API key.

---

## Top 7 Free Models by Rate Limit

### 1) `llama-3.1-8b-instant`

- `RPM`: 30
- `RPD`: 14.4K
- `TPM`: 6K
- `TPD`: 500K

Best for high-volume chat, prototypes, and general use.

### 2) `allam-2-7b`

- `RPM`: 30
- `RPD`: 7K
- `TPM`: 6K
- `TPD`: 500K

Best for Arabic-focused workloads and lightweight text tasks.

### 3) `llama-3.3-70b-versatile`

- `RPM`: 30
- `RPD`: 1K
- `TPM`: 12K
- `TPD`: 100K

Best for higher-quality chat and reasoning when you can stay within the lower daily cap.

### 4) `meta-llama/llama-4-scout-17b-16e-instruct`

- `RPM`: 30
- `RPD`: 1K
- `TPM`: 30K
- `TPD`: 500K

Best for multimodal-style text and image workflows.

### 5) `qwen/qwen3-32b`

- `RPM`: 60
- `RPD`: 1K
- `TPM`: 6K
- `TPD`: 500K

Best for text generation when you want a higher RPM ceiling.

### 6) `moonshotai/kimi-k2-instruct`

- `RPM`: 60
- `RPD`: 1K
- `TPM`: 10K
- `TPD`: 300K

Best for agentic or reasoning-heavy text tasks.

### 7) `moonshotai/kimi-k2-instruct-0905`

- `RPM`: 60
- `RPD`: 1K
- `TPM`: 10K
- `TPD`: 300K

Best if you want the newer 0905 version with the same rate-limit profile.

### Honorable mentions

- `openai/gpt-oss-120b`
- `openai/gpt-oss-20b`
- `openai/gpt-oss-safeguard-20b`
- `groq/compound`
- `groq/compound-mini`

These are useful, but they do not beat the top 7 above on free-tier request allowance.

---

## Step-by-Step Setup

### 1) Create your account

1. Go to the Groq console.
2. Sign in or create an account.
3. Open the API keys page.

### 2) Create an API key

1. Generate a new API key.
2. Copy it once and store it safely.
3. Add it to your environment as `GROQ_API_KEY`.

### 3) Confirm your limits

1. Open the Groq rate limits page.
2. Check the free plan table.
3. Confirm the model you want is available in your organization.

### 4) Pick a model

1. Start with `llama-3.1-8b-instant` if you want the safest free-tier choice.
2. Move to a larger model only if you need the extra quality or capability.
3. If your app needs more throughput, check whether the model has a higher `RPM`.

### 5) Send your first request

Use the OpenAI-compatible endpoint:

```bash
curl https://api.groq.com/openai/v1/chat/completions ^
  -H "Authorization: Bearer %GROQ_API_KEY%" ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"llama-3.1-8b-instant\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}"
```

### 5a) Windows (CMD/Powershell)

```bash
curl https://api.groq.com/openai/v1/chat/completions -H "Authorization: Bearer %GROQ_API_KEY%" -H "Content-Type: application/json" -d "{\"model\":\"llama-3.1-8b-instant\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}"
```

### 5b) Why 5a Works in CMD/Powershell but Not Bash

The `%GROQ_API_KEY%` syntax is Windows CMD/Powershell environment variable expansion — it only works in those shells. In bash (including Git Bash), environment variables use `$VAR` syntax. So on Windows:

- **CMD/Powershell**: `%GROQ_API_KEY%` → expands to the API key value
- **Bash**: `%GROQ_API_KEY%` → passed literally as a string (invalid key)

To use in bash, either export the variable first or use `$GROQ_API_KEY` directly.

### 5c) Verified Working Windows (CMD/Powershell)

```bash
curl https://api.groq.com/openai/v1/chat/completions -H "Authorization: Bearer %GROQ_API_KEY%" -H "Content-Type: application/json" -d "{\"model\":\"llama-3.1-8b-instant\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}"
```

---

## Python Example

Install the SDK:

```bash
pip install openai
```

Use this code:

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ["GROQ_API_KEY"],
)

response = client.chat.completions.create(
    model="llama-3.1-8b-instant",
    messages=[{"role": "user", "content": "Hello"}],
)

print(response.choices[0].message.content)
```

---

## JavaScript Example

Install the SDK:

```bash
npm install openai
```

Use this code:

```js
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "https://api.groq.com/openai/v1",
  apiKey: process.env.GROQ_API_KEY,
});

const response = await client.chat.completions.create({
  model: "llama-3.1-8b-instant",
  messages: [{ role: "user", content: "Hello" }],
});

console.log(response.choices[0].message.content);
```

---

## Best Practices

1. Start with `llama-3.1-8b-instant` for the easiest free-tier success path.
2. Watch `429 Too Many Requests` responses and respect `retry-after`.
3. Track `x-ratelimit-remaining-requests` and `x-ratelimit-remaining-tokens`.
4. Keep prompts short when you are testing rate limits.
5. Use cached tokens when possible because Groq does not count them toward rate limits.

### Important: Do Daily Limits Reset When Switching Models?

**No.** Groq rate limits apply at the **organization level**, not per model. This means:

- All 7 models share the same daily/request limits
- Switching models does **NOT** reset your RPD or TPD counters
- Your daily quota is shared across ALL models you use
- Using `llama-3.1-8b-instant` (14.4K RPD) and `llama-3.3-70b-versatile` (1K RPD) draws from the same pool

**Strategy:** Use `llama-3.1-8b-instant` for most tasks (highest RPD), switch to larger models only when needed for reasoning quality.

---

## Token Optimization Tips

To minimize token usage and extend your daily limits:

1. **Be Concise** - Shorter prompts = fewer tokens per request
2. **Avoid Repeating** - The AI remembers conversation context
3. **Use 'clear' Command** - Reset conversation to clear history (also resets session metrics)
4. **One Clear Question** - Better than multiple vague questions
5. **End with "keep it short"** - For brief, token-efficient responses
6. **Skip Filler Words** - "please", "thanks", "could you please" add tokens
7. **Keep Messages Brief** - Each turn sends the full conversation history
8. **Use `llama-3.1-8b-instant`** - Best RPD (14,400) for high-volume chat
9. **Switch Models Wisely** - Use `llama-3.3-70b-versatile` only for reasoning tasks
10. **Monitor Metrics** - Watch Session Metrics for RPD/TPD usage warnings

---

## Useful Headers

Groq exposes useful headers in responses:

- `retry-after`
- `x-ratelimit-limit-requests`
- `x-ratelimit-limit-tokens`
- `x-ratelimit-remaining-requests`
- `x-ratelimit-remaining-tokens`
- `x-ratelimit-reset-requests`
- `x-ratelimit-reset-tokens`

---

## Copy-Paste Checklist

1. Create a Groq account.
2. Generate an API key.
3. Set `GROQ_API_KEY`.
4. Pick a model from the top 7 list.
5. Install `openai` in Python or JavaScript.
6. Run the example request.
7. Add retry handling for rate-limit errors.

---

## How to Run Python Script

### Prerequisites
- Python installed
- `openai` package installed (`pip install openai`)
- A Groq API key

### Pro Setup with python-dotenv (Recommended)

1. **Install python-dotenv**:
   ```bash
   pip install python-dotenv
   ```

2. **Create `.env` file** in your project folder:
   ```text
   GROQ_API_KEY=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
   ```

3. **Update `Groq.py`** to load from `.env`:
   ```python
   from dotenv import load_dotenv
   load_dotenv()  # Loads .env
   # Then os.environ["GROQ_API_KEY"] works!
   ```

4. **Run the script**:
   ```bash
   python Groq.py
   ```

### Step-by-Step Instructions

0. **Permanently save your API key** (PowerShell - persists across sessions):
   ```powershell
   [Environment]::SetEnvironmentVariable("GROQ_API_KEY", "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", "User")
   ```

1. **Save your API key** (session-only - resets when terminal closes):
   ```powershell
   $env:GROQ_API_KEY="your_api_key_here"
   ```

2. **Install the OpenAI SDK** (if not already installed):
   ```bash
   pip install openai
   ```

3. **Save the example code** to a file (e.g., `Groq.py`) or use the provided `Groq.py` file.

4. **Run the script**:
   ```bash
   python Groq.py
   ```

   Or with the API key set inline:
   ```bash
   GROQ_API_KEY=your_api_key_here python Groq.py
   ```

5. **Expected output**:
   ```
   Hello response from the model
   ```

### Troubleshooting

- **ModuleNotFoundError: No module named 'openai'** - Run `pip install openai`
- **KeyError: 'GROQ_API_KEY'** - Set the `GROQ_API_KEY` environment variable
- **429 Too Many Requests** - Wait and retry, or switch to a model with higher RPM

---

## Groq.py Commands and Features

The `Groq.py` chat script includes token optimization features:

### Commands
- `clear` - Clear conversation & reset session metrics
- `stats` - View token statistics and daily rate limits
- `models` - List all 7 available models with limits
- `model X` - Switch to model number X (e.g., `model 3`)
- `tips` - Show token-saving tips
- `exit` - End chat session

### Session Metrics Display
After each response, you'll see:
- **Req #** - Current request number
- **RPD** - Requests Per Day used vs limit
- **Prompt** - Tokens in your message
- **TPD** - Tokens Per Day used vs limit
- **Output** - Tokens in AI response
- **Window** - Context window usage percentage
- **Tip** - Rotating token-saving reminder

### Model Switching
- All models share the same daily limits (RPD/TPD)
- Switching models does NOT reset daily counters
- Use `model 1` for high-volume, `model 3` for reasoning

### Rate Limits Are Shared
Groq rate limits apply at the organization level, not per API key or model. Your daily quota is shared across all models.

