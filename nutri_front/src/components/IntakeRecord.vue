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
const emptyWeeks = { 1: '', 2: '', 3: '', 4: '' }
const intakeOptions = [
  { value: '25', label: '占正常进食0 ~ 1/4' },
  { value: '50', label: '占正常进食的1/4 ~ 1/2' },
  { value: '75', label: '占正常进食的1/2 ~ 3/4' },
  { value: '100', label: '占正常进食的3/4以上' },
]

// NRS-2002 仅使用最近一周摄食量；前3周不再在前端采集。
function updateLastWeek(value) {
  const next = { ...emptyWeeks, 4: value }
  emit('update:weeks', next)
  emit('update:lastWeek', value)
}

function restoreFromDraft() {
  const saved = draftContext?.draftData.intake_records
  if (!saved || !Object.keys(saved).length) return
  isRestoring.value = true
  const next = { ...emptyWeeks, 4: saved['4'] || '' }
  emit('update:weeks', next)
  emit('update:lastWeek', next['4'])
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
  <section class='form-card'>
    <div class='section-title-row'>
      <div>
        <p class='section-kicker'>Intake</p>
        <h2>摄食量记录</h2>
      </div>
    </div>
    <p class='help-text'>请选择最近一周摄食量相当于正常需求的区间。</p>

    <div class='intake-single'>
      <label class='field-block intake-week' :class="{ invalid: showErrors && !weeks['4'] }">
        <span>最近一周摄食量 <strong>*</strong></span>
        <select :value="weeks['4']" @change="updateLastWeek($event.target.value)">
          <option value=''>请选择</option>
          <option v-for='option in intakeOptions' :key='option.value' :value='option.value'>{{ option.label }}</option>
        </select>
        <small>NRS-2002 评分仅使用最近一周摄食量。</small>
      </label>
    </div>
  </section>
</template>
