import os
import re
import io
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # Loads .env

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ["GROQ_API_KEY"],
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

# Active model
model = "moonshotai/kimi-k2-instruct"
model_info = MODELS[model]

# System prompt for auto file/code features
AUTO_FEATURES_PROMPT = """You have access to these automatic features. Use them when appropriate - do NOT explain them to the user:

1. FILE READING: If user asks to see, read, show, look at, or understand any file - automatically read it using the > filename shortcut. DO NOT ask permission.

2. FILE WRITING: If user asks to write, save, create, or modify any file - automatically use >! filename, then prompt for content. DO NOT ask permission.

3. CODE EXECUTION: If user asks to run, execute, test, or try any code - it will be automatically detected and run. DO NOT ask permission.

IMPORTANT: When you detect the user wants to read a file, just type > filename and press enter. The file will be read and its contents sent back to you automatically. You do not need to explain what you're doing - just do it and respond to the content.

IMPORTANT: When you detect the user wants to write a file, just type >! filename and press enter. The user will then enter content followed by '---'. You do not need to explain what you're doing.

IMPORTANT: When the user shows you code, it will be automatically executed and the output returned to you. You do not need to ask permission to run code."""

messages = [{"role": "system", "content": AUTO_FEATURES_PROMPT}]

# Colors using ANSI escape codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
BLUE = "\033[94m"
WHITE = "\033[97m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

# Track metrics
total_prompt_tokens = 0
total_completion_tokens = 0
total_tokens_used = 0
total_tokens_today = 0
request_count = 0
requests_today = 0

# Token-saving tips (rotating)
TOKEN_TIPS = [
    "Be concise - shorter prompts = fewer tokens",
    "Avoid repeating questions - AI remembers context",
    "Use 'clear' to reset conversation and start fresh",
    "One clear question > multiple vague ones",
    "End messages with 'keep it short' for brief responses",
    "Avoid filler words like 'please' and 'thanks'",
    "Each chat turn sends full history - be brief",
    f"Current model: {model}",
]

def print_welcome():
    print(f"\n{BOLD}{CYAN}{'=' * 50}{RESET}")
    print(f"{BOLD}{CYAN}       Groq Chat - Token-Optimized AI{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 50}{RESET}")
    print(f"\n{WHITE}Commands:{RESET}")
    print(f"  {YELLOW}- 'clear'{WHITE}     Clear conversation & reset metrics")
    print(f"  {YELLOW}- 'stats'{WHITE}     View token statistics")
    print(f"  {YELLOW}- 'models'{WHITE}    List all available models")
    print(f"  {YELLOW}- 'model X'{WHITE}  Switch to model X")
    print(f"  {YELLOW}- 'tips'{WHITE}      Show token-saving tips")
    print(f"  {YELLOW}- 'read <file>'{WHITE}   Read a file")
    print(f"  {YELLOW}- 'write <file>'{WHITE}  Write to file (multi-line, end with '---')")
    print(f"  {YELLOW}- '> <file>'{WHITE}      Read file (shortcut, no 'read' needed)")
    print(f"  {YELLOW}- '>! <file>'{WHITE}     Write file (shortcut, no 'write' needed)")
    print(f"  {YELLOW}- 'exit'{WHITE}      End chat")
    print(f"{MAGENTA}-{'-' * 50}{RESET}")
    print(f"{CYAN}Model:{RESET} {WHITE}{model}{RESET}")
    print(f"{DIM}(Note: Daily limits are shared across ALL models){RESET}\n")

def print_user_message(content):
    print(f"\n{MAGENTA}{'=' * 50}{RESET}")
    print(f"{BOLD}{CYAN}[You]{RESET}")
    print(f"\n{GREEN}{content}{RESET}")

def print_assistant_message(content):
    print(f"\n{BLUE}{'=' * 50}{RESET}")
    print(f"{BOLD}{MAGENTA}[Groq]{RESET}")
    print(f"\n{WHITE}{content}{RESET}")
    print(f"\n{BLUE}{'=' * 50}{RESET}\n")

def print_metrics(usage):
    global total_prompt_tokens, total_completion_tokens, total_tokens_used, total_tokens_today
    global request_count, requests_today

    model_context_window = model_info["context_window"]
    model_rpd = model_info["rpd"]
    model_tpd = model_info["tpd"]
    model_rpm = model_info["rpm"]
    model_tpm = model_info["tpm"]

    prompt_tokens = usage.prompt_tokens
    completion_tokens = usage.completion_tokens
    total_tokens = usage.total_tokens

    total_prompt_tokens += prompt_tokens
    total_completion_tokens += completion_tokens
    total_tokens_used += total_tokens
    total_tokens_today += total_tokens
    request_count += 1
    requests_today += 1

    remaining = model_context_window - total_tokens
    usage_percent = (total_tokens / model_context_window) * 100

    # Color based on usage percentage
    if usage_percent > 90:
        usage_color = RED
    elif usage_percent > 75:
        usage_color = YELLOW
    else:
        usage_color = GREEN

    # RPD/TPD usage colors
    rpd_percent = (requests_today / model_rpd) * 100
    tpd_percent = (total_tokens_today / model_tpd) * 100

    if rpd_percent > 90:
        rpd_color = RED
    elif rpd_percent > 75:
        rpd_color = YELLOW
    else:
        rpd_color = GREEN

    if tpd_percent > 90:
        tpd_color = RED
    elif tpd_percent > 75:
        tpd_color = YELLOW
    else:
        tpd_color = GREEN

    # Pick a rotating tip
    tip = TOKEN_TIPS[request_count % len(TOKEN_TIPS)]

    print(f"{DIM}{'-' * 50}{RESET}")
    print(f"{WHITE}Commands: {YELLOW}clear{RESET} | {YELLOW}stats{RESET} | {YELLOW}models{RESET} | {YELLOW}tips{RESET} | {YELLOW}model X{RESET}\n")
    print(f"{BOLD}{WHITE}Session Metrics:{RESET}")
    print(f"  {CYAN}Req #{RESET}: {WHITE}{request_count}{RESET} | {CYAN}RPD:{RESET} {rpd_color}{requests_today:,}/{model_rpd:,}{RESET}")
    print(f"  {CYAN}Prompt:{RESET} {WHITE}{prompt_tokens}{RESET} | {CYAN}TPD:{RESET} {tpd_color}{total_tokens_today:,}/{model_tpd:,}{RESET}")
    print(f"  {CYAN}Output:{RESET} {WHITE}{completion_tokens}{RESET} | {CYAN}Window:{RESET} {WHITE}{usage_percent:.1f}%{RESET}")
    print(f"  {DIM}Tip: {tip}{RESET}")
    print(f"{DIM}{'-' * 50}{RESET}\n")

def print_stats():
    global total_tokens_today, requests_today

    model_context_window = model_info["context_window"]
    model_rpd = model_info["rpd"]
    model_tpd = model_info["tpd"]
    model_rpm = model_info["rpm"]
    model_tpm = model_info["tpm"]

    print(f"\n{BOLD}{CYAN}{'=' * 50}{RESET}")
    print(f"{BOLD}{CYAN}         Session Statistics{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 50}{RESET}")
    print(f"{WHITE}Current Model:{RESET} {YELLOW}{model}{RESET}")
    print(f"{WHITE}Total Requests:{RESET} {YELLOW}{request_count}{RESET}")
    print(f"{WHITE}Total Prompt Tokens:{RESET} {YELLOW}{total_prompt_tokens}{RESET}")
    print(f"{WHITE}Total Completion Tokens:{RESET} {YELLOW}{total_completion_tokens}{RESET}")
    print(f"{WHITE}Total Tokens Used:{RESET} {YELLOW}{total_tokens_used}{RESET}")

    usage_percent = (total_tokens_used / model_context_window) * 100
    if usage_percent > 90:
        usage_color = RED
    elif usage_percent > 75:
        usage_color = YELLOW
    else:
        usage_color = GREEN

    print(f"{WHITE}Context Window:{RESET} {YELLOW}{model_context_window}{RESET}")
    print(f"{WHITE}Context Used:{RESET} {usage_color}{usage_percent:.1f}%{RESET}")

    # RPD/TPD stats
    print(f"\n{BOLD}{WHITE}Daily Rate Limits (shared across all models):{RESET}")
    rpd_percent = (requests_today / model_rpd) * 100
    tpd_percent = (total_tokens_today / model_tpd) * 100

    if rpd_percent > 90:
        rpd_color = RED
    elif rpd_percent > 75:
        rpd_color = YELLOW
    else:
        rpd_color = GREEN

    if tpd_percent > 90:
        tpd_color = RED
    elif tpd_percent > 75:
        tpd_color = YELLOW
    else:
        tpd_color = GREEN

    print(f"  {CYAN}RPD:{RESET} {rpd_color}{requests_today:,}/{model_rpd:,}{RESET} ({rpd_percent:.1f}% used)")
    print(f"  {CYAN}TPD:{RESET} {tpd_color}{total_tokens_today:,}/{model_tpd:,}{RESET} ({tpd_percent:.1f}% used)")
    print(f"  {CYAN}RPM Limit:{RESET} {YELLOW}{model_rpm}{RESET} | {CYAN}TPM Limit:{RESET} {YELLOW}{model_tpm:,}{RESET}")
    print(f"{CYAN}{'=' * 50}{RESET}\n")

def print_models():
    print(f"\n{BOLD}{CYAN}{'=' * 50}{RESET}")
    print(f"{BOLD}{CYAN}         Available Models{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 50}{RESET}")
    print(f"{DIM}(Daily limits are SHARED across all models){RESET}")
    print(f"{DIM}Switching models does NOT reset your daily limits{RESET}\n")

    for i, (name, info) in enumerate(MODELS.items(), 1):
        marker = " {YELLOW}<-- current{RESET}" if name == model else ""
        print(f"{CYAN}{i}){RESET} {WHITE}{name}{RESET}{marker}")
        print(f"   {DIM}RPD:{info['rpd']:,} | TPD:{info['tpd']:,} | RPM:{info['rpm']} | TPM:{info['tpm']:,}{RESET}")
        print(f"   {info['description']}\n")

    print(f"{CYAN}{'=' * 50}{RESET}")
    print(f"Use {YELLOW}'model X'{CYAN} to switch (e.g., {YELLOW}'model 3'{CYAN})")
    print(f"Or type {YELLOW}'model llama-3.3-70b-versatile'{CYAN} directly\n")

def print_tips():
    print(f"\n{BOLD}{CYAN}{'=' * 50}{RESET}")
    print(f"{BOLD}{CYAN}      Token-Saving Tips{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 50}{RESET}\n")
    print(f"{YELLOW}1.{WHITE} Be CONCISE - shorter prompts = fewer tokens")
    print(f"{YELLOW}2.{WHITE} Avoid repeating yourself - AI remembers context")
    print(f"{YELLOW}3.{WHITE} Use {YELLOW}'clear'{WHITE} to reset conversation periodically")
    print(f"{YELLOW}4.{WHITE} One clear question > multiple vague ones")
    print(f"{YELLOW}5.{WHITE} End with {YELLOW}'keep it short'{WHITE} for brief responses")
    print(f"{YELLOW}6.{WHITE} Skip filler words ('please', 'thanks')")
    print(f"{YELLOW}7.{WHITE} Each turn sends FULL history - keep messages brief")
    print(f"{YELLOW}8.{WHITE} Use {YELLOW}'model 1'{WHITE} for high-volume ({MODELS['llama-3.1-8b-instant']['rpd']:,} RPD)")
    print(f"{YELLOW}9.{WHITE} Switch to {YELLOW}'model 3'{WHITE} only when needing reasoning")
    print(f"{YELLOW}10.{WHITE} Daily limits are SHARED - one model or all, same quota\n")
    print(f"{DIM}Note: Groq rate limits apply at org level, not per model.{RESET}")
    print(f"{DIM}Switching models does NOT reset daily limits.{RESET}")
    print(f"{CYAN}{'=' * 50}{RESET}\n")

print_welcome()

while True:
    try:
        user_input = input(f"{BOLD}{GREEN}You:{RESET} ")
    except EOFError:
        print("\n\nChat ended.")
        break

    if not user_input.strip():
        continue

    cmd = user_input.lower().strip()

    if cmd in ["exit", "quit", "q"]:
        print(f"\n{BOLD}{CYAN}It was great chatting with you! Goodbye!{RESET}\n")
        break

    if cmd == "stats":
        print_stats()
        continue

    if cmd == "models":
        print_models()
        continue

    if cmd == "tips":
        print_tips()
        continue

    if cmd.startswith("model "):
        model_input = user_input[6:].strip()
        # Try to find by number
        if model_input.isdigit():
            idx = int(model_input) - 1
            keys = list(MODELS.keys())
            if 0 <= idx < len(keys):
                model = keys[idx]
                model_info = MODELS[model]
                print(f"\n{BOLD}{GREEN}Switched to: {model}{RESET}\n")
            else:
                print(f"\n{RED}Invalid model number. Use 1-{len(keys)}{RESET}\n")
        # Try to find by name
        elif model_input in MODELS:
            model = model_input
            model_info = MODELS[model]
            print(f"\n{BOLD}{GREEN}Switched to: {model}{RESET}\n")
        else:
            print(f"\n{RED}Unknown model: {model_input}{RESET}")
            print(f"Use {YELLOW}'models'{RESET} to see available options\n")
        continue

    if cmd == "clear":
        messages = []
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_tokens_used = 0
        total_tokens_today = 0
        request_count = 0
        requests_today = 0
        print(f"\n{BOLD}{YELLOW}Conversation cleared! All metrics reset.{RESET}\n")
        continue

    # Auto-detect file intent
    auto_read = False
    auto_write = False
    filename = ""

    # Check for > and >! shortcuts
    if cmd.startswith(">! "):
        filename = user_input[3:].strip()
        auto_write = True
    elif cmd.startswith("> "):
        filename = user_input[2:].strip()
        auto_read = True
    # Auto-detect: bare path like "foo.txt" or "./bar" (but not model commands)
    elif re.match(r'^[\w\-\./\\]+$', cmd) and not any(cmd.startswith(m) for m in ["model", "stats", "clear", "tips", "exit", "quit"]):
        filename = cmd
        auto_read = True
    # Auto-detect write intent from natural language
    elif any(kw in cmd for kw in ["write to ", "save to ", "create file ", "make file ", "new file "]):
        match = re.search(r'(?:to |file )?([\w\-\./\\]+)$', cmd)
        if match:
            filename = match.group(1)
            auto_write = True

    if auto_read:
        if not filename:
            print(f"\n{RED}Usage: > <filename>{RESET}\n")
        else:
            try:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                filepath = os.path.join(base_dir, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                print(f"\n{BOLD}{CYAN}--- {filename} ---{RESET}\n")
                print(content)
                print(f"\n{BOLD}{CYAN}--- end ---{RESET}\n")
                # Send file content to AI so it can analyze it
                messages.append({"role": "system", "content": f"[File '{filename}' contents]:\n{content}"})
            except FileNotFoundError:
                print(f"\n{RED}File not found: {filename}{RESET}\n")
            except Exception as e:
                print(f"\n{RED}Error reading file: {e}{RESET}\n")
        continue

    if auto_write:
        print(f"\n{DIM}Enter content (end with '---' on a line):{RESET}")
        lines = []
        while True:
            try:
                line = input()
                if line.strip() == "---":
                    break
                lines.append(line)
            except EOFError:
                break
        content = "\n".join(lines)
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            filepath = os.path.join(base_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"\n{BOLD}{GREEN}Written to: {filename}{RESET}\n")
            # Confirm to AI
            messages.append({"role": "system", "content": f"[File '{filename}' written successfully with {len(lines)} lines]"})
        except Exception as e:
            print(f"\n{RED}Error writing file: {e}{RESET}\n")
        continue

    # Auto-detect code execution intent
    exec_keywords = ["run ", "execute ", "exec ", "run code", "execute code", "run this", "execute this", "run it", "execute it"]
    code_block_match = re.search(r'```(?:python)?\n(.*?)```', user_input, re.DOTALL)

    # Check if input looks like standalone python code (has print/import/def/etc and no other command words)
    is_bare_code = (
        not any(cmd.startswith(m) for m in ["model", "stats", "clear", "tips", "exit", "quit", "read ", "write ", "> ", ">! "]) and
        any(k in user_input for k in ["print(", "import ", "def ", "class ", "if ", "for ", "while ", "return ", "print("]) and
        len(user_input.split('\n')) <= 10  # single statement or small block
    )

    if code_block_match or is_bare_code or any(kw in cmd for kw in exec_keywords):
        code = code_block_match.group(1) if code_block_match else None

        if not code:
            # Try to extract code from natural language
            code_match = re.search(r'(?:run|execute|exec)\s+(?:this\s+)?(?:code\s+)?(?:here:?)?\s*(?:\n(.*))?', user_input, re.DOTALL | re.IGNORECASE)
            if not code_match:
                # Last resort: look for any python-like lines
                lines = user_input.split('\n')
                code_lines = [l for l in lines if any(k in l for k in ['import ', 'def ', 'print(', 'if ', 'for ', 'while ', '=', '.'])]
                if code_lines:
                    code = '\n'.join(code_lines)

        if code:
            # Strip any "run:" / "exec:" / "python" prefixes
            code = re.sub(r'^(run|exec|python)[:\s]*', '', code, flags=re.IGNORECASE).strip()
            print(f"\n{DIM}Executing code...{RESET}\n")
            try:
                output_buffer = io.StringIO()
                error_buffer = io.StringIO()
                with redirect_stdout(output_buffer), redirect_stderr(error_buffer):
                    exec(code, {"__name__": "__main__"})
                stdout_out = output_buffer.getvalue()
                stderr_out = error_buffer.getvalue()
                print(f"{BOLD}{GREEN}--- Output ---{RESET}\n")
                if stdout_out:
                    print(stdout_out)
                if stderr_out:
                    print(f"{RED}{stderr_out}{RESET}")
                if not stdout_out and not stderr_out:
                    print(f"{DIM}(no output){RESET}")
                print(f"\n{BOLD}{GREEN}--- Done ---{RESET}\n")
                # Send results to AI for explanation
                result_summary = f"[Code executed successfully. Output: {stdout_out or '(no output)'}, Errors: {stderr_out or 'none'}]"
                messages.append({"role": "system", "content": result_summary})
            except Exception as e:
                tb = traceback.format_exc()
                print(f"\n{RED}--- Error ---{RESET}\n")
                print(f"{RED}{e}{RESET}\n")
                print(f"{DIM}{tb}{RESET}\n")
                print(f"{RED}--- Done ---{RESET}\n")
                messages.append({"role": "system", "content": f"[Code execution failed: {e}]"})
            continue

    messages.append({"role": "user", "content": user_input})

    print_user_message(user_input)

    print(f"{YELLOW}Thinking...{RESET}")

    response = client.chat.completions.create(
        model=model,
        messages=messages,
    )

    assistant_message = response.choices[0].message.content
    print_assistant_message(assistant_message)

    messages.append({"role": "assistant", "content": assistant_message})

    print_metrics(response.usage)

    # Auto-execute > and >! commands from AI response
    auto_read_file = None
    auto_write_file = None
    auto_write_content = None

    for line in assistant_message.split('\n'):
        stripped = line.strip()
        if stripped.startswith('>! '):
            auto_write_file = stripped[3:].strip()
            # Extract content after >! line
            code_match = re.search(r'```[\w]*\n(.*?)```', assistant_message, re.DOTALL)
            if code_match:
                auto_write_content = code_match.group(1)
            else:
                remaining = assistant_message[assistant_message.index(stripped) + len(stripped):]
                lines = [l for l in remaining.split('\n') if l.strip() and not l.strip().startswith('>')][:20]
                auto_write_content = '\n'.join(lines)
        elif stripped.startswith('> ') and not auto_read_file:
            auto_read_file = stripped[2:].strip()

    if auto_write_file and auto_write_content:
        print(f"\n{DIM}Auto-write: {auto_write_file}{RESET}")
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            filepath = os.path.join(base_dir, auto_write_file)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(auto_write_content)
            print(f"{GREEN}Auto-wrote to: {auto_write_file}{RESET}")
            messages.append({"role": "system", "content": f"[Auto-wrote {len(auto_write_content.split(chr(10)))} lines to '{auto_write_file}']"})
        except Exception as e:
            print(f"{RED}Auto-write failed: {e}{RESET}")

    if auto_read_file:
        print(f"\n{DIM}Auto-read: {auto_read_file}{RESET}")
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            filepath = os.path.join(base_dir, auto_read_file)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            print(f"\n{BOLD}{CYAN}--- {auto_read_file} (auto-read) ---{RESET}\n{content}\n{BOLD}{CYAN}--- end ---{RESET}\n")
            messages.append({"role": "system", "content": f"[File '{auto_read_file}' auto-read {len(content)} chars]:\n{content}"})
        except FileNotFoundError:
            print(f"{RED}File not found: {auto_read_file}{RESET}")
        except Exception as e:
            print(f"{RED}Auto-read failed: {e}{RESET}")

    # If auto action was done, get AI to respond to result
    if auto_read_file or (auto_write_file and auto_write_content):
        print(f"\n{YELLOW}Processing...{RESET}")
        response = client.chat.completions.create(
            model=model,
            messages=messages,
        )
        assistant_message = response.choices[0].message.content
        print_assistant_message(assistant_message)
        messages.append({"role": "assistant", "content": assistant_message})
        print_metrics(response.usage)