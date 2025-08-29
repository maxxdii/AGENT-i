import os

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

    # Prefer new SDK interface if available
    try:
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=api_key, timeout=30.0)  # 30 second timeout
        model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Be concise."},
                {"role": "user", "content": prompt},
            ],
            temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "500")),  # Limit response length
        )
        return (resp.choices[0].message.content or "").strip()
    except ModuleNotFoundError:
        pass

    # Fallback to legacy SDK
    try:
        import openai as openai_legacy  # type: ignore
        openai_legacy.api_key = api_key
        model = model or os.getenv("OPENAI_MODEL", "gpt-4")
        resp = openai_legacy.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.2")),
        )
        return resp["choices"][0]["message"]["content"].strip()
    except ModuleNotFoundError as e:
        raise RuntimeError("OpenAI SDK not installed. Run: pip install openai") from e
