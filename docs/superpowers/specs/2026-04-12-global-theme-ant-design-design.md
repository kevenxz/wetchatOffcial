# 全站主题与 Ant Design 统一设计

## 1. 背景与目标

当前前端已经形成较强的深色工作台风格，但主题能力和基础组件体系还没有完全统一：

- `frontend/src/theme.ts` 目前只提供单套深色 Ant Design token
- `frontend/src/styles/variables.css` 只定义深色变量，缺少白天模式映射
- `frontend/src/styles/global.css` 已显式声明 `color-scheme: dark`，全局默认偏向夜间
- 业务页面同时依赖 Ant Design、全局 CSS 和 CSS Module，颜色来源分散

本次设计的目标不是一次性重写所有页面，而是建立一套可持续扩展的前端样式底座：

- 支持全站白天 / 黑夜切换
- 首次进入默认跟随系统主题
- 提供用户可见的手动切换入口，并允许覆盖系统偏好
- 用 Ant Design 统一全局主题和基础组件表现
- 保留现有业务外壳和工作台视觉结构
- 为后续分阶段收敛页面组件提供稳定基础

## 2. 决策结论

### 2.1 总体策略

采用“Ant Design 统一全局主题和基础组件，业务外壳保留定制，分阶段改造”的路线。

这意味着：

- `Button`、`Form`、`Input`、`Select`、`Table`、`Modal`、`Drawer`、`Tabs`、`Tag` 等基础组件以 Ant Design 为标准实现
- 品牌化工作台壳层、Hero 区、状态轨道、组合面板等业务级外壳允许继续保留定制
- 自定义样式不再直接写死深色值，而是统一消费主题变量

### 2.2 主题模式

全局主题模式定义为三态：

- `system`：默认值，跟随操作系统的 `prefers-color-scheme`
- `light`：强制白天模式
- `dark`：强制黑夜模式

### 2.3 单一事实来源

主题状态由 React 层统一管理，并同步到两个消费层：

1. Ant Design `ConfigProvider`
2. 根节点主题属性，例如 `document.documentElement.dataset.theme`

Ant Design token 与 CSS 变量都必须由同一个有效主题推导，避免组件和页面壳体各自维护一套颜色体系。

## 3. 架构设计

### 3.1 Theme State Layer

新增全局主题状态模块，建议放在 `frontend/src/store` 或 `frontend/src/theme` 目录中，职责如下：

- 管理用户偏好模式：`system | light | dark`
- 计算当前生效主题：`light | dark`
- 监听系统主题变化
- 将用户偏好持久化到本地存储
- 提供切换接口给全局主题入口使用

建议暴露的核心能力：

- `themeMode`
- `resolvedTheme`
- `setThemeMode(mode)`
- `initializeTheme()`

### 3.2 Ant Design Theme Layer

`frontend/src/theme.ts` 从“单一静态配置”改为“按主题生成配置”的工厂式接口，例如：

- `getAntdTheme('light')`
- `getAntdTheme('dark')`

设计原则：

- 两套主题共用同一套品牌色语义
- 白天模式强调清晰层级、对比度和可读性
- 黑夜模式延续当前工作台氛围，但不再通过散落的硬编码维持
- Layout、Menu、Card、Table、Modal 等高频组件应提供明确 token 对应

### 3.3 CSS Variable Layer

`frontend/src/styles/variables.css` 改为基于主题属性输出变量，例如：

- `:root[data-theme='light'] { ... }`
- `:root[data-theme='dark'] { ... }`

变量命名不直接绑定具体颜色，而绑定语义角色，建议集中覆盖：

- 背景：`--app-bg`、`--app-surface`、`--app-elevated`
- 文本：`--app-text`、`--app-text-secondary`
- 边框：`--app-border`、`--app-border-strong`
- 品牌：`--app-primary`、`--app-primary-soft`
- 阴影：`--app-shadow-sm`、`--app-shadow-md`

现有 `--bg-workbench`、`--text-primary` 等变量可保留兼容一段时间，但新代码应逐步迁移到统一语义变量。

### 3.4 Business Shell Layer

现有业务外壳保持结构不动，但颜色、背景、描边、阴影统一走变量，不再写死夜间值。

优先覆盖以下区域：

- 应用最外层背景
- 顶部区域与导航壳体
- 常见面板、工作台卡片、内容容器
- 详情页轨道、状态区、列表容器

这一步只解决“同一页面在两种主题下都成立”，不追求重新设计全部页面表现。

## 4. 交互设计

### 4.1 主题入口

全局主题切换入口放在顶层通用操作区域，优先选择所有页面都能访问到的位置，例如主框架顶部右侧。

入口不使用简单二元开关，而使用三态选择控件，明确展示：

- 跟随系统
- 浅色模式
- 深色模式

可选交互形态：

- `Dropdown + Segmented`
- `Dropdown Menu`
- `Popover + Radio Group`

推荐使用与现有 Ant Design 体系兼容的轻量下拉入口。

### 4.2 初始化规则

- 首次进入时，如果没有本地记录，默认使用 `system`
- 若用户曾手动选择 `light` 或 `dark`，则刷新后优先使用用户选择
- 若用户将模式改回 `system`，恢复跟随系统
- 在 React 首屏渲染前尽可能早地应用根节点主题，降低闪烁和“先白后黑 / 先黑后白”问题

### 4.3 系统同步

当主题模式为 `system` 时，需要监听 `matchMedia('(prefers-color-scheme: dark)')`：

- 系统切到深色，页面自动切到 `dark`
- 系统切到浅色，页面自动切到 `light`

当模式为 `light` 或 `dark` 时，不响应系统变更。

## 5. 第一阶段改造范围

第一阶段只做主题底座与全局统一入口，不做整站重写。

### 5.1 包含内容

- 建立全局主题状态与本地持久化
- 为 Ant Design 提供明暗两套主题配置
- 为 CSS 变量提供明暗两套语义值
- 接入全局主题切换入口
- 清理全局样式中阻碍白天模式的关键硬编码
- 让全站最外层背景、文本、边框、基础容器在两种主题下可读且统一

### 5.2 暂不包含

- 不一次性把所有页面重写成 Ant Design 组件页
- 不系统性改造所有 CSS Module
- 不在第一阶段进行大规模布局改版
- 不为每个页面单独做视觉精修

## 6. 分阶段迁移策略

### 阶段一：主题底座

完成本设计中定义的全局主题状态、Ant Design token、CSS 变量和主题切换入口。

### 阶段二：基础组件收敛

后续新增页面或正在修改的页面，统一优先使用 Ant Design 基础组件，减少重复封装与视觉漂移。

### 阶段三：高频页面治理

按页面使用频率和改动热度，逐步收敛以下页面：

- `ScheduleManage`
- `TaskDetail`
- `ArticleManage`
- `TaskCreate`

治理目标是统一组件、层级、颜色和状态表现，而不是把页面做成通用模板风格。

## 7. 风险与约束

### 7.1 已知风险

- 现有页面中存在写死的深色背景和浅色文字，切到白天模式后可能产生局部对比问题
- Ant Design token 与自定义 CSS 若并行维护颜色，后续可能再次分叉
- 首屏渲染前主题初始化过晚，会引起闪烁

### 7.2 控制策略

- 第一阶段优先梳理全局壳层和高频公共容器
- 所有颜色统一收口到 “Ant Design token + CSS 变量” 两层
- 启动阶段尽早应用主题属性，避免渲染后再反切

## 8. 验收标准

- 首次进入默认跟随系统主题
- 系统主题变化时，`system` 模式下页面能自动同步
- 用户手动切换为 `light` 或 `dark` 后，刷新页面仍能保持选择
- Ant Design 基础组件在两种主题下表现统一
- 全站背景、文本、边框和常见面板在两种主题下对比正常
- 业务外壳结构保持不变，不影响现有主要功能

## 9. 实施入口建议

第一阶段实施时，优先检查和修改以下文件：

- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/theme.ts`
- `frontend/src/styles/variables.css`
- `frontend/src/styles/global.css`
- 全局布局或导航相关组件

如现有布局缺少统一顶部操作区，可在第一阶段补一个最小可用的全局主题入口承载位置，但不扩展为新的整体布局重构任务。
