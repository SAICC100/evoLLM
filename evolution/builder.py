"""
Builder - 把 Proposer 的假设翻译成可执行的代码或 Prompt 文件。

流程：
1. 生成代码 → 写入 staging/
2. 备份 live/ 中的旧版本 → backup/
3. 直接 deploy 到 live/（让 Core 立即执行新版本）
4. 记录 deployed_tick，供 Judge 观察对比

Judge 在观察期结束后：
- 有效 → 删除 backup（保留新版本）
- 无效 → 从 backup 恢复旧版本
"""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from base import AgentBase, WORKSPACE, LIVE

logger = logging.getLogger("builder")

BACKUP_DIR = LIVE / "backup"

PLUGIN_SYSTEM_PROMPT = """你是一个 Python 函数生成器，专门编写 evo-core 的 Plugin 文件。

Plugin 规范：
- 文件顶部有 docstring 说明功能
- 包含 run(context: dict) -> dict 函数
- context["data"] 是只读的世界状态，包含 npcs（列表）、tribes（列表）、world（dict）
- 返回 {"changes": [...], "logs": [...]}
- changes 元素格式：{"path": str, "op": "set|add|append|remove", "value": any}
- 更新单个 NPC 属性的 path 格式：npcs[id=npc_001].health
- 在 __main__ 中读取 stdin JSON，调用 run()，print stdout JSON
- 不能有网络调用、文件 IO、全局可变状态
- 所有异常 try/except 捕获，写入 logs，不抛出

示例 Plugin（NPC健康衰减）：
```python
#!/usr/bin/env python3
\"\"\"health_decay: NPC 每日健康衰减\"\"\"
import sys, json, random

def run(context: dict) -> dict:
    data = context.get("data", {})
    npcs = data.get("npcs", [])
    season = data.get("world", {}).get("current_season", "spring")
    changes, logs = [], []
    for npc in npcs:
        if not isinstance(npc, dict): continue
        npc_id = npc.get("id", "")
        age = npc.get("age", 20)
        decay = 2 if age > 60 else 1
        if season == "winter": decay *= 2
        changes.append({"path": f"npcs[id={npc_id}].health", "op": "add", "value": -decay})
        logs.append(f"{npc.get('name','?')} health -{decay}")
    return {"changes": changes, "logs": logs[:5]}

if __name__ == "__main__":
    data = json.loads(sys.stdin.read())
    print(json.dumps(run(data["context"])))
```

只输出完整的 Python 文件，用```python 包裹。"""


def _extract_code(content: str) -> str:
    """从 LLM 输出中提取 Python 代码，兼容多种格式。"""
    for pattern in [
        r"```python\s*(.*?)```",
        r"```Python\s*(.*?)```",
        r"```py\s*(.*?)```",
        r"```\s*(.*?)```",
    ]:
        m = re.search(pattern, content, re.DOTALL)
        if m:
            code = m.group(1).strip()
            if "def " in code or "import " in code:
                return code
    return content.strip()


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
                # 部署：备份旧版本 → deploy 到 live
                deployed_tick = self._deploy(change_type, target_file)
                prop["status"] = "deployed"
                prop["deployed_tick"] = deployed_tick
                prop["live_path"] = str(LIVE / f"{change_type}s" / target_file)
                prop["backup_path"] = str(BACKUP_DIR / f"{change_type}s" / target_file)
                self.write_json(prop_path, prop)
                logger.info(f"Builder deployed: {proposal_id} -> live/{change_type}s/{target_file} (tick={deployed_tick})")
            return success

        except Exception as e:
            logger.error(f"Builder 失败 {proposal_id}: {e}")
            return False

    def _deploy(self, change_type: str, target_file: str) -> int:
        """备份旧版本，把 staging 文件 deploy 到 live。返回当前 tick。"""
        staging_path = WORKSPACE / "staging" / f"{change_type}s" / target_file
        live_path = LIVE / f"{change_type}s" / target_file
        backup_path = BACKUP_DIR / f"{change_type}s" / target_file

        # 备份旧版本
        if live_path.exists():
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(live_path, backup_path)

        # Deploy
        live_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staging_path, live_path)
        staging_path.unlink(missing_ok=True)

        # 获取当前 tick（从最新快照推断）
        obs_dir = WORKSPACE / "observations"
        files = sorted(obs_dir.glob("tick_*.json"), reverse=True)
        return int(files[0].stem.replace("tick_", "")) if files else 0

    def _build_plugin(self, prop: dict) -> bool:
        staging_path = WORKSPACE / "staging" / "plugins" / prop["target_file"]

        # 读取当前 live 版本作为参考
        existing = ""
        live_path = LIVE / "plugins" / prop["target_file"]
        if live_path.exists():
            existing = f"\n当前版本（需要在此基础上改进）：\n```python\n{live_path.read_text()[:2000]}\n```"

        content = self.llm([
            {"role": "system", "content": PLUGIN_SYSTEM_PROMPT},
            {"role": "user", "content": f"""目标文件：{prop['target_file']}
改进思路：{prop['hypothesis']}
预期效果：{prop['expected_improvement']}
{existing}

请生成完整的 Plugin 文件。"""}
        ], temperature=0.3)

        code = _extract_code(content)

        try:
            compile(code, prop["target_file"], "exec")
        except SyntaxError as e:
            logger.warning(f"第一次生成语法错误({e})，重试...")
            retry = self.llm([
                {"role": "system", "content": PLUGIN_SYSTEM_PROMPT},
                {"role": "user", "content": f"""上次生成的代码有语法错误：{e}
请重新生成，只输出纯 Python 代码，用```python 和 ``` 包裹，不要任何说明。

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
        staging_path = WORKSPACE / "staging" / "prompts" / prop["target_file"]
        existing = ""
        live_path = LIVE / "prompts" / prop["target_file"]
        if live_path.exists():
            existing = f"\n现有 Prompt：\n{live_path.read_text()}"

        content = self.llm([{"role": "user", "content": f"""
生成一个 Prompt 文件（纯文本，供 LLM 调用时使用）。
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
生成一个 Pipeline YAML 文件，定义 Plugin 的执行顺序。
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
```
只输出 YAML 内容。"""}], temperature=0.3)

        m = re.search(r"```yaml\s*(.*?)```", content, re.DOTALL)
        yaml_content = m.group(1).strip() if m else content.strip()
        self.write_file(staging_path, yaml_content)
        return True

    def run_pending(self, max_count: int = 0) -> int:
        """处理 pending 状态的提案，max_count=0 表示全部处理。"""
        proposals_dir = WORKSPACE / "proposals"
        count = 0
        for f in sorted(proposals_dir.glob("prop_*.json"),
                        key=lambda x: x.stat().st_mtime, reverse=True):
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
