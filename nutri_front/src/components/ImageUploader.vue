<script setup>
import { inject, onMounted, ref, watch } from 'vue'
import { API_BASE } from '../config'

const props = defineProps({
  viewKey: {
    type: String,
    required: true,
  },
  title: {
    type: String,
    required: true,
  },
  subtitle: {
    type: String,
    required: true,
  },
  resetToken: {
    type: Number,
    default: 0,
  },
})

const emit = defineEmits(['change', 'error'])
const draftContext = inject('draftContext', null)

const inputRef = ref(null)
const previewUrl = ref('')
const previewIsObjectUrl = ref(false)
const isDragging = ref(false)

const supportedTypes = ['image/jpeg', 'image/png', 'image/bmp']

function restoreDraftPreview() {
  const imageInfo = draftContext?.draftData.images?.[props.viewKey]
  if (imageInfo?.saved) {
    clearPreview()
    previewUrl.value = `${API_BASE}/draft/image/${props.viewKey}?t=${Date.now()}`
    previewIsObjectUrl.value = false
    emit('change', props.viewKey, null)
  }
}

async function saveDraftImage(file) {
  if (!draftContext) return
  const formData = new FormData()
  formData.append('file', file)
  try {
    const response = await fetch(`${API_BASE}/draft/image/${props.viewKey}`, {
      method: 'POST',
      body: formData,
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || '图片草稿保存失败。')
    draftContext.draftData.images[props.viewKey] = { filename: file.name, saved: true }
  } catch (error) {
    emit('error', error.message || `${props.title}图片草稿保存失败。`)
  }
}

// 统一处理点击、拖拽进入的文件，校验格式后交给父组件。
async function handleFile(file) {
  if (!file) return

  if (!supportedTypes.includes(file.type)) {
    emit('error', `${props.title}图片格式不支持，请上传 JPG、PNG 或 BMP 图片。`)
    return
  }

  clearPreview()
  previewUrl.value = URL.createObjectURL(file)
  previewIsObjectUrl.value = true
  emit('change', props.viewKey, file)
  await saveDraftImage(file)
}

function openFileDialog() {
  inputRef.value?.click()
}

function onFileChange(event) {
  const file = event.target.files?.[0]
  handleFile(file)
  event.target.value = ''
}

function onDrop(event) {
  isDragging.value = false
  handleFile(event.dataTransfer.files?.[0])
}

async function removeImage(event) {
  event.stopPropagation()
  clearPreview()
  emit('change', props.viewKey, null)
  if (!draftContext) return
  try {
    await fetch(`${API_BASE}/draft/image/${props.viewKey}`, { method: 'DELETE' })
    draftContext.draftData.images[props.viewKey] = null
  } catch (error) {
    emit('error', `${props.title}图片草稿删除失败。`)
  }
}

function clearPreview() {
  if (previewUrl.value && previewIsObjectUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
  previewUrl.value = ''
  previewIsObjectUrl.value = false
}

onMounted(() => {
  restoreDraftPreview()
})

watch(
  () => draftContext?.draftLoaded.value,
  (loaded) => {
    if (loaded) restoreDraftPreview()
  },
)

watch(
  () => draftContext?.draftData.images?.[props.viewKey],
  (imageInfo) => {
    if (imageInfo?.saved && !previewUrl.value) restoreDraftPreview()
    if (!imageInfo && !previewIsObjectUrl.value) clearPreview()
  },
  { deep: true },
)

// 父组件触发重新筛查时，同步清空本组件内部预览状态。
watch(
  () => props.resetToken,
  () => {
    clearPreview()
  },
)
</script>

<template>
  <section
    class="upload-card"
    :class="{ 'is-dragging': isDragging, 'has-image': previewUrl }"
    @click="openFileDialog"
    @dragover.prevent="isDragging = true"
    @dragleave.prevent="isDragging = false"
    @drop.prevent="onDrop"
  >
    <input
      ref="inputRef"
      class="file-input"
      type="file"
      accept=".jpg,.jpeg,.png,.bmp,image/jpeg,image/png,image/bmp"
      @change="onFileChange"
    />

    <button v-if="previewUrl" class="remove-button" type="button" aria-label="删除图片" @click="removeImage">
      ×
    </button>

    <img v-if="previewUrl" class="preview-image" :src="previewUrl" :alt="`${title}预览`" />

    <div v-else class="upload-placeholder">
      <div class="camera-icon" aria-hidden="true">
        <span class="camera-body"></span>
        <span class="camera-lens"></span>
      </div>
      <h3>{{ title }}</h3>
      <p>{{ subtitle }}</p>
    </div>
  </section>
</template>
