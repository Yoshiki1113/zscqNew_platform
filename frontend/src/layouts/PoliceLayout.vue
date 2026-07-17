<template>
  <div class="police-shell">
    <header class="police-header">
      <div class="ph-left">
        <div class="ph-logo">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="22" height="22">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
        </div>
      </div>
      <h1 class="ph-name">嘉剧荟驾驶舱</h1>
      <div class="ph-right">
        <RoleSwitcher variant="header" />
      </div>
    </header>
    <main class="police-main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import RoleSwitcher from '@/components/RoleSwitcher.vue'
</script>

<style scoped>
.police-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background:
    radial-gradient(ellipse 70% 40% at 50% 0%, rgba(22, 93, 255, 0.08), transparent),
    linear-gradient(180deg, #edf2f8 0%, #f5f7fa 40%, #eef1f6 100%);
}

.police-header {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 64px;
  padding: 0 16px;
  background: linear-gradient(90deg, #0b2a5b 0%, #123a7a 45%, #165DFF 100%);
  color: #fff;
  box-shadow: 0 2px 12px rgba(11, 42, 91, 0.35);
}

.ph-left {
  position: absolute;
  left: 16px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
}

.ph-right {
  position: absolute;
  right: 16px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  z-index: 2;
}

.ph-logo {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
}

.ph-name {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: 4px;
  text-align: center;
  white-space: nowrap;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

.ph-right :deep(.header .role-btn) {
  background: rgba(255, 255, 255, 0.14);
  border-color: rgba(255, 255, 255, 0.3);
  color: #fff;
}
.ph-right :deep(.header .role-hint) { color: rgba(255, 255, 255, 0.7); }
.ph-right :deep(.header .role-btn:hover) {
  background: rgba(255, 255, 255, 0.24);
  border-color: rgba(255, 255, 255, 0.45);
  color: #fff;
}

.police-main {
  flex: 1;
  padding: 16px 18px 24px;
  max-width: 1600px;
  width: 100%;
  margin: 0 auto;
}

@media (max-width: 640px) {
  .ph-name { font-size: 20px; letter-spacing: 2px; }
  .police-header { height: 56px; padding: 0 12px; }
}
</style>
