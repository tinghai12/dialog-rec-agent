<template>
  <div class="track-page">
    <div class="track-head">
      <el-button text @click="$router.back()">← 返回</el-button>
      <span class="order-no">{{ order?.order_no }}</span>
      <span class="status" :class="order?.status">{{ order?.status_text }}</span>
    </div>

    <div v-if="error" class="track-error">
      <el-alert :title="error" type="warning" :closable="false" show-icon />
    </div>

    <div class="map-wrap">
      <div ref="mapRef" class="map"></div>

      <!-- 无 Key / 加载失败时的兜底底图：同样画双折线与小车 -->
      <svg v-if="fallback" class="fallback" viewBox="0 0 800 500" preserveAspectRatio="xMidYMid slice">
        <rect width="800" height="500" fill="#f2f3f5" />
        <g stroke="#e2e4e8" stroke-width="1">
          <line v-for="i in 15" :key="'h' + i" :x1="0" :x2="800" :y1="i * 33" :y2="i * 33" />
          <line v-for="i in 24" :key="'v' + i" :y1="0" :y2="500" :x1="i * 33" :x2="i * 33" />
        </g>
        <polyline :points="fbTraveled" fill="none" stroke="#ff6a00" stroke-width="7"
                  stroke-linecap="round" stroke-linejoin="round" />
        <polyline :points="fbRemaining" fill="none" stroke="#ff6a00" stroke-width="5"
                  stroke-dasharray="12 10" stroke-linecap="round" opacity="0.55" />
        <circle :cx="fbStart[0]" :cy="fbStart[1]" r="8" fill="#fff" stroke="#ff6a00" stroke-width="3" />
        <circle :cx="fbEnd[0]" :cy="fbEnd[1]" r="8" fill="#ff6a00" />
        <g :transform="`translate(${fbCar[0]},${fbCar[1]}) rotate(${carAngle})`">
          <circle r="15" fill="#fff" stroke="#ff6a00" stroke-width="2.5" />
          <text y="6" text-anchor="middle" font-size="17">🛵</text>
        </g>
      </svg>

      <!-- 底部悬浮卡片 -->
      <div class="info-card">
        <div class="info-main">
          <div class="info-title">
            <span class="dot"></span>
            {{ deliveringText }}
          </div>
          <div class="info-eta">
            <template v-if="order?.status === 'shipping'">
              预计 <b>{{ order.remain_minutes }}</b> 分钟后送达
            </template>
            <template v-else-if="order?.status === 'delivered'">订单已送达，感谢下单</template>
            <template v-else>{{ order?.status_text }}</template>
          </div>
          <div class="info-addr">
            <span class="from">{{ order?.origin_name || '发货仓' }}</span>
            <span class="arrow">→</span>
            <span class="to">{{ order?.address_text }}</span>
          </div>
        </div>

        <div class="rider">
          <div class="rider-avatar">{{ (order?.rider_name || '骑')[0] }}</div>
          <div class="rider-info">
            <div class="rider-name">{{ order?.rider_name || '待分配' }}</div>
            <div class="rider-phone">{{ order?.rider_phone }}</div>
          </div>
        </div>
      </div>

      <!-- 调试：手动拖动配送进度 -->
      <div class="debug-bar" :class="{ open: debugOpen }">
        <el-button v-if="!debugOpen" size="small" class="debug-toggle" @click="debugOpen = true">调试进度</el-button>
        <template v-else>
          <span class="debug-label">进度 {{ Math.round(displayProgress * 100) }}%</span>
          <el-slider v-model="debugValue" :min="0" :max="100" :step="1" class="debug-slider"
                     @input="onDebugDrag" />
          <el-button size="small" text @click="exitDebug">跟随实时</el-button>
        </template>
      </div>
    </div>

    <!-- 商品清单 -->
    <div class="goods">
      <div v-for="p in order?.products || []" :key="p.id" class="goods-row">
        <ProductThumb :product="p" :size="48" />
        <span class="g-title">{{ p.title }}</span>
        <span class="g-qty">×{{ p.quantity }}</span>
        <span class="g-price">¥{{ Number(p.price).toLocaleString() }}</span>
      </div>
      <div class="goods-total">合计 <b>¥{{ Number(order?.total_amount || 0).toLocaleString() }}</b></div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import ProductThumb from '../components/ProductThumb.vue'
import { getOrder, saveOrderRoute } from '../api'
import { loadAMap, planRoute, hasAMapKey } from '../amap'

const route = useRoute()
const mapRef = ref(null)
const order = ref(null)
const error = ref('')
const fallback = ref(false)

const points = ref([])            // 完整路线 [[lng,lat], ...]
const displayProgress = ref(0)    // 当前展示进度 0~1（带动画插值）
const carAngle = ref(0)

const debugOpen = ref(false)
const debugValue = ref(0)
const debugMode = ref(false)

let map = null
let traveledLine = null
let remainingLine = null
let carMarker = null
let rafId = null
let syncTimer = null
let targetProgress = 0            // 后端算出的真实进度，动画向它逼近

const deliveringText = computed(() => {
  if (!order.value) return '加载中'
  if (order.value.status === 'shipping') return `${order.value.rider_name || '骑手'}正在送货中`
  if (order.value.status === 'delivered') return '已送达'
  if (order.value.status === 'pending') return '等待商家接单'
  return order.value.status_text
})

// ---------- 几何工具 ----------
function cumulative(pts) {
  const acc = [0]
  for (let i = 1; i < pts.length; i++) {
    const dx = pts[i][0] - pts[i - 1][0]
    const dy = pts[i][1] - pts[i - 1][1]
    acc.push(acc[i - 1] + Math.hypot(dx, dy))
  }
  return acc
}

/** 按进度切分路线，返回 {traveled, remaining, car, angle} */
function splitAt(pts, progress) {
  if (pts.length < 2) return { traveled: pts, remaining: pts, car: pts[0] || [0, 0], angle: 0 }
  const acc = cumulative(pts)
  const total = acc[acc.length - 1]
  const target = total * Math.min(1, Math.max(0, progress))

  let i = 1
  while (i < acc.length - 1 && acc[i] < target) i++
  const segStart = pts[i - 1]
  const segEnd = pts[i]
  const segLen = acc[i] - acc[i - 1] || 1
  const t = Math.min(1, Math.max(0, (target - acc[i - 1]) / segLen))
  const car = [
    segStart[0] + (segEnd[0] - segStart[0]) * t,
    segStart[1] + (segEnd[1] - segStart[1]) * t,
  ]
  // 方位角：正北为 0，顺时针增大
  const dLng = (segEnd[0] - segStart[0]) * Math.cos((segEnd[1] * Math.PI) / 180)
  const dLat = segEnd[1] - segStart[1]
  const angle = (Math.atan2(dLng, dLat) * 180) / Math.PI

  return {
    traveled: [...pts.slice(0, i), car],
    remaining: [car, ...pts.slice(i)],
    car,
    angle,
  }
}

// ---------- 高德地图 ----------
const CAR_ICON =
  'data:image/svg+xml;charset=utf-8,' +
  encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">
    <circle cx="20" cy="20" r="15" fill="#fff" stroke="#ff6a00" stroke-width="3"/>
    <path d="M20 9 L25 20 L20 17.5 L15 20 Z" fill="#ff6a00"/>
    <circle cx="20" cy="23" r="3.5" fill="#ff6a00"/>
  </svg>`)

async function initMap() {
  const AMap = await loadAMap()
  map = new AMap.Map(mapRef.value, {
    zoom: 14,
    mapStyle: 'amap://styles/whitesmoke',   // 浅色/灰白主题
    resizeEnable: true,
    viewMode: '2D',
  })

  traveledLine = new AMap.Polyline({
    path: [], strokeColor: '#ff6a00', strokeWeight: 7, strokeOpacity: 1,
    lineJoin: 'round', lineCap: 'round', zIndex: 60,
  })
  remainingLine = new AMap.Polyline({
    path: [], strokeColor: '#ff6a00', strokeWeight: 5, strokeOpacity: 0.55,
    strokeStyle: 'dashed', strokeDasharray: [10, 8],
    lineJoin: 'round', zIndex: 50,
  })
  carMarker = new AMap.Marker({
    icon: new AMap.Icon({ image: CAR_ICON, size: new AMap.Size(40, 40), imageSize: new AMap.Size(40, 40) }),
    offset: new AMap.Pixel(-20, -20),
    autoRotation: false,
    zIndex: 100,
  })

  const start = new AMap.Marker({
    position: order.value.origin, zIndex: 80,
    content: '<div class="pin pin-start">仓</div>',
    offset: new AMap.Pixel(-13, -13),
  })
  const end = new AMap.Marker({
    position: order.value.dest, zIndex: 80,
    content: '<div class="pin pin-end">收</div>',
    offset: new AMap.Pixel(-13, -13),
  })

  map.add([traveledLine, remainingLine, start, end, carMarker])
  map.setFitView([traveledLine, remainingLine, start, end], false, [80, 80, 180, 80])
}

function renderFrame(progress) {
  const { traveled, remaining, car, angle } = splitAt(points.value, progress)
  carAngle.value = angle
  if (map) {
    traveledLine.setPath(traveled)
    remainingLine.setPath(remaining)
    carMarker.setPosition(car)
    carMarker.setAngle(angle)
  } else {
    fbState.value = { traveled, remaining, car }
  }
}

// ---------- 兜底 SVG 底图 ----------
const fbState = ref({ traveled: [], remaining: [], car: [0, 0] })

const fbBounds = computed(() => {
  const pts = points.value
  if (!pts.length) return { minX: 0, maxX: 1, minY: 0, maxY: 1 }
  const xs = pts.map((p) => p[0])
  const ys = pts.map((p) => p[1])
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) }
})

function toSvg(p) {
  const { minX, maxX, minY, maxY } = fbBounds.value
  const w = maxX - minX || 1
  const h = maxY - minY || 1
  return [60 + ((p[0] - minX) / w) * 680, 420 - ((p[1] - minY) / h) * 320]
}
const fbTraveled = computed(() => fbState.value.traveled.map((p) => toSvg(p).join(',')).join(' '))
const fbRemaining = computed(() => fbState.value.remaining.map((p) => toSvg(p).join(',')).join(' '))
const fbCar = computed(() => toSvg(fbState.value.car))
const fbStart = computed(() => toSvg(points.value[0] || [0, 0]))
const fbEnd = computed(() => toSvg(points.value[points.value.length - 1] || [0, 0]))

// ---------- 进度动画 ----------
function animate() {
  // 每帧向目标进度逼近，做出平滑移动的效果
  const diff = targetProgress - displayProgress.value
  if (Math.abs(diff) > 0.00002) {
    displayProgress.value += diff * 0.06
    renderFrame(displayProgress.value)
  }
  rafId = requestAnimationFrame(animate)
}

function localAdvance() {
  // 两次后端对齐之间，按时间自行推进，避免小车停顿
  if (debugMode.value || !order.value || order.value.status !== 'shipping') return
  const eta = Math.max(1, order.value.eta_minutes)
  targetProgress = Math.min(1, targetProgress + 1 / (eta * 60))
}

function onDebugDrag(v) {
  debugMode.value = true
  targetProgress = v / 100
  displayProgress.value = targetProgress
  renderFrame(displayProgress.value)
}

function exitDebug() {
  debugMode.value = false
  debugOpen.value = false
  targetProgress = order.value?.progress ?? 0
}

// ---------- 数据 ----------
async function loadOrder(first = false) {
  const { data } = await getOrder(route.params.orderNo)
  if (data?.code !== 0) {
    error.value = data?.message || '订单加载失败'
    return null
  }
  order.value = data.data
  if (!debugMode.value) {
    targetProgress = order.value.progress
    if (first) displayProgress.value = order.value.progress
  }
  return order.value
}

async function ensureRoute() {
  const o = order.value
  if (!o?.origin || !o?.dest) {
    error.value = '该订单缺少收货坐标，无法展示轨迹（添加地址时请选到具体位置）'
    return false
  }
  if (o.route?.length >= 2) {
    points.value = o.route
    return true
  }
  // 首次查看：用高德规划真实道路，然后回存订单，后续直接复用
  try {
    const planned = await planRoute(o.origin, o.dest)
    points.value = planned
    await saveOrderRoute(o.order_no, planned)
  } catch (e) {
    points.value = [o.origin, o.dest]
    error.value = '路径规划不可用，已用直线路径示意'
  }
  return true
}

onMounted(async () => {
  const o = await loadOrder(true)
  if (!o) return
  if (o.status === 'pending') {
    error.value = '商家还未接单，接单后即可查看配送轨迹'
  }

  if (!hasAMapKey()) {
    fallback.value = true
    error.value = error.value || '未配置高德 Key（frontend/.env 的 VITE_AMAP_KEY），当前为示意底图'
  }

  const ok = await ensureRoute()
  if (!ok) return

  if (!fallback.value) {
    try {
      await initMap()
    } catch (e) {
      fallback.value = true
      error.value = e.message || '高德地图加载失败，已切换为示意底图'
    }
  }

  renderFrame(displayProgress.value)
  rafId = requestAnimationFrame(animate)
  // 每 20 秒与后端对齐一次真实进度，中间自行推进
  syncTimer = setInterval(() => {
    localAdvance()
    if (!debugMode.value) loadOrder().catch(() => {})
  }, 20000)
  const tick = setInterval(localAdvance, 1000)
  onBeforeUnmount(() => clearInterval(tick))
})

onBeforeUnmount(() => {
  if (rafId) cancelAnimationFrame(rafId)
  if (syncTimer) clearInterval(syncTimer)
  if (map) map.destroy()
})
</script>

<style scoped>
.track-page { max-width: 900px; margin: 0 auto; padding: 16px 16px 40px; }
.track-head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.order-no { font-weight: 700; color: var(--text); }
.status { font-size: 12.5px; padding: 2px 10px; border-radius: 999px; background: var(--surface-2); color: var(--text-muted); }
.status.shipping { background: #fff4e6; color: #fa6400; }
.status.delivered { background: #e8f8ee; color: #0f9d58; }
.track-error { margin-bottom: 12px; }

.map-wrap {
  position: relative; height: 460px; border-radius: 16px; overflow: hidden;
  border: 1px solid var(--border); box-shadow: var(--card-shadow);
}
.map { width: 100%; height: 100%; }
.fallback { position: absolute; inset: 0; width: 100%; height: 100%; }

/* 起终点标记 */
:global(.pin) {
  width: 26px; height: 26px; border-radius: 50%; color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
}
:global(.pin-start) { background: #4f7cff; }
:global(.pin-end) { background: #ff4d18; }

.info-card {
  position: absolute; left: 16px; right: 16px; bottom: 16px;
  background: var(--surface); border-radius: 14px; padding: 14px 16px;
  box-shadow: 0 8px 28px rgba(31, 45, 92, 0.18);
  display: flex; align-items: center; gap: 16px;
}
.info-main { flex: 1; min-width: 0; }
.info-title { display: flex; align-items: center; gap: 8px; font-weight: 700; color: var(--text); font-size: 15px; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #ff6a00; box-shadow: 0 0 0 4px rgba(255, 106, 0, 0.18); }
.info-eta { margin-top: 6px; color: var(--text-sub); font-size: 13.5px; }
.info-eta b { color: #ff4d18; font-size: 18px; margin: 0 2px; }
.info-addr {
  margin-top: 4px; color: var(--text-muted); font-size: 12px;
  display: flex; gap: 6px; align-items: center; overflow: hidden;
}
.info-addr .to { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.arrow { color: #ff8f1f; }

.rider { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.rider-avatar {
  width: 40px; height: 40px; border-radius: 50%;
  background: linear-gradient(135deg, #ff8f1f, #ff4d18); color: #fff;
  display: flex; align-items: center; justify-content: center; font-weight: 700;
}
.rider-name { font-size: 13.5px; color: var(--text); font-weight: 600; }
.rider-phone { font-size: 12px; color: var(--text-muted); }

.debug-bar {
  position: absolute; right: 16px; top: 16px;
  display: flex; align-items: center; gap: 10px;
  background: var(--surface); border-radius: 10px; padding: 6px 10px;
  box-shadow: var(--card-shadow);
}
.debug-bar.open { left: 16px; }
.debug-label { font-size: 12px; color: var(--text-muted); white-space: nowrap; }
.debug-slider { flex: 1; min-width: 120px; }

.goods { margin-top: 16px; background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 8px 16px 14px; }
.goods-row { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border); }
.g-title { flex: 1; min-width: 0; font-size: 13.5px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.g-qty { color: var(--text-muted); font-size: 13px; }
.g-price { color: var(--price); font-weight: 700; }
.goods-total { text-align: right; padding-top: 12px; color: var(--text-sub); font-size: 13.5px; }
.goods-total b { color: #ff4d18; font-size: 19px; margin-left: 6px; }
</style>
