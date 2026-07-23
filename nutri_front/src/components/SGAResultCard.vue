<script setup>
defineProps({
  evaluation: { type: Object, default: null },
  title: { type: String, default: 'SGA 营养状况评估' },
})
</script>

<template>
  <section v-if="evaluation" class="assessment-result sga-assessment-result" :class="evaluation.className">
    <h3 class="final-result-title">{{ title }}</h3>
    <div class="score-hero"><strong>{{ evaluation.level }}</strong></div>
    <div class="result-metrics three"><div v-for="item in evaluation.metrics" :key="item.title"><span>{{ item.title }}</span><strong>{{ item.level }}</strong><p class="metric-reason">{{ item.reason }}</p></div></div>
    <p class="message-text">{{ evaluation.summary }}</p>
  </section>
</template>
