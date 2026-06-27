<script setup>
import { computed, onMounted, provide, reactive, ref, watch } from 'vue'
import { API_BASE } from './config'
import PatientInfoCard from './components/PatientInfoCard.vue'
import WeightRecordTable from './components/WeightRecordTable.vue'
import IntakeRecord from './components/IntakeRecord.vue'
import ImageUploader from './components/ImageUploader.vue'
import ResultPanel from './components/ResultPanel.vue'
import NRS2002Form from './components/NRS2002Form.vue'
import MNASFForm from './components/MNASFForm.vue'
import GLIMForm from './components/GLIMForm.vue'

const emptyDraft = () => ({
  current_step: 1,
  skipped_mnasf: false,
  patient_info: {},
  weight_records: {},
  intake_records: {},
  nrs2002_form: {},
  mnasf_form: {},
  glim_form: {},
  images: { front: null, left: null, right: null },
  image_result: null,
  nrs2002_result: null,
  mnasf_result: null,
  glim_result: null,
})

const steps = [
  { number: 1, label: 'NRS-2002 营养风险筛查' },
  { number: 2, label: 'MNA-SF 微型营养评估', optional: true },
  { number: 3, label: '面部图像筛查' },
  { number: 4, label: 'GLIM 营养不良评定' },
  { number: 5, label: '综合结果' },
]

const uploaders = [
  { key: 'front', title: '正面（Front）', subtitle: '上传正面面部图像' },
  { key: 'left', title: '左45°（Left）', subtitle: '上传左45°面部图像' },
  { key: 'right', title: '右45°（Right）', subtitle: '上传右45°面部图像' },
]

const draftData = reactive(emptyDraft())
const draftLoaded = ref(false)
const currentStep = ref(1)
const skippedMnaSF = ref(false)
const showErrors = ref(false)
const clearToken = ref(0)
const resetToken = ref(0)
const diseases = ref([])
const nrsDiseases = ref([])
const glimConfig = ref(null)
const diseaseError = ref('')
const imageError = ref('')
const imageLoading = ref(false)
const pendingImageUploads = ref(0)
const nrsFormRef = ref(null)
const mnaFormRef = ref(null)
const glimFormRef = ref(null)
let draftTimer = null

const patientInfo = reactive({ name: '', age: '', gender: 'male', height: '', calfCircumference: '' })
const weightRecords = reactive(Object.fromEntries(Array.from({ length: 13 }, (_, index) => [String(index), ''])))
const intakeRecords = reactive({ 1: '', 2: '', 3: '', 4: '' })
const intakeLastWeek = ref('')
const imageFiles = reactive({ front: null, left: null, right: null })
const nrs2002Result = ref(null)
const mnaSFResult = ref(null)
const imageResult = ref(null)
const glimResult = ref(null)
// 综合结果页的勾选状态只用于当前前端会话，不写入草稿。
const finalResultSelection = reactive({ nrs2002: false, mnaSF: false, image: false, glim: false })

const patientReady = computed(() => Boolean(patientInfo.age && patientInfo.height))
const step1VisibleMonths = [0, 1, 2, 3]
const step1RequiredMonths = [0, 1, 2, 3]
const step2VisibleMonths = [0, 3]
const step2RequiredMonths = [0, 3]
const step4VisibleMonths = [0, 6, 12]
const step4RequiredMonths = [0, 6, 12]
const step1Ready = computed(() => patientReady.value && step1RequiredMonths.every((month) => weightRecords[String(month)]) && intakeLastWeek.value !== '')
const step2Ready = computed(() => patientReady.value && step2RequiredMonths.every((month) => weightRecords[String(month)]) && intakeLastWeek.value !== '')
const step4Ready = computed(() => patientReady.value && step4RequiredMonths.every((month) => weightRecords[String(month)]))
const hasDraftImage = computed(() => Object.values(draftData.images || {}).some((item) => item?.saved))
const canSubmitImage = computed(() => hasDraftImage.value && pendingImageUploads.value === 0 && !imageLoading.value)
const finalResultOptions = computed(() => [
  { key: 'nrs2002', label: 'NRS-2002 营养风险筛查', visible: Boolean(nrs2002Result.value) },
  { key: 'mnaSF', label: 'MNA-SF 微型营养评估', visible: Boolean(mnaSFResult.value && !skippedMnaSF.value) },
  { key: 'image', label: '面部图像筛查', visible: Boolean(imageResult.value) },
  { key: 'glim', label: 'GLIM 营养不良评定', visible: Boolean(glimResult.value) },
])

function replaceDraftData(nextDraft) {
  Object.assign(draftData, emptyDraft(), nextDraft || {})
  draftData.images = { front: null, left: null, right: null, ...(draftData.images || {}) }
}

function syncStateFromDraft() {
  Object.assign(patientInfo, { name: '', age: '', gender: 'male', height: '', calfCircumference: '' }, draftData.patient_info || {})
  Object.assign(weightRecords, Object.fromEntries(Array.from({ length: 13 }, (_, index) => [String(index), ''])), draftData.weight_records || {})
  Object.assign(intakeRecords, { 1: '', 2: '', 3: '', 4: '' }, draftData.intake_records || {})
  intakeLastWeek.value = intakeRecords['4'] || ''
  nrs2002Result.value = draftData.nrs2002_result || null
  mnaSFResult.value = draftData.mnasf_result || null
  imageResult.value = draftData.image_result || null
  glimResult.value = draftData.glim_result || null
  skippedMnaSF.value = Boolean(draftData.skipped_mnasf)
  currentStep.value = Number(draftData.current_step || inferStepFromDraft())
}

function inferStepFromDraft() {
  if (draftData.glim_result) return 5
  if (draftData.image_result) return 4
  if (draftData.mnasf_result || draftData.skipped_mnasf) return 3
  if (draftData.nrs2002_result) return 2
  return 1
}

// 防抖保存完整草稿，步骤状态和表单数据统一交给后端草稿接口持久化。
function saveDraft() {
  if (!draftLoaded.value) return
  window.clearTimeout(draftTimer)
  draftTimer = window.setTimeout(async () => {
    try {
      await fetch(`${API_BASE}/draft`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draftData),
      })
    } catch (error) {
      console.warn('保存草稿失败', error)
    }
  }, 500)
}

function beginDraftImageUpload() {
  pendingImageUploads.value += 1
}

function endDraftImageUpload() {
  pendingImageUploads.value = Math.max(0, pendingImageUploads.value - 1)
}

provide('draftContext', {
  draftData,
  draftLoaded,
  saveDraft,
  replaceDraftData,
  beginDraftImageUpload,
  endDraftImageUpload,
})

onMounted(async () => {
  try {
    const response = await fetch(`${API_BASE}/draft`)
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || '草稿读取失败。')
    replaceDraftData(data)
    syncStateFromDraft()
  } catch (error) {
    console.warn(error.message || '草稿读取失败。')
  } finally {
    draftLoaded.value = true
  }

  try {
    const response = await fetch(`${API_BASE}/diseases`)
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || '疾病列表加载失败。')
    diseases.value = data.diseases || []
    nrsDiseases.value = data.nrs2002?.diseases || data.diseases || []
    glimConfig.value = data.glim || null
  } catch (error) {
    diseaseError.value = error.message || '无法连接后端服务，疾病列表暂不可用。'
  }
})

watch(currentStep, (value) => {
  draftData.current_step = value
  saveDraft()
})

watch(skippedMnaSF, (value) => {
  draftData.skipped_mnasf = value
  saveDraft()
})

function updatePatient(next) {
  Object.assign(patientInfo, next)
  draftData.patient_info = { ...patientInfo }
  saveDraft()
}

function updateWeights(next) {
  Object.assign(weightRecords, next)
  draftData.weight_records = { ...weightRecords }
  saveDraft()
}

function updateWeeks(next) {
  Object.assign(intakeRecords, next)
  draftData.intake_records = { ...intakeRecords }
  saveDraft()
}

function updateLastWeek(value) {
  intakeLastWeek.value = value
}

function markValidationFailed() {
  showErrors.value = true
}

function setNrsResult(value) {
  nrs2002Result.value = value
  draftData.nrs2002_result = value
  saveDraft()
}

function setMnaResult(value) {
  mnaSFResult.value = value
  draftData.mnasf_result = value
  if (value) skippedMnaSF.value = false
  saveDraft()
}

function setGlimResult(value) {
  glimResult.value = value
  draftData.glim_result = value
  saveDraft()
}

function submitNrs() {
  showErrors.value = true
  if (!step1Ready.value) return
  nrsFormRef.value?.submit()
}

function submitMna() {
  showErrors.value = true
  if (!step2Ready.value) return
  mnaFormRef.value?.submit()
}

function submitGlim() {
  showErrors.value = true
  if (!step4Ready.value) return
  glimFormRef.value?.submit()
}

function skipMna() {
  skippedMnaSF.value = true
  setMnaResult(null)
  currentStep.value = 3
}

function onFileChange(viewKey, file) {
  imageFiles[viewKey] = file
  imageError.value = ''
}

function onUploadError(message) {
  imageError.value = message
}

async function appendDraftImage(formData, view) {
  const response = await fetch(`${API_BASE}/draft/image/${view}`)
  if (!response.ok) return
  const blob = await response.blob()
  formData.append(view, new File([blob], `${view}.jpg`, { type: 'image/jpeg' }))
}

// 使用 /predict 接口提交图片；草稿恢复场景下先把已保存图片取回再组装为上传表单。
async function submitPrediction() {
  if (!canSubmitImage.value) return
  imageLoading.value = true
  imageError.value = ''
  imageResult.value = null
  draftData.image_result = null
  saveDraft()

  try {
    const formData = new FormData()
    for (const view of ['front', 'left', 'right']) {
      if (imageFiles[view]) {
        formData.append(view, imageFiles[view])
      } else if (draftData.images?.[view]?.saved) {
        await appendDraftImage(formData, view)
      }
    }

    const response = await fetch(`${API_BASE}/predict`, { method: 'POST', body: formData })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || '筛查请求失败，请稍后重试。')
    imageResult.value = data
    draftData.image_result = data
    saveDraft()
  } catch (error) {
    imageError.value = error.message || '网络错误或服务不可用，请确认后端服务已启动。'
  } finally {
    imageLoading.value = false
  }
}

async function resetFinalResultSelection() {
  Object.assign(finalResultSelection, { nrs2002: false, mnaSF: false, image: false, glim: false })
}

async function resetAll() {
  try {
    const response = await fetch(`${API_BASE}/draft`, { method: 'DELETE' })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || '清除草稿失败。')
    replaceDraftData(data)
  } catch (error) {
    console.warn(error.message || '清除草稿失败。')
    replaceDraftData(emptyDraft())
  }
  syncStateFromDraft()
  Object.assign(imageFiles, { front: null, left: null, right: null })
  showErrors.value = false
  imageError.value = ''
  clearToken.value += 1
  resetToken.value += 1
  resetFinalResultSelection()
  currentStep.value = 1
}

function goPrevious() {
  currentStep.value = Math.max(1, currentStep.value - 1)
}

function stepClass(step) {
  return {
    active: step.number === currentStep.value,
    complete: step.number < currentStep.value,
    pending: step.number > currentStep.value,
  }
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

function percent(value) {
  return `${Math.round(Number(value || 0) * 10000) / 100}%`
}
</script>

<template>
  <main class="page-shell">
    <header class="page-header">
      <p class="eyebrow">Nutri Screening</p>
      <h1>营养状态筛查系统</h1>
      <p>基于面部图像与临床量表的老年营养不良辅助筛查</p>
    </header>

    <nav class="linear-stepper" aria-label="筛查流程进度">
      <div v-for="step in steps" :key="step.number" class="linear-step" :class="stepClass(step)">
        <span class="step-index">{{ step.number < currentStep ? '✓' : step.number }}</span>
        <span class="step-label">{{ step.label }}</span>
        <em v-if="step.optional">可跳过</em>
      </div>
    </nav>

    <PatientInfoCard
      :key="`patient-${clearToken}`"
      :model-value="patientInfo"
      :show-errors="showErrors"
      :collapsed="currentStep > 1"
      :readonly="currentStep > 1"
      @update:model-value="updatePatient"
    />

    <p v-if="diseaseError" class="error-alert">{{ diseaseError }}</p>

    <section v-if="currentStep === 1" class="step-panel">
      <WeightRecordTable :key="`weight-${clearToken}`" :model-value="weightRecords" :show-errors="showErrors" :visible-months="step1VisibleMonths" :required-months="step1RequiredMonths" @update:model-value="updateWeights" />
      <IntakeRecord :key="`intake-${clearToken}`" :weeks="intakeRecords" :show-errors="showErrors" @update:weeks="updateWeeks" @update:last-week="updateLastWeek" />
      <NRS2002Form ref="nrsFormRef" :patient="patientInfo" :weights="weightRecords" :intake-last-week="intakeLastWeek" :diseases="nrsDiseases" :show-submit="false" @validation-failed="markValidationFailed" @assessed="setNrsResult" />
      <div class="step-actions">
        <button class="primary-button" type="button" :disabled="!step1Ready" @click="submitNrs">开始评估</button>
        <button v-if="nrs2002Result" class="primary-button" type="button" @click="currentStep = 2">下一步</button>
      </div>
    </section>

    <section v-if="currentStep === 2" class="step-panel">
      <section class="form-card readonly-summary-card">
        <div class="section-title-row"><div><p class="section-kicker">Summary</p><h2>步骤1数据摘要</h2></div></div>
        <div class="result-metrics three">
          <div><span>体重数据</span><strong>已从步骤1读取</strong></div>
          <div><span>摄食量</span><strong>最近一周 {{ intakeLastWeek || '-' }}%</strong></div>
          <div><span>3个月体重</span><strong>{{ weightRecords['3'] || '可在下方补填' }}{{ weightRecords['3'] ? 'kg' : '' }}</strong></div>
        </div>
      </section>
      <WeightRecordTable :model-value="weightRecords" :show-errors="showErrors" :visible-months="step2VisibleMonths" :required-months="step2RequiredMonths" @update:model-value="updateWeights" />
      <MNASFForm ref="mnaFormRef" :patient="patientInfo" :weights="weightRecords" :intake-last-week="intakeLastWeek" :show-submit="false" @validation-failed="markValidationFailed" @highlight-calf="showErrors = true" @assessed="setMnaResult" />
      <div class="step-actions split-actions">
        <button class="secondary-button" type="button" @click="goPrevious">上一步</button>
        <span class="action-spacer"></span>
        <button class="secondary-button" type="button" @click="skipMna">跳过此步骤</button>
        <button class="primary-button" type="button" :disabled="!step2Ready" @click="submitMna">开始评估</button>
        <button v-if="mnaSFResult" class="primary-button" type="button" @click="currentStep = 3">下一步</button>
      </div>
    </section>

    <section v-if="currentStep === 3" class="step-panel">
      <section class="workspace image-step-workspace">
        <div class="upload-grid">
          <ImageUploader v-for="item in uploaders" :key="item.key" :view-key="item.key" :title="item.title" :subtitle="item.subtitle" :reset-token="resetToken" @change="onFileChange" @error="onUploadError" />
        </div>
        <p v-if="imageError" class="error-alert">{{ imageError }}</p>
      </section>
      <ResultPanel v-if="imageResult" :result="imageResult" :show-actions="false" />
      <div class="step-actions split-actions">
        <button class="secondary-button" type="button" @click="goPrevious">上一步</button>
        <span class="action-spacer"></span>
        <button class="primary-button" type="button" :disabled="!canSubmitImage" @click="submitPrediction">
          <span v-if="imageLoading" class="spinner" aria-hidden="true"></span>
          {{ imageLoading ? '分析中...' : pendingImageUploads > 0 ? '图片保存中...' : '开始筛查' }}
        </button>
        <button v-if="imageResult" class="primary-button" type="button" @click="currentStep = 4">下一步</button>
      </div>
    </section>

    <section v-if="currentStep === 4" class="step-panel">
      <section class="form-card readonly-summary-card">
        <div class="section-title-row"><div><p class="section-kicker">Summary</p><h2>步骤1数据摘要</h2></div></div>
        <div class="result-metrics three">
          <div><span>当前体重</span><strong>已从步骤1读取</strong></div>
          <div><span>0个月</span><strong>{{ weightRecords['0'] || '-' }}kg</strong></div>
          <div><span>6/12个月</span><strong>{{ weightRecords['6'] || '待补填' }}{{ weightRecords['6'] ? 'kg' : '' }} / {{ weightRecords['12'] || '待补填' }}{{ weightRecords['12'] ? 'kg' : '' }}</strong></div>
        </div>
      </section>
      <WeightRecordTable :model-value="weightRecords" :show-errors="showErrors" :visible-months="step4VisibleMonths" :required-months="step4RequiredMonths" :readonly-months="[0]" @update:model-value="updateWeights" />
      <GLIMForm ref="glimFormRef" :patient="patientInfo" :weights="weightRecords" :diseases="diseases" :glim-config="glimConfig" :show-submit="false" @validation-failed="markValidationFailed" @assessed="setGlimResult" />
      <div class="step-actions split-actions">
        <button class="secondary-button" type="button" @click="goPrevious">上一步</button>
        <span class="action-spacer"></span>
        <button class="primary-button" type="button" :disabled="!step4Ready" @click="submitGlim">开始评估</button>
        <button v-if="glimResult" class="primary-button" type="button" @click="currentStep = 5">查看综合结果</button>
      </div>
    </section>

    <section v-if="currentStep === 5" class="step-panel">
      <section class="final-result-selector" aria-label="选择要查看的综合结果">
        <label v-for="option in finalResultOptions.filter((item) => item.visible)" :key="option.key" class="final-result-check">
          <input v-model="finalResultSelection[option.key]" type="checkbox" />
          <span>{{ option.label }}</span>
        </label>
        <p>请勾选需要查看的评估结果</p>
      </section>

      <div class="final-results-grid">
        <section v-if="nrs2002Result && finalResultSelection.nrs2002" class="assessment-result" :class="nrs2002Result.has_risk ? 'risk' : 'good'">
          <div class="score-hero"><span>NRS-2002</span><strong>{{ nrs2002Result.total_score }}</strong><em>{{ nrs2002Result.risk_level }}</em></div>
          <div class="result-metrics three"><div><span>营养状态受损</span><strong>{{ nrs2002Result.nutrition_score }}分</strong></div><div><span>疾病严重程度</span><strong>{{ nrs2002Result.disease_score }}分</strong></div><div><span>年龄</span><strong>{{ nrs2002Result.age_score }}分</strong></div></div>
          <p class="message-text">{{ nrs2002Result.message }}</p>
        </section>

        <section v-if="mnaSFResult && !skippedMnaSF && finalResultSelection.mnaSF" class="assessment-result" :class="mnaSFResult.level === '营养正常' ? 'good' : mnaSFResult.level === '营养不良风险' ? 'caution' : 'risk'">
          <div class="score-hero"><span>MNA-SF</span><strong>{{ mnaSFResult.total_score }}/14</strong><em>{{ mnaSFResult.level }}</em></div>
          <div class="progress-track"><span class="progress-fill success" :style="{ width: `${Math.min(100, mnaSFResult.total_score / 14 * 100)}%` }"></span></div>
          <p class="message-text">{{ mnaSFResult.message }}</p>
        </section>

        <ResultPanel v-if="imageResult && finalResultSelection.image" :result="imageResult" :show-actions="false" />

        <section v-if="glimResult && finalResultSelection.glim" class="assessment-result" :class="glimResult.is_malnourished ? 'risk' : 'good'">
          <div class="score-hero"><span>GLIM</span><strong>{{ glimResult.is_malnourished ? '营养不良' : '未诊断营养不良' }}</strong><em v-if="glimResult.severity">{{ glimResult.severity }}</em></div>
          <div class="criteria-columns"><div><h3>表型标准</h3><span v-for="item in glimResult.phenotypic_criteria_triggered" :key="item" class="tag-pill">{{ item }}</span><p v-if="!glimResult.phenotypic_criteria_triggered.length">未触发</p></div><div><h3>病因标准</h3><div v-for="group in formatEtiologicalCriteria(glimResult.etiological_criteria_triggered)" :key="group.title" class="criteria-group"><h4>{{ group.title }}</h4><span v-for="option in group.options" :key="`${group.title}-${option}`" class="tag-pill">{{ option }}</span></div><p v-if="!glimResult.etiological_criteria_triggered.length">未触发</p></div></div>
          <div class="result-metrics three"><div><span>6个月内体重丢失</span><strong>{{ glimResult.weight_loss_6m_pct }}%</strong></div><div><span>6个月以上体重丢失</span><strong>{{ glimResult.weight_loss_over6m_pct }}%</strong></div><div><span>BMI</span><strong>{{ glimResult.bmi }}</strong></div></div>
          <p class="message-text">{{ glimResult.message }}</p>
        </section>
      </div>
      <div class="step-actions split-actions">
        <button class="secondary-button" type="button" @click="goPrevious">上一步</button>
        <span class="action-spacer"></span>
        <button class="secondary-button" type="button" @click="resetAll">重新开始</button>
      </div>
    </section>
  </main>
</template>

<style scoped>
.linear-stepper {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin: 0 0 20px;
}

.linear-step {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 58px;
  padding: 10px 12px;
  border: 1px solid #dceaf2;
  border-radius: 8px;
  background: #fff;
  color: #7a8795;
}

.linear-step.active {
  border-color: #1689a7;
  background: #eefaff;
  color: #126981;
}

.linear-step.complete {
  border-color: #9cd8bb;
  background: #f1fbf5;
  color: #267a48;
}

.step-index {
  display: inline-grid;
  flex: 0 0 28px;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 999px;
  background: #e7eef4;
  color: inherit;
  font-weight: 800;
}

.linear-step.active .step-index {
  background: #1689a7;
  color: #fff;
}

.linear-step.complete .step-index {
  background: #2a9d55;
  color: #fff;
}

.step-label {
  min-width: 0;
  font-size: 13px;
  font-weight: 800;
  line-height: 1.3;
}

.linear-step em {
  flex: 0 0 auto;
  padding: 2px 6px;
  border-radius: 999px;
  background: #f2f6f9;
  font-size: 12px;
  font-style: normal;
  font-weight: 700;
}

.step-panel {
  display: grid;
  gap: 18px;
  margin-top: 18px;
}

.step-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}

/* 全局 secondary-button 带有顶部间距，步骤底部按钮需要同一水平线对齐。 */
.step-actions .secondary-button {
  margin-top: 0;
}

.split-actions {
  justify-content: flex-start;
}

.action-spacer {
  flex: 1 1 auto;
}

.readonly-summary-card {
  border-style: dashed;
}

.image-step-workspace {
  margin-top: 0;
}

.final-result-selector {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 18px;
  padding: 16px;
  border: 1px solid #dceaf2;
  border-radius: 8px;
  background: #fff;
}

.final-result-check {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #263746;
  font-size: 14px;
  font-weight: 800;
}

.final-result-check input {
  width: 16px;
  height: 16px;
  accent-color: #1689a7;
}

.final-result-selector p {
  flex-basis: 100%;
  margin: 0;
  color: #7a8795;
  font-size: 13px;
  font-weight: 700;
}

.final-results-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: stretch;
  gap: 18px;
}

/* 综合结果卡片统一作为网格项展示，避免 ResultPanel 的全局上边距造成错位。 */
.final-results-grid > .assessment-result,
.final-results-grid > .result-panel {
  height: 100%;
  margin-top: 0;
}

@media (max-width: 900px) {
  .linear-stepper,
  .final-results-grid {
    grid-template-columns: 1fr;
  }

  .action-spacer {
    display: none;
  }
}
</style>
