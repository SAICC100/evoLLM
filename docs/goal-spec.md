# 目标定义规范

目标是系统成长的北极星，驱动进化层的优先级判断。

---

## 文件位置

`live/config/goal.yaml`

---

## 结构

```yaml
name: "真实的世界模拟"
description: |
  用户设定世界背景和基础参数，系统自动演绎一个有生命力的虚拟世界。
  世界中的 NPC 有自己的生老病死，会产生社交、冲突、贸易等多样化事件。

version: "1.0"

# 评估指标
metrics:
  - id: population_vitality
    description: "人口有自然流动，每 30 天内应有出生和死亡"
    query: "SELECT SUM(value) FROM events WHERE type IN ('death','birth') AND day > {current_day} - 30"
    threshold: "> 5"
    weight: 0.3

  - id: event_diversity
    description: "事件类型不应高度集中，应覆盖多个领域"
    query: "SELECT COUNT(DISTINCT type) FROM events WHERE day > {current_day} - 7"
    threshold: "> 8"
    weight: 0.3

  - id: narrative_causality
    description: "叙事应包含因果关系，事件之间有关联"
    query: "SELECT AVG(has_cause) FROM narratives WHERE day > {current_day} - 7"
    threshold: "> 0.4"
    weight: 0.4

# 总分计算方式
scoring: weighted_average

# 达标定义（总分超过此值视为"已达标"）
target_score: 0.8
```

---

## 指标字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 唯一标识，进化层用这个引用指标 |
| `description` | string | 人类可读的说明 |
| `query` | string | DuckDB SQL，支持 `{current_day}` 占位符 |
| `threshold` | string | 阈值表达式：`> N`、`< N`、`>= N` |
| `weight` | float | 在总分中的权重，所有权重之和应为 1.0 |

---

## 总分计算

每轮循环结束后，Analyst 计算每个指标的得分（0~1），再按权重汇总：

```
指标得分 = 当前值 / 阈值目标值（超过 1.0 时截断为 1.0）
总分 = Σ(指标得分 × 权重)
```

Proposer 优先攻得分最低的指标。

---

## 目标演化

系统达标后（总分 > target_score），进入维护模式：
- 进化层降低频率，只处理指标回退的情况
- Agent 可以提议提高某个指标的阈值，或引入新指标
- 所有目标变更需要人工审批（在 workspace/goal_proposals/ 目录下等待）

人工审批后，将新的 goal.yaml 写入 `live/config/`，系统自动以新目标继续进化。

---

## 冷启动时的目标

冷启动时，Bootstrapper 会读取 goal.yaml，理解系统的目的，据此生成最小可运行的 Plugin 集。

**目标写得越清晰，Bootstrapper 生成的初始 Plugin 质量越高。**

建议在 description 里说明：
- 系统是做什么的（领域）
- 核心实体有哪些（NPC、事件、世界状态）
- 最重要的行为是什么（成长、交互、演化）
