<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  result: {
    type: Object,
    required: true,
  },
  showActions: {
    type: Boolean,
    default: true,
  },
  panelTitle: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['reset', 'enable-assessment', 'go-assessment'])
const expanded = ref(false)

const viewLabels = {
  front: '正面',
  left: '左45°',
  right: '右45°',
}

const isMalnourished = computed(() => props.result.prediction === 'malnourished')
const resultTitle = computed(() => (isMalnourished.value ? '营养不良风险' : '营养状态正常'))
const resultIcon = computed(() => (isMalnourished.value ? '!' : '✓'))

function toPercent(value) {
  return `${Math.round(Number(value || 0) * 10000) / 100}%`
}

// 面部筛查提示营养不良风险时，通知父组件解锁量表评估Tab。
watch(
  isMalnourished,
  (value) => {
    if (value) emit('enable-assessment')
  },
  { immediate: true },
)
</script>

<template>
  <section class="result-panel" :class="{ warning: isMalnourished, normal: !isMalnourished }">
    <h3 v-if="panelTitle" class="final-result-title">{{ panelTitle }}</h3>
    <div class="result-summary">
      <div class="result-badge" aria-hidden="true">{{ resultIcon }}</div>
      <div>
        <p class="result-label">筛查结果</p>
        <h2>{{ resultTitle }}</h2>
      </div>
    </div>

    <div class="probability-list">
      <div class="probability-item">
        <div class="probability-header">
          <span>营养不良概率</span>
          <strong>{{ toPercent(result.malnourished_probability) }}</strong>
        </div>
        <div class="progress-track">
          <span class="progress-fill danger" :style="{ width: toPercent(result.malnourished_probability) }"></span>
        </div>
      </div>

      <div class="probability-item">
        <div class="probability-header">
          <span>正常概率</span>
          <strong>{{ toPercent(result.normal_probability) }}</strong>
        </div>
        <div class="progress-track">
          <span class="progress-fill success" :style="{ width: toPercent(result.normal_probability) }"></span>
        </div>
      </div>
    </div>

    <div class="meta-grid">
      <div>
        <span>置信度</span>
        <strong>{{ toPercent(result.confidence) }}</strong>
      </div>
      <div>
        <span>已分析</span>
        <strong>{{ result.views_used.map((item) => viewLabels[item]).join('、') }}</strong>
      </div>
    </div>

    <p class="message-text">{{ result.message }}</p>

    <div class="details-block">
      <button class="details-toggle" type="button" @click="expanded = !expanded">
        <span>各视角详细得分</span>
        <strong>{{ expanded ? '收起' : '展开' }}</strong>
      </button>

      <div v-if="expanded" class="score-list">
        <div v-for="(scores, view) in result.per_view_scores" :key="view" class="score-row">
          <h3>{{ viewLabels[view] }}</h3>
          <p>营养不良：{{ toPercent(scores.malnourished_face) }}</p>
          <p>正常：{{ toPercent(scores.normal_face) }}</p>
        </div>
      </div>
    </div>

    <div v-if="showActions && isMalnourished" class="assessment-advice">
      <p>⚠️ 面部筛查提示存在营养不良风险，建议进一步进行量表评估以明确营养状态。</p>
      <button class="secondary-button" type="button" @click="emit('go-assessment')">前往量表评估</button>
    </div>

    <button v-if="showActions" class="secondary-button" type="button" @click="emit('reset')">重新筛查</button>
  </section>
</template>
