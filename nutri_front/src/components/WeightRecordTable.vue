<script setup>
import { computed, inject, onMounted, ref, watch } from 'vue'

const props = defineProps({
  modelValue: {
    type: Object,
    required: true,
  },
  showErrors: {
    type: Boolean,
    default: false,
  },
  visibleMonths: {
    type: Array,
    default: () => Array.from({ length: 13 }, (_, index) => index),
  },
  requiredMonths: {
    type: Array,
    default: () => ['0', '1', '2', '3'],
  },
  readonlyMonths: {
    type: Array,
    default: () => [],
  },
  monthLabels: {
    type: Object,
    default: () => ({}),
  },
  statusText: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['update:modelValue'])
const draftContext = inject('draftContext', null)
const isRestoring = ref(false)

const visibleMonthKeys = computed(() => props.visibleMonths.map((month) => String(month)))
const requiredMonthKeys = computed(() => props.requiredMonths.map((month) => String(month)))
const readonlyMonthKeys = computed(() => props.readonlyMonths.map((month) => String(month)))

// 只更新当前月份字段，但始终向父级回传完整体重对象，未展示月份不会被清空。
function updateWeight(month, value) {
  if (readonlyMonthKeys.value.includes(month)) return
  emit('update:modelValue', {
    ...props.modelValue,
    [month]: value,
  })
}

function restoreFromDraft() {
  const saved = draftContext?.draftData.weight_records
  if (!saved || !Object.keys(saved).length) return
  isRestoring.value = true
  emit('update:modelValue', { ...props.modelValue, ...saved })
  requestAnimationFrame(() => {
    isRestoring.value = false
  })
}

function missingRequired(month) {
  return props.showErrors && requiredMonthKeys.value.includes(month) && !props.modelValue[month]
}

function isInvalidWeight(month) {
  if (!props.showErrors || !props.modelValue[month]) return false
  const weight = Number(props.modelValue[month])
  return Number.isNaN(weight) || weight < 30 || weight > 200
}

function isReadonly(month) {
  return readonlyMonthKeys.value.includes(month)
}

function monthLabel(month) {
  return props.monthLabels[month] || `${month}个月`
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

watch(
  () => props.modelValue,
  (value) => {
    if (!draftContext || isRestoring.value) return
    draftContext.draftData.weight_records = { ...value }
    draftContext.saveDraft()
  },
  { deep: true },
)
</script>

<template>
  <section class="form-card">
    <div class="section-title-row">
      <div>
        <p class="section-kicker">Weight</p>
        <h2>月度体重记录</h2>
      </div>
      <span class="muted-note">仅显示当前步骤需要的体重节点，其他月份数据会保留</span>
    </div>

    <div class="weight-table-wrap">
      <table class="weight-table">
        <thead>
          <tr>
            <th>距今月数</th>
            <th>体重（kg）</th>
            <th>填写要求</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="month in visibleMonthKeys" :key="month" :class="{ invalid: missingRequired(month) || isInvalidWeight(month) }">
            <td>{{ monthLabel(month) }}</td>
            <td>
              <input
                :value="modelValue[month]"
                type="number"
                min="30"
                max="200"
                step="0.1"
                placeholder="kg"
                :disabled="isReadonly(month)"
                @input="updateWeight(month, $event.target.value)"
              />
            </td>
            <td>
              <span class="require-pill" :class="requiredMonthKeys.includes(month) ? 'required' : 'optional'">
                <strong v-if="requiredMonthKeys.includes(month)">*</strong>
                {{ requiredMonthKeys.includes(month) ? '必填' : '选填' }}
              </span>
              <span v-if="statusText && month === '6'" class="weight-status-text">{{ statusText }}</span>
              <small v-if="isInvalidWeight(month)">体重需填写30到200kg之间的数值</small>
              <small v-if="isReadonly(month)">已锁定</small>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
