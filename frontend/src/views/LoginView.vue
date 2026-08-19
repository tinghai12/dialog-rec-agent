<template>
  <div class="login-page">
    <el-card class="login-card" shadow="always">
      <div class="logo-row">
        <span class="logo">语</span>
      </div>
      <h2>自然语言电商</h2>
      <p class="sub">{{ role === 'merchant' ? '商家中心：管商品，配营销位' : '说出需求，我来帮你买' }}</p>

      <!-- 身份切换：买家 / 商家 -->
      <el-radio-group v-model="role" class="role-switch" size="large">
        <el-radio-button value="buyer">我是买家</el-radio-button>
        <el-radio-button value="merchant">我是商家</el-radio-button>
      </el-radio-group>

      <el-tabs v-model="tab" stretch>
        <el-tab-pane label="登录" name="login">
          <el-form @submit.prevent>
            <el-form-item>
              <el-input v-model="username" placeholder="用户名" size="large" />
            </el-form-item>
            <el-form-item>
              <el-input v-model="password" type="password" placeholder="密码" size="large" show-password @keyup.enter="doLogin" />
            </el-form-item>
            <el-button type="primary" size="large" class="submit" :loading="loading" @click="doLogin">登 录</el-button>
          </el-form>
          <p v-if="role === 'merchant'" class="hint">
            演示商家账号：<b>merchant01</b> ~ <b>merchant18</b>，密码 <b>123456</b>
          </p>
        </el-tab-pane>
        <el-tab-pane label="注册" name="register">
          <el-form @submit.prevent>
            <el-form-item>
              <el-input v-model="username" placeholder="用户名（至少2位）" size="large" />
            </el-form-item>
            <el-form-item>
              <el-input v-model="password" type="password" placeholder="密码（至少4位）" size="large" show-password />
            </el-form-item>
            <el-form-item v-if="role === 'merchant'">
              <el-input v-model="shopName" placeholder="店铺名（必填，展示在商品卡片上）" size="large" />
            </el-form-item>
            <el-form-item v-else>
              <el-input v-model="nickname" placeholder="昵称（可选）" size="large" @keyup.enter="doRegister" />
            </el-form-item>
            <el-button type="primary" size="large" class="submit" :loading="loading" @click="doRegister">
              注册{{ role === 'merchant' ? '商家账号' : '' }}
            </el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login, register, setToken, setUser } from '../api'

const router = useRouter()
const tab = ref('login')
const role = ref('buyer')
const username = ref('')
const password = ref('')
const nickname = ref('')
const shopName = ref('')
const loading = ref(false)

async function doLogin() {
  if (!username.value || !password.value) return ElMessage.warning('填用户名和密码')
  loading.value = true
  try {
    const { data } = await login({ username: username.value, password: password.value })
    if (data?.code !== 0) return ElMessage.error(data?.message)
    const user = data.data.user
    // 身份与账号实际角色不符时给出提示，但仍按真实角色登录
    if (user.role !== role.value) {
      ElMessage.warning(`该账号是${user.role === 'merchant' ? '商家' : '买家'}账号，已按其身份登录`)
    }
    setToken(data.data.token)
    setUser(user)
    window.dispatchEvent(new CustomEvent('auth-changed'))
    ElMessage.success(`欢迎，${user.nickname || user.username}`)
    router.push(user.role === 'merchant' ? '/merchant' : '/')
  } catch (e) {
    ElMessage.error('登录失败，请重试')
  } finally {
    loading.value = false
  }
}

async function doRegister() {
  if (!username.value || !password.value) return ElMessage.warning('填用户名和密码')
  if (role.value === 'merchant' && !shopName.value.trim()) return ElMessage.warning('商家需要填写店铺名')
  loading.value = true
  try {
    const { data } = await register({
      username: username.value,
      password: password.value,
      nickname: nickname.value,
      role: role.value,
      shop_name: shopName.value,
    })
    if (data?.code !== 0) return ElMessage.error(data?.message)
    ElMessage.success('注册成功，去登录')
    tab.value = 'login'
  } catch (e) {
    ElMessage.error('注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: calc(100vh - 60px);
  display: flex; justify-content: center; align-items: center;
  background:
    radial-gradient(800px 400px at 15% 10%, rgba(123, 92, 255, 0.14), transparent 60%),
    radial-gradient(700px 380px at 85% 85%, rgba(79, 124, 255, 0.16), transparent 60%);
}
.login-card { width: 380px; padding: 14px 22px 24px; border-radius: 18px; border: none;
  box-shadow: 0 18px 50px rgba(31, 45, 92, 0.14); }
.logo-row { text-align: center; margin-top: 6px; }
.logo {
  display: inline-flex; align-items: center; justify-content: center;
  width: 52px; height: 52px; border-radius: 14px;
  background: var(--primary-grad); color: #fff; font-size: 24px; font-weight: 800;
  box-shadow: 0 8px 20px rgba(79, 124, 255, 0.4);
}
.login-card h2 { margin: 12px 0 2px; text-align: center; color: #2a3050; }
.login-card .sub { color: #98a0c0; text-align: center; margin: 4px 0 14px; font-size: 13.5px; }
.role-switch { display: flex; justify-content: center; margin-bottom: 6px; }
.role-switch :deep(.el-radio-button__inner) { padding: 8px 26px; }
.submit { width: 100%; margin-top: 4px; background: var(--primary-grad); border: none;
  box-shadow: 0 6px 16px rgba(79, 124, 255, 0.35); }
.submit:hover { opacity: 0.92; }
.hint { margin: 12px 0 0; font-size: 12px; color: #98a0c0; text-align: center; line-height: 1.6; }
.hint b { color: #4a5175; }
</style>
