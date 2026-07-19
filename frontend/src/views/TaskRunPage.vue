<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">任务 #{{ task.id || $route.params.id }}</h1>
        <p class="page-subtitle">{{ task.keyword || '加载中...' }}</p>
      </div>
      <el-space>
        <el-tag :type="statusConfig.tagType" :effect="statusConfig.tagEffect">{{ statusConfig.tag }}</el-tag>
        <el-button v-if="actionButtons.showStop" type="danger" size="small" @click="stopTask" :loading="stopping">停止</el-button>
        <el-button v-if="actionButtons.showStart" type="primary" size="small" @click="startTask" :loading="starting">开始执行</el-button>
        <template v-if="actionButtons.showPhase2">
          <el-button type="primary" size="small" @click="startPhase2" :loading="startingPhase2">直接采集这批链接</el-button>
          <el-button size="small" @click="$router.push('/collector/link-pool')">去链接池合并更多</el-button>
        </template>
        <el-button
          v-if="actionButtons.showResumePhase2"
          type="primary"
          size="small"
          @click="resumePhase2"
          :loading="resumingPhase2"
        >断点续采</el-button>
        <el-button v-if="actionButtons.showRetry" size="small" @click="retryTask" :loading="retrying">重试</el-button>
        <el-button v-if="actionButtons.showEvidence" size="small" @click="$router.push('/evidence')">查看证据</el-button>
      </el-space>
    </div>

    <!-- 任务不存在 -->
    <div v-if="taskNotFound" class="card">
      <div class="empty-state">
        <div class="empty-icon"><el-icon><DocumentRemove /></el-icon></div>
        <div class="empty-text" style="font-size:16px;font-weight:600;margin-bottom:8px;">任务不存在</div>
        <div class="empty-text" style="margin-bottom:20px;">任务 #{{ $route.params.id }} 可能已被删除或尚未创建</div>
        <el-button type="primary" @click="$router.push('/')">返回首页创建任务</el-button>
      </div>
    </div>

    <template v-if="!taskNotFound">

    <!-- 任务结束 banner -->
    <div v-if="taskBanner.visible" :class="['task-banner', taskBanner.type]">
      <div class="banner-icon">
        <el-icon v-if="taskBanner.type === 'completed'" :size="28"><CircleCheckFilled /></el-icon>
        <el-icon v-else-if="taskBanner.type === 'failed'" :size="28"><CircleCloseFilled /></el-icon>
        <el-icon v-else :size="28"><WarningFilled /></el-icon>
      </div>
      <div class="banner-body">
        <div class="banner-title">{{ taskBanner.title }}</div>
        <div class="banner-desc">{{ taskBanner.desc }}</div>
      </div>
      <div class="banner-actions">
        <el-button v-if="taskBanner.type === 'completed'" type="primary" @click="$router.push('/evidence')">查看证据列表</el-button>
        <el-button v-if="taskBanner.type === 'completed'" @click="$router.push('/collector/review-pool')">去审核</el-button>
        <el-button
          v-if="['failed','stopped'].includes(taskBanner.type) && actionButtons.showResumePhase2"
          type="primary"
          @click="resumePhase2"
          :loading="resumingPhase2"
        >断点续采</el-button>
        <el-button
          v-else-if="['failed','stopped'].includes(taskBanner.type)"
          type="primary"
          @click="retryTask"
        >重新执行</el-button>
      </div>
    </div>

    <!-- 进度概览 -->
    <div class="card">
      <div class="card-body">
        <div class="stat-grid" style="margin-bottom:0;">
          <div class="stat-card">
          <div class="stat-value text-primary">{{ collectedCount }}{{ task.max_videos > 0 ? ' / ' + task.max_videos : '' }}</div>
          <div class="stat-label">{{ collectedLabel }}</div>
          </div>
          <div class="stat-card success">
            <div class="stat-value text-success">{{ elapsedTime }}</div>
            <div class="stat-label">已用时间</div>
          </div>
          <div class="stat-card">
          <div class="stat-value">{{ currentProcessingText }}</div>
          <div class="stat-label">当前处理</div>
          </div>
          <div class="stat-card warning">
            <div class="stat-value text-warning">{{ phaseLabel }}</div>
            <div class="stat-label">当前阶段</div>
          </div>
        </div>
        <div style="margin-top:16px;">
          <div class="progress-bar">
            <div
              :class="['fill', task.status === 'completed' ? 'success' : '']"
              :style="{ width: progressPercent + '%' }"
            ></div>
          </div>
          <div style="margin-top:6px;font-size:12px;color:var(--muted);text-align:center;">{{ progressText }}</div>
        </div>
      </div>
    </div>

    <!-- 实时日志 + 截图 + 摘要 -->
    <div class="detail-layout">
      <!-- 左：实时日志 -->
      <div>
        <div class="card">
          <div class="card-header">
            <span class="flex-center">
              <span class="header-icon"><el-icon><Tickets /></el-icon></span>
              实时日志
            </span>
            <span style="font-size:12px;" :style="{ color: wsConnected ? 'var(--success)' : 'var(--danger)' }">
              {{ wsConnected ? '● 连接中' : '● 未连接' }}
            </span>
          </div>
          <div class="card-body no-pad">
            <div class="log-terminal" ref="logTerminal">
              <div v-for="(log, i) in logs" :key="i" :class="logClass(log.level)">
                <span class="time">{{ log.timestamp ? '[' + log.timestamp + ']' : '' }}</span> {{ log.message }}
              </div>
              <div v-if="!logs.length" style="color:#5a5d63;padding:20px;text-align:center;">
                {{ wsConnected ? '等待日志...' : '正在连接...' }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右：截图 + 摘要 -->
      <div>
        <!-- 当前截图 -->
        <div class="card">
          <div class="card-header">
            <span class="flex-center">
              <span class="header-icon"><el-icon><Camera /></el-icon></span>
              当前截图
            </span>
          </div>
          <div class="card-body">
            <div class="shot-grid" v-if="recentShots.length">
              <div v-for="(shot, i) in recentShots" :key="i" class="shot-card" @click="previewFile(shot.path)">
                <img :src="`/files/${shot.path}`" v-if="shot.path" />
                <div v-else style="height:200px;background:#0D1117;display:flex;align-items:center;justify-content:center;color:#555;font-size:14px;">
                  {{ shot.icon }}
                </div>
                <div class="label">{{ shot.label }}</div>
              </div>
            </div>
            <div v-else class="empty-state" style="padding:30px;">
              <div class="empty-text">暂无截图</div>
            </div>
          </div>
        </div>

      </div>
    </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Tickets, Camera, DocumentRemove, CircleCheckFilled, CircleCloseFilled, WarningFilled } from '@element-plus/icons-vue'
import { taskApi } from '@/api/index'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const taskId = computed(() => parseInt(route.params.id) || 0)

const task = ref({})
const taskNotFound = ref(false)
const taskBanner = ref({ visible: false, type: '', title: '', desc: '' })
const logs = ref([])
const recentShots = ref([])
const wsConnected = ref(false)
const starting = ref(false)
const stopping = ref(false)
const retrying = ref(false)
const startingPhase2 = ref(false)
const resumingPhase2 = ref(false)
const collectedCount = ref(0)

const statusConfig = computed(() => {
  const map = {
    running:  { tag: '运行中',   tagType: 'warning', tagEffect: 'light' },
    completed:{ tag: '已完成',   tagType: 'success', tagEffect: 'light' },
    failed:   { tag: '失败',     tagType: 'danger',  tagEffect: 'light' },
    stopped:  { tag: '已停止',   tagType: 'info',    tagEffect: 'light' },
    pending:  { tag: '等待中',   tagType: 'primary', tagEffect: 'light' },
    links_collected: { tag: '链接已收集', tagType: 'success', tagEffect: 'dark' },
  }
  return map[task.value.status] || { tag: task.value.status || '未知', tagType: 'info', tagEffect: 'light' }
})

const phaseLabel = computed(() => {
  if (task.value.status === 'links_collected') return '阶段一完成'
  if (task.value.status === 'completed') return '已完成'
  if (task.value.status === 'running' && task.value.phase === 1) return '阶段一'
  if (task.value.status === 'running' && task.value.phase === 2) return '阶段二'
  if (task.value.status === 'running') return '采集中'
  return '—'
})

const isPhase2 = computed(() => task.value.phase === 2)

const collectedLabel = computed(() => {
  if (task.value.status === 'running' && task.value.phase === 1) return '已收集链接'
  return '已采集视频'
})

const currentProcessingText = computed(() => {
  if (['completed', 'stopped'].includes(task.value.status)) return '已完成'
  if (task.value.status === 'links_collected') return '阶段一完成'
  if (task.value.status === 'running' && task.value.phase === 1) return `第 ${collectedCount.value + 1} 条链接`
  return `第 ${collectedCount.value + 1} 条`
})

const actionButtons = computed(() => {
  const s = task.value.status
  const phase = task.value.phase || 1
  const isPhase2Interrupted = phase === 2 && ['failed', 'stopped'].includes(s)
  return {
    showStop:     s === 'running',
    showStart:    s === 'pending',
    showPhase2:   s === 'links_collected',
    showResumePhase2: isPhase2Interrupted,
    showRetry:    ['failed', 'stopped'].includes(s) && !isPhase2Interrupted,
    showEvidence: s === 'completed',
  }
})
const startTime = ref(null)
const currentTime = ref(Date.now())

let ws = null
let timer = null
let _scrollPending = false
let _heartbeatId = null
let _reconnectCount = 0
const MAX_RECONNECT = 10

const progressPercent = computed(() => {
  if (task.value.status === 'completed') return 100
  if (!task.value.max_videos || task.value.max_videos === 0) {
    return collectedCount.value > 0 ? Math.min(collectedCount.value * 5, 90) : 10
  }
  return Math.min(Math.round((collectedCount.value / task.value.max_videos) * 100), 99)
})

const progressText = computed(() => {
  if (task.value.status === 'completed') return `已完成 — 共采集 ${collectedCount.value} 条视频`
  if (task.value.status === 'running') {
    const label = task.value.phase === 1 ? '已收集' : '已采集'
    if (task.value.max_videos > 0) return `${label} ${collectedCount.value}/${task.value.max_videos} 条`
    return `${label} ${collectedCount.value} 条，继续中...`
  }
  return task.value.status === 'failed' ? `错误: ${task.value.error_message || '未知'}` : ''
})

const elapsedTime = computed(() => {
  if (!startTime.value) return '00:00:00'
  const diff = Math.max(0, Math.floor((currentTime.value - startTime.value) / 1000))
  const h = String(Math.floor(diff / 3600)).padStart(2, '0')
  const m = String(Math.floor((diff % 3600) / 60)).padStart(2, '0')
  const s = String(diff % 60).padStart(2, '0')
  return `${h}:${m}:${s}`
})

async function loadTask() {
  try {
    const { data } = await taskApi.get(taskId.value)
    // 初始化已采集计数（避免刷新后显示 0，WebSocket 日志会继续更新）
    collectedCount.value = data.evidence_count || 0
    task.value = data
    taskNotFound.value = false
    appStore.setLastTaskId(data.id)
    if (data.started_at) startTime.value = new Date(data.started_at).getTime()
  } catch (e) {
    taskNotFound.value = true
    task.value = { id: taskId.value, status: 'not_found' }
  }
}

async function startTask() {
  starting.value = true
  try {
    const { data } = await taskApi.start(taskId.value)
    task.value = data
    startTime.value = Date.now()
    taskBanner.value = { visible: false, type: '', title: '', desc: '' }
    logs.value = []
    collectedCount.value = 0
    ElMessage.success('任务已启动')
    connectWS()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '启动失败')
  } finally {
    starting.value = false
  }
}

async function stopTask() {
  stopping.value = true
  try {
    await taskApi.stop(taskId.value)
    task.value.status = 'stopped'
    ElMessage.warning('正在停止任务...')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '停止失败')
  } finally {
    stopping.value = false
  }
}

async function retryTask() {
  retrying.value = true
  try {
    await taskApi.retry(taskId.value)
    task.value.status = 'pending'
    task.value.error_message = ''
    taskBanner.value = { visible: false, type: '', title: '', desc: '' }
    ElMessage.success('任务已重置，可以重新开始')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '重试失败')
  } finally {
    retrying.value = false
  }
}

async function startPhase2() {
  startingPhase2.value = true
  try {
    await taskApi.startPhase2(taskId.value, {
      hold_seconds: task.value.hold_seconds || 240,
      capture_method: 'scrcpy',
      enable_asr: task.value.enable_asr !== false,
    })
    task.value.status = 'running'
    task.value.phase = 2
    taskBanner.value = { visible: false, type: '', title: '', desc: '' }
    logs.value = []
    collectedCount.value = 0
    startTime.value = Date.now()
    ElMessage.success('阶段二已启动')
    connectWS()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '启动阶段二失败')
  } finally {
    startingPhase2.value = false
  }
}

async function resumePhase2() {
  resumingPhase2.value = true
  try {
    const { data } = await taskApi.startPhase2(taskId.value, {
      hold_seconds: task.value.hold_seconds || 240,
      capture_method: 'scrcpy',
      enable_asr: task.value.enable_asr !== false,
      resume: true,
    })
    task.value.status = 'running'
    task.value.phase = 2
    task.value.error_message = ''
    taskBanner.value = { visible: false, type: '', title: '', desc: '' }
    logs.value = []
    // 保留已采计数，便于进度展示
    collectedCount.value = task.value.evidence_count || collectedCount.value || 0
    startTime.value = Date.now()
    const n = data?.orphans_deleted || 0
    ElMessage.success(n > 0 ? `断点续采已启动（已清除中断半截文件 ${n} 个）` : '断点续采已启动')
    connectWS()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '断点续采失败')
  } finally {
    resumingPhase2.value = false
  }
}

function connectWS() {
  if (ws) ws.close()
  if (_heartbeatId) { clearInterval(_heartbeatId); _heartbeatId = null }
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${location.hostname}:8000/ws/tasks/${taskId.value}`
  ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    wsConnected.value = true
    _reconnectCount = 0
    _heartbeatId = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send('ping')
    }, 30000)
  }

  ws.onmessage = async (event) => {
    try {
      const entry = JSON.parse(event.data)
      if (entry.type === 'pong') return
      logs.value.push(entry)
      if (logs.value.length > 500) logs.value.splice(0, logs.value.length - 500)

      // 截图推送
      if (entry.message && entry.message.includes('[截图]')) {
        const m = entry.message.match(/\[截图\]\s+([A-Za-z]:\\[^\s]+\.(png|jpg))/i)
        if (m) {
          const absPath = m[1]
          const idx = absPath.indexOf('evidence_data')
          const relPath = idx >= 0 ? absPath.slice(idx + 'evidence_data/'.length).replace(/\\/g, '/') : absPath.replace(/\\/g, '/').split('/').slice(-2).join('/')
          if (!recentShots.value.find(s => s.path === relPath)) {
            recentShots.value.push({ path: relPath, label: shotLabel(relPath) })
            if (recentShots.value.length > 9) recentShots.value.shift()
          }
        }
      }

      // 实时进度计数（阶段一"已收集链接" + 阶段二"已采集"）
      if (entry.message) {
        let m = entry.message.match(/已采集:\s*(\d+)\s*条/)
        if (!m) m = entry.message.match(/已收集链接:\s*(\d+)\s*条/)
        if (m) collectedCount.value = parseInt(m[1])
      }

      if (entry.type === 'done') {
        collectedCount.value = entry.records || collectedCount.value
        // 从 API 重新加载任务状态，而不是猜测
        try {
          const { data } = await taskApi.get(taskId.value)
          task.value = data
        } catch {}
        taskBanner.value = {
          visible: true,
          type: task.value.status,
          title: task.value.status === 'completed' ? '🎉 任务执行完成'
               : task.value.status === 'links_collected' ? '📋 阶段一完成 — 链接已收集'
               : task.value.status === 'failed' ? '❌ 任务执行失败'
               : '⏹ 任务已停止',
          desc: entry.message || (task.value.status === 'completed' ? `共采集 ${collectedCount.value} 条证据`
                               : task.value.status === 'links_collected' ? '请选择链接后启动阶段二'
                               : ''),
        }
      }

      if (!_scrollPending) {
        _scrollPending = true
        requestAnimationFrame(() => {
          const el = document.querySelector('.log-terminal')
          if (el) el.scrollTop = el.scrollHeight
          _scrollPending = false
        })
      }
    } catch (e) {}
  }

  ws.onclose = () => {
    wsConnected.value = false
    if (_heartbeatId) { clearInterval(_heartbeatId); _heartbeatId = null }
    if (_reconnectCount < MAX_RECONNECT && task.value.status === 'running') {
      _reconnectCount++
      setTimeout(connectWS, 5000)
    }
  }

  ws.onerror = () => { wsConnected.value = false }
}

function startTimer() {
  timer = setInterval(() => {
    if (task.value.status === 'running' || task.value.status === 'pending') {
      currentTime.value = Date.now()
    }
  }, 1000)
}

onMounted(async () => {
  if (taskId.value === 0) {
    try {
      const { data } = await taskApi.list({ page_size: 1 })
      const recent = data?.items?.[0] || data?.[0]
      if (recent && recent.id) {
        router.replace(`/collector/tasks/${recent.id}`)
        return
      }
    } catch {}
    taskNotFound.value = true
    task.value = { id: 0, status: 'not_found' }
    return
  }
  await loadTask()
  startTimer()
  if (!taskNotFound.value) connectWS()
})

onUnmounted(() => {
  if (ws) ws.close()
  if (timer) clearInterval(timer)
  if (_heartbeatId) clearInterval(_heartbeatId)
})

function shotLabel(path) {
  const name = (path || '').split(/[/\\]/).pop()?.toLowerCase() || ''
  if (name.startsWith('play_')) return '视频播放页'
  if (name.startsWith('share_sheet_')) return '分享面板'
  if (name.startsWith('share_copy_')) return '复制链接区域'
  if (name.startsWith('profile_card_name_region_')) return '博主名称裁剪'
  if (name.startsWith('profile_card_')) return '博主资料卡'
  if (name.startsWith('profile_info_')) return '博主更多信息'
  if (name.startsWith('traffic_marker_region_')) return '引流标记裁剪'
  if (name.startsWith('traffic_marker_full_')) return '引流标记整页'
  if (name.startsWith('traffic_popup_')) return '引流弹窗'
  if (name.startsWith('traffic_landing_')) return '引流落地页'
  if (name.startsWith('traffic_page_name_region_')) return '引流账号名称裁剪'
  if (name.startsWith('traffic_page_')) return '引流账号资料页'
  if (name.startsWith('traffic_info_')) return '引流账号更多信息'
  if (name.startsWith('_video_page_probe')) return '探测截图'
  return name
}

function logClass(level) {
  if (level === 'success') return 'ok'
  if (level === 'warning') return 'warn'
  if (level === 'error') return 'err'
  return ''
}

function previewFile(path) {
  if (path) window.open(`/files/${path}`, '_blank')
}
</script>

<style scoped>
/* ── 任务结束 Banner ── */
.task-banner {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  border-radius: var(--radius);
  margin-bottom: 20px;
  border: 1px solid transparent;
}

.task-banner.completed {
  background: linear-gradient(135deg, #e6f7ed 0%, #f0fdf4 100%);
  border-color: #86efac;
}

.task-banner.failed {
  background: linear-gradient(135deg, #fee2e2 0%, #fef2f2 100%);
  border-color: #fca5a5;
}

.task-banner.stopped {
  background: linear-gradient(135deg, #fef3c7 0%, #fffbeb 100%);
  border-color: #fcd34d;
}

.task-banner.links_collected {
  background: linear-gradient(135deg, #e0f2fe 0%, #f0f9ff 100%);
  border-color: #7dd3fc;
}

.banner-icon {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}

.task-banner.completed .banner-icon {
  background: #22c55e20;
  color: #16a34a;
}

.task-banner.failed .banner-icon {
  background: #ef444420;
  color: #dc2626;
}

.task-banner.stopped .banner-icon {
  background: #f59e0b20;
  color: #d97706;
}

.task-banner.links_collected .banner-icon {
  background: #0ea5e920;
  color: #0284c7;
}

.banner-body { flex: 1; }

.banner-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--ink);
  margin-bottom: 4px;
}

.banner-desc {
  font-size: 13px;
  color: var(--muted);
}

.banner-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.shot-card img {
  object-fit: contain;
  height: 200px;
}
.shot-card .label {
  display: none;
}
</style>
