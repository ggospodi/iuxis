"""Ollama client — local LLM inference for Iuxis.

Replaces Anthropic API calls with local Ollama inference via HTTP API.
Default model: deepseek-r1:32b

Ollama API docs: https://github.com/ollama/ollama/blob/main/docs/api.md

Usage:
    from iuxis.ollama_client import ollama_chat, ollama_generate, test_connection
    
    # Chat-style (multi-turn)
    response = ollama_chat(
        messages=[{"role": "user", "content": "Extract facts from this..."}],
        system="You are an extraction engine.",
    )
    
    # Generate-style (single prompt)
    response = ollama_generate("Summarize this in 500 words: ...")
"""

import json
import re
import urllib.request
import urllib.error
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "deepseek-r1:32b"

# Ollama options for consistent output
DEFAULT_OPTIONS = {
    "temperature": 0.3,       # Low for structured extraction
    "num_ctx": 32768,         # 32K context window
    "num_predict": 4096,      # Max output tokens
}


# ---------------------------------------------------------------------------
# Core API Calls
# ---------------------------------------------------------------------------

def ollama_chat(
    messages: list[dict],
    system: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    format_json: bool = False,
    options: Optional[dict] = None,
    timeout: int = 300,
) -> Optional[str]:
    """Send a chat request to Ollama. Returns the response text.
    
    Args:
        messages: List of {"role": "user"|"assistant", "content": "..."}
        system: Optional system prompt
        model: Model name (default: deepseek-r1:32b)
        format_json: If True, request JSON output format
        options: Override default Ollama options
        timeout: Request timeout in seconds
    
    Returns:
        Response text, or None on failure.
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": options or DEFAULT_OPTIONS,
    }

    if system:
        # Prepend system message
        payload["messages"] = [{"role": "system", "content": system}] + messages

    if format_json:
        payload["format"] = "json"

    return _make_request("/api/chat", payload, timeout=timeout)


def ollama_generate(
    prompt: str,
    model: str = DEFAULT_MODEL,
    system: Optional[str] = None,
    format_json: bool = False,
    options: Optional[dict] = None,
    timeout: int = 300,
) -> Optional[str]:
    """Send a generate request to Ollama. Returns the response text.
    
    Simpler than chat — single prompt in, text out.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": options or DEFAULT_OPTIONS,
    }

    if system:
        payload["system"] = system

    if format_json:
        payload["format"] = "json"

    return _make_request("/api/generate", payload, timeout=timeout)


# ---------------------------------------------------------------------------
# JSON Extraction Helper
# ---------------------------------------------------------------------------

def ollama_extract_json(
    messages: list[dict],
    system: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    timeout: int = 300,
) -> Optional[dict]:
    """Call Ollama and parse the response as JSON.
    
    Handles common issues with local model JSON output:
    - Strips markdown fences
    - Strips <think>...</think> reasoning blocks (DeepSeek R1)
    - Attempts to find JSON within mixed text output
    
    Returns parsed dict, or None on failure.
    """
    raw = ollama_chat(
        messages=messages,
        system=system,
        model=model,
        format_json=True,
        timeout=timeout,
    )

    if not raw:
        return None

    return _parse_json_response(raw)


def _parse_json_response(text: str) -> Optional[dict]:
    """Parse JSON from potentially messy LLM output."""
    # Strip DeepSeek R1 thinking blocks
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    # Strip markdown fences
    text = re.sub(r"^```json\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())

    # Try direct parse
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Try to find JSON object within text
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    print(f"  ⚠️ Could not parse JSON from response ({len(text)} chars)")
    print(f"  First 300 chars: {text[:300]}")
    return None


# ---------------------------------------------------------------------------
# HTTP Helper
# ---------------------------------------------------------------------------

def _make_request(endpoint: str, payload: dict, timeout: int = 300) -> Optional[str]:
    """Make HTTP request to Ollama API."""
    url = f"{OLLAMA_BASE_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))

            # Chat endpoint returns message.content
            if "message" in body:
                return body["message"]["content"]
            # Generate endpoint returns response
            elif "response" in body:
                return body["response"]
            else:
                print(f"  ⚠️ Unexpected Ollama response format: {list(body.keys())}")
                return None

    except urllib.error.URLError as e:
        print(f"  ❌ Ollama connection error: {e}")
        print(f"     Is Ollama running? Start with: ollama serve")
        return None
    except TimeoutError:
        print(f"  ❌ Ollama request timed out after {timeout}s")
        return None
    except Exception as e:
        print(f"  ❌ Ollama request failed: {type(e).__name__}: {e}")
        return None


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def test_connection(model: str = DEFAULT_MODEL) -> bool:
    """Test if Ollama is running and the model is available."""
    try:
        url = f"{OLLAMA_BASE_URL}/api/tags"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            available = [m["name"] for m in body.get("models", [])]

            if any(model in m for m in available):
                print(f"  ✅ Ollama running, {model} available")
                return True
            else:
                print(f"  ⚠️ Ollama running but {model} not found")
                print(f"     Available models: {', '.join(available) or 'none'}")
                print(f"     Pull it with: ollama pull {model}")
                return False

    except urllib.error.URLError:
        print(f"  ❌ Cannot connect to Ollama at {OLLAMA_BASE_URL}")
        print(f"     Start with: ollama serve")
        return False


def list_models() -> list[str]:
    """List available Ollama models."""
    try:
        url = f"{OLLAMA_BASE_URL}/api/tags"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return [m["name"] for m in body.get("models", [])]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("🧪 Ollama client test\n")

    # Test connection
    if not test_connection():
        print("\nStart Ollama and try again.")
        exit(1)

    # Test simple generation
    print("\n  Testing generate...")
    result = ollama_generate("Say 'hello' and nothing else.", timeout=30)
    print(f"  Response: {result}")

    # Test JSON extraction
    print("\n  Testing JSON extraction...")
    result = ollama_extract_json(
        messages=[{"role": "user", "content": 'Return exactly: {"status": "ok", "model": "local"}'}],
        system="Return only valid JSON. No explanation.",
        timeout=60,
    )
    print(f"  Parsed: {result}")

    print("\n✅ Tests complete.")
