# RepoPilot 开发文档
## 从 0 到 Demo 的可执行开发方案

---

## 1. 开发目标

这份文档的目标不是只告诉你“做什么”，而是同时回答：

- **做什么**
- **为什么先做这个**
- **这一阶段做到什么程度算够**
- **下一步怎么扩展**

你最终要做出的不是一个“什么都想做”的系统，而是一个**可运行、可讲、可扩展**的 demo。

## 1.1 当前代码状态

当前 RepoPilot 已经不再是最初那种固定流水线 demo，而是一个第一版混合式 Agent runtime，已经具备：

- 轻状态机：`TASK_INTAKE -> RETRIEVE -> PLAN -> ACT -> VERIFY -> RECOVER`
- `RETRIEVE` 阶段内动态检索与升级
- `PLAN` 输出结构化 execution contract
- `ACT` 按任务类型和 executor 路由
- `VERIFY` 的 scope / test / noop 校验
- `RECOVER` 的 retry / switch executor / rollback + replan
- 本地 Ollama `gemma4:26b` 驱动 retrieval 与 file-level code editing

所以这份文档现在除了“从 0 到 1”，也要回答：

- 当前已经做到哪里
- 为什么架构从固定 workflow 演进成混合模式
- 下一阶段应该优先补哪一层

## 2. 开发总原则

### 原则一：先做闭环，再做高级能力

不要一开始就做：

- 长期记忆
- 真正复杂 multi-agent
- 向量数据库
- 大规模 benchmark
- 完整 CI/CD

先把下面这条链路打通：

```text
任务输入
→ repo理解
→ contract核验
→ impact分析
→ plan
→ patch编辑
→ 跑测试
→ review
→ recovery
```

### 原则二：先用“工具 + 规则 + 少量 LLM”实现

不要一开始什么都交给 LLM。
很多能力第一版完全可以靠：

- 静态分析
- 搜索
- 正则 / AST
- 简单规则
- LLM 做总结和决策

这样更稳，也更容易调试。

### 原则三：先做“可演示的工程骨架”

你现在更需要的是：

- 架构清晰
- 流程完整
- 有日志
- 有失败恢复
- 能解释 trade-off

而不是追求“最终最强效果”。

## 3. 第一阶段：定义 MVP 范围

### 3.1 MVP 只支持这些任务

从下面挑一类开始：

- 给已有函数增加一个可选参数
- 给后端接口增加一个简单功能
- 补一个 unit test
- 修一个有明确报错的小 bug
- 调整一个 service 函数并联动修改调用方

### 3.2 MVP 不做的事情

先明确砍掉：

- 真正长期 memory
- 完整多模态
- 浏览器 agent
- 多 repo 支持
- 真正并行 multi-agent
- 自动开 PR
- 完整 benchmark 平台
- 复杂权限系统

### 3.3 当前 MVP 完成度

当前代码已经完成了第一版 MVP 的核心闭环：

- 接收任务并结构化 task type / target / scope
- 动态决定 retrieval level
- 做 local / global retrieval
- 自动核验 contract
- 自动分析 impact
- 自动生成 execution plan
- 按任务类型路由执行器
- 在需要时调用本地 Ollama 执行 file-level code edit
- 在失败时做 retry / switch executor / rollback + replan

当前还没有彻底做强的部分是：

- 更丰富的 retrieval action set
- 更通用的 builtin code editing
- 更细的 approval / HITL
- 更稳定的 memory / repo preference

## 4. 第二阶段：项目结构搭建

### 4.1 目录结构

```text
repopilot/
├── app/
│   ├── main.py
│   ├── orchestrator.py
│   ├── state_machine.py
│   └── logging.py
├── agents/
│   ├── planner.py
│   ├── coder.py
│   └── reviewer.py
├── core/
│   ├── contract_validator.py
│   ├── impact_analyzer.py
│   ├── local_retriever.py
│   ├── recovery_manager.py
│   ├── repo_instructions.py
│   ├── repo_mapper.py
│   └── retrieval_decider.py
├── models/
│   ├── llm.py
│   ├── codex.py
│   └── ollama.py
├── schemas/
│   ├── task.py
│   ├── contract.py
│   ├── impact.py
│   ├── plan.py
│   ├── edit.py
│   ├── recovery.py
│   ├── review.py
│   ├── retrieval.py
│   └── run_context.py
├── tools/
│   ├── file_tools.py
│   ├── search_tools.py
│   ├── git_tools.py
│   ├── test_runner.py
│   ├── safety_guard.py
│   └── tool_registry.py
├── logs/
├── tests/
├── README.md
```

### 4.2 为什么这样拆

这样拆不是为了好看，而是为了：

- tool 和 agent 分离
- 核心逻辑和 LLM 调用分离
- 后续容易替换实现
- 面试时能讲清楚职责边界

## 5. 第三阶段：先实现工具层

开发顺序上，先写 tools，不要先写 agent。

因为 agent 的上限取决于工具能力，而不是 prompt 长度。

### 5.1 `file_tools.py`

**要实现**

- `read_file(path)`
- `write_file(path, content)`
- `list_files(root)`

**为什么先做**

所有能力都依赖读写文件。这是最低层基础设施。

**注意**

- 加路径限制
- 限制只允许操作目标仓库目录

### 5.2 `search_tools.py`

**要实现**

- `search_text(query)`
- `find_symbol(name)`
- `find_references(symbol)`

**为什么现在做**

你后面的：

- Repo Mapper
- Contract Validator
- Impact Analyzer

都依赖搜索能力。

**第一版建议**

可以先用：

- `ripgrep`
- Python 正则
- 简单文本搜索

不用一开始就做复杂语义搜索。

### 5.3 `repomap.py`

**要实现**

- 扫描项目目录
- 识别关键文件类型
- 抽取简单文件摘要

**第一版可做**

遍历 `.py/.js/.ts/.tsx`，用 AST 或正则提取：

- 函数名
- 类名
- 路由装饰器

输出 repo map 文本。

**为什么现在做**

这是后续“懂仓库”的前提。

### 5.4 `contract_tools.py`

**要实现**

- `extract_function_signature(path, symbol)`
- `extract_schema_fields(path)`
- `extract_api_contract(path)`

**第一版实现建议**

- Python 用 `ast`
- TypeScript 可先用正则/简单解析
- 返回结构化结果

**为什么现在做**

因为这是你项目和普通 coding assistant 最大的差异点之一。

### 5.5 `impact_tools.py`

**要实现**

- `search_callers(symbol)`
- `search_importers(module)`
- `collect_related_tests(paths)`

**第一版实现建议**

不要追求完整 call graph，先做一个实用版：

- 搜索 symbol 引用
- 搜索 import
- 搜索相关 test 文件名

**为什么现在做**

这能解决“目标模块改好了，调用方崩了”的问题。

### 5.6 `git_tools.py`

**要实现**

- `create_checkpoint()`
- `get_diff()`
- `revert_checkpoint()`

**为什么必须有**

这是 recovery 的基础。没有 checkpoint，失败恢复就很虚。

### 5.7 `test_runner.py`

**要实现**

- `run_test(cmd)`
- `run_targeted_tests(paths)`

**第一版建议**

只支持少数标准命令：

- `pytest`
- `npm test`
- `python -m pytest`

**为什么现在做**

因为验证闭环和日志都依赖它。

### 5.8 `safety_guard.py`

**要实现**

- 命令白名单
- 危险操作拦截
- 写文件范围限制
- 高风险审批判断

**为什么现在就做**

因为工具一旦能运行 shell，就必须加边界。
这也是让项目更工程化的重要一步。

## 6. 第四阶段：定义数据结构和状态机

### 6.1 先定义 schema

`task.py`

- 定义任务输入输出

`state.py`

- 定义状态机状态

`contract.py`

- 定义 contract report

`impact.py`

- 定义 impact report

`review.py`

- 定义 review result

### 6.2 为什么要先定义 schema

很多 demo 后面会越写越乱，因为模块之间全靠自然语言传。
先定义 schema 有几个好处：

- 输入输出稳定
- 容易日志化
- 容易调试
- 容易替换 agent

### 6.3 定义状态机

当前实现已经从细粒度状态转成治理型状态机：

- INIT
- TASK_INTAKE
- RETRIEVE
- PLAN
- ACT
- VERIFY
- RECOVER
- DONE / FAILED

这里的关键不是状态数量变少，而是分层更清楚：

- 状态机只负责治理和阶段切换
- `RETRIEVE` 内部做动态检索
- `PLAN` 决定 executor 和 edit scope
- `ACT` 只执行
- `VERIFY / RECOVER` 显式接管失败控制流

这也是 RepoPilot 从“固定 workflow”演进成“混合式 Agent runtime”的核心变化。

## 7. 第五阶段：实现核心逻辑模块（非 LLM）

### 7.1 `task_analyzer.py`

**做什么**

- 把自然语言任务结构化
- 识别 task type
- 提取目标对象和约束

**第一版怎么做**

可以用：

- 规则 + 关键词
- 或一小次 LLM 调用转成 JSON

**为什么这样做**

先把最基础的任务分流做起来。

### 7.2 `retrieval_decision.py`

**做什么**

让系统判断这次任务需要检索哪些东西。

**第一版规则例子**

- 改函数签名 -> 必查 callers
- 新增 API -> 必查 contract
- 补测试 -> 查 related tests
- 解释仓库 -> 只查 repo map

**为什么这样做**

这是从“固定流程”向“策略化流程”迈进的关键一步。

### 7.3 `contract_validator.py`

**做什么**

调用 contract_tools，汇总成 contract report。

**第一版流程**

1. 找相关 route / symbol
2. 提取 schema / 签名
3. 整理成结构化 contract
4. 标出 uncertainties

**为什么这样做**

把“先核对真实契约，再写代码”落地。

### 7.4 `impact_analyzer.py`

**做什么**

调用 impact_tools，输出影响报告。

**第一版流程**

1. 查 symbol references
2. 查 importers
3. 判断签名是否变化
4. 估算风险等级
5. 选择 related tests

**为什么这样做**

让系统具有 dependency-aware editing 能力。

### 7.5 `recovery_manager.py`

**做什么**

在失败时决定：

- 重试
- 回滚
- 重新规划
- 请求人工确认

**第一版规则**

- syntax/import error -> 局部修复
- failed tests -> 重新计划并限制范围
- too many files changed -> 回滚
- repeated failure -> 请求确认

**为什么这样做**

让失败变成流程的一部分，而不是 demo 直接崩掉。

## 8. 第六阶段：接入最小 Agent 层

当前这一阶段已经完成，而且不再是“只接一个 LLM”这么简单。

现状是：

- retrieval decision 可由本地 Ollama 驱动
- file-level code editing 的 `codex` executor 可由本地 Ollama 驱动
- planner / reviewer / recovery 仍然由系统层控制

这正是当前 RepoPilot 的核心路线：

> 状态机做治理，LLM 只进入最需要智能决策的阶段

### 8.1 `planner.py`

**输入**

- task report
- retrieval decision
- repo map
- contract report
- impact report

**输出**

- step-by-step plan
- files_to_edit
- risk summary

**为什么先做 planner**

因为没有 plan，coder 很容易乱写。

### 8.2 `coder.py`

**输入**

- 当前步骤
- 目标文件
- 相关上下文
- 安全限制

**输出**

- patch 或修改后的片段
- edit explanation

**为什么 coder 要晚于工具层**

因为 coder 不是独立完成任务，它必须依赖真实工具和上下文。

### 8.3 `reviewer.py`

**输入**

- task
- plan
- diff
- test results

**输出**

- 是否完成
- 风险点
- 是否需要继续修改

**为什么 reviewer 重要**

因为 test pass != task truly complete。
reviewer 负责质量把关。

## 9. 第七阶段：串起完整执行流程

### 9.1 `orchestrator.py`

负责：

- 驱动状态流转
- 调用 tools / core / agents
- 记录日志
- 调用 recovery

### 9.2 你要打通的第一条闭环

选一个简单任务，例如：

**示例 1**

给 login 接口加 rate limiting。

**示例 2**

给 `create_order` 增加一个可选参数，并检查调用方兼容性。

**示例 3**

为 payment service 增加测试并修复 failing case。

### 9.3 期望流程

```text
接收任务
→ TASK_INTAKE
→ RETRIEVE
  ↳ local search / repo map / contract / impact
→ PLAN
  ↳ executor contract
→ ACT
  ↳ analysis / builtin_doc / builtin_test / builtin_code / codex
→ VERIFY
→ DONE / RECOVER
```

## 10. 第八阶段：补日志与可观测性

### 10.1 至少记录这些内容

- 当前状态
- 当前任务
- 使用了哪些工具
- tool 输入输出摘要
- planner 输出
- coder 修改哪些文件
- diff 摘要
- test 结果
- recovery 行为

### 10.2 为什么这一步重要

没有日志，你很难：

- debug
- 做 demo
- 解释设计
- 做 benchmark

## 11. 第九阶段：补最小 memory

### 11.1 `task_memory.py`

保存：

- 当前任务
- 当前 plan
- 当前失败信息
- 已完成步骤

### 11.2 `preference_memory.py`

保存：

- 用户偏好（如先出 plan）
- 风险阈值（如改超过 3 个文件需确认）

### 11.3 为什么先做最小版

两天版不追求强长期记忆，但要能说：

- 我已经考虑了 layered memory
- 当前实现有 task memory 和 preference memory 原型

## 12. 第十阶段：补 human-in-the-loop

### 12.1 先做最小触发条件

以下情况要求确认：

- 修改文件数 > 3
- 删除文件
- 改函数签名且影响调用方 > 2
- 连续失败超过 2 次

### 12.2 为什么这一步划算

实现不难，但很能体现工程意识。

## 13. 第十一阶段：做最小 eval

### 13.1 不要一开始做大 benchmark

先设计 5~10 个任务就够。

### 13.2 baseline

直接单轮 LLM 改代码。

### 13.3 对比项

- task success rate
- test pass rate
- retry count
- regression count
- modified files count

### 13.4 为什么这一步重要

因为“能演示”不等于“能证明更好”。

## 14. 第十二阶段：做最小多模态入口（可选）

### 14.1 目标

支持一张截图作为输入，不让流程中断。

### 14.2 实现方式

1. 先用 vision model 提取文本和错误摘要
2. 再交给 task analyzer

### 14.3 为什么现在只做轻量版

因为你当前重点仍然是 repository task 闭环。

## 15. 建议开发顺序总表

上面那套顺序对应的是从 0 到第一版闭环。

如果以当前代码为起点，下一阶段更合理的顺序是：

1. 扩展 `RETRIEVE` 的 action set
2. 做更强的 executor contract 和 edit verification
3. 增强 builtin code path，减少 file-level task 对 Ollama 的硬依赖
4. 补 approval / HITL
5. 补 memory / repo preference
6. 做更系统的 demo case 和 benchmark

## 16. 两天开发计划

**Day 1 上午**

- 建目录
- 写基础 tools
- 跑通 file/search/git/test

**Day 1 下午**

- 写 repo map / contract tools / impact tools
- 定义 schemas 和状态机

**Day 1 晚上**

- 写 task analyzer / retrieval decision / contract validator / impact analyzer
- 接入 planner

**Day 2 上午**

- 接入 coder / reviewer / orchestrator
- 打通完整闭环

**Day 2 下午**

- 加 recovery / safety guard / approval / logs

**Day 2 晚上**

- 准备 2 个 demo case
- 做简单 benchmark
- 优化 README 和演示话术

## 17. 建议你边做边学的重点

### 学什么 1：为什么先做 tools

因为 agent 的能力边界本质上由工具决定，而不是由 prompt 决定。

### 学什么 2：为什么状态机现在要变“轻”

因为现在要解决的问题已经不是“有没有流程”，而是“流程是否足够灵活，同时还能被治理”。

所以当前 RepoPilot 的做法不是继续把状态拆细，而是：

- 用少量治理状态稳定外层
- 在阶段内部引入动态决策

### 学什么 3：为什么要先做 contract validation

因为真实工程里最常见的问题不是写不出代码，而是写出来的代码和项目真实契约不一致。

### 学什么 4：为什么要做 impact analysis

因为变更不是局部行为，而是依赖图中的受影响修改。

### 学什么 5：为什么 recovery 很重要

因为 production agent 真正难的不是第一次执行，而是失败时怎么继续。

### 学什么 6：为什么要做安全治理

因为一旦 agent 能跑命令和改文件，没有治理就不再是工程，而是裸跑脚本。

## 18. 第一版 demo 最终要展示什么

你最终演示时，最重要的不是“它改出了代码”，而是展示下面这条链：

- 系统接收任务
- 自动判断要查什么
- 自动分析仓库
- 自动核对真实 contract
- 自动检查依赖影响
- 自动生成 plan
- 自动做 patch 级修改
- 自动跑相关测试
- 如果失败，自动恢复或重规划
- 输出 diff、测试结果和执行总结

## 19. 第一版完成后怎么升级

### 升级方向 1

更强的 call graph 和 symbol analysis。

### 升级方向 2

更强的 layered memory。

### 升级方向 3

更完整的 benchmark。

### 升级方向 4

更多 task types。

### 升级方向 5

多模态输入。

### 升级方向 6

真正的 GitHub / CI 集成。

## 20. 你可以怎么理解整个开发过程

这个项目的开发过程，本质上是在一步步把一个“会生成代码的模型”升级成一个“会执行工程任务的系统”：

```text
LLM
→ Tool User
→ Controlled Executor
→ Verified Agent
→ Recoverable Engineering System
```

## 21. 一句话开发目标

先做出一个能在真实仓库里安全地查、改、测、回滚的小型执行闭环，再逐步扩展成真正工程化的 coding agent。
