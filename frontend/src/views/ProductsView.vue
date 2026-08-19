<template>
  <div class="products-page">
    <div class="hero">
      <h2>想买什么，直接说</h2>
      <p>试试「7000以内写代码笔记本 32G内存」或「三千左右拍照好的手机」</p>
      <div class="search-bar">
        <el-input
          v-model="query"
          placeholder="用自然语言描述你的需求…"
          size="large"
          clearable
          @keyup.enter="doSearch"
        >
          <template #append>
            <el-button type="primary" :loading="loading" @click="doSearch">搜索</el-button>
          </template>
        </el-input>
      </div>
    </div>

    <div class="filters">
      <el-radio-group v-model="category" @change="doSearch">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="笔记本">笔记本</el-radio-button>
        <el-radio-button value="手机">手机</el-radio-button>
      </el-radio-group>
      <span class="count" v-if="results.length">{{ results.length }} 款</span>
      <el-button text type="primary" @click="loadAll">浏览全部</el-button>
    </div>

    <div v-if="results.length" class="grid">
      <ProductCard
        v-for="p in results"
        :key="p.id"
        :product="p"
        @click="goDetail(p.id)"
      />
    </div>
    <el-empty v-else description="没有结果，换个说法试试" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { searchProducts, listProducts } from '../api'
import ProductCard from '../components/ProductCard.vue'

const router = useRouter()
const query = ref('')
const category = ref('')
const results = ref([])
const loading = ref(false)

function goDetail(id) {
  router.push('/products/' + id)
}

async function doSearch() {
  loading.value = true
  try {
    if (!query.value.trim()) {
      return loadAll()
    }
    const { data } = await searchProducts(query.value.trim(), category.value || null)
    results.value = data?.data?.results || []
  } catch (e) {
    results.value = []
  } finally {
    loading.value = false
  }
}

async function loadAll() {
  loading.value = true
  try {
    const { data } = await listProducts()
    const all = data?.data || []
    results.value = category.value ? all.filter((p) => p.category === category.value) : all
  } catch (e) {
    results.value = []
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.products-page { max-width: 1560px; margin: 0 auto; padding: 26px 20px 40px; }
.hero { text-align: center; padding: 26px 0 18px; }
.hero h2 { margin: 0 0 6px; color: var(--text); font-size: 26px; }
.hero p { color: var(--text-muted); margin: 0 0 18px; font-size: 13.5px; }
.search-bar { max-width: 620px; margin: 0 auto; }
:deep(.search-bar .el-input-group__append) { background: var(--primary-grad); border: none; box-shadow: none; }
:deep(.search-bar .el-input__wrapper) { border-radius: 12px 0 0 12px; padding: 6px 16px; }
:deep(.search-bar .el-button) { color: #fff; font-weight: 600; }
.filters { display: flex; align-items: center; gap: 16px; margin: 22px 2px 18px; }
.count { color: var(--text-muted); font-size: 13px; }

/* 一行六列；窄屏逐级降列 */
.grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 14px; }
@media (max-width: 1400px) { .grid { grid-template-columns: repeat(5, 1fr); } }
@media (max-width: 1160px) { .grid { grid-template-columns: repeat(4, 1fr); } }
@media (max-width: 900px)  { .grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 640px)  { .grid { grid-template-columns: repeat(2, 1fr); } }
</style>
