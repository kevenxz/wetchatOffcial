import type { CSSProperties } from 'react'
import { useEffect, useMemo, useState } from 'react'
import dayjs from 'dayjs'
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Tag, message } from 'antd'
import type { TableColumnsType } from 'antd'
import {
  createUser,
  deleteUser,
  listUsers,
  updateUser,
  type CreateUserRequest,
  type UpdateUserRequest,
  type UserProfile,
  type UserRole,
} from '@/api'
import { HeroPanel, SectionBlock } from '@/components/workbench'

const roleLabelMap: Record<UserRole, string> = {
  admin: '管理员',
  operator: '运营',
}

const listStyle: CSSProperties = {
  margin: 0,
  paddingInlineStart: 20,
  display: 'grid',
  gap: 6,
}

export default function UserManage() {
  const [users, setUsers] = useState<UserProfile[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<UserProfile | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()

  const enabledCount = useMemo(() => users.filter((item) => item.enabled).length, [users])

  const fetchUsers = async () => {
    setLoading(true)
    try {
      const data = await listUsers()
      setUsers(data)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载用户失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchUsers()
  }, [])

  const handleCreate = () => {
    setEditingUser(null)
    form.resetFields()
    form.setFieldsValue({ role: 'operator', enabled: true })
    setModalOpen(true)
  }

  const handleEdit = (record: UserProfile) => {
    setEditingUser(record)
    form.setFieldsValue({
      username: record.username,
      display_name: record.display_name,
      role: record.role,
      enabled: record.enabled,
      password: '',
    })
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      if (editingUser) {
        const patch: UpdateUserRequest = {
          display_name: values.display_name,
          role: values.role,
          enabled: values.enabled,
        }
        if (values.password) {
          patch.password = values.password
        }
        const updated = await updateUser(editingUser.user_id, patch)
        setUsers((prev) => prev.map((item) => (item.user_id === updated.user_id ? updated : item)))
        message.success('系统账号已更新')
      } else {
        const payload: CreateUserRequest = {
          username: values.username,
          password: values.password,
          display_name: values.display_name,
          role: values.role,
          enabled: values.enabled,
        }
        const created = await createUser(payload)
        setUsers((prev) => [created, ...prev])
        message.success('系统账号已创建')
      }
      setModalOpen(false)
    } catch (err) {
      if (err && typeof err === 'object' && 'errorFields' in err) return
      message.error(err instanceof Error ? err.message : '提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (userId: string) => {
    try {
      await deleteUser(userId)
      setUsers((prev) => prev.filter((item) => item.user_id !== userId))
      message.success('系统账号已删除')
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败')
    }
  }

  const handleToggleEnabled = async (record: UserProfile, enabled: boolean) => {
    setUsers((prev) =>
      prev.map((item) => (item.user_id === record.user_id ? { ...item, enabled } : item)),
    )
    try {
      const updated = await updateUser(record.user_id, { enabled })
      setUsers((prev) => prev.map((item) => (item.user_id === record.user_id ? updated : item)))
    } catch (err) {
      setUsers((prev) =>
        prev.map((item) => (item.user_id === record.user_id ? { ...item, enabled: !enabled } : item)),
      )
      message.error(err instanceof Error ? err.message : '状态更新失败')
    }
  }

  const columns: TableColumnsType<UserProfile> = [
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
      width: 160,
    },
    {
      title: '显示名称',
      dataIndex: 'display_name',
      key: 'display_name',
      width: 180,
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      width: 120,
      render: (role: UserRole) => <Tag color={role === 'admin' ? 'volcano' : 'blue'}>{roleLabelMap[role]}</Tag>,
    },
    {
      title: '启用',
      key: 'enabled',
      width: 80,
      render: (_, record) => (
        <Switch checked={record.enabled} size="small" onChange={(checked) => handleToggleEnabled(record, checked)} />
      ),
    },
    {
      title: '最近登录',
      dataIndex: 'last_login_at',
      key: 'last_login_at',
      width: 180,
      render: (value?: string | null) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_, record) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除该用户？"
            description="删除后不可恢复"
            onConfirm={() => handleDelete(record.user_id)}
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
        eyebrow="Admin"
        title="系统账号管理"
        description="集中维护系统登录账号、角色权限和启用状态"
      >
        <ul aria-label="系统账号提示" style={listStyle}>
          <li>管理员账号可创建、修改和删除其他用户</li>
          <li>可在编辑用户时重置登录密码</li>
          <li>禁用用户后该账号将无法登录系统</li>
        </ul>
      </HeroPanel>

      <SectionBlock
        title="账号列表"
        aside={(
          <Space>
            <Tag color="green">启用 {enabledCount}</Tag>
            <Tag color="blue">总数 {users.length}</Tag>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
              新建系统账号
            </Button>
          </Space>
        )}
      >
        <Table<UserProfile>
          rowKey="user_id"
          loading={loading}
          columns={columns}
          dataSource={users}
          pagination={false}
          locale={{ emptyText: '暂无系统账号' }}
        />
      </SectionBlock>

      <Modal
        title={editingUser ? '编辑系统账号' : '新建系统账号'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSubmit}
        confirmLoading={submitting}
        destroyOnClose
        okText={editingUser ? '保存' : '创建'}
        cancelText="取消"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item
            label="用户名"
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input disabled={Boolean(editingUser)} placeholder="仅支持字母数字，至少 3 位" />
          </Form.Item>

          <Form.Item
            label="显示名称"
            name="display_name"
            rules={[{ required: true, message: '请输入显示名称' }]}
          >
            <Input placeholder="例如：运营A、管理员" />
          </Form.Item>

          <Form.Item
            label="角色"
            name="role"
            rules={[{ required: true, message: '请选择角色' }]}
          >
            <Select
              options={[
                { value: 'admin', label: '管理员' },
                { value: 'operator', label: '运营' },
              ]}
            />
          </Form.Item>

          <Form.Item
            label="登录密码"
            name="password"
            rules={[
              {
                required: !editingUser,
                message: '请输入登录密码',
              },
              {
                min: 8,
                message: '密码至少 8 位',
              },
            ]}
          >
            <Input.Password placeholder={editingUser ? '留空则不修改密码' : '请输入登录密码'} />
          </Form.Item>

          <Form.Item name="enabled" label="启用状态" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
