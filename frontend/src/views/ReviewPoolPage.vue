<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">复核池</h1>
        <p class="page-subtitle">待审核样本：<strong class="text-warning">{{ total }}</strong> 条</p>
      </div>
      <el-button size="small" @click="fetchData">
        <el-icon style="margin-right:4px"><Refresh /></el-icon>刷新
      </el-button>
    </div>

    <!-- 筛选 -->
    <div class="card" style="margin-bottom:16px;">
      <div class="card-body" style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;">
        <div>
          <label class="filter-label">博主</label>
          <el-input v-model="filterKeyword" placeholder="博主名称" style="width:140px;" @change="onFilter" />
        </div>
        <div>
          <label class="filter-label">时间</label>
          <el-select v-model="filterTime" style="width:110px;">
            <el-option label="最近7天" value="7" />
            <el-option label="最近30天" value="30" />
            <el-option label="全部" value="" />
          </el-select>
        </div>
        <div>
          <label class="filter-label">排序</label>
          <el-select v-model="sortBy" style="width:100px;">
            <el-option label="最新" value="newest" />
            <el-option label="最旧" value="oldest" />
            <el-option label="最多喜欢" value="likes" />
          </el-select>
        </div>
        <el-button type="primary" @click="onFilter">
          <el-icon style="margin-right:2px"><Search /></el-icon>筛选
        </el-button>
      </div>
    </div>

    <!-- 批量操作栏 -->
    <div class="flex-between" style="margin-bottom:12px;">
      <span class="text-muted" style="font-size:13px;">
        当前第 <strong style="color:var(--ink);">{{ total > 0 ? currentIndex + 1 : 0 }}</strong> / {{ total || 0 }} 条
        · 已处理 {{ reviewedInSession }} 条
      </span>
      <div style="display:flex;gap:6px;">
        <el-button size="small" type="danger" @click="batchReview('侵权')" :loading="batchReviewing">全部标侵权</el-button>
        <el-button size="small" type="success" @click="batchReview('未侵权')" :loading="batchReviewing">全部标未侵权</el-button>
      </div>
    </div>

    <div v-if="items.length === 0 && !loading" class="card">
      <div class="empty-state">
        <div class="empty-icon"><el-icon><CircleCheck /></el-icon></div>
        <div class="empty-text">没有待审核的样本</div>
      </div>
    </div>

    <!-- 当前审核卡片 -->
    <div v-if="items.length > 0" class="card review-active-card">
      <div style="display:flex;gap:0;">
        <!-- 截图预览 -->
        <div class="review-preview">
          <img v-if="firstScreen" :src="`/files/${firstScreen}`" />
          <div v-else class="preview-placeholder">
            <el-icon><VideoPlay /></el-icon>
          </div>
        </div>
        <!-- 信息区 -->
        <div class="review-info">
          <div class="flex-between" style="margin-bottom:8px;">
            <div class="flex-center">
              <el-tag type="info" size="small" effect="light">未审核</el-tag>
              <span class="text-muted" style="font-size:12px;">{{ formatDateOnly(current.capture_timestamp) }}</span>
            </div>
            <span class="text-muted" style="font-size:12px;">{{ currentIndex + 1 }} / {{ items.length }}</span>
          </div>
          <h3 class="review-title">{{ current.title || '无标题' }}</h3>
          <div class="review-meta">
            <span><el-icon><User /></el-icon> <strong>{{ current.blogger_name || '未知' }}</strong></span>
            <span class="font-mono text-muted">ID: {{ current.video_channel_id?.slice(0,16) || '-' }}</span>
            <span v-if="current.company_full_name"><el-icon><OfficeBuilding /></el-icon> {{ current.subject_type || '' }} · {{ current.company_full_name }}</span>
          </div>
          <div class="review-stats">
            <span v-if="current.like_count"><el-icon><Star /></el-icon> {{ current.like_count }}</span>
            <span v-if="current.comment_count"><el-icon><ChatDotRound /></el-icon> {{ current.comment_count }}</span>
            <span v-if="current.share_count"><el-icon><Share /></el-icon> {{ current.share_count }}</span>
            <a v-if="current.video_link" :href="current.video_link" target="_blank">
              <el-icon><Link /></el-icon> 视频链接
            </a>
          </div>
          <el-alert
            v-if="current.has_traffic_marker"
            type="warning"
            :closable="false"
            style="margin-top:8px;"
          >
            <span style="font-size:12px;">引流：<strong>{{ current.traffic_marker_text || '有' }}</strong>
            <span v-if="current.target_blogger_name"> → {{ current.target_blogger_name }}</span></span>
          </el-alert>
          <el-alert
            v-if="current.script_match_status === 'matched'"
            type="success"
            :closable="false"
            style="margin-top:8px;"
          >
            <span style="font-size:12px;">ASR剧本匹配：<strong>{{ (current.script_match_similarity * 100).toFixed(1) }}%</strong> · {{ current.script_match_episode || '' }}</span>
          </el-alert>
          <div v-if="current.asr_text" class="asr-preview">
            <el-icon><Microphone /></el-icon>
            {{ current.asr_text?.slice(0,200) }}{{ current.asr_text?.length > 200 ? '...' : '' }}
          </div>
          <a @click="$router.push(`/collector/evidence/${current.id}`)" class="detail-link">
            打开完整证据详情
            <el-icon><ArrowRight /></el-icon>
          </a>
        </div>
        <!-- 操作区 -->
        <div class="review-actions">
          <el-button type="danger" style="width:100%;" @click="doReview('侵权')" :loading="reviewing==='侵权'">侵权</el-button>
          <el-button type="success" style="width:100%;" @click="doReview('未侵权')" :loading="reviewing==='未侵权'">未侵权</el-button>
          <el-input v-model="reviewNote" type="textarea" :rows="2" placeholder="审核备注..." style="margin-top:8px;font-size:12px;" />
        </div>
      </div>
    </div>

    <!-- 队列预览 -->
    <div v-if="items.length > 1" class="queue-grid">
      <div
        v-for="(q, i) in items.slice(0, Math.min(items.length, 12))" :key="q.id"
        :class="['queue-item', { active: i === currentIndex, done: i < currentIndex }]"
        @click="currentIndex = i"
      >
        <div class="flex-between" style="margin-bottom:4px;">
          <el-tag :type="q.review_status === '侵权' ? 'danger' : q.review_status === '未侵权' ? 'success' : 'info'" size="small" effect="light">
            {{ q.review_status || '未审核' }}
          </el-tag>
          <span class="text-muted" style="font-size:12px;">#{{ i + 1 }}</span>
        </div>
        <div class="queue-title">{{ q.title?.slice(0,20) || '无标题' }}</div>
        <div class="text-muted" style="font-size:12px;">{{ q.blogger_name || '未知' }} · {{ q.like_count || '' }} 喜欢</div>
        <div v-if="q.has_traffic_marker" class="text-warning" style="font-size:12px;">引流：{{ q.traffic_marker_text?.slice(0,15) || '有' }}</div>
      </div>
    </div>

    <!-- 翻页 -->
    <div v-if="items.length > 0" class="flex-between" style="margin-top:16px;">
      <span class="text-muted" style="font-size:13px;">已处理 {{ reviewedInSession }} 条，剩余 {{ items.length - currentIndex - 1 }} 条待审核</span>
      <div style="display:flex;gap:4px;">
        <el-button size="small" :disabled="currentIndex === 0" @click="currentIndex--">
          <el-icon><ArrowLeft /></el-icon> 上一条
        </el-button>
        <el-button size="small" :disabled="currentIndex >= items.length - 1" @click="currentIndex++">
          下一条 <el-icon><ArrowRight /></el-icon>
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Refresh, Search, CircleCheck, VideoPlay, User, OfficeBuilding,
  Star, ChatDotRound, Share, Link, Microphone, ArrowLeft, ArrowRight
} from '@element-plus/icons-vue'
import { reviewApi } from '@/api/index'
import { formatDateOnly } from '@/utils/time'

const items = ref([])
const loading = ref(false)
const total = ref(0)
const currentIndex = ref(0)
const reviewedInSession = ref(0)
const reviewing = ref('')
const batchReviewing = ref(false)
const reviewNote = ref('')
const filterKeyword = ref('')
const filterTime = ref('')
const sortBy = ref('newest')

const current = computed(() => items.value[currentIndex.value] || {})
const firstScreen = computed(() => {
  const screens = current.value.screenshots || []
  if (!screens.length) return ''
  const s = screens[0]
  return typeof s === 'string' ? s : s?.path || ''
})

async function fetchData() {
  loading.value = true
  try {
    const params = { page_size: 200 }
    if (filterKeyword.value) params.keyword = filterKeyword.value
    const { data } = await reviewApi.pool(params)
    items.value = data.items || []
    total.value = data.total || 0
    currentIndex.value = 0
  } catch (e) { items.value = [] }
  finally { loading.value = false }
}

function onFilter() { fetchData() }

async function doReview(status) {
  if (!current.value.id) return
  reviewing.value = status
  try {
    await reviewApi.update(current.value.id, { review_status: status, review_notes: reviewNote.value })
    items.value[currentIndex.value].review_status = status
    reviewedInSession.value++; reviewNote.value = ''
    ElMessage.success(`已标注: ${status}`)
    if (currentIndex.value < items.value.length - 1) setTimeout(() => currentIndex.value++, 200)
    else ElMessage.success('全部审核完成！')
  } catch (e) { ElMessage.error(e.response?.data?.detail || '标注失败') }
  finally { reviewing.value = '' }
}

async function batchReview(status) {
  const remaining = items.value.slice(currentIndex.value)
  if (!remaining.length) return
  await ElMessageBox.confirm(`剩余 ${remaining.length} 条标注为"${status}"？`, '批量标注', {
    confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning'
  })
  batchReviewing.value = true
  try {
    await reviewApi.batch({ evidence_ids: remaining.map(r=>r.id), review_status: status })
    remaining.forEach(r=>r.review_status=status); reviewedInSession.value+=remaining.length
    ElMessage.success(`已批量标注 ${remaining.length} 条`); fetchData(); currentIndex.value=0
  } catch (e) { ElMessage.error('批量失败: '+(e.response?.data?.detail||e.message)) }
  finally { batchReviewing.value = false }
}

onMounted(fetchData)
</script>

<style scoped>
.filter-label {
  font-size: 12px;
  color: var(--muted);
  display: block;
  margin-bottom: 4px;
}

.review-active-card {
  border: 2px solid var(--warning);
  box-shadow: var(--shadow-md);
  margin-bottom: 16px;
}

.review-preview {
  width: 180px;
  min-width: 180px;
  background: #0D1117;
  overflow: hidden;
  flex-shrink: 0;
}

.review-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.preview-placeholder {
  height: 100%;
  min-height: 240px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  font-size: 32px;
}

.review-info {
  flex: 1;
  min-width: 0;
  padding: 16px;
}

.review-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--ink);
}

.review-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  font-size: 12px;
  margin-bottom: 6px;
  color: var(--text);
}

.review-meta .el-icon {
  vertical-align: middle;
  margin-right: 2px;
}

.review-stats {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 6px;
}

.review-stats .el-icon {
  vertical-align: middle;
  margin-right: 2px;
}

.asr-preview {
  margin-top: 8px;
  font-size: 12px;
  color: var(--muted);
  max-height: 60px;
  overflow-y: auto;
  line-height: 1.6;
}

.asr-preview .el-icon {
  vertical-align: middle;
  margin-right: 4px;
}

.detail-link {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-top: 8px;
  font-size: 12px;
  cursor: pointer;
  color: var(--primary);
}

.review-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  justify-content: center;
  min-width: 140px;
  padding: 16px;
  border-left: 1px solid var(--line);
  background: var(--bg-alt);
}

.queue-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.queue-item {
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--paper);
  cursor: pointer;
  transition: all var(--transition);
  opacity: 1;
}

.queue-item:hover {
  border-color: var(--primary-border);
  box-shadow: var(--shadow-sm);
}

.queue-item.active {
  border-color: var(--warning);
  border-width: 2px;
  box-shadow: var(--shadow-sm);
}

.queue-item.done {
  opacity: 0.5;
}

.queue-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 2px;
  color: var(--ink);
}
</style>
