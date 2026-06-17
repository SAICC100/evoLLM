#!/usr/bin/env python3
"""
单独重新生成一个失败的 Plugin。
用法：python3 scripts/regen_plugin.py <filename>
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "evolution"))
from base import AgentBase, LIVE

SYSTEM = """你是 Python 代码生成器，生成 evo-core Plugin 文件。

严格规范：
1. 文件只包含 import、常量、函数定义、if __name__ == "__main__" 块
2. run(context: dict) -> dict 是唯一入口
3. 返回格式固定：{"changes": [...], "logs": [...]}
4. changes 元素格式：{"path": str, "op": "set|add|append|remove", "value": any}
5. if __name__ == "__main__": 读 stdin JSON，调 run()，print stdout JSON
6. 禁止网络调用、文件 IO、全局可变状态
7. 所有异常 try/except 捕获，写入 logs，不抛出
8. 直接输出代码，不要任何解释，只有 ```python ... ``` 块"""


def regen(filename: str, purpose: str, inputs: list, outputs: list, background: str = "") -> None:
    b = AgentBase()
    b.name = "regen"

    content = b.llm([
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"""生成文件：{filename}
用途：{purpose}
读取字段：{inputs}
写入字段：{outputs}
世界背景：{background}

输出完整 Python 文件，用```python 包裹。"""}
    ], temperature=0.2, max_tokens=3000)

    m = re.search(r"```python\s*(.*?)```", content, re.DOTALL)
    code = m.group(1).strip() if m else content.strip()

    try:
        compile(code, filename, "exec")
    except SyntaxError as e:
        print(f"语法错误: {e}\n前200字符:\n{code[:200]}")
        sys.exit(1)

    out = LIVE / "plugins" / filename
    out.write_text(code, encoding="utf-8")
    print(f"生成成功: {filename} ({len(code)} chars)")


if __name__ == "__main__":
    regen(
        filename="npc_daily_actions.py",
        purpose="NPC 每日行动：根据职业和健康状态从 [hunting, farming, patrol, trade, rest] 中选择一个行动，产生事件记录，并更新体力和金钱",
        inputs=["context.data.npcs（列表）", "context.data.world.season", "context.data.tribes"],
        outputs=["world.events（append 行动事件）", "npcs[i].energy（add）", "npcs[i].gold（add）"],
        background="3个部落：铁爪（战士/森林）、银月（智者/平原）、石心（工匠/山脉）。NPC字段：id, name, age, gender, occupation, health, energy, gold, tribe_id, position"
    )
