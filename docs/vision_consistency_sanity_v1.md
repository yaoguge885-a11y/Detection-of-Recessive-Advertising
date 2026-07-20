# 图文一致性 30 对 sanity set · v1

> 运行日期：2026-07-20

## 范围

本轮使用 30 对固定合成输入验证 `image_text_consistency` 的分数方向，其中 15 对语义匹配、15 对明显错配。测试直接构造独立的 `ImageTextConsistencyInput` 和 `VisionContext`，不依赖 P1 帖子 Schema，也不运行真实 YOLO/EasyOCR。

样例位于 `implicit-ad-agent/samples/vision_consistency_sanity.json`，自动验收位于 `implicit-ad-agent/tests/test_vision_consistency_sanity.py`。

## 结果

| 分组 | 数量 | 平均一致性分 |
| --- | ---: | ---: |
| 语义匹配 | 15 | 0.659 |
| 明显错配 | 15 | 0.000 |
| 均值差 | 30 | **0.659** |

固定测试要求匹配组平均分至少高于错配组 0.35，本次通过。30 个样例的关系类型也全部符合预期：匹配组为 `aligned`，错配组为 `conflicting`。

## 能力边界

这份结果只验证 OCR 字符 bigram 与 YOLO 对象映射降级算法的方向性和接口稳定性，不能当作真实图片准确率。真实视觉 integration 仍需在安装 `requirements-vision.txt` 的环境中运行，并使用许可清晰的图片复核 OCR、检测结果和耗时。
