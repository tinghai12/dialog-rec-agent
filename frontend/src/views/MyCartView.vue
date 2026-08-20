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

    <!-- 收货地址 -->
    <el-card class="section" shadow="never">
      <template #header>
        <b>收货地址</b><span class="tip">长期保存，下单时直接选</span>
        <el-button size="small" type="primary" text class="head-btn" @click="openAddr()">＋ 新增地址</el-button>
      </template>
      <div v-if="!addresses.length" class="empty">还没有收货地址，添加一个才能下单</div>
      <div v-for="a in addresses" :key="a.id" class="addr-row" :class="{ picked: a.id === pickedAddressId }">
        <el-radio :model-value="pickedAddressId" :value="a.id" @change="pickedAddressId = a.id">
          <span class="addr-name">{{ a.receiver }}</span>
          <span class="addr-phone">{{ a.phone }}</span>
          <el-tag v-if="a.is_default" size="small" type="primary" effect="plain">默认</el-tag>
          <el-tag v-if="a.lng == null" size="small" type="warning" effect="plain">无坐标</el-tag>
        </el-radio>
        <div class="addr-text">{{ a.full_text }}</div>
        <div class="addr-ops">
          <el-button link type="primary" size="small" @click="openAddr(a)">编辑</el-button>
          <el-button v-if="!a.is_default" link size="small" @click="makeDefault(a)">设为默认</el-button>
          <el-button link type="danger" size="small" @click="removeAddr(a)">删除</el-button>
        </div>
      </div>
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
        <span class="ship-to" v-if="currentAddress">寄往：{{ currentAddress.full_text }}</span>
        <span class="total">合计：<b class="total-price">¥{{ total.toLocaleString() }}</b></span>
        <el-button type="primary" @click="checkout">确认下单</el-button>
      </div>
    </el-card>

    <!-- 历史订单 -->
    <el-card class="section" shadow="never">
      <template #header><b>我的订单</b><span class="tip">商家接单后可查看配送轨迹</span></template>
      <el-empty v-if="!orders.length" description="还没有订单" :image-size="60" />
      <div v-for="o in orders" :key="o.order_no" class="order-item">
        <div class="order-head">
          <span class="order-no">{{ o.order_no }}</span>
          <span class="order-shop">{{ o.shop_name }}</span>
          <span class="order-status" :class="o.status">{{ o.status_text }}</span>
        </div>

        <div class="order-body">
          <ProductThumb v-for="p in o.products" :key="p.id" :product="p" :size="40" />
          <span class="order-prods">
            {{ o.products.map((p) => p.title).join('、').slice(0, 48) }}
          </span>
        </div>

        <!-- 配送信息：仅商家接单后展示 -->
        <div v-if="o.status === 'shipping'" class="order-ship">
          <div class="ship-bar"><div class="ship-fill" :style="{ width: (o.progress * 100).toFixed(1) + '%' }"></div></div>
          <span class="ship-text">
            {{ o.rider_name }}配送中 · 预计 {{ o.remain_minutes }} 分钟送达
          </span>
          <el-button size="small" type="primary" plain @click="track(o)">查看配送轨迹</el-button>
        </div>
        <div v-else-if="o.status === 'delivered'" class="order-ship">
          <span class="ship-text done">已送达</span>
          <el-button size="small" text type="primary" @click="track(o)">查看轨迹</el-button>
        </div>
        <div v-else-if="o.status === 'pending'" class="order-ship">
          <span class="ship-text">等待「{{ o.shop_name }}」接单，接单后可查看配送</span>
        </div>

        <div class="order-total">¥{{ o.total_amount.toLocaleString() }} · {{ o.created_at }}</div>
      </div>
    </el-card>

    <!-- 用户画像 -->
    <el-card class="section" shadow="never">
      <template #header><b>我的偏好画像</b><span class="tip">系统根据我们的对话理解你</span></template>
      <div v-if="profileTags.length" class="tags">
        <el-tag v-for="t in profileTags" :key="t" type="primary" effect="plain" class="tag">{{ t }}</el-tag>
      </div>
      <div v-else class="empty">还没有偏好数据，去对话页聊聊你的需求吧</div>
      <div ref="radarRef" class="radar"></div>
    </el-card>

    <!-- 地址编辑弹窗 -->
    <el-dialog v-model="addrVisible" :title="addrForm.id ? '编辑地址' : '新增收货地址'" width="480">
      <el-form label-width="72px">
        <el-form-item label="收货人" required>
          <el-input v-model="addrForm.receiver" placeholder="姓名" />
        </el-form-item>
        <el-form-item label="手机号" required>
          <el-input v-model="addrForm.phone" placeholder="联系电话" />
        </el-form-item>
        <el-form-item label="省/市/区">
          <div class="region">
            <el-input v-model="addrForm.province" placeholder="省" />
            <el-input v-model="addrForm.city" placeholder="市" />
            <el-input v-model="addrForm.district" placeholder="区/县" />
          </div>
        </el-form-item>
        <el-form-item label="详细地址" required>
          <el-input v-model="addrForm.detail" type="textarea" :rows="2" placeholder="街道、门牌号" />
        </el-form-item>
        <el-form-item label="坐标">
          <div class="geo-row">
            <span v-if="addrForm.lng" class="geo-ok">已定位 {{ addrForm.lng.toFixed(4) }}, {{ addrForm.lat.toFixed(4) }}</span>
            <span v-else class="geo-none">未定位（配送轨迹需要坐标）</span>
            <el-button size="small" :loading="geoLoading" @click="doGeocode">解析地址坐标</el-button>
          </div>
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="addrForm.is_default" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addrVisible = false">取消</el-button>
        <el-button type="primary" :loading="addrSaving" @click="saveAddr">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import ProductThumb from '../components/ProductThumb.vue'
import { geocode, hasAMapKey } from '../amap'
import {
  getProfile, getCart, removeCartItem, createOrder, getOrders, isLoggedIn, getUser, clearAuth,
  listAddresses, createAddress, updateAddress, setDefaultAddress, deleteAddress,
} from '../api'

const router = useRouter()
const user = ref(getUser())
const profileTags = ref([])
const radarRef = ref(null)
const cart = ref([])
const orders = ref([])
const addresses = ref([])
const pickedAddressId = ref(null)
const total = ref(0)

const currentAddress = computed(() =>
  addresses.value.find((a) => a.id === pickedAddressId.value) || null
)

function logout() {
  clearAuth()
  ElMessage.success('已退出')
  router.push('/login')
}

async function loadAll() {
  try {
    const [prof, cartRes, orderRes, addrRes] = await Promise.all([
      getProfile(), getCart(), getOrders(), listAddresses(),
    ])
    profileTags.value = prof?.data?.data?.tags || []
    cart.value = cartRes?.data?.data?.cart || []
    orders.value = orderRes?.data?.data?.orders || []
    addresses.value = addrRes?.data?.data?.addresses || []
    if (!pickedAddressId.value || !addresses.value.some((a) => a.id === pickedAddressId.value)) {
      pickedAddressId.value = addresses.value.find((a) => a.is_default)?.id || addresses.value[0]?.id || null
    }
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

function track(o) {
  router.push(`/orders/${o.order_no}/track`)
}

async function checkout() {
  if (!cart.value.length) return
  if (!pickedAddressId.value) return ElMessage.warning('请先添加并选择收货地址')
  try {
    await ElMessageBox.confirm(
      `确认下单这 ${cart.value.length} 件商品，合计 ¥${total.value.toLocaleString()}？\n寄往：${currentAddress.value?.full_text || ''}`,
      '确认下单', { confirmButtonText: '确认', cancelButtonText: '再看看', type: 'info' }
    )
  } catch (e) {
    return // 用户取消（人在环路）
  }
  const { data } = await createOrder(pickedAddressId.value)
  if (data?.code !== 0) return ElMessage.error(data?.message)
  const n = data.data.orders.length
  ElMessage.success(n > 1 ? `已按店铺拆成 ${n} 笔订单，等待商家接单` : `下单成功，订单号 ${data.data.order_no}`)
  window.dispatchEvent(new CustomEvent('cart-changed'))
  loadAll()
}

// ---- 地址 ----
const addrVisible = ref(false)
const addrSaving = ref(false)
const geoLoading = ref(false)
const addrForm = reactive({
  id: null, receiver: '', phone: '', province: '', city: '', district: '',
  detail: '', lng: null, lat: null, is_default: false,
})

function openAddr(a = null) {
  Object.assign(addrForm, a
    ? { ...a, is_default: !!a.is_default }
    : { id: null, receiver: '', phone: '', province: '', city: '', district: '', detail: '', lng: null, lat: null, is_default: false })
  addrVisible.value = true
}

async function doGeocode() {
  if (!hasAMapKey()) return ElMessage.warning('未配置高德 Key，无法解析坐标')
  const full = `${addrForm.province}${addrForm.city}${addrForm.district}${addrForm.detail}`
  if (!full.trim()) return ElMessage.warning('先填写地址')
  geoLoading.value = true
  try {
    const r = await geocode(full, addrForm.city)
    if (!r) return ElMessage.warning('没能解析出坐标，请把地址写具体些')
    addrForm.lng = r.lng
    addrForm.lat = r.lat
    ElMessage.success('已定位：' + r.formatted)
  } catch (e) {
    ElMessage.error('地址解析失败')
  } finally {
    geoLoading.value = false
  }
}

async function saveAddr() {
  if (!addrForm.receiver.trim() || !addrForm.phone.trim() || !addrForm.detail.trim()) {
    return ElMessage.warning('收货人、手机号、详细地址都要填')
  }
  addrSaving.value = true
  try {
    // 没手动定位就自动解析一次，尽量让订单能画轨迹
    if (addrForm.lng == null && hasAMapKey()) {
      try {
        const full = `${addrForm.province}${addrForm.city}${addrForm.district}${addrForm.detail}`
        const r = await geocode(full, addrForm.city)
        if (r) { addrForm.lng = r.lng; addrForm.lat = r.lat }
      } catch (e) { /* 定位失败不阻断保存 */ }
    }
    const payload = { ...addrForm }
    delete payload.id
    const { data } = addrForm.id
      ? await updateAddress(addrForm.id, payload)
      : await createAddress(payload)
    if (data?.code !== 0) return ElMessage.error(data?.message)
    ElMessage.success(data.message)
    addrVisible.value = false
    loadAll()
  } finally {
    addrSaving.value = false
  }
}

async function makeDefault(a) {
  await setDefaultAddress(a.id)
  ElMessage.success('已设为默认')
  loadAll()
}

async function removeAddr(a) {
  try {
    await ElMessageBox.confirm(`删除地址「${a.full_text}」？`, '删除地址', { type: 'warning' })
  } catch (e) { return }
  await deleteAddress(a.id)
  ElMessage.success('已删除')
  loadAll()
}

onMounted(loadAll)
</script>

<style scoped>
.me-page { max-width: 940px; margin: 0 auto; padding: 26px 20px 40px; }
.me-header h2 { margin: 0; color: var(--text); }
.me-header .me-sub { color: var(--text-muted); margin: 6px 0 18px; display: flex; align-items: center; gap: 12px; font-size: 14px; }
.login-link { color: var(--primary); text-decoration: none; }
.section { margin-bottom: 16px; border-radius: var(--card-radius); border: none; box-shadow: var(--card-shadow); }
.section .tip { color: var(--text-muted); font-weight: 400; font-size: 12px; margin-left: 10px; }
.head-btn { float: right; }
.tags { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.radar { height: 260px; }
.empty { color: var(--text-muted); padding: 12px 0; }

/* 地址 */
.addr-row { padding: 10px 12px; border-radius: 10px; border: 1px solid var(--border); margin-bottom: 8px; }
.addr-row.picked { border-color: var(--primary); background: rgba(79, 124, 255, 0.05); }
.addr-name { font-weight: 600; color: var(--text); margin-right: 10px; }
.addr-phone { color: var(--text-sub); margin-right: 10px; }
.addr-text { color: var(--text-muted); font-size: 13px; margin: 4px 0 0 24px; }
.addr-ops { margin-left: 20px; }
.region { display: flex; gap: 8px; }
.geo-row { display: flex; align-items: center; gap: 12px; }
.geo-ok { color: #0f9d58; font-size: 13px; }
.geo-none { color: var(--text-muted); font-size: 13px; }

.cart-footer { display: flex; justify-content: flex-end; align-items: center; gap: 20px; margin-top: 16px; flex-wrap: wrap; }
.ship-to { color: var(--text-muted); font-size: 12.5px; margin-right: auto; }
.total { font-size: 15px; color: var(--text-sub); }
.total-price { color: var(--price); font-size: 22px; font-weight: 800; }

/* 订单 */
.order-item { border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px; margin-bottom: 10px; background: var(--surface); }
.order-head { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.order-no { font-weight: 600; color: var(--primary); }
.order-shop { color: var(--text-muted); font-size: 12.5px; }
.order-status { margin-left: auto; font-size: 12px; padding: 2px 10px; border-radius: 999px; background: var(--surface-2); color: var(--text-muted); }
.order-status.shipping { background: #fff4e6; color: #fa6400; }
.order-status.delivered { background: #e8f8ee; color: #0f9d58; }
.order-status.cancelled { background: #fff1f0; color: #e4393c; }
.order-body { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.order-prods { color: var(--text-sub); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.order-ship { display: flex; align-items: center; gap: 12px; margin: 8px 0; }
.ship-bar { flex: 1; height: 6px; border-radius: 3px; background: var(--surface-2); overflow: hidden; max-width: 240px; }
.ship-fill { height: 100%; background: linear-gradient(90deg, #ff8f1f, #ff4d18); border-radius: 3px; transition: width 0.6s ease; }
.ship-text { color: var(--text-sub); font-size: 12.5px; }
.ship-text.done { color: #0f9d58; }
.order-total { color: var(--text-muted); font-size: 12px; }
</style>
