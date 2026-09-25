# 文档导航

> 本目录按“谁需要读、解决什么问题”组织。规范文档只定义规则，评测目录保存过程与证据，最终提交材料统一放 `materials/`。

## 推荐阅读顺序

| 角色/任务 | 建议阅读 |
| --- | --- |
| 第一次了解项目 | 根目录 `README.md` → `product/软件需求说明.md` → `competition/项目说明与答辩要点.md` |
| 开发与联调 | `engineering/开发规范与开发顺序.md` → `engineering/API接口说明.md` → `evaluation/开发过程与验证记录.md` |
| 测试与复核 | `evaluation/测试论文生成提示词.md` → `evaluation/blind-tests/` → `materials/03-测试报告.md` |
| 部署与运维 | `operations/本地启动运行手册.md`（本机跑起来） → `operations/生产部署启动手册.md` → `operations/安全与运维核查清单.md` → `operations/生产上线待办清单.md` |
| 答辩与提交 | `competition/竞赛硬性门槛与评分规则对齐.md` → `competition/项目说明与答辩要点.md` → `materials/00-材料总览.md` |

## 目录说明

```text
docs/
├── README.md                         # 本导航
├── product/
│   └── 软件需求说明.md                # 做什么、验收什么
├── engineering/
│   ├── 开发规范与开发顺序.md          # 怎么写、怎么拆任务
│   └── API接口说明.md                 # 对外接口
├── operations/
│   ├── 本地启动运行手册.md            # 本机前后端启动、配置、自测与排查
│   ├── 生产部署启动手册.md            # 公网部署、TLS 与上线收口
│   ├── 安全与运维核查清单.md          # 已实现控制点与运维核查
│   └── 生产上线待办清单.md            # 8 项上线门禁与验收
├── evaluation/
│   ├── 测试论文生成提示词.md
│   ├── 开发过程与验证记录.md
│   └── blind-tests/
│       ├── blind-001-机器学习中的线性回归.md
│       ├── blind-002-模型参数的确定方法.md
│       ├── blind-003-中文短文本分类.md
│       └── blind-004-预埋缺陷实证论文.md
└── competition/
    ├── 竞赛硬性门槛与评分规则对齐.md
    └── 项目说明与答辩要点.md
```

## 唯一口径

- 功能范围以 `product/软件需求说明.md` 为准。
- 评测数量和指标以 `python backend/scripts/eval_ac.py` 的实际输出为准，入口说明见 `samples/README.md`。
- 安全控制点以 `python backend/scripts/security_audit.py` 为准，业务说明见 `operations/安全与运维核查清单.md`。
- 生产上线状态以 `operations/生产上线待办清单.md` 和 `backend/scripts/deploy_gate.py` 为准。
- 最终提交材料以 `materials/00-材料总览.md` 为准；`docs/` 保存内部规范与证据，不重复制作提交版。

## 当前报告能力边界

- 用户可以查看结构化审查报告，并下载 Markdown 审查报告。
- 当前不导出“已自动修改的论文 DOCX”：修改稿在系统内生成并对修改稿做真实二次审查（补写由模型结合全文生成、须附可核验原文出处，图表/真实数据依赖条目由作者处理），作者据此回到 Word 中落实；原文件与修改稿均仅在会话内暂存。
- 盲测报告是内部验证证据，不是用户论文的修改稿，也不是运行时生成的用户报告。
- 解析能力边界：一期不解析公式与图片，表格按行并入 `paragraphs[]` 仅作上下文。**二期（`软件需求说明.md` §15.5）已全部落地**：表格结构化入 `tables[]` 并从 `paragraphs[]` 移出、OMML 公式文本提取、L1 图-文一致性（`R-FIG-01`）、内嵌图片落盘 + 视觉识读（`R-FIG-02`，结论为「存疑」）、追问支持多轮上下文（上限 10 轮 / 20 条 + 8000 字符）、自由提问面向全文（注入全文 DATA 区，`QA_FULLTEXT_MAX_CHARS` 约束）、修改稿由模型结合全文补写并做真实二次审查。