import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({
  baseURL: '/api',
  timeout: 120000,  // 2分钟，设备操作和任务启动可能较慢
})

request.interceptors.response.use(
  (response) => response,
  (error) => {
    // 不弹错误提示的情况：
    // 1. 请求中配置了 suppressError
    // 2. 404 — 页面自行处理"不存在"
    const suppressError = error.config?.suppressError !== false
      ? error.config?.suppressError || error.response?.status === 404
      : false

    if (suppressError) {
      return Promise.reject(error)
    }

    const message = error.response?.data?.detail || error.message || '请求失败'
    ElMessage.error(message)
    return Promise.reject(error)
  }
)

export default request
