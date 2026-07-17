<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">已推送线索</h1>
      <el-tag type="primary" effect="light">共 {{ total }} 条</el-tag>
    </div>

    <div class="card">
      <div class="card-body" style="display:flex;gap:12px;flex-wrap:wrap;">
        <el-input v-model="filters.keyword" placeholder="剧名/关键词" clearable style="width:180px;" @change="onFilter" />
        <el-input v-model="filters.blogger" placeholder="博主名称" clearable style="width:150px;" @change="onFilter" />
        <el-select v-model="filters.reviewStatus" placeholder="复核结论" clearable style="width:140px;" @change="onFilter">
          <el-option label="侵权" value="侵权" />
          <el-option label="未侵权" value="未侵权" />
        </el-select>
        <el-button @click="fetchData"><el-icon><Refresh /></el-icon> 刷新</el-button>
      </div>
    </div>

    <div v-loading="loading">
      <div
        v-for="item in items"
        :key="item.id"
        class="card clue-card"
        @click="openDetail(item.id)"
      >
        <div class="clue-main">
          <div class="clue-tags">
            <el-tag :type="statusType(item.review_status)" size="small">{{ item.review_status || '未审核' }}</el-tag>
            <el-tag v-if="item.infringement_level" :type="infringeType(item.infringement_level)" size="small" effect="dark">
              {{ item.infringement_level }}
            </el-tag>
            <el-tag type="success" size="small" effect="plain">已推送</el-tag>
          </div>
          <div class="clue-title">{{ item.title || '无标题' }}</div>
          <div class="clue-meta">
            博主 {{ item.blogger_name || '未知' }} · {{ formatDateTimeShort(item.pushed_at || item.created_at) }}
          </div>
          <div v-if="item.infringement_reason" class="clue-reason">{{ item.infringement_reason }}</div>
        </div>
        <el-icon class="clue-arrow"><ArrowRight /></el-icon>
      </div>
    </div>

    <div v-if="!loading && !items.length" class="card">
      <div class="empty-state">
        <div class="empty-text">暂无已推送线索</div>
      </div>
    </div>

    <div v-if="total > pageSize" style="text-align:center;margin-top:16px;">
      <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next" @current-change="fetchData" />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, ArrowRight } from '@element-plus/icons-vue'
import { evidenceApi } from '@/api/index'
import { formatDateTimeShort } from '@/utils/time'

const router = useRouter()
const items = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = reactive({ keyword: '', blogger: '', reviewStatus: '' })

function statusType(s) { return s === '侵权' ? 'danger' : s === '未侵权' ? 'success' : 'info' }
function infringeType(l) { return l === '高度疑似' ? 'danger' : 'warning' }

function onFilter() { page.value = 1; fetchData() }
function openDetail(id) { router.push(`/police/evidence/${id}`) }

async function fetchData() {
  loading.value = true
  try {
    const { data } = await evidenceApi.list({
      page: page.value,
      page_size: pageSize.value,
      pushed_only: true,
      keyword: filters.keyword,
      blogger: filters.blogger,
      review_status: filters.reviewStatus,
    })
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

<style scoped>
.clue-card {
  display: flex;
  align-items: center;
  padding: 16px 20px;
  cursor: pointer;
  transition: box-shadow var(--transition);
  margin-bottom: 10px;
}
.clue-card:hover { box-shadow: var(--shadow-md); }
.clue-main { flex: 1; min-width: 0; }
.clue-tags { display: flex; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }
.clue-title { font-weight: 600; font-size: 15px; margin-bottom: 4px; }
.clue-meta { font-size: 12px; color: var(--muted); }
.clue-reason { font-size: 13px; color: var(--danger); margin-top: 6px; }
.clue-arrow { color: var(--muted); font-size: 18px; }
</style>
