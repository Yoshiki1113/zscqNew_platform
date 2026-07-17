<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">博主聚合分析</h1>
        <p class="page-subtitle">按博主维度统计侵权证据分布，共 <strong>{{ authorList.length }}</strong> 个博主</p>
      </div>
    </div>

    <!-- 总览统计 -->
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-value">{{ authorList.length }}</div>
        <div class="stat-label">博主总数</div>
      </div>
      <div class="stat-card danger">
        <div class="stat-value text-danger">{{ infringementAuthors }}</div>
        <div class="stat-label">有过侵权记录</div>
      </div>
      <div class="stat-card warning">
        <div class="stat-value text-warning">{{ uncertainOnly }}</div>
        <div class="stat-label">全部未审核</div>
      </div>
      <div class="stat-card success">
        <div class="stat-value text-success">{{ whitelistOnly }}</div>
        <div class="stat-label">全部未侵权</div>
      </div>
      <div class="stat-card info">
        <div class="stat-value text-primary">{{ totalVideos }}</div>
        <div class="stat-label">总视频数</div>
      </div>
    </div>

    <!-- 筛选 -->
    <div class="flex-between" style="margin-bottom:12px;">
      <div style="display:flex;gap:12px;align-items:flex-end;">
        <el-input v-model="searchName" placeholder="搜索博主..." style="width:160px;" @change="onSearch">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="sortBy" style="width:140px;" @change="fetchData">
          <el-option label="按侵权数（默认）" value="infringement" />
        </el-select>
        <el-button size="small" @click="resetSearch">
          <el-icon style="margin-right:2px"><RefreshLeft /></el-icon>重置
        </el-button>
      </div>
    </div>

    <!-- 博主列表 -->
    <div v-loading="loading">
      <div
        v-for="author in authorList" :key="author.video_channel_id"
        class="card author-card"
        :style="{ borderLeftColor: author.infringement_count > 0 ? 'var(--danger)' : (author.whitelist_count > 0 && !author.uncertain_count ? 'var(--success)' : 'transparent') }"
        :class="{ 'border-danger': author.infringement_count > 0, 'border-success': author.whitelist_count > 0 && !author.uncertain_count }"
      >
        <div class="card-body" style="cursor:pointer;" @click="toggleExpand(author.video_channel_id)">
          <div class="flex-between" style="margin-bottom:8px;">
            <div class="flex-center">
              <el-icon style="font-size:14px;color:var(--muted);">
                <ArrowDown v-if="expanded[author.video_channel_id]" />
                <ArrowRight v-else />
              </el-icon>
              <span style="font-size:16px;font-weight:700;color:var(--ink);">{{ author.blogger_name || '未知博主' }}</span>
              <el-tag size="small" effect="plain">微信视频号</el-tag>
              <code class="font-mono text-muted" style="font-size:12px;">{{ author.video_channel_id?.slice(0,20) || '' }}...</code>
            </div>
            <span class="text-muted" style="font-size:12px;">最近取证：{{ formatDateOnly(author.last_capture_time) }}</span>
          </div>
          <div style="display:flex;gap:8px;font-size:12px;color:var(--text);margin-bottom:8px;">
            <span v-if="author.company_full_name"><el-icon><OfficeBuilding /></el-icon> 企业：<strong>{{ author.company_full_name }}</strong></span>
            <span v-if="author.subject_type">· 主体类型：{{ author.subject_type }}</span>
          </div>
          <!-- 统计条 -->
          <div class="author-stats">
            <span style="font-size:12px;">总计 <strong>{{ author.total_videos || 0 }}</strong> 条视频</span>
            <div class="ratio-bar" style="flex:1;max-width:300px;">
              <div v-if="author.infringement_count" class="seg-danger" :style="{ width: (author.infringement_count/author.total_videos*100)+'%' }"></div>
              <div v-if="author.whitelist_count" class="seg-success" :style="{ width: (author.whitelist_count/author.total_videos*100)+'%' }"></div>
              <div v-if="author.uncertain_count" class="seg-warning" :style="{ width: (author.uncertain_count/author.total_videos*100)+'%' }"></div>
            </div>
            <el-tag type="danger" size="small" effect="light">侵权 {{ author.infringement_count || 0 }}</el-tag>
            <el-tag type="success" size="small" effect="light">未侵权 {{ author.whitelist_count || 0 }}</el-tag>
            <el-tag type="info" size="small" effect="light">未审核 {{ author.uncertain_count || 0 }}</el-tag>
          </div>
        </div>

        <!-- 展开：视频列表表格 -->
        <div v-if="expanded[author.video_channel_id]" style="border-top:1px solid var(--line);padding:16px 20px;">
          <div v-if="expandedLoading[author.video_channel_id]" class="empty-state">
            <div class="empty-text">加载中...</div>
          </div>
          <div v-else-if="expandedRecords[author.video_channel_id]?.length">
            <div style="font-size:13px;font-weight:600;margin-bottom:8px;color:var(--ink);">该博主全部证据记录：</div>
            <el-table :data="expandedRecords[author.video_channel_id]" stripe size="small">
              <el-table-column label="#" type="index" width="50" />
              <el-table-column prop="search_keyword" label="关键词" />
              <el-table-column label="视频标题">
                <template #default="{row}">{{ row.title?.slice(0,25) || '无标题' }}</template>
              </el-table-column>
              <el-table-column prop="like_count" label="喜欢" width="70" align="center" />
              <el-table-column label="引流" width="100">
                <template #default="{row}">
                  <el-tag v-if="row.has_traffic_marker" type="warning" size="small" effect="light">{{ row.traffic_marker_text?.slice(0,10) || '有' }}</el-tag>
                  <span v-else class="text-muted">-</span>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="100">
                <template #default="{row}">
                  <el-tag :type="row.review_status==='侵权'?'danger':row.review_status==='未侵权'?'success':'info'" size="small" effect="light">
                    {{ row.review_status || '未审核' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="采集时间" width="140">
                <template #default="{row}">{{ formatDateTimeShort(row.capture_timestamp) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="80">
                <template #default="{row}">
                  <el-button size="small" text type="primary" @click="$router.push(`/collector/evidence/${row.id}`)">详情</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <div v-else class="empty-state" style="padding:16px;">
            <div class="empty-text">暂无记录</div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="!loading && !authorList.length" class="card">
      <div class="empty-state">
        <div class="empty-icon"><el-icon><UserFilled /></el-icon></div>
        <div class="empty-text">暂无博主聚合数据</div>
      </div>
    </div>

    <div v-if="total > pageSize" class="flex-between" style="margin-top:16px;">
      <span class="text-muted" style="font-size:13px;">
        显示 {{ (page-1)*pageSize+1 }}-{{ Math.min(page*pageSize, total) }} 个博主，共 {{ total }} 个
      </span>
      <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev,pager,next" @current-change="fetchData" />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import {
  Search, RefreshLeft, ArrowDown, ArrowRight, OfficeBuilding, UserFilled
} from '@element-plus/icons-vue'
import { authorApi } from '@/api/index'
import { formatDateOnly, formatDateTimeShort } from '@/utils/time'

const authorList = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const searchName = ref('')
const sortBy = ref('infringement')

const expanded = reactive({})
const expandedRecords = reactive({})
const expandedLoading = reactive({})

const infringementAuthors = computed(() => authorList.value.filter(a => a.infringement_count > 0).length)
const uncertainOnly = computed(() => authorList.value.filter(a => a.infringement_count===0 && a.whitelist_count===0 && a.uncertain_count>0).length)
const whitelistOnly = computed(() => authorList.value.filter(a => a.infringement_count===0 && a.whitelist_count>0 && a.uncertain_count===0).length)
const totalVideos = computed(() => authorList.value.reduce((s, a) => s + (a.total_videos||0), 0))

async function fetchData() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (searchName.value) params.keyword = searchName.value
    const { data } = await authorApi.list(params)
    authorList.value = data.items || []
    total.value = data.total || 0
  } catch (e) { authorList.value = [] }
  finally { loading.value = false }
}

async function toggleExpand(channelId) {
  if (expanded[channelId]) { expanded[channelId]=false; return }
  expanded[channelId]=true
  if (expandedRecords[channelId]) return
  expandedLoading[channelId]=true
  try { const { data }=await authorApi.get(encodeURIComponent(channelId)); expandedRecords[channelId]=data.evidence_records||[] }
  catch (e) { expandedRecords[channelId]=[] }
  finally { expandedLoading[channelId]=false }
}
function onSearch() { page.value=1; fetchData() }
function resetSearch() { searchName.value=''; sortBy.value='infringement'; page.value=1; fetchData() }
onMounted(fetchData)
</script>

<style scoped>
.author-card {
  border-left: 3px solid transparent;
  transition: all var(--transition);
}

.author-card:hover {
  box-shadow: var(--shadow-sm);
}

.author-stats {
  display: flex;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
}
</style>
