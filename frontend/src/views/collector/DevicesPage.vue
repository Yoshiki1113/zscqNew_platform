<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">设备管理</h1>
      <el-space>
        <el-button type="primary" @click="scanDevices" :loading="scanning">
          <el-icon><Refresh /></el-icon> 扫描设备
        </el-button>
      </el-space>
    </div>

    <el-row :gutter="20">
      <el-col :span="14">
        <div class="card">
          <div class="card-header">已连接设备</div>
          <div class="card-body" v-loading="loading">
            <el-table :data="devices" stripe empty-text="暂无设备，请点击扫描">
              <el-table-column prop="id" label="序列号" min-width="140" />
              <el-table-column prop="model" label="型号" width="120" />
              <el-table-column prop="ip_address" label="IP" width="130" />
              <el-table-column label="操作" width="200">
                <template #default="{ row }">
                  <el-button size="small" text type="primary" @click="selectDevice(row.id)">选为当前</el-button>
                  <el-button size="small" text @click="checkDevice(row.id)">检测</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>

        <div class="card" style="margin-top:16px;">
          <div class="card-header">WiFi 连接</div>
          <div class="card-body">
            <el-form inline @submit.prevent="connectWifi">
              <el-form-item label="主机">
                <el-input v-model="wifi.host" placeholder="192.168.x.x" style="width:160px;" />
              </el-form-item>
              <el-form-item label="端口">
                <el-input-number v-model="wifi.port" :min="1" :max="65535" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="connectWifi" :loading="connecting">连接</el-button>
                <el-button @click="disconnectWifi" :disabled="!wifi.host">断开</el-button>
              </el-form-item>
            </el-form>
          </div>
        </div>
      </el-col>

      <el-col :span="10">
        <DeviceStatus v-model="selectedDeviceId" />
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { deviceApi } from '@/api/index'
import DeviceStatus from '@/components/DeviceStatus.vue'

const devices = ref([])
const loading = ref(false)
const scanning = ref(false)
const connecting = ref(false)
const selectedDeviceId = ref(localStorage.getItem('selectedDeviceId') || '')

const wifi = reactive({ host: '', port: 5555 })

function selectDevice(id) {
  selectedDeviceId.value = id
  localStorage.setItem('selectedDeviceId', id)
  ElMessage.success('已设为当前设备')
}

async function loadDevices() {
  loading.value = true
  try {
    const { data } = await deviceApi.list()
    devices.value = data || []
    if (!selectedDeviceId.value && devices.value.length) {
      selectDevice(devices.value[0].id)
    }
  } finally {
    loading.value = false
  }
}

async function scanDevices() {
  scanning.value = true
  try {
    const { data } = await deviceApi.scan()
    devices.value = data || []
    ElMessage.success(`扫描完成，发现 ${devices.value.length} 台设备`)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '扫描失败')
  } finally {
    scanning.value = false
  }
}

async function checkDevice(serial) {
  try {
    const { data } = await deviceApi.check(serial)
    ElMessage.info(data?.message || '检测完成')
  } catch (e) {
    ElMessage.error('检测失败')
  }
}

async function connectWifi() {
  if (!wifi.host) {
    ElMessage.warning('请输入主机 IP')
    return
  }
  connecting.value = true
  try {
    await deviceApi.connect(wifi.host, wifi.port)
    ElMessage.success('连接成功')
    await loadDevices()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '连接失败')
  } finally {
    connecting.value = false
  }
}

async function disconnectWifi() {
  try {
    await deviceApi.disconnect(wifi.host)
    ElMessage.success('已断开')
    await loadDevices()
  } catch (e) {
    ElMessage.error('断开失败')
  }
}

onMounted(loadDevices)
</script>
