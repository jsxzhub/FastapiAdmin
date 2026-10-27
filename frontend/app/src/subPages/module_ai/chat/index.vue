<script setup lang="ts">
import type { ChatMessage, ChatSession } from '@/api/module_ai/chat'
import { onLoad, onUnload } from '@dcloudio/uni-app'
import { computed, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChatAPI } from '@/api/module_ai/chat'
import { useAiChat } from '@/composables/useAiChat'
import { useI18nNavTitle } from '@/composables/useI18nNavTitle'
import { useShare } from '@/composables/useShare'
import { MARKDOWN_TAG_STYLE } from '@/constants/markdown.constant'

const { t } = useI18n()

useShare({
  title: t('chat.shareTitle'),
  path: '/subPages/module_ai/chat/index',
})

definePage({ name: 'work-chat', style: { navigationBarTitleText: 'AI 助手' } })
useI18nNavTitle('chat.title')

const toast = useToast()
const sessions = ref<ChatSession[]>([])
const currentSession = ref<string | null>(null)
const currentTitle = ref(t('chat.title'))
const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const loading = ref(false)
const showSessions = ref(false)

/** 会话历史：搜索关键字 + 折叠分组（参照 web 端 AI 侧边栏） */
const searchQuery = ref('')
const collapsedGroups = ref<Set<string>>(new Set())
/** 分组顺序固定：今天 / 昨天 / 本周 / 更早 */
const GROUP_KEYS = ['today', 'yesterday', 'week', 'earlier'] as const
type GroupKey = (typeof GROUP_KEYS)[number]

const filteredSessions = computed<ChatSession[]>(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q)
    return sessions.value
  return sessions.value.filter(s => (s.title || s.session_name || '').toLowerCase().includes(q))
})

const groupedSessions = computed<{ key: GroupKey, list: ChatSession[] }[]>(() => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const todayStart = today.getTime() / 1000
  const yesterdayStart = todayStart - 86400
  const weekAgo = todayStart - 7 * 86400

  const buckets: Record<GroupKey, ChatSession[]> = { today: [], yesterday: [], week: [], earlier: [] }
  filteredSessions.value.forEach((s) => {
    // 后端 updated_at 为 Unix 秒；缺失时归入「更早」避免会话被隐藏
    const t = s.updated_at ?? s.created_at
    if (t === undefined || t < weekAgo)
      buckets.earlier.push(s)
    else if (t >= todayStart)
      buckets.today.push(s)
    else if (t >= yesterdayStart)
      buckets.yesterday.push(s)
    else
      buckets.week.push(s)
  })
  return GROUP_KEYS
    .map(key => ({ key, list: buckets[key] }))
    .filter(g => g.list.length > 0)
})

/** Unix 秒 → 展示用的时间文本（今天只显示时分，其余显示月-日） */
function formatSessionTime(ts?: number): string {
  if (!ts)
    return ''
  const d = new Date(ts * 1000)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return sameDay
    ? `${hh}:${mm}`
    : `${d.getMonth() + 1}-${String(d.getDate()).padStart(2, '0')} ${hh}:${mm}`
}

function toggleGroup(key: GroupKey) {
  const next = new Set(collapsedGroups.value)
  if (next.has(key))
    next.delete(key)
  else
    next.add(key)
  collapsedGroups.value = next
}

/** 流式对话（WebSocket） */
const streamChat = useAiChat()
const streaming = streamChat.isStreaming

// ===== 消息窗口化渲染 =====
// 长会话只渲染最近 MAX_VISIBLE_MESSAGES 条，避免消息过多时 DOM 节点与 setData 数据量膨胀导致卡顿；
// 通过"加载更早消息"按步长扩大渲染窗口，保持浏览位置不跳变。
const MAX_VISIBLE_MESSAGES = 60
const INCREMENT = 40
const messageWindow = ref(MAX_VISIBLE_MESSAGES)
const scrollTarget = ref('')
const visibleMessages = computed(() => messages.value.slice(-messageWindow.value))
const hasOlderMessages = computed(() => messages.value.length > messageWindow.value)

function loadOlderMessages() {
  messageWindow.value += INCREMENT
  // 滚动到新增窗口边界，保持已读消息位置不跳变
  scrollTarget.value = `msg-${INCREMENT - 1}`
  nextTick(() => {
    scrollTarget.value = ''
  })
}

function resetWindow() {
  messageWindow.value = MAX_VISIBLE_MESSAGES
  scrollTarget.value = ''
}

async function loadSessions() {
  loading.value = true
  try {
    const res = await ChatAPI.getSessions()
    sessions.value = res.items || []
  }
  catch {
    sessions.value = []
    toast.error(t('chat.loadSessionsFailed'))
  }
  finally { loading.value = false }
}

async function createSession() {
  try {
    const res = await ChatAPI.createSession(t('chat.newSession'))
    // 兼容后端可能返回 { data: ChatSession } 或直接 ChatSession 两种结构
    const newSession = (res as { data?: ChatSession })?.data ?? (res as ChatSession)
    if (newSession?.id) {
      sessions.value.unshift(newSession)
      selectSession(newSession.id, newSession.title)
    }
    toast.success(t('chat.newSessionSuccess'))
  }
  catch { toast.error(t('chat.createFailed')) }
}

async function selectSession(id: string, title?: string) {
  currentSession.value = id
  currentTitle.value = title || t('chat.sessionId', { id })
  showSessions.value = false
  loading.value = true
  try {
    const detail = await ChatAPI.getDetail(id)
    // 兼容后端可能返回 { messages: [] } 或 { data: { messages: [] } } 两种结构
    const detailRes = detail as { messages?: ChatMessage[], data?: { messages?: ChatMessage[] } }
    const msgs = detailRes?.messages || detailRes?.data?.messages || []
    resetWindow()
    messages.value = msgs.map(m => ({ role: m.role || 'ai', content: m.content || '', time: String(m.created_at || m.time || '') }))
  }
  catch {
    messages.value = []
    toast.error(t('chat.loadMessagesFailed'))
  }
  finally { loading.value = false }
}

async function deleteSession(id: string) {
  uni.showModal({
    title: t('common.title'),
    content: t('chat.deleteConfirm'),
    success: async (r) => {
      if (r.confirm) {
        try {
          await ChatAPI.removeSession([id])
          sessions.value = sessions.value.filter(s => s.id !== id)
          if (currentSession.value === id) {
            currentSession.value = null
            currentTitle.value = t('chat.title')
            messages.value = []
          }
          toast.success(t('chat.deleted'))
        }
        catch { toast.error(t('chat.deleteFailed')) }
      }
    },
  })
}

/** 重命名会话（参照 web 端侧边栏的重命名入口） */
function renameSession(session: ChatSession) {
  uni.showModal({
    title: t('chat.rename'),
    content: session.title || session.session_name || '',
    editable: true,
    placeholderText: t('chat.renamePlaceholder'),
    success: async (r) => {
      if (!r.confirm)
        return
      const title = (r.content || '').trim()
      if (!title)
        return toast.warning(t('chat.renameEmpty'))
      try {
        await ChatAPI.updateSession(session.id, { title })
        session.title = title
        if (currentSession.value === session.id)
          currentTitle.value = title
        toast.success(t('chat.renameSuccess'))
      }
      catch { toast.error(t('chat.renameFailed')) }
    },
  })
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || streaming.value)
    return
  // 无会话时自动创建，避免"请先创建会话"的额外步骤
  let sid = currentSession.value
  if (!sid) {
    try {
      const res = await ChatAPI.createSession()
      // 兼容后端可能返回 { data: ChatSession } 或直接 ChatSession 两种结构
      const newSession = (res as { data?: ChatSession })?.data ?? (res as ChatSession)
      if (newSession?.id) {
        sessions.value.unshift(newSession)
        sid = newSession.id
        currentSession.value = sid
        currentTitle.value = newSession.title || t('chat.title')
      }
      else {
        return toast.error(t('chat.createFailed'))
      }
    }
    catch {
      return toast.error(t('chat.createFailed'))
    }
  }

  messages.value.push({ role: 'user', content: text, time: new Date().toLocaleTimeString() })
  inputText.value = ''
  // 占位 AI 消息，流式分片实时追加（打字机效果）
  messages.value.push({ role: 'ai', content: '', time: new Date().toLocaleTimeString() })
  // 必须取数组内的响应式代理来改写：直接改裸对象不会触发视图更新（mp-html 收不到新 content）
  const aiMsg = messages.value[messages.value.length - 1]
  scrollToBottom()

  await streamChat.sendMessage({ message: text, session_id: String(sid) }, {
    onChunk: (chunk) => {
      aiMsg.content += chunk
      scrollToBottom()
    },
    onDone: () => {
      if (!aiMsg.content)
        aiMsg.content = t('chat.noReply')
    },
    onError: (err) => {
      aiMsg.content = err || t('chat.requestFailed')
    },
  })
}

/** 停止当前生成 */
function stopGenerate() {
  streamChat.stop()
}

/** 滚动到最新一条消息 */
function scrollToBottom() {
  scrollTarget.value = `msg-${visibleMessages.value.length - 1}`
  nextTick(() => {
    scrollTarget.value = ''
  })
}

onUnload(() => {
  streamChat.close()
})

onLoad(() => {
  loadSessions()
})
</script>

<template>
  <view class="page-wraper" style="display:flex;flex-direction:column;">
    <!-- Header -->
    <view class="wot-bg-filled-oppo wot-border-border-main wot-gap-extra-tight wot-p-tight flex items-center" style="border-bottom:1px solid;">
      <wd-button size="small" variant="plain" @click="showSessions = !showSessions">
        <wd-icon name="menu" size="16px" />
      </wd-button>
      <wd-text class="text-md flex-1 truncate text-center" :text="currentTitle" bold />
      <wd-button size="small" type="primary" variant="plain" @click="createSession">
        <wd-icon name="plus" size="16px" />
      </wd-button>
    </view>

    <!-- Session panel overlay -->
    <view v-if="showSessions" class="session-overlay wot-bg-filled-oppo" style="position:absolute;top:88rpx;left:0;right:0;bottom:0;z-index:100;overflow-y:auto;">
      <view class="p-sm">
        <view class="mb-md flex items-center justify-between px-xs">
          <wd-text class="text-lg" :text="t('chat.sessionList')" bold />
          <wd-button size="small" type="primary" @click="createSession">
            {{ t('chat.new') }}
          </wd-button>
        </view>
        <!-- 搜索会话历史 -->
        <wd-search v-model="searchQuery" :placeholder="t('chat.searchPlaceholder')" hide-cancel class="mb-md" />
        <SkeletonPage v-if="loading && sessions.length === 0" />
        <template v-else>
          <!-- 按时间分组（今天/昨天/本周/更早），组标题可折叠 -->
          <view v-for="group in groupedSessions" :key="group.key" class="mb-md">
            <view
              class="mb-xs flex items-center justify-between px-xs"
              @click="toggleGroup(group.key)"
            >
              <wd-text class="wot-text-text-auxiliary text-2.5 font-medium" :text="t(`chat.group${group.key[0].toUpperCase()}${group.key.slice(1)}`, { count: group.list.length })" />
              <wd-icon
                name="arrow-down"
                size="14px"
                color="var(--wot-text-auxiliary)"
                :style="{ transform: collapsedGroups.has(group.key) ? 'rotate(-90deg)' : 'none', transition: 'transform .2s' }"
              />
            </view>
            <template v-if="!collapsedGroups.has(group.key)">
              <view v-for="s in group.list" :key="s.id" class="admin-card" @click="selectSession(s.id, s.title)">
                <wd-cell
                  :title="s.title || s.session_name || t('chat.untitled')"
                  :label="formatSessionTime(s.updated_at ?? s.created_at)"
                  center
                  clickable
                  :class="currentSession === s.id ? 'wot-text-primary-6' : ''"
                >
                  <template #default>
                    <view class="flex items-center gap-sm">
                      <wd-icon name="edit" size="18px" color="var(--wot-text-auxiliary)" @click.stop="renameSession(s)" />
                      <wd-icon name="delete" size="18px" color="var(--wot-danger-main)" @click.stop="deleteSession(s.id)" />
                    </view>
                  </template>
                </wd-cell>
              </view>
            </template>
          </view>
          <wd-empty v-if="!loading && filteredSessions.length === 0" :tip="searchQuery.trim() ? t('chat.noMatch') : t('chat.empty')" />
        </template>
      </view>
    </view>

    <!-- Messages -->
    <scroll-view
      scroll-y
      class="chat-messages wot-p-tight"
      style="flex:1;"
      :scroll-into-view="scrollTarget || `msg-${visibleMessages.length - 1}`"
      :scroll-with-animation="true"
    >
      <!-- 窗口化渲染：仅渲染最近 N 条消息，支持加载更早消息 -->
      <view v-if="hasOlderMessages" style="padding:16rpx 0;text-align:center;">
        <wd-button size="small" variant="plain" @click="loadOlderMessages">
          {{ t('chat.loadMore', { count: messages.length - visibleMessages.length }) }}
        </wd-button>
      </view>
      <view v-for="(msg, i) in visibleMessages" :id="`msg-${i}`" :key="i" style="margin-bottom:24rpx;">
        <view class="flex items-start gap-sm" :class="msg.role === 'user' ? 'flex-row-reverse' : ''">
          <view
            v-if="msg.role === 'user'"
            class="h-8 w-8 flex shrink-0 items-center justify-center rounded-full"
            style="background: linear-gradient(135deg, var(--wot-primary-6), var(--wot-primary-7));"
          >
            <wd-icon name="user" size="18px" color="#FFFFFF" />
          </view>
          <view
            class="max-w-[72%] break-words px-3 py-2"
            :class="msg.role === 'user' ? 'wot-bg-primary-6 wot-text-text-white' : 'wot-bg-filled-oppo wot-text-text-main wot-border-border-main'"
            :style="{
              borderRadius: msg.role === 'user' ? '16rpx 16rpx 4rpx 16rpx' : '16rpx 16rpx 16rpx 4rpx',
              border: msg.role === 'user' ? 'none' : '1px solid',
            }"
          >
            <!-- AI 消息渲染 markdown；用户消息保持纯文本 -->
            <template v-if="msg.role !== 'user'">
              <wd-loading v-if="streaming && !msg.content" />
              <mp-html v-else :content="msg.content" markdown :tag-style="MARKDOWN_TAG_STYLE" />
            </template>
            <wd-text v-else style="white-space:pre-wrap;font-size:var(--font-sm,24rpx);line-height:1.7;" :text="msg.content" />
            <wd-text v-if="msg.time" style="font-size:var(--font-xs,20rpx);opacity:0.6;margin-top:8rpx;display:block;" :style="msg.role === 'user' ? 'text-align:right' : 'text-align:left'" :text="msg.time" />
          </view>
        </view>
      </view>
    </scroll-view>

    <!-- Input -->
    <view class="wot-bg-filled-oppo wot-border-border-main wot-p-tight" style="border-top:1px solid;padding-bottom:calc(24rpx + env(safe-area-inset-bottom, 0px));">
      <view class="flex items-center gap-sm">
        <wd-input v-model="inputText" :placeholder="t('chat.inputPlaceholder')" :disabled="streaming" class="flex-1" confirm-type="send" @confirm="sendMessage" />
        <wd-button v-if="streaming" type="danger" variant="plain" @click="stopGenerate">
          {{ t('chat.stop') }}
        </wd-button>
        <wd-button v-else :disabled="!inputText.trim()" type="primary" @click="sendMessage">
          {{ t('common.send') }}
        </wd-button>
      </view>
    </view>
  </view>
</template>
