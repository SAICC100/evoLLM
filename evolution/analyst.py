"""
Analyst - 量化当前状态与目标的差距，不提方案。

输入：
  - workspace/observations/summary_N.json（Observer 输出）
  - live/config/goal.yaml（目标定义）
  - workspace/observations/summary_*.json（历史，用于趋势）

输出：workspace/gaps/tick_N.json
"""
from __future__ import annotations

import logging
from pathlib import Path

from base import AgentBase, WORKSPACE, LIVE

logger = logging.getLogger("analyst")


class Analyst(AgentBase):
    name = "analyst"

    def run(self, tick: int) -> dict:
        summary_path = WORKSPACE / "observations" / f"summary_{tick:06d}.json"
        if not summary_path.exists():
            logger.warning(f"摘要不存在，跳过分析: tick={tick}")
            return {}

        summary = self.read_json(summary_path)
        goal = self.load_goal()

        # 收集最近 10 轮的 gaps，了解哪些问题是持续性的
        recent_gaps = []
        for i in range(max(0, tick - 10), tick):
            p = WORKSPACE / "gaps" / f"tick_{i:06d}.json"
            if p.exists():
                recent_gaps.append(self.read_json(p))

        prompt = f"""你是一个分析师，任务是量化系统当前状态与目标之间的差距。
只输出差距的客观描述，不提改进建议。

系统目标：
{goal}

当前观察摘要（tick {tick}）：
{summary}

最近 10 轮的历史差距（用于判断哪些问题是持续性的）：
{recent_gaps[-3:] if recent_gaps else "（无历史）"}

请对每个目标指标计算：
1. 当前值是多少
2. 目标阈值是多少
3. 差距有多大（0~1，0表示完全达标，1表示完全未达标）
4. 这个问题持续了多少轮（基于历史 gaps）

输出 JSON：
{{
  "tick": {tick},
  "overall_score": 0.0,
  "gaps": [
    {{
      "metric_id": "population_vitality",
      "current_value": 0,
      "threshold": "> 5",
      "gap_score": 1.0,
      "persisted_ticks": 100,
      "trend": "stable"
    }}
  ]
}}"""

        try:
            gaps = self.llm_json([{"role": "user", "content": prompt}])
            out_path = WORKSPACE / "gaps" / f"tick_{tick:06d}.json"
            self.write_json(out_path, gaps)
            logger.info(f"Analyst 完成 tick={tick}, score={gaps.get('overall_score', '?')}")
            return gaps
        except Exception as e:
            logger.error(f"Analyst 失败: {e}")
            return {}


if __name__ == "__main__":
    import sys
    tick = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    Analyst().run(tick)
