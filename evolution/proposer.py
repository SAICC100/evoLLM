"""
Proposer - 针对差距提出改进假设，不写代码。

输入：
  - workspace/gaps/tick_N.json（Analyst 输出）
  - workspace/verdicts/（历史实验结论，知道什么试过了）

输出：workspace/proposals/prop_N.json
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from base import AgentBase, WORKSPACE, LIVE

logger = logging.getLogger("proposer")


class Proposer(AgentBase):
    name = "proposer"

    def run(self, tick: int) -> list[dict]:
        gaps_path = WORKSPACE / "gaps" / f"tick_{tick:06d}.json"
        if not gaps_path.exists():
            return []

        gaps = self.read_json(gaps_path)
        if not gaps.get("gaps"):
            return []

        # 只处理 gap_score > 0.5 的指标（优先级最高的问题）
        priority_gaps = [g for g in gaps["gaps"] if g.get("gap_score", 0) > 0.5]
        if not priority_gaps:
            return []

        # 已有的提案和实验结论（避免重复提相同的方案）
        existing_proposals = self._load_recent_proposals(20)
        past_verdicts = self._load_verdicts(20)

        # 已生效的 Plugin 和 Pipeline
        live_plugins = [p.stem for p in (LIVE / "plugins").glob("*.py")]
        live_pipelines = [p.stem for p in (LIVE / "pipelines").glob("*.yaml")]

        prompt = f"""你是一个系统改进专家，负责提出改进假设。
只输出假设（"如果改变X，指标Y会提升"），不写代码。

当前优先级最高的问题：
{priority_gaps}

已尝试过的方案（避免重复提）：
{past_verdicts[-5:] if past_verdicts else "（无历史）"}

当前已有的 Plugin：{live_plugins}
当前已有的 Pipeline：{live_pipelines}

系统可以改变的内容只有三种：
1. plugin - 新增或修改一个 Python 函数（实现具体功能）
2. prompt - 新增或修改一个 Prompt 文本文件（影响 LLM 行为）
3. pipeline - 新增或修改 Plugin 的组合和执行顺序

请提出 1~3 个改进假设，每个假设包含：
- 针对哪个 metric_id
- 改变什么（plugin/prompt/pipeline）
- 具体目标文件名
- 改变的思路（自然语言，不是代码）
- 预期哪个指标会改善多少

输出 JSON 数组：
[
  {{
    "metric_id": "population_vitality",
    "change_type": "plugin",
    "target_file": "death_check.py",
    "hypothesis": "为每个 NPC 添加基于年龄和健康值的每日死亡概率检测",
    "expected_improvement": "death_events 从 0 增加到每 30 轮 > 5"
  }}
]"""

        try:
            hypotheses = self.llm_json([{"role": "user", "content": prompt}])
            if not isinstance(hypotheses, list):
                hypotheses = [hypotheses]

            proposals = []
            for h in hypotheses:
                prop = {
                    "id": f"prop_{uuid.uuid4().hex[:8]}",
                    "tick": tick,
                    "metric_id": h.get("metric_id"),
                    "change_type": h.get("change_type"),
                    "target_file": h.get("target_file"),
                    "hypothesis": h.get("hypothesis"),
                    "expected_improvement": h.get("expected_improvement"),
                    "status": "pending",
                }
                out_path = WORKSPACE / "proposals" / f"{prop['id']}.json"
                self.write_json(out_path, prop)
                proposals.append(prop)
                logger.info(f"Proposer 生成提案: {prop['id']} -> {prop['target_file']}")

            return proposals
        except Exception as e:
            logger.error(f"Proposer 失败: {e}")
            return []

    def _load_recent_proposals(self, n: int) -> list[dict]:
        d = WORKSPACE / "proposals"
        files = sorted(d.glob("prop_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:n]
        return [self.read_json(f) for f in files]

    def _load_verdicts(self, n: int) -> list[dict]:
        d = WORKSPACE / "verdicts"
        if not d.exists():
            return []
        files = sorted(d.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:n]
        return [self.read_json(f) for f in files]


if __name__ == "__main__":
    import sys
    tick = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    Proposer().run(tick)
