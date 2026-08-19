<template>
  <div class="merchant-page">
    <div class="head">
      <div>
        <h2>商家中心</h2>
        <p class="sub">{{ user?.shop_name || user?.nickname }} · 管理商品与营销位</p>
      </div>
      <el-button type="primary" @click="openCreate">＋ 新建商品</el-button>
    </div>

    <el-tabs v-model="tab" class="tabs">
      <!-- ===== 数据看板 ===== -->
      <el-tab-pane label="数据看板" name="dashboard">
        <div class="board-head">
          <el-radio-group v-model="days" size="small" @change="loadDashboard">
            <el-radio-button :value="7">近7天</el-radio-button>
            <el-radio-button :value="30">近30天</el-radio-button>
            <el-radio-button :value="90">近90天</el-radio-button>
          </el-radio-group>
        </div>

        <div class="stat-row">
          <div class="stat"><span class="k">在售商品</span><span class="v">{{ board.overview?.on_sale ?? 0 }}<i>/ {{ board.overview?.total ?? 0 }}</i></span></div>
          <div class="stat"><span class="k">已配促销条</span><span class="v">{{ board.overview?.with_promo ?? 0 }}</span></div>
          <div class="stat"><span class="k">已传主图</span><span class="v">{{ board.overview?.with_image ?? 0 }}</span></div>
          <div class="stat"><span class="k">均价</span><span class="v">¥{{ Math.round(board.overview?.avg_price || 0).toLocaleString() }}</span></div>
        </div>

        <div class="panel">
          <div class="panel-title">转化漏斗</div>
          <div class="funnel">
            <div v-for="s in funnelSteps" :key="s.key" class="funnel-step">
              <div class="fs-bar" :style="{ width: funnelWidth(s.value) }"></div>
              <span class="fs-label">{{ s.label }}</span>
              <span class="fs-value">{{ s.value }}</span>
            </div>
          </div>
          <div class="rates">
            <span>曝光→加购 <b>{{ board.funnel?.cart_rate ?? 0 }}%</b></span>
            <span>加购→下单 <b>{{ board.funnel?.order_rate ?? 0 }}%</b></span>
          </div>
        </div>

        <div class="panel">
          <div class="panel-title">热门商品 Top 10</div>
          <el-table :data="board.top_products || []" size="small" empty-text="暂无埋点数据">
            <el-table-column prop="title" label="商品" min-width="260" show-overflow-tooltip />
            <el-table-column prop="recommend" label="曝光" width="80" />
            <el-table-column prop="view" label="浏览" width="80" />
            <el-table-column prop="cart" label="加购" width="80" />
            <el-table-column prop="order" label="下单" width="80" />
          </el-table>
        </div>
      </el-tab-pane>

      <!-- ===== 商品管理 ===== -->
      <el-tab-pane label="商品管理" name="products">
        <div class="filters">
          <el-input v-model="keyword" placeholder="搜索标题或品牌" clearable style="width: 240px"
                    @keyup.enter="reload" @clear="reload" />
          <el-select v-model="category" placeholder="全部品类" clearable style="width: 140px" @change="reload">
            <el-option label="笔记本" value="笔记本" />
            <el-option label="手机" value="手机" />
          </el-select>
          <el-button @click="reload">查询</el-button>
          <span class="total">共 {{ total }} 款</span>
        </div>

        <el-table :data="items" v-loading="loading" size="small" empty-text="还没有商品">
          <el-table-column label="主图" width="70">
            <template #default="{ row }">
              <img v-if="row.main_image" :src="row.main_image" class="thumb" />
              <span v-else class="thumb thumb-empty">无图</span>
            </template>
          </el-table-column>
          <el-table-column prop="title" label="标题" min-width="260" show-overflow-tooltip />
          <el-table-column prop="brand" label="品牌" width="90" />
          <el-table-column label="价格 / 到手价" width="150">
            <template #default="{ row }">
              <span class="price-cell">¥{{ row.price.toLocaleString() }}</span>
              <span v-if="row.final_price && row.final_price !== row.price" class="final-cell">
                → ¥{{ row.final_price.toLocaleString() }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="促销条" min-width="160">
            <template #default="{ row }">
              <span v-if="row.promo_banner" class="promo-chip" :class="'style-' + row.promo_banner_style">
                {{ row.promo_banner }}
              </span>
              <span v-else class="muted">未设置</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-switch :model-value="row.is_on_sale === 1" @change="(v) => setOnSale(row, v)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="210" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openMarketing(row)">营销位</el-button>
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" @click="remove(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          class="pager"
          layout="prev, pager, next"
          :current-page="page"
          :page-size="pageSize"
          :total="total"
          @current-change="(p) => { page = p; load() }"
        />
      </el-tab-pane>
    </el-tabs>

    <!-- ===== 商品基础信息 对话框 ===== -->
    <el-dialog v-model="editVisible" :title="editing.id ? '编辑商品' : '新建商品'" width="520">
      <el-form label-width="72px">
        <el-form-item label="标题" required>
          <el-input v-model="editing.title" placeholder="如：轻薄本 X14 16GB+512GB" />
        </el-form-item>
        <el-form-item label="品牌">
          <el-input v-model="editing.brand" />
        </el-form-item>
        <el-form-item label="品类" required>
          <el-select v-model="editing.category" style="width: 100%">
            <el-option label="笔记本" value="笔记本" />
            <el-option label="手机" value="手机" />
          </el-select>
        </el-form-item>
        <el-form-item label="价格" required>
          <el-input-number v-model="editing.price" :min="1" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="上架">
          <el-switch v-model="editing.is_on_sale" :active-value="1" :inactive-value="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveProduct">保存</el-button>
      </template>
    </el-dialog>

    <!-- ===== 营销位编辑 抽屉（左表单 / 右实时预览） ===== -->
    <el-drawer v-model="promoVisible" title="营销位设置" size="820px">
      <div class="promo-layout">
        <div class="promo-form">
          <el-divider content-position="left">主图</el-divider>
          <div class="upload-row">
            <img v-if="promo.main_image" :src="promo.main_image" class="upload-preview" />
            <div v-else class="upload-preview upload-empty">未上传<br />（用兜底海报）</div>
            <div class="upload-actions">
              <input ref="fileInput" type="file" accept="image/*" hidden @change="onFilePicked" />
              <el-button size="small" :loading="uploading" @click="$refs.fileInput.click()">上传主图</el-button>
              <el-button size="small" v-if="promo.main_image" @click="clearImage">清除主图</el-button>
              <p class="upload-tip">png/jpg/webp，5MB 以内。不传则用下方文案生成海报。</p>
            </div>
          </div>

          <el-divider content-position="left">兜底海报文案</el-divider>
          <el-form label-width="86px" size="small">
            <el-form-item label="底色主题">
              <el-select v-model="promo.poster_bg" style="width: 100%">
                <el-option v-for="b in posterBgs" :key="b" :label="b" :value="b" />
              </el-select>
            </el-form-item>
            <el-form-item label="主标语">
              <el-input v-model="promo.poster_headline" maxlength="20" show-word-limit />
            </el-form-item>
            <el-form-item label="副标语">
              <el-input v-model="promo.poster_subline" maxlength="26" show-word-limit />
            </el-form-item>
            <el-form-item label="规格浮层">
              <el-select v-model="promo.poster_specs" multiple filterable allow-create
                         default-first-option placeholder="如 R7 9800X3D" style="width: 100%" />
            </el-form-item>
            <el-form-item label="浮层价签">
              <el-input v-model="promo.poster_price_label" placeholder="如 国补到手价" maxlength="10" />
            </el-form-item>

            <el-divider content-position="left">促销条与标题</el-divider>
            <el-form-item label="促销条">
              <el-input v-model="promo.promo_banner" placeholder="如 天猫 七夕礼遇季" maxlength="20" />
            </el-form-item>
            <el-form-item label="促销条样式">
              <el-radio-group v-model="promo.promo_banner_style">
                <el-radio-button value="none">隐藏</el-radio-button>
                <el-radio-button value="tmall">红</el-radio-button>
                <el-radio-button value="subsidy">绿</el-radio-button>
                <el-radio-button value="live">橙</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="标题前缀">
              <el-input v-model="promo.title_prefix" placeholder="如 【24期免息】" maxlength="20" />
            </el-form-item>
            <el-form-item label="榜单标签">
              <el-input v-model="promo.rank_label" placeholder="如 办公笔记本好评榜·第1名" maxlength="24" />
            </el-form-item>

            <el-divider content-position="left">价格与利益点</el-divider>
            <el-form-item label="到手价">
              <el-input-number v-model="promo.final_price" :min="0" :precision="2" style="width: 100%" />
            </el-form-item>
            <el-form-item label="已省金额">
              <el-input-number v-model="promo.saved_amount" :min="0" :precision="2" style="width: 100%" />
            </el-form-item>
            <el-form-item label="分期">
              <el-input v-model="promo.installment" placeholder="如 12期 / 24期免息" maxlength="10" />
            </el-form-item>
            <el-form-item label="服务标签">
              <el-select v-model="promo.service_tags" multiple filterable allow-create
                         default-first-option placeholder="如 退货宝、包邮" style="width: 100%" />
            </el-form-item>
            <el-form-item label="付款人数">
              <el-input-number v-model="promo.sold_count" :min="0" style="width: 100%" />
            </el-form-item>
            <el-form-item label="回头客">
              <el-input-number v-model="promo.repeat_buyers" :min="0" style="width: 100%" />
            </el-form-item>
          </el-form>
        </div>

        <div class="promo-preview">
          <div class="preview-title">前台效果预览</div>
          <ProductCard :product="previewProduct" />
          <p class="preview-tip">与「逛商品」列表中的卡片完全一致。</p>
        </div>
      </div>
      <template #footer>
        <el-button @click="promoVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveMarketing">保存营销位</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import ProductCard from '../components/ProductCard.vue'
import {
  getUser, isMerchant,
  merchantListProducts, merchantCreateProduct, merchantUpdateProduct,
  merchantDeleteProduct, merchantSetOnSale, merchantUploadImage,
  merchantRemoveImage, merchantDashboard,
} from '../api'

const router = useRouter()
const user = ref(getUser())
const tab = ref('dashboard')

// ---- 看板 ----
const days = ref(30)
const board = ref({})
const funnelSteps = computed(() => [
  { key: 'recommend', label: '曝光', value: board.value.funnel?.recommend ?? 0 },
  { key: 'view', label: '浏览', value: board.value.funnel?.view ?? 0 },
  { key: 'cart', label: '加购', value: board.value.funnel?.cart ?? 0 },
  { key: 'order', label: '下单', value: board.value.funnel?.order ?? 0 },
])
function funnelWidth(v) {
  const max = Math.max(...funnelSteps.value.map((s) => s.value), 1)
  return `${Math.max((v / max) * 100, 2)}%`
}
async function loadDashboard() {
  const { data } = await merchantDashboard(days.value)
  if (data?.code === 0) board.value = data.data
}

// ---- 商品列表 ----
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const keyword = ref('')
const category = ref('')
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await merchantListProducts({
      keyword: keyword.value, category: category.value,
      page: page.value, page_size: pageSize,
    })
    if (data?.code !== 0) return ElMessage.error(data?.message)
    items.value = data.data.items
    total.value = data.data.total
  } finally {
    loading.value = false
  }
}
function reload() { page.value = 1; load() }

// ---- 商品基础信息 ----
const editVisible = ref(false)
const saving = ref(false)
const editing = reactive({ id: null, title: '', brand: '', category: '笔记本', price: 999, is_on_sale: 1 })

function openCreate() {
  Object.assign(editing, { id: null, title: '', brand: user.value?.shop_name || '', category: '笔记本', price: 999, is_on_sale: 1 })
  editVisible.value = true
}
function openEdit(row) {
  Object.assign(editing, {
    id: row.id, title: row.title, brand: row.brand,
    category: row.category, price: row.price, is_on_sale: row.is_on_sale,
  })
  editVisible.value = true
}
async function saveProduct() {
  if (!editing.title.trim()) return ElMessage.warning('标题不能为空')
  saving.value = true
  try {
    const payload = {
      title: editing.title, brand: editing.brand, category: editing.category,
      price: editing.price, is_on_sale: editing.is_on_sale,
    }
    const { data } = editing.id
      ? await merchantUpdateProduct(editing.id, payload)
      : await merchantCreateProduct(payload)
    if (data?.code !== 0) return ElMessage.error(data?.message)
    ElMessage.success(data.message)
    editVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function setOnSale(row, value) {
  const { data } = await merchantSetOnSale(row.id, value)
  if (data?.code !== 0) return ElMessage.error(data?.message)
  row.is_on_sale = value ? 1 : 0
  ElMessage.success(data.message)
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确定删除「${row.title}」？该商品会同时从买家的购物车与收藏中移除。`, '删除商品', { type: 'warning' })
  } catch (e) {
    return
  }
  const { data } = await merchantDeleteProduct(row.id)
  if (data?.code !== 0) return ElMessage.error(data?.message)
  ElMessage.success('已删除')
  load()
}

// ---- 营销位 ----
const promoVisible = ref(false)
const uploading = ref(false)
const fileInput = ref(null)
const posterBgs = ['dark', 'blue', 'purple', 'red', 'green', 'ink']
const promo = reactive({})
const promoBase = ref({})

function openMarketing(row) {
  promoBase.value = row
  Object.assign(promo, {
    id: row.id,
    main_image: row.main_image || '',
    poster_bg: row.poster_bg || 'dark',
    poster_headline: row.poster_headline || '',
    poster_subline: row.poster_subline || '',
    poster_specs: [...(row.poster_specs || [])],
    poster_price_label: row.poster_price_label || '',
    promo_banner: row.promo_banner || '',
    promo_banner_style: row.promo_banner_style || 'none',
    title_prefix: row.title_prefix || '',
    rank_label: row.rank_label || '',
    final_price: row.final_price ?? row.price,
    saved_amount: row.saved_amount ?? 0,
    installment: row.installment || '',
    service_tags: [...(row.service_tags || [])],
    sold_count: row.sold_count || 0,
    repeat_buyers: row.repeat_buyers || 0,
  })
  promoVisible.value = true
}

// 预览用：商品基础字段 + 表单里正在编辑的营销位
const previewProduct = computed(() => ({ ...promoBase.value, ...promo }))

async function onFilePicked(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  uploading.value = true
  try {
    const { data } = await merchantUploadImage(promo.id, file)
    if (data?.code !== 0) return ElMessage.error(data?.message)
    promo.main_image = data.data.main_image
    ElMessage.success('主图已上传')
    load()
  } catch (err) {
    ElMessage.error('上传失败')
  } finally {
    uploading.value = false
  }
}

async function clearImage() {
  const { data } = await merchantRemoveImage(promo.id)
  if (data?.code !== 0) return ElMessage.error(data?.message)
  promo.main_image = ''
  ElMessage.success('已清除主图')
  load()
}

async function saveMarketing() {
  saving.value = true
  try {
    const { id, ...payload } = promo
    const { data } = await merchantUpdateProduct(id, payload)
    if (data?.code !== 0) return ElMessage.error(data?.message)
    ElMessage.success('营销位已保存，前台立即生效')
    promoVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  if (!isMerchant()) {
    ElMessage.warning('请先用商家账号登录')
    return router.push('/login')
  }
  loadDashboard()
  load()
})
</script>

<style scoped>
.merchant-page { max-width: 1280px; margin: 0 auto; padding: 24px 20px 40px; }
.head { display: flex; align-items: center; justify-content: space-between; }
.head h2 { margin: 0 0 4px; color: #2a3050; }
.sub { color: #98a0c0; margin: 0; font-size: 13px; }
.tabs { margin-top: 14px; }

/* 看板 */
.board-head { margin-bottom: 14px; }
.stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.stat {
  background: #fff; border-radius: 12px; padding: 16px 18px;
  border: 1px solid rgba(31, 45, 92, 0.06); display: flex; flex-direction: column; gap: 6px;
}
.stat .k { color: #98a0c0; font-size: 12.5px; }
.stat .v { color: #2a3050; font-size: 24px; font-weight: 800; }
.stat .v i { font-style: normal; font-size: 13px; color: #98a0c0; font-weight: 500; margin-left: 4px; }

.panel {
  background: #fff; border-radius: 12px; padding: 16px 18px; margin-top: 14px;
  border: 1px solid rgba(31, 45, 92, 0.06);
}
.panel-title { font-weight: 700; color: #2a3050; margin-bottom: 12px; font-size: 14px; }
.funnel { display: flex; flex-direction: column; gap: 8px; }
.funnel-step { position: relative; height: 30px; display: flex; align-items: center; }
.fs-bar {
  position: absolute; left: 0; top: 0; height: 100%; border-radius: 6px;
  background: linear-gradient(90deg, rgba(79, 124, 255, 0.85), rgba(123, 92, 255, 0.5));
}
.fs-label { position: relative; color: #fff; font-size: 12.5px; margin-left: 10px; font-weight: 600; mix-blend-mode: difference; }
.fs-value { position: relative; margin-left: auto; color: #4a5175; font-size: 13px; font-weight: 700; }
.rates { display: flex; gap: 24px; margin-top: 12px; font-size: 13px; color: #98a0c0; }
.rates b { color: #4f7cff; font-size: 15px; }

/* 商品管理 */
.filters { display: flex; gap: 10px; align-items: center; margin-bottom: 14px; }
.total { color: #98a0c0; font-size: 13px; }
.thumb { width: 42px; height: 42px; border-radius: 6px; object-fit: cover; display: block; }
.thumb-empty {
  display: flex; align-items: center; justify-content: center;
  background: #f2f4fa; color: #b6bdd4; font-size: 11px;
}
.price-cell { color: #4a5175; }
.final-cell { color: #ff4d18; font-weight: 700; margin-left: 4px; }
.promo-chip { padding: 2px 8px; border-radius: 4px; font-size: 12px; }
.promo-chip.style-tmall { background: #fff1f0; color: #e4393c; }
.promo-chip.style-subsidy { background: #e8f8ee; color: #0f9d58; }
.promo-chip.style-live { background: #fff4e6; color: #fa6400; }
.promo-chip.style-none { background: #f2f4fa; color: #98a0c0; }
.muted { color: #b6bdd4; font-size: 12px; }
.pager { margin-top: 16px; justify-content: center; }

/* 营销位抽屉 */
.promo-layout { display: grid; grid-template-columns: 1fr 250px; gap: 24px; }
.promo-form { min-width: 0; }
.upload-row { display: flex; gap: 14px; align-items: flex-start; }
.upload-preview { width: 96px; height: 96px; border-radius: 8px; object-fit: cover; flex-shrink: 0; }
.upload-empty {
  display: flex; align-items: center; justify-content: center; text-align: center;
  background: #f2f4fa; color: #b6bdd4; font-size: 11.5px; line-height: 1.5;
}
.upload-actions { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.upload-tip { margin: 0; color: #98a0c0; font-size: 12px; line-height: 1.6; }
.promo-preview { position: sticky; top: 0; align-self: start; }
.preview-title { font-size: 13px; font-weight: 700; color: #2a3050; margin-bottom: 10px; }
.preview-tip { margin: 10px 0 0; color: #98a0c0; font-size: 12px; line-height: 1.6; }
</style>
