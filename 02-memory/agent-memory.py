"""
第二阶段：记忆 + 任务拆解

关键改进：
1) 把结果写入本地记忆文件，供下次任务参考
2) 增加简单 planning（先拆步骤，再逐步执行）

说明：
- `load_memory` / `save_memory` 负责持久化记忆
- `create_plan` 负责生成步骤化执行计划
- `run_agent` 负责串联规划与执行流程
"""

import json
import os
import sys
from datetime import datetime

from openai import OpenAI

from pathlib import Path
import subprocess


# 客户端与模型选择：和第一阶段相同，用环境变量控制。
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), base_url=os.environ.get("OPENAI_BASE_URL"))
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
# 记忆文件用 Markdown，方便人类直接打开阅读。
MEMORY_FILE = "agent_memory.md"

TOOLS = [
    {"type": "function", "function": {"name": "bash", "description": "run shell", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "read", "description": "read file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write", "description": "write file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
]


def bash(command: str) -> str:
    # 返回命令输出，给模型“观察外部环境”的能力。
    p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
    return p.stdout + p.stderr


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, content: str) -> str:
    Path(path).write_text(content, encoding="utf-8")
    return f"wrote: {path}"


FUNCTIONS = {"bash": bash, "read": read, "write": write}


def load_memory() -> str:
    if not Path(MEMORY_FILE).exists():
        return ""
    # 只带最近内容，避免历史太长污染上下文
    lines = Path(MEMORY_FILE).read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[-60:])


def save_memory(task: str, result: str) -> None:
    # 每次任务追加一段时间戳记录，形成“可追溯”的执行日志。
    entry = f"\n## {datetime.now().isoformat(timespec='seconds')}\nTask: {task}\nResult: {result}\n"
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(entry)


def create_plan(task: str) -> list[str]:
    # 注：这里故意保持简单，后续你可增加“失败重试”“依赖关系”等机制
    # 这里单独调用一次模型，只做“规划”，不做工具执行。
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Break this task into 3-5 short actionable steps. Return JSON: {\"steps\": [...]}"},
            {"role": "user", "content": task},
        ],
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content or "{}")
    steps = data.get("steps", [])
    # 容错：如果模型没按约定返回 steps，就退化为“单步直做”。
    return steps if isinstance(steps, list) and steps else [task]


def run_step(step: str, messages: list[dict], max_iterations: int = 6) -> tuple[str, list[dict]]:
    # 每个 step 都作为新的 user 输入压入同一上下文，
    # 这样后续 step 能“看到”前面 step 的结果。
    messages.append({"role": "user", "content": step})
    for _ in range(max_iterations):
        r = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        m = r.choices[0].message
        messages.append(m)
        if not m.tool_calls:
            return m.content or "", messages
        for tc in m.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments or "{}")
            # 第二阶段保持最小实现：假设 name 一定在 FUNCTIONS 里。
            result = FUNCTIONS[name](**args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    return "max iterations reached", messages


def run_agent(task: str, use_plan: bool) -> str:
    # 把长期记忆注入 system prompt，让模型“带着历史经验”工作。
    memory = load_memory()
    system = "You are a concise coding assistant."
    if memory:
        system += f"\nPrevious context:\n{memory}"
    messages = [{"role": "system", "content": system}]

    # --plan 开启时：先拆步骤；否则就直接执行原任务。
    steps = create_plan(task) if use_plan else [task]
    results = []
    for i, step in enumerate(steps, 1):
        print(f"[Step {i}/{len(steps)}] {step}")
        res, messages = run_step(step, messages)
        results.append(res)
    final = "\n".join(results)
    save_memory(task, final)
    return final


if __name__ == "__main__":
    use_plan = "--plan" in sys.argv
    argv = [x for x in sys.argv[1:] if x != "--plan"]
    if not argv:
        print("Usage: python 02-memory/agent-memory.py [--plan] 'your task'")
        sys.exit(1)
    print(run_agent(" ".join(argv), use_plan=use_plan))
