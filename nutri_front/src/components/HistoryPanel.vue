<script setup>
import { computed, ref, watch } from 'vue'
import { API_BASE } from '../config'

const props = defineProps({ open: Boolean })
const emit = defineEmits(['close'])
const items = ref([])
const detail = ref(null)
const error = ref('')
const loading = ref(false)

const reportTypes = [
  ['nrs2002_result', 'NRS-2002 营养风险筛查'],
  ['mnasf_result', 'MNA-SF 微型营养评估'],
  ['image_result', '面部图像筛查'],
  ['glim_result', 'GLIM 营养不良评定'],
]
const reports = computed(() => reportTypes.map(([key, label]) => ({ key, label, result: detail.value?.snapshot?.[key] })).filter((item) => item.result))
const historyImages = computed(() => ['front', 'left', 'right'].filter((view) => detail.value?.snapshot?.images?.[view]?.history_image))

async function load() {
  loading.value = true; error.value = ''
  try {
    const response = await fetch(`${API_BASE}/history`)
    const data = await response.json().catch(() => [])
    if (!response.ok) throw new Error(data.detail || '历史记录加载失败。')
    items.value = data
  } catch (err) { error.value = err.message || '历史记录加载失败。' }
  finally { loading.value = false }
}
watch(() => props.open, (open) => { if (open) { detail.value = null; load() } }, { immediate: true })

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
function downloadReport(filename) { window.open(`${API_BASE}/history/${detail.value.id}/reports/${encodeURIComponent(filename)}`, '_blank', 'noopener') }
function downloadAllReports() {
  reports.value.filter((item) => item.result.history_report).forEach((item) => downloadReport(item.result.history_report))
}
function resultText(key, result) {
  if (key === 'nrs2002_result') return `总分 ${result.total_score} 分（${result.total_score}/7）· ${result.risk_level}`
  if (key === 'mnasf_result') return `总分 ${result.total_score} 分（${result.total_score}/14）· ${result.level}`
  if (key === 'image_result') {
    const score = Number(result.sga_normalized_score || 0).toFixed(2)
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
        <button v-for="item in items" :key="item.id" class="history-item" type="button" @click="view(item.id)"><span>{{ item.created_at }}_{{ item.patient_name }}</span><strong>查看 →</strong></button>
        <p v-if="!loading && !items.length" class="muted">暂无已保存的历史记录。</p>
      </template>
      <template v-else>
        <div class="history-actions"><button class="secondary-button" type="button" @click="detail = null">← 返回列表</button><button class="danger-button" type="button" @click="remove(detail.id)">删除此记录</button></div>
        <h3 class="record-title">{{ detail.created_at }}_{{ detail.patient_name }}</h3>
        <section class="patient-card"><h4>患者信息</h4><span>姓名：{{ detail.snapshot.patient_info?.name || '未填写' }}</span><span>性别：{{ detail.snapshot.patient_info?.gender === 'female' ? '女' : '男' }}</span><span>年龄：{{ detail.snapshot.patient_info?.age || '未填写' }} 岁</span><span>身高：{{ detail.snapshot.patient_info?.height || '未填写' }} cm</span></section>
        <section v-if="historyImages.length" class="history-section"><h4>面部图像</h4><div class="image-grid"><figure v-for="viewName in historyImages" :key="viewName"><img :src="`${API_BASE}/history/${detail.id}/images/${viewName}`" :alt="`${viewName} 面部图像`"><figcaption>{{ { front: '正面', left: '左45°', right: '右45°' }[viewName] }}</figcaption></figure></div></section>
        <section class="history-section"><div class="report-section-header"><h4>评估结果与 DOCX 报告</h4><button v-if="reports.some((item) => item.result.history_report)" class="secondary-button" type="button" @click="downloadAllReports">↓ 一键下载全部量表</button></div><article v-for="item in reports" :key="item.key" class="result-card"><h5>{{ item.label }}</h5><p>{{ resultText(item.key, item.result) }}</p><button v-if="item.result.history_report" class="secondary-button" type="button" @click="downloadReport(item.result.history_report)">↓ 下载 DOCX 报告</button></article></section>
        <section class="history-section history-advice"><h4>个性化营养建议</h4><template v-if="detail.personalized_analysis"><section class="history-advice-summary"><p class="history-advice-eyebrow">本次筛查摘要</p><p>{{ detail.personalized_analysis.summary }}</p></section><div class="history-advice-grid"><section v-if="detail.personalized_analysis.key_findings?.length" class="history-advice-block"><h5>重点发现</h5><ul><li v-for="item in detail.personalized_analysis.key_findings" :key="item">{{ item }}</li></ul></section><section v-if="detail.personalized_analysis.suggestions?.length" class="history-advice-block history-advice-actions"><h5>建议行动</h5><ol><li v-for="item in detail.personalized_analysis.suggestions" :key="item">{{ item }}</li></ol></section></div><section v-if="detail.personalized_analysis.follow_up" class="history-follow-up"><h5>随访建议</h5><ul v-if="Array.isArray(detail.personalized_analysis.follow_up)"><li v-for="item in detail.personalized_analysis.follow_up" :key="item">{{ item }}</li></ul><p v-else>{{ detail.personalized_analysis.follow_up }}</p></section><details v-if="detail.personalized_analysis.missing_information?.length" class="history-advice-gap"><summary>为进一步个性化，建议补充信息</summary><ul><li v-for="item in detail.personalized_analysis.missing_information" :key="item">{{ item }}</li></ul></details><section v-if="detail.personalized_analysis.urgent_signs?.length" class="history-advice-urgent"><h5>需要尽快专业评估</h5><p>{{ detail.personalized_analysis.urgent_signs.join('；') }}</p></section><p v-if="detail.personalized_analysis.disclaimer" class="history-advice-disclaimer">{{ detail.personalized_analysis.disclaimer }}</p></template><p v-else class="muted">本次归档时尚未生成个性化营养建议。</p></section>
      </template>
    </section>
  </div>
</template>

<style scoped>
.history-page{position:fixed;inset:0;z-index:20;overflow:auto;background:#f5f9fc}.history-content{width:min(1000px,calc(100% - 32px));margin:0 auto;padding:40px 0 64px}.history-header,.history-actions{display:flex;align-items:center;justify-content:space-between;gap:16px}.history-header{margin-bottom:24px}.history-header p{margin:0 0 6px;color:#147a92;font-size:13px;font-weight:800;text-transform:uppercase}.history-header h2,.record-title{margin:0;color:#10253f}.history-item{display:flex;width:100%;align-items:center;justify-content:space-between;margin:10px 0;padding:16px;border:1px solid #dceaf2;border-radius:8px;background:#fff;color:#263746;font:inherit;font-weight:800;text-align:left}.history-item:hover{border-color:#1689a7;background:#eefaff}.history-item strong{color:#147a92}.history-actions{display:flex!important;align-items:center!important;justify-content:flex-start;gap:16px;margin-bottom:18px}.history-actions>button{align-self:center!important;margin:0!important;display:inline-flex!important;align-items:center!important;justify-content:center!important;box-sizing:border-box;min-height:42px!important;height:42px!important}.danger-button{min-height:40px;padding:0 14px;border:1px solid #e9b7aa;border-radius:8px;background:#fff5f0;color:#a6451f;font-weight:800}.patient-card,.history-section{margin-top:18px;padding:18px;border:1px solid #dceaf2;border-radius:9px;background:#fff}.patient-card{display:flex;flex-wrap:wrap;gap:12px 26px}.patient-card span{font-size:15px;font-weight:600;color:#334b5d}.patient-card h4{font-size:16px}.patient-card h4,.history-section h4{width:100%;margin:0;color:#10253f}.report-section-header{display:flex;align-items:center;justify-content:space-between;gap:16px}.report-section-header h4{width:auto}.report-section-header .secondary-button{min-height:38px;white-space:nowrap}.image-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:14px}.image-grid figure{margin:0}.image-grid img{display:block;width:100%;aspect-ratio:1;object-fit:cover;border-radius:8px;background:#edf3f7}.image-grid figcaption{margin-top:6px;color:#607181;font-size:13px;font-weight:800}.result-card{margin-top:12px;padding:14px;border:1px solid #e0edf4;border-radius:8px;background:#f8fbfd}.result-card h5,.result-card p{margin:0 0 8px}.result-card h5{color:#10253f;font-size:15px}.result-card p{color:#52606d;line-height:1.55}.result-card .secondary-button{min-height:38px;margin-top:4px}.history-advice{display:grid;gap:14px}.history-advice > h4{margin-bottom:0}.history-advice-summary{padding:15px 17px;border-left:4px solid #1689a7;border-radius:8px;background:#eff9fc;color:#263746;font-size:15px;line-height:1.7}.history-advice-summary p{margin:0}.history-advice-eyebrow{margin-bottom:5px!important;color:#147a92;font-size:13px;font-weight:800;letter-spacing:.04em}.history-advice-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.history-advice-block,.history-follow-up{padding:15px 17px;border:1px solid #e0ebf1;border-radius:9px;background:#fff;color:#334b5d;font-size:15px;line-height:1.7}.history-advice-block h5,.history-follow-up h5,.history-advice-urgent h5{margin:0;color:#10253f;font-size:15px}.history-advice-block ul,.history-advice-block ol,.history-follow-up ul,.history-advice-gap ul{margin:9px 0 0;padding-left:22px}.history-advice-block li,.history-follow-up li,.history-advice-gap li{margin-top:7px}.history-advice-actions{border-color:#c7e4ec;background:#f7fcfd}.history-advice-actions li::marker{color:#147a92;font-weight:800}.history-follow-up{background:#f3f9fc}.history-follow-up p{margin:7px 0 0}.history-advice-gap{padding:12px 14px;border-radius:8px;background:#f5f9fc;color:#52606d;font-size:14px;line-height:1.65}.history-advice-gap summary{cursor:pointer;font-weight:700;color:#35546a}.history-advice-urgent{padding:14px 16px;border-left:4px solid #c75b42;border-radius:8px;background:#fff5f0;color:#a9432c;font-size:15px;line-height:1.65}.history-advice-urgent p{margin:6px 0 0;font-weight:600}.history-advice-disclaimer{margin:0;color:#607181;font-size:13px;line-height:1.6}.muted{color:#607181}@media(max-width:680px){.image-grid,.history-advice-grid{grid-template-columns:1fr}.history-actions{gap:10px;flex-wrap:wrap}.history-content{width:min(100% - 20px,1000px);padding-top:24px}.history-header{align-items:flex-start}}
</style>
