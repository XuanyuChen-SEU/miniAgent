"""
第一阶段：Agent 本质

目标：
1) 让模型自己决定是否调用工具
2) 我们执行工具，再把结果喂回模型
3) 重复直到模型直接给出答案

说明：
- 这个文件只保留最小闭环，便于你后续逐步加功能。
- 核心思路都写在注释里，不依赖额外文档。
"""

import json
import os
import subprocess
import sys

from openai import OpenAI


client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url=os.environ.get("OPENAI_BASE_URL"),
)
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


# Step 1: 定义工具协议（给模型看的“菜单”）
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_bash",
            "description": "Execute a bash command",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write text to file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
]


# Step 2: 实现真实工具（给程序执行）
def execute_bash(command: str) -> str:
    result = subprocess.run(command, shell=True, text=True, capture_output=True, timeout=30)
    return result.stdout + result.stderr


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path: str, content: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"wrote: {path}"


FUNCTIONS = {
    "execute_bash": execute_bash,
    "read_file": read_file,
    "write_file": write_file,
}


def run_agent(task: str, max_iterations: int = 8) -> str:
    # Step 3: 初始化消息上下文
    messages = [
        {"role": "system", "content": "You are a concise coding assistant."},
        {"role": "user", "content": task},
    ]

    # Step 4: Agent 循环（模型 <-> 工具 <-> 模型）
    for _ in range(max_iterations):
        response = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        message = response.choices[0].message
        messages.append(message)

        # 模型不再调用工具时，说明可以直接结束
        if not message.tool_calls:
            return message.content or ""

        for tool_call in message.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments or "{}")
            print(f"[Tool] {fn_name}({fn_args})")

            fn = FUNCTIONS.get(fn_name)
            result = fn(**fn_args) if fn else f"Unknown tool: {fn_name}"
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

    return "Max iterations reached."


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 01-essence/agent-essence.py 'your task'")
        sys.exit(1)
    print(run_agent(" ".join(sys.argv[1:])))
