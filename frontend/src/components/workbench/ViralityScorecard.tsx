import styles from './ViralityScorecard.module.css'

const DIMENSION_LABELS: Record<string, string> = {
  headline: '标题点击力',
  hook: '首屏留存',
  novelty: '观点新颖度',
  resonance: '读者共鸣',
  shareability: '分享动机',
  credibility: '证据可信度',
  readability: '阅读流畅度',
}

interface ViralityScorecardProps {
  strategy?: Record<string, any> | null
  review?: Record<string, any> | null
}

function scoreTone(score: number) {
  if (score >= 85) return styles.strong
  if (score >= 75) return styles.steady
  return styles.weak
}

export default function ViralityScorecard({ strategy, review }: ViralityScorecardProps) {
  const score = Number(review?.score || 0)
  const threshold = Number(review?.threshold || 78)
  const dimensions = Object.entries((review?.dimensions || {}) as Record<string, number>)
  const guidance = (review?.revision_guidance || []) as string[]

  return (
    <section className={styles.scorecard} aria-label="传播潜力评估">
      <div className={styles.scoreColumn}>
        <span className={styles.eyebrow}>Distribution Potential</span>
        <div className={`${styles.score} ${scoreTone(score)}`}>{score || '—'}</div>
        <p className={styles.scoreCaption}>
          {score ? (score >= threshold ? '已越过传播质量线' : `距离质量线还差 ${threshold - score} 分`) : '等待独立评审'}
        </p>
        <div className={styles.thresholdTrack} aria-label={`质量线 ${threshold} 分`}>
          <span style={{ width: `${Math.min(score, 100)}%` }} />
          <i style={{ left: `${threshold}%` }} />
        </div>
      </div>

      <div className={styles.strategyColumn}>
        <span className={styles.eyebrow}>Editorial Bet</span>
        <h3>{strategy?.core_promise || '传播承诺尚未生成'}</h3>
        <p>{strategy?.audience_tension || '系统将先识别读者张力，再决定内容角度。'}</p>
        {strategy?.share_trigger ? <blockquote>{strategy.share_trigger}</blockquote> : null}
      </div>

      <div className={styles.dimensionColumn}>
        <span className={styles.eyebrow}>Signal Board</span>
        <div className={styles.dimensions}>
          {dimensions.length ? dimensions.map(([key, value]) => (
            <div key={key} className={styles.dimension}>
              <span>{DIMENSION_LABELS[key] || key}</span>
              <div><i style={{ width: `${Math.min(Number(value), 100)}%` }} /></div>
              <strong>{value}</strong>
            </div>
          )) : <p className={styles.empty}>成稿后将显示七维传播信号。</p>}
        </div>
        {guidance.length ? (
          <details className={styles.guidance}>
            <summary>{guidance.length} 条定向修订建议</summary>
            <ol>{guidance.map((item) => <li key={item}>{item}</li>)}</ol>
          </details>
        ) : null}
      </div>
    </section>
  )
}
