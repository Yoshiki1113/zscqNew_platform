<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ pageTitle }}</h1>
        <p class="page-subtitle">{{ pageSubtitle }}</p>
      </div>
      <el-select v-model="statusFilter" placeholder="状态筛选" clearable style="width:140px;" @change="loadTasks">
        <el-option label="全部" value="" />
        <el-option label="运行中" value="running" />
        <el-option label="准备中" value="preparing" />
        <el-option label="已完成" value="completed" />
        <el-option label="链接已收集" value="links_collected" />
        <el-option label="失败" value="failed" />
        <el-option label="已停止" value="stopped" />
        <el-option label="等待中" value="pending" />
      </el-select>
    </div>

    <div class="card">
      <div class="card-body no-pad">
        <el-table :data="tasks" stripe v-loading="loading">
          <el-table-column label="任务ID" width="80">
            <template #default="{row}"><span class="font-mono">#{{ row.id }}</span></template>
          </el-table-column>
          <el-table-column prop="keyword" label="任务名称" min-width="150" />
          <el-table-column label="阶段" width="90">
            <template #default="{row}">
              <el-tag v-if="row.collect_mode !== 'link_first'" size="small">标准</el-tag>
              <el-tag v-else-if="row.evidence_count > 0 || row.status === 'completed'" type="warning" size="small">二阶段</el-tag>
              <el-tag v-else type="primary" size="small">一阶段</el-tag>
            </template>
          </el-table-column>
          <!-- 二阶段：显示视频数和证据 -->
          <template v-if="!isPhase1">
            <el-table-column prop="max_videos" label="视频数" width="80" align="center" />
            <el-table-column prop="evidence_count" label="证据" width="70" align="center" />
          </template>
          <el-table-column label="状态" width="120">
            <template #default="{row}">
              <el-tag v-if="row.status==='completed'" type="success" size="small">已完成</el-tag>
              <el-tag v-else-if="row.status==='running'" type="warning" size="small">运行中</el-tag>
              <el-tag v-else-if="row.status==='failed'" type="danger" size="small">失败</el-tag>
              <el-tag v-else-if="row.status==='stopped'" type="info" size="small">已停止</el-tag>
              <el-tag v-else-if="row.status==='preparing'" type="primary" size="small">准备中</el-tag>
              <el-tag v-else-if="row.status==='links_collected'" type="success" size="small">链接已收集</el-tag>
              <el-tag v-else type="info" size="small">{{ row.status || '等待中' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="170">
            <template #default="{row}">{{ formatDateTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="130" fixed="right">
            <template #default="{row}">
              <div style="display:flex;align-items:center;gap:4px;">
                <el-button size="small" text type="primary" @click.stop="goTask(row)">查看</el-button>
                <el-button size="small" text type="danger" @click.stop="deleteTask(row)">删除</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!loading && !tasks.length" class="empty-state">
          <div class="empty-icon"><el-icon><DocumentRemove /></el-icon></div>
          <div class="empty-text">暂无任务</div>
        </div>
      </div>
      <div class="card-body" style="padding-top:8px;display:flex;justify-content:center;" v-if="total > pageSize">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          @current-change="loadTasks"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DocumentRemove } from '@element-plus/icons-vue'
import { taskApi } from '@/api/index'
import { formatDateTime } from '@/utils/time'

const router = useRouter()
const route = useRoute()
const tasks = ref([])
const loading = ref(false)
const page = ref(1)
const total = ref(0)
const pageSize = 30
const statusFilter = ref('')

const currentPhase = computed(() => parseInt(route.query.phase) || 0)
const isPhase1 = computed(() => currentPhase.value === 1)
const isPhase2 = computed(() => currentPhase.value === 2)
const pageTitle = computed(() => {
  if (isPhase1.value) return '一阶段任务列表'
  if (isPhase2.value) return '二阶段任务列表'
  return '任务列表'
})
const pageSubtitle = computed(() => {
  if (isPhase1.value) return '查看链接采集任务及状态'
  if (isPhase2.value) return '查看视频取证任务及状态'
  return '查看所有取证任务及状态'
})

async function loadTasks() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize }
    if (statusFilter.value) params.status = statusFilter.value
    if (currentPhase.value) params.phase = currentPhase.value
    const { data } = await taskApi.list(params)
    tasks.value = data?.items || data || []
    total.value = data?.total || 0
  } catch {
    tasks.value = []
  } finally {
    loading.value = false
  }
}

function goTask(row) {
  router.push(`/tasks/${row.id}`)
}

async function deleteTask(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除任务 #${row.id}「${row.keyword}」吗？关联的证据记录和链接也将被删除。`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    await taskApi.delete(row.id)
    ElMessage.success('任务已删除')
    await loadTasks()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

watch(currentPhase, () => { page.value = 1; loadTasks() })
onMounted(loadTasks)
</script>
