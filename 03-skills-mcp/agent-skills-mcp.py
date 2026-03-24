"""
第三阶段：Rules / Skills / MCP 思路骨架

重点：
- 这里先做“可运行的最小版”，把外部能力接入点留清楚。
- 重要设计写在注释里，你可以按注释逐步补全真实 MCP 对接。

说明：
- Rules：约束执行边界与行为规范
- Skills：定义可复用任务能力索引
- MCP：接入外部系统工具能力
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from openai import OpenAI


# 与前两个阶段一致：基础客户端初始化。
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), base_url=os.environ.get("OPENAI_BASE_URL"))
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# 约定目录（你也可以换成自己项目里的路径）
RULES_DIR = ".agent/rules"
SKILLS_DIR = ".agent/skills"
MCP_FILE = ".agent/mcp.json"


def bash(command: str) -> str:
    p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
    return p.stdout + p.stderr


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, content: str) -> str:
    Path(path).write_text(content, encoding="utf-8")
    return f"wrote: {path}"


BASE_TOOLS = [
    {"type": "function", "function": {"name": "bash", "description": "run shell", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "read", "description": "read file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write", "description": "write file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
]
FUNCTIONS = {"bash": bash, "read": read, "write": write}


def load_rules_text() -> str:
    # 规则会拼到 system prompt，让模型“先懂约束，再做事”
    if not Path(RULES_DIR).exists():
        return ""
    parts = []
    # 把每个规则文件合并成一个大文本块。
    for p in Path(RULES_DIR).glob("*.md"):
        parts.append(f"# {p.name}\n{p.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def load_skill_index_text() -> str:
    # 这里先只加载技能清单（元信息）；真正执行技能可在后续加 dispatcher
    if not Path(SKILLS_DIR).exists():
        return ""
    # 这里只给模型一个“可用技能目录”，还没做技能文件内容注入，p.stem返回文件名。
    names = [p.stem for p in Path(SKILLS_DIR).glob("*.json")]
    return "\n".join(f"- {name}" for name in names)


def load_mcp_tools() -> list[dict]:
    # 这里只是读取配置并转成 tool schema；真实调用逻辑后面再接
    if not Path(MCP_FILE).exists():
        return []
    try:
        data = json.loads(Path(MCP_FILE).read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    tools = []
    # 把多个 MCP server 的工具声明统一平铺成 tools 列表。
    for _, server in data.get("mcpServers", {}).items():
        for tool in server.get("tools", []):
            tools.append({"type": "function", "function": tool})
    return tools


def run(task: str) -> str:
    rules_text = load_rules_text()
    skills_text = load_skill_index_text()
    mcp_tools = load_mcp_tools()

    # 注意：这里只是“声明可调用”，还没有“真正可执行”。
    # TODO: 为 mcp_tools 增加函数分发器，把 tc.function.name 路由到实际 MCP 调用
    tools = BASE_TOOLS + mcp_tools
    system = "You are a concise coding assistant."
    if rules_text:
        system += f"\n\n[Rules]\n{rules_text}"
    if skills_text:
        system += f"\n\n[Skills]\n{skills_text}"

    messages = [{"role": "system", "content": system}, {"role": "user", "content": task}]
    # 仍然是经典闭环：模型决定 -> 程序执行 -> 工具结果回填。
    for _ in range(8):
        resp = client.chat.completions.create(model=MODEL, messages=messages, tools=tools)
        msg = resp.choices[0].message
        messages.append(msg)
        if not msg.tool_calls:
            return msg.content or ""
        for tc in msg.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments or "{}")
            if name in FUNCTIONS:
                result = FUNCTIONS[name](**args)
            else:
                # 注：先占位，提醒“工具声明了但尚未绑定执行器”
                result = f"Tool '{name}' declared but runtime handler not implemented yet."
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    return "max iterations reached"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 03-skills-mcp/agent-skills-mcp.py 'your task'")
        sys.exit(1)
    print(run(" ".join(sys.argv[1:])))
