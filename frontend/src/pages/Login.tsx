import { useEffect, useState } from 'react'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { Button, Card, Form, Input, Space, Typography, message } from 'antd'
import { Navigate, useNavigate } from 'react-router-dom'
import { login } from '@/api'
import { ThemeModeSwitch } from '@/components/workbench'
import useAuthStore from '@/store/authStore'
import styles from './Login.module.css'

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
    <main className={styles.page}>
      <div className={styles.themeControl}>
        <ThemeModeSwitch />
      </div>
      <section className={styles.manifesto} aria-label="产品介绍">
        <span className={styles.edition}>EDITORIAL OS · 2026</span>
        <h1>让每一次选题，<br />都有成为代表作的理由。</h1>
        <p>从热点、证据到标题与分享动机，一条可追踪的智能编辑链路。</p>
        <div className={styles.signalRow}>
          <span>01 / 研究</span>
          <span>02 / 策略</span>
          <span>03 / 反思</span>
        </div>
      </section>

      <Card className={styles.card} styles={{ body: { padding: 32 } }}>
        <Space direction="vertical" size={20} style={{ width: '100%' }}>
          <div>
            <Typography.Text className={styles.kicker}>CONTENT COMMAND ROOM</Typography.Text>
            <Typography.Title level={3} className={styles.title}>
              回到编辑部
            </Typography.Title>
            <Typography.Text type="secondary">
              登录后继续管理选题、Agent 运行与文章发布
            </Typography.Text>
          </div>

          <Form layout="vertical" onFinish={handleSubmit} initialValues={{ username: 'admin' }}>
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
    </main>
  )
}
