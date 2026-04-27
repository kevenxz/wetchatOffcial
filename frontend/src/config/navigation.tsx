import type { ReactNode } from 'react'
import {
  CalendarOutlined,
  FileTextOutlined,
  HistoryOutlined,
  PictureOutlined,
  PlusCircleOutlined,
  SafetyOutlined,
  SettingOutlined,
  TeamOutlined,
  ThunderboltOutlined,
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
    path: '/history',
    navLabel: '工作台',
    contextTitle: '工作台',
    contextEyebrow: 'Workspace',
    contextDescription: '查看系统运行概览、近期任务和关键产出。',
    icon: <HistoryOutlined />,
  },
  {
    path: '/task',
    navLabel: '任务管理',
    contextTitle: '任务管理',
    contextEyebrow: 'Tasks',
    contextDescription: '查看任务状态、审核进度、失败重试和文章生成记录。',
    icon: <PlusCircleOutlined />,
  },
  {
    path: '/task/new',
    navLabel: '新建任务',
    contextTitle: '新建任务',
    contextEyebrow: 'Create',
    contextDescription: '配置主题、受众和生成策略，然后启动完整创作流程。',
    icon: <PlusCircleOutlined />,
    nav: false,
  },
  {
    path: '/task/:id',
    matchPath: '/task/:id',
    navLabel: '任务详情',
    contextTitle: '任务详情',
    contextEyebrow: 'Task',
    contextDescription: '查看生成进度、草稿状态与后续操作。',
    icon: <PlusCircleOutlined />,
    nav: false,
  },
  {
    path: '/topics',
    navLabel: '热点监控',
    contextTitle: '热点监控',
    contextEyebrow: 'Hotspots',
    contextDescription: '集中管理热点候选、人工选题和转任务动作。',
    icon: <ThunderboltOutlined />,
  },
  {
    path: '/articles',
    navLabel: '内容管理',
    contextTitle: '内容管理',
    contextEyebrow: 'Content',
    contextDescription: '集中查看文章成果、预览内容并准备发布。',
    icon: <FileTextOutlined />,
  },
  {
    path: '/reviews',
    navLabel: '人工审核',
    contextTitle: '人工审核',
    contextEyebrow: 'Review',
    contextDescription: '处理人工复核队列，查看风险摘要并决定通过、驳回或退回改写。',
    icon: <SafetyOutlined />,
  },
  {
    path: '/images',
    navLabel: '图片管理',
    contextTitle: '图片管理',
    contextEyebrow: 'Images',
    contextDescription: '查看封面和文内配图资产。',
    icon: <PictureOutlined />,
  },
  {
    path: '/schedules',
    navLabel: '发布记录',
    contextTitle: '发布记录',
    contextEyebrow: 'Publishing',
    contextDescription: '查看发布动作、定时计划和运行结果。',
    icon: <CalendarOutlined />,
  },
  {
    path: '/settings',
    navLabel: '配置中心',
    contextTitle: '配置中心',
    contextEyebrow: 'System',
    contextDescription: '维护品牌风格、文案偏好与系统配置。',
    icon: <SettingOutlined />,
  },
  {
    path: '/models',
    navLabel: '模型配置',
    contextTitle: '模型配置',
    contextEyebrow: 'Models',
    contextDescription: '管理模型接入与生成能力参数。',
    icon: <SettingOutlined />,
  },
  {
    path: '/accounts',
    navLabel: '渠道账号',
    contextTitle: '渠道账号配置',
    contextEyebrow: 'Accounts',
    contextDescription: '维护微信公众号等发布渠道的接入凭据。',
    icon: <UserOutlined />,
  },
  {
    path: '/users',
    navLabel: '系统账号',
    contextTitle: '系统账号管理',
    contextEyebrow: 'Security',
    contextDescription: '管理登录账号、角色与启用状态。',
    icon: <TeamOutlined />,
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
