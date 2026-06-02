<script setup>
import { computed, inject, onMounted, ref, watch } from 'vue'
import { API_BASE } from '../config'

const props = defineProps({
  patient: { type: Object, required: true },
  weights: { type: Object, required: true },
  intakeLastWeek: { type: [String, Number], required: true },
})

const emit = defineEmits(['validation-failed', 'highlight-calf'])
const draftContext = inject('draftContext', null)
const isRestoring = ref(false)
const mobility = ref('2')
const stressOrAcuteDisease = ref('false')
const mentalStatus = ref('2')
const useBmi = ref('true')
const calfOverride = ref('')
const loading = ref(false)
const errorMessage = ref('')
const result = ref(null)
const touched = ref(false)

const calfValue = computed(() => calfOverride.value || props.patient.calfCircumference)
const formReady = computed(() => Boolean(props.patient.age && props.patient.height && props.weights['0'] && props.intakeLastWeek !== '' && (useBmi.value === 'true' || calfValue.value)))

function restoreFromDraft() {
  if (!draftContext) return
  const saved = draftContext.draftData.mnasf_form || {}
  isRestoring.value = true
  mobility.value = saved.mobility ?? '2'
  stressOrAcuteDisease.value = saved.stressOrAcuteDisease ?? 'false'
  mentalStatus.value = saved.mentalStatus ?? '2'
  useBmi.value = saved.useBmi ?? 'true'
  calfOverride.value = saved.calfOverride ?? ''
  result.value = draftContext.draftData.mnasf_result || null
  requestAnimationFrame(() => {
    isRestoring.value = false
  })
}

function persistForm() {
  if (!draftContext || isRestoring.value) return
  draftContext.draftData.mnasf_form = {
    mobility: mobility.value,
    stressOrAcuteDisease: stressOrAcuteDisease.value,
    mentalStatus: mentalStatus.value,
    useBmi: useBmi.value,
    calfOverride: calfOverride.value,
  }
  draftContext.saveDraft()
}

watch(useBmi, (value) => {
  if (value === 'false') emit('highlight-calf')
})

function buildPayload() {
  const records = Object.fromEntries(Object.entries(props.weights).filter(([, value]) => value !== '').map(([key, value]) => [key, Number(value)]))
  return {
    age: Number(props.patient.age),
    height: Number(props.patient.height),
    weight_records: records,
    intake_last_week: Number(props.intakeLastWeek),
    mobility: Number(mobility.value),
    stress_or_acute_disease: stressOrAcuteDisease.value === 'true',
    mental_status: Number(mentalStatus.value),
    use_bmi: useBmi.value === 'true',
    calf_circumference: calfValue.value ? Number(calfValue.value) : null,
  }
}

async function submit() {
  touched.value = true
  if (!formReady.value) {
    emit('validation-failed')
    errorMessage.value = '请先补全患者年龄、身高、当前体重、最近一周摄食量；使用小腿围时需填写小腿围。'
    return
  }
  loading.value = true
  errorMessage.value = ''
  result.value = null
  try {
    const response = await fetch(`${API_BASE}/assess/mna_sf`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildPayload()) })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || 'MNA-SF评估失败，请稍后重试。')
    result.value = data
  } catch (error) {
    errorMessage.value = error.message || '网络错误，请确认后端服务已启动。'
  } finally {
    loading.value = false
  }
}

function levelClass(level) {
  if (level === '营养正常') return 'good'
  if (level === '营养不良风险') return 'caution'
  return 'risk'
}

function resetResult() {
  result.value = null
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

watch([mobility, stressOrAcuteDisease, mentalStatus, useBmi, calfOverride], persistForm)

watch(result, (value) => {
  if (!draftContext || isRestoring.value) return
  draftContext.draftData.mnasf_result = value
  draftContext.saveDraft()
})
</script>

<template>
  <section class="scale-form">
    <div class="form-card">
      <div class="section-title-row"><div><p class="section-kicker">MNA-SF</p><h2>微型营养评估简表</h2></div></div>
      <div class="field-block"><span>活动能力</span><div class="radio-stack"><label><input v-model="mobility" type="radio" value="0" />需长期卧床或坐轮椅</label><label><input v-model="mobility" type="radio" value="1" />可下床但不能外出</label><label><input v-model="mobility" type="radio" value="2" />可以外出</label></div></div>
      <div class="field-block"><span>近3个月是否有心理创伤或急性疾病</span><div class="segmented-options"><label><input v-model="stressOrAcuteDisease" type="radio" value="true" />是</label><label><input v-model="stressOrAcuteDisease" type="radio" value="false" />否</label></div></div>
      <div class="field-block"><span>精神心理状况</span><div class="radio-stack"><label><input v-model="mentalStatus" type="radio" value="0" />严重痴呆或抑郁</label><label><input v-model="mentalStatus" type="radio" value="1" />轻度痴呆</label><label><input v-model="mentalStatus" type="radio" value="2" />无问题</label></div></div>
      <div class="field-block" :class="{ callout: useBmi === 'false' }"><span>第6题选择方式</span><div class="segmented-options"><label><input v-model="useBmi" type="radio" value="true" />使用BMI</label><label><input v-model="useBmi" type="radio" value="false" />使用小腿围</label></div><input v-if="useBmi === 'false'" v-model="calfOverride" type="number" min="0" step="0.1" placeholder="可覆盖患者基本信息中的小腿围" /></div>
      <p v-if="errorMessage" class="error-alert compact-alert">{{ errorMessage }}</p>
      <button class="primary-button" type="button" :disabled="loading || !formReady" @click="submit"><span v-if="loading" class="spinner" aria-hidden="true"></span>{{ loading ? '评估中...' : '开始评估 - MNA-SF' }}</button>
      <p v-if="touched && !formReady" class="field-error">仍有必填项未完成。</p>
    </div>
    <section v-if="result" class="assessment-result" :class="levelClass(result.level)"><div class="score-hero"><span>总分</span><strong>{{ result.total_score }}/14</strong><em>{{ result.level }}</em></div><div class="progress-track"><span class="progress-fill success" :style="{ width: `${Math.min(100, result.total_score / 14 * 100)}%` }"></span></div><div class="result-metrics three"><div v-for="(score, key) in result.score_breakdown" :key="key"><span>{{ key }}</span><strong>{{ score }}分</strong></div><div><span>{{ useBmi === 'true' ? 'BMI' : '小腿围' }}</span><strong>{{ useBmi === 'true' ? result.bmi : calfValue }}</strong></div><div><span>3个月体重下降</span><strong>{{ result.weight_loss_3m_kg }}kg</strong></div></div><p class="message-text">{{ result.message }}</p><button class="secondary-button" type="button" @click="resetResult">重新评估</button></section>
  </section>
</template>
