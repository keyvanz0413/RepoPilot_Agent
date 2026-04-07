# RepoPilot 项目设计文档
## A Contract-Grounded, Dependency-Aware Coding Agent for Repository-Level Task Execution

---

## 1. 项目概述

### 1.1 项目定义

RepoPilot 是一个**面向代码仓库任务执行的智能体系统**。

它不是一个“让大模型直接写代码”的工具，而是一个在真实工程环境中执行软件变更任务的受控系统。

它的核心目标是：

> 让 AI 像一个有工程意识的开发者一样，先理解仓库、核对契约、分析依赖影响，再进行受控修改，并通过验证与恢复机制完成任务。

### 1.2 项目要解决的核心问题

当前很多 AI coding assistant 存在以下问题：

1. **不会先核对真实接口和参数**
   - 会凭经验猜 schema、字段名、返回结构、函数签名
   - 常出现“看起来合理，但根本跑不通”的改动
2. **缺乏 repo-level understanding**
   - 只看当前文件，不理解项目整体结构
   - 容易改错模块、重复实现已有逻辑
3. **只修目标点，不分析依赖影响**
   - 把目标函数改好了，但调用它的其他模块全部崩掉
   - 不会自动检查调用方、测试、上下游契约兼容性
4. **没有验证和恢复闭环**
   - 改完就结束
   - 不跑测试、不分析错误、不回滚、不重规划
5. **工具使用缺乏安全边界**
   - shell、文件写入、删除操作可能失控
   - 没有审批、没有白名单、没有防护

### 1.3 为什么这个项目不是 toy demo

这个项目不是“一个大 prompt 让 LLM 写代码”，而是一个具备工程化特征的 agent 系统，包含：

- Planner / Executor / Reviewer 分工
- Contract grounding
- Dependency-aware editing
- Retrieval decision & retrieval policy
- Tool safety governance
- Verification & recovery loop
- Layered memory
- Evaluation plan
- Human-in-the-loop

## 2. 系统设计目标

### 2.1 功能目标

系统支持以下任务类型：

- 修复小型 bug
- 为已有模块新增参数或逻辑
- 新增简单后端接口
- 新增简单前端功能对接
- 自动补测试
- 分析代码仓库结构
- 自动定位受影响调用方并联动修改

### 2.2 工程目标

本项目重点追求：

- **可控性**：流程可拆分、可跟踪、可中断
- **可靠性**：改动前有契约核验，改动后有验证
- **安全性**：工具调用受限制
- **可恢复性**：失败后可回滚、重试、重规划
- **可解释性**：知道为什么查、为什么改、为什么测
- **可评估性**：可与 baseline 对比

## 3. 系统总体架构

```text
User Task
  ↓
Task Analyzer
  ↓
Retrieval Decision Layer
  ↓
Repo Mapper
  ↓
Contract Validator
  ↓
Dependency Impact Analyzer
  ↓
Planner
  ↓
Patch Coder / Executor
  ↓
Test Runner
  ↓
Reviewer
  ↓
Recovery Manager
  ↓
Result (Patch + Diff + Summary + Logs)
```

系统外围能力：

- Memory Layer
- Tool Safety Guard
- Human-in-the-Loop
- Evaluation Layer
- Observability / Execution Logs

## 4. 状态机设计

### 4.1 为什么要用状态机

很多 toy agent 的问题是流程写死或者全塞在一个 prompt 里。
RepoPilot 采用显式状态机，原因是：

- 便于控制每个阶段职责
- 便于插入检索、审查、人工确认
- 便于失败恢复
- 便于调试和日志记录
- 便于后续扩展到多 agent / 并行节点

### 4.2 状态流

```text
INIT
 → ANALYZE_TASK
 → DECIDE_RETRIEVAL
 → MAP_REPO
 → VALIDATE_CONTRACT
 → ANALYZE_IMPACT
 → PLAN
 → EDIT
 → TEST
 → REVIEW
 → DONE
```

失败分支：

```text
EDIT / TEST / REVIEW
 → RECOVER
 → PLAN / EDIT / DONE
```

人工确认分支：

```text
PLAN / EDIT
 → HUMAN_APPROVAL
 → CONTINUE / ABORT
```

## 5. 核心模块设计

### 5.1 Task Analyzer

**作用**

负责理解用户任务，提取目标和约束。

**输入**

- 用户任务文本
- 可选附件说明（截图描述、报错摘要、issue 描述）

**输出**

```json
{
  "task_type": "bug_fix | add_feature | add_test | refactor | explain_repo",
  "target": "auth login endpoint",
  "intent": "add rate limiting",
  "constraints": [
    "keep existing auth flow unchanged",
    "modify as few files as possible"
  ]
}
```

**为什么这样设计**

如果没有任务分类，后续检索和执行策略会非常混乱。
Task Analyzer 为 retrieval policy 和 planner 提供结构化输入。

### 5.2 Retrieval Decision Layer

**作用**

决定当前任务需要检索哪些信息，而不是默认每次都全查。

**典型判断**

- 新增接口：必须查 contract
- 改函数签名：必须查 callers
- 只补注释：无需复杂检索
- 修测试失败：先查 stack trace，再定位模块
- 前后端联调：查 API contract + client usage

**输出**

```json
{
  "need_repo_map": true,
  "need_contract_check": true,
  "need_dependency_check": true,
  "need_test_selection": true,
  "reasoning": [
    "task changes endpoint behavior",
    "possible signature compatibility risk"
  ]
}
```

**为什么这样设计**

对应“博主贴文”里很关键的一条：

> Agent 要自己决定要不要检索

这一步能防止系统退化成固定流水线，也体现工程化检索策略。

### 5.3 Repo Mapper

**作用**

建立代码仓库级别的结构理解。

**功能**

- 扫描目录结构
- 提取关键文件
- 标记入口文件
- 识别 route/controller/service/model/test
- 输出 repo map 摘要

**输出示例**

```text
main.py -> app entrypoint
routes/auth.py -> login/register endpoints
services/auth_service.py -> auth business logic
schemas/auth.py -> request/response models
tests/test_auth.py -> auth-related tests
```

**为什么这样设计**

AI coding assistant 的一个大问题是只看局部，不懂全局。
Repo Mapper 的目标是让后续模块知道“在哪改”，而不是盲改。

### 5.4 Contract Validator

**作用**

在真正生成代码之前，先从仓库中核对真实契约。

**检查内容**

- route / endpoint
- request schema / DTO / Pydantic / zod
- response schema
- service 函数签名
- 前端类型定义或 client 封装

**输出示例**

```json
{
  "endpoint": "POST /api/login",
  "request_fields": ["email", "password"],
  "response_fields": ["token", "user"],
  "service_signature": "login(email: str, password: str) -> AuthResult",
  "uncertainties": []
}
```

**为什么这样设计**

这是整个项目的重要亮点之一。它解决的是：

AI 不应该先猜接口，再让人返工；而应该先基于真实代码契约做 grounding。

对应博主贴文强调的两点：

- 让 Agent 自己决定要不要检索
- 检索策略说清楚为什么选它

因为这里不仅检索，而且说明为什么检索 contract。

### 5.5 Dependency Impact Analyzer

**作用**

分析修改影响面，避免只改目标模块导致调用方崩溃。

**核心能力**

- 搜索调用方 / references
- 分析 import 关系
- 分析参数依赖
- 分析返回值使用方式
- 识别高风险变更
- 自动选择相关测试

**输出示例**

```json
{
  "target": "services/user.py:get_user",
  "risk_level": "high",
  "affected_files": [
    "routes/profile.py",
    "services/order.py",
    "tests/test_user.py"
  ],
  "impact_reason": [
    "function signature changed",
    "callers depend on old return fields"
  ],
  "suggested_actions": [
    "update callers",
    "rerun related tests"
  ]
}
```

**为什么这样设计**

这是第二个关键亮点。它解决的是：

AI 改完这个模块，却没有看其他依赖它的代码会不会一起崩。

对应博主贴文中的工程化问题：

- 链路写死
- 检索策略
- 工程项目而不是 demo

因为这一步体现了动态计划调整和依赖感知检索。

### 5.6 Planner

**作用**

把任务转成可执行的步骤，而不是让模型直接自由写代码。

**输入**

- Task report
- Retrieval decision
- Repo map
- Contract report
- Impact report

**输出示例**

```json
{
  "goal": "Add rate limiting to login endpoint",
  "steps": [
    "inspect login route and auth middleware",
    "add rate limiter utility",
    "update login route",
    "check affected callers and tests",
    "run verification"
  ],
  "files_to_edit": [
    "routes/auth.py",
    "middleware/rate_limit.py",
    "tests/test_auth.py"
  ],
  "risk_level": "medium"
}
```

**为什么这样设计**

Planner 的价值不在于“拆步骤好看”，而在于：

- 让执行可控
- 让审查和恢复有依据
- 让 human approval 可插入

对应博主贴文中的：

- Planner-Executor 分工
- Agent 中途改变计划

### 5.7 Patch Coder / Executor

**作用**

根据 plan 做实际代码修改。

**原则**

- patch-based editing
- 每次少量文件
- 优先函数/模块级受控修改
- 尽量避免整文件重写
- 高风险变更触发 human approval

**输出**

- patch
- diff
- edit summary

**为什么这样设计**

toy 系统常见问题是整文件重写、上下文漂移、改动过大。
Patch Coder 把模型限制在更可控的修改方式里。

对应博主贴文中的：

- “System prompt 折叠起来还剩几个 Agent”
- “包打天下”问题

因为这里把执行和规划分开了。

### 5.8 Test Runner

**作用**

验证改动，而不是生成即结束。

**策略**

- 优先跑目标模块测试
- 跑 Dependency Analyzer 找到的相关调用方测试
- 必要时再扩大范围
- 保留 stderr / stack trace / failing tests

**为什么这样设计**

很多 AI coding assistant 的问题不是第一次写错，而是没有形成测试闭环。
Test Runner 是系统可靠性的核心模块。

对应博主贴文中的：

- “Harness 是空的”
- “工具调用失败后能不能自恢复”

### 5.9 Reviewer

**作用**

检查任务是否真的完成，是否引入了副作用。

**检查点**

- diff 是否与目标一致
- 是否超范围修改
- 是否存在高风险兼容性问题
- 测试结果是否可信
- 是否需要继续修正

**为什么这样设计**

不是所有测试通过都意味着设计正确。
Reviewer 负责任务对齐和结果质量判断。

### 5.10 Recovery Manager

**作用**

在失败时决定下一步动作。

**常见恢复策略**

- syntax / import error -> 局部修复
- signature mismatch -> 查调用方并联动修改
- tests failed -> 基于错误日志重新规划
- diff 范围过大 -> 回滚并缩小修改范围
- repeated failure -> 请求人工确认

**为什么这样设计**

真正的工程系统不能把失败当作异常路径，而应当把失败当作常规控制流的一部分。

对应博主贴文中的：

- “工具调用失败过吗”
- “失败了能不能自己恢复”
- “中途改变计划”

## 6. Memory 设计

### 6.1 为什么要做分层记忆

对应博主贴文里的一个核心问题：

> 用户上周说过的偏好，Agent 今天还记得吗？

如果没有记忆，系统每次都在“第一次见用户”。

### 6.2 分层方案

**短期记忆（Task Memory）**

保存：

- 当前任务目标
- 当前 plan
- 当前失败信息
- 已完成步骤

**长期记忆（Preference / Failure Memory）**

保存：

- 用户偏好（如先看 plan、限制改动文件数）
- 仓库偏好（如严格类型检查、测试优先级）
- 常见失败模式（如 import path 容易出错）

**为什么这样设计**

短期记忆服务当前任务，长期记忆帮助后续任务更像“连续协作”。

## 7. 多模态输入设计

### 7.1 支持范围

- 报错截图
- 页面截图
- 控制台截图
- 设计稿截图

### 7.2 处理方式

第一版不直接做端到端多模态推理，而是：

1. 先用 vision model 提取结构化摘要
2. 再把摘要交给 Task Analyzer / Planner

### 7.3 为什么这样设计

对应博主贴文的问题：

> 用户丢一张截图进来，流程会断吗？

多模态不是为了炫技，而是为了让系统在真实开发输入下不断链。

## 8. Tool Safety Governance

### 8.1 为什么要做安全治理

对应博主贴文最关键的一条：

> MCP 工具安全治理

即使不是 MCP，也必须有工具治理。否则只是“调 API”，不是工程系统。

### 8.2 安全策略

**命令白名单**

允许：

- `pytest`
- `npm test`
- `python -m ...`
- `grep / rg`
- `ls / cat`

禁止默认直接执行危险命令：

- `rm -rf`
- `sudo`
- `curl | bash`
- `production deploy`

**写文件限制**

- 限制写入仓库目录内
- 保护关键配置文件
- 大范围改动需审批

**Git checkpoint**

- 修改前强制创建 checkpoint
- 恢复时可回滚

**高风险审批**

以下操作要求 human approval：

- 删除文件
- 修改超过 N 个文件
- 改动核心配置
- 修改函数签名且影响调用方很多

### 8.3 为什么这样设计

工具一旦能写文件、跑命令，就不能裸奔。
这是工程系统和 demo 的重要分水岭。

## 9. Human-in-the-Loop

### 9.1 插入点

- plan 审批
- 高风险改动审批
- 回滚确认
- 多轮失败后的继续执行确认

### 9.2 为什么这样设计

完全自动化不是第一目标。
真正有工程意识的系统应支持“自动 + 人工把关”的混合模式。

## 10. Evaluation 设计

### 10.1 为什么需要评估

对应博主贴文中的问题：

> 你能说出项目比 baseline 强多少个百分点吗？

如果没有评估，项目就很容易停留在“演示能跑”。

### 10.2 Baseline 设计

**Baseline A**

直接把任务和目标文件扔给单一 LLM 改代码。

**RepoPilot**

完整流程包括：

- contract grounding
- dependency analysis
- patch-based edit
- targeted verification
- recovery

### 10.3 指标

**任务级**

- Task success rate
- Retry count
- End-to-end latency

**代码级**

- Test pass rate
- Build pass rate
- Files changed
- Regression count

**Agent 级**

- Retrieval correctness
- Plan validity
- Recovery success rate

### 10.4 最小 benchmark 方案

设计 10~20 个任务：

- 增参数
- 小 bug
- 新增接口
- 补测试
- 改函数签名并联动修改调用方

**为什么这样设计**

哪怕是小 benchmark，也比“没有数字”强很多。

## 11. Observability / 执行日志

### 11.1 记录内容

- 状态跳转
- 每个 tool 调用
- 每个 agent 输出
- 检索理由
- 失败原因
- 恢复动作
- diff 摘要
- 测试结果

### 11.2 为什么这样设计

这是后续调试、评估、演示和面试表达的基础。

## 12. 对照“博主贴文”的工程化自检

### 已覆盖

- Planner-Executor 分工
- 动态重规划
- 工具失败恢复
- retrieval policy 雏形
- patch-based controlled editing
- harness / checkpoint / verification
- human-in-the-loop 雏形

### 需要重点落地

- retrieval decision 更动态
- layered memory
- evaluation benchmark
- 多模态输入
- tool safety governance

### 结论

RepoPilot 的目标不是做一个“demo 级 agent”，而是尽可能向“工程级 repository task agent”靠近。

## 13. 项目亮点总结

- **Contract-Grounded**：不靠猜接口，先核验真实契约
- **Dependency-Aware**：修改前分析影响面和调用方
- **Retrieval-Driven**：让 agent 决定何时查、查什么、为什么查
- **Patch-Controlled**：受控修改，减少漂移
- **Verification-Driven**：以测试和审查形成闭环
- **Recovery-Capable**：失败后可恢复，而不是直接崩
- **Safety-Governed**：工具调用有边界，有审批，有回滚

## 14. 一句话项目定义

RepoPilot 是一个具备契约核验、依赖影响分析、工具安全治理与验证恢复闭环的 repository-level coding agent，用于在真实工程环境中可靠地执行软件变更任务。
