# 2026-04-26 文章大纲与 Image Agent 实现说明

## 背景

`docs/xitong.md` 要求内容生产链路必须按以下顺序执行：

```text
搜索与素材提取
  -> Planner 生成文章大纲
  -> Writer 按大纲写正文
  -> Reviewer 审核
  -> Image Agent 规划并生成封面/文内图
  -> 成稿组装
  -> 页面展示/草稿箱
```

本次实现重点解决三个问题：

- 文章结构不能固定模板化，必须由 AI 根据搜索内容和证据包自行决定标题、子标题和章节结构。
- 图片不能独立生成，必须由 Image Agent 根据文章内容、章节重点和数据自行规划。
- 前端任务详情页必须能展示完整图文文章，图片插入正文对应位置。

## Workflow 变更

### 1. 新增 `outline_planner`

新增文件：

- `workflow/skills/outline_planner.py`

职责：

- 调用现有搜索证据驱动的文章角度规划能力。
- 生成符合 `xitong.md` 的 `outline_result`。
- 将标题候选、文章框架、章节目标、证据映射、风险边界和图片规划种子写入共享状态。

输出结构：

```json
{
  "framework": "AI 自主判定结构",
  "title_candidates": [],
  "thesis": "",
  "reader_value": "",
  "outline": [
    {
      "section": "",
      "goal": "",
      "shape": "",
      "source_refs": [],
      "key_points": [],
      "image_hint": "inline"
    }
  ],
  "must_use_facts": [],
  "risk_boundaries": [],
  "source_driven_framework": [],
  "evidence_map": [],
  "image_plan_seed": {
    "cover_needed": true,
    "inline_count": 2
  }
}
```

### 2. Writer 强制按大纲写作

`workflow/skills/compose_draft.py` 现在会读取：

- `outline_result`
- `source_driven_framework`
- `evidence_map`
- `must_use_facts`
- `risk_boundaries`

写作约束：

- 正文必须按 `outline_result.outline` 的顺序和目标写。
- 标题和子标题由 AI 生成，但必须基于大纲和搜索证据。
- 不允许把搜索驱动结构替换成通用模板。
- 证据不足时必须写证据边界，不能硬编结论。

### 3. 新增 `image_agent`

新增文件：

- `workflow/skills/image_agent.py`

职责：

- 作为明确的生图 Agent 节点接入 workflow。
- 使用现有 `ModelConfig.image` 图片模型配置。
- 包装 `generate_visual_assets_node`，并在 `visual_state.agent` 中记录 Agent 元信息。

### 4. 图片规划基于文章内容

`workflow/skills/plan_visual_assets.py` 改为优先读取：

- `outline_result.image_plan_seed`
- `outline_result.outline`
- `writing_state.draft`
- `config_snapshot.image_policy`

规划逻辑：

- 封面图默认围绕文章核心判断生成。
- 文内图优先绑定 `evidence`、`case` 等章节。
- 每张图片 brief 会包含 `section`、`purpose`、`key_points`、`source_refs`。
- 生图 prompt 会包含文章段落目标和数据/事实线索。

### 5. 成稿组装补齐图文数据

`workflow/skills/assemble_article.py` 现在会把以下内容写入 `final_article`：

- `outline_result`
- `image_plan`
- `images`
- `html_content`
- `cover_image`
- `illustrations`

`html_content` 通过 Markdown 转 HTML 生成，并把 `[插图N]` 替换为对应图片。

## API 与前端变更

### 1. API 字段

`TaskResponse` 新增：

- `outline_result`

workflow result payload、任务重试状态、任务同步逻辑都已补齐该字段。

### 2. 静态图片访问

`api/main.py` 新增 `/artifacts` 静态目录挂载。

本地生成的图片保存在：

```text
artifacts/generated_images
```

前端会把本地图片路径转换为 `/artifacts/...` 进行展示。

### 3. 任务详情页图文展示

`frontend/src/pages/TaskDetail.tsx` 现在支持：

- 展示封面图。
- 渲染 Markdown/HTML 正文。
- 将 `[插图N]` 替换为真实文内图片。
- 展示文章大纲。
- 展示图片计划。
- 展示图片资产。

## 测试覆盖

新增测试：

- `tests/test_outline_planner.py`
- `tests/test_image_agent.py`

验证命令：

```text
python -m compileall api workflow tests
pytest -q
cd frontend
npm run build
npm run test -- --run
```

验证结果：

- 后端：`126 passed`
- 前端：`44 passed, 1 skipped`
- 前端构建：通过

前端测试仍有项目既有 React Router future flag、AntD `destroyOnClose`、jsdom `getComputedStyle` 警告，不影响结果。
