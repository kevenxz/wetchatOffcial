# 前端设计系统重建与公开门面页（明亮极简瑞士风）

日期：2026-10-09
范围：`frontend/`（设计令牌层、基础层、布局组件、Shell、门面页、动效原语）与文档治理
目标：按设计奖项（Awwwards 等）标准重建页面样式；"页面模型"= 设计系统/令牌层先建立

---

## 1. 起因与诊断

用户要求以拿设计奖为目标重做页面样式，并指出"页面模型需要配置"。这里的"页面模型"经确认为
**设计系统 / 令牌层需要先建立**。

改造前的实测问题（均为实测，非印象）：

| 问题 | 证据 | 影响 |
|---|---|---|
| favicon 是坏链 | `frontend/public/` 为空，`index.html` 引用 `/vite.svg` | 提交页 404 图标 |
| 字体从未加载 | 令牌与 antd 主题声明 `Noto Sans SC` / `Noto Serif SC`，但无 `<link>`、无 `@font-face` | 期望的衬线编辑感完全没渲染，落回 SimSun |
| 两套令牌并存 | `--app-*`（暖纸+青）与 `--color-*`/`--text-*`/`--bg-*`（冷蓝灰）语义重名 | 同一变量在不同主题下解析不同值 |
| 浅色配色复制两份 | `variables.css` 的 `:root`(1–135) 与 `:root[data-theme='light']`(137–189) | 改色必须改两处，必然漂移 |
| 品牌色自相矛盾 | 代码 `#0f766e` vs `CLAUDE.md` 写的 `#1677FF` | 无法作为设计基线 |
| 101 处内联 `style={{}}` | TaskCreate 34、StyleConfig 25、ScheduleManage 14… | 违反仓库规定，主题化不可能彻底 |
| 7/15 页面无 CSS Module | ModelConfig / StyleConfig / ScheduleManage / AccountConfig / ImageManage / UserManage / History | 完全靠内联样式拼装 |
| 零动效 | `@keyframes` 0 个、`view-transition` 0 个、`prefers-reduced-motion` 0 条 | 与"大胆动效"目标差距最大 |
| 焦点态几乎没做 | `focus-visible` 仅 2 处、`aria-live` 0 处 | 键盘可用性不达标 |
| 无公开门面 | `/` 在 `RequireAuth` 内重定向到 `/task` | 评奖没有可看的门面页 |

现成资产：`Login.module.css` 已有真正的美术指导（巨型「爆」字底纹、`clamp()` 流体字阶、等宽小标签）；
导航元数据里的 `contextEyebrow` / `contextDescription` 被 `display: none` 主动隐藏；真实 23 节点管线本身极具视觉叙事价值。

---

## 2. 设计方向：明亮极简瑞士风

| 维度 | 规则 |
|---|---|
| 色彩 | 近单色：纸 `#FAFAFA` / 面 `#FFFFFF` / 墨 `#0A0A0A` / 次级 `#3F3F46` / 三级 `#71717A` / 发丝线 `#E4E4E7`；**单一强调色**青绿 `#0F766E` |
| 圆角 | 面块 `0`，控件 `2px` |
| 阴影 | 默认无；层级用发丝线；仅浮层保留一层高度阴影 |
| 字体 | 拉丁与中文均走系统栈（见第 3.4 节关于未引入字体的说明） |
| 字阶 | 12 / 13 / 14 / 16 / 20 / 28 / 40 / 64 / 96，行高 1.05 / 1.2 / 1.4 / 1.5 / 1.7 |
| 字距 | 大标题 `-0.03em`，等宽小标签 `+0.16em` 大写 |
| 网格 | 12 栏 / 24px 沟槽 / 内容最大宽 1440 / 基线 8px |

**为什么强调色不是瑞士经典红**：本产品是运营控制台，红/琥珀/绿已被状态语义占用，
再加一个红色会让"危险"与"品牌"产生歧义。青绿可同时满足品牌与语义共存。

---

## 3. 阶段一：令牌层（唯一真源）

### 3.1 `styles/tokens.css`

三层结构，重构掉了原来的两套并行体系：

1. **原始层**（主题无关，只声明一次）：`--ink-*`、`--paper-*`、`--line-*`、`--accent-*`、
   `--status-*`、`--space-*`、`--type-*`、`--leading-*`、`--tracking-*`、`--weight-*`、
   `--radius-*`、`--elevation-*`、`--dur-*`、`--ease-*`、`--font-*`、`--layout-*`、`--z-*`
2. **语义层**（组件只能使用这一层）：`--surface-*`、`--text-*`、`--border-*`、`--accent*`、`--status-*-text/-subtle`、`--focus-ring`、`--grid-line`
3. **深色主题**：`:root[data-theme='dark']` **只覆盖语义层**（约 40 行），不再复制调色板

### 3.2 防漂移：`styles/tokens.ts` + `tokenParity.test.ts`

令牌值在 CSS 里（组件要用），但 antd 需要在 JS 里拿到同一批值。两份手抄的调色板必然漂移
——`#1677FF` 与 `#0f766e` 的分歧就是这么来的。做法：

- `tokens.ts` **只镜像 CSS 值是字面量的那些令牌**（原始层 + 深色语义字面量）；
  指向别名的令牌（如 `--surface-page: var(--paper-50)`）刻意不镜像，由 antd 从原始层派生。
- 字体族以 `var(--font-sans)` / `var(--font-mono)` 传给 antd，因此类型栈只有一处定义。
- `tokenParity.test.ts`（**62 项**）解析 `tokens.css`，逐值比对，并断言：
  每个原始令牌在全文件只定义一次；深色主题不含非语义令牌；深色主题不重定义原始令牌。

### 3.3 `variables.css` 降级为兼容别名块

原 246 行令牌文件改为约 150 行别名映射（`--app-*` → `--surface-*` 等），使 15 个尚未迁移的页面
继续工作。其中两项是刻意的行为改变：

- `--app-bg-gradient` 与 `--app-sidebar-bg-layer` **被抹平为纯色**：瑞士风格的面是平的。
- `--app-shadow-sm/md` → `none`：卡片不再有阴影，层级改由发丝线表达。

### 3.4 字体：一个必须说明的偏差

计划假设可以自托管一个 ≤60KB 的拉丁紧体。实际核查：`node_modules` 内**没有任何 woff2/woff**，
`public/` 为空，Windows 系统字体（Segoe UI 等）**不可再分发**。
因此**没有引入字体文件**，而是：

- 拉丁与中文统一使用高质量系统栈；
- 把瑞士身份建立在**排版纪律**上（严格模数、负字距、等宽大写小标签、`tabular-nums`、发丝线、网格）；
- 在 `tokens.css` 留出接入点（注释说明放入 `public/fonts/` 后前置到 `--font-sans` 并补 `@font-face`）。

这比加一个指向不存在文件的 `@font-face`、或塞入一个无授权字体要诚实得多。

---

## 4. 阶段二：基础层

| 项 | 结果 |
|---|---|
| favicon | 新增 `public/favicon.svg`（单色瑞士网格标记），修掉坏链；`apple-touch-icon`、`theme-color`（明/暗各一）、`og:*`、`twitter:card` 一并补上 |
| 品牌标记 | 新增 `components/brand/BrandMark.tsx`（内联 SVG，用 `currentColor`/令牌随主题反转），替换 Shell 里临时用的 `WechatOutlined` |
| 分享图 | 新增 `public/og-image.svg`（1200×630，含管线抽象与真实技术栈文字） |
| `global.css` | 抹平渐变背景；标题改用无衬线 + 负字距（原本声明的衬线字体从未加载）；新增全局 `:focus-visible`；新增 `prefers-reduced-motion` 全局兜底；滚动条改发丝；表格表头改等宽大写 + `tabular-nums`；删除主按钮发光阴影 |
| 遗留脚手架 | `.backstage-*` 层刻意继续使用 `--app-*` 别名，作为"待迁移"的显式标记 |

---

## 5. 阶段三：布局组件与 Shell

### 5.1 布局原语（`components/layout/`）

`PageHeader`（eyebrow / title / description / actions）、`Panel`（唯一的表面容器：发丝边框、直角、无阴影）、
`Toolbar`、`StatGrid` + `Stat`（1px 网格间隙 + 边框色背景做出真实分隔线）、`EmptyState`、
`KeyValueList`（`dt`/`dd` 必须是网格直接子元素，因此用带 key 的 Fragment 而不是 `div`）、
`Stack` / `Split` / `Grid`。

### 5.2 Shell 重做

- 侧栏：直角、发丝分隔、当前项用**左侧 2px 强调条 + 字重**（而不是整块填色）。
- 顶栏：**启用**此前被 `display: none` 隐藏的 `contextEyebrow` / `contextDescription`，
  形成「等宽小标签 → 页面标题 → 说明」的编辑式层级。
- 新增 **⌘K / Ctrl+K** 聚焦全局搜索，并在输入框内显示平台对应的快捷键提示。
- 宽度/高度/间距全部改由 `--layout-*` 与 `--space-*` 驱动。

---

## 6. 阶段四：公开门面页

### 6.1 路由

`/` 从「鉴权内重定向到 `/task`」改为**公开门面页**（`LandingPage`）。`/login` 仍公开；
控制台 14 条路由保持鉴权不变；`*` 回落到 `/`。`Login.tsx` 原本就跳 `/task`，因此登录后行为不变。

> **部署检查项**：`api/main.py` 只挂载 `/artifacts`，前端由外部服务器托管
> （已确认 FastAPI 不提供 `index.html`）。因此新路由需要 SPA fallback
> （nginx `try_files ... /index.html`）覆盖 `/`，否则直访会 404。这一条需在 nginx 配置中确认。

### 6.2 内容（不依赖图库预算）

Hero（超大字级 `clamp(2.75rem, 8.4vw, 7rem)` + 列网格底纹 + 单一 CTA）、
八阶段管线（scroll 驱动进度条）、六格能力网格、四格指标带（数字滚动）、收尾 CTA、极简页脚。
所有内容均为**静态**：不新增公开数据接口，避免扩大鉴权面。

### 6.3 移动端范围（明确取舍）

用户选择"移动端不做重点"，但 Awwwards 评委常在手机初筛且 Usability 是评分项。
折中：**门面页与登录页做完整响应式（720 / 1080 断点）；控制台桌面优先**。
这一取舍已记录，控制台小屏体验仍是已知短板。

---

## 7. 阶段六：动效原语（`src/motion/`）

**不引入任何新运行时依赖**，全部自建：

| 原语 | 机制 |
|---|---|
| `useReducedMotion` / `prefersReducedMotion` | `matchMedia` 监听；`matchMedia` 不存在时安全降级为"允许动效" |
| `useReveal` | `IntersectionObserver`；reduce 或缺少 API 时**立即置为已显示** |
| `useScrollProgress` | rAF + `getBoundingClientRect`，写入 `--scroll-progress`（唯一的合法内联写法） |
| `useCountUp` | rAF + easeOutCubic，滚动进入 40% 时启动；不可动画时直接显示终值 |

`motion.module.css` 新增 4 个 keyframes（`rise` / `sweep` / `pulseDot` / `drawLine`），
此前全站为 **0**。全部动效只作用于 `transform` / `opacity`，并在 `prefers-reduced-motion` 下关闭。

> 明确不做：滚动钉住（pinning）与横向滚动叙事。若后续确实需要，升级路径是 GSAP ScrollTrigger，
> 届时作为独立决策，不在本次引入。

---

## 8. 测试与守卫

| 测试 | 内容 |
|---|---|
| `styles/__tests__/tokenParity.test.ts`（62） | TS 与 CSS 令牌逐值一致；原始令牌只定义一次；深色只覆盖语义层 |
| `styles/__tests__/noInlineStyle.test.ts`（3） | 扫描 `src/**/*.tsx`，禁止新增内联样式对象；待迁移清单不得有陈旧项；数量棘轮 < 20 |
| `styles/__tests__/noLegacyTokens.test.ts`（3） | 禁止新增旧令牌引用；清单不得陈旧；断言已迁移文件（Shell / 门面页 / 原语 / motion / theme）确实干净 |
| `motion/__tests__/reducedMotion.test.tsx`（6） | reduce 时立即显示内容；缺少 `matchMedia` / `IntersectionObserver` 时同样不隐藏内容 |
| `pages/__tests__/Landing.test.tsx`（4） | 门面页无需鉴权即可渲染；CTA 指向 `/login`；管线阶段与能力/指标块存在 |

**两个守卫都使用「只减不增」的待迁移清单**：新文件违规会失败，清单里已修好的文件也会因"陈旧项"失败。
这样迁移过程始终绿灯，同时进度不可遗忘。

**回归断言的处理原则**：改造使 5 处断言失败（旧调色板、被隐藏的 eyebrow、`280px` 硬编码宽度等），
全部是**断言固化了旧实现**。处理方式是更新断言（改为引用令牌、断言 `::before` 强调条规则、
用 WCAG 相对亮度证明"浅色主题确实是浅色"），而不是删掉或放宽断言。

**验证结果**：前端测试 **144 passed / 1 skipped**（改造前 66 passed / 1 skipped，净增 78 项）；
`tsc --noEmit`、`npm run lint`（0 warning）、`npm run build` 全部通过。
产物：CSS 61.35 kB（gzip 12.63 kB），JS 1.61 MB（gzip 513.76 kB）。

---

## 9. 已知遗留与后续

1. **控制台 15 个页面已迁移 8 页**（阶段五进行中）：Stats、History、TaskCreate、TaskDetail、TaskManage、
   TopicCenter、StyleConfig。当前状态：
   - 内联样式待迁移 **17 → 9 个文件**（剩 ScheduleManage 14 处，其余为配置类小页面 1–3 处）；
   - 旧令牌待迁移 **19 → 12 个文件**（7 个 `components/**` CSS module + Login / ArticleManage + `global.css`；
     其中 `global.css` 的 `.backstage-*` 层为刻意保留，需待全部页面迁移完成后再删）。
   - 两个守卫测试中的待迁移清单即为精确工单；清空后即可删除 `variables.css` 与 `.backstage-*` 层。
   - 已迁移并可作为模板：Shell、门面页、原语层、motion 层，以及上述 7 个页面。
2. **缺字体文件**（第 3.4 节）：拿到有授权的拉丁紧体后放入 `public/fonts/` 即可生效。
3. **顺带修复了一个既有偶发失败**：`TopicCenter.test.tsx` 在 `await findByText(标题)` 之后用
   **同步** `getByText('账号匹配')`，而该文案只在卡片展开态渲染、展开由**第二个 effect** 触发，
   于是断言正好卡在两次提交之间，并发负载下偶发失败。改为 `await findByText(...)` 后
   **连续 3 次全量运行均 144 passed**。这是测试自身的竞态，不是产品缺陷。
4. **迁移中发现的三个真实缺陷（均已修复）**：
   - `StyleConfig` 的三栏主题工作台全部使用**硬编码灰**（`#f0f0f0` / `#f8fafc` / `#fff` / `#fafafa`），
     深色模式下会渲染出浅灰线条与亮底面 —— 迁移到语义令牌后恢复正常。这也是"内联样式为什么必须清掉"
     最好的例证：硬编码色绕过了主题系统。
   - `TaskManage` 用内联硬编码色（`#059669` / `#d97706` / `#e11d48`）表达状态，
     已改为 `StatGrid` + `Stat` 的 `tone`，由状态令牌统一着色。
   - `TaskDetail.module.css` 引用了**从未定义过的** `--app-text-primary`，
     该 `color` 声明被浏览器整条丢弃（长期靠继承"碰巧"正常）；迁移后改为 `--text-primary` 才真正生效。
5. **门面页与 antd 同包**：`App.tsx` 静态引入控制台，因此访问 `/` 也会下载整个 antd 包。
   若要冲性能分，应把控制台路由改为 `React.lazy` 代码分割。
6. **无视觉回归测试**：需引入 Playwright/Chromatic 等新依赖，本次明确不做，改为每批人工清单
   （明暗 × 1440/1024/390、键盘全路径、`prefers-reduced-motion`、对比度 ≥4.5:1）。

---

## 10. 评奖就绪度：可争取与客观限制

**可争取**：Design 靠令牌严格度 + 网格 + 排版纪律 + 零装饰阴影（本次投入最重、收益最确定）；
Creativity 靠**真实 23 节点管线的滚动可视化**与巨型汉字几何母题（原创、且不需图库预算）；
Content 靠把"中文公众号内容生产自动化"这件事本身讲清楚；Usability 靠控制台统一表格/表单皮肤与 ⌘K。

**客观限制**（需知悉）：

1. Awwwards 提交要求**可公开访问的 URL**。本次已把门面页公开化即为此准备；若站点整体不对外，
   只能走内部评审/作品集路径。
2. 评委常在移动端初筛，**"移动端不做重点"会实质压低 Usability 分**。影响面已缩到最小
   （门面页与登录页完整响应式），但控制台小屏仍是短板。
3. 拿奖级作品通常还含定制图形/摄影/插画与品牌声音。本次以排版 + 真实数据可视化 + 动效替代图库素材，
   是无预算条件下的最佳路径，但视觉完成度与有专职设计师的参赛作品仍有差距。

---

## 11. 相关文件

- 令牌：`frontend/src/styles/tokens.css`、`tokens.ts`、`variables.css`（临时）
- 主题：`frontend/src/theme.ts`
- 原语：`frontend/src/components/layout/`、`frontend/src/components/brand/BrandMark.tsx`
- 动效：`frontend/src/motion/`
- 门面页：`frontend/src/pages/Landing.tsx`、`Landing.module.css`
- 路由与品牌资源：`frontend/src/App.tsx`、`frontend/index.html`、`frontend/public/`
- 规范：`CLAUDE.md`（UI 风格规范）、`demand.md`
