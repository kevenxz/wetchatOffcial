import { Link } from 'react-router-dom'
import BrandMark from '@/components/brand/BrandMark'
import { useCountUp, useReveal, useScrollProgress } from '@/motion'
import motion from '@/motion/motion.module.css'
import styles from './Landing.module.css'

/**
 * Public landing page.
 *
 * Before this existed the only public surface was `/login`: everything else sat
 * behind `RequireAuth`, so there was no front door to judge. The page is entirely
 * static (no API calls, no new public endpoints) — the visual idea comes from the
 * real pipeline and from the typography.
 */

const PIPELINE: { title: string; body: string }[] = [
  { title: '捕获热点', body: '按分类与权重抓取榜单候选，打分排序后给出可写选题。' },
  { title: '先读原文', body: '解析榜单跳转链接，抓取热点对应的原始文章并读取正文。' },
  { title: '过滤来源', body: '相关性、质量、近重复、单域名上限四道关卡，掉因可审计。' },
  { title: '决定结构', body: '由素材自身生成小标题，不同故事必然得到不同结构。' },
  { title: '撰写成稿', body: '按编辑契约成文，机械性缺陷本地修复，不轻易二次生成。' },
  { title: '双重评审', body: '编辑视角与传播视角并行打分，独立评审后才进质量门禁。' },
  { title: '生成配图', body: '封面与文内插图并发生成，配图审核与生成合并为一步。' },
  { title: '推送发布', body: '多账号绑定，草稿箱与直接发布双通道，失败仍保留草稿。' },
]

const CAPABILITIES: { title: string; body: string }[] = [
  {
    title: '热点原文优先',
    body: '先用热点自身的文章决定叙事主线，搜索只作佐证、背景与反向观点，避免每篇都长成同一个样子。',
  },
  {
    title: '来源过滤',
    body: '跑题、抓取失败、同稿转载与单一来源堆叠都会在进入证据包之前被拦下，并记录掉因。',
  },
  {
    title: '动态文章结构',
    body: '结构由证据生成而非模板套用：标题、章节数量与顺序都随素材变化。',
  },
  {
    title: '结构化输出保障',
    body: '输出截断可检测、可重试、可降级；降级会明确标记并转入人工复核，而不是静默产出模板。',
  },
  {
    title: '证据可追溯',
    body: '事实、数据点、案例与反向观点分组入包，每条判断都带来源与置信度。',
  },
  {
    title: '可控的发布链路',
    body: '默认只入草稿箱，直接发布需显式开启；失败回退为 publish_failed，不会丢稿。',
  },
]

const METRICS: { value: number; label: string }[] = [
  { value: 23, label: '工作流节点' },
  { value: 4, label: '来源过滤关卡' },
  { value: 3, label: '文章类型策略' },
  { value: 2, label: '并行评审通道' },
]

function Metric({ value, label }: { value: number; label: string }) {
  const { ref, value: display } = useCountUp(value)
  const { ref: revealRef, revealed } = useReveal<HTMLDivElement>()

  return (
    <div ref={revealRef} className={[motion.reveal, revealed ? motion.revealed : ''].join(' ')}>
      <div className={styles.metric}>
        <span className={styles.metricValue} ref={ref}>
          {display}
        </span>
        <span className={styles.metricLabel}>{label}</span>
      </div>
    </div>
  )
}

export default function LandingPage() {
  const pipelineRef = useScrollProgress<HTMLElement>()
  const heroReveal = useReveal<HTMLDivElement>()
  const flowReveal = useReveal<HTMLDivElement>()

  return (
    <div className={styles.page}>
      <header className={styles.topbar}>
        <div className={`${styles.shell} ${styles.topbarInner}`}>
          <div className={styles.brand}>
            <BrandMark size={30} />
            <span className={styles.brandText}>
              <span className={styles.brandName}>AI 内容工厂</span>
              <span className={styles.brandMeta}>WeChat Article Automation</span>
            </span>
          </div>
          <nav className={styles.topbarActions} aria-label="页面导航">
            <a className={styles.quietLink} href="#pipeline">
              工作流
            </a>
            <a className={styles.quietLink} href="#capabilities">
              能力
            </a>
            <Link className={styles.cta} to="/login">
              进入控制台
            </Link>
          </nav>
        </div>
      </header>

      <main className={styles.shell}>
        <section className={styles.hero}>
          <div className={styles.heroInner}>
            <div
              ref={heroReveal.ref}
              className={[motion.reveal, heroReveal.revealed ? motion.revealed : ''].join(' ')}
            >
              <span className={styles.eyebrow}>
                <span className={styles.eyebrowRule} aria-hidden="true" />
                微信公众号内容生产自动化
              </span>
            </div>

            <h1 className={[styles.headline, motion.pageEnter].join(' ')}>
              从热点到草稿箱
              <span className={styles.headlineAccent}>一条链路全部自动</span>
            </h1>

            <p className={styles.lede}>
              系统先读取热点自身的原文，再过滤搜索来源，由素材决定文章结构，
              经双重评审与配图后推送到草稿箱或直接发布。每一步都可追溯、可复核、可干预。
            </p>

            <div className={styles.heroActions}>
              <Link className={styles.cta} to="/login">
                进入控制台
              </Link>
              <a className={styles.ctaSecondary} href="#pipeline">
                查看工作流
              </a>
            </div>

            <div className={styles.heroMeta}>
              <span>23 个工作流节点</span>
              <span>PostgreSQL + Redis</span>
              <span>单机可部署</span>
              <span>中文内容优先</span>
            </div>
          </div>
        </section>

        <section className={styles.pipeline} id="pipeline" ref={pipelineRef}>
          <div className={styles.sectionHead}>
            <span className={styles.eyebrow}>
              <span className={styles.eyebrowRule} aria-hidden="true" />
              Pipeline
            </span>
            <h2 className={styles.sectionTitle}>八个阶段，一条不会静默降级的链路</h2>
            <p className={styles.sectionLede}>
              每个阶段都产出具名产物：热点候选、原文正文、过滤记录、文章蓝图、成稿、评审结论与发布记录。
            </p>
          </div>

          <div className={styles.progressTrack} aria-hidden="true">
            <span className={styles.progressFill} />
          </div>

          <div
            ref={flowReveal.ref}
            className={[motion.reveal, flowReveal.revealed ? motion.revealed : ''].join(' ')}
          >
            <ol className={styles.flow}>
              {PIPELINE.map((step, index) => (
                <li key={step.title} className={styles.flowStep}>
                  <span className={styles.flowIndex}>{String(index + 1).padStart(2, '0')}</span>
                  <span className={styles.flowTitle}>{step.title}</span>
                  <span className={styles.flowBody}>{step.body}</span>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className={styles.capabilities} id="capabilities">
          <div className={styles.sectionHead}>
            <span className={styles.eyebrow}>
              <span className={styles.eyebrowRule} aria-hidden="true" />
              Capabilities
            </span>
            <h2 className={styles.sectionTitle}>为「发得出去、经得起核对」而设计</h2>
          </div>

          <ul className={styles.capabilityGrid}>
            {CAPABILITIES.map((item) => (
              <li key={item.title} className={styles.capability}>
                <h3 className={styles.capabilityTitle}>{item.title}</h3>
                <p className={styles.capabilityBody}>{item.body}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className={styles.metrics}>
          <div className={styles.metricGrid}>
            {METRICS.map((metric) => (
              <Metric key={metric.label} value={metric.value} label={metric.label} />
            ))}
          </div>
        </section>

        <section className={styles.closing}>
          <h2 className={styles.closingTitle}>现在就可以跑一条完整链路</h2>
          <p className={styles.lede}>
            用一句话主题启动任务，或先让系统抓一轮热点。默认只入草稿箱，确认无误后再决定是否直接发布。
          </p>
          <Link className={styles.cta} to="/login">
            进入控制台
          </Link>
        </section>
      </main>

      <footer className={`${styles.shell} ${styles.footer}`}>
        <span>AI 内容工厂 · 微信公众号文章自动发布系统</span>
        <span>FastAPI · LangGraph · React</span>
      </footer>
    </div>
  )
}
