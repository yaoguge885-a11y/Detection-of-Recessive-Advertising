# scripts/data/annotation — 标注与质量控制脚本
# 
# 包含：
#   标注工具：
#     - manual_review_annotate.py   手动复核标注 CLI
#     - auto_image_annotate.py      图像自动标注 (YOLO+OCR)
#   Schema 与数据：
#     - validate_schema.py          Schema 校验（读权威 schema）
#     - migrate_p1_candidates_to_v1.py  P1 候选数据迁移
#     - report_p1_migration.py      迁移报告
#   质量控制：
#     - normalize_and_deduplicate.py  规范化与去重
#     - calculate_agreement.py       标注者一致性 κ 计算
#     - build_gold_dataset.py        金标数据集构建
#     - split_by_blogger.py          按博主分组划分数据集
#   合规：
#     - privacy_scan.py             隐私合规扫描
