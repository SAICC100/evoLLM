# Plugin 开发规范

Plugin 是系统中最小的可进化单元，每个 Plugin 负责一个具体功能。

---

## 接口约定

Plugin 是一个独立的 Python 文件，通过 stdin/stdout 与 Core 通信。

### 输入（stdin）

Core 在调用 Plugin 时，通过 stdin 传入 JSON：

```json
{
  "context": {
    "npc": {
      "id": "npc_001",
      "name": "艾莉温",
      "health": 80,
      "age": 35,
      "gold": 120
    },
    "world": {
      "day": 100,
      "season": "spring"
    }
  },
  "timeout_ms": 5000
}
```

`context` 是当前轮次的只读世界快照，Plugin 不能修改它，只能读取。

### 输出（stdout）

Plugin 执行完毕后，向 stdout 输出 JSON：

```json
{
  "changes": [
    { "path": "npc.health", "op": "add", "value": -5 },
    { "path": "world.events", "op": "append", "value": {
      "type": "health_decay",
      "description": "艾莉温 因年龄增长健康衰减 5 点"
    }}
  ],
  "logs": [
    "health decayed by 5 (age=35, season=spring)"
  ]
}
```

`changes` 是声明式的变更列表，由 Core 负责应用。Plugin 不直接写数据库。

### 变更操作类型

| op | 说明 |
|----|------|
| `set` | 直接赋值 |
| `add` | 数值加减 |
| `append` | 追加到列表 |
| `remove` | 从列表删除 |

---

## Plugin 文件结构

```python
#!/usr/bin/env python3
"""
health_decay.py
NPC 每日健康衰减，基于年龄和季节。
"""
import sys
import json


def run(context: dict) -> dict:
    npc = context["npc"]
    world = context["world"]

    age = npc.get("age", 20)
    season = world.get("season", "spring")

    # 冬季衰减加倍
    decay = 2 if age > 60 else 1
    if season == "winter":
        decay *= 2

    return {
        "changes": [
            {"path": "npc.health", "op": "add", "value": -decay}
        ],
        "logs": [f"health decayed by {decay} (age={age}, season={season})"]
    }


if __name__ == "__main__":
    input_data = json.loads(sys.stdin.read())
    result = run(input_data["context"])
    print(json.dumps(result))
```

---

## 约束

1. **只读 context**：Plugin 不修改传入的 context 对象
2. **无网络调用**：Plugin 不调用外部 API（需要 LLM 的场景走 Prompt 机制）
3. **无文件 IO**：Plugin 不读写文件系统
4. **无状态**：Plugin 不持有跨调用的状态，每次调用独立
5. **超时**：Core 会在 timeout_ms 后强制 kill，Plugin 应该快速返回
6. **异常处理**：Plugin 内部应 catch 异常，在 logs 里记录，不能让异常传播到 stdout

---

## 错误响应

Plugin 出错时，返回空变更，在 logs 里说明原因：

```json
{
  "changes": [],
  "logs": ["ERROR: health_decay failed: division by zero"]
}
```

Core 会继续执行 Pipeline 的下一步，不会因为单个 Plugin 出错而停止。

---

## Plugin 的元数据（可选）

在文件顶部可以声明元数据，帮助 Core 做优化：

```python
PLUGIN_META = {
    "name": "health_decay",
    "version": "1.0",
    "reads": ["npc.health", "npc.age", "world.season"],
    "writes": ["npc.health", "world.events"],
    "description": "NPC 每日健康衰减"
}
```

这是可选的，不声明也能正常运行。
