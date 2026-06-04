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
const MAX_IMAGE_SIDE = 1024
const JPEG_QUALITY = 0.9

function restoreDraftPreview() {
  const imageInfo = draftContext?.draftData.images?.[props.viewKey]
  if (imageInfo?.saved) {
    clearPreview()
    previewUrl.value = `${API_BASE}/draft/image/${props.viewKey}?t=${Date.now()}`
    previewIsObjectUrl.value = false
    emit('change', props.viewKey, null)
  }
}

function compressedFilename(file) {
  const baseName = (file.name || 'upload').replace(/\.[^.]+$/, '')
  return `${baseName}.jpg`
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const image = new Image()
    image.onload = () => {
      URL.revokeObjectURL(url)
      resolve(image)
    }
    image.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('图片读取失败，请重新选择图片。'))
    }
    image.src = url
  })
}

async function prepareUploadImage(file) {
  const image = await loadImage(file)
  const scale = Math.min(1, MAX_IMAGE_SIDE / Math.max(image.naturalWidth, image.naturalHeight))
  const width = Math.max(1, Math.round(image.naturalWidth * scale))
  const height = Math.max(1, Math.round(image.naturalHeight * scale))
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  context.drawImage(image, 0, 0, width, height)

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          reject(new Error('图片处理失败，请重新选择图片。'))
          return
        }
        resolve(new File([blob], compressedFilename(file), { type: 'image/jpeg' }))
      },
      'image/jpeg',
      JPEG_QUALITY,
    )
  })
}

async function saveDraftImage(file) {
  if (!draftContext) return false
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
    return true
  } catch (error) {
    draftContext.draftData.images[props.viewKey] = null
    emit('error', error.message || `${props.title}图片草稿保存失败。`)
    return false
  }
}

// 统一处理点击、拖拽进入的文件，校验格式后交给父组件。
async function handleFile(file) {
  if (!file) return

  if (!supportedTypes.includes(file.type)) {
    emit('error', `${props.title}图片格式不支持，请上传 JPG、PNG 或 BMP 图片。`)
    return
  }

  let uploadFile
  try {
    // 保守处理：最长边1024、JPEG质量0.9；不裁剪、不改变比例，兼顾速度和模型稳定性。
    uploadFile = await prepareUploadImage(file)
  } catch (error) {
    emit('error', error.message || `${props.title}图片处理失败，请重新上传。`)
    return
  }

  clearPreview()
  previewUrl.value = URL.createObjectURL(uploadFile)
  previewIsObjectUrl.value = true
  emit('change', props.viewKey, null)

  if (draftContext) {
    // 替换图片时先清空该视角的草稿状态，避免预测接口读到旧图片。
    draftContext.draftData.images[props.viewKey] = null
    draftContext.beginDraftImageUpload?.()
  }

  try {
    const saved = await saveDraftImage(uploadFile)
    emit('change', props.viewKey, saved ? uploadFile : null)
  } finally {
    draftContext?.endDraftImageUpload?.()
  }
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
