<script setup>
import { inject, onMounted, ref, watch } from 'vue'

const props = defineProps({
  modelValue: {
    type: Object,
    required: true,
  },
  showErrors: {
    type: Boolean,
    default: false,
  },
  collapsed: {
    type: Boolean,
    default: false,
  },
  readonly: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue'])
const draftContext = inject('draftContext', null)
const isRestoring = ref(false)

// 公共患者信息在三个量表间共享，局部更新后回传给父组件。
function updateField(field, value) {
  if (props.readonly) return
  emit('update:modelValue', {
    ...props.modelValue,
    [field]: value,
  })
}

function restoreFromDraft() {
  const saved = draftContext?.draftData.patient_info
  if (!saved || !Object.keys(saved).length) return
  isRestoring.value = true
  emit('update:modelValue', { ...props.modelValue, ...saved })
  requestAnimationFrame(() => {
    isRestoring.value = false
  })
}

function isMissing(field) {
  return props.showErrors && (props.modelValue[field] === '' || props.modelValue[field] === null || props.modelValue[field] === undefined)
}

function isInvalidAge() {
  if (!props.showErrors || isMissing('age')) return false
  const age = Number(props.modelValue.age)
  return !Number.isInteger(age) || age < 0 || age > 110
}

function isInvalidHeight() {
  if (!props.showErrors || isMissing('height')) return false
  const height = Number(props.modelValue.height)
  return Number.isNaN(height) || height < 100 || height > 250
}

onMounted(() => {
  restoreFromDraft()
})

watch(
  () => draftContext?.draftLoaded.value,
  (loaded) => {
    if (loaded) restoreFromDraft()
  },
)

watch(
  () => props.modelValue,
  (value) => {
    if (!draftContext || isRestoring.value) return
    draftContext.draftData.patient_info = { ...value }
    draftContext.saveDraft()
  },
  { deep: true },
)
</script>

<template>
  <section class="form-card patient-card">
    <div class="section-title-row">
      <div>
        <p class="section-kicker">Patient</p>
        <h2>患者基本信息</h2>
      </div>
      <span class="muted-note">{{ collapsed ? '如需修改，请返回步骤1' : '姓名选填，其余关键字段用于量表计算' }}</span>
    </div>

    <div v-if="collapsed" class="result-metrics three">
      <div>
        <span>姓名</span>
        <strong>{{ modelValue.name || '未填写' }}</strong>
      </div>
      <div>
        <span>年龄</span>
        <strong>{{ modelValue.age || '-' }}岁</strong>
      </div>
      <div>
        <span>身高</span>
        <strong>{{ modelValue.height || '-' }}cm</strong>
      </div>
    </div>

    <div v-else class="form-grid five-cols">
      <label class="field-block">
        <span>姓名</span>
        <input :value="modelValue.name" type="text" placeholder="选填" :disabled="readonly" @input="updateField('name', $event.target.value)" />
      </label>

      <label class="field-block" :class="{ invalid: isMissing('age') || isInvalidAge() }">
        <span>年龄 <strong>*</strong></span>
        <input :value="modelValue.age" type="number" min="0" max="110" step="1" placeholder="岁" :disabled="readonly" @input="updateField('age', $event.target.value)" />
        <small v-if="isInvalidAge()">年龄需填写0到110之间的整数</small>
      </label>

      <div class="field-block">
        <span>性别</span>
        <div class="segmented-options compact">
          <label><input :checked="modelValue.gender === 'male'" type="radio" name="gender" :disabled="readonly" @change="updateField('gender', 'male')" />男</label>
          <label><input :checked="modelValue.gender === 'female'" type="radio" name="gender" :disabled="readonly" @change="updateField('gender', 'female')" />女</label>
        </div>
      </div>

      <label class="field-block" :class="{ invalid: isMissing('height') || isInvalidHeight() }">
        <span>身高 <strong>*</strong></span>
        <input :value="modelValue.height" type="number" min="100" max="250" step="0.1" placeholder="cm" :disabled="readonly" @input="updateField('height', $event.target.value)" />
        <small v-if="isInvalidHeight()">身高需填写100到250cm之间的数值</small>
      </label>

      <label class="field-block">
        <span>小腿围</span>
        <input :value="modelValue.calfCircumference" type="number" min="0.1" step="0.1" placeholder="cm" :disabled="readonly" @input="updateField('calfCircumference', $event.target.value)" />
        <small>MNA-SF中可替代BMI使用</small>
      </label>
    </div>
  </section>
</template>
