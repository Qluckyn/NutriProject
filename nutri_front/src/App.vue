<script setup>
import { computed, reactive, ref } from 'vue'
import { API_BASE } from './config'
import ImageUploader from './components/ImageUploader.vue'
import ResultPanel from './components/ResultPanel.vue'
import AssessmentPanel from './components/AssessmentPanel.vue'

const activeMainTab = ref('image')

const files = reactive({
  front: null,
  left: null,
  right: null,
})

const result = ref(null)
const errorMessage = ref('')
const isLoading = ref(false)
const resetToken = ref(0)

const uploaders = [
  { key: 'front', title: '正面（Front）', subtitle: '上传正面面部图像' },
  { key: 'left', title: '左45°（Left）', subtitle: '上传左45°面部图像' },
  { key: 'right', title: '右45°（Right）', subtitle: '上传右45°面部图像' },
]

const mainTabs = [
  { key: 'image', label: '面部图像筛查' },
  { key: 'assessment', label: '量表评估' },
]

const canSubmit = computed(() => Object.values(files).some(Boolean) && !isLoading.value)

function onFileChange(viewKey, file) {
  files[viewKey] = file
  result.value = null
  errorMessage.value = ''
}

function onUploadError(message) {
  errorMessage.value = message
}

function resetAll() {
  files.front = null
  files.left = null
  files.right = null
  result.value = null
  errorMessage.value = ''
  resetToken.value += 1
}

// 根据当前已上传视角组装 multipart/form-data 请求。
async function submitPrediction() {
  if (!canSubmit.value) return

  isLoading.value = true
  errorMessage.value = ''
  result.value = null

  const formData = new FormData()
  Object.entries(files).forEach(([key, file]) => {
    if (file) {
      formData.append(key, file)
    }
  })

  try {
    const response = await fetch(`${API_BASE}/predict`, {
      method: 'POST',
      body: formData,
    })

    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(data.detail || '筛查请求失败，请稍后重试。')
    }

    result.value = data
  } catch (error) {
    errorMessage.value = error.message || '网络错误或服务不可用，请确认后端服务已启动。'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <main class="page-shell">
    <header class="page-header">
      <p class="eyebrow">Nutri Screening</p>
      <h1>营养状态筛查系统</h1>
      <p>基于面部图像的老年营养不良辅助筛查</p>
    </header>

    <nav class="main-tab-bar" aria-label="功能切换">
      <button v-for="tab in mainTabs" :key="tab.key" type="button" :class="{ active: activeMainTab === tab.key }" @click="activeMainTab = tab.key">
        {{ tab.label }}
      </button>
    </nav>

    <template v-if="activeMainTab === 'image'">
      <section class="workspace">
        <div class="upload-grid">
          <ImageUploader
            v-for="item in uploaders"
            :key="item.key"
            :view-key="item.key"
            :title="item.title"
            :subtitle="item.subtitle"
            :reset-token="resetToken"
            @change="onFileChange"
            @error="onUploadError"
          />
        </div>

        <p v-if="errorMessage" class="error-alert">{{ errorMessage }}</p>

        <div class="action-bar">
          <button class="primary-button" type="button" :disabled="!canSubmit" @click="submitPrediction">
            <span v-if="isLoading" class="spinner" aria-hidden="true"></span>
            {{ isLoading ? '分析中...' : '开始筛查' }}
          </button>
        </div>
      </section>

      <ResultPanel v-if="result" :result="result" @reset="resetAll" />
    </template>

    <AssessmentPanel v-else />
  </main>
</template>
