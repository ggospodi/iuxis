"""
llm_client.py — Unified local LLM client for Iuxis
Supports LM Studio (MLX, OpenAI-compatible) as primary and Ollama as fallback.

Primary:  Qwen3.5-35B-A3B via LM Studio MLX  → http://localhost:1234/v1/chat/completions
Fallback: DeepSeek R1 32B via Ollama          → http://localhost:11434/api/chat

Drop-in replacement for ollama_client.OllamaClient.
"""

import base64
import json
import logging
import re
from pathlib import Path
from typing import Optional, Union

import requests

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Unified client supporting LM Studio (MLX) and Ollama backends.

    Interface is intentionally identical to the old OllamaClient so every
    consumer file only needs its import line changed.
    """

    # ------------------------------------------------------------------ #
    #  Construction                                                        #
    # ------------------------------------------------------------------ #

    def __init__(self, config: Optional[dict] = None):
        # ---- defaults (all overridable via config.yaml llm: block) ---- #
        self.primary_backend = "ollama"
        self.primary_url   = "http://localhost:11434/api/chat"
        self.fallback_url  = "http://localhost:11434/api/chat"
        self.primary_model = "qwen2.5:32b"
        self.fallback_model = "deepseek-r1:32b"
        self.timeout       = 300   # seconds — long generations can take a while
        self.max_tokens    = 4096
        self.use_thinking  = False  # default: /no_think for speed

        # Auto-load config.yaml if no config passed
        if config is None:
            try:
                import yaml, os
                cfg_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
                with open(cfg_path) as f:
                    config = yaml.safe_load(f)
            except Exception:
                pass

        if config:
            llm_cfg = config.get("llm", config)  # support both nested and flat
            self.primary_backend = llm_cfg.get("primary_backend", self.primary_backend)
            self.primary_url    = llm_cfg.get("primary_url",    self.primary_url)
            self.fallback_url   = llm_cfg.get("fallback_url",   self.fallback_url)
            self.primary_model  = llm_cfg.get("primary_model",  self.primary_model)
            self.fallback_model = llm_cfg.get("fallback_model", self.fallback_model)
            self.timeout        = llm_cfg.get("timeout",        self.timeout)
            self.max_tokens     = llm_cfg.get("max_tokens",     self.max_tokens)
            self.use_thinking   = llm_cfg.get("use_thinking",   self.use_thinking)

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        format_json: bool = False,
        use_thinking: Optional[bool] = None,
    ) -> str:
        """
        Generate a response.  Tries LM Studio first, falls back to Ollama.

        Args:
            prompt:        User-facing prompt text.
            system_prompt: Optional system/context message.
            format_json:   Request JSON-only output (uses response_format on
                           OpenAI-compatible backends, format=json on Ollama).
            use_thinking:  Override the instance-level thinking mode for this
                           call.  None → use self.use_thinking.

        Returns:
            Stripped response string (no <think> blocks).
        """
        thinking = self.use_thinking if use_thinking is None else use_thinking

        # ---- try primary ---- #
        _use_ollama_primary = self.primary_backend == "ollama"
        try:
            if _use_ollama_primary:
                return self._call_ollama(
                    self.primary_url, self.primary_model,
                    prompt, system_prompt, format_json,
                )
            return self._call_openai_compatible(
                self.primary_url, self.primary_model,
                prompt, system_prompt, format_json, thinking,
            )
        except Exception as exc:
            logger.warning("Primary LLM failed: %s — falling back", exc)

        # ---- fallback (Ollama) ---- #
        return self._call_ollama(
            self.fallback_url, self.fallback_model,
            prompt, system_prompt, format_json,
        )

    def generate_with_vision(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
        image_media_type: str = "image/png",
        system_prompt: str = "",
        format_json: bool = False,
    ) -> str:
        """
        Generate a response that includes an image (vision/multimodal).

        Qwen3.5-35B-A3B is natively multimodal — images are sent as
        base64-encoded data URIs in the OpenAI vision format.

        Falls back to text-only Ollama if LM Studio is unavailable (Ollama's
        DeepSeek R1 has no vision capability, so the image is simply omitted).

        Args:
            prompt:           Instruction prompt for the image.
            image_path:       Path to local image file (png/jpg/webp).
            image_bytes:      Raw image bytes (alternative to image_path).
            image_media_type: MIME type, e.g. "image/png".
            system_prompt:    Optional system message.
            format_json:      Request JSON-only output.

        Returns:
            Stripped response string.
        """
        # Load image bytes
        if image_bytes is None and image_path is not None:
            image_bytes = Path(image_path).read_bytes()
            # Infer media type from extension if not specified
            ext = Path(image_path).suffix.lower()
            type_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                        ".png": "image/png",  ".webp": "image/webp",
                        ".gif": "image/gif"}
            image_media_type = type_map.get(ext, image_media_type)

        if image_bytes is None:
            logger.warning("generate_with_vision called but no image supplied — using text-only")
            return self.generate(prompt, system_prompt=system_prompt, format_json=format_json)

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:{image_media_type};base64,{b64}"

        # Build vision-capable message
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": "/no_think " + prompt},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        })

        payload: dict = {
            "model": self.primary_model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": 0.3,
        }
        if format_json:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = requests.post(self.primary_url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return self._strip_thinking(content)
        except Exception as exc:
            logger.warning("Vision call to LM Studio failed: %s — falling back to text-only Ollama", exc)
            return self._call_ollama(
                self.fallback_url, self.fallback_model,
                prompt, system_prompt, format_json,
            )

    def generate_fast(self, prompt: str, system_prompt: str = "", format_json: bool = False) -> str:
        """
        Generate with /no_think prefix — for formatting/ranking tasks.
        Fast mode disables chain-of-thought reasoning.
        """
        return self.generate(prompt, system_prompt=system_prompt, format_json=format_json, use_thinking=False)

    def generate_deep(self, prompt: str, system_prompt: str = "", format_json: bool = False) -> str:
        """
        Generate with /think prefix — for analysis/insight tasks.
        Deep mode enables chain-of-thought reasoning.
        """
        return self.generate(prompt, system_prompt=system_prompt, format_json=format_json, use_thinking=True)

    def health_check(self) -> dict:
        """
        Check which backends are currently reachable.

        Returns:
            {
                "primary":  bool,  # LM Studio reachable
                "fallback": bool,  # Ollama reachable
                "active":   str,   # "primary" | "fallback" | "none"
                "primary_model":  str,
                "fallback_model": str,
            }
        """
        status: dict = {
            "primary":  False,
            "fallback": False,
            "primary_model":  self.primary_model,
            "fallback_model": self.fallback_model,
        }

        try:
            r = requests.get("http://localhost:1234/v1/models", timeout=3)
            status["primary"] = r.status_code == 200
        except Exception:
            pass

        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=3)
            status["fallback"] = r.status_code == 200
        except Exception:
            pass

        if status["primary"]:
            status["active"] = "primary"
        elif status["fallback"]:
            status["active"] = "fallback"
        else:
            status["active"] = "none"

        return status

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    def _call_openai_compatible(
        self,
        url: str,
        model: str,
        prompt: str,
        system_prompt: str,
        format_json: bool,
        use_thinking: bool,
    ) -> str:
        """Call LM Studio or any OpenAI-compatible endpoint."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Qwen3.5 thinking mode: prefix prompt with /think or /no_think
        prefix = "/think " if use_thinking else "/no_think "
        messages.append({"role": "user", "content": prefix + prompt})

        payload: dict = {
            "model": model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": 0.7,
        }
        if format_json:
            payload["response_format"] = {"type": "json_object"}

        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]
        # Strip any <think>...</think> blocks Qwen3.5 emits in thinking mode
        return self._strip_thinking(content)

    def _call_ollama(
        self,
        url: str,
        model: str,
        prompt: str,
        system_prompt: str,
        format_json: bool,
    ) -> str:
        """Call Ollama /api/chat endpoint (same logic as old ollama_client.py)."""
        payload: dict = {
            "model": model,
            "messages": [],
            "stream": False,
        }
        if system_prompt:
            payload["messages"].append({"role": "system", "content": system_prompt})
        payload["messages"].append({"role": "user", "content": prompt})

        if format_json:
            payload["format"] = "json"

        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()

        content = response.json().get("message", {}).get("content", "")
        return self._strip_thinking(content)

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """Remove <think>...</think> blocks from model output (DeepSeek R1 / Qwen3.5 thinking mode)."""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # ------------------------------------------------------------------ #
    #  Convenience: robust JSON parsing                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def parse_json_response(response: Union[str, dict], fallback: Optional[dict] = None) -> dict:
        """
        Safely parse a JSON response from the LLM.

        Handles the common failure mode where the LLM returns a plain string
        instead of JSON (e.g. insight_engine's 'str has no attribute get').

        Args:
            response: Raw LLM output (str) or already-parsed dict.
            fallback: Value to return on parse failure (default: {}).

        Returns:
            Parsed dict or fallback.
        """
        if fallback is None:
            fallback = {}

        # Already a dict — use as-is
        if isinstance(response, dict):
            return response

        if not isinstance(response, str):
            logger.warning("parse_json_response: unexpected type %s, returning fallback", type(response))
            return fallback

        text = response.strip()

        # Strip markdown code fences if present: ```json ... ```
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        # Attempt direct parse
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # Try to extract first {...} block from the string
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

        logger.warning("parse_json_response: could not parse JSON, returning fallback. Raw: %s…", text[:200])
        return fallback
