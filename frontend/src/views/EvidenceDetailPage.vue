<template>
  <div v-loading="loading">
    <div class="page-container">
      <div class="page-header">
        <div>
          <div style="display:flex;align-items:center;gap:12px;">
            <h1 class="page-title" style="margin:0;">{{ record.title || '证据详情' }}</h1>
            <el-tag v-if="record.review_status" :type="reviewType" size="large" effect="dark">{{ record.review_status }}</el-tag>
          </div>
          <p class="page-subtitle">{{ record.blogger_name || '' }} {{ formatDateTime(record.capture_timestamp) }}</p>
        </div>
        <el-button size="small" @click="goBack">
          <el-icon style="margin-right:2px"><ArrowLeft /></el-icon>返回
        </el-button>
      </div>

      <!-- 侵权评分 -->
      <div v-if="infringementScore !== null" :class="['infringement-bar', infringementLevelType]">
        <el-tooltip placement="bottom" effect="light" :teleported="false" popper-class="score-tooltip">
          <template #content>
            <div class="tooltip-formula">
              <div class="tooltip-title">疑似度计算规则</div>
              <div class="tooltip-row">
                <span>覆盖率</span>
                <span>{{ (record.script_match_similarity * 100).toFixed(1) }}% × 35 分 = {{ (record.script_match_similarity * 0.35 * 100).toFixed(1) }} 分</span>
              </div>
              <div class="tooltip-row">
                <span>最佳匹配</span>
                <span>{{ ((record.script_match_pinyin_score * 0.55 + record.script_match_char_score * 0.45) * 100).toFixed(1) }}% × 40 分 = {{ ((record.script_match_pinyin_score * 0.55 + record.script_match_char_score * 0.45) * 0.40 * 100).toFixed(1) }} 分</span>
              </div>
              <div class="tooltip-row">
                <span>片段数</span>
                <span>min({{ record.script_match_segments_matched || 0 }}/5, 1.0) × 25 分 = {{ (Math.min((record.script_match_segments_matched || 0) / 5, 1) * 0.25 * 100).toFixed(1) }} 分</span>
              </div>
              <div class="tooltip-divider"></div>
              <div class="tooltip-row total">
                <span>合计</span>
                <span>{{ (infringementScore * 100).toFixed(0) }} 分</span>
              </div>
              <div class="tooltip-divider"></div>
              <div class="tooltip-levels">
                <span>≥70 高度疑似</span><span>≥50 疑似</span><span>≥30 待观察</span>
              </div>
            </div>
          </template>
          <div class="infringement-score">
            <span class="score-num">{{ (infringementScore * 100).toFixed(0) }}</span>
            <span class="score-unit">分</span>
          </div>
        </el-tooltip>
        <div class="infringement-info">
          <div class="infringement-label">{{ record.infringement_level || '无明显匹配' }}</div>
          <div v-if="record.infringement_reason" class="infringement-reason" style="color:#f56c6c;font-size:13px;margin-top:2px;">
            {{ record.infringement_reason }}
          </div>
          <div class="infringement-detail">
            覆盖率 {{ (record.script_match_similarity * 100).toFixed(0) }}% ·
            最佳匹配 {{ ((record.script_match_pinyin_score * 0.55 + record.script_match_char_score * 0.45) * 100).toFixed(0) }}% ·
            {{ record.script_match_segments_matched || 0 }}/{{ record.script_match_segments_total || 0 }} 句匹配
          </div>
        </div>
      </div>

      <!-- 审核操作栏：公司端复核 -->
      <div v-if="companyReview" class="card">
        <div class="card-body" style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
          <el-button type="danger" @click="doReview('侵权')" :loading="reviewing">
            <el-icon style="margin-right:2px"><CircleCloseFilled /></el-icon>侵权
          </el-button>
          <el-button type="success" @click="doReview('未侵权')" :loading="reviewing">
            <el-icon style="margin-right:2px"><CircleCheckFilled /></el-icon>未侵权
          </el-button>
          <el-button v-if="record.review_status" @click="doReview('')" :loading="reviewing" plain>
            <el-icon style="margin-right:2px"><RefreshLeft /></el-icon>撤销
          </el-button>
          <el-input v-model="reviewNotes" placeholder="复核备注" style="width:200px;" />
          <el-button type="primary" @click="doReview(record.review_status)" :loading="reviewing">
            <el-icon style="margin-right:2px"><Check /></el-icon>保存
          </el-button>
        </div>
      </div>
      <!-- 取证端：推送公司 / 公安 -->
      <div v-else-if="!readonly" class="card">
        <div class="card-body" style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
          <el-button
            v-if="!record.pushed_to_company"
            type="primary"
            :loading="pushingCompany"
            @click="pushToCompany"
          >
            推送公司核查池
          </el-button>
          <el-tag v-else type="primary" effect="plain">
            已送核查池 {{ formatDateTime(record.pushed_to_company_at) }}
          </el-tag>
          <el-button
            v-if="canPushPolice"
            type="warning"
            :loading="pushing"
            @click="pushToPolice"
          >
            推送公安
          </el-button>
          <el-tag v-else-if="record.pushed_to_police" type="success" effect="plain">
            已推送公安 {{ formatDateTime(record.pushed_at) }}
          </el-tag>
          <el-tag v-else-if="record.pushed_to_company" type="info" effect="plain">
            公司复核：{{ record.review_status || '待复核' }}
          </el-tag>
        </div>
      </div>
      <div v-else-if="record.pushed_to_police" class="card">
        <div class="card-body">
          <el-tag type="success">已推送公安 · {{ formatDateTime(record.pushed_at) }}</el-tag>
        </div>
      </div>

      <!-- 取证摘要 -->
      <div class="card">
        <div class="card-header">
          <span class="flex-center">
            <span class="header-icon"><el-icon><InfoFilled /></el-icon></span>
            取证摘要
          </span>
        </div>
        <div class="card-body">
          <dl class="kv-list">
            <dt>搜索词</dt><dd>{{ record.search_keyword || '-' }}</dd>
            <dt>视频标识符</dt><dd><code class="font-mono">{{ record.video_identifier || '-' }}</code></dd>
            <dt>去重指纹</dt><dd><code class="font-mono">{{ record.fingerprint || '-' }}</code></dd>
            <dt>视频链接</dt><dd><a v-if="record.video_link" :href="record.video_link" target="_blank">{{ record.video_link }}</a><span v-else class="text-muted">-</span></dd>
            <dt>录屏文件</dt><dd><a v-if="record.recording_video_path" :href="`/files/${record.recording_video_path}`" target="_blank">{{ record.recording_video_path }}</a><span v-else class="text-muted">-</span></dd>
            <dt>JSON</dt><dd><a v-if="record.json_path" :href="`/files/${record.json_path}`" target="_blank">打开原始 JSON</a><span v-else class="text-muted">-</span></dd>
          </dl>
        </div>
      </div>

      <!-- 录屏 -->
      <div class="card" v-if="record.recording_video_path">
        <div class="card-header">
          <span class="flex-center">
            <span class="header-icon"><el-icon><VideoPlay /></el-icon></span>
            录屏
          </span>
        </div>
        <div class="card-body">
          <div class="video-box">
            <video controls preload="metadata">
              <source :src="`/files/${record.recording_video_path}`" type="video/mp4">
            </video>
          </div>
          <dl class="kv-list" style="margin-top:12px;">
            <dt>录制秒数</dt><dd>{{ record.recording_duration_seconds || 0 }}</dd>
            <dt>是否有音频</dt><dd>{{ record.has_audio ? '是' : '否' }}</dd>
          </dl>
        </div>
      </div>

      <!-- 视频信息 + 截图 -->
      <div class="card">
        <div class="card-header">
          <span class="flex-center">
            <span class="header-icon"><el-icon><DataLine /></el-icon></span>
            视频信息与互动数据
          </span>
        </div>
        <div class="card-body">
          <div class="evidence-block">
            <div>
              <dl class="kv-list">
                <dt>博主名称</dt><dd>{{ record.blogger_name || '-' }}</dd>
                <dt>视频号ID</dt><dd><code class="font-mono">{{ record.video_channel_id || '-' }}</code></dd>
                <dt>视频标题</dt><dd>{{ record.title || '-' }}</dd>
                <dt>发布时间</dt><dd>{{ record.publish_time || '-' }}</dd>
                <dt>喜欢数</dt><dd>{{ record.like_count || '-' }}</dd>
                <dt>收藏数</dt><dd>{{ record.favorite_count || '-' }}</dd>
                <dt>转发数</dt><dd>{{ record.share_count || '-' }}</dd>
                <dt>评论数</dt><dd>{{ record.comment_count || '-' }}</dd>
                <dt>视频链接</dt><dd><a v-if="record.video_link" :href="record.video_link" target="_blank">{{ record.video_link }}</a><span v-else class="text-muted">-</span></dd>
              </dl>
            </div>
            <div>
              <div v-if="groupedShots.video.length" class="shot-grid">
                <div v-for="(s, i) in groupedShots.video" :key="i" class="shot-card">
                  <img :src="`/files/${s.path}`" loading="lazy" alt="">
                  <div class="label">{{ s.label }}</div>
                </div>
              </div>
              <div v-else class="empty-hint">暂无对应截图</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 博主信息 + 截图 -->
      <div class="card">
        <div class="card-header">
          <span class="flex-center">
            <span class="header-icon"><el-icon><User /></el-icon></span>
            博主身份信息
          </span>
        </div>
        <div class="card-body">
          <div class="evidence-block">
            <div>
              <dl class="kv-list">
                <dt>博主名称</dt><dd>{{ record.profile_name || record.blogger_name || '-' }}</dd>
                <dt>视频号ID</dt><dd><code class="font-mono">{{ record.profile_account || record.video_channel_id || '-' }}</code></dd>
                <dt>主体类型</dt><dd>{{ record.subject_type || '-' }}</dd>
                <dt>企业全称</dt><dd>{{ record.company_full_name || '-' }}</dd>
                <dt>ID原文</dt><dd>{{ record.video_channel_id_raw || '-' }}</dd>
                <dt>ID需审核</dt><dd>
                  <el-tag :type="record.video_channel_id_needs_review ? 'warning' : 'success'" size="small" effect="light">
                    {{ record.video_channel_id_needs_review ? '是' : '否' }}
                  </el-tag>
                </dd>
              </dl>
            </div>
            <div>
              <div v-if="groupedShots.author.length" class="shot-grid">
                <div v-for="(s, i) in groupedShots.author" :key="i" class="shot-card">
                  <img :src="`/files/${s.path}`" loading="lazy" alt="">
                  <div class="label">{{ s.label }}</div>
                </div>
              </div>
              <div v-else class="empty-hint">暂无对应截图</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 引流信息 + 截图 -->
      <div class="card">
        <div class="card-header">
          <span class="flex-center">
            <span class="header-icon"><el-icon><Connection /></el-icon></span>
            引流账号与公司信息
          </span>
        </div>
        <div class="card-body">
          <div class="evidence-block">
            <div>
              <dl class="kv-list">
                <dt>存在引流</dt><dd>
                  <el-tag :type="record.has_traffic_marker ? 'danger' : 'info'" size="small" effect="light">
                    {{ record.has_traffic_marker ? '是' : '否' }}
                  </el-tag>
                </dd>
                <dt>引流标记</dt><dd>{{ record.traffic_marker_text || '-' }}</dd>
                <dt>引流视频名称</dt><dd>{{ record.traffic_video_name || '-' }}</dd>
                <dt>目标博主</dt><dd>{{ record.target_blogger_name || '-' }}</dd>
                <dt>目标视频号ID</dt><dd><code class="font-mono">{{ record.target_video_channel_id || '-' }}</code></dd>
                <dt>ID原文</dt><dd>{{ record.target_video_channel_id_raw || '-' }}</dd>
                <dt>ID需审核</dt><dd>
                  <el-tag :type="record.target_video_channel_id_needs_review ? 'warning' : 'success'" size="small" effect="light">
                    {{ record.target_video_channel_id_needs_review !== undefined ? (record.target_video_channel_id_needs_review ? '是' : '否') : '-' }}
                  </el-tag>
                </dd>
                <dt>公司名</dt><dd>{{ record.target_company_name || '-' }}</dd>
                <dt>认证时间</dt><dd>{{ record.target_company_verified_at || '-' }}</dd>
              </dl>
              <div v-if="!record.has_traffic_marker && !groupedShots.traffic.length" class="empty-hint">
                未检测到引流标记
              </div>
            </div>
            <div>
              <div v-if="groupedShots.traffic.length" class="shot-grid">
                <div v-for="(s, i) in groupedShots.traffic" :key="i" class="shot-card">
                  <img :src="`/files/${s.path}`" loading="lazy" alt="">
                  <div class="label">{{ s.label }}</div>
                </div>
              </div>
              <div v-else class="empty-hint">暂无对应截图</div>
            </div>
          </div>
        </div>
      </div>

      <!-- ASR 语音转写与剧本比对 -->
      <div class="card" v-if="record.asr_text || record.script_match_status">
        <div class="card-header">
          <span class="flex-center">
            <span class="header-icon"><el-icon><Microphone /></el-icon></span>
            ASR 语音转写与剧本比对
          </span>
        </div>
        <div class="card-body">
          <div class="asr-block">
            <!-- 左：ASR 转写全文 -->
            <div>
              <div class="asr-label">ASR 转写文本</div>
              <div class="asr-text">{{ record.asr_text || '-' }}</div>
            </div>
            <!-- 右：剧本比对结果 -->
            <div>
              <div class="asr-label">剧本比对结果</div>
              <!-- 匹配成功 -->
              <div v-if="record.script_match_status === 'matched'" class="match-card">
                <div class="match-header">
                  <el-tag type="success" effect="dark" size="small">已匹配</el-tag>
                  <span class="match-scores">
                    {{ record.script_match_segments_matched || 0 }}/{{ record.script_match_segments_total || 0 }} 句
                    · 覆盖率 {{ scriptCoverageText }}
                  </span>
                </div>
                <div class="match-tagline">
                  <el-tag v-if="record.script_match_episode" size="small" effect="plain">{{ record.script_match_episode }}</el-tag>
                  <el-tag v-if="record.script_match_scene" size="small" effect="plain">场景 {{ record.script_match_scene }}</el-tag>
                  <el-tag v-if="record.script_match_character" size="small" effect="plain">{{ record.script_match_character }}</el-tag>
                  <el-tag v-if="record.script_match_location" size="small" effect="plain">{{ record.script_match_location }}</el-tag>
                  <el-tag type="primary" size="small" effect="light">拼音 {{ scriptPinyinPercent }}% · 字符 {{ scriptCharPercent }}%</el-tag>
                </div>
                <!-- 逐句对照列表 -->
                <div class="compare-panel" v-if="segmentsList.length">
                  <div class="compare-header">
                    <span class="ch-col ch-left">ASR 提取</span>
                    <span class="ch-col ch-mid">相似度</span>
                    <span class="ch-col ch-right">匹配剧本</span>
                  </div>
                  <div v-for="(seg, i) in segmentsList" :key="i" class="compare-row">
                    <div class="ch-col ch-left">{{ seg.asr_segment }}</div>
                    <div class="ch-col ch-mid">
                      <span class="sim-badge" :style="simStyle(seg.similarity)">{{ (seg.similarity * 100).toFixed(0) }}%</span>
                    </div>
                    <div class="ch-col ch-right">
                      <div class="seg-script">{{ seg.script_text }}</div>
                      <div class="seg-meta" v-if="seg.character || seg.episode || seg.scene">
                        {{ seg.character }}{{ seg.episode ? ' · ' + seg.episode : '' }}{{ seg.scene ? ' · ' + seg.scene : '' }}
                      </div>
                    </div>
                  </div>
                </div>
                <div v-else class="empty-hint">匹配的剧本原文未保存</div>
              </div>
              <!-- 未匹配 -->
              <div v-else-if="record.script_match_status === 'not_found'" class="match-card no-match">
                <div class="match-header">
                  <el-tag type="warning" effect="dark" size="small">未匹配</el-tag>
                </div>
                <div class="empty-hint">ASR 文本在剧本中未找到匹配内容</div>
              </div>
              <!-- 剧本不可用 -->
              <div v-else-if="record.script_match_status === 'script_unavailable'" class="match-card no-match">
                <div class="match-header">
                  <el-tag type="info" effect="dark" size="small">剧本不可用</el-tag>
                </div>
                <div class="empty-hint">该剧的台词文件未就绪，无法进行剧本比对</div>
              </div>
              <!-- 待处理 -->
              <div v-else-if="record.script_match_status === 'pending'" class="match-card no-match">
                <div class="match-header">
                  <el-tag type="info" effect="dark" size="small">待处理</el-tag>
                </div>
                <div class="empty-hint">ASR 已完成，等待剧本比对处理</div>
              </div>
              <!-- 其他 -->
              <div v-else class="match-card no-match">
                <div class="match-header">
                  <el-tag type="info" effect="dark" size="small">暂无比对</el-tag>
                </div>
                <div class="empty-hint">尚未进行剧本比对</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 其他截图 -->
      <div class="card" v-if="groupedShots.other.length">
        <div class="card-header">
          <span class="flex-center">
            <span class="header-icon"><el-icon><Picture /></el-icon></span>
            其他截图
          </span>
        </div>
        <div class="card-body">
          <div class="shot-grid">
            <div v-for="(s, i) in groupedShots.other" :key="i" class="shot-card">
              <a :href="`/files/${s.path}`" target="_blank">
                <img :src="`/files/${s.path}`" loading="lazy" alt="">
              </a>
              <div class="label">{{ s.label }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 原始 JSON -->
      <div class="card">
        <div class="card-header">
          <span class="flex-center">
            <span class="header-icon"><el-icon><Document /></el-icon></span>
            原始 JSON
          </span>
        </div>
        <div class="card-body">
          <el-collapse>
            <el-collapse-item title="展开完整记录">
              <pre class="json-pre">{{ jsonContent || '加载中...' }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft, CircleCloseFilled, CircleCheckFilled, RefreshLeft, Check,
  InfoFilled, VideoPlay, DataLine, User, Connection, Microphone, Picture, Document
} from '@element-plus/icons-vue'
import { evidenceApi, reviewApi } from '@/api/index'
import { formatDateTime } from '@/utils/time'
import { useAuthStore } from '@/stores/auth'
import axios from 'axios'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const readonly = computed(() => !!route.meta.readonly)
const companyReview = computed(() => !!route.meta.companyReview)
const record = ref({})
const loading = ref(false)
const reviewing = ref(false)
const pushing = ref(false)
const pushingCompany = ref(false)
const reviewNotes = ref('')
const jsonContent = ref('')

function goBack() {
  const tid = record.value.task_id || Number(route.query.task_id) || 0
  if (companyReview.value) {
    router.push('/company/review-pool')
    return
  }
  if (readonly.value) {
    router.back()
    return
  }
  router.push(tid ? { path: '/collector/evidence', query: { task_id: String(tid) } } : '/collector/evidence')
}

const canPushPolice = computed(() =>
  record.value.pushed_to_company &&
  record.value.review_status === '侵权' &&
  !record.value.pushed_to_police
)

const reviewType = computed(() => record.value.review_status === '侵权' ? 'danger' : record.value.review_status === '未侵权' ? 'success' : 'info')

const scriptPinyinPercent = computed(() => {
  const v = record.value.script_match_pinyin_score
  if (v === null || v === undefined) return '-'
  return (v * 100).toFixed(1)
})

const scriptCharPercent = computed(() => {
  const v = record.value.script_match_char_score
  if (v === null || v === undefined) return '-'
  return (v * 100).toFixed(1)
})

const scriptCoverageText = computed(() => {
  const v = record.value.script_match_similarity
  if (v === null || v === undefined || v === 0) return '-'
  return (v * 100).toFixed(1) + '%'
})

const segmentsList = computed(() => record.value.script_match_segments || [])

const infringementScore = computed(() => {
  const r = record.value
  if (r.infringement_score > 0 || r.infringement_level) return r.infringement_score
  if (!r.script_match_status || r.script_match_status === 'pending') return null
  return 0
})

const infringementLevelType = computed(() => {
  const l = record.value.infringement_level
  if (l === '侵权') return 'danger'
  if (l === '高度疑似') return 'danger'
  if (l === '疑似') return 'warning'
  if (l === '待观察') return 'info'
  return ''
})

function simStyle(v) {
  if (v >= 0.7) return 'background:var(--success-bg);color:var(--success);border:1px solid var(--success)'
  if (v >= 0.4) return 'background:var(--warning-bg);color:var(--warning);border:1px solid var(--warning)'
  return 'background:var(--danger-bg);color:var(--danger);border:1px solid var(--danger)'
}

const groupedShots = computed(() => {
  const groups = { video: [], author: [], traffic: [], other: [] }
  for (const s of record.value.screenshots || []) {
    const path = typeof s === 'string' ? s : (s?.path || '')
    const base = path.split(/[/\\]/).pop()?.toLowerCase() || ''
    const item = { path, label: shotLabel(path) }
    if (base.startsWith('play_') || base.startsWith('share_')) groups.video.push(item)
    else if (base.startsWith('profile_') || base.startsWith('author_')) groups.author.push(item)
    else if (base.startsWith('traffic_')) groups.traffic.push(item)
    else groups.other.push(item)
  }
  return groups
})

function shotLabel(path) {
  const name = (path || '').split(/[/\\]/).pop()?.toLowerCase() || ''
  if (name.startsWith('play_')) return '视频播放页截图'
  if (name.startsWith('share_sheet_')) return '分享面板截图'
  if (name.startsWith('share_copy_')) return '复制链接区域截图'
  if (name.startsWith('profile_card_name_region_')) return '博主名称裁剪图'
  if (name.startsWith('profile_card_')) return '博主资料卡截图'
  if (name.startsWith('profile_info_')) return '博主更多信息页截图'
  if (name.startsWith('traffic_marker_region_')) return '引流标记裁剪图'
  if (name.startsWith('traffic_marker_full_')) return '引流标记整页截图'
  if (name.startsWith('traffic_popup_')) return '引流弹窗截图'
  if (name.startsWith('traffic_landing_')) return '引流落地页截图'
  if (name.startsWith('traffic_page_name_region_')) return '引流账号名称裁剪图'
  if (name.startsWith('traffic_page_')) return '引流账号资料页截图'
  if (name.startsWith('traffic_info_')) return '引流账号更多信息页截图'
  return name
}

async function fetchDetail() {
  loading.value = true
  try {
    const { data } = await evidenceApi.get(parseInt(route.params.id)||0)
    record.value = data; reviewNotes.value = data.review_notes || ''
    if (data.json_path) {
      try { const res = await axios.get(`/files/${data.json_path}`); jsonContent.value = JSON.stringify(res.data, null, 2) }
      catch (e) { jsonContent.value = '无法加载 JSON: ' + (e.response?.status || e.message || '未知错误') }
    } else {
      jsonContent.value = '无 JSON 文件路径'
    }
  } catch (e) { ElMessage.error('加载失败') }
  finally { loading.value = false }
}

async function doReview(status) {
  reviewing.value = true
  try {
    const { data } = await reviewApi.update(parseInt(route.params.id) || 0, {
      review_status: status,
      review_notes: reviewNotes.value,
    })
    record.value.review_status = status
    record.value.review_notes = reviewNotes.value
    ElMessage.success(`已标注: ${status}`)
    const peerIds = data?.peer_ids || []
    const n = data?.peer_count || peerIds.length
    if (companyReview.value && n > 0 && status) {
      try {
        await ElMessageBox.confirm(
          `检测到该博主在同剧下还有 ${n} 条证据未标记为「${status}」，是否一键同步？`,
          '一键同步标记',
          { confirmButtonText: '一键标记', cancelButtonText: '仅本条', type: 'warning' },
        )
        await reviewApi.batch({
          evidence_ids: peerIds,
          review_status: status,
          review_notes: reviewNotes.value,
        })
        ElMessage.success(`已同步标记 ${peerIds.length} 条`)
      } catch {
        /* 用户取消 */
      }
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '标注失败')
  } finally {
    reviewing.value = false
  }
}

async function pushToCompany() {
  pushingCompany.value = true
  try {
    await evidenceApi.pushCompany([parseInt(route.params.id)], auth.assignee || '取证员')
    record.value.pushed_to_company = true
    record.value.pushed_to_company_at = new Date().toISOString()
    ElMessage.success('已推送至公司核查池')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '推送失败')
  } finally {
    pushingCompany.value = false
  }
}

async function pushToPolice() {
  pushing.value = true
  try {
    await evidenceApi.push([parseInt(route.params.id)], auth.assignee || '取证员')
    record.value.pushed_to_police = true
    record.value.pushed_at = new Date().toISOString()
    ElMessage.success('已推送给公安')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '推送失败')
  } finally {
    pushing.value = false
  }
}

onMounted(fetchDetail)
</script>

<style scoped>
/* ── 侵权评分条 ── */
.infringement-bar {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 16px 20px;
  border-radius: var(--radius);
  margin-bottom: 16px;
  border: 1px solid transparent;
}

.infringement-bar.danger {
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  border-color: #fca5a5;
}

.infringement-bar.warning {
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  border-color: #fcd34d;
}

.infringement-bar.info {
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border-color: #93c5fd;
}

.infringement-score {
  display: flex;
  align-items: baseline;
  flex-shrink: 0;
}

.score-num {
  font-size: 32px;
  font-weight: 800;
  line-height: 1;
}

.infringement-bar.danger .score-num { color: #dc2626; }
.infringement-bar.warning .score-num { color: #d97706; }
.infringement-bar.info .score-num { color: #2563eb; }

.score-unit {
  font-size: 14px;
  color: var(--muted);
  margin-left: 2px;
}

.infringement-info { flex: 1; min-width: 0; }

.infringement-label {
  font-size: 15px;
  font-weight: 700;
  color: var(--ink);
  margin-bottom: 3px;
}

.infringement-detail {
  font-size: 12px;
  color: var(--muted);
}

.infringement-score { cursor: help; }

/* ── 分数 tooltip ── */
.tooltip-formula {
  font-size: 13px;
  line-height: 1.8;
  min-width: 280px;
}

.tooltip-title {
  font-weight: 700;
  font-size: 14px;
  color: var(--ink);
  margin-bottom: 8px;
}

.tooltip-row {
  display: flex;
  justify-content: space-between;
  gap: 20px;
}

.tooltip-row span:first-child { color: var(--muted); }
.tooltip-row span:last-child { font-weight: 600; color: var(--ink); }

.tooltip-row.total { font-size: 15px; font-weight: 700; }
.tooltip-row.total span { color: var(--ink); }

.tooltip-divider {
  height: 1px;
  background: var(--line);
  margin: 6px 0;
}

.tooltip-levels {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--muted);
}

.evidence-block {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) minmax(360px, 1.6fr);
  gap: 24px;
}

/* ── 截图网格 ── */
.shot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
}

.shot-card {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--paper);
  position: relative;
}

.shot-card img {
  display: block;
  width: 100%;
  max-height: 460px;
  object-fit: contain;
  background: #0d0d0d;
  cursor: default;
}

/* 鼠标悬停原图预览 — 页面居中展示 */
.shot-card:hover {
  overflow: visible;
  z-index: 100;
}

.shot-card:hover img {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 9999;
  width: auto;
  max-width: 90vw;
  max-height: 90vh;
  height: auto;
  cursor: default;
  border-radius: 2px;
  box-shadow: 0 8px 40px rgba(0,0,0,0.6);
}

.shot-card:hover .label {
  display: none;
}

.shot-card .label {
  padding: 6px 10px;
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  border-top: 1px solid var(--line);
  position: relative;
  background: var(--paper);
}

.video-box {
  background: #0D1117;
  border-radius: var(--radius);
  overflow: hidden;
}

video {
  display: block;
  width: 100%;
  max-height: 70vh;
  background: #0D1117;
}

.empty-hint {
  color: var(--muted);
  background: var(--bg-alt);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  padding: 16px;
  text-align: center;
  font-size: 13px;
}

.json-pre {
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.6;
  font-family: var(--font-mono);
  color: var(--text);
  background: var(--bg-alt);
  padding: 12px;
  border-radius: var(--radius);
}

/* ── ASR 剧本逐句对照 ── */
.asr-block {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  align-items: stretch;
}

.asr-block > div {
  display: flex;
  flex-direction: column;
}

.asr-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 8px;
}

.asr-text {
  white-space: pre-wrap;
  height: 100%;
  min-height: 200px;
  overflow-y: auto;
  background: var(--bg-alt);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 12px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--ink);
}

.match-card {
  background: var(--success-bg);
  border: 1px solid var(--success);
  border-radius: var(--radius);
  overflow: hidden;
}

.match-card.no-match {
  background: var(--warning-bg);
  border-color: var(--warning);
}

.match-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: rgba(255,255,255,0.5);
  border-bottom: 1px solid var(--line);
  flex-wrap: wrap;
}

.match-scores {
  margin-left: auto;
  font-size: 12px;
  color: var(--text);
  background: var(--paper);
  padding: 2px 10px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--line);
}

.match-tagline {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 14px;
}

/* 逐句对照面板 */
.compare-panel {
  margin: 0 14px 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
  max-height: 460px;
  overflow-y: auto;
  background: var(--paper);
}

.compare-header {
  display: flex;
  background: var(--bg-alt);
  border-bottom: 1px solid var(--line);
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
  position: sticky;
  top: 0;
  z-index: 1;
}

.compare-row {
  display: flex;
  border-bottom: 1px solid var(--line);
  font-size: 13px;
  line-height: 1.7;
}

.compare-row:last-child { border-bottom: none; }

.ch-col { padding: 8px 10px; }

.ch-left {
  flex: 0 0 36%;
  color: var(--ink);
}

.ch-mid {
  flex: 0 0 12%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-alt);
  border-left: 1px solid var(--line);
  border-right: 1px solid var(--line);
}

.ch-right {
  flex: 1;
  background: var(--paper);
}

.sim-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  white-space: nowrap;
}

.seg-script {
  font-size: 13px;
  color: var(--ink);
}

.seg-meta {
  font-size: 11px;
  color: var(--muted);
  margin-top: 2px;
}

@media (max-width: 860px) {
  .evidence-block { grid-template-columns: 1fr; }
  .asr-block { grid-template-columns: 1fr; }
}
</style>
