import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore, ROLES } from '@/stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginPage.vue'),
    meta: { public: true, title: '登录' },
  },
  {
    path: '/',
    name: 'Root',
    redirect: () => {
      const auth = useAuthStore()
      return auth.isLoggedIn ? ROLES[auth.role].home : '/login'
    },
  },

  // 公安端
  {
    path: '/police',
    component: () => import('@/layouts/PoliceLayout.vue'),
    meta: { role: 'police' },
    children: [
      { path: '', name: 'PoliceDashboard', component: () => import('@/views/police/PoliceDashboard.vue'), meta: { title: '驾驶舱' } },
      { path: 'clues', name: 'PoliceClues', component: () => import('@/views/police/PoliceCluesPage.vue'), meta: { title: '线索列表' } },
      {
        path: 'evidence/:id',
        name: 'PoliceEvidenceDetail',
        component: () => import('@/views/EvidenceDetailPage.vue'),
        meta: { title: '证据详情', readonly: true },
      },
    ],
  },

  // 公司端
  {
    path: '/company',
    component: () => import('@/layouts/CompanyLayout.vue'),
    meta: { role: 'company' },
    children: [
      { path: '', name: 'CompanyWorkOrders', component: () => import('@/views/company/CompanyWorkOrdersPage.vue'), meta: { title: '工单列表' } },
      { path: 'review-pool', name: 'CompanyReviewPool', component: () => import('@/views/company/CompanyReviewPoolPage.vue'), meta: { title: '核查池' } },
      { path: 'work-orders/new', name: 'CompanyWorkOrderNew', component: () => import('@/views/company/CompanyWorkOrderFormPage.vue'), meta: { title: '新建工单' } },
      { path: 'help-collect', name: 'CompanyHelpCollect', component: () => import('@/views/company/CompanyHelpCollectPage.vue'), meta: { title: '帮我取证' } },
      { path: 'work-orders/:id/edit', name: 'CompanyWorkOrderEdit', component: () => import('@/views/company/CompanyWorkOrderFormPage.vue'), meta: { title: '编辑工单' } },
      { path: 'work-orders/:id', name: 'CompanyWorkOrderDetail', component: () => import('@/views/company/CompanyWorkOrderDetailPage.vue'), meta: { title: '工单详情' } },
      {
        path: 'evidence/:id',
        name: 'CompanyEvidenceDetail',
        component: () => import('@/views/EvidenceDetailPage.vue'),
        meta: { title: '证据复核', companyReview: true },
      },
    ],
  },

  // 取证端
  {
    path: '/collector',
    component: () => import('@/layouts/CollectorLayout.vue'),
    meta: { role: 'collector' },
    children: [
      { path: '', name: 'CollectorQueue', component: () => import('@/views/collector/CollectorQueuePage.vue'), meta: { title: '调度台' } },
      { path: 'home', name: 'CollectorHome', component: () => import('@/views/HomePage.vue'), meta: { title: '新建任务' } },
      { path: 'tasks', name: 'TaskList', component: () => import('@/views/TaskListPage.vue'), meta: { title: '任务列表' } },
      { path: 'link-pool', name: 'LinkPool', component: () => import('@/views/LinkPoolPage.vue'), meta: { title: '链接池' } },
      { path: 'tasks/:id', name: 'TaskRun', component: () => import('@/views/TaskRunPage.vue'), meta: { title: '执行监控' } },
      { path: 'evidence', name: 'EvidenceList', component: () => import('@/views/ResultListPage.vue'), meta: { title: '证据列表' } },
      {
        path: 'evidence/:id',
        name: 'EvidenceDetail',
        component: () => import('@/views/EvidenceDetailPage.vue'),
        meta: { title: '证据详情' },
      },
      { path: 'review-pool', name: 'ReviewPool', component: () => import('@/views/ReviewPoolPage.vue'), meta: { title: '复核池' } },
      { path: 'authors', name: 'AuthorCluster', component: () => import('@/views/AuthorClusterPage.vue'), meta: { title: '博主聚合' } },
      { path: 'devices', name: 'Devices', component: () => import('@/views/collector/DevicesPage.vue'), meta: { title: '设备管理' } },
    ],
  },

  // 占位端
  {
    path: '/copyright',
    component: () => import('@/views/PlaceholderPage.vue'),
    meta: { role: 'copyright', placeholderTitle: '版权端', placeholderDesc: '权属库、授权链、侵权对比报告等功能规划中。' },
  },
  {
    path: '/culture',
    component: () => import('@/views/PlaceholderPage.vue'),
    meta: { role: 'culture', placeholderTitle: '文旅端', placeholderDesc: '属地传播热力、重点剧目监测等功能规划中。' },
  },

  // 旧路径重定向
  { path: '/tasks', redirect: '/collector/tasks' },
  { path: '/tasks/:id', redirect: to => `/collector/tasks/${to.params.id}` },
  { path: '/link-pool', redirect: '/collector/link-pool' },
  { path: '/evidence', redirect: '/collector/evidence' },
  { path: '/evidence/:id', redirect: to => `/collector/evidence/${to.params.id}` },
  { path: '/review-pool', redirect: '/collector/review-pool' },
  { path: '/authors', redirect: '/collector/authors' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const auth = useAuthStore()

  if (to.meta.public) {
    if (to.path === '/login' && auth.isLoggedIn) {
      return next(ROLES[auth.role].home)
    }
    return next()
  }

  if (!auth.isLoggedIn) {
    return next('/login')
  }

  const requiredRole = to.matched.find(r => r.meta.role)?.meta.role
  if (requiredRole && requiredRole !== auth.role) {
    return next(ROLES[auth.role].home)
  }

  next()
})

export default router
