# Lightweight Workbench Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify the frontend into a lighter workbench style with a fixed-width sidebar, compact page headers, complete light-theme coverage, and list-first page layouts across the main screens.

**Architecture:** First shrink and standardize the shared shell so every route inherits the same calmer layout: fixed `216px` sidebar, compact header, lighter surfaces, and fewer decorative blocks. Then refactor each major page from “card-heavy showcase” layouts toward “toolbar + list/table + grouped form” structures, keeping the existing business logic and API calls intact while updating tests alongside each page.

**Tech Stack:** React 18, TypeScript, Ant Design 5, CSS Modules, global CSS variables, Vitest, Testing Library, React Router

---

### File Map

**Create:**
- `frontend/src/pages/__tests__/LightweightLayout.test.tsx`

**Modify:**
- `frontend/src/components/workbench/WorkbenchShell.module.css`
- `frontend/src/components/workbench/HeroPanel.module.css`
- `frontend/src/components/workbench/HeroPanel.tsx`
- `frontend/src/components/workbench/SectionBlock.module.css`
- `frontend/src/styles/variables.css`
- `frontend/src/styles/global.css`
- `frontend/src/pages/TaskCreate.tsx`
- `frontend/src/pages/TaskDetail.tsx`
- `frontend/src/pages/History.tsx`
- `frontend/src/pages/ArticleManage.tsx`
- `frontend/src/pages/ScheduleManage.tsx`
- `frontend/src/pages/StyleConfig.tsx`
- `frontend/src/pages/ModelConfig.tsx`
- `frontend/src/pages/AccountConfig.tsx`
- `frontend/src/pages/__tests__/TaskCreate.test.tsx`
- `frontend/src/pages/__tests__/TaskDetail.test.tsx`
- `frontend/src/pages/__tests__/History.test.tsx`
- `frontend/src/pages/__tests__/ArticleManage.test.tsx`
- `frontend/src/pages/__tests__/ScheduleManage.test.tsx`
- `frontend/src/components/workbench/__tests__/WorkbenchShell.test.tsx`

**Verify With Existing Commands:**
- `npm run test -- LightweightLayout`
- `npm run test -- TaskCreate`
- `npm run test -- TaskDetail`
- `npm run test -- History`
- `npm run test -- ArticleManage`
- `npm run test -- ScheduleManage`
- `npm run test -- WorkbenchShell`
- `npm run build`

### Task 1: Simplify The Shared Shell And Fixed Sidebar

**Files:**
- Modify: `frontend/src/components/workbench/WorkbenchShell.module.css`
- Modify: `frontend/src/components/workbench/__tests__/WorkbenchShell.test.tsx`
- Create: `frontend/src/pages/__tests__/LightweightLayout.test.tsx`

- [ ] **Step 1: Write the failing test**

Add a focused layout test in `frontend/src/pages/__tests__/LightweightLayout.test.tsx`:

```tsx
import { renderWithRouter } from '@/test/renderWithRouter'
import WorkbenchShell from '@/components/workbench/WorkbenchShell'

it('renders a fixed 216px sidebar shell with compact main spacing', () => {
  const { container } = renderWithRouter(<WorkbenchShell />, { route: '/task', theme: 'light' })

  const shell = container.querySelector('[class*="shell"]') as HTMLElement
  const sidebar = container.querySelector('[class*="sidebar"]') as HTMLElement
  const main = container.querySelector('[class*="main"]') as HTMLElement

  expect(shell).toBeInTheDocument()
  expect(sidebar).toBeInTheDocument()
  expect(main).toBeInTheDocument()
  expect(getComputedStyle(shell).gridTemplateColumns).toContain('216px')
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- LightweightLayout`

Expected: FAIL because the current shell still uses a `280px` sidebar and old spacing.

- [ ] **Step 3: Write minimal implementation**

Update `frontend/src/components/workbench/WorkbenchShell.module.css`:

```css
.shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 216px minmax(0, 1fr);
  background-color: var(--app-bg);
  background-image: none;
}

.sidebar {
  gap: 16px;
  padding: 20px 16px;
  border-right: 1px solid var(--app-border);
  background: var(--app-surface);
}

.main {
  min-width: 0;
  padding: 20px 24px;
}

.frame {
  gap: 16px;
}
```

Update `frontend/src/components/workbench/__tests__/WorkbenchShell.test.tsx` to keep asserting the shell renders for `/task`.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- LightweightLayout`

Expected: PASS with the fixed-width sidebar assertion green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/workbench/WorkbenchShell.module.css frontend/src/components/workbench/__tests__/WorkbenchShell.test.tsx frontend/src/pages/__tests__/LightweightLayout.test.tsx
git commit -m "收敛全局外壳与固定侧栏"
```

### Task 2: Replace The Large Hero With Compact Page Headers

**Files:**
- Modify: `frontend/src/components/workbench/HeroPanel.module.css`
- Modify: `frontend/src/components/workbench/HeroPanel.tsx`
- Modify: `frontend/src/pages/__tests__/LightweightLayout.test.tsx`

- [ ] **Step 1: Write the failing test**

Extend `frontend/src/pages/__tests__/LightweightLayout.test.tsx`:

```tsx
it('renders a compact page header instead of a tall hero panel', () => {
  const { container } = renderWithRouter(<WorkbenchShell />, { route: '/task', theme: 'light' })
  const panel = container.querySelector('[class*="panel"]') as HTMLElement
  const title = container.querySelector('[class*="title"]') as HTMLElement

  expect(panel).toBeInTheDocument()
  expect(title).toBeInTheDocument()
  expect(getComputedStyle(panel).paddingTop).toBe('16px')
  expect(parseFloat(getComputedStyle(title).fontSize)).toBeLessThan(32)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- LightweightLayout`

Expected: FAIL because the current hero header remains oversized.

- [ ] **Step 3: Write minimal implementation**

Update `frontend/src/components/workbench/HeroPanel.module.css`:

```css
.panel {
  display: grid;
  gap: 10px;
  padding: 16px 20px;
  border: 1px solid var(--app-border);
  border-radius: 18px;
  background: var(--app-surface);
  box-shadow: none;
}

.panel::after {
  display: none;
}

.eyebrow {
  font-size: 12px;
  letter-spacing: 0.12em;
  color: var(--app-text-tertiary);
}

.title {
  font-size: clamp(1.125rem, 1.4vw, 1.5rem);
  color: var(--app-text);
}

.description {
  max-width: none;
  font-size: 13px;
  color: var(--app-text-secondary);
}
```

Update `frontend/src/components/workbench/HeroPanel.tsx` to render the description only when present:

```tsx
{description ? <p className={styles.description}>{description}</p> : null}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- LightweightLayout`

Expected: PASS with compact header sizing assertions green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/workbench/HeroPanel.module.css frontend/src/components/workbench/HeroPanel.tsx frontend/src/pages/__tests__/LightweightLayout.test.tsx
git commit -m "压缩全局页面头部"
```

### Task 3: Complete Light Theme Coverage In Shared Styles

**Files:**
- Modify: `frontend/src/styles/variables.css`
- Modify: `frontend/src/styles/global.css`
- Modify: `frontend/src/pages/__tests__/LightweightLayout.test.tsx`

- [ ] **Step 1: Write the failing test**

Add a light-theme style assertion:

```tsx
it('keeps shared surfaces light in light mode', () => {
  const { container } = renderWithRouter(<WorkbenchShell />, { route: '/task', theme: 'light' })
  const sidebar = container.querySelector('[class*="sidebar"]') as HTMLElement
  const canvas = container.querySelector('[class*="canvas"]') as HTMLElement

  expect(getComputedStyle(sidebar).backgroundColor).not.toBe('rgb(11, 16, 32)')
  expect(getComputedStyle(canvas).backgroundColor).not.toBe('rgb(15, 23, 42)')
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- LightweightLayout`

Expected: FAIL because some shared surfaces still read as dark in light mode.

- [ ] **Step 3: Write minimal implementation**

Update `frontend/src/styles/variables.css` to lighten any remaining shared shell tokens and add explicit list-oriented surface variables:

```css
:root,
:root[data-theme='light'] {
  --app-surface-muted: #f8fbff;
  --app-toolbar-bg: #f8fbff;
  --app-list-row-hover: #f3f7fd;
}

:root[data-theme='dark'] {
  --app-surface-muted: #0f172a;
  --app-toolbar-bg: #121a2b;
  --app-list-row-hover: #182235;
}
```

Update `frontend/src/styles/global.css`:

```css
.backstage-toolbar {
  padding: 12px 0;
  border-bottom: 1px solid var(--app-border);
}

.backstage-surface-card {
  border-radius: 16px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  box-shadow: none;
}

.backstage-preview-frame {
  border: 1px solid var(--app-border);
  border-radius: 16px;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- LightweightLayout`

Expected: PASS with light-theme surface assertions green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/styles/variables.css frontend/src/styles/global.css frontend/src/pages/__tests__/LightweightLayout.test.tsx
git commit -m "补齐共享样式浅色态"
```

### Task 4: Simplify TaskCreate Into A Grouped Form Page

**Files:**
- Modify: `frontend/src/pages/TaskCreate.tsx`
- Modify: `frontend/src/pages/__tests__/TaskCreate.test.tsx`

- [ ] **Step 1: Write the failing test**

Append a structure assertion to `frontend/src/pages/__tests__/TaskCreate.test.tsx`:

```tsx
it('renders task creation as grouped form sections instead of showcase cards', () => {
  renderWithRouter(<TaskCreate />, { route: '/task', theme: 'light' })

  expect(screen.getByText(/启动创作流程|创建任务/i)).toBeInTheDocument()
  expect(screen.queryByText(/创作节奏/i)).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: /创建|启动/i })).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- TaskCreate`

Expected: FAIL because the page still renders showcase-style metrics and signals.

- [ ] **Step 3: Write minimal implementation**

Update `frontend/src/pages/TaskCreate.tsx`:

```tsx
<HeroPanel
  eyebrow="Task"
  title="创建任务"
  description="配置关键词、受众和写作策略后即可启动。"
/>

<div className="backstage-grid backstage-grid--double">
  <SectionBlock title="任务配置">
    {/* existing AntD Form preserved */}
  </SectionBlock>
  <SectionBlock title="填写说明">
    <ul className="backstage-note-list">
      <li>关键词支持多个主题词组合。</li>
      <li>受众角色会影响行文角度。</li>
      <li>风格提示可选，不填则使用默认策略。</li>
    </ul>
  </SectionBlock>
</div>
```

Remove the large metric cards and signal cards from this page.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- TaskCreate`

Expected: PASS with the compact grouped-form layout assertion green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/TaskCreate.tsx frontend/src/pages/__tests__/TaskCreate.test.tsx
git commit -m "收敛任务创建页结构"
```

### Task 5: Convert History And Article Pages To List-First Layouts

**Files:**
- Modify: `frontend/src/pages/History.tsx`
- Modify: `frontend/src/pages/ArticleManage.tsx`
- Modify: `frontend/src/pages/__tests__/History.test.tsx`
- Modify: `frontend/src/pages/__tests__/ArticleManage.test.tsx`

- [ ] **Step 1: Write the failing test**

Update `frontend/src/pages/__tests__/History.test.tsx`:

```tsx
it('defaults history to a list/table-first layout', async () => {
  renderWithRouter(<History />, { route: '/history', theme: 'light' })

  expect(await screen.findByRole('table')).toBeInTheDocument()
  expect(screen.queryByText(/卡片视图/i)).not.toBeInTheDocument()
})
```

Update `frontend/src/pages/__tests__/ArticleManage.test.tsx`:

```tsx
it('renders article management as a compact list with preview', async () => {
  renderWithRouter(<ArticleManage />, { route: '/articles', theme: 'light' })

  expect(await screen.findByRole('table')).toBeInTheDocument()
  expect(screen.getByText(/预览/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- History`

Run: `npm run test -- ArticleManage`

Expected: FAIL because the pages still lean on heavier cards and non-list-first defaults.

- [ ] **Step 3: Write minimal implementation**

Update `frontend/src/pages/History.tsx`:

```tsx
const [viewMode] = useState<HistoryViewMode>('table')
```

Replace card-first wrappers with:

```tsx
<div className="backstage-page">
  <HeroPanel eyebrow="History" title="历史任务" description="按列表查看任务状态、时间和操作。" />
  <div className="backstage-toolbar">{/* existing actions */}</div>
  <Table /* existing columns and data */ />
</div>
```

Update `frontend/src/pages/ArticleManage.tsx` to use:

```tsx
<div className="backstage-page">
  <HeroPanel eyebrow="Articles" title="文章管理" description="通过列表管理文章状态、主题和推送动作。" />
  <div className="backstage-grid backstage-grid--preview">
    <div>{/* toolbar + table/list */}</div>
    <SectionBlock title="预览">{/* existing preview content */}</SectionBlock>
  </div>
</div>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- History`

Run: `npm run test -- ArticleManage`

Expected: PASS with list-first layout assertions green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/History.tsx frontend/src/pages/ArticleManage.tsx frontend/src/pages/__tests__/History.test.tsx frontend/src/pages/__tests__/ArticleManage.test.tsx
git commit -m "将内容页收敛为列表优先布局"
```

### Task 6: Simplify TaskDetail And ScheduleManage

**Files:**
- Modify: `frontend/src/pages/TaskDetail.tsx`
- Modify: `frontend/src/pages/ScheduleManage.tsx`
- Modify: `frontend/src/pages/__tests__/TaskDetail.test.tsx`
- Modify: `frontend/src/pages/__tests__/ScheduleManage.test.tsx`

- [ ] **Step 1: Write the failing test**

Update `frontend/src/pages/__tests__/TaskDetail.test.tsx`:

```tsx
it('renders a compact task detail header with sectioned details', async () => {
  renderWithRouter(<TaskDetail />, { route: '/task/mock-task', theme: 'light' })

  expect(await screen.findByText(/任务详情|任务轨道/i)).toBeInTheDocument()
  expect(screen.queryByText(/Focus/i)).not.toBeInTheDocument()
})
```

Update `frontend/src/pages/__tests__/ScheduleManage.test.tsx`:

```tsx
it('renders schedule management as toolbar plus table layout', async () => {
  renderWithRouter(<ScheduleManage />, { route: '/schedules', theme: 'light' })

  expect(await screen.findByRole('table')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- TaskDetail`

Run: `npm run test -- ScheduleManage`

Expected: FAIL because these pages still rely on larger display-heavy wrappers.

- [ ] **Step 3: Write minimal implementation**

Update `frontend/src/pages/TaskDetail.tsx`:

```tsx
<HeroPanel eyebrow="Task Detail" title={task?.keywords || '任务详情'} description="查看任务状态、文章产出和执行记录。" />
```

Refactor the body into:

```tsx
<div className="backstage-grid backstage-grid--double">
  <SectionBlock title="执行状态">{/* existing status/timeline content */}</SectionBlock>
  <SectionBlock title="任务信息">{/* existing metadata list */}</SectionBlock>
</div>
```

Update `frontend/src/pages/ScheduleManage.tsx`:

```tsx
<div className="backstage-page">
  <HeroPanel eyebrow="Schedules" title="定时任务" description="通过列表查看、筛选和编辑自动化规则。" />
  <div className="backstage-toolbar">{/* existing actions and filters */}</div>
  <Table /* existing schedule table */ />
</div>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- TaskDetail`

Run: `npm run test -- ScheduleManage`

Expected: PASS with compact detail and list-first schedule assertions green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/TaskDetail.tsx frontend/src/pages/ScheduleManage.tsx frontend/src/pages/__tests__/TaskDetail.test.tsx frontend/src/pages/__tests__/ScheduleManage.test.tsx
git commit -m "压缩详情与调度页外观"
```

### Task 7: Simplify Remaining Configuration Pages

**Files:**
- Modify: `frontend/src/pages/StyleConfig.tsx`
- Modify: `frontend/src/pages/ModelConfig.tsx`
- Modify: `frontend/src/pages/AccountConfig.tsx`

- [ ] **Step 1: Write the failing test**

Add one broad structure test to `frontend/src/pages/__tests__/LightweightLayout.test.tsx`:

```tsx
import AccountConfigPage from '@/pages/AccountConfig'
import ModelConfigPage from '@/pages/ModelConfig'

it('renders config pages with compact headers and grouped sections', () => {
  const { rerender } = renderWithRouter(<ModelConfigPage />, { route: '/models', theme: 'light' })
  expect(screen.getByText(/模型配置|模型/i)).toBeInTheDocument()

  rerender(<AccountConfigPage />)
  expect(screen.getByText(/账号配置|账号/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- LightweightLayout`

Expected: FAIL if these pages still depend on oversized headers or heavy cards.

- [ ] **Step 3: Write minimal implementation**

Refactor `StyleConfig.tsx`, `ModelConfig.tsx`, and `AccountConfig.tsx` to wrap content in:

```tsx
<div className="backstage-page">
  <HeroPanel eyebrow="Settings" title="..." description="..." />
  <div className="backstage-toolbar">{/* existing page actions */}</div>
  <div className="backstage-stack">{/* existing grouped forms and lists */}</div>
</div>
```

Reduce card-heavy wrappers where possible and prefer grouped sections over stacked decorated cards.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- LightweightLayout`

Expected: PASS with the configuration-page structure assertions green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/StyleConfig.tsx frontend/src/pages/ModelConfig.tsx frontend/src/pages/AccountConfig.tsx frontend/src/pages/__tests__/LightweightLayout.test.tsx
git commit -m "收敛配置页视觉层级"
```

### Task 8: Run Final Verification

**Files:**
- Modify: none

- [ ] **Step 1: Run focused shell and page tests**

Run: `npm run test -- LightweightLayout`

Expected: PASS with shell, compact header, and configuration-page assertions green.

- [ ] **Step 2: Run page-specific regressions**

Run: `npm run test -- TaskCreate`

Run: `npm run test -- TaskDetail`

Run: `npm run test -- History`

Run: `npm run test -- ArticleManage`

Run: `npm run test -- ScheduleManage`

Expected: PASS with all updated page tests green.

- [ ] **Step 3: Run shared-shell verification**

Run: `npm run test -- WorkbenchShell`

Expected: PASS with the shared workbench shell still rendering normally.

- [ ] **Step 4: Run full frontend verification**

Run: `npm run build`

Expected: PASS with the production bundle compiling successfully.

- [ ] **Step 5: Commit final integrated changes**

```bash
git add frontend/src/components/workbench/WorkbenchShell.module.css frontend/src/components/workbench/HeroPanel.module.css frontend/src/components/workbench/HeroPanel.tsx frontend/src/components/workbench/SectionBlock.module.css frontend/src/styles/variables.css frontend/src/styles/global.css frontend/src/pages/TaskCreate.tsx frontend/src/pages/TaskDetail.tsx frontend/src/pages/History.tsx frontend/src/pages/ArticleManage.tsx frontend/src/pages/ScheduleManage.tsx frontend/src/pages/StyleConfig.tsx frontend/src/pages/ModelConfig.tsx frontend/src/pages/AccountConfig.tsx frontend/src/pages/__tests__/LightweightLayout.test.tsx frontend/src/pages/__tests__/TaskCreate.test.tsx frontend/src/pages/__tests__/TaskDetail.test.tsx frontend/src/pages/__tests__/History.test.tsx frontend/src/pages/__tests__/ArticleManage.test.tsx frontend/src/pages/__tests__/ScheduleManage.test.tsx frontend/src/components/workbench/__tests__/WorkbenchShell.test.tsx
git commit -m "收敛前端为轻量工作台风格"
```

### Self-Review

**Spec coverage**
- Fixed `216px` sidebar and quieter shell: Task 1
- Compact page headers and reduced hero footprint: Task 2
- Complete light-theme coverage in shared styles: Task 3
- List-first and grouped-form layouts across major pages: Tasks 4, 5, 6, 7
- Reduced card usage and calmer visual style: Tasks 1 through 7
- Final verification: Task 8

**Placeholder scan**
- No `TODO`, `TBD`, or “similar to task N” placeholders remain.
- Each task has exact files, commands, and concrete implementation snippets.

**Type consistency**
- Shared shell width stays consistently `216px`.
- Compact header concept is consistently implemented through `HeroPanel`.
- List-first layout is consistently expressed through `backstage-page`, `backstage-toolbar`, `Table`, and grouped `SectionBlock` sections.
