#!/bin/bash
# evo-core 启动脚本
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# 环境变量
export GATEWAY_URL="${GATEWAY_URL:-http://localhost:7000}"
export WORKSPACE_DIR="${WORKSPACE_DIR:-$ROOT/workspace}"
export LIVE_DIR="${LIVE_DIR:-$ROOT/live}"
export LLM_API_KEY="${LLM_API_KEY:-NONE}"
export LLM_BASE_URL="${LLM_BASE_URL:-https://api.openai.com/v1}"
export LLM_MODEL="${LLM_MODEL:-gpt-4o-mini}"

echo "=== evo-core 启动 ==="
echo "ROOT:     $ROOT"
echo "LIVE:     $LIVE_DIR"
echo "GATEWAY:  $GATEWAY_URL"

# 确保目录存在
mkdir -p "$ROOT"/{workspace/{observations,gaps,proposals,staging/{plugins,prompts,pipelines},verdicts},live/{plugins,prompts,pipelines,config},data}

# 检查 goal.yaml
if [ ! -f "$LIVE_DIR/config/goal.yaml" ]; then
    echo "错误：$LIVE_DIR/config/goal.yaml 不存在"
    echo "请先创建目标定义文件，参考 docs/goal-spec.md"
    exit 1
fi

# 1. 启动 LLM Gateway
echo "启动 LLM Gateway..."
cd "$ROOT/llm-gateway"
python3 gateway.py &
GATEWAY_PID=$!
sleep 2

# 2. 冷启动（如果 live/plugins/ 为空）
if [ -z "$(ls -A "$LIVE_DIR/plugins" 2>/dev/null)" ]; then
    echo "运行冷启动..."
    cd "$ROOT/evolution"
    python3 bootstrapper.py
fi

# 3. 启动进化层调度器
echo "启动进化层..."
cd "$ROOT/evolution"
python3 scheduler.py &
EVO_PID=$!

# 4. 启动 Core（Go）
echo "启动 Core..."
cd "$ROOT/core"
./core \
    --live "$LIVE_DIR" \
    --workspace "$ROOT/workspace" \
    --db "$ROOT/data/state.db" \
    --tick 5s &
CORE_PID=$!

echo "=== 所有服务已启动 ==="
echo "Gateway PID: $GATEWAY_PID"
echo "Evolution PID: $EVO_PID"
echo "Core PID: $CORE_PID"

# 等待退出信号
trap "kill $GATEWAY_PID $EVO_PID $CORE_PID 2>/dev/null; exit 0" SIGINT SIGTERM
wait
