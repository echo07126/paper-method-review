# archive/：50 个一次性历史脚本（已完成使命，仅供回溯）

- 本目录保存开发过程中一次性执行的补丁、修数据、标注和文档整理脚本；效果已合并进代码、样本或文档，日常不运行。
- CI 的编译检查只覆盖 `backend/scripts/*.py`，不会编译本目录。
- 后端 Dockerfile 只复制活动脚本，不把本目录打入运行镜像。
- 保留理由：答辩被追问“规则判据为什么这么写”时，可回溯原始修改过程，例如 `enhance_rules_round4.py`、`fix_r03_leakage.py`、`fix_r08_guard.py`、`label_real_005_007.py`。

当前活动脚本（24 个）：

`anchor_diff`、`api_check`、`blind_test`、`classify_check`、`consistency_check`、
`debug_sample`、`demote_check`、`deploy_gate`、`diagnose_format`、`eval_ac`、
`fetch_real_samples`、`gen_api_doc`、`inspect_samples`、`label_real_samples`、
`live_check`、`llm_check`、`llm_review_check`、`make_samples`、
`register_blind003`、`register_blind004`、`security_audit`、`smoke`、
`sync_check`、`update_ground_truth`。