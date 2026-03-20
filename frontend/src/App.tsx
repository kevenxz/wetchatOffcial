import { useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Layout, Menu } from 'antd'
import {
  PlusCircleOutlined,
  HistoryOutlined,
  SettingOutlined,
  WechatOutlined,
  UserOutlined,
} from '@ant-design/icons'
import type { MenuProps } from 'antd'
import TaskCreate from '@/pages/TaskCreate'
import TaskDetail from '@/pages/TaskDetail'
import History from '@/pages/History'
import StyleConfigPage from '@/pages/StyleConfig'
import AccountConfigPage from '@/pages/AccountConfig'

const { Sider, Content } = Layout

type MenuItem = Required<MenuProps>['items'][number]

const menuItems: MenuItem[] = [
  { key: '/task', icon: <PlusCircleOutlined />, label: '创建任务' },
  { key: '/history', icon: <HistoryOutlined />, label: '历史任务' },
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
  { key: '/accounts', icon: <UserOutlined />, label: '账号配置' },
]

function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()

  const selectedKey = '/' + location.pathname.split('/')[1]

  return (
    <Layout style={{ height: '100vh', overflow: 'hidden' }}>
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

      <Layout style={{ overflow: 'hidden' }}>
        <Content style={{ height: '100%', overflow: 'auto', backgroundColor: '#f5f5f5' }}>
          <Routes>
            <Route path="/" element={<Navigate to="/task" replace />} />
            <Route path="/task" element={<TaskCreate />} />
            <Route path="/task/:id" element={<TaskDetail />} />
            <Route path="/history" element={<History />} />
            <Route path="/settings" element={<StyleConfigPage />} />
            <Route path="/accounts" element={<AccountConfigPage />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppLayout />
    </BrowserRouter>
  )
}
