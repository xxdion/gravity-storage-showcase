const APP_VERSION = 'browser-demo-0.1.0'
const LABELS = Array.from({ length: 24 }, (_, hour) => `${String(hour).padStart(2, '0')}:00`)
const QUARTER_LABELS = Array.from({ length: 16 }, (_, idx) => `${String(8 + Math.floor(idx / 4)).padStart(2, '0')}:${String((idx % 4) * 15).padStart(2, '0')}`)

const DEFAULT_SCENARIO = {
  application: '风光峰谷蓄调',
  season: '夏季',
  building: '园区综合能源站',
  layers: 35,
  columns: 33,
  blockMass: 25,
  efficiency: 0.85,
  maxPower: 25.92,
  initialSoc: 62
}

const DEFAULT_PLANNING = {
  capacityBoundary: 100,
  switchLimit: 7,
  rollingCycle: 15,
  seasonReserve: 18
}

const DEFAULT_OPTIMIZATION = {
  soc: 62,
  revenueWeight: 0.45,
  peakWeight: 0.35,
  switchWeight: 0.2,
  popSize: 80,
  generations: 120
}

const DEFAULT_CONTROL = {
  model: 'TCN-VAE + 改进 NSGA-II',
  horizon: '未来 4 小时',
  deviation: 8.4,
  mode: '人工确认'
}

function clamp(value, minValue, maxValue) {
  return Math.max(minValue, Math.min(maxValue, value))
}

function roundTo(value, digits = 2) {
  return Number(Number(value).toFixed(digits))
}

function merge(defaults, values) {
  return { ...defaults, ...(values ?? {}) }
}

function wave(index, phase, amp = 1) {
  return Math.sin(((index + phase) / 24) * Math.PI * 2) * amp + Math.sin(((index + phase) / 24) * Math.PI * 6) * amp * 0.2
}

function seasonFactor(season) {
  return { 春季: 0.94, 夏季: 1.12, 秋季: 0.98, 冬季: 1.08 }[season] ?? 1
}

function buildingFactor(building) {
  return { 办公建筑: 0.92, 酒店建筑: 1.02, 园区综合能源站: 1.12 }[building] ?? 1
}

function simulateScenario(scenarioValues) {
  const scenario = merge(DEFAULT_SCENARIO, scenarioValues)
  const sf = seasonFactor(String(scenario.season))
  const bf = buildingFactor(String(scenario.building))
  const application = String(scenario.application)
  const season = String(scenario.season)

  const rows = LABELS.map((time, idx) => {
    const officePeak = idx >= 8 && idx <= 19 ? 13 : -5
    const load = 78 * sf * bf + wave(idx, -7, 17) + officePeak
    const wind = 22 + wave(idx, 5, 9) + (application.includes('风') ? 4 : 0)
    const daylight = Math.max(0, Math.sin(((idx - 6) / 13) * Math.PI))
    const solar = daylight * (season === '夏季' ? 43 : 33)
    const price = [0, 1, 2, 3, 4, 5, 6, 23].includes(idx) ? 0.34 : [8, 9, 10, 11, 17, 18, 19, 20].includes(idx) ? 0.98 : 0.59
    return {
      time,
      load: roundTo(load),
      wind: roundTo(wind),
      solar: roundTo(solar),
      price: roundTo(price),
      netLoad: roundTo(load - wind - solar)
    }
  })

  const netValues = rows.map((row) => row.netLoad)
  const capacity = Number(scenario.layers) * Number(scenario.columns) * 48 * Number(scenario.blockMass) * 9.8 * 4 * Number(scenario.efficiency) / 3600
  const peakHour = rows.reduce((best, row) => row.netLoad > best.netLoad ? row : best, rows[0])
  const valleyHour = rows.reduce((best, row) => row.netLoad < best.netLoad ? row : best, rows[0])

  const stats = {
    capacity: roundTo(capacity, 1),
    soc: Number(scenario.initialSoc),
    peakValley: roundTo(Math.max(...netValues) - Math.min(...netValues)),
    power: Number(scenario.maxPower),
    maxNet: roundTo(Math.max(...netValues)),
    minNet: roundTo(Math.min(...netValues)),
    avgNet: roundTo(netValues.reduce((sum, value) => sum + value, 0) / netValues.length)
  }

  return {
    scenario,
    series: rows,
    stats,
    summary: {
      peakHour,
      valleyHour,
      highPriceHours: rows.filter((row) => row.price >= 0.98).length,
      renewableTotal: roundTo(rows.reduce((sum, row) => sum + row.wind + row.solar, 0), 1)
    }
  }
}

function buildSolutions(stats, scenario, selectedId = 2) {
  const pv = Number(stats.peakValley)
  const maxPower = Number(scenario.maxPower)
  const baseRevenue = 6.8 + maxPower * 0.12 + (scenario.season === '夏季' ? 0.9 : 0.45)
  const candidates = [
    { id: 1, revenue: baseRevenue + 0.15, peakValley: pv * 0.72, switchCount: 4, score: 82 },
    { id: 2, revenue: baseRevenue + 0.92, peakValley: pv * 0.58, switchCount: 6, score: 92 },
    { id: 3, revenue: baseRevenue + 1.36, peakValley: pv * 0.66, switchCount: 8, score: 88 },
    { id: 4, revenue: baseRevenue + 0.48, peakValley: pv * 0.52, switchCount: 7, score: 90 },
    { id: 5, revenue: baseRevenue + 0.70, peakValley: pv * 0.55, switchCount: 5, score: 91 }
  ]
  return candidates.map((item) => ({
    ...item,
    revenue: roundTo(item.revenue),
    peakValley: roundTo(item.peakValley, 1),
    selected: item.id === selectedId
  }))
}

function runOptimization(payload = {}) {
  const scenarioResult = simulateScenario(payload.scenario)
  const scenario = scenarioResult.scenario
  const stats = scenarioResult.stats
  const series = scenarioResult.series
  const optimization = merge(DEFAULT_OPTIMIZATION, payload.optimization)
  const selectedId = Number(payload.selectedSolutionId || 2)
  const solutions = buildSolutions(stats, scenario, selectedId)
  const selectedSolution = solutions.find((item) => item.id === selectedId) ?? solutions[1]

  const highLine = stats.avgNet + stats.peakValley * 0.18
  const lowLine = stats.avgNet - stats.peakValley * 0.16
  const maxPower = Number(scenario.maxPower) * (0.72 + selectedSolution.score / 420)
  let soc = Number(optimization.soc)

  const dispatchRows = series.map((row, idx) => {
    const before = row.netLoad
    const price = row.price
    const dischargeNeed = Math.max(0, before - highLine) * (price > 0.58 ? 0.82 : 0.35)
    const chargeNeed = Math.max(0, lowLine - before) * (price < 0.6 ? 0.78 : 0.25)
    const scheduledBoost = idx >= 17 && idx <= 20 ? 5.2 : idx <= 6 || idx >= 22 ? -4.8 : 0
    const power = roundTo(clamp(dischargeNeed - chargeNeed + scheduledBoost, -maxPower, maxPower))
    soc = clamp(soc - power * 0.31, 12, 88)
    const netLoadAfter = roundTo(before - power * 0.72)
    return {
      time: row.time,
      action: power > 1 ? '放电' : power < -1 ? '充电' : '待机',
      power,
      soc: roundTo(soc, 1),
      netLoadBefore: before,
      netLoadAfter,
      price,
      revenue: roundTo(power > 0 ? power * price * 0.1 : -Math.abs(power) * price * 0.05)
    }
  })

  const beforeValues = dispatchRows.map((row) => row.netLoadBefore)
  const afterValues = dispatchRows.map((row) => row.netLoadAfter)
  const switches = dispatchRows.reduce((count, row, idx) => idx > 0 && row.action !== dispatchRows[idx - 1].action ? count + 1 : count, 0)

  return {
    optimization,
    solutions,
    selectedSolution,
    dispatchRows,
    optimizedStats: {
      beforePeakValley: roundTo(Math.max(...beforeValues) - Math.min(...beforeValues), 1),
      afterPeakValley: roundTo(Math.max(...afterValues) - Math.min(...afterValues), 1),
      revenue: roundTo(dispatchRows.reduce((sum, row) => sum + row.revenue, 0)),
      switches
    }
  }
}

function runControl(payload = {}) {
  const scenarioResult = simulateScenario(payload.scenario)
  const optimizationResult = runOptimization(payload)
  const control = merge(DEFAULT_CONTROL, payload.control)
  const series = scenarioResult.series
  const dispatchRows = optimizationResult.dispatchRows

  const rows = QUARTER_LABELS.map((time, idx) => {
    const sourceIndex = (8 + Math.floor(idx / 4)) % 24
    const source = series[sourceIndex]
    const dispatch = dispatchRows[sourceIndex]
    const predictedLoad = source.load + Math.sin(idx / 2) * 4 + Number(control.deviation) * 0.22
    const predictedWind = source.wind + Math.cos(idx / 3) * 2
    const predictedSolar = source.solar * (0.92 + Math.sin(idx / 4) * 0.05)
    const net = predictedLoad - predictedWind - predictedSolar + (dispatch.netLoadAfter - source.netLoad) * 0.18
    const uncertainty = 3.6 + Math.abs(Number(control.deviation)) * 0.16 + idx * 0.08
    const suggestedAction = net > 62 ? '放电削峰' : net < 36 ? '充电消纳' : '保持待机'
    const commandPower = suggestedAction === '放电削峰'
      ? Math.min(25.92, (net - 55) * 0.7)
      : suggestedAction === '充电消纳'
        ? -Math.min(18, (42 - net) * 0.65)
        : 0
    const confidence = 92 - Math.abs(idx - 5) * 1.8 - Math.abs(Number(control.deviation)) * 0.4
    return {
      time,
      predictedLoad: roundTo(predictedLoad),
      loadLower: roundTo(predictedLoad - uncertainty),
      loadUpper: roundTo(predictedLoad + uncertainty),
      predictedWind: roundTo(predictedWind),
      predictedSolar: roundTo(predictedSolar),
      predictedNetLoad: roundTo(net),
      suggestedAction,
      commandPower: roundTo(commandPower),
      duration: 15,
      confidence: roundTo(confidence, 1)
    }
  })

  const scenarioDistribution = Array.from({ length: 9 }, (_, sceneIdx) => {
    const phase = sceneIdx * 0.72
    const bias = (sceneIdx - 4) * 1.45
    return {
      name: `S${sceneIdx + 1}`,
      values: rows.map((row, idx) => {
        const spread = Math.sin(idx * 0.85 + phase) * (2.2 + sceneIdx * 0.18) + Math.cos(idx * 0.33 + phase) * 1.5
        return {
          time: row.time,
          netLoad: roundTo(row.predictedNetLoad + bias + spread)
        }
      })
    }
  })

  return {
    control,
    rows,
    nextCommand: rows.find((row) => row.suggestedAction !== '保持待机') ?? rows[0],
    scenarioDistribution
  }
}

export function mockGet(path) {
  if (path === '/api/health') {
    return { status: 'ok', algorithmVersion: APP_VERSION, time: new Date().toISOString().slice(0, 19) }
  }
  if (path === '/api/bootstrap') {
    return {
      demoAccount: { account: 'cscec-admin', password: 'demo123456' },
      options: {
        applications: ['风光峰谷蓄调', '风电消纳', '光伏平滑', '园区削峰填谷'],
        seasons: ['春季', '夏季', '秋季', '冬季'],
        buildings: ['办公建筑', '酒店建筑', '园区综合能源站']
      },
      forms: {
        scenario: DEFAULT_SCENARIO,
        planning: DEFAULT_PLANNING,
        optimization: DEFAULT_OPTIMIZATION,
        control: DEFAULT_CONTROL
      },
      results: {}
    }
  }
  throw new Error(`${path} mock not found`)
}

export function mockPost(path, payload = {}) {
  if (path === '/api/scenario/simulate') return simulateScenario(payload.scenario ?? payload)
  if (path === '/api/optimization/run') return runOptimization(payload)
  if (path === '/api/control/preview') return runControl(payload)
  throw new Error(`${path} mock not found`)
}
