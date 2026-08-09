# P5.3/P5.4 平台适配器 Synthetic Fixture 设计

## 1. 目标

在不启用真实平台联网采集的前提下，为小红书和 B站建立可回归的
平台适配器 fixture 工程链：

1. 保存明确标注为 synthetic 的 HTML/JSON fixture；
2. 对 fixture 做确定性解析；
3. 统一输出 `PostRecord + CaptureStatus`；
4. 分别表达正文、图片、评论和披露标记的采集状态；
5. 复用现有 URL preview、人工修正和 confirm 流程；
6. 用回归测试固定解析结果和安全边界。

本设计对应阶段计划中的 P5.3 小红书和 P5.4 B站。A2A、local/A2A
对照、登录、Cookie、验证码处理、大规模实时抓取和真实来源条款审批均不在
本阶段范围内。

## 2. 已确认的设计决策

- 第一批 fixture 采用结构仿真的 synthetic 数据，不声称来自真实页面。
- 保留 `partial`，新增 `unsupported`；不把部分采集降格成完全缺失。
- `PostRecord` 新增结构化 `disclosures`，只保存明确可观察的披露标记。
- synthetic fixture 必须包含脱敏的 `post_id` 和 `creator_id`，不生成占位身份。
- B站首轮覆盖 `video`、`opus`、`article`。
- 小红书首轮覆盖 `normal`、`video`。
- 只有图片 URL、没有安全本地图片文件时，图片状态为 `partial`。
- 适配器不默认注册到正式应用；测试显式注入 registry 和 fixture fetcher。
- 默认应用继续不宣称真实平台 URL 能力。

## 3. 方案选择

采用“平台专用解析器 + 严格共享规范化层”。

不直接导入 `data-tooling/crawler` 中的旧提取器。旧代码可以作为已知结构的
参考，但它与 Playwright、请求会话、评论 API、下载和宽松异常处理相邻，
不适合作为公开运行时依赖。

不建立配置化 JSONPath/CSS 规则引擎。当前只有两个平台和五种内容类型，
规则引擎会增加无必要的抽象、调试面和配置漂移风险。

数据流固定为：

```text
synthetic HTML/JSON
        -> 平台专用确定性解析器
        -> 严格内部规范化载荷
        -> 共享 PostRecord 构建器
        -> URLImportService.preview
        -> 人工修正
        -> URLImportService.confirm
```

## 4. 契约扩展

### 4.1 采集状态

`CaptureState` 保留现有值并新增 `unsupported`：

- `complete`：适配器声明的采集表面已完整检查；实际值允许为空；
- `partial`：只获得部分内容或只获得引用而没有可用内容；
- `missing`：该表面应可采集，但输入缺字段、结构异常或解析不完整；
- `unsupported`：当前内容类型或离线适配器明确不支持该表面；
- `not_applicable`：为现有非平台适配器保留兼容性，P5.3/P5.4 的四个目标
  模态不使用该值。

`CaptureModalityName` 新增 `disclosure`。小红书和 B站适配器必须在
`CaptureStatus.modalities` 中显式给出 `text`、`image`、`comment`、
`disclosure`，不能靠字段缺席表达未知状态。

### 4.2 结构化披露

新增严格模型 `DisclosureRecord`：

```text
kind: platform_badge | hashtag | text_statement
text: 非空的页面原始标记文本
source: platform_metadata | post_text
```

`PostRecord` 新增：

```text
disclosures: list[DisclosureRecord] = []
```

解析器只记录平台结构化徽标、精确标签和版本化明确短语，不从软性商业信号
推断披露或广告结论。完成检查但没有发现披露时，结果是
`disclosure.status=complete` 且 `disclosures=[]`，不是 `missing`。

### 4.3 下游覆盖兼容

`EvidenceSourceType` 增加 `disclosure`，`CoverageStatus` 增加
`unsupported`。采集到的结构化披露在本阶段只进入规范化记录和覆盖审计，
不新增分类器或 Judge 规则。

证据构建必须能映射 `disclosure`，并将 `unsupported` 保留为显式覆盖状态，
不能抛出未知枚举或把它转换成 `covered`。`unsupported` 可以形成明确的采集
限制记录，但不能当作负面证据。

充分性判断中：

- `text` 的 `partial`、`missing` 或 `unsupported` 均不能支持强制结论；
- `image=unsupported` 表示没有可运行的图片能力，不等价于图片已检查；
- `can_assess_disclosure=true` 只允许在披露表面完整，并且正文及需要检查的
  图片表面也足够完整时设置；
- `disclosures=[]` 本身不能证明“无披露”。

## 5. Fixture 目录与声明

目录使用案例名表达预期边界：

```text
implicit-ad-agent/tests/fixtures/platforms/
|-- xiaohongshu/
|   |-- normal_complete/
|   |   |-- source.html
|   |   |-- source_state.json
|   |   |-- manifest.json
|   |   `-- expected_post.json
|   `-- video_missing_comments/
|       |-- source.html
|       |-- source_state.json
|       |-- manifest.json
|       `-- expected_post.json
`-- bilibili/
    |-- video_no_images/
    |-- opus_partial_images/
    `-- article_missing_disclosure_surface/
        `-- 每个案例包含 source.html、source_state.json、manifest.json、
            expected_post.json
```

`source.html` 是最小结构仿真页面，`source_state.json` 是其中嵌入的 synthetic
状态载荷。两者不得包含真实账号、真实内容、Cookie、令牌或真实媒体 URL。
HTML 集成测试和 JSON 解析单元测试使用同一逻辑事实，防止两条解析路径漂移。

每份 `manifest.json` 必须包含：

- `fixture_version`；
- `synthetic: true`；
- `contains_real_user_data: false`；
- `network_required: false`；
- `platform`；
- `content_type`；
- 固定的四模态预期状态；
- `real_platform_compatibility_verified: false`；
- `terms_approved: false`。

`expected_post.json` 保存固定时间戳、固定 ID 和完整规范化结果，作为 golden
snapshot。该文件是工程契约，不是分类 Gold，也不提供研究准确率证据。

### 5.1 首批状态矩阵

| 案例 | text | image | comment | disclosure |
| --- | --- | --- | --- | --- |
| 小红书 normal | complete | partial | complete | complete |
| 小红书 video | complete | unsupported | missing | complete |
| B站 video | complete | unsupported | unsupported | complete |
| B站 opus | complete | partial | unsupported | complete |
| B站 article | complete | partial | unsupported | missing |

另用聚焦单元测试覆盖本表未出现但允许的组合，包括本地安全图片文件对应的
`image=complete`、空正文对应的 `text=missing`，以及完整检查后
`disclosures=[]` 的情况。

## 6. 解析规则

### 6.1 通用规则

- 解析器输出严格内部载荷，随后由共享构建器生成 `PostRecord`；
- `post_id` 和 `creator_id` 必须非空；缺失时解析失败；
- 时间必须归一化为带时区的 `datetime`；
- 列表保持源顺序并按稳定 ID 去重；
- 标题、正文和图片位置标记按固定顺序拼接成 `text`；
- 不使用随机值、当前时间或进程状态生成 fixture 输出；
- 不使用 `except Exception: pass`；
- 可选模态失败不销毁已成功解析的正文和身份字段，而是在
  `CaptureModality` 中记录稳定问题码和 `missing_fields`。

### 6.2 小红书

- 使用括号计数读取 `window.__INITIAL_STATE__`，不依赖非贪婪正则截取嵌套
  JSON；
- 支持 `normal` 与 `video`；
- 使用原生 note ID、脱敏 creator ID 和带时区发布时间；
- 图片 URL 生成 `MediaRecord(type="image")`；没有本地图片文件时状态为
  `partial`；
- 视频生成 `MediaRecord(type="video", ref=None)`，不下载视频；
- 评论列表存在或页面明确声明评论总数为零时为 `complete`；声明存在评论但
  没有可解析评论数据时为 `missing`；
- 结构化徽标和精确正文标记生成 `DisclosureRecord`。

### 6.3 B站

- 按 URL 和载荷结构确定性分流 `video`、`opus`、`article`；
- 视频映射标题、简介、bvid 和 creator ID；视频本体不下载，内容图片为
  `unsupported`；
- opus 映射标题、正文、dynamic ID 和图片位置；
- article 映射标题、正文、cv ID 和插图位置；
- 只通过额外评论 API 才能获得的评论统一为 `unsupported`，不发起请求；
- 不处理 `b23.tv` 等需要真实重定向的短链接；
- 不使用 aid、dynamic ID 或 cv ID 以外的临时占位身份。

## 7. 图片语义与媒体安全

- 已解析全部 synthetic 图片 URL、但没有本地文件：`partial`；
- 存在安全 cache root 内的本地文件及引用：`complete`；
- 内容类型支持图片，但应有图片而未解析到：`missing`；
- 内容类型不提供可分析的内容图片：`unsupported`。

fixture 使用 `example.test` 下的 synthetic HTTPS URL。测试 fetcher 只做确定性
目标验证，不下载媒体。URLImportService 继续通过 `PlatformMediaPolicy`
清除查询参数和片段，并拒绝私网、非 HTTPS、目录穿越和 cache root 外路径。

## 8. PlatformAdapter 与注册边界

新增 `XiaohongshuAdapter` 和 `BilibiliAdapter`，实现现有
`PlatformAdapter.preview(source, fetcher=...) -> PostRecord` 契约。版本明确
包含 fixture 阶段语义，例如 `xiaohongshu-fixture-v1` 和
`bilibili-fixture-v1`。

适配器类可以声明平台正式主域名用于 registry 路由，但正式应用的默认
registry 仍为空。专项测试显式构造：

```text
PlatformAdapterRegistry([XiaohongshuAdapter(), BilibiliAdapter()])
```

并注入只返回 fixture 字节的 fetcher。默认 `create_app()`、默认 capabilities
和默认 `DisabledURLFetcher` 均保持原状，因此不会对外宣称已具备真实平台
联网能力。

## 9. 人工修正

复用现有 `preview -> corrections -> confirm` 流程。

`URLImportCorrections` 新增 `disclosures`，并继续允许修正正文、creator ID、
发布时间、媒体、评论、历史和 capture status。工作台 URL 预览区域新增
disclosures JSON 编辑框。

以下字段继续不可修正：

- `post_id`；
- `platform`；
- `source_type`；
- `provenance`；
- `privacy`。

服务端继续覆盖并保护 `capture_status.source`、`adapter_version` 和已有
`user_corrections`。实际变化的 `disclosures` 或 `capture_status` 字段必须追加
到 `user_corrections`，无变化提交不产生虚假审计记录。

## 10. 失败与安全处理

- 缺少必填身份字段：解析器确定性失败，不生成 unknown 占位值；
- malformed HTML/JSON：产生稳定的内部解析错误，URL 服务边界对外保持无敏感
  信息的 `adapter_failed`；
- 可选字段异常：保留可用 PostRecord 字段，并在对应模态中记录问题；
- fixture 或 URL 中的查询秘密、片段、内部路径不得进入 preview、confirm、
  run store 或错误消息；
- 不保存 Cookie、Authorization、验证码、会话存储或真实用户标识；
- 不调用 Playwright、requests、平台评论 API、媒体下载器或任何真实网络；
- fixture 扫描必须拒绝疑似 Cookie、令牌、私钥、真实手机号和真实邮箱。

## 11. 回归测试

### 11.1 契约测试

- 新枚举和 `DisclosureRecord` 严格校验；
- `PostRecord.disclosures` 默认空列表，旧 manual/P1 输入保持兼容；
- Evidence coverage 支持 `disclosure` 和 `unsupported`；
- `unsupported` 不成为负面证据，文本不支持会触发复核而非强制结论。

### 11.2 解析 golden tests

- 小红书 normal、video；
- B站 video、opus、article；
- HTML 和 JSON 两种入口映射到同一个 `expected_post.json`；
- 同一 fixture 重复解析得到字节等价 JSON；
- 标题/正文顺序、图片位置、ID、时间、评论、披露和四模态状态均精确比较。

### 11.3 错误与状态测试

- 必填 ID 缺失时失败；
- 可选模态缺失时仍返回 PostRecord；
- `complete/partial/missing/unsupported` 状态矩阵；
- URL-only 图片不下载并保持 partial；
- safe cache 本地图片为 complete；
- 视频和外部评论 API 为 unsupported；
- 完整检查但无披露为 complete + 空列表。

### 11.4 URL 与人工修正测试

- 显式 registry 解析两个平台；
- fixture fetcher 注入且不访问网络；
- preview 后可修正 text、media、comments、disclosures、capture status；
- 变更字段进入 `user_corrections`；
- 不可变字段和审计字段不能伪造；
- 默认应用仍报告空平台列表。

### 11.5 工作台与安全回归

- disclosures 编辑框正确回填、解析和提交；
- malformed JSON 不发送确认请求；
- fixture manifest 全部声明 synthetic/no-network/no-real-user-data；
- 安全扫描未发现秘密或真实个人信息；
- 现有 URL safety、media safety、P5.7 安全测试继续通过。

验证顺序为平台聚焦测试、受影响契约/编排/API/Web 测试、全量测试、
`compileall`、`pip check` 和 `git diff --check`。测试结果只能证明 synthetic
fixture 工程契约，不能证明真实平台解析率、研究准确率或条款合规。

## 12. 文档与验收边界

实现完成后只允许记录以下工程结论：

- P5.3/P5.4 synthetic fixture 解析链已实现；
- 五种内容类型能产生统一 PostRecord；
- 四目标模态状态、人工修正和回归测试有当前输出证据；
- 默认应用未启用真实平台联网。

不得据此声明：

- 真实小红书/B站页面兼容；
- 来源条款、隐私或安全审批已完成；
- 登录、Cookie、验证码或反爬问题已解决；
- M5、P5.5、P5.6 或 A2A 已完成；
- synthetic fixture 指标代表研究效果。

## 13. 完成标准

本设计的实现完成必须同时满足：

1. 五个首批 fixture 案例及 manifest/expected snapshot 均存在且通过扫描；
2. 两个平台适配器和共享规范化层均为确定性、零网络；
3. PostRecord、CaptureStatus、disclosures 和 evidence coverage 契约一致；
4. 四目标模态的状态和问题字段有聚焦测试；
5. 人工修正覆盖 disclosures 且审计元数据不可伪造；
6. 默认应用不注册平台适配器；
7. 聚焦测试和全量回归通过；
8. 文档明确 synthetic、未联网、未完成条款审批和未通过 M5。
