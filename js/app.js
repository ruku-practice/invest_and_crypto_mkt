const DATA_URL = 'data/latest.json';
const HISTORY_URL = 'data/history.json';

const formatter = new Intl.DateTimeFormat('ja-JP', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

let dashboardData = null;
let historyData = null;
let selectedDate = '';
let chartFilter = 'all';
let chartRangeKey = 'all';
let chartCustomStart = '';
let chartCustomEnd = '';

const COLORS = ['#0f6b5f', '#b22a2a', '#2d5db3', '#8c5b12', '#5d3fa3', '#0c7a42', '#9b2463', '#48626b', '#d06b1f', '#1d2524', '#627a14'];
const ABSOLUTE_CHART_STARTS = new Set(['2026-01-01', '2025-01-01', '2024-01-01']);
const DAY_MS = 24 * 60 * 60 * 1000;

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function slashToInputDate(date) {
  return date.replaceAll('/', '-');
}

function inputToSlashDate(date) {
  return date.replaceAll('-', '/');
}

function dateMs(date) {
  return new Date(date).getTime();
}

function allDates(data) {
  return [...new Set((data?.items || []).flatMap((item) => item.points.map((point) => point.date)))].sort();
}

function clampDateToAvailable(date, dates) {
  if (!dates.length) return '';
  if (!date) return dates[0];
  const target = dateMs(date);
  if (Number.isNaN(target)) return dates[0];
  if (target <= dateMs(dates[0])) return dates[0];
  if (target >= dateMs(dates[dates.length - 1])) return dates[dates.length - 1];
  return dates.find((value) => dateMs(value) >= target) || dates[dates.length - 1];
}

function normalizeWindow(start, end, dates) {
  const availableStart = clampDateToAvailable(start, dates);
  const availableEnd = clampDateToAvailable(end, dates);
  if (!availableStart || !availableEnd) return { start: availableStart, end: availableEnd };
  if (dateMs(availableStart) <= dateMs(availableEnd)) {
    return { start: availableStart, end: availableEnd };
  }
  return { start: availableEnd, end: availableStart };
}

function formatPct(value) {
  if (typeof value !== 'number') return '--';
  return `${value >= 0 ? '+' : ''}${value.toFixed(Math.abs(value) >= 100 ? 0 : 1)}%`;
}

function formatValue(item, value) {
  if (typeof value !== 'number') return '--';
  const abs = Math.abs(value);
  const decimals = abs < 1 ? 4 : abs < 100 ? 2 : 0;
  const formatted = value.toLocaleString('ja-JP', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  if (item.id === 'usdjpy') return `¥${formatted}`;
  if (item.currency === 'USD') return `$${formatted}`;
  if (item.currency === 'JPY') return `¥${formatted}`;
  return formatted;
}

function changeClass(value) {
  if (typeof value !== 'number') return 'flat';
  if (value > 0) return 'up';
  if (value < 0) return 'down';
  return 'flat';
}

function numericPointsUpTo(item, date) {
  return item.points.filter((point) => point.date <= date && typeof point.value === 'number');
}

function dayChangeFor(item, points) {
  const point = points[points.length - 1];
  if (!point) return undefined;
  if (typeof point.change_from_prev_pct === 'number') return point.change_from_prev_pct;
  const prev = points[points.length - 2];
  if (!prev || !prev.value) return undefined;
  return ((point.value / prev.value) - 1) * 100;
}

function yearBaseChangeFor(item, points) {
  const point = points[points.length - 1];
  if (!point) return undefined;
  const jan1 = `${point.date.slice(0, 4)}/01/01`;
  const allNumeric = item.points.filter((p) => typeof p.value === 'number');
  const before = allNumeric.filter((p) => p.date <= jan1);
  const base = before[before.length - 1] || allNumeric.find((p) => p.date >= jan1);
  if (!base || !base.value) return undefined;
  return ((point.value / base.value) - 1) * 100;
}

function renderQuoteList(id, items) {
  const root = document.getElementById(id);
  if (!root) return;
  root.innerHTML = '';

  items.forEach((item) => {
    const points = numericPointsUpTo(item, selectedDate);
    const point = points[points.length - 1] || null;
    const dayChange = dayChangeFor(item, points);
    const baseChange = yearBaseChangeFor(item, points);
    const row = document.createElement('article');
    row.className = `quote-row ${point ? '' : 'is-error'}`;
    row.innerHTML = `
      <div class="quote-name">${item.name}</div>
      <div class="quote-price">${point ? formatValue(item, point.value) : '--'}</div>
      <div class="quote-change ${changeClass(dayChange)}" data-label="前日比">${formatPct(dayChange)}</div>
      <div class="quote-change ${changeClass(baseChange)}" data-label="1/1比">${formatPct(baseChange)}</div>
    `;
    root.appendChild(row);
  });
}

function renderQuotePanels() {
  const items = historyData?.items || [];
  renderQuoteList('markets-list', items.filter((item) => item.category !== 'crypto'));
  renderQuoteList('crypto-list', items.filter((item) => item.category === 'crypto'));
}

function renderNews(news) {
  const list = document.getElementById('news-list');
  const post = document.getElementById('post-text');
  const status = document.getElementById('news-status');
  const items = news?.items || [];

  if (status) status.textContent = items.length ? '取得済み' : '未連携';
  if (post) post.textContent = news?.post_text || 'ニュース取得の移植後に表示します。';
  if (!list) return;

  list.innerHTML = '';
  if (!items.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-text';
    empty.textContent = 'ニュース取得は次フェーズで連携します。';
    list.appendChild(empty);
    return;
  }

  items.forEach((item) => {
    const article = document.createElement('article');
    article.className = 'news-item';
    const link = item.url
      ? `<a href="${item.url}" target="_blank" rel="noopener">${item.title}</a>`
      : `<span>${item.title}</span>`;
    article.innerHTML = `
      <span class="news-source">${item.source || item.category || 'news'}</span>
      ${link}
      <time>${item.published_at || ''}</time>
    `;
    list.appendChild(article);
  });
}

function chartItems(data) {
  const all = (data?.items || []).filter((item) => Array.isArray(item.points) && item.points.length > 1);
  if (chartFilter === 'markets') return all.filter((item) => item.category !== 'crypto');
  if (chartFilter === 'crypto') return all.filter((item) => item.category === 'crypto');
  return all;
}

function visiblePoints(item, startDate, endDate) {
  return item.points.filter((point) => (
    point.date >= startDate
    && point.date <= endDate
    && typeof point.value === 'number'
  ));
}

function chartWindow(dates) {
  if (!dates.length) return { start: '', end: '' };

  const end = clampDateToAvailable(selectedDate || dates[dates.length - 1], dates);

  if (chartRangeKey === 'all') {
    return { start: dates[0], end };
  }

  if (['90', '30', '7'].includes(chartRangeKey)) {
    const startTime = dateMs(end) - (Number(chartRangeKey) - 1) * DAY_MS;
    const start = dates.find((date) => dateMs(date) >= startTime) || dates[0];
    return normalizeWindow(start, end, dates);
  }

  if (ABSOLUTE_CHART_STARTS.has(chartRangeKey)) {
    const start = clampDateToAvailable(inputToSlashDate(chartRangeKey), dates);
    return {
      start,
      end: dateMs(end) < dateMs(start) ? start : end,
    };
  }

  if (chartRangeKey === 'custom') {
    const start = chartCustomStart ? inputToSlashDate(chartCustomStart) : dates[0];
    const customEnd = chartCustomEnd ? inputToSlashDate(chartCustomEnd) : end;
    return normalizeWindow(start, customEnd, dates);
  }

  return { start: dates[0], end };
}

function placeLabels(labels, minY, maxY) {
  const gap = 18;
  const placed = [...labels].sort((a, b) => a.targetY - b.targetY);
  placed.forEach((label, index) => {
    const lower = index === 0 ? minY : placed[index - 1].labelY + gap;
    label.labelY = Math.max(lower, Math.min(maxY, label.targetY));
  });
  for (let i = placed.length - 2; i >= 0; i -= 1) {
    placed[i].labelY = Math.min(placed[i].labelY, placed[i + 1].labelY - gap);
    placed[i].labelY = Math.max(minY, placed[i].labelY);
  }
  return placed;
}

function renderTrendChart(data) {
  const canvas = document.getElementById('trend-chart');
  if (!canvas || !data) return;

  const dates = allDates(data);
  const items = chartItems(data);
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const cssWidth = Math.max(320, rect.width || 1000);
  const isCompact = cssWidth < 720;
  const cssHeight = Math.max(380, isCompact ? 500 : 560);

  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(cssHeight * dpr);
  canvas.style.height = `${cssHeight}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);
  ctx.fillStyle = '#fffdf7';
  ctx.fillRect(0, 0, cssWidth, cssHeight);

  if (!dates.length || !items.length) {
    ctx.fillStyle = '#66706b';
    ctx.font = '700 16px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    ctx.fillText('表示できる推移データがありません。', 24, 52);
    return;
  }

  const { start, end } = chartWindow(dates);
  const series = items
    .map((item, index) => {
      const rawPoints = visiblePoints(item, start, end);
      const basePoint = rawPoints.find((point) => typeof point.value === 'number') || null;
      if (!basePoint) return null;
      const baseValue = basePoint.value;
      const points = rawPoints.map((point) => ({
        date: point.date,
        value: point.value,
        change_from_base_pct: baseValue ? ((point.value / baseValue) - 1) * 100 : null,
      }));
      return {
        item,
        index,
        points,
        baseDate: basePoint.date,
        baseValue,
      };
    })
    .filter((entry) => entry && entry.points.length > 1);
  const allPoints = series.flatMap((entry) => entry.points);
  if (!allPoints.length) return;

  const left = isCompact ? 54 : 70;
  const right = isCompact ? 20 : 190;
  const top = 30;
  const bottom = isCompact ? 90 : 56;
  const chartWidth = cssWidth - left - right;
  const chartHeight = cssHeight - top - bottom;
  const minValue = Math.min(-5, ...allPoints.map((point) => point.change_from_base_pct));
  const maxValue = Math.max(5, ...allPoints.map((point) => point.change_from_base_pct));
  const minTime = dateMs(start);
  const maxTime = dateMs(end);
  const valueRange = maxValue - minValue || 1;
  const dateRange = maxTime - minTime || 1;
  const xFor = (date) => left + ((dateMs(date) - minTime) / dateRange) * chartWidth;
  const yFor = (value) => top + chartHeight - ((value - minValue) / valueRange) * chartHeight;

  ctx.strokeStyle = '#d7d8cf';
  ctx.lineWidth = 1;
  ctx.font = '700 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  ctx.fillStyle = '#66706b';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';

  for (let i = 0; i <= 5; i += 1) {
    const value = minValue + (valueRange / 5) * i;
    const y = yFor(value);
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(left + chartWidth, y);
    ctx.stroke();
    ctx.fillText(`${value.toFixed(0)}%`, left - 8, y);
  }

  const zeroY = yFor(0);
  ctx.strokeStyle = '#1d2524';
  ctx.beginPath();
  ctx.moveTo(left, zeroY);
  ctx.lineTo(left + chartWidth, zeroY);
  ctx.stroke();

  const labels = [];
  series.forEach((entry) => {
    const color = COLORS[entry.index % COLORS.length];
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    entry.points.forEach((point, pointIndex) => {
      const x = xFor(point.date);
      const y = yFor(point.change_from_base_pct);
      if (pointIndex === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    const latest = entry.points[entry.points.length - 1];
    const latestX = xFor(latest.date);
    const latestY = yFor(latest.change_from_base_pct);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(latestX, latestY, 3, 0, Math.PI * 2);
    ctx.fill();

    labels.push({
      item: entry.item,
      color,
      pointX: latestX,
      pointY: latestY,
      targetY: latestY,
      value: latest.change_from_base_pct,
    });
  });

  if (isCompact) {
    renderMobileLegend(ctx, labels, left, top + chartHeight + 34, chartWidth);
  } else {
    placeLabels(labels, top + 10, top + chartHeight - 10).forEach((label) => {
      const labelX = left + chartWidth + 24;
      const bendX = left + chartWidth + 10;
      ctx.strokeStyle = label.color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(label.pointX + 4, label.pointY);
      ctx.lineTo(bendX, label.labelY);
      ctx.lineTo(labelX - 6, label.labelY);
      ctx.stroke();

      ctx.fillStyle = label.color;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.font = '800 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
      ctx.fillText(`${label.item.name} ${formatPct(label.value)}`, labelX, label.labelY);
    });
  }

  const firstDate = new Date(start);
  const lastDate = new Date(end);
  ctx.fillStyle = '#66706b';
  ctx.font = '700 11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  ctx.textBaseline = 'top';
  ctx.textAlign = 'left';
  ctx.fillText(`${firstDate.getMonth() + 1}/${firstDate.getDate()}`, left, top + chartHeight + 14);
  ctx.textAlign = 'right';
  ctx.fillText(`${lastDate.getMonth() + 1}/${lastDate.getDate()}`, left + chartWidth, top + chartHeight + 14);
}

function renderMobileLegend(ctx, labels, x, y, width) {
  let cursorX = x;
  let cursorY = y;
  ctx.font = '800 11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  ctx.textBaseline = 'middle';
  labels.forEach((label) => {
    const text = `${label.item.name} ${formatPct(label.value)}`;
    const labelWidth = ctx.measureText(text).width + 22;
    if (cursorX + labelWidth > x + width) {
      cursorX = x;
      cursorY += 18;
    }
    ctx.fillStyle = label.color;
    ctx.fillRect(cursorX, cursorY - 4, 10, 8);
    ctx.fillStyle = '#1d2524';
    ctx.textAlign = 'left';
    ctx.fillText(text, cursorX + 14, cursorY);
    cursorX += labelWidth + 8;
  });
}

function renderAll() {
  if (!historyData || !selectedDate) return;
  const dates = allDates(historyData);
  const statusLine = document.getElementById('status-line');
  if (statusLine) {
    const generatedAt = dashboardData?.generated_at ? formatter.format(new Date(dashboardData.generated_at)) : '';
    statusLine.textContent = generatedAt
      ? `最終生成: ${generatedAt} / 表示日: ${selectedDate}`
      : `表示日: ${selectedDate}`;
  }
  renderQuotePanels();
  syncChartControls(dates);
  renderTrendChart(historyData);
}

function syncChartControls(dates) {
  document.querySelectorAll('.chart-range-toggle').forEach((button) => {
    button.classList.toggle('active', button.dataset.chartRange === chartRangeKey);
  });

  const customPanel = document.getElementById('chart-custom-range');
  if (customPanel) customPanel.hidden = chartRangeKey !== 'custom';

  const startInput = document.getElementById('chart-start-date');
  const endInput = document.getElementById('chart-end-date');
  if (!startInput || !endInput || !dates.length) return;

  const window = chartWindow(dates);
  const minDate = slashToInputDate(dates[0]);
  const maxDate = slashToInputDate(dates[dates.length - 1]);
  startInput.min = minDate;
  startInput.max = maxDate;
  endInput.min = minDate;
  endInput.max = maxDate;

  if (chartRangeKey === 'custom') {
    if (!chartCustomStart) chartCustomStart = slashToInputDate(window.start);
    if (!chartCustomEnd) chartCustomEnd = slashToInputDate(window.end);
    startInput.value = chartCustomStart;
    endInput.value = chartCustomEnd;
  } else {
    startInput.value = '';
    endInput.value = '';
  }
}

function bindControls() {
  document.querySelectorAll('.chart-toggle').forEach((button) => {
    button.addEventListener('click', () => {
      chartFilter = button.dataset.chartFilter || 'all';
      document.querySelectorAll('.chart-toggle').forEach((el) => el.classList.toggle('active', el === button));
      renderAll();
    });
  });

  document.querySelectorAll('.chart-range-toggle').forEach((button) => {
    button.addEventListener('click', () => {
      const nextRange = button.dataset.chartRange || 'all';
      const dates = historyData ? allDates(historyData) : [];
      if (nextRange === 'custom' && dates.length) {
        const currentWindow = chartWindow(dates);
        if (!chartCustomStart) chartCustomStart = slashToInputDate(currentWindow.start);
        if (!chartCustomEnd) chartCustomEnd = slashToInputDate(currentWindow.end);
      }
      chartRangeKey = nextRange;
      renderAll();
    });
  });

  const chartStartInput = document.getElementById('chart-start-date');
  const chartEndInput = document.getElementById('chart-end-date');
  if (chartStartInput && chartEndInput) {
    const updateCustomRange = () => {
      chartRangeKey = 'custom';
      chartCustomStart = chartStartInput.value;
      chartCustomEnd = chartEndInput.value;
      renderAll();
    };

    chartStartInput.addEventListener('change', updateCustomRange);
    chartEndInput.addEventListener('change', updateCustomRange);
  }

  const dateInput = document.getElementById('selected-date');
  if (dateInput) {
    dateInput.addEventListener('change', () => {
      selectedDate = inputToSlashDate(dateInput.value);
      setText('updated-date', selectedDate);
      renderAll();
    });
  }

  window.addEventListener('resize', () => {
    window.requestAnimationFrame(renderAll);
  });
}

function setupDateInput(data) {
  const dates = allDates(data);
  const dateInput = document.getElementById('selected-date');
  if (!dates.length || !dateInput) return;
  selectedDate = dates[dates.length - 1];
  dateInput.min = slashToInputDate(dates[0]);
  dateInput.max = slashToInputDate(dates[dates.length - 1]);
  dateInput.value = slashToInputDate(selectedDate);
  setText('updated-date', selectedDate);
  syncChartControls(dates);
}

async function loadDashboard() {
  const statusLine = document.getElementById('status-line');
  try {
    const [latestResponse, historyResponse] = await Promise.all([
      fetch(DATA_URL, { cache: 'no-store' }),
      fetch(HISTORY_URL, { cache: 'no-store' }),
    ]);
    if (!latestResponse.ok) throw new Error(`latest HTTP ${latestResponse.status}`);
    if (!historyResponse.ok) throw new Error(`history HTTP ${historyResponse.status}`);

    dashboardData = await latestResponse.json();
    historyData = await historyResponse.json();
    setupDateInput(historyData);
    setText('updated-time', dashboardData.display_time || '--:--');
    renderNews(dashboardData.news || {});
    renderAll();

    const generatedAt = dashboardData.generated_at ? formatter.format(new Date(dashboardData.generated_at)) : '';
    if (statusLine) {
      statusLine.textContent = generatedAt
        ? `最終生成: ${generatedAt} / 表示日: ${selectedDate}`
        : `表示日: ${selectedDate}`;
      statusLine.classList.add('ready');
    }
  } catch (error) {
    if (statusLine) {
      statusLine.textContent = `データの読み込みに失敗しました: ${error.message}`;
      statusLine.classList.add('error');
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  bindControls();
  loadDashboard();
});
