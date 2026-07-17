<template>
  <div class="cockpit" v-loading="loading">
    <!-- 子标题 + 筛选 -->
    <div class="cockpit-toolbar">
      <div class="unit-name">嘉兴知识产权保护 · 运行态势</div>
      <div class="filters">
        <el-radio-group v-model="period" size="small" @change="fetchData">
          <el-radio-button value="today">今日</el-radio-button>
          <el-radio-button value="7d">近7日</el-radio-button>
          <el-radio-button value="30d">近30日</el-radio-button>
          <el-radio-button value="all">累计</el-radio-button>
        </el-radio-group>
        <el-button type="primary" size="small" @click="fetchData">查询</el-button>
      </div>
    </div>

    <div class="cockpit-grid">
      <!-- 左栏 -->
      <section class="col left">
        <div class="quick-row">
          <div class="quick-card warn">
            <div class="q-num">{{ data.company_pending || 0 }}</div>
            <div class="q-lbl">公司待复核</div>
          </div>
          <div class="quick-card danger">
            <div class="q-num">{{ data.infringement?.high || 0 }}</div>
            <div class="q-lbl">高度疑似</div>
          </div>
          <div class="quick-card primary">
            <div class="q-num">{{ data.pushed_total || 0 }}</div>
            <div class="q-lbl">已推送线索</div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-title">业务链路</div>
          <div class="pipe-row">
            <div class="pipe-step" v-for="s in pipelineSteps" :key="s.label">
              <div class="pipe-num" :style="{ color: s.color }">{{ s.value }}</div>
              <div class="pipe-lbl">{{ s.label }}</div>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-title">任务态势</div>
          <div class="rings">
            <div class="ring-item" v-for="r in taskRings" :key="r.label">
              <div class="ring" :style="ringStyle(r.pct, r.color)">
                <span>{{ r.value }}</span>
              </div>
              <div class="ring-label">{{ r.label }}</div>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-title">工单状态</div>
          <div class="vbars">
            <div v-for="b in woBars" :key="b.label" class="vbar-item">
              <div class="vbar-track">
                <div class="vbar-fill" :style="{ height: b.h + '%', background: b.color }" :title="b.value"></div>
              </div>
              <div class="vbar-val">{{ b.value }}</div>
              <div class="vbar-lbl">{{ b.label }}</div>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-title">侵权等级分布</div>
          <div class="donut-row">
            <div class="donut" :style="donutStyle"></div>
            <div class="donut-legend">
              <div v-for="l in infringeLegend" :key="l.label" class="leg-item">
                <i :style="{ background: l.color }"></i>
                <span>{{ l.label }}</span>
                <strong>{{ l.value }}</strong>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 中栏 -->
      <section class="col center">
        <div class="panel hero-panel">
          <div class="panel-title">运行总览</div>
          <div class="hero-kpis">
            <div class="hk" v-for="k in heroKpis" :key="k.label">
              <div class="hk-val">{{ k.value }}</div>
              <div class="hk-lbl">{{ k.label }}</div>
            </div>
          </div>
          <div class="trend-wrap">
            <div class="trend-caption">近14日 · 证据 / 推公司 / 公司复核 / 推公安</div>
            <div class="trend-chart">
              <div v-for="d in data.trend_14d || []" :key="d.date" class="trend-col">
                <div class="trend-bars">
                  <div class="tbar ev" :style="{ height: barH(d.evidence) + 'px' }"></div>
                  <div class="tbar cp" :style="{ height: barH(d.company_pushed) + 'px' }"></div>
                  <div class="tbar cr" :style="{ height: barH(d.company_reviewed) + 'px' }"></div>
                  <div class="tbar ps" :style="{ height: barH(d.pushed) + 'px' }"></div>
                </div>
                <span>{{ d.date }}</span>
              </div>
            </div>
            <div class="trend-legend">
              <span><i class="ev"></i>证据</span>
              <span><i class="cp"></i>推公司</span>
              <span><i class="cr"></i>公司复核</span>
              <span><i class="ps"></i>推公安</span>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-title row-between">
            <span>指标统计</span>
            <router-link to="/police/clues" class="more-link">查看线索 →</router-link>
          </div>
          <table class="ind-table">
            <thead>
              <tr>
                <th>剧名 / 指标</th>
                <th>证据数</th>
                <th>已推送</th>
                <th>推送率</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!(data.indicators || []).length">
                <td colspan="4" class="empty">暂无工单剧名数据</td>
              </tr>
              <tr v-for="row in data.indicators || []" :key="row.name">
                <td class="name">{{ row.name }}</td>
                <td>{{ row.total }}</td>
                <td>{{ row.pushed }}</td>
                <td>
                  <div class="rate-cell">
                    <div class="rate-bar"><i :style="{ width: Math.min(row.rate, 100) + '%' }"></i></div>
                    <span>{{ row.rate }}%</span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- 右栏 -->
      <section class="col right">
        <div class="panel">
          <div class="panel-title">最新操作动态</div>
          <div class="act-list">
            <div
              v-for="(a, idx) in data.recent_activity || []"
              :key="idx"
              class="act-row"
              @click="a.evidence_id && $router.push(`/police/evidence/${a.evidence_id}`)"
            >
              <span class="act-tag" :class="a.type">{{ actTag(a.type) }}</span>
              <div class="act-body">
                <div class="act-title">{{ a.title }}</div>
                <div class="act-sub">{{ a.label }} · {{ a.actor }}</div>
              </div>
              <span class="act-time">{{ formatShort(a.time) }}</span>
            </div>
            <div v-if="!(data.recent_activity || []).length" class="media-empty">暂无操作记录</div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-title row-between">
            <span>最新推送线索</span>
            <router-link to="/police/clues" class="more-link">更多</router-link>
          </div>
          <div class="media-grid">
            <div
              v-for="item in data.recent_pushed || []"
              :key="item.id"
              class="media-card"
              @click="$router.push(`/police/evidence/${item.id}`)"
            >
              <div class="media-thumb">
                <img v-if="item.thumb" :src="`/files/${item.thumb}`" />
                <span v-else class="no-img">无图</span>
              </div>
              <div class="media-meta">
                <div class="media-title">{{ item.title }}</div>
                <div class="media-sub">{{ item.blogger_name || '未知博主' }}</div>
                <div class="media-time">{{ formatShort(item.pushed_at) }}</div>
              </div>
            </div>
            <div v-if="!(data.recent_pushed || []).length" class="media-empty">暂无已推送线索</div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-title">热点剧名排行</div>
          <div class="rank-list">
            <div v-for="(d, i) in data.top_dramas || []" :key="d.name" class="rank-row">
              <span class="rk" :class="'r' + (i + 1)">{{ i + 1 }}</span>
              <span class="rn">{{ d.name }}</span>
              <div class="rbar"><i :style="{ width: rankWidth(d.count) + '%' }"></i></div>
              <span class="rc">{{ d.count }}</span>
            </div>
            <div v-if="!(data.top_dramas || []).length" class="media-empty">暂无排行</div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { dashboardApi } from '@/api/index'

const loading = ref(false)
const period = ref('all')
const data = ref({})

const heroKpis = computed(() => [
  { label: '运行时长(h)', value: data.value.runtime_hours ?? 0 },
  { label: '采集任务', value: data.value.tasks?.total || 0 },
  { label: '取证条数', value: data.value.evidence_total || 0 },
  { label: '覆盖剧名', value: data.value.drama_count || 0 },
  { label: '工单总数', value: data.value.work_orders || 0 },
  { label: '收集链接', value: data.value.links_collected || 0 },
])

const pipelineSteps = computed(() => {
  const p = data.value.pipeline || {}
  return [
    { label: '已推公司', value: p.company_pushed || 0, color: '#165DFF' },
    { label: '待复核', value: p.company_pending || 0, color: '#FF7D00' },
    { label: '标侵权', value: p.company_infringement || 0, color: '#F53F3F' },
    { label: '未侵权', value: p.company_not_infringement || 0, color: '#86909C' },
    { label: '已推公安', value: p.police_pushed || 0, color: '#00B42A' },
  ]
})

const taskRings = computed(() => {
  const t = data.value.tasks || {}
  const total = Math.max(t.total || 1, 1)
  return [
    { label: '进行中', value: t.running || 0, pct: ((t.running || 0) / total) * 100, color: '#FF7D00' },
    { label: '已完成', value: t.completed || 0, pct: ((t.completed || 0) / total) * 100, color: '#00B42A' },
    { label: '待执行', value: t.pending || 0, pct: ((t.pending || 0) / total) * 100, color: '#165DFF' },
  ]
})

const woBars = computed(() => {
  const s = data.value.work_order_status || {}
  const items = [
    { label: '已提交', value: s.submitted || 0, color: '#4080FF' },
    { label: '取证中', value: s.collecting || 0, color: '#FF7D00' },
    { label: '部分完成', value: s.partial || 0, color: '#F7BA1E' },
    { label: '已完成', value: s.completed || 0, color: '#00B42A' },
  ]
  const max = Math.max(...items.map(i => i.value), 1)
  return items.map(i => ({ ...i, h: Math.max(8, Math.round((i.value / max) * 100)) }))
})

const infringeLegend = computed(() => {
  const inf = data.value.infringement || {}
  return [
    { label: '高度疑似', value: inf.high || 0, color: '#F53F3F' },
    { label: '疑似', value: inf.mid || 0, color: '#FF7D00' },
    { label: '待观察', value: inf.low || 0, color: '#165DFF' },
    { label: '已标侵权', value: inf.reviewed_infringement || 0, color: '#00B42A' },
  ]
})

const donutStyle = computed(() => {
  const parts = infringeLegend.value
  const total = parts.reduce((s, p) => s + p.value, 0) || 1
  let acc = 0
  const stops = parts.map(p => {
    const start = acc
    acc += (p.value / total) * 100
    return `${p.color} ${start}% ${acc}%`
  })
  return {
    background: `conic-gradient(${stops.join(', ')})`,
  }
})

const maxTrend = computed(() => {
  const vals = (data.value.trend_14d || []).flatMap(d => [
    d.evidence, d.pushed, d.company_pushed || 0, d.company_reviewed || 0,
  ])
  return Math.max(...vals, 1)
})

const maxRank = computed(() => Math.max(...(data.value.top_dramas || []).map(d => d.count), 1))

function barH(v) { return Math.max(3, Math.round(((v || 0) / maxTrend.value) * 72)) }
function rankWidth(v) { return Math.max(6, Math.round((v / maxRank.value) * 100)) }

function actTag(type) {
  if (type === 'push_company') return '推公司'
  if (type === 'company_review') return '复核'
  if (type === 'push_police') return '推公安'
  return '动态'
}

function ringStyle(pct, color) {
  const p = Math.min(100, Math.max(0, pct))
  return {
    background: `conic-gradient(${color} 0 ${p}%, #e8edf5 ${p}% 100%)`,
  }
}

function formatShort(s) {
  if (!s) return ''
  return String(s).replace('T', ' ').slice(0, 16)
}

async function fetchData() {
  loading.value = true
  try {
    const { data: res } = await dashboardApi.police({ period: period.value })
    data.value = res || {}
  } catch (e) {
    data.value = {}
    ElMessage.error(e.response?.data?.detail || e.message || '驾驶舱数据加载失败，请确认后端已重启')
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
</script>

<style scoped>
.cockpit { min-height: calc(100vh - 88px); }

.cockpit-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.unit-name {
  font-size: 16px;
  font-weight: 700;
  color: #1D2129;
  padding-left: 10px;
  border-left: 3px solid #165DFF;
}
.filters { display: flex; align-items: center; gap: 10px; }

.cockpit-grid {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr) 300px;
  gap: 12px;
  align-items: start;
}

.panel {
  background: #fff;
  border: 1px solid #e5e8ef;
  border-radius: 8px;
  padding: 12px 14px 14px;
  margin-bottom: 12px;
  box-shadow: 0 1px 4px rgba(15, 40, 80, 0.04);
}
.panel-title {
  font-size: 13px;
  font-weight: 700;
  color: #1D2129;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f2f5;
}
.row-between { display: flex; justify-content: space-between; align-items: center; }
.more-link { font-size: 12px; font-weight: 500; }

/* 快捷卡 */
.quick-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-bottom: 12px; }
.quick-card {
  border-radius: 8px;
  padding: 12px 8px;
  text-align: center;
  color: #fff;
}
.quick-card.warn { background: linear-gradient(135deg, #FF9A2E, #FF7D00); }
.quick-card.danger { background: linear-gradient(135deg, #F76560, #F53F3F); }
.quick-card.primary { background: linear-gradient(135deg, #4080FF, #165DFF); }
.q-num { font-size: 22px; font-weight: 800; line-height: 1.1; }
.q-lbl { font-size: 11px; opacity: 0.92; margin-top: 4px; }

/* 业务链路 */
.pipe-row {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 4px;
}
.pipe-step { text-align: center; padding: 4px 0; }
.pipe-num { font-size: 18px; font-weight: 800; line-height: 1.2; }
.pipe-lbl { font-size: 10px; color: #86909C; margin-top: 2px; white-space: nowrap; }

/* 环图 */
.rings { display: flex; justify-content: space-around; gap: 6px; }
.ring-item { text-align: center; }
.ring {
  width: 68px; height: 68px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  margin: 0 auto 6px;
  position: relative;
}
.ring::after {
  content: '';
  position: absolute;
  inset: 10px;
  background: #fff;
  border-radius: 50%;
}
.ring span {
  position: relative; z-index: 1;
  font-size: 16px; font-weight: 800; color: #1D2129;
}
.ring-label { font-size: 11px; color: #86909C; }

/* 竖条 */
.vbars { display: flex; align-items: flex-end; justify-content: space-around; height: 120px; gap: 4px; }
.vbar-item { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; }
.vbar-track {
  flex: 1; width: 100%; max-width: 28px;
  display: flex; align-items: flex-end;
  background: #f2f5fa; border-radius: 4px 4px 0 0;
}
.vbar-fill { width: 100%; border-radius: 4px 4px 0 0; min-height: 4px; transition: height 0.3s; }
.vbar-val { font-size: 12px; font-weight: 700; margin-top: 4px; color: #1D2129; }
.vbar-lbl { font-size: 10px; color: #86909C; white-space: nowrap; }

/* 甜甜圈 */
.donut-row { display: flex; align-items: center; gap: 14px; }
.donut {
  width: 88px; height: 88px; border-radius: 50%; flex-shrink: 0;
  position: relative;
}
.donut::after {
  content: '';
  position: absolute;
  inset: 22px;
  background: #fff;
  border-radius: 50%;
}
.donut-legend { flex: 1; display: flex; flex-direction: column; gap: 6px; }
.leg-item {
  display: flex; align-items: center; gap: 6px; font-size: 12px; color: #4E5969;
}
.leg-item i { width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }
.leg-item strong { margin-left: auto; color: #1D2129; }

/* 中栏总览 */
.hero-panel { min-height: 280px; }
.hero-kpis {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-bottom: 14px;
}
.hk {
  background: linear-gradient(180deg, #f5f8ff 0%, #eef3fb 100%);
  border: 1px solid #e0e8f5;
  border-radius: 6px;
  padding: 10px 8px;
  text-align: center;
}
.hk-val { font-size: 20px; font-weight: 800; color: #0E42D2; }
.hk-lbl { font-size: 11px; color: #86909C; margin-top: 2px; }

.trend-caption { font-size: 12px; color: #86909C; margin-bottom: 6px; }
.trend-chart {
  display: flex; align-items: flex-end; gap: 4px; height: 100px;
}
.trend-col { flex: 1; display: flex; flex-direction: column; align-items: center; }
.trend-bars { display: flex; gap: 2px; align-items: flex-end; height: 76px; }
.tbar { width: 5px; border-radius: 2px 2px 0 0; min-height: 2px; }
.tbar.ev { background: #165DFF; }
.tbar.cp { background: #4080FF; }
.tbar.cr { background: #FF7D00; }
.tbar.ps { background: #00B42A; }
.trend-col span { font-size: 9px; color: #86909C; margin-top: 4px; transform: scale(0.9); }
.trend-legend { display: flex; gap: 10px; font-size: 11px; color: #86909C; margin-top: 6px; flex-wrap: wrap; }
.trend-legend i {
  display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 4px; vertical-align: middle;
}
.trend-legend i.ev { background: #165DFF; }
.trend-legend i.cp { background: #4080FF; }
.trend-legend i.cr { background: #FF7D00; }
.trend-legend i.ps { background: #00B42A; }

/* 操作动态 */
.act-list { display: flex; flex-direction: column; gap: 8px; max-height: 280px; overflow-y: auto; }
.act-row {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 6px 4px; border-radius: 6px; cursor: pointer;
  transition: background 0.15s;
}
.act-row:hover { background: #f5f8ff; }
.act-tag {
  flex-shrink: 0; font-size: 10px; font-weight: 700;
  padding: 2px 6px; border-radius: 3px; margin-top: 2px;
}
.act-tag.push_company { background: #e8f3ff; color: #165DFF; }
.act-tag.company_review { background: #fff7e8; color: #FF7D00; }
.act-tag.push_police { background: #e8ffea; color: #00B42A; }
.act-body { flex: 1; min-width: 0; }
.act-title {
  font-size: 12px; font-weight: 600; color: #1D2129;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.act-sub { font-size: 10px; color: #86909C; margin-top: 2px; }
.act-time { flex-shrink: 0; font-size: 10px; color: #C9CDD4; }

/* 指标表 */
.ind-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.ind-table th {
  text-align: left; padding: 8px 6px; color: #86909C; font-weight: 600;
  border-bottom: 1px solid #f0f2f5; background: #fafbfc;
}
.ind-table td { padding: 9px 6px; border-bottom: 1px solid #f5f6f8; color: #4E5969; }
.ind-table td.name { color: #1D2129; font-weight: 600; max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ind-table .empty { text-align: center; color: #86909C; padding: 20px; }
.rate-cell { display: flex; align-items: center; gap: 6px; }
.rate-bar { flex: 1; height: 6px; background: #eef1f6; border-radius: 3px; overflow: hidden; min-width: 40px; }
.rate-bar i { display: block; height: 100%; background: linear-gradient(90deg, #4080FF, #165DFF); border-radius: 3px; }

/* 媒体墙 */
.media-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.media-card {
  border: 1px solid #e8ecf2; border-radius: 6px; overflow: hidden; cursor: pointer;
  transition: box-shadow 0.2s, transform 0.2s; background: #fff;
}
.media-card:hover { box-shadow: 0 4px 12px rgba(22, 93, 255, 0.12); transform: translateY(-1px); }
.media-thumb {
  height: 72px; background: #0d1117;
  display: flex; align-items: center; justify-content: center; overflow: hidden;
}
.media-thumb img { width: 100%; height: 100%; object-fit: cover; }
.no-img { color: rgba(255,255,255,0.35); font-size: 12px; }
.media-meta { padding: 6px 8px 8px; }
.media-title {
  font-size: 12px; font-weight: 600; color: #1D2129;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.media-sub, .media-time { font-size: 10px; color: #86909C; margin-top: 2px; }
.media-empty { grid-column: 1 / -1; text-align: center; color: #86909C; font-size: 12px; padding: 24px 0; }

/* 排行 */
.rank-list { display: flex; flex-direction: column; gap: 10px; }
.rank-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.rk {
  width: 18px; height: 18px; border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 800; background: #e8edf5; color: #4E5969; flex-shrink: 0;
}
.rk.r1 { background: #F53F3F; color: #fff; }
.rk.r2 { background: #FF7D00; color: #fff; }
.rk.r3 { background: #F7BA1E; color: #fff; }
.rn { width: 72px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #1D2129; font-weight: 500; }
.rbar { flex: 1; height: 8px; background: #eef1f6; border-radius: 4px; overflow: hidden; }
.rbar i { display: block; height: 100%; background: linear-gradient(90deg, #7aa2ff, #165DFF); border-radius: 4px; }
.rc { width: 28px; text-align: right; font-weight: 700; color: #165DFF; }

@media (max-width: 1200px) {
  .cockpit-grid { grid-template-columns: 1fr 1fr; }
  .col.left { grid-column: 1 / -1; }
  .col.left .quick-row { max-width: 480px; }
}
@media (max-width: 800px) {
  .cockpit-grid { grid-template-columns: 1fr; }
}
</style>
