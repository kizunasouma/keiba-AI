/**
 * Playwright によるスクリーンショット撮影 + 機能テスト
 * ユーザーガイド用の画像を自動生成し、各機能の動作を検証する
 *
 * 前提: localhost:5173（Vite）と localhost:8000（API）が起動していること
 * 実行: cd keiba-AI && node scripts/capture_screenshots.js
 */
const { chromium } = require('playwright')
const path = require('path')
const fs = require('fs')

const BASE_URL = 'http://localhost:5173'
const API_URL = 'http://localhost:8000'
const OUTPUT_DIR = path.join(__dirname, '..', 'frontend', 'public', 'guide', 'images')

let testResults = []

function log(msg) { console.log(`  ${msg}`) }
function pass(name) { testResults.push({ name, ok: true }); log(`[PASS] ${name}`) }
function fail(name, err) { testResults.push({ name, ok: false, err }); log(`[FAIL] ${name}: ${err}`) }

async function screenshot(page, filename, opts = {}) {
  const fp = path.join(OUTPUT_DIR, filename)
  await page.screenshot({ path: fp, fullPage: opts.fullPage || false })
  log(`  📸 ${filename}`)
}

async function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true })

  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({
    viewport: { width: 1400, height: 900 },
    locale: 'ja-JP',
  })
  const page = await context.newPage()

  console.log('\n=== スクリーンショット撮影 + 機能テスト ===\n')

  // -------------------------------------------------------
  // 1. ダッシュボード
  // -------------------------------------------------------
  console.log('[1] ダッシュボード')
  await page.goto(BASE_URL, { waitUntil: 'networkidle' })
  await page.waitForTimeout(3000)

  // セットアップウィザードが出ていないか確認
  const wizardText = await page.locator('text=セットアップ').count()
  if (wizardText > 0) {
    fail('セットアップウィザード', 'メイン画面の代わりにウィザードが表示されている')
  } else {
    pass('メイン画面表示')
  }

  await screenshot(page, '01_dashboard.png')
  await screenshot(page, '01_dashboard_full.png', { fullPage: true })

  // ナビゲーションタブの確認
  for (const tab of ['レース', 'AI予想', '統計DB', 'お気に入り', '検索']) {
    const btn = page.locator(`button:has-text("${tab}")`).first()
    if (await btn.count() > 0) {
      pass(`タブ「${tab}」存在`)
    } else {
      fail(`タブ「${tab}」存在`, '見つからない')
    }
  }

  // データ最新化ボタン確認
  const syncBtn = page.locator('button:has-text("データ最新化")')
  if (await syncBtn.count() > 0) {
    pass('データ最新化ボタン存在')
  } else {
    fail('データ最新化ボタン', '見つからない')
  }

  // -------------------------------------------------------
  // 2. レース詳細（フローティングウィンドウ）
  // -------------------------------------------------------
  console.log('\n[2] レース詳細')

  // レースカードをクリック（最初の重賞またはOPレースを探す）
  const raceCards = page.locator('[class*="cursor-pointer"][class*="rounded"]')
  const cardCount = await raceCards.count()
  log(`  レースカード: ${cardCount}枚`)

  if (cardCount > 0) {
    // 最初のカードをクリック
    await raceCards.first().click()
    await page.waitForTimeout(4000)
    pass('レース詳細を開く')

    await screenshot(page, '02_race_detail.png')

    // AI予測サマリーが表示されているか
    const aiPrediction = page.locator('text=AI PREDICTION')
    if (await aiPrediction.count() > 0) {
      pass('AI予測サマリー表示')
    } else {
      // 「モデル未学習」かもしれない
      const modelUntrained = page.locator('text=モデル未学習')
      if (await modelUntrained.count() > 0) {
        pass('AI予測（モデル未学習表示）')
      } else {
        fail('AI予測サマリー', '見つからない')
      }
    }

    // トラックバイアスカード
    const biasCard = page.locator('text=トラックバイアス')
    if (await biasCard.count() > 0) {
      pass('トラックバイアスカード表示')
      // バイアスカード部分をクローズアップ
      const biasEl = page.locator('text=トラックバイアス').locator('..')
      try {
        await biasEl.screenshot({ path: path.join(OUTPUT_DIR, '02b_track_bias_closeup.png') })
        log('  📸 02b_track_bias_closeup.png')
      } catch {}
    } else {
      fail('トラックバイアスカード', '見つからない')
    }

    // 出馬表の行を展開（最初の馬をクリック）
    const entryRows = page.locator('table tbody tr')
    if (await entryRows.count() > 0) {
      await entryRows.first().click()
      await page.waitForTimeout(1000)
      pass('出馬表の行展開')
      await screenshot(page, '02c_entry_expanded.png')
    }

    // ソートボタンのテスト
    const sortButtons = ['馬番順', 'オッズ順', '人気順']
    for (const label of sortButtons) {
      const btn = page.locator(`button:has-text("${label}")`)
      if (await btn.count() > 0) {
        await btn.click()
        await page.waitForTimeout(500)
        pass(`ソート「${label}」`)
      }
    }
    // 馬番順に戻す
    const numSort = page.locator('button:has-text("馬番順")')
    if (await numSort.count() > 0) await numSort.click()

    // AI詳細タブ
    const aiDetailTab = page.locator('button:has-text("AI詳細")')
    if (await aiDetailTab.count() > 0) {
      await aiDetailTab.click()
      await page.waitForTimeout(2000)
      pass('AI詳細タブ切替')
      await screenshot(page, '02d_ai_detail.png')
    }

    // 分析タブ
    const analysisTab = page.locator('button:has-text("分析")')
    if (await analysisTab.count() > 0) {
      await analysisTab.click()
      await page.waitForTimeout(2000)
      pass('分析タブ切替')
      await screenshot(page, '02e_analysis.png')
    }

    // 買い目タブ
    const bettingTab = page.locator('button:has-text("買い目")')
    if (await bettingTab.count() > 0) {
      await bettingTab.click()
      await page.waitForTimeout(1000)
      pass('買い目タブ切替')
      await screenshot(page, '02f_betting.png')
    }

    // 払戻タブ
    const payoutTab = page.locator('button:has-text("払戻")')
    if (await payoutTab.count() > 0) {
      await payoutTab.click()
      await page.waitForTimeout(1000)
      pass('払戻タブ切替')
      await screenshot(page, '02g_payout.png')
    }

    // 出馬表タブに戻す
    const tableTab = page.locator('button:has-text("出馬表")')
    if (await tableTab.count() > 0) {
      await tableTab.click()
      await page.waitForTimeout(1000)
    }
    await screenshot(page, '02h_entry_table.png')
  }

  // フローティングウィンドウを閉じる（後続テストで邪魔にならないよう）
  const closeAllBtn = page.locator('button[title*="全閉じ"]')
  if (await closeAllBtn.count() > 0) {
    await closeAllBtn.click()
    await page.waitForTimeout(500)
    log('  フローティングウィンドウを全閉じ')
  }

  // -------------------------------------------------------
  // 3. AI予想画面
  // -------------------------------------------------------
  console.log('\n[3] AI予想画面')
  const aiNavTab = page.locator('button:has-text("AI予想")').first()
  if (await aiNavTab.count() > 0) {
    await aiNavTab.click()
    await page.waitForTimeout(4000)
    pass('AI予想タブ遷移')
    await screenshot(page, '03_ai_prediction.png')
    await screenshot(page, '03_ai_prediction_full.png', { fullPage: true })

    // 期待値ランキングの存在確認
    const ranking = page.locator('text=期待値ランキング')
    if (await ranking.count() > 0) {
      pass('期待値ランキング表示')
    }

    // 推奨買い目の存在確認
    const bets = page.locator('text=推奨買い目')
    if (await bets.count() > 0) {
      pass('推奨買い目セクション表示')
    }

    // 馬券一覧の存在確認
    const ticketList = page.locator('text=推奨馬券')
    if (await ticketList.count() > 0) {
      pass('AI推奨馬券一覧表示')
    }
  }

  // -------------------------------------------------------
  // 4. 統計DB
  // -------------------------------------------------------
  console.log('\n[4] 統計DB')
  const statsNavTab = page.locator('button:has-text("統計DB")').first()
  if (await statsNavTab.count() > 0) {
    await statsNavTab.click()
    await page.waitForTimeout(3000)
    pass('統計DBタブ遷移')
    await screenshot(page, '04_stats_sire.png')

    // 母父タブ
    const bmsTab = page.locator('button:has-text("母父別")')
    if (await bmsTab.count() > 0) {
      await bmsTab.click({ force: true })
      await page.waitForTimeout(2000)
      pass('母父別タブ')
      await screenshot(page, '04b_stats_bms.png')
    }

    // 枠番タブ
    const frameTab = page.locator('button:has-text("枠番別")')
    if (await frameTab.count() > 0) {
      await frameTab.click({ force: true })
      await page.waitForTimeout(2000)
      pass('枠番別タブ')
      await screenshot(page, '04c_stats_frame.png')
    }

    // データマイニング
    const miningTab = page.locator('button:has-text("マイニング")')
    if (await miningTab.count() > 0) {
      await miningTab.click({ force: true })
      await page.waitForTimeout(1000)
      pass('データマイニングタブ')
      await screenshot(page, '04d_stats_mining.png')
    }
  }

  // -------------------------------------------------------
  // 5. お気に入り
  // -------------------------------------------------------
  console.log('\n[5] お気に入り')
  const favNavTab = page.locator('button:has-text("お気に入り")').first()
  if (await favNavTab.count() > 0) {
    await favNavTab.click()
    await page.waitForTimeout(2000)
    pass('お気に入りタブ遷移')
    await screenshot(page, '05_favorites.png')
  }

  // -------------------------------------------------------
  // 6. 検索
  // -------------------------------------------------------
  console.log('\n[6] 検索')
  const searchNavTab = page.locator('button:has-text("検索")').first()
  if (await searchNavTab.count() > 0) {
    await searchNavTab.click()
    await page.waitForTimeout(1000)
    pass('検索タブ遷移')

    // 検索実行
    const searchInput = page.locator('input[placeholder]').first()
    if (await searchInput.count() > 0) {
      await searchInput.fill('ドウデュース')
      await page.waitForTimeout(2000)
      pass('検索実行')
      await screenshot(page, '06_search_result.png')
    }
  }

  // -------------------------------------------------------
  // 7. 設定ダイアログ
  // -------------------------------------------------------
  console.log('\n[7] 設定')
  const settingsBtn = page.locator('button[title="設定"]')
  if (await settingsBtn.count() > 0) {
    await settingsBtn.click()
    await page.waitForTimeout(1000)
    pass('設定ダイアログ表示')
    await screenshot(page, '07_settings.png')

    // ESCで閉じる
    await page.keyboard.press('Escape')
    await page.waitForTimeout(500)
  }

  // -------------------------------------------------------
  // 8. ガイドボタン
  // -------------------------------------------------------
  console.log('\n[8] ガイドボタン')
  const guideBtn = page.locator('button[title="使い方ガイド"]')
  if (await guideBtn.count() > 0) {
    pass('ガイドボタン存在')
  } else {
    fail('ガイドボタン', '見つからない')
  }

  // -------------------------------------------------------
  // 9. ダークモード
  // -------------------------------------------------------
  console.log('\n[9] ダークモード')
  const darkToggle = page.locator('button[title*="モード"]')
  if (await darkToggle.count() > 0) {
    // レースタブに戻す
    const raceTab = page.locator('button:has-text("レース")').first()
    if (await raceTab.count() > 0) await raceTab.click()
    await page.waitForTimeout(2000)

    await darkToggle.click()
    await page.waitForTimeout(1000)
    pass('ダークモード切替')
    await screenshot(page, '09_dark_mode.png')

    // ライトモードに戻す
    await darkToggle.click()
    await page.waitForTimeout(500)
  }

  // -------------------------------------------------------
  // API テスト
  // -------------------------------------------------------
  console.log('\n[10] API直接テスト')
  const apiTests = [
    '/health',
    '/health/db',
    '/races?limit=3',
    '/stats/track_bias_detail?race_date=2026-05-10&venue_code=05',
    '/settings',
    '/settings/setup-status',
    '/tasks/db/summary',
  ]
  for (const endpoint of apiTests) {
    try {
      const res = await fetch(`${API_URL}${endpoint}`)
      if (res.ok) {
        pass(`API ${endpoint}`)
      } else {
        fail(`API ${endpoint}`, `status=${res.status}`)
      }
    } catch (e) {
      fail(`API ${endpoint}`, e.message)
    }
  }

  await browser.close()

  // -------------------------------------------------------
  // 結果サマリー
  // -------------------------------------------------------
  const files = fs.readdirSync(OUTPUT_DIR).filter(f => f.endsWith('.png'))
  const passed = testResults.filter(r => r.ok).length
  const failed = testResults.filter(r => !r.ok).length

  console.log(`\n${'='.repeat(50)}`)
  console.log(`📸 スクリーンショット: ${files.length}枚`)
  files.forEach(f => console.log(`   ${f}`))
  console.log(`\n✅ テスト結果: ${passed} passed, ${failed} failed / ${testResults.length} total`)
  if (failed > 0) {
    console.log('\n❌ 失敗した項目:')
    testResults.filter(r => !r.ok).forEach(r => console.log(`   ${r.name}: ${r.err}`))
  }
  console.log('='.repeat(50))
}

main().catch(err => {
  console.error('致命的エラー:', err)
  process.exit(1)
})
