# 知微 Knowence 技术方案 — 架构拆解与改造设计

> 版本：v0.1 ｜ 日期：2026-09-29 ｜ 配套：docs/PRD/PRD.md、docs/阶段文档/技术适配声明.md
> 证据基线：Tencent/WeKnora @ main（2026-09-29，★31,030，MIT）；对照 infiniflow/ragflow @ main（Apache-2.0）。文中路径均为该仓库真实文件路径。

---

## 一、候选底子横评（选型依据）

| 维度 | WeKnora | RAGFlow | Dify | FastGPT | onyx | MaxKB |
| --- | --- | --- | --- | --- | --- | --- |
| 许可证 | **MIT（纯）** | Apache-2.0（纯） | 改 Apache：**禁多租户+禁去 logo** | 同左 | MIT + `ee/` 企业目录 | GPL-3.0 | AGPL-3.0（法务高危） |
| 语言栈 | Go 单体 + Vue + Python docreader | Go 为主（已重写） | Python(Flask)+TS | Next.js/TS | Python | Python | Python |
| RBAC | **四级角色+空间隔离+API-Key scope default-deny** | 弱 | workspace 制 | team 制 | 有但部分在 ee | 基础 | 基础 |
| 审计 | **62 类事件+保留清理+查询界面** | 无成型 | 部分 | 部分 | 部分 | 部分 | 无 |
| 混合检索+rerank | ✅ chat_pipeline 内置 | ✅✅ 最深（deepdoc） | ✅ | ✅ | ✅ | ✅ | ✅ |
| 引用溯源 | ✅ citation_sources/references 环节 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Agent+沙箱 | ✅ ReAct+Docker/E2B/Cube 沙箱+审批 | Agent canvas 有、沙箱无 | workflow 强 | flow 强 | 弱 | 弱 | 无 |
| IM 渠道 | **10 平台 Adapter（企微/飞书/钉钉…）** | 无 | 部分 | web 为主 | 若干 | 无 | 桌面端为主 |
| 本地模型友好度 | OpenAI 兼容 provider 三类独立 | 同类 | 同类 | 同类 | 同类 | 同类 | — |
| 部署组件数 | compose profiles 可裁剪 | ES/Infinity+MinIO+Redis+MySQL 全家桶 | 7+ 服务 | Mongo+向量库+MinIO | 重 | 中 | 轻 |
| 维护热度 | 日更 | 日更 | 日更 | 日更 | 日更 | 日更 | 停更 11 个月 |

**结论**：需求清单（统一知识库/RBAC/审计/沙箱/渠道/私有化）与 WeKnora 能力逐项对应且许可证干净——选它当底座；RAGFlow 作为「检索深度」参照系，借鉴其分块模板思想。

## 二、WeKnora 分层架构（实测拆解）

### 2.1 总体形态

Go 单二进制应用（`internal/` 约 2400 个 .go 文件），外加三个 sidecar：**docreader**（Python 文档解析服务）、**sandbox**（技能执行容器）、前端静态站。任务走队列（运行时任务面板+Worker 池）。compose 服务全集：frontend/app/sandbox/docreader/postgres(ParadeDB)/redis/minio/qdrant/milvus/weaviate/doris/elasticsearch/neo4j/searxng——**按 profile 裁剪，最小集只有 5 个左右**。

### 2.2 请求主链路：chat_pipeline（核心资产）

问答不是"一把梭调模型"，而是一条显式管线（`internal/application/service/chat_pipeline/`，每步一个文件、可插拔）：

```
query_understand（改写/拆子问题）
  → query_expansion（多查询扩展）
  → search_parallel（多路并发召回：向量+关键词混合，跨多个 KB）
  → rerank（独立重排模型打分）
  → filter_top_k / merge（截断与融合）
  → wiki_boost / search_entity（图谱加权，可选）
  → citation_sources + references（引用回填）
  → into_chat_message → chat_completion[_stream]（生成，SSE 收尾）
```

配套：`memory_recall/memory_affinity`（长期记忆召回）、`load_history`（会话续接）、`web_fetch`（联网兜底，内部场景关闭）。

混合检索的落地：`internal/application/service/retriever/keywords_vector_hybrid_indexer.go`；关键词侧 ParadeDB 提供 BM25 级全文，Milvus 配中文 analyzer（`retriever/milvus/analyzer.go`，官方文档还有 milvus-bm25-chinese 修复记录图）。**向量后端是插件**：`repository/retriever/{elasticsearch v7/v8, milvus, qdrant, weaviate, doris, neo4j, opensearch}` 各自实现同一接口。

### 2.3 入库链路

上传 → **docreader 进程外解析**（Office 由 anydoc 在 Go 进程内解析、PDF/图片走解析服务，覆盖十余种格式）→ 分块落 `repository/chunk.go`（分块**可编辑、可比对、可回滚**——这是它比多数开源 RAG 细的地方）→ embedding（`internal/models/embedding` provider）→ 写入所选向量后端。FAQ 型资料有专用通道（faq_direct_answer）。

### 2.4 模型层抽象（"多模型路由"的答案）

`internal/models/` 按能力类型分包：**chat / embedding / rerank / vlm / asr 五类各自独立配置**，providers 子包做厂商适配，catalog 自动生成模型目录（README 称内置 27 家厂商：OpenAI、DeepSeek、Qwen、智谱、混元、Gemini、Ollama、LiteLLM…），runtime+limiter 管调用与限流，`api/compat_settings.go`+`credentials.go` 承载 OpenAI 兼容 base_url/key。**含义：把对话模型指到公司内网 vLLM、embedding 留云端小模型、rerank 用本地 bge——都是配置动作，不是代码动作。**

### 2.5 Agent / Skill / 沙箱 / MCP

- Agent：`internal/agent/engine.go` ReAct 主循环 + `act.go/finalize.go/checkpoint.go`（断点）+ `grounding_prompt.go`（落地约束）；工具在 `agent/tools/`（data_analysis、database_query、browserskill…），带 `execution_policy.go` 与 `scope_authorization.go`（工具级授权）；敏感动作走 `agent/approval/`。
- Skill：**SKILL.md + YAML frontmatter 约定、Level-2 渐进加载**（`agent/skills/skill.go`）——与 Claude 的 Agent Skills 同构；来源可插拔（`SkillSource`：内置目录/租户镜像），支持 ClawHub/Git/ZIP 安装。
- 沙箱：`internal/sandbox/`，provider 枚举 `{Docker, Cube, E2B, Disabled}`，能力以窄接口暴露（`capabilities.go`：SessionShellExecutor/FileStore/Terminal/Desktop），租户级沙箱配置入库（migration 000082/000108）。另有单机 `internal/localsandbox`（pathguard 防越界）。
- MCP：双向——客户端 `internal/mcp/`（连接池+完整 OAuth 套件），服务端 `internal/mcpserver/`（对外暴露 ask/retrieve/ingest/wiki 工具，供 Cursor/Claude 等直连本平台）。

### 2.6 权限治理（RBAC + 审计）

- 数据模型：`tenant_members(user_id, tenant_id, role, status)`（migration 000043），一人可跨多租户持不同角色；KB 带 creator_id 做所有权。
- 四级角色：`internal/types/tenant_member.go` — **owner(40) > admin(30) > contributor(20) > viewer(10)**，数值分级便于插入新角色；`HasPermission = Level() >= required`。
- 判权两层：HTTP 中间件（`middleware/rbac.go` RequireRole，`router/rbac.go` 逐路由挂 ViewerOnly/ContributorPlus/AdminPlus/OwnerOnly）+ service 层共享规则（`application/access/`：ResolveKB/RequireKBWrite/KBPermissions，不依赖 Web 框架）。**API-Key 不走角色阶梯**，由 `api_key_gate.go` + KB scope **default-deny**。检索入口单独判权：`access/kb_search.go: AuthorizeKBAccess`。灰度开关 `Tenant.EnableRBAC`（关时只记日志不拦截——生产必须开）。
- 审计：`audit_logs` 表（000044）记录 actor_role/action/target/request_path/outcome/details JSONB，**62 类事件常量**（rbac.*、kb.*、knowledge.*、datasource.*、vector_store.*…含 `rbac.access_denied`），带保留期清理（`audit_log_retention.go`）与管理台查询页（SystemAuditLog.vue）。缺口：**无导出**（要对接 SOC 需自补）。

### 2.7 渠道分发

`internal/im/`：单一 `Adapter` 接口（VerifyCallback/ParseCallback/SendReply）+ 可选能力接口（StreamSender 打字机流式、FileDownloader）；10 平台各一子包（wecom/feishu/slack/telegram/dingtalk/mattermost/wechat/qqbot/yunzhijia/lark 复用 feishu），长连接与回调双模式（longconn.go），命令注册表可扩展（/search /clear /stop）。另有 Web Widget 嵌入发布。

## 三、五层架构映射（产品叙事 ↔ 代码事实）

| 我们的五层 | WeKnora 对应 | 状态 |
| --- | --- | --- |
| 大模型基座层 | `internal/models/*`（chat/embedding/rerank/vlm/asr + providers/catalog） | ✅ 现成 |
| 业务资产层 | 知识库/chunk 版本化 + datasource 同步（飞书/Confluence/语雀/Notion…）+（可选）neo4j 图谱 | ✅ 大部分现成 |
| RAG/Agent 引擎层 | chat_pipeline 九段管线 + agent ReAct + sandbox + skill | ✅ 核心资产 |
| 权限治理层 | tenant RBAC + audit + api-key scope + approval | ✅ 现成，粒度见 §四 |
| 多渠道分发层 | im Adapter×10 + Widget + MCP Server | ✅ 现成 |

## 四、改造点设计（二次开发范围）

### M1 品牌与外壳（低成本）
换 logo/主题色/文案（MIT 允许，无 Dify 式限制）；管理台收敛为「知识运营 / 权限 / 审计 / 模型」四视图。

### M2 知识可见性下沉（高成本，第二版）
现状：权限粒度=KB 集合级。方案对比：
- **近似解（MVP 采用）**：一密级一知识库，财务库仅授财务角色——零改造，够用即真。
- **正解（第二版）**：chunk/document 级 ACL。改动三处且必须一致：①角色/密级枚举扩展（tenant_member.go 现为硬编码 const）；②`access/` 新增谓词构造器并在 kb_search 后过滤；③最贵——各 retriever 后端把 acl 数组写入索引 mapping 并**下推到检索查询**（否则 top-k 被污染）。有利条件：`types.Caller`（Role/TenantID）已贯穿到 repository 层，传参通路现成。

### M3 Prompt/模型「沙箱验证→发布」流水线（中成本，第二版）
素材已齐：prompt 模板（config/prompt_templates/*.yaml，需 DB 化+版本字段）、`SkillRolloutNextTurn/NewSession` 灰度语义可直接复用作发布门控、沙箱 `SessionDestroyer` 支持一次性评测会话。缺的是评测编排层（仓库内未找到 eval 框架）——自建小规模回归集+通过门禁即可。

### M4 置信度分流（低-中成本，MVP 后紧接）
管线已有 rerank 分数与 citation 覆盖率信号，在 `filter_top_k` 之后加策略位：高置信直答 / 低置信转人工附材料 / 敏感类目强制人工。转人工出口先做 IM 通知占位。

### M5 成本计量（低成本）
Langfuse 追踪 Token/步骤为 README 明示能力，接入即用；空间/人维度聚合报表薄薄一层。

### M6 审计导出（低成本）
补 CSV/API 导出，对齐企业安全团队要求。

## 五、部署方案（私有化）

- **最小集**（MVP）：app + frontend + postgres(ParadeDB) + redis + minio + docreader ≈ 6 容器；向量先用 ParadeDB 一体化（省独立向量库），规模阈值后再评估 Milvus/Qdrant。
- **模型演进三步**：① 全云端 OpenAI 兼容 API（最快见效）→ ② 对话切本地 vLLM(Qwen)，embedding/rerank 暂云端 → ③ 全本地（vLLM + bge-m3 + reranker），达成"数据不出域"终态。每步都只是 provider 配置变更。
- 资源参考（假设，待实测修正）：纯 CPU 跑云端 API 形态 8C16G 即可；本地 14B-Qwen 量化推理单卡 24G 起步、32B 需 2×24G 或 48G。
- 离线内网：镜像预拉取+私有 registry；模型权重随包分发；searxng/web_fetch 整组关闭。

## 六、风险清单

| 风险 | 等级 | 应对 |
| --- | --- | --- |
| 项目年轻（v0.8.x），API 与 migration 节奏快 | 中 | 锁版本 fork，升级走 diff 评审 |
| RBAC 灰度开关默认行为需确认 | 中 | 部署清单强制 `EnableRBAC=true`+启动自检 |
| chunk 级 ACL 改造涉及全部向量后端 | 高 | MVP 用分库近似；正解放第二版并先做单后端 PoC |
| 审计无导出 | 低 | M6 自补 |
| 中文 OCR/扫描件效果未实测 | 中 | 验收样例必含扫描件；必要时引入外部解析器（docreader 已是进程外接口） |
| 许可证第三方组件 | 低 | 读 THIRD_PARTY_NOTICES.md 复核强 copyleft 项 |
