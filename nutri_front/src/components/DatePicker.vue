<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({ modelValue: { type: String, default: '' } })
const emit = defineEmits(['update:modelValue'])
const root = ref(null)
const open = ref(false)
const viewDate = ref(toDate(props.modelValue) || new Date())
const weekdays = ['一', '二', '三', '四', '五', '六', '日']

function toDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(year, month - 1, day)
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : null
}
function formatValue(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
const displayValue = computed(() => {
  const date = toDate(props.modelValue)
  return date ? `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日` : ''
})
const monthTitle = computed(() => `${viewDate.value.getFullYear()}年${viewDate.value.getMonth() + 1}月`)
const days = computed(() => {
  const year = viewDate.value.getFullYear()
  const month = viewDate.value.getMonth()
  const firstWeekday = (new Date(year, month, 1).getDay() + 6) % 7
  const count = new Date(year, month + 1, 0).getDate()
  return Array.from({ length: firstWeekday + count }, (_, index) => index < firstWeekday ? null : new Date(year, month, index - firstWeekday + 1))
})

watch(() => props.modelValue, (value) => { if (toDate(value)) viewDate.value = toDate(value) })
function toggle() { open.value = !open.value }
function changeMonth(offset) { viewDate.value = new Date(viewDate.value.getFullYear(), viewDate.value.getMonth() + offset, 1) }
function select(date) { emit('update:modelValue', formatValue(date)); open.value = false }
function clear() { emit('update:modelValue', ''); open.value = false }
function isSelected(date) { return formatValue(date) === props.modelValue }
function isToday(date) { return formatValue(date) === formatValue(new Date()) }
function closeOnOutside(event) { if (root.value && !root.value.contains(event.target)) open.value = false }
onMounted(() => document.addEventListener('mousedown', closeOnOutside))
onBeforeUnmount(() => document.removeEventListener('mousedown', closeOnOutside))
</script>

<template>
  <div ref="root" class="date-picker">
    <button class="date-picker-input" type="button" :class="{ empty: !displayValue }" @click="toggle">
      <span>{{ displayValue || '年-月-日' }}</span><span aria-hidden="true">▦</span>
    </button>
    <div v-if="open" class="date-picker-popover">
      <header><button type="button" aria-label="上个月" @click="changeMonth(-1)">‹</button><strong>{{ monthTitle }}</strong><button type="button" aria-label="下个月" @click="changeMonth(1)">›</button></header>
      <div class="date-picker-weekdays"><span v-for="day in weekdays" :key="day">{{ day }}</span></div>
      <div class="date-picker-days"><span v-for="(date, index) in days" :key="date ? formatValue(date) : `empty-${index}`"><button v-if="date" type="button" :class="{ selected: isSelected(date), today: isToday(date) }" @click="select(date)">{{ date.getDate() }}</button></span></div>
      <footer><button type="button" @click="clear">清除</button><button type="button" @click="select(new Date())">今天</button></footer>
    </div>
  </div>
</template>

<style scoped>
.date-picker{position:relative}.date-picker-input{display:flex;width:100%;height:38px;align-items:center;justify-content:space-between;padding:0 10px;border:1px solid #bfd5e0;border-radius:7px;background:#fff;color:#263746;font:inherit;text-align:left}.date-picker-input.empty{color:#7d8c98}.date-picker-input:focus-visible{outline:2px solid #78bdcf;outline-offset:1px}.date-picker-popover{position:absolute;z-index:30;top:calc(100% + 6px);right:0;width:264px;padding:12px;border:1px solid #c8dbe6;border-radius:10px;background:#fff;box-shadow:0 12px 28px rgba(16,37,63,.16)}.date-picker-popover header,.date-picker-popover footer{display:flex;align-items:center;justify-content:space-between}.date-picker-popover header button,.date-picker-popover footer button{border:0;background:transparent;color:#147a92;font:inherit;font-weight:700;cursor:pointer}.date-picker-popover header button{width:28px;height:28px;border-radius:50%;font-size:22px;line-height:1}.date-picker-popover header button:hover{background:#eefaff}.date-picker-weekdays,.date-picker-days{display:grid;grid-template-columns:repeat(7,1fr);margin-top:10px;text-align:center}.date-picker-weekdays{color:#71808d;font-size:12px}.date-picker-days{row-gap:3px}.date-picker-days span{display:grid;place-items:center;height:30px}.date-picker-days button{width:28px;height:28px;border:0;border-radius:50%;background:transparent;color:#263746;font:inherit;cursor:pointer}.date-picker-days button:hover,.date-picker-days button.today{background:#eefaff;color:#147a92}.date-picker-days button.selected{background:#147a92;color:#fff}.date-picker-popover footer{margin-top:10px;padding-top:10px;border-top:1px solid #e5eef3;font-size:13px}
</style>
