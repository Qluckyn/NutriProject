<script setup>
import { onMounted, reactive, ref } from 'vue'
import { API_BASE } from '../config'
import PatientInfoCard from './PatientInfoCard.vue'
import WeightRecordTable from './WeightRecordTable.vue'
import IntakeRecord from './IntakeRecord.vue'
import NRS2002Form from './NRS2002Form.vue'
import MNASFForm from './MNASFForm.vue'
import GLIMForm from './GLIMForm.vue'

const activeScale = ref('nrs')
const showErrors = ref(false)
const diseaseError = ref('')
const diseases = ref([])
const patient = reactive({ name: '', age: '', gender: 'male', height: '', calfCircumference: '' })
const weights = reactive(Object.fromEntries(Array.from({ length: 13 }, (_, index) => [String(index), ''])))
const intakeWeeks = reactive({ 1: '', 2: '', 3: '', 4: '' })
const intakeLastWeek = ref('')

const scaleTabs = [
  { key: 'nrs', label: 'NRS-2002 营养风险筛查' },
  { key: 'mna', label: 'MNA-SF 微型营养评估简表' },
  { key: 'glim', label: 'GLIM 营养不良评定标准' },
]

// 疾病列表由后端配置驱动，服务重启后可反映 diseases.json 的变更。
onMounted(async () => {
  try {
    const response = await fetch(`${API_BASE}/diseases`)
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || '疾病列表加载失败。')
    diseases.value = data.diseases || []
  } catch (error) {
    diseaseError.value = error.message || '无法连接后端服务，疾病列表暂不可用。'
  }
})

function markValidationFailed() {
  showErrors.value = true
}

function updatePatient(next) {
  Object.assign(patient, next)
}

function updateWeights(next) {
  Object.assign(weights, next)
}

function updateWeeks(next) {
  Object.assign(intakeWeeks, next)
}
</script>

<template>
  <section class="assessment-panel">
    <PatientInfoCard :model-value="patient" :show-errors="showErrors" @update:model-value="updatePatient" />
    <WeightRecordTable :model-value="weights" :show-errors="showErrors" @update:model-value="updateWeights" />
    <IntakeRecord :weeks="intakeWeeks" :show-errors="showErrors" @update:weeks="updateWeeks" @update:last-week="intakeLastWeek = $event" />

    <p v-if="diseaseError" class="error-alert">{{ diseaseError }}</p>

    <section class="form-card scale-tabs-card">
      <div class="sub-tab-bar" role="tablist" aria-label="量表评估类型">
        <button v-for="tab in scaleTabs" :key="tab.key" type="button" :class="{ active: activeScale === tab.key }" @click="activeScale = tab.key">{{ tab.label }}</button>
      </div>

      <NRS2002Form v-if="activeScale === 'nrs'" :patient="patient" :weights="weights" :intake-last-week="intakeLastWeek" :diseases="diseases" @validation-failed="markValidationFailed" />
      <MNASFForm v-if="activeScale === 'mna'" :patient="patient" :weights="weights" :intake-last-week="intakeLastWeek" @validation-failed="markValidationFailed" @highlight-calf="showErrors = true" />
      <GLIMForm v-if="activeScale === 'glim'" :patient="patient" :weights="weights" :diseases="diseases" @validation-failed="markValidationFailed" />
    </section>
  </section>
</template>
