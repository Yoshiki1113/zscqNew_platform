import request from '@/api/request'

/** 设备管理 */
export const deviceApi = {
  list() { return request.get('/devices') },
  get(serial) { return request.get(`/devices/${serial}`) },
  check(serial) { return request.get(`/devices/${serial}/check`) },
  checkAscript(serial) { return request.get(`/devices/${serial}/check-ascript`) },
  checkRuntime() { return request.get('/devices/check-runtime') },
  scan() { return request.post('/devices/scan') },
  connect(host, port = 5555) { return request.post('/devices/connect', { host, port }) },
  disconnect(host) { return request.post('/devices/disconnect', { host }) },
}

/** 任务管理 */
export const taskApi = {
  list(params = {}) { return request.get('/tasks', { params }) },
  create(data) { return request.post('/tasks', data) },
  get(id) { return request.get(`/tasks/${id}`) },
  delete(id) { return request.delete(`/tasks/${id}`) },
  start(id) { return request.post(`/tasks/${id}/start`) },
  stop(id) { return request.post(`/tasks/${id}/stop`) },
  retry(id) { return request.post(`/tasks/${id}/retry`) },
  startPhase2(id, data = {}) { return request.post(`/tasks/${id}/start-phase2`, data) },
  listVideoLinks(id) { return request.get(`/tasks/${id}/video-links`) },
  createFromClues(data) { return request.post('/tasks/create-from-clues', data) },
}

/** 侵权线索 */
export const clueApi = {
  list(params = {}) { return request.get('/clues', { params }) },
  withLinks() { return request.get('/clues/with-links') },
  deleteAll() { return request.delete('/clues/all') },
}

/** 链接池 */
export const linkPoolApi = {
  // 批次
  listBatches() { return request.get('/link-pool/batches') },
  createBatch(name) { return request.post('/link-pool/batches', null, { params: { name } }) },
  deleteBatch(batchId) { return request.delete(`/link-pool/batches/${batchId}`) },
  // 批次内链接
  listBatchLinks(batchId) { return request.get(`/link-pool/batches/${batchId}/links`) },
  addLinkToBatch(batchId, linkUrl, keyword) { return request.post(`/link-pool/batches/${batchId}/add-link`, null, { params: { link_url: linkUrl, keyword } }) },
  // 线索导入
  importFromClues(batchName) { return request.post('/link-pool/import-from-clues', null, { params: { batch_name: batchName } }) },
  // 从批次创建任务
  createTask(data) { return request.post('/link-pool/create-task', data) },
}

/** 证据查询 */
export const evidenceApi = {
  list(params = {}) { return request.get('/evidence', { params }) },
  get(id) { return request.get(`/evidence/${id}`) },
  rematchScripts(data = {}) {
    // 可能含补转写，批量讯飞耗时长
    return request.post('/evidence/rematch-scripts', data, { timeout: 1800000 })
  },
  rematchCandidates(data = {}) {
    return request.post('/evidence/rematch-scripts/candidates', data)
  },
  rematchOne(id) {
    return request.post(`/evidence/${id}/rematch-script`, null, { timeout: 600000 })
  },
  batchAsrCandidates(data = {}) {
    return request.post('/evidence/batch-asr/candidates', data)
  },
  batchAsr(data = {}) {
    return request.post('/evidence/batch-asr', data, { timeout: 1800000 })
  },
  asrOne(id) {
    return request.post(`/evidence/${id}/asr`, null, { timeout: 600000 })
  },
  push(ids, pushedBy = '取证员') {
    return request.post('/evidence/push', { ids, pushed_by: pushedBy })
  },
  pushCompany(ids, pushedBy = '取证员') {
    return request.post('/evidence/push-company', { ids, pushed_by: pushedBy })
  },
  pushCompanyAll({ pushedBy = '取证员', taskId, workOrderId } = {}) {
    const body = { pushed_by: pushedBy }
    if (taskId) body.task_id = taskId
    if (workOrderId) body.work_order_id = workOrderId
    return request.post('/evidence/push-company-all', body)
  },
}

/** 工单 */
export const workOrderApi = {
  list(params = {}) { return request.get('/work-orders', { params }) },
  get(id) { return request.get(`/work-orders/${id}`) },
  create(data) { return request.post('/work-orders', data) },
  update(id, data) { return request.patch(`/work-orders/${id}`, data) },
  submit(id) { return request.post(`/work-orders/${id}/submit`) },
  assign(id, assignedTo) { return request.post(`/work-orders/${id}/assign`, { assigned_to: assignedTo }) },
  cleanScript(id) { return request.post(`/work-orders/${id}/clean-script`, {}, { timeout: 600000 }) },
  importLinks(id, links = []) { return request.post(`/work-orders/${id}/import-links`, { links }) },
  linkPool(id) { return request.get(`/work-orders/${id}/link-pool`) },
  uploadAttachment(id, file, fileType = 'other') {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('file_type', fileType)
    return request.post(`/work-orders/${id}/attachments`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  importPackage(file, submitter = '公司用户') {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('submitter', submitter)
    return request.post('/work-orders/import-package', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  helpCollect(excel, submitter = '公司用户') {
    const fd = new FormData()
    fd.append('excel', excel)
    fd.append('submitter', submitter)
    return request.post('/work-orders/help-collect', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  async downloadPackageTemplate() {
    const res = await request.get('/work-orders/package-template', { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = 'work-order-package-sample.zip'
    a.click()
    URL.revokeObjectURL(url)
  },
}

/** 驾驶舱 */
export const dashboardApi = {
  police(params = {}) { return request.get('/dashboard/police', { params }) },
}

/** 审核管理 */
export const reviewApi = {
  pool(params = {}) { return request.get('/reviews/pool', { params }) },
  update(id, data) { return request.put(`/reviews/${id}`, data) },
  batch(data) { return request.post('/reviews/batch', data) },
  peers(evidenceId, status) {
    return request.get('/reviews/peers', { params: { evidence_id: evidenceId, status } })
  },
}

/** 博主聚合 */
export const authorApi = {
  list(params = {}) { return request.get('/authors', { params }) },
  get(channelId) { return request.get(`/authors/${channelId}`) },
}
