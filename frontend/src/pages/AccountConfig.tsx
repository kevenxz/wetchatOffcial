import { useEffect, useMemo, useState } from 'react'
import {
  DeleteOutlined,
  EditOutlined,
  LinkOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
  WechatOutlined,
} from '@ant-design/icons'
import {
  Button,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { TableColumnsType } from 'antd'
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
import { HeroPanel, SectionBlock, SignalCard } from '@/components/workbench'

const { Text } = Typography

const PLATFORM_LABELS: Record<PlatformType, string> = {
  wechat_mp: '微信公众号',
  toutiao: '头条号',
}

const PLATFORM_COLORS: Record<PlatformType, string> = {
  wechat_mp: 'blue',
  toutiao: 'orange',
}

const guidanceListStyle = {
  display: 'grid',
  gap: 8,
  margin: 0,
  paddingInlineStart: 20,
  listStyleType: 'disc',
  listStylePosition: 'outside',
  color: 'var(--text-secondary)',
  fontSize: 13,
  lineHeight: 1.6,
}

const panelStyle = {
  display: 'grid',
  gap: 16,
  padding: 20,
  borderRadius: 16,
  border: '1px solid var(--app-border)',
  background: 'var(--app-surface)',
}

const panelTitleStyle = {
  margin: 0,
  fontSize: 15,
  fontWeight: 600,
  color: 'var(--app-text)',
}

export default function AccountConfigPage() {
  const [accounts, setAccounts] = useState<AccountConfig[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingAccount, setEditingAccount] = useState<AccountConfig | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [testingIds, setTestingIds] = useState<Set<string>>(new Set())
  const [form] = Form.useForm()

  const enabledCount = useMemo(() => accounts.filter((account) => account.enabled).length, [accounts])
  const platformCount = useMemo(() => new Set(accounts.map((account) => account.platform)).size, [accounts])

  const fetchAccounts = async () => {
    setLoading(true)
    try {
      const data = await listAccounts()
      setAccounts(data)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载账户列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchAccounts()
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
        setAccounts((prev) => prev.map((account) => (account.account_id === updated.account_id ? updated : account)))
        message.success('账户已更新')
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
        message.success('账户已创建')
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
    const previousAccounts = accounts
    setAccounts((list) => list.filter((account) => account.account_id !== accountId))
    try {
      await deleteAccount(accountId)
      message.success('账户已删除')
    } catch (err) {
      setAccounts(previousAccounts)
      message.error(err instanceof Error ? err.message : '删除失败')
    }
  }

  const handleToggleEnabled = async (record: AccountConfig, checked: boolean) => {
    setAccounts((prev) =>
      prev.map((account) =>
        account.account_id === record.account_id ? { ...account, enabled: checked } : account,
      ),
    )
    try {
      await updateAccount(record.account_id, { enabled: checked })
    } catch (err) {
      setAccounts((prev) =>
        prev.map((account) =>
          account.account_id === record.account_id ? { ...account, enabled: !checked } : account,
        ),
      )
      message.error('状态更新失败')
    }
  }

  const handleTest = async (accountId: string) => {
    setTestingIds((prev) => new Set([...prev, accountId]))
    try {
      const result = await testAccountConnection(accountId)
      if (result.success) {
        message.success(result.message)
      } else {
        message.error(result.message)
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '连接测试失败')
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
      title: '账户名称',
      dataIndex: 'name',
      key: 'name',
      width: 180,
    },
    {
      title: '平台',
      dataIndex: 'platform',
      key: 'platform',
      width: 140,
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
      render: () => <Text type="secondary">••••••••••••</Text>,
    },
    {
      title: '启用',
      key: 'enabled',
      width: 90,
      render: (_, record) => (
        <Switch checked={record.enabled} onChange={(checked) => handleToggleEnabled(record, checked)} size="small" />
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 240,
      render: (_, record) => (
        <Space size="small" wrap>
          <Button size="small" loading={testingIds.has(record.account_id)} onClick={() => handleTest(record.account_id)}>
            测试连接
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除这个账户吗？"
            description="删除后不可恢复。"
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
    <div className="backstage-page">
      <HeroPanel
        eyebrow="System Backstage"
        title="账户接入配置"
        description="统一管理微信公众号和其他投放账户的凭证、启用状态与连通性。"
      >
        <ul style={guidanceListStyle} aria-label="账户配置提示">
          <li>新增或编辑账户后，建议立刻执行一次连接测试。</li>
          <li>启用状态会直接影响调度和发布链路的可用性。</li>
          <li>AppSecret 编辑时可留空，避免覆盖已经存在的密钥。</li>
        </ul>
      </HeroPanel>

      <div className="backstage-grid backstage-grid--double">
        <SectionBlock
          title="账户清单"
          aside={
            <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
              新增账户
            </Button>
          }
        >
          <div style={panelStyle}>
            <Table
              rowKey="account_id"
              columns={columns}
              dataSource={accounts}
              loading={loading}
              pagination={false}
              locale={{ emptyText: '暂无账户，先点击右上角新增一条接入配置。' }}
            />
          </div>
        </SectionBlock>

        <SectionBlock title="接入提醒" aside={<Text type="secondary">保留原有增删改、启停和连接测试行为。</Text>}>
          <div className="backstage-note-list">
            <SignalCard
              icon={<WechatOutlined />}
              title="公众号优先"
              description="微信公众号仍然是当前工作流的主要发布目标，启停会直接影响推送可见性。"
            />
            <SignalCard
              icon={<LinkOutlined />}
              title="连接测试"
              description="新增或修改凭证后尽快测试连接，避免调度真正执行时才发现认证失败。"
            />
            <SignalCard
              icon={<SafetyCertificateOutlined />}
              title="凭证管理"
              description="编辑时保留 AppSecret 为空的能力，避免误覆盖已有生产密钥。"
            />
          </div>

          <div style={panelStyle}>
            <Space size={[8, 8]} wrap>
              <Tag color="blue">账户数 {String(accounts.length).padStart(2, '0')}</Tag>
              <Tag color="green">启用数 {String(enabledCount).padStart(2, '0')}</Tag>
              <Tag color="gold">平台数 {String(platformCount).padStart(2, '0')}</Tag>
            </Space>
          </div>
        </SectionBlock>
      </div>

      <Modal
        title={editingAccount ? '编辑账户' : '新增账户'}
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
            label="账户名称"
            rules={[{ required: true, message: '请输入账户名称' }]}
          >
            <Input placeholder="例如：主账号、测试号" maxLength={100} />
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
