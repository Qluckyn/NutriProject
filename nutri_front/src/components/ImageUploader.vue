<script setup>
import { ref, watch } from 'vue'

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

const inputRef = ref(null)
const previewUrl = ref('')
const isDragging = ref(false)

const supportedTypes = ['image/jpeg', 'image/png', 'image/bmp']

// 统一处理点击、拖拽进入的文件，校验格式后交给父组件。
function handleFile(file) {
  if (!file) return

  if (!supportedTypes.includes(file.type)) {
    emit('error', `${props.title}图片格式不支持，请上传 JPG、PNG 或 BMP 图片。`)
    return
  }

  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }

  previewUrl.value = URL.createObjectURL(file)
  emit('change', props.viewKey, file)
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

function removeImage(event) {
  event.stopPropagation()
  clearPreview()
  emit('change', props.viewKey, null)
}

function clearPreview() {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
  previewUrl.value = ''
}

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
