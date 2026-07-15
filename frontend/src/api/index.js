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
}

/** 审核管理 */
export const reviewApi = {
  pool(params = {}) { return request.get('/reviews/pool', { params }) },
  update(id, data) { return request.put(`/reviews/${id}`, data) },
  batch(data) { return request.post('/reviews/batch', data) },
}

/** 博主聚合 */
export const authorApi = {
  list(params = {}) { return request.get('/authors', { params }) },
  get(channelId) { return request.get(`/authors/${channelId}`) },
}
