# 文章结构自适应：让 Agent 自己决定类型与结构

日期：2026-10-21
状态：已实现（后端 393 项测试通过；前端 tsc/lint/build/测试全绿）
关联：`demand.md` §23、`docs/2026-09-24-article-chain-latency-and-publish-optimization.md` §16

---

## 1. 问题

> 这里的文章结构还是有问题，不能固定话，应该让 agent 自己决定文章的结构，
> 自己根据不同的类型文章 生成对应的文章结构。

---

## 2. 证据

### 2.1 三篇不同题材的文章，骨架完全一致（来自 `data/tasks.json`）

| 任务 | 小节数 | shape 序列 |
|---|---|---|
| 刚刚，GPT-6全面开放 | 2 | `evidence` → `tension` |
| 法国骚乱百年市政厅被烧毁 | 2 | `evidence` → `drivers` |
| 感悟"统筹区域发展"之道 | 3 | `evidence` → `drivers` → `tension` |

且这三篇的 `framework` / `narrative_arc` / `central_question` / `opening_move` / `ending_move`
**逐字相同**，`article_type` 全部为 `None`。

### 2.2 小节标题是截断的抓取文本

```
#法国骚乱商店餐馆被砸汽车被烧#】法国数十万人1为何在此时发生
从“腾笼换鸟仍待验证的部分
```

第二条是一个**开引号没有闭合**的残句；第一条是微博话题标签 + 省略号残留。

### 2.3 同一个话题，`selected_skill` 也永远一样

三篇题材（AI 产品、法国骚乱、区域发展政策）全部落到
`general_tech_explainer`（通用科技解读）——因为 `ARTICLE_SKILLS` 只有两个技能，
且用关键词打分。法国骚乱被打成"应用评测"。

---

## 3. 根因

### RC1（主因）模型的正确回答被 schema 丢掉了

日志原文：

```
plan_article_angle_fallback ... error=9 validation errors for BlueprintOutput
sections.0.key_evidence
  Input should be a valid string [input_value=['高铁约100分钟', '国家级算力枢纽之一'], input_type=list]
evidence_map.0.supporting_sources
  Input should be a valid string [input_value=['source_1', 'source_3'], input_type=list]
thesis
  Field required
```

`BlueprintOutput` 声明的是 `list[dict[str, str]]`，但模型很自然地写出：

- `key_evidence`：**证据条目的列表**
- `supporting_sources`：**来源 id 的列表**

两种表示都完全合理，却被判为 9 个类型错误 → **整份自适应蓝图被丢弃** → 回退到固定骨架。
提示词里"freely choose their number, order, and shape""Never output a fixed template"
全都写了，问题出在**回答没有被接收**。

### RC2 `thesis` 是唯一必填字段，一票否决

模型漏了 `thesis`（但填了 `central_question`）就整份作废。代价与信息量完全不成比例。

### RC3 兜底蓝图是单一固定骨架

`_NARRATIVE_JOBS` 按固定顺序遍历（event → evidence → drivers → case → tension），
标题 = **抓取文本前 24 字 + 固定后缀**，于是产生 2.2 的残句。

### RC4 类型系统互相打架且都偏技术向

| 系统 | 取值 | 判定方式 |
|---|---|---|
| `article_strategy` | auto / tech_breakdown / application_review / trend_outlook | 关键词 |
| `article_type` | trend_analysis / hotspot_interpretation | 关键词（只看 goal 串） |
| `selected_skill` | general_tech_explainer / quantum_tech_explainer | 关键词打分 |

三套都默认技术向，同一篇文章拿不到对应类型的结构。

### RC5 结构化阶段被截断

`text_fast` 未配置 → 所有结构化阶段走推理模型 `deepseek/deepseek-v4-pro-0813`
→ 日志中 `completion_tokens` 全部顶满预算（4000 / 1200 / 2500）
→ `llm_structured_truncated` → 各阶段退回确定性模板。

---

## 4. 改动

### 4.1 schema 变得宽容（修 RC1 / RC2）

- `key_evidence`、`supporting_sources` 这类**字符串列表**不再要求 `str`；
  `sections` / `evidence_map` / `source_driven_framework` 统一为 `list[dict[str, Any]]`。
- `thesis` 改为**可缺省**，并用 `model_validator(mode="after")` 依次从
  `central_question` → `reader_value` → `framework` → `narrative_arc` 回填。
  （用 after-validator 是因为字段顺序：`thesis` 声明在 `central_question` 之前，
  field-level validator 看不到候选值。）
- 空 payload 也能解析；`model_config` 允许额外字段，不再因为多一个键就报错。

### 4.2 兜底骨架改为按素材自适应（修 RC3）

- 新增 `_order_shapes()`：按**故事自身的因果依赖**排序
  （开场 → 事件/证据 → 解读 → 原因 → 场景 → 后果 → 未决），
  而不是遍历固定 job 表。未在表中的 shape 保留素材顺序，不会静默丢失。
- 新增 `_detect_opener()`：有热点原文 → `event` 开场；素材以官方/数据为主 → `evidence` 开场。
- `_build_source_driven_sections()` 增加 `opener` 参数并改用自适应顺序；
  证据以 `key_evidence` **列表**保存，而不是塞进一个长字符串。

### 4.3 标题质量闸门（修 2.2）

- 新增 `_heading_quality()`：对噪声字符（`#【】“”`）、截断尾巴（`为何在此时发生`、
  `仍待验证的部分`）、过长逗号串、悬空标点扣分，对疑问式/短标题加分；`<= 0` 即拒绝。
- 新增 `_recover_heading()` + `_clamp_heading()`：标题不可用时，**从该小节自己的
  `purpose`/`key_evidence` 重建**一个短标题，而不是套用主题占位符。
  实测把 `复盘政府、内政部门与地方警力的应对方式` 这类整句收窄为标题长度。
- `_normalize_sections()` 现在**保留模型给出的额外字段**（此前只留 heading/goal/shape，
  这也是上游类型错误的来源之一）。

### 4.4 类型由 Agent 自己命名，无预设枚举（修 RC4）

按要求**不预设枚举**：提示词要求 Agent 从素材判断类型并用**自己的话**命名，
同时允许运营在创建任务时指定覆盖。

- `BlueprintOutput` 新增 `article_type` / `article_type_reason` / `structure_rationale`。
- `clamp_type_label()`：模型偶尔会把类型写成整句标题
  （实测：`事件复盘：从一座百年市政厅被烧看法国骚乱的象征冲突与秩序风险`），
  此处收窄为 `事件复盘`；**标签内容仍是模型自己的措辞**，不是枚举映射。
- 兜底路径新增 `_derive_article_type()` / `_describe_structure()`：
  没有模型时也能给出类型与结构理由，`article_type` 不再恒为 `None`。
- 运营覆盖：`requested_article_type`（空 = 自动判断，`auto` 亦视为空）
  经 `GenerationConfig` → `normalize_generation_config` → `intake` → `task_brief` → 规划节点。
  在**模型成功与降级两条路径上都生效**。

> 注意：三套旧类型系统未删除（仍有引用方），本次让 `article_type` 成为
> **规划 Agent 的产出**。`article_strategy` / `selected_skill` 作为输入提示保留。

### 4.5 结构化阶段的 token 预算按 tier 放大（修 RC5）

- 新增 `runtime_settings.budget_for_tier()`：当阶段落在 `strong`（可能是推理模型）时，
  预算 ×6（上限 32000）。推理模型把隐藏推理计入同一个 completion 预算，
  按纯 JSON 估算的额度会在产出 JSON 前耗尽。
- `structured_chain()` 与 `invoke_structured()` 统一改用该函数。

---

## 5. 实测验证

对真实模型发起调用（修复前该路径正是 9 个校验错误的现场），得到：

```
article_type : 事件复盘
structure_rationale : 事件复盘需要回答"发生了什么、为何升级、谁参与、作何应对、留下什么"…
sections :
  楠泰尔的一声枪响：事件如何在最初几小时里失去控制
  呈现骚乱升级的空间和时间特征
  谁在愤怒、谁在趁乱：抗议者、街区居民与暴力实施者的重叠
  复盘政府、内政部门与地方警力的应对方式      ← 模型未给出可用标题，由该节 purpose 重建
  余烬未熄：赔偿、追责与下一次危机的未了结
```

同一路径此前输出的是固定两段式骨架。

---

## 6. 测试

新增 `tests/test_adaptive_article_structure.py`（28 项），后端合计 **365 → 393 passed**。

关键断言：

- **生产现场 payload 不再抛错**：`key_evidence` / `supporting_sources` 为列表时可解析，
  且原始结构完整保留；
- 缺 `thesis` 时从 `central_question` 回填，而不是丢弃整份蓝图；
- 空 payload 可解析（不再全有或全无）；
- `#法国骚乱…被烧#】法国数十万人1为何在此时发生` 与 `从"腾笼换鸟仍待验证的部分`
  **被拒绝**；`为什么要等10年才动手` 等可读标题**被保留**；
- 标题不可用时从该节证据重建，且**不是**主题占位符；
- **两个不同故事得到不同类型、不同 spine、不同标题**；
- 类型被收窄为标签而非整句标题，且保留模型自己的措辞；
- 覆盖：写入 → 归一化 → intake → task_brief → 规划节点的**端到端**生效；
  两种 config key（`generation` / `generation_config`）都能读到。

同时更新 5 处断言旧固定 token 预算的测试，改为断言 `budget_for_tier`。

---

## 7. 已知遗留

1. **`selected_skill` 仍只有 2 个技能且偏技术向**（法国骚乱 → 通用科技解读）。
   本次未动，因为它现在只是输入提示，类型与结构已由 Agent 决定；
   若要按题材选技能，需要扩充技能库，属于产品决策。
2. **`article_strategy` 与 `article_type` 语义重叠**，前端同时暴露两个字段。
   按"不预设类型枚举"的决定，`article_strategy` 暂留作提示；
   后续可考虑合并为单一入口。
3. **历史任务的 `article_type` 仍为 `None`**：旧数据不会回填。
4. **`plan_article_angle` 在 `strong` tier 的预算被放大到 18000**，
   对非推理模型是浪费；配置好 `OPENAI_FAST_MODEL`（非推理）后会自动回到 3000。
   这是刻意的保守选择：预算不足的失败模式是静默退化成模板文章，代价远高于多花 token。
