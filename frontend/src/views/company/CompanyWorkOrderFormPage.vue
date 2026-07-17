<template>
  <div class="soft-page">
    <div v-if="isEditRoute" class="soft-card tip-card">
      <h2>编辑已收敛</h2>
      <p>一期请通过「新建工单」上传工单包提交材料。如需补充侵权链接，请前往「帮我取证」。</p>
      <div class="btn-row">
        <el-button type="primary" @click="$router.push('/company/work-orders/new')">去新建工单</el-button>
        <el-button @click="$router.push('/company/help-collect')">去帮我取证</el-button>
      </div>
    </div>

    <template v-else>
      <section class="hero-card">
        <div class="hero-left">
          <div class="hero-badge">
            <el-icon :size="22"><FolderOpened /></el-icon>
          </div>
          <div class="hero-copy">
            <p class="eyebrow">WORK ORDER</p>
            <h2 class="hero-title">上传工单包</h2>
            <p class="hero-desc">按规范打包 zip，系统将为每部剧自动创建已提交工单并入库台词。</p>
            <div class="hero-steps">
              <span>1. Excel 剧名</span>
              <i></i>
              <span>2. Docx 台词</span>
              <i></i>
              <span>3. 打包上传</span>
            </div>
          </div>
        </div>
        <div class="hero-right">
          <el-button type="primary" round size="large" @click="downloadTemplate">
            <el-icon style="margin-right:6px"><Download /></el-icon>
            下载样板 zip
          </el-button>
          <p class="hero-hint">内含示例 Excel + 台词 docx</p>
        </div>
      </section>

      <div class="soft-grid">
        <section class="soft-card">
          <div class="card-head">
            <h3>打包说明</h3>
          </div>
          <ol class="tips">
            <li>新建一个文件夹（例如「工单包」）。</li>
            <li>放入 Excel：每行一部<strong>剧名</strong>（列名建议为「剧名」）。</li>
            <li>同目录放置台词 <strong>docx</strong>，一部剧一个文件，文件名 = 剧名。</li>
            <li>打包为 zip 后在右侧上传。</li>
          </ol>
          <pre class="tree">工单包/
  剧名列表.xlsx
  流年.docx
  霸总.docx</pre>
        </section>

        <section class="soft-card upload-card">
          <div class="card-head">
            <h3>上传区域</h3>
            <span class="tag">.zip</span>
          </div>
          <el-upload
            drag
            :show-file-list="false"
            accept=".zip"
            :http-request="onUpload"
            :disabled="uploading"
          >
            <div class="drop-inner">
              <div class="drop-icon"><el-icon :size="28"><UploadFilled /></el-icon></div>
              <strong>{{ uploading ? '正在解析并创建工单…' : '拖拽或点击上传 zip' }}</strong>
              <span>Excel 剧名 + 同目录 docx 台词</span>
            </div>
          </el-upload>

          <div v-if="result" class="result">
            <p class="ok">{{ result.message }}</p>
            <ul v-if="result.created?.length">
              <li v-for="c in result.created" :key="c.id">
                <router-link :to="`/company/work-orders/${c.id}`">{{ c.order_no }}</router-link>
                — {{ c.drama_name }}（台词 {{ c.chars }} 字）
              </li>
            </ul>
            <p v-if="result.missing_script?.length" class="warn">
              缺台词未建单：{{ result.missing_script.join('、') }}
            </p>
            <div class="btn-row" style="margin-top:12px;">
              <el-button type="primary" round @click="$router.push('/company')">查看工单列表</el-button>
              <el-button round @click="$router.push('/company/help-collect')">继续：帮我取证</el-button>
            </div>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { UploadFilled, FolderOpened, Download } from '@element-plus/icons-vue'
import { workOrderApi } from '@/api/index'

const route = useRoute()
const isEditRoute = computed(() => route.name === 'CompanyWorkOrderEdit')
const uploading = ref(false)
const result = ref(null)

async function downloadTemplate() {
  try {
    await workOrderApi.downloadPackageTemplate()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '样板下载失败')
  }
}

async function onUpload({ file }) {
  uploading.value = true
  result.value = null
  try {
    const { data } = await workOrderApi.importPackage(file)
    result.value = data
    ElMessage.success(data.message || '导入成功')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '上传失败')
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
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 18px;
  padding: 22px 26px;
  border-radius: 22px;
  background:
    radial-gradient(ellipse 55% 90% at 0% 40%, rgba(139, 92, 246, 0.1), transparent 60%),
    linear-gradient(135deg, #EEF1FF 0%, #F0EDFF 50%, #F5F0FF 100%);
  color: #1A1D2E;
  box-shadow: 0 8px 24px rgba(91, 108, 255, 0.08);
  border: 1px solid #E4E8FF;
  overflow: hidden;
  position: relative;
}
.hero-card::after {
  content: '';
  position: absolute;
  right: -40px;
  top: -40px;
  width: 160px;
  height: 160px;
  border-radius: 50%;
  background: rgba(91, 108, 255, 0.06);
  pointer-events: none;
}
.hero-left {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  position: relative;
  z-index: 1;
  min-width: 0;
}
.hero-badge {
  width: 52px;
  height: 52px;
  border-radius: 16px;
  background: linear-gradient(135deg, #5B6CFF, #8B5CF6);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 6px 16px rgba(91, 108, 255, 0.25);
}
.hero-copy { min-width: 0; }
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
  line-height: 1.25;
  color: #1A1D2E;
}
.hero-desc {
  margin-top: 6px;
  font-size: 13px;
  color: #5A6072;
  max-width: 460px;
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
  color: #5B6CFF;
  border: 1px solid #DCE1FF;
}
.hero-steps i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #C5CBFF;
}
.hero-right {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  flex-shrink: 0;
}
.hero-right :deep(.el-button--primary) {
  --el-button-bg-color: #5B6CFF;
  --el-button-border-color: #5B6CFF;
  --el-button-text-color: #fff;
  --el-button-hover-bg-color: #7B88FF;
  --el-button-hover-border-color: #7B88FF;
  --el-button-hover-text-color: #fff;
  font-weight: 700;
  box-shadow: 0 6px 16px rgba(91, 108, 255, 0.22);
}
.hero-hint {
  font-size: 11px;
  color: #8B91A3;
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
.card-head h3 {
  font-size: 15px;
  font-weight: 800;
  color: #1A1D2E;
}
.tag {
  font-size: 11px;
  font-weight: 700;
  color: #5B6CFF;
  background: #EEF0FF;
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
  border: 1.5px dashed #D4D9FF;
  background: linear-gradient(180deg, #F8F9FF 0%, #F3F5FF 100%);
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
.drop-inner strong { font-size: 15px; color: #1A1D2E; }
.drop-inner span { font-size: 12px; color: #8B91A3; }

.result {
  margin-top: 16px;
  padding: 14px 16px;
  background: #F7F8FC;
  border-radius: 14px;
  font-size: 13px;
}
.result .ok { color: #00B42A; font-weight: 700; margin-bottom: 8px; }
.result .warn { color: #FF7D00; margin-top: 6px; }
.result ul { margin: 8px 0 0 16px; line-height: 1.7; }

.btn-row { display: flex; gap: 10px; flex-wrap: wrap; }
.tip-card h2 { font-size: 18px; font-weight: 800; margin-bottom: 8px; }
.tip-card p { font-size: 13px; color: #5A6072; margin-bottom: 14px; line-height: 1.6; }

@media (max-width: 860px) {
  .soft-grid { grid-template-columns: 1fr; }
  .hero-card { flex-direction: column; align-items: stretch; }
  .hero-right { align-items: stretch; }
  .hero-title { font-size: 22px; }
}
</style>
