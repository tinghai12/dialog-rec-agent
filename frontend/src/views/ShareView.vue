<template>
  <div class="share-page">
    <div class="share-card">
      <div class="share-head">
        <span class="share-logo">语</span>
        <div>
          <h2>{{ title }}</h2>
          <p class="share-sub">来自「自然语言电商」的对话记录 · 只读分享</p>
        </div>
      </div>

      <div v-if="loading" class="share-empty">加载中…</div>
      <div v-else-if="!messages.length" class="share-empty">该对话不存在或已被删除</div>

      <div v-else class="share-body">
        <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role">
          <div class="msg-bubble" v-if="m.content">{{ m.content }}</div>
          <div v-if="m.cards && m.cards.length" class="cards">
            <div v-for="c in m.cards" :key="c.id" class="product-card">
              <ProductThumb :product="c" :size="88" />
              <div class="card-main">
                <div class="card-head">
                  <span class="card-title">{{ c.title }}</span>
                  <span class="card-price">¥{{ Number(c.final_price ?? c.price).toLocaleString() }}</span>
                </div>
                <div class="card-reason" v-if="c.reason">推荐理由：{{ c.reason }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="share-foot">
        <el-button type="primary" @click="$router.push('/')">我也要聊一个</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import ProductThumb from '../components/ProductThumb.vue'
import { getSessionMessages } from '../api'

const route = useRoute()
const messages = ref([])
const title = ref('对话记录')
const loading = ref(true)

onMounted(async () => {
  try {
    const { data } = await getSessionMessages(route.params.key)
    messages.value = (data?.data?.messages || []).map((m) => ({
      role: m.role, content: m.content, cards: m.cards || [],
    }))
    title.value = data?.data?.title || '对话记录'
  } catch (e) {
    messages.value = []
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.share-page { min-height: calc(100vh - 60px); padding: 30px 20px 50px; background: var(--bg); }
.share-card {
  max-width: 820px; margin: 0 auto; background: var(--surface);
  border: 1px solid var(--border); border-radius: 16px; box-shadow: var(--card-shadow);
  overflow: hidden;
}
.share-head {
  display: flex; align-items: center; gap: 14px;
  padding: 20px 24px; border-bottom: 1px solid var(--border);
}
.share-logo {
  display: inline-flex; align-items: center; justify-content: center;
  width: 42px; height: 42px; border-radius: 12px; flex-shrink: 0;
  background: var(--primary-grad); color: #fff; font-size: 20px; font-weight: 800;
}
.share-head h2 { margin: 0; font-size: 18px; color: var(--text); }
.share-sub { margin: 3px 0 0; color: var(--text-muted); font-size: 12.5px; }
.share-empty { padding: 60px; text-align: center; color: var(--text-muted); }
.share-body { padding: 18px 24px; }
.share-foot { padding: 16px 24px 22px; text-align: center; border-top: 1px solid var(--border); }

.msg-row { margin: 12px 0; }
.msg-row.user { text-align: right; }
.msg-bubble {
  display: inline-block; max-width: 72%;
  padding: 10px 15px; white-space: pre-wrap; text-align: left;
  border-radius: 14px; font-size: 14px; line-height: 1.55;
}
.msg-row.user .msg-bubble { background: var(--primary-grad); color: #fff; border-bottom-right-radius: 4px; }
.msg-row.assistant .msg-bubble {
  background: var(--surface-2); color: var(--text);
  border: 1px solid var(--border); border-bottom-left-radius: 4px;
}
.cards { display: flex; flex-direction: column; gap: 10px; margin-top: 10px; max-width: 620px; }
.product-card {
  display: flex; gap: 12px; padding: 12px;
  background: var(--surface-2); border-radius: 12px; border: 1px solid var(--border);
}
.card-main { flex: 1; min-width: 0; }
.card-head { display: flex; justify-content: space-between; gap: 10px; }
.card-title { font-weight: 600; font-size: 14px; color: var(--text); }
.card-price { color: var(--price); font-weight: 800; font-size: 16px; white-space: nowrap; }
.card-reason { color: var(--text-sub); margin-top: 6px; font-size: 13px; line-height: 1.5; }
</style>
