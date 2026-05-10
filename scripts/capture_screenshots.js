/**
 * Playwright による自動スクリーンショット撮影スクリプト
 * ユーザーガイド用の画像を自動生成する
 *
 * 前提: localhost:5173（Vite dev server）と localhost:8000（API）が起動していること
 * 実行: npx playwright test scripts/capture_screenshots.js --headed
 *   または: node scripts/capture_screenshots.js
 */
const { chromium } = require('playwright')
const path = require('path')
const fs = require('fs')

const BASE_URL = 'http://localhost:5173'
const OUTPUT_DIR = path.join(__dirname, '..', 'frontend', 'public', 'guide', 'images')

async function main() {
  // 出力ディレクトリ作成
  fs.mkdirSync(OUTPUT_DIR, { recursive: true })

  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({
    viewport: { width: 1400, height: 900 },
    locale: 'ja-JP',
  })
  const page = await context.newPage()

  console.log('スクリーンショット撮影開始...')

  // 1. ダッシュボード
  console.log('  [1/7] ダッシュボード')
  await page.goto(BASE_URL, { waitUntil: 'networkidle' })
  await page.waitForTimeout(2000)
  await page.screenshot({ path: path.join(OUTPUT_DIR, '01_dashboard.png'), fullPage: false })

  // 2. レース詳細を開く（最初のレースカードをクリック）
  console.log('  [2/7] レース詳細（出馬表）')
  const raceCard = page.locator('[class*="cursor-pointer"]').first()
  if (await raceCard.count() > 0) {
    await raceCard.click()
    await page.waitForTimeout(3000)
    await page.screenshot({ path: path.join(OUTPUT_DIR, '02_race_detail.png'), fullPage: false })
  }

  // 3. AI予測サマリー + トラックバイアス（レース詳細の上部）
  console.log('  [3/7] AI予測サマリー + バイアス')
  await page.screenshot({ path: path.join(OUTPUT_DIR, '03_ai_summary_bias.png'), fullPage: false })

  // 4. AI予想タブ
  console.log('  [4/7] AI予想画面')
  await page.goto(BASE_URL, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1000)
  // AI予想タブをクリック
  const aiTab = page.locator('button:has-text("AI予想")')
  if (await aiTab.count() > 0) {
    await aiTab.click()
    await page.waitForTimeout(3000)
    await page.screenshot({ path: path.join(OUTPUT_DIR, '04_ai_prediction.png'), fullPage: false })
  }

  // 5. 統計DB
  console.log('  [5/7] 統計DB')
  const statsTab = page.locator('button:has-text("統計DB")')
  if (await statsTab.count() > 0) {
    await statsTab.click()
    await page.waitForTimeout(2000)
    await page.screenshot({ path: path.join(OUTPUT_DIR, '05_stats.png'), fullPage: false })
  }

  // 6. 検索
  console.log('  [6/7] 検索')
  const searchTab = page.locator('button:has-text("検索")')
  if (await searchTab.count() > 0) {
    await searchTab.click()
    await page.waitForTimeout(1000)
    await page.screenshot({ path: path.join(OUTPUT_DIR, '06_search.png'), fullPage: false })
  }

  // 7. お気に入り
  console.log('  [7/7] お気に入り')
  const favTab = page.locator('button:has-text("お気に入り")')
  if (await favTab.count() > 0) {
    await favTab.click()
    await page.waitForTimeout(1000)
    await page.screenshot({ path: path.join(OUTPUT_DIR, '07_favorites.png'), fullPage: false })
  }

  await browser.close()

  // 撮影結果を表示
  const files = fs.readdirSync(OUTPUT_DIR).filter(f => f.endsWith('.png'))
  console.log(`\n撮影完了: ${files.length}枚`)
  files.forEach(f => console.log(`  ${f}`))
}

main().catch(err => {
  console.error('エラー:', err)
  process.exit(1)
})
