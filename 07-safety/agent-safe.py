"""
第七阶段：安全防线

三道最小防线：
1) 黑名单：直接拦截高危命令
2) 人工确认：执行前要求用户允许（可 --auto 跳过）
3) 输出截断：避免超长工具输出塞爆上下文
"""

import json
import os
import re
import subprocess
import sys

from openai import OpenAI


client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), base_url=os.environ.get("OPENAI_BASE_URL"))
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
AUTO_APPROVE = False
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
    for pattern in DANGEROUS:
        if re.search(pattern, command):
            return True, pattern
    return False, ""


def ask_confirmation(command: str) -> bool:
    if AUTO_APPROVE:
        return True
    answer = input(f"\n允许执行命令？\n{command}\n[Y/n]: ").strip().lower()
    return answer in ("", "y", "yes")


def truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT:
        return text
    half = MAX_OUTPUT // 2
    return text[:half] + f"\n\n...[truncated from {len(text)} chars]...\n\n" + text[-half:]


def bash(command: str) -> str:
    blocked, pattern = is_dangerous(command)
    if blocked:
        return f"blocked dangerous command (pattern={pattern}): {command}"
    if not ask_confirmation(command):
        return "user denied command"
    try:
        p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        return truncate(p.stdout + p.stderr)
    except Exception as e:
        return f"error: {e}"


def run(task: str) -> str:
    messages = [
        {"role": "system", "content": "You are a safe coding assistant. If command fails/blocked, choose alternatives."},
        {"role": "user", "content": task},
    ]
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
