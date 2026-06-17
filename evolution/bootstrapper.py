"""
Bootstrapper - 冷启动 Agent，只运行一次。

读取 goal.yaml，生成最小可运行的 Plugin 集和 Pipeline，
直接写入 live/（唯一一次特权写入，跳过 Judge）。

目标：让 Core 能跑起来产生数据，不追求功能完善。
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

from base import AgentBase, LIVE

logger = logging.getLogger("bootstrapper")


class Bootstrapper(AgentBase):
    name = "bootstrapper"

    def run(self) -> None:
        goal = self.load_goal()
        if not goal:
            logger.error("goal.yaml 不存在或为空，请先创建 live/config/goal.yaml")
            sys.exit(1)

        # 检查是否已经初始化过
        if any((LIVE / "plugins").glob("*.py")):
            logger.info("live/plugins/ 已有文件，跳过冷启动")
            return

        logger.info(f"开始冷启动：{goal.get('name', '未命名系统')}")
        logger.info("目标：" + goal.get("description", "")[:100])

        # 第一步：让 LLM 理解目标，设计最小 Plugin 集
        plugin_plan = self._plan_plugins(goal)

        # 第二步：生成每个 Plugin
        for plugin_spec in plugin_plan:
            self._generate_plugin(plugin_spec, goal)

        # 第三步：生成 Pipeline 把 Plugin 串起来
        self._generate_pipeline(plugin_plan, goal)

        logger.info(f"冷启动完成，生成了 {len(plugin_plan)} 个 Plugin")
        logger.info("Core 启动后将开始产生数据，进化层将接管后续迭代")

    def _plan_plugins(self, goal: dict) -> list[dict]:
        prompt = f"""你是一个系统设计专家。给定一个系统目标，设计最小可运行的 Plugin 集合。

系统目标：
{goal}

原则：
1. 最少的 Plugin，让系统能跑起来产生可观测的数据
2. 不追求功能完善，只追求能产生数据
3. 每个 Plugin 职责单一
4. 一般 3~5 个 Plugin 就够了

输出 JSON 数组，描述需要创建哪些 Plugin：
[
  {{
    "filename": "xxx.py",
    "purpose": "这个 Plugin 做什么",
    "inputs": ["context.data.xxx 字段列表"],
    "outputs": ["写入哪些字段"]
  }}
]"""

        return self.llm_json([{"role": "user", "content": prompt}])

    def _generate_plugin(self, spec: dict, goal: dict) -> None:
        filename = spec["filename"]
        out_path = LIVE / "plugins" / filename

        prompt = f"""你是一个 Python 函数生成器，为 evo-core 框架编写 Plugin 文件。

Plugin 规范：
- 包含 run(context: dict) -> dict 函数
- context["data"] 是世界状态
- 返回 {{"changes": [...], "logs": [...]}}
- changes 格式：{{"path": "key", "op": "set|add|append|remove", "value": ...}}
- 在 __main__ 中读取 stdin，调用 run()，输出 stdout
- 不能有网络调用、文件 IO

要生成的 Plugin：
- 文件名：{filename}
- 用途：{spec['purpose']}
- 读取字段：{spec.get('inputs', [])}
- 写入字段：{spec.get('outputs', [])}

系统背景：{goal.get('description', '')}

只输出完整的 Python 文件内容（用```python包裹）。"""

        content = self.llm([{"role": "user", "content": prompt}], temperature=0.2)
        m = re.search(r"```python\s*(.*?)```", content, re.DOTALL)
        code = m.group(1).strip() if m else content.strip()

        try:
            compile(code, filename, "exec")
        except SyntaxError as e:
            logger.error(f"生成的 {filename} 语法错误: {e}，跳过")
            return

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(code, encoding="utf-8")
        logger.info(f"生成 Plugin: {filename}")

    def _generate_pipeline(self, plugin_plan: list[dict], goal: dict) -> None:
        filenames = [p["filename"].replace(".py", "") for p in plugin_plan]

        prompt = f"""请生成一个 Pipeline YAML 文件，把以下 Plugin 串联起来。

可用 Plugin：{filenames}
系统背景：{goal.get('description', '')}

Pipeline 格式：
```yaml
name: main
steps:
  - plugin: plugin_name
  - plugin: another_plugin
    after: plugin_name
```

只输出 YAML 内容（用```yaml包裹）。"""

        content = self.llm([{"role": "user", "content": prompt}], temperature=0.2)
        m = re.search(r"```yaml\s*(.*?)```", content, re.DOTALL)
        yaml_content = m.group(1).strip() if m else content.strip()

        out_path = LIVE / "pipelines" / "01_main.yaml"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(yaml_content, encoding="utf-8")
        logger.info("生成 Pipeline: 01_main.yaml")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    Bootstrapper().run()
