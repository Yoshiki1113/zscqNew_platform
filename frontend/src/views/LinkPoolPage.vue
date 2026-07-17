<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">链接池</h1>
        <p class="page-subtitle">按批次管理链接，选择批次创建取证任务</p>
      </div>
      <el-space>
        <el-button @click="showManualBatchDialog = true" :icon="Plus">手动创建批次</el-button>
        <el-button type="warning" @click="showImportDialog = true" v-if="unimportedClueCount > 0">
          从线索导入（{{ unimportedClueCount }} 条）
        </el-button>
      </el-space>
    </div>

    <el-alert
      v-if="workOrderId"
      type="warning"
      :closable="false"
      :title="`当前为工单 #${workOrderId} 取证：请选择对应批次后创建二阶段任务`"
      style="margin-bottom:16px;"
    />

    <!-- 批次列表 -->
    <div class="card" v-loading="loading">
      <div class="card-body no-pad" v-if="batches.length">
        <el-table :data="batches" stripe @selection-change="onSelectionChange" ref="tableRef">
          <el-table-column type="selection" width="45" />
          <el-table-column label="批次名称" min-width="220">
            <template #default="{row}">
              <span style="font-weight:600;">{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="来源" width="110">
            <template #default="{row}">
              <el-tag v-if="row.source === 'collected'" type="primary" size="small">自动采集</el-tag>
              <el-tag v-else-if="row.source === 'imported'" type="warning" size="small">Excel导入</el-tag>
              <el-tag v-else-if="row.source === 'work_order'" type="danger" size="small">工单导入</el-tag>
              <el-tag v-else type="success" size="small">手动添加</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="链接数（待处理/总数）" width="160" align="center">
            <template #default="{row}">
              <span :style="{color: row.pending_count > 0 ? 'var(--primary)' : 'var(--muted)'}">
                {{ row.pending_count }} / {{ row.total_count }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="170">
            <template #default="{row}">{{ formatDateTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{row}">
              <el-button size="small" text type="primary" @click="viewLinks(row)">查看链接</el-button>
              <el-button size="small" text type="danger" @click="deleteBatch(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div v-if="!loading && !batches.length" class="empty-state" style="padding:40px;">
        <div class="empty-icon"><el-icon><FolderOpened /></el-icon></div>
        <div class="empty-text">暂无链接批次</div>
        <div class="empty-text" style="font-size:12px;">执行阶段一任务、导入线索Excel、或手动创建批次来填充链接池</div>
      </div>
    </div>

    <!-- 底部选择栏 -->
    <div class="bottom-bar" v-if="selectedBatches.length > 0">
      <div class="bottom-bar-inner">
        <span>已选择 <b style="color:var(--primary);">{{ selectedBatches.length }}</b> 个批次（共 <b>{{ selectedTotalLinks }}</b> 条链接）</span>
        <el-button type="primary" @click="openConfigDialog">
          配置取证参数并启动
        </el-button>
      </div>
    </div>

    <!-- 链接明细弹窗 -->
    <el-dialog v-model="showLinksDialog" :title="`批次：${viewingBatch?.name}`" width="700px">
      <el-table :data="batchLinks" stripe max-height="400" v-loading="linksLoading">
        <el-table-column label="#" width="50">
          <template #default="{row}">{{ row.sort_order }}</template>
        </el-table-column>
        <el-table-column label="链接" min-width="300" show-overflow-tooltip>
          <template #default="{row}">
            <span style="font-size:12px;font-family:monospace;">{{ row.link_url }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关键词" width="130" show-overflow-tooltip>
          <template #default="{row}">{{ row.keyword || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{row}">
            <el-tag v-if="row.collected" size="small" type="success">已采集</el-tag>
            <el-tag v-else size="small" type="primary">待处理</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 手动创建批次 -->
    <el-dialog v-model="showManualBatchDialog" title="手动创建批次" width="450px">
      <el-form label-position="top">
        <el-form-item label="批次名称">
          <el-input v-model="manualBatchName" placeholder="如：手动添加_2026年7月" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showManualBatchDialog = false">取消</el-button>
        <el-button type="primary" @click="createManualBatch" :loading="creatingBatch">创建</el-button>
      </template>
    </el-dialog>

    <!-- 线索导入 -->
    <el-dialog v-model="showImportDialog" title="从线索导入批次" width="450px">
      <el-form label-position="top">
        <el-form-item label="批次名称（必填）">
          <el-input v-model="importBatchName" placeholder="如：侵权线索_2026年7月" />
        </el-form-item>
      </el-form>
      <div style="padding:12px;background:var(--bg-muted);border-radius:8px;">
        <span style="font-size:13px;color:var(--muted);">
          将从 {{ unimportedClueCount }} 条侵权线索中导入包含视频链接的记录
        </span>
      </div>
      <template #footer>
        <el-button @click="showImportDialog = false">取消</el-button>
        <el-button type="primary" @click="doImportFromClues" :loading="importing">
          导入
        </el-button>
      </template>
    </el-dialog>

    <!-- 取证参数配置 -->
    <el-dialog v-model="showConfigDialog" title="配置取证参数" width="450px">
      <el-form label-position="top">
        <el-form-item label="执行设备">
          <el-select v-model="configForm.deviceId" style="width:100%" placeholder="请选择设备">
            <el-option v-for="d in devices" :key="d.id" :label="`${d.model || d.id} (${d.ip_address || '无IP'})`" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="任务名称" required>
          <el-input v-model="configForm.keyword" placeholder="请输入任务名称" />
        </el-form-item>
        <el-form-item label="每条视频停留时长（分钟）">
          <el-input-number v-model="configForm.holdMinutes" :min="0.5" :max="60" :step="0.5" :precision="1" style="width:100%" />
        </el-form-item>
        <el-form-item label="ASR 台词比对">
          <el-switch v-model="configForm.enableAsr" active-text="启用" inactive-text="关闭" />
        </el-form-item>
      </el-form>
      <div style="padding:12px;background:var(--bg-muted);border-radius:8px;margin-top:8px;">
        <span style="font-size:13px;color:var(--muted);">
          将从 {{ selectedBatches.length }} 个批次中导入 <b>{{ selectedTotalLinks }}</b> 条链接并直接启动阶段二
        </span>
      </div>
      <template #footer>
        <el-button @click="showConfigDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmCreateAndStart" :loading="creating">
          启动阶段二
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, FolderOpened } from '@element-plus/icons-vue'
import { linkPoolApi, taskApi, deviceApi } from '@/api/index'
import { formatDateTime } from '@/utils/time'
import { useAppStore } from '@/stores/app'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const workOrderId = ref(parseInt(route.query.work_order_id) || 0)

const loading = ref(false)
const batches = ref([])
const unimportedClueCount = ref(0)
const tableRef = ref(null)

// 选择
const selectedBatches = ref([])
const selectedTotalLinks = computed(() =>
  selectedBatches.value.reduce((s, b) => s + (b.pending_count || 0), 0)
)

// 链接明细
const showLinksDialog = ref(false)
const viewingBatch = ref(null)
const batchLinks = ref([])
const linksLoading = ref(false)

// 手动批次
const showManualBatchDialog = ref(false)
const manualBatchName = ref('')
const creatingBatch = ref(false)

// 线索导入
const showImportDialog = ref(false)
const importBatchName = ref('')
const importing = ref(false)

// 取证配置
const showConfigDialog = ref(false)
const creating = ref(false)
const devices = ref([])
const configForm = reactive({
  deviceId: '',
  keyword: '',
  holdMinutes: 4,
  enableAsr: true,
})

function openConfigDialog() {
  configForm.keyword = selectedBatches.value[0]?.name || ''
  showConfigDialog.value = true
}

function onSelectionChange(selection) {
  selectedBatches.value = selection
}

async function deleteBatch(row) {
  try {
    await ElMessageBox.confirm(
      `确定要删除批次「${row.name}」吗？未采集的链接将被一并删除，已采集的链接不受影响。`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return  // 用户取消
  }
  try {
    const { data } = await linkPoolApi.deleteBatch(row.id)
    ElMessage.success(data?.message || '已删除')
    await loadBatches()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

async function loadBatches() {
  loading.value = true
  try {
    const { data } = await linkPoolApi.listBatches()
    batches.value = data?.batches || []
    unimportedClueCount.value = data?.unimported_clue_count || 0
    await nextTick()
    const batchId = parseInt(route.query.batch_id) || 0
    if (batchId && tableRef.value) {
      const batch = batches.value.find(b => b.id === batchId)
      if (batch) {
        tableRef.value.toggleRowSelection(batch, true)
        if (route.query.keyword) configForm.keyword = route.query.keyword
      }
    }
  } catch {
    batches.value = []
  } finally {
    loading.value = false
  }
}

async function viewLinks(batch) {
  viewingBatch.value = batch
  showLinksDialog.value = true
  linksLoading.value = true
  try {
    const { data } = await linkPoolApi.listBatchLinks(batch.id)
    batchLinks.value = data?.links || []
  } catch {
    batchLinks.value = []
  } finally {
    linksLoading.value = false
  }
}

async function createManualBatch() {
  creatingBatch.value = true
  try {
    await linkPoolApi.createBatch(manualBatchName.value)
    ElMessage.success('批次已创建')
    showManualBatchDialog.value = false
    manualBatchName.value = ''
    await loadBatches()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '创建失败')
  } finally {
    creatingBatch.value = false
  }
}

async function doImportFromClues() {
  if (!importBatchName.value.trim()) {
    ElMessage.warning('请为导入批次命名')
    return
  }
  importing.value = true
  try {
    const { data } = await linkPoolApi.importFromClues(importBatchName.value.trim())
    ElMessage.success(data.message || `已导入`)
    showImportDialog.value = false
    importBatchName.value = ''
    await loadBatches()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  } finally {
    importing.value = false
  }
}

async function confirmCreateAndStart() {
  if (!configForm.keyword.trim()) {
    ElMessage.warning('请输入任务名称')
    return
  }
  creating.value = true
  try {
    const batchIds = selectedBatches.value.map(b => b.id)
    const { data } = await linkPoolApi.createTask({
      batch_ids: batchIds,
      keyword: configForm.keyword,
      device_id: configForm.deviceId,
      hold_seconds: Math.round(configForm.holdMinutes * 60),
      capture_method: 'scrcpy',
      enable_asr: configForm.enableAsr,
      work_order_id: workOrderId.value || undefined,
    })
    showConfigDialog.value = false
    if (data.id) {
      appStore.setLastTaskId(data.id)
      try {
        await taskApi.startPhase2(data.id, {
          hold_seconds: Math.round(configForm.holdMinutes * 60),
          capture_method: 'scrcpy',
          enable_asr: configForm.enableAsr,
        })
        ElMessage.success(`已启动阶段二，${data.batch_count || 0} 个批次，${data.imported_links} 条链接`)
      } catch (e2) {
        ElMessage.warning('任务已创建，但自动启动失败，请手动启动')
      }
      router.push(`/collector/tasks/${data.id}`)
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '创建失败')
  } finally {
    creating.value = false
  }
}

async function loadDevices() {
  try {
    const { data } = await deviceApi.list()
    devices.value = data || []
    if (!configForm.deviceId && devices.value.length > 0) {
      configForm.deviceId = devices.value[0].id
    }
  } catch { devices.value = [] }
}

onMounted(() => {
  loadBatches()
  loadDevices()
})
</script>

<style scoped>
.bottom-bar {
  position: sticky;
  bottom: 16px;
  z-index: 10;
}
.bottom-bar-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 4px 20px rgba(0,0,0,0.12);
}
</style>
