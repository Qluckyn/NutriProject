<script setup>
import { computed, ref, watch } from 'vue'
import { API_BASE, apiUrl } from '../config'

const props = defineProps({
  result: {
    type: Object,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: '',
  },
  expandToken: {
    type: Number,
    default: 0,
  },
})

const viewLabels = {
  front: '正面',
  left: '左45°',
  right: '右45°',
}
const viewOrder = ['front', 'left', 'right']
const activeView = ref('front')
const expanded = ref(false)
const roiLegend = [
  { key: 'temporal', label: '颞部', color: '#ff5050' },
  { key: 'orbital', label: '眶周', color: '#50ffff' },
  { key: 'malar', label: '颧颊', color: '#50b4ff' },
  { key: 'jawline', label: '下颌缘', color: '#64ff64' },
]

const availableViews = computed(() => {
  const views = props.result?.views || {}
  return viewOrder.filter((view) => views[view])
})

const selectedView = computed(() => {
  if (availableViews.value.includes(activeView.value)) return activeView.value
  return availableViews.value[0] || 'front'
})

const selectedResult = computed(() => props.result?.views?.[selectedView.value] || null)

function explainImageSrc(kind) {
  const result = selectedResult.value
  const file = result?.[`${kind}_file`]
  return file ? apiUrl(`${API_BASE}/draft/explain/${selectedView.value}/${kind}`) : result?.[`${kind}_base64`] || ''
}

watch(
  () => props.result,
  () => {
    expanded.value = false
  },
)

watch(
  () => props.expandToken,
  (value) => {
    if (value > 0) expanded.value = true
  },
)
</script>

<template>
  <section v-if="loading || error || result" class="explainability-panel">
    <div class="explain-header">
      <div>
        <p class="section-kicker">Explainability</p>
        <h2>可解释性结果</h2>
      </div>
      <p v-if="result?.target_class_note" class="target-note">{{ result.target_class_note }}</p>
    </div>

    <p v-if="loading" class="explain-state">可解释性结果生成中...</p>
    <p v-else-if="error" class="error-alert">{{ error }}</p>
    <p v-else-if="!availableViews.length" class="explain-state">暂无可解释性结果。</p>

    <template v-else>
      <div class="details-block explain-details-block">
        <button class="details-toggle" type="button" @click="expanded = !expanded">
          <span>可解释性结果</span>
          <strong>{{ expanded ? '收起' : '展开' }}</strong>
        </button>

        <div v-if="expanded" class="explain-details-content">
          <div class="explain-tabs" role="tablist" aria-label="可解释性视角">
            <button
              v-for="view in availableViews"
              :key="view"
              class="explain-tab"
              :class="{ active: selectedView === view }"
              type="button"
              @click="activeView = view"
            >
              {{ viewLabels[view] }}
            </button>
          </div>

          <article class="explain-card">
            <template v-if="selectedResult?.status === 'ok'">
              <div class="explain-image-grid">
                <figure v-if="explainImageSrc('heatmap')" class="explain-figure">
                  <img class="explain-image" :src="explainImageSrc('heatmap')" :alt="`${viewLabels[selectedView]}热力图`" />
                  <figcaption>模型关注热力图</figcaption>
                </figure>
                <figure v-if="explainImageSrc('roi_overlay')" class="explain-figure">
                  <img class="explain-image" :src="explainImageSrc('roi_overlay')" :alt="`${viewLabels[selectedView]}Clinical ROI划分图`" />
                  <figcaption>Clinical ROI划分区域</figcaption>
                </figure>
              </div>
              <div class="roi-legend" aria-label="Clinical ROI图例">
                <span v-for="item in roiLegend" :key="item.key" class="legend-item">
                  <i :style="{ backgroundColor: item.color }"></i>{{ item.label }}
                </span>
              </div>
              <p class="attention-text">{{ selectedResult.attention_text }}</p>
            </template>
            <p v-else class="failed-text">
              该视角未能生成可解释性结果：{{ selectedResult?.reason || '未知原因' }}
            </p>
          </article>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.explainability-panel {
  display: grid;
  gap: 14px;
  padding: 20px;
  border: 1px solid #dceaf2;
  border-radius: 8px;
  background: #fff;
}

.explain-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.explain-header h2 {
  margin: 4px 0 0;
  color: #10253f;
  font-size: 20px;
}

.target-note,
.explain-state,
.attention-text,
.failed-text {
  margin: 0;
  color: #52606d;
  font-size: 14px;
  line-height: 1.6;
}

.target-note {
  max-width: 360px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #eefaff;
  color: #126981;
  font-weight: 800;
}

.explain-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.explain-tab {
  border: 1px solid #d4e4ec;
  border-radius: 999px;
  background: #f7fbfd;
  color: #52606d;
  cursor: pointer;
  font-weight: 800;
  padding: 8px 14px;
}

.explain-tab.active {
  border-color: #1689a7;
  background: #1689a7;
  color: #fff;
}

.explain-details-block {
  margin-top: 0;
}

.explain-details-content {
  display: grid;
  gap: 14px;
  padding: 14px;
}

.explain-card {
  display: grid;
  gap: 10px;
}

.explain-image-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.explain-figure {
  display: grid;
  gap: 8px;
  margin: 0;
}

.explain-image {
  display: block;
  width: 100%;
  aspect-ratio: 1 / 1;
  border-radius: 8px;
  object-fit: contain;
  background: #f2f6f9;
}

.explain-figure figcaption {
  color: #52606d;
  font-size: 13px;
  font-weight: 800;
}

.roi-legend {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px 12px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #52606d;
  font-size: 13px;
  font-weight: 800;
}

.legend-item i {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  border: 1px solid rgba(16, 37, 63, 0.18);
}

.attention-text {
  color: #263746;
  font-weight: 800;
}

.failed-text {
  padding: 14px;
  border-radius: 8px;
  background: #fff7ed;
  color: #9a3412;
  font-weight: 800;
}

@media (max-width: 720px) {
  .explain-header,
  .explain-image-grid {
    display: grid;
    grid-template-columns: 1fr;
  }

  .target-note {
    max-width: none;
  }

  .roi-legend {
    justify-content: flex-start;
  }
}
</style>
