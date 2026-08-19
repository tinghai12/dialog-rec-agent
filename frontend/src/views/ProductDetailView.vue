<template>
  <div class="detail-page" v-if="product">
    <el-button text type="primary" @click="$router.back()">← 返回</el-button>

    <el-card shadow="never" class="main-card">
      <div class="head">
        <div class="head-l">
          <span class="brand-avatar" style="width:52px;height:52px;font-size:22px;border-radius:14px;">{{ product.brand[0] }}</span>
          <div>
            <h2>{{ product.title }}</h2>
            <div class="meta">
              <el-tag size="small" type="primary" effect="plain">{{ product.brand }}</el-tag>
              <el-tag size="small" effect="plain">{{ product.category }}</el-tag>
            </div>
          </div>
        </div>
        <div class="price">¥{{ product.price.toLocaleString() }}</div>
      </div>
      <div class="actions">
        <el-button type="primary" :disabled="!isLoggedIn()" @click="addCart">加入购物车</el-button>
        <el-button :type="product.is_favorite ? 'warning' : 'default'" :disabled="!isLoggedIn()" @click="toggleFav">
          {{ product.is_favorite ? '已收藏 ♥' : '收藏' }}
        </el-button>
        <span v-if="!isLoggedIn()" class="login-tip">登录后可收藏/加购</span>
      </div>
    </el-card>

    <el-card shadow="never" class="sec">
      <template #header><b>详细参数</b></template>
      <el-descriptions :column="2" border>
        <el-descriptions-item v-for="(v, k) in product.attributes" :key="k" :label="k">{{ v }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card shadow="never" class="sec">
      <template #header><b>优点 / 缺点</b></template>
      <div class="pros">
        <div v-for="p in product.pros" :key="p" class="pro">＋ {{ p }}</div>
      </div>
      <div class="cons">
        <div v-for="c in product.cons" :key="c" class="con">－ {{ c }}</div>
      </div>
    </el-card>

    <el-card shadow="never" class="sec" v-if="product.reviews && product.reviews.length">
      <template #header><b>用户评价</b></template>
      <div v-for="(r, i) in product.reviews" :key="i" class="review">
        <span class="review-q">"{{ r }}"</span>
      </div>
    </el-card>

    <el-card shadow="never" class="sec" v-if="product.similar && product.similar.length">
      <template #header><b>看了这个还看这个（内容相似推荐）</b></template>
      <div class="similar">
        <el-card v-for="s in product.similar" :key="s.id" shadow="hover" class="s-card" @click="$router.push(`/products/${s.id}`)">
          <div class="s-title">{{ s.title }}</div>
          <div class="s-price">¥{{ s.price.toLocaleString() }}</div>
        </el-card>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getProductDetail, addToCart, addFavorite, removeFavorite, isLoggedIn } from '../api'

const route = useRoute()
const product = ref(null)

async function load() {
  const { data } = await getProductDetail(route.params.id)
  if (data?.code === 0) product.value = data.data
}

async function addCart() {
  await addToCart(product.value.id)
  ElMessage.success('已加入购物车')
  window.dispatchEvent(new CustomEvent('cart-changed'))
}

async function toggleFav() {
  try {
    if (product.value.is_favorite) {
      await removeFavorite(product.value.id)
      product.value.is_favorite = false
      ElMessage.success('已取消收藏')
    } else {
      await addFavorite(product.value.id)
      product.value.is_favorite = true
      ElMessage.success('已收藏')
    }
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

onMounted(load)
</script>

<style scoped>
.detail-page { max-width: 920px; margin: 0 auto; padding: 20px; }
.main-card { margin-bottom: 16px; border-radius: var(--card-radius); border: none; box-shadow: var(--card-shadow); }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.head-l { display: flex; gap: 14px; align-items: flex-start; }
.head h2 { margin: 0 0 10px; font-size: 20px; color: #2a3050; }
.meta { display: flex; gap: 6px; }
.price { color: var(--price); font-size: 30px; font-weight: 800; white-space: nowrap; }
.actions { margin-top: 18px; display: flex; align-items: center; gap: 10px; }
.actions .el-button--primary { background: var(--primary-grad); border: none; box-shadow: 0 6px 16px rgba(79,124,255,0.3); }
.login-tip { color: #a6aecb; font-size: 12px; }
.sec { margin-bottom: 16px; border-radius: var(--card-radius); border: none; box-shadow: var(--card-shadow); }
:deep(.sec .el-card__header) { font-weight: 700; color: #2a3050; }
.pro { color: #2e9e5b; margin: 5px 0; font-size: 14px; }
.con { color: #d4380d; margin: 5px 0; font-size: 14px; }
.review {
  border-left: 3px solid rgba(79,124,255,0.35); background: #f8f9fd;
  padding: 10px 14px; margin: 10px 0; color: #4a5175; border-radius: 0 8px 8px 0; font-size: 14px;
}
.similar { display: flex; gap: 12px; flex-wrap: wrap; }
.s-card { width: 240px; cursor: pointer; border-radius: 12px; transition: transform 0.2s ease, box-shadow 0.2s ease; }
.s-card:hover { transform: translateY(-3px); box-shadow: var(--card-shadow-hover); }
.s-title { font-size: 13px; margin-bottom: 6px; color: #2a3050; }
.s-price { color: var(--price); font-weight: 700; }
</style>
