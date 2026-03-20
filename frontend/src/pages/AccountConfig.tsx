import { useEffect, useState } from 'react'
import {
  Button,
  Card,
  Col,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { TableColumnsType } from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import {
  type AccountConfig,
  type CreateAccountRequest,
  type PlatformType,
  type UpdateAccountRequest,
  createAccount,
  deleteAccount,
  listAccounts,
  testAccountConnection,
  updateAccount,
} from '@/api'

const { Title, Text } = Typography

const PLATFORM_LABELS: Record<PlatformType, string> = {
  wechat_mp: '微信公众号',
  toutiao: '头条号',
}

const PLATFORM_COLORS: Record<PlatformType, string> = {
  wechat_mp: 'blue',
  toutiao: 'orange',
}

export default function AccountConfigPage() {
  const [accounts, setAccounts] = useState<AccountConfig[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingAccount, setEditingAccount] = useState<AccountConfig | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [testingIds, setTestingIds] = useState<Set<string>>(new Set())
  const [form] = Form.useForm()

  const fetchAccounts = async () => {
    setLoading(true)
    try {
      const data = await listAccounts()
      setAccounts(data)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载账号列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAccounts()
  }, [])

  const handleAdd = () => {
    setEditingAccount(null)
    form.resetFields()
    form.setFieldValue('enabled', true)
    setModalOpen(true)
  }

  const handleEdit = (record: AccountConfig) => {
    setEditingAccount(record)
    form.setFieldsValue({
      name: record.name,
      platform: record.platform,
      app_id: record.app_id,
      app_secret: '',
      enabled: record.enabled,
    })
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)

      if (editingAccount) {
        const patch: UpdateAccountRequest = {
          name: values.name,
          platform: values.platform,
          app_id: values.app_id,
          enabled: values.enabled,
        }
        if (values.app_secret) {
          patch.app_secret = values.app_secret
        }
        const updated = await updateAccount(editingAccount.account_id, patch)
        setAccounts((prev) =>
          prev.map((a) => (a.account_id === updated.account_id ? updated : a)),
        )
        message.success('账号已更新')
      } else {
        const data: CreateAccountRequest = {
          name: values.name,
          platform: values.platform,
          app_id: values.app_id,
          app_secret: values.app_secret,
          enabled: values.enabled,
        }
        const created = await createAccount(data)
        setAccounts((prev) => [created, ...prev])
        message.success('账号已创建')
      }

      setModalOpen(false)
    } catch (err) {
      if (err && typeof err === 'object' && 'errorFields' in err) return
      message.error(err instanceof Error ? err.message : '操作失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (accountId: string) => {
    const prev = accounts
    setAccounts((list) => list.filter((a) => a.account_id !== accountId))
    try {
      await deleteAccount(accountId)
      message.success('账号已删除')
    } catch (err) {
      setAccounts(prev)
      message.error(err instanceof Error ? err.message : '删除失败')
    }
  }

  const handleToggleEnabled = async (record: AccountConfig, checked: boolean) => {
    setAccounts((prev) =>
      prev.map((a) => (a.account_id === record.account_id ? { ...a, enabled: checked } : a)),
    )
    try {
      await updateAccount(record.account_id, { enabled: checked })
    } catch (err) {
      setAccounts((prev) =>
        prev.map((a) =>
          a.account_id === record.account_id ? { ...a, enabled: !checked } : a,
        ),
      )
      message.error('状态更新失败')
    }
  }

  const handleTest = async (accountId: string) => {
    setTestingIds((prev) => new Set([...prev, accountId]))
    try {
      const res = await testAccountConnection(accountId)
      if (res.success) {
        message.success(res.message)
      } else {
        message.error(res.message)
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '测试连接失败')
    } finally {
      setTestingIds((prev) => {
        const next = new Set(prev)
        next.delete(accountId)
        return next
      })
    }
  }

  const columns: TableColumnsType<AccountConfig> = [
    {
      title: '账号名称',
      dataIndex: 'name',
      key: 'name',
      width: 160,
    },
    {
      title: '平台',
      dataIndex: 'platform',
      key: 'platform',
      width: 130,
      render: (platform: PlatformType) => (
        <Tag color={PLATFORM_COLORS[platform]}>{PLATFORM_LABELS[platform]}</Tag>
      ),
    },
    {
      title: 'AppID',
      dataIndex: 'app_id',
      key: 'app_id',
    },
    {
      title: 'AppSecret',
      key: 'app_secret',
      width: 140,
      render: () => <Text type="secondary">••••••••</Text>,
    },
    {
      title: '状态',
      key: 'enabled',
      width: 80,
      render: (_, record) => (
        <Switch
          checked={record.enabled}
          onChange={(checked) => handleToggleEnabled(record, checked)}
          size="small"
        />
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_, record) => (
        <Space size="small">
          <Button
            size="small"
            loading={testingIds.has(record.account_id)}
            onClick={() => handleTest(record.account_id)}
          >
            测试连接
          </Button>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确认删除该账号？"
            description="删除后不可恢复"
            onConfirm={() => handleDelete(record.account_id)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ maxWidth: 1100, margin: '24px auto', padding: '0 24px' }}>
      <Row justify="space-between" align="middle" style={{ marginBottom: 20 }}>
        <Col>
          <Title level={2} style={{ margin: 0 }}>
            账号配置
          </Title>
          <Text type="secondary">管理微信公众号等平台的 API 账号凭证</Text>
        </Col>
        <Col>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            新增账号
          </Button>
        </Col>
      </Row>

      <Card>
        <Table
          rowKey="account_id"
          columns={columns}
          dataSource={accounts}
          loading={loading}
          pagination={false}
          locale={{ emptyText: '暂无账号，点击右上角新增' }}
        />
      </Card>

      <Modal
        title={editingAccount ? '编辑账号' : '新增账号'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSubmit}
        confirmLoading={submitting}
        destroyOnClose
        okText={editingAccount ? '保存' : '创建'}
        cancelText="取消"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="name"
            label="账号名称"
            rules={[{ required: true, message: '请输入账号名称' }]}
          >
            <Input placeholder="如：主账号、测试号" maxLength={100} />
          </Form.Item>
          <Form.Item
            name="platform"
            label="平台类型"
            rules={[{ required: true, message: '请选择平台类型' }]}
          >
            <Select
              placeholder="选择平台"
              options={[
                { value: 'wechat_mp', label: '微信公众号' },
                { value: 'toutiao', label: '头条号' },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="app_id"
            label="AppID"
            rules={[{ required: true, message: '请输入 AppID' }]}
          >
            <Input placeholder="输入 AppID" maxLength={200} />
          </Form.Item>
          <Form.Item
            name="app_secret"
            label="AppSecret"
            rules={[
              {
                required: !editingAccount,
                message: '请输入 AppSecret',
              },
            ]}
          >
            <Input.Password
              placeholder={editingAccount ? '留空则不修改' : '输入 AppSecret'}
              visibilityToggle
              maxLength={200}
            />
          </Form.Item>
          <Form.Item name="enabled" label="启用状态" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
