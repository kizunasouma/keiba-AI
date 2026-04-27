/**
 * フロントエンド用モックデータ — DB・APIに依存せずUIを確認できる
 */

// --- 定数 ---
const VENUES = ['05', '09', '07'] // 東京、阪神、中京
const VENUE_NAMES: Record<string, string> = { '05': '東京', '09': '阪神', '07': '中京' }
const SIRES = ['ディープインパクト', 'キングカメハメハ', 'ロードカナロア', 'ハーツクライ', 'エピファネイア', 'ドゥラメンテ', 'キタサンブラック', 'モーリス']
const BMS = ['サンデーサイレンス', 'キングカメハメハ', 'フレンチデピュティ', 'スペシャルウィーク', 'クロフネ', 'ブライアンズタイム']
const MOTHERS = ['ジェンティルドンナ', 'ブエナビスタ', 'ウオッカ', 'アーモンドアイ', 'ソダシ', 'デアリングタクト']
const JOCKEYS = ['C.ルメール', '川田将雅', '武豊', '横山武史', '松山弘平', '戸崎圭太', 'M.デムーロ', '坂井瑠星', '岩田望来', '吉田隼人', '福永祐一', '浜中俊']
const TRAINERS = ['矢作芳人', '中内田充正', '国枝栄', '堀宣行', '友道康夫', '木村哲也', '藤原英昭', '手塚貴久']
const HORSE_NAMES = [
  'ドウデュース', 'イクイノックス', 'リバティアイランド', 'ソダシ', 'エフフォーリア',
  'タイトルホルダー', 'ジャックドール', 'スターズオンアース', 'パンサラッサ', 'ナミュール',
  'ダノンベルーガ', 'シャフリヤール', 'セリフォス', 'ジオグリフ', 'ガイアフォース',
  'レモンポップ', 'メイケイエール', 'ソングライン', 'ジャスティンパレス', 'ドゥレッツァ',
]
const STYLES = ['逃', '先', '差', '追']
const RACE_NAMES_G1 = ['天皇賞（秋）', '日本ダービー', 'ジャパンカップ', '有馬記念', '桜花賞', '安田記念']
const RACE_NAMES_G2 = ['毎日王冠', 'スプリングS', '京都記念', '中山記念', '阪神大賞典']
const RACE_NAMES_G3 = ['ラジオNIKKEI賞', '新潟記念', '函館記念', '七夕賞', '中京記念']

function pick<T>(arr: T[]): T { return arr[Math.floor(Math.random() * arr.length)] }
function rand(min: number, max: number) { return Math.floor(Math.random() * (max - min + 1)) + min }

// 日付ヘルパー
function toStr(d: Date) { return d.toISOString().slice(0, 10) }
function addDays(d: Date, n: number) { const r = new Date(d); r.setDate(d.getDate() + n); return r }
function getSaturdays(baseDate: Date, weeks: number): string[] {
  const dates: string[] = []
  const day = baseDate.getDay()
  const lastSat = addDays(baseDate, -(day === 0 ? 1 : day === 6 ? 0 : day + 1))
  for (let w = -weeks; w <= 1; w++) {
    const sat = addDays(lastSat, w * 7)
    const sun = addDays(sat, 1)
    dates.push(toStr(sat), toStr(sun))
  }
  return [...new Set(dates)].sort()
}

// --- モックレース生成 ---
function generateRaces(): any[] {
  const today = new Date()
  const raceDates = getSaturdays(today, 4)
  const races: any[] = []

  for (const rd of raceDates) {
    for (const vc of VENUES) {
      for (let rn = 1; rn <= 12; rn++) {
        const grade = rn === 11 ? pick([1, 2, 3, 5]) : rn === 12 ? pick([5, 6, 7, 8]) : pick([8, 9, 9, 10, 10, 10])
        const trackType = pick([1, 1, 1, 2, 2])
        const distance = trackType === 1 ? pick([1200, 1400, 1600, 1800, 2000, 2200, 2400]) : pick([1200, 1400, 1700, 1800, 2100])
        let raceName: string | null = null
        if (grade === 1) raceName = pick(RACE_NAMES_G1)
        else if (grade === 2) raceName = pick(RACE_NAMES_G2)
        else if (grade === 3) raceName = pick(RACE_NAMES_G3)
        else if (grade <= 5) raceName = `${VENUE_NAMES[vc]}特別`

        // 発走時刻をレース番号に応じて生成（10:00〜16:30）
        const startHour = 10 + Math.floor(rn / 2)
        const startMin = rn % 2 === 0 ? '00' : '30'
        const startTime = `${startHour}:${startMin}`

        races.push({
          id: races.length + 1,
          race_key: `${rd.replace(/-/g, '')}${vc}010${String(rn).padStart(2, '0')}`,
          race_date: rd,
          venue_code: vc,
          kai: 1, nichi: 1,
          race_num: rn,
          race_name: raceName,
          start_time: startTime,
          grade,
          distance,
          track_type: trackType,
          track_dir: pick([1, 2]),
          horse_count: rand(8, 18),
          weather: pick([1, 1, 1, 2, 3]),
          track_cond: pick([1, 1, 1, 2, 3]),
          is_handicap: Math.random() < 0.12,
          is_female_only: Math.random() < 0.08,
          is_special: grade <= 5,
          prize_1st: grade === 1 ? 200000 : grade === 2 ? 100000 : grade === 3 ? 70000 : rand(5000, 20000),
        })
      }
    }
  }
  return races
}

// --- モックエントリー生成 ---
function generateEntries(race: any): any[] {
  const n = race.horse_count || 14
  const isPast = new Date(race.race_date) < new Date()
  const finishOrders = Array.from({ length: n }, (_, i) => i + 1).sort(() => Math.random() - 0.5)

  return Array.from({ length: n }, (_, i) => {
    const fo = isPast ? finishOrders[i] : null
    const odds = Math.round((1.5 + Math.random() * 50) * 10) / 10
    return {
      horse_num: i + 1,
      frame_num: Math.min(Math.floor(i / 2) + 1, 8),
      horse_name: HORSE_NAMES[i % HORSE_NAMES.length],
      horse_name_eng: null,
      horse_id: 100 + i,
      jockey_name: JOCKEYS[i % JOCKEYS.length],
      jockey_id: 200 + (i % JOCKEYS.length),
      trainer_name: TRAINERS[i % TRAINERS.length],
      trainer_id: 300 + (i % TRAINERS.length),
      age: rand(2, 7),
      sex: pick([1, 1, 1, 2, 2, 3]),
      weight_carry: pick([54, 55, 56, 57, 58]),
      horse_weight: rand(420, 540),
      weight_diff: pick([-6, -4, -2, 0, 0, 2, 4, 6]),
      odds_win: odds,
      odds_place_min: Math.round(odds * 0.4 * 10) / 10,
      odds_place_max: Math.round(odds * 0.7 * 10) / 10,
      popularity: i + 1,
      finish_order: fo,
      finish_time: fo ? 900 + fo * rand(1, 4) + rand(0, 50) : null,
      last_3f: fo ? 330 + fo * rand(1, 3) + rand(0, 10) : null,
      margin: fo && fo > 1 ? pick(['ハナ', 'アタマ', 'クビ', '1/2', '1', '2']) : null,
      corner_text: isPast ? `${rand(1, n)}-${rand(1, n)}-${rand(1, n)}-${rand(1, n)}` : null,
      speed_index: null,
      abnormal_code: Math.random() < 0.05 ? pick([1, 2]) : 0,
      margin_text: isPast && fo != null && fo > 1 ? pick(['ハナ', 'アタマ', 'クビ', '1/2', '1', '1.1/2', '2', '3']) : null,
      father: pick(SIRES),
      mother_father: pick(BMS),
      mother_name: pick(MOTHERS),
      running_style: pick(STYLES),
      jockey_change: Math.random() < 0.2,
      is_foreign_jockey: Math.random() < 0.1,
      interval_days: rand(14, 90),
      total_wins: rand(0, 10),
      total_races: rand(5, 40),
      total_record: `${rand(0, 10)}-${rand(5, 30)}`,
      total_earnings: rand(500, 50000),
      past_races: Array.from({ length: 5 }, (_, j) => ({
        race_date: toStr(addDays(new Date(race.race_date), -(j + 1) * rand(14, 42))),
        race_name: pick([null, '特別', '未勝利', 'OP']),
        venue: pick(['東京', '中山', '阪神', '京都', '新潟']),
        distance: pick([1200, 1600, 1800, 2000]),
        track: pick(['芝', 'ダ']),
        cond: pick(['良', '稍', '重']),
        horse_count: rand(8, 18),
        grade: pick([null, 5, 8, 9, 10]),
        horse_num: rand(1, 18),
        popularity: rand(1, 18),
        finish_order: rand(1, 18),
        finish_time: 900 + rand(0, 100),
        last_3f: 330 + rand(0, 30),
        weight_carry: pick([54, 55, 56, 57, 58]),
        horse_weight: rand(420, 540),
        weight_diff: pick([-4, -2, 0, 2, 4]),
        odds_win: Math.round((2 + Math.random() * 30) * 10) / 10,
        margin: pick([null, 'ハナ', 'クビ', '1/2', '1']),
        corner_text: `${rand(1, 18)}-${rand(1, 18)}-${rand(1, 18)}-${rand(1, 18)}`,
        speed_index: null,
        jockey_name: pick(JOCKEYS),
        running_style: pick(STYLES),
      })),
      training: Math.random() < 0.6 ? [
        { training_date: toStr(addDays(new Date(race.race_date), -7)), weeks_before: 1, course_type: pick(['坂路', 'W']), distance: pick([800, 1000]), lap_time: rand(480, 560), last_3f: rand(350, 400), last_1f: null, rank: pick(['A', 'B', 'B', 'C']), note: null },
        { training_date: toStr(addDays(new Date(race.race_date), -14)), weeks_before: 2, course_type: pick(['坂路', 'W']), distance: pick([800, 1000]), lap_time: rand(480, 560), last_3f: rand(350, 400), last_1f: null, rank: pick(['A', 'B', 'C']), note: null },
      ] : [],
    }
  })
}

// --- モック予測生成 ---
function generatePredictions(raceKey: string, entries: any[]): any {
  const preds = entries.map((e: any) => {
    const prob = Math.random() * 0.25
    const ev = prob * (e.odds_win || 5) - 1
    return {
      entry_id: e.horse_num,
      horse_num: e.horse_num,
      horse_name: e.horse_name,
      jockey_name: e.jockey_name,
      odds_win: e.odds_win,
      win_prob: Math.round(prob * 10000) / 10000,
      expected_value: Math.round(ev * 10000) / 10000,
      win_prob_no_odds: Math.round(prob * 0.9 * 10000) / 10000,
      ev_no_odds: Math.round((prob * 0.9 * (e.odds_win || 5) - 1) * 10000) / 10000,
      recommendation: ev > 0.2 ? '◎ 強推奨' : ev > 0 ? '○ 推奨' : '△ 様子見',
    }
  }).sort((a: any, b: any) => b.expected_value - a.expected_value)

  return {
    race_key: raceKey,
    model_available: true,
    model_type: 'ensemble',
    predictions: preds,
    message: null,
  }
}

// --- キャッシュ ---
let _races: any[] | null = null
function getRaces() {
  if (!_races) _races = generateRaces()
  return _races
}

// --- エクスポート: モックAPI関数 ---

export function mockFetchRaces(params: any) {
  let races = getRaces()
  if (params.date_from) races = races.filter((r: any) => r.race_date >= params.date_from)
  if (params.date_to) races = races.filter((r: any) => r.race_date <= params.date_to)
  if (params.race_date) races = races.filter((r: any) => r.race_date === params.race_date)
  if (params.venue_code) races = races.filter((r: any) => params.venue_code.split(',').includes(r.venue_code))
  if (params.race_name) races = races.filter((r: any) => r.race_name?.includes(params.race_name))
  return races.slice(0, params.limit || 500)
}

export function mockFetchRace(raceKey: string) {
  return getRaces().find((r: any) => r.race_key === raceKey) || null
}

const _entriesCache = new Map<string, any[]>()
export function mockFetchEntries(raceKey: string) {
  if (!_entriesCache.has(raceKey)) {
    const race = mockFetchRace(raceKey)
    if (!race) return []
    _entriesCache.set(raceKey, generateEntries(race))
  }
  return _entriesCache.get(raceKey)!
}

export function mockFetchPredictions(raceKey: string) {
  const entries = mockFetchEntries(raceKey)
  return generatePredictions(raceKey, entries)
}

export function mockFetchLaps(raceKey: string) {
  const race = mockFetchRace(raceKey)
  if (!race) return { race_key: raceKey, distance: 0, laps: [], pace_analysis: null }
  const n = Math.floor(race.distance / 200)
  const laps = Array.from({ length: n }, (_, i) => ({ order: i + 1, time: 115 + rand(-8, 8) }))
  const first3 = laps.slice(0, 3).reduce((s, l) => s + l.time, 0)
  const last3 = laps.slice(-3).reduce((s, l) => s + l.time, 0)
  const pci = Math.round(first3 / last3 * 1000) / 10
  return {
    race_key: raceKey,
    distance: race.distance,
    laps,
    pace_analysis: { first_3f: first3, last_3f: last3, pci, pace_label: pci >= 105 ? 'H' : pci <= 95 ? 'S' : 'M' },
  }
}

export function mockFetchPayouts(raceKey: string) {
  return {
    race_key: raceKey,
    payouts: {
      '単勝': [{ combination: String(rand(1, 18)), payout: rand(200, 5000), popularity: 1 }],
      '複勝': [
        { combination: String(rand(1, 18)), payout: rand(100, 1500), popularity: 1 },
        { combination: String(rand(1, 18)), payout: rand(100, 2000), popularity: 2 },
      ],
      '馬連': [{ combination: `${rand(1, 9)}-${rand(10, 18)}`, payout: rand(500, 20000), popularity: 1 }],
      '三連単': [{ combination: `${rand(1, 6)}-${rand(7, 12)}-${rand(13, 18)}`, payout: rand(5000, 300000), popularity: 1 }],
    },
  }
}

export function mockFetchHorse(horseId: number) {
  const idx = (horseId - 100) % HORSE_NAMES.length
  return {
    id: horseId,
    blood_reg_num: `2020${String(idx).padStart(5, '0')}0`,
    name: HORSE_NAMES[idx] || `馬${horseId}`,
    name_eng: null,
    birth_date: '2020-03-15',
    sex: pick([1, 2]),
    coat_color: 1,
    producer: pick(['ノーザンファーム', '社台ファーム', '追分ファーム']),
    area: pick(['安平町', '千歳市']),
    owner: pick(['サンデーレーシング', 'キャロットファーム', 'シルクレーシング']),
    total_wins: rand(1, 10),
    total_races: rand(5, 30),
    total_earnings: rand(1000, 80000),
    pedigree: {
      father: pick(SIRES), mother: pick(MOTHERS), mother_father: pick(BMS),
      father_code: null, mother_code: null, mother_father_code: null,
    },
  }
}

export function mockFetchHorseResults(horseId: number) {
  return Array.from({ length: rand(5, 15) }, (_, i) => ({
    race_key: `2026${String(rand(1, 12)).padStart(2, '0')}${String(rand(1, 28)).padStart(2, '0')}050101${String(rand(1, 12)).padStart(2, '0')}`,
    race_date: `2026-${String(rand(1, 12)).padStart(2, '0')}-${String(rand(1, 28)).padStart(2, '0')}`,
    race_name: pick([null, '特別', '未勝利', 'OP', '天皇賞']),
    venue: pick(['東京', '中山', '阪神', '京都']),
    distance: pick([1200, 1600, 1800, 2000, 2400]),
    track: pick(['芝', 'ダ']),
    cond: pick(['良', '稍', '重']),
    grade: pick([null, 1, 2, 5, 8, 10]),
    horse_count: rand(8, 18),
    horse_num: rand(1, 18), frame_num: rand(1, 8),
    finish_order: rand(1, 18),
    finish_time: 900 + rand(0, 100),
    last_3f: 330 + rand(0, 30),
    weight_carry: pick([54, 55, 56, 57, 58]),
    horse_weight: rand(420, 540), weight_diff: pick([-4, -2, 0, 2, 4]),
    odds_win: Math.round((2 + Math.random() * 30) * 10) / 10,
    popularity: rand(1, 18), speed_index: null,
    corner_text: `${rand(1, 18)}-${rand(1, 18)}-${rand(1, 18)}-${rand(1, 18)}`,
    jockey_name: pick(JOCKEYS), abnormal_code: null,
  }))
}

export function mockFetchHorseStats(horseId: number) {
  const mkRow = (label: string) => ({ label, runs: rand(3, 20), wins: rand(0, 5), top3: rand(1, 8) })
  return {
    by_track: [mkRow('芝'), mkRow('ダ')],
    by_distance: [mkRow('〜1400m'), mkRow('1401-1800m'), mkRow('1801-2200m'), mkRow('2201m〜')],
    by_condition: [mkRow('良'), mkRow('稍'), mkRow('重')],
    by_venue: [mkRow('東京'), mkRow('中山'), mkRow('阪神'), mkRow('京都')],
  }
}

export function mockFetchHorseWeightHistory(horseId: number) {
  return Array.from({ length: 10 }, (_, i) => ({
    race_date: `2025-${String(i + 1).padStart(2, '0')}-15`,
    weight: 470 + rand(-20, 20),
    diff: pick([-4, -2, 0, 2, 4]),
    finish_order: rand(1, 18),
  }))
}

export function mockFetchJockey(jockeyId: number) {
  const idx = (jockeyId - 200) % JOCKEYS.length
  const total = rand(500, 5000)
  const w = rand(50, 800)
  const p = rand(50, 600)
  const s = rand(50, 500)
  return {
    id: jockeyId, jockey_code: String(10000 + idx), name: JOCKEYS[idx], name_kana: '', birth_date: '1985-03-01',
    belong: pick(['美浦', '栗東', '外国']),
    total_1st: w, total_2nd: p, total_3rd: s, total_races: total,
    win_rate: Math.round(w / total * 1000) / 10,
    top3_rate: Math.round((w + p + s) / total * 1000) / 10,
  }
}

export function mockFetchJockeyStats(jockeyId: number) {
  const mk = (label: string) => ({ label, runs: rand(10, 200), wins: rand(1, 40), top3: rand(3, 80) })
  return {
    by_track: [mk('芝'), mk('ダ')],
    by_distance: [mk('〜1400m'), mk('1401-1800m'), mk('1801-2200m')],
    by_venue: [mk('東京'), mk('中山'), mk('阪神'), mk('京都')],
    by_grade: [mk('G1'), mk('G2'), mk('G3'), mk('OP'), mk('条件戦')],
  }
}

export function mockFetchJockeyRecent(jockeyId: number) {
  return Array.from({ length: 20 }, (_, i) => ({
    date: toStr(addDays(new Date(), -i * rand(1, 5))),
    runs: rand(1, 8), wins: rand(0, 3), top3: rand(0, 5),
  }))
}

export function mockFetchJockeyCombo(jockeyId: number) {
  return TRAINERS.slice(0, 5).map((t, i) => ({
    trainer_name: t, trainer_id: 300 + i,
    runs: rand(10, 100), wins: rand(1, 20), top3: rand(3, 40),
  }))
}

export function mockFetchTrainer(trainerId: number) {
  const idx = (trainerId - 300) % TRAINERS.length
  const total = rand(500, 5000)
  const w = rand(50, 500)
  return {
    id: trainerId, trainer_code: String(20000 + idx), name: TRAINERS[idx], name_kana: '',
    belong: pick(['美浦', '栗東']),
    total_1st: w, total_races: total,
    win_rate: Math.round(w / total * 1000) / 10,
  }
}

export function mockFetchTrainerStats(trainerId: number) {
  const mk = (label: string) => ({ label, runs: rand(10, 200), wins: rand(1, 40), top3: rand(3, 80) })
  return { by_track: [mk('芝'), mk('ダ')], by_distance: [mk('〜1400m'), mk('1401-1800m')], by_venue: [mk('東京'), mk('阪神')] }
}

export function mockFetchTrainerRecent(trainerId: number) {
  return Array.from({ length: 15 }, (_, i) => ({
    date: toStr(addDays(new Date(), -i * rand(1, 5))),
    runs: rand(1, 6), wins: rand(0, 2), top3: rand(0, 4),
  }))
}

export function mockFetchHealth() { return { status: 'ok', database: 'mock' } }

// --- 統合検索モック ---
export function mockSearchHorses(q: string) {
  return HORSE_NAMES
    .filter(n => n.includes(q) || q === '')
    .map((n, i) => ({
      id: 100 + i, name: n, name_eng: null, sex: pick([1, 2]),
      father: pick(SIRES), total_wins: rand(0, 10), total_races: rand(5, 30),
      total_earnings: rand(500, 50000),
    }))
}

export function mockSearchJockeys(q: string) {
  return JOCKEYS.filter(n => n.includes(q) || q === '').map((n, i) => ({
    id: 200 + i, name: n, name_kana: '', belong: pick(['美浦', '栗東', '外国']),
    total_1st: rand(50, 800), total_races: rand(500, 5000),
    win_rate: Math.round(Math.random() * 15 * 10) / 10,
  }))
}

export function mockSearchTrainers(q: string) {
  return TRAINERS.map(([n]) => n).filter(n => n.includes(q) || q === '').map((n, i) => ({
    id: 300 + i, name: n, name_kana: '', belong: pick(['美浦', '栗東']),
    total_1st: rand(50, 500), total_races: rand(500, 5000),
    win_rate: Math.round(Math.random() * 12 * 10) / 10,
  }))
}

export function mockSearchRaces(q: string) {
  const names = ['天皇賞（秋）', '日本ダービー', 'ジャパンカップ', '有馬記念', '桜花賞', '安田記念', 'スプリングS', '毎日王冠', '函館記念']
  return names.filter(n => n.includes(q) || q === '').map((n, i) => ({
    id: i + 1, race_key: '2026041205010' + String(i + 1).padStart(2, '0'),
    race_date: '2026-04-12', venue_code: '05', race_num: 11, race_name: n,
    grade: pick([1, 2, 3]), distance: pick([1600, 2000, 2400]),
    track_type: 1, horse_count: rand(10, 18),
  }))
}

// --- 回収率バックテストモック ---
export function mockBacktestSummary() {
  const daily = Array.from({ length: 20 }, (_, i) => {
    const bets = rand(2, 8)
    const hits = rand(0, Math.min(3, bets))
    const invest = bets * 100
    const ret = hits * rand(200, 1500)
    return {
      date: toStr(addDays(new Date(), -(20 - i) * rand(1, 4))),
      invest, ret, bets, hits,
    }
  })
  const totalInvest = daily.reduce((s, d) => s + d.invest, 0)
  const totalReturn = daily.reduce((s, d) => s + d.ret, 0)
  const totalBets = daily.reduce((s, d) => s + d.bets, 0)
  const totalHits = daily.reduce((s, d) => s + d.hits, 0)
  return {
    days: 30, ev_threshold: 0,
    total_races: rand(100, 300), total_bets: totalBets,
    total_invest: totalInvest, total_return: totalReturn,
    roi: Math.round(totalReturn / totalInvest * 1000) / 10,
    hit_rate: Math.round(totalHits / totalBets * 1000) / 10,
    daily,
  }
}

// --- お気に入りモック ---
let _mockFavorites: { horse_id: number; horse_name: string | null; note: string | null }[] = [
  { horse_id: 100, horse_name: 'ドウデュース', note: '注目' },
  { horse_id: 101, horse_name: 'イクイノックス', note: null },
]

export function mockGetFavorites() { return [..._mockFavorites] }
export function mockAddFavorite(data: { horse_id: number; horse_name?: string; note?: string }) {
  if (!_mockFavorites.find(f => f.horse_id === data.horse_id)) {
    _mockFavorites.push({ horse_id: data.horse_id, horse_name: data.horse_name ?? null, note: data.note ?? null })
  }
  return { message: '追加しました', favorites: [..._mockFavorites] }
}
export function mockRemoveFavorite(horseId: number) {
  _mockFavorites = _mockFavorites.filter(f => f.horse_id !== horseId)
  return { message: '削除しました', favorites: [..._mockFavorites] }
}
export function mockFetchUpcoming() {
  return _mockFavorites.slice(0, 3).map((f, i) => ({
    horse_id: f.horse_id, horse_name: f.horse_name,
    race_key: `20260412050101${String(i + 5).padStart(2, '0')}`,
    race_date: toStr(addDays(new Date(), rand(0, 3))),
    race_name: pick(['天皇賞', '特別', null]),
    venue: pick(['東京', '阪神']), distance: pick([1600, 2000]), track: '芝', race_num: rand(1, 12),
  }))
}

// --- 統計モック ---
export function mockFetchSireStats() {
  return SIRES.map(s => ({
    sire: s, runs: rand(50, 500), wins: rand(5, 80), top2: rand(10, 120), top3: rand(15, 160),
    win_rate: Math.round(Math.random() * 20 * 10) / 10,
  })).sort((a, b) => b.win_rate - a.win_rate)
}

export function mockFetchBmsStats() {
  return BMS.map(b => ({
    bms: b, runs: rand(30, 300), wins: rand(3, 50), top3: rand(8, 100),
    win_rate: Math.round(Math.random() * 18 * 10) / 10,
  })).sort((a, b) => b.win_rate - a.win_rate)
}

export function mockFetchFrameStats() {
  return [1,2,3,4,5,6,7,8].map(f => ({
    frame: f, runs: rand(200, 800), wins: rand(20, 100), top3: rand(60, 250),
    win_rate: Math.round((8 + Math.random() * 8) * 10) / 10,
  }))
}

export function mockFetchPopularityStats() {
  return Array.from({ length: 18 }, (_, i) => {
    const pop = i + 1
    const runs = rand(200, 1000)
    const winRate = Math.max(0, 35 - pop * 2.5 + Math.random() * 3)
    const wins = Math.round(runs * winRate / 100)
    const top3 = Math.round(runs * Math.min(90, winRate * 2.5) / 100)
    return {
      popularity: pop, runs, wins, top3,
      win_rate: Math.round(winRate * 10) / 10,
      avg_odds: Math.round((1.5 + pop * 2.5 + Math.random() * 5) * 10) / 10,
    }
  })
}

export function mockFetchMiningStats() {
  const total = rand(500, 5000)
  const wins = rand(50, Math.floor(total * 0.2))
  const top2 = wins + rand(30, 100)
  const top3 = top2 + rand(30, 100)
  return {
    total_runs: total, wins, top2, top3,
    win_rate: Math.round(wins / total * 1000) / 10,
    top2_rate: Math.round(top2 / total * 1000) / 10,
    top3_rate: Math.round(top3 / total * 1000) / 10,
    avg_odds: Math.round((5 + Math.random() * 20) * 10) / 10,
    avg_finish: Math.round((5 + Math.random() * 5) * 10) / 10,
  }
}
