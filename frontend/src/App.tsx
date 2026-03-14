import { useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Layout, Menu } from 'antd'
import {
  PlusCircleOutlined,
  HistoryOutlined,
  SettingOutlined,
  WechatOutlined,
} from '@ant-design/icons'
import type { MenuProps } from 'antd'
import TaskCreate from '@/pages/TaskCreate'
import TaskDetail from '@/pages/TaskDetail'
import History from '@/pages/History'

const { Sider, Content } = Layout

type MenuItem = Required<MenuProps>['items'][number]

const menuItems: MenuItem[] = [
  { key: '/task', icon: <PlusCircleOutlined />, label: '创建任务' },
  { key: '/history', icon: <HistoryOutlined />, label: '历史任务' },
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
]

function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()

  const selectedKey = '/' + location.pathname.split('/')[1]

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed} width={220}>
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: collapsed ? 'center' : 'flex-start',
            padding: collapsed ? 0 : '0 24px',
            gap: 8,
            color: '#fff',
            fontSize: collapsed ? 20 : 16,
            fontWeight: 600,
            borderBottom: '1px solid rgba(255,255,255,0.1)',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
          }}
        >
          <WechatOutlined style={{ fontSize: 20, flexShrink: 0 }} />
          {!collapsed && <span>公众号助手</span>}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>

      <Layout>
        <Content>
          <Routes>
            <Route path="/" element={<Navigate to="/task" replace />} />
            <Route path="/task" element={<TaskCreate />} />
            <Route path="/task/:id" element={<TaskDetail />} />
            <Route path="/history" element={<History />} />
            <Route path="/settings" element={<PagePlaceholder title="系统设置" />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}

function PagePlaceholder({ title }: { title: string }) {
  return (
    <div
      style={{
        background: '#fff',
        borderRadius: 8,
        padding: 24,
        minHeight: 360,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'rgba(0,0,0,0.45)',
        fontSize: 16,
      }}
    >
      {title} — 页面开发中
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppLayout />
    </BrowserRouter>
  )
}
