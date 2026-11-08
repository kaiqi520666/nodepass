<script setup lang="ts">
defineProps<{
  eyebrow: string
  title: string
  headingId?: string
}>()
</script>

<template>
  <header class="page-header" :aria-labelledby="headingId">
    <div class="page-header-copy">
      <span class="page-header-accent" aria-hidden="true"></span>
      <div>
        <p class="page-header-eyebrow">{{ eyebrow }}</p>
        <h1 :id="headingId">{{ title }}</h1>
      </div>
    </div>
    <div v-if="$slots.default" class="page-header-actions">
      <slot />
    </div>
  </header>
</template>
