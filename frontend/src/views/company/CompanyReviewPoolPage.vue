<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">核查池</h1>
        <p class="page-subtitle">取证二阶段推送的待核查证据</p>
      </div>
      <el-space>
        <el-tag type="warning" effect="light" v-if="pendingCount">待复核 {{ pendingCount }}</el-tag>
        <el-tag type="primary" effect="light">共 {{ total }} 条</el-tag>
        <el-button @click="fetchData"><el-icon><Refresh /></el-icon> 刷新</el-button>
      </el-space>
    </div>

    <div class="card">
      <div class="card-body" style="display:flex;gap:12px;flex-wrap:wrap;">
        <el-select v-model="filters.reviewStatus" placeholder="复核状态" clearable style="width:140px;" @change="onFilter">
          <el-option label="待复核" value="__pending__" />
          <el-option label="侵权" value="侵权" />
          <el-option label="未侵权" value="未侵权" />
        </el-select>
        <el-input v-model="filters.keyword" placeholder="剧名/关键词" clearable style="width:160px;" @change="onFilter" />
        <el-input v-model="filters.blogger" placeholder="博主" clearable style="width:140px;" @change="onFilter" />
      </div>
    </div>

    <div v-loading="loading">
      <div
        v-for="item in items"
        :key="item.id"
        class="card pool-card"
        :class="reviewBorder(item)"
        @click="openDetail(item.id)"
      >
        <div class="pool-thumb">
          <img v-if="getFirstScreen(item)" :src="`/files/${getFirstScreen(item)}`" />
          <el-icon v-else :size="32"><VideoPlay /></el-icon>
        </div>
        <div class="pool-main">
          <div class="pool-tags">
            <el-tag :type="statusType(item.review_status)" size="small">{{ item.review_status || '待复核' }}</el-tag>
            <el-tag v-if="item.infringement_level" size="small" effect="plain">{{ item.infringement_level }}</el-tag>
            <span class="text-muted" style="font-size:12px;">{{ formatDateTimeShort(item.pushed_to_company_at || item.created_at) }}</span>
          </div>
          <div class="pool-title">{{ item.title || '无标题' }}</div>
          <div class="pool-meta">博主 {{ item.blogger_name || '未知' }}</div>
        </div>
        <div class="pool-actions" @click.stop>
          <el-button size="small" type="danger" @click="quickReview(item, '侵权')">侵权</el-button>
          <el-button size="small" type="success" @click="quickReview(item, '未侵权')">未侵权</el-button>
          <el-button size="small" text type="primary" @click="openDetail(item.id)">详情</el-button>
        </div>
      </div>
    </div>

    <div v-if="!loading && !items.length" class="card">
      <div class="empty-state">
        <div class="empty-text">暂无待核查证据，请等待取证员推送二阶段结果</div>
      </div>
    </div>

    <div v-if="total > pageSize" style="text-align:center;margin-top:16px;">
      <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next" @current-change="fetchData" />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh, VideoPlay } from '@element-plus/icons-vue'
import { evidenceApi, reviewApi } from '@/api/index'
import { formatDateTimeShort } from '@/utils/time'

const router = useRouter()
const items = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const stats = ref({})

const filters = reactive({ reviewStatus: '', keyword: '', blogger: '' })

const pendingCount = computed(() => {
  if (filters.reviewStatus === '__pending__') return total.value
  return stats.value.pending || 0
})

function statusType(s) { return s === '侵权' ? 'danger' : s === '未侵权' ? 'success' : 'warning' }
function reviewBorder(item) {
  if (item.review_status === '侵权') return 'border-danger'
  if (item.review_status === '未侵权') return 'border-success'
  return 'border-pending'
}

function getFirstScreen(item) {
  const screens = item.screenshots || []
  if (!screens.length) return ''
  const s = screens[0]
  return typeof s === 'string' ? s : s?.path || ''
}

function onFilter() { page.value = 1; fetchData() }
function openDetail(id) { router.push(`/company/evidence/${id}`) }

async function quickReview(item, status) {
  try {
    await reviewApi.update(item.id, { review_status: status })
    item.review_status = status
    ElMessage.success(`已标注: ${status || '撤销'}`)
    fetchData()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '标注失败')
  }
}

async function fetchData() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
      company_pool_only: true,
      phase: 2,
      keyword: filters.keyword,
      blogger: filters.blogger,
    }
    if (filters.reviewStatus === '__pending__') {
      params.review_pending = true
    } else if (filters.reviewStatus) {
      params.review_status = filters.reviewStatus
    }

    const { data } = await evidenceApi.list(params)
    items.value = data.items || []
    total.value = data.total || 0
    stats.value = data.stats || {}
    if (!filters.reviewStatus) {
      stats.value.pending = (data.items || []).filter(i => !i.review_status).length
    }
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
</script>

<style scoped>
.pool-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 18px;
  margin-bottom: 10px;
  cursor: pointer;
  border-left: 4px solid transparent;
}
.pool-card.border-pending { border-left-color: var(--warning); }
.pool-card.border-danger { border-left-color: var(--danger); }
.pool-card.border-success { border-left-color: var(--success); }
.pool-thumb {
  width: 72px; height: 96px; flex-shrink: 0;
  background: #0d1117; border-radius: var(--radius-sm);
  display: flex; align-items: center; justify-content: center;
  overflow: hidden; color: var(--muted);
}
.pool-thumb img { width: 100%; height: 100%; object-fit: cover; }
.pool-main { flex: 1; min-width: 0; }
.pool-tags { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; flex-wrap: wrap; }
.pool-title { font-weight: 600; margin-bottom: 4px; }
.pool-meta { font-size: 12px; color: var(--muted); }
.pool-actions { display: flex; gap: 6px; flex-shrink: 0; flex-wrap: wrap; }
</style>
