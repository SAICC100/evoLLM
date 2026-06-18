"""
Judge - 评估已部署到 live/ 的变更效果，决定保留或回滚。

流程：
- 提案 status=deployed 且观察期已满 → 读取部署前后的指标对比
- 有效（指标改善或至少不变）→ 删除 backup，status=committed
- 无效（指标无变化或变差）→ 从 backup 恢复旧版本，status=reverted
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from base import AgentBase, WORKSPACE, LIVE

logger = logging.getLogger("judge")

OBSERVATION_WINDOW = int(__import__("os").getenv("JUDGE_WINDOW", "5"))
BACKUP_DIR = LIVE / "backup"


class Judge(AgentBase):
    name = "judge"

    def run(self, proposal_id: str, current_tick: int) -> str:
        """
        评估一个已部署的提案。
        返回：'committed' | 'reverted' | 'waiting'
        """
        prop_path = WORKSPACE / "proposals" / f"{proposal_id}.json"
        if not prop_path.exists():
            return "waiting"

        prop = self.read_json(prop_path)
        if prop.get("status") != "deployed":
            return "waiting"

        deployed_tick = prop.get("deployed_tick", 0)
        if current_tick - deployed_tick < OBSERVATION_WINDOW:
            return "waiting"

        change_type = prop["change_type"]
        target_file = prop["target_file"]
        live_path = LIVE / f"{change_type}s" / target_file
        backup_path = BACKUP_DIR / f"{change_type}s" / target_file

        # 收集部署前后的 gaps
        pre_gaps = self._get_gaps_around(max(0, deployed_tick - 3), deployed_tick)
        post_gaps = self._get_gaps_around(deployed_tick + 1, current_tick)

        if not post_gaps:
            return "waiting"

        metric_id = prop.get("metric_id", "")

        prompt = f"""你是实验评估专家，判断一个代码改动是否有效。

提案假设：{prop.get('hypothesis', '')[:200]}
目标指标：{metric_id}
预期效果：{prop.get('expected_improvement', '')[:100]}

部署前（{len(pre_gaps)} 轮数据）：
{pre_gaps}

部署后（{len(post_gaps)} 轮数据）：
{post_gaps}

判断标准：
- 目标指标的 current_value 有增加，或 gap_score 有下降 → commit
- 部署后所有指标完全没有变化，且已观察 {OBSERVATION_WINDOW} 轮 → revert
- 数据不足（post_gaps 少于 3 条）→ waiting

注意：如果部署前后指标都是 0，但这是全局问题（所有 Plugin 都没产生事件），
应该判断为 waiting 而不是 revert，给更多时间观察。

输出 JSON：
{{
  "verdict": "commit|revert|waiting",
  "reason": "一句话判断理由",
  "metric_before": 数值或null,
  "metric_after": 数值或null
}}"""

        try:
            result = self.llm_json([{"role": "user", "content": prompt}])
            verdict = result.get("verdict", "waiting")

            # 记录判决
            self.write_json(WORKSPACE / "verdicts" / f"{proposal_id}.json", {
                "proposal_id": proposal_id,
                "tick": current_tick,
                "verdict": verdict,
                "reason": result.get("reason"),
                "metric_before": result.get("metric_before"),
                "metric_after": result.get("metric_after"),
                "change_type": change_type,
                "target_file": target_file,
            })

            if verdict == "commit":
                # 保留新版本，删除备份
                backup_path.unlink(missing_ok=True)
                prop["status"] = "committed"
                logger.info(f"Judge COMMIT: {proposal_id} -> {target_file} ({result.get('reason','')})")

            elif verdict == "revert":
                # 从备份恢复旧版本
                if backup_path.exists():
                    shutil.copy2(backup_path, live_path)
                    backup_path.unlink()
                    logger.info(f"Judge REVERT: {proposal_id} -> 已恢复旧版本 ({result.get('reason','')})")
                else:
                    logger.warning(f"Judge REVERT: {proposal_id} 无备份可恢复，保留当前版本")
                prop["status"] = "reverted"

            self.write_json(prop_path, prop)
            return verdict

        except Exception as e:
            logger.error(f"Judge 失败 {proposal_id}: {e}")
            return "waiting"

    def _get_gaps_around(self, start: int, end: int) -> list[dict]:
        result = []
        for tick in range(max(0, start), end + 1):
            p = WORKSPACE / "gaps" / f"tick_{tick:06d}.json"
            if p.exists():
                result.append(self.read_json(p))
        return result

    def run_all_deployed(self, current_tick: int) -> dict:
        """评估所有 deployed 状态的提案。"""
        proposals_dir = WORKSPACE / "proposals"
        stats = {"committed": 0, "reverted": 0, "waiting": 0}
        for f in proposals_dir.glob("prop_*.json"):
            prop = self.read_json(f)
            if prop.get("status") == "deployed":
                verdict = self.run(prop["id"], current_tick)
                stats[verdict] = stats.get(verdict, 0) + 1
        return stats


if __name__ == "__main__":
    import sys
    current_tick = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    stats = Judge().run_all_deployed(current_tick)
    print(f"Judge 结果: {stats}")
