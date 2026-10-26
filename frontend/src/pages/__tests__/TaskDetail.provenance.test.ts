import { describe, expect, it } from 'vitest'
import { collectImageRefs } from '../TaskDetail'

/**
 * A photograph taken from a reference article forces human review, so the reviewer has to see
 * where it came from. This covers the provenance extraction that the gallery renders.
 */
const sourceAsset = {
  provider: 'source',
  role: 'cover',
  url: 'artifacts/source_images/t/abc.jpg',
  path: 'artifacts/source_images/t/abc.jpg',
  remote_url: 'https://img.example.com/original.jpg',
  attribution: {
    source_title: '示例新闻：某公司上市',
    source_domain: 'news.example.com',
    source_url: 'https://news.example.com/article-1',
    image_url: 'https://img.example.com/original.jpg',
  },
}

describe('collectImageRefs provenance', () => {
  it('attaches provenance to a harvested photo', () => {
    const refs = collectImageRefs({ visual_assets: [sourceAsset] })

    expect(refs).toHaveLength(1)
    expect(refs[0].provenance).toEqual({
      label: '示例新闻：某公司上市',
      url: 'https://news.example.com/article-1',
      warning: undefined,
    })
  })

  it('carries the crop warning so the reviewer sees it', () => {
    const refs = collectImageRefs({
      visual_assets: [{ ...sourceAsset, notes: ['封面裁切丢弃 26% 画面，请确认主体是否被裁掉'] }],
    })

    expect(refs[0].provenance?.warning).toContain('裁切')
  })

  it('falls back to the domain when the source has no title', () => {
    const refs = collectImageRefs({
      visual_assets: [
        { ...sourceAsset, attribution: { ...sourceAsset.attribution, source_title: '', source_domain: 'news.example.com' } },
      ],
    })

    expect(refs[0].provenance?.label).toBe('news.example.com')
  })

  it('leaves generated images without provenance', () => {
    const refs = collectImageRefs({
      visual_assets: [{ provider: 'model', role: 'cover', url: 'artifacts/generated_images/a.png', prompt: 'x' }],
    })

    expect(refs[0].provenance).toBeUndefined()
  })

  it('still collects the cover and inline illustrations as before', () => {
    const refs = collectImageRefs({
      cover_image: 'artifacts/generated_images/cover.png',
      illustrations: ['artifacts/source_images/t/a.jpg', 'artifacts/generated_images/b.png'],
      visual_assets: [sourceAsset],
    })

    expect(refs.map((ref) => ref.role)).toEqual(['cover', '插图1', '插图2', 'cover'])
    // The photo referenced by both `illustrations` and `visual_assets` is de-duplicated.
    expect(new Set(refs.map((ref) => ref.src)).size).toBe(refs.length)
  })

  it('tolerates a missing attribution block', () => {
    const refs = collectImageRefs({
      visual_assets: [{ provider: 'source', role: 'cover', path: 'a.jpg', attribution: {} }],
    })

    expect(refs[0].provenance).toBeUndefined()
  })

  it('handles a missing article', () => {
    expect(collectImageRefs(undefined)).toEqual([])
  })
})
