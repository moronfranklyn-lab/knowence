# 贡献指南

感谢有兴趣参与。本项目是 [Tencent/WeKnora](https://github.com/Tencent/WeKnora)（MIT）的衍生作品，
请先阅读 [`docs/与上游的差异.md`](docs/与上游的差异.md) 了解改动边界。

---

## 一、最容易踩的三个坑

### 1. 别把改动落到 `vendor/weknora/internal/`

`vendor/weknora/` 是**上游快照**。目前只有 `frontend/src/` 有品牌层补丁（31 个文件），
`internal/`、`migrations/`、`mcp-server/`、`docreader/`、`cli/` 是**零改动**的——
这保证上游的 bug 修复能直接同步。

**如果你的功能需要改 Go 后端**，请在 issue 里先讨论方案，不要直接改 `vendor/`。

### 2. `.ps1` 脚本必须保持纯 ASCII

PowerShell 5.1 读取 **UTF-8 无 BOM** 的 `.ps1` 时，会按系统 ANSI 代码页（中文 Windows = GBK）解码。
中文字节被误读后可能"吃掉"紧随其后的字符——**包括 `}` 和引号**，
于是报出看起来毫不相干的语法错误。

> 真实案例：脚本报 `Missing closing '}'`，而花括号明明是配平的。
> 详见 [`docs/阶段文档/本地部署实录.md`](docs/阶段文档/本地部署实录.md) 坑 9。

**规则**：`.ps1` 里不写非 ASCII 字符，中文只放在输出层。
Python 文件无此问题（Python 3 源码默认 UTF-8）。

### 3. 模型文件必须放 Docker 原生卷

llama.cpp 用 **mmap** 读权重。跨宿主/容器的共享挂载（bind mount）会让 mmap
退化成逐次读盘——实测推理速度差 **9.4 倍**（2.0 tok/s vs 18.7 tok/s）。

> 详见 [`docs/阶段文档/本地部署实录.md`](docs/阶段文档/本地部署实录.md) 坑 7。

**规则**：用 `./scripts/download-models.sh`（它会自动放进命名卷），不要自己 bind mount。

---

## 二、提交前必跑

```bash
cd vendor/weknora/frontend

npm run check-i18n                                  # i18n 键审计（13 项）
npx tsx --test src/assets/theme/styleGuard.test.mjs # 主题守卫（10 项）
npm run build                                       # 必须构建通过
```

**品牌残留扫描**（确认没有把上游品牌带进来）：

```bash
npm run build && python3 - <<'EOF'
import os
bad = ["WeKnora Cloud", "Tencent/WeKnora"]
for root, _, files in os.walk("dist/assets"):
    for f in files:
        if f.endswith(".js"):
            t = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
            for k in bad:
                if k in t:
                    print(f"⚠️ {f} 含上游品牌: {k}")
print("扫描完成（无输出即通过）")
EOF
```

**管控组件测试**（如果你改了 `knowence-guard/` 下的东西）：

```bash
python3 knowence-guard/handoff_test.py   # 44 项
python3 knowence-guard/prompt_test.py    # 42 项
```

---

## 三、文档贡献

| 想写什么 | 放哪 |
| --- | --- |
| 部署踩的坑、排障经验 | `docs/阶段文档/本地部署实录.md`（追加，**编号连续**） |
| 评测方法与结果 | `docs/evidence/` |
| 部门 Agent 配置方案 | 参考 `部门Agent设计指南.md` 的格式 |
| 与上游的差异 | `docs/与上游的差异.md`（改了 `vendor/` 就必须更新） |

**写踩坑记录的格式**（见部署实录）：

```
### N. 一句话现象（按教训价值排序）

- **现象**：
- **定位过程**：（关键是**怎么找到的**，不只是结论）
- **根因**：
- **修法**：
- **教训**：> 引用块，一句话可迁移的经验
```

**最有价值的不是"我修好了"，而是"我怎么定位到的"。**

---

## 四、Issue 与 PR

- **Bug**：请附上 `docker compose logs` 的相关片段 + 复现步骤
- **部署问题**：请说明系统、Docker 版本、是否使用 GPU
- **新功能**：请先在 issue 里讨论——特别是涉及改 `vendor/` 的

---

## 五、许可

提交贡献即表示同意以 **MIT** 许可证发布你的贡献。
