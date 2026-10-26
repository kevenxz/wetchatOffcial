# 图片生成链路重做：从「拼字符串」到「先写视觉描述」

日期：2026-10-10
状态：已实现（后端 363 项测试通过；人工看图验收待运营确认）
关联：`docs/2026-09-24-article-chain-latency-and-publish-optimization.md` §16（结构化输出）、`demand.md` §22

---

## 1. 问题

运营反馈三条：

1. **生成的图片与文章内容不符合**；
2. **图片都是文本**；
3. **图片风格有问题**。

三条都成立，而且有同一个根因：**这条链路从来没有"描述画面"的步骤。**

---

## 2. 证据

### 2.1 实际发给图像模型的提示词（来自 `data/tasks.json`）

```
cover for 刚刚，GPT-6全面开放，免费用户也能用了, clean composition, mobile readable,
no watermark. Article section: 封面. Purpose: 用文章核心判断吸引点击.
Use these article/data signals: 刚刚，GPT-6全面开放，免费用户也能用了需要放回搜索证据里判断：
哪些已经被证明，哪些仍只是信号。. No fake UI screenshots, no unreadable small text,
no watermark., style preference: Modern technology style, clear diagrams first,
avoid exaggerated sci-fi posters., brand colors: not specified
```

这张图的提示词里**没有一句话在描述画面里应该有什么**。

### 2.2 同一任务的另一张图（`infographic`）

其"数据信号"就是抓取到的**转载样板文字**：

```
以下文章来源于科创板日报 ，作者史正丞 专注科创板和科技创新，上海报业集团主管主办，界面财联社出品。
```

并把这段文字丢给图像模型"**use these signals**"。

### 2.3 落库的 `visual_plan`

```json
{"asset_roles": ["cover", "infographic"], "quality_threshold": 75,
 "style": "Modern technology style, clear diagrams first, avoid exaggerated sci-fi posters.",
 "brand_colors": [], "title_safe_area": true}
```

注意 `clear diagrams first` —— **要求画图表，图表就是文字**。

---

## 3. 根因

| 编号 | 根因 | 说明 |
|---|---|---|
| RC0 | **文章本身仍是模板**（前置阻塞） | `text_fast` 未配置 → 结构化阶段仍走推理模型 → 截断 → 蓝图回退模板。证据：封面的"文章信号"是 `_build_fallback_blueprint` 的 `thesis_map["general"]` 模板句。**配图质量的上限是文章内容** |
| RC1 | 没有"写画面"的步骤 | `visual_briefs.py:19` 的模板 + `visual_plan.py` 的拼接：role token + 主题 + 抓取正文 + 英文样板 |
| RC2 | role 标识符被当成主语 | 拼出 `cover for <主题>` / `infographic for <主题>`，模型把内部标识符当画面主题 |
| RC3 | 输入与措辞共同诱发文字 | `infographic` 角色名、`clear diagrams first`、`Use these article/data signals: <中文原文>`，并点名 `text`/`watermark`/`UI screenshots` |
| RC4 | 抓取垃圾进入提示词 | 转载样板经 outline 的 `goal`（`可用证据：…`）进入 `purpose` 与 `key_points` |
| RC5 | 风格英文、自相矛盾、排最后 | `clear diagrams first` 与 `avoid exaggerated sci-fi posters` 互相矛盾；被拼在 600+ 字符噪声之后 |
| RC6 | **审核是假的** | `review_visual_assets_node` 从不看图，固定给 `score: 82`；且占位图 `generated://<role>` 的 `path` 为真值，**生成失败也算通过** |
| RC7 | 提示词过长 | 实测 ~700–900 字符、中英混杂 |
| RC8 | **图片没有出口** | `ImageManage.tsx` 只有 11 行占位；无列表接口；~90 张图（≈110 MB）无界面可审阅 |

---

## 4. 改动

### 4.1 新增视觉描述阶段（核心）

`workflow/agents/visual_describer.py`：调用结构化模型，为每张图产出一份 `VisualSpec`。

```python
class VisualSpec(BaseModel):
    asset_index: int   # 用于回填到对应 brief
    role: str
    subject: str       # 画面主体：必须是具体物件/场景
    setting: str       # 环境、材质、光线、机位
    composition: str   # 构图与留白
    section_link: str  # 与所在小节论点的关系（审计用，不进提示词）
```

- **一次调用覆盖全部配图**，保证同任务风格一致，成本是一次而不是每图一次。
- 输入严格限量：标题、中心论点、小节标题、**清洗后**的论点，禁止传入原始抓取正文与 `可用证据：` 原串。
- 提示词明确要求：物理名词、禁止文字/图表/UI/logo、字段长度上限、全英文。

### 4.2 短提示词组装

`workflow/utils/visual_spec.py`：

```
{风格句}. {主体}. {环境}. {构图}. No text, letters, numbers, logos, or watermarks anywhere in the image.
```

- 默认上限 **400 字符**（可配，硬上限 900）。
- 超长时按 **构图 → 环境 → 风格句** 的顺序裁掉，**主体与文字排除句永不裁掉**（主体承载内容）。
- 只用**一处**文字排除句；历史上那三处（`no watermark`/`no fake UI screenshots`/`unreadable small text`）全部移除——图像模型会画出被点名的概念。

### 4.3 风格预设取代英文散串

`workflow/utils/image_styles.py`，默认 `editorial_photo`（编辑部摄影感）：

| id | 名称 |
|---|---|
| `editorial_photo` **默认** | 编辑部摄影感（真实场景、自然布光、浅景深、克制冷调） |
| `concept_illustration` | 概念插画 |
| `minimal_geometric` | 极简几何 |

- 预设的 `avoid` 列表**只用于校验**，绝不拼进提示词（原因见上）。
- 移除 `article_skills.py` 的 `visual_style` 在出图链路上的用途。
- 前端「图片风格」由自由文本改为**预设下拉**（从 `/api/images/styles` 拉取，静态兜底）。

### 4.4 role 语义修正

| 旧 | 新 | 说明 |
|---|---|---|
| `infographic` | `data_scene` | 不再要求图表；改为"有数据氛围的实拍场景"（仪表、刻度、屏幕辉光、机架指示灯），**数字留在正文**，由文字承载 |

兼容：`infographic` 作为历史角色名仍在评审与宽高比表中保留。

### 4.5 抓取垃圾清洗

`workflow/utils/claim_clean.py`：剔除转载样板、署名、URL、截断省略号，按句边界截断。
`visual_plan.py` 新增 `_split_goal()`：把 `可用证据：…` 从 `purpose` 拆出并清洗进 `key_points`。

### 4.6 审核改为诚实

`workflow/agents/visual_reviewer.py`：

- **修复占位图误判**：`generated://` 前缀计为缺失（新增 `is_generated_asset()`）。
- **删除写死的 `score: 82`**，改为 `check: "structural_only"` + `missing` + `findings`。
- 附 `note` 明说：本系统没有视觉模型，无法判断内容是否一致、是否夹带文字，请人工确认。
- 缺失时置 `visual_degraded_reason`。

### 4.7 补上审计面

- 新增 `api/routers/images.py`：`GET /api/images`（按任务聚合，含 prompt 与 visual_spec，支持 `degraded_only`）、`GET /api/images/styles`。
- `ImageManage.tsx` 由 11 行占位改为真实列表：缩略图、风格、**视觉描述**、**最终提示词**、所属任务、时间、失败标记，并支持"仅看失败"。

### 4.8 安全网

`generate_visual_assets_node` 在生成前检查：若某 brief 没有提示词（续跑/导入状态/阶段被跳过），用兜底 spec 组装一个无文字的提示词，**绝不把空字符串发给图像模型**。

---

## 5. 关键设计决定

1. **三个步骤放在同一个图节点内**（describe → generate → review）。
   `image_agent` 分支必须保持深度 1，否则 `quality_gate` 的 join 会提前触发并重复执行（上一轮已修的缺陷）。放在节点内部既保持深度不变，也不阻塞 `parallel_review` 分支。
2. **`plan_visual_assets` 不再构建提示词**，只产出结构信息（角色、小节、尺寸、清洗后的输入）。
3. **描述只写一次**（一次调用覆盖全部图），而非每图一次。
4. **`describe_visual` 必须注册进 `STRUCTURED_STAGES`**，否则会走推理模型 tier，重演截断问题。
5. **风格描述用英文**（图像模型对英文风格控制更稳定），但**不引用任何中文原文**——由模型把含义翻译成视觉名词。
6. **品牌名/产品名不作为画面文字或 logo 出现**。

---

## 6. 顺带修掉的缺陷

| 缺陷 | 说明 |
|---|---|
| 占位图通过审核 | `generated://infographic` 的 `path` 为真值，旧检查判为"有资产" |
| 写死 `score: 82` | 与实际质量无关的伪分数，让运营以为审过了 |
| `forbidden_concepts_in` 子串误判 | 新写的校验函数最初用子串匹配，导致 **"photograph" 含 "graph"**、"quiet"/"equipment" 含 "ui"、"texture" 含 "text"，几乎会拒掉所有合法 spec。已改为**词边界正则**，并补了 4 条回归测试 |
| 列表接口分页截断 | `_iter_task_images` 最初按 `limit` 逐任务切片，导致 `total` 错误且丢数据。改为全量收集后再分页 |
| 相对路径无法访问 | `artifacts/...` 相对路径未映射到 `/artifacts/...` 挂载点 |

---

## 7. 测试

新增 4 个测试文件（+38 项）：`test_image_styles_and_claim_clean.py`（20）、
`test_visual_prompt_assembly.py`（20）、`test_review_visual_assets.py`（8，重写）、
`test_images_router.py`（8）。后端合计 **363 passed**。

关键回归断言：

- 提示词**不以 role 标识符作主语**，且**不含** `cover for` / `infographic for`；
- 提示词**不含**任何抓取样板（`以下文章来源于`、`主管主办`、`界面财联社`、`可用证据`）；
- 提示词**只含一处**文字排除句，且不含全部历史触发短语；
- **主体在极紧预算下仍然保留**（150/200/300/400 四档）；
- 请求画图表的 spec 被拒绝并回退到安全 spec，且记录降级原因；
- 占位图判为缺失、`missing` 正确、**不再返回 `score`**；
- 无模型时全链路降级但提示词依旧干净。

---

## 8. 已知遗留与验收

1. **人工验收必须由运营完成**：本会话所用模型不支持图像输入，无法自动判断"图里是否还有文字"。
   路径：先配好结构化模型（RC0），跑一条真实任务，再打开「图片管理」逐张确认。
2. **不引入视觉模型就无法自动判断画面内容**。本次以「提示词层保证 + 审核如实标注 + 列表页人工确认」
   替代，而**不声称已自动达标**。
3. **历史任务仍显示旧提示词**（改造前生成的记录）。这恰好可用于前后对比。
4. **生成图不清理**：`artifacts/generated_images/` 已 ~90 张 / ≈110 MB。审计面已补齐，清理策略待定。
5. **`image_allow_text` 开关已真正生效**：关闭时（默认）提示词带文字排除句；打开时去掉该句，
   并把 `text_allowed` 传给视觉描述阶段。两条行为各有测试覆盖（避免出现"界面上有开关但不改变行为"
   这种与伪分数同类的误导）。

---

## 9. 部署检查

- 新增环境变量（均有默认值，可不配）：`IMAGE_STYLE_PRESET`、`IMAGE_ALLOW_TEXT`、
  `IMAGE_PROMPT_MAX_CHARS`、`LLM_MAX_TOKENS_VISUAL_SPEC`。
- 新增接口：`GET /api/images`、`GET /api/images/styles`（沿用既有 Token 鉴权）。
- 图片通过既有 `/artifacts` 静态挂载访问，无需新增 nginx 规则。
- **前置项**：为结构化阶段配置非推理模型（`OPENAI_FAST_MODEL`），否则 RC0 未解，
  配图上限被模板文章锁死；`GET /api/config/model/effective` 可确认是否生效。
