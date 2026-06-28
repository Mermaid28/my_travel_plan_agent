# my_travel_plan_agent
## 场景描述
用户用一两句话描述旅行偏好，会涉及旅行目的地，旅行时间，旅行人数，旅行偏好，旅行预算等，
根据用户偏好返回旅行计划推荐

## 场景边界
1. 推荐依据：用户偏好 -> LLM推理
2. 信息源：需要实时数据（天气/酒店/餐厅/景点/美食）
3. 可执行操纵：只做不推荐不直接预定酒店餐厅等
4. 用户画像：单次对话式推荐

## Agent架构
1. 会话状态：内存
2. 模型后端：OpenAI
3. 工具定义：ToolRegistry 统一注册 + 按 name 路由
   // 所有工具注册到一个 registry，LLM 调用时按工具名路由到对应 handler
   // 加新工具只需在 registry 中注册一条，不改 Agent 核心代码
4. 工具失败处理：
   ├─ API 超时/报错 → 告诉 LLM "XX查询不可用，按无此数据推荐"
   └─ 部分成功 → 返回已有数据，LLM 自行判断是否够用
5. 核心循环（LLM call loop）：
   循环逻辑：
     1. 组装 messages：[session.summary（如果有）] + [当前轮消息]
     2. 调 LLM（携带所有工具定义）
     3. LLM 返回 →
          text 消息 → 输出结果（结束循环或进入下一阶段）
          tool_call → 从 registry 查到 handler → 执行 → 结果追加到 messages → 回到第2步
   说明：一次 LLM 调用可能触发多个 tool_call（并行），全部执行完再统一回传给 LLM


## 工具清单
### 外部工具（Tool Layer 负责，Agent 通过tool_call调用 → 工具执行 → 返回数据给 Agent）
1. 天气查询query_weather：地点 + 日期 → 天气列表  ← 高德地图API（需要 API key，通过环境变量 AMAP_KEY 传入）
2. 景点查询query_attractions：目的地 + 兴趣 → 景点列表  ← LLM知识 + 提示词示例（不需要 API key）
3. 餐厅查询query_restaurants：地点 + 口味 → 餐厅列表  ← LLM知识 + 提示词示例（不需要 API key）
4. 酒店查询query_hotels：地点 + 日期 → 酒店列表  ← 高德地图API（需要 API key，通过环境变量 AMAP_KEY 传入）
### LLM 推理任务（Agent Layer 负责，LLM 基于已有信息直接生成，不需要工具）
5. 行程编排：基于景点、餐厅、酒店、时间等已有数据，生成每日行程
6. 预算估算：基于行程内容，预估总花费 ← LLM知识 + 提示词示例给参考价
 参考价格式（coding agent 写到 system prompt 里）：
 酒店：经济型 200-300/晚，舒适型 400-800/晚，
 门票：平均 50-150/景点/人，餐饮：80-200/天/人
### 操作类工具（本地写入，受权限控制）：
7. save_itinerary：保存当前行程到 saved/ 目录 ← 本地文件系统
   格式：Markdown 文件 (.md)，文件名根据目的地+时间自动生成
   例如：云南亲子7日游.md


## 权限模型
Agent 默认只读，所有查询类工具始终可用，不需要授权。
唯一受控的操作是"保存行程"：
1. 用户说"保存"或"收藏" → Agent 调用 save_itinerary 工具
2. --writable 是 CLI 启动参数，一旦启动不可中途切换
   └── 以 --writable 启动 → 用户说"保存" → 写 Markdown 文件到 saved/ 目录
   └── 未指定 --writable → save_itinerary 报错：
                            "当前为只读模式，请用 --writable 重新启动"


## 会话与状态设计

### 1. 三阶段总览

信息补齐 → 推荐主循环 → 后续交互

### 2. 生命周期

创建：CLI 启动时创建 Session，分配唯一 id
销毁：用户输入 exit 或 Ctrl+C 时销毁
恢复：不支持。每次 CLI 启动都是新会话，旧数据不保留（存在内存里，退出就丢）

### 3. 阶段一：信息补全

目标：补齐做推荐所需的必填信息。

必填：destination + travelDates    缺了就追问，用户不回答就不让过
选填：people / budget / interests  LLM 可问可不问，用户不答也可以跳

执行策略：LLM 提取 + 硬编码兜底

1. LLM 从用户输入提取结构化信息
   输出：{ destination, travelDates, people, budget, interests }
   缺的字段为 null
2. 代码检查必填字段（destination + travelDates）
   ├── 两者都有 → 进入阶段二
   └── 任一缺失 → 让 LLM 追问 → 等用户补充 → 回到第 1 步
3. 选填字段不做硬编码检查，LLM 追问时可顺带问，用户不答也可以跳

流程：

用户输入
  │
  ▼
LLM 提取结构化信息
  │
  ▼
代码检查必填字段
  ├── 都齐 ──────────→ 进入阶段二
  │
  └── 缺必填
        │
        ▼
      LLM 生成追问
        │
        ▼
      用户补充回答
        │
        └──→ 回到 LLM 提取（循环）

示例：

用户: "我想去云南旅游"
  → LLM 提取: { destination: "云南", travelDates: null, people: null, budget: null, interests: null }
  → 代码检查: travelDates 缺失 → 触发追问
  → LLM 追问: "你打算什么时候去？大概几个人？"
  → 用户: "7月份，两个大人一个小孩"
  → LLM 提取: { destination: "云南", travelDates: "7月", people: "2大1小", budget: null, interests: null }
  → 代码检查: 必填都有 → 进入阶段二

### 4. 阶段二：推荐主循环

循环逻辑：LLM 自行决定下一步

  ├─ 需要数据 → 调用工具（天气/景点/餐厅/酒店）→ 拿到结果 → 继续思考
  └─ 不需要 → 直接推理（排行程、估预算）

直到 LLM 确认推荐就绪，按 ItineraryOutput 格式输出。

流程：

LLM 思考下一步
  │
  ▼
需要查数据吗？
  ├── 是 ──→ 调用工具 ──→ 拿到结果 ──→ 继续思考 ──→ 回到 LLM 思考
  │
  └── 否 ──→ 直接推理（编排行程、估算预算）
                │
                ▼
           准备好推荐了吗？
              ├── 否 ──→ 继续思考（回到 LLM 思考）
              │
              └── 是 ──→ 输出行程 → 写入 summary → 清旧消息 → 进入阶段三

摘要写入（推荐完成后执行）：
  1. 将阶段一 + 阶段二的全部消息合并为一段摘要
     摘要内容：目的地 + 时间 + 人数 + 已查到的关键数据 + 已输出的行程
  2. 存入 session.summary
  3. 清空 session.messages 中的旧消息（只保留 summary）
  后续阶段 LLM 看到的上下文：[session.summary] + [当前轮消息]

示例：

用户: "7月去云南，2大1小"
  │
  ▼
LLM 思考: "需要查天气和景点"
  │
  ▼
query_weather("云南", "7月") → 返回: "20-25°C，多雨"
  │
  ▼
LLM 思考: "景点也需要查"
  │
  ▼
query_attractions("云南", "亲子") → 返回: ["滇池", "石林", "丽江古城"...]
  │
  ▼
LLM 思考: "再查一下餐厅"
  │
  ▼
query_restaurants("云南", "亲子") → 返回: ["过桥米线", "汽锅鸡"...]
  │
  ▼
LLM 思考: "信息够了，开始编排行程"
  │
  ▼
输出格式化行程推荐
  │
  ▼
写入 summary = "用户7月去云南2大1小，已查天气20-25°C多雨，推荐行程D1昆明D2大理..."
清空旧消息

### 5. 阶段三：后续交互

用户获得推荐后可以继续对话。

LLM 根据修改幅度自行判断走哪条路径：

局部修改（只调一次工具，不重置上下文）
  "换个酒店"、"加一天"、"预算调低"
  → 调用对应工具一次 → 拿到结果 → 更新行程

全局修改（清空已有数据，重新走阶段二）
  "换目的地"、"换日期"、"换人数"
  → 回到阶段二，从头查起

其他操作：
  "保存" → 调用 save_itinerary（需要 --writable 模式）
  "再见" → 退出

流程：

用户反馈
  │
  ▼
LLM 判断修改幅度
  ├── 局部修改 ──→ 调一次工具 ──→ 更新行程 ──→ 等待下一轮反馈
  │
  ├── 全局修改 ──→ 回到阶段二（清空旧数据，从头查起）
  │
  ├── 保存 ──→ save_itinerary（检查 --writable）
  │
  └── 再见 ──→ 退出

示例：

用户: "帮我换个酒店"          ← 局部修改
  → query_hotels("云南", "亲子") → 新酒店列表
  → 更新行程中的酒店部分

用户: "换成大理"              ← 全局修改
  → 清空天气/景点/餐厅/酒店数据
  → 回到阶段二，从头查起

用户: "保存行程"              ← 保存操作
  → save_itinerary → 检查 --writable
  → 写入 saved/ 目录

### 6. 数据结构

type Message = {
  role: 'user' | 'assistant' | 'tool'
  content: string
  tool_calls?: {               // assistant 消息带：调了哪个工具、入参是什么
    id: string
    name: string
    arguments: Record<string, unknown>
  }[]
  tool_call_id?: string        // tool 消息带：对应哪次工具调用
  name?: string                // tool 消息带：对应哪个工具名
}

type Session = {
  id: string
  messages: Message[]          // 当前轮对话消息（历史消息已压缩到 summary 中）
  userPreferences: {           // 当前对话中提取的偏好
    destination?: string
    budget?: string
    interests?: string[]
    travelDates?: string
    people?: string
    dietaryRestrictions?: string[]
  }
  currentPlan?: Itinerary      // Agent 正在编排的行程
  summary?: string             // 历史摘要（阶段二输出后写入，阶段三/下一轮作为上下文输入）
}

type ItineraryOutput = {
  destination: string
  dates: { start: string; end: string }
  budget: { estimated: number; breakdown: string[] }
  dailyPlan: {
    day: number
    date: string
    morning: string
    afternoon: string
    evening: string
    meals: string[]
    reason: string
  }[]
  tips: string[]
}


## 项目分层
┌──────────────────────────────────────────┐
│           CLI 交互层                       │
│  职责：读用户输入 → 显示输出               │
│  不依赖模型，不管业务逻辑，只管 I/O          │
│  向下层传：用户输入的文本                    │
│  从下层收：Agent 返回的回复文本              │
├──────────────────────────────────────────┤
│           Agent 编排层                    │
│  职责：                                    │
│  → 三阶段流转（补全 → 推荐 → 后续）        │
│  → 信息补全：追问生成 + 必填检查            │
│  → 推荐：思考 → 调工具 → 拿到结果 → 继续   │
│  → 后续交互：判断局部/全局修改              │
│  → 格式化输出为 ItineraryOutput           │
│  核心逻辑，不依赖具体工具实现                │
│  向下层传：工具名 + 参数                    │
│  从下层收：工具执行结果                     │
├──────────────────────────────────────────┤
│           工具执行层                       │
│  职责：                                    │
│  → query_weather    调用高德API           │
│  → query_attractions LLM知识              │
│  → query_restaurants 待确认               │
│  → query_hotels     高德API               │
│  → save_itinerary   写本地 Markdown 文件   │
│  每个工具独立，不依赖上层逻辑                │
│  从上层收：工具名 + 参数                    │
│  向上层返：执行结果                         │
└──────────────────────────────────────────┘


## UI形态

CLI 终端，REPL 模式。

启动：
  $ travel-agent                       ← 只读模式
  $ travel-agent --writable            ← 可保存模式

启动后提示：
  ╔══════════════════════════════════════╗
  ║     旅行推荐助手                      ║
  ║  告诉我你想去哪里，我来帮你规划行程     ║
  ║  输入 exit 退出                       ║
  ╚══════════════════════════════════════╝

交互示例（只读模式）：
  请输入旅行需求 > 推荐云南7日游
  [输出行程（一次性打印完整 Markdown）]
  请输入旅行需求 > 换成大理
  [更新行程]
  请输入旅行需求 > exit
  $

交互示例（可写模式）：
  请输入旅行需求 > 推荐云南7日游
  [输出行程]
  请输入旅行需求 > 保存
  → 已保存到 saved/云南亲子7日游.md
  请输入旅行需求 > exit
  $

输出说明：Agent 完成推荐后一次性输出完整行程，不逐 token 流式打印。


## 技术栈
1. 运行环境：Python 3.10+
2. 模型SDK：OpenAI Python SDK（openai）
3. LLM后端：支持 OpenAI 兼容接口的模型
4. 外部API：高德地图API（环境变量传入）