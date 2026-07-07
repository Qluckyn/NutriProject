<script setup>
import { inject, onMounted, ref, watch } from 'vue'

const props = defineProps({
  weeks: {
    type: Object,
    required: true,
  },
  showErrors: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:weeks', 'update:lastWeek'])
const draftContext = inject('draftContext', null)
const isRestoring = ref(false)
const intakeOptions = [
  { value: '0', label: '完全不进食' },
  { value: '25', label: '占正常进食的1/4' },
  { value: '50', label: '占正常进食的1/2' },
  { value: '75', label: '占正常进食的3/4' },
  { value: '100', label: '正常进食' },
]

// 第4周是最近一周，会同步给量表计算使用；前3周仅作为临床参考。
function updateWeek(week, value) {
  const next = { ...props.weeks, [week]: value }
  emit('update:weeks', next)
  if (week === '4') {
    emit('update:lastWeek', value)
  }
}

function restoreFromDraft() {
  const saved = draftContext?.draftData.intake_records
  if (!saved || !Object.keys(saved).length) return
  isRestoring.value = true
  const next = { ...props.weeks, ...saved }
  emit('update:weeks', next)
  emit('update:lastWeek', next['4'] || '')
  requestAnimationFrame(() => {
    isRestoring.value = false
  })
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
  () => props.weeks,
  (value) => {
    if (!draftContext || isRestoring.value) return
    draftContext.draftData.intake_records = { ...value }
    draftContext.saveDraft()
  },
  { deep: true },
)
</script>

<template>
  <section class="form-card">
    <div class="section-title-row">
      <div>
        <p class="section-kicker">Intake</p>
        <h2>摄食量记录</h2>
      </div>
    </div>
    <p class="help-text">请选择每周摄食量相当于正常需求的比例，0表示完全不进食，1表示正常进食</p>

    <div class="intake-grid">
      <label v-for="week in ['1', '2', '3', '4']" :key="week" class="field-block intake-week" :class="{ highlight: week === '4', invalid: showErrors && week === '4' && !weeks[week] }">
        <span>第{{ week }}周{{ week === '4' ? '（最近一周）' : '' }} <strong v-if="week === '4'">*</strong></span>
        <select :value="weeks[week]" @change="updateWeek(week, $event.target.value)">
          <option value="">请选择</option>
          <option v-for="option in intakeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
      </label>
    </div>
  </section>
</template>
