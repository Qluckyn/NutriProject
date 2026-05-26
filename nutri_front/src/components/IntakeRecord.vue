<script setup>
const props = defineProps({
  weeks: {
    type: Object,
    required: true,
  },
  showErrors: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:weeks', 'update:lastWeek'])

// 第4周是最近一周，会同步给量表计算使用；前3周仅作为临床参考。
function updateWeek(week, value) {
  const next = { ...props.weeks, [week]: value }
  emit('update:weeks', next)
  if (week === '4') {
    emit('update:lastWeek', value)
  }
}
</script>

<template>
  <section class="form-card">
    <div class="section-title-row">
      <div>
        <p class="section-kicker">Intake</p>
        <h2>摄食量记录</h2>
      </div>
    </div>
    <p class="help-text">请填写每周摄食量占正常需求的百分比（0%=完全不进食，100%=正常进食）</p>

    <div class="intake-grid">
      <label v-for="week in ['1', '2', '3', '4']" :key="week" class="field-block intake-week" :class="{ highlight: week === '4', invalid: showErrors && week === '4' && !weeks[week] }">
        <span>第{{ week }}周{{ week === '4' ? '（最近一周）' : '' }}</span>
        <input :value="weeks[week]" type="number" min="0" max="100" step="1" placeholder="%" @input="updateWeek(week, $event.target.value)" />
      </label>
    </div>
  </section>
</template>
