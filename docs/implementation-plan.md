# 旅行推荐 Agent 实施计划

## 1. 项目结构

```
my_travel_plan_agent/
├── main.py                    # CLI 入口：解析参数 + 启动 REPL
├── requirements.txt           # 依赖：openai, pydantic
├── saved/                     # 保存的行程目录（--writable 模式写入）
├── docs/
│   ├── first.md               # 架构文档
│   └── implementation-plan.md # 本文件
└── travel_agent/
    ├── __init__.py
    ├── agent.py               # Agent 编排层：三阶段流转 + LLM 调用循环
    ├── session.py             # Session 数据结构 + Message 类型定义
    ├── registry.py            # ToolRegistry：统一注册 + 按 name 路由
    ├── llm.py                 # LLM 调用封装（OpenAI SDK）
    ├── tools/
    │   ├── __init__.py
    │   ├── weather.py         # query_weather：高德地图 API
    │   ├── attractions.py     # query_attractions：LLM 知识生成
    │   ├── restaurants.py     # query_restaurants：LLM 知识生成
    │   ├── hotels.py          # query_hotels：高德地图 API
    │   ├── save_itinerary.py  # save_itinerary：写本地 Markdown 文件
    │   └── base.py            # 工具基类和工具函数定义（JSON Schema 生成）
    └── prompts.py             # System Prompt 模板
```

## 2. 实施步骤（共 8 步）

### Step 1：项目初始化
- 创建 `requirements.txt`
- 安装依赖
- 创建目录结构

### Step 2：数据结构定义 — `session.py`
- 定义 `Message` dataclass（role, content, tool_calls, tool_call_id, name）
- 定义 `Session` dataclass（id, messages, userPreferences, summary, writable）
- 定义 `UserPreferences` dataclass
- 定义 `ItineraryOutput` dataclass（用于结构化输出）
- 定义 `LLMResponse`（解析 LLM 返回，区分 text 和 tool_calls）

### Step 3：LLM 调用封装 — `llm.py`
- 封装 OpenAI 客户端初始化（从环境变量读取 API key/base_url）
- `call_llm(messages, tools=None)` 函数
  - 支持传入 OpenAI 格式的 tools 定义
  - 返回解析后的 `LLMResponse`
- 环境变量：
  - `OPENAI_API_KEY` — OpenAI API 密钥
  - `OPENAI_BASE_URL` — 可选，自定义 API 地址
  - `AMAP_KEY` — 高德地图 API 密钥

### Step 4：工具系统 — `registry.py` + `tools/`
- **Tool 基类**：每个工具是一个类或函数，注册时提供：
  - `name`：工具名
  - `description`：工具描述
  - `parameters`：JSON Schema（OpenAI function calling 格式）
  - `handler`：异步执行函数
- **ToolRegistry**：
  - `register(tool)` 注册工具
  - `get_openai_tools()` → 返回 OpenAI 格式的 tools 列表
  - `execute(name, arguments)` → 按 name 找到 handler 并执行
- **query_weather**（高德 API）：
  - 参数：city, date
  - 调用高德天气 API
  - 返回天气信息列表
- **query_hotels**（高德 API）：
  - 参数：city, check_in, check_out
  - 调用高德周边/PIO API
  - 返回酒店列表
- **query_attractions**（LLM 知识）：
  - 参数：destination, interests
  - 调用 LLM 生成景点列表（带 System Prompt 中的示例）
  - 返回景点列表
- **query_restaurants**（LLM 知识）：
  - 参数：location, taste
  - 调用 LLM 生成餐厅列表（带 System Prompt 中的示例）
  - 返回餐厅列表
- **save_itinerary**（文件系统）：
  - 参数：content, filename
  - 检查 `session.writable`，非可写模式则报错
  - 写入 `saved/` 目录

### Step 5：System Prompt — `prompts.py`
- 定义 System Prompt 模板，包含：
  - Agent 角色定义（旅行规划助手）
  - 三阶段行为指引
  - 工具使用说明
  - 参考价格（酒店/门票/餐饮）
  - 结构化输出格式（ItineraryOutput JSON schema）
  - 局部修改 vs 全局修改的判断逻辑
  - `query_attractions` 和 `query_restaurants` 的示例数据（用于 LLM 知识生成）

### Step 6：Agent 编排核心 — `agent.py`
这是最核心的模块，实现三阶段流转：

**阶段一：信息补全**
1. 接收用户输入
2. 调用 LLM 提取结构化信息（destination, travelDates, people, budget, interests）
3. 代码检查必填字段（destination + travelDates）
4. 缺失 → 让 LLM 生成追问 → 等用户补充 → 回到第 2 步
5. 都齐 → 进入阶段二

**阶段二：推荐主循环**
1. LLM 思考下一步
2. LLM 可能：
   a. 调工具 → 执行 → 结果追加到 messages → 回到第 1 步
   b. 直接推理（编排行程/估预算）
   c. 输出最终行程
3. 输出后：写入 summary → 清空旧消息 → 进入阶段三

**阶段三：后续交互**
1. LLM 判断修改幅度：
   - 局部修改 → 调一次工具 → 更新行程
   - 全局修改 → 回到阶段二
   - 保存 → save_itinerary（检查 --writable）
   - 退出 → 返回退出信号

**LLM 调用循环（核心）**：
```
def run_llm_loop(messages, tools):
    while True:
        response = call_llm(messages, tools)
        if response.text:
            return response.text
        if response.tool_calls:
            for tc in response.tool_calls:
                result = registry.execute(tc.name, tc.arguments)
                messages.append(tool_result_message)
            # 继续循环
```

### Step 7：CLI 入口 — `main.py`
- 解析命令行参数（`--writable`）
- 创建 Session
- 打印启动 banner
- REPL 循环：
  ```
  while True:
      user_input = input("请输入旅行需求 > ")
      if user_input == "exit": break
      result = agent.run(user_input)
      print(result)
  ```
- 优雅处理 Ctrl+C

### Step 8：集成测试
- 模拟用户输入，验证三阶段流转
- 验证工具注册和路由
- 验证保存模式权限控制

## 3. 文件责任矩阵

| 文件 | 层 | 职责 | 依赖 |
|------|-----|------|------|
| main.py | CLI | 参数解析、REPL 循环 | agent |
| agent.py | Agent | 三阶段流转、LLM 循环 | llm, registry, session, prompts |
| session.py | 数据 | Session/Message 数据结构 | 无 |
| llm.py | 基础设施 | OpenAI API 调用 | openai |
| registry.py | 工具 | 工具注册与路由 | tools 各模块 |
| prompts.py | 配置 | System Prompt 模板 | 无 |
| tools/weather.py | 工具 | 天气查询（高德 API） | requests |
| tools/hotels.py | 工具 | 酒店查询（高德 API） | requests |
| tools/attractions.py | 工具 | 景点查询（LLM 知识） | llm |
| tools/restaurants.py | 工具 | 餐厅查询（LLM 知识） | llm |
| tools/save_itinerary.py | 工具 | 保存行程 | session |

## 4. 关键设计决策

### 4.1 工具定义格式
所有工具使用 OpenAI function calling 格式定义 JSON Schema，由 ToolRegistry 管理。Agent 层不直接感知具体工具实现，只通过 registry 执行。

### 4.2 query_attractions / query_restaurants 的实现策略
这两个工具不是调用外部 API，而是调用 LLM 生成。有两种实现方式：
- **方式 A（选定的）**：在 registry 中注册为普通工具，但 handler 内部调用 LLM 并传入示例数据。这样对 Agent 透明，Agent 只需正常调用工具。
- **方式 B**：直接在 System Prompt 中注入示例数据，让 LLM 在推理阶段直接生成。
- **选择理由**：方式 A 使工具调用对 Agent 透明，Agent 统一走 tool_call 路径，不需要特殊处理。同时示例数据可以封装在工具内部，不污染 System Prompt。

### 4.3 消息压缩时机
阶段二输出推荐后立即执行：
1. 将阶段一 + 阶段二的全部消息合并为一段摘要
2. 存入 session.summary
3. 清空 session.messages 中的旧消息

### 4.4 权限模型
- `session.writable` 是启动时设置的布尔值
- `save_itinerary` 工具检查该值
- 默认 `False`（只读）

### 4.5 错误处理策略
- API 超时/报错 → 工具返回错误消息 "XX查询不可用，请按无此数据推荐"
- 部分成功 → 返回已有数据，LLM 自行判断
- 网络错误 → Agent 重试 1 次，再失败则提示用户

## 5. 开发顺序

```
Step 1: 项目初始化
    ↓
Step 2: session.py（数据结构）
    ↓
Step 3: llm.py（LLM 调用）
    ↓
Step 4: registry.py + tools/*（工具系统）
    ↓
Step 5: prompts.py（System Prompt）
    ↓
Step 6: agent.py（Agent 编排，核心逻辑）
    ↓
Step 7: main.py（CLI 入口）
    ↓
Step 8: 集成测试与调试
```

## 6. 测试策略

每个步骤完成后进行单元测试：
- **Step 3**：手动调用 LLM，验证返回格式正确
- **Step 4**：验证每个工具调用正常返回，错误处理符合预期
- **Step 6**：模拟三阶段流转，验证：
  - 信息补全循环正常
  - 工具调用循环正常
  - 消息压缩正常
  - 阶段三局部/全局修改判断正常
- **Step 7**：完整的端到端测试

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 高德 API 无可用 key | 天气/酒店查询不可用 | 工具返回降级信息，LLM 按无此数据推荐 |
| LLM tool_choice 不稳定 | Agent 循环异常 | 对 tool_calls 为空做兜底处理 |
| Token 超限（长对话） | API 调用失败 | 阶段二结束后压缩消息为 summary |
| OpenAI 兼容性问题 | API 调用失败 | 使用标准 OpenAI SDK，支持自定义 base_url |
