<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">工单调度台</h1>
      <el-space>
        <el-tag v-if="deviceOnline" type="success">设备在线 {{ deviceCount }}</el-tag>
        <el-tag v-else type="info">无在线设备</el-tag>
        <el-button @click="refreshAll"><el-icon><Refresh /></el-icon> 刷新</el-button>
      </el-space>
    </div>

    <el-alert
      type="info"
      :closable="false"
      title="流程：认领 → 一阶段搜链 → 链接池二阶段（上传即原文比对，可选手动清洗旁白+对白）→ 推送公司核查"
      style="margin-bottom:16px;"
    />

    <div class="stat-grid">
      <div class="stat-card"><div class="stat-value">{{ pendingCount }}</div><div class="stat-label">待认领工单</div></div>
      <div class="stat-card"><div class="stat-value">{{ mineCount }}</div><div class="stat-label">我的进行中</div></div>
      <div class="stat-card"><div class="stat-value">{{ deviceCount }}</div><div class="stat-label">在线设备</div></div>
    </div>

    <el-tabs v-model="activeTab" @tab-change="fetchOrders">
      <el-tab-pane label="待认领" name="pending" />
      <el-tab-pane label="我的进行中" name="mine" />
      <el-tab-pane label="全部" name="all" />
    </el-tabs>

    <div v-loading="loading">
      <div v-for="wo in items" :key="wo.id" class="card queue-card">
        <div class="queue-main">
          <div class="queue-head">
            <span class="order-no">{{ wo.order_no }}</span>
            <el-tag :type="statusTag(wo.status)" size="small">{{ wo.status_label }}</el-tag>
            <el-tag :type="scriptTag(wo.script_status)" size="small" effect="plain">
              {{ wo.script_status_label || scriptLabel(wo.script_status) }}
            </el-tag>
            <el-tag v-if="wo.library_mode_label" size="small" effect="plain">
              {{ wo.library_mode_label }}
            </el-tag>
            <el-tag v-if="wo.priority" type="danger" size="small" effect="plain">P{{ wo.priority }}</el-tag>
          </div>
          <div class="drama">{{ wo.drama_name }}</div>
          <div class="meta">
            链接池 {{ wo.link_pool?.pending_count ?? '—' }} 条待取证 · 证据 {{ wo.evidence_count }} · 已推送 {{ wo.pushed_count }}
            <span v-if="wo.assigned_to"> · {{ wo.assigned_to }}</span>
            <span v-if="wo.script_error" class="script-err"> · {{ wo.script_error }}</span>
          </div>
        </div>
        <div class="queue-actions">
          <el-button
            v-if="activeTab === 'pending' && !wo.assigned_to"
            size="small"
            @click="assign(wo)"
          >认领</el-button>
          <el-button
            v-if="canClean(wo)"
            size="small"
            type="warning"
            :loading="cleaning === wo.id"
            @click="cleanScript(wo)"
          >清洗</el-button>
          <el-button
            v-if="canStartPhase1(wo)"
            type="warning"
            size="small"
            :loading="startingPhase1 === wo.id"
            :disabled="!deviceOnline"
            @click="startPhase1(wo)"
          >一阶段取证</el-button>
          <el-button
            size="small"
            :loading="importing === wo.id"
            @click="importLinks(wo)"
          >同步链接</el-button>
          <el-button
            type="primary"
            size="small"
            @click="goLinkPool(wo)"
          >链接池取证</el-button>
        </div>
      </div>
    </div>

    <div v-if="!loading && !items.length" class="card">
      <div class="empty-state"><div class="empty-text">暂无工单</div></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { workOrderApi, deviceApi, taskApi } from '@/api/index'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const activeTab = ref('pending')
const items = ref([])
const loading = ref(false)
const importing = ref(null)
const startingPhase1 = ref(null)
const cleaning = ref(null)
const pendingCount = ref(0)
const mineCount = ref(0)
const deviceOnline = ref(false)
const deviceCount = ref(0)
const devices = ref([])

function statusTag(s) {
  const map = { submitted: '', collecting: 'warning', partial: 'warning', completed: 'success' }
  return map[s] || 'info'
}

function scriptTag(s) {
  const map = {
    ready: 'success',
    pending: 'warning',
    cleaning: 'warning',
    failed: 'danger',
    none: 'info',
  }
  return map[s] || 'info'
}

function scriptLabel(s) {
  const map = {
    ready: '台词就绪',
    pending: '待装库',
    cleaning: '清洗中',
    failed: '清洗失败',
    none: '缺台词',
  }
  return map[s] || (s || '缺台词')
}

function canClean(wo) {
  const s = wo?.script_status
  return s === 'ready' || s === 'failed' || s === 'pending'
}

function canStartPhase1(wo) {
  // 已认领（含当前员）或「我的进行中」可开一阶段；待认领未认领时先认领
  if (!wo?.drama_name) return false
  if (activeTab.value === 'mine') return true
  if (wo.assigned_to) return true
  return false
}

async function fetchDevices() {
  try {
    const { data } = await deviceApi.list()
    devices.value = data || []
    deviceCount.value = devices.value.length
    deviceOnline.value = deviceCount.value > 0
  } catch {
    devices.value = []
    deviceOnline.value = false
  }
}

async function fetchOrders() {
  loading.value = true
  try {
    const params = { page: 1, page_size: 50 }
    if (activeTab.value === 'pending') params.queue = 'pending'
    else if (activeTab.value === 'mine') {
      params.queue = 'mine'
      params.assigned_to = auth.assignee
    }
    const { data } = await workOrderApi.list(params)
    const rows = data.items || []
    items.value = rows

    const [pRes, mRes] = await Promise.all([
      workOrderApi.list({ queue: 'pending', page_size: 1 }),
      workOrderApi.list({ queue: 'mine', assigned_to: auth.assignee, page_size: 1 }),
    ])
    pendingCount.value = pRes.data?.total || 0
    mineCount.value = mRes.data?.total || 0
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

async function assign(wo) {
  try {
    await workOrderApi.assign(wo.id, auth.assignee)
    ElMessage.success('已认领')
    fetchOrders()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '认领失败')
  }
}

async function cleanScript(wo) {
  cleaning.value = wo.id
  try {
    const { data } = await workOrderApi.cleanScript(wo.id)
    ElMessage.success(data.message || '清洗完成')
    fetchOrders()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '清洗失败')
  } finally {
    cleaning.value = null
  }
}

async function startPhase1(wo) {
  if (!devices.value.length) {
    ElMessage.warning('无在线设备，请先到「设备管理」连接手机')
    return
  }
  const deviceId = devices.value[0].id
  if (!deviceId) {
    ElMessage.warning('设备 ID 无效，请刷新设备列表')
    return
  }
  startingPhase1.value = wo.id
  try {
    const { data: task } = await taskApi.create({
      keyword: wo.drama_name,
      max_videos: 0, // 0 = 全量采集（滑到底为止）
      device_id: deviceId,
      work_order_id: wo.id,
      collect_mode: 'link_first',
      skip_search: false,
      enable_asr: true,
    })
    await taskApi.start(task.id)
    ElMessage.success('一阶段取证已启动（仅抽链接），完成后请到链接池做二阶段')
    router.push(`/collector/tasks/${task.id}`)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '启动一阶段失败')
  } finally {
    startingPhase1.value = null
  }
}

async function importLinks(wo) {
  importing.value = wo.id
  try {
    const { data } = await workOrderApi.importLinks(wo.id, [])
    ElMessage.success(`已同步 ${data.imported || 0} 条链接`)
    fetchOrders()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '同步失败')
  } finally {
    importing.value = null
  }
}

function goLinkPool(wo) {
  const q = { work_order_id: wo.id, keyword: wo.drama_name }
  if (wo.link_pool?.batch_id) q.batch_id = wo.link_pool.batch_id
  router.push({ path: '/collector/link-pool', query: q })
}

function refreshAll() {
  fetchDevices()
  fetchOrders()
}

onMounted(refreshAll)
</script>

<style scoped>
.stat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
.stat-card { background: var(--paper); border: 1px solid var(--line); border-radius: var(--radius); padding: 16px; text-align: center; }
.stat-value { font-size: 28px; font-weight: 800; }
.stat-label { font-size: 12px; color: var(--muted); }
.queue-card { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; margin-bottom: 10px; gap: 16px; flex-wrap: wrap; }
.queue-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.order-no { font-family: var(--font-mono); font-size: 12px; color: var(--muted); }
.drama { font-size: 16px; font-weight: 700; }
.meta { font-size: 12px; color: var(--muted); margin-top: 4px; }
.script-err { color: #c45656; }
.queue-actions { display: flex; gap: 8px; flex-shrink: 0; flex-wrap: wrap; }
</style>
