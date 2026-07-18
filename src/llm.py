"""
轻量 LLM 调用层 — 用 httpx 直接调 DeepSeek API，替代 openai 包。

无需安装 openai 包，避免 jiter/pydantic-core 的 Rust 编译问题。
DeepSeek API 与 OpenAI 完全兼容。
"""
import json
import httpx
from typing import List, Dict, Optional


class _Completions:
    def __init__(self, parent: "LLMClient"):
        self._parent = parent

    def create(self, *, model: str, messages: List[Dict[str, str]],
               temperature: float = 0.3, max_tokens: int = 4096):
        text = self._parent.chat(messages, model=model,
                                 temperature=temperature, max_tokens=max_tokens)
        return _FakeResponse(text)


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class _Chat:
    def __init__(self, parent: "LLMClient"):
        self.completions = _Completions(parent)


class LLMClient:
    """极简 OpenAI-compatible 客户端，只用 httpx。
    兼容 openai 包接口：client.chat.completions.create(...)"""

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=120.0)
        self.chat = _Chat(self)

    def chat(self, messages: List[Dict[str, str]], *,
             model: str = "deepseek-chat",
             temperature: float = 0.3,
             max_tokens: int = 4096) -> str:
        """发送聊天请求，返回文本内容"""
        resp = self._client.post(
            f"{self.base_url}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def close(self):
        self._client.close()


__all__ = ["LLMClient"]
