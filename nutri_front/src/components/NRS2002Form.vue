<script setup>
import { computed, inject, onMounted, ref, watch } from 'vue'
import { API_BASE } from '../config'

const props = defineProps({
  patient: { type: Object, required: true },
  weights: { type: Object, required: true },
  intakeLastWeek: { type: [String, Number], required: true },
  diseases: { type: Array, default: () => [] },
})

const emit = defineEmits(['validation-failed'])
const draftContext = inject('draftContext', null)
const isRestoring = ref(false)
const generalConditionImpaired = ref('false')
const selectedDiseaseIds = ref([])
const loading = ref(false)
const errorMessage = ref('')
const result = ref(null)
const touched = ref(false)

const groupedDiseases = computed(() => {
  return [1, 2, 3].map((score) => ({
    score,
    items: props.diseases.filter((item) => Number(item.nrs_score) === score),
  }))
})

const requiredMonths = ['0', '1', '2', '3']
const formReady = computed(() => Boolean(props.patient.age && props.patient.height && props.intakeLastWeek !== '' && requiredMonths.every((m) => props.weights[m])))

function restoreFromDraft() {
  if (!draftContext) return
  const saved = draftContext.draftData.nrs2002_form || {}
  isRestoring.value = true
  generalConditionImpaired.value = saved.generalConditionImpaired ?? 'false'
  selectedDiseaseIds.value = Array.isArray(saved.selectedDiseaseIds) ? [...saved.selectedDiseaseIds] : []
  result.value = draftContext.draftData.nrs2002_result || null
  requestAnimationFrame(() => {
    isRestoring.value = false
  })
}

function persistForm() {
  if (!draftContext || isRestoring.value) return
  draftContext.draftData.nrs2002_form = {
    generalConditionImpaired: generalConditionImpaired.value,
    selectedDiseaseIds: [...selectedDiseaseIds.value],
  }
  draftContext.saveDraft()
}

function buildPayload() {
  return {
    age: Number(props.patient.age),
    height: Number(props.patient.height),
    weight_records: Object.fromEntries(Object.entries(props.weights).filter(([, value]) => value !== '').map(([key, value]) => [key, Number(value)])),
    intake_last_week: Number(props.intakeLastWeek),
    disease_ids: selectedDiseaseIds.value,
    general_condition_impaired: generalConditionImpaired.value === 'true',
  }
}

async function submit() {
  touched.value = true
  if (!formReady.value) {
    emit('validation-failed')
    errorMessage.value = '请先补全患者年龄、身高、最近一周摄食量和必填体重记录。'
    return
  }

  loading.value = true
  errorMessage.value = ''
  result.value = null
  try {
    const response = await fetch(`${API_BASE}/assess/nrs2002`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildPayload()),
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || 'NRS-2002评估失败，请稍后重试。')
    result.value = data
  } catch (error) {
    errorMessage.value = error.message || '网络错误，请确认后端服务已启动。'
  } finally {
    loading.value = false
  }
}

function resetResult() {
  result.value = null
  errorMessage.value = ''
  touched.value = false
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

watch([generalConditionImpaired, selectedDiseaseIds], persistForm, { deep: true })

watch(result, (value) => {
  if (!draftContext || isRestoring.value) return
  draftContext.draftData.nrs2002_result = value
  draftContext.saveDraft()
})
</script>

<template>
  <section class="scale-form">
    <div class="form-card">
      <div class="section-title-row"><div><p class="section-kicker">NRS-2002</p><h2>营养风险筛查</h2></div></div>
      <div class="field-block"><span>全身情况是否受损</span><small>因疾病导致一般状态差，如虚弱、卧床等</small><div class="segmented-options"><label><input v-model="generalConditionImpaired" type="radio" value="true" />是</label><label><input v-model="generalConditionImpaired" type="radio" value="false" />否</label></div></div>
      <div class="disease-section"><h3>疾病严重程度</h3><div v-for="group in groupedDiseases" :key="group.score" class="disease-group"><h4>{{ group.score }}分疾病</h4><label v-for="item in group.items" :key="item.id" class="check-option"><input v-model="selectedDiseaseIds" type="checkbox" :value="item.id" /><span>{{ item.name }}</span></label></div></div>
      <p v-if="errorMessage" class="error-alert compact-alert">{{ errorMessage }}</p>
      <button class="primary-button" type="button" :disabled="loading || !formReady" @click="submit"><span v-if="loading" class="spinner" aria-hidden="true"></span>{{ loading ? '评估中...' : '开始评估 - NRS-2002' }}</button>
      <p v-if="touched && !formReady" class="field-error">仍有必填项未完成。</p>
    </div>
    <section v-if="result" class="assessment-result" :class="result.has_risk ? 'risk' : 'good'"><div class="score-hero"><span>总分</span><strong>{{ result.total_score }}</strong><em>{{ result.risk_level }}</em></div><div class="result-metrics three"><div><span>营养状态受损</span><strong>{{ result.nutrition_score }}分</strong></div><div><span>疾病严重程度</span><strong>{{ result.disease_score }}分</strong></div><div><span>年龄</span><strong>{{ result.age_score }}分</strong></div></div><div class="result-metrics four"><div><span>1个月丢失</span><strong>{{ result.weight_loss_details['1m_loss_pct'] }}%</strong></div><div><span>2个月丢失</span><strong>{{ result.weight_loss_details['2m_loss_pct'] }}%</strong></div><div><span>3个月丢失</span><strong>{{ result.weight_loss_details['3m_loss_pct'] }}%</strong></div><div><span>BMI</span><strong>{{ result.bmi }}</strong></div></div><p class="message-text">{{ result.recommendation }}</p><p class="message-text">{{ result.message }}</p><button class="secondary-button" type="button" @click="resetResult">重新评估</button></section>
  </section>
</template>
