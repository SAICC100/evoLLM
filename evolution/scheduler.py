"""
进化层调度器 - 监听 workspace/observations/，按流水线顺序触发各 Agent。

设计原则：
- 只处理最新的 tick，跳过积压（Core 速度远快于进化层）
- Observer+Analyst 每轮必跑
- Proposer 每 N 轮跑一次
- Builder/Judge 每轮都检查 pending/built 状态
"""
from __future__ import annotations

import logging
import os
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

PROPOSE_EVERY = int(os.getenv("PROPOSE_EVERY", "5"))
# 进化层与 Core 的速度比：每处理1个tick，跳过多少个积压tick
# Core 10s/tick，进化层约 60-120s/tick，所以至少跳 6-12 个
SKIP_RATIO = int(os.getenv("EVO_SKIP_RATIO", "10"))


def get_latest_tick() -> int:
    """获取最新的快照 tick 编号。"""
    obs_dir = WORKSPACE / "observations"
    files = sorted(obs_dir.glob("tick_*.json"), reverse=True)
    if not files:
        return 0
    return int(files[0].stem.replace("tick_", ""))


def run_forever() -> None:
    observer = Observer()
    analyst = Analyst()
    proposer = Proposer()
    builder = Builder()
    judge = Judge()

    last_processed = 0

    logger.info("进化层调度器启动（跳过积压模式，skip_ratio=%d）", SKIP_RATIO)

    while True:
        latest = get_latest_tick()

        if latest <= last_processed:
            time.sleep(2)
            continue

        # 跳过积压：直接跳到最新，不逐个处理
        tick = latest
        skipped = tick - last_processed - 1
        if skipped > 0:
            logger.info(f"跳过积压 {skipped} 个 tick，直接处理最新 tick={tick}")

        last_processed = tick
        logger.info(f"── 处理 tick={tick} ──")

        try:
            # 1. Observer：事实摘要
            observer.run(tick)

            # 2. Analyst：量化差距
            analyst.run(tick)

            # 3. Proposer：每 N 轮提一次新方案
            if tick % PROPOSE_EVERY == 0:
                proposals = proposer.run(tick)
                if proposals:
                    logger.info(f"Proposer 生成 {len(proposals)} 个提案")

            # 4. Builder：处理所有 pending 提案（最多 3 个，避免积压）
            n_built = builder.run_pending(max_count=3)
            if n_built:
                logger.info(f"Builder 处理了 {n_built} 个提案")

            # 5. Judge：评估所有已部署提案
            stats = judge.run_all_deployed(tick)
            if any(v > 0 for v in stats.values()):
                logger.info(f"Judge 结果: {stats}")

        except Exception as e:
            logger.error(f"tick={tick} 处理失败: {e}", exc_info=True)

        # 处理完一个 tick 后短暂等待，让 Core 再积累几个 tick
        time.sleep(1)


if __name__ == "__main__":
    run_forever()
