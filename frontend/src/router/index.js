import { createRouter, createWebHistory } from 'vue-router'
import { isMerchant } from '../api'

const routes = [
  { path: '/', name: 'chat', component: () => import('../views/ChatView.vue') },
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
  { path: '/products', name: 'products', component: () => import('../views/ProductsView.vue') },
  { path: '/products/:id', name: 'product-detail', component: () => import('../views/ProductDetailView.vue') },
  { path: '/favorites', name: 'favorites', component: () => import('../views/FavoritesView.vue') },
  { path: '/me', name: 'me', component: () => import('../views/MyCartView.vue') },
  { path: '/share/:key', name: 'share', component: () => import('../views/ShareView.vue') },
  { path: '/orders/:orderNo/track', name: 'order-track', component: () => import('../views/OrderTrackView.vue') },
  {
    path: '/merchant',
    name: 'merchant',
    component: () => import('../views/MerchantView.vue'),
    meta: { requiresMerchant: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 商家页面守卫：非商家身份跳登录
router.beforeEach((to) => {
  if (to.meta.requiresMerchant && !isMerchant()) {
    return { path: '/login' }
  }
  return true
})

export default router
