import { useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Layout, Menu } from 'antd'
import type { MenuProps } from 'antd'
import {
  ApiOutlined,
  CalendarOutlined,
  FileTextOutlined,
  HistoryOutlined,
  PlusCircleOutlined,
  SettingOutlined,
  UserOutlined,
  WechatOutlined,
} from '@ant-design/icons'
import TaskCreate from '@/pages/TaskCreate'
import TaskDetail from '@/pages/TaskDetail'
import History from '@/pages/History'
import StyleConfigPage from '@/pages/StyleConfig'
import ModelConfigPage from '@/pages/ModelConfig'
import AccountConfigPage from '@/pages/AccountConfig'
import ArticleManage from '@/pages/ArticleManage'
import ScheduleManage from '@/pages/ScheduleManage'

const { Sider, Content } = Layout

type MenuItem = Required<MenuProps>['items'][number]

const menuItems: MenuItem[] = [
  { key: '/task', icon: <PlusCircleOutlined />, label: '创建任务' },
  { key: '/history', icon: <HistoryOutlined />, label: '历史任务' },
  { key: '/articles', icon: <FileTextOutlined />, label: '文章管理' },
  { key: '/schedules', icon: <CalendarOutlined />, label: '定时任务' },
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
  { key: '/models', icon: <ApiOutlined />, label: 'Model Config' },
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
            <Route path="/articles" element={<ArticleManage />} />
            <Route path="/schedules" element={<ScheduleManage />} />
            <Route path="/settings" element={<StyleConfigPage />} />
            <Route path="/models" element={<ModelConfigPage />} />
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
