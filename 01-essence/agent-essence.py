"""
第一阶段：Agent 本质

目标：
1) 让模型自己决定是否调用工具
2) 我们执行工具，再把结果喂回模型
3) 重复直到模型直接给出答案

说明：
- 这个文件只保留最小闭环，便于逐步扩展。
- 核心流程均在代码注释中说明。
"""

import json
import os
import subprocess
import sys

from openai import OpenAI


# OpenAI 客户端：从环境变量中读取鉴权信息。
# - OPENAI_API_KEY: 你的 key
# - OPENAI_BASE_URL: 可选，自建网关/代理时使用
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url=os.environ.get("OPENAI_BASE_URL"),
)
# 默认模型可通过环境变量覆盖，便于你在不同模型之间切换实验。
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


# Step 1: 定义工具协议（给模型看的“菜单”）
# 这里的 JSON Schema 只描述“能做什么、参数是什么”，不会真正执行任何动作。
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
# 这些函数才是“真正会运行”的代码，模型只是在 tool_call 里请求调用它们。
def execute_bash(command: str) -> str:
    # shell=True 代表让系统 shell 来解释命令字符串，方便但也有注入风险（后续阶段会加安全防线）。
    result = subprocess.run(command, shell=True, text=True, capture_output=True, timeout=30)
    # 返回 stdout + stderr，便于模型拿到完整上下文（成功输出 + 报错信息）。
    return result.stdout + result.stderr


def read_file(path: str) -> str:
    # UTF-8 是最常见文本编码，避免中文读取乱码。
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path: str, content: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    # 工具返回简短确认文本，模型可据此继续下一步。
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
    # 每轮做三件事：
    # A. 调模型，看看是直接回答还是发起工具调用
    # B. 若有工具调用，程序执行工具并把结果回填
    # C. 继续下一轮，直到模型不再需要工具
    for _ in range(max_iterations):
        response = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        message = response.choices[0].message
        # 把模型这轮输出加入上下文，供后续轮次参考。
        messages.append(message)

        # 模型不再调用工具时，说明可以直接结束
        if not message.tool_calls:
            return message.content or ""

        for tool_call in message.tool_calls:
            fn_name = tool_call.function.name
            # tool_call.function.arguments 是 JSON 字符串，需要先反序列化成 dict。
            fn_args = json.loads(tool_call.function.arguments or "{}")
            print(f"[Tool] {fn_name}({fn_args})")

            fn = FUNCTIONS.get(fn_name)
            # 若模型调用了未知工具，给出可读报错，避免程序直接崩。
            result = fn(**fn_args) if fn else f"Unknown tool: {fn_name}"
            # 关键：以 role=tool 回填结果，并携带 tool_call_id 与该次调用对应。
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

    # 达到上限还没完成，说明任务太复杂或策略卡住。
    return "Max iterations reached."


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 01-essence/agent-essence.py 'your task'")
        sys.exit(1)
    print(run_agent(" ".join(sys.argv[1:])))
