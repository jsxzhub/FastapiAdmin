import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/store/userStore'

export interface AiChatStreamHandlers {
  /** 收到内容分片（追加到当前 AI 消息） */
  onChunk?: (text: string) => void
  /** 生成结束（[DONE] / [STOPPED]） */
  onDone?: () => void
  /** 连接或生成错误 */
  onError?: (message: string) => void
}

/**
 * 构建 AI 对话 WebSocket 连接参数：优先 VITE_APP_WS_ENDPOINT，否则从 API 域名推导（http→ws）
 * token 通过 Sec-WebSocket-Protocol 子协议携带（access_token.<jwt>），不进入 URL / 网关 access log，
 * 后端 app/core/dependencies.py:get_websocket_token 读取子协议。
 */
function buildChatWsOptions(): { url: string, protocols: string[] } {
  const userStore = useUserStore()
  const token = userStore.getAccessToken() || ''
  let wsBase = import.meta.env.VITE_APP_WS_ENDPOINT || ''
  if (!wsBase) {
    const apiBase = import.meta.env.VITE_API_BASE_URL || ''
    wsBase = apiBase.replace(/^http/, 'ws')
  }
  const apiPrefix = import.meta.env.VITE_APP_BASE_API || '/api/v1'
  // 子协议列表：含 jwt 的 access_token.<jwt> 用于鉴权；纯 access_token 便于握手协商回显
  const protocols = token ? ['access_token', `access_token.${token}`] : ['access_token']
  return { url: `${wsBase}${apiPrefix}/ai/chat/ws`, protocols }
}

/**
 * AI 对话流式输出（WebSocket）
 * 协议（对应后端 /ai/chat/ws）：
 * - 发送：{"message": "...", "session_id": "..."} | {"action": "stop"}
 * - 接收：内容分片（纯文本）→ [DONE] 结束 / [STOPPED] 停止确认
 */
export function useAiChat() {
  const { t } = useI18n()
  const isStreaming = ref(false)
  let socketTask: ReturnType<typeof uni.connectSocket> | null = null
  let pendingOpen: Promise<void> | null = null
  let resolveOpen: (() => void) | null = null
  let closedByUser = false
  let handlers: AiChatStreamHandlers = {}

  function ensureConnected(): Promise<void> {
    if (socketTask)
      return Promise.resolve()
    closedByUser = false
    pendingOpen = new Promise<void>((resolve) => {
      resolveOpen = resolve
    })
    const task = uni.connectSocket({ ...buildChatWsOptions(), complete: () => {} })
    socketTask = task
    task.onOpen(() => resolveOpen?.())
    task.onMessage((res) => {
      const text = typeof res.data === 'string' ? res.data : ''
      if (text === '[DONE]' || text === '[STOPPED]') {
        isStreaming.value = false
        handlers.onDone?.()
      }
      else if (text) {
        handlers.onChunk?.(text)
      }
    })
    task.onError((err) => {
      resolveOpen?.()
      isStreaming.value = false
      handlers.onError?.(err?.errMsg || t('chat.wsConnectFailed'))
    })
    task.onClose(() => {
      socketTask = null
      if (!closedByUser) {
        isStreaming.value = false
        handlers.onError?.(t('chat.wsDisconnected'))
      }
    })
    return pendingOpen
  }

  /** 发送一条流式对话消息（自动建立/复用连接） */
  async function sendMessage(
    payload: { message: string, session_id?: string | null },
    handler: AiChatStreamHandlers,
  ): Promise<void> {
    handlers = handler
    isStreaming.value = true
    try {
      await ensureConnected()
      socketTask?.send({
        data: JSON.stringify({ message: payload.message, session_id: payload.session_id || undefined }),
      })
    }
    catch {
      isStreaming.value = false
      handlers.onError?.(t('chat.wsSendFailed'))
    }
  }

  /** 停止当前生成（后端停止后返回 [STOPPED]） */
  function stop() {
    if (!isStreaming.value)
      return
    try {
      socketTask?.send({ data: JSON.stringify({ action: 'stop' }) })
    }
    catch { /* 忽略发送失败 */ }
  }

  /** 关闭连接（页面卸载时调用） */
  function close() {
    closedByUser = true
    isStreaming.value = false
    if (socketTask) {
      socketTask.close({ code: 1000, reason: 'page unload' })
      socketTask = null
    }
  }

  return { isStreaming, sendMessage, stop, close }
}
