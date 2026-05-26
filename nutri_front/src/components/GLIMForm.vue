<script setup>
import { computed, ref } from 'vue'
import { API_BASE } from '../config'

const props = defineProps({
  patient: { type: Object, required: true },
  weights: { type: Object, required: true },
  diseases: { type: Array, default: () => [] },
})

const emit = defineEmits(['validation-failed'])
const muscleLoss = ref('none')
const reducedIntake = ref('false')
const inflammationBurden = ref('false')
const selectedDiseaseIds = ref([])
const crp = ref('')
const il6 = ref('')
const loading = ref(false)
const errorMessage = ref('')
const result = ref(null)
const touched = ref(false)

const groupedDiseases = computed(() => [
  { type: 'acute', title: '急性疾病', items: props.diseases.filter((item) => item.glim_type === 'acute') },
  { type: 'chronic', title: '慢性疾病', items: props.diseases.filter((item) => item.glim_type === 'chronic') },
])
const formReady = computed(() => Boolean(props.patient.age && props.patient.height && props.weights['0'] && props.weights['6'] && props.weights['12']))

function buildPayload() {
  return {
    age: Number(props.patient.age),
    height: Number(props.patient.height),
    weight_records: Object.fromEntries(Object.entries(props.weights).filter(([, value]) => value !== '').map(([key, value]) => [key, Number(value)])),
    muscle_loss: muscleLoss.value,
    disease_ids: inflammationBurden.value === 'true' ? selectedDiseaseIds.value : selectedDiseaseIds.value,
    reduced_intake: reducedIntake.value === 'true',
    crp: crp.value === '' ? -1 : Number(crp.value),
    il6: il6.value === '' ? -1 : Number(il6.value),
  }
}

async function submit() {
  touched.value = true
  if (!formReady.value) {
    emit('validation-failed')
    errorMessage.value = '请先补全年龄、身高、当前体重、6个月前体重和12个月前体重。'
    return
  }

  loading.value = true
  errorMessage.value = ''
  result.value = null
  try {
    const response = await fetch(`${API_BASE}/assess/glim`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildPayload()),
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || 'GLIM评估失败，请稍后重试。')
    result.value = data
  } catch (error) {
    errorMessage.value = error.message || '网络错误，请确认后端服务已启动。'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="scale-form">
    <div class="form-card">
      <div class="section-title-row">
        <div>
          <p class="section-kicker">GLIM</p>
          <h2>营养不良评定标准</h2>
        </div>
      </div>

      <div class="field-block"><span>肌肉减少程度</span><small>请根据人体成分分析（BIA/DXA等）结果选择</small><div class="radio-stack"><label><input v-model="muscleLoss" type="radio" value="none" />无肌肉减少</label><label><input v-model="muscleLoss" type="radio" value="mild_moderate" />轻至中度减少</label><label><input v-model="muscleLoss" type="radio" value="severe" />重度减少</label></div></div>
      <div class="field-block"><span>摄食减少或消化吸收障碍</span><div class="segmented-options"><label><input v-model="reducedIntake" type="radio" value="true" />是</label><label><input v-model="reducedIntake" type="radio" value="false" />否</label></div></div>
      <div class="field-block"><span>炎症或疾病负担</span><div class="segmented-options"><label><input v-model="inflammationBurden" type="radio" value="true" />是</label><label><input v-model="inflammationBurden" type="radio" value="false" />否</label></div></div>

      <div class="disease-section">
        <h3>疾病勾选列表</h3>
        <div v-for="group in groupedDiseases" :key="group.type" class="disease-group">
          <h4>{{ group.title }}</h4>
          <label v-for="item in group.items" :key="item.id" class="check-option">
            <input v-model="selectedDiseaseIds" type="checkbox" :value="item.id" />
            <span>{{ item.name }}</span>
          </label>
        </div>
      </div>

      <div class="form-grid two-cols">
        <label class="field-block"><span>CRP</span><input v-model="crp" type="number" min="0" step="0.1" placeholder="选填，如有检测结果请填写" /><small>mg/L</small></label>
        <label class="field-block"><span>IL-6</span><input v-model="il6" type="number" min="0" step="0.1" placeholder="选填，如有检测结果请填写" /><small>pg/mL</small></label>
      </div>

      <p v-if="errorMessage" class="error-alert compact-alert">{{ errorMessage }}</p>
      <button class="primary-button" type="button" :disabled="loading || !formReady" @click="submit"><span v-if="loading" class="spinner" aria-hidden="true"></span>{{ loading ? '评估中...' : '开始评估 - GLIM' }}</button>
      <p v-if="touched && !formReady" class="field-error">仍有必填项未完成。</p>
    </div>

    <section v-if="result" class="assessment-result" :class="result.is_malnourished ? 'risk' : 'good'">
      <div class="score-hero"><span>诊断结果</span><strong>{{ result.is_malnourished ? '营养不良' : '未诊断营养不良' }}</strong><em v-if="result.severity" :class="result.severity.includes('重度') ? 'severity-red' : 'severity-orange'">{{ result.severity }}</em></div>
      <div class="criteria-columns">
        <div><h3>表型标准</h3><span v-for="item in result.phenotypic_criteria_triggered" :key="item" class="tag-pill">{{ item }}</span><p v-if="!result.phenotypic_criteria_triggered.length">未触发</p></div>
        <div><h3>病因标准</h3><span v-for="item in result.etiological_criteria_triggered" :key="item" class="tag-pill">{{ item }}</span><p v-if="!result.etiological_criteria_triggered.length">未触发</p></div>
      </div>
      <div class="result-metrics three"><div><span>6个月内体重丢失</span><strong>{{ result.weight_loss_6m_pct }}%</strong></div><div><span>6个月以上体重丢失</span><strong>{{ result.weight_loss_over6m_pct }}%</strong></div><div><span>BMI</span><strong>{{ result.bmi }}</strong></div></div>
      <p class="message-text">{{ result.message }}</p>
      <button class="secondary-button" type="button" @click="result = null">重新评估</button>
    </section>
  </section>
</template>
