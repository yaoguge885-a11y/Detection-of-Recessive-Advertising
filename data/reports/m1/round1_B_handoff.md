# M1 Round 1：B 盲标交接说明

## 独立性要求

- B 只接收 Round 1 输入、manifest、冻结前标注指南和自己的启动命令。
- 在 B 完成 100 条之前，不得查看 A 的标注文件、标签分布、证据或逐条判断。
- B 的输出目录固定为 `data/run_outputs/m1_annotations/round1/B`，标注人 ID 必须为 `B`。

## 输入校验

- 批次 ID：`m1_round1_100_2991`
- 记录数：100
- Bilibili：74
- 微信公众号：26
- Round 1 JSONL SHA-256：`3ff71c9f51de8c137f25934ae20ef65dcb8933cca9264d18a873488725de76e5`
- 标注指南 SHA-256：`4d03c11298c5e895b6607992adc387516b9c9c60d76b40f6c528aac24a15a316`

如哈希不一致，应停止标注并联系 A/C，不得继续使用被修改的批次。

## B 启动方式

B 需要拥有同一仓库和已解压的 `merged_20260728` 数据集。在仓库根目录执行：

```powershell
.\scripts\start_round1_B.ps1
```

如果执行策略阻止脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_round1_B.ps1
```

每条记录先按 `v` 查看媒体，再按 `n` 独立填写标签、证据代码、置信度和文字证据。`q` 保存退出；重新运行脚本可断点续标。

## B 完成后的交付

B 只需把以下目录中新生成的 `B_*.json` 文件交给负责计算一致性的人：

```text
data/run_outputs/m1_annotations/round1/B/
```

只有确认 A、B 都完成 100 条后，才允许把两份文件放在一起计算 Round 1 一致性并解盲讨论。
