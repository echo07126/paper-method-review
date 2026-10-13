# 评测样本集（16 篇 / 82 条标准答案）

> 本文件的数量和指标必须与 `python backend/scripts/eval_ac.py` 的实际输出一致。当前结果（2026-10-10，**本地全量口径**）：**仅规则模式检出 82/82、精确率 82/82、定位 79/82（96%，容差 ±1 段）；`--llm` 模型采信模式检出 82/82、精确率 99%、定位 96%**。仓库 tracked 子集（不含不入库的盲测件）为 **12 篇 / 68 条**，见下。

## 样本组成

| 分组 | 用途 | 篇数 | 标准答案 | 入库 |
| --- | --- | ---: | ---: | :---: |
| `fixtures/` | 自建受控规则夹具，含 1 篇负对照 | 5 | 42 | 是 |
| `real/` | 开放许可论文改写并脱敏 | 7 | 26 | 是 |
| `review` | 综述/理论论文，检查误报（blind-001/002） | 2 | 0 | 否（本地生成） |
| `empirical` | 规范实证论文，检查误报（blind-003） | 1 | 0 | 否（本地生成） |
| `planted` | 预埋缺陷论文，检查阳性召回（blind-004） | 1 | 14 | 否（本地生成） |
| **本地合计** | | **16** | **82** | — |
| **仓库 tracked 子集** | 盲测件缺失时脚本自动跳过对应分组 | **12** | **68** | — |

同名标准答案位于 `ground_truth/`，JSON 格式见 [`annotation-schema.md`](annotation-schema.md)。`ground_truth/blind-00*.json` 仅含 `sample_id`/类型/条目/锚点等**标注元数据**（不含论文正文），正常入库。

> **关于 `real/raw/` 与盲测件（合规口径）**：`raw/` 保存用户提供的 4 篇**原始**论文，仅本地留档，已被 `.gitignore` 排除、**不进入公开仓库**。此约束的**范围仅限 git**——目的是避免未发表论文随公开仓库分发，**不是「不能用于参赛材料」**；团队已确认这批论文可用于参赛材料（含界面截图与演示视频），依据见 `ground_truth/blind-004.json` 的 `license`（`team-authorized`）与 `note`。
>
> 由 `raw/` 复制而来的盲测件 `real/blind-001..004.docx` **同样不进公开仓库**（`.gitignore` 含 `samples/real/blind-*.docx` 与 `samples/real/*_media/`，插图亦为原论文派生物）。因此评测有两个口径：
>
> - **本地全量口径 = 16 篇 / 82 条**：先在本地生成 4 个盲测件（见下方命令）后运行脚本，`review`/`empirical`/`planted` 分组才纳入评测。
> - **仓库 tracked 子集口径 = 12 篇 / 68 条（CI 运行口径）**：盲测件缺失时 `eval_ac.py` / `ablation.py` **自动跳过**对应分组——实测 68/68 = 100% 检出、精确率 100%、定位 97%（fixtures 42 + real 26），`ablation.py --strict` 通过（要素 P/R/F1 86%/86%/86%）。

## `eval_ac.py` 实测

| 分组 | AC-2 检出率 | 精确率 | AC-3 定位 |
| --- | --- | --- | --- |
| fixtures | 42/42 = 100% | 42/42 = 100% | 40/42 = 95% |
| real | 26/26 = 100% | 26/26 = 100% | 26/26 = 100% |
| review | 不适用（期望 0） | 误报 0 | 不适用 |
| empirical | 不适用（期望 0） | 误报 0 | 不适用 |
| planted | 14/14 = 100% | 14/14 = 100% | 13/14 = 93% |
| **合计** | **82/82 = 100%** | **82/82 = 100%** | **79/82 = 96%** |

## 要素级标注与消融（`ground_truth/elements/`）

同一批 16 篇样本另带**要素级标注** `ground_truth/elements/<sample_id>.json`（「文档 × 要素类型」级，21 类词表要素 + `citation`/`reference_list`），用于 `ablation.py` 度量当前抽取器的要素 P/R/F1（实测 **90% / 90% / 90%**）。口径：**单次标注**（`annotator: single-pass`），规则为「要素被实质性报告/使用即标为存在，仅作通用术语一掠而过不计入」；`real-*` 为论文「方法」节**选段**，标注仅覆盖节选内容。

运行方式：

```bash
# 默认：仅规则引擎
python backend/scripts/eval_ac.py

# 模型采信模式（judge=llm 默认采信），需要联网和模型 Key
python backend/scripts/eval_ac.py --llm

# 消融矩阵（E/A/B/C/D）+ 要素 P/R/F1；--strict 作回归门禁（未达标返回非零）；加 --llm 补 D 配置
python backend/scripts/ablation.py --strict

# 刷新自建 fixtures
python backend/scripts/make_samples.py
```

本地生成盲测件（不入库，仅用于把本地补到 16 篇口径；`raw/` 缺失时跳过即可，脚本会自动按 12 篇运行）：

```powershell
Copy-Item samples/real/raw/盲测论文.docx  samples/real/blind-001.docx
Copy-Item samples/real/raw/盲测论文2.docx samples/real/blind-002.docx
Copy-Item samples/real/raw/盲测论文3.docx samples/real/blind-003.docx
Copy-Item samples/real/raw/盲测论文4.docx samples/real/blind-004.docx
```

> `blind-003`/`blind-004` 亦可用历史登记脚本 `python backend/scripts/register_blind003.py`、`python backend/scripts/register_blind004.py` 复现（含复制与标注写入）；二者标注已入库，日常只需上面的复制命令。

说明：

- fixtures 是受控短文本，只用于规则回归，不能代表真实论文难度。
- real 为公开论文方法/结果节选改写，指标仍偏乐观；最终以未见过的完整论文盲测为准。
- `--llm` 下 `judge=llm` 档的模型结论默认作为正式问题采信（实测引入 1 条 R-06 误报，精确率 100% → 99%）；`advisory` 档（R-05/R-10/R-11/R-12）一律降级为「存疑」，规则侧不受影响。