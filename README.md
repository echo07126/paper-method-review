# 论文方法论审查助手

面向中文科研写作的 DOCX 方法学审查工具。系统按 17 条可插拔清单检查研究设计、统计方法、数据划分、基线与消融、引用等内容，输出可定位到原文、带严重等级和修改建议的结构化报告。

## 当前状态

> 指标口径统一以 `python backend/scripts/eval_ac.py` 的实际输出为准（数据截至 2026-09-25）。

| 门禁 | 结果 | 说明 |
| --- | --- | --- |
| 评测集 | 16 篇 / 82 条标准答案 | fixtures 5、real 7、review 2、empirical 1、planted 1 |
| AC-2 检出 | **82/82 = 100%** | 规则引擎模式 |
| 精确率 | **82/82 = 100%** | 规则引擎模式 |
| AC-3 定位 | **79/82 = 96%** | 容差 ±1 段 |
| 单元测试 | **78 passed** | `pytest backend/tests -q` |
| 安全核查 | **33/33** | `security_audit.py` |
| 生产上线 | **0/8 已完成** | `deploy_gate.py` 返回非零，阻止对外公开 |
| 二期进度 | **P2-1 / P2-2 / P2-3 / P2-4 已完成** | 表体结构化 + OMML 公式提取 + L1 图-文一致性 + L3 图像内容识读 + 追问多轮上下文；规划见 `docs/product/软件需求说明.md` §15.5 |

## 核心能力

- **DOCX 闭环**：上传、分章、要素抽取、17 条逐项审查、报告定位、Markdown 导出、追问和修改前后对比。
- **规则优先、模型增强**：规则引擎可离线运行；DeepSeek 仅作顾问判定，输出必须通过结构化校验和证据门控。
- **可追溯报告**：Finding 保存清单条目、严重级、说明、建议及段落/句子锚点；无证据的模型断言不进入报告。
- **隐私与安全**：匿名会话隔离、上传校验、日志脱敏、限流、删除传播和生产配置守卫；正文仅在会话内暂存，运行期每 5 分钟由常驻任务回收过期会话与孤儿临时目录。
- **可扩展结构**：解析器、清单、LLM Provider、报告导出器均以接口或配置解耦；一期仅实现 DOCX，PDF 保留接口。二期（§15.5）在 DOCX 上解除「不解析公式与图片」边界：表格结构化入 `tables[]`、OMML 公式文本提取、内嵌图片视觉识读，Provider 不变。

## 本地运行

> 完整的本地启动、配置项速查、自测命令与故障排查见 [`docs/operations/本地启动运行手册.md`](docs/operations/本地启动运行手册.md)。以下为最简版。

### 后端

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cp backend/.env.example backend/.env   # Windows: Copy-Item
# 在 backend/.env 填写 DEEPSEEK_API_KEY；不配置时仍可使用规则引擎
cd backend && python -m uvicorn app.main:app --port 8000
```

> 必须在 `backend/` 目录内启动：`CHECKLIST_DIR=../checklists` 等相对路径以该目录为基准。

接口文档仅在 `DOCS_ENABLED=true` 时开放：<http://127.0.0.1:8000/docs>。

### 前端

```bash
cd frontend
npm ci
npm run dev
npm run typecheck
npm run build
```

### Docker

```bash
docker compose up -d --build
# 前端：http://127.0.0.1:8080
```

Compose 仅绑定本机回环端口；`data/` 为运行数据卷，`checklists/` 只读挂载。

### 依赖锁定

- 后端直接依赖在 `backend/requirements.txt` 中用 `==` 固定版本，开发依赖在根 `requirements.txt` 中同样固定；CI、镜像构建与本地安装共用同一份清单，避免「本地过、线上挂」。
- 前端由 `frontend/package-lock.json` 锁定（已入库）。
- 升级依赖时先改清单再跑全套门禁（pytest / eval_ac / security_audit / api_check / 前端 build），确认无回归后再提交。

## 回归与上线门禁

```bash
python -m pytest backend/tests -q
python backend/scripts/eval_ac.py
python backend/scripts/security_audit.py
python backend/scripts/api_check.py     # 端到端冒烟（含 data/ 隔离自证）
python backend/scripts/deploy_gate.py
```

- `eval_ac.py` 是样本数量、检出率、精确率和定位率的唯一数字口径。
- `security_audit.py` 对代码与配置逐项取证，**未通过时返回 1**（可作 CI 门禁）。
- `api_check.py` 通过 `set_settings_override()` + `env_file=None` 子类做配置隔离，
  保证冒烟不写入真实 `data/`（末尾有断言自证）。
- `deploy_gate.py` 在 8 项生产待办未完成时返回 1；全部完成后才返回 0。

以上四项（pytest / eval_ac / security_audit / api_check）加前端 `npm run build`
均已纳入 `.github/workflows/ci.yml`，任一步失败即阻断合并。

## 项目结构

```text
paper-method-review/
├── .github/workflows/ci.yml     # CI：依赖审计、pytest、eval_ac、security_audit、api_check、前端构建
├── backend/
│   ├── app/
│   │   ├── api/                 # 上传、文档、审查、报告、对比、追问、会话、健康检查
│   │   ├── core/                # 配置、错误、日志、限流、审计、ID
│   │   ├── engine/              # 规则、要素、论文类型、LLM、提示词、引用核验
│   │   ├── models/              # Pydantic Schema
│   │   ├── parsers/             # DOCX 解析与 Parser 注册表
│   │   ├── reports/             # Markdown 导出
│   │   └── storage/             # SQLite、文件与会话维护
│   ├── scripts/                 # 24 个活动工具
│   │   └── archive/             # 50 个已完成使命的一次性脚本
│   ├── tests/                   # pytest
│   ├── Dockerfile
│   ├── requirements.txt         # 后端运行时依赖（唯一来源）
│   └── .env.example
├── checklists/quant-ai-v1.json  # 17 条审查清单
├── docs/                        # 产品、工程、运维、评测、竞赛文档导航
├── frontend/                    # Vue3 + Vite + TypeScript
├── materials/                   # 参赛提交材料
├── samples/                     # fixtures、real 样本与 ground_truth
├── docker-compose.yml
├── requirements.txt             # 引用后端运行时依赖并加入 pytest
└── README.md
```

## 文档索引

- 文档导航：[`docs/README.md`](docs/README.md)
- 软件需求：[`docs/product/软件需求说明.md`](docs/product/软件需求说明.md)
- 开发规范：[`docs/engineering/开发规范与开发顺序.md`](docs/engineering/开发规范与开发顺序.md)
- API：[`docs/engineering/API接口说明.md`](docs/engineering/API接口说明.md)
- 开发验证记录：[`docs/evaluation/开发过程与验证记录.md`](docs/evaluation/开发过程与验证记录.md)
- 盲测报告：[`docs/evaluation/blind-tests/`](docs/evaluation/blind-tests/)
- 样本与评测口径：[`samples/README.md`](samples/README.md)
- 安全核查：[`docs/operations/安全与运维核查清单.md`](docs/operations/安全与运维核查清单.md)
- 本地启动：[`docs/operations/本地启动运行手册.md`](docs/operations/本地启动运行手册.md)
- 生产部署：[`docs/operations/生产部署启动手册.md`](docs/operations/生产部署启动手册.md)
- 生产待办：[`docs/operations/生产上线待办清单.md`](docs/operations/生产上线待办清单.md)
- 竞赛与答辩：[`docs/competition/`](docs/competition/)