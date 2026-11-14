<script setup lang="ts">
import { ChatDotRound, Picture, Right, VideoCamera } from '@element-plus/icons-vue'
</script>

<template>
  <div>
    <section class="home-hero" aria-labelledby="home-title">
      <div class="hero-backdrop" aria-hidden="true"></div>
      <div class="home-hero-grid">
        <div class="home-hero-copy">
          <p class="home-kicker"><span class="home-kicker-dot" aria-hidden="true"></span>图片 · 视频 · 多模态文本</p>
          <h1 id="home-title">一个 Key，<br />调用三类生成能力</h1>
          <p class="home-description">图片生成与编辑、异步视频生成、多模态文本对话，统一使用 OpenAI 兼容接口和按量计费。</p>
          <div class="home-actions">
            <RouterLink to="/pricing" class="primary-link">查看模型与价格</RouterLink>
            <RouterLink to="/api-docs" class="secondary-link">阅读 API 文档</RouterLink>
          </div>
          <dl class="home-proof" aria-label="服务特点">
            <div><dt>接口</dt><dd>OpenAI 兼容</dd></div>
            <div><dt>计费</dt><dd>按量结算</dd></div>
            <div><dt>交付</dt><dd>异步任务</dd></div>
          </dl>
        </div>
        <aside class="home-terminal" aria-labelledby="home-terminal-title">
          <div class="home-terminal-bar">
            <span class="home-terminal-dots" aria-hidden="true"><i></i><i></i><i></i></span>
            <code id="home-terminal-title">POST /v1/images/generations</code>
          </div>
          <pre class="home-terminal-code"><code><span class="home-code-muted"># 提交后返回 202 和任务 ID</span>
POST /v1/images/generations
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  <span class="home-code-accent">"model"</span>: "gpt-image-2",
  <span class="home-code-accent">"prompt"</span>: "a quiet harbor at dawn"
}</code></pre>
          <p class="home-terminal-note">后台异步生成；轮询任务查询结果 URL。</p>
        </aside>
      </div>
    </section>

    <section class="home-showcase" aria-labelledby="showcase-title">
      <div class="showcase-heading">
        <div>
          <p class="home-kicker">能力范围</p>
          <h2 id="showcase-title">图片、视频与文本</h2>
        </div>
        <RouterLink to="/pricing">查看模型广场 <el-icon aria-hidden="true"><Right /></el-icon></RouterLink>
      </div>
      <div class="showcase-grid">
        <figure>
          <div class="media-placeholder" role="img" aria-label="图片效果展示占位">
            <el-icon :size="36" aria-hidden="true"><Picture /></el-icon>
            <span>图片生成与编辑</span>
            <small>固定比例展示占位</small>
          </div>
          <figcaption><strong>图片</strong><span>生成 / 参考图编辑 / mask</span></figcaption>
        </figure>
        <figure>
          <div class="media-placeholder media-placeholder-video" role="img" aria-label="视频效果展示占位">
            <el-icon :size="36" aria-hidden="true"><VideoCamera /></el-icon>
            <span>异步视频生成</span>
            <small>固定比例展示占位</small>
          </div>
          <figcaption><strong>视频</strong><span>首尾帧 / 参考素材 / 异步任务</span></figcaption>
        </figure>
      </div>
      <div class="showcase-text">
        <el-icon :size="20" aria-hidden="true"><ChatDotRound /></el-icon>
        <div><strong>多模态文本</strong><span>图片理解、结构化输出、函数调用、JSON 与 SSE</span></div>
        <RouterLink to="/api-docs#chat-completions">查看文本接口 <el-icon aria-hidden="true"><Right /></el-icon></RouterLink>
      </div>
    </section>
  </div>
</template>
