<template>
  <div class="chat-layout">
    <!-- 左侧历史边栏 -->
    <aside class="sidebar">
      <el-button type="primary" class="new-btn" @click="newChat">+ 新建对话</el-button>

      <div class="session-list">
        <div
          v-for="s in sessions"
          :key="s.session_id"
          class="session-item"
          :class="{ active: s.session_id === sessionId }"
          @click="switchChat(s.session_id)"
        >
          <div class="session-body">
            <div class="session-title">
              <svg v-if="s.pinned" class="pin-icon" viewBox="0 0 24 24" width="11" height="11">
                <path fill="currentColor" d="M16 3v2l-2 2v5l3 3v2h-4.5v5h-1v-5H7v-2l3-3V7L8 5V3z" />
              </svg>
              {{ s.title }}
            </div>
            <div class="session-meta">{{ s.updated_at }} · {{ s.msg_count }}条</div>
          </div>

          <!-- 会话操作菜单 -->
          <el-dropdown trigger="click" placement="bottom-end" @command="(cmd) => onCommand(cmd, s)">
            <span class="session-more" @click.stop>⋮</span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="share">分享对话</el-dropdown-item>
                <el-dropdown-item command="pin">{{ s.pinned ? '取消置顶' : '置顶对话' }}</el-dropdown-item>
                <el-dropdown-item command="rename">重命名</el-dropdown-item>
                <el-dropdown-item command="delete" divided>删除对话</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <div v-if="!sessions.length" class="sidebar-empty">还没有历史对话</div>
      </div>

      <!-- 左下角主题切换 -->
      <div class="theme-bar" @click="toggleTheme">
        <span class="theme-icon">
          <svg v-if="theme === 'dark'" viewBox="0 0 24 24" width="15" height="15">
            <path fill="currentColor" d="M12 7a5 5 0 100 10 5 5 0 000-10zm0-5v2m0 16v2M4.2 4.2l1.4 1.4m12.8 12.8l1.4 1.4M2 12h2m16 0h2M4.2 19.8l1.4-1.4M17 5.6l1.4-1.4"
                  stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
          </svg>
          <svg v-else viewBox="0 0 24 24" width="15" height="15">
            <path fill="currentColor" d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z" />
          </svg>
        </span>
        {{ theme === 'dark' ? '明亮模式' : '黑暗模式' }}
      </div>
    </aside>

    <!-- 主聊天区 -->
    <div class="chat-main">
      <div class="chat-header">
        <span class="title">对话式推荐智能体</span>
        <span class="subtitle">说出你的需求，我来帮你找</span>
      </div>

      <!-- 初始态：欢迎语 + 居中输入框 + 示例 -->
      <div v-if="!messages.length" class="welcome-stage">
        <h1 class="welcome-title">你好，{{ displayName }}</h1>
        <p class="welcome-sub">想买点什么？描述你的需求，我来帮你挑</p>

        <div class="welcome-input">
          <el-input
            v-model="input"
            size="large"
            placeholder="描述你的需求，例如：想买个写代码的笔记本，七千左右"
            :disabled="loading"
            @keyup.enter="send"
          >
            <template #append>
              <el-button type="primary" :loading="loading" @click="send">发送</el-button>
            </template>
          </el-input>
        </div>

        <div class="examples">
          <span v-for="e in EXAMPLES" :key="e" class="example-chip" @click="useExample(e)">{{ e }}</span>
        </div>
      </div>

      <!-- 对话态 -->
      <template v-else>
        <div class="chat-body" ref="bodyRef">
          <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role">
            <div class="msg-bubble" v-if="m.content">{{ m.content }}</div>

            <div v-if="m.cards && m.cards.length" class="cards">
              <div v-for="c in m.cards" :key="c.id" class="product-card" @click="goDetail(c.id)">
                <ProductThumb :product="c" :size="104" />
                <div class="card-main">
                  <div class="card-head">
                    <span class="card-title">{{ c.title }}</span>
                    <span class="card-price">¥{{ Number(c.final_price ?? c.price).toLocaleString() }}</span>
                  </div>
                  <div class="card-tags">
                    <el-tag size="small" type="primary" effect="plain">{{ c.brand }}</el-tag>
                    <el-tag v-for="(v, k) in keyAttrs(c)" :key="k" size="small" effect="plain">{{ k }} {{ v }}</el-tag>
                  </div>
                  <div class="card-reason" v-if="c.reason">推荐理由：{{ c.reason }}</div>
                  <div class="card-con" v-if="c.con">不足：{{ c.con }}</div>
                  <div class="card-actions" @click.stop>
                    <el-button size="small" type="warning" plain :disabled="!isLoggedIn()" @click="favCard(c)">收藏</el-button>
                    <el-button size="small" type="primary" plain :disabled="!isLoggedIn()" @click="addToCart(c)">加入购物车</el-button>
                  </div>
                </div>
              </div>
            </div>

            <!-- 订单卡片：横向滚动 -->
            <div v-if="m.orderCards && m.orderCards.length" class="order-cards">
              <OrderCard
                v-for="o in m.orderCards"
                :key="o.order_no"
                :order="o"
                role="buyer"
                @track="goTrack"
                @aftersale="askAftersale"
              />
            </div>
          </div>
        </div>

        <div class="chat-input">
          <el-input
            v-model="input"
            placeholder="描述你的需求，例如：想买个写代码的笔记本，七千左右"
            :disabled="loading"
            @keyup.enter="send"
          >
            <template #append>
              <el-button type="primary" :loading="loading" @click="send">发送</el-button>
            </template>
          </el-input>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import ProductThumb from '../components/ProductThumb.vue'
import OrderCard from '../components/OrderCard.vue'
import { theme, toggleTheme } from '../theme'
import {
  sendChat, addToCart as apiAddToCart, addFavorite, getSessionId, setSessionId,
  getSessions, getSessionMessages, isLoggedIn, getUser,
  renameSession, pinSession, deleteSession, applyAftersale,
} from '../api'

const EXAMPLES = [
  '想买个写代码的笔记本，七千左右',
  '三千左右拍照好的手机',
  '我的订单到哪了',
  '我要申请售后',
]

const router = useRouter()
const input = ref('')
const loading = ref(false)
const sessionId = ref(getSessionId())
const messages = ref([])
const sessions = ref([])
const bodyRef = ref(null)

const displayName = computed(() => {
  const u = getUser()
  return u?.nickname || u?.username || '朋友'
})

function keyAttrs(card) {
  return Object.fromEntries(
    Object.entries(card.attributes || {}).filter(([, v]) => v)
  )
}

function useExample(text) {
  input.value = text
  send()
}

function goDetail(id) {
  router.push('/products/' + id)
}

async function loadSessions() {
  try {
    const { data } = await getSessions()
    sessions.value = data?.data?.sessions || []
  } catch (e) {
    sessions.value = []
  }
}

async function loadMessages(key) {
  try {
    const { data } = await getSessionMessages(key)
    const msgs = data?.data?.messages || []
    // 历史消息连同当时推荐的卡片一起还原
    messages.value = msgs.map((m) => ({ role: m.role, content: m.content, cards: m.cards || [] }))
    scrollBottom()
  } catch (e) {
    messages.value = []
  }
}

function newChat() {
  const id = 's_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8)
  setSessionId(id)
  sessionId.value = id
  messages.value = []
  loadSessions()
}

function switchChat(key) {
  if (key === sessionId.value) return
  setSessionId(key)
  sessionId.value = key
  loadMessages(key)
}

// ---- 会话操作 ----
function onCommand(cmd, s) {
  if (cmd === 'share') return shareChat(s)
  if (cmd === 'pin') return togglePin(s)
  if (cmd === 'rename') return renameChat(s)
  if (cmd === 'delete') return removeChat(s)
}

async function shareChat(s) {
  const link = `${location.origin}/share/${s.session_id}`
  try {
    await navigator.clipboard.writeText(link)
    ElMessage.success('只读分享链接已复制')
  } catch (e) {
    // 非安全上下文下 clipboard 不可用，退回手动复制
    ElMessageBox.alert(link, '复制以下链接分享', { confirmButtonText: '知道了' })
  }
}

async function togglePin(s) {
  const { data } = await pinSession(s.session_id, !s.pinned)
  if (data?.code !== 0) return ElMessage.error(data?.message)
  ElMessage.success(data.message)
  loadSessions()
}

async function renameChat(s) {
  let value
  try {
    const r = await ElMessageBox.prompt('新的对话名称', '重命名', {
      inputValue: s.title,
      inputValidator: (v) => (v && v.trim() ? true : '名称不能为空'),
    })
    value = r.value
  } catch (e) {
    return
  }
  const { data } = await renameSession(s.session_id, value.trim())
  if (data?.code !== 0) return ElMessage.error(data?.message)
  ElMessage.success('已重命名')
  loadSessions()
}

async function removeChat(s) {
  try {
    await ElMessageBox.confirm(`确定删除对话「${s.title}」？删除后无法恢复。`, '删除对话', { type: 'warning' })
  } catch (e) {
    return
  }
  const { data } = await deleteSession(s.session_id)
  if (data?.code !== 0) return ElMessage.error(data?.message)
  ElMessage.success('已删除')
  // 删的是当前会话就顺势开一个新的
  if (s.session_id === sessionId.value) newChat()
  else loadSessions()
}

// ---- 商品操作 ----
async function addToCart(card) {
  try {
    await apiAddToCart(card.id)
    ElMessage.success(`已加入购物车：${card.title.slice(0, 18)}`)
    window.dispatchEvent(new CustomEvent('cart-changed'))
  } catch (e) {
    ElMessage.error('加购失败，请先登录')
  }
}

async function favCard(card) {
  try {
    await addFavorite(card.id)
    ElMessage.success(`已收藏：${card.title.slice(0, 18)}`)
    window.dispatchEvent(new CustomEvent('favorites-changed'))
  } catch (e) {
    ElMessage.error('收藏失败，请先登录')
  }
}

function scrollBottom() {
  nextTick(() => {
    if (bodyRef.value) bodyRef.value.scrollTop = bodyRef.value.scrollHeight
  })
}

// ---- 订单卡片交互 ----
function goTrack(o) {
  router.push(`/orders/${o.order_no}/track`)
}

async function askAftersale(o) {
  let kind
  try {
    const r = await ElMessageBox.prompt('说明一下售后原因，方便商家处理', '申请售后', {
      inputPlaceholder: '例如：屏幕有划痕，想退货',
      inputValidator: (v) => (v && v.trim() ? true : '请填写原因'),
      distinguishCancelAndClose: true,
    })
    kind = r.value
  } catch (e) {
    return
  }
  const { data } = await applyAftersale(o.order_no, guessKind(kind), kind.trim())
  if (data?.code !== 0) return ElMessage.error(data?.message)
  ElMessage.success(data.message)
  // 就地更新卡片状态，不用重新发消息
  for (const m of messages.value) {
    const hit = (m.orderCards || []).find((x) => x.order_no === o.order_no)
    if (hit) Object.assign(hit, data.data)
  }
}

function guessKind(text) {
  if (text.includes('退货')) return 'return'
  if (text.includes('换')) return 'exchange'
  if (text.includes('修')) return 'repair'
  return 'refund'
}

async function send() {
  const text = input.value.trim()
  if (!text || loading.value) return
  input.value = ''
  loading.value = true
  messages.value.push({ role: 'user', content: text, cards: [] })
  scrollBottom()

  try {
    const { data } = await sendChat(text, sessionId.value)
    const body = data?.data ?? {}
    messages.value.push({
      role: 'assistant',
      content: body.reply || '',
      cards: body.cards || [],
      orderCards: body.order_cards || [],
    })
  } catch (e) {
    messages.value.push({ role: 'assistant', content: '（请求失败，请检查后端服务）', cards: [] })
  } finally {
    loading.value = false
  }
  scrollBottom()
  loadSessions() // 标题/时间更新
}

onMounted(() => {
  loadSessions()
  if (localStorage.getItem('session_id')) {
    loadMessages(sessionId.value)
  }
})
</script>

<style scoped>
.chat-layout { display: flex; height: calc(100vh - 60px); }

/* ===== 侧边栏 ===== */
.sidebar {
  width: 250px; flex-shrink: 0; border-right: 1px solid var(--border);
  background: var(--surface); display: flex; flex-direction: column; overflow: hidden;
}
.new-btn { margin: 14px; width: calc(100% - 28px); border-radius: 10px; font-weight: 600; }
.session-list { flex: 1; padding-bottom: 10px; overflow-y: auto; }
.session-item {
  display: flex; align-items: center; gap: 6px;
  padding: 10px 10px 10px 16px; cursor: pointer; border-left: 3px solid transparent;
  transition: background 0.15s ease;
}
.session-item:hover { background: var(--surface-2); }
.session-item.active { background: rgba(79, 124, 255, 0.08); border-left-color: var(--primary); }
.session-body { flex: 1; min-width: 0; }
.session-title {
  display: flex; align-items: center; gap: 4px;
  font-size: 13px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.pin-icon { flex-shrink: 0; color: var(--primary); }
.session-meta { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
.session-more {
  flex-shrink: 0; width: 22px; height: 22px; line-height: 20px; text-align: center;
  border-radius: 6px; color: var(--text-muted); font-size: 16px;
  opacity: 0; transition: opacity 0.15s ease, background 0.15s ease;
}
.session-item:hover .session-more { opacity: 1; }
.session-more:hover { background: rgba(79, 124, 255, 0.14); color: var(--primary); }
.sidebar-empty { color: var(--text-muted); text-align: center; margin-top: 30px; font-size: 13px; }

.theme-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px; cursor: pointer; font-size: 13px; color: var(--text-sub);
  border-top: 1px solid var(--border); transition: background 0.15s ease;
}
.theme-bar:hover { background: var(--surface-2); color: var(--primary); }
.theme-icon { display: inline-flex; align-items: center; }

/* ===== 主区 ===== */
.chat-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.chat-header {
  display: flex; align-items: baseline; gap: 12px;
  padding: 0 20px; height: 56px; flex-shrink: 0;
  border-bottom: 1px solid var(--border); background: var(--nav-bg);
}
.chat-header .title { font-size: 19px; font-weight: 700; color: var(--text); }
.chat-header .subtitle { color: var(--text-muted); font-size: 13px; }

/* 初始态：整体居中 */
.welcome-stage {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  padding: 0 24px 60px; background: var(--bg);
}
.welcome-title {
  margin: 0 0 8px; font-size: 32px; font-weight: 800; color: var(--text);
  background: var(--primary-grad); -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent;
}
.welcome-sub { margin: 0 0 26px; color: var(--text-muted); font-size: 14.5px; }
.welcome-input { width: 100%; max-width: 640px; }
:deep(.welcome-input .el-input__wrapper) { border-radius: 14px 0 0 14px; padding: 10px 18px; }
:deep(.welcome-input .el-input-group__append) { background: var(--primary-grad); border: none; }
:deep(.welcome-input .el-input-group__append .el-button) { color: #fff; font-weight: 600; }
.examples { display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; margin-top: 18px; max-width: 660px; }
.example-chip {
  padding: 7px 14px; border-radius: 999px; cursor: pointer;
  background: var(--surface); border: 1px solid var(--border);
  color: var(--text-sub); font-size: 13px; transition: all 0.16s ease;
}
.example-chip:hover { border-color: var(--primary); color: var(--primary); transform: translateY(-2px); }

/* 对话态 */
.chat-body { flex: 1; overflow-y: auto; background: var(--bg); padding: 16px 20px; }
.msg-row { margin: 12px 0; }
.msg-row.user { text-align: right; }
.msg-bubble {
  display: inline-block; max-width: 70%;
  padding: 11px 16px; white-space: pre-wrap; text-align: left;
  border-radius: 14px; font-size: 14.5px; line-height: 1.55;
}
.msg-row.user .msg-bubble {
  background: var(--primary-grad); color: #fff;
  border-bottom-right-radius: 4px;
  box-shadow: 0 4px 12px rgba(79, 124, 255, 0.3);
}
.msg-row.assistant .msg-bubble {
  background: var(--surface); color: var(--text);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
  box-shadow: var(--card-shadow);
}
.cards { display: flex; flex-direction: column; gap: 12px; margin-top: 10px; max-width: 720px; }

/* 订单卡片：横向排列，超出可横向滚动 */
.order-cards {
  display: flex; gap: 12px; margin-top: 10px;
  overflow-x: auto; padding-bottom: 6px; max-width: 100%;
}
.order-cards::-webkit-scrollbar { height: 6px; }
/* 左图右文 */
.product-card {
  display: flex; gap: 14px; padding: 14px; cursor: pointer;
  background: var(--surface);
  border-radius: var(--card-radius); border: 1px solid var(--border);
  box-shadow: var(--card-shadow);
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}
.product-card:hover { transform: translateY(-2px); box-shadow: var(--card-shadow-hover); }
.card-main { flex: 1; min-width: 0; }
.card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.card-title { font-weight: 600; font-size: 14.5px; color: var(--text); line-height: 1.4; }
.card-price { color: var(--price); font-weight: 800; font-size: 17px; white-space: nowrap; }
.card-tags { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
.card-reason { color: var(--text-sub); margin: 6px 0; font-size: 13.5px; background: rgba(79, 124, 255, 0.07); padding: 8px 10px; border-radius: 8px; }
.card-con { color: #d97070; font-size: 13.5px; background: rgba(255, 77, 79, 0.07); padding: 7px 10px; border-radius: 8px; }
.card-actions { margin-top: 10px; text-align: right; display: flex; gap: 8px; justify-content: flex-end; }

.chat-input { padding: 0 20px 18px; flex-shrink: 0; }
:deep(.chat-input .el-input__wrapper) { border-radius: 12px; padding: 6px 14px; box-shadow: var(--card-shadow); }
</style>
