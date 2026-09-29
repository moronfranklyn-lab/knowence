# 版本锁定记录（Base Lock）

> 本文件记录 Knowence 的底座来源。任何改动 `vendor/weknora/` 的操作前必读。

## 锁定的上游版本

| 项 | 值 |
| --- | --- |
| 上游仓库 | [Tencent/WeKnora](https://github.com/Tencent/WeKnora) |
| tag | **v0.8.2**（2026-09-24 发布） |
| commit SHA | `3e8b0bfc80b845b2d4b2ed683994748741450a97` |
| 快照位置 | `vendor/weknora/`（源码 tarball 解包，非 submodule） |
| 许可证 | MIT（快照内保留完整 LICENSE 与 THIRD_PARTY_NOTICES.md） |
| 工作 fork | moronfranklyn-lab/WeKnora（用于跟踪 upstream PR / 试验性改动） |

## 为什么锁这个版本

WeKnora 处于快速迭代期（周更、migration 编号已到 100+）。不锁版本的后果：上游一次 breaking migration 就能让你的本地数据库和定制代码同时报废。锁定后升级变成显式决策——先看 upstream diff，评估影响，再决定跟不跟。

## 规则

1. **`vendor/weknora/` 只允许两种改动**：
   - 整目录替换到新的锁定版本（需在本文件登记新旧 SHA + 迁移说明）；
   - 打上明确标注的补丁（commit message 以 `[patch]` 开头），作为升级到新版本前的临时承载。
2. Knowence 自己的改造（M1-M6）**不进 vendor**，放在独立目录/服务里，通过 API 与底座交互或做分叉构建。
3. 每次换锁必须同步检查：migrations 增量、`.env.example` 新增变量、docker-compose profile 变化。
