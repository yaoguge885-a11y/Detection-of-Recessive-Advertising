# P2/M2 工具舱技术验收记录

> 验收日期：2026-07-20

## 结论

七个工具均已进入注册表并达到 `ready=true`。默认零 Key 回归、真实 YOLO/EasyOCR 集成、同图上下文复用、30 对图文质量小测、固定脱敏样例演示和公共契约检查均通过，P2/M2 代码层技术验收完成。

P1 `data_schema v0.1` 尚未握手时，工具继续使用独立 Pydantic Input；收到 Schema 后只需增加帖子记录到工具输入的适配层，不修改七个工具的核心契约。

## 验收环境

- Python 3.10.11
- Windows，GPU 推理
- PyTorch 2.13.0+cu126
- CUDA Runtime 12.6，`torch.cuda.is_available() == True`
- NVIDIA GeForce RTX 4060 Laptop GPU
- YOLO11 nano 本地权重
- EasyOCR 中英文模型
- 视觉依赖来自 `requirements-vision.txt`

## 自动化结果

| 检查 | 结果 |
| --- | --- |
| 默认回归 | `58 passed, 2 skipped`；两个 skipped 为显式 opt-in 的真实视觉测试 |
| 真实视觉 integration | `2 passed` |
| 工具注册表 | 7/7 名称唯一、均有 docstring 与 Pydantic args schema，最小样例可独立调用 |
| 公共结果契约 | 七工具结果均可 JSON 序列化，状态、分数、证据和模型信息通过统一验收 |
| 视觉复用 | 三个视觉工具使用同一个 `VisionContext`；若发生第二次 YOLO/OCR 推理，测试立即失败 |
| 图文 sanity set | 30 对、四类关系全覆盖；匹配均值 0.668，错配均值 0.000，差值 0.668 |

## 真实视觉探针

- `samples/images/test_dog.jpg`：YOLO 检出 `dog`，置信度 0.883；同时检出 `frisbee`，置信度 0.486。
- 固定生成的高对比度文本图：EasyOCR 识别 `SALE 99`，置信度 0.951，并返回 bbox。
- GPU 复验中，固定狗图用例约 4.92 秒（包含模型初始化），模型已加载后的 OCR/复用用例约 0.23 秒。
- 固定七工具 demo 使用真实狗图约 4.71 秒；三个视觉工具的 `context_reused` 均为 `true`。

## 交叉评审修正

1. 将 Ultralytics 配置目录重定向到可写缓存，解决受限 Windows 环境无法读取 roaming settings 的问题；保留已有 EasyOCR 模型缓存。
2. 测试启动时强制关闭 LangSmith/LangChain tracing，确保默认回归不会因开发者 `.env` 意外联网或上传测试输入。
3. 增加真实视觉 marker 和 opt-in 策略，默认测试不加载重模型。
4. 增加七工具注册表最小调用验收，统一检查证据、模型信息、分数范围和 JSON 序列化。
5. 将 30 对图文集由两类扩展为 `aligned/complementary/conflicting/insufficient` 四类。
6. 固定演示改为读取 `samples/tool_demo_post.json`，并支持 `--image` 切换真实本地视觉路径。

## 已知非阻塞限制

- `image_text_consistency` 仍是 OCR bigram + YOLO 对象映射的降级实现，状态为 `degraded`，不是完整 VLM 图像语义理解。
- 当前没有专用 Logo 模型；`logo_candidates` 保持为空，品牌只作为 OCR 候选。
- 若 CUDA 不可用而回落 CPU，EasyOCR 可能出现 PyTorch 量化弃用和 `pin_memory` 警告，不影响降级路径正确性。
- 最终组内流程仍应完成 P1 Schema 握手以及 L/V 对验收记录的人工确认。
