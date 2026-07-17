import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const ROLE_KEY = 'platform_role'
const ASSIGNEE_KEY = 'platform_assignee'

export const ROLES = {
  police: { id: 'police', label: '公安端', desc: '态势感知与线索查阅', home: '/police' },
  company: { id: 'company', label: '公司端', desc: '工单提交与进度跟踪', home: '/company' },
  collector: { id: 'collector', label: '取证端', desc: '工单调度与采集执行', home: '/collector' },
  copyright: { id: 'copyright', label: '版权端', desc: '功能规划中', home: '/copyright' },
  culture: { id: 'culture', label: '文旅端', desc: '功能规划中', home: '/culture' },
}

export const useAuthStore = defineStore('auth', () => {
  const role = ref(localStorage.getItem(ROLE_KEY) || '')
  const assignee = ref(localStorage.getItem(ASSIGNEE_KEY) || '取证员')

  const roleInfo = computed(() => ROLES[role.value] || null)
  const isLoggedIn = computed(() => !!role.value && !!ROLES[role.value])

  function login(selectedRole, name = '') {
    if (!ROLES[selectedRole]) return false
    role.value = selectedRole
    localStorage.setItem(ROLE_KEY, selectedRole)
    if (selectedRole === 'collector') {
      assignee.value = name || '取证员'
      localStorage.setItem(ASSIGNEE_KEY, assignee.value)
    }
    return true
  }

  function logout() {
    role.value = ''
    localStorage.removeItem(ROLE_KEY)
  }

  function switchRole(newRole) {
    if (!ROLES[newRole]) return
    role.value = newRole
    localStorage.setItem(ROLE_KEY, newRole)
  }

  return { role, assignee, roleInfo, isLoggedIn, login, logout, switchRole }
})
