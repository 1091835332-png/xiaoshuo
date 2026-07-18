"""
轻量 LLM 调用层 — 用 httpx 直接调 DeepSeek API，替代 openai 包。

无需安装 openai 包，避免 jiter/pydantic-core 的 Rust 编译问题。
DeepSeek API 与 OpenAI 完全兼容。
"""
import json
import time
import httpx
from typing import List, Dict, Optional


class _Completions:
    def __init__(self, parent: "LLMClient"):
        self._parent = parent

    def create(self, *, model: str, messages: List[Dict[str, str]],
               temperature: float = 0.3, max_tokens: int = 4096):
        text = self._parent._chat_impl(messages, model=model,
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
        self._client = httpx.Client(timeout=httpx.Timeout(90.0, connect=15.0))
        self.chat = _Chat(self)  # openai 兼容接口: client.chat.completions.create()

    def _chat_impl(self, messages: List[Dict[str, str]], *,
             model: str = "deepseek-chat",
             temperature: float = 0.3,
             max_tokens: int = 4096) -> str:
        """发送聊天请求，返回文本内容。失败自动重试一次。"""
        last_err = ""
        for attempt in range(2):
            try:
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
            except httpx.HTTPStatusError as e:
                last_err = f"API {e.response.status_code}: {e.response.text[:200]}"
                if e.response.status_code == 429:
                    time.sleep(2 * (attempt + 1))
                    continue
                break
            except Exception as e:
                last_err = f"网络错误: {e}"
                if attempt == 0:
                    time.sleep(1.5)
                    continue
        return f"[AI调用失败: {last_err}]"

    def close(self):
        self._client.close()


__all__ = ["LLMClient"]
