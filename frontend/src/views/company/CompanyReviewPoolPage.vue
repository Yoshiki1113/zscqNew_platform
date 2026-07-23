<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">核查池</h1>
        <p class="page-subtitle">按工单查看已推送的待核查证据</p>
      </div>
      <el-space>
        <el-tag type="warning" effect="light" v-if="pendingTotal">待复核 {{ pendingTotal }}</el-tag>
        <el-tag type="primary" effect="light">共 {{ total }} 个工单</el-tag>
        <el-button @click="fetchData"><el-icon><Refresh /></el-icon> 刷新</el-button>
      </el-space>
    </div>

    <div v-loading="loading">
      <div
        v-for="item in items"
        :key="item.id"
        class="card wo-card"
        @click="openDetail(item.id)"
      >
        <div class="wo-main">
          <div class="wo-tags">
            <el-tag size="small" effect="plain">{{ item.order_no }}</el-tag>
            <el-tag :type="statusTag(item.status)" size="small">{{ item.status_label }}</el-tag>
            <span class="text-muted" style="font-size:12px;">
              {{ formatDateTimeShort(item.updated_at || item.submitted_at || item.created_at) }}
            </span>
          </div>
          <div class="wo-title">{{ item.drama_name || '未命名剧目' }}</div>
          <div class="wo-meta">
            已送核查 {{ item.company_pushed_count || 0 }} 条
            <template v-if="item.review_pending_count">
              · 待复核 {{ item.review_pending_count }}
            </template>
          </div>
        </div>
        <div class="wo-actions" @click.stop>
          <el-button size="small" type="primary" @click="openDetail(item.id)">进入复核</el-button>
        </div>
      </div>
    </div>

    <div v-if="!loading && !items.length" class="card">
      <div class="empty-state">
        <div class="empty-text">暂无已推送核查的工单，请等待取证员推送二阶段结果</div>
      </div>
    </div>

    <div v-if="total > pageSize" style="text-align:center;margin-top:16px;">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        @current-change="fetchData"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh } from '@element-plus/icons-vue'
import { workOrderApi } from '@/api/index'
import { formatDateTimeShort } from '@/utils/time'

const router = useRouter()
const items = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

const pendingTotal = computed(() =>
  items.value.reduce((sum, i) => sum + (i.review_pending_count || 0), 0),
)

function statusTag(s) {
  const map = {
    draft: 'info',
    submitted: '',
    collecting: 'warning',
    partial: 'warning',
    completed: 'success',
    closed: 'info',
  }
  return map[s] || 'info'
}

function openDetail(id) {
  router.push(`/company/work-orders/${id}`)
}

async function fetchData() {
  loading.value = true
  try {
    const { data } = await workOrderApi.list({
      page: page.value,
      page_size: pageSize.value,
      has_company_pushed: true,
    })
    items.value = data.items || []
    total.value = data.total || 0
  } catch {
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
</script>

<style scoped>
.wo-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 18px;
  margin-bottom: 10px;
  cursor: pointer;
  border-left: 4px solid var(--primary, #409eff);
}
.wo-main { flex: 1; min-width: 0; }
.wo-tags { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; flex-wrap: wrap; }
.wo-title { font-weight: 600; margin-bottom: 4px; }
.wo-meta { font-size: 12px; color: var(--muted); }
.wo-actions { flex-shrink: 0; }
</style>
