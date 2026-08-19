<template>
  <!-- 商家上传了主图就用图；否则用品牌 + 底色生成迷你海报，保证任何商品都有视觉锚点 -->
  <div class="thumb" :class="'bg-' + (product.poster_bg || fallbackBg)" :style="{ width: size + 'px', height: size + 'px' }">
    <img v-if="product.main_image" :src="product.main_image" :alt="product.title" />
    <template v-else>
      <span class="t-brand">{{ product.brand }}</span>
      <span v-if="product.poster_headline && size >= 88" class="t-headline">{{ product.poster_headline }}</span>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  product: { type: Object, required: true },
  size: { type: Number, default: 88 },
})

const BGS = ['dark', 'blue', 'purple', 'red', 'green', 'ink']
// 没配底色时按 id 稳定取一个，避免同屏一片同色
const fallbackBg = computed(() => BGS[(Number(props.product.id) || 0) % BGS.length])
</script>

<style scoped>
.thumb {
  position: relative; flex-shrink: 0; overflow: hidden;
  border-radius: 10px; color: #fff;
  display: flex; flex-direction: column; justify-content: center; align-items: center;
  gap: 4px; padding: 6px; text-align: center;
}
.thumb img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.t-brand { font-size: 12px; font-weight: 800; letter-spacing: 0.5px; }
.t-headline { font-size: 10px; opacity: 0.85; line-height: 1.3; }

.bg-dark   { background: linear-gradient(150deg, #1b1b22 0%, #3a3a46 100%); }
.bg-blue   { background: linear-gradient(150deg, #072a6b 0%, #1e63d6 100%); }
.bg-purple { background: linear-gradient(150deg, #2a1b52 0%, #7048c8 100%); }
.bg-red    { background: linear-gradient(150deg, #6b0f1a 0%, #d63a2f 100%); }
.bg-green  { background: linear-gradient(150deg, #0b4a35 0%, #17a06a 100%); }
.bg-ink    { background: linear-gradient(150deg, #101a2b 0%, #2f5680 100%); }
</style>
