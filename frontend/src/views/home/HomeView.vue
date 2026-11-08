<script setup lang="ts">
import { Picture, Right, VideoCamera } from '@element-plus/icons-vue'
</script>

<template>
  <div>
    <section class="home-hero" aria-labelledby="home-title">
      <div class="hero-placeholder" role="img" aria-label="首页展示图占位">
        <span><el-icon :size="22" aria-hidden="true"><Picture /></el-icon>首页展示图占位</span>
      </div>
      <div class="home-hero-copy">
        <p class="home-kicker">图片与视频 API</p>
        <h1 id="home-title">NodePass</h1>
        <p class="home-description">了解模型与价格，连接你的应用。</p>
        <div class="home-actions">
          <RouterLink to="/pricing" class="primary-link">查看模型广场</RouterLink>
          <RouterLink to="/api-docs" class="secondary-link">API 文档</RouterLink>
        </div>
      </div>
    </section>
    <section class="home-showcase" aria-labelledby="showcase-title">
      <div class="showcase-heading"><h2 id="showcase-title">图片与视频</h2><RouterLink to="/pricing">查看模型广场 <el-icon aria-hidden="true"><Right /></el-icon></RouterLink></div>
      <div class="showcase-grid">
        <figure>
          <div class="media-placeholder" role="img" aria-label="图片效果展示占位"><el-icon :size="36" aria-hidden="true"><Picture /></el-icon><span>图片展示占位</span></div>
          <figcaption>图片</figcaption>
        </figure>
        <figure>
          <div class="media-placeholder" role="img" aria-label="视频效果展示占位"><el-icon :size="36" aria-hidden="true"><VideoCamera /></el-icon><span>视频展示占位</span></div>
          <figcaption>视频</figcaption>
        </figure>
      </div>
    </section>
  </div>
</template>
