# 图文一致性 30 对 sanity set · v1

> 运行日期：2026-07-20

## 范围

本轮使用 30 对固定合成输入验证 `image_text_consistency` 的分数方向与四态关系，其中包括语义匹配、互补、明显错配和信息不足。测试直接构造独立的 `ImageTextConsistencyInput` 和 `VisionContext`，不依赖 P1 帖子 Schema，也不运行真实 YOLO/EasyOCR。

样例位于 `implicit-ad-agent/samples/vision_consistency_sanity.json`，自动验收位于 `implicit-ad-agent/tests/test_vision_consistency_sanity.py`。

## 结果

| 分组 | 数量 | 平均一致性分 |
| --- | ---: | ---: |
| 语义匹配（`aligned`） | 12 | 0.668 |
| 互补（`complementary`） | 3 | 0.300 |
| 明显错配（`conflicting`） | 12 | 0.000 |
| 信息不足（`insufficient`） | 3 | `null` |
| 匹配－错配均值差 | 24 | **0.668** |

固定测试要求匹配组平均分至少高于错配组 0.35，本次通过。30 个样例的关系类型全部符合预期；信息不足样例返回 `skipped` 和 `score=null`，没有用 0 分冒充正常证据。

## 能力边界

这份结果只验证 OCR 字符 bigram 与 YOLO 对象映射降级算法的方向性和接口稳定性，不能当作真实图片准确率。真实视觉 integration 已另行通过，结果记录于 `docs/m2_verification_report.md`。
