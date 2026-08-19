<template>
  <div class="fav-page">
    <h2>我的收藏</h2>
    <div v-if="items.length" class="grid">
      <el-card v-for="p in items" :key="p.id" shadow="hover" class="f-card" @click="$router.push(`/products/${p.id}`)">
        <div class="f-head">
          <span class="f-title">{{ p.title }}</span>
          <span class="f-price">¥{{ p.price.toLocaleString() }}</span>
        </div>
        <div class="f-tags">
          <el-tag size="small" type="primary" effect="plain">{{ p.brand }}</el-tag>
          <el-tag size="small" effect="plain">{{ p.category }}</el-tag>
        </div>
        <div class="f-actions">
          <el-button size="small" type="danger" text @click.stop="removeFav(p)">取消收藏</el-button>
        </div>
      </el-card>
    </div>
    <el-empty v-else description="还没有收藏，去逛商品或对话里说「收藏这个」" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getFavorites, removeFavorite } from '../api'

const items = ref([])

async function load() {
  const { data } = await getFavorites()
  items.value = data?.data?.favorites || []
}

async function removeFav(p) {
  await removeFavorite(p.id)
  ElMessage.success('已取消收藏')
  load()
}

onMounted(load)
</script>

<style scoped>
.fav-page { max-width: 1000px; margin: 0 auto; padding: 26px 20px 40px; }
.fav-page h2 { color: #2a3050; margin: 0 0 18px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
.f-card { cursor: pointer; border-radius: var(--card-radius); border: 1px solid rgba(31,45,92,0.06); box-shadow: var(--card-shadow); transition: transform .2s ease, box-shadow .2s ease; }
.f-card:hover { transform: translateY(-4px); box-shadow: var(--card-shadow-hover); }
.f-head { display: flex; justify-content: space-between; gap: 10px; align-items: center; }
.f-title { font-weight: 600; font-size: 14px; }
.f-price { color: var(--price); font-weight: 800; font-size: 16px; white-space: nowrap; }
.f-tags { display: flex; gap: 6px; margin: 8px 0; }
.f-actions { text-align: right; }
</style>
