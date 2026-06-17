"""
Observer - 只看数据，输出事实，不做判断。

输入：workspace/observations/tick_N.json（Core 每轮写入）
输出：workspace/observations/summary_N.json（结构化事实摘要）
"""
from __future__ import annotations

import logging
from pathlib import Path

from base import AgentBase, WORKSPACE

logger = logging.getLogger("observer")


class Observer(AgentBase):
    name = "observer"

    def run(self, tick: int) -> dict:
        obs_path = WORKSPACE / "observations" / f"tick_{tick:06d}.json"
        if not obs_path.exists():
            logger.warning(f"快照不存在: {obs_path}")
            return {}

        snapshot = self.read_json(obs_path)

        # 读取最近 30 轮历史，用于趋势对比
        recent = self.latest_observations(30)

        prompt = f"""你是一个数据观察员，只报告事实，不做判断，不提建议。

当前快照（tick {tick}）：
{snapshot}

最近 30 轮历史快照（从新到旧）：
{recent[:5]}  # 只给前5条避免 context 过长

请输出一份结构化的事实摘要，包含：
- 本轮发生了什么（事件列表）
- 关键数值的当前值（人口、资源等）
- 与上一轮相比有哪些变化（只列变化，不分析原因）

输出 JSON 格式：
{{
  "tick": {tick},
  "events": ["事件描述1", "事件描述2"],
  "metrics": {{"key": value}},
  "changes_from_last": {{"key": "变化描述"}}
}}"""

        try:
            summary = self.llm_json([{"role": "user", "content": prompt}])
            out_path = WORKSPACE / "observations" / f"summary_{tick:06d}.json"
            self.write_json(out_path, summary)
            logger.info(f"Observer 完成 tick={tick}")
            return summary
        except Exception as e:
            logger.error(f"Observer 失败: {e}")
            # 降级：直接把快照作为摘要
            return snapshot


if __name__ == "__main__":
    import sys
    tick = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    Observer().run(tick)
