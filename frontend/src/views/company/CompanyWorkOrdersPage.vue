<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">工单列表</h1>
      <router-link to="/company/work-orders/new">
        <el-button type="primary"><el-icon><Plus /></el-icon> 新建工单</el-button>
      </router-link>
    </div>

    <div class="card">
      <div class="card-body" style="display:flex;gap:12px;flex-wrap:wrap;">
        <el-select v-model="statusFilter" placeholder="状态筛选" clearable style="width:160px;" @change="fetchData">
          <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-button @click="fetchData"><el-icon><Refresh /></el-icon> 刷新</el-button>
      </div>
    </div>

    <div v-loading="loading">
      <el-table :data="items" stripe @row-click="row => $router.push(`/company/work-orders/${row.id}`)" style="cursor:pointer;">
        <el-table-column prop="order_no" label="工单号" width="180" />
        <el-table-column prop="drama_name" label="剧名" min-width="140" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ row.status_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="80" align="center" />
        <el-table-column prop="evidence_count" label="证据数" width="80" align="center" />
        <el-table-column prop="company_pushed_count" label="核查池" width="80" align="center" />
        <el-table-column prop="pushed_count" label="已推送公安" width="100" align="center" />
        <el-table-column label="提交时间" width="160">
          <template #default="{ row }">{{ formatDateTimeShort(row.submitted_at || row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" text @click.stop="$router.push(`/company/work-orders/${row.id}`)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="total > pageSize" style="text-align:center;margin-top:16px;">
      <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next" @current-change="fetchData" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { workOrderApi } from '@/api/index'
import { formatDateTimeShort } from '@/utils/time'

const items = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const statusFilter = ref('')

const statusOptions = [
  { value: 'draft', label: '草稿' },
  { value: 'submitted', label: '已提交' },
  { value: 'collecting', label: '取证中' },
  { value: 'partial', label: '部分完成' },
  { value: 'completed', label: '已完成' },
  { value: 'closed', label: '已关闭' },
]

function statusTag(s) {
  const map = { draft: 'info', submitted: '', collecting: 'warning', partial: 'warning', completed: 'success', closed: 'info' }
  return map[s] || 'info'
}

async function fetchData() {
  loading.value = true
  try {
    const { data } = await workOrderApi.list({ page: page.value, page_size: pageSize.value, status: statusFilter.value })
    items.value = data.items || []
    total.value = data.total || 0
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
</script>
