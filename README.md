# evo-core

> 一个目标驱动、可自主进化的系统框架

---

## 核心理念

给框架一个目标描述，Agent 会自动生成实现、观察效果、持续迭代，直到达成目标。

系统成长的方式和初创团队一样：一开始只有模糊的目标，具体的实现由 Agent 一点点长出来。没有预设的功能，只有可观测的指标和不断尝试的实验。

**最小可观测循环**是系统的生命线：

```
能跑 → 产生数据 → 发现差距 → 尝试改进 → 更好地跑
```

这个循环一旦转起来就不能断。架构的所有设计都围绕"保证循环永不断裂"展开。

---

## 架构总览

```
┌──────────────────────────────────────────────────────┐
│  目标层  goal.yaml                                    │
│  人工定义目标和评估指标，Agent 可提议修改，人审批       │
└─────────────────────┬────────────────────────────────┘
                      │ 目标分数驱动优先级
┌─────────────────────▼────────────────────────────────┐
│  进化层  evolution/                                   │
│                                                      │
│  Bootstrapper  (冷启动，只跑一次)                     │
│       ↓                                              │
│  Observer → Analyst → Proposer → Builder → Judge     │
│                                                      │
│  共享工作区：workspace/                               │
│  observations/ gaps/ proposals/ staging/ verdicts/   │
└─────────────────────┬────────────────────────────────┘
                      │ 只有通过 Judge 的才能进入
┌─────────────────────▼────────────────────────────────┐
│  执行层  core/  (Go，永不修改)                        │
│                                                      │
│  Kernel: Scheduler / PipelineLoader / PluginRunner   │
│          StateStore / EvolutionTrigger               │
│                                                      │
│  live/                                               │
│    plugins/    纯函数，每次从磁盘读，不缓存            │
│    prompts/    纯文本，每次从磁盘读，不缓存            │
│    pipelines/  编排文件，定义 Plugin 的组合关系        │
│    config/     参数配置                               │
└──────────────────────────────────────────────────────┘

独立服务：
  llm-gateway/  统一 LLM 调用入口，限流/重试/fallback
  state-store/  DuckDB，持久化世界状态
```

---

## 三层的设计原则

**越底层越稳定，越顶层越易变。**

- 执行层（Core）：人工编写，永不自动修改，出问题容易排查
- 进化层（Agent）：框架固定，内容由 Agent 自主生成和更新
- 目标层：人工定义，Agent 可提议调整，人审批后生效

---

## 目录结构

```
evo-core/
├── core/                   # Go 实现的执行内核
│   ├── main.go
│   ├── scheduler/          # 触发每轮循环
│   ├── pipeline/           # 加载和执行 Pipeline
│   ├── plugin/             # subprocess 执行 Plugin
│   ├── state/              # DuckDB 状态读写
│   └── trigger/            # 通知进化层
│
├── evolution/              # Python 实现的进化层 Agent
│   ├── bootstrapper.py     # 冷启动，生成第一批 Plugin
│   ├── observer.py         # 观察数据，输出事实
│   ├── analyst.py          # 量化与目标的差距
│   ├── proposer.py         # 提出改进假设
│   ├── builder.py          # 将假设转化为代码/prompt
│   ├── judge.py            # 评估实验效果，决定固化或回滚
│   └── scheduler.py        # 进化层自己的调度
│
├── llm-gateway/            # Python 实现的 LLM 网关服务
│   └── gateway.py
│
├── live/                   # 当前生效的 Plugin/Prompt/Pipeline
│   ├── plugins/
│   ├── prompts/
│   ├── pipelines/
│   └── config/
│       └── goal.yaml       # 目标定义
│
├── workspace/              # 进化层的工作区（文件系统消息总线）
│   ├── observations/       # Observer 输出
│   ├── gaps/               # Analyst 输出
│   ├── proposals/          # Proposer 输出
│   ├── staging/            # Builder 输出（待验证）
│   │   ├── plugins/
│   │   ├── prompts/
│   │   └── pipelines/
│   └── verdicts/           # Judge 输出
│
├── docs/
│   ├── architecture.md     # 本文
│   ├── plugin-spec.md      # Plugin 开发规范
│   ├── pipeline-spec.md    # Pipeline 配置规范
│   └── goal-spec.md        # 目标定义规范
│
└── scripts/
    ├── init.sh             # 项目初始化
    └── start.sh            # 启动所有服务
```

---

## 关键设计决策

### 1. Plugin 是纯函数

Plugin 通过 subprocess 执行，Core 通过 stdin/stdout 传递数据：

```
Core → Plugin stdin:
{
  "context": { ...世界快照... },
  "timeout_ms": 5000
}

Plugin → Core stdout:
{
  "changes": [
    { "path": "npc.health", "op": "add", "value": -5 }
  ],
  "logs": ["health decayed by 5"]
}
```

Plugin 不能直接写数据库，不能调用其他 Plugin，只能返回声明式的变更意图。Core 负责把多个 Plugin 的变更合并应用。

### 2. Pipeline 定义组合关系

Plugin 之间的组合关系由 Agent 决定，写在 Pipeline 文件里：

```yaml
# live/pipelines/npc_daily.yaml
name: npc_daily
steps:
  - plugin: age_advance
  - plugin: health_decay
    after: age_advance
  - plugin: death_check
    after: health_decay
    condition: "npc.health < 0"
```

Pipeline 本身也是可进化的产物，Agent 可以新增、修改、重组 Pipeline。

### 3. 文件系统作为消息总线

进化层各 Agent 之间不直接调用，通过写文件和读文件通信：

```
Observer 写 → workspace/observations/day_N.json
Analyst  读 ↑，写 → workspace/gaps/day_N.json
Proposer 读 ↑，写 → workspace/proposals/prop_N.json
Builder  读 ↑，写 → workspace/staging/plugins/xxx.py
Judge    读 ↑，写 → workspace/verdicts/prop_N.json
                      并触发 staging → live 的移动
```

任何一个 Agent 挂了，其他的继续跑。每一步都有中间产物，可以回溯。

### 4. 三种可进化产物

Agent 的产出只有三个落点：

| 类型 | 位置 | 作用 |
|------|------|------|
| Plugin | `live/plugins/` | 具体功能实现 |
| Prompt | `live/prompts/` | LLM 调用指令 |
| Pipeline | `live/pipelines/` | Plugin 的组合编排 |

Agent 不能修改 Core 代码，不能直接操作数据库，没有第四个落点。

### 5. 所有变更必须经过实验验证

```
Builder 产出 → staging/（待验证区）
Judge 观察 N 轮后评估效果
效果达标 → 移入 live/（固化）
效果不达标 → 删除 staging/ 中的文件（回滚）
```

没有"紧急部署"。Core 出问题找人，不找 Agent。

---

## 冷启动流程

```
1. 人工编写 live/config/goal.yaml（目标定义）
2. 启动 Core（此时 live/plugins/ 为空，Core 空转）
3. 触发 Bootstrapper
4. Bootstrapper 读取 goal.yaml，生成最小可运行 Plugin 集和 Pipeline
5. Bootstrapper 直接写入 live/（唯一一次特权写入，跳过 Judge）
6. Core 开始正常运行，产生第一批数据
7. 进化层流水线启动，开始观察和迭代
```

Bootstrapper 生成的第一批 Plugin 不需要好，只需要能让系统跑起来、产生可观测的数据。

---

## 技术栈

| 层 | 语言 | 理由 |
|----|------|------|
| Core | Go | 稳定、并发好、单二进制部署、Plugin 隔离靠 subprocess |
| Plugin | Python | Agent 写代码的首选，生态丰富 |
| 进化层 Agent | Python | LLM 调用、文件操作、数据分析 |
| LLM Gateway | Python | 灵活，策略经常变 |
| 数据存储 | DuckDB | 本地优先，无需部署，分析查询性能好 |
| 消息总线 | 文件系统 | 最简单，天然持久化，易于调试 |

---

## 与传统架构的区别

| | 传统软件 | evo-core |
|---|---|---|
| 功能从哪来 | 人写代码预设 | 实验验证后固化 |
| 如何扩展 | 人添加模块 | Agent 提案 + 实验 |
| bug 怎么修 | 人工修复 | 替换 Plugin，旧版自动回滚 |
| 方向谁决定 | 产品/工程师 | 目标层的指标差距 |
| 什么永远不变 | 业务逻辑 | 调度/调用/存储的基础设施 |
