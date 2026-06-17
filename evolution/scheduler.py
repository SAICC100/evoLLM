"""
进化层调度器 - 监听 workspace/observations/，按流水线顺序触发各 Agent。

每当 Core 写入新快照，依次触发：
Observer → Analyst → Proposer → Builder → Judge
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

from base import WORKSPACE
from observer import Observer
from analyst import Analyst
from proposer import Proposer
from builder import Builder
from judge import Judge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-12s %(levelname)s %(message)s"
)
logger = logging.getLogger("evo-scheduler")

# 每隔多少轮触发一次 Proposer（避免提案过多）
PROPOSE_EVERY = int(os.getenv("PROPOSE_EVERY", "5"))


def run_forever() -> None:
    observer = Observer()
    analyst = Analyst()
    proposer = Proposer()
    builder = Builder()
    judge = Judge()

    processed: set[int] = set()

    logger.info("进化层调度器启动，等待 Core 写入快照...")

    while True:
        # 扫描未处理的快照
        obs_dir = WORKSPACE / "observations"
        if not obs_dir.exists():
            time.sleep(2)
            continue

        for snap_file in sorted(obs_dir.glob("tick_*.json")):
            tick = int(snap_file.stem.replace("tick_", ""))
            if tick in processed:
                continue

            processed.add(tick)
            logger.info(f"── 开始处理 tick={tick} ──")

            try:
                # 1. Observer：事实摘要
                observer.run(tick)

                # 2. Analyst：量化差距
                analyst.run(tick)

                # 3. Proposer：每 N 轮提一次新方案
                if tick % PROPOSE_EVERY == 0:
                    proposals = proposer.run(tick)
                    logger.info(f"Proposer 生成 {len(proposals)} 个提案")

                # 4. Builder：处理所有 pending 提案
                n_built = builder.run_pending()
                if n_built:
                    logger.info(f"Builder 处理了 {n_built} 个提案")

                # 5. Judge：评估所有 built 提案
                stats = judge.run_all_built(tick)
                if any(v > 0 for v in stats.values()):
                    logger.info(f"Judge 结果: {stats}")

            except Exception as e:
                logger.error(f"tick={tick} 处理失败: {e}", exc_info=True)

        time.sleep(1)


if __name__ == "__main__":
    run_forever()
