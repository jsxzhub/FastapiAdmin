<!-- 小程序滑块拼图：点击入口展开弹层，拖动图块到位后交给后端校验 -->
<template>
  <view class="fa-puzzle" :class="{ 'is-passed': passed }">
    <!-- 入口：与 web 端一致，点击后换题并展开拼图弹层 -->
    <view class="fa-puzzle__entry" @click="requestPanel">
      <wd-icon :name="passed ? 'check' : 'lock'" size="16px" />
      <text class="fa-puzzle__entry-text">{{ passed ? successText : entryText }}</text>
      <wd-icon v-if="!passed" name="arrow-right" size="14px" class="fa-puzzle__entry-arrow" />
    </view>

    <!-- 弹层：v-show 保留轨道 DOM，H5 的 pointerdown 监听在 mounted 时即可绑定 -->
    <view v-show="panelOpen" class="fa-puzzle__overlay" @click="closePanel">
      <view class="fa-puzzle__dialog" @click.stop>
        <view class="fa-puzzle__close" @click="closePanel">
          <wd-icon name="close" size="18px" />
        </view>
        <text class="fa-puzzle__title">{{ titleText }}</text>

        <view class="fa-puzzle__stage">
          <image v-if="bgImage" class="fa-puzzle__bg" :src="bgImage" mode="scaleToFill" />
          <image
            v-if="pieceImage"
            class="fa-puzzle__piece"
            :src="pieceImage"
            mode="scaleToFill"
            :style="pieceStyle"
          />
          <view class="fa-puzzle__refresh" @click.stop="emit('refresh')">
            <wd-icon name="refresh" size="16px" />
          </view>
          <view v-if="loading" class="fa-puzzle__mask">
            <wd-loading size="20px" />
          </view>
        </view>

        <view
          ref="trackRef"
          class="fa-puzzle__track"
          :class="{ 'is-passed': passed, 'is-dragging': dragging }"
          @touchstart.prevent="onTouchStart"
          @touchmove.prevent="onTouchMove"
          @touchend="onTouchEnd"
          @touchcancel="onTouchEnd"
        >
          <view class="fa-puzzle__fill" :style="{ width: `${fillWidth}%` }" />
          <view class="fa-puzzle__button" :style="{ transform: `translateX(${buttonX}px)` }">
            <wd-icon :name="passed ? 'check' : 'double-right'" size="20px" />
          </view>
          <text class="fa-puzzle__text">{{ passed ? successText : text }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { getCurrentInstance, onBeforeUnmount, onMounted } from 'vue'

defineOptions({ name: 'FaPuzzleCaptcha' })

interface Props {
  bgImage: string
  pieceImage: string
  pieceY?: number
  pieceWidth?: number
  pieceHeight?: number
  bgWidth?: number
  bgHeight?: number
  passed?: boolean
  loading?: boolean
  text: string
  titleText: string
  successText: string
  entryText: string
}

const props = withDefaults(defineProps<Props>(), {
  pieceY: 0,
  pieceWidth: 55,
  pieceHeight: 48,
  bgWidth: 320,
  bgHeight: 160,
  passed: false,
  loading: false,
})

const emit = defineEmits<{
  verify: [position: number]
  refresh: []
  request: []
}>()

// 单一声明，H5 构建时置为 true（条件编译注释对 tsc 不可见，不能声明两次）
let isH5 = false
// #ifdef H5
isH5 = true
// #endif

const instance = getCurrentInstance()
const trackRef = ref<{ $el?: HTMLElement } | HTMLElement | null>(null)
const panelOpen = ref(false)
const progress = ref(0)
const dragging = ref(false)
const trackLeft = ref(0)
const trackWidth = ref(0)
/** 滑块按钮尺寸（px）— CSS 中按钮宽高同为轨道高度，度量轨道时一并取到 */
const buttonSize = ref(44)

const pieceStyle = computed(() => ({
  left: `${progress.value * (100 - (props.pieceWidth / props.bgWidth) * 100)}%`,
  top: `${(props.pieceY / props.bgHeight) * 100}%`,
  width: `${(props.pieceWidth / props.bgWidth) * 100}%`,
  height: `${(props.pieceHeight / props.bgHeight) * 100}%`,
}))

const fillWidth = computed(() => (props.passed ? 100 : progress.value * 100))

const buttonX = computed(() => {
  const max = Math.max(0, trackWidth.value - buttonSize.value)
  return props.passed ? max : progress.value * max
})

function measureTrack(): Promise<void> {
  return new Promise((resolve) => {
    const query = uni.createSelectorQuery().in(instance?.proxy as object)
    query
      .select('.fa-puzzle__track')
      .boundingClientRect((rect) => {
        const box = rect as UniApp.NodeInfo | null
        if (box) {
          trackLeft.value = box.left ?? 0
          trackWidth.value = box.width ?? 0
          if (box.height)
            buttonSize.value = box.height
        }
        resolve()
      })
      .exec()
  })
}

function clamp(value: number): number {
  return Math.min(1, Math.max(0, value))
}

function updateFromClientX(clientX: number) {
  if (trackWidth.value <= buttonSize.value)
    return
  progress.value = clamp((clientX - trackLeft.value - buttonSize.value / 2) / (trackWidth.value - buttonSize.value))
}

function updateFromTouch(event: TouchEvent) {
  const touch = event.touches?.[0] ?? event.changedTouches?.[0]
  if (!touch)
    return
  updateFromClientX(touch.clientX ?? touch.pageX ?? 0)
}

/** 结束拖动：未越过起始阈值则回弹，否则交回父组件做位置校验 */
function finishDrag() {
  if (!dragging.value)
    return
  dragging.value = false
  if (progress.value <= 0.03) {
    progress.value = 0
    return
  }
  const max = Math.max(0, props.bgWidth - props.pieceWidth)
  emit('verify', Math.round(progress.value * max))
}

function onTouchStart(event: TouchEvent) {
  // H5 统一走 pointer 事件，避免触摸时 touch/pointer 同时驱动
  if (isH5)
    return
  if (props.passed || props.loading)
    return
  dragging.value = true
  void measureTrack().then(() => updateFromTouch(event))
}

function onTouchMove(event: TouchEvent) {
  if (isH5 || !dragging.value)
    return
  updateFromTouch(event)
}

function onTouchEnd() {
  if (isH5)
    return
  finishDrag()
}

// #ifdef H5
/** H5 取轨道 DOM 元素（view 在 H5 可能是原生自定义元素或其组件实例） */
function getTrackElement(): HTMLElement | null {
  const current = trackRef.value
  if (!current)
    return null
  if (current instanceof HTMLElement)
    return current
  return current.$el ?? null
}

function onPointerDown(event: PointerEvent) {
  if (props.passed || props.loading)
    return
  event.preventDefault()
  dragging.value = true
  void measureTrack().then(() => updateFromClientX(event.clientX))
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp, { once: true })
  window.addEventListener('pointercancel', onPointerUp, { once: true })
}

function onPointerMove(event: PointerEvent) {
  if (!dragging.value)
    return
  updateFromClientX(event.clientX)
}

function onPointerUp() {
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
  finishDrag()
}

onMounted(() => {
  getTrackElement()?.addEventListener('pointerdown', onPointerDown, { passive: false })
})

onBeforeUnmount(() => {
  getTrackElement()?.removeEventListener('pointerdown', onPointerDown)
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
})
// #endif

function reset() {
  progress.value = 0
  dragging.value = false
}

/** 点击入口：交给父组件换一张新题，再回调 open() 展开弹层（与 web 端一致） */
function requestPanel() {
  if (props.loading)
    return
  emit('request')
}

function openPanel() {
  if (props.loading)
    return
  panelOpen.value = true
}

function closePanel() {
  panelOpen.value = false
  reset()
}

watch(
  () => props.bgImage,
  () => reset(),
)

watch(
  () => props.passed,
  (value) => {
    if (value)
      setTimeout(closePanel, 700)
  },
)

defineExpose({ reset, open: openPanel })
</script>

<style scoped lang="scss">
.fa-puzzle {
  width: 100%;
}

.fa-puzzle__entry {
  display: flex;
  gap: 12rpx;
  align-items: center;
  box-sizing: border-box;
  width: 100%;
  height: 88rpx;
  padding: 0 28rpx;
  font-size: 28rpx;
  color: var(--fa-text-secondary, #5b6472);
  background: #fff;
  border: 2rpx solid var(--fa-border, #e6e8ec);
  border-radius: var(--fa-radius-sm, 16rpx);
}

.fa-puzzle__entry-text {
  flex: 1;
}

.fa-puzzle__entry-arrow {
  opacity: 0.55;
}

.fa-puzzle.is-passed .fa-puzzle__entry {
  color: var(--wot-success-5, #22c55e);
  border-color: var(--wot-success-5, #22c55e);
}

.fa-puzzle__overlay {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgb(0 0 0 / 45%);
}

.fa-puzzle__dialog {
  position: relative;
  box-sizing: border-box;
  width: 620rpx;
  max-width: 90vw;
  padding: 36rpx 28rpx 28rpx;
  background: #fff;
  border-radius: 24rpx;
}

.fa-puzzle__close {
  position: absolute;
  top: 16rpx;
  right: 16rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56rpx;
  height: 56rpx;
  color: var(--fa-text-secondary, #5b6472);
}

.fa-puzzle__title {
  display: block;
  margin-bottom: 20rpx;
  font-size: 30rpx;
  font-weight: 600;
  color: var(--fa-text-primary, #1f2937);
  text-align: center;
}

.fa-puzzle__stage {
  position: relative;
  width: 100%;
  padding-bottom: 50%;
  overflow: hidden;
  background: #10131c;
  border-radius: var(--fa-radius-sm, 16rpx);
}

.fa-puzzle__bg,
.fa-puzzle__piece {
  position: absolute;
}

.fa-puzzle__bg {
  inset: 0;
  width: 100%;
  height: 100%;
}

.fa-puzzle__piece {
  filter: drop-shadow(0 4rpx 8rpx rgb(0 0 0 / 45%));
}

.fa-puzzle__refresh {
  position: absolute;
  top: 12rpx;
  right: 12rpx;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52rpx;
  height: 52rpx;
  color: #fff;
  background: rgb(0 0 0 / 38%);
  border-radius: 12rpx;
}

.fa-puzzle__mask {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgb(0 0 0 / 30%);
}

.fa-puzzle__track {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 88rpx;
  margin-top: 16rpx;
  overflow: hidden;
  touch-action: none;
  background: var(--fa-canvas, #f5f6f8);
  border: 2rpx solid var(--fa-border, #e6e8ec);
  border-radius: var(--fa-radius-sm, 16rpx);
}

.fa-puzzle__fill {
  position: absolute;
  inset: 0 auto 0 0;
  background: linear-gradient(90deg, #4f6bff, #6d5bff);
  opacity: 0.28;
  transition: width 0.2s ease;
}

.fa-puzzle__button {
  position: absolute;
  top: 0;
  left: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 88rpx;
  height: 100%;
  color: var(--wot-primary-6, #4f6bff);
  background: #fff;
  border: 2rpx solid var(--wot-primary-2, #dce2ff);
  border-radius: var(--fa-radius-sm, 16rpx);
  box-shadow: 0 4rpx 12rpx rgb(15 23 42 / 10%);
  transition: transform 0.2s ease;
}

.fa-puzzle__text {
  position: relative;
  z-index: 1;
  font-size: 26rpx;
  color: var(--fa-text-secondary, #5b6472);
  pointer-events: none;
}

.wot-theme-dark .fa-puzzle__entry {
  background: #15181e;
  border-color: #262b34;
}

.wot-theme-dark .fa-puzzle__dialog {
  background: #15181e;
}

.wot-theme-dark .fa-puzzle__title {
  color: #e5e7eb;
}

.wot-theme-dark .fa-puzzle__track {
  background: #191d24;
  border-color: #262b34;
}

.wot-theme-dark .fa-puzzle__button {
  background: #15181e;
  border-color: #262b34;
}

.wot-theme-dark .fa-puzzle__text {
  color: #a3aab8;
}

.fa-puzzle.is-passed,
.fa-puzzle__track.is-passed {
  border-color: var(--wot-success-5, #22c55e);
}

.fa-puzzle__track.is-passed .fa-puzzle__fill {
  background: var(--wot-success-5, #22c55e);
  opacity: 0.22;
}

.fa-puzzle__track.is-passed .fa-puzzle__button {
  color: var(--wot-success-5, #22c55e);
  border-color: var(--wot-success-5, #22c55e);
}

.fa-puzzle__track.is-passed .fa-puzzle__text {
  color: var(--wot-success-5, #22c55e);
}
</style>
