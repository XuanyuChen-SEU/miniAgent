"""
第五阶段：多 Agent 团队

关键升级：
1) 持久 Agent 对象（有自己的历史消息）
2) 团队内消息传递（inbox）
3) 生命周期管理（创建 -> 协作 -> 解散）
"""

import os
import sys
from dataclasses import dataclass, field

from openai import OpenAI


client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), base_url=os.environ.get("OPENAI_BASE_URL"))
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


@dataclass
class Agent:
    name: str
    role: str
    messages: list[dict] = field(default_factory=list)
    inbox: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.messages.append({"role": "system", "content": f"You are {self.name}, a {self.role}. Be concise."})

    def receive(self, text: str) -> None:
        self.inbox.append(text)

    def chat(self, task: str) -> str:
        # 把 inbox 先注入上下文，让团队信息可以被这个 agent 感知
        if self.inbox:
            self.messages.append({"role": "user", "content": "Team updates:\n" + "\n".join(self.inbox)})
            self.inbox.clear()
        self.messages.append({"role": "user", "content": task})
        r = client.chat.completions.create(model=MODEL, messages=self.messages)
        m = r.choices[0].message
        self.messages.append(m)
        return m.content or ""


class Team:
    def __init__(self) -> None:
        self.agents: dict[str, Agent] = {}

    def hire(self, name: str, role: str) -> Agent:
        agent = Agent(name=name, role=role)
        self.agents[name] = agent
        return agent

    def broadcast(self, sender: str, content: str) -> None:
        for name, agent in self.agents.items():
            if name != sender:
                agent.receive(f"from {sender}: {content}")

    def disband(self) -> None:
        self.agents.clear()


def run(task: str) -> str:
    team = Team()
    planner = team.hire("planner", "project planner")
    coder = team.hire("coder", "python developer")
    reviewer = team.hire("reviewer", "code reviewer")

    # 注：这里是固定团队模板，后续可改成让模型动态生成成员
    p = planner.chat(f"Create a short implementation plan for: {task}")
    team.broadcast("planner", p)
    c = coder.chat("Implement according to latest plan and explain key decisions.")
    team.broadcast("coder", c)
    r = reviewer.chat("Review planner/coder outputs and provide final result.")

    team.disband()
    return f"[planner]\n{p}\n\n[coder]\n{c}\n\n[reviewer]\n{r}"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 05-teams/agent-teams.py 'your task'")
        sys.exit(1)
    print(run(" ".join(sys.argv[1:])))
