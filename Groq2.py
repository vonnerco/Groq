import os
import re
import io
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr
from dotenv import load_dotenv
import streamlit as st
from typing import Generator
from groq import Groq

load_dotenv()  # Loads .env

st.set_page_config(page_icon="💬", layout="wide",
                   page_title="Groq2 Chat - Token-Optimized AI")

client = Groq(
    api_key=os.environ.get("GROQ_API_KEY"),
)

# All 7 Groq models with their rate limits
MODELS = {
    "llama-3.1-8b-instant": {
        "context_window": 8192,
        "rpm": 30,
        "rpd": 14400,
        "tpm": 6000,
        "tpd": 500000,
        "description": "Best for high-volume chat, prototypes, general use",
    },
    "allam-2-7b": {
        "context_window": 8192,
        "rpm": 30,
        "rpd": 7000,
        "tpm": 6000,
        "tpd": 500000,
        "description": "Arabic-focused workloads, lightweight text",
    },
    "llama-3.3-70b-versatile": {
        "context_window": 8192,
        "rpm": 30,
        "rpd": 1000,
        "tpm": 12000,
        "tpd": 100000,
        "description": "Higher-quality chat and reasoning",
    },
    "meta-llama/llama-4-scout-17b-16e-instruct": {
        "context_window": 8192,
        "rpm": 30,
        "rpd": 1000,
        "tpm": 30000,
        "tpd": 500000,
        "description": "Multimodal-style text and image workflows",
    },
    "qwen/qwen3-32b": {
        "context_window": 8192,
        "rpm": 60,
        "rpd": 1000,
        "tpm": 6000,
        "tpd": 500000,
        "description": "Higher RPM ceiling for text generation",
    },
    "moonshotai/kimi-k2-instruct": {
        "context_window": 8192,
        "rpm": 60,
        "rpd": 1000,
        "tpm": 10000,
        "tpd": 300000,
        "description": "Agentic or reasoning-heavy tasks",
    },
    "moonshotai/kimi-k2-instruct-0905": {
        "context_window": 8192,
        "rpm": 60,
        "rpd": 1000,
        "tpm": 10000,
        "tpd": 300000,
        "description": "Newer 0905 version of kimi-k2",
    },
}

# Default model
DEFAULT_MODEL = "moonshotai/kimi-k2-instruct"

# System prompt for auto file/code features
AUTO_FEATURES_PROMPT = """You have access to these automatic features. Use them when appropriate - do NOT explain them to the user:

1. FILE READING: If user asks to see, read, show, look at, or understand any file - automatically read it using the > filename shortcut. DO NOT ask permission.

2. FILE WRITING: If user asks to write, save, create, or modify any file - automatically use >! filename, then prompt for content. DO NOT ask permission.

3. CODE EXECUTION: If user asks to run, execute, test, or try any code - it will be automatically detected and run. DO NOT ask permission.

IMPORTANT: When you detect the user wants to read a file, just type > filename and press enter. The file will be read and its contents sent back to you automatically. You do not need to explain what you're doing - just do it and respond to the content.

IMPORTANT: When you detect the user wants to write a file, just type >! filename and press enter. The user will then enter content followed by '---'. You do not need to explain what you're doing.

IMPORTANT: When the user shows you code, it will be automatically executed and the output returned to you. You do not need to ask permission to run code."""

# Custom styling
st.markdown("""
<style>
    .user-message {
        background-color: #1a1a2e;
        padding: 10px 15px;
        border-radius: 10px;
        margin: 5px 0;
    }
    .assistant-message {
        background-color: #16213e;
        padding: 10px 15px;
        border-radius: 10px;
        margin: 5px 0;
    }
    .stats-box {
        background-color: #0f3460;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)


def icon(emoji: str):
    """Shows an emoji as a Notion-style page icon."""
    st.write(
        f'<span style="font-size: 78px; line-height: 1">{emoji}</span>',
        unsafe_allow_html=True,
    )


# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": AUTO_FEATURES_PROMPT}]

if "selected_model" not in st.session_state:
    st.session_state.selected_model = DEFAULT_MODEL

if "total_prompt_tokens" not in st.session_state:
    st.session_state.total_prompt_tokens = 0

if "total_completion_tokens" not in st.session_state:
    st.session_state.total_completion_tokens = 0

if "total_tokens_used" not in st.session_state:
    st.session_state.total_tokens_used = 0

if "request_count" not in st.session_state:
    st.session_state.request_count = 0


icon("🏎️")

st.subheader("Groq2 Chat - Token-Optimized AI", divider="rainbow", anchor=False)

# Layout for model selection and max_tokens slider
col1, col2 = st.columns(2)

with col1:
    model_option = st.selectbox(
        "Choose a model:",
        options=list(MODELS.keys()),
        format_func=lambda x: f"{x} ({MODELS[x]['description'][:40]})",
        index=list(MODELS.keys()).index(DEFAULT_MODEL) if DEFAULT_MODEL in MODELS else 0,
    )

# Detect model change and clear chat history if model has changed
if st.session_state.selected_model != model_option:
    st.session_state.messages = [{"role": "system", "content": AUTO_FEATURES_PROMPT}]
    st.session_state.selected_model = model_option
    st.session_state.total_prompt_tokens = 0
    st.session_state.total_completion_tokens = 0
    st.session_state.total_tokens_used = 0
    st.session_state.request_count = 0

model_info = MODELS[model_option]
max_tokens_range = model_info["context_window"]

with col2:
    max_tokens = st.slider(
        "Max Tokens:",
        min_value=512,
        max_value=max_tokens_range,
        value=min(8192, max_tokens_range),
        step=512,
        help=f"Adjust the maximum number of tokens. Max for selected model: {max_tokens_range}"
    )

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    if message["role"] == "system":
        continue
    avatar = '🤖' if message["role"] == "assistant" else '👨‍💻'
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])

# Stats display
st.markdown("---")
col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)
with col_stats1:
    st.metric("Requests", st.session_state.request_count)
with col_stats2:
    st.metric("Prompt Tokens", st.session_state.total_prompt_tokens)
with col_stats3:
    st.metric("Completion Tokens", st.session_state.total_completion_tokens)
with col_stats4:
    st.metric("Total Tokens", st.session_state.total_tokens_used)


def generate_chat_responses(chat_completion) -> Generator[str, None, None]:
    """Yield chat response content from the Groq API response."""
    for chunk in chat_completion:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def execute_code(code: str) -> tuple[str, str]:
    """Execute Python code and return (stdout, stderr)."""
    output_buffer = io.StringIO()
    error_buffer = io.StringIO()
    try:
        with redirect_stdout(output_buffer), redirect_stderr(error_buffer):
            exec(code, {"__name__": "__main__"})
        return output_buffer.getvalue(), error_buffer.getvalue()
    except Exception as e:
        tb = traceback.format_exc()
        return "", f"{e}\n{tb}"


def handle_auto_actions(content: str) -> tuple[str, str, str]:
    """Handle auto file read/write actions. Returns (read_content, write_file, write_content)."""
    auto_read_file = None
    auto_write_file = None
    auto_write_content = None

    for line in content.split('\n'):
        stripped = line.strip()
        if stripped.startswith('>! '):
            auto_write_file = stripped[3:].strip()
            code_match = re.search(r'```[\w]*\n(.*?)```', content, re.DOTALL)
            if code_match:
                auto_write_content = code_match.group(1)
            else:
                remaining = content[content.index(stripped) + len(stripped):]
                lines = [l for l in remaining.split('\n') if l.strip() and not l.strip().startswith('>')][:20]
                auto_write_content = '\n'.join(lines)
        elif stripped.startswith('> ') and not auto_read_file:
            auto_read_file = stripped[2:].strip()

    # Perform auto-read
    if auto_read_file:
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            filepath = os.path.join(base_dir, auto_read_file)
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read(), None, None
        except FileNotFoundError:
            return f"File not found: {auto_read_file}", None, None
        except Exception as e:
            return f"Error reading file: {e}", None, None

    # Perform auto-write
    if auto_write_file and auto_write_content:
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            filepath = os.path.join(base_dir, auto_write_file)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(auto_write_content)
            return None, auto_write_file, f"Auto-wrote {len(auto_write_content.split(chr(10)))} lines to '{auto_write_file}'"
        except Exception as e:
            return None, None, f"Auto-write failed: {e}"

    return None, None, None


if prompt := st.chat_input("Enter your prompt here..."):
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user", avatar='👨‍💻'):
        st.markdown(prompt)

    # Auto-detect file intent
    auto_read = False
    auto_write = False
    filename = ""
    exec_code = False
    code_to_run = None

    cmd = prompt.lower().strip()

    # Check for > and >! shortcuts
    if cmd.startswith(">! "):
        filename = prompt[3:].strip()
        auto_write = True
    elif cmd.startswith("> "):
        filename = prompt[2:].strip()
        auto_read = True
    # Auto-detect: bare path
    elif re.match(r'^[\w\-\./\\]+$', cmd) and not any(cmd.startswith(m) for m in ["model", "stats", "clear", "tips", "exit"]):
        filename = cmd
        auto_read = True
    # Auto-detect write intent
    elif any(kw in cmd for kw in ["write to ", "save to ", "create file ", "make file ", "new file "]):
        match = re.search(r'(?:to |file )?([\w\-\./\\]+)$', cmd)
        if match:
            filename = match.group(1)
            auto_write = True

    # Auto-detect code execution
    code_block_match = re.search(r'```(?:python)?\n(.*?)```', prompt, re.DOTALL)
    exec_keywords = ["run ", "execute ", "exec ", "run code", "execute code", "run this", "execute this", "run it", "execute it"]
    is_bare_code = (
        not any(cmd.startswith(m) for m in ["model", "stats", "clear", "tips", "exit", "read ", "write ", "> ", ">! "]) and
        any(k in prompt for k in ["print(", "import ", "def ", "class ", "if ", "for ", "while ", "return ", "print("]) and
        len(prompt.split('\n')) <= 10
    )

    if code_block_match or is_bare_code or any(kw in cmd for kw in exec_keywords):
        code = code_block_match.group(1) if code_block_match else None
        if not code:
            code_match = re.search(r'(?:run|execute|exec)\s+(?:this\s+)?(?:code\s+)?(?:here:?)?\s*(?:\n(.*))?', prompt, re.DOTALL | re.IGNORECASE)
            if not code_match:
                lines = prompt.split('\n')
                code_lines = [l for l in lines if any(k in l for k in ['import ', 'def ', 'print(', 'if ', 'for ', 'while ', '=', '.'])]
                if code_lines:
                    code = '\n'.join(code_lines)
        if code:
            code = re.sub(r'^(run|exec|python)[:\s]*', '', code, flags=re.IGNORECASE).strip()
            code_to_run = code
            exec_code = True

    full_response = ""

    # Handle file read
    if auto_read:
        if filename:
            try:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                filepath = os.path.join(base_dir, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                st.session_state.messages.append({"role": "system", "content": f"[File '{filename}' contents]:\n{content}"})
                with st.chat_message("system", avatar='📄'):
                    st.code(content, language="text")
            except FileNotFoundError:
                st.error(f"File not found: {filename}")
            except Exception as e:
                st.error(f"Error reading file: {e}")
        st.rerun()

    # Handle file write
    elif auto_write:
        st.info(f"Write mode for: {filename}. Use the code execution feature to write files.")
        st.rerun()

    # Handle code execution
    elif exec_code and code_to_run:
        st.info("Executing code...")
        stdout_out, stderr_out = execute_code(code_to_run)
        if stdout_out:
            st.code(stdout_out, language="python")
        if stderr_out:
            st.error(stderr_out)
        if not stdout_out and not stderr_out:
            st.info("(no output)")
        st.rerun()

    # Normal chat completion with specified parameters
    else:
        try:
            # Build API call kwargs
            api_kwargs = {
                "model": model_option,
                "messages": [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages
                ],
                "temperature": 0.2,
                "max_completion_tokens": 8192,
                "top_p": 0.9,
                "stream": True,
                "stop": None,
            }
            # Only add reasoning_effort for models that support it with "high" value
            # Most models don't support it, or only support "none"/"default"
            chat_completion = client.chat.completions.create(**api_kwargs)

            # Use the generator function with st.write_stream
            with st.chat_message("assistant", avatar="🤖"):
                chat_responses_generator = generate_chat_responses(chat_completion)
                full_response = st.write_stream(chat_responses_generator)

            # Append the full response to session_state.messages
            if isinstance(full_response, str):
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            else:
                combined_response = "\n".join(str(item) for item in full_response)
                st.session_state.messages.append({"role": "assistant", "content": combined_response})

            # Handle auto actions from AI response
            read_content, write_file, write_msg = handle_auto_actions(full_response)
            if read_content:
                st.session_state.messages.append({"role": "system", "content": f"[File contents]:\n{read_content}"})
            if write_file:
                st.session_state.messages.append({"role": "system", "content": f"[{write_msg}]"})

            st.rerun()

        except Exception as e:
            st.error(e, icon="🚨")