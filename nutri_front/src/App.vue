<script setup>
import { computed, onMounted, provide, reactive, ref, watch } from 'vue'
import { API_BASE } from './config'
import PatientInfoCard from './components/PatientInfoCard.vue'
import WeightRecordTable from './components/WeightRecordTable.vue'
import IntakeRecord from './components/IntakeRecord.vue'
import ImageUploader from './components/ImageUploader.vue'
import ResultPanel from './components/ResultPanel.vue'
import ExplainabilityPanel from './components/ExplainabilityPanel.vue'
import NRS2002Form from './components/NRS2002Form.vue'
import MNASFForm from './components/MNASFForm.vue'
import GLIMForm from './components/GLIMForm.vue'
import HistoryPanel from './components/HistoryPanel.vue'
import SGAResultCard from './components/SGAResultCard.vue'

const emptyDraft = () => ({
  current_step: 1,
  skipped_mnasf: false,
  skipped_image: false,
  patient_info: {},
  weight_records: {},
  intake_records: {},
  nrs2002_form: {},
  mnasf_form: {},
  glim_form: {},
  image_screening_form: { giSymptoms: 'none', stressResponse: 'no_fever', ankleEdema: 'none' },
  images: { front: null, left: null, right: null },
  image_result: null,
  explain_result: null,
  nrs2002_result: null,
  mnasf_result: null,
  glim_result: null,
  personalized_analysis: null,
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
const validationMessage = ref('')
const imageLoading = ref(false)
const explainLoading = ref(false)
const explainError = ref('')
const pendingImageUploads = ref(0)
const nrsFormRef = ref(null)
const mnaFormRef = ref(null)
const glimFormRef = ref(null)
let draftTimer = null

const patientInfo = reactive({ name: '', recordNumber: '', consultingDoctor: '', age: '', gender: 'male', height: '' })
const weightRecords = reactive(Object.fromEntries(Array.from({ length: 13 }, (_, index) => [String(index), ''])))
const intakeRecords = reactive({ 1: '', 2: '', 3: '', 4: '' })
const intakeLastWeek = ref('')
const imageFiles = reactive({ front: null, left: null, right: null })
const imageScreeningForm = reactive({ giSymptoms: 'none', stressResponse: 'no_fever', ankleEdema: 'none' })
const nrs2002Result = ref(null)
const mnaSFResult = ref(null)
const imageResult = ref(null)
const explainResult = ref(null)
const showExplainResult = ref(false)
const explainExpandToken = ref(0)
const glimResult = ref(null)
const personalizedAnalysis = ref(null)
const personalizedLoading = ref(false)
const personalizedError = ref('')
const finalResultTab = ref('advice')
const reportDownloading = ref(false)
const reportDownloadError = ref('')
const reportMenuOpen = ref(false)
const historyOpen = ref(false)
const historySaving = ref(false)
const historyArchiveMessage = ref('')
const historyArchiveError = ref('')
// 综合结果页的勾选状态只用于当前前端会话，不写入草稿。
const finalResultSelection = reactive({ nrs2002: false, mnaSF: false, image: false, glim: false })

const step1VisibleMonths = [0, 1, 2, 3]
const step1RequiredMonths = [0]
const step2VisibleMonths = [0, 3]
const step2RequiredMonths = [0]
const step4VisibleMonths = [0, 6, 12]
const step4RequiredMonths = [0]
const step4MonthLabels = { 6: '6个月以内', 12: '6个月以上' }
const validPatientInfo = computed(() => validatePatientInfo() === '')
const step1Ready = computed(() => validPatientInfo.value && validateWeightRecords(step1RequiredMonths) === '' && intakeLastWeek.value !== '')
const step2Ready = computed(() => validPatientInfo.value && validateWeightRecords(step2RequiredMonths) === '' && intakeLastWeek.value !== '')
const step4Ready = computed(() => validPatientInfo.value && validateWeightRecords(step4RequiredMonths) === '')
const hasDraftImage = computed(() => Object.values(draftData.images || {}).some((item) => item?.saved))
const canSubmitImage = computed(() => pendingImageUploads.value === 0 && !imageLoading.value)
const sgaEvaluation = computed(() => imageResult.value?.sga_evaluation || null)

const finalResultOptions = computed(() => [

  { key: 'nrs2002', label: 'NRS-2002 营养风险筛查', visible: Boolean(nrs2002Result.value) },
  { key: 'mnaSF', label: 'MNA-SF 微型营养评估', visible: Boolean(mnaSFResult.value && !skippedMnaSF.value) },
  { key: 'image', label: '面部图像筛查', visible: Boolean(imageResult.value) },
  { key: 'glim', label: 'GLIM 营养不良评定', visible: Boolean(glimResult.value) },
])
const availableReportItems = computed(() => [
  nrs2002Result.value?.document_output && { key: 'nrs2002', label: 'NRS-2002' },
  mnaSFResult.value?.document_output && !skippedMnaSF.value && { key: 'mnasf', label: 'MNA-SF' },
  imageResult.value?.document_output && { key: 'image', label: '面部图像筛查（SGA）' },
  glimResult.value?.document_output && { key: 'glim', label: 'GLIM' },
].filter(Boolean))

function replaceDraftData(nextDraft) {
  Object.assign(draftData, emptyDraft(), nextDraft || {})
  draftData.images = { front: null, left: null, right: null, ...(draftData.images || {}) }
}

function syncStateFromDraft() {
  Object.assign(patientInfo, { name: '', recordNumber: '', consultingDoctor: '', age: '', gender: 'male', height: '' }, draftData.patient_info || {})
  Object.assign(weightRecords, Object.fromEntries(Array.from({ length: 13 }, (_, index) => [String(index), ''])), draftData.weight_records || {})
  Object.assign(intakeRecords, { 1: '', 2: '', 3: '', 4: '' }, draftData.intake_records || {})
  intakeLastWeek.value = intakeRecords['4'] || ''
  Object.assign(imageScreeningForm, { giSymptoms: 'none', stressResponse: 'no_fever', ankleEdema: 'none' }, draftData.image_screening_form || {})
  nrs2002Result.value = draftData.nrs2002_result || null
  mnaSFResult.value = draftData.mnasf_result || null
  imageResult.value = draftData.image_result || null
  explainResult.value = draftData.explain_result || null
  showExplainResult.value = Boolean(explainResult.value)
  glimResult.value = draftData.glim_result || null
  personalizedAnalysis.value = draftData.personalized_analysis || null
  skippedMnaSF.value = Boolean(draftData.skipped_mnasf)
  currentStep.value = Number(draftData.current_step || inferStepFromDraft())
}

function inferStepFromDraft() {
  if (draftData.glim_result) return 5
  if (draftData.image_result || draftData.skipped_image) return 4
  if (draftData.mnasf_result || draftData.skipped_mnasf) return 3
  if (draftData.nrs2002_result) return 2
  return 1
}

async function writeDraftNow() {
  const response = await fetch(`${API_BASE}/draft`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(draftData),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || '保存草稿失败。')
  }
}

// 防抖保存完整草稿，步骤状态和表单数据统一交给后端草稿接口持久化。
function saveDraft() {
  if (!draftLoaded.value) return
  window.clearTimeout(draftTimer)
  draftTimer = window.setTimeout(async () => {
    try {
      await writeDraftNow()
    } catch (error) {
      console.warn('保存草稿失败', error)
    }
  }, 500)
}

async function saveDraftNow() {
  if (!draftLoaded.value) return
  window.clearTimeout(draftTimer)
  draftTimer = null
  try {
    await writeDraftNow()
  } catch (error) {
    console.warn('保存草稿失败', error)
  }
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
  validationMessage.value = ''
  Object.assign(patientInfo, next)
  draftData.patient_info = { ...patientInfo }
  saveDraft()
}

function updateWeights(next) {
  validationMessage.value = ''
  Object.assign(weightRecords, next)
  draftData.weight_records = { ...weightRecords }
  saveDraft()
}

function updateImageScreeningField(field, value) {
  imageScreeningForm[field] = value
  draftData.image_screening_form = { ...imageScreeningForm }
  saveDraft()
}

function updateWeeks(next) {
  validationMessage.value = ''
  Object.assign(intakeRecords, next)
  draftData.intake_records = { ...intakeRecords }
  saveDraft()
}

function updateLastWeek(value) {
  validationMessage.value = ''
  intakeLastWeek.value = value
}

function markValidationFailed(message = '仍有必填项未完成。') {
  showErrors.value = true
  validationMessage.value = message
}

function validatePatientInfo() {
  if (patientInfo.age === '' || patientInfo.age === null || patientInfo.age === undefined || patientInfo.height === '' || patientInfo.height === null || patientInfo.height === undefined) return '请先补全患者年龄和身高。'

  const age = Number(patientInfo.age)
  if (!Number.isInteger(age) || age < 0 || age > 110) return '年龄需填写0到110之间的整数。'

  const height = Number(patientInfo.height)
  if (Number.isNaN(height) || height < 100 || height > 250) return '身高需填写100到250cm之间的数值。'

  return ''
}

function validateWeightRecords(requiredMonths = []) {
  const requiredKeys = requiredMonths.map((month) => String(month))
  const missing = requiredKeys.filter((month) => !weightRecords[month])
  if (missing.length) return '请先补全必填体重记录。'

  const invalid = Object.entries(weightRecords).filter(([, value]) => {
    if (value === '' || value === null || value === undefined) return false
    const weight = Number(value)
    return Number.isNaN(weight) || weight < 30 || weight > 200
  })
  if (invalid.length) return '体重需填写30到200kg之间的数值。'

  return ''
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
  validationMessage.value = ''
  showErrors.value = true
  const patientMessage = validatePatientInfo()
  if (patientMessage) {
    markValidationFailed(patientMessage)
    return
  }
  const weightMessage = validateWeightRecords(step1RequiredMonths)
  if (weightMessage) {
    markValidationFailed(weightMessage)
    return
  }
  if (!step1Ready.value) {
    markValidationFailed('请先补全患者年龄、身高、当前体重和最近一周摄食量。')
    return
  }
  nrsFormRef.value?.submit()
}

function submitMna() {
  validationMessage.value = ''
  showErrors.value = true
  const patientMessage = validatePatientInfo()
  if (patientMessage) {
    markValidationFailed(patientMessage)
    return
  }
  const weightMessage = validateWeightRecords(step2RequiredMonths)
  if (weightMessage) {
    markValidationFailed(weightMessage)
    return
  }
  if (!step2Ready.value) {
    markValidationFailed('请先补全患者年龄、身高、当前体重和最近一周摄食量。')
    return
  }
  mnaFormRef.value?.submit()
}

function submitGlim() {
  validationMessage.value = ''
  showErrors.value = true
  const patientMessage = validatePatientInfo()
  if (patientMessage) {
    markValidationFailed(patientMessage)
    return
  }
  const weightMessage = validateWeightRecords(step4RequiredMonths)
  if (weightMessage) {
    markValidationFailed(weightMessage)
    return
  }
  if (!step4Ready.value) {
    markValidationFailed('请先补全年龄、身高和当前体重。')
    return
  }
  glimFormRef.value?.submit()
}

function skipMna() {
  skippedMnaSF.value = true
  setMnaResult(null)
  currentStep.value = 3
}

function skipImageScreening() {
  draftData.skipped_image = true
  imageResult.value = null
  explainResult.value = null
  draftData.image_result = null
  draftData.explain_result = null
  showExplainResult.value = false
  currentStep.value = 4
  saveDraft()
}

function onFileChange(viewKey, file) {
  imageFiles[viewKey] = file
  draftData.skipped_image = false
  imageError.value = ''
  explainError.value = ''
  imageResult.value = null
  explainResult.value = null
  draftData.image_result = null
  draftData.explain_result = null
  showExplainResult.value = false
  saveDraft()
}

function onUploadError(message) {
  imageError.value = message
}

// 图片已在选择时保存到后端草稿；筛查时直接让后端读取草稿图片，避免二次上传。
async function submitPrediction() {
  if (!canSubmitImage.value) return
  if (!hasDraftImage.value) {
    imageError.value = ''
    explainResult.value = null
    draftData.explain_result = null
    showExplainResult.value = false
    imageLoading.value = true
    try {
      await saveDraftNow()
      const response = await fetch(`${API_BASE}/sga/evaluation`, { method: 'POST' })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || 'SGA 评估请求失败，请稍后重试。')
      imageResult.value = data
      draftData.image_result = data
      draftData.skipped_image = true
      await saveDraftNow()
    } catch (error) {
      imageError.value = error.message || 'SGA 评估请求失败，请稍后重试。'
    } finally {
      imageLoading.value = false
    }
    return
  }
  imageLoading.value = true
  explainLoading.value = false
  imageError.value = ''
  explainError.value = ''
  imageResult.value = null
  explainResult.value = null
  draftData.image_result = null
  draftData.explain_result = null
  showExplainResult.value = false
  await saveDraftNow()

  try {
    const response = await fetch(`${API_BASE}/predict/draft`, { method: 'POST' })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || '筛查请求失败，请稍后重试。')
    imageResult.value = data
    draftData.image_result = data
    await saveDraftNow()

  } catch (error) {
    imageError.value = error.message || '网络错误或服务不可用，请确认后端服务已启动。'
  } finally {
    imageLoading.value = false
  }
}

async function runExplainAnalysis() {
  if (!imageResult.value || explainLoading.value) return
  if (explainResult.value) {
    showExplainResult.value = true
    explainExpandToken.value += 1
    return
  }

  showExplainResult.value = true
  explainLoading.value = true
  explainError.value = ''
  try {
    const explainResponse = await fetch(API_BASE + '/explain/roi/draft', { method: 'POST' })
    const explainData = await explainResponse.json().catch(() => ({}))
    if (!explainResponse.ok) throw new Error(explainData.detail || '可解释性结果生成失败。')
    explainResult.value = explainData
    draftData.explain_result = explainData
    explainExpandToken.value += 1
    await saveDraftNow()
  } catch (error) {
    explainError.value = error.message || '可解释性结果暂不可用。'
  } finally {
    explainLoading.value = false
  }
}

async function triggerReportDownload(reportKey) {
  // 评估接口生成 DOCX 后已立即将结果及 document_output 写入后端草稿，
  // 下载无需再上传完整草稿（其中可能包含较大的 Base64 可解释性图片）。
  const response = await fetch(`${API_BASE}/reports/file/${reportKey}`)
  if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(data.detail || '报告下载失败。') }
  const disposition = response.headers.get('content-disposition') || ''
  const filenameMatch = disposition.match(/filename\*=UTF-8\x27\x27([^;]+)|filename="?([^";]+)"?/i)
  const filename = decodeURIComponent(filenameMatch?.[1] || filenameMatch?.[2] || `${reportKey}评估表.docx`)
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

async function triggerReportsArchiveDownload() {
  const response = await fetch(`${API_BASE}/reports/archive?download_at=${Date.now()}`, { cache: "no-store" })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || "报告打包下载失败。")
  }
  const disposition = response.headers.get("content-disposition") || ""
  const filenameMatch = disposition.match(/filename\*=UTF-8\x27\x27([^;]+)|filename="?([^";]+)"?/i)
  const filename = decodeURIComponent(filenameMatch?.[1] || filenameMatch?.[2] || "assessment_reports.zip")
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

async function downloadReport(report) {
  reportMenuOpen.value = false
  if (reportDownloading.value) return
  reportDownloading.value = true
  reportDownloadError.value = ''
  try { await triggerReportDownload(report.key) }
  catch (error) { reportDownloadError.value = error.message || '报告下载失败，请稍后重试。' }
  finally { reportDownloading.value = false }
}

async function downloadAllReports() {
  reportMenuOpen.value = false
  if (reportDownloading.value || !availableReportItems.value.length) return
  reportDownloading.value = true
  reportDownloadError.value = ''
  try {
    await triggerReportsArchiveDownload()
  } catch (error) {
    reportDownloadError.value = error.message || '批量下载失败，请稍后重试。'
  } finally { reportDownloading.value = false }
}

async function archiveCurrentHistory() {
  if (historySaving.value) return
  historySaving.value = true
  historyArchiveMessage.value = ''
  historyArchiveError.value = ''
  try {
    // 归档是明确的保存动作：先一次性保存当前表单快照，再由后端复制 DOCX 和图片。
    await writeDraftNow()
    const response = await fetch(`${API_BASE}/history`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ personalized_analysis: personalizedAnalysis.value }),
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || '保存历史记录失败。')
    historyArchiveMessage.value = `已保存为历史记录：${data.created_at}_${data.patient_name}`
  } catch (error) {
    historyArchiveError.value = error.message || '保存历史记录失败。'
  } finally {
    historySaving.value = false
  }
}


async function generatePersonalizedAnalysis() {
  if (personalizedLoading.value) return
  personalizedLoading.value = true
  personalizedError.value = ''
  try {
    // 后端从草稿读取数据并脱敏后调用 Qwen，前端不接触模型密钥。
    const response = await fetch(`${API_BASE}/analysis/personalized`, { method: 'POST' })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || '个性化建议生成失败，请稍后重试。')
    personalizedAnalysis.value = data.analysis
    draftData.personalized_analysis = data.analysis
    await writeDraftNow()
  } catch (error) {
    personalizedError.value = error.message || '个性化建议暂不可用，请稍后重试。'
  } finally {
    personalizedLoading.value = false
  }
}

async function resetFinalResultSelection() {
  finalResultTab.value = 'advice'
  personalizedAnalysis.value = null
  draftData.personalized_analysis = null
  personalizedError.value = ''
  personalizedLoading.value = false
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
  explainError.value = ''
  validationMessage.value = ''
  clearToken.value += 1
  resetToken.value += 1
  explainResult.value = null
  explainLoading.value = false
  showExplainResult.value = false
  resetFinalResultSelection()
  personalizedAnalysis.value = null
  personalizedError.value = ''
  personalizedLoading.value = false
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



function nrsLossText(value) {
  if (value === null || value === undefined) return '数据缺失'
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return '数据缺失'
  if (numeric <= 0) return '未丢失体重'
  return `${numeric}%`
}

function nrsBmiText(value) {
  if (value?.bmi === null || value?.bmi === undefined) return '数据缺失'
  return String(value.bmi)
}

function nrsMetricReasons(value, key) {
  const evidence = value?.score_evidence
  if (!evidence) return []
  if (key === 'nutrition') {
    const allItems = evidence.nutrition || []
    const score = Number(value.nutrition_score)
    if (score === 0) return ['正常营养状态']
    const triggeredItems = allItems.filter((item) => item.label !== '最终采用' && item.triggered && Number(item.score) === score)
    return triggeredItems.map((item) => item.reason).filter(Boolean)
  }
  if (key === 'disease') {
    if (Number(value.disease_score) === 0) return ['正常营养需求']
    return evidence.disease?.[0]?.reason ? [evidence.disease[0].reason] : []
  }
  if (key === 'age') return evidence.age?.[0]?.reason ? [evidence.age[0].reason] : []
  return []
}

function mnaLevelClass(level) {
  if (level === '营养正常') return 'good'
  if (level === '营养不良风险') return 'caution'
  return 'risk'
}

const mnaEvidenceKeyOrder = ['q1_appetite', 'q2_weight_loss', 'q3_mobility', 'q4_stress', 'q5_mental', 'q6_bmi_or_calf']
const mnaMetricLabels = {
  q1_appetite: '摄食量',
  q2_weight_loss: '近3个月体重下降',
  q3_mobility: '活动能力',
  q4_stress: '心理创伤或急性疾病',
  q5_mental: '精神心理状况',
  q6_bmi_or_calf: 'BMI/小腿围',
}

function mnaMetricLabel(key) {
  return mnaMetricLabels[key] || key
}

function mnaMetricReason(value, key) {
  const index = mnaEvidenceKeyOrder.indexOf(key)
  return index === -1 ? '' : value?.score_evidence?.[index]?.reason || ''
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

function glimDiagnosisReasons(value) {
  if (!value) return []
  if (!value.is_malnourished) return [value.message]

  const severeReasons = []
  const moderateReasons = []
  const age = Number(patientInfo.age)
  const bmi = Number(value.bmi)
  const loss6m = value.weight_loss_6m_pct === null || value.weight_loss_6m_pct === undefined ? null : Number(value.weight_loss_6m_pct)
  const lossOver6m = value.weight_loss_over6m_pct === null || value.weight_loss_over6m_pct === undefined ? null : Number(value.weight_loss_over6m_pct)
  const muscleLoss = draftData.glim_form?.muscleLoss

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
  if (muscleLoss === 'severe') severeReasons.push('重度肌肉减少，符合重度营养不良（2期）表型标准。')
  else if (muscleLoss === 'mild_moderate') moderateReasons.push('轻至中度肌肉减少，符合中度营养不良（1期）表型标准。')

  if (value.severity?.includes('重度')) return severeReasons.length ? severeReasons : value.phenotypic_criteria_triggered
  if (value.severity?.includes('中度')) return moderateReasons.length ? moderateReasons : value.phenotypic_criteria_triggered

  const reasons = [...severeReasons, ...moderateReasons]
  return reasons.length ? reasons : value.phenotypic_criteria_triggered
}

const imageScreeningLabels = {
  giSymptoms: {
    none: '无消化道症状',
    mild_under_2w: '轻度消化道症状持续时间＜2周',
    severe_over_2w: '重度消化道症状持续时间＞2周',
  },
  stressResponse: {
    no_fever: '无发热',
    temp_37_to_39_3d: '近3天体温波动在37℃～39℃之间',
    temp_ge_39_over_3d: '体温≥39℃持续3天以上',
  },
  ankleEdema: {
    none: '无',
    mild_moderate: '轻度～中度',
    severe: '重度',
  },
}

function imageScreeningLabel(field) {
  const value = imageScreeningForm[field]
  return value ? imageScreeningLabels[field]?.[value] || value : '未填写'
}

function formatIntakeFraction(value) {
  if (value === "" || value === null || value === undefined) return "-"
  const labels = { 0: "占正常进食0 ~ 1/4", 25: "占正常进食0 ~ 1/4", 50: "占正常进食的1/4 ~ 1/2", 75: "占正常进食的1/2 ~ 3/4", 100: "占正常进食的3/4以上" }
  const numeric = Number(value)
  return labels[numeric] || String(numeric / 100)
}
</script>

<template>
  <main class="page-shell">
  <header class="page-header">
    <button class="history-button" type="button" @click="historyOpen = true">历史记录</button>
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
      <p v-if="validationMessage && currentStep === 1" class="field-error">{{ validationMessage }}</p>
      <div class="step-actions">
        <button class="primary-button" type="button" @click="submitNrs">开始评估</button>
        <button v-if="nrs2002Result" class="primary-button" type="button" @click="currentStep = 2">下一步</button>
      </div>
    </section>

    <section v-if="currentStep === 2" class="step-panel">
      <WeightRecordTable :model-value="weightRecords" :show-errors="showErrors" :visible-months="step2VisibleMonths" :required-months="step2RequiredMonths" :readonly-months="[0]" @update:model-value="updateWeights" />
      <MNASFForm ref="mnaFormRef" :patient="patientInfo" :weights="weightRecords" :intake-last-week="intakeLastWeek" :show-submit="false" @validation-failed="markValidationFailed" @assessed="setMnaResult" />
      <p v-if="validationMessage && currentStep === 2" class="field-error">{{ validationMessage }}</p>
      <div class="step-actions split-actions">
        <button class="secondary-button" type="button" @click="goPrevious">上一步</button>
        <span class="action-spacer"></span>
        <button class="primary-button" type="button" @click="submitMna">开始评估</button>
        <button v-if="!mnaSFResult" class="secondary-button" type="button" @click="skipMna">跳过此步骤</button>
        <button v-if="mnaSFResult" class="primary-button" type="button" @click="currentStep = 3">下一步</button>
      </div>
    </section>

    <section v-if="currentStep === 3" class="step-panel">
      <WeightRecordTable :model-value="weightRecords" :show-errors="showErrors" :visible-months="[0, 6]" :required-months="[0]" :readonly-months="[0]" :month-labels="{ 0: '当前（0个月）', 6: '6个月以内' }" @update:model-value="updateWeights" />
      <section class="form-card">
        <div class="section-title-row"><div><p class="section-kicker">Clinical context</p><h2>临床补充信息</h2></div><span class="muted-note">均为选填，不参与面部 AI 预测</span></div>
        <div class="form-grid">
          <div class="field-block"><span>胃肠道症状</span><div class="radio-stack"><label><input :checked="imageScreeningForm.giSymptoms === 'none'" type="radio" name="gi-symptoms" @change="updateImageScreeningField('giSymptoms', 'none')" />无消化道症状</label><label><input :checked="imageScreeningForm.giSymptoms === 'mild_under_2w'" type="radio" name="gi-symptoms" @change="updateImageScreeningField('giSymptoms', 'mild_under_2w')" />轻度消化道症状持续时间＜2周</label><label><input :checked="imageScreeningForm.giSymptoms === 'severe_over_2w'" type="radio" name="gi-symptoms" @change="updateImageScreeningField('giSymptoms', 'severe_over_2w')" />重度消化道症状持续时间＞2周</label></div></div>
          <div class="field-block"><span>应激反应</span><div class="radio-stack"><label><input :checked="imageScreeningForm.stressResponse === 'no_fever'" type="radio" name="stress-response" @change="updateImageScreeningField('stressResponse', 'no_fever')" />无发热</label><label><input :checked="imageScreeningForm.stressResponse === 'temp_37_to_39_3d'" type="radio" name="stress-response" @change="updateImageScreeningField('stressResponse', 'temp_37_to_39_3d')" />近3天体温波动在37℃～39℃之间</label><label><input :checked="imageScreeningForm.stressResponse === 'temp_ge_39_over_3d'" type="radio" name="stress-response" @change="updateImageScreeningField('stressResponse', 'temp_ge_39_over_3d')" />体温≥39℃持续3天以上</label></div></div>
          <div class="field-block"><span>踝部水肿</span><div class="radio-stack"><label><input :checked="imageScreeningForm.ankleEdema === 'none'" type="radio" name="ankle-edema" @change="updateImageScreeningField('ankleEdema', 'none')" />无</label><label><input :checked="imageScreeningForm.ankleEdema === 'mild_moderate'" type="radio" name="ankle-edema" @change="updateImageScreeningField('ankleEdema', 'mild_moderate')" />轻度～中度</label><label><input :checked="imageScreeningForm.ankleEdema === 'severe'" type="radio" name="ankle-edema" @change="updateImageScreeningField('ankleEdema', 'severe')" />重度</label></div></div>
        </div>
      </section>
      <section class="workspace image-step-workspace">
        <div class="upload-grid">
          <ImageUploader v-for="item in uploaders" :key="item.key" :view-key="item.key" :title="item.title" :subtitle="item.subtitle" :reset-token="resetToken" @change="onFileChange" @error="onUploadError" />
        </div>
        <p v-if="imageError" class="error-alert">{{ imageError }}</p>
      </section>
      <ResultPanel v-if="imageResult && !imageResult.sga_only" :result="imageResult" :show-actions="false" />
      <SGAResultCard :evaluation="sgaEvaluation" />
      <ExplainabilityPanel v-if="showExplainResult && !imageResult?.sga_only" :result="explainResult" :loading="explainLoading" :error="explainError" :expand-token="explainExpandToken" />
      <div class="step-actions split-actions">
        <button class="secondary-button" type="button" @click="goPrevious">上一步</button>
        <span class="action-spacer"></span>
        <button v-if="imageResult && !imageResult.sga_only && !showExplainResult" class="secondary-button" type="button" :disabled="explainLoading" @click="runExplainAnalysis">
          <span v-if="explainLoading" class="spinner" aria-hidden="true"></span>
          <span v-if="explainLoading">可解释性分析中...</span>
          <span v-else>可解释性分析</span>
        </button>
        <button class="primary-button" type="button" :disabled="!canSubmitImage" @click="submitPrediction">
          <span v-if="imageLoading" class="spinner" aria-hidden="true"></span>
          {{ imageLoading ? '分析中...' : pendingImageUploads > 0 ? '图片保存中...' : '开始筛查' }}
        </button>
        <button v-if="imageResult" class="primary-button" type="button" @click="currentStep = 4">下一步</button>
      </div>
    </section>

    <section v-if="currentStep === 4" class="step-panel">
      <WeightRecordTable :model-value="weightRecords" :show-errors="showErrors" :visible-months="step4VisibleMonths" :required-months="step4RequiredMonths" :readonly-months="[0]" :month-labels="step4MonthLabels" @update:model-value="updateWeights" />
      <GLIMForm ref="glimFormRef" :patient="patientInfo" :weights="weightRecords" :diseases="diseases" :glim-config="glimConfig" :show-submit="false" @validation-failed="markValidationFailed" @assessed="setGlimResult" />
      <p v-if="validationMessage && currentStep === 4" class="field-error">{{ validationMessage }}</p>
      <div class="step-actions split-actions">
        <button class="secondary-button" type="button" @click="goPrevious">上一步</button>
        <span class="action-spacer"></span>
        <button class="primary-button" type="button" @click="submitGlim">开始评估</button>
        <button v-if="glimResult" class="primary-button" type="button" @click="currentStep = 5">查看综合结果</button>
      </div>
    </section>

    <section v-if="currentStep === 5" class="step-panel">
      <!-- 一级标签将评估卡片与大模型建议分开，减少同屏信息密度。 -->
      <nav class="final-tab-nav" aria-label="综合结果内容切换">
        <button class="final-tab" :class="{ active: finalResultTab === 'advice' }" type="button" @click="finalResultTab = 'advice'">个性化营养建议</button>
        <button class="final-tab" :class="{ active: finalResultTab === 'assessment' }" type="button" @click="finalResultTab = 'assessment'">综合评估结果</button>
      </nav>


      <section v-if="finalResultTab === 'assessment'" class="report-download-toolbar">
        <span class="report-download-title">评估报告</span>
        <div class="report-download-toolbar-actions">
          <button class="primary-button" type="button" :disabled="reportDownloading || !availableReportItems.length" @click="downloadAllReports">{{ reportDownloading ? '下载准备中...' : '↓ 一键下载全部量表' }}</button>
          <div class="report-menu-wrap">
            <button class="secondary-button report-menu-trigger" type="button" :disabled="!availableReportItems.length" :aria-expanded="reportMenuOpen" @click="reportMenuOpen = !reportMenuOpen">单独下载 {{ reportMenuOpen ? '⌃' : '⌄' }}</button>
            <div v-if="reportMenuOpen" class="report-download-menu">
              <button v-for="report in availableReportItems" :key="report.key" type="button" :disabled="reportDownloading" @click="downloadReport(report)"><span>{{ report.label }}</span><strong>下载</strong></button>
            </div>
          </div>
          <button class="secondary-button" type="button" :disabled="historySaving" @click="archiveCurrentHistory">{{ historySaving ? '保存中...' : '保存本次记录' }}</button>
        </div>
        <p v-if="!availableReportItems.length" class="report-empty">完成对应评估后可下载报告。</p>
        <p v-if="reportDownloadError" class="error-alert">{{ reportDownloadError }}</p>
        <p v-if="historyArchiveError" class="error-alert">{{ historyArchiveError }}</p>
        <p v-if="historyArchiveMessage" class="success-alert">{{ historyArchiveMessage }}</p>
      </section>

      <section v-if="finalResultTab === 'assessment'" class="final-result-selector" aria-label="选择要查看的综合结果">
        <label v-for="option in finalResultOptions.filter((item) => item.visible)" :key="option.key" class="final-result-check">
          <input v-model="finalResultSelection[option.key]" type="checkbox" />
          <span>{{ option.label }}</span>
        </label>
        <p>请勾选需要查看的评估结果</p>
      </section>

      <section v-if="finalResultTab === 'advice'" class="personalized-analysis" aria-live="polite">
        <div class="personalized-analysis-header">
          <div><h3>Qwen 个性化营养建议</h3><p>基于本次筛查风险提示生成，仅作辅助参考，不能判定营养状况。</p></div>
          <button class="primary-button" type="button" :disabled="personalizedLoading" @click="generatePersonalizedAnalysis">
            <span v-if="personalizedLoading" class="spinner" aria-hidden="true"></span>
            {{ personalizedLoading ? '生成中...' : personalizedAnalysis ? '重新生成' : '生成个性化建议' }}
          </button>
        </div>
        <p v-if="personalizedError" class="error-alert">{{ personalizedError }}</p>
        <div v-if="personalizedAnalysis" class="personalized-analysis-content">
          <section class="analysis-summary-card"><p class="analysis-eyebrow">本次筛查摘要</p><p class="analysis-summary">{{ personalizedAnalysis.summary }}</p></section>
          <div class="analysis-main-grid">
            <section v-if="personalizedAnalysis.key_findings?.length" class="analysis-block analysis-findings"><h4>重点发现</h4><ul><li v-for="item in personalizedAnalysis.key_findings" :key="item">{{ item }}</li></ul></section>
            <section v-if="personalizedAnalysis.suggestions?.length" class="analysis-block analysis-actions"><h4>建议行动</h4><ol><li v-for="item in personalizedAnalysis.suggestions" :key="item">{{ item }}</li></ol></section>
          </div>
          <section class="analysis-follow-up"><h4>随访建议</h4><ul v-if="Array.isArray(personalizedAnalysis.follow_up)"><li v-for="item in personalizedAnalysis.follow_up" :key="item">{{ item }}</li></ul><p v-else>{{ personalizedAnalysis.follow_up }}</p></section>
          <section v-if="personalizedAnalysis.urgent_signs?.length" class="analysis-urgent"><h4>需要尽快专业评估</h4><p>{{ personalizedAnalysis.urgent_signs.join('；') }}</p></section>
          <p class="analysis-disclaimer">{{ personalizedAnalysis.disclaimer }}</p>
        </div>
      </section>

      <div v-if="finalResultTab === 'assessment'" class="final-results-grid">
        <section v-if="nrs2002Result && finalResultSelection.nrs2002" class="assessment-result" :class="nrs2002Result.has_risk ? 'risk' : 'good'">
          <h3 class="final-result-title">NRS-2002 营养风险筛查</h3>
          <div class="score-hero"><span>总分</span><strong>{{ nrs2002Result.total_score }}</strong><em>{{ nrs2002Result.risk_level }}</em></div>
          <div class="result-metrics three"><div><span>营养状态受损</span><strong>{{ nrs2002Result.nutrition_score }}分</strong><p v-for="reason in nrsMetricReasons(nrs2002Result, 'nutrition')" :key="reason" class="metric-reason">{{ reason }}</p></div><div><span>疾病严重程度</span><strong>{{ nrs2002Result.disease_score }}分</strong><p v-for="reason in nrsMetricReasons(nrs2002Result, 'disease')" :key="reason" class="metric-reason">{{ reason }}</p></div><div><span>年龄</span><strong>{{ nrs2002Result.age_score }}分</strong><p v-for="reason in nrsMetricReasons(nrs2002Result, 'age')" :key="reason" class="metric-reason">{{ reason }}</p></div></div>
          <div class="result-metrics nrs-detail-metrics"><div><span>1个月内体重丢失</span><strong>{{ nrsLossText(nrs2002Result.weight_loss_details?.['1m_loss_pct']) }}</strong></div><div><span>2个月内体重丢失</span><strong>{{ nrsLossText(nrs2002Result.weight_loss_details?.['2m_loss_pct']) }}</strong></div><div><span>3个月内体重丢失</span><strong>{{ nrsLossText(nrs2002Result.weight_loss_details?.['3m_loss_pct']) }}</strong></div><div><span>BMI</span><strong>{{ nrsBmiText(nrs2002Result) }}</strong></div></div>
          <p class="message-text">{{ nrs2002Result.recommendation }}</p><p class="message-text">{{ nrs2002Result.message }}</p>
        </section>

        <section v-if="mnaSFResult && !skippedMnaSF && finalResultSelection.mnaSF" class="assessment-result" :class="mnaLevelClass(mnaSFResult.level)">
          <h3 class="final-result-title">MNA-SF 微型营养评估</h3>
          <div class="score-hero"><span>总分</span><strong>{{ mnaSFResult.total_score }}/14</strong><em>{{ mnaSFResult.level }}</em></div>
          <div class="progress-track"><span class="progress-fill success" :style="{ width: `${Math.min(100, mnaSFResult.total_score / 14 * 100)}%` }"></span></div>
          <div class="result-metrics three"><div v-for="(score, key) in mnaSFResult.score_breakdown" :key="key"><span>{{ mnaMetricLabel(key) }}</span><strong>{{ score }}分</strong><p v-if="mnaMetricReason(mnaSFResult, key)" class="metric-reason">{{ mnaMetricReason(mnaSFResult, key) }}</p></div></div>
          <p class="message-text">{{ mnaSFResult.message }}</p>
        </section>

        <div v-if="imageResult && finalResultSelection.image" class="image-result-stack">
          <ResultPanel v-if="!imageResult.sga_only" :result="imageResult" :show-actions="false" panel-title="面部图像筛查" />
          <SGAResultCard :evaluation="sgaEvaluation" />
          <ExplainabilityPanel v-if="!imageResult.sga_only" :result="explainResult" :loading="explainLoading" :error="explainError" />
        </div>

        <section v-if="glimResult && finalResultSelection.glim" class="assessment-result" :class="glimResult.is_malnourished ? 'risk' : 'good'">
          <h3 class="final-result-title">GLIM 营养不良评定</h3>
          <div class="score-hero"><strong>{{ glimResult.is_malnourished ? '营养不良' : '未诊断营养不良' }}</strong><em v-if="glimResult.severity" :class="glimResult.severity.includes('重度') ? 'severity-red' : 'severity-orange'">{{ glimResult.severity }}</em></div>
          <div class="result-metrics glim-result-metrics"><div><span>诊断依据</span><p v-for="reason in glimDiagnosisReasons(glimResult)" :key="reason" class="metric-reason">{{ reason }}</p></div></div>
          <div class="criteria-columns"><div><h3>表型标准</h3><span v-for="item in glimResult.phenotypic_criteria_triggered" :key="item" class="tag-pill">{{ item }}</span><p v-if="!glimResult.phenotypic_criteria_triggered.length">未触发</p></div><div><h3>病因标准</h3><div v-for="group in formatEtiologicalCriteria(glimResult.etiological_criteria_triggered)" :key="group.title" class="criteria-group"><h4>{{ group.title }}</h4><span v-for="option in group.options" :key="`${group.title}-${option}`" class="tag-pill">{{ option }}</span></div><p v-if="!glimResult.etiological_criteria_triggered.length">未触发</p></div></div>
          <div class="result-metrics detail-metrics"><div><span>6个月内体重丢失</span><strong>{{ glimLossText(glimResult.weight_loss_6m_pct) }}</strong></div><div><span>6个月以上体重丢失</span><strong>{{ glimLossText(glimResult.weight_loss_over6m_pct) }}</strong></div><div><span>BMI</span><strong>{{ glimBmiText(glimResult) }}</strong></div></div>
        </section>
      </div>
      <div class="step-actions split-actions">
        <button class="secondary-button" type="button" @click="goPrevious">上一步</button>
        <span class="action-spacer"></span>
        <button class="secondary-button" type="button" @click="resetAll">重新开始</button>
      </div>
    </section>
  </main>
  <HistoryPanel :open="historyOpen" @close="historyOpen = false" />
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


.image-step-workspace {
  margin-top: 0;
}

/* 紧凑下载工具栏：常用的批量下载常驻，单份下载按需展开。 */
.report-download-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 14px;
  min-height: 48px;
  padding: 8px 12px;
  border: 1px solid #dceaf2;
  border-radius: 9px;
  background: #fff;
}

.report-download-title { color: #10253f; font-size: 14px; font-weight: 900; }
.report-download-toolbar-actions { display: flex; align-items: center; gap: 8px; margin-left: auto; }
.report-download-toolbar .secondary-button { margin-top: 0; }
.report-menu-wrap { position: relative; }
.report-menu-trigger { min-width: 104px; }
.report-download-menu {
  position: absolute;
  z-index: 5;
  top: calc(100% + 8px);
  right: 0;
  display: grid;
  min-width: 220px;
  padding: 6px;
  border: 1px solid #cfe1eb;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 8px 22px rgba(20, 48, 70, 0.16);
}

.report-download-menu button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 9px 10px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: #263746;
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.report-download-menu button:hover { background: #eefaff; }
.report-download-menu strong { color: #1689a7; }
.report-download-toolbar .report-empty, .report-download-toolbar .error-alert { flex-basis: 100%; margin: 0; }

/* 最终页一级标签：评估结果与建议一次只展示一个工作区。 */
.final-tab-nav {
  display: flex;
  gap: 8px;
  padding: 6px;
  border: 1px solid #dceaf2;
  border-radius: 10px;
  background: #f7fbfd;
}

.final-tab {
  flex: 1 1 0;
  min-height: 40px;
  padding: 8px 14px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: #607181;
  font: inherit;
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
}

.final-tab.active {
  background: #1689a7;
  color: #fff;
  box-shadow: 0 2px 6px rgba(22, 137, 167, 0.2);
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

.final-result-title {
  margin: 0 0 14px;
  color: #10253f;
  font-size: 16px;
  font-weight: 900;
}

/* 综合结果卡片统一作为网格项展示，避免 ResultPanel 的全局上边距造成错位。 */
.final-results-grid > .assessment-result,
.final-results-grid > .result-panel,
.final-results-grid > .image-result-stack {
  height: 100%;
  margin-top: 0;
}

.image-result-stack {
  display: grid;
  gap: 18px;
}

.image-result-stack > .result-panel {
  margin-top: 0;
}

/* 大模型建议独立展示，避免和各量表卡片混排造成阅读负担。 */
.personalized-analysis {
  padding: 24px;
  border: 1px solid #d8e7ee;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(16, 37, 63, 0.05);
}

.personalized-analysis-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 18px;
  border-bottom: 1px solid #e6eef2;
}

.personalized-analysis h3, .personalized-analysis h4 { margin: 0; color: #10253f; }
.personalized-analysis-header p, .analysis-disclaimer { margin: 6px 0 0; color: #607181; font-size: 13px; }
.personalized-analysis-content { display: grid; gap: 16px; margin-top: 18px; color: #263746; font-size: 15px; line-height: 1.75; }
.personalized-analysis-content p { margin: 0; }
.analysis-summary-card { padding: 16px 18px; border-left: 4px solid #1689a7; border-radius: 8px; background: #eff9fc; }
.analysis-eyebrow { margin: 0 0 5px !important; color: #147a92; font-size: 13px; font-weight: 800; letter-spacing: .04em; }
.analysis-summary { font-size: 16px; font-weight: 500; }
.analysis-main-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.analysis-block, .analysis-follow-up { padding: 16px 18px; border: 1px solid #e0ebf1; border-radius: 10px; background: #fff; }
.analysis-block h4, .analysis-follow-up h4, .analysis-urgent h4 { font-size: 15px; font-weight: 800; }
.analysis-block ul, .analysis-block ol, .analysis-info-gap ul { margin: 10px 0 0; padding-left: 22px; }
.analysis-block li, .analysis-info-gap li { margin-top: 8px; }
.analysis-actions { border-color: #c7e4ec; background: #f7fcfd; }
.analysis-actions li::marker { color: #147a92; font-weight: 800; }
.analysis-follow-up { display: grid; gap: 6px; background: #f3f9fc; }.analysis-follow-up ul { margin: 4px 0 0; padding-left: 22px; }.analysis-follow-up li { margin-top: 7px; }
.analysis-info-gap { padding: 12px 14px; border-radius: 8px; background: #f5f9fc; color: #52606d; }
.analysis-info-gap summary { cursor: pointer; color: #35546a; font-weight: 700; }
.analysis-urgent { padding: 14px 16px; border-left: 4px solid #c75b42; border-radius: 8px; background: #fff5f0; color: #a9432c; }
.analysis-urgent p { margin-top: 6px; font-weight: 600; }
.analysis-disclaimer { padding-top: 2px; }

@media (max-width: 900px) {
  .linear-stepper,
  .final-results-grid,
  .analysis-main-grid {
    grid-template-columns: 1fr;
  }

  .personalized-analysis {
    padding: 18px;
  }

  .personalized-analysis-header {
    align-items: flex-start;
    flex-direction: column;
  }




  .report-download-toolbar-actions {
    width: 100%;
    margin-left: 0;
    justify-content: flex-start;
  }


  .final-tab-nav {
    gap: 4px;
  }

  .final-tab {
    padding-inline: 8px;
    font-size: 13px;
  }


  .action-spacer {
    display: none;
  }
}
</style>
@media (max-width: 640px) {
  .linear-stepper {
    grid-template-columns: repeat(5, minmax(128px, 1fr));
    gap: 8px;
    overflow-x: auto;
    padding-bottom: 4px;
  }

  .linear-step {
    min-height: 50px;
    padding: 8px;
  }

  .step-label {
    font-size: 12px;
  }

  .linear-step em {
    display: none;
  }

  .final-tab-nav {
    display: grid;
    grid-template-columns: 1fr;
  }

  .final-tab {
    min-height: 46px;
    font-size: 14px;
  }

  .report-download-toolbar,
  .personalized-analysis {
    padding: 14px;
  }

  .report-download-toolbar-actions {
    display: grid;
    grid-template-columns: 1fr;
  }

  .report-download-toolbar-actions > button {
    width: 100%;
  }

  .report-menu-wrap,
  .report-menu-trigger {
    width: 100%;
  }

  .report-download-menu {
    right: auto;
    left: 0;
    width: 100%;
    min-width: 0;
  }
}
