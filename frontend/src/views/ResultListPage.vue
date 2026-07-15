<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">证据列表</h1>
      <el-space>
        <el-tag type="primary" effect="light">共 {{ stats.total || total }} 条</el-tag>
        <el-tag type="warning" effect="light" v-if="(stats.high || 0) + (stats.mid || 0) > 0">
          {{ (stats.high || 0) + (stats.mid || 0) }} 条待审核
        </el-tag>
        <el-button type="primary" plain size="small" @click="fetchData">
          <el-icon style="margin-right:4px"><Refresh /></el-icon>刷新
        </el-button>
      </el-space>
    </div>

    <!-- 统计卡片 -->
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-icon"><el-icon :size="22"><Document /></el-icon></div>
        <div class="stat-body">
          <div class="stat-value">{{ stats.total || total }}</div>
          <div class="stat-label">总证据</div>
        </div>
      </div>
      <div class="stat-card danger">
        <div class="stat-icon"><el-icon :size="22"><WarningFilled /></el-icon></div>
        <div class="stat-body">
          <div class="stat-value text-danger">{{ stats.infringement || 0 }}</div>
          <div class="stat-label">侵权</div>
        </div>
      </div>
      <div class="stat-card danger">
        <div class="stat-icon"><el-icon :size="22"><WarningFilled /></el-icon></div>
        <div class="stat-body">
          <div class="stat-value text-danger">{{ stats.high || 0 }}</div>
          <div class="stat-label">高度疑似</div>
        </div>
      </div>
      <div class="stat-card warning">
        <div class="stat-icon"><el-icon :size="22"><QuestionFilled /></el-icon></div>
        <div class="stat-body">
          <div class="stat-value text-warning">{{ stats.mid || 0 }}</div>
          <div class="stat-label">疑似</div>
        </div>
      </div>
      <div class="stat-card info">
        <div class="stat-icon"><el-icon :size="22"><View /></el-icon></div>
        <div class="stat-body">
          <div class="stat-value text-primary">{{ stats.low || 0 }}</div>
          <div class="stat-label">待观察</div>
        </div>
      </div>
    </div>

    <!-- 筛选 + 排序 -->
    <div class="card">
      <div class="card-body" style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
        <el-select v-model="filters.taskId" placeholder="选择任务" clearable filterable style="width:240px;" @change="onFilterChange">
          <el-option
            v-for="t in taskOptions"
            :key="t.id"
            :label="`#${t.id} ${t.keyword}（${formatDateTimeShort(t.created_at)}）`"
            :value="t.id"
          />
        </el-select>
        <el-select v-model="filters.reviewStatus" placeholder="审核状态" clearable style="width:140px;" @change="onFilterChange">
          <el-option label="全部" value="" />
          <el-option label="侵权" value="侵权" />
          <el-option label="未侵权" value="未侵权" />
        </el-select>
        <el-input v-model="filters.keyword" placeholder="搜索关键词" clearable style="width:170px;" @change="onFilterChange" />
        <el-input v-model="filters.blogger" placeholder="博主名称" clearable style="width:150px;" @change="onFilterChange" />
        <el-select v-model="sortBy" style="width:130px;" @change="fetchData">
          <el-option label="最新优先" value="newest" />
        </el-select>
        <el-button text @click="resetFilter">
          <el-icon style="margin-right:2px"><RefreshLeft /></el-icon>重置
        </el-button>
      </div>
    </div>

    <!-- 证据卡片列表 -->
    <div v-loading="loading">
      <div v-for="item in items" :key="item.id" :class="['card', 'evidence-card', reviewBorder(item)]" @click="openDetail(item.id)">
        <div style="display:flex;">
          <!-- 缩略图 -->
          <div class="evidence-thumb">
            <img v-if="getFirstScreen(item)" :src="`/files/${getFirstScreen(item)}`" />
            <span v-else class="thumb-placeholder">
              <el-icon><VideoPlay /></el-icon>
            </span>
          </div>
          <!-- 信息 -->
          <div style="flex:1;min-width:0;padding:14px 16px;display:flex;flex-direction:column;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;">
              <el-tag :type="statusType(item.review_status)" size="small" effect="light">
                {{ statusLabel(item.review_status) }}
              </el-tag>
              <el-tag v-if="item.infringement_level" :type="infringeType(item.infringement_level)" size="small" effect="dark">
                {{ infringeLabel(item.infringement_level) }} {{ (item.infringement_score * 100).toFixed(0) }}
              </el-tag>
              <span class="text-muted" style="font-size:12px;">{{ formatDateTimeShort(item.capture_timestamp) || formatDateTimeShort(item.created_at) }}</span>
              <span v-if="item.company_full_name" class="text-muted" style="font-size:12px;">{{ item.company_full_name }}</span>
            </div>
            <div v-if="item.infringement_reason" style="font-size:13px;color:#f56c6c;margin-bottom:4px;font-weight:700;line-height:1.5;">
              <el-icon><WarningFilled /></el-icon> <strong>{{ item.infringement_reason }}</strong>
            </div>
            <div class="evidence-title">{{ item.title || '无标题' }}</div>
            <div class="text-muted" style="font-size:12px;margin-bottom:6px;">
              博主: <strong style="color:var(--text);">{{ item.blogger_name || '未知' }}</strong>
              <code class="font-mono" style="font-size:11px;margin-left:6px;color:var(--muted);">{{ item.video_channel_id?.slice(0,16) || '' }}{{ item.video_channel_id ? '...' : '' }}</code>
            </div>
            <div style="font-size:12px;color:var(--muted);display:flex;gap:14px;">
              <span v-if="item.like_count"><el-icon><Star /></el-icon> {{ item.like_count }}</span>
              <span v-if="item.comment_count"><el-icon><ChatDotRound /></el-icon> {{ item.comment_count }}</span>
              <span v-if="item.share_count"><el-icon><Share /></el-icon> {{ item.share_count }}</span>
              <a v-if="item.video_link" :href="item.video_link" target="_blank" class="video-link" @click.stop>
                <el-icon><Link /></el-icon> 链接
              </a>
            </div>
            <el-alert
              v-if="item.has_traffic_marker && item.traffic_marker_text"
              type="warning"
              :closable="false"
              style="margin-top:8px;padding:4px 10px;"
            >
              <span style="font-size:12px;">{{ item.traffic_marker_text }}</span>
              <span v-if="item.target_blogger_name" style="font-size:12px;"> → {{ item.target_blogger_name }}</span>
            </el-alert>
            <div style="margin-top:auto;display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
              <el-button size="small" type="danger" @click.stop="quickReview(item, '侵权')">侵权</el-button>
              <el-button size="small" type="success" @click.stop="quickReview(item, '未侵权')">未侵权</el-button>
              <el-button v-if="item.review_status" size="small" @click.stop="quickReview(item, '')">撤销</el-button>
              <el-tag v-if="item.screenshots?.length" size="small" type="info" effect="plain">{{ item.screenshots.length }} 张截图</el-tag>
            </div>
          </div>
          <!-- 右侧：裁剪图 -->
          <div style="display:flex;gap:6px;padding:10px 12px 10px 0;align-items:center;flex-shrink:0;" @click.stop>
            <div v-if="getProfileCrop(item)" class="crop-thumb" :title="'博主: ' + (item.profile_name || item.blogger_name || '')">
              <img :src="`/files/${getProfileCrop(item)}`" />
              <div class="crop-label">博主</div>
            </div>
            <div v-if="getTrafficCrop(item)" class="crop-thumb" :title="'引流: ' + (item.target_blogger_name || '')">
              <img :src="`/files/${getTrafficCrop(item)}`" />
              <div class="crop-label">引流</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="!loading && !items.length" class="card">
      <div class="empty-state">
        <div class="empty-icon"><el-icon><FolderOpened /></el-icon></div>
        <div class="empty-text">暂无证据记录，请先创建并执行取证任务</div>
      </div>
    </div>

    <div style="text-align:center;margin-top:16px;" v-if="total > pageSize">
      <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next" @current-change="fetchData" />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  Refresh, RefreshLeft, VideoPlay, Star, ChatDotRound, Share,
  Link, Document, FolderOpened, WarningFilled, QuestionFilled, View
} from '@element-plus/icons-vue'
import { evidenceApi, reviewApi, taskApi } from '@/api/index'
import { formatDateTime, formatDateTimeShort } from '@/utils/time'

const router = useRouter()
const items = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const sortBy = ref('newest')

const stats = ref({})

const filters = reactive({ reviewStatus: '', keyword: '', blogger: '', taskId: '' })
const taskOptions = ref([])

async function loadTasks() {
  try {
    const { data } = await taskApi.list({ page: 1, page_size: 100, phase: 2 })
    taskOptions.value = data.items || []
    // 默认选中最新任务
    if (taskOptions.value.length && !filters.taskId) {
      filters.taskId = taskOptions.value[0].id
    }
  } catch (e) {
    taskOptions.value = []
  }
}

function statusType(s) { return s === '侵权' ? 'danger' : s === '未侵权' ? 'success' : 'info' }
function statusLabel(s) { return s || '未审核' }
function infringeLabel(l) { return l === '侵权' ? '侵权线索' : l }
function infringeType(l) { return l === '高度疑似' ? 'danger' : (l === '侵权' || l === '疑似') ? 'warning' : 'info' }
function reviewBorder(item) {
  if (item.review_status === '侵权') return 'border-danger'
  if (item.review_status === '未侵权') return 'border-success'
  return ''
}

function getFirstScreen(item) {
  const screens = item.screenshots || []
  if (!screens.length) return ''
  const s = screens[0]
  return typeof s === 'string' ? s : s?.path || ''
}

function findShot(item, prefix) {
  const screens = item.screenshots || []
  for (const s of screens) {
    const p = typeof s === 'string' ? s : s?.path || ''
    if (p.split(/[/\\]/).pop()?.toLowerCase().startsWith(prefix)) return p
  }
  return ''
}

function getProfileCrop(item) { return findShot(item, 'profile_card_name_region_') }
function getTrafficCrop(item) { return findShot(item, 'traffic_page_name_region_') }

async function quickReview(item, status) {
  const { ElMessage } = await import('element-plus')
  try {
    await reviewApi.update(item.id, { review_status: status })
    item.review_status = status
    ElMessage.success(`已标注: ${status}`)
    fetchData()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '标注失败')
  }
}

async function fetchData() {
  loading.value = true
  try {
    const { data } = await evidenceApi.list({
      page: page.value, page_size: pageSize.value,
      review_status: filters.reviewStatus, keyword: filters.keyword, blogger: filters.blogger,
      task_id: filters.taskId || 0,
    })
    items.value = data.items || []
    total.value = data.total || 0
    stats.value = data.stats || {}
  } catch (e) {
    items.value = []
  } finally {
    loading.value = false
  }
}

function onFilterChange() { page.value = 1; fetchData() }
function resetFilter() { filters.reviewStatus = ''; filters.keyword = ''; filters.blogger = ''; sortBy.value = 'newest'; page.value = 1; fetchData() }
function openDetail(id) { router.push(`/evidence/${id}`) }
function previewFile(path) { if (path) window.open(`/files/${path}`, '_blank') }

onMounted(async () => {
  await loadTasks()
  fetchData()
})
</script>

<style scoped>
/* ── 统计卡片 ── */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 22px 28px;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  position: relative;
  overflow: hidden;
  transition: all var(--transition);
}

.stat-card::after {
  content: '';
  position: absolute;
  right: -24px; top: -24px;
  width: 90px; height: 90px;
  border-radius: 50%;
  opacity: 0.04;
  background: var(--muted);
  transition: all 0.3s ease;
}

.stat-card.danger::after { background: var(--danger); }
.stat-card.warning::after { background: var(--warning); }
.stat-card.info::after { background: var(--primary); }

.stat-card:hover {
  border-color: var(--primary-border);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.stat-card:hover::after {
  right: -14px; top: -14px;
  width: 110px; height: 110px;
  opacity: 0.07;
}

.stat-icon {
  position: absolute;
  left: 20px;
  width: 44px; height: 44px;
  display: flex; align-items: center; justify-content: center;
  border-radius: var(--radius);
  background: var(--bg);
  color: var(--primary);
  font-size: 22px;
}

.stat-card.danger .stat-icon { background: var(--danger-bg); color: var(--danger); }
.stat-card.warning .stat-icon { background: var(--warning-bg); color: var(--warning); }
.stat-card.info .stat-icon { background: var(--primary-bg); color: var(--primary); }

.stat-body { text-align: center; }

.stat-value {
  font-size: 32px;
  font-weight: 800;
  line-height: 1;
  color: var(--ink);
  font-feature-settings: 'tnum';
  letter-spacing: -1px;
}

.stat-label {
  font-size: 13px;
  color: var(--muted);
  margin-top: 4px;
  letter-spacing: 0.5px;
  font-weight: 500;
}

.evidence-card { border-left: 6px solid transparent; cursor: pointer; position: relative; transition: all 0.2s; }
.evidence-card.border-danger { border-left-color: #ef4444; background: linear-gradient(90deg, rgba(239,68,68,0.08) 0%, rgba(239,68,68,0) 30%); }
.evidence-card.border-success { border-left-color: #22c55e; background: linear-gradient(90deg, rgba(34,197,94,0.08) 0%, rgba(34,197,94,0) 30%); }
.evidence-card.border-danger::before {
  content: '侵权'; position: absolute; top: 0; right: 0;
  background: #ef4444; color: #fff; font-size: 11px; font-weight: 600;
  padding: 2px 10px; border-bottom-left-radius: 8px;
  letter-spacing: 1px;
}
.evidence-card.border-success::before {
  content: '已审核'; position: absolute; top: 0; right: 0;
  background: #22c55e; color: #fff; font-size: 11px; font-weight: 600;
  padding: 2px 10px; border-bottom-left-radius: 8px;
  letter-spacing: 1px;
}
.evidence-card:hover { box-shadow: var(--shadow-md); transform: translateY(-1px); }
.evidence-card.border-danger:hover { border-left-color: #dc2626; box-shadow: 0 4px 12px rgba(239,68,68,0.2); }
.evidence-card.border-success:hover { border-left-color: #16a34a; box-shadow: 0 4px 12px rgba(34,197,94,0.2); }
.evidence-thumb {
  width: 120px; min-width: 120px; height: 210px;
  background: #0D1117; display: flex; align-items: center; justify-content: center;
  overflow: hidden; flex-shrink: 0;
}
.evidence-thumb img { width: 100%; height: 100%; object-fit: contain; }
.thumb-placeholder { font-size: 36px; opacity: 0.3; color: var(--muted); }
.evidence-title {
  font-weight: 600; margin-bottom: 4px;
  color: var(--ink);
}
.video-link { display: inline-flex; align-items: center; gap: 2px; font-size: 12px; }
.video-link .el-icon { font-size: 13px; }

.crop-thumb {
  width: 150px; height: 150px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
  background: #0d0d0d;
  position: relative;
}
.crop-thumb img {
  width: 100%; height: 100%;
  object-fit: contain;
}
.crop-thumb .crop-label {
  position: absolute; bottom: 0; left: 0; right: 0;
  padding: 2px 0; text-align: center;
  font-size: 10px; color: #fff;
  background: rgba(0,0,0,0.65);
}
</style>
