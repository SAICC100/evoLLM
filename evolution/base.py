"""
进化层基础类：所有 Agent 共用的 LLM 调用、文件读写、日志。
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:7000")
WORKSPACE = Path(os.getenv("WORKSPACE_DIR", "../workspace"))
LIVE = Path(os.getenv("LIVE_DIR", "../live"))

logger = logging.getLogger("evolution")


class AgentBase:
    name: str = "base"

    def llm(self, messages: list[dict], temperature: float = 0.7,
            max_tokens: int = 2000) -> str:
        resp = requests.post(f"{GATEWAY_URL}/chat", json={
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "caller": self.name,
        }, timeout=60)
        resp.raise_for_status()
        return resp.json()["content"]

    def llm_json(self, messages: list[dict], **kwargs) -> Any:
        """调用 LLM 并解析 JSON 输出，自动提取代码块。"""
        content = self.llm(messages, **kwargs)
        # 提取 ```json ... ``` 或 [ ... ] 或 { ... }
        for pattern in [r"```json\s*(.*?)```", r"(\[.*\])", r"(\{.*\})"]:
            m = re.search(pattern, content, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    continue
        raise ValueError(f"LLM 未返回合法 JSON:\n{content[:300]}")

    def read_json(self, path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_file(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def load_goal(self) -> dict:
        goal_path = LIVE / "config" / "goal.yaml"
        if not goal_path.exists():
            return {}
        import yaml
        return yaml.safe_load(goal_path.read_text(encoding="utf-8"))

    def latest_observations(self, n: int = 10) -> list[dict]:
        obs_dir = WORKSPACE / "observations"
        files = sorted(obs_dir.glob("tick_*.json"), reverse=True)[:n]
        return [self.read_json(f) for f in files]
