<script setup lang="ts">
import ApiKeysPanel from './ApiKeysPanel.vue'
import PageHeader from '../../components/PageHeader.vue'
</script>

<template>
  <section aria-labelledby="tokens-title">
    <PageHeader eyebrow="控制台" title="API 令牌" heading-id="tokens-title" />
    <ApiKeysPanel />
  </section>
</template>
