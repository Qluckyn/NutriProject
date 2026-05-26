<script setup>
const props = defineProps({
  modelValue: {
    type: Object,
    required: true,
  },
  showErrors: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue'])
const months = Array.from({ length: 13 }, (_, index) => String(index))
const requiredMonths = ['0', '1', '2', '3', '6', '12']

// 表格保留0-12个月的完整记录，提交时由各量表按需校验。
function updateWeight(month, value) {
  emit('update:modelValue', {
    ...props.modelValue,
    [month]: value,
  })
}

function missingRequired(month) {
  return props.showErrors && requiredMonths.includes(month) && !props.modelValue[month]
}
</script>

<template>
  <section class="form-card">
    <div class="section-title-row">
      <div>
        <p class="section-kicker">Weight</p>
        <h2>月度体重记录</h2>
      </div>
      <span class="muted-note">0、1、2、3、6、12个月为常用必填节点</span>
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
          <tr v-for="month in months" :key="month" :class="{ invalid: missingRequired(month) }">
            <td>{{ month }}个月</td>
            <td>
              <input
                :value="modelValue[month]"
                type="number"
                min="0"
                step="0.1"
                placeholder="kg"
                @input="updateWeight(month, $event.target.value)"
              />
            </td>
            <td>
              <span class="require-pill" :class="requiredMonths.includes(month) ? 'required' : 'optional'">
                {{ requiredMonths.includes(month) ? '必填' : '选填' }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
