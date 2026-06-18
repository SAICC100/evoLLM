"""
Builder - 把 Proposer 的假设翻译成可执行的代码或 Prompt 文件。
写入 workspace/staging/，不直接写 live/。

输入：workspace/proposals/prop_N.json（status=pending）
输出：workspace/staging/{plugins|prompts|pipelines}/目标文件
     同时更新 proposal 的 status=built
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from base import AgentBase, WORKSPACE, LIVE

logger = logging.getLogger("builder")


def _extract_code(content: str) -> str:
    """
    从 LLM 输出中提取 Python 代码。
    兼容各种格式：```python、```Python、```、无代码块。
    """
    # 尝试各种代码块格式
    for pattern in [
        r"```python\s*(.*?)```",   # 标准格式
        r"```Python\s*(.*?)```",   # 大写
        r"```py\s*(.*?)```",       # 缩写
        r"```\s*(.*?)```",         # 无语言标注
    ]:
        m = re.search(pattern, content, re.DOTALL)
        if m:
            code = m.group(1).strip()
            # 排除空块或纯说明文字（必须含 def 或 import）
            if "def " in code or "import " in code:
                return code

    # 无代码块：整体当作代码，去掉明显的说明行
    lines = content.strip().splitlines()
    code_lines = []
    for line in lines:
        stripped = line.strip()
        # 跳过看起来是说明文字的行（中文开头、非代码）
        if stripped and not stripped.startswith("#") and \
           any(c in stripped for c in ["def ", "import ", "class ", "    ", "return", "if ", "for "]):
            code_lines = lines  # 整体保留
            break
        elif stripped.startswith(("import ", "from ", "def ", "class ", "#")):
            code_lines = lines
            break

    return "\n".join(code_lines).strip() if code_lines else content.strip()

PLUGIN_SYSTEM_PROMPT = """你是一个 Python 函数生成器，专门编写 evo-core 的 Plugin 文件。

Plugin 规范：
- 文件顶部有 docstring 说明功能
- 包含 run(context: dict) -> dict 函数
- context 是只读的世界状态快照
- 返回 {"changes": [...], "logs": [...]}
- changes 格式：{"path": "key", "op": "set|add|append|remove", "value": ...}
- 不能有网络调用、文件 IO、全局状态
- 在 __main__ 中读取 stdin，调用 run()，输出 stdout

示例 Plugin：
```python
#!/usr/bin/env python3
\"\"\"health_decay: NPC 每日健康衰减\"\"\"
import sys, json

def run(context: dict) -> dict:
    npc = context.get("data", {}).get("npc", {})
    age = npc.get("age", 20)
    decay = 2 if age > 60 else 1
    return {
        "changes": [{"path": "npc.health", "op": "add", "value": -decay}],
        "logs": [f"health -{decay}"]
    }

if __name__ == "__main__":
    data = json.loads(sys.stdin.read())
    print(json.dumps(run(data["context"])))
```

只输出完整的 Python 文件内容，不要有额外解释。"""


class Builder(AgentBase):
    name = "builder"

    def run(self, proposal_id: str) -> bool:
        prop_path = WORKSPACE / "proposals" / f"{proposal_id}.json"
        if not prop_path.exists():
            logger.error(f"提案不存在: {proposal_id}")
            return False

        prop = self.read_json(prop_path)
        if prop.get("status") != "pending":
            return False

        change_type = prop["change_type"]
        target_file = prop["target_file"]
        hypothesis = prop["hypothesis"]

        try:
            if change_type == "plugin":
                success = self._build_plugin(prop)
            elif change_type == "prompt":
                success = self._build_prompt(prop)
            elif change_type == "pipeline":
                success = self._build_pipeline(prop)
            else:
                logger.error(f"未知 change_type: {change_type}")
                return False

            if success:
                prop["status"] = "built"
                prop["staging_path"] = str(
                    WORKSPACE / "staging" / f"{change_type}s" / target_file
                )
                self.write_json(prop_path, prop)
                logger.info(f"Builder 完成: {proposal_id} -> {target_file}")
            return success

        except Exception as e:
            logger.error(f"Builder 失败 {proposal_id}: {e}")
            return False

    def _build_plugin(self, prop: dict) -> bool:
        # 读取已有的同名 Plugin 作为参考
        existing = ""
        live_path = LIVE / "plugins" / prop["target_file"]
        staging_path = WORKSPACE / "staging" / "plugins" / prop["target_file"]
        if live_path.exists():
            existing = f"\n现有代码供参考（需要在此基础上改进）：\n```python\n{live_path.read_text()}\n```"

        content = self.llm([
            {"role": "system", "content": PLUGIN_SYSTEM_PROMPT},
            {"role": "user", "content": f"""
目标文件：{prop['target_file']}
改进思路：{prop['hypothesis']}
预期效果：{prop['expected_improvement']}
{existing}

请生成完整的 Plugin 文件。"""}
        ], temperature=0.3)

        code = _extract_code(content)

        # 语法检查失败则重试一次，要求更严格的格式
        try:
            compile(code, prop["target_file"], "exec")
        except SyntaxError as e:
            logger.warning(f"第一次生成语法错误({e})，重试...")
            retry = self.llm([
                {"role": "system", "content": PLUGIN_SYSTEM_PROMPT},
                {"role": "user", "content": f"""上次生成的代码有语法错误：{e}
请重新生成，只输出纯 Python 代码，用```python 和 ``` 包裹，不要任何说明文字。

目标文件：{prop['target_file']}
改进思路：{prop['hypothesis']}"""}
            ], temperature=0.1)
            code = _extract_code(retry)
            try:
                compile(code, prop["target_file"], "exec")
            except SyntaxError as e2:
                logger.error(f"重试后仍有语法错误: {e2}")
                return False

        self.write_file(staging_path, code)
        return True

    def _build_prompt(self, prop: dict) -> bool:
        existing = ""
        live_path = LIVE / "prompts" / prop["target_file"]
        staging_path = WORKSPACE / "staging" / "prompts" / prop["target_file"]
        if live_path.exists():
            existing = f"\n现有 Prompt：\n{live_path.read_text()}"

        content = self.llm([{"role": "user", "content": f"""
请生成一个 Prompt 文件（纯文本，供 LLM 调用时使用）。
目标文件：{prop['target_file']}
改进思路：{prop['hypothesis']}
{existing}

只输出 Prompt 文本内容，不要任何包装。"""}], temperature=0.5)

        self.write_file(staging_path, content.strip())
        return True

    def _build_pipeline(self, prop: dict) -> bool:
        live_plugins = [p.stem for p in (LIVE / "plugins").glob("*.py")]
        staging_path = WORKSPACE / "staging" / "pipelines" / prop["target_file"]

        content = self.llm([{"role": "user", "content": f"""
请生成一个 Pipeline YAML 文件，定义 Plugin 的执行顺序。
目标文件：{prop['target_file']}
改进思路：{prop['hypothesis']}
当前可用 Plugin：{live_plugins}

Pipeline 格式：
```yaml
name: pipeline_name
steps:
  - plugin: plugin_name
  - plugin: another_plugin
    after: plugin_name
    condition: "some.condition"
```

只输出 YAML 内容。"""}], temperature=0.3)

        import re
        m = re.search(r"```yaml\s*(.*?)```", content, re.DOTALL)
        yaml_content = m.group(1).strip() if m else content.strip()

        self.write_file(staging_path, yaml_content)
        return True

    def run_pending(self, max_count: int = 0) -> int:
        """处理 pending 状态的提案，max_count=0 表示全部处理。"""
        proposals_dir = WORKSPACE / "proposals"
        count = 0
        for f in sorted(proposals_dir.glob("prop_*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            if max_count and count >= max_count:
                break
            prop = self.read_json(f)
            if prop.get("status") == "pending":
                if self.run(prop["id"]):
                    count += 1
        return count


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        Builder().run(sys.argv[1])
    else:
        n = Builder().run_pending()
        print(f"Builder 处理了 {n} 个提案")
