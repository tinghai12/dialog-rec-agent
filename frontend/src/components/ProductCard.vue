<template>
  <div class="p-card" @click="$emit('click')">
    <!-- A. 主图区：商家上传的海报图；没有则用 CSS 生成营销海报兜底 -->
    <div class="poster" :class="'bg-' + (product.poster_bg || 'dark')">
      <img v-if="product.main_image" :src="product.main_image" :alt="product.title" class="poster-img" />
      <template v-else>
        <div class="poster-brand">{{ product.brand }}</div>
        <div class="poster-headline">{{ product.poster_headline || product.title }}</div>
        <div v-if="product.poster_subline" class="poster-subline">{{ product.poster_subline }}</div>
        <div v-if="specs.length" class="poster-specs">
          <span v-for="s in specs" :key="s" class="spec-chip">{{ s }}</span>
        </div>
      </template>
      <!-- 价格浮层：真实图与兜底海报都叠加 -->
      <div v-if="product.poster_price_label" class="poster-price">
        <span class="pp-label">{{ product.poster_price_label }}</span>
        <span class="pp-value">¥{{ formatPrice(finalPrice) }}<span class="pp-suffix">起</span></span>
      </div>
    </div>

    <!-- B. 促销条 -->
    <div v-if="product.promo_banner" class="promo-bar" :class="'style-' + (product.promo_banner_style || 'none')">
      {{ product.promo_banner }}
    </div>

    <div class="card-body">
      <!-- C. 标题（含商家设置的优惠前缀） -->
      <div class="title">
        <span v-if="product.title_prefix" class="title-prefix">{{ product.title_prefix }}</span>{{ product.title }}
      </div>

      <!-- 榜单标签 / 关键规格 -->
      <div v-if="product.rank_label" class="rank-label">{{ product.rank_label }}</div>
      <div v-else class="spec-line">{{ specLine }}</div>

      <!-- D. 价格与购买数据 -->
      <div class="price-row">
        <span class="price">¥{{ formatPrice(finalPrice) }}</span>
        <span v-if="product.sold_count" class="sold">{{ formatCount(product.sold_count) }}+人付款</span>
      </div>

      <div class="promo-row">
        <span v-if="product.saved_amount > 0" class="saved">已补{{ Math.round(product.saved_amount) }}元</span>
        <span v-if="product.installment" class="tag-plain">{{ product.installment }}</span>
        <span v-for="t in serviceTags" :key="t" class="tag-plain">{{ t }}</span>
      </div>

      <div class="shop-row">
        <span v-if="product.repeat_buyers" class="repeat">回头客{{ formatCount(product.repeat_buyers) }}</span>
        <span class="shop-name">{{ product.shop_name || product.brand }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  product: { type: Object, required: true },
})
defineEmits(['click'])

const finalPrice = computed(() => props.product.final_price ?? props.product.price)

const specs = computed(() => (props.product.poster_specs || []).slice(0, 2))

const serviceTags = computed(() => (props.product.service_tags || []).slice(0, 2))

// 无榜单标签时，退化展示关键规格（内存/硬盘/屏幕）
const specLine = computed(() => {
  const a = props.product.attributes || {}
  return ['内存', '硬盘', '屏幕'].map((k) => a[k]).filter(Boolean).slice(0, 3).join('  ')
})

function formatPrice(v) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatCount(n) {
  return n >= 10000 ? (n / 10000).toFixed(n % 10000 === 0 ? 0 : 1) + '万' : n
}
</script>

<style scoped>
.p-card {
  background: var(--surface);
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  border: 1px solid var(--border);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  display: flex;
  flex-direction: column;
}
.p-card:hover { transform: translateY(-4px); box-shadow: var(--card-shadow-hover); }

/* ===== A. 海报主图 ===== */
.poster {
  position: relative;
  aspect-ratio: 1 / 1;
  padding: 14px 12px;
  color: #fff;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.poster-img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.bg-dark   { background: linear-gradient(150deg, #1b1b22 0%, #3a3a46 100%); }
.bg-blue   { background: linear-gradient(150deg, #072a6b 0%, #1e63d6 100%); }
.bg-purple { background: linear-gradient(150deg, #2a1b52 0%, #7048c8 100%); }
.bg-red    { background: linear-gradient(150deg, #6b0f1a 0%, #d63a2f 100%); }
.bg-green  { background: linear-gradient(150deg, #0b4a35 0%, #17a06a 100%); }
.bg-ink    { background: linear-gradient(150deg, #101a2b 0%, #2f5680 100%); }

.poster-brand {
  font-size: 12px; font-weight: 800; letter-spacing: 1px;
  opacity: 0.9; text-transform: uppercase;
}
.poster-headline {
  margin-top: 10px; font-size: 17px; font-weight: 800; line-height: 1.3;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
}
.poster-subline { margin-top: 5px; font-size: 11.5px; opacity: 0.8; line-height: 1.4; }
.poster-specs { margin-top: auto; display: flex; flex-wrap: wrap; gap: 5px; }
.spec-chip {
  background: rgba(0, 0, 0, 0.42);
  border: 1px solid rgba(255, 255, 255, 0.28);
  padding: 3px 7px; border-radius: 4px;
  font-size: 10.5px; font-weight: 600;
  backdrop-filter: blur(2px);
}
/* 价格浮层：右下角，红黄配色贴合大促观感 */
.poster-price {
  position: absolute; right: 0; bottom: 0;
  background: linear-gradient(105deg, #ff3b30, #ff6a00);
  padding: 5px 10px 6px; border-top-left-radius: 10px;
  display: flex; flex-direction: column; align-items: flex-end;
  box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.25);
}
.pp-label { font-size: 9.5px; opacity: 0.95; }
.pp-value { font-size: 17px; font-weight: 800; color: #ffe66b; line-height: 1.1; }
.pp-suffix { font-size: 10px; margin-left: 1px; }

/* ===== B. 促销条 ===== */
.promo-bar {
  padding: 4px 10px; font-size: 11.5px; font-weight: 700;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.style-tmall   { background: #fff1f0; color: #e4393c; }
.style-subsidy { background: #e8f8ee; color: #0f9d58; }
.style-live    { background: #fff4e6; color: #fa6400; }
.style-none    { display: none; }
/* 暗色下促销条底色压暗，保证文字对比度 */
[data-theme='dark'] .style-tmall   { background: rgba(228, 57, 60, 0.16); color: #ff8a8c; }
[data-theme='dark'] .style-subsidy { background: rgba(15, 157, 88, 0.16); color: #56d195; }
[data-theme='dark'] .style-live    { background: rgba(250, 100, 0, 0.16); color: #ffa257; }

/* ===== C/D. 文本区 ===== */
.card-body { padding: 9px 10px 11px; display: flex; flex-direction: column; gap: 5px; }
.title {
  font-size: 13px; line-height: 1.45; color: var(--text);
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden;
  min-height: 37px;
}
.title-prefix { color: #e4393c; font-weight: 700; }
.rank-label, .spec-line {
  font-size: 11.5px; color: #ff8f1f;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.spec-line { color: var(--text-muted); }

.price-row { display: flex; align-items: baseline; gap: 7px; flex-wrap: wrap; }
.price { color: #ff4d18; font-size: 19px; font-weight: 800; }
.sold { color: var(--text-muted); font-size: 11.5px; }

.promo-row { display: flex; gap: 7px; flex-wrap: wrap; font-size: 11.5px; }
.saved { color: #e4393c; }
.tag-plain { color: #ff8f1f; }

.shop-row {
  display: flex; gap: 7px; align-items: center;
  font-size: 11.5px; color: var(--text-muted); overflow: hidden;
}
.repeat { color: #ff8f1f; flex-shrink: 0; }
.shop-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
