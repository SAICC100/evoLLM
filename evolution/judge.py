"""
Judge - 评估实验效果，决定固化到 live/ 或删除 staging/ 中的文件。

输入：
  - workspace/staging/（Builder 写入的待验证文件）
  - workspace/proposals/（提案，含 metric_id 和 expected_improvement）
  - workspace/gaps/（实验前后的差距对比）

输出：
  - workspace/verdicts/prop_N.json（评估结论）
  - 成功：把文件从 staging/ 移入 live/
  - 失败：删除 staging/ 中的文件
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from base import AgentBase, WORKSPACE, LIVE

logger = logging.getLogger("judge")

# 实验需要观察多少轮才能评估
OBSERVATION_WINDOW = int(__import__("os").getenv("JUDGE_WINDOW", "5"))


class Judge(AgentBase):
    name = "judge"

    def run(self, proposal_id: str, current_tick: int) -> str:
        """
        评估一个提案的效果。
        返回：'commit'（固化）| 'revert'（回滚）| 'waiting'（观察期未到）
        """
        prop_path = WORKSPACE / "proposals" / f"{proposal_id}.json"
        if not prop_path.exists():
            return "revert"

        prop = self.read_json(prop_path)
        if prop.get("status") != "built":
            return "waiting"

        # 检查是否已经在 staging 里（Builder 已写入）
        change_type = prop["change_type"]
        target_file = prop["target_file"]
        staging_path = WORKSPACE / "staging" / f"{change_type}s" / target_file

        if not staging_path.exists():
            return "revert"

        # 检查观察期：提案创建后至少跑了 OBSERVATION_WINDOW 轮
        built_tick = prop.get("tick", 0)
        if current_tick - built_tick < OBSERVATION_WINDOW:
            logger.debug(f"观察期未到: {proposal_id} ({current_tick - built_tick}/{OBSERVATION_WINDOW})")
            return "waiting"

        # 收集实验前后的 gaps
        pre_gaps = self._get_gaps_around(built_tick - 3, built_tick)
        post_gaps = self._get_gaps_around(current_tick - OBSERVATION_WINDOW, current_tick)

        metric_id = prop.get("metric_id", "")

        prompt = f"""你是一个实验评估专家，判断这个改动是否有效。

提案假设：{prop['hypothesis']}
预期效果：{prop['expected_improvement']}
目标指标：{metric_id}

实验前（改动前 3 轮的 gaps）：
{pre_gaps}

实验后（改动后 {OBSERVATION_WINDOW} 轮的 gaps）：
{post_gaps}

判断标准：
- 目标指标有改善（gap_score 下降，或 current_value 更接近阈值）→ commit
- 指标无变化或变差，且持续 {OBSERVATION_WINDOW} 轮 → revert
- 数据不足以判断 → waiting

请输出 JSON：
{{
  "verdict": "commit|revert|waiting",
  "reason": "判断理由，一句话",
  "metric_before": 0.0,
  "metric_after": 0.0
}}"""

        try:
            result = self.llm_json([{"role": "user", "content": prompt}])
            verdict = result.get("verdict", "revert")

            # 记录判决
            verdict_data = {
                "proposal_id": proposal_id,
                "tick": current_tick,
                "verdict": verdict,
                "reason": result.get("reason"),
                "metric_before": result.get("metric_before"),
                "metric_after": result.get("metric_after"),
                "change_type": change_type,
                "target_file": target_file,
                "hypothesis": prop.get("hypothesis"),
            }
            self.write_json(WORKSPACE / "verdicts" / f"{proposal_id}.json", verdict_data)

            if verdict == "commit":
                self._commit(staging_path, change_type, target_file)
                prop["status"] = "committed"
                logger.info(f"Judge COMMIT: {proposal_id} -> {target_file} ({result.get('reason')})")
            elif verdict == "revert":
                staging_path.unlink(missing_ok=True)
                prop["status"] = "reverted"
                logger.info(f"Judge REVERT: {proposal_id} ({result.get('reason')})")

            self.write_json(prop_path, prop)
            return verdict

        except Exception as e:
            logger.error(f"Judge 失败 {proposal_id}: {e}")
            return "waiting"

    def _commit(self, staging_path: Path, change_type: str, target_file: str) -> None:
        """将文件从 staging/ 移入 live/。"""
        live_path = LIVE / f"{change_type}s" / target_file
        live_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staging_path, live_path)
        staging_path.unlink()
        logger.info(f"已固化到 live: {live_path}")

    def _get_gaps_around(self, start: int, end: int) -> list[dict]:
        result = []
        for tick in range(max(0, start), end + 1):
            p = WORKSPACE / "gaps" / f"tick_{tick:06d}.json"
            if p.exists():
                result.append(self.read_json(p))
        return result

    def run_all_built(self, current_tick: int) -> dict:
        """评估所有 built 状态的提案。"""
        proposals_dir = WORKSPACE / "proposals"
        stats = {"commit": 0, "revert": 0, "waiting": 0}
        for f in proposals_dir.glob("prop_*.json"):
            prop = self.read_json(f)
            if prop.get("status") == "built":
                verdict = self.run(prop["id"], current_tick)
                stats[verdict] = stats.get(verdict, 0) + 1
        return stats


if __name__ == "__main__":
    import sys
    current_tick = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    stats = Judge().run_all_built(current_tick)
    print(f"Judge 结果: {stats}")
