"""
LLM Gateway - 统一 LLM 调用入口

所有 Plugin 和进化层 Agent 都通过这个服务调用 LLM，不直接调用 OpenAI SDK。
提供：限流、重试、fallback、请求日志。
"""
from __future__ import annotations

import os
import time
import logging
from typing import Any
from collections import deque

from flask import Flask, request, jsonify
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("llm-gateway")

app = Flask(__name__)

# ── LLM 客户端 ──────────────────────────────────────────────────────────────

_client = OpenAI(
    api_key=os.getenv("LLM_API_KEY", "NONE"),
    base_url=os.getenv("LLM_BASE_URL", "http://wbaigcproxy.search.weibo.com:9029/v1"),
)
DEFAULT_MODEL = os.getenv("LLM_MODEL_NAME", "deepseek-v3.2")

# ── 简单令牌桶限流 ───────────────────────────────────────────────────────────

class RateLimiter:
    """每分钟最多 N 次请求的令牌桶。"""
    def __init__(self, rpm: int = 60):
        self.rpm = rpm
        self.window = deque()

    def acquire(self) -> bool:
        now = time.time()
        # 清除 1 分钟前的记录
        while self.window and self.window[0] < now - 60:
            self.window.popleft()
        if len(self.window) >= self.rpm:
            return False
        self.window.append(now)
        return True

_limiter = RateLimiter(rpm=int(os.getenv("LLM_RPM", "60")))

# ── API ─────────────────────────────────────────────────────────────────────

@app.route("/chat", methods=["POST"])
def chat():
    """
    统一聊天接口。

    请求体：
    {
      "messages": [{"role": "user", "content": "..."}],
      "model": "gpt-4o-mini",      // 可选，默认使用环境变量
      "temperature": 0.7,           // 可选
      "max_tokens": 1000,           // 可选
      "caller": "observer"          // 可选，用于日志
    }

    响应体：
    {
      "content": "...",
      "model": "gpt-4o-mini",
      "usage": { "prompt_tokens": 100, "completion_tokens": 50 }
    }
    """
    body = request.get_json(force=True)
    messages = body.get("messages", [])
    model = body.get("model", DEFAULT_MODEL)
    temperature = body.get("temperature", 0.7)
    max_tokens = body.get("max_tokens", 2000)
    caller = body.get("caller", "unknown")

    if not messages:
        return jsonify({"error": "messages 不能为空"}), 400

    if not _limiter.acquire():
        logger.warning("限流触发", extra={"caller": caller})
        return jsonify({"error": "rate limit exceeded, retry later"}), 429

    # 重试最多 3 次
    last_error = None
    for attempt in range(3):
        try:
            resp = _client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content
            usage = {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
            }
            logger.info("LLM 调用成功",
                        extra={"caller": caller, "model": model,
                               "tokens": resp.usage.total_tokens})
            return jsonify({"content": content, "model": model, "usage": usage})

        except Exception as e:
            last_error = e
            wait = 2 ** attempt
            logger.warning(f"LLM 调用失败（第{attempt+1}次），{wait}s 后重试: {e}")
            time.sleep(wait)

    logger.error(f"LLM 调用最终失败: {last_error}")
    return jsonify({"error": str(last_error)}), 502


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model": DEFAULT_MODEL})


if __name__ == "__main__":
    port = int(os.getenv("GATEWAY_PORT", "7000"))
    logger.info(f"LLM Gateway 启动，端口 {port}，模型 {DEFAULT_MODEL}")
    app.run(host="0.0.0.0", port=port)
