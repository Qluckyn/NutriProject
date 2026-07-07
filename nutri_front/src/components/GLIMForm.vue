<script setup>
import { computed, inject, onMounted, ref, watch } from 'vue'
import { API_BASE } from '../config'

const props = defineProps({
  patient: { type: Object, required: true },
  weights: { type: Object, required: true },
  diseases: { type: Array, default: () => [] },
  glimConfig: { type: Object, default: null },
  showSubmit: { type: Boolean, default: true },
})

const emit = defineEmits(['validation-failed', 'assessed'])
const draftContext = inject('draftContext', null)
const isRestoring = ref(false)
const muscleLoss = ref('none')
const intakeUnder50Over1w = ref(false)
const anyIntakeReductionOver2w = ref(false)
const giSymptoms = ref([])
const nutritionImpactConditions = ref([])
const acuteDiseaseIds = ref([])
const chronicDiseaseIds = ref([])
const cancerSite = ref('')
const cancerStage = ref('')
const cancerMalnutritionRelated = ref('')
const crp = ref('')
const il6 = ref('')
const loading = ref(false)
const errorMessage = ref('')
const result = ref(null)
const touched = ref(false)

const fallbackGiSymptomOptions = [
  { id: 'dysphagia', name: '吞咽困难' },
  { id: 'nausea_vomiting', name: '恶心、呕吐' },
  { id: 'diarrhea', name: '腹泻' },
  { id: 'constipation', name: '便秘' },
  { id: 'abdominal_pain', name: '腹痛' },
  { id: 'other', name: '其他' },
]
const fallbackNutritionImpactOptions = [
  { id: 'short_bowel', name: '短肠综合征' },
  { id: 'pancreatic_insufficiency', name: '胰腺功能不全' },
  { id: 'post_bariatric', name: '减肥手术后' },
  { id: 'esophageal_stricture', name: '食管狭窄' },
  { id: 'gastroparesis', name: '胃轻瘫' },
  { id: 'intestinal_obstruction', name: '肠梗阻' },
  { id: 'diarrhea_or_steatorrhea', name: '腹泻或脂肪痢' },
  { id: 'high_output_stoma', name: '排出量较大的肠道造口患者' },
  { id: 'other', name: '其他' },
]
const giSymptomOptions = computed(() => props.glimConfig?.intake_or_malabsorption?.gi_symptoms || fallbackGiSymptomOptions)
const nutritionImpactOptions = computed(() => props.glimConfig?.intake_or_malabsorption?.related_diseases || fallbackNutritionImpactOptions)
const acuteDiseaseOptions = computed(() => props.glimConfig?.inflammation_or_disease_burden?.acute || diseaseOptions(['severe_infection', 'burn', 'trauma', 'brain_injury']))
const malignantTumorOption = computed(() => (props.glimConfig?.inflammation_or_disease_burden?.chronic || diseaseOptions(['malignant_tumor'])).find((item) => item.id === 'malignant_tumor') || diseaseOptions(['malignant_tumor'])[0])
const chronicDiseaseOptions = computed(() => (props.glimConfig?.inflammation_or_disease_burden?.chronic || diseaseOptions(['copd', 'heart_failure', 'ckd', 'chronic_liver', 'liver_cirrhosis', 'rheumatoid_arthritis', 'other'])).filter((item) => item.id !== 'malignant_tumor'))
const malignantTumorSelected = computed(() => chronicDiseaseIds.value.includes('malignant_tumor'))
const formReady = computed(() => Boolean(props.patient.age && props.patient.height && props.weights['0']))

function diseaseOptions(ids) {
  return ids.map((id) => props.diseases.find((item) => item.id === id) || { id, name: fallbackDiseaseName(id) })
}

function fallbackDiseaseName(id) {
  const names = {
    severe_infection: '严重感染',
    burn: '烧伤',
    trauma: '创伤',
    brain_injury: '闭合性脑损伤',
    malignant_tumor: '恶性肿瘤（癌症）',
    copd: '慢性阻塞性肺疾病',
    heart_failure: '充血性心衰',
    ckd: '慢性肾脏疾病',
    chronic_liver: '慢性肝病',
    liver_cirrhosis: '肝硬化',
    rheumatoid_arthritis: '类风湿性关节炎',
    other: '其他',
  }
  return names[id] || id
}

function restoreFromDraft() {
  if (!draftContext) return
  const saved = draftContext.draftData.glim_form || {}
  isRestoring.value = true
  muscleLoss.value = saved.muscleLoss ?? 'none'
  intakeUnder50Over1w.value = Boolean(saved.intakeUnder50Over1w)
  anyIntakeReductionOver2w.value = Boolean(saved.anyIntakeReductionOver2w)
  giSymptoms.value = Array.isArray(saved.giSymptoms) ? [...saved.giSymptoms] : []
  nutritionImpactConditions.value = Array.isArray(saved.nutritionImpactConditions) ? [...saved.nutritionImpactConditions] : []
  acuteDiseaseIds.value = Array.isArray(saved.acuteDiseaseIds) ? [...saved.acuteDiseaseIds] : []
  chronicDiseaseIds.value = Array.isArray(saved.chronicDiseaseIds) ? [...saved.chronicDiseaseIds] : []
  cancerSite.value = saved.cancerSite ?? ''
  cancerStage.value = saved.cancerStage ?? ''
  cancerMalnutritionRelated.value = saved.cancerMalnutritionRelated ?? ''
  crp.value = saved.crp ?? ''
  il6.value = saved.il6 ?? ''
  result.value = draftContext.draftData.glim_result || null
  requestAnimationFrame(() => {
    isRestoring.value = false
  })
}

function persistForm() {
  if (!draftContext || isRestoring.value) return
  draftContext.draftData.glim_form = {
    muscleLoss: muscleLoss.value,
    intakeUnder50Over1w: intakeUnder50Over1w.value,
    anyIntakeReductionOver2w: anyIntakeReductionOver2w.value,
    giSymptoms: [...giSymptoms.value],
    nutritionImpactConditions: [...nutritionImpactConditions.value],
    acuteDiseaseIds: [...acuteDiseaseIds.value],
    chronicDiseaseIds: [...chronicDiseaseIds.value],
    cancerSite: cancerSite.value,
    cancerStage: cancerStage.value,
    cancerMalnutritionRelated: cancerMalnutritionRelated.value,
    crp: crp.value,
    il6: il6.value,
  }
  draftContext.saveDraft()
}

function formatEtiologicalCriteria(items = []) {
  return items.map((item) => {
    const text = String(item)
    const splitIndex = text.indexOf('：')
    const title = splitIndex === -1 ? text : text.slice(0, splitIndex)
    const detail = splitIndex === -1 ? '' : text.slice(splitIndex + 1)
    const options = detail
      .replace(/\s*\[.*?\]/g, '')
      .split(/[、，]/)
      .map((part) => {
        const cleaned = part.trim()
        if (!cleaned || cleaned === title) return ''
        const pieces = cleaned.split('：')
        return pieces[pieces.length - 1].trim()
      })
      .filter((part) => part && part !== title)
    return { title, options: [...new Set(options)] }
  })
}



function buildPayload() {
  const reducedIntake = intakeUnder50Over1w.value || anyIntakeReductionOver2w.value || giSymptoms.value.length > 0 || nutritionImpactConditions.value.length > 0
  return {
    age: Number(props.patient.age),
    height: Number(props.patient.height),
    weight_records: Object.fromEntries(Object.entries(props.weights).filter(([, value]) => value !== '').map(([key, value]) => [key, Number(value)])),
    muscle_loss: muscleLoss.value === 'unknown' ? 'none' : muscleLoss.value,
    disease_ids: [],
    reduced_intake: reducedIntake,
    intake_under_50_over_1w: intakeUnder50Over1w.value,
    any_intake_reduction_over_2w: anyIntakeReductionOver2w.value,
    gi_symptoms: giSymptoms.value,
    nutrition_impact_conditions: nutritionImpactConditions.value,
    acute_disease_ids: acuteDiseaseIds.value,
    chronic_disease_ids: chronicDiseaseIds.value,
    cancer_site: cancerSite.value,
    cancer_stage: cancerStage.value,
    cancer_malnutrition_related: cancerMalnutritionRelated.value === '' ? null : cancerMalnutritionRelated.value === 'true',
    crp: crp.value === '' ? -1 : Number(crp.value),
    il6: il6.value === '' ? -1 : Number(il6.value),
  }
}

async function submit() {
  touched.value = true
  if (!formReady.value) {
    emit('validation-failed')
    errorMessage.value = '请先补全年龄、身高和当前体重。'
    return
  }
  loading.value = true
  errorMessage.value = ''
  result.value = null
  try {
    const response = await fetch(`${API_BASE}/assess/glim`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildPayload()) })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || 'GLIM评估失败，请稍后重试。')
    result.value = data
    emit('assessed', data)
  } catch (error) {
    errorMessage.value = error.message || '网络错误，请确认后端服务已启动。'
  } finally {
    loading.value = false
  }
}

defineExpose({ submit })

function resetResult() {
  result.value = null
  emit('assessed', null)
}




function glimLossText(value) {
  if (value === null || value === undefined) return '数据缺失'
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return '数据缺失'
  if (numeric <= 0) return '未丢失体重'
  return `${numeric}%`
}

function glimBmiText(value) {
  if (value?.bmi === null || value?.bmi === undefined) return '数据缺失'
  return String(value.bmi)
}

const glimDiagnosisReasons = computed(() => {
  const value = result.value
  if (!value) return []
  if (!value.is_malnourished) return [value.message]

  const severeReasons = []
  const moderateReasons = []
  const age = Number(props.patient.age)
  const bmi = Number(value.bmi)
  const loss6m = value.weight_loss_6m_pct === null || value.weight_loss_6m_pct === undefined ? null : Number(value.weight_loss_6m_pct)
  const lossOver6m = value.weight_loss_over6m_pct === null || value.weight_loss_over6m_pct === undefined ? null : Number(value.weight_loss_over6m_pct)

  if (loss6m !== null) {
    if (loss6m > 10) severeReasons.push(`6个月内体重丢失${loss6m}%，超过10%，符合重度营养不良（2期）表型标准。`)
    else if (loss6m >= 5) moderateReasons.push(`6个月内体重丢失${loss6m}%，在5%～10%范围，符合中度营养不良（1期）表型标准。`)
  }
  if (lossOver6m !== null) {
    if (lossOver6m > 20) severeReasons.push(`6个月以上体重丢失${lossOver6m}%，超过20%，符合重度营养不良（2期）表型标准。`)
    else if (lossOver6m >= 10) moderateReasons.push(`6个月以上体重丢失${lossOver6m}%，在10%～20%范围，符合中度营养不良（1期）表型标准。`)
  }
  if (!Number.isNaN(age) && !Number.isNaN(bmi)) {
    if (age < 70 && bmi < 18.5) severeReasons.push(`70岁以下BMI ${bmi}kg/m²，低于18.5kg/m²，符合重度营养不良（2期）表型标准。`)
    else if (age < 70 && bmi < 20) moderateReasons.push(`70岁以下BMI ${bmi}kg/m²，低于20kg/m²，符合中度营养不良（1期）表型标准。`)
    else if (age >= 70 && bmi < 20) severeReasons.push(`70岁及以上BMI ${bmi}kg/m²，低于20kg/m²，符合重度营养不良（2期）表型标准。`)
    else if (age >= 70 && bmi < 22) moderateReasons.push(`70岁及以上BMI ${bmi}kg/m²，低于22kg/m²，符合中度营养不良（1期）表型标准。`)
  }
  if (muscleLoss.value === 'severe') severeReasons.push('重度肌肉减少，符合重度营养不良（2期）表型标准。')
  else if (muscleLoss.value === 'mild_moderate') moderateReasons.push('轻至中度肌肉减少，符合中度营养不良（1期）表型标准。')

  if (value.severity?.includes('重度')) return severeReasons.length ? severeReasons : value.phenotypic_criteria_triggered
  if (value.severity?.includes('中度')) return moderateReasons.length ? moderateReasons : value.phenotypic_criteria_triggered

  const reasons = [...severeReasons, ...moderateReasons]
  return reasons.length ? reasons : value.phenotypic_criteria_triggered
})

onMounted(() => {
  restoreFromDraft()
})

watch(
  () => draftContext?.draftLoaded.value,
  (loaded) => {
    if (loaded) restoreFromDraft()
  },
)

watch([
  muscleLoss,
  intakeUnder50Over1w,
  anyIntakeReductionOver2w,
  giSymptoms,
  nutritionImpactConditions,
  acuteDiseaseIds,
  chronicDiseaseIds,
  cancerSite,
  cancerStage,
  cancerMalnutritionRelated,
  crp,
  il6,
], persistForm, { deep: true })

watch(result, (value) => {
  if (!draftContext || isRestoring.value) return
  draftContext.draftData.glim_result = value
  draftContext.saveDraft()
})
</script>

<template>
  <section class="scale-form">
    <div class="form-card">
      <div class="section-title-row"><div><p class="section-kicker">GLIM</p><h2>营养不良评定标准</h2></div></div>
      <div class="field-block"><span>肌肉减少程度</span><small>请根据人体成分分析（BIA/DXA等）结果选择</small><div class="radio-stack"><label><input v-model="muscleLoss" type="radio" value="unknown" />不详</label><label><input v-model="muscleLoss" type="radio" value="none" />无肌肉减少</label><label><input v-model="muscleLoss" type="radio" value="mild_moderate" />轻至中度减少</label><label><input v-model="muscleLoss" type="radio" value="severe" />重度减少</label></div></div>

      <div class="disease-section"><h3>摄食减少或消化吸收障碍</h3><label class="check-option"><input v-model="intakeUnder50Over1w" type="checkbox" /><span>摄入量≤50%的能量需求超过一周</span></label><label class="check-option"><input v-model="anyIntakeReductionOver2w" type="checkbox" /><span>任何摄入量减少超过2周</span></label><div class="disease-group"><h4>任何影响消化吸收的慢性胃肠状况</h4><label v-for="item in giSymptomOptions" :key="item.id" class="check-option"><input v-model="giSymptoms" type="checkbox" :value="item.id" /><span>{{ item.name }}</span></label></div><div class="disease-group"><h4>有关疾病</h4><label v-for="item in nutritionImpactOptions" :key="item.id" class="check-option"><input v-model="nutritionImpactConditions" type="checkbox" :value="item.id" /><span>{{ item.name }}</span></label></div></div>

      <div class="disease-section"><h3>炎症或疾病负担</h3><div class="disease-group"><h4>急性疾病或损伤有关</h4><label v-for="item in acuteDiseaseOptions" :key="item.id" class="check-option"><input v-model="acuteDiseaseIds" type="checkbox" :value="item.id" /><span>{{ item.name }}</span></label></div><div class="disease-group"><h4>慢性或反复发作的疾病</h4><div class="cancer-option-block"><label class="check-option"><input v-model="chronicDiseaseIds" type="checkbox" :value="malignantTumorOption.id" /><span>{{ malignantTumorOption.name }}</span></label><div v-if="malignantTumorSelected" class="cancer-detail-grid"><label class="field-block"><span>具体部位</span><input v-model="cancerSite" type="text" placeholder="选填" /></label><label class="field-block"><span>癌症分期</span><select v-model="cancerStage"><option value="">选填</option><option value="早期">早</option><option value="中期">中</option><option value="晚期">晚</option><option value="终末期">终末期</option></select></label><div class="field-block"><span>此癌症是否是疾病相关性营养不良的病因</span><div class="segmented-options"><label><input v-model="cancerMalnutritionRelated" type="radio" value="true" />是</label><label><input v-model="cancerMalnutritionRelated" type="radio" value="false" />否</label><label><input v-model="cancerMalnutritionRelated" type="radio" value="" />未填</label></div></div></div></div><label v-for="item in chronicDiseaseOptions" :key="item.id" class="check-option"><input v-model="chronicDiseaseIds" type="checkbox" :value="item.id" /><span>{{ item.name }}</span></label></div><div class="disease-group inflammation-fields"><h4>炎症状态指标</h4><small>轻度、短暂的升高不纳入</small><label class="field-block"><span>CRP</span><input v-model="crp" type="number" min="0" step="0.1" placeholder="选填，如有检测结果请填写" /><small>mg/L</small></label><label class="field-block"><span>IL-6C</span><input v-model="il6" type="number" min="0" step="0.1" placeholder="选填，如有检测结果请填写" /><small>pg/mL</small></label></div></div>
      <p v-if="errorMessage" class="error-alert compact-alert">{{ errorMessage }}</p>
      <button v-if="showSubmit" class="primary-button" type="button" :disabled="loading || !formReady" @click="submit"><span v-if="loading" class="spinner" aria-hidden="true"></span>{{ loading ? '评估中...' : '开始评估 - GLIM' }}</button>
      <p v-if="touched && !formReady" class="field-error">仍有必填项未完成。</p>
    </div>
    <section v-if="result" class="assessment-result" :class="result.is_malnourished ? 'risk' : 'good'"><div class="score-hero"><strong>{{ result.is_malnourished ? '营养不良' : '未诊断营养不良' }}</strong><em v-if="result.severity" :class="result.severity.includes('重度') ? 'severity-red' : 'severity-orange'">{{ result.severity }}</em></div><div class="result-metrics glim-result-metrics"><div><span>诊断依据</span><p v-for="reason in glimDiagnosisReasons" :key="reason" class="metric-reason">{{ reason }}</p></div></div><div class="criteria-columns"><div><h3>表型标准</h3><span v-for="item in result.phenotypic_criteria_triggered" :key="item" class="tag-pill">{{ item }}</span><p v-if="!result.phenotypic_criteria_triggered.length">未触发</p></div><div><h3>病因标准</h3><div v-for="group in formatEtiologicalCriteria(result.etiological_criteria_triggered)" :key="group.title" class="criteria-group"><h4>{{ group.title }}</h4><span v-for="option in group.options" :key="`${group.title}-${option}`" class="tag-pill">{{ option }}</span></div><p v-if="!result.etiological_criteria_triggered.length">未触发</p></div></div><div class="result-metrics detail-metrics"><div><span>6个月内体重丢失</span><strong>{{ glimLossText(result.weight_loss_6m_pct) }}</strong></div><div><span>6个月以上体重丢失</span><strong>{{ glimLossText(result.weight_loss_over6m_pct) }}</strong></div><div><span>BMI</span><strong>{{ glimBmiText(result) }}</strong></div></div><button class="secondary-button" type="button" @click="resetResult">重新评估</button></section>
  </section>
</template>
