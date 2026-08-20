<template>
  <div class="order-card" :class="{ merchant: role === 'merchant' }">
    <div class="oc-head">
      <span class="oc-no">{{ order.order_no }}</span>
      <span class="oc-status" :class="order.status">{{ order.status_text }}</span>
    </div>

    <div class="oc-goods">
      <ProductThumb :product="order.products[0] || {}" :size="46" />
      <div class="oc-goods-main">
        <div class="oc-title">{{ order.products[0]?.title || '商品' }}</div>
        <div class="oc-sub">
          <span v-if="order.products.length > 1">等 {{ order.products.length }} 件</span>
          <span class="oc-shop">{{ role === 'merchant' ? order.receiver : order.shop_name }}</span>
        </div>
      </div>
      <span class="oc-amount">¥{{ Number(order.total_amount).toLocaleString() }}</span>
    </div>

    <!-- 配送进度（已接单才有） -->
    <div v-if="order.status === 'shipping'" class="oc-ship">
      <div class="oc-bar"><div class="oc-fill" :style="{ width: (order.progress * 100).toFixed(1) + '%' }"></div></div>
      <span class="oc-ship-text">{{ order.rider_name }} · 还有 {{ order.remain_minutes }} 分钟</span>
    </div>

    <!-- 售后状态 -->
    <div v-if="order.aftersale_status !== 'none'" class="oc-aftersale" :class="order.aftersale_status">
      {{ order.aftersale_type_text }}：{{ order.aftersale_status_text }}
      <span v-if="order.aftersale_reply" class="oc-reply">（{{ order.aftersale_reply }}）</span>
      <div v-if="order.aftersale_reason" class="oc-reason">买家：{{ order.aftersale_reason }}</div>
    </div>

    <!-- 商家：选仓 + 推荐 -->
    <div v-if="role === 'merchant' && order.status === 'pending' && order.warehouses?.length" class="oc-wh">
      <div class="oc-wh-title">选择发货仓</div>
      <label v-for="w in order.warehouses" :key="w.id" class="oc-wh-row"
             :class="{ picked: pickedWarehouse === w.id, disabled: !w.enough }">
        <input type="radio" :value="w.id" :checked="pickedWarehouse === w.id"
               :disabled="!w.enough" @change="pickedWarehouse = w.id" />
        <span class="wh-name">
          {{ w.name }}
          <em v-if="w.recommended" class="wh-best">推荐</em>
        </span>
        <span class="wh-dist">{{ w.distance_km != null ? w.distance_km + 'km' : '—' }}</span>
        <span class="wh-stock" :class="{ lack: !w.enough }">
          <span v-for="i in w.items" :key="i.product_id" class="wh-item">
            {{ i.title.slice(0, 8) }} 需{{ i.need }}/存{{ i.stock }}
          </span>
        </span>
      </label>
      <div v-if="order.recommendation" class="oc-reco">{{ order.recommendation }}</div>
    </div>

    <!-- 操作按钮 -->
    <div class="oc-ops">
      <template v-if="role === 'merchant'">
        <template v-if="order.status === 'pending'">
          <el-button size="small" type="primary" :loading="busy" @click="emit('accept', order, pickedWarehouse)">
            接单发货
          </el-button>
          <el-button size="small" :loading="busy" @click="emit('reject', order)">拒单</el-button>
        </template>
        <template v-if="order.aftersale_status === 'pending'">
          <el-button size="small" type="primary" :loading="busy" @click="emit('aftersale', order, true)">同意售后</el-button>
          <el-button size="small" :loading="busy" @click="emit('aftersale', order, false)">拒绝售后</el-button>
        </template>
      </template>
      <template v-else>
        <el-button v-if="order.status === 'shipping' || order.status === 'delivered'"
                   size="small" type="primary" plain @click="emit('track', order)">
          查看轨迹
        </el-button>
        <el-button v-if="canAftersale" size="small" plain @click="emit('aftersale', order)">申请售后</el-button>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import ProductThumb from './ProductThumb.vue'

const props = defineProps({
  order: { type: Object, required: true },
  role: { type: String, default: 'buyer' },   // buyer | merchant
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['accept', 'reject', 'track', 'aftersale'])

// 默认选中推荐仓
const pickedWarehouse = ref(props.order.recommended_id ?? null)
watch(() => props.order.recommended_id, (v) => { pickedWarehouse.value = v })

const canAftersale = computed(() =>
  ['shipping', 'delivered'].includes(props.order.status) &&
  ['none', 'rejected'].includes(props.order.aftersale_status)
)
</script>

<style scoped>
.order-card {
  width: 300px; flex-shrink: 0;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px; padding: 12px;
  display: flex; flex-direction: column; gap: 9px;
  box-shadow: var(--card-shadow);
}
.order-card.merchant { width: 360px; }

.oc-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.oc-no { font-size: 12px; color: var(--text-muted); font-family: ui-monospace, monospace; }
.oc-status { font-size: 11.5px; padding: 2px 8px; border-radius: 999px; background: var(--surface-2); color: var(--text-muted); white-space: nowrap; }
.oc-status.shipping { background: #fff4e6; color: #fa6400; }
.oc-status.delivered { background: #e8f8ee; color: #0f9d58; }
.oc-status.cancelled { background: #fff1f0; color: #e4393c; }

.oc-goods { display: flex; align-items: center; gap: 10px; }
.oc-goods-main { flex: 1; min-width: 0; }
.oc-title {
  font-size: 13px; color: var(--text); line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden;
}
.oc-sub { display: flex; gap: 8px; margin-top: 3px; font-size: 11.5px; color: var(--text-muted); }
.oc-shop { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.oc-amount { color: #ff4d18; font-weight: 800; font-size: 15px; white-space: nowrap; }

.oc-ship { display: flex; align-items: center; gap: 8px; }
.oc-bar { flex: 1; height: 5px; border-radius: 3px; background: var(--surface-2); overflow: hidden; }
.oc-fill { height: 100%; background: linear-gradient(90deg, #ff8f1f, #ff4d18); transition: width 0.6s ease; }
.oc-ship-text { font-size: 11.5px; color: var(--text-muted); white-space: nowrap; }

.oc-aftersale { font-size: 12px; padding: 6px 8px; border-radius: 8px; background: var(--surface-2); color: var(--text-sub); }
.oc-aftersale.pending { background: #fff4e6; color: #fa6400; }
.oc-aftersale.approved { background: #e8f8ee; color: #0f9d58; }
.oc-aftersale.rejected { background: #fff1f0; color: #e4393c; }
.oc-reply { opacity: 0.85; }
.oc-reason { margin-top: 3px; color: var(--text-muted); font-size: 11.5px; }

/* 选仓 */
.oc-wh { border-top: 1px dashed var(--border); padding-top: 8px; }
.oc-wh-title { font-size: 12px; color: var(--text-muted); margin-bottom: 6px; }
.oc-wh-row {
  display: flex; align-items: flex-start; gap: 7px; padding: 6px;
  border-radius: 8px; cursor: pointer; font-size: 12px;
  border: 1px solid transparent; flex-wrap: wrap;
}
.oc-wh-row:hover { background: var(--surface-2); }
.oc-wh-row.picked { border-color: var(--primary); background: rgba(79, 124, 255, 0.06); }
.oc-wh-row.disabled { opacity: 0.55; cursor: not-allowed; }
.wh-name { flex: 1; min-width: 0; color: var(--text); }
.wh-best { font-style: normal; color: #fa6400; font-size: 10.5px; margin-left: 4px; }
.wh-dist { color: var(--text-sub); white-space: nowrap; }
.wh-stock { width: 100%; display: flex; flex-wrap: wrap; gap: 6px; color: var(--text-muted); font-size: 11px; margin-top: 2px; }
.wh-stock.lack { color: #e4393c; }
.oc-reco { margin-top: 6px; font-size: 11.5px; color: #fa6400; }

.oc-ops { display: flex; gap: 8px; flex-wrap: wrap; }
</style>
