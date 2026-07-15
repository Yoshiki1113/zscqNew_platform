<template>
  <div class="device-status-panel">
    <!-- 前置环境检查 -->
    <div class="card">
      <div class="card-header">
        <span class="flex-center">
          <span class="header-icon"><el-icon><CircleCheck /></el-icon></span>
          前置环境检查
        </span>
        <el-button size="small" @click="refreshChecks" :loading="checkLoading">刷新检查</el-button>
      </div>
      <div class="card-body">
        <div v-if="!selectedDevice" class="empty-hint">
          请先在下方选择一个 ADB 设备
        </div>
        <template v-else>
          <div class="checks-grid">
            <div v-for="item in checkItems" :key="item.key" class="check-item">
              <el-icon :class="item.ok ? 'check-ok' : 'check-fail'">
                <CircleCheckFilled v-if="item.ok" />
                <CircleCloseFilled v-else />
              </el-icon>
              <span class="check-label">{{ item.label }}</span>
              <span class="check-value">{{ item.value || (item.ok ? '正常' : '异常') }}</span>
            </div>
          </div>
          <el-alert
            v-if="allChecksPassed"
            type="success"
            :closable="false"
            style="margin-top:12px;"
          >
            所有检查项通过，可以发起取证
          </el-alert>
          <el-alert
            v-else
            type="warning"
            :closable="false"
            style="margin-top:12px;"
          >
            部分检查项未通过，请确认设备状态
          </el-alert>
          <!-- AScript 录屏授权（独立检查，较慢，单独按钮触发） -->
          <div class="ascript-auth-section">
            <div class="ascript-auth-row">
              <span class="ascript-auth-label">AScript 录屏授权</span>
              <el-tag v-if="ascriptConnected === true" type="success" size="small" effect="light">已授权</el-tag>
              <el-tag v-else-if="ascriptConnected === false" type="warning" size="small" effect="light">未授权</el-tag>
              <el-tag v-else type="info" size="small" effect="plain">未检查</el-tag>
              <el-button
                size="small"
                type="primary"
                plain
                @click="checkAscript"
                :loading="ascriptChecking"
                :disabled="!checkResults.ascript_port_reachable"
              >
                {{ ascriptConnected === true ? '重新检查' : '检查并授权' }}
              </el-button>
            </div>
            <el-alert
              v-if="ascriptConnected === false"
              type="info"
              :closable="false"
              style="margin-top:8px;"
            >
              手机端可能弹出「要开始使用AScript录屏或投屏吗？」对话框，请点击「允许」后再次点击检查
            </el-alert>
          </div>
        </template>
      </div>
    </div>

    <!-- 设备信息 -->
    <div class="card">
      <div class="card-header">
        <span class="flex-center">
          <span class="header-icon"><el-icon><Iphone /></el-icon></span>
          当前设备
        </span>
        <el-tag v-if="selectedDevice" :type="selectedDevice.status === 'online' ? 'success' : 'danger'" size="small" effect="light">
          {{ selectedDevice.status === 'online' ? '在线' : selectedDevice.status }}
        </el-tag>
      </div>
      <div class="card-body">
        <div v-if="loading" class="empty-hint">正在扫描设备...</div>
        <div v-else-if="!selectedDevice" class="empty-hint">
          未检测到 ADB 设备，请连接手机后刷新
        </div>
        <template v-else>
          <dl class="kv-list">
            <dt>设备型号</dt><dd>{{ selectedDevice.model || selectedDevice.name || selectedDevice.id }}</dd>
            <dt>序列号</dt><dd><code class="font-mono">{{ selectedDevice.id }}</code></dd>
            <dt>Android</dt><dd>{{ selectedDevice.android_version || '未知' }}</dd>
            <dt>连接方式</dt><dd>{{ selectedDevice.connection_mode === 'LocalIP' ? 'WiFi' : selectedDevice.connection_mode || '未知' }} {{ selectedDevice.ip_address ? '(' + selectedDevice.ip_address + ')' : '' }}</dd>
            <dt>分辨率</dt><dd>{{ selectedDevice.screen_width }} × {{ selectedDevice.screen_height }}</dd>
            <dt>最后检测</dt><dd>{{ formatDateTime(selectedDevice.last_checked_at) || '未检测' }}</dd>
          </dl>
        </template>
      </div>
    </div>

    <!-- 设备选择 -->
    <div class="card">
      <div class="card-header">
        <span class="flex-center">
          <span class="header-icon"><el-icon><Monitor /></el-icon></span>
          可用设备
        </span>
        <el-tag size="small" effect="plain">{{ devices.length }}</el-tag>
      </div>
      <div class="card-body" style="padding:8px;">
        <el-radio-group v-model="currentSerial" @change="onDeviceChange" style="width:100%">
          <div v-for="d in devices" :key="d.id" class="device-radio-item">
            <el-radio :value="d.id" border style="width:100%;margin:0;">
              <div class="device-radio-content">
                <span class="device-name">{{ d.model || d.id }}</span>
                <span class="device-meta">{{ d.ip_address || '无IP' }} · {{ d.screen_width }}×{{ d.screen_height }}</span>
              </div>
            </el-radio>
          </div>
        </el-radio-group>
        <div v-if="!devices.length" class="empty-hint">
          暂无设备，<el-button size="small" text type="primary" @click="refreshAll">点击扫描</el-button>
        </div>
      </div>
    </div>

    <!-- WiFi 连接设备 -->
    <div class="card">
      <div class="card-header">
        <span class="flex-center">
          <span class="header-icon"><el-icon><Connection /></el-icon></span>
          连接新设备
        </span>
      </div>
      <div class="card-body">
        <div class="connect-row">
          <el-input
            v-model="connectHost"
            placeholder="手机 IP，如 192.168.1.105"
            size="small"
            clearable
            @keyup.enter="doConnect"
          />
          <el-input
            v-model="connectPort"
            placeholder="端口"
            size="small"
            style="width:80px"
            @keyup.enter="doConnect"
          />
          <el-button size="small" type="primary" @click="doConnect" :loading="connecting">
            连接
          </el-button>
        </div>
        <div class="connect-hint">
          手机需先在开发者选项中开启 <strong>USB 调试</strong> 和 <strong>无线调试</strong>（或先通过 USB 执行 <code>adb tcpip 5555</code>），且与 PC 在同一 WiFi 下
        </div>
        <div v-if="connectError" class="connect-error">{{ connectError }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import {
  CircleCheck, CircleCheckFilled, CircleCloseFilled, Iphone, Monitor, Connection
} from '@element-plus/icons-vue'
import { deviceApi } from '@/api/index'
import { formatDateTime } from '@/utils/time'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: { type: String, default: '' }
})

const emit = defineEmits(['update:modelValue', 'device-ready'])

const devices = ref([])
const currentSerial = ref(props.modelValue)
const selectedDevice = ref(null)
const checkResults = ref({})
const loading = ref(false)
const checkLoading = ref(false)
const ascriptChecking = ref(false)
const ascriptConnected = ref(null)

// 连接新设备
const connectHost = ref('')
const connectPort = ref(5555)
const connecting = ref(false)
const connectError = ref('')

const checkItems = computed(() => {
  const r = checkResults.value
  return [
    { key: 'adb_connected', label: 'ADB 连接', ok: r.adb_connected, value: '' },
    { key: 'wechat_running', label: '视频号已启动', ok: r.wechat_running, value: '' },
    { key: 'screen_on', label: '屏幕点亮', ok: r.screen_on, value: '' },
    { key: 'storage_ok', label: '存储空间', ok: r.storage_ok, value: r.storage_used_pct ? `${r.storage_used_pct}%已用` : '' },
    { key: 'scrcpy_available', label: 'scrcpy 可用', ok: r.scrcpy_available, value: r.scrcpy_path || '' },
    { key: 'ffmpeg_available', label: 'ffmpeg 可用', ok: r.ffmpeg_available, value: r.ffmpeg_path || '' },
    { key: 'ascript_port_reachable', label: 'AScript 端口可达', ok: r.ascript_port_reachable, value: '' },
  ]
})

const allChecksPassed = computed(() => checkResults.value.all_checks_passed)

async function refreshAll() {
  loading.value = true
  try {
    const { data } = await deviceApi.list()
    devices.value = data || []
    if (!currentSerial.value && devices.value.length > 0) {
      currentSerial.value = devices.value[0].id
    }
    updateSelectedDevice()
  } catch (e) {
    devices.value = []
  } finally {
    loading.value = false
  }
}

function updateSelectedDevice() {
  selectedDevice.value = devices.value.find(d => d.id === currentSerial.value) || null
}

function onDeviceChange(val) {
  currentSerial.value = val
  updateSelectedDevice()
  emit('update:modelValue', val)
  ascriptConnected.value = null
  if (val) refreshChecks()
}

async function refreshChecks() {
  if (!currentSerial.value) return
  checkLoading.value = true
  try {
    const { data } = await deviceApi.check(currentSerial.value)
    checkResults.value = data
  } catch (e) {
    checkResults.value = {}
  } finally {
    checkLoading.value = false
  }
}

async function checkAscript() {
  if (!currentSerial.value) return
  ascriptChecking.value = true
  try {
    const { data } = await deviceApi.checkAscript(currentSerial.value)
    ascriptConnected.value = data.ascript_connected
  } catch (e) {
    ascriptConnected.value = false
  } finally {
    ascriptChecking.value = false
  }
}

async function doConnect() {
  const host = connectHost.value.trim()
  if (!host) {
    connectError.value = '请输入手机 IP 地址'
    return
  }
  const port = Number(connectPort.value) || 5555
  connecting.value = true
  connectError.value = ''
  try {
    const { data } = await deviceApi.connect(host, port)
    ElMessage.success(data.message || `已连接 ${host}:${port}`)
    // 刷新设备列表
    devices.value = data.devices || []
    if (!currentSerial.value && devices.value.length > 0) {
      currentSerial.value = devices.value[0].id
      updateSelectedDevice()
      refreshChecks()
    } else {
      updateSelectedDevice()
    }
    connectHost.value = ''
  } catch (e) {
    const msg = e?.response?.data?.detail || e.message || '连接失败'
    connectError.value = msg
    ElMessage.error(msg)
    // 即使失败也刷新一下（可能已有部分连接）
    await refreshAll()
  } finally {
    connecting.value = false
  }
}

onMounted(() => {
  refreshAll().then(() => {
    if (currentSerial.value) refreshChecks()
  })
})

watch(() => props.modelValue, (val) => {
  if (val !== currentSerial.value) {
    currentSerial.value = val
    updateSelectedDevice()
    ascriptConnected.value = null
    if (val) refreshChecks()
  }
})
</script>

<style scoped>
.device-status-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.checks-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.check-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  padding: 4px 0;
}

.check-ok { color: var(--success); font-size: 14px; }
.check-fail { color: var(--danger); font-size: 14px; }

.check-label {
  color: var(--ink);
  min-width: 80px;
}

.check-value {
  color: var(--muted);
  font-size: 11px;
}

.empty-hint {
  text-align: center;
  padding: 20px;
  color: var(--muted);
  font-size: 13px;
}

.device-radio-item {
  margin-bottom: 4px;
}

.device-radio-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.device-name {
  font-size: 13px;
  font-weight: 500;
}

.device-meta {
  font-size: 11px;
  color: var(--muted);
}

.ascript-auth-section {
  margin-top: 12px;
  padding: 10px 12px;
  background: var(--bg, #f6f4ef);
  border-radius: 8px;
  border: 1px solid var(--line, #e4e0d6);
}

.ascript-auth-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ascript-auth-label {
  font-size: 13px;
  color: var(--ink);
  font-weight: 500;
  margin-right: auto;
}

.connect-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.connect-hint {
  margin-top: 8px;
  font-size: 11px;
  color: var(--muted);
  line-height: 1.5;
}

.connect-hint code {
  background: var(--bg, #f6f4ef);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 10px;
}

.connect-error {
  margin-top: 8px;
  font-size: 12px;
  color: var(--danger);
}
</style>
