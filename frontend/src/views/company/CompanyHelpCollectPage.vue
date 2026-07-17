<template>
  <div class="soft-page">
    <section class="hero-card">
      <div class="hero-left">
        <div class="hero-badge">
          <el-icon :size="22"><VideoCamera /></el-icon>
        </div>
        <div class="hero-copy">
          <p class="eyebrow">HELP COLLECT</p>
          <h2 class="hero-title">帮我取证</h2>
          <p class="hero-desc">上传已找到的侵权视频链接 Excel，按剧名挂到已有工单链接池。</p>
          <div class="hero-steps">
            <span>平台</span>
            <i></i>
            <span>剧名</span>
            <i></i>
            <span>侵权视频链接</span>
          </div>
        </div>
      </div>
    </section>

    <div class="soft-grid">
      <section class="soft-card">
        <div class="card-head">
          <h3>Excel 字段约定</h3>
        </div>
        <ul class="tips">
          <li>必须包含列：<strong>平台</strong>、<strong>剧名</strong>、<strong>侵权视频链接</strong></li>
          <li>一期平台请填写：<strong>微信视频号</strong></li>
        </ul>
        <pre class="tree">平台 | 剧名 | 侵权视频链接
微信视频号 | 流年 | https://...
微信视频号 | 霸总 | https://...</pre>
      </section>

      <section class="soft-card upload-card">
        <div class="card-head">
          <h3>上传链接表</h3>
          <span class="tag">.xlsx</span>
        </div>
        <el-upload
          drag
          :show-file-list="false"
          accept=".xlsx,.xls"
          :http-request="onUpload"
          :disabled="uploading"
        >
          <div class="drop-inner">
            <div class="drop-icon warn"><el-icon :size="28"><UploadFilled /></el-icon></div>
            <strong>{{ uploading ? '正在导入…' : '拖拽或点击上传 Excel' }}</strong>
            <span>将按剧名写入对应工单链接池</span>
          </div>
        </el-upload>

        <div v-if="result" class="result">
          <p class="ok">{{ result.message }}</p>
          <p v-if="result.platforms?.length" class="mute">平台：{{ result.platforms.join('、') }}</p>
          <ul v-if="result.success?.length">
            <li v-for="s in result.success" :key="s.work_order_id">
              <router-link :to="`/company/work-orders/${s.work_order_id}`">{{ s.order_no }}</router-link>
              — {{ s.drama_name }}：导入 {{ s.imported }}，跳过 {{ s.skipped }}
            </li>
          </ul>
          <div v-if="result.failed?.length" class="fail-box">
            <p class="warn">失败 {{ result.failed.length }} 条</p>
            <ul>
              <li v-for="(f, i) in result.failed.slice(0, 20)" :key="i">
                {{ f.drama_name || '（无剧名）' }} — {{ f.reason }}
              </li>
            </ul>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, VideoCamera } from '@element-plus/icons-vue'
import { workOrderApi } from '@/api/index'

const uploading = ref(false)
const result = ref(null)

async function onUpload({ file }) {
  uploading.value = true
  result.value = null
  try {
    const { data } = await workOrderApi.helpCollect(file)
    result.value = data
    ElMessage.success(data.message || '导入完成')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped>
.soft-page { max-width: 1080px; }

.hero-card {
  display: flex;
  align-items: center;
  margin-bottom: 18px;
  padding: 22px 26px;
  border-radius: 22px;
  background:
    radial-gradient(ellipse 50% 80% at 100% 0%, rgba(255, 154, 46, 0.12), transparent 55%),
    linear-gradient(135deg, #FFF8F0 0%, #FFF4E8 55%, #FFEEE0 100%);
  color: #1A1D2E;
  box-shadow: 0 8px 24px rgba(255, 125, 0, 0.08);
  border: 1px solid #FFE2C4;
  overflow: hidden;
  position: relative;
}
.hero-left {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  position: relative;
  z-index: 1;
}
.hero-badge {
  width: 52px;
  height: 52px;
  border-radius: 16px;
  background: linear-gradient(135deg, #FF9A2E, #FF7D00);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 6px 16px rgba(255, 125, 0, 0.22);
}
.eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: #8B91A3;
  margin-bottom: 4px;
}
.hero-title {
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: #1A1D2E;
}
.hero-desc {
  margin-top: 6px;
  font-size: 13px;
  color: #5A6072;
  max-width: 480px;
  line-height: 1.55;
}
.hero-steps {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}
.hero-steps span {
  font-size: 12px;
  font-weight: 600;
  padding: 5px 12px;
  border-radius: 999px;
  background: #fff;
  color: #FF7D00;
  border: 1px solid #FFD6A8;
}
.hero-steps i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #FFD6A8;
}

.soft-grid {
  display: grid;
  grid-template-columns: 1fr 1.1fr;
  gap: 16px;
}

.soft-card {
  background: #fff;
  border: 1px solid #E6E9F2;
  border-radius: 20px;
  padding: 20px 22px 22px;
  box-shadow: 0 8px 28px rgba(40, 50, 90, 0.05);
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.card-head h3 { font-size: 15px; font-weight: 800; color: #1A1D2E; }
.tag {
  font-size: 11px;
  font-weight: 700;
  color: #FF7D00;
  background: #FFF7E8;
  padding: 4px 10px;
  border-radius: 999px;
}

.tips {
  margin: 0 0 14px 18px;
  font-size: 13px;
  color: #5A6072;
  line-height: 1.75;
}
.tree {
  margin: 0;
  padding: 14px 16px;
  background: #F7F8FC;
  border-radius: 14px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: #1A1D2E;
  line-height: 1.65;
}

.upload-card :deep(.el-upload),
.upload-card :deep(.el-upload-dragger) { width: 100%; }
.upload-card :deep(.el-upload-dragger) {
  padding: 40px 16px;
  border-radius: 16px;
  border: 1.5px dashed #FFD6A8;
  background: linear-gradient(180deg, #FFFBF5 0%, #FFF6EB 100%);
}
.drop-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #5A6072;
}
.drop-icon {
  width: 52px;
  height: 52px;
  border-radius: 16px;
  background: linear-gradient(135deg, #5B6CFF, #8B5CF6);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 20px rgba(91, 108, 255, 0.3);
  margin-bottom: 4px;
}
.drop-icon.warn {
  background: linear-gradient(135deg, #FF9A2E, #FF7D00);
  box-shadow: 0 8px 20px rgba(255, 125, 0, 0.28);
}
.drop-inner strong { font-size: 15px; color: #1A1D2E; }
.drop-inner span { font-size: 12px; color: #8B91A3; }

.result {
  margin-top: 16px;
  padding: 14px 16px;
  background: #F7F8FC;
  border-radius: 14px;
  font-size: 13px;
}
.result .ok { color: #00B42A; font-weight: 700; margin-bottom: 6px; }
.result .warn { color: #FF7D00; font-weight: 600; }
.result .mute { color: #8B91A3; margin-bottom: 8px; }
.result ul { margin: 6px 0 0 16px; line-height: 1.7; }
.fail-box { margin-top: 10px; padding-top: 8px; border-top: 1px dashed #E6E9F2; }

@media (max-width: 860px) {
  .soft-grid { grid-template-columns: 1fr; }
}
</style>
