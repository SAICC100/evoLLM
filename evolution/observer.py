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


def _compress_snapshot(snapshot: dict) -> dict:
    """
    把原始快照压缩成 LLM 可以处理的摘要结构。
    原始快照可能有 300 个 NPC + 32x32 地图，超出 token 限制。
    这里只提取关键统计信息，不传原始数据。
    """
    data = snapshot.get("state", {}).get("data", {})
    tick = snapshot.get("tick", 0)

    npcs = data.get("npcs", [])
    tribes = data.get("tribes", [])
    world = data.get("world", {})
    events = data.get("events", [])

    # 防御：确保是 dict 列表，过滤掉非 dict 元素
    npcs = [n for n in npcs if isinstance(n, dict)]
    tribes = [t for t in tribes if isinstance(t, dict)]
    events = [e for e in events if isinstance(e, dict)]
    if not isinstance(world, dict):
        world = {}

    # NPC 统计
    npc_stats = {
        "total": len(npcs),
        "avg_health": round(sum(n.get("health", 0) for n in npcs) / max(len(npcs), 1), 1),
        "avg_stamina": round(sum(n.get("stamina", 0) for n in npcs) / max(len(npcs), 1), 1),
        "avg_money": round(sum(n.get("money", 0) for n in npcs) / max(len(npcs), 1), 1),
        "by_profession": {},
        "by_tribe": {},
    }
    for n in npcs:
        prof = n.get("profession", "unknown")
        tribe = n.get("tribe_id", "unknown")
        npc_stats["by_profession"][prof] = npc_stats["by_profession"].get(prof, 0) + 1
        npc_stats["by_tribe"][tribe] = npc_stats["by_tribe"].get(tribe, 0) + 1

    # 部落统计
    tribe_stats = [
        {
            "id": t.get("id"),
            "name": t.get("name"),
            "population": t.get("population", 0),
            "resources": t.get("resources", {}),
        }
        for t in tribes
    ]

    # 事件统计（最近 20 条）
    event_types = {}
    recent_events = events[-20:] if events else []
    for e in events:
        t = e.get("type", "unknown")
        event_types[t] = event_types.get(t, 0) + 1

    return {
        "tick": tick,
        "season": world.get("current_season", "unknown"),
        "npc_stats": npc_stats,
        "tribe_stats": tribe_stats,
        "event_types": event_types,
        "recent_events": recent_events,
        "map_size": f"{len(world.get('map', []))}x{len(world.get('map', [[]])[0]) if world.get('map') else 0}",
    }


class Observer(AgentBase):
    name = "observer"

    def run(self, tick: int) -> dict:
        obs_path = WORKSPACE / "observations" / f"tick_{tick:06d}.json"
        if not obs_path.exists():
            logger.warning(f"快照不存在: {obs_path}")
            return {}

        snapshot = self.read_json(obs_path)
        compressed = _compress_snapshot(snapshot)

        # 最近 3 轮的压缩摘要用于趋势对比
        recent_compressed = []
        for i in range(max(1, tick - 3), tick):
            p = WORKSPACE / "observations" / f"summary_{i:06d}.json"
            if p.exists():
                recent_compressed.append(self.read_json(p))

        prompt = f"""你是数据观察员，只报告事实，不做判断，不提建议。

当前世界状态摘要（tick {tick}）：
{compressed}

最近 3 轮历史摘要（用于对比变化）：
{recent_compressed if recent_compressed else "（无历史）"}

请输出结构化事实摘要，包含：
- 本轮关键数值（人口总数、平均健康、各部落人口）
- 发生了哪些类型的事件，各多少次
- 与上一轮相比有哪些明显变化（只列事实，不分析原因）

输出 JSON：
{{
  "tick": {tick},
  "npc_total": 0,
  "avg_health": 0.0,
  "event_types": {{}},
  "tribe_populations": {{}},
  "notable_changes": []
}}"""

        try:
            summary = self.llm_json([{"role": "user", "content": prompt}])
            out_path = WORKSPACE / "observations" / f"summary_{tick:06d}.json"
            self.write_json(out_path, summary)
            logger.info(f"Observer 完成 tick={tick}, events={summary.get('event_types', {})}")
            return summary
        except Exception as e:
            logger.error(f"Observer 失败: {e}")
            # 降级：用压缩数据直接作为摘要
            fallback = {
                "tick": tick,
                "npc_total": compressed["npc_stats"]["total"],
                "avg_health": compressed["npc_stats"]["avg_health"],
                "event_types": compressed["event_types"],
                "tribe_populations": {t["name"]: t["population"] for t in compressed["tribe_stats"]},
                "notable_changes": [],
            }
            out_path = WORKSPACE / "observations" / f"summary_{tick:06d}.json"
            self.write_json(out_path, fallback)
            return fallback


if __name__ == "__main__":
    import sys
    tick = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    Observer().run(tick)
