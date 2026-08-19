<template>
  <div class="me-page">
    <div class="me-header">
      <h2>我的导购</h2>
      <div class="me-sub">
        <span v-if="isLoggedIn()">{{ user?.nickname || user?.username }} 的购物空间</span>
        <router-link v-else to="/login" class="login-link">去登录</router-link>
        <el-button v-if="isLoggedIn()" size="small" text type="danger" @click="logout">退出</el-button>
      </div>
    </div>

    <!-- 用户画像 -->
    <el-card class="section" shadow="never">
      <template #header><b>我的偏好画像</b><span class="tip">系统根据我们的对话理解你</span></template>
      <div v-if="profileTags.length" class="tags">
        <el-tag v-for="t in profileTags" :key="t" type="primary" effect="plain" class="tag">{{ t }}</el-tag>
      </div>
      <div v-else class="empty">还没有偏好数据，去对话页聊聊你的需求吧</div>
      <div ref="radarRef" class="radar"></div>
    </el-card>

    <!-- 购物车 -->
    <el-card class="section" shadow="never">
      <template #header><b>购物车</b><span class="tip">对话中看中的商品在这里</span></template>
      <el-table v-if="cart.length" :data="cart" style="width: 100%">
        <el-table-column prop="title" label="商品" min-width="200" />
        <el-table-column label="品类" width="90">
          <template #default="{ row }">{{ row.category }}</template>
        </el-table-column>
        <el-table-column label="单价" width="100">
          <template #default="{ row }">¥{{ row.price.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="quantity" label="数量" width="80" />
        <el-table-column label="小计" width="110">
          <template #default="{ row }">¥{{ (row.price * row.quantity).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button size="small" type="danger" text @click="remove(row.item_id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-else class="empty">购物车是空的，去对话页让系统推荐并加入购物车吧</div>
      <div v-if="cart.length" class="cart-footer">
        <span class="total">合计：<b class="total-price">¥{{ total.toLocaleString() }}</b></span>
        <el-button type="primary" @click="checkout">确认下单</el-button>
      </div>
    </el-card>

    <!-- 历史订单 -->
    <el-card class="section" shadow="never">
      <template #header><b>历史订单</b></template>
      <el-empty v-if="!orders.length" description="还没有订单" :image-size="60" />
      <div v-for="o in orders" :key="o.order_no" class="order-item">
        <div class="order-head">
          <span class="order-no">{{ o.order_no }}</span>
          <span class="order-status">{{ statusText(o.status) }}</span>
        </div>
        <div class="order-body">
          <span v-for="p in o.products" :key="p.id" class="order-prod">{{ p.title.slice(0, 18) }} ×{{ p.quantity }}</span>
        </div>
        <div class="order-total">¥{{ o.total_amount.toLocaleString() }} · {{ o.created_at }}</div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import { getProfile, getCart, removeCartItem, createOrder, getOrders, isLoggedIn, getUser, clearAuth } from '../api'

const router = useRouter()
const user = ref(getUser())
const profileTags = ref([])
const radarRef = ref(null)
const cart = ref([])
const orders = ref([])

const total = ref(0)

function logout() {
  clearAuth()
  ElMessage.success('已退出')
  router.push('/login')
}

function statusText(s) {
  return { pending: '待处理', paid: '已支付', shipped: '已发货', done: '已完成' }[s] || s
}

async function loadAll() {
  try {
    const [prof, cartRes, orderRes] = await Promise.all([
      getProfile(), getCart(), getOrders(),
    ])
    profileTags.value = prof?.data?.data?.tags || []
    cart.value = cartRes?.data?.data?.cart || []
    orders.value = orderRes?.data?.data?.orders || []
    total.value = cart.value.reduce((s, c) => s + c.price * c.quantity, 0)
    await nextTick()
    renderRadar(prof?.data?.data?.radar)
  } catch (e) {
    ElMessage.error('加载失败，请检查后端服务')
  }
}

function renderRadar(radar) {
  if (!radarRef.value) return
  if (!radar) {
    radarRef.value.innerHTML = ''
    return
  }
  const chart = echarts.init(radarRef.value)
  const indicators = Object.keys(radar).map((k) => ({ name: k, max: 100 }))
  chart.setOption({
    radar: { indicator: indicators, radius: '65%' },
    series: [{
      type: 'radar',
      data: [{ value: Object.values(radar), name: '偏好', areaStyle: { opacity: 0.25 } }],
    }],
  })
}

async function remove(itemId) {
  await removeCartItem(itemId)
  ElMessage.success('已移除')
  loadAll()
}

async function checkout() {
  if (!cart.value.length) return
  try {
    await ElMessageBox.confirm(
      `确认下单这 ${cart.value.length} 件商品，合计 ¥${total.value.toLocaleString()}？`,
      '确认下单', { confirmButtonText: '确认', cancelButtonText: '再看看', type: 'info' }
    )
  } catch (e) {
    return // 用户取消（人在环路）
  }
  const { data } = await createOrder()
  ElMessage.success(`下单成功，订单号 ${data?.data?.order_no}`)
  window.dispatchEvent(new CustomEvent('cart-changed'))
  loadAll()
}

onMounted(loadAll)
</script>

<style scoped>
.me-page { max-width: 900px; margin: 0 auto; padding: 26px 20px 40px; }
.me-header h2 { margin: 0; color: #2a3050; }
.me-header .me-sub { color: #98a0c0; margin: 6px 0 18px; display: flex; align-items: center; gap: 12px; font-size: 14px; }
.login-link { color: var(--primary); text-decoration: none; }
.section { margin-bottom: 16px; border-radius: var(--card-radius); border: none; box-shadow: var(--card-shadow); }
.section .tip { color: #a6aecb; font-weight: 400; font-size: 12px; margin-left: 10px; }
.tags { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.radar { height: 260px; }
.empty { color: #a6aecb; padding: 12px 0; }
.cart-footer { display: flex; justify-content: flex-end; align-items: center; gap: 20px; margin-top: 16px; }
.total { font-size: 15px; color: #4a5175; }
.total-price { color: var(--price); font-size: 22px; font-weight: 800; }
.order-item { border: 1px solid rgba(31,45,92,0.07); border-radius: 12px; padding: 12px 16px; margin-bottom: 10px; background: #fff; }
.order-head { display: flex; justify-content: space-between; margin-bottom: 6px; }
.order-no { font-weight: 600; color: var(--primary); }
.order-status { color: #2e9e5b; font-size: 12px; }
.order-body { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 6px; }
.order-prod { color: #4a5175; font-size: 13px; }
.order-total { color: #a6aecb; font-size: 12px; }
</style>
