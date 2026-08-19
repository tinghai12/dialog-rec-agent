<template>
  <div class="app-nav">
    <div class="nav-inner">
      <router-link to="/" class="brand">
        <span class="brand-logo">语</span>
        <span class="brand-name">自然语言电商</span>
      </router-link>
      <div class="nav-links">
        <router-link to="/" class="nav-link">对话推荐</router-link>
        <router-link to="/products" class="nav-link">逛商品</router-link>
        <!-- 商家只看商家中心，买家看购物/收藏 -->
        <template v-if="merchant">
          <router-link to="/merchant" class="nav-link">商家中心</router-link>
        </template>
        <template v-else>
          <router-link to="/me" class="nav-link">
            我的导购
            <span v-if="cartCount > 0" class="badge">{{ cartCount }}</span>
          </router-link>

          <!-- 收藏：悬停展开预览浮层 -->
          <div class="fav-wrap" @mouseenter="openFav" @mouseleave="closeFav">
            <router-link to="/favorites" class="nav-link">
              收藏
              <span v-if="favorites.length" class="badge">{{ favorites.length }}</span>
            </router-link>

            <transition name="fav-fade">
              <div v-show="favOpen" class="fav-panel">
                <div class="fav-head">
                  <span>我的收藏</span>
                  <span class="fav-count">{{ favorites.length }} 件</span>
                </div>

                <div v-if="!isLoggedIn()" class="fav-empty">登录后查看收藏</div>
                <div v-else-if="favLoading" class="fav-empty">加载中…</div>
                <div v-else-if="!favorites.length" class="fav-empty">还没有收藏，去逛逛吧</div>

                <div v-else class="fav-list">
                  <div v-for="f in favorites" :key="f.id" class="fav-row" @click="goProduct(f.id)">
                    <el-checkbox
                      :model-value="selected.includes(f.id)"
                      class="fav-check"
                      @click.stop
                      @change="(v) => toggleSelect(f.id, v)"
                    />
                    <ProductThumb :product="f" :size="56" />
                    <div class="fav-main">
                      <div class="fav-title">
                        <span v-if="f.title_prefix" class="fav-prefix">{{ f.title_prefix }}</span>{{ f.title }}
                      </div>
                      <div class="fav-promo">
                        <span v-if="f.promo_banner" class="fp-tag">{{ f.promo_banner }}</span>
                        <span v-if="f.saved_amount > 0" class="fp-tag">已省{{ Math.round(f.saved_amount) }}元</span>
                        <span v-for="t in (f.service_tags || []).slice(0, 2)" :key="t" class="fp-tag">{{ t }}</span>
                      </div>
                    </div>
                    <div class="fav-spec">{{ specOf(f) }}</div>
                    <div class="fav-price">¥{{ Number(f.final_price ?? f.price).toFixed(2) }}</div>
                    <div class="fav-ops" @click.stop>
                      <a @click="moveToCart(f)">移入购物车</a>
                      <a class="danger" @click="removeFav(f)">删除</a>
                    </div>
                  </div>
                </div>

                <div class="fav-foot">
                  <span class="fav-total">
                    已选 {{ selected.length }} 件
                    <b v-if="selected.length">合计 ¥{{ selectedTotal.toFixed(2) }}</b>
                  </span>
                  <el-button type="primary" size="small" :disabled="!selected.length"
                             :loading="paying" @click="goCheckout">付款</el-button>
                </div>
              </div>
            </transition>
          </div>
        </template>

        <template v-if="isLoggedIn()">
          <span class="nav-user">
            <span class="user-avatar" :class="{ merchant }">{{ (user?.nickname || user?.username || '用')[0] }}</span>
            {{ user?.nickname || user?.username }}
            <span v-if="merchant" class="role-tag">商家</span>
          </span>
          <el-button size="small" text @click="logout">退出</el-button>
        </template>
        <router-link v-else to="/login" class="nav-link login-btn">登录 / 注册</router-link>
      </div>
    </div>
    <router-view />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ProductThumb from './components/ProductThumb.vue'
import {
  getCart, isLoggedIn, getUser, clearAuth,
  getFavorites, removeFavorite, addToCart,
} from './api'

const cartCount = ref(0)
const user = ref(getUser())
const route = useRoute()
const router = useRouter()

const merchant = computed(() => user.value?.role === 'merchant')

// ---- 收藏悬浮框 ----
const favOpen = ref(false)
const favLoading = ref(false)
const favorites = ref([])
const selected = ref([])
const paying = ref(false)
let closeTimer = null

const selectedTotal = computed(() =>
  favorites.value
    .filter((f) => selected.value.includes(f.id))
    .reduce((sum, f) => sum + Number(f.final_price ?? f.price), 0)
)

function specOf(f) {
  const a = f.attributes || {}
  return ['内存', '硬盘', '屏幕'].map((k) => a[k]).filter(Boolean).slice(0, 2).join(' / ')
}

function openFav() {
  clearTimeout(closeTimer)
  favOpen.value = true
  loadFavorites()
}
function closeFav() {
  // 留一点缓冲，避免鼠标划过缝隙就收起
  closeTimer = setTimeout(() => { favOpen.value = false }, 150)
}

async function loadFavorites() {
  if (!isLoggedIn() || merchant.value) { favorites.value = []; return }
  favLoading.value = true
  try {
    const { data } = await getFavorites()
    favorites.value = data?.data?.favorites || data?.data || []
  } catch (e) {
    favorites.value = []
  } finally {
    favLoading.value = false
  }
}

function toggleSelect(id, checked) {
  if (checked) selected.value = [...selected.value, id]
  else selected.value = selected.value.filter((x) => x !== id)
}

function goProduct(id) {
  favOpen.value = false
  router.push('/products/' + id)
}

async function moveToCart(f) {
  try {
    await addToCart(f.id)
    await removeFavorite(f.id)
    ElMessage.success('已移入购物车')
    selected.value = selected.value.filter((x) => x !== f.id)
    loadFavorites()
    refreshCount()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

async function removeFav(f) {
  try {
    await removeFavorite(f.id)
    selected.value = selected.value.filter((x) => x !== f.id)
    loadFavorites()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

// 付款：把勾选商品加入购物车后进结算页，由用户确认下单（避免误触直接生成订单）
async function goCheckout() {
  paying.value = true
  try {
    for (const id of selected.value) {
      await addToCart(id)
    }
    ElMessage.success('已加入购物车，请确认后付款')
    selected.value = []
    favOpen.value = false
    refreshCount()
    router.push('/me')
  } catch (e) {
    ElMessage.error('操作失败，请重试')
  } finally {
    paying.value = false
  }
}

async function refreshCount() {
  // 商家没有购物车，不必请求
  if (!isLoggedIn() || merchant.value) { cartCount.value = 0; return }
  try {
    const { data } = await getCart()
    cartCount.value = (data?.data?.cart || []).length
  } catch (e) {
    cartCount.value = 0
  }
}

function logout() {
  clearAuth()
  user.value = null
  favorites.value = []
  selected.value = []
  refreshCount()
  router.push('/')
}

onMounted(() => {
  refreshCount()
  window.addEventListener('cart-changed', refreshCount)
  window.addEventListener('favorites-changed', loadFavorites)
  window.addEventListener('auth-changed', () => {
    user.value = getUser()
    refreshCount()
  })
  user.value = getUser()
})
watch(() => route.path, () => {
  user.value = getUser()
  refreshCount()
})
</script>

<style scoped>
.app-nav { min-height: 100vh; }
.nav-inner {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 28px; height: 60px;
  background: var(--nav-bg);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
  box-shadow: 0 1px 10px rgba(31, 45, 92, 0.05);
  position: sticky; top: 0; z-index: 100;
}
.brand { display: flex; align-items: center; gap: 10px; text-decoration: none; }
.brand-logo {
  display: inline-flex; align-items: center; justify-content: center;
  width: 34px; height: 34px; border-radius: 10px;
  background: var(--primary-grad); color: #fff; font-weight: 800; font-size: 17px;
  box-shadow: 0 4px 12px rgba(79, 124, 255, 0.4);
}
.brand-name { font-weight: 700; font-size: 18px; color: var(--text); letter-spacing: 0.5px; }
.nav-links { display: flex; gap: 6px; align-items: center; }
.nav-link {
  position: relative; color: var(--text-sub); text-decoration: none;
  padding: 7px 16px; border-radius: 999px; font-size: 14.5px;
  transition: all 0.18s ease;
}
.nav-link:hover { background: rgba(79, 124, 255, 0.08); color: var(--primary); }
.nav-link.router-link-active {
  background: var(--primary-grad); color: #fff; font-weight: 600;
  box-shadow: 0 4px 12px rgba(79, 124, 255, 0.35);
}
.login-btn { background: none; }
.nav-link.login-btn.router-link-active { background: var(--primary-grad); }
.nav-user { display: flex; align-items: center; gap: 8px; color: var(--text-sub); font-size: 14px; padding: 0 8px; }
.user-avatar {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: 50%;
  background: var(--primary-grad); color: #fff; font-size: 13px; font-weight: 700;
}
/* 商家用暖色头像，与买家区分 */
.user-avatar.merchant { background: linear-gradient(135deg, #ff8f1f, #ff4d18); }
.role-tag {
  background: #fff4e6; color: #fa6400; font-size: 11px; font-weight: 700;
  padding: 1px 6px; border-radius: 4px;
}
.badge {
  position: absolute; top: -6px; right: -8px; background: #ff4d4f; color: #fff;
  font-size: 11px; min-width: 17px; height: 17px; line-height: 17px; text-align: center;
  border-radius: 9px; padding: 0 4px; font-weight: 600;
  border: 2px solid var(--surface);
}

/* ===== 收藏悬浮框 ===== */
.fav-wrap { position: relative; }
.fav-panel {
  position: absolute; top: calc(100% + 10px); right: 0;
  width: 760px; max-height: 460px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 14px; box-shadow: var(--card-shadow-hover);
  z-index: 200; display: flex; flex-direction: column; overflow: hidden;
}
/* 顶部留一条透明补丁，鼠标从按钮移向面板不会中断 hover */
.fav-panel::before {
  content: ''; position: absolute; top: -10px; left: 0; right: 0; height: 10px;
}
.fav-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; border-bottom: 1px solid var(--border);
  font-weight: 700; color: var(--text); font-size: 14px;
}
.fav-count { color: var(--text-muted); font-weight: 500; font-size: 12.5px; }
.fav-empty { padding: 34px; text-align: center; color: var(--text-muted); font-size: 13px; }
.fav-list { overflow-y: auto; flex: 1; }
.fav-row {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 16px; cursor: pointer;
  border-bottom: 1px solid var(--border);
  transition: background 0.15s ease;
}
.fav-row:hover { background: var(--surface-2); }
.fav-check { flex-shrink: 0; }
.fav-main { flex: 1; min-width: 0; }
.fav-title {
  font-size: 13px; color: var(--text); line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden;
}
.fav-prefix { color: #e4393c; font-weight: 700; }
.fav-promo { display: flex; gap: 8px; margin-top: 4px; flex-wrap: wrap; }
.fp-tag { color: #e4393c; font-size: 11.5px; }
.fav-spec { width: 120px; flex-shrink: 0; color: var(--text-muted); font-size: 11.5px; line-height: 1.5; }
.fav-price { width: 96px; flex-shrink: 0; text-align: right; color: #ff4d18; font-weight: 800; font-size: 15px; }
.fav-ops { width: 84px; flex-shrink: 0; display: flex; flex-direction: column; gap: 4px; align-items: flex-end; }
.fav-ops a { color: var(--text-muted); font-size: 12px; cursor: pointer; }
.fav-ops a:hover { color: var(--primary); }
.fav-ops a.danger:hover { color: #ff4d4f; }
.fav-foot {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px; border-top: 1px solid var(--border); background: var(--surface-2);
}
.fav-total { color: var(--text-muted); font-size: 12.5px; }
.fav-total b { color: #ff4d18; font-size: 15px; margin-left: 6px; }

.fav-fade-enter-active, .fav-fade-leave-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.fav-fade-enter-from, .fav-fade-leave-to { opacity: 0; transform: translateY(-6px); }
</style>
