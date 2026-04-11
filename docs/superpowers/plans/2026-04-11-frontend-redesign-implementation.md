# Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the React frontend into a branded “Brand Studio” workbench with a new shell, shared design system, redesigned primary workflows, and unified backstage pages without changing backend behavior.

**Architecture:** Keep `React + Ant Design` as the interaction foundation, but move visual ownership into a custom workbench layer composed of shell, hero, card, rail, and asset components. Implement the redesign in vertical slices so each milestone leaves the app in a runnable state and adds tests around layout, navigation, and the highest-risk workflow pages.

**Tech Stack:** React 18, TypeScript, Vite, Ant Design 5, React Router 6, CSS modules/global CSS variables, Vitest, Testing Library

---

## File Map

### New files

- `frontend/src/components/workbench/WorkbenchShell.tsx`
- `frontend/src/components/workbench/WorkbenchShell.module.css`
- `frontend/src/components/workbench/HeroPanel.tsx`
- `frontend/src/components/workbench/HeroPanel.module.css`
- `frontend/src/components/workbench/SectionBlock.tsx`
- `frontend/src/components/workbench/SectionBlock.module.css`
- `frontend/src/components/workbench/MetricCard.tsx`
- `frontend/src/components/workbench/MetricCard.module.css`
- `frontend/src/components/workbench/SignalCard.tsx`
- `frontend/src/components/workbench/SignalCard.module.css`
- `frontend/src/components/workbench/StatusRail.tsx`
- `frontend/src/components/workbench/StatusRail.module.css`
- `frontend/src/components/workbench/AssetList.tsx`
- `frontend/src/components/workbench/AssetList.module.css`
- `frontend/src/components/workbench/AutomationRuleCard.tsx`
- `frontend/src/components/workbench/AutomationRuleCard.module.css`
- `frontend/src/components/workbench/index.ts`
- `frontend/src/config/navigation.tsx`
- `frontend/src/styles/workbench.css`
- `frontend/src/test/setup.ts`
- `frontend/src/test/renderWithRouter.tsx`
- `frontend/src/components/workbench/__tests__/WorkbenchShell.test.tsx`
- `frontend/src/pages/__tests__/TaskCreate.test.tsx`
- `frontend/src/pages/__tests__/TaskDetail.test.tsx`
- `frontend/src/pages/__tests__/History.test.tsx`
- `frontend/src/pages/__tests__/ArticleManage.test.tsx`
- `frontend/src/pages/__tests__/ScheduleManage.test.tsx`

### Modified files

- `frontend/package.json`
- `frontend/vite.config.ts`
- `frontend/src/App.tsx`
- `frontend/src/main.tsx`
- `frontend/src/theme.ts`
- `frontend/src/styles/variables.css`
- `frontend/src/styles/global.css`
- `frontend/src/pages/TaskCreate.tsx`
- `frontend/src/pages/TaskDetail.tsx`
- `frontend/src/pages/TaskDetail.module.css`
- `frontend/src/pages/History.tsx`
- `frontend/src/pages/ArticleManage.tsx`
- `frontend/src/pages/ScheduleManage.tsx`
- `frontend/src/pages/StyleConfig.tsx`
- `frontend/src/pages/ModelConfig.tsx`
- `frontend/src/pages/AccountConfig.tsx`

## Task 1: Establish the redesign foundation

**Files:**
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/test/renderWithRouter.tsx`
- Modify: `frontend/package.json`
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/src/theme.ts`
- Modify: `frontend/src/styles/variables.css`
- Modify: `frontend/src/styles/global.css`

- [ ] **Step 1: Add the failing test and missing test tooling references**

```tsx
// frontend/src/test/renderWithRouter.tsx
import { MemoryRouter } from 'react-router-dom'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'

export function renderWithRouter(ui: ReactElement, route = '/task') {
  return render(<MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>)
}
```

```json
// frontend/package.json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.2.0",
    "@testing-library/user-event": "^14.6.1",
    "jsdom": "^26.0.0",
    "vitest": "^2.1.8"
  }
}
```

- [ ] **Step 2: Run the new test command to verify it fails before the config exists**

Run: `cd frontend && npm test`
Expected: FAIL with a Vitest configuration/setup import error such as `Cannot find module './src/test/setup.ts'` or `Unknown test environment`.

- [ ] **Step 3: Add the minimal Vitest and design-token foundation**

```ts
// frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
    css: true,
  },
})
```

```ts
// frontend/src/test/setup.ts
import '@testing-library/jest-dom'
```

```ts
// frontend/src/theme.ts
import type { ThemeConfig } from 'antd'

const theme: ThemeConfig = {
  token: {
    colorPrimary: '#9fe870',
    colorSuccess: '#79d483',
    colorWarning: '#f4b860',
    colorError: '#f17a7a',
    colorBgLayout: '#07110d',
    colorBgContainer: 'rgba(12, 24, 19, 0.82)',
    colorText: 'rgba(240, 247, 242, 0.92)',
    colorTextSecondary: 'rgba(194, 208, 198, 0.72)',
    fontFamily: "'Noto Serif SC', 'Source Han Serif SC', serif",
    borderRadius: 18,
  },
}

export default theme
```

```css
/* frontend/src/styles/variables.css */
:root {
  --wb-bg: #07110d;
  --wb-surface: rgba(12, 24, 19, 0.8);
  --wb-surface-strong: rgba(18, 33, 26, 0.92);
  --wb-border: rgba(159, 232, 112, 0.14);
  --wb-text: rgba(240, 247, 242, 0.92);
  --wb-text-muted: rgba(194, 208, 198, 0.72);
  --wb-accent: #9fe870;
  --wb-accent-alt: #d7a86e;
  --wb-danger: #f17a7a;
  --wb-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
}
```

- [ ] **Step 4: Run tests to verify the tooling and foundation compile**

Run: `cd frontend && npm test`
Expected: PASS with `0 failed` and the environment booting successfully.

- [ ] **Step 5: Commit the foundation setup**

```bash
git add frontend/package.json frontend/vite.config.ts frontend/src/test/setup.ts frontend/src/test/renderWithRouter.tsx frontend/src/theme.ts frontend/src/styles/variables.css frontend/src/styles/global.css
git commit -m "搭建前端重构基础设施"
```

## Task 2: Build the shared workbench shell and route metadata

**Files:**
- Create: `frontend/src/components/workbench/WorkbenchShell.tsx`
- Create: `frontend/src/components/workbench/WorkbenchShell.module.css`
- Create: `frontend/src/components/workbench/HeroPanel.tsx`
- Create: `frontend/src/components/workbench/HeroPanel.module.css`
- Create: `frontend/src/components/workbench/SectionBlock.tsx`
- Create: `frontend/src/components/workbench/SectionBlock.module.css`
- Create: `frontend/src/components/workbench/MetricCard.tsx`
- Create: `frontend/src/components/workbench/MetricCard.module.css`
- Create: `frontend/src/components/workbench/SignalCard.tsx`
- Create: `frontend/src/components/workbench/SignalCard.module.css`
- Create: `frontend/src/components/workbench/index.ts`
- Create: `frontend/src/config/navigation.tsx`
- Create: `frontend/src/components/workbench/__tests__/WorkbenchShell.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/styles/global.css`

- [ ] **Step 1: Write the failing shell test**

```tsx
// frontend/src/components/workbench/__tests__/WorkbenchShell.test.tsx
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/renderWithRouter'
import App from '@/App'

test('renders brand navigation and page context for the task route', async () => {
  renderWithRouter(<App />, '/task')

  expect(await screen.findByText('Brand Studio')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '创作台' })).toBeInTheDocument()
  expect(screen.getByText('任务创建')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the shell test to verify it fails against the old layout**

Run: `cd frontend && npm test -- WorkbenchShell`
Expected: FAIL because the old app still renders the default sider and does not include `Brand Studio` or the new route labels.

- [ ] **Step 3: Implement the shell, route metadata, and App integration**

```tsx
// frontend/src/config/navigation.tsx
import {
  CalendarOutlined,
  FileTextOutlined,
  HistoryOutlined,
  PlusCircleOutlined,
  SettingOutlined,
  UserOutlined,
  ApiOutlined,
} from '@ant-design/icons'

export const navigationItems = [
  { key: '/task', label: '创作台', icon: <PlusCircleOutlined />, title: '任务创建', summary: '启动一次完整的内容生产流程' },
  { key: '/history', label: '内容资产', icon: <HistoryOutlined />, title: '历史任务', summary: '回看、筛选和复用已生成资产' },
  { key: '/articles', label: '文章库', icon: <FileTextOutlined />, title: '文章管理', summary: '管理文章主题、预览与推送' },
  { key: '/schedules', label: '自动化', icon: <CalendarOutlined />, title: '定时任务', summary: '编排热点抓取和自动发布规则' },
  { key: '/settings', label: '系统舞台', icon: <SettingOutlined />, title: '风格配置', summary: '管理品牌内容样式' },
  { key: '/models', label: '模型配置', icon: <ApiOutlined />, title: '模型配置', summary: '维护模型与推理参数' },
  { key: '/accounts', label: '账号配置', icon: <UserOutlined />, title: '账号配置', summary: '维护推送目标与平台账号' },
]
```

```tsx
// frontend/src/components/workbench/WorkbenchShell.tsx
import { Layout, Menu } from 'antd'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { navigationItems } from '@/config/navigation'
import styles from './WorkbenchShell.module.css'

export function WorkbenchShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const current = navigationItems.find((item) => location.pathname.startsWith(item.key)) ?? navigationItems[0]

  return (
    <Layout className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>Brand Studio</div>
        <Menu
          mode="inline"
          selectedKeys={[current.key]}
          items={navigationItems.map(({ key, label, icon }) => ({ key, label, icon }))}
          onClick={({ key }) => navigate(key)}
        />
      </aside>
      <Layout className={styles.stage}>
        <header className={styles.contextBar}>
          <div>
            <p className={styles.kicker}>微信内容工作台</p>
            <h1>{current.title}</h1>
            <p>{current.summary}</p>
          </div>
        </header>
        <main className={styles.canvas}>
          <Outlet />
        </main>
      </Layout>
    </Layout>
  )
}
```

```tsx
// frontend/src/App.tsx
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { WorkbenchShell } from '@/components/workbench'
// keep existing page imports

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<WorkbenchShell />}>
          <Route path="/" element={<Navigate to="/task" replace />} />
          <Route path="/task" element={<TaskCreate />} />
          <Route path="/task/:id" element={<TaskDetail />} />
          <Route path="/history" element={<History />} />
          <Route path="/articles" element={<ArticleManage />} />
          <Route path="/schedules" element={<ScheduleManage />} />
          <Route path="/settings" element={<StyleConfigPage />} />
          <Route path="/models" element={<ModelConfigPage />} />
          <Route path="/accounts" element={<AccountConfigPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
```

- [ ] **Step 4: Run the shell test, lint, and build**

Run: `cd frontend && npm test -- WorkbenchShell && npm run lint && npm run build`
Expected: PASS with the new shell test green, ESLint clean, and Vite building the shared shell.

- [ ] **Step 5: Commit the shell milestone**

```bash
git add frontend/src/components/workbench frontend/src/config/navigation.tsx frontend/src/App.tsx frontend/src/main.tsx frontend/src/styles/global.css
git commit -m "重构前端工作台骨架"
```

## Task 3: Redesign the task creation page as the studio landing page

**Files:**
- Modify: `frontend/src/pages/TaskCreate.tsx`
- Modify: `frontend/src/components/workbench/HeroPanel.tsx`
- Modify: `frontend/src/components/workbench/SectionBlock.tsx`
- Create: `frontend/src/pages/__tests__/TaskCreate.test.tsx`

- [ ] **Step 1: Write the failing task creation page test**

```tsx
// frontend/src/pages/__tests__/TaskCreate.test.tsx
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/renderWithRouter'
import App from '@/App'

test('task creation page renders the studio hero and launch action', async () => {
  renderWithRouter(<App />, '/task')

  expect(await screen.findByText('启动一次完整创作流程')).toBeInTheDocument()
  expect(screen.getByText('热点灵感')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '启动创作流程' })).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the page test to verify it fails before the redesign**

Run: `cd frontend && npm test -- TaskCreate`
Expected: FAIL because the current page does not render the hero copy or the renamed primary action.

- [ ] **Step 3: Implement the landing-page layout with shared workbench sections**

```tsx
// frontend/src/pages/TaskCreate.tsx
return (
  <div className="page-grid page-grid--task">
    <HeroPanel
      eyebrow="Creative Pipeline"
      title="启动一次完整创作流程"
      description="输入主题、角色和风格偏好，工作台将串联热点捕获、结构规划、写作与推送。"
      actions={
        <Button type="primary" htmlType="submit" size="large" loading={isCreating}>
          启动创作流程
        </Button>
      }
    />

    <div className="page-grid__main">
      <SectionBlock title="创作指令" description="填写本次任务的关键词、角色与策略。">
        {/* existing Form fields kept, but grouped and retitled */}
      </SectionBlock>
    </div>

    <aside className="page-grid__side">
      <SignalCard title="热点灵感" subtitle="一键带入本次任务">
        {/* map HOT_TOPICS into branded quick-pick buttons */}
      </SignalCard>
      <MetricCard label="默认风格" value="系统自动推断" hint="可在系统舞台中长期调整" />
    </aside>
  </div>
)
```

- [ ] **Step 4: Run the targeted test and smoke the task route**

Run: `cd frontend && npm test -- TaskCreate && npm run lint`
Expected: PASS with the task page test green and no lint errors after the layout split.

- [ ] **Step 5: Commit the redesigned landing page**

```bash
git add frontend/src/pages/TaskCreate.tsx frontend/src/components/workbench/HeroPanel.tsx frontend/src/components/workbench/SectionBlock.tsx frontend/src/pages/__tests__/TaskCreate.test.tsx
git commit -m "重设计任务创建页"
```

## Task 4: Rebuild task detail into a status rail and result workspace

**Files:**
- Create: `frontend/src/components/workbench/StatusRail.tsx`
- Create: `frontend/src/components/workbench/StatusRail.module.css`
- Modify: `frontend/src/pages/TaskDetail.tsx`
- Modify: `frontend/src/pages/TaskDetail.module.css`
- Create: `frontend/src/pages/__tests__/TaskDetail.test.tsx`

- [ ] **Step 1: Write the failing task detail test**

```tsx
// frontend/src/pages/__tests__/TaskDetail.test.tsx
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/renderWithRouter'
import App from '@/App'

test('task detail route renders the process rail container', async () => {
  renderWithRouter(<App />, '/task/demo-id')

  expect(await screen.findByText('执行轨道')).toBeInTheDocument()
  expect(screen.getByText('结果预览')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the task detail test to verify it fails**

Run: `cd frontend && npm test -- TaskDetail`
Expected: FAIL because the old page uses plain cards and does not expose the new labels.

- [ ] **Step 3: Implement the split layout and reusable rail**

```tsx
// frontend/src/components/workbench/StatusRail.tsx
type RailItem = {
  key: string
  title: string
  description: string
  status: 'wait' | 'process' | 'finish' | 'error'
}

export function StatusRail({ items }: { items: RailItem[] }) {
  return (
    <ol className={styles.rail}>
      {items.map((item) => (
        <li key={item.key} data-status={item.status} className={styles.item}>
          <span className={styles.dot} />
          <div>
            <h3>{item.title}</h3>
            <p>{item.description}</p>
          </div>
        </li>
      ))}
    </ol>
  )
}
```

```tsx
// frontend/src/pages/TaskDetail.tsx
<div className={styles.detailPage}>
  <HeroPanel
    eyebrow="Task Rail"
    title={task?.keywords || '任务详情'}
    description={statusMessage}
    meta={<Tag>{STATUS_LABEL[wsStatus] ?? wsStatus}</Tag>}
  />

  <div className={styles.columns}>
    <SectionBlock title="执行轨道" description="跟踪当前工作流步骤与中间状态。">
      <StatusRail items={railItems} />
    </SectionBlock>
    <SectionBlock title="结果预览" description="查看文章草稿、风格画像和推送结果。">
      {/* success/failure/result content */}
    </SectionBlock>
  </div>
</div>
```

- [ ] **Step 4: Run the detail test plus full frontend checks**

Run: `cd frontend && npm test -- TaskDetail && npm run lint && npm run build`
Expected: PASS with the route compiling, the new rail rendered, and build output generated.

- [ ] **Step 5: Commit the detail page redesign**

```bash
git add frontend/src/components/workbench/StatusRail.tsx frontend/src/components/workbench/StatusRail.module.css frontend/src/pages/TaskDetail.tsx frontend/src/pages/TaskDetail.module.css frontend/src/pages/__tests__/TaskDetail.test.tsx
git commit -m "重构任务详情轨道页"
```

## Task 5: Merge history and article browsing into a unified asset experience

**Files:**
- Create: `frontend/src/components/workbench/AssetList.tsx`
- Create: `frontend/src/components/workbench/AssetList.module.css`
- Modify: `frontend/src/pages/History.tsx`
- Modify: `frontend/src/pages/ArticleManage.tsx`
- Create: `frontend/src/pages/__tests__/History.test.tsx`
- Create: `frontend/src/pages/__tests__/ArticleManage.test.tsx`

- [ ] **Step 1: Write the failing asset page tests**

```tsx
// frontend/src/pages/__tests__/History.test.tsx
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/renderWithRouter'
import App from '@/App'

test('history page exposes asset filters and view toggle', async () => {
  renderWithRouter(<App />, '/history')
  expect(await screen.findByText('内容资产')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '卡片视图' })).toBeInTheDocument()
})
```

```tsx
// frontend/src/pages/__tests__/ArticleManage.test.tsx
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/renderWithRouter'
import App from '@/App'

test('article manage page renders the asset hero and batch push panel', async () => {
  renderWithRouter(<App />, '/articles')
  expect(await screen.findByText('文章库')).toBeInTheDocument()
  expect(screen.getByText('批量推送')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the asset tests to verify they fail on the old pages**

Run: `cd frontend && npm test -- History ArticleManage`
Expected: FAIL because neither page exposes the new asset hero labels or view controls.

- [ ] **Step 3: Implement the shared asset container and migrate both pages**

```tsx
// frontend/src/components/workbench/AssetList.tsx
type AssetListProps<T> = {
  title: string
  description: string
  view: 'grid' | 'table'
  onViewChange: (view: 'grid' | 'table') => void
  toolbar?: React.ReactNode
  grid: React.ReactNode
  table: React.ReactNode
}

export function AssetList<T>({ title, description, view, onViewChange, toolbar, grid, table }: AssetListProps<T>) {
  return (
    <section className={styles.assetList}>
      <HeroPanel
        eyebrow="Content Assets"
        title={title}
        description={description}
        actions={
          <Space>
            <Button onClick={() => onViewChange('grid')}>卡片视图</Button>
            <Button onClick={() => onViewChange('table')}>列表视图</Button>
          </Space>
        }
      />
      {toolbar}
      {view === 'grid' ? grid : table}
    </section>
  )
}
```

```tsx
// frontend/src/pages/History.tsx
<AssetList
  title="内容资产"
  description="回看创作任务、筛选结果，并快速进入详情。"
  view={view}
  onViewChange={setView}
  grid={<div className={styles.assetGrid}>{tasks.map(renderTaskCard)}</div>}
  table={<Table columns={columns} dataSource={tasks} rowKey="task_id" />}
/>
```

```tsx
// frontend/src/pages/ArticleManage.tsx
<AssetList
  title="文章库"
  description="统一管理文章预览、主题与推送动作。"
  view={view}
  onViewChange={setView}
  toolbar={<BatchPushToolbar ... />}
  grid={<div className={styles.assetGrid}>{articles.map(renderArticleCard)}</div>}
  table={<Table ... />}
/>
```

- [ ] **Step 4: Run the asset tests, lint, and build**

Run: `cd frontend && npm test -- History ArticleManage && npm run lint && npm run build`
Expected: PASS with both route tests green and the shared asset component building cleanly.

- [ ] **Step 5: Commit the asset experience**

```bash
git add frontend/src/components/workbench/AssetList.tsx frontend/src/components/workbench/AssetList.module.css frontend/src/pages/History.tsx frontend/src/pages/ArticleManage.tsx frontend/src/pages/__tests__/History.test.tsx frontend/src/pages/__tests__/ArticleManage.test.tsx
git commit -m "统一历史任务与文章资产视图"
```

## Task 6: Rework schedule management into an automation workbench

**Files:**
- Create: `frontend/src/components/workbench/AutomationRuleCard.tsx`
- Create: `frontend/src/components/workbench/AutomationRuleCard.module.css`
- Modify: `frontend/src/pages/ScheduleManage.tsx`
- Create: `frontend/src/pages/__tests__/ScheduleManage.test.tsx`

- [ ] **Step 1: Write the failing automation page test**

```tsx
// frontend/src/pages/__tests__/ScheduleManage.test.tsx
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/renderWithRouter'
import App from '@/App'

test('schedule page renders automation hero and segmented rule editor labels', async () => {
  renderWithRouter(<App />, '/schedules')
  expect(await screen.findByText('自动化编排台')).toBeInTheDocument()
  expect(screen.getByText('执行规则')).toBeInTheDocument()
  expect(screen.getByText('推送目标')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the schedule page test to verify it fails**

Run: `cd frontend && npm test -- ScheduleManage`
Expected: FAIL because the current page still uses a single modal and does not render the new section titles.

- [ ] **Step 3: Replace the modal-first flow with a page-level rule editor**

```tsx
// frontend/src/components/workbench/AutomationRuleCard.tsx
export function AutomationRuleCard({ schedule, onEdit, onRunNow }: AutomationRuleCardProps) {
  return (
    <article className={styles.card}>
      <header>
        <h3>{schedule.name}</h3>
        <Tag color={schedule.status === 'running' ? 'processing' : 'default'}>
          {schedule.status === 'running' ? '运行中' : '已停止'}
        </Tag>
      </header>
      <p>{schedule.mode === 'once' ? '指定时间执行' : `每 ${schedule.interval_minutes} 分钟执行一次`}</p>
      <Space>
        <Button onClick={() => onEdit(schedule)}>编辑规则</Button>
        <Button type="primary" onClick={() => onRunNow(schedule.schedule_id)}>立即执行</Button>
      </Space>
    </article>
  )
}
```

```tsx
// frontend/src/pages/ScheduleManage.tsx
<div className={styles.schedulePage}>
  <HeroPanel
    eyebrow="Automation"
    title="自动化编排台"
    description="配置执行节奏、内容策略、热点来源和推送目标。"
    actions={<Button type="primary" onClick={openCreate}>新建自动化规则</Button>}
  />

  <section className={styles.ruleGrid}>
    {schedules.map((schedule) => (
      <AutomationRuleCard key={schedule.schedule_id} schedule={schedule} onEdit={openEdit} onRunNow={handleRunNow} />
    ))}
  </section>

  {(modalOpen || editing) && (
    <SectionBlock title="执行规则" description="定义触发方式与运行时间。">
      {/* split form sections: 执行规则 / 内容生成 / 热点来源 / 推送目标 */}
    </SectionBlock>
  )}
</div>
```

- [ ] **Step 4: Run the automation test and full verification**

Run: `cd frontend && npm test -- ScheduleManage && npm run lint && npm run build`
Expected: PASS with the automation labels visible and the page compiling without the old modal-centric layout breaking.

- [ ] **Step 5: Commit the automation workbench**

```bash
git add frontend/src/components/workbench/AutomationRuleCard.tsx frontend/src/components/workbench/AutomationRuleCard.module.css frontend/src/pages/ScheduleManage.tsx frontend/src/pages/__tests__/ScheduleManage.test.tsx
git commit -m "重构自动化编排台"
```

## Task 7: Unify backstage pages and clean broken Chinese copy during the redesign pass

**Files:**
- Modify: `frontend/src/pages/StyleConfig.tsx`
- Modify: `frontend/src/pages/ModelConfig.tsx`
- Modify: `frontend/src/pages/AccountConfig.tsx`
- Modify: `frontend/src/pages/ArticleManage.tsx`
- Modify: `frontend/src/pages/History.tsx`
- Modify: `frontend/src/pages/TaskCreate.tsx`
- Modify: `frontend/src/pages/ScheduleManage.tsx`
- Modify: `frontend/src/theme.ts`
- Modify: `frontend/src/styles/global.css`

- [ ] **Step 1: Add a failing copy sanity test on one backstage page**

```tsx
// append to frontend/src/pages/__tests__/ArticleManage.test.tsx
test('article manage page does not render mojibake placeholders', async () => {
  renderWithRouter(<App />, '/articles')
  expect(await screen.findByText('文章库')).toBeInTheDocument()
  expect(screen.queryByText(/鍒|鏈|璇锋/)).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run the copy sanity test to verify current mojibake is caught**

Run: `cd frontend && npm test -- ArticleManage`
Expected: FAIL because the existing page and related shared strings still contain mojibake sequences.

- [ ] **Step 3: Replace mojibake strings and bring backstage pages onto the shared workbench sections**

```tsx
// frontend/src/pages/StyleConfig.tsx
<HeroPanel
  eyebrow="Backstage"
  title="风格配置"
  description="维护公众号主题预览、样式编辑和导入导出。"
/>
```

```tsx
// example string cleanup in any page
const PAGE_TITLE = '文章管理'
const EMPTY_STATE = '暂无可预览内容'
const PUSH_BUTTON = '指定推送'
```

```tsx
// frontend/src/pages/ModelConfig.tsx and AccountConfig.tsx
return (
  <div className={styles.backstagePage}>
    <HeroPanel eyebrow="Backstage" title="模型配置" description="维护模型与调用参数。" />
    <SectionBlock title="配置列表" description="按环境查看和调整当前配置。">
      {/* existing content */}
    </SectionBlock>
  </div>
)
```

- [ ] **Step 4: Run the full regression suite**

Run: `cd frontend && npm test && npm run lint && npm run build`
Expected: PASS with all new route tests green, no mojibake assertions failing, and the production build succeeding.

- [ ] **Step 5: Commit the backstage polish and copy cleanup**

```bash
git add frontend/src/pages/StyleConfig.tsx frontend/src/pages/ModelConfig.tsx frontend/src/pages/AccountConfig.tsx frontend/src/pages/ArticleManage.tsx frontend/src/pages/History.tsx frontend/src/pages/TaskCreate.tsx frontend/src/pages/ScheduleManage.tsx frontend/src/theme.ts frontend/src/styles/global.css
git commit -m "统一系统页风格并清理乱码文案"
```

## Self-Review

- Spec coverage: the plan covers the shared shell, visual system, task creation, task detail, assets, automation, backstage pages, copy cleanup, and required verification commands.
- Placeholder scan: no `TODO`, `TBD`, or “similar to Task N” placeholders remain; each task includes explicit files, commands, and code snippets.
- Type consistency: all shared workbench component names are reused consistently across later tasks: `WorkbenchShell`, `HeroPanel`, `SectionBlock`, `StatusRail`, `AssetList`, and `AutomationRuleCard`.

