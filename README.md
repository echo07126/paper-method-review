# 论文方法论审查助手

面向中文科研写作的 DOCX 方法学审查工具。系统按 17 条可插拔清单检查研究设计、统计方法、数据划分、基线与消融、引用等内容，输出可定位到原文、带严重等级和修改建议的结构化报告。

## 当前状态

> 指标口径统一以 `python backend/scripts/eval_ac.py` 的实际输出为准（数据截至 2026-10-10）。

| 门禁 | 结果 | 说明 |
| --- | --- | --- |
| 评测集 | 16 篇 / 82 条标准答案（本地全量） | fixtures 5、real 7、review 2、empirical 1、planted 1；盲测件由 `samples/real/raw/` **本地生成、不入库**，CI 在 tracked 子集 **12 篇 / 68 条**上运行（68/68 = 100%） |
| AC-2 检出 | **82/82 = 100%** | 规则引擎模式；`--llm` 模型采信模式同为 82/82 |
| 精确率 | **82/82 = 100%**（规则）/ **99%**（`--llm`） | `--llm` 模型侧新增 1 条 R-06 误报 |
| AC-3 定位 | **79/82 = 96%** | 容差 ±1 段 |
| 要素抽取 | **P/R/F1 均 90%** | 16 篇「文档 × 要素类型」级标注实测（`ablation.py`） |
| 并发负载 | **1~16 路零失败、加速比约 1.00→1.64** | 进程内 ASGI（`load_check.py`，每档 10 轮，审查为任务模式提交 + 轮询）；8 路墙钟 0.70 s、16 路 1.24 s |
| 单元测试 | **127 passed** | `pytest backend/tests -q` |
| 安全核查 | **33/33** | `security_audit.py` |
| 本地交付核查 | **8/8 就绪**（5 已内置 + 3 不适用） | 交付形态为本地 Docker 包、不上公网；`deploy_gate.py` 返回 0 |
| 二期进度 | **P2-1 / P2-2 / P2-3 / P2-4 已完成** | 表体结构化 + OMML 公式提取 + L1 图-文一致性 + L3 图像内容识读 + 追问多轮上下文 |

## 核心能力

- **DOCX 闭环**：上传、分章、要素抽取、17 条逐项审查、报告定位、Markdown 导出、追问和修改前后对比。
- **规则优先、模型增强**：规则引擎可离线运行；DeepSeek 仅作顾问判定，输出必须通过结构化校验和证据门控。
- **可追溯报告**：Finding 保存清单条目、严重级、说明、建议及段落/句子锚点；无证据的模型断言不进入报告。
- **隐私与安全**：匿名会话隔离、上传校验、日志脱敏、限流、删除传播和生产配置守卫；正文仅在会话内暂存，运行期每 5 分钟由常驻任务回收过期会话与孤儿临时目录。
- **可扩展结构**：解析器、清单、LLM Provider、报告导出器均以接口或配置解耦；一期仅实现 DOCX，PDF 保留接口。二期在 DOCX 上解除「不解析公式与图片」边界：表格结构化入 `tables[]`、OMML 公式文本提取、内嵌图片视觉识读，Provider 不变。
- **确定性等级**：Finding 除严重等级外另带确定性等级（deterministic 确定性核验 / suspected 高置信疑似 / undetermined 未能判定）；未能判定项在报告中显式列出且不计入问题数。
- **高级应用六项**：按要素定向送审（每条清单只携带检索到的相关原文片段）、证据检索式审查（RAG 原文切片检索）、双模型互证、R-DATA-* 数值自洽检测器族、多模态读图入证、评测驱动（每项改动均给出 `eval_ac` 前后对比）。
- **消融与要素级评测**：`ablation.py` 以 E/A/B/C/D 五配置（要素提取 × 门控 × 模型）在固定评测集上对比检出率/误报率/审查率/token/耗时；16 篇样本带「文档 × 要素类型」级标注，给出要素抽取 P/R/F1。

## 本地运行

> 以下为最简本地启动步骤；容器化一键启动（评委 / 运行方）见包内 [《交付说明.md》](交付说明.md)。

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

## 回归与上线门禁（开发仓库）

> 以下命令在**开发仓库**执行；交付包不含 `backend/scripts`、`backend/tests` 与 `.github/`，运行方按《交付说明.md》启动即可。

```bash
python -m pytest backend/tests -q
python backend/scripts/eval_ac.py
python backend/scripts/ablation.py --strict   # 消融：E/A/B/C/D 五配置 + 要素 P/R/F1（低于下限返回非零）
python backend/scripts/load_check.py          # 负载：并发梯度 1~16 路延迟/吞吐/健康探针
python backend/scripts/security_audit.py
python backend/scripts/api_check.py     # 端到端冒烟（含 data/ 隔离自证）
python backend/scripts/deploy_gate.py
```

- `eval_ac.py` 是样本数量、检出率、精确率和定位率的唯一数字口径（`--llm` 取模型采信模式口径）。
- `ablation.py` 用 `unittest.mock` 进程内打桩（生产代码不加开关），输出 E/A/B/C/D 消融矩阵与要素抽取 P/R/F1。
- `ablation.py --strict` 按回归下限校验要素抽取 F1 与规则口径，**未达标时返回 1**（CI 门禁）。
- `load_check.py` 进程内 ASGI 负载检查（并发 1/2/4/8/16 路，输出上传/审查延迟 p50/p95/max、墙钟、加速比与健康探针）；只作观测，不进 CI。
- `security_audit.py` 对代码与配置逐项取证，**未通过时返回 1**（可作 CI 门禁）。
- `api_check.py` 通过 `set_settings_override()` + `env_file=None` 子类做配置隔离，
  保证冒烟不写入真实 `data/`（末尾有断言自证）。
- `deploy_gate.py` 核对《交付核查清单（本地 Docker 包）》（三态）：仅 `⬜ 需运行方完成` 返回 1，`✅ 已内置` / `➖ 不适用` 不计入阻塞。

以上四项（pytest / eval_ac / security_audit / api_check）加前端 `npm run build`
均已纳入 `.github/workflows/ci.yml`，任一步失败即阻断合并。

## 项目结构

```text
paper-method-review/                       # 本地 / 内网交付包（不上公网）
├── docker-compose.yml                     # 单机编排：回环端口、日志轮转、健康检查
├── start.ps1 / start.sh                   # 一键启动
├── 交付说明.md                            # 环境要求、两种交付形态、验证与常见问题
├── requirements.txt                       # 开发安装用（容器内用 backend/requirements.txt）
├── backend/
│   ├── app/                               # api / core / engine / models / parsers / reports / storage
│   ├── Dockerfile                         # python:3.12-slim，非 root（uid 10001）
│   ├── requirements.txt                   # 后端运行时依赖（唯一来源）
│   ├── .env                               # 模型 Key（不进镜像层，由 compose env_file 读取）
│   └── .env.example
├── frontend/                              # Vue3 + Vite + TypeScript（src + 构建配置 + Dockerfile + nginx.conf）
├── checklists/quant-ai-v1.json            # 17 条审查清单
├── data/                                  # 运行数据卷（SQLite + 临时目录）
└── README.md
```

> 开发仓库另含 `docs/`（产品/工程/运维/评测文档）、`materials/`（参赛提交材料）、`samples/`（评测样本）、`backend/scripts`（评测与门禁工具）、`backend/tests` 与 `.github/`——这些**不进交付包**。

## 交付

- 交付说明：[《交付说明.md》](交付说明.md)——环境要求、一键启动（`start.ps1` / `start.sh`）、离线镜像包（`docker load`）与源码包说明。