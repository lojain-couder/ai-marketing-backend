// Local dev → localhost:8000 | Production → same origin as the page
const API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
  ? 'http://localhost:8000'
  : window.location.origin;

window.appState = {
  businessProfile: {},
  salesSummary: null,
  tiktokData: null,
  analysisResult: null,
  currentStep: 1,
  currentDay: 0,
  weeklyPlan: [],
  editMode: {}
};

function saveState() {
  sessionStorage.setItem('mudarState', JSON.stringify(window.appState));
}
function loadState() {
  const s = sessionStorage.getItem('mudarState');
  if (s) { try { window.appState = JSON.parse(s); } catch(e) {} }
}

// ── Toast ──
function toast(msg, type = 'success') {
  const colors = {
    success: { bg: '#C9F03A', text: '#1F176E' },
    error:   { bg: '#fee2e2', text: '#ef4444' },
    info:    { bg: '#EDE9FF', text: '#1F176E' }
  };
  const t = document.createElement('div');
  t.style.cssText = `
    position:fixed;bottom:24px;right:24px;
    background:${colors[type].bg};color:${colors[type].text};
    padding:12px 20px;border-radius:10px;font-family:'Tajawal',sans-serif;
    font-size:14px;font-weight:700;z-index:9999;
    box-shadow:0 4px 20px rgba(31,23,110,0.15);
    animation:slideUp .3s ease;max-width:320px;
  `;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity .3s'; setTimeout(() => t.remove(), 300); }, 3000);
}

// ── API Wrapper ──
async function apiCall(fn) {
  try {
    return await fn();
  } catch (err) {
    toast('حدث خطأ — حاولي مرة ثانية', 'error');
    console.error(err);
    return null;
  }
}

// ── API Functions ──
async function fetchTikTok(username, maxItems) {
  const res = await fetch(`${API_BASE}/api/tiktok/fetch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, max_items: maxItems })
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function runAnalysis(dataset) {
  const res = await fetch(`${API_BASE}/api/analysis/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(dataset)
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function uploadSales(file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/api/business/upload-sales`, {
    method: 'POST',
    body: formData
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function saveBusinessProfile(profile) {
  const res = await fetch(`${API_BASE}/api/business/profile`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile)
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── Helpers ──
function formatNumber(n) {
  if (!n) return '0';
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return String(n);
}

function calcEngagement(v) {
  const views = v.playCount || v.views || 0;
  if (!views) return 0;
  const interactions = (v.diggCount || v.likes || 0) + (v.commentCount || v.comments || 0) + (v.shareCount || v.shares || 0);
  return ((interactions / views) * 100).toFixed(1);
}

function engagementBadge(rate) {
  const r = parseFloat(rate);
  if (r >= 5) return `<span class="badge badge-green">${rate}% عالي</span>`;
  if (r >= 2) return `<span class="badge badge-amber">${rate}% متوسط</span>`;
  return `<span class="badge badge-red">${rate}% منخفض</span>`;
}

function markdownToHtml(text) {
  if (!text) return '';
  return text
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/^#{1,3}\s+(.+)$/gm, '<strong>$1</strong>')
    .replace(/^[-•]\s+(.+)$/gm, '<li>$1</li>')
    .replace(/(<li>[\s\S]*?<\/li>)/g, (m) => `<ul style="margin:8px 0;padding-right:20px">${m}</ul>`)
    .replace(/\n{2,}/g, '<br><br>')
    .replace(/\n/g, '<br>');
}

function parseAnalysisSections(text) {
  if (!text) return {};
  const sections = {};
  const re = /\*\*[١٢٣٤٥٦٧\d]+[.．]\s*([^*\n]+)\*\*|^[١٢٣٤٥٦٧\d]+[.．]\s*\*\*([^*\n]+)\*\*/gm;
  const parts = text.split(/\n(?=\*\*[١٢٣٤٥٦٧\d]+[.．]|\n[١٢٣٤٥٦٧\d]+[.．])/);
  const arabicNums = { '١':'1','٢':'2','٣':'3','٤':'4','٥':'5','٦':'6','٧':'7' };
  parts.forEach(part => {
    const m = part.match(/^[\s\n]*\*?\*?([١٢٣٤٥٦٧\d])/);
    if (m) {
      let num = m[1];
      num = arabicNums[num] || num;
      sections[num] = part.replace(/^[^\n]+\n+/, '').trim();
    }
  });
  return sections;
}
