#!/bin/bash
# 项目初始化：编译 Go Core，安装 Python 依赖
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== evo-core 初始化 ==="

# 编译 Go Core
echo "编译 Go Core..."
cd "$ROOT/core"
GOPROXY=https://goproxy.cn,direct go mod tidy
GOPROXY=https://goproxy.cn,direct go build -o core .
echo "Go Core 编译完成"

# 安装 Python 依赖
echo "安装 Python 依赖..."
pip install flask openai requests pyyaml 2>/dev/null || \
    pip3 install flask openai requests pyyaml
echo "Python 依赖安装完成"

echo "=== 初始化完成 ==="
echo "下一步：编辑 live/config/goal.yaml，然后运行 scripts/start.sh"
