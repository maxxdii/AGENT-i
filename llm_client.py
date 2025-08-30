import os
import time
import threading

_RATE_LOCK = threading.Lock()
_LAST_CALL_TS = 0.0

def _is_rate_error(err: Exception) -> bool:
    msg = str(err or "").lower()
    return ("rate limit" in msg) or ("429" in msg) or ("rate_limit_exceeded" in msg) or ("rpd" in msg)

def _load_env_if_available():
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
    except Exception:
        # dotenv is optional; ignore if not installed
        pass


def call_llm(prompt: str, model: str | None = None) -> str:
    """Call an OpenAI chat model with a simple system+user prompt.

    Requires OPENAI_API_KEY in the environment. Supports both the new `openai` SDK
    (from openai import OpenAI) and the legacy `openai` module (ChatCompletion).
    """
    _load_env_if_available()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in environment")

    # Simple rate gate (process-local)
    min_interval = float(os.getenv("LLM_MIN_INTERVAL_SEC", "0.0"))
    if min_interval > 0:
        with _RATE_LOCK:
            global _LAST_CALL_TS
            now = time.monotonic()
            wait = (_LAST_CALL_TS + min_interval) - now
            if wait > 0:
                time.sleep(wait)
            _LAST_CALL_TS = time.monotonic()

    max_retries = int(os.getenv("LLM_MAX_RETRIES", "2"))
    base_delay = float(os.getenv("LLM_RETRY_BASE_SEC", "4.0"))

    # Prefer new SDK interface if available
    try:
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=api_key, timeout=30.0)  # 30 second timeout
        model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        messages = [
            {"role": "system", "content": (
                "You are AGENT-i, an autonomous local operator.\n"
                "- You can accomplish tasks by proposing exact Ubuntu bash commands or 'llm:' reasoning steps that are queued and then executed locally.\n"
                "- Never claim you cannot access files or code. If access is needed, propose the precise commands to do it (e.g., ls, grep, sed, python).\n"
                "- Prefer concise answers. When appropriate, add a short list of exact next-step commands."
            )},
            {"role": "user", "content": prompt},
        ]
        attempt = 0
        while True:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.2")),
                    max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "500")),
                )
                return (resp.choices[0].message.content or "").strip()
            except Exception as e:
                if _is_rate_error(e) and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
                    attempt += 1
                    continue
                raise
    except ModuleNotFoundError:
        pass

    # Fallback to legacy SDK
    try:
        import openai as openai_legacy  # type: ignore
        openai_legacy.api_key = api_key
        model = model or os.getenv("OPENAI_MODEL", "gpt-4")
        messages = [
            {"role": "system", "content": (
                "You are AGENT-i, an autonomous local operator.\n"
                "Propose exact Ubuntu bash commands or 'llm:' steps to achieve goals; do not claim inability to access local files—suggest the commands needed. Be concise."
            )},
            {"role": "user", "content": prompt},
        ]
        attempt = 0
        while True:
            try:
                resp = openai_legacy.ChatCompletion.create(
                    model=model,
                    messages=messages,
                    temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.2")),
                )
                return resp["choices"][0]["message"]["content"].strip()
            except Exception as e:
                if _is_rate_error(e) and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
                    attempt += 1
                    continue
                raise
    except ModuleNotFoundError as e:
        raise RuntimeError("OpenAI SDK not installed. Run: pip install openai") from e
