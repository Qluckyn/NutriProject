<script setup>
import { computed, onMounted, provide, reactive, ref } from 'vue'
import { API_BASE } from './config'
import ImageUploader from './components/ImageUploader.vue'
import ResultPanel from './components/ResultPanel.vue'
import AssessmentPanel from './components/AssessmentPanel.vue'

const emptyDraft = () => ({
  patient_info: {},
  weight_records: {},
  intake_records: {},
  nrs2002_form: {},
  mnasf_form: {},
  glim_form: {},
  images: { front: null, left: null, right: null },
  image_result: null,
  nrs2002_result: null,
  mnasf_result: null,
  glim_result: null,
})

const activeMainTab = ref('image')
const canAssess = ref(false)
const draftData = reactive(emptyDraft())
const draftLoaded = ref(false)
let draftTimer = null

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
  // { key: 'assessment', label: '量表评估' },
]

const hasDraftImage = computed(() => Object.values(draftData.images || {}).some((item) => item?.saved))
const canSubmit = computed(() => (Object.values(files).some(Boolean) || hasDraftImage.value) && !isLoading.value)

function replaceDraftData(nextDraft) {
  Object.assign(draftData, emptyDraft(), nextDraft || {})
  draftData.images = { front: null, left: null, right: null, ...(draftData.images || {}) }
}

// 防抖保存完整草稿，避免每次输入都立即写文件。
function saveDraft() {
  if (!draftLoaded.value) return
  window.clearTimeout(draftTimer)
  draftTimer = window.setTimeout(async () => {
    try {
      await fetch(`${API_BASE}/draft`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draftData),
      })
    } catch (error) {
      console.warn('保存草稿失败', error)
    }
  }, 500)
}

provide('draftContext', {
  draftData,
  draftLoaded,
  saveDraft,
  replaceDraftData,
})

onMounted(async () => {
  try {
    const response = await fetch(`${API_BASE}/draft`)
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || '草稿读取失败。')
    replaceDraftData(data)
    result.value = draftData.image_result || null
    // 草稿中已有营养不良风险结果时，恢复量表评估解锁状态。
    canAssess.value = draftData.image_result?.prediction === 'malnourished' 
  } catch (error) {
    console.warn(error.message || '草稿读取失败。')
  } finally {
    draftLoaded.value = true
  }
})

function onFileChange(viewKey, file) {
  files[viewKey] = file
  errorMessage.value = ''
}

function onUploadError(message) {
  errorMessage.value = message
}

async function deleteDraftImage(view) {
  try {
    await fetch(`${API_BASE}/draft/image/${view}`, { method: 'DELETE' })
  } catch (error) {
    console.warn(`删除${view}草稿图片失败`, error)
  }
  draftData.images[view] = null
}

function handleMainTabClick(tabKey) {
  if (tabKey === 'assessment' && !canAssess.value) return
  activeMainTab.value = tabKey
}

function enableAssessment() {
  canAssess.value = true
}

function goAssessment() {
  if (!canAssess.value) return
  activeMainTab.value = 'assessment'
}

async function resetAll() {
  files.front = null
  files.left = null
  files.right = null
  result.value = null
  draftData.image_result = null
  canAssess.value = false
  errorMessage.value = ''
  await Promise.all(['front', 'left', 'right'].map(deleteDraftImage))
  resetToken.value += 1
  saveDraft()
}

async function appendDraftImage(formData, view) {
  const imageInfo = draftData.images?.[view]
  if (!imageInfo?.saved) return
  const response = await fetch(`${API_BASE}/draft/image/${view}`)
  if (!response.ok) return
  const blob = await response.blob()
  formData.append(view, blob, imageInfo.filename || `${view}.jpg`)
}

// 根据当前已上传视角组装 multipart/form-data 请求；若页面恢复自草稿，则从后端取图片Blob。
async function submitPrediction() {
  if (!canSubmit.value) return

  isLoading.value = true
  errorMessage.value = ''
  result.value = null
  draftData.image_result = null
  canAssess.value = false
  saveDraft()

  const formData = new FormData()
  for (const key of ['front', 'left', 'right']) {
    if (files[key]) {
      formData.append(key, files[key])
    } else {
      await appendDraftImage(formData, key)
    }
  }

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
    draftData.image_result = data
    canAssess.value = data.prediction === 'malnourished'
    saveDraft()
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
      <button
        v-for="tab in mainTabs"
        :key="tab.key"
        type="button"
        :disabled="tab.key === 'assessment' && !canAssess"
        :class="{ active: activeMainTab === tab.key, disabled: tab.key === 'assessment' && !canAssess }"
        @click="handleMainTabClick(tab.key)"
      >
        {{ tab.label }}
      </button>
    </nav>

    <section v-show="activeMainTab === 'image'" class="main-tab-panel">
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

      <ResultPanel v-if="result" :result="result" @reset="resetAll" @enable-assessment="enableAssessment" @go-assessment="goAssessment" />
    </section>

    <section v-show="activeMainTab === 'assessment'" class="main-tab-panel">
      <AssessmentPanel />
    </section>
  </main>
</template>
