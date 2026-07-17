<template>
  <div class="role-switcher" :class="variant">
    <el-dropdown trigger="click" @command="onCommand" :placement="variant === 'header' ? 'bottom-end' : 'top-start'">
      <button type="button" class="role-btn" :title="'当前：' + (auth.roleInfo?.label || '未登录')">
        <el-icon class="role-icon"><Switch /></el-icon>
        <span class="role-text">
          <span class="role-label">{{ auth.roleInfo?.label || '未登录' }}</span>
          <span class="role-hint">切换角色</span>
        </span>
        <el-icon class="role-caret"><ArrowDown /></el-icon>
      </button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item disabled class="role-menu-title">选择角色</el-dropdown-item>
          <el-dropdown-item
            v-for="r in roleList"
            :key="r.id"
            :command="r.id"
            :disabled="r.id === auth.role"
          >
            <span class="menu-row">
              <span>{{ r.label }}</span>
              <el-tag v-if="r.id === auth.role" size="small" type="primary" effect="plain">当前</el-tag>
            </span>
          </el-dropdown-item>
          <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowDown, Switch } from '@element-plus/icons-vue'
import { ROLES, useAuthStore } from '@/stores/auth'

defineProps({
  /** sidebar：深色侧栏；header：顶栏右上角 */
  variant: { type: String, default: 'sidebar' },
})

const auth = useAuthStore()
const router = useRouter()
const roleList = computed(() => Object.values(ROLES))

function onCommand(cmd) {
  if (cmd === 'logout') {
    auth.logout()
    router.push('/login')
    return
  }
  auth.switchRole(cmd)
  router.push(ROLES[cmd].home)
}
</script>

<style scoped>
.role-switcher.sidebar { width: 100%; }
.role-switcher.header { width: auto; flex-shrink: 0; }

.role-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: var(--radius);
  cursor: pointer;
  font-family: inherit;
  text-align: left;
  transition: all var(--transition);
}

.role-icon { font-size: 16px; flex-shrink: 0; }
.role-caret { font-size: 12px; margin-left: auto; flex-shrink: 0; opacity: 0.7; }

.role-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.25;
}

.role-label {
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.role-hint {
  font-size: 11px;
  opacity: 0.75;
}

.sidebar .role-btn {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.1);
  color: #fff;
}
.sidebar .role-btn:hover {
  background: rgba(22, 93, 255, 0.35);
  border-color: rgba(22, 93, 255, 0.5);
}
.sidebar .role-hint { color: rgba(255, 255, 255, 0.55); }

.header .role-btn {
  background: var(--paper);
  border-color: var(--line);
  color: var(--ink);
  width: auto;
  min-width: 132px;
  box-shadow: var(--shadow-xs);
}
.header .role-btn:hover {
  border-color: var(--primary-border);
  background: var(--primary-bg);
  color: var(--primary-dark);
}
.header .role-hint { color: var(--muted); }

.menu-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}
</style>
