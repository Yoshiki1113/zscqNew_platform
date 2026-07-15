<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">取证工作台</h1>
        <p class="page-subtitle">一键发起短剧知识产权侵权证据采集</p>
      </div>
      <el-tag v-if="devices.length" type="success" effect="light" round>环境就绪</el-tag>
      <el-tag v-else type="warning" effect="light" round>等待设备</el-tag>
    </div>

    <el-row :gutter="20">
      <!-- 新建任务 -->
      <el-col :span="14">
        <div class="card">
          <div class="card-header">
            <span class="flex-center">
              <span class="header-icon"><el-icon><EditPen /></el-icon></span>
              新建取证任务
            </span>
          </div>
          <div class="card-body">
            <el-form :model="form" label-position="top">
              <el-form-item label="目标平台">
                <el-tag type="primary" effect="light">微信视频号</el-tag>
              </el-form-item>
              <el-form-item label="执行设备">
                <el-select v-model="form.deviceId" style="width:100%" placeholder="请选择设备">
                  <el-option
                    v-for="d in devices"
                    :key="d.id"
                    :label="`${d.model || d.id} (${d.ip_address || '无IP'})`"
                    :value="d.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="搜索剧名">
                <el-input v-model="form.keyword" placeholder="如：弃子归来震万城" />
              </el-form-item>
              <el-form-item>
                <el-switch v-model="form.skipSearch" active-text="从当前视频开始采集（跳过搜索）" inactive-text="" />
              </el-form-item>
              <el-form-item label="收集链接数量">
                <el-select v-model="form.maxVideos" style="width:100%">
                  <el-option :value="1" label="1 条" />
                  <el-option :value="2" label="2 条" />
                  <el-option :value="5" label="5 条" />
                  <el-option :value="10" label="10 条" />
                  <el-option :value="0" label="全量采集" />
                </el-select>
                <div style="font-size:12px;color:var(--muted);margin-top:4px;">
                  阶段一只收集链接（约5秒/条），后续在链接池中选择链接并配置取证参数
                </div>
              </el-form-item>
              <el-form-item>
                <el-button
                  type="primary"
                  size="large"
                  style="width:100%"
                  @click="startTask"
                  :loading="creating"
                  :disabled="!form.deviceId"
                >
                  <el-icon v-if="form.deviceId" style="margin-right:6px"><Promotion /></el-icon>
                  {{ form.deviceId ? '开始收集链接' : '请先选择设备' }}
                </el-button>
              </el-form-item>
            </el-form>
          </div>
        </div>
      </el-col>

      <!-- 设备状态面板 -->
      <el-col :span="10">
        <DeviceStatus v-model="form.deviceId" @device-ready="onDeviceReady" />
      </el-col>
    </el-row>

    <!-- 从线索导入链接 -->
    <div v-if="cluesWithLinks > 0" style="margin-top:20px;">
      <div class="card">
        <div class="card-body" style="display:flex;align-items:center;justify-content:space-between;padding:14px 20px;">
          <span style="font-size:13px;color:var(--muted);">
            📋 侵权线索中有 <b>{{ cluesWithLinks }}</b> 条链接可用 —
            前往 <router-link to="/link-pool" style="font-weight:600;">链接池</router-link> 选择链接并创建取证任务
          </span>
          <el-button size="small" @click="$router.push('/link-pool')">前往链接池</el-button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { EditPen, Promotion } from '@element-plus/icons-vue'
import { taskApi, deviceApi, clueApi } from '@/api/index'
import { useAppStore } from '@/stores/app'
import DeviceStatus from '@/components/DeviceStatus.vue'

const router = useRouter()
const appStore = useAppStore()

const form = reactive({
  keyword: '弃子归来震万城',
  maxVideos: 5,
  deviceId: '',
  skipSearch: false,
})

const devices = ref([])
const creating = ref(false)
const cluesWithLinks = ref(0)

async function loadDevices() {
  try {
    const { data } = await deviceApi.list()
    devices.value = data || []
    if (!form.deviceId && devices.value.length > 0) {
      form.deviceId = devices.value[0].id
    }
  } catch (e) {
    devices.value = []
  }
}

function onDeviceReady(ready) {}

async function startTask() {
  if (!form.deviceId) {
    ElMessage.warning('请先选择执行设备')
    return
  }
  if (!form.keyword.trim()) {
    ElMessage.warning('请输入搜索剧名')
    return
  }
  creating.value = true
  try {
    const { data } = await taskApi.create({
      keyword: form.keyword,
      max_videos: form.maxVideos,
      hold_seconds: 240,
      capture_method: 'scrcpy',
      device_id: form.deviceId,
      enable_asr: true,
      skip_search: form.skipSearch,
      collect_mode: 'link_first',
    })
    ElMessage.success(`任务 #${data.id} 已创建`)
    appStore.setLastTaskId(data.id)
    try {
      await taskApi.start(data.id)
    } catch (e) {
      ElMessage.error('任务启动失败: ' + (e.response?.data?.detail || e.message))
    }
    router.push(`/tasks/${data.id}`)
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    creating.value = false
  }
}

async function loadCluesLinkCount() {
  try {
    const { data } = await clueApi.withLinks()
    cluesWithLinks.value = data?.with_links || 0
  } catch {}
}


onMounted(() => {
  loadDevices()
  loadCluesLinkCount()
})
</script>
