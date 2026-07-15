import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { i18n } from './i18n'
import './assets/main.css'

const savedLocale = localStorage.getItem('locale') as 'en' | 'ru' | null
const browserLocale: 'en' | 'ru' = navigator.language.startsWith('ru') ? 'ru' : 'en'
i18n.global.locale.value = savedLocale ?? browserLocale

const savedTheme = localStorage.getItem('theme')
if (savedTheme === 'light') {
  document.documentElement.classList.add('light-theme')
}

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(i18n)
app.mount('#app')
