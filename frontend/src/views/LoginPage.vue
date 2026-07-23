<template>
  <div class="login-page">
    <div class="login-bg"></div>
    <div class="login-panel">
      <div class="login-brand">
        <div class="brand-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="32" height="32"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        </div>
        <h1>嘉剧荟</h1>
        <p>嘉剧荟版权保护智能侦测平台</p>
      </div>

      <div class="role-grid">
        <button
          v-for="r in roleList"
          :key="r.id"
          class="role-card"
          :class="{ selected: selected === r.id }"
          @click="selected = r.id"
        >
          <span class="role-name">{{ r.label }}</span>
          <span class="role-desc">{{ r.desc }}</span>
        </button>
      </div>

      <el-input
        v-if="selected === 'collector'"
        v-model="assigneeName"
        placeholder="取证员姓名（可选）"
        style="margin-bottom: 16px;"
      />

      <el-button type="primary" size="large" class="enter-btn" :disabled="!selected" @click="enter">
        进入系统
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ROLES, useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const roleList = Object.values(ROLES)
const selected = ref(auth.role || 'collector')
const assigneeName = ref(auth.assignee || '取证员')

function enter() {
  if (!selected.value) return
  auth.login(selected.value, assigneeName.value)
  router.push(ROLES[selected.value].home)
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.login-bg {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 80% 60% at 20% 20%, rgba(22, 93, 255, 0.18), transparent),
    radial-gradient(ellipse 60% 50% at 80% 80%, rgba(14, 66, 210, 0.12), transparent),
    linear-gradient(160deg, #0F1B2D 0%, #162236 45%, #1a2d4a 100%);
}

.login-panel {
  position: relative;
  width: min(520px, 92vw);
  padding: 40px 36px;
  background: rgba(255, 255, 255, 0.97);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-xl);
}

.login-brand { text-align: center; margin-bottom: 32px; }

.brand-icon {
  width: 56px;
  height: 56px;
  margin: 0 auto 12px;
  background: linear-gradient(135deg, var(--primary), var(--primary-light));
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

.login-brand h1 {
  font-size: 28px;
  font-weight: 800;
  color: var(--ink);
  letter-spacing: 2px;
}

.login-brand p {
  font-size: 13px;
  color: var(--muted);
  margin-top: 4px;
}

.role-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 20px;
}

.role-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--paper);
  cursor: pointer;
  transition: all var(--transition);
  text-align: left;
}

.role-card:hover { border-color: var(--primary-border); background: var(--primary-bg); }
.role-card.selected { border-color: var(--primary); background: var(--primary-bg); box-shadow: 0 0 0 2px rgba(22,93,255,0.15); }

.role-name { font-size: 14px; font-weight: 700; color: var(--ink); }
.role-desc { font-size: 11px; color: var(--muted); line-height: 1.4; }

.enter-btn { width: 100%; }
</style>
