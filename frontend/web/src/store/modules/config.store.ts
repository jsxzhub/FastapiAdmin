/**
 * 系统配置状态管理模块
 *
 * 提供系统配置参数的状态管理
 *
 * ## 主要功能
 *
 * - 网站基础信息管理（标题、版本、描述）
 * - 网站图标配置（登录背景、favicon、Logo）
 * - 安全隐私配置（服务条款、版权、隐私政策）
 * - 接口安全配置（白名单、黑名单）
 * - 演示环境配置
 *
 * ## 使用场景
 *
 * - 系统初始化配置加载
 * - 登录页背景和Logo显示
 * - 底部版权信息展示
 * - 接口安全控制
 *
 * ## 持久化
 *
 * - 使用 localStorage 存储
 * - 自动缓存已加载的配置
 * - 支持强制刷新配置
 *
 * @module store/modules/config.store
 * @author FastapiAdmin Team
 */
import { store } from "@stores";
import ParamsAPI, { ConfigTable } from "@/api/module_system/params";

import { defineStore } from "pinia";
import { ref } from "vue";

export const useConfigStore = defineStore(
  "configStore",
  () => {
    // 配置数据
    const configData = ref<Record<string, ConfigTable>>({});
    // 是否已加载配置
    const isConfigLoaded = ref(false);
    // 是否正在加载配置
    const configLoading = ref(false);
    // 最近一次 fetch 时间戳，用于 force=true 时防止短期重复请求
    let _lastFetchedAt = 0;
    const MIN_FETCH_INTERVAL_MS = 5000;

    /**
     * 获取系统配置
     * @param force 是否强制刷新配置
     */
    async function getConfig(force = false) {
      if (configLoading.value) {
        return;
      }
      // force=true 时也需防短期内重复请求
      if (!force && isConfigLoaded.value) {
        return;
      }
      if (force && Date.now() - _lastFetchedAt < MIN_FETCH_INTERVAL_MS) {
        return;
      }
      configLoading.value = true;
      try {
        // 注意：不要在请求前清空 configData。
        // 清空会让依赖它的位置（顶栏/侧栏 logo、系统名称、登录页背景等）
        // 在接口返回前回退到内置默认值，出现「先闪一下旧 logo」的现象。
        // 新数据由 applyConfigList 一次性整体替换。

        // 获取系统级配置（演示模式、IP黑白名单等）
        const response = await ParamsAPI.getInitConfig();
        const list = response?.data?.data;
        if (!Array.isArray(list)) {
          console.warn("[configStore] getInitConfig: 响应 data 非数组", response?.data);
          return;
        }
        applyConfigList(list);
      } catch (error) {
        console.warn("[configStore] 获取配置失败:", error);
      } finally {
        configLoading.value = false;
      }
    }

    function applyConfigList(list: ConfigTable[]) {
      const next: Record<string, ConfigTable> = {};
      list.forEach((item: ConfigTable) => {
        if (item.config_value !== undefined && item.config_key) {
          next[item.config_key] = item;
        }
      });
      // 整体替换：既不出现「空配置」中间态（避免 logo 闪烁），
      // 也能正确丢弃后端已删除的参数
      configData.value = next;
      isConfigLoaded.value = true;
      _lastFetchedAt = Date.now();
    }

    return {
      configData,
      isConfigLoaded,
      configLoading,
      getConfig,
    };
  },
  {
    persist: {
      key: "config",
      storage: localStorage,
      pick: ["configData", "isConfigLoaded"],
    },
  }
);

export function useConfigStoreHook() {
  return useConfigStore(store);
}
