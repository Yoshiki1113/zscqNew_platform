<template>
  <div class="app-layout">
    <!-- 左侧导航栏 -->
    <aside class="app-sidebar">
      <div class="sidebar-logo">
        <div class="logo-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        </div>
        <div class="logo-text">
          嘉剧荟
          <span class="sub">短剧侵权识别平台</span>
        </div>
      </div>

      <nav class="sidebar-nav">
        <div class="nav-label">阶段一 · 采集链接</div>
        <router-link to="/" class="nav-step" :class="{ active: route.path === '/' }">
          <span class="step-icon" v-html="svgHome"></span>
          <span class="step-label">新建任务</span>
        </router-link>
        <router-link to="/link-pool" class="nav-step" :class="{ active: route.path === '/link-pool' }">
          <span class="step-icon" v-html="svgLink"></span>
          <span class="step-label">链接池</span>
        </router-link>
        <router-link to="/tasks?phase=1" class="nav-step" :class="{ active: route.path === '/tasks' && route.query.phase === '1' }">
          <span class="step-icon" v-html="svgDoc"></span>
          <span class="step-label">一阶段任务</span>
        </router-link>

        <div class="nav-label" style="margin-top: 14px;">阶段二 · 视频取证</div>
        <router-link to="/tasks?phase=2" class="nav-step" :class="{ active: route.path === '/tasks' && route.query.phase === '2' }">
          <span class="step-icon" v-html="svgDoc"></span>
          <span class="step-label">二阶段任务</span>
        </router-link>

        <div class="nav-label" style="margin-top: 14px;">执行监控</div>
        <router-link :to="monitorPath" class="nav-step" :class="{ active: route.path.startsWith('/tasks/') && !route.path.startsWith('/tasks?') }">
          <span class="step-icon" v-html="svgMonitor"></span>
          <span class="step-label">执行监控</span>
        </router-link>

        <div class="nav-label" style="margin-top: 14px;">审核分析</div>
        <router-link to="/evidence" class="nav-step" :class="{ active: route.path.startsWith('/evidence') }">
          <span class="step-icon" v-html="svgDoc"></span>
          <span class="step-label">证据列表</span>
        </router-link>
        <router-link to="/review-pool" class="nav-step" :class="{ active: route.path === '/review-pool' }">
          <span class="step-icon" v-html="svgCheck"></span>
          <span class="step-label">复核池</span>
        </router-link>
        <router-link to="/authors" class="nav-step" :class="{ active: route.path === '/authors' }">
          <span class="step-icon" v-html="svgUser"></span>
          <span class="step-label">博主聚合</span>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <div class="device-status">
          <span :class="['device-dot', deviceOnline ? '' : 'offline']"></span>
          <span>{{ deviceOnline ? deviceName : '等待设备连接' }}</span>
        </div>
        <div v-if="deviceOnline" class="device-ip">{{ deviceIP }}</div>
      </div>
    </aside>

    <!-- 右侧内容区 -->
    <div class="app-main-wrapper">
      <router-view />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { deviceApi } from '@/api/index'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const appStore = useAppStore()

const monitorPath = computed(() => appStore.lastTaskId ? `/tasks/${appStore.lastTaskId}` : '/tasks/0')

const svgHome = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>'
const svgMonitor = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>'
const svgDoc = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>'
const svgCheck = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>'
const svgUser = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>'
const svgLink = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>'

// 侧边栏设备状态
const deviceOnline = ref(false)
const deviceName = ref('')
const deviceIP = ref('')
let _deviceTimer = null

async function checkDeviceStatus() {
  try {
    const { data } = await deviceApi.list()
    if (data && data.length > 0) {
      deviceOnline.value = true
      deviceName.value = data[0].model || data[0].id || '未知设备'
      deviceIP.value = data[0].ip_address || ''
    } else {
      deviceOnline.value = false
      deviceName.value = ''
    }
  } catch {
    deviceOnline.value = false
    deviceName.value = ''
  }
}

onMounted(() => {
  checkDeviceStatus()
  _deviceTimer = setInterval(checkDeviceStatus, 120000)
})

onUnmounted(() => {
  if (_deviceTimer) clearInterval(_deviceTimer)
})
</script>
