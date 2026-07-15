import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/HomePage.vue'),
    meta: { title: '取证工作台', step: 1, icon: 'HomeFilled' },
  },
  {
    path: '/tasks',
    name: 'TaskList',
    component: () => import('@/views/TaskListPage.vue'),
    meta: { title: '任务列表' },
  },
  {
    path: '/link-pool',
    name: 'LinkPool',
    component: () => import('@/views/LinkPoolPage.vue'),
    meta: { title: '链接池' },
  },
  {
    path: '/tasks/:id',
    name: 'TaskRun',
    component: () => import('@/views/TaskRunPage.vue'),
    meta: { title: '执行监控', step: 2, icon: 'Monitor' },
  },
  {
    path: '/evidence',
    name: 'EvidenceList',
    component: () => import('@/views/ResultListPage.vue'),
    meta: { title: '证据列表', step: 3, icon: 'Document' },
  },
  {
    path: '/evidence/:id',
    name: 'EvidenceDetail',
    component: () => import('@/views/EvidenceDetailPage.vue'),
    meta: { title: '证据详情', step: 3, icon: 'Document' },
  },
  {
    path: '/review-pool',
    name: 'ReviewPool',
    component: () => import('@/views/ReviewPoolPage.vue'),
    meta: { title: '复核池', step: 4, icon: 'Checked' },
  },
  {
    path: '/authors',
    name: 'AuthorCluster',
    component: () => import('@/views/AuthorClusterPage.vue'),
    meta: { title: '博主聚合', step: 5, icon: 'UserFilled' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/HomePage.vue'),
    meta: { title: '页面不存在' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
