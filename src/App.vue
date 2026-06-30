<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { mockGet, mockPost } from './mockApi'

const modules = [
  { id: 'model', no: '01', title: '多场景重力储能模型', hint: '风电、光伏、峰谷蓄调与参数化模型' },
  { id: 'optimization', no: '02', title: '智能优化调度算法', hint: '三目标优化与推荐调度' },
  { id: 'control', no: '03', title: '负荷预测实时控制', hint: 'TCN-VAE 场景生成与控制建议' }
]

const isLoggedIn = ref(false)
const activeModule = ref('model')
const loading = ref('')
const lastRunAt = ref('')
const selectedSolutionId = ref(2)
const backendConnected = ref(false)
const backendMessage = ref('后端连接检测中')
const apiError = ref('')
const usingMockApi = ref(false)
const generated = reactive({
  scenario: false,
  optimization: false,
  control: false
})

const loginForm = reactive({
  account: 'siat-admin',
  password: 'demo123456',
  remember: true
})

const scenarioForm = reactive({
  application: '风光峰谷蓄调',
  season: '夏季',
  building: '园区综合能源站',
  layers: 35,
  columns: 33,
  blockMass: 25,
  efficiency: 0.85,
  maxPower: 25.92,
  initialSoc: 62
})

const planningForm = reactive({
  capacityBoundary: 100,
  switchLimit: 7,
  rollingCycle: 15,
  seasonReserve: 18
})

const optimizationForm = reactive({
  soc: 62,
  revenueWeight: 0.45,
  peakWeight: 0.35,
  switchWeight: 0.2,
  popSize: 80,
  generations: 120
})

const controlForm = reactive({
  model: 'TCN-VAE + 改进 NSGA-II',
  horizon: '未来 4 小时',
  deviation: 8.4,
  mode: '人工确认'
})

const scenarioSeries = ref([])
const modelStats = ref({
  capacity: 0,
  soc: 0,
  peakValley: 0,
  power: 0,
  maxNet: 0,
  minNet: 0,
  avgNet: 0
})
const outputSummary = ref({
  peakHour: { time: '--', netLoad: 0 },
  valleyHour: { time: '--', netLoad: 0 },
  highPriceHours: 0,
  renewableTotal: 0
})
const candidateSolutions = ref([])

const selectedSolution = computed(() => candidateSolutions.value.find((item) => item.id === selectedSolutionId.value) ?? candidateSolutions.value[0] ?? {
  id: 0,
  revenue: 0,
  peakValley: 0,
  switchCount: 0,
  score: 0
})
const dispatchRows = ref([])
const optimizedStats = ref({
  beforePeakValley: 0,
  afterPeakValley: 0,
  revenue: 0,
  switches: 0
})
const controlRows = ref([])
const nextCommand = ref({ suggestedAction: '待生成', commandPower: 0, duration: 15, confidence: 0 })
const scenarioDistribution = ref([])

function emptyCommand() {
  return { suggestedAction: '待生成', commandPower: 0, duration: 15, confidence: 0 }
}

function clearOptimizationResults() {
  generated.optimization = false
  generated.control = false
  candidateSolutions.value = []
  dispatchRows.value = []
  optimizedStats.value = {
    beforePeakValley: 0,
    afterPeakValley: 0,
    revenue: 0,
    switches: 0
  }
  controlRows.value = []
  nextCommand.value = emptyCommand()
  scenarioDistribution.value = []
}

function clearScenarioResults() {
  generated.scenario = false
  scenarioSeries.value = []
  modelStats.value = {
    capacity: 0,
    soc: 0,
    peakValley: 0,
    power: 0,
    maxNet: 0,
    minNet: 0,
    avgNet: 0
  }
  outputSummary.value = {
    peakHour: { time: '--', netLoad: 0 },
    valleyHour: { time: '--', netLoad: 0 },
    highPriceHours: 0,
    renewableTotal: 0
  }
  clearOptimizationResults()
}

function clearControlResults() {
  generated.control = false
  controlRows.value = []
  nextCommand.value = emptyCommand()
  scenarioDistribution.value = []
}

function currentModule() {
  return modules.find((item) => item.id === activeModule.value) ?? modules[0]
}

function fmt(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '--'
  return Number(value).toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function chartArea(width = 720, height = 230, pad = 42) {
  return {
    left: pad,
    right: width - pad,
    top: pad,
    bottom: height - pad,
    width: width - pad * 2,
    height: height - pad * 2
  }
}

function domainFor(rows, group) {
  const groups = {
    source: { keys: ['load', 'wind', 'solar', 'netLoad'], includeZero: true },
    price: { fixed: [0, 1.1] },
    net: { keys: ['netLoadBefore', 'netLoadAfter'], includeZero: false },
    soc: { fixed: [0, 100] },
    forecastLoad: { keys: ['predictedLoad', 'loadLower', 'loadUpper'], includeZero: false },
    renewableForecast: { keys: ['predictedWind', 'predictedSolar'], includeZero: true },
    scenarioNet: { keys: ['predictedNetLoad'], includeZero: false },
    power: { keys: ['power'], symmetric: true }
  }
  const config = groups[group] ?? { keys: [group], includeZero: false }
  if (config.fixed) return config.fixed
  const scenarioValues = group === 'scenarioNet'
    ? scenarioDistribution.value.flatMap((scene) => (scene.values ?? []).map((point) => Number(point.netLoad)))
    : []
  const values = rows
    .flatMap((row) => config.keys.map((key) => Number(row[key])))
    .concat(scenarioValues)
    .filter((value) => Number.isFinite(value))
  if (!values.length) return [0, 1]
  if (config.symmetric) {
    const maxAbs = Math.max(1, Math.max(...values.map((value) => Math.abs(value))))
    const rounded = Math.ceil(maxAbs / 5) * 5
    return [-rounded, rounded]
  }
  let min = Math.min(...values)
  let max = Math.max(...values)
  if (config.includeZero) {
    min = Math.min(0, min)
    max = Math.max(0, max)
  }
  const span = max - min || 1
  return [min - span * 0.08, max + span * 0.08]
}

function yForValue(value, group, rows, width = 720, height = 230, pad = 42) {
  const area = chartArea(width, height, pad)
  const [min, max] = domainFor(rows, group)
  const ratio = (Number(value) - min) / (max - min || 1)
  return area.bottom - ratio * area.height
}

function xForIndex(index, total, width = 720, height = 230, pad = 42) {
  const area = chartArea(width, height, pad)
  return area.left + index * (area.width / (total - 1 || 1))
}

function linePoints(rows, key, group = key, width = 720, height = 230, pad = 42) {
  if (!rows.length) return ''
  return rows.map((row, index) => {
    const x = xForIndex(index, rows.length, width, height, pad)
    const y = yForValue(row[key], group, rows, width, height, pad)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}

function bandPoints(rows, lowKey, highKey, group, width = 720, height = 230, pad = 42) {
  if (!rows.length) return ''
  const validRows = rows.filter((row) => Number.isFinite(Number(row[lowKey])) && Number.isFinite(Number(row[highKey])))
  if (!validRows.length) return ''
  const upper = validRows.map((row, index) => {
    const x = xForIndex(index, rows.length, width, height, pad)
    const y = yForValue(row[highKey], group, rows, width, height, pad)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  const lower = validRows.slice().reverse().map((row, reverseIndex) => {
    const index = validRows.length - 1 - reverseIndex
    const x = xForIndex(index, rows.length, width, height, pad)
    const y = yForValue(row[lowKey], group, rows, width, height, pad)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  return upper.concat(lower).join(' ')
}

function scenarioLinePoints(scene, width = 720, height = 230, pad = 42) {
  const rows = scene?.values ?? []
  if (!rows.length) return ''
  return rows.map((row, index) => {
    const x = xForIndex(index, rows.length, width, height, pad)
    const y = yForValue(row.netLoad, 'scenarioNet', controlRows.value, width, height, pad)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}

function yTicks(rows, group, count = 5, width = 720, height = 230, pad = 42) {
  const [min, max] = domainFor(rows, group)
  return Array.from({ length: count }, (_, index) => {
    const value = min + ((max - min) / (count - 1 || 1)) * index
    const compact = Math.abs(max - min) <= 2
    return {
      value,
      label: compact ? value.toFixed(2) : value.toFixed(0),
      y: yForValue(value, group, rows, width, height, pad)
    }
  }).reverse()
}

function reportGrid(width = 720, height = 230, pad = 42) {
  const area = chartArea(width, height, pad)
  return {
    x: Array.from({ length: 7 }, (_, index) => area.left + index * (area.width / 6)),
    y: Array.from({ length: 5 }, (_, index) => area.top + index * (area.height / 4)),
    left: area.left,
    right: area.right,
    top: area.top,
    bottom: area.bottom
  }
}

function reportTicks(rows, width = 720, pad = 42) {
  return rows
    .map((row, index) => ({ row, index }))
    .filter((item) => item.index % 4 === 0 || item.index === rows.length - 1)
    .map(({ row, index }) => ({
      label: row.time.slice(0, 2),
      time: row.time,
      x: pad + index * ((width - pad * 2) / (rows.length - 1 || 1))
    }))
}

function powerBar(value, index, total = 24, width = 720, height = 230, pad = 42, max = 28) {
  const area = chartArea(width, height, pad)
  const domain = domainFor(dispatchRows.value, 'power')
  const cell = area.width / total
  const barWidth = Math.max(7, cell * 0.58)
  const baseline = yForValue(0, 'power', dispatchRows.value, width, height, pad)
  const yValue = area.bottom - ((Number(value) - domain[0]) / (domain[1] - domain[0] || 1)) * area.height
  const barHeightValue = Math.max(1.5, Math.abs(yValue - baseline))
  return {
    x: area.left + index * cell + (cell - barWidth) / 2,
    y: Math.min(yValue, baseline),
    width: barWidth,
    height: barHeightValue
  }
}

function pct(value, max) {
  const number = Number(value) || 0
  return `${Math.max(6, Math.min(100, number / max * 100))}%`
}

function requestPayload() {
  return {
    scenario: { ...scenarioForm },
    planning: { ...planningForm },
    optimization: { ...optimizationForm },
    control: { ...controlForm },
    selectedSolutionId: selectedSolutionId.value
  }
}

async function apiGet(path) {
  try {
    const response = await fetch(path)
    if (!response.ok) throw new Error(`${path} ${response.status}`)
    usingMockApi.value = false
    return response.json()
  } catch (error) {
    usingMockApi.value = true
    return mockGet(path)
  }
}

async function apiPost(path, payload) {
  try {
    const response = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!response.ok) throw new Error(`${path} ${response.status}`)
    usingMockApi.value = false
    return response.json()
  } catch (error) {
    usingMockApi.value = true
    return mockPost(path, payload)
  }
}

function applyScenario(result) {
  scenarioSeries.value = result.series ?? []
  modelStats.value = result.stats ?? modelStats.value
  outputSummary.value = result.summary ?? outputSummary.value
  generated.scenario = true
}

function applyOptimization(result) {
  candidateSolutions.value = result.solutions ?? []
  dispatchRows.value = result.dispatchRows ?? []
  optimizedStats.value = result.optimizedStats ?? optimizedStats.value
  const selected = result.selectedSolution ?? candidateSolutions.value.find((item) => item.selected)
  if (selected) selectedSolutionId.value = selected.id
  generated.optimization = true
}

function normalizeControlRows(rows) {
  return (rows ?? []).map((row, index) => {
    const predictedLoad = Number(row.predictedLoad ?? 0)
    const predictedWind = Number(row.predictedWind ?? 0)
    const predictedSolar = Number(row.predictedSolar ?? 0)
    const spread = 3.2 + Math.abs(Math.sin(index * 0.75)) * 1.8 + Math.abs(Number(controlForm.deviation) || 0) * 0.08
    return {
      ...row,
      predictedLoad,
      loadLower: Number.isFinite(Number(row.loadLower)) ? Number(row.loadLower) : Number((predictedLoad - spread).toFixed(2)),
      loadUpper: Number.isFinite(Number(row.loadUpper)) ? Number(row.loadUpper) : Number((predictedLoad + spread).toFixed(2)),
      predictedWind,
      predictedSolar,
      predictedNetLoad: Number.isFinite(Number(row.predictedNetLoad))
        ? Number(row.predictedNetLoad)
        : Number((predictedLoad - predictedWind - predictedSolar).toFixed(2))
    }
  })
}

function buildScenarioDistribution(rows, rawDistribution) {
  const structured = (rawDistribution ?? []).filter((scene) => Array.isArray(scene?.values))
  if (structured.length) return structured
  if (!rows.length) return []
  return Array.from({ length: 9 }, (_, sceneIndex) => {
    const bias = (sceneIndex - 4) * 1.35
    const phase = sceneIndex * 0.68
    return {
      name: `S${sceneIndex + 1}`,
      values: rows.map((row, index) => {
        const swing = Math.sin(index * 0.9 + phase) * (2.1 + sceneIndex * 0.16) + Math.cos(index * 0.36 + phase) * 1.4
        return {
          time: row.time,
          netLoad: Number((Number(row.predictedNetLoad) + bias + swing).toFixed(2))
        }
      })
    }
  })
}

function applyControl(result) {
  const rows = normalizeControlRows(result.rows)
  controlRows.value = rows
  nextCommand.value = result.nextCommand ?? nextCommand.value
  scenarioDistribution.value = buildScenarioDistribution(rows, result.scenarioDistribution)
  generated.control = true
}

function moduleStatus(id) {
  if (id === 'model') return generated.scenario ? '已生成' : '待生成'
  if (id === 'optimization') {
    if (generated.optimization) return '已求解'
    return generated.scenario ? '可求解' : '需先生成场景'
  }
  if (id === 'control') {
    if (generated.control) return '已生成'
    return generated.optimization ? '可生成' : '需先优化'
  }
  return ''
}

async function refreshHealth() {
  try {
    const result = await apiGet('/api/health')
    backendConnected.value = true
    backendMessage.value = usingMockApi.value
      ? `浏览器演示模式 · ${result.algorithmVersion}`
      : `后端已连接 · ${result.algorithmVersion}`
    apiError.value = ''
  } catch (error) {
    backendConnected.value = false
    backendMessage.value = '后端未连接'
    apiError.value = '后端服务不可用，请确认 FastAPI 已在 8001 端口启动。'
  }
}

async function bootstrap() {
  await refreshHealth()
  if (!backendConnected.value) return
  try {
    const result = await apiGet('/api/bootstrap')
    Object.assign(scenarioForm, result.forms?.scenario ?? {})
    Object.assign(planningForm, result.forms?.planning ?? {})
    Object.assign(optimizationForm, result.forms?.optimization ?? {})
    Object.assign(controlForm, result.forms?.control ?? {})
    clearScenarioResults()
  } catch (error) {
    backendConnected.value = false
    backendMessage.value = '后端数据初始化失败'
    apiError.value = error.message
  }
}

async function runWithStatus(flag, task) {
  loading.value = flag
  apiError.value = ''
  try {
    await task()
    backendConnected.value = true
    backendMessage.value = usingMockApi.value ? '浏览器演示模式' : '后端已连接'
    lastRunAt.value = new Date().toLocaleString('zh-CN')
  } catch (error) {
    backendConnected.value = false
    backendMessage.value = '后端未连接'
    apiError.value = error.message || '接口调用失败'
  } finally {
    loading.value = ''
  }
}

function submitLogin() {
  isLoggedIn.value = true
  refreshHealth()
}

async function simulateScenario() {
  await runWithStatus('场景曲线生成中', async () => {
    clearOptimizationResults()
    const result = await apiPost('/api/scenario/simulate', requestPayload())
    applyScenario(result)
    activeModule.value = 'model'
  })
}

async function runOptimization() {
  if (!generated.scenario) {
    activeModule.value = 'model'
    apiError.value = '请先在“多场景重力储能模型”中生成场景曲线，再进行优化求解。'
    return
  }
  await runWithStatus('三目标优化求解中', async () => {
    clearControlResults()
    const result = await apiPost('/api/optimization/run', requestPayload())
    applyOptimization(result)
    activeModule.value = 'optimization'
  })
}

async function previewControl() {
  if (!generated.optimization) {
    activeModule.value = 'optimization'
    apiError.value = '请先完成优化求解，再生成实时控制建议。'
    return
  }
  await runWithStatus('控制建议生成中', async () => {
    const result = await apiPost('/api/control/preview', requestPayload())
    applyControl(result)
    activeModule.value = 'control'
  })
}

async function selectSolution(id) {
  if (!generated.optimization) return
  selectedSolutionId.value = id
  if (!backendConnected.value) return
  await runWithStatus('方案切换计算中', async () => {
    const result = await apiPost('/api/optimization/run', requestPayload())
    applyOptimization(result)
    clearControlResults()
  })
}

watch(
  () => [
    scenarioForm.application,
    scenarioForm.season,
    scenarioForm.building,
    scenarioForm.maxPower,
    scenarioForm.initialSoc
  ],
  () => clearScenarioResults()
)

watch(
  () => [
    optimizationForm.soc,
    optimizationForm.revenueWeight,
    optimizationForm.peakWeight,
    optimizationForm.switchWeight,
    optimizationForm.popSize,
    optimizationForm.generations
  ],
  () => clearOptimizationResults()
)

watch(
  () => [
    controlForm.model,
    controlForm.horizon,
    controlForm.deviation,
    controlForm.mode
  ],
  () => clearControlResults()
)

onMounted(bootstrap)
</script>

<template>
  <div v-if="!isLoggedIn" class="login-shell">
    <section class="login-layout">
      <div class="login-brand">
        <img src="/siat-logo.png" alt="中国科学院深圳先进技术研究院" class="login-logo" />
        <span>GRAVITY ENERGY STORAGE</span>
      </div>
      <div class="login-panel">
        <div class="login-card">
          <p class="eyebrow">SIAT SHOWCASE</p>
          <h1>重力储能智能调度</h1>
          <label>账号<input v-model="loginForm.account" /></label>
          <label>密码<input v-model="loginForm.password" type="password" /></label>
          <label class="check-line"><input v-model="loginForm.remember" type="checkbox" />记住登录</label>
          <button class="primary-btn" @click="submitLogin">登录系统</button>
          <p class="hint">siat-admin / demo123456</p>
        </div>
      </div>
    </section>
  </div>

  <div v-else class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <img src="/siat-logo.png" alt="SIAT" />
        <strong>重力储能智能调度</strong>
        <span>模型 · 优化 · 控制</span>
      </div>
      <nav>
        <button v-for="item in modules" :key="item.id" :class="{ active: activeModule === item.id }" @click="activeModule = item.id">
          <span>{{ item.no }}</span>
          <strong>{{ item.title }}</strong>
          <small>{{ item.hint }}</small>
          <em>{{ moduleStatus(item.id) }}</em>
        </button>
      </nav>

      <button class="secondary-btn" @click="isLoggedIn = false">退出登录</button>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <p class="tag">中国科学院深圳先进技术研究院</p>
          <h1>{{ currentModule().title }}</h1>
          <p>{{ currentModule().hint }}</p>
        </div>
        <div class="status-strip">
          <span>{{ loading || '系统就绪' }}</span>
          <span :class="{ danger: !backendConnected }">{{ backendMessage }}</span>
          <span>最近运行：{{ lastRunAt || '--' }}</span>
        </div>
      </header>
      <div v-if="apiError" class="error-banner">{{ apiError }}</div>

      <section v-if="activeModule === 'model'" class="screen-grid model-grid">
        <article class="panel span-3 operation-panel">
          <div class="section-head">
            <div><p class="eyebrow">模块输入</p><h2>场景与结构参数</h2></div>
            <button class="primary-btn" :disabled="!backendConnected || !!loading" @click="simulateScenario">
              {{ loading === '场景曲线生成中' ? '生成中...' : '生成场景曲线' }}
            </button>
          </div>
          <div class="form-grid condensed">
            <label>应用场景<select v-model="scenarioForm.application"><option>风光峰谷蓄调</option><option>风电消纳</option><option>光伏平滑</option><option>园区削峰填谷</option></select></label>
            <label>季节<select v-model="scenarioForm.season"><option>春季</option><option>夏季</option><option>秋季</option><option>冬季</option></select></label>
            <label>类型<select v-model="scenarioForm.building"><option>办公建筑</option><option>酒店建筑</option><option>园区综合能源站</option></select></label>
            <label>最大功率/MW<input v-model.number="scenarioForm.maxPower" type="number" step="0.01" /></label>
            <label>初始 SOC/%<input v-model.number="scenarioForm.initialSoc" type="number" /></label>
          </div>
        </article>

        <article v-if="!generated.scenario" class="panel span-3 empty-state">
          <p class="eyebrow">等待操作</p>
          <h2>第一步：选择场景参数，点击“生成场景曲线”</h2>
          <p>系统会调用后端生成 24 小时负荷、风电、光伏、电价和净负荷数据。生成前不会展示结果，方便你在会议上一步一步演示。</p>
        </article>

        <template v-else>
        <article class="panel span-3 visual-summary-panel">
          <div class="section-head"><h2>关键指标总览</h2><span class="pill">模型 + 场景输出</span></div>
          <div class="visual-kpi-row">
            <div class="visual-kpi">
              <span>估算容量</span>
              <strong>{{ fmt(modelStats.capacity, 1) }}</strong>
              <small>MWh</small>
              <i><b :style="{ width: pct(modelStats.capacity, 15000) }"></b></i>
            </div>
            <div class="visual-kpi">
              <span>原始峰谷差</span>
              <strong>{{ fmt(modelStats.peakValley, 1) }}</strong>
              <small>MW</small>
              <i><b :style="{ width: pct(modelStats.peakValley, 80) }"></b></i>
            </div>
            <div class="visual-kpi">
              <span>最大功率</span>
              <strong>{{ fmt(modelStats.power, 2) }}</strong>
              <small>MW</small>
              <i><b :style="{ width: pct(modelStats.power, 40) }"></b></i>
            </div>
            <div class="visual-kpi accent">
              <span>净负荷最高</span>
              <strong>{{ outputSummary.peakHour.time }}</strong>
              <small>{{ outputSummary.peakHour.netLoad }} MW</small>
              <i><b :style="{ width: pct(outputSummary.peakHour.netLoad, 120) }"></b></i>
            </div>
            <div class="visual-kpi soft">
              <span>净负荷最低</span>
              <strong>{{ outputSummary.valleyHour.time }}</strong>
              <small>{{ outputSummary.valleyHour.netLoad }} MW</small>
              <i><b :style="{ width: pct(outputSummary.valleyHour.netLoad, 120) }"></b></i>
            </div>
            <div class="visual-kpi">
              <span>高电价时段</span>
              <strong>{{ outputSummary.highPriceHours }}</strong>
              <small>小时</small>
              <i><b :style="{ width: pct(outputSummary.highPriceHours, 24) }"></b></i>
            </div>
            <div class="visual-kpi">
              <span>新能源日出力</span>
              <strong>{{ fmt(outputSummary.renewableTotal, 1) }}</strong>
              <small>MWh</small>
              <i><b :style="{ width: pct(outputSummary.renewableTotal, 1400) }"></b></i>
            </div>
          </div>
        </article>

        <article class="panel span-3 report-panel">
          <div class="section-head"><h2>源荷场景结果图</h2><span class="pill">科研汇报图风格</span></div>
          <div class="report-figure">
          <div class="report-caption">负荷、风电、光伏与净负荷曲线</div>
          <svg class="line-chart report-chart" viewBox="0 0 720 230">
            <g class="chart-grid">
              <line v-for="x in reportGrid().x" :key="`sx-${x}`" :x1="x" y1="42" :x2="x" y2="188" />
              <line v-for="y in reportGrid().y" :key="`sy-${y}`" x1="42" :y1="y" x2="678" :y2="y" />
              <line x1="42" y1="188" x2="678" y2="188" class="axis" />
              <line x1="42" y1="42" x2="42" y2="188" class="axis" />
            </g>
            <polyline :points="linePoints(scenarioSeries, 'load', 'source')" class="line load" />
            <polyline :points="linePoints(scenarioSeries, 'wind', 'source')" class="line wind" />
            <polyline :points="linePoints(scenarioSeries, 'solar', 'source')" class="line solar" />
            <polyline :points="linePoints(scenarioSeries, 'netLoad', 'source')" class="line net" />
            <g class="axis-labels">
              <text v-for="tick in yTicks(scenarioSeries, 'source')" :key="`source-y-${tick.label}`" x="34" :y="tick.y + 4" class="left-axis-label">{{ tick.label }}</text>
              <text v-for="tick in reportTicks(scenarioSeries)" :key="tick.x" :x="tick.x" y="210">{{ tick.label }}</text>
              <text x="52" y="30">功率 MW</text>
            </g>
          </svg>
          <div class="legend report-legend"><span class="load">负荷</span><span class="wind">风电</span><span class="solar">光伏</span><span class="net">净负荷</span></div>
          </div>
        </article>

        <article class="panel span-3 report-panel">
          <div class="section-head"><h2>分时电价曲线</h2><span class="pill">用于优化调度收益计算</span></div>
          <div class="report-figure">
          <div class="report-caption">峰平谷电价曲线</div>
          <svg class="line-chart report-chart compact" viewBox="0 0 720 230">
            <g class="chart-grid">
              <line v-for="x in reportGrid().x" :key="`px-${x}`" :x1="x" y1="42" :x2="x" y2="188" />
              <line v-for="y in reportGrid().y" :key="`py-${y}`" x1="42" :y1="y" x2="678" :y2="y" />
              <line x1="42" y1="188" x2="678" y2="188" class="axis" />
              <line x1="42" y1="42" x2="42" y2="188" class="axis" />
            </g>
            <polyline :points="linePoints(scenarioSeries, 'price', 'price')" class="line price" />
            <g class="axis-labels">
              <text v-for="tick in yTicks(scenarioSeries, 'price')" :key="`price-y-${tick.label}`" x="34" :y="tick.y + 4" class="left-axis-label">{{ tick.label }}</text>
              <text v-for="tick in reportTicks(scenarioSeries)" :key="tick.x" :x="tick.x" y="210">{{ tick.label }}</text>
              <text x="60" y="30">电价 元/kWh</text>
            </g>
          </svg>
          <div class="legend report-legend"><span class="price">分时电价</span></div>
          </div>
        </article>

        <article class="panel span-3">
          <h2>输出表：源荷场景预览</h2>
          <div class="table-wrap"><table><thead><tr><th>time</th><th>load</th><th>wind</th><th>solar</th><th>price</th><th>netLoad</th></tr></thead><tbody><tr v-for="row in scenarioSeries" :key="row.time"><td>{{ row.time }}</td><td>{{ row.load }}</td><td>{{ row.wind }}</td><td>{{ row.solar }}</td><td>{{ row.price }}</td><td>{{ row.netLoad }}</td></tr></tbody></table></div>
        </article>
        <article class="panel span-3 next-panel">
          <div>
            <p class="eyebrow">下一步</p>
            <h2>源荷场景已经生成，可以进入优化调度</h2>
            <p>后续优化会使用这里生成的净负荷、电价、SOC 和最大功率作为输入。</p>
          </div>
          <button class="primary-btn" @click="activeModule = 'optimization'">进入智能优化调度</button>
        </article>
        </template>
      </section>

      <section v-if="activeModule === 'optimization'" class="screen-grid">
        <article class="panel span-3 operation-panel">
          <div class="section-head">
            <div><p class="eyebrow">模块输入</p><h2>三目标优化参数</h2></div>
            <button class="primary-btn" :disabled="!backendConnected || !!loading || !generated.scenario" @click="runOptimization">
              {{ loading === '三目标优化求解中' ? '求解中...' : '开始优化求解' }}
            </button>
          </div>
          <div class="form-grid condensed">
            <label>初始 SOC/%<input v-model.number="optimizationForm.soc" type="number" /></label>
            <label>经济权重<input v-model.number="optimizationForm.revenueWeight" type="number" step="0.01" /></label>
            <label>峰谷权重<input v-model.number="optimizationForm.peakWeight" type="number" step="0.01" /></label>
            <label>启停权重<input v-model.number="optimizationForm.switchWeight" type="number" step="0.01" /></label>
            <label>种群规模<input v-model.number="optimizationForm.popSize" type="number" /></label>
            <label>迭代次数<input v-model.number="optimizationForm.generations" type="number" /></label>
          </div>
        </article>

        <article v-if="!generated.scenario" class="panel span-3 empty-state">
          <p class="eyebrow">等待上一步</p>
          <h2>请先生成场景曲线</h2>
          <p>优化调度需要使用模块 01 的负荷、风电、光伏、电价和净负荷数据。先完成场景生成，再回到这里点击“开始优化求解”。</p>
          <button class="primary-btn" @click="activeModule = 'model'">返回生成场景</button>
        </article>

        <article v-else-if="!generated.optimization" class="panel span-3 empty-state">
          <p class="eyebrow">等待操作</p>
          <h2>第二步：调整优化参数，点击“开始优化求解”</h2>
          <p>系统会根据当前源荷曲线和三目标权重，计算多组候选方案，并给出推荐充放电计划。</p>
        </article>

        <template v-else>
        <article class="panel">
          <h2>推荐方案</h2>
          <div class="big-number">{{ selectedSolution.score }}</div><span>综合评分</span>
          <p>收益 {{ selectedSolution.revenue }} 万元，峰谷差 {{ selectedSolution.peakValley }} MW，启停 {{ selectedSolution.switchCount }} 次。</p>
          <p>净负荷峰谷差由 {{ optimizedStats.beforePeakValley }} MW 降至 {{ optimizedStats.afterPeakValley }} MW。</p>
        </article>
        <article class="panel span-2">
          <h2>优化效果摘要</h2>
          <div class="summary-grid four-cells">
            <div><span>峰谷差降低</span><strong>{{ fmt(optimizedStats.beforePeakValley - optimizedStats.afterPeakValley, 1) }} MW</strong></div>
            <div><span>日收益估算</span><strong>{{ optimizedStats.revenue }} 万元</strong></div>
            <div><span>动作切换</span><strong>{{ optimizedStats.switches }} 次</strong></div>
            <div><span>选中方案</span><strong>#{{ selectedSolution.id }}</strong></div>
          </div>
        </article>
        <article class="panel span-3 report-panel">
          <h2>净负荷削峰填谷结果图</h2>
          <div class="report-figure">
          <div class="report-caption">优化前后净负荷对比</div>
          <svg class="line-chart report-chart" viewBox="0 0 720 230">
            <g class="chart-grid">
              <line v-for="x in reportGrid().x" :key="`ox-${x}`" :x1="x" y1="42" :x2="x" y2="188" />
              <line v-for="y in reportGrid().y" :key="`oy-${y}`" x1="42" :y1="y" x2="678" :y2="y" />
              <line x1="42" y1="188" x2="678" y2="188" class="axis" />
              <line x1="42" y1="42" x2="42" y2="188" class="axis" />
            </g>
            <polyline :points="linePoints(dispatchRows, 'netLoadBefore', 'net')" class="line net" />
            <polyline :points="linePoints(dispatchRows, 'netLoadAfter', 'net')" class="line plan" />
            <g class="axis-labels">
              <text v-for="tick in yTicks(dispatchRows, 'net')" :key="`net-y-${tick.label}`" x="34" :y="tick.y + 4" class="left-axis-label">{{ tick.label }}</text>
              <text v-for="tick in reportTicks(dispatchRows)" :key="tick.x" :x="tick.x" y="210">{{ tick.label }}</text>
              <text x="58" y="30">净负荷 MW</text>
            </g>
          </svg>
          <div class="legend report-legend"><span class="net">优化前净负荷</span><span class="plan">优化后净负荷</span></div>
          </div>
        </article>
        <article class="panel span-3 report-panel">
          <h2>SOC 轨迹图</h2>
          <div class="report-figure">
          <div class="report-caption">储能荷电状态变化</div>
          <svg class="line-chart report-chart" viewBox="0 0 720 230">
            <g class="chart-grid">
              <line v-for="x in reportGrid().x" :key="`socx-${x}`" :x1="x" y1="42" :x2="x" y2="188" />
              <line v-for="y in reportGrid().y" :key="`socy-${y}`" x1="42" :y1="y" x2="678" :y2="y" />
              <line x1="42" y1="188" x2="678" y2="188" class="axis" />
              <line x1="42" y1="42" x2="42" y2="188" class="axis" />
            </g>
            <polyline :points="linePoints(dispatchRows, 'soc', 'soc')" class="line control" />
            <g class="axis-labels">
              <text v-for="tick in yTicks(dispatchRows, 'soc')" :key="`soc-y-${tick.label}`" x="34" :y="tick.y + 4" class="left-axis-label">{{ tick.label }}</text>
              <text v-for="tick in reportTicks(dispatchRows)" :key="tick.x" :x="tick.x" y="210">{{ tick.label }}</text>
              <text x="58" y="30">SOC %</text>
            </g>
          </svg>
          <div class="legend report-legend"><span class="control">SOC</span></div>
          </div>
        </article>
        <article class="panel span-3 report-panel">
          <h2>重力储能系统调度策略结果图</h2>
          <div class="report-figure">
          <div class="report-caption">24 小时充放电功率策略</div>
          <svg class="line-chart report-chart" viewBox="0 0 720 230">
            <g class="chart-grid">
              <line v-for="x in reportGrid().x" :key="`bx-${x}`" :x1="x" y1="42" :x2="x" y2="188" />
              <line v-for="y in reportGrid().y" :key="`by-${y}`" x1="42" :y1="y" x2="678" :y2="y" />
              <line x1="42" :y1="yForValue(0, 'power', dispatchRows)" x2="678" :y2="yForValue(0, 'power', dispatchRows)" class="zero-axis" />
              <line x1="42" y1="188" x2="678" y2="188" class="axis" />
              <line x1="42" y1="42" x2="42" y2="188" class="axis" />
            </g>
            <rect v-for="(row, index) in dispatchRows" :key="row.time" :x="powerBar(row.power, index).x" :y="powerBar(row.power, index).y" :width="powerBar(row.power, index).width" :height="powerBar(row.power, index).height" :class="row.power >= 0 ? 'discharge-bar' : 'charge-bar'" />
            <g class="axis-labels">
              <text v-for="tick in yTicks(dispatchRows, 'power')" :key="`power-y-${tick.label}`" x="34" :y="tick.y + 4" class="left-axis-label">{{ tick.label }}</text>
              <text v-for="tick in reportTicks(dispatchRows)" :key="tick.x" :x="tick.x" y="210">{{ tick.label }}</text>
              <text x="52" y="30">充放电功率 MW</text>
            </g>
          </svg>
          <div class="legend report-legend"><span class="discharge">放电</span><span class="charge">充电</span><span>0 功率基线</span></div>
          </div>
        </article>
        <article class="panel span-3">
          <h2>输出表：方案集</h2>
          <div class="table-wrap"><table><thead><tr><th>solutionId</th><th>revenue</th><th>peakValley</th><th>switchCount</th><th>score</th><th>selected</th></tr></thead><tbody><tr v-for="row in candidateSolutions" :key="row.id" @click="selectSolution(row.id)"><td>#{{ row.id }}</td><td>{{ row.revenue }}</td><td>{{ row.peakValley }}</td><td>{{ row.switchCount }}</td><td>{{ row.score }}</td><td>{{ selectedSolutionId === row.id ? 'YES' : 'NO' }}</td></tr></tbody></table></div>
        </article>
        <article class="panel span-3">
          <h2>输出表：推荐调度明细</h2>
          <div class="table-wrap"><table><thead><tr><th>time</th><th>action</th><th>power</th><th>soc</th><th>netLoadBefore</th><th>netLoadAfter</th><th>price</th><th>revenue</th></tr></thead><tbody><tr v-for="row in dispatchRows" :key="row.time"><td>{{ row.time }}</td><td>{{ row.action }}</td><td>{{ row.power }}</td><td>{{ row.soc }}</td><td>{{ row.netLoadBefore }}</td><td>{{ row.netLoadAfter }}</td><td>{{ row.price }}</td><td>{{ row.revenue }}</td></tr></tbody></table></div>
        </article>
        <article class="panel span-3 next-panel">
          <div>
            <p class="eyebrow">下一步</p>
            <h2>优化方案已经得到，可以进入实时控制预览</h2>
            <p>实时控制会读取当前选中的调度方案，并结合预测偏差生成下一周期建议。</p>
          </div>
          <button class="primary-btn" @click="activeModule = 'control'">进入实时控制</button>
        </article>
        </template>
      </section>

      <section v-if="activeModule === 'control'" class="screen-grid">
        <article class="panel span-3 operation-panel">
          <div class="section-head">
            <div><p class="eyebrow">模块输入</p><h2>预测控制参数</h2></div>
            <button class="primary-btn" :disabled="!backendConnected || !!loading || !generated.optimization" @click="previewControl">
              {{ loading === '控制建议生成中' ? '生成中...' : '生成控制建议' }}
            </button>
          </div>
          <div class="form-grid condensed">
            <label>预测模型<select v-model="controlForm.model"><option>TCN-VAE + 改进 NSGA-II</option><option>TCN-VAE 场景生成</option><option>负荷预测 + 规则修正</option></select></label>
            <label>预测时域<select v-model="controlForm.horizon"><option>未来 1 小时</option><option>未来 4 小时</option><option>未来 24 小时</option></select></label>
            <label>实时偏差/MW<input v-model.number="controlForm.deviation" type="number" /></label>
            <label>控制模式<select v-model="controlForm.mode"><option>人工确认</option><option>自动建议</option><option>闭环演示</option></select></label>
          </div>
        </article>

        <article v-if="!generated.optimization" class="panel span-3 empty-state">
          <p class="eyebrow">等待上一步</p>
          <h2>请先完成优化求解</h2>
          <p>实时控制建议需要读取推荐调度方案、SOC 轨迹和优化后净负荷。先完成模块 02，再生成控制建议。</p>
          <button class="primary-btn" @click="activeModule = 'optimization'">返回优化求解</button>
        </article>

        <article v-else-if="!generated.control" class="panel span-3 empty-state">
          <p class="eyebrow">等待操作</p>
          <h2>第三步：设置预测偏差和控制模式，点击“生成控制建议”</h2>
          <p>系统会基于优化后的调度结果，生成未来控制周期的负荷预测、场景分布和充放电建议。</p>
        </article>

        <template v-else>
        <article class="panel">
          <h2>下一控制周期建议</h2>
          <div class="command-card">
            <strong>{{ nextCommand.suggestedAction }}</strong>
            <span>{{ nextCommand.commandPower }} MW · {{ nextCommand.duration }} min</span>
            <p>置信度 {{ nextCommand.confidence }}%，模式：{{ controlForm.mode }}</p>
          </div>
        </article>
        <article class="panel span-2 report-panel">
          <h2>预测结果</h2>
          <div class="report-figure">
          <div class="report-caption">负荷预测区间</div>
          <svg class="line-chart mini report-chart" viewBox="0 0 720 230">
            <g class="chart-grid">
              <line v-for="x in reportGrid().x" :key="`cx-${x}`" :x1="x" y1="42" :x2="x" y2="188" />
              <line v-for="y in reportGrid().y" :key="`cy-${y}`" x1="42" :y1="y" x2="678" :y2="y" />
              <line x1="42" y1="188" x2="678" y2="188" class="axis" />
              <line x1="42" y1="42" x2="42" y2="188" class="axis" />
            </g>
            <polygon :points="bandPoints(controlRows, 'loadLower', 'loadUpper', 'forecastLoad')" class="confidence-band" />
            <polyline :points="linePoints(controlRows, 'loadUpper', 'forecastLoad')" class="band-edge" />
            <polyline :points="linePoints(controlRows, 'loadLower', 'forecastLoad')" class="band-edge" />
            <polyline :points="linePoints(controlRows, 'predictedLoad', 'forecastLoad')" class="line load" />
            <g class="axis-labels">
              <text v-for="tick in yTicks(controlRows, 'forecastLoad')" :key="`load-y-${tick.label}`" x="34" :y="tick.y + 4" class="left-axis-label">{{ tick.label }}</text>
              <text v-for="tick in reportTicks(controlRows)" :key="tick.x" :x="tick.x" y="210">{{ tick.time }}</text>
              <text x="54" y="30">负荷 MW</text>
            </g>
          </svg>
          <div class="legend report-legend"><span class="load">预测负荷</span><span class="band">预测区间</span></div>
          <div class="report-caption subcaption">风电 / 光伏出力预测</div>
          <svg class="line-chart mini report-chart" viewBox="0 0 720 230">
            <g class="chart-grid">
              <line v-for="x in reportGrid().x" :key="`rx-${x}`" :x1="x" y1="42" :x2="x" y2="188" />
              <line v-for="y in reportGrid().y" :key="`ry-${y}`" x1="42" :y1="y" x2="678" :y2="y" />
              <line x1="42" y1="188" x2="678" y2="188" class="axis" />
              <line x1="42" y1="42" x2="42" y2="188" class="axis" />
            </g>
            <polyline :points="linePoints(controlRows, 'predictedWind', 'renewableForecast')" class="line wind" />
            <polyline :points="linePoints(controlRows, 'predictedSolar', 'renewableForecast')" class="line solar" />
            <g class="axis-labels">
              <text v-for="tick in yTicks(controlRows, 'renewableForecast')" :key="`renew-y-${tick.label}`" x="34" :y="tick.y + 4" class="left-axis-label">{{ tick.label }}</text>
              <text v-for="tick in reportTicks(controlRows)" :key="tick.x" :x="tick.x" y="210">{{ tick.time }}</text>
              <text x="54" y="30">出力 MW</text>
            </g>
          </svg>
          <div class="legend report-legend"><span class="wind">预测风电</span><span class="solar">预测光伏</span></div>
          </div>
        </article>
        <article class="panel span-3 report-panel">
          <h2>生成场景分布</h2>
          <div class="report-figure">
          <div class="report-caption">未来净负荷多场景样本</div>
          <svg class="line-chart report-chart" viewBox="0 0 720 230">
            <g class="chart-grid">
              <line v-for="x in reportGrid().x" :key="`sx-${x}`" :x1="x" y1="42" :x2="x" y2="188" />
              <line v-for="y in reportGrid().y" :key="`sy-${y}`" x1="42" :y1="y" x2="678" :y2="y" />
              <line x1="42" y1="188" x2="678" y2="188" class="axis" />
              <line x1="42" y1="42" x2="42" y2="188" class="axis" />
            </g>
            <polyline v-for="scene in scenarioDistribution" :key="scene.name" :points="scenarioLinePoints(scene)" class="scenario-line" />
            <polyline :points="linePoints(controlRows, 'predictedNetLoad', 'scenarioNet')" class="line plan" />
            <g class="axis-labels">
              <text v-for="tick in yTicks(controlRows, 'scenarioNet')" :key="`scene-y-${tick.label}`" x="34" :y="tick.y + 4" class="left-axis-label">{{ tick.label }}</text>
              <text v-for="tick in reportTicks(controlRows)" :key="tick.x" :x="tick.x" y="210">{{ tick.time }}</text>
              <text x="58" y="30">净负荷 MW</text>
            </g>
          </svg>
          <div class="legend report-legend"><span class="plan">中心预测</span><span class="scenario">生成场景</span></div>
          </div>
        </article>
        <article class="panel span-3">
          <h2>输出表：实时控制建议</h2>
          <div class="table-wrap"><table><thead><tr><th>time</th><th>predictedLoad</th><th>predictedWind</th><th>predictedSolar</th><th>suggestedAction</th><th>commandPower</th><th>duration</th><th>confidence</th></tr></thead><tbody><tr v-for="row in controlRows" :key="row.time"><td>{{ row.time }}</td><td>{{ row.predictedLoad }}</td><td>{{ row.predictedWind }}</td><td>{{ row.predictedSolar }}</td><td>{{ row.suggestedAction }}</td><td>{{ row.commandPower }}</td><td>{{ row.duration }}</td><td>{{ row.confidence }}%</td></tr></tbody></table></div>
        </article>
        </template>
      </section>
    </main>
  </div>
</template>
