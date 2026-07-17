<template>
  <div class="page-container" v-loading="loading">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ order.drama_name || '工单详情' }}</h1>
        <p class="page-subtitle">{{ order.order_no }} · {{ order.status_label }}</p>
      </div>
      <el-button @click="$router.push('/company')">返回列表</el-button>
    </div>

    <div class="stat-grid">
      <div class="stat-card"><div class="stat-value">{{ order.company_pushed_count || 0 }}</div><div class="stat-label">已送核查池</div></div>
      <div class="stat-card"><div class="stat-value">{{ reviewStats.infringement || 0 }}</div><div class="stat-label">已标侵权</div></div>
      <div class="stat-card"><div class="stat-value">{{ reviewStats.not_infringement || 0 }}</div><div class="stat-label">已标未侵权</div></div>
      <div class="stat-card"><div class="stat-value">{{ order.pushed_count || 0 }}</div><div class="stat-label">已推送公安</div></div>
    </div>

    <div class="card">
      <div class="card-header">进度时间线</div>
      <div class="card-body">
        <el-timeline>
          <el-timeline-item :type="order.created_at ? 'primary' : 'info'" timestamp="创建">
            {{ formatDateTimeShort(order.created_at) || '—' }}
          </el-timeline-item>
          <el-timeline-item :type="order.submitted_at ? 'primary' : 'info'" timestamp="提交">
            {{ formatDateTimeShort(order.submitted_at) || '待提交' }}
          </el-timeline-item>
          <el-timeline-item :type="order.started_at ? 'warning' : 'info'" timestamp="开始取证">
            {{ formatDateTimeShort(order.started_at) || '待开始' }}
          </el-timeline-item>
          <el-timeline-item :type="order.company_pushed_count ? 'primary' : 'info'" timestamp="推送核查池">
            {{ order.company_pushed_count ? `已推送 ${order.company_pushed_count} 条` : '待取证端推送' }}
          </el-timeline-item>
          <el-timeline-item :type="order.pushed_count ? 'success' : 'info'" timestamp="推送公安">
            {{ order.pushed_count ? `已推送 ${order.pushed_count} 条` : '待取证端推送' }}
          </el-timeline-item>
        </el-timeline>
      </div>
    </div>

    <div class="card">
      <div class="card-header">工单信息</div>
      <div class="card-body info-grid">
        <div><span class="lbl">诉求说明</span><p>{{ order.description || '—' }}</p></div>
        <div><span class="lbl">链接池</span><p>{{ linkPool.pending_count || 0 }} 条待取证 / 共 {{ linkPool.link_count || 0 }} 条</p></div>
        <div><span class="lbl">提交人</span><p>{{ order.submitter }}</p></div>
        <div><span class="lbl">负责人</span><p>{{ order.assigned_to || '待认领' }}</p></div>
      </div>
    </div>

    <div class="card" v-if="attachments.length">
      <div class="card-header">附件</div>
      <div class="card-body">
        <div v-for="a in attachments" :key="a.id" class="attach-row">
          <el-icon><Document /></el-icon> {{ a.file_name }}
          <el-tag size="small">{{ a.file_type }}</el-tag>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-header" style="display:flex;justify-content:space-between;align-items:center;">
        <span>核查池证据（取证推送后可复核）</span>
        <router-link to="/company/review-pool">前往核查池 →</router-link>
      </div>
      <div class="card-body" style="padding:0;">
        <ResultListPage
          v-if="order.id"
          :embed-work-order-id="order.id"
          embed-mode="company"
          hide-chrome
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Document } from '@element-plus/icons-vue'
import { workOrderApi } from '@/api/index'
import { formatDateTimeShort } from '@/utils/time'
import ResultListPage from '@/views/ResultListPage.vue'

const route = useRoute()
const loading = ref(false)
const order = ref({})
const attachments = ref([])
const reviewStats = computed(() => order.value.review_stats || {})
const linkPool = computed(() => order.value.link_pool || {})

async function fetchDetail() {
  loading.value = true
  try {
    const { data } = await workOrderApi.get(parseInt(route.params.id))
    order.value = data
    attachments.value = (data.attachments || []).map(a => ({ id: a.id, file_name: a.file_name, file_type: a.file_type }))
  } finally {
    loading.value = false
  }
}

onMounted(fetchDetail)
</script>

<style scoped>
.stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
.stat-card { background: var(--paper); border: 1px solid var(--line); border-radius: var(--radius); padding: 16px; text-align: center; }
.stat-value { font-size: 28px; font-weight: 800; }
.stat-label { font-size: 12px; color: var(--muted); }
.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.info-grid .lbl { font-size: 12px; color: var(--muted); }
.info-grid p { margin-top: 4px; font-size: 14px; }
.attach-row { display: flex; align-items: center; gap: 8px; padding: 6px 0; font-size: 13px; }
@media (max-width: 640px) { .stat-grid { grid-template-columns: 1fr 1fr; } }
</style>
