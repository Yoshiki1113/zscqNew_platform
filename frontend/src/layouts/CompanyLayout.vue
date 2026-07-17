<template>
  <div class="app-layout theme-soft">
    <aside class="app-sidebar">
      <div class="sidebar-logo">
        <div class="logo-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        </div>
        <div class="logo-text">
          嘉剧荟
          <span class="sub">公司工单门户</span>
        </div>
      </div>
      <nav class="sidebar-nav">
        <div class="nav-label">GENERAL</div>
        <router-link to="/company/work-orders/new" class="nav-step" :class="{ active: route.path === '/company/work-orders/new' }">
          <span class="step-icon"><el-icon><Plus /></el-icon></span>
          <span class="step-label">新建工单</span>
        </router-link>
        <router-link to="/company/help-collect" class="nav-step" :class="{ active: route.path === '/company/help-collect' }">
          <span class="step-icon"><el-icon><VideoCamera /></el-icon></span>
          <span class="step-label">帮我取证</span>
        </router-link>

        <div class="nav-label">WORKSPACE</div>
        <router-link to="/company" class="nav-step" :class="{ active: route.path === '/company' }">
          <span class="step-icon"><el-icon><List /></el-icon></span>
          <span class="step-label">工单列表</span>
        </router-link>
        <router-link to="/company/review-pool" class="nav-step" :class="{ active: route.path === '/company/review-pool' || route.path.startsWith('/company/evidence') }">
          <span class="step-icon"><el-icon><Checked /></el-icon></span>
          <span class="step-label">核查池</span>
        </router-link>
      </nav>
    </aside>
    <div class="app-main-wrapper">
      <header class="app-topbar">
        <h1 class="topbar-title">{{ pageTitle }}</h1>
        <div class="topbar-right">
          <RoleSwitcher variant="header" />
        </div>
      </header>
      <div class="app-main-body">
        <router-view />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { List, Plus, Checked, VideoCamera } from '@element-plus/icons-vue'
import RoleSwitcher from '@/components/RoleSwitcher.vue'

const route = useRoute()
const pageTitle = computed(() => route.meta?.title || '公司端')
</script>
