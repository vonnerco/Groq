import os
import json
from datetime import datetime

import sys
import warnings

def suppress_streamlit_warnings():
    """Suppress Streamlit context warnings for bare mode."""
    if not hasattr(sys, "_getframe"):
        return
    warnings.filterwarnings("ignore", message=".*missing ScriptRunContext.*")

suppress_streamlit_warnings()

import re
import io
import traceback
import mimetypes
import uuid
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from dotenv import load_dotenv
import streamlit as st
from typing import Generator
from groq import Groq
import asyncio
from streamlit.runtime.scriptrunner import get_script_run_ctx


def is_streamlit_context() -> bool:
    return get_script_run_ctx() is not None


if not is_streamlit_context():
    print("Run this app with: streamlit run Groq2.py")
    sys.exit(0)


APP_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "groq2_state.json")
SEED_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "groq2_seed_state.json")
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "groq2_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def load_persistent_state() -> dict:
    """Load durable app state from disk."""
    today = datetime.now().date().isoformat()
    default_state = {
        "saved_chats": {},
        "uploaded_files": [],
        "chat_name": "New Chat",
        "selected_model": DEFAULT_MODEL,
        "messages": [{"role": "system", "content": AUTO_FEATURES_PROMPT}],
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_tokens_used": 0,
        "request_count": 0,
        "current_tokens": 0,
        "usage_date": today,
        "recent_prompts": [],
    }
    if not os.path.exists(APP_STATE_FILE):
        if os.path.exists(SEED_STATE_FILE):
            try:
                with open(SEED_STATE_FILE, "r", encoding="utf-8") as f:
                    seeded = json.load(f)
                if isinstance(seeded, dict):
                    default_state.update({k: seeded.get(k, v) for k, v in default_state.items()})
                    default_state["uploaded_files"] = []
                    return default_state
            except Exception:
                pass
        return default_state
    try:
        with open(APP_STATE_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            return default_state
        default_state.update({k: loaded.get(k, v) for k, v in default_state.items()})
        if not isinstance(default_state.get("usage_date"), str) or not default_state["usage_date"]:
            default_state["usage_date"] = today
        if not isinstance(default_state["messages"], list) or not default_state["messages"]:
            default_state["messages"] = [{"role": "system", "content": AUTO_FEATURES_PROMPT}]
        if not isinstance(default_state["saved_chats"], dict):
            default_state["saved_chats"] = {}
        if not isinstance(default_state.get("recent_prompts"), list):
            default_state["recent_prompts"] = []
        uploaded_files = default_state["uploaded_files"]
        if isinstance(uploaded_files, dict):
            default_state["uploaded_files"] = [
                {"id": uuid.uuid4().hex, "label": name, "path": path, "original_name": name}
                for name, path in uploaded_files.items()
            ]
        elif not isinstance(uploaded_files, list):
            default_state["uploaded_files"] = []
        else:
            normalized = []
            for item in uploaded_files:
                if isinstance(item, dict) and "path" in item:
                    normalized.append({
                        "id": item.get("id", uuid.uuid4().hex),
                        "label": item.get("label") or item.get("original_name") or os.path.basename(item["path"]),
                        "path": item["path"],
                        "original_name": item.get("original_name") or item.get("label") or os.path.basename(item["path"]),
                    })
            default_state["uploaded_files"] = normalized
        return default_state
    except Exception:
        return default_state


def save_persistent_state() -> None:
    """Write durable app state to disk."""
    state = {
        "saved_chats": st.session_state.saved_chats,
        "uploaded_files": st.session_state.get("uploaded_files", []),
        "chat_name": st.session_state.chat_name,
        "selected_model": st.session_state.selected_model,
        "messages": st.session_state.messages,
        "total_prompt_tokens": st.session_state.total_prompt_tokens,
        "total_completion_tokens": st.session_state.total_completion_tokens,
        "total_tokens_used": st.session_state.total_tokens_used,
        "request_count": st.session_state.request_count,
        "current_tokens": st.session_state.current_tokens,
        "usage_date": st.session_state.usage_date,
        "recent_prompts": st.session_state.get("recent_prompts", []),
        "uploaded_signatures": st.session_state.get("uploaded_signatures", []),
    }
    tmp_file = f"{APP_STATE_FILE}.tmp"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp_file, APP_STATE_FILE)
    except Exception:
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass


def reset_chat_state(clear_name: bool = False) -> None:
    st.session_state.messages = [{"role": "system", "content": AUTO_FEATURES_PROMPT}]
    st.session_state.current_tokens = 0
    if clear_name:
        st.session_state.chat_name = "New Chat"
    save_persistent_state()


def get_safe_upload_path(filename: str) -> str:
    safe_name = os.path.basename(filename)
    base, ext = os.path.splitext(safe_name)
    candidate = os.path.join(UPLOAD_DIR, safe_name)
    if not os.path.exists(candidate):
        return candidate
    unique_name = f"{base}_{uuid.uuid4().hex[:8]}{ext}"
    return os.path.join(UPLOAD_DIR, unique_name)


def save_uploaded_file(uploaded_file) -> dict:
    file_bytes = uploaded_file.getbuffer()
    path = get_safe_upload_path(uploaded_file.name)
    with open(path, "wb") as f:
        f.write(file_bytes)
    return {
        "id": uuid.uuid4().hex,
        "label": uploaded_file.name,
        "path": path,
        "original_name": uploaded_file.name,
        "size_bytes": len(file_bytes),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }


def file_record_signature(uploaded_file) -> str:
    """Create a lightweight signature to avoid duplicate saves on reruns."""
    try:
        size = len(uploaded_file.getbuffer())
    except Exception:
        size = 0
    return f"{uploaded_file.name}|{size}"


def read_text_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return Path(path).read_bytes().decode("utf-8", errors="replace")


def try_preview_csv(path: str):
    try:
        import pandas as pd
        return pd.read_csv(path)
    except Exception:
        try:
            import pandas as pd
            return pd.read_csv(path, encoding="latin-1")
        except Exception:
            return None


def try_preview_xlsx(path: str):
    try:
        import pandas as pd
        return pd.read_excel(path)
    except Exception:
        return None


def try_preview_docx(path: str) -> str | None:
    try:
        from docx import Document
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception:
        return None


def try_preview_pdf(path: str) -> str | None:
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        parts = []
        for page in reader.pages[:3]:
            parts.append(page.extract_text() or "")
        return "\n".join(parts).strip()
    except Exception:
        return None


def render_uploaded_file(path: str, original_name: str, file_id: str):
    ext = Path(original_name).suffix.lower()
    mime, _ = mimetypes.guess_type(original_name)
    st.markdown(f"### {original_name}")
    file_bytes = Path(path).read_bytes()
    st.download_button(
        label=f"Download {original_name}",
        data=file_bytes,
        file_name=original_name,
        mime=mime or "application/octet-stream",
        use_container_width=True,
        key=f"download_{file_id}",
    )

    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}:
        st.image(path, caption=original_name, use_container_width=True)
        return

    if ext in {".txt", ".py", ".sql", ".java", ".html", ".htm", ".md", ".json", ".xml", ".yaml", ".yml", ".css", ".js", ".ts", ".sh", ".ini", ".cfg", ".log"}:
        st.code(read_text_file(path), language=ext.lstrip(".") or "text")
        return

    if ext == ".csv":
        df = try_preview_csv(path)
        if df is not None:
            st.dataframe(df, use_container_width=True)
        else:
            st.code(read_text_file(path), language="text")
        return

    if ext in {".xlsx", ".xls"}:
        df = try_preview_xlsx(path)
        if df is not None:
            st.dataframe(df, use_container_width=True)
        else:
            st.code(read_text_file(path), language="text")
            st.info("Install `pandas` and `openpyxl` to preview spreadsheets as tables.")
        return

    if ext == ".docx":
        text = try_preview_docx(path)
        if text:
            st.text_area("Document text preview", text, height=300)
        else:
            st.code(read_text_file(path), language="text")
            st.info("Install `python-docx` to preview Word documents as extracted text.")
        return

    if ext == ".pdf":
        text = try_preview_pdf(path)
        if text:
            st.text_area("PDF text preview", text, height=300)
        else:
            st.code(read_text_file(path), language="text")
            st.info("Install `pypdf` to extract text from PDFs.")
        return

    st.text_area("File preview", read_text_file(path), height=300)


def delete_uploaded_file(file_id: str) -> None:
    uploaded_files = st.session_state.get("uploaded_files", [])
    target = next((item for item in uploaded_files if item.get("id") == file_id), None)
    if target and os.path.exists(target.get("path", "")):
        try:
            os.remove(target["path"])
        except Exception:
            pass
    st.session_state["uploaded_files"] = [item for item in uploaded_files if item.get("id") != file_id]
    save_persistent_state()


def clear_all_uploaded_files() -> None:
    uploaded_files = st.session_state.get("uploaded_files", [])
    for item in uploaded_files:
        path = item.get("path")
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
    st.session_state["uploaded_files"] = []
    save_persistent_state()


def ensure_daily_usage_state() -> None:
    """Reset usage counters when a new calendar day starts."""
    today = datetime.now().date().isoformat()
    if st.session_state.get("usage_date") != today:
        st.session_state.total_prompt_tokens = 0
        st.session_state.total_completion_tokens = 0
        st.session_state.total_tokens_used = 0
        st.session_state.request_count = 0
        st.session_state.current_tokens = 0
        st.session_state.usage_date = today
        save_persistent_state()


def get_tokens_left_today(model_name: str) -> int | None:
    """Return the remaining daily token budget for the active model."""
    model_info = MODELS.get(model_name)
    if not model_info:
        return None
    daily_limit = model_info.get("tpd")
    if not isinstance(daily_limit, int):
        return None
    return max(daily_limit - int(st.session_state.get("total_tokens_used", 0)), 0)


def ensure_ux_state() -> None:
    """Initialize UX-related state used by the app chrome."""
    defaults = {
        "safe_mode": False,
        "last_assistant_response": "",
        "model_health": "unknown",
        "recent_prompts": [],
        "show_prompt_history": False,
        "uploaded_signatures": [],
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def track_prompt(prompt: str) -> None:
    prompts = st.session_state.setdefault("recent_prompts", [])
    clean_prompt = prompt.strip()
    if not clean_prompt:
        return
    if clean_prompt in prompts:
        prompts.remove(clean_prompt)
    prompts.insert(0, clean_prompt)
    del prompts[10:]
    save_persistent_state()


def already_uploaded(signature: str) -> bool:
    return signature in st.session_state.setdefault("uploaded_signatures", [])


def remember_uploaded(signature: str) -> None:
    signatures = st.session_state.setdefault("uploaded_signatures", [])
    if signature not in signatures:
        signatures.append(signature)
        save_persistent_state()


def set_model_health(model_name: str) -> str:
    model_info = MODELS.get(model_name)
    if not model_info:
        return "unavailable"
    return "available"


def model_status_emoji(status: str) -> str:
    return {
        "available": "🟢",
        "rate limited": "🟡",
        "unverified": "🟠",
        "unavailable": "🔴",
        "unknown": "⚪",
    }.get(status, "⚪")


def insert_uploaded_file_into_chat(file_id: str) -> None:
    uploaded_files = st.session_state.get("uploaded_files", [])
    target = next((item for item in uploaded_files if item.get("id") == file_id), None)
    if not target or not os.path.exists(target.get("path", "")):
        st.error("File not found.")
        return
    path = target["path"]
    original_name = target.get("original_name") or target.get("label") or os.path.basename(path)
    ext = Path(original_name).suffix.lower()
    content = ""
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}:
        st.session_state.messages.append({
            "role": "system",
            "content": f"[Image uploaded: {original_name} stored at {path}]",
        })
    else:
        if ext == ".csv":
            df = try_preview_csv(path)
            content = df.to_string(index=False) if df is not None else read_text_file(path)
        elif ext in {".xlsx", ".xls"}:
            df = try_preview_xlsx(path)
            content = df.to_string(index=False) if df is not None else read_text_file(path)
        elif ext == ".docx":
            content = try_preview_docx(path) or read_text_file(path)
        elif ext == ".pdf":
            content = try_preview_pdf(path) or read_text_file(path)
        else:
            content = read_text_file(path)
        st.session_state.messages.append({
            "role": "system",
            "content": f"[Uploaded file: {original_name}]\n{content}",
        })
    save_persistent_state()


def format_file_size(size_bytes: int | None) -> str:
    if not size_bytes:
        return "0 B"
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024


def upload_group_for_extension(ext: str) -> str:
    ext = ext.lower()
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}:
        return "Images"
    if ext in {".pdf", ".docx"}:
        return "Documents"
    if ext in {".csv", ".xlsx", ".xls"}:
        return "Spreadsheets"
    if ext in {".txt", ".md", ".json", ".xml", ".yaml", ".yml", ".log"}:
        return "Text"
    if ext in {".py", ".sql", ".java", ".html", ".htm", ".css", ".js", ".ts", ".sh", ".ini", ".cfg"}:
        return "Code"
    return "Other"

try:
    from mcp import ClientSession
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
load_dotenv()  # Loads .env
st.set_page_config(page_icon="💬", layout="wide",
                   page_title="Vonnerco GPT")

# MCP Client
mcp_client = None
mcp_session = None


async def connect_mcp_server(command: str, args: list = None):
    """Connect to a local MCP server."""
    global mcp_client, mcp_session
    if not MCP_AVAILABLE:
        return "MCP package not installed. Run: pip install mcp"
    try:
        from mcp.client.stdio import stdio_client
        params = {"command": command}
        if args:
            params["args"] = args
        mcp_client = stdio_client(params)
        mcp_session = ClientSession(mcp_client)
        await mcp_session.initialize()
        return "Connected to MCP server"
    except Exception as e:
        return f"Failed to connect: {e}"


async def call_mcp_tool(tool_name: str, arguments: dict = None):
    """Call a tool from the MCP server."""
    global mcp_session
    if not mcp_session:
        return "Not connected to MCP server"
    try:
        result = await mcp_session.call_tool(tool_name, arguments or {})
        return result.content if hasattr(result, 'content') else str(result)
    except Exception as e:
        return f"Tool error: {e}"


async def list_mcp_tools():
    """List available tools from MCP server."""
    global mcp_session
    if not mcp_session:
        return []
    try:
        tools = await mcp_session.list_tools()
        return tools
    except Exception:
        return []

groq_api_key = os.getenv("GROQ_API_KEY")
if not groq_api_key:
    st.error("GROQ_API_KEY is not set. Add it to your .env file before running this app.")
    st.stop()

client = Groq(api_key=groq_api_key)
# Supported Groq models with their approximate rate limits
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
    "qwen-qwq-32b": {
        "context_window": 8192,
        "rpm": 30,
        "rpd": 1000,
        "tpm": 6000,
        "tpd": 300000,
        "description": "Reasoning-heavy tasks and step-by-step problem solving",
    },
    "openai/gpt-oss-120b": {
        "context_window": 8192,
        "rpm": 30,
        "rpd": 1000,
        "tpm": 6000,
        "tpd": 300000,
        "description": "High-capability agentic work and long-context reasoning",
    },
}
# Default model
DEFAULT_MODEL = "openai/gpt-oss-120b"
# System prompt for auto file/code features
AUTO_FEATURES_PROMPT = "Auto-features: Type > filename to read, >! filename to write, code runs automatically."
def inject_theme_css(theme: str):
    is_dark = theme == "Dark"
    user_bg = "#1a1a2e" if is_dark else "#eef4ff"
    assistant_bg = "#16213e" if is_dark else "#f4f7fb"
    text_color = "#ffffff" if is_dark else "#1f2937"
    stats_bg = "#0f3460" if is_dark else "#dbeafe"
    stats_text = "#ffffff" if is_dark else "#0f172a"
    st.markdown(
        f"""
        <style>
            .user-message {{
                background-color: {user_bg};
                color: {text_color};
                padding: 10px 15px;
                border-radius: 10px;
                margin: 5px 0;
            }}
            .assistant-message {{
                background-color: {assistant_bg};
                color: {text_color};
                padding: 10px 15px;
                border-radius: 10px;
                margin: 5px 0;
            }}
            .stats-box {{
                color: {stats_text};
                background-color: {stats_bg};
                padding: 15px;
                border-radius: 10px;
                margin: 10px 0;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )
def icon(emoji: str):
    """Shows an emoji as a Notion-style page icon."""
    st.write(
        f'<span style="font-size: 78px; line-height: 1">{emoji}</span>',
        unsafe_allow_html=True,
    )
persisted_state = load_persistent_state()
for key, value in persisted_state.items():
    if key not in st.session_state:
        st.session_state[key] = value

ensure_daily_usage_state()
ensure_ux_state()

if st.session_state.get("selected_model") not in MODELS:
    st.session_state.selected_model = DEFAULT_MODEL
    save_persistent_state()

if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = "Dark"

inject_theme_css(st.session_state.theme_mode)

st.subheader("Vonnerco GPT", divider="rainbow", anchor=False)
st.caption("Persistent chats, uploads, and model controls optimized for desktop and iPhone.")

with st.container():
    action_col1, action_col2, action_col3, action_col4 = st.columns([1, 1, 1, 1])
    with action_col1:
        if st.button("New Chat", use_container_width=True):
            reset_chat_state(clear_name=True)
            st.rerun()
    with action_col2:
        if st.button("Clear Chat", use_container_width=True):
            reset_chat_state(clear_name=False)
            st.rerun()
    with action_col3:
        if st.button("Theme", use_container_width=True):
            st.session_state.theme_mode = "Light" if st.session_state.theme_mode == "Dark" else "Dark"
            st.rerun()
    with action_col4:
        st.markdown("[Latest](#latest-message)", unsafe_allow_html=True)
    action_col5, action_col6 = st.columns([1, 1])
    with action_col5:
        if st.button("Clear System Messages", use_container_width=True):
            st.session_state.messages = [m for m in st.session_state.messages if m.get("role") != "system"]
            if not st.session_state.messages:
                st.session_state.messages = [{"role": "system", "content": AUTO_FEATURES_PROMPT}]
            save_persistent_state()
            st.rerun()
    with action_col6:
        st.toggle("Safe mode", key="safe_mode", help="Disables automatic code execution and file writes.")
    with st.container():
        st.markdown(
            f"<div class='stats-box'><strong>Session:</strong> "
            f"{st.session_state.request_count} req | "
            f"{st.session_state.total_tokens_used} tokens total | "
            f"{st.session_state.current_tokens} current | "
            f"{get_tokens_left_today(st.session_state.selected_model)} left today</div>",
            unsafe_allow_html=True,
        )

with st.expander("Session details", expanded=False):
    stats_left, stats_right = st.columns(2)
    with stats_left:
        st.metric("Requests", st.session_state.request_count)
        st.metric("Prompt Tokens", st.session_state.total_prompt_tokens)
        st.metric("Completion Tokens", st.session_state.total_completion_tokens)
    with stats_right:
        st.metric("Total Tokens", st.session_state.total_tokens_used)
        st.metric("Tokens Left Today", get_tokens_left_today(st.session_state.selected_model))
        st.metric("Current Msg", st.session_state.current_tokens)

with st.sidebar:
    st.header("Uploads")
    st.caption("Drag and drop files here, or tap to browse.")
    st.caption("Images, docs, spreadsheets, and code files are supported.")
    uploaded_files = st.file_uploader(
        "Upload files",
        accept_multiple_files=True,
        type=[
            "docx", "pdf", "csv", "txt", "xlsx", "xls",
            "py", "sql", "java", "html", "htm", "md", "json",
            "xml", "yaml", "yml", "css", "js", "ts", "sh",
            "png", "jpg", "jpeg", "gif", "webp", "bmp", "tiff",
        ],
        label_visibility="collapsed",
        key="sidebar_file_uploader",
    )
    if uploaded_files:
        saved_uploads = st.session_state.setdefault("uploaded_files", [])
        for uploaded_file in uploaded_files:
            signature = file_record_signature(uploaded_file)
            if already_uploaded(signature):
                continue
            record = save_uploaded_file(uploaded_file)
            saved_uploads.append(record)
            remember_uploaded(signature)
            st.success(f"Saved: {uploaded_file.name}")
        save_persistent_state()

    if st.session_state.get("uploaded_files"):
        upload_filter = st.text_input("Search files", placeholder="Filter by name", key="upload_search")
        if st.button("Clear All Uploads", use_container_width=True):
            clear_all_uploaded_files()
            st.rerun()
        st.caption(f"{len(st.session_state.uploaded_files)} files saved")

        filtered_files = list(st.session_state.uploaded_files)
        if upload_filter.strip():
            query = upload_filter.strip().lower()
            filtered_files = [
                item for item in filtered_files
                if query in (item.get("label") or "").lower()
                or query in (item.get("original_name") or "").lower()
            ]

        recent_files = filtered_files[-3:][::-1]
        if recent_files:
            with st.expander("Recent uploads", expanded=True):
                for file_record in recent_files:
                    file_id = file_record.get("id")
                    name = file_record.get("label") or file_record.get("original_name") or "Untitled"
                    path = file_record.get("path")
                    if path and os.path.exists(path):
                        st.caption(name)
                        recent_col1, recent_col2 = st.columns([1, 1])
                        with recent_col1:
                            if st.button("Preview", key=f"recent_preview_btn_{file_id}", use_container_width=True):
                                st.session_state[f"show_preview_{file_id}"] = True
                        with recent_col2:
                            if st.button("Insert", key=f"recent_insert_btn_{file_id}", use_container_width=True):
                                insert_uploaded_file_into_chat(file_id)
                                st.rerun()
                        if st.session_state.get(f"show_preview_{file_id}"):
                            render_uploaded_file(path, file_record.get("original_name") or name, file_id)

        with st.expander("All uploads", expanded=False):
            grouped_files = {}
            for file_record in filtered_files:
                ext = Path((file_record.get("original_name") or file_record.get("label") or "")).suffix.lower()
                group_name = upload_group_for_extension(ext)
                grouped_files.setdefault(group_name, []).append(file_record)

            for group_name in ["Images", "Documents", "Spreadsheets", "Text", "Code", "Other"]:
                items = grouped_files.get(group_name, [])
                if not items:
                    continue
                with st.expander(f"{group_name} ({len(items)})", expanded=(group_name == "Images")):
                    for file_record in items:
                        file_id = file_record.get("id")
                        name = file_record.get("label") or file_record.get("original_name") or "Untitled"
                        path = file_record.get("path")
                        if path and os.path.exists(path):
                            st.caption(name)
                            st.caption(
                                f"{format_file_size(file_record.get('size_bytes'))} | "
                                f"saved {file_record.get('saved_at', 'unknown')}"
                            )
                            file_col1, file_col2, file_col3 = st.columns([4, 1, 1])
                            with file_col1:
                                if st.button("Preview", key=f"preview_btn_{file_id}", use_container_width=True):
                                    st.session_state[f"show_preview_{file_id}"] = True
                            with file_col2:
                                if st.button("Insert", key=f"insert_btn_{file_id}", use_container_width=True):
                                    insert_uploaded_file_into_chat(file_id)
                                    st.rerun()
                            with file_col3:
                                if st.button("Delete", key=f"delete_btn_{file_id}", use_container_width=True):
                                    delete_uploaded_file(file_id)
                                    st.rerun()
                            if st.session_state.get(f"show_preview_{file_id}"):
                                render_uploaded_file(path, file_record.get("original_name") or name, file_id)
                        else:
                            st.warning(f"Missing file on disk: {name}")

# Past Chats Dropdown
chat_col1, chat_col2, chat_col3, chat_col4 = st.columns([2, 1, 1, 1])
with chat_col1:
    chat_options = ["New Chat"] + list(st.session_state.saved_chats.keys())
    selected_chat = st.selectbox("Past Chats", options=chat_options, index=chat_options.index(st.session_state.chat_name) if st.session_state.chat_name in chat_options else 0)
    if selected_chat != st.session_state.chat_name:
        if selected_chat == "New Chat":
            st.session_state.messages = [{"role": "system", "content": AUTO_FEATURES_PROMPT}]
        else:
            st.session_state.messages = st.session_state.saved_chats[selected_chat].copy()
        st.session_state.chat_name = selected_chat
        save_persistent_state()
        st.rerun()
with chat_col2:
    st.text("")
    st.text("")
    chat_name_input = st.text_input("Save as", value=st.session_state.chat_name if st.session_state.chat_name != "New Chat" else "")
with chat_col3:
    st.text("")
    st.text("")
    if st.button("Save Chat", use_container_width=True) and chat_name_input.strip():
        st.session_state.saved_chats[chat_name_input.strip()] = st.session_state.messages.copy()
        st.session_state.chat_name = chat_name_input.strip()
        save_persistent_state()
        st.success(f"Chat saved: {chat_name_input}")
        st.rerun()
with chat_col4:
    st.text("")
    st.text("")
    chat_export = json.dumps(st.session_state.messages, ensure_ascii=False, indent=2)
    st.download_button(
        "Download Chat",
        data=chat_export,
        file_name=f"{st.session_state.chat_name or 'chat'}.json",
        mime="application/json",
        use_container_width=True,
    )

with st.expander("Model settings", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        model_option = st.selectbox(
            "Choose a model:",
            options=list(MODELS.keys()),
            format_func=lambda x: f"{x} ({MODELS[x]['description'][:40]})",
            index=list(MODELS.keys()).index(DEFAULT_MODEL) if DEFAULT_MODEL in MODELS else 0,
        )
    with col2:
        model_info = MODELS[model_option]
        max_tokens_range = model_info["context_window"]
        max_tokens = st.slider(
            "Max Tokens:",
            min_value=512,
            max_value=max_tokens_range,
            value=min(4000, max_tokens_range),
            step=512,
            help=f"Adjust the maximum number of tokens. Max for selected model: {max_tokens_range}"
        )

    st.caption(f"Active model: {model_option}")
    st.caption(f"{model_status_emoji(set_model_health(model_option))} Model health: {set_model_health(model_option).title()}")
    if st.button("Refresh model selection", use_container_width=True):
        st.session_state.selected_model = DEFAULT_MODEL
        st.session_state.total_prompt_tokens = 0
        st.session_state.total_completion_tokens = 0
        st.session_state.total_tokens_used = 0
        st.session_state.request_count = 0
        st.session_state.current_tokens = 0
        st.session_state.messages = [{"role": "system", "content": AUTO_FEATURES_PROMPT}]
        save_persistent_state()
        st.rerun()

with st.expander("Recent prompts", expanded=False):
    if st.session_state.get("recent_prompts"):
        for i, prompt_item in enumerate(st.session_state.recent_prompts[:5]):
            prompt_col1, prompt_col2 = st.columns([5, 1])
            with prompt_col1:
                st.caption(prompt_item)
            with prompt_col2:
                if st.button("Load", key=f"load_prompt_{i}", use_container_width=True):
                    st.session_state.queued_prompt = prompt_item
                    st.rerun()
    else:
        st.caption("No recent prompts yet.")

# Detect model change and clear chat history if model has changed
if st.session_state.selected_model != model_option:
    reset_chat_state(clear_name=False)
    st.session_state.selected_model = model_option
    st.session_state.total_prompt_tokens = 0
    st.session_state.total_completion_tokens = 0
    st.session_state.total_tokens_used = 0
    st.session_state.request_count = 0
    st.session_state.current_tokens = 0
    save_persistent_state()
# Display chat messages from history on app rerun
for message in st.session_state.messages:
    if message["role"] == "system":
        continue
    avatar = '🤖' if message["role"] == "assistant" else '👨‍💻'
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])

st.markdown('<div id="latest-message"></div>', unsafe_allow_html=True)

# MCP Server Connection
if MCP_AVAILABLE:
    st.markdown("---")
    with st.expander("MCP Server Connection", expanded=False):
        mcp_col1, mcp_col2 = st.columns([3, 1])
        with mcp_col1:
            mcp_command = st.text_input("MCP Server Command", value="npx", help="Command to run MCP server (e.g., npx, python, node)")
            mcp_args = st.text_input("Server Args (optional)", value="-y @anthropic/mcp-server-anthropic", help="Arguments for the server command")
        with mcp_col2:
            st.text("")
            if st.button("Connect", use_container_width=True):
                args_list = mcp_args.split() if mcp_args.strip() else None
                import asyncio
                result = asyncio.run(connect_mcp_server(mcp_command, args_list))
                st.session_state.mcp_status = result
                st.rerun()
        if "mcp_status" in st.session_state:
            st.info(st.session_state.mcp_status)
        if mcp_session:
            tools = asyncio.run(list_mcp_tools())
            if tools:
                st.success(f"Connected! {len(tools)} tools available")
# Stats display
st.markdown("---")
col_stats1, col_stats2, col_stats3, col_stats4, col_stats5 = st.columns(5)
with col_stats1:
    st.metric("Requests", st.session_state.request_count)
with col_stats2:
    st.metric("Prompt Tokens", st.session_state.total_prompt_tokens)
with col_stats3:
    st.metric("Completion Tokens", st.session_state.total_completion_tokens)
with col_stats4:
    st.metric("Total Tokens", st.session_state.total_tokens_used)
    st.metric("Current Msg", st.session_state.current_tokens)
def trim_messages(messages: list, max_tokens: int = 6000) -> list:
    """Trim messages to stay within token limit, keeping system prompt."""
    if not messages:
        return messages
    
    system_msg = messages[0] if messages[0]["role"] == "system" else None
    chat_msgs = messages[1:] if system_msg else messages
    
    system_tokens = estimate_tokens(system_msg["content"]) if system_msg else 0
    target_tokens = max_tokens - system_tokens - 500  # Buffer for response
    
    trimmed = chat_msgs
    while estimate_tokens(str(trimmed)) > target_tokens and len(trimmed) > 4:
        trimmed = trimmed[2:]  # Remove oldest user+assistant pair
    
    return [system_msg] + trimmed if system_msg else trimmed
def estimate_tokens(text: str) -> int:
    if isinstance(text, list):
        text = " ".join(str(item) for item in text)
    return len(text) // 4
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
queued_prompt = st.session_state.pop("queued_prompt", None)
prompt = queued_prompt or st.chat_input("Enter your prompt here...")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    track_prompt(prompt)
    save_persistent_state()
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
    if st.session_state.safe_mode:
        auto_write = False
        exec_code = False
        code_to_run = None
    elif code_block_match or is_bare_code or any(kw in cmd for kw in exec_keywords):
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
                save_persistent_state()
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
                "messages": [{"role": m["role"], "content": m["content"]} for m in trim_messages(st.session_state.messages)],
                "temperature": 0.2,
                "max_completion_tokens": 4000,
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
            response_text = full_response if isinstance(full_response, str) else "\n".join(str(item) for item in full_response)
            if isinstance(full_response, str):
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            else:
                st.session_state.messages.append({"role": "assistant", "content": response_text})
            st.session_state.last_assistant_response = response_text
            
            # Update token counts
            user_tokens = estimate_tokens(prompt)
            response_tokens = estimate_tokens(response_text)
            st.session_state.current_tokens = user_tokens + response_tokens
            st.session_state.total_prompt_tokens += user_tokens
            st.session_state.total_completion_tokens += response_tokens
            st.session_state.total_tokens_used += st.session_state.current_tokens
            st.session_state.request_count += 1
            # Handle auto actions from AI response
            read_content, write_file, write_msg = handle_auto_actions(full_response)
            if read_content:
                st.session_state.messages.append({"role": "system", "content": f"[File contents]:\n{read_content}"})
            if write_file:
                st.session_state.messages.append({"role": "system", "content": f"[{write_msg}]"})
            save_persistent_state()
            st.rerun()
        except Exception as e:
            if hasattr(e, "response") and getattr(e.response, "status_code", None) == 404:
                st.warning("The selected model is unavailable right now. Falling back to the default supported model.")
                st.session_state.selected_model = DEFAULT_MODEL
                st.session_state.total_prompt_tokens = 0
                st.session_state.total_completion_tokens = 0
                st.session_state.total_tokens_used = 0
                st.session_state.request_count = 0
                st.session_state.current_tokens = 0
                save_persistent_state()
                st.rerun()
            st.error(e, icon="🚨")

if st.session_state.get("last_assistant_response"):
    with st.expander("Last assistant response", expanded=False):
        st.text_area("Response", st.session_state.last_assistant_response, height=200)
        st.download_button(
            "Download response",
            data=st.session_state.last_assistant_response,
            file_name="last_assistant_response.txt",
            mime="text/plain",
            use_container_width=True,
        )

st.markdown("---")
footer_cols = st.columns(4)
with footer_cols[0]:
    st.caption(f"Model: {st.session_state.selected_model}")
with footer_cols[1]:
    st.caption(f"Daily left: {get_tokens_left_today(st.session_state.selected_model)}")
with footer_cols[2]:
    st.caption(f"Key loaded: {'yes' if groq_api_key else 'no'}")
with footer_cols[3]:
    st.caption(f"Safe mode: {'on' if st.session_state.safe_mode else 'off'}")
