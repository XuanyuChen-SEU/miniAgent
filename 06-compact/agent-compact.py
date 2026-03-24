"""
第六阶段：上下文压缩（compact）

问题：
- 长任务会导致 messages 过长，成本上升，甚至超 context window。

做法：
- 当消息数量超过阈值，压缩旧消息为摘要，只保留最近几条原文。

说明：
- 通过摘要替换旧消息，控制上下文长度与成本
- 保留近期原始消息，降低摘要带来的信息损失
"""

import json
import os
import subprocess
import sys

from openai import OpenAI


# 基础客户端初始化。
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), base_url=os.environ.get("OPENAI_BASE_URL"))
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# 超过这个消息数量就触发压缩。
THRESHOLD = 16
# 压缩时保留最近多少条原始消息不动。
KEEP_RECENT = 6


TOOLS = [
    {"type": "function", "function": {"name": "bash", "description": "run shell", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}}
]


def bash(command: str) -> str:
    p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
    return p.stdout + p.stderr


def compact_messages(messages: list[dict]) -> list[dict]:
    # 未达阈值时直接返回，避免不必要的额外模型调用。
    if len(messages) <= THRESHOLD:
        return messages
    system = messages[0]
    # 旧消息用于摘要；近期消息保留原文，保障短期精度。
    old_msgs = messages[1:-KEEP_RECENT]
    recent = messages[-KEEP_RECENT:]

    text = []
    for m in old_msgs:
        role = m.get("role", "unknown")
        content = m.get("content", "")
        if content:
            text.append(f"[{role}] {content}")

    # 注：摘要质量直接决定后续行为稳定性，后续可加“关键信息清单”格式约束
    s = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Summarize key facts, decisions, commands and outputs concisely."},
            {"role": "user", "content": "\n".join(text)},
        ],
    )
    summary = s.choices[0].message.content or ""
    # 这里加入一条 assistant 的确认语句，
    # 让后续模型自然承接“我已读取摘要”的语境。
    return [
        system,
        {"role": "user", "content": f"[history summary]\n{summary}"},
        {"role": "assistant", "content": "Acknowledged. I will continue with this summary context."},
        *recent,
    ]


def run(task: str) -> str:
    messages = [{"role": "system", "content": "You are a concise coding assistant."}, {"role": "user", "content": task}]
    for _ in range(20):
        # 每轮先尝试压缩，再进入工具调用循环。
        messages = compact_messages(messages)
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
    if len(sys.argv) < 2:
        print("Usage: python 06-compact/agent-compact.py 'your task'")
        sys.exit(1)
    print(run(" ".join(sys.argv[1:])))
