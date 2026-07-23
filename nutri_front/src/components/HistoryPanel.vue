<script setup>
import { computed, ref, watch } from 'vue'
import { API_BASE, apiUrl } from '../config'
import DatePicker from './DatePicker.vue'

const props = defineProps({ open: Boolean })
const emit = defineEmits(['close'])
const items = ref([])
const detail = ref(null)
const error = ref('')
const loading = ref(false)
const nameQuery = ref('')
const dateQuery = ref('')
const currentPage = ref(1)
const pageSize = 10
const selectedIds = ref([])
const deleting = ref(false)

const reportTypes = [
  ['nrs2002_result', 'NRS-2002 营养风险筛查'],
  ['mnasf_result', 'MNA-SF 微型营养评估'],
  ['image_result', '面部图像筛查'],
  ['glim_result', 'GLIM 营养不良评定'],
]
const reports = computed(() => reportTypes.map(([key, label]) => ({ key, label, result: detail.value?.snapshot?.[key] })).filter((item) => item.result))
const historyImages = computed(() => ['front', 'left', 'right'].filter((view) => detail.value?.snapshot?.images?.[view]?.history_image))
const filteredItems = computed(() => {
  const name = nameQuery.value.trim().toLocaleLowerCase()
  return items.value.filter((item) => {
    const matchesName = !name || String(item.patient_name || '').toLocaleLowerCase().includes(name)
    const matchesDate = !dateQuery.value || String(item.created_at || '').startsWith(dateQuery.value)
    return matchesName && matchesDate
  })
})
const pageCount = computed(() => Math.max(1, Math.ceil(filteredItems.value.length / pageSize)))
const paginatedItems = computed(() => {
  const page = Math.min(currentPage.value, pageCount.value)
  return filteredItems.value.slice((page - 1) * pageSize, page * pageSize)
})
const pageStart = computed(() => filteredItems.value.length ? (Math.min(currentPage.value, pageCount.value) - 1) * pageSize + 1 : 0)
const pageEnd = computed(() => Math.min(pageStart.value + pageSize - 1, filteredItems.value.length))
const pageItemsSelected = computed(() => paginatedItems.value.length > 0 && paginatedItems.value.every((item) => selectedIds.value.includes(item.id)))

async function load() {
  loading.value = true; error.value = ''
  try {
    const response = await fetch(`${API_BASE}/history`)
    const data = await response.json().catch(() => [])
    if (!response.ok) throw new Error(data.detail || '历史记录加载失败。')
    items.value = data
    selectedIds.value = selectedIds.value.filter((id) => data.some((item) => item.id === id))
    currentPage.value = 1
  } catch (err) { error.value = err.message || '历史记录加载失败。' }
  finally { loading.value = false }
}
watch(() => props.open, (open) => { if (open) { detail.value = null; load() } }, { immediate: true })
watch([nameQuery, dateQuery], () => { currentPage.value = 1 })

function clearSearch() { nameQuery.value = ''; dateQuery.value = '' }
function goToPage(page) { currentPage.value = Math.min(Math.max(page, 1), pageCount.value) }

function toggleItemSelection(id, checked) {
  selectedIds.value = checked ? [...new Set([...selectedIds.value, id])] : selectedIds.value.filter((value) => value !== id)
}
function togglePageSelection(checked) {
  const pageIds = paginatedItems.value.map((item) => item.id)
  selectedIds.value = checked ? [...new Set([...selectedIds.value, ...pageIds])] : selectedIds.value.filter((id) => !pageIds.includes(id))
}

async function view(id) {
  try {
    const response = await fetch(`${API_BASE}/history/${id}`)
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || '历史记录读取失败。')
    detail.value = data
  } catch (err) { error.value = err.message || '历史记录读取失败。' }
}
async function remove(id) {
  if (!window.confirm('确定删除此历史记录及其报告、图片吗？')) return
  const response = await fetch(`${API_BASE}/history/${id}`, { method: 'DELETE' })
  if (!response.ok) { error.value = '删除历史记录失败。'; return }
  detail.value = null; await load()
}
async function removeSelected() {
  if (!selectedIds.value.length || deleting.value) return
  if (!window.confirm(`确定删除已选的 ${selectedIds.value.length} 条历史记录及其报告、图片吗？`)) return
  deleting.value = true
  error.value = ""
  const failedIds = []
  for (const id of selectedIds.value) {
    try {
      const response = await fetch(`${API_BASE}/history/${id}`, { method: "DELETE" })
      if (!response.ok) failedIds.push(id)
    } catch { failedIds.push(id) }
  }
  selectedIds.value = failedIds
  if (failedIds.length) error.value = `${failedIds.length} 条历史记录删除失败，请重试。`
  await load()
  deleting.value = false
}

async function downloadReport(filename) {
  try {
    const response = await fetch(`${API_BASE}/history/${detail.value.id}/reports/${encodeURIComponent(filename)}`)
    if (!response.ok) throw new Error('历史报告下载失败。')
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    error.value = err.message || '历史报告下载失败。'
  }
}
async function downloadAllReports() {
  try {
    const response = await fetch(`${API_BASE}/history/${detail.value.id}/reports.zip?download_at=${Date.now()}`, { cache: "no-store" })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || `历史报告打包下载失败（HTTP ${response.status}）。`)
    }
    const disposition = response.headers.get("content-disposition") || ""
    const filenameMatch = disposition.match(/filename\*=UTF-8\x27\x27([^;]+)|filename="?([^";]+)"?/i)
    const filename = decodeURIComponent(filenameMatch?.[1] || filenameMatch?.[2] || "全部量表.zip")
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement("a")
    link.href = url
    link.download = filename
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (err) {
    error.value = err.message || '历史报告打包下载失败。'
  }
}
function resultText(key, result) {
  if (key === 'nrs2002_result') return `总分 ${result.total_score} 分（${result.total_score}/7）· ${result.risk_level}`
  if (key === 'mnasf_result') return `总分 ${result.total_score} 分（${result.total_score}/14）· ${result.level}`
  if (key === 'image_result') {
    const score = Math.round(Number(result.sga_normalized_score || 0))
    const prediction = result.prediction === 'malnourished' ? '营养不良风险' : '营养状态正常'
    return `归一化分值 ${score} 分（${score}/7）· ${prediction}`
  }
  return `${result.is_malnourished ? '营养不良' : '未诊断营养不良'}${result.severity ? ` · ${result.severity}` : ''}`
}
</script>

<template>
  <div v-if="open" class="history-page">
    <section class="history-content">
      <header class="history-header"><div><p>History archive</p><h2>历史记录</h2></div><button class="secondary-button" type="button" @click="emit('close')">返回筛查</button></header>
      <p v-if="error" class="error-alert">{{ error }}</p>
      <template v-if="!detail">
        <p v-if="loading" class="muted">加载中...</p>
        <div v-if="!loading" class="history-search"><label>姓名<input v-model="nameQuery" type="search" placeholder="输入患者姓名"></label><label>日期<DatePicker v-model="dateQuery" /></label><button v-if="nameQuery || dateQuery" class="history-clear" type="button" @click="clearSearch" aria-label="清除筛选">×</button></div>
        <div v-if="!loading && filteredItems.length" class="history-batch-actions"><label><input type="checkbox" :checked="pageItemsSelected" @change="togglePageSelection($event.target.checked)"><span>全选当前页</span></label><span v-if="selectedIds.length" class="history-selection-count">已选 {{ selectedIds.length }} 条</span><button class="danger-button" type="button" :disabled="!selectedIds.length || deleting" @click="removeSelected">{{ deleting ? "删除中..." : "删除已选" }}</button></div>
        <div v-for="item in paginatedItems" :key="item.id" class="history-list-row" :class="{ selected: selectedIds.includes(item.id) }"><label class="history-select"><input type="checkbox" :checked="selectedIds.includes(item.id)" :aria-label="`选择 ${item.patient_name} 的历史记录`" @change="toggleItemSelection(item.id, $event.target.checked)"></label><button class="history-item" type="button" @click="view(item.id)"><span>{{ item.created_at }}_{{ item.patient_name }}</span><strong>查看 →</strong></button></div>
        <p v-if="!loading && !items.length" class="muted">暂无已保存的历史记录。</p>
        <p v-else-if="!loading && !filteredItems.length" class="muted">未找到符合条件的历史记录。</p>
        <nav v-if="!loading && filteredItems.length" class="history-pagination" aria-label="历史记录分页"><button type="button" :disabled="currentPage === 1" @click="goToPage(currentPage - 1)">← 上一页</button><span>第 <b>{{ currentPage }}</b> / {{ pageCount }} 页</span><button type="button" :disabled="currentPage === pageCount" @click="goToPage(currentPage + 1)">下一页 →</button></nav>
      </template>
      <template v-else>
        <div class="history-actions"><button class="secondary-button" type="button" @click="detail = null">← 返回列表</button><button class="danger-button" type="button" @click="remove(detail.id)">删除此记录</button></div>
        <h3 class="record-title">{{ detail.created_at }}_{{ detail.patient_name }}</h3>
        <section class="patient-card"><h4>患者信息</h4><span>姓名：{{ detail.snapshot.patient_info?.name || '未填写' }}</span><span>性别：{{ detail.snapshot.patient_info?.gender === 'female' ? '女' : '男' }}</span><span>年龄：{{ detail.snapshot.patient_info?.age || '未填写' }} 岁</span><span>身高：{{ detail.snapshot.patient_info?.height || '未填写' }} cm</span></section>
        <section v-if="historyImages.length" class="history-section"><h4>面部图像</h4><div class="image-grid"><figure v-for="viewName in historyImages" :key="viewName"><img :src="apiUrl(`${API_BASE}/history/${detail.id}/images/${viewName}`)" :alt="`${viewName} 面部图像`"><figcaption>{{ { front: '正面', left: '左45°', right: '右45°' }[viewName] }}</figcaption></figure></div></section>
        <section class="history-section"><div class="report-section-header"><h4>评估结果与 DOCX 报告</h4><button v-if="reports.some((item) => item.result.history_report)" class="secondary-button" type="button" @click="downloadAllReports">↓ 一键下载全部量表</button></div><article v-for="item in reports" :key="item.key" class="result-card"><h5>{{ item.label }}</h5><p>{{ resultText(item.key, item.result) }}</p><button v-if="item.result.history_report" class="secondary-button" type="button" @click="downloadReport(item.result.history_report)">↓ 下载 DOCX 报告</button></article></section>
        <section class="history-section history-advice"><h4>个性化营养建议</h4><template v-if="detail.personalized_analysis"><section class="history-advice-summary"><p class="history-advice-eyebrow">本次筛查摘要</p><p>{{ detail.personalized_analysis.summary }}</p></section><div class="history-advice-grid"><section v-if="detail.personalized_analysis.key_findings?.length" class="history-advice-block"><h5>重点发现</h5><ul><li v-for="item in detail.personalized_analysis.key_findings" :key="item">{{ item }}</li></ul></section><section v-if="detail.personalized_analysis.suggestions?.length" class="history-advice-block history-advice-actions"><h5>建议行动</h5><ol><li v-for="item in detail.personalized_analysis.suggestions" :key="item">{{ item }}</li></ol></section></div><section v-if="detail.personalized_analysis.follow_up" class="history-follow-up"><h5>随访建议</h5><ul v-if="Array.isArray(detail.personalized_analysis.follow_up)"><li v-for="item in detail.personalized_analysis.follow_up" :key="item">{{ item }}</li></ul><p v-else>{{ detail.personalized_analysis.follow_up }}</p></section><section v-if="detail.personalized_analysis.urgent_signs?.length" class="history-advice-urgent"><h5>需要尽快专业评估</h5><p>{{ detail.personalized_analysis.urgent_signs.join('；') }}</p></section><p v-if="detail.personalized_analysis.disclaimer" class="history-advice-disclaimer">{{ detail.personalized_analysis.disclaimer }}</p></template><p v-else class="muted">本次归档时尚未生成个性化营养建议。</p></section>
      </template>
    </section>
  </div>
</template>

<style scoped>
.history-page{position:fixed;inset:0;z-index:20;overflow:auto;background:#f5f9fc}.history-content{width:min(1000px,calc(100% - 32px));margin:0 auto;padding:40px 0 64px}.history-header,.history-actions{display:flex;align-items:center;justify-content:space-between;gap:16px}.history-header{margin-bottom:24px}.history-header p{margin:0 0 6px;color:#147a92;font-size:13px;font-weight:800;text-transform:uppercase}.history-header h2,.record-title{margin:0;color:#10253f}.history-search{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,.8fr) auto;align-items:end;gap:10px;margin-bottom:16px;padding:12px 14px;border:1px solid #dceaf2;border-radius:10px;background:#fff}.history-search label{display:grid;gap:5px;color:#35546a;font-size:13px;font-weight:800}.history-search input{width:100%;height:38px;padding:0 10px;border:1px solid #bfd5e0;border-radius:7px;background:#fff;color:#263746;font:inherit}.history-clear{width:30px;height:30px;margin-bottom:4px;border:0;border-radius:50%;background:#eef5f8;color:#527080;font-size:20px;line-height:1}.history-clear:hover{background:#dcecf2;color:#147a92}.history-item{display:flex;width:100%;align-items:center;justify-content:space-between;margin:10px 0;padding:16px;border:1px solid #dceaf2;border-radius:8px;background:#fff;color:#263746;font:inherit;font-weight:800;text-align:left}.history-item:hover{border-color:#1689a7;background:#eefaff}.history-item strong{color:#147a92}.history-pagination{display:flex;align-items:center;justify-content:center;gap:12px;margin-top:20px;color:#52606d;font-size:14px}.history-pagination button{min-width:86px;height:34px;padding:0 10px;border:1px solid #c8dbe6;border-radius:7px;background:#fff;color:#147a92;font:inherit;font-weight:700}.history-pagination button:hover:not(:disabled){border-color:#1689a7;background:#eefaff}.history-pagination button:disabled{cursor:not-allowed;opacity:.45}.history-pagination b{color:#147a92}.history-actions{display:flex!important;align-items:center!important;justify-content:flex-start;gap:16px;margin-bottom:18px}.history-actions>button{align-self:center!important;margin:0!important;display:inline-flex!important;align-items:center!important;justify-content:center!important;box-sizing:border-box;min-height:42px!important;height:42px!important}.danger-button{min-height:40px;padding:0 14px;border:1px solid #e9b7aa;border-radius:8px;background:#fff5f0;color:#a6451f;font-weight:800}.patient-card,.history-section{margin-top:18px;padding:18px;border:1px solid #dceaf2;border-radius:9px;background:#fff}.patient-card{display:flex;flex-wrap:wrap;gap:12px 26px}.patient-card span{font-size:15px;font-weight:600;color:#334b5d}.patient-card h4{font-size:16px}.patient-card h4,.history-section h4{width:100%;margin:0;color:#10253f}.report-section-header{display:flex;align-items:center;justify-content:space-between;gap:16px}.report-section-header h4{width:auto}.report-section-header .secondary-button{min-height:38px;white-space:nowrap}.image-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:14px}.image-grid figure{margin:0}.image-grid img{display:block;width:100%;aspect-ratio:1;object-fit:cover;border-radius:8px;background:#edf3f7}.image-grid figcaption{margin-top:6px;color:#607181;font-size:13px;font-weight:800}.result-card{margin-top:12px;padding:14px;border:1px solid #e0edf4;border-radius:8px;background:#f8fbfd}.result-card h5,.result-card p{margin:0 0 8px}.result-card h5{color:#10253f;font-size:15px}.result-card p{color:#52606d;line-height:1.55}.result-card .secondary-button{min-height:38px;margin-top:4px}.history-advice{display:grid;gap:14px}.history-advice > h4{margin-bottom:0}.history-advice-summary{padding:15px 17px;border-left:4px solid #1689a7;border-radius:8px;background:#eff9fc;color:#263746;font-size:15px;line-height:1.7}.history-advice-summary p{margin:0}.history-advice-eyebrow{margin-bottom:5px!important;color:#147a92;font-size:13px;font-weight:800;letter-spacing:.04em}.history-advice-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.history-advice-block,.history-follow-up{padding:15px 17px;border:1px solid #e0ebf1;border-radius:9px;background:#fff;color:#334b5d;font-size:15px;line-height:1.7}.history-advice-block h5,.history-follow-up h5,.history-advice-urgent h5{margin:0;color:#10253f;font-size:15px}.history-advice-block ul,.history-advice-block ol,.history-follow-up ul,.history-advice-gap ul{margin:9px 0 0;padding-left:22px}.history-advice-block li,.history-follow-up li,.history-advice-gap li{margin-top:7px}.history-advice-actions{border-color:#c7e4ec;background:#f7fcfd}.history-advice-actions li::marker{color:#147a92;font-weight:800}.history-follow-up{background:#f3f9fc}.history-follow-up p{margin:7px 0 0}.history-advice-gap{padding:12px 14px;border-radius:8px;background:#f5f9fc;color:#52606d;font-size:14px;line-height:1.65}.history-advice-gap summary{cursor:pointer;font-weight:700;color:#35546a}.history-advice-urgent{padding:14px 16px;border-left:4px solid #c75b42;border-radius:8px;background:#fff5f0;color:#a9432c;font-size:15px;line-height:1.65}.history-advice-urgent p{margin:6px 0 0;font-weight:13px;line-height:1.65}.history-advice-urgent p{margin:6px 0 0;font-weight:600}.history-advice-disclaimer{margin:0;color:#607181;font-size:13px;line-height:1.6}.muted{color:#607181}@media(max-width:680px){.image-grid,.history-advice-grid{grid-template-columns:1fr}.history-search{grid-template-columns:minmax(0,1fr) minmax(0,.8fr) auto;padding:10px}.history-pagination{gap:8px}.history-pagination button{min-width:76px}.history-actions{gap:10px;flex-wrap:wrap}.history-content{width:min(100% - 20px,1000px);padding-top:24px}.history-header{align-items:flex-start}}
.history-batch-actions{display:flex;align-items:center;gap:12px;margin:0 0 12px;color:#52606d;font-size:14px}.history-batch-actions label{display:inline-flex;align-items:center;gap:5px;font-weight:700}.history-batch-actions .danger-button{min-height:34px;margin-left:auto}.history-batch-actions .danger-button:disabled{cursor:not-allowed;opacity:.45}.history-list-row{display:flex;align-items:center;gap:10px}.history-list-row .history-item{flex:1}.history-select{display:grid;width:20px;height:20px;place-items:center}.history-select input{width:16px;height:16px;accent-color:#147a92}.sr-only{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}@media(max-width:680px){.history-batch-actions{flex-wrap:wrap}.history-batch-actions .danger-button{margin-left:auto}}
.history-batch-actions{min-height:46px;margin-bottom:14px;padding:7px 9px 7px 13px;border:1px solid #d5e5ec;border-radius:10px;background:#fff;box-shadow:0 2px 8px rgba(24,72,94,.04)}.history-batch-actions label{height:32px;padding:0 9px;border-radius:7px;background:#f1f8fb;color:#2b596d}.history-batch-actions label:hover{background:#e4f3f8}.history-batch-actions label input{width:16px;height:16px;margin:0;accent-color:#147a92}.history-batch-actions .history-selection-count{padding:0 2px;color:#147a92;font-weight:800}.history-batch-actions .danger-button{height:32px;min-height:32px;margin-left:auto;padding:0 12px;border-color:#edc8bf;border-radius:7px;font-size:13px}.history-list-row{margin:10px 0;padding:3px 10px 3px 4px;border:1px solid transparent;border-radius:9px;background:#fff;transition:.18s}.history-list-row:hover{border-color:#b9dce9}.history-list-row.selected{border-color:#83c7d8;background:#f0fbfd}.history-list-row .history-item{margin:0;border:0;background:transparent}.history-list-row .history-item:hover{border:0;background:transparent}.history-select{position:relative;flex:0 0 16px;width:16px;height:16px;border:1px solid #9bb7c4;border-radius:4px;background:#fff;cursor:pointer}.history-select input{position:absolute;width:1px;height:1px;opacity:0}.history-select span{display:grid;width:100%;height:100%;place-items:center;border-radius:3px;color:transparent;font-size:11px;font-weight:900}.history-select input:checked+span{background:#147a92;color:#fff}.history-select input:focus-visible+span{outline:2px solid #78bdcf;outline-offset:2px}.sr-only{display:none}
.history-list-row{display:grid;grid-template-columns:16px minmax(0,1fr);align-items:center;gap:12px;margin:10px 0;padding:0;border:1px solid #dceaf2;border-radius:9px;background:#fff;overflow:hidden;transition:.18s}.history-list-row:hover{border-color:#b9dce9}.history-list-row.selected{border-color:#83c7d8;background:#f0fbfd}.history-list-row .history-item{width:100%;min-height:62px;margin:0!important;padding:16px;border:0!important;border-radius:0;background:transparent}.history-select{display:flex;position:static;align-items:center;justify-content:center;width:16px;height:16px;margin-left:14px;border:0;background:transparent;cursor:pointer}.history-select input{position:static;width:16px;height:16px;margin:0;opacity:1;accent-color:#147a92}.history-select span{display:none}
</style>
