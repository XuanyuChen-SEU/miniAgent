# miniAgent（注释驱动版）

这是一个按阶段逐步完善的 Agent 学习与实现项目，参考 `nanoAgent` 的演进路径，但把核心说明放进代码注释中，而不是拆成多篇文档。

## 目标

- 用最小代码跑通 Agent 闭环（模型调用工具 -> 执行工具 -> 回传结果）。
- 每个阶段只引入一类能力，方便理解和迭代。
- 通过注释记录关键设计取舍与下一步扩展点。

## 阶段结构

- `01-essence/agent-essence.py`：最小 Agent 闭环（工具调用循环）
- `02-memory/agent-memory.py`：记忆落盘 + 基础任务拆解（plan）
- `03-skills-mcp/agent-skills-mcp.py`：Rules / Skills / MCP 接入骨架
- `04-subagent/agent-subagent.py`：把“委派”抽象成 `subagent` 工具
- `05-teams/agent-teams.py`：持久 Agent + 团队消息流 + 生命周期
- `06-compact/agent-compact.py`：上下文压缩（摘要旧消息，保留近期消息）
- `07-safety/agent-safe.py`：命令黑名单 + 人工确认 + 输出截断

## 附加内容（已同步）

除 01-07 主线外，以下 `nanoAgent` 补充内容也已放到项目根目录：

- `full/`：更完整的整合版 Agent 与补充说明
- `real-mcp/`：真实 MCP HTTP server/client 示例
- `nano-skill/`：Skill 相关教学内容
- `tech-sharing/`：技术分享材料
- `tests/`：示例测试用例

## 安装与环境变量

安装依赖（项目根目录）：

```bash
pip install -r requirements.txt
```

设置环境变量（Linux/macOS）：

```bash
export OPENAI_API_KEY='your-key'
export OPENAI_BASE_URL='https://api.openai.com/v1'  # 可选
export OPENAI_MODEL='gpt-4o-mini'                    # 可选
```

## 快速运行

```bash
python 01-essence/agent-essence.py "列出当前目录所有 py 文件"
python 02-memory/agent-memory.py --plan "创建一个 hello.py 并运行"
python 04-subagent/agent-subagent.py "把任务拆成前后端并协作完成"
python 07-safety/agent-safe.py --auto "统计项目中的 Python 文件数量"
```

## 如何继续完善

- 先跑通 01，再按顺序向后补，避免一次加太多复杂度。
- 每个阶段建议先改注释中的 TODO/提示点，再补实现。
- 优先保持“可运行”，其次再追求“功能完整”。

## 注意事项

- 当前代码偏教学化，很多能力是“最小可用实现”。
- `03-skills-mcp` 已保留 MCP 工具声明位，真实 runtime 分发器可继续补齐。
- `07-safety` 的黑名单不是完备安全策略，生产环境需更严格隔离与权限控制。
