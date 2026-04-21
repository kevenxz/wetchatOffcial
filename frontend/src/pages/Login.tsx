import type { CSSProperties } from 'react'
import { useEffect, useState } from 'react'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { Button, Card, Form, Input, Space, Typography, message } from 'antd'
import { Navigate, useNavigate } from 'react-router-dom'
import { login } from '@/api'
import useAuthStore from '@/store/authStore'

const cardStyle: CSSProperties = {
  width: 420,
  maxWidth: '92vw',
  borderRadius: 16,
}

const layoutStyle: CSSProperties = {
  minHeight: '100vh',
  display: 'grid',
  placeItems: 'center',
  background: 'linear-gradient(140deg, #edf5ff 0%, #f8fbff 45%, #eef8f4 100%)',
  padding: 20,
}

export default function LoginPage() {
  const navigate = useNavigate()
  const [submitting, setSubmitting] = useState(false)
  const token = useAuthStore((state) => state.token)
  const initialized = useAuthStore((state) => state.initialized)
  const bootstrap = useAuthStore((state) => state.bootstrap)
  const setSession = useAuthStore((state) => state.setSession)

  useEffect(() => {
    if (!initialized) bootstrap()
  }, [bootstrap, initialized])

  if (initialized && token) {
    return <Navigate to="/task" replace />
  }

  const handleSubmit = async (values: { username: string; password: string }) => {
    setSubmitting(true)
    try {
      const result = await login(values)
      setSession(result.access_token, result.user)
      navigate('/task', { replace: true })
      message.success('登录成功')
    } catch (err) {
      message.error(err instanceof Error ? err.message : '登录失败，请重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={layoutStyle}>
      <Card style={cardStyle} bodyStyle={{ padding: 28 }}>
        <Space direction="vertical" size={20} style={{ width: '100%' }}>
          <div>
            <Typography.Title level={3} style={{ marginBottom: 4 }}>
              系统登录
            </Typography.Title>
            <Typography.Text type="secondary">
              使用系统账号登录后可管理任务、模型配置和账号权限
            </Typography.Text>
          </div>

          <Form layout="vertical" onFinish={handleSubmit} initialValues={{ username: 'admin', password: 'admin123456' }}>
            <Form.Item
              label="用户名"
              name="username"
              rules={[{ required: true, message: '请输入用户名' }]}
            >
              <Input prefix={<UserOutlined />} placeholder="请输入用户名" autoComplete="username" />
            </Form.Item>
            <Form.Item
              label="密码"
              name="password"
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="请输入密码" autoComplete="current-password" />
            </Form.Item>

            <Button type="primary" htmlType="submit" loading={submitting} block>
              登录
            </Button>
          </Form>
        </Space>
      </Card>
    </div>
  )
}
