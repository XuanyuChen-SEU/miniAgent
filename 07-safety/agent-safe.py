"""
第七阶段：安全防线

三道最小防线：
1) 黑名单：直接拦截高危命令
2) 人工确认：执行前要求用户允许（可 --auto 跳过）
3) 输出截断：避免超长工具输出塞爆上下文

说明：
该实现提供最小安全控制能力，不等同于完整沙箱。
"""

import json
import os
import re
import subprocess
import sys

from openai import OpenAI


# 基础客户端初始化。
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), base_url=os.environ.get("OPENAI_BASE_URL"))
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
# 默认需要人工确认；传 --auto 才会自动放行。
AUTO_APPROVE = False
# 工具输出最大字符数，防止上下文被超长日志撑爆。
MAX_OUTPUT = 4000

DANGEROUS = [
    r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+|.*--no-preserve-root)",
    r"\bmkfs\b",
    r"\bdd\s+.*of\s*=\s*/dev/",
    r"\bcurl\b.*\|\s*(ba)?sh",
    r"\bwget\b.*\|\s*(ba)?sh",
]

TOOLS = [
    {"type": "function", "function": {"name": "bash", "description": "run shell", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}}
]


def is_dangerous(command: str) -> tuple[bool, str]:
    # 只要匹配任一高危模式就拦截。
    for pattern in DANGEROUS:
        if re.search(pattern, command):
            return True, pattern
    return False, ""


def ask_confirmation(command: str) -> bool:
    if AUTO_APPROVE:
        return True
    # 默认回车视为允许，输入 n/no 拒绝执行。
    answer = input(f"\n允许执行命令？\n{command}\n[Y/n]: ").strip().lower()
    return answer in ("", "y", "yes")


def truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT:
        return text
    # 中间截断：同时保留开头和结尾，便于看错误上下文。
    half = MAX_OUTPUT // 2
    return text[:half] + f"\n\n...[truncated from {len(text)} chars]...\n\n" + text[-half:]


def bash(command: str) -> str:
    # 防线 1：黑名单拦截
    blocked, pattern = is_dangerous(command)
    if blocked:
        return f"blocked dangerous command (pattern={pattern}): {command}"
    # 防线 2：人工确认
    if not ask_confirmation(command):
        return "user denied command"
    try:
        p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        # 防线 3：输出截断
        return truncate(p.stdout + p.stderr)
    except Exception as e:
        return f"error: {e}"


def run(task: str) -> str:
    messages = [
        {"role": "system", "content": "You are a safe coding assistant. If command fails/blocked, choose alternatives."},
        {"role": "user", "content": task},
    ]
    # 安全版仍沿用标准 agent 回路：模型提议 -> 工具执行 -> 结果回填。
    for _ in range(12):
        r = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        m = r.choices[0].message
        messages.append(m)
        if not m.tool_calls:
            return m.content or ""
        for tc in m.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            out = bash(**args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
    return "max iterations reached"


if __name__ == "__main__":
    AUTO_APPROVE = "--auto" in sys.argv
    argv = [x for x in sys.argv[1:] if x != "--auto"]
    if not argv:
        print("Usage: python 07-safety/agent-safe.py [--auto] 'your task'")
        sys.exit(1)
    print(run(" ".join(argv)))
