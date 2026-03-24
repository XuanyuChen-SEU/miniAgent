"""
第四阶段：SubAgent

核心思路：
- 把“委派”也做成一个工具（subagent）。
- subagent 启动独立消息上下文，干完返回结果给主 agent。

说明：
- 主 agent 负责编排，subagent 负责子任务执行
- 独立上下文可降低不同任务之间的上下文干扰
"""

import json
import os
import subprocess
import sys

from openai import OpenAI


# 基础模型客户端初始化。
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), base_url=os.environ.get("OPENAI_BASE_URL"))
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def bash(command: str) -> str:
    p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
    return p.stdout + p.stderr


def subagent(role: str, task: str) -> str:
    # subagent 使用独立 messages，避免污染主 agent 的中间上下文。
    sub_messages = [
        {"role": "system", "content": f"You are a {role}. Be concise and finish the assigned task only."},
        {"role": "user", "content": task},
    ]
    # 避免 subagent 再次调用 subagent（递归委派会让流程复杂度激增）。
    sub_tools = [t for t in TOOLS if t["function"]["name"] != "subagent"]
    for _ in range(6):
        r = client.chat.completions.create(model=MODEL, messages=sub_messages, tools=sub_tools)
        m = r.choices[0].message
        sub_messages.append(m)
        if not m.tool_calls:
            return m.content or ""
        for tc in m.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments or "{}")
            fn = FUNCTIONS.get(name)
            # 容错：遇到未知子工具时返回错误文本，而不是抛异常中断主流程。
            out = fn(**args) if fn else f"Unknown sub tool: {name}"
            sub_messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
    return "subagent max iterations reached"


TOOLS = [
    {"type": "function", "function": {"name": "bash", "description": "run shell", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "subagent", "description": "delegate task to a specialist", "parameters": {"type": "object", "properties": {"role": {"type": "string"}, "task": {"type": "string"}}, "required": ["role", "task"]}}},
]
FUNCTIONS = {"bash": bash, "subagent": subagent}


def run(task: str) -> str:
    # 主 agent 的角色是“编排器”：决定何时自己做、何时委派给 subagent。
    messages = [
        {"role": "system", "content": "You are an orchestrator. Use subagent when specialization helps."},
        {"role": "user", "content": task},
    ]
    for _ in range(8):
        r = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        m = r.choices[0].message
        messages.append(m)
        if not m.tool_calls:
            return m.content or ""
        for tc in m.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments or "{}")
            out = FUNCTIONS[name](**args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
    return "max iterations reached"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 04-subagent/agent-subagent.py 'your task'")
        sys.exit(1)
    print(run(" ".join(sys.argv[1:])))
