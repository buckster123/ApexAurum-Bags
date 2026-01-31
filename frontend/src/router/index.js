import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'landing',
      component: () => import('@/views/LandingView.vue'),
      meta: { requiresGuest: true }
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { requiresGuest: true }
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('@/views/RegisterView.vue'),
      meta: { requiresGuest: true }
    },
    {
      path: '/chat',
      name: 'chat',
      component: () => import('@/views/ChatView.vue'),
      meta: { requiresAuth: false }  // Allow unauthenticated for testing
    },
    {
      path: '/chat/:id',
      name: 'conversation',
      component: () => import('@/views/ChatView.vue'),
      meta: { requiresAuth: true }  // Saved conversations still require auth
    },
    {
      path: '/agents',
      name: 'agents',
      component: () => import('@/views/AgentsView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/village',
      name: 'village',
      component: () => import('@/views/VillageView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/music',
      name: 'music',
      component: () => import('@/views/MusicView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/jam',
      name: 'jam',
      component: () => import('@/views/JamView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/jam/:id',
      name: 'jam-session',
      component: () => import('@/views/JamView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/files',
      name: 'files',
      component: () => import('@/views/FilesView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/files/:folderId',
      name: 'folder',
      component: () => import('@/views/FilesView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/devices',
      name: 'devices',
      component: () => import('@/views/DevicesView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/neural',
      name: 'neural',
      component: () => import('@/views/NeuralView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/village-gui',
      name: 'village-gui',
      component: () => import('@/views/VillageGUIView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/nursery',
      name: 'nursery',
      component: () => import('@/views/NurseryView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/billing',
      name: 'billing',
      component: () => import('@/views/BillingView.vue'),
      meta: { requiresAuth: false }  // Allow viewing pricing without auth
    },
    {
      path: '/council',
      name: 'council',
      component: () => import('@/views/CouncilView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/council/:id',
      name: 'council-session',
      component: () => import('@/views/CouncilView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/billing/success',
      name: 'billing-success',
      component: () => import('@/views/BillingView.vue'),
      meta: { requiresAuth: true }  // Need auth to verify purchase
    },
    {
      path: '/terms',
      name: 'terms',
      component: () => import('@/views/TermsView.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/privacy',
      name: 'privacy',
      component: () => import('@/views/PrivacyView.vue'),
      meta: { requiresAuth: false }
    },
  ]
})

// Navigation guards
router.beforeEach((to, from, next) => {
  const auth = useAuthStore()

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    next({ name: 'login', query: { redirect: to.fullPath } })
  } else if (to.meta.requiresGuest && auth.isAuthenticated) {
    next('/chat')
  } else {
    next()
  }
})

export default router
