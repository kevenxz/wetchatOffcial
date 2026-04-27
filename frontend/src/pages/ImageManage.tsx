import { Empty } from 'antd'

export default function ImageManage() {
  return (
    <div className="backstage-page">
      <section className="backstage-surface-card">
        <Empty description="暂无图片资产" style={{ padding: 64 }} />
      </section>
    </div>
  )
}
