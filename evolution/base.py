"""
进化层基础类：所有 Agent 共用的 LLM 调用、文件读写、日志。
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

# 加载 .env（如果存在）
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:7000")
WORKSPACE = Path(os.getenv("WORKSPACE_DIR", str(Path(__file__).parent.parent / "workspace")))
LIVE = Path(os.getenv("LIVE_DIR", str(Path(__file__).parent.parent / "live")))

# 直连 LLM（不依赖 gateway 服务，保证 Bootstrapper 独立可运行）
_llm_client = OpenAI(
    api_key=os.getenv("LLM_API_KEY", "NONE"),
    base_url=os.getenv("LLM_BASE_URL", "http://wbaigcproxy.search.weibo.com:9029/v1"),
)
_llm_model = os.getenv("LLM_MODEL_NAME", "deepseek-v3.2")

logger = logging.getLogger("evolution")


class AgentBase:
    name: str = "base"

    def llm(self, messages: list[dict], temperature: float = 0.7,
            max_tokens: int = 4000) -> str:
        resp = _llm_client.chat.completions.create(
            model=_llm_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content

    def llm_json(self, messages: list[dict], **kwargs) -> Any:
        """调用 LLM 并解析 JSON 输出，自动提取代码块。"""
        content = self.llm(messages, **kwargs)
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
        if not obs_dir.exists():
            return []
        files = sorted(obs_dir.glob("tick_*.json"), reverse=True)[:n]
        return [self.read_json(f) for f in files]
