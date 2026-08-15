<script setup>
import { onMounted, ref } from 'vue'

const props = defineProps({
  api: {
    type: Object,
    default: () => ({}),
  },
  initialConfig: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['save', 'close'])

const loading = ref(true)
const saving = ref(false)
const error = ref('')
const savedMessage = ref('')
const config = ref({
  enabled: false,
  notify: false,
  onlyonce: false,
  clear_cache: false,
  monitor_dirs: '',
  video_exts: 'mp4,mkv,avi,ts',
  sub_exts: 'ass,ssa,srt,sup',
})

async function loadConfig() {
  loading.value = true
  error.value = ''
  try {
    if (props.initialConfig && Object.keys(props.initialConfig).length > 0) {
      config.value = { ...config.value, ...props.initialConfig, clear_cache: false }
      return
    }
    const result = await props.api.get('plugin/form/AutoSubRename')
    if (result?.model) {
      config.value = { ...config.value, ...result.model, clear_cache: false }
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function saveConfig() {
  saving.value = true
  error.value = ''
  savedMessage.value = ''
  try {
    const payload = { ...config.value }
    if (props.initialConfig && Object.keys(props.initialConfig).length > 0) {
      emit('save', payload)
      config.value.clear_cache = false
      savedMessage.value = '设置已保存'
      return
    }
    const result = await props.api.put('plugin/AutoSubRename', payload)
    if (!result?.success) {
      throw new Error(result?.message || '保存设置失败')
    }
    config.value.clear_cache = false
    savedMessage.value = '设置已保存'
    await loadConfig()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    saving.value = false
  }
}

async function clearCache() {
  config.value.clear_cache = true
  await saveConfig()
}

onMounted(loadConfig)
</script>

<template>
  <div class="autosubrename-page pa-4">
    <VToolbar density="comfortable" color="transparent">
      <div class="text-h6">剧集字幕重命名设置</div>
      <VSpacer />
      <VBtn icon="mdi-refresh" variant="text" :loading="loading" @click="loadConfig" />
      <VBtn icon="mdi-content-save" variant="text" color="primary" :loading="saving" @click="saveConfig" />
      <VBtn icon="mdi-close" variant="text" @click="emit('close')" />
    </VToolbar>
    <VDivider class="mb-4" />

    <VAlert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</VAlert>
    <VAlert v-if="savedMessage" type="success" variant="tonal" class="mb-4">{{ savedMessage }}</VAlert>

    <VRow>
      <VCol cols="12" md="3">
        <VSwitch v-model="config.enabled" label="启用插件" :disabled="loading || saving" />
      </VCol>
      <VCol cols="12" md="3">
        <VSwitch v-model="config.notify" label="发送通知" :disabled="loading || saving" />
      </VCol>
      <VCol cols="12" md="3">
        <VSwitch v-model="config.onlyonce" label="立即运行一次" :disabled="loading || saving" />
      </VCol>
      <VCol cols="12" md="3">
        <VSwitch
          v-model="config.clear_cache"
          label="一键清除重命名记录缓存"
          :disabled="loading || saving"
          @update:model-value="value => value && clearCache()"
        />
      </VCol>
    </VRow>

    <VTextarea
      v-model="config.monitor_dirs"
      label="监控目录"
      rows="3"
      placeholder="每行一个目录路径（支持子目录监控）"
      :disabled="loading || saving"
      class="mb-4"
    />

    <VRow>
      <VCol cols="12" md="6">
        <VTextField
          v-model="config.video_exts"
          label="视频扩展名"
          placeholder="多个用逗号分隔"
          :disabled="loading || saving"
        />
      </VCol>
      <VCol cols="12" md="6">
        <VTextField
          v-model="config.sub_exts"
          label="字幕扩展名"
          placeholder="多个用逗号分隔，例如 ass,ssa,srt,sup"
          :disabled="loading || saving"
        />
      </VCol>
    </VRow>

    <VAlert type="info" variant="tonal" class="mt-4">
      设置会直接保存到 MoviePilot；清除缓存只清除已处理路径记录，不会删除任何视频或字幕文件。
    </VAlert>
  </div>
</template>
