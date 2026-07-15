import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  /** 最近一个任务的 ID，用于侧边栏"执行监控"链接，持久化到 localStorage */
  const lastTaskId = ref(parseInt(localStorage.getItem('lastTaskId')) || null)

  function setLastTaskId(id) {
    lastTaskId.value = id
    if (id) {
      localStorage.setItem('lastTaskId', String(id))
    } else {
      localStorage.removeItem('lastTaskId')
    }
  }

  return { lastTaskId, setLastTaskId }
})
