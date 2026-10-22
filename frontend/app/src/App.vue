<script setup lang="ts">
import { computed } from 'vue'
import { useUserStore } from '@/store/userStore'
import { useConfigStore } from '@/store/configStore'
// #ifdef H5
import { useFavicon } from '@vueuse/core'
// #endif

/**
 * 启动校验：本地存在 access_token 时，向后端确认会话是否仍然有效。
 *
 * 为什么不看本地 JWT 的 exp：后端默认开启滑动续期（TOKEN_SLIDING_EXPIRE），
 * 每次请求都跳过 JWT exp 校验、由 Redis 会话 TTL 决定有效期（会话绝对上限 7 天），
 * 按本地 exp 判断会把服务端仍然有效的会话误踢。
 *
 * 因此改为发一次带鉴权的请求（getInfo）交后端裁决：
 * - 会话仍有效 → 正常进入应用（access_token 过期时由 http 层静默刷新后重放）
 * - 会话已失效（过期/被踢/停用/超最大存活）→ http 层清空凭据并 reLaunch 登录页
 * - 网络异常 → getInfo 内部已吞掉错误，保留本地会话，避免误登出
 */
onLaunch(() => {
  const userStore = useUserStore()
  if (!userStore.getAccessToken())
    return
  void userStore.getInfo()
})

// #ifdef H5
// 浏览器标签页图标（favicon）跟随后台「系统参数」的 logo_url，未配置时回退本地 logo
const configStore = useConfigStore()
const faviconUrl = computed(() => configStore.configData?.logo_url?.config_value?.trim() || 'static/logo.png')
useFavicon(faviconUrl)
void configStore.getConfig()
// #endif
</script>

<style lang="scss">
/* 全局样式按职责拆分：
   - theme.scss：玻璃水滴渐变主题变量（6 套主题色）
   - base.scss：页面容器 / 暗色背景等基础全局样式
   页面级样式（登录表单输入框、滑块等）保留在各页面 scoped 内 */
@import './styles/brand-tokens.generated.scss';
@import './styles/brand-dark.generated.scss';
@import './styles/theme.scss';
@import './styles/base.scss';
</style>
