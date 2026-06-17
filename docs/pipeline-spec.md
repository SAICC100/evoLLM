# Pipeline 配置规范

Pipeline 定义 Plugin 的组合关系和执行顺序，是系统中另一种可进化产物。

---

## 基本结构

```yaml
name: npc_daily
description: "NPC 每日行动循环"
version: "1.0"

# 触发条件（可选，默认每轮都触发）
trigger:
  every: 1          # 每 N 轮触发一次

steps:
  - plugin: age_advance
    description: "年龄推进"

  - plugin: health_decay
    description: "健康衰减"
    after: age_advance       # 依赖关系，age_advance 完成后才执行

  - plugin: death_check
    description: "死亡检测"
    after: health_decay
    condition: "npc.health <= 0"   # 条件表达式，false 时跳过
```

---

## 步骤字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `plugin` | string | 是 | Plugin 文件名（不含 .py） |
| `description` | string | 否 | 步骤说明 |
| `after` | string/list | 否 | 依赖的步骤名，支持多个 |
| `condition` | string | 否 | 执行条件，对 context 求值，false 时跳过 |
| `timeout_ms` | int | 否 | 覆盖默认超时，默认 5000 |
| `on_error` | string | 否 | 出错时的行为：skip（默认）/ stop |

---

## 并行执行

没有 `after` 依赖的步骤会并行执行：

```yaml
steps:
  # 这三个并行执行
  - plugin: age_advance
  - plugin: mood_update
  - plugin: gold_interest

  # 等上面都完成后执行
  - plugin: death_check
    after: [age_advance, mood_update, gold_interest]
```

---

## 多 Pipeline

一个系统可以有多个 Pipeline，Core 按触发条件依次执行：

```
live/pipelines/
  npc_daily.yaml       # 每轮执行，处理 NPC 行动
  world_events.yaml    # 每 7 轮执行，生成世界事件
  economy.yaml         # 每 30 轮执行，经济周期
  evolution_trigger.yaml  # 每轮执行，触发进化层
```

Pipeline 的执行顺序由文件名字母序决定，可以用数字前缀控制：

```
01_npc_daily.yaml
02_world_events.yaml
03_economy.yaml
99_evolution_trigger.yaml
```

---

## 组合关系也可以进化

Pipeline 文件本身经过 staging → Judge → live 的流程，Agent 可以：

- 新增 Pipeline（引入新的执行逻辑）
- 修改步骤顺序（优化执行效率）
- 增删条件（改变触发规则）
- 重组已有 Plugin（不写新代码，只改编排）

**重组已有 Plugin 是成本最低的改进方式。**
