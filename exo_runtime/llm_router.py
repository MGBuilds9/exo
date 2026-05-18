"""LLM router — dispatches to claude-oauth / ollama-cloud / local-ollama by model string.

Model string format: `<provider>/<model>` or bare `<provider>` (uses provider default).
Recognized providers:
  - claude-oauth         — shells out to `claude` CLI (Claude Code)
  - ollama-cloud/<model> — POST to https://api.ollama.com (key from OLLAMA_CLOUD_API_KEY)
  - local-ollama/<model> — POST to LOCAL_OLLAMA_BASE_URL (default localhost:11434)
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass

import requests


@dataclass
class LLMRequest:
    model: str
    system: str
    user: str
    max_tokens: int = 400
    temperature: float = 0.7


class LLMRouter:
    def __init__(self, *, default_model: str = "ollama-cloud/qwen3-coder:480b", temperature: float = 0.7, timeout: int = 120) -> None:
        self.default_model = default_model
        self.temperature = temperature
        self.timeout = timeout
        self.ollama_cloud_key = os.environ.get("OLLAMA_CLOUD_API_KEY") or os.environ.get("OLLAMA_API_KEY", "")
        self.ollama_cloud_base = os.environ.get("OLLAMA_CLOUD_BASE_URL", "https://ollama.com")
        self.local_ollama_base = os.environ.get("LOCAL_OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self.local_ollama_key = os.environ.get("LOCAL_OLLAMA_API_KEY", "ollama")

    def call(self, req: LLMRequest) -> str:
        model = req.model or self.default_model
        provider = model.split("/", 1)[0]
        if provider == "claude-oauth":
            return self._call_claude(req)
        elif provider == "ollama-cloud":
            return self._call_ollama_cloud(req, model.split("/", 1)[1] if "/" in model else "qwen3-coder:480b")
        elif provider == "local-ollama":
            return self._call_local_ollama(req, model.split("/", 1)[1] if "/" in model else "qwen2.5:14b")
        else:
            raise ValueError(f"Unknown LLM provider: {provider} (model: {model})")

    def _call_ollama_cloud(self, req: LLMRequest, model: str) -> str:
        if not self.ollama_cloud_key:
            raise RuntimeError("OLLAMA_CLOUD_API_KEY not set. Configure in .env or environment.")
        url = f"{self.ollama_cloud_base.rstrip('/')}/api/chat"
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.user},
            ],
            "stream": False,
            "options": {"temperature": req.temperature, "num_predict": req.max_tokens},
        }
        headers = {"Authorization": f"Bearer {self.ollama_cloud_key}", "Content-Type": "application/json"}
        r = requests.post(url, headers=headers, json=body, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        return data.get("message", {}).get("content", "").strip()

    def _call_local_ollama(self, req: LLMRequest, model: str) -> str:
        url = f"{self.local_ollama_base.rstrip('/')}/chat/completions"
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.user},
            ],
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        }
        headers = {"Authorization": f"Bearer {self.local_ollama_key}", "Content-Type": "application/json"}
        r = requests.post(url, headers=headers, json=body, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()

    def _call_claude(self, req: LLMRequest) -> str:
        # Shells out to `claude` CLI (Claude Code). Non-interactive mode required.
        cmd = ["claude", "-p", req.user, "--system-prompt", req.system, "--no-render-text"]
        # Note: actual flag names may vary; this is a placeholder. Use ollama-cloud or local-ollama for v0.1.
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(f"claude CLI failed (code {proc.returncode}): {proc.stderr[:500]}")
        return proc.stdout.strip()
