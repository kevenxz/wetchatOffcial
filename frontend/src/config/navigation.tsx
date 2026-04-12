import type { ReactNode } from 'react'
import {
  CalendarOutlined,
  FileTextOutlined,
  HistoryOutlined,
  PlusCircleOutlined,
  SettingOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { matchPath } from 'react-router-dom'

export type RouteMeta = {
  path: string
  matchPath?: string
  navLabel: string
  contextTitle: string
  contextEyebrow: string
  contextDescription: string
  icon: ReactNode
  nav?: boolean
}

export const routeMetadata: RouteMeta[] = [
  {
    path: '/task',
    navLabel: '创作台',
    contextTitle: '任务创建',
    contextEyebrow: 'Brand Studio',
    contextDescription: '配置选题、受众和生成策略，然后在当前工作台继续推进内容生产。',
    icon: <PlusCircleOutlined />,
  },
  {
    path: '/task/:id',
    matchPath: '/task/:id',
    navLabel: '创作台',
    contextTitle: '任务详情',
    contextEyebrow: 'Brand Studio',
    contextDescription: '查看生成进度、草稿状态与后续动作。',
    icon: <PlusCircleOutlined />,
    nav: false,
  },
  {
    path: '/history',
    navLabel: '任务档案',
    contextTitle: '历史任务',
    contextEyebrow: 'Archive',
    contextDescription: '回看过往生成记录，筛选和复用已完成的创作任务。',
    icon: <HistoryOutlined />,
  },
  {
    path: '/articles',
    navLabel: '文章库',
    contextTitle: '文章管理',
    contextEyebrow: 'Publishing',
    contextDescription: '集中查看文章成稿、预览内容并准备发布。',
    icon: <FileTextOutlined />,
  },
  {
    path: '/schedules',
    navLabel: '排期台',
    contextTitle: '定时任务',
    contextEyebrow: 'Automation',
    contextDescription: '安排任务执行节奏，保持内容生产持续运转。',
    icon: <CalendarOutlined />,
  },
  {
    path: '/settings',
    navLabel: '风格设定',
    contextTitle: '系统设置',
    contextEyebrow: 'System',
    contextDescription: '维护品牌风格、文案偏好与系统级配置。',
    icon: <SettingOutlined />,
  },
  {
    path: '/models',
    navLabel: '模型配置',
    contextTitle: '模型配置',
    contextEyebrow: 'Models',
    contextDescription: '管理模型接入和生成能力选项。',
    icon: <SettingOutlined />,
  },
  {
    path: '/accounts',
    navLabel: '账号中心',
    contextTitle: '账号配置',
    contextEyebrow: 'Accounts',
    contextDescription: '维护发布账号与渠道关联信息。',
    icon: <UserOutlined />,
  },
]

export const navigationItems = routeMetadata.filter((route) => route.nav !== false)

export function resolveRouteMeta(pathname: string) {
  return (
    routeMetadata.find((route) =>
      matchPath({ path: route.matchPath ?? route.path, end: true }, pathname),
    ) ?? routeMetadata[0]
  )
}
