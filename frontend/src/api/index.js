import axios from 'axios'

// 开发期走 vite 代理，生产期可改 baseURL
const http = axios.create({
  baseURL: '/api',
  timeout: 40000,
})

// ---- token / 用户状态（localStorage） ----
export function getToken() {
  return localStorage.getItem('token') || ''
}
export function setToken(t) {
  if (t) localStorage.setItem('token', t)
  else localStorage.removeItem('token')
}
export function getUser() {
  try {
    return JSON.parse(localStorage.getItem('user') || 'null')
  } catch (e) {
    return null
  }
}
export function setUser(u) {
  if (u) localStorage.setItem('user', JSON.stringify(u))
  else localStorage.removeItem('user')
}
export function isLoggedIn() {
  return !!getToken()
}
export function isMerchant() {
  return getUser()?.role === 'merchant'
}
export function clearAuth() {
  setToken('')
  setUser(null)
}

// axios 拦截器：统一带 token
http.interceptors.request.use((config) => {
  const t = getToken()
  if (t) config.headers.Authorization = `Bearer ${t}`
  return config
})

// 当前会话 ID（localStorage 持久）。新建/切换历史会话时用 setSessionId 更新
export function getSessionId() {
  let id = localStorage.getItem('session_id')
  if (!id) {
    id = 's_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8)
    localStorage.setItem('session_id', id)
  }
  return id
}
export function setSessionId(id) {
  localStorage.setItem('session_id', id)
}

// ---- 认证 ----
export function register(payload) { return http.post('/auth/register', payload) }
export function login(payload) { return http.post('/auth/login', payload) }
export function fetchMe() { return http.get('/auth/me') }

// ---- 对话 / 历史 ----
export function sendChat(message, sessionId) {
  return http.post('/chat', { message, session_id: sessionId })
}
export function getSessions() { return http.get('/sessions') }
export function getSessionMessages(sessionKey) {
  return http.get(`/sessions/${sessionKey}/messages`)
}
export function renameSession(sessionKey, title) {
  return http.patch(`/sessions/${sessionKey}/title`, { title })
}
export function pinSession(sessionKey, pinned) {
  return http.patch(`/sessions/${sessionKey}/pin`, { pinned })
}
export function deleteSession(sessionKey) { return http.delete(`/sessions/${sessionKey}`) }

// ---- 商品 ----
export function listProducts() { return http.get('/products') }
export function searchProducts(query, category) {
  return http.post('/products/search', { query, category, session_id: getSessionId() })
}
export function getProductDetail(id) { return http.get(`/products/${id}`) }
export function getSimilar(id) { return http.get(`/products/${id}/similar`) }

// ---- 商家端（需 role=merchant） ----
export function merchantListProducts(params) {
  return http.get('/merchant/products', { params })
}
export function merchantGetProduct(id) { return http.get(`/merchant/products/${id}`) }
export function merchantCreateProduct(payload) { return http.post('/merchant/products', payload) }
export function merchantUpdateProduct(id, payload) { return http.put(`/merchant/products/${id}`, payload) }
export function merchantDeleteProduct(id) { return http.delete(`/merchant/products/${id}`) }
export function merchantSetOnSale(id, isOnSale) {
  return http.post(`/merchant/products/${id}/on-sale`, { is_on_sale: isOnSale })
}
export function merchantUploadImage(id, file) {
  const form = new FormData()
  form.append('file', file)
  return http.post(`/merchant/products/${id}/image`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
export function merchantRemoveImage(id) { return http.delete(`/merchant/products/${id}/image`) }
export function merchantDashboard(days = 30) {
  return http.get('/merchant/dashboard', { params: { days } })
}
export function merchantListOrders(status = '') {
  return http.get('/merchant/orders', { params: { status } })
}
export function merchantPendingCount() { return http.get('/merchant/orders/pending-count') }
export function merchantOrderWarehouses(orderNo) {
  return http.get(`/merchant/orders/${orderNo}/warehouses`)
}
export function merchantAcceptOrder(orderNo, warehouseId) {
  return http.post(`/merchant/orders/${orderNo}/accept`, { warehouse_id: warehouseId ?? null })
}
export function merchantRejectOrder(orderNo) { return http.post(`/merchant/orders/${orderNo}/reject`) }
export function merchantListAftersale() { return http.get('/merchant/aftersale') }
export function merchantHandleAftersale(orderNo, approve, reply = '') {
  return http.post(`/merchant/orders/${orderNo}/aftersale`, { approve, reply })
}
export function merchantAssistant(message) {
  return http.post('/merchant/assistant', { message })
}

// ---- 购物车 / 订单 / 画像（需登录） ----
export function addToCart(productId) {
  return http.post('/cart/add', { product_id: productId })
}
export function getCart() { return http.get('/cart') }
export function removeCartItem(itemId) { return http.delete(`/cart/${itemId}`) }
export function createOrder(addressId) {
  return http.post('/order', { address_id: addressId ?? null, session_id: getSessionId() })
}
export function getOrders() { return http.get('/order') }
export function getOrder(orderNo) { return http.get(`/order/${orderNo}`) }
export function saveOrderRoute(orderNo, route) {
  return http.post(`/order/${orderNo}/route`, { route })
}
export function applyAftersale(orderNo, type, reason) {
  return http.post(`/order/${orderNo}/aftersale`, { type, reason })
}
export function getProfile() { return http.get('/profile') }

// ---- 收货地址 ----
export function listAddresses() { return http.get('/addresses') }
export function createAddress(payload) { return http.post('/addresses', payload) }
export function updateAddress(id, payload) { return http.put(`/addresses/${id}`, payload) }
export function setDefaultAddress(id) { return http.post(`/addresses/${id}/default`) }
export function deleteAddress(id) { return http.delete(`/addresses/${id}`) }

// ---- 收藏（需登录） ----
export function addFavorite(productId) { return http.post('/favorites/add', { product_id: productId }) }
export function getFavorites() { return http.get('/favorites') }
export function removeFavorite(productId) { return http.delete(`/favorites/${productId}`) }
