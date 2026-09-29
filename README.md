# 知微 Knowence · 企业 AI 工作系统

> 面向企业的私有化 AI 工作系统：放入企业资料，即获得带出处的知识问答、多步骤任务执行与多渠道分发能力；AI 能力按角色分级开放，全程留痕可审计。
>
> 基于 [Tencent/WeKnora](https://github.com/Tencent/WeKnora)（MIT）二次开发。

## 它能做什么

- **统一 RAG 知识库**：Word/PDF/Excel/Markdown 等多格式入库，分块可编辑、可比对、可回滚
- **有据可查的回答**：查询理解 → 多路并发召回（向量+关键词混合）→ Rerank 重排 → 引用回填 → 生成，答案每条事实都能点开原文
- **Agent 任务执行**：ReAct 循环 + 工具（数据分析/数据库查询/浏览器），敏感动作人工审批，技能在沙箱中运行
- **权限治理**：四级角色 RBAC（owner/admin/contributor/viewer）、空间隔离、API-Key 默认拒绝、62 类事件审计日志
- **模型自由**：对话 / Embedding / Rerank 三类模型独立配置，OpenAI 兼容协议，云端 API 与本地 vLLM/Ollama 一键切换——数据不出域
- **多渠道分发**：Web 端先行；企微 / 飞书 / 钉钉等 IM 内直接问答，Web Widget 嵌入，内置 MCP Server 供 AI 工具直连

## 架构分层

```
┌───────────────────────────────┐
│  多渠道分发层  Web / IM×10 / MCP │
├───────────────────────────────┤
│  权限治理层    RBAC / 审计 / 审批 │
├───────────────────────────────┤
│  RAG / Agent 引擎层                 │
│  query_understand → search_parallel │
│  → rerank → citation → completion   │
├───────────────────────────────┤
│  业务资产层  知识库 / 分块版本 / 同步源 │
├───────────────────────────────┤
│  大模型基座层  chat·embedding·rerank  │
│              （云端 / 本地同接口）     │
└───────────────────────────────┘
```

## 文档

| 文件 | 内容 |
| --- | --- |
| [docs/PRD/PRD.md](docs/PRD/PRD.md) | 产品需求：目标用户、主链路、验收标准、阶段划分 |
| [docs/阶段文档/技术适配声明.md](docs/阶段文档/技术适配声明.md) | 选型结论与偏离说明 |
| [docs/阶段文档/Knowence技术方案.md](docs/阶段文档/Knowence技术方案.md) | 架构拆解与改造设计 |

## 部署（规划中）

最小集 6 容器：app + frontend + PostgreSQL(ParadeDB) + Redis + MinIO + docreader。
模型演进：云端 API → 对话切本地 vLLM → 全栈本地化。

## License

本项目为 WeKnora（MIT）的衍生作品；改造部分同样以 MIT 发布（见 LICENSE）。
