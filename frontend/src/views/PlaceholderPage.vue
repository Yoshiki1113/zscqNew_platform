<template>
  <div class="placeholder-shell">
    <header class="placeholder-header">
      <router-link to="/login" class="brand-link">嘉剧荟</router-link>
      <RoleSwitcher variant="header" />
    </header>
    <div class="page-container placeholder-page">
      <div class="placeholder-inner">
        <div class="placeholder-icon">
          <el-icon :size="48"><Clock /></el-icon>
        </div>
        <h1>{{ title }}</h1>
        <p>{{ subtitle }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Clock } from '@element-plus/icons-vue'
import RoleSwitcher from '@/components/RoleSwitcher.vue'

const route = useRoute()
const title = computed(() => route.meta.placeholderTitle || '功能规划中')
const subtitle = computed(() => route.meta.placeholderDesc || '该模块将在后续版本开放，敬请期待。')
</script>

<style scoped>
.placeholder-shell { min-height: 100vh; background: var(--bg); }
.placeholder-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  background: var(--paper);
  border-bottom: 1px solid var(--line);
}
.brand-link { font-weight: 800; font-size: 16px; color: var(--ink); }
.placeholder-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 48px);
}

.placeholder-inner {
  text-align: center;
  max-width: 400px;
}

.placeholder-icon {
  width: 88px;
  height: 88px;
  margin: 0 auto 20px;
  background: var(--primary-bg);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary);
}

.placeholder-inner h1 {
  font-size: 22px;
  font-weight: 700;
  color: var(--ink);
  margin-bottom: 8px;
}

.placeholder-inner p {
  font-size: 14px;
  color: var(--muted);
  margin-bottom: 24px;
  line-height: 1.6;
}
</style>
