import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('../views/HomePage.vue'),
    },
    {
      path: '/purl-resolver',
      name: 'purl-resolver',
      component: () => import('../views/PurlResolver.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/Settings.vue'),
    },
    {
      path: '/images-list-converter',
      name: 'images-list-converter',
      component: () => import('../views/ImagesListConverter.vue'),
    },
    {
      path: '/sbom-updater',
      name: 'sbom-updater',
      component: () => import('../views/SbomUpdater.vue'),
    },
    {
      path: '/db-admin',
      name: 'db-admin',
      component: () => import('../views/DatabaseAdmin.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('../views/NotFound.vue'),
    },
  ],
})

export default router
