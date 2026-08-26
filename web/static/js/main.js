/* ═══════════════════════════════════════════════════════════════════
   tgstat-opensource — Основной JS (глобальные функции)
   ═══════════════════════════════════════════════════════════════════ */

// ── Helpers ────────────────────────────────────────────────

function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function fmtNum(n) {
  if (n === null || n === undefined) return '—';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return n.toLocaleString('ru');
}

function fmtDate(dt) {
  if (!dt) return '';
  const d = new Date(dt);
  return d.toLocaleDateString('ru', { day: 'numeric', month: 'short' });
}

function fmtDateTime(dt) {
  if (!dt) return '';
  const d = new Date(dt);
  return d.toLocaleString('ru', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
  });
}

function fmtPercent(v) {
  if (v === null || v === undefined) return '—';
  return v.toFixed(2) + '%';
}

function truncate(text, len=120) {
  if (!text) return '';
  return text.length > len ? text.substring(0, len) + '…' : text;
}

function plural(n, forms) {
  const [one, few, many] = forms;
  if (n % 10 === 1 && n % 100 !== 11) return one;
  if (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20)) return few;
  return many;
}

// ── API fetch wrapper ──────────────────────────────────────

async function api(path) {
  const res = await fetch(path);
  if (!res.ok) return null;
  return res.json();
}

// ── Chart store ────────────────────────────────────────────

const charts = {};

function destroyChart(key) {
  if (charts[key]) { charts[key].destroy(); delete charts[key]; }
}

function createChart(canvasId, config) {
  destroyChart(canvasId);
  const canvas = document.getElementById(canvasId);
  if (!canvas) return null;
  const ctx = canvas.getContext('2d');
  charts[canvasId] = new Chart(ctx, config);
  return charts[canvasId];
}

// ── Common line chart builder ──────────────────────────────

function lineChart(canvasId, labels, values, label, color) {
  return createChart(canvasId, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label,
        data: values,
        borderColor: color,
        backgroundColor: color + '18',
        fill: true,
        tension: 0.4,
        pointRadius: 2,
        pointHoverRadius: 5,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { mode: 'index', intersect: false }
      },
      scales: {
        x: {
          ticks: { color: '#6c6c80', maxTicksLimit: 8 },
          grid: { color: 'rgba(42,42,68,0.3)' }
        },
        y: {
          beginAtZero: true,
          ticks: { color: '#6c6c80' },
          grid: { color: 'rgba(42,42,68,0.3)' }
        }
      }
    }
  });
}
