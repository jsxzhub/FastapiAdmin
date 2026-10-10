<!-- 登录页：顶栏固定；仅插画列与表单区随布局切换 -->
<template>
  <div class="login-page-root flex h-screen w-full flex-col overflow-hidden" :style="loginBgStyle">
    <FaLoginCenterBackdrop v-if="panelAlign === 'center'" viewport-fixed />
    <FaAuthTopBar v-model:panel-align="panelAlign" />

    <div
      class="login-auth-split relative z-1 flex min-h-0 flex-1 overflow-hidden"
      :class="`login-auth-split--${panelAlign}`"
    >
      <div
        v-if="panelAlign !== 'center'"
        class="login-auth-split__col login-auth-split__col--illustration"
      >
        <FaLoginLeftView hide-top-branding />
      </div>

      <div
        class="login-auth-split__col login-auth-split__col--form login-page-panel relative flex min-h-0 min-w-0 flex-col"
        :class="panelAlign === 'center' ? 'bg-transparent' : 'bg-(--fa-canvas)'"
      >
        <div
          class="login-page-panel__main relative z-1 flex min-h-0 flex-1 flex-col overflow-hidden px-5 pb-2 pt-14 md:px-10 md:pt-18"
        >
          <ElScrollbar>
            <div
              class="login-page-panel__scroll pb-6"
              :class="panelAlign === 'center' && 'login-page-panel__scroll--centered'"
            >
              <div
                class="login-panel-align-row flex w-full items-center justify-center max-sm:min-h-0"
                :class="
                  panelAlign === 'center'
                    ? 'min-h-0 flex-1 py-4'
                    : 'min-h-[min(720px,calc(100vh-13rem))]'
                "
              >
                <div class="auth-right-wrap">
                  <div class="form">
                    <div class="form-intro">
                      <h3 class="title">{{ panelTitle }}</h3>
                      <p class="sub-title">{{ panelSubTitle }}</p>
                    </div>

                    <FaLoginAccountForm
                      v-if="authPanel === 'login'"
                      ref="accountFormRef"
                      v-model:is-passing="isPassing"
                      v-model:is-click-pass="isClickPass"
                      v-model:login-form="loginForm"
                      :rules="rules"
                      :captcha-state="captchaState"
                      :code-loading="codeLoading"
                      :demo-account-key="demoAccountKey"
                      :accounts="accounts"
                      :form-key="formKey"
                      :is-dark="isDark"
                      :drag-verify-text-color="dragVerifyTextColor"
                      :loading="loading"
                      @submit="handleSubmit"
                      @setup-account="setupAccount"
                      @get-captcha="getCaptcha"
                      @forget="setAuthPanel('forget')"
                      @slider-pass="handleSliderPass"
                      @request-puzzle="handlePuzzleRequest"
                    />

                    <FaLoginForgetPanel
                      v-else
                      ref="forgetPanelRef"
                      v-model:forget-form="forgetForm"
                      :forget-rules="forgetRules"
                      :form-key="formKey"
                      :forget-loading="forgetLoading"
                      @submit="submitForget"
                      @to-login="setAuthPanel('login')"
                    />
                  </div>
                </div>
              </div>
            </div>
          </ElScrollbar>
        </div>

        <footer
          class="login-page-footer login-page-footer--pinned shrink-0 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3"
          :class="panelAlign === 'center' && 'login-page-footer--floating-layout'"
        >
          <div class="login-footer-text text-sm">
            <div class="login-footer-row">
              <a
                :href="configStore.configData?.git_code?.config_value || '#'"
                target="_blank"
                rel="noopener noreferrer"
                class="login-page-footer__link"
              >
                {{ configStore.configData?.copyright?.config_value || "" }}
              </a>
            </div>
            <span class="login-page-footer__sep login-footer-sep-center">|</span>
            <div class="login-footer-row">
              <a
                :href="configStore.configData?.help_doc?.config_value || '#'"
                target="_blank"
                rel="noopener noreferrer"
                class="login-page-footer__link"
              >
                {{ $t("common.help") }}
              </a>
              <span class="login-page-footer__sep">|</span>
              <a
                :href="configStore.configData?.privacy?.config_value || '#'"
                target="_blank"
                rel="noopener noreferrer"
                class="login-page-footer__link"
              >
                {{ $t("common.privacy") }}
              </a>
              <span class="login-page-footer__sep">|</span>
              <a
                :href="configStore.configData?.clause?.config_value || '#'"
                target="_blank"
                rel="noopener noreferrer"
                class="login-page-footer__link"
              >
                {{ $t("common.terms") }}
              </a>
              <span
                v-if="configStore.configData?.keep_record?.config_value"
                class="login-page-footer__sep"
                >|</span
              >
              <span
                v-if="configStore.configData?.keep_record?.config_value"
                class="login-page-footer__record"
              >
                {{ configStore.configData.keep_record.config_value }}
              </span>
            </div>
          </div>
        </footer>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { LocationQuery, RouteLocationRaw } from "vue-router";
import AuthAPI, { type CaptchaInfo, type LoginFormData } from "@/api/module_system/auth";

import UserAPI, { type ForgetPasswordForm } from "@/api/module_system/user";
import { useConfigStore, useAppStore, useSettingsStore, useUserStore } from "@stores";
import { Auth, HttpError } from "@utils";
import { ElMessage, ElNotification } from "element-plus";
import type { FormRules } from "element-plus";
import type { Account, AccountKey } from "./types";
import { useLoginPanelAlign } from "./components/composables/useLoginPanelAlign";
import type FaLoginAccountForm from "./components/forms/FaLoginAccountForm.vue";
import type FaLoginForgetPanel from "./components/panels/FaLoginForgetPanel.vue";

defineOptions({ name: "Login" });

type AuthPanel = "login" | "forget";

const configStore = useConfigStore();
const settingStore = useSettingsStore();
const appStore = useAppStore();
const { isDark } = storeToRefs(settingStore);
const { t, locale } = useI18n();

const { panelAlign } = useLoginPanelAlign();

const authPanel = ref<AuthPanel>("login");

const panelTitle = computed(() => {
  if (authPanel.value === "forget") return t("login.resetPassword");
  return t("login.title");
});

const panelSubTitle = computed(() => {
  if (authPanel.value === "forget") return t("forgetPassword.subTitle");
  return t("login.subTitle");
});

function setAuthPanel(panel: AuthPanel) {
  authPanel.value = panel;
  nextTick(() => {
    accountFormRef.value?.clearValidate?.();
    forgetPanelRef.value?.clearValidate?.();
  });
}

async function tryConsumeOAuthCallback() {
  const q = route.query;
  const oauthError = q.oauth_error as string | undefined;
  const access = q.access_token as string | undefined;
  const refresh = q.refresh_token as string | undefined;

  if (!oauthError && !(access && refresh)) return;

  const rest: Record<string, unknown> = { ...q };
  delete rest.oauth_error;
  delete rest.access_token;
  delete rest.refresh_token;
  delete rest.token_type;

  if (oauthError) {
    ElMessage.error(decodeURIComponent(oauthError));
    await router.replace({ path: route.path, query: rest as LocationQuery });
    return;
  }

  if (access && refresh) {
    try {
      Auth.setTokens(access, refresh, true);
      userStore.setToken(access, refresh);
      userStore.setLoginStatus(true);
      ElNotification({
        title: t("login.oauthNoticeTitle"),
        message: t("login.oauthLoginSuccess"),
        type: "success",
      });
      await router.replace(resolveRedirectTarget(rest as LocationQuery));
      if (settingStore.showGuide) {
        appStore.showGuide(true);
      }
    } catch (error) {
      console.error("[Login] OAuth callback:", error);
      ElMessage.error(t("login.oauthLoginFailed"));
      await router.replace({ path: route.path, query: rest as LocationQuery });
    }
  }
}

const dragVerifyTextColor = computed(() =>
  isDark.value ? "rgba(255, 255, 255, 0.45)" : "var(--fa-gray-700)"
);
const formKey = ref(0);

watch(locale, () => {
  formKey.value++;
});

watch(authPanel, (panel) => {
  if (panel !== "login") return;
  getCaptcha();
  accountFormRef.value?.resetDragVerify?.();
  isPassing.value = false;
  isClickPass.value = false;
});

const accounts = computed<Account[]>(() => [
  {
    key: "super",
    label: t("login.roles.super"),
    username: "super",
    password: "123456",
    roles: ["R_SUPER"],
  },
  {
    key: "admin",
    label: t("login.roles.admin"),
    username: "admin",
    password: "123456",
    roles: ["R_ADMIN"],
  },
  {
    key: "user",
    label: t("login.roles.user"),
    username: "user",
    password: "123456",
    roles: ["R_USER"],
  },
]);

const demoAccountKey = ref<AccountKey>("super");
const userStore = useUserStore();
const router = useRouter();
const route = useRoute();
const isPassing = ref(false);
const isClickPass = ref(false);

const accountFormRef = ref<InstanceType<typeof FaLoginAccountForm> | null>(null);
const forgetPanelRef = ref<InstanceType<typeof FaLoginForgetPanel> | null>(null);

const loading = ref(false);
const forgetLoading = ref(false);
const codeLoading = ref(false);

const forgetForm = reactive<ForgetPasswordForm>({
  username: "",
});

const forgetRules = computed<FormRules<ForgetPasswordForm>>(() => ({
  username: [{ required: true, message: t("login.message.username.required"), trigger: "blur" }],
}));

const loginForm = reactive<LoginFormData>({
  username: "",
  password: "",
  captcha_key: "",
  remember: true,
  login_type: "PC端",
});

// —— 登录页背景 ——
const loginBgStyle = computed(() => {
  const bg = configStore.configData?.login_bg?.config_value?.trim();
  return bg
    ? { backgroundImage: `url(${bg})`, backgroundSize: "cover", backgroundPosition: "center" }
    : {};
});

const captchaState = reactive<CaptchaInfo>({
  enable: false,
  key: "",
  img_base: "",
  piece_base: "",
  piece_y: 0,
  piece_width: 55,
  piece_height: 48,
  bg_width: 320,
  bg_height: 160,
});

const rules = computed<FormRules>(() => {
  const base: FormRules = {
    username: [
      {
        required: true,
        trigger: "blur",
        message: t("login.message.username.required"),
      },
    ],
    password: [
      {
        required: true,
        trigger: "blur",
        message: t("login.message.password.required"),
      },
      {
        min: 6,
        message: t("login.message.password.min"),
        trigger: "blur",
      },
    ],
  };
  return base;
});

function setupAccount(key: AccountKey) {
  const selected = accounts.value.find((a: Account) => a.key === key);
  demoAccountKey.value = key;
  loginForm.username = selected?.username ?? "";
  loginForm.password = selected?.password ?? "";
}

async function getCaptcha() {
  try {
    codeLoading.value = true;
    const response = await AuthAPI.getCaptcha();
    const data = response.data.data;
    loginForm.captcha_key = data.key;
    captchaState.img_base = data.img_base ?? "";
    captchaState.piece_base = data.piece_base ?? "";
    captchaState.piece_y = data.piece_y ?? 0;
    captchaState.piece_width = data.piece_width ?? 55;
    captchaState.piece_height = data.piece_height ?? 48;
    captchaState.bg_width = data.bg_width ?? 320;
    captchaState.bg_height = data.bg_height ?? 160;
    captchaState.enable = data.enable;
    // 重置滑块状态
    isPassing.value = false;
    isClickPass.value = false;
  } catch {
    captchaState.enable = false;
    loginForm.captcha_key = "";
  } finally {
    codeLoading.value = false;
  }
}

/** 每次点击入口都换一张新题，再打开弹窗 */
async function handlePuzzleRequest() {
  await getCaptcha();
  accountFormRef.value?.openPuzzle?.();
}

/** 拼图滑块释放后交给后端校验位置 */
async function handleSliderPass(position: number) {
  if (!loginForm.captcha_key) return;
  try {
    await AuthAPI.sliderComplete(loginForm.captcha_key, position);
    isPassing.value = true;
  } catch {
    isPassing.value = false;
    accountFormRef.value?.resetDragVerify?.();
    await getCaptcha();
  }
}

function resolveRedirectTarget(query: LocationQuery): RouteLocationRaw {
  const defaultPath = "/";
  const rawRedirect = (query.redirect as string) || defaultPath;
  try {
    const resolved = router.resolve(rawRedirect);
    return {
      path: resolved.path,
      query: resolved.query,
    };
  } catch {
    return { path: defaultPath };
  }
}

onMounted(async () => {
  setupAccount("super");
  await configStore.getConfig(true);
  await tryConsumeOAuthCallback();
  if (userStore.isLogin) {
    await router.replace(resolveRedirectTarget(route.query));
    return;
  }
  getCaptcha();
});

onActivated(() => {
  if (authPanel.value !== "login") return;
  getCaptcha();
});

watch(
  () => route.fullPath,
  () => {
    if (authPanel.value !== "login") return;
    getCaptcha();
  }
);

const handleSubmit = async () => {
  if (!accountFormRef.value) return;

  try {
    const valid = await accountFormRef.value.validate?.();
    if (!valid) return;

    if (!isPassing.value) {
      isClickPass.value = true;
      return;
    }

    loading.value = true;

    await userStore.login(loginForm);
    await router.replace(resolveRedirectTarget(route.query));

    if (settingStore.showGuide) {
      appStore.showGuide(true);
    }
  } catch (error) {
    // 自增 formKey 强制重新挂载表单（滑块自动重置为初始状态）
    formKey.value++;
    await getCaptcha();
    if (!(error instanceof HttpError)) {
      console.error("[Login] Unexpected error:", error);
      ElNotification({
        title: "提示",
        message: error instanceof Error ? error.message : String(error),
        type: "error",
      });
    }
  } finally {
    loading.value = false;
  }
};

async function submitForget() {
  if (!forgetPanelRef.value) return;
  try {
    await forgetPanelRef.value.validate?.();
    forgetLoading.value = true;
    await UserAPI.forgetPassword(forgetForm);
    forgetForm.username = "";
    setAuthPanel("login");
  } catch (error) {
    console.error("[Login] forget password:", error);
  } finally {
    forgetLoading.value = false;
  }
}
</script>
