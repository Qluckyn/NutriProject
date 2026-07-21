<script setup>
import { ref, watch } from 'vue'
import { API_BASE } from '../config'
const props=defineProps({ open:Boolean })
const emit=defineEmits(['close'])
const items=ref([]), detail=ref(null), error=ref('')
async function load(){try{const r=await fetch(`${API_BASE}/history`);items.value=await r.json();if(!r.ok)throw Error()}catch{error.value='历史记录加载失败。'}}
watch(()=>props.open,v=>{if(v){detail.value=null;load()}},{immediate:true})
async function view(id){const r=await fetch(`${API_BASE}/history/${id}`);detail.value=await r.json()}
async function remove(id){if(!confirm('确定删除此历史记录？'))return;await fetch(`${API_BASE}/history/${id}`,{method:'DELETE'});detail.value=null;load()}
</script>
<template><div v-if="open" class="mask"><section class="panel"><header><h2>历史记录</h2><button @click="emit('close')">关闭</button></header><p v-if="error">{{ error }}</p><div v-if="!detail"><button v-for="x in items" :key="x.id" class="item" @click="view(x.id)">{{x.created_at}}_{{x.patient_name}} <b>查看 →</b></button><p v-if="!items.length">暂无历史记录。</p></div><div v-else><button @click="detail=null">← 返回列表</button><button @click="remove(detail.id)">删除此记录</button><h3>{{detail.created_at}}_{{detail.patient_name}}</h3><h4>评估结果与表单快照</h4><pre>{{JSON.stringify(detail.snapshot,null,2)}}</pre><h4>个性化营养建议</h4><p>{{detail.personalized_analysis?.summary||'未生成个性化建议。'}}</p><h4>DOCX 报告</h4><button v-for="r in [detail.snapshot.nrs2002_result,detail.snapshot.mnasf_result,detail.snapshot.image_result,detail.snapshot.glim_result]" v-if="r?.history_report" :key="r.history_report" @click="window.open(`${API_BASE}/history/${detail.id}/reports/${encodeURIComponent(r.history_report)}`)">{{r.history_report}}</button></div></section></div></template>
<style scoped>.mask{position:fixed;inset:0;z-index:20;padding:5vh 4vw;background:#10253f88;overflow:auto}.panel{max-width:900px;margin:auto;padding:24px;border-radius:10px;background:#fff}.panel header{display:flex;justify-content:space-between}.item{display:flex;width:100%;justify-content:space-between;margin:8px 0;padding:14px;border:1px solid #dceaf2;background:#fff;text-align:left}.panel pre{max-height:420px;overflow:auto;padding:14px;background:#f5f9fc;white-space:pre-wrap}</style>
