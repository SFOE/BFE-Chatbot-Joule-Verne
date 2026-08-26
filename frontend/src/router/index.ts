import { createRouter, createWebHistory } from 'vue-router'
import ChatView from '@/views/ChatView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: ChatView,
    },
    {
      path: '/release-notes',
      component: () => import('@/views/ReleaseNotesView.vue'),
    },
    {
      path: '/kb-upload',
      component: () => import('@/views/KbUploadView.vue'),
    },
  ],
})

export default router
