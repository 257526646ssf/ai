import React, { useState } from 'react';
import { 
  Gauge, 
  Search, 
  ChevronDown, 
  ArrowLeft, 
  Play, 
  Download, 
  Sparkles,
  CheckCircle,
  AlertTriangle,
  RotateCw,
  Clock,
  Plus
} from 'lucide-react';
import TiltCard from '../components/TiltCard';
import AnimatedNumber from '../components/AnimatedNumber';
import { apiGet, apiPost, apiRequest, downloadBase64File, downloadTextFile, formatDateTime, pickList } from '../lib/api';
import { useProjectContext } from '../lib/projectContext';

const showToast = (message, type = 'success') => {
  window.dispatchEvent(new CustomEvent('show-toast', { detail: { message, type } }));
};

const DEFAULT_TARGET_APIS = [
  { method: 'POST', url: '/api/v1/auth/login', weight: 30 },
  { method: 'POST', url: '/api/v1/session/create', weight: 40 },
  { method: 'POST', url: '/api/v1/message/send', weight: 30 }
];

const DEFAULT_PERF_FORM = {
  threads: 500,
  duration: '5m',
  rampUp: '1m',
  loops: 1
};

const DEFAULT_THRESHOLDS = {
  p95: 800,
  error_rate: 1,
  avg: 500,
  tps: 100
};

const PRESSURE_VUS = [100, 500, 1000];

const toNumber = (value, fallback = 0) => {
  if (value === '' || value === null || value === undefined) return fallback;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
};

const normalizePercentRate = (value, fallback = 0) => {
  const numeric = toNumber(value, fallback);
  if (numeric < 0) return 0;
  return numeric > 1 ? numeric / 100 : numeric;
};

const percentToFraction = (value) => Math.max(0, toNumber(value, 0) / 100);

const formatMs = (value) => {
  const numeric = toNumber(value, NaN);
  return Number.isFinite(numeric) ? `${Math.round(numeric)}ms` : '--';
};

const formatRate = (value) => {
  const numeric = normalizePercentRate(value, NaN);
  return Number.isFinite(numeric) ? `${(numeric * 100).toFixed(numeric < 0.01 ? 2 : 1)}%` : '--';
};

const formatNumber = (value, suffix = '') => {
  const numeric = toNumber(value, NaN);
  if (!Number.isFinite(numeric)) return '--';
  return `${numeric.toLocaleString('zh-CN', { maximumFractionDigits: numeric >= 100 ? 0 : 2 })}${suffix}`;
};

const parseDurationSeconds = (value, fallback = 60) => {
  if (value === null || value === undefined || value === '') return fallback;
  if (typeof value === 'number') return Math.max(1, Math.round(value));
  const raw = String(value).trim().toLowerCase();
  const match = raw.match(/^(\d+(?:\.\d+)?)(ms|s|m|h)?$/);
  if (!match) return fallback;
  const amount = Number(match[1]);
  const unit = match[2] || 's';
  if (!Number.isFinite(amount)) return fallback;
  if (unit === 'ms') return Math.max(1, Math.round(amount / 1000));
  if (unit === 'm') return Math.max(1, Math.round(amount * 60));
  if (unit === 'h') return Math.max(1, Math.round(amount * 3600));
  return Math.max(1, Math.round(amount));
};

const readSummary = (result) => result?.summary_data || result?.summaryData || {};

const metricValue = (summary, keys, fallback = null) => {
  for (const key of keys) {
    if (summary?.[key] !== undefined && summary?.[key] !== null && summary?.[key] !== '') {
      return toNumber(summary[key], fallback);
    }
  }
  return fallback;
};

const readResultTime = (result) => {
  const value = result?.executed_at || result?.executedAt || result?.created_at || result?.createdAt || result?.updated_at || result?.updatedAt;
  const date = value ? new Date(value) : null;
  if (date && !Number.isNaN(date.getTime())) return date.getTime();
  return toNumber(result?.id, 0);
};

const sortResultsAsc = (results = []) => [...results].sort((a, b) => readResultTime(a) - readResultTime(b));

const sortResultsDesc = (results = []) => [...results].sort((a, b) => readResultTime(b) - readResultTime(a));

const normalizeTargetApis = (value) => {
  const list = Array.isArray(value) ? value : [];
  const normalized = list
    .map((item) => ({
      method: String(item?.method || 'GET').toUpperCase(),
      url: String(item?.url || item?.path || '').trim(),
      weight: Math.max(0, toNumber(item?.weight, 0))
    }))
    .filter((item) => item.url);
  return normalized.length ? normalized : DEFAULT_TARGET_APIS;
};

const extractPlanConfig = (plan) => {
  const raw = plan?.raw || plan || {};
  const assets = raw.target_assets_json || raw.targetAssetsJson || raw.target_assets || {};
  const schema = raw.plan_schema || raw.planSchema || {};
  const targets = Array.isArray(schema.targets) ? schema.targets : schema.targets?.apis;
  const templateParams = schema.template_params || schema.templateParams || assets.template_params || assets.templateParams || {};
  const thresholds = schema.thresholds || assets.thresholds || {};
  const threads = toNumber(templateParams.threads ?? templateParams.vus ?? assets.threads ?? assets.vus ?? schema?.scenarios?.[0]?.users, plan?.vus || DEFAULT_PERF_FORM.threads);
  const duration = templateParams.duration || assets.duration || schema?.scenarios?.[0]?.duration || DEFAULT_PERF_FORM.duration;
  const rampUp = templateParams.ramp_up || templateParams.rampUp || assets.ramp_up || assets.rampUp || DEFAULT_PERF_FORM.rampUp;
  const loops = toNumber(templateParams.loops ?? assets.loops, DEFAULT_PERF_FORM.loops);
  const errorRateThreshold = thresholds.error_rate ?? thresholds.errorRate ?? DEFAULT_THRESHOLDS.error_rate / 100;

  return {
    form: { threads, duration, rampUp, loops },
    thresholds: {
      p95: toNumber(thresholds.p95_ms ?? thresholds.p95 ?? thresholds.rt95, DEFAULT_THRESHOLDS.p95),
      error_rate: normalizePercentRate(errorRateThreshold, DEFAULT_THRESHOLDS.error_rate / 100) * 100,
      avg: toNumber(thresholds.avg_ms ?? thresholds.avg ?? thresholds.average_ms, DEFAULT_THRESHOLDS.avg),
      tps: toNumber(thresholds.tps ?? thresholds.min_tps, DEFAULT_THRESHOLDS.tps)
    },
    targetApis: normalizeTargetApis(assets.apis || assets.targets || targets)
  };
};

const buildThresholdPayload = (thresholds) => ({
  p95_ms: toNumber(thresholds.p95, DEFAULT_THRESHOLDS.p95),
  error_rate: percentToFraction(thresholds.error_rate),
  error_rate_percent: toNumber(thresholds.error_rate, DEFAULT_THRESHOLDS.error_rate),
  avg_ms: toNumber(thresholds.avg, DEFAULT_THRESHOLDS.avg),
  tps: toNumber(thresholds.tps, DEFAULT_THRESHOLDS.tps)
});

const buildPerfPayload = ({ name, form, targetApis, thresholds, previousPlan }) => {
  const previousRaw = previousPlan?.raw || previousPlan || {};
  const previousAssets = previousRaw.target_assets_json || previousRaw.targetAssetsJson || previousRaw.target_assets || {};
  const previousSchema = previousRaw.plan_schema || previousRaw.planSchema || {};
  const apis = normalizeTargetApis(targetApis);
  const templateParams = {
    threads: Math.max(1, toNumber(form.threads, DEFAULT_PERF_FORM.threads)),
    vus: Math.max(1, toNumber(form.threads, DEFAULT_PERF_FORM.threads)),
    duration: form.duration || DEFAULT_PERF_FORM.duration,
    duration_seconds: parseDurationSeconds(form.duration, 300),
    ramp_up: form.rampUp || DEFAULT_PERF_FORM.rampUp,
    ramp_up_seconds: parseDurationSeconds(form.rampUp, 60),
    loops: Math.max(1, toNumber(form.loops, DEFAULT_PERF_FORM.loops))
  };
  const thresholdPayload = buildThresholdPayload(thresholds);

  return {
    name: name || previousRaw.name || 'Performance Plan',
    description: previousRaw.description || '由性能测试页面创建的后端压测方案',
    target_assets: {
      ...previousAssets,
      apis,
      targets: apis,
      vus: templateParams.vus,
      threads: templateParams.threads,
      duration: templateParams.duration,
      ramp_up: templateParams.ramp_up,
      loops: templateParams.loops,
      protocol: previousAssets.protocol || 'HTTP / JSON',
      ref: previousAssets.ref || 'REQ-PERF',
      owner: previousAssets.owner || '系统',
      thresholds: thresholdPayload,
      template_params: templateParams
    },
    target_doc: apis.map((item) => `${item.method} ${item.url} (${item.weight}%)`).join('\n'),
    plan_schema: {
      ...previousSchema,
      targets: apis,
      thresholds: thresholdPayload,
      template_params: templateParams,
      scenarios: [
        {
          name: previousSchema?.scenarios?.[0]?.name || 'main',
          users: templateParams.vus,
          duration: templateParams.duration,
          ramp_up: templateParams.ramp_up,
          loops: templateParams.loops,
          targets: apis
        }
      ]
    },
    status: previousRaw.status || 'draft'
  };
};

const normalizeThresholdResults = (rawResults) => {
  if (!rawResults) return [];
  if (Array.isArray(rawResults)) {
    return rawResults.map((item, index) => ({
      metric: item.metric || item.name || `threshold_${index + 1}`,
      label: item.label || item.metric || item.name || `阈值 ${index + 1}`,
      actual: item.actual ?? item.value,
      threshold: item.threshold ?? item.expected,
      status: normalizeThresholdStatus(item.status ?? item.result ?? (item.passed === false ? 'fail' : item.passed === true ? 'pass' : 'warning')),
      message: item.message || item.detail || ''
    }));
  }
  if (typeof rawResults === 'object') {
    return Object.entries(rawResults).map(([metric, value]) => {
      if (value && typeof value === 'object') {
        return {
          metric,
          label: value.label || metric,
          actual: value.actual ?? value.value,
          threshold: value.threshold ?? value.expected,
          status: normalizeThresholdStatus(value.status ?? value.result ?? (value.passed === false ? 'fail' : value.passed === true ? 'pass' : 'warning')),
          message: value.message || value.detail || ''
        };
      }
      return {
        metric,
        label: metric,
        actual: value,
        threshold: '',
        status: normalizeThresholdStatus(value === false ? 'fail' : value === true ? 'pass' : value),
        message: ''
      };
    });
  }
  return [];
};

const normalizeThresholdStatus = (value) => {
  const raw = String(value || '').toLowerCase();
  if (['pass', 'passed', 'success', 'ok', 'true'].includes(raw)) return 'pass';
  if (['fail', 'failed', 'error', 'critical', 'false'].includes(raw)) return 'fail';
  return 'warning';
};

const summarizeThresholdStatus = (items, backendStatus) => {
  if (backendStatus) return normalizeThresholdStatus(backendStatus);
  if (items.some((item) => item.status === 'fail')) return 'fail';
  if (items.some((item) => item.status === 'warning')) return 'warning';
  return 'pass';
};

const evaluateThresholds = (result, thresholds) => {
  const summary = readSummary(result);
  const backendItems = normalizeThresholdResults(summary.threshold_results || summary.thresholdResults || result?.threshold_results || result?.thresholdResults);
  if (backendItems.length) {
    return {
      status: summarizeThresholdStatus(backendItems, summary.threshold_status || summary.thresholdStatus || result?.threshold_status || result?.thresholdStatus),
      source: '后端判定',
      items: backendItems
    };
  }

  const thresholdPayload = buildThresholdPayload(thresholds);
  const p95 = metricValue(summary, ['p95_ms', 'p95', 'rt95_ms', 'rt95']);
  const avg = metricValue(summary, ['avg_ms', 'average_ms', 'avg', 'mean_ms']);
  const tps = metricValue(summary, ['tps', 'max_tps', 'throughput', 'rps']);
  const errorRate = normalizePercentRate(metricValue(summary, ['error_rate', 'err_rate', 'errors_rate'], NaN), NaN);
  const items = [
    buildLocalThresholdItem('P95 RT', p95, thresholdPayload.p95_ms, '<=', 'ms'),
    buildLocalThresholdItem('平均 RT', avg, thresholdPayload.avg_ms, '<=', 'ms'),
    buildLocalThresholdItem('错误率', errorRate, thresholdPayload.error_rate, '<=', '%'),
    buildLocalThresholdItem('TPS', tps, thresholdPayload.tps, '>=', '/s')
  ];

  return { status: summarizeThresholdStatus(items), source: '前端本地计算', items };
};

const buildLocalThresholdItem = (label, actual, threshold, operator, unit) => {
  const hasActual = actual !== null && actual !== undefined && Number.isFinite(Number(actual));
  const hasThreshold = threshold !== null && threshold !== undefined && Number.isFinite(Number(threshold));
  if (!hasActual || !hasThreshold) {
    return { label, actual: '--', threshold: hasThreshold ? formatThresholdValue(threshold, unit) : '--', status: 'warning', message: '缺少可判定数据' };
  }
  const passed = operator === '>=' ? Number(actual) >= Number(threshold) : Number(actual) <= Number(threshold);
  return {
    label,
    actual: formatThresholdValue(actual, unit),
    threshold: `${operator} ${formatThresholdValue(threshold, unit)}`,
    status: passed ? 'pass' : 'fail',
    message: passed ? '达标' : '超出阈值'
  };
};

const formatThresholdValue = (value, unit) => {
  if (unit === '%') return formatRate(value);
  return `${formatNumber(value)}${unit}`;
};

const normalizeTrendPoint = (item, fallbackIndex = 0) => {
  const summary = item?.summary_data || item?.summaryData || item || {};
  const date = item?.date || item?.day || item?.executed_at || item?.executedAt || item?.created_at || item?.createdAt || `#${fallbackIndex + 1}`;
  return {
    date: String(date).includes('T') ? String(date).slice(0, 10) : String(date),
    avg_ms: metricValue(summary, ['avg_ms', 'average_ms', 'avg', 'mean_ms']),
    p95_ms: metricValue(summary, ['p95_ms', 'p95', 'rt95_ms', 'rt95']),
    tps: metricValue(summary, ['tps', 'max_tps', 'throughput', 'rps']),
    error_rate: normalizePercentRate(metricValue(summary, ['error_rate', 'err_rate', 'errors_rate'], NaN), NaN),
    vus: metricValue(summary, ['vus', 'virtual_users', 'threads'], item?.vus ?? item?.virtual_users ?? item?.threads ?? null),
    count: toNumber(item?.count ?? item?.executions ?? item?.total ?? 1, 1)
  };
};

const normalizeTrendPayload = (payload) => {
  const list = pickList(payload).length
    ? pickList(payload)
    : (Array.isArray(payload?.points) ? payload.points : Array.isArray(payload?.trend) ? payload.trend : []);
  return list.map(normalizeTrendPoint).filter((item) => item.avg_ms !== null || item.p95_ms !== null || item.tps !== null || Number.isFinite(item.error_rate));
};

const aggregateTrendFromPlans = (plans = []) => {
  const groups = new Map();
  plans.flatMap((plan) => plan.results || []).forEach((result, index) => {
    const point = normalizeTrendPoint(result, index);
    if (!point.date) return;
    const current = groups.get(point.date) || { date: point.date, avg_ms: 0, p95_ms: 0, tps: 0, error_rate: 0, vus: 0, count: 0 };
    const weight = Math.max(1, point.count || 1);
    current.avg_ms += toNumber(point.avg_ms, 0) * weight;
    current.p95_ms += toNumber(point.p95_ms, 0) * weight;
    current.tps += toNumber(point.tps, 0) * weight;
    current.error_rate = Math.max(current.error_rate, Number.isFinite(point.error_rate) ? point.error_rate : 0);
    current.vus = Math.max(current.vus, toNumber(point.vus, 0));
    current.count += weight;
    groups.set(point.date, current);
  });
  return [...groups.values()]
    .sort((a, b) => String(a.date).localeCompare(String(b.date)))
    .slice(-7)
    .map((item) => ({
      ...item,
      avg_ms: item.count ? item.avg_ms / item.count : null,
      p95_ms: item.count ? item.p95_ms / item.count : null,
      tps: item.count ? item.tps / item.count : null
    }));
};

const resultSummaryRows = (results, thresholds) => {
  const sorted = sortResultsAsc(results);
  const baseline = sorted.find((item) => item.is_baseline || item.isBaseline) || sorted[0] || null;
  const baselineSummary = readSummary(baseline);
  const baselineP95 = metricValue(baselineSummary, ['p95_ms', 'p95', 'rt95_ms', 'rt95']);
  const baselineAvg = metricValue(baselineSummary, ['avg_ms', 'average_ms', 'avg', 'mean_ms']);
  const baselineTps = metricValue(baselineSummary, ['tps', 'max_tps', 'throughput', 'rps']);
  const baselineErr = normalizePercentRate(metricValue(baselineSummary, ['error_rate', 'err_rate', 'errors_rate'], NaN), NaN);

  return sorted.map((result, index) => {
    const summary = readSummary(result);
    const p95 = metricValue(summary, ['p95_ms', 'p95', 'rt95_ms', 'rt95']);
    const avg = metricValue(summary, ['avg_ms', 'average_ms', 'avg', 'mean_ms']);
    const tps = metricValue(summary, ['tps', 'max_tps', 'throughput', 'rps']);
    const errorRate = normalizePercentRate(metricValue(summary, ['error_rate', 'err_rate', 'errors_rate'], NaN), NaN);
    const thresholdView = evaluateThresholds(result, thresholds);
    const p95Regression = Number.isFinite(p95) && Number.isFinite(baselineP95) && baselineP95 > 0 && p95 > baselineP95 * 1.1;
    const errorRegression = Number.isFinite(errorRate) && Number.isFinite(baselineErr) && errorRate > baselineErr + 0.005;
    const tpsRegression = Number.isFinite(tps) && Number.isFinite(baselineTps) && baselineTps > 0 && tps < baselineTps * 0.9;
    const isRegression = index > 0 && (p95Regression || errorRegression || tpsRegression || thresholdView.status === 'fail');

    return {
      id: result.id || index + 1,
      build: result.is_baseline || result.isBaseline ? 'Baseline' : `Run #${result.id || index + 1}`,
      time: formatDateTime(result.executed_at || result.executedAt || result.created_at || result.createdAt),
      vus: metricValue(summary, ['vus', 'virtual_users', 'threads'], '--'),
      avg,
      p95,
      tps,
      errorRate,
      cpu: metricValue(summary, ['cpu_peak', 'cpu', 'cpu_usage'], null),
      mem: metricValue(summary, ['mem_peak', 'memory', 'memory_usage'], null),
      status: result.is_baseline || result.isBaseline ? '基线' : isRegression ? '回归' : thresholdView.status === 'warning' ? '告警' : '通过',
      thresholdStatus: thresholdView.status,
      isRegression,
      p95Delta: buildDeltaText(p95, baselineP95, false),
      avgDelta: buildDeltaText(avg, baselineAvg, false),
      tpsDelta: buildDeltaText(tps, baselineTps, true)
    };
  });
};

const buildDeltaText = (value, baseline, higherBetter) => {
  if (!Number.isFinite(Number(value)) || !Number.isFinite(Number(baseline)) || Number(baseline) === 0) return '—';
  const delta = (Number(value) - Number(baseline)) / Number(baseline);
  const improved = higherBetter ? delta >= 0 : delta <= 0;
  return `${delta >= 0 ? '+' : ''}${(delta * 100).toFixed(1)}%${improved ? ' 改善' : ' 回退'}`;
};

const buildLinePath = (points, key, width = 400, height = 120, padding = 10) => {
  const values = points.map((point) => toNumber(point?.[key], NaN));
  const validValues = values.filter(Number.isFinite);
  if (points.length < 2 || !validValues.length) return '';
  const max = Math.max(...validValues, 1);
  const min = Math.min(...validValues, 0);
  const span = Math.max(1, max - min);
  return points.map((point, index) => {
    const raw = toNumber(point?.[key], min);
    const x = padding + index * ((width - padding * 2) / Math.max(1, points.length - 1));
    const y = height - padding - ((raw - min) / span) * (height - padding * 2);
    return `${index === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(' ');
};

const extractReportAdvice = (payload) => {
  const report = payload?.report || payload?.data?.report || payload;
  const snapshot = report?.data_snapshot || report?.dataSnapshot || payload?.data_snapshot || payload?.dataSnapshot || {};
  const risks = payload?.risk_items || payload?.riskItems || report?.risk_items || report?.riskItems || snapshot?.risk_items || snapshot?.riskItems || [];
  const rawRecommendations = payload?.recommendations || report?.recommendations || snapshot?.recommendations || snapshot?.perf?.recommendations || [];
  const content = report?.content || payload?.content || '';
  const contentRecommendations = typeof content === 'string'
    ? content.split('\n').map((line) => line.replace(/^[-*\d.\s#]+/, '').trim()).filter((line) => /建议|优化|风险|需要|推荐/.test(line)).slice(0, 5)
    : [];
  return {
    risks: Array.isArray(risks) ? risks : [],
    recommendations: Array.isArray(rawRecommendations) && rawRecommendations.length ? rawRecommendations : contentRecommendations,
    content
  };
};

const buildTransactionRows = (result, apis, thresholds) => {
  if (!result) return [];
  const summary = readSummary(result);
  const candidates = result.transaction_details || result.transactionDetails || summary.transactions || summary.transaction_details || summary.transactionDetails || [];
  const rows = Array.isArray(candidates) && candidates.length
    ? candidates
    : normalizeTargetApis(apis).map((api) => ({
      name: `${api.method} ${api.url}`,
      count: summary.total_requests || summary.samples || summary.count,
      avg_ms: metricValue(summary, ['avg_ms', 'average_ms', 'avg', 'mean_ms']),
      p95_ms: metricValue(summary, ['p95_ms', 'p95', 'rt95_ms', 'rt95']),
      tps: metricValue(summary, ['tps', 'max_tps', 'throughput', 'rps']),
      error_rate: metricValue(summary, ['error_rate', 'err_rate', 'errors_rate'], 0),
      errors: summary.error_count || summary.errors || 0
    }));

  const thresholdPayload = buildThresholdPayload(thresholds);
  return rows.map((row, index) => {
    const p95 = metricValue(row, ['p95_ms', 'p95', 'rt95_ms', 'rt95']);
    const avg = metricValue(row, ['avg_ms', 'average_ms', 'avg', 'mean_ms']);
    const tps = metricValue(row, ['tps', 'throughput', 'rps']);
    const errorRate = normalizePercentRate(metricValue(row, ['error_rate', 'err_rate', 'errors_rate'], 0), 0);
    const failed = (Number.isFinite(p95) && p95 > thresholdPayload.p95_ms) || errorRate > thresholdPayload.error_rate;
    const warning = Number.isFinite(avg) && avg > thresholdPayload.avg_ms;
    return {
      name: row.name || row.label || row.url || `${row.method || 'REQ'} #${index + 1}`,
      count: formatNumber(row.count || row.samples || row.total_requests || '--'),
      rt: formatMs(avg),
      rt95: formatMs(p95),
      tps: Number.isFinite(tps) ? formatNumber(tps, ' /s') : '--',
      err: `${formatNumber(row.errors || row.error_count || 0)} (${formatRate(errorRate)})`,
      status: failed ? '失败' : warning ? '告警' : '通过',
      statusColor: failed ? 'text-red-500 bg-red-50' : warning ? 'text-amber-600 bg-amber-50' : 'text-emerald-500 bg-emerald-50'
    };
  });
};

const mapBackendPerfPlan = (plan, latestResult = null, results = []) => {
  const assets = plan.target_assets_json || plan.targetAssetsJson || {};
  const schema = plan.plan_schema || plan.planSchema || {};
  const summary = latestResult?.summary_data || latestResult?.summaryData || {};
  const config = extractPlanConfig({ raw: plan, vus: assets.vus || schema?.scenarios?.[0]?.users });
  const vus = Number(assets.vus || config.form.threads || schema?.scenarios?.[0]?.users || 100);
  const normalizedStatus = String(plan.status || '').toLowerCase();
  const status = normalizedStatus === 'executed' ? '已完成' : normalizedStatus === 'execution_failed' ? '执行失败' : normalizedStatus === 'aborted' ? '已中止' : normalizedStatus === 'scripted' ? '已生成脚本' : normalizedStatus === 'planned' ? '已规划' : '草稿';
  const statusColor = normalizedStatus === 'executed' ? 'bg-emerald-500' : normalizedStatus === 'execution_failed' ? 'bg-red-500' : normalizedStatus === 'aborted' ? 'bg-amber-500' : normalizedStatus === 'scripted' ? 'bg-blue-500' : 'bg-slate-400';
  return {
    backendId: plan.id,
    name: plan.name || 'Performance Plan',
    ref: assets.ref || plan.target_doc || '后端方案',
    vus,
    type: assets.protocol || 'HTTP / JSON',
    status,
    statusColor,
    rt: summary.avg_ms ? `${summary.avg_ms}ms` : '—',
    owner: assets.owner || '系统',
    time: formatDateTime(plan.updated_at || plan.created_at),
    raw: plan,
    latestResult,
    results,
    thresholds: config.thresholds
  };
};

export default function Performance() {
  const { selectedProject, loading: projectLoading, error: projectError } = useProjectContext();
  const [viewMode, setViewMode] = useState('list'); // 'list', 'report', 'plan-create', 'script-gen', 'history-compare'
  const [isRunning, setIsRunning] = useState(false);
  const [pressureMode, setPressureMode] = useState(0);
  const [planName, setPlanName] = useState('智能客服高并发接口压力测试');
  const [selectedPlanIndex, setSelectedPlanIndex] = useState(0);
  const [projectContext, setProjectContext] = useState(null);
  const [remotePlans, setRemotePlans] = useState([]);
  const [perfStatus, setPerfStatus] = useState({ loading: true, usingBackend: false, message: '正在同步后端性能方案...' });
  const [perfExecution, setPerfExecution] = useState(null);
  const [perfReportPayload, setPerfReportPayload] = useState(null);
  const [generatedScriptContent, setGeneratedScriptContent] = useState('');
  const [useJMeterRunner, setUseJMeterRunner] = useState(false);
  const [generateHtmlReport, setGenerateHtmlReport] = useState(true);
  const [runtimeDeps, setRuntimeDeps] = useState(null);
  const [perfForm, setPerfForm] = useState(DEFAULT_PERF_FORM);
  const [thresholds, setThresholds] = useState(DEFAULT_THRESHOLDS);
  const [targetApis, setTargetApis] = useState(DEFAULT_TARGET_APIS);
  const [editingPlanId, setEditingPlanId] = useState(null);
  const [runState, setRunState] = useState({ status: 'idle', planId: null, jobId: null, resultId: null, controller: null, message: '' });
  const [performanceTrend, setPerformanceTrend] = useState({ loading: false, source: 'none', points: [], message: '' });

  // 19-页指标
  const perfStats = [
    { label: '方案总数', val: '8', change: '较昨日 持平', icon: Gauge, color: 'text-blue-500 bg-blue-500/10' },
    { label: '总执行次数', val: '64', change: '较昨日 ↑ 3', icon: Clock, color: 'text-purple-500 bg-purple-500/10' },
    { label: '并发上限 (VUs)', val: '10,000', change: '较上月 提升 20%', icon: Play, color: 'text-indigo-500 bg-indigo-500/10' },
    { label: '健康方案数', val: '6', change: '通过率 85.0%', hasChart: true }
  ];

  const perfPlans = [
    { name: 'AI需求解析接口100并发压测', ref: 'REQ-001 用户登录', vus: 100, type: 'HTTP / JSON', status: '已完成', statusColor: 'bg-emerald-500', rt: '156ms', owner: '张明' },
    { name: '电商核心结算下单链路混合负载', ref: 'REQ-004 下单模块', vus: 500, type: 'gRPC / JSON', status: '运行中', statusColor: 'bg-blue-500 animate-pulse', rt: '210ms', owner: '李华' },
    { name: '支付回调接收端并发压测', ref: 'REQ-005 支付网关', vus: 800, type: 'HTTP / XML', status: '已完成', statusColor: 'bg-emerald-500', rt: '184ms', owner: '王芳' },
    { name: 'SSO 登录授权高频率并发压测', ref: 'REQ-002 统一鉴权', vus: 300, type: 'HTTP / JSON', status: '排队中', statusColor: 'bg-slate-400', rt: '—', owner: '赵强' }
  ];

  const displayPlans = remotePlans.length ? remotePlans : perfPlans;
  const activePlan = displayPlans[selectedPlanIndex] || displayPlans[0] || perfPlans[0];
  const trendLatest = performanceTrend.points[performanceTrend.points.length - 1] || null;
  const healthyPercent = remotePlans.length
    ? Math.round((remotePlans.filter(item => item.latestResult && evaluateThresholds(item.latestResult, item.thresholds || DEFAULT_THRESHOLDS).status === 'pass').length / remotePlans.length) * 100)
    : 85;
  const displayStats = remotePlans.length ? [
    { label: '方案总数', val: String(remotePlans.length), change: projectContext?.name || '后端项目', icon: Gauge, color: 'text-blue-500 bg-blue-500/10' },
    { label: '总执行次数', val: String(remotePlans.reduce((total, item) => total + (item.results?.length || 0), 0)), change: '由 PerfResult 汇总', icon: Clock, color: 'text-purple-500 bg-purple-500/10' },
    { label: '并发上限 (VUs)', val: String(Math.max(...remotePlans.map(item => Number(item.vus || 0)), 0)), change: '后端方案目标并发', icon: Play, color: 'text-indigo-500 bg-indigo-500/10' },
    { label: '7日趋势 P95', val: trendLatest?.p95_ms ? formatMs(trendLatest.p95_ms) : '--', change: performanceTrend.source === 'backend' ? '后端趋势接口' : '本地结果聚合', hasChart: true, chartValue: healthyPercent }
  ] : perfStats;

  const loadPerformanceData = React.useCallback(async ({ silent = false, focusPlanId = null } = {}) => {
    if (!silent) setPerfStatus(prev => ({ ...prev, loading: true }));
    try {
      if (projectLoading) return;
      if (!selectedProject?.id) {
        setProjectContext(null);
        setRemotePlans([]);
        setPerformanceTrend({ loading: false, source: 'none', points: [], message: '暂无项目，无法加载趋势。' });
        setPerfStatus({ loading: false, usingBackend: false, message: projectError || '后端暂无项目，列表使用内置样例。' });
        return;
      }

      const payload = await apiGet(`/projects/${selectedProject.id}/perf-plans`, { params: { page: 1, pageSize: 20 } }).catch(() => null);
      const selected = { project: selectedProject, plans: pickList(payload) };

      const enrichedPlans = await Promise.all(selected.plans.map(async (plan) => {
        const resultPayload = await apiGet(`/perf-plans/${plan.id}/results`).catch(() => null);
        const results = sortResultsDesc(pickList(resultPayload));
        const latestResult = results[0] || null;
        return mapBackendPerfPlan(plan, latestResult, results);
      }));

      let trendState = { loading: false, source: 'local', points: aggregateTrendFromPlans(enrichedPlans), message: '由本地 PerfResult 聚合' };
      try {
        setPerformanceTrend(prev => ({ ...prev, loading: true }));
        const trendPayload = await apiGet(`/projects/${selectedProject.id}/performance-trend`, { params: { days: 7 }, timeoutMs: 12000 });
        const points = normalizeTrendPayload(trendPayload);
        trendState = points.length
          ? { loading: false, source: 'backend', points, message: '来自后端 performance-trend 接口' }
          : trendState;
      } catch (trendError) {
        trendState = { ...trendState, message: `后端趋势接口不可用，已用本地结果聚合：${trendError.message || trendError}` };
      }

      setProjectContext(selected.project);
      setRemotePlans(enrichedPlans);
      setPerformanceTrend(trendState);
      setSelectedPlanIndex(prev => {
        if (focusPlanId) {
          const focusedIndex = enrichedPlans.findIndex(item => String(item.backendId) === String(focusPlanId));
          if (focusedIndex >= 0) return focusedIndex;
        }
        return Math.min(prev, Math.max(enrichedPlans.length - 1, 0));
      });
      setPerfStatus({
        loading: false,
        usingBackend: enrichedPlans.length > 0,
        message: enrichedPlans.length > 0
          ? `已同步后端项目「${selected.project.name}」的性能方案与结果。`
          : `后端项目「${selected.project.name}」暂无性能方案，可新建后执行。`
      });
    } catch (error) {
      setPerfStatus({ loading: false, usingBackend: false, message: `性能方案加载失败：${error.message || error}` });
      showToast(`性能方案加载失败：${error.message || error}`, 'error');
    }
  }, [projectLoading, projectError, selectedProject]);

  React.useEffect(() => {
    loadPerformanceData();
  }, [loadPerformanceData]);

  React.useEffect(() => {
    let cancelled = false;
    apiGet('/system/runtime-dependencies')
      .then((payload) => {
        if (!cancelled) setRuntimeDeps(payload);
      })
      .catch(() => {
        if (!cancelled) setRuntimeDeps(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const agentLoads = [
    [
      { name: 'Agent-01 (北京)', cpu: 32, mem: 45, status: 'online' },
      { name: 'Agent-02 (深圳)', cpu: 48, mem: 60, status: 'online' },
      { name: 'Agent-03 (上海)', cpu: 22, mem: 38, status: 'online' }
    ],
    [
      { name: 'Agent-01 (北京)', cpu: 89, mem: 91, status: 'high-load' },
      { name: 'Agent-02 (深圳)', cpu: 94, mem: 88, status: 'high-load' },
      { name: 'Agent-03 (上海)', cpu: 76, mem: 82, status: 'high-load' }
    ],
    [
      { name: 'Agent-01 (北京)', cpu: 54, mem: 68, status: 'online' },
      { name: 'Agent-02 (深圳)', cpu: 61, mem: 72, status: 'online' },
      { name: 'Agent-03 (上海)', cpu: 30, mem: 46, status: 'online' }
    ],
    [
      { name: 'Agent-01 (北京)', cpu: 2, mem: 12, status: 'idle' },
      { name: 'Agent-02 (深圳)', cpu: 1, mem: 10, status: 'idle' },
      { name: 'Agent-03 (上海)', cpu: 1, mem: 14, status: 'idle' }
    ]
  ];

  // 20-页核心数据
  const reportMetrics = [
    { label: '并发 VUs', val: '--', sub: '暂无执行结果' },
    { label: '平均响应时间 (RT)', val: '--', sub: '95% RT: --' },
    { label: '吞吐量 (TPS)', val: '--', sub: '等待压测执行' },
    { label: '异常率', val: '--', sub: '错误明细: --' }
  ];

  const updatePerfForm = (key, value) => {
    setPerfForm(prev => ({ ...prev, [key]: value }));
  };

  const updateThreshold = (key, value) => {
    setThresholds(prev => ({ ...prev, [key]: value }));
  };

  const updateTargetApi = (index, patch) => {
    setTargetApis(prev => prev.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  };

  const openCreatePlan = () => {
    setEditingPlanId(null);
    setPlanName('智能客服高并发接口压力测试');
    setPerfForm(DEFAULT_PERF_FORM);
    setThresholds(DEFAULT_THRESHOLDS);
    setTargetApis(DEFAULT_TARGET_APIS);
    setViewMode('plan-create');
  };

  const openEditPlan = (plan) => {
    const config = extractPlanConfig(plan);
    setEditingPlanId(plan?.backendId || null);
    setPlanName(plan?.name || 'Performance Plan');
    setPerfForm(config.form);
    setThresholds(config.thresholds);
    setTargetApis(config.targetApis);
    setViewMode('plan-create');
  };

  const savePerfPlanFromForm = async () => {
    if (!projectContext?.id) {
      throw new Error('后端暂无可关联的项目，请先在项目管理中创建项目。');
    }
    const existingPlan = editingPlanId ? displayPlans.find(item => item.backendId === editingPlanId) : null;
    const payload = buildPerfPayload({
      name: planName,
      form: perfForm,
      targetApis,
      thresholds,
      previousPlan: existingPlan
    });
    const saved = existingPlan?.backendId
      ? await apiRequest(`/perf-plans/${existingPlan.backendId}`, { method: 'PATCH', body: payload, timeoutMs: 15000 })
      : await apiPost(`/projects/${projectContext.id}/perf-plans`, payload, { timeoutMs: 15000 });
    const mapped = mapBackendPerfPlan(saved, existingPlan?.latestResult || null, existingPlan?.results || []);
    setEditingPlanId(mapped.backendId);
    return mapped;
  };

  const ensureBackendPerfPlan = async (plan = activePlan) => {
    if (viewMode === 'plan-create' || !plan?.backendId) {
      return savePerfPlanFromForm();
    }
    if (viewMode === 'script-gen' && editingPlanId) {
      return displayPlans.find(item => String(item.backendId) === String(editingPlanId)) || plan;
    }
    return plan;
  };

  const buildExecutionPayload = (plan) => {
    const config = viewMode === 'plan-create'
      ? { form: perfForm, thresholds, targetApis }
      : extractPlanConfig(plan);
    const thresholdPayload = buildThresholdPayload(config.thresholds);
    const templateParams = buildPerfPayload({
      name: plan?.name,
      form: config.form,
      targetApis: config.targetApis,
      thresholds: config.thresholds,
      previousPlan: plan
    }).plan_schema.template_params;
    return {
      mode: useJMeterRunner ? 'real' : 'placeholder',
      real: useJMeterRunner,
      use_jmeter: useJMeterRunner,
      generate_html_report: generateHtmlReport,
      html_report: generateHtmlReport,
      virtual_users: templateParams.vus,
      thresholds: thresholdPayload,
      target_apis: config.targetApis,
      template_params: templateParams,
      timeout_seconds: Math.min(1800, Math.max(30, templateParams.duration_seconds + templateParams.ramp_up_seconds + 30))
    };
  };

  const handleRunPerfPlan = async (plan = activePlan) => {
    if (isRunning) return;
    setIsRunning(true);
    const controller = new AbortController();
    try {
      const target = await ensureBackendPerfPlan(plan);
      const jmeterStatus = runtimeDeps?.perf_runner?.jmeter;
      if (useJMeterRunner && jmeterStatus && !jmeterStatus.available) {
        showToast('JMeter CLI 未检测到，请安装 JMeter 或关闭真实 JMeter runner。', 'error');
        return;
      }
      const executionPayloadBody = buildExecutionPayload(target);
      const requestTimeoutMs = Math.min(1900, Math.max(90, executionPayloadBody.timeout_seconds + 30)) * 1000;
      setRunState({ status: 'running', planId: target.backendId, jobId: null, resultId: null, controller, message: '执行中' });
      const planResult = await apiPost(`/perf-plans/${target.backendId}/generate-plan`, {}, { timeoutMs: 15000, signal: controller.signal });
      const scriptResult = await apiPost(`/perf-plans/${target.backendId}/generate-script`, {}, { timeoutMs: 15000, signal: controller.signal });
      setGeneratedScriptContent(scriptResult?.script?.content || '');
      const executionPayload = await apiPost(`/perf-plans/${target.backendId}/execute`, executionPayloadBody, { timeoutMs: requestTimeoutMs, signal: controller.signal });
      const result = executionPayload.result || executionPayload;
      const jobId = executionPayload?.job?.id || executionPayload?.job_id || executionPayload?.jobId || null;
      const resultId = result?.id || executionPayload?.result_id || executionPayload?.resultId || null;
      setRunState({ status: 'completed', planId: target.backendId, jobId, resultId, controller: null, message: '执行完成' });
      const reportPayload = await apiPost(`/perf-plans/${target.backendId}/generate-report`, {}, { timeoutMs: 20000 }).catch(() => null);
      setPerfReportPayload(reportPayload ? { planId: target.backendId, payload: reportPayload } : null);
      setPerfExecution({ ...result, plan: planResult?.plan || target.raw, planId: target.backendId, jobId, resultId });
      setSelectedPlanIndex(Math.max(0, displayPlans.findIndex(item => item.backendId === target.backendId)));
      setViewMode('report');
      await loadPerformanceData({ silent: true, focusPlanId: target.backendId });
      showToast(`性能方案「${target.name}」已完成后端压测执行。`);
    } catch (error) {
      if (controller.signal.aborted) {
        setRunState(prev => ({ ...prev, status: 'aborted', controller: null, message: '已中止' }));
        showToast('性能压测已中止。', 'info');
      } else {
        setRunState(prev => ({ ...prev, status: 'failed', controller: null, message: error.message || String(error) }));
        showToast(`性能压测执行失败：${error.message || error}`, 'error');
      }
    } finally {
      setIsRunning(false);
    }
  };

  const handleGeneratePerfScript = async () => {
    if (isRunning) return;
    setIsRunning(true);
    try {
      const target = await ensureBackendPerfPlan(activePlan);
      await apiPost(`/perf-plans/${target.backendId}/generate-plan`, buildExecutionPayload(target), { timeoutMs: 15000 });
      const scriptResult = await apiPost(`/perf-plans/${target.backendId}/generate-script`, buildExecutionPayload(target), { timeoutMs: 15000 });
      setGeneratedScriptContent(scriptResult?.script?.content || '');
      await loadPerformanceData({ silent: true, focusPlanId: target.backendId });
      setViewMode('script-gen');
      showToast(`性能方案「${target.name}」已生成后端压测脚本。`);
    } catch (error) {
      showToast(`压测脚本生成失败：${error.message || error}`, 'error');
    } finally {
      setIsRunning(false);
    }
  };

  const handleRetest = () => {
    handleRunPerfPlan(activePlan);
  };

  const handleOpenReport = async (plan) => {
    setPerfExecution(plan.latestResult ? { ...plan.latestResult, planId: plan.backendId } : null);
    setPerfReportPayload(null);
    setViewMode('report');
    if (!plan?.backendId) return;
    try {
      const reportPayload = await apiPost(`/perf-plans/${plan.backendId}/generate-report`, {}, { timeoutMs: 20000 });
      setPerfReportPayload({ planId: plan.backendId, payload: reportPayload });
    } catch {
      setPerfReportPayload(null);
    }
  };

  const handleStopPerfExecution = async () => {
    const planId = runState.planId || perfExecution?.planId || activePlan?.backendId;
    if (!planId || !['running', 'stopping'].includes(runState.status)) {
      showToast('当前没有正在执行的性能任务。', 'info');
      return;
    }
    setRunState(prev => ({ ...prev, status: 'stopping', message: '停止中' }));
    const abortPayload = { job_id: runState.jobId, result_id: runState.resultId };
    let backendAborted = false;
    const abortEndpoints = [
      `/perf-plans/${planId}/abort`,
      runState.jobId ? `/jobs/${runState.jobId}/abort` : null,
      runState.resultId ? `/perf-results/${runState.resultId}/abort` : null
    ].filter(Boolean);

    for (const endpoint of abortEndpoints) {
      try {
        await apiPost(endpoint, abortPayload, { timeoutMs: 10000 });
        backendAborted = true;
        break;
      } catch {
        backendAborted = false;
      }
    }

    runState.controller?.abort?.();
    setRunState(prev => ({ ...prev, status: 'aborted', controller: null, message: backendAborted ? '后端已中止' : '本地已中止，后端中止接口不可用' }));
    showToast(backendAborted ? '性能任务已请求后端中止。' : '已本地中止请求；后端中止接口暂不可用。', backendAborted ? 'success' : 'warning');
  };

  const handleDownloadPerfScript = async () => {
    const planId = activePlan?.backendId;
    if (!planId) {
      showToast('当前没有可下载的后端 JMX 脚本。', 'info');
      return;
    }
    try {
      const payload = await apiGet(`/perf-plans/${planId}/download-script`, { timeoutMs: 15000 });
      if (!payload.available && !payload.content) {
        showToast('当前方案还没有 JMX 脚本，请先生成脚本。', 'info');
        return;
      }
      downloadTextFile({ filename: payload.filename, content: payload.content, mimeType: payload.mime_type || payload.mimeType });
    } catch (error) {
      showToast(`JMX 下载失败：${error.message || error}`, 'error');
    }
  };

  const handleExportPerfResult = async (format = 'json') => {
    const planId = perfExecution?.planId || activePlan?.backendId;
    const resultId = perfExecution?.id || activePlan?.latestResult?.id || 'latest';
    if (!planId) {
      showToast('当前没有可导出的后端性能结果。', 'info');
      return;
    }
    try {
      const payload = await apiGet(`/perf-plans/${planId}/results/${resultId}/download`, { params: { format }, timeoutMs: 15000 });
      downloadTextFile({ filename: payload.filename, content: payload.content, mimeType: payload.mime_type || payload.mimeType });
    } catch (error) {
      showToast(`性能结果导出失败：${error.message || error}`, 'error');
    }
  };

  const handleDownloadPerfArtifacts = async () => {
    const resultId = perfExecution?.id || activePlan?.latestResult?.id;
    if (!resultId) {
      showToast('当前没有可下载的性能执行 artifacts。', 'info');
      return;
    }
    try {
      const payload = await apiGet(`/perf-results/${resultId}/artifacts/download`, { timeoutMs: 15000 });
      downloadBase64File({
        filename: payload.filename,
        contentBase64: payload.content_base64,
        mimeType: payload.mime_type || payload.mimeType
      });
    } catch (error) {
      showToast(`性能 artifacts 下载失败：${error.message || error}`, 'error');
    }
  };

  const reportResult = perfExecution || activePlan?.latestResult;
  const reportSummary = reportResult?.summary_data || reportResult?.summaryData || {};
  const activePlanConfig = extractPlanConfig(activePlan);
  const activeThresholds = activePlan?.thresholds || activePlanConfig.thresholds || thresholds;
  const thresholdView = reportResult ? evaluateThresholds(reportResult, activeThresholds) : { status: 'warning', source: '暂无结果', items: [] };
  const hasReportPayloadForActivePlan =
    perfReportPayload &&
    activePlan?.backendId !== undefined &&
    activePlan?.backendId !== null &&
    perfReportPayload.planId === activePlan.backendId;
  const reportAdvice = hasReportPayloadForActivePlan ? extractReportAdvice(perfReportPayload.payload) : { risks: [], recommendations: [], content: '' };
  const reportContentExcerpt = typeof reportAdvice.content === 'string' ? reportAdvice.content.replace(/\s+/g, ' ').slice(0, 220) : '';
  const compareRows = resultSummaryRows(activePlan?.results || [], activeThresholds);
  const activeTrendPoints = (activePlan?.results?.length ? sortResultsAsc(activePlan.results).map(normalizeTrendPoint) : performanceTrend.points).filter(Boolean);
  const reportTimeline = Array.isArray(reportResult?.timeline_data || reportResult?.timelineData)
    ? (reportResult.timeline_data || reportResult.timelineData).map(normalizeTrendPoint)
    : [];
  const reportTrendPoints = reportTimeline.length > 1 ? reportTimeline : activeTrendPoints;
  const trendAvgPath = buildLinePath(reportTrendPoints, 'avg_ms', 520, 160, 20);
  const trendTpsPath = buildLinePath(reportTrendPoints, 'tps', 520, 160, 20);
  const sparklinePath = buildLinePath(activeTrendPoints, 'avg_ms', 400, 120, 10);
  const sparklineFillPath = sparklinePath ? `${sparklinePath} L 390 120 L 10 120 Z` : '';
  const compareP95Path = buildLinePath(compareRows.map(row => ({ p95_ms: row.p95 })), 'p95_ms', 1000, 160, 50);
  const compareTpsPath = buildLinePath(compareRows.map(row => ({ tps: row.tps })), 'tps', 1000, 160, 50);
  const thresholdBadge = thresholdView.status === 'pass'
    ? { text: '通过', className: 'border-emerald-500/20 text-emerald-600 bg-emerald-500/10' }
    : thresholdView.status === 'fail'
      ? { text: '失败', className: 'border-red-500/20 text-red-600 bg-red-500/10' }
      : { text: '告警', className: 'border-amber-500/20 text-amber-600 bg-amber-500/10' };
  const reportMetricsView = reportResult ? [
    { label: '并发 VUs', val: String(activePlan?.vus || metricValue(reportSummary, ['vus', 'virtual_users', 'threads'], 100)), sub: `执行状态: ${reportResult.status || 'completed'}` },
    { label: '平均响应时间 (RT)', val: formatMs(metricValue(reportSummary, ['avg_ms', 'average_ms', 'avg', 'mean_ms'])), sub: `95% RT: ${formatMs(metricValue(reportSummary, ['p95_ms', 'p95', 'rt95_ms', 'rt95']))}` },
    { label: '吞吐量 (TPS)', val: metricValue(reportSummary, ['tps', 'max_tps', 'throughput', 'rps']) ? formatNumber(metricValue(reportSummary, ['tps', 'max_tps', 'throughput', 'rps']), ' /s') : '--', sub: `持续时长: ${reportResult.duration || '--'}s` },
    { label: '异常率', val: formatRate(metricValue(reportSummary, ['error_rate', 'err_rate', 'errors_rate'], 0)), sub: `错误明细: ${(reportResult.error_details || reportResult.errorDetails || []).length} 条`, err: normalizePercentRate(metricValue(reportSummary, ['error_rate', 'err_rate', 'errors_rate'], 0)) > 0 }
  ] : reportMetrics;
  const transactionDetailsView = buildTransactionRows(reportResult, activePlanConfig.targetApis, activeThresholds);

  const renderPlanCreate = () => {
    return (
      <div className="space-y-4 text-left animate-[fadeIn_0.2s_ease-out] w-full">
        {/* 面包屑 */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <button 
              onClick={() => setViewMode('list')}
              className="flex items-center gap-1 px-2.5 py-1 rounded border border-[var(--border-color)] bg-[var(--bg-card)] text-[10px] text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 transition-colors shadow-sm cursor-pointer"
            >
              <ArrowLeft className="size-3" />
              <span>返回列表</span>
            </button>
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400 font-semibold">
              <span>性能测试</span>
              <span>/</span>
              <span className="text-[var(--text-primary)]">{editingPlanId ? '编辑 JMeter 参数' : '新建性能测试方案'}</span>
            </div>
          </div>
          <button 
            onClick={handleGeneratePerfScript}
            disabled={isRunning}
            className="px-3 py-1.5 rounded-lg accent-btn text-[11px] font-bold text-white cursor-pointer shadow-sm flex items-center gap-1 disabled:opacity-60"
          >
            <Sparkles className={`size-3.5 ${isRunning ? 'animate-spin' : ''}`} />
            <span>{isRunning ? '生成中...' : '智能生成压测脚本'}</span>
          </button>
        </div>

        {/* 表单内容 */}
        <div className="grid grid-cols-12 gap-4">
          {/* 左侧：表单参数 */}
          <div className="col-span-6 theme-card rounded-xl p-4 shadow-soft space-y-4 text-xs font-semibold text-slate-600">
            <h3 className="text-xs font-bold border-b border-[var(--border-color)] pb-2 mb-1 text-[var(--text-primary)]">压测方案基础配置</h3>
            <div className="space-y-1.5">
              <label className="block text-[var(--text-primary)]">方案名称</label>
              <input 
                type="text" 
                value={planName}
                onChange={(e) => setPlanName(e.target.value)}
                className="premium-input w-full px-3 py-2 text-[11px]"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="block text-[var(--text-primary)]">并发上限 (VUs)</label>
                <input 
                  type="number" 
                  min="1"
                  value={perfForm.threads}
                  onChange={(event) => updatePerfForm('threads', Number(event.target.value))}
                  className="premium-input w-full px-3 py-2 text-[11px]"
                />
              </div>
              <div className="space-y-1.5">
                <label className="block text-[var(--text-primary)]">持续时间</label>
                <select
                  value={perfForm.duration}
                  onChange={(event) => updatePerfForm('duration', event.target.value)}
                  className="premium-input w-full px-3 py-2 text-[11px]"
                >
                  <option value="5m">5 分钟</option>
                  <option value="10m">10 分钟</option>
                  <option value="30m">30 分钟</option>
                  <option value="1h">1 小时</option>
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="block text-[var(--text-primary)]">Ramp Up</label>
                <input
                  type="text"
                  value={perfForm.rampUp}
                  onChange={(event) => updatePerfForm('rampUp', event.target.value)}
                  className="premium-input w-full px-3 py-2 text-[11px]"
                  placeholder="例如 30s / 1m"
                />
              </div>
              <div className="space-y-1.5">
                <label className="block text-[var(--text-primary)]">Loops</label>
                <input
                  type="number"
                  min="1"
                  value={perfForm.loops}
                  onChange={(event) => updatePerfForm('loops', Number(event.target.value))}
                  className="premium-input w-full px-3 py-2 text-[11px]"
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <label className="block text-[var(--text-primary)]">加压模式</label>
              <div className="grid grid-cols-3 gap-2">
                {['阶梯加压 (Ramping)', '恒定并发 (Constant)', '骤增压测 (Spike)'].map((mode, i) => (
                  <label 
                    key={i} 
                    onClick={() => {
                      setPressureMode(i);
                      updatePerfForm('threads', PRESSURE_VUS[i]);
                    }}
                    style={pressureMode === i ? { borderColor: 'var(--accent-color)', backgroundColor: 'var(--accent-glow)' } : {}}
                    className={`p-2.5 border rounded-lg cursor-pointer flex flex-col justify-between items-center text-center transition-all ${
                      pressureMode === i ? '' : 'border-[var(--border-color)] hover:bg-[var(--border-color)]/30'
                    }`}
                  >
                    <input type="radio" name="pressure-mode" checked={pressureMode === i} readOnly className="size-3" style={{ accentColor: 'var(--accent-color)' }} />
                    <span className="text-[9px] font-bold mt-1 text-[var(--text-primary)]">{mode}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-4 gap-2">
              {[
                ['p95', 'P95(ms)'],
                ['avg', 'Avg(ms)'],
                ['error_rate', 'Err(%)'],
                ['tps', 'TPS下限']
              ].map(([key, label]) => (
                <div key={key} className="space-y-1.5">
                  <label className="block text-[var(--text-primary)]">{label}</label>
                  <input
                    type="number"
                    min="0"
                    value={thresholds[key]}
                    onChange={(event) => updateThreshold(key, Number(event.target.value))}
                    className="premium-input w-full px-2 py-2 text-[11px]"
                  />
                </div>
              ))}
            </div>
          </div>

          {/* 右侧：接口与权重 */}
          <div className="col-span-6 theme-card rounded-xl p-4 shadow-soft flex flex-col justify-between">
            <div>
              <h3 className="text-xs font-bold border-b border-[var(--border-color)] pb-2 mb-3 flex justify-between items-center text-slate-800">
                  <span>压测接口列表与权重配置</span>
                  <span className="text-[9px] text-slate-400 font-normal">总权重应等于 100%</span>
                </h3>
              <div className="space-y-2.5 max-h-[270px] overflow-y-auto pr-1">
                {targetApis.map((api, idx) => (
                  <div key={idx} className="flex gap-2 items-center">
                    <select
                      value={api.method}
                      onChange={(event) => updateTargetApi(idx, { method: event.target.value })}
                      className={`premium-input w-[70px] px-1 py-1.5 text-[9px] font-bold ${api.method === 'POST' ? 'text-blue-600' : 'text-emerald-600'}`}
                    >
                      {['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((method) => (
                        <option key={method} value={method}>{method}</option>
                      ))}
                    </select>
                    <input 
                      type="text" 
                      value={api.url} 
                      onChange={(e) => updateTargetApi(idx, { url: e.target.value })}
                      className="premium-input flex-1 px-2 py-1.5 font-mono text-[9px]"
                    />
                    <div className="flex items-center gap-1 shrink-0">
                      <input 
                        type="number" 
                        value={api.weight} 
                        onChange={(e) => updateTargetApi(idx, { weight: Number(e.target.value) })}
                        className="premium-input w-10 px-1 py-1 text-[10px] text-center font-bold"
                      />
                      <span className="text-[9px] text-slate-400 font-bold">%</span>
                    </div>
                    <button
                      onClick={() => setTargetApis(prev => prev.filter((_, itemIndex) => itemIndex !== idx))}
                      className="px-1.5 py-1 rounded border border-red-500/20 text-red-500 text-[9px] font-bold hover:bg-red-500/10"
                    >
                      删
                    </button>
                  </div>
                ))}
              </div>
            </div>

            <button 
              onClick={() => {
                const newApis = [...targetApis, { method: 'GET', url: '/api/v1/new-endpoint', weight: 10 }];
                setTargetApis(newApis);
              }}
              className="w-full py-1.5 border border-dashed border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--border-color)]/30 text-[9.5px] rounded-lg cursor-pointer text-center flex items-center justify-center gap-1 mt-4 transition-colors"
            >
              <Plus className="size-3" />
              <span>新增压测API接口</span>
            </button>
          </div>
        </div>
      </div>
    );
  };

  const renderScriptGen = () => {
    const generatedScript = generatedScriptContent || `import http from 'k6/http';\nimport { check, sleep } from 'k6';\n\nexport const options = {\n  stages: [\n    { duration: '1m', target: 200 }, // ramp up\n    { duration: '3m', target: 500 }, // steady state\n    { duration: '1m', target: 0 },   // ramp down\n  ],\n};\n\nexport default function () {\n  const res = http.post('https://gateway-test.domain.com/api/v1/auth/login', \n    JSON.stringify({ username: 'user_test', password: 'password_123' }),\n    { headers: { 'Content-Type': 'application/json' } }\n  );\n\n  check(res, {\n    'status is 200': (r) => r.status === 200,\n    'login token exists': (r) => r.json().data.token !== undefined,\n  });\n\n  sleep(1);\n}`;

    return (
      <div className="space-y-4 text-left animate-[fadeIn_0.2s_ease-out] w-full">
        {/* 面包屑 */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <button 
              onClick={() => setViewMode('plan-create')}
              className="flex items-center gap-1 px-2.5 py-1 rounded border border-[var(--border-color)] bg-[var(--bg-card)] text-[10px] text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 transition-colors shadow-sm cursor-pointer"
            >
              <ArrowLeft className="size-3" />
              <span>上一步</span>
            </button>
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400 font-semibold">
              <span>性能测试</span>
              <span>/</span>
              <span>新建性能方案</span>
              <span>/</span>
              <span className="text-[var(--text-primary)]">压测脚本自动生成</span>
            </div>
          </div>
          <button 
            onClick={() => handleRunPerfPlan(activePlan)}
            disabled={isRunning}
            className="px-3 py-1.5 rounded-lg accent-btn text-[11px] font-bold text-white cursor-pointer shadow-sm disabled:opacity-60"
          >
            {isRunning ? '执行中...' : '保存方案并立即执行'}
          </button>
        </div>

        {/* 脚本生成双栏 */}
        <div className="grid grid-cols-12 gap-4">
          {/* 左侧：动态参数与映射 */}
          <div className="col-span-4 theme-card rounded-xl p-4 shadow-soft space-y-4 text-xs font-semibold text-slate-600">
            <h3 className="text-xs font-bold border-b border-[var(--border-color)] pb-2 text-slate-800">智能参数化映射配置</h3>
            <div className="space-y-3">
              <div className="p-3 bg-purple-500/5 border border-purple-500/10 rounded-xl space-y-1.5">
                <div className="font-bold text-purple-700 flex items-center gap-1">
                  <Sparkles className="size-3.5" />
                  <span>动态 Token 自动绑定</span>
                </div>
                <p className="text-[8px] text-slate-400 leading-relaxed">
                  AI 检查到 <code className="bg-black/5 dark:bg-white/10 px-1 py-0.5 rounded text-[7.5px]">/login</code> 接口，已自动将返回体内的 <code className="bg-black/5 dark:bg-white/10 px-1 py-0.5 rounded text-[7.5px]">data.token</code> 绑定至全局变量，传递给后续请求的 Header。
                </p>
              </div>

              <div className="space-y-1.5">
                <label className="block text-slate-700">数据源参数文件 (CSV)</label>
                <div className="border border-dashed border-slate-200 rounded-lg p-3 bg-slate-50/50 flex flex-col items-center justify-center text-center text-[9px] text-slate-400">
                  <span className="font-bold text-slate-600">user_csv_pool.csv</span>
                  <span className="opacity-75 mt-0.5">内含 10,000 条测试账号与密码映射</span>
                  <span className="underline cursor-pointer text-indigo-500 mt-1 font-bold">重新上传参数池</span>
                </div>
              </div>
            </div>
          </div>

          {/* 右侧：代码编辑器 */}
          <div className="col-span-8 mac-terminal p-4 flex flex-col font-mono text-[9px] text-left">
            <div className="flex justify-between items-center border-b border-white/10 pb-2 mb-3 shrink-0">
              <span className="font-bold text-[#8be9fd]">AI Generated k6 loadtest.js</span>
              <button 
                onClick={() => {
                  navigator.clipboard.writeText(generatedScript);
                  window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '压测代码已复制到剪贴板！', type: 'success' } }));
                }}
                className="px-2 py-0.5 bg-white/10 hover:bg-white/20 text-[#f8f8f2] rounded border border-white/15 text-[8.5px] cursor-pointer"
              >
                复制代码
              </button>
            </div>
            <pre className="overflow-y-auto max-h-[300px] leading-normal select-all">{generatedScript}</pre>
          </div>
        </div>
      </div>
    );
  };

  const renderHistoryCompare = () => {
    return (
      <div className="space-y-4 text-left animate-[fadeIn_0.2s_ease-out] w-full">
        {/* 面包屑 */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <button 
              onClick={() => setViewMode('list')}
              className="flex items-center gap-1 px-2.5 py-1 rounded border border-[var(--border-color)] bg-[var(--bg-card)] text-[10px] text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 transition-colors shadow-sm cursor-pointer"
            >
              <ArrowLeft className="size-3" />
              <span>返回列表</span>
            </button>
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400 font-semibold">
              <span>性能测试</span>
              <span>/</span>
              <span className="text-[var(--text-primary)]">性能测试历史比对</span>
            </div>
          </div>
          <button 
            onClick={() => window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '多维性能比对报告已成功导出。', type: 'success' } }))}
            className="px-3 py-1.5 rounded-lg accent-btn text-[11px] font-bold text-white cursor-pointer shadow-sm"
          >
            导出比对报告
          </button>
        </div>

        {/* 多曲线重合交叉比对 (SVG) */}
        <div className="theme-card rounded-xl p-4 shadow-soft">
          <h3 className="text-xs font-bold mb-3 border-b border-[var(--border-color)] pb-2 flex justify-between items-center text-slate-800">
            <span>吞吐量 (TPS) 与响应时间 (RT) 多曲线交叉比对</span>
            <div className="flex gap-4 text-[9px]">
              <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-blue-500"></span> P95 RT</span>
              <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-emerald-500"></span> TPS</span>
              <span className="text-slate-400">{compareRows.length ? `${compareRows.length} 次结果` : '暂无结果'}</span>
            </div>
          </h3>
          <div className="h-44 w-full relative mt-2">
            <svg className="w-full h-full" viewBox="0 0 1000 160" preserveAspectRatio="none">
              {/* 网格线 */}
              <line x1="0" y1="20" x2="1000" y2="20" stroke="var(--border-color)" strokeWidth="1" strokeDasharray="5,5" />
              <line x1="0" y1="80" x2="1000" y2="80" stroke="var(--border-color)" strokeWidth="1" strokeDasharray="5,5" />
              <line x1="0" y1="140" x2="1000" y2="140" stroke="var(--border-color)" strokeWidth="1" strokeDasharray="5,5" />
              {compareP95Path && <path d={compareP95Path} fill="none" stroke="#06b6d4" strokeWidth="2.4" opacity="0.9" className="path-drawn" />}
              {compareTpsPath && <path d={compareTpsPath} fill="none" stroke="#10b981" strokeWidth="2.2" strokeDasharray="4,2" className="path-drawn" />}
            </svg>
            <div className="absolute top-2 left-2 text-[8px] text-slate-400 bg-white/80 dark:bg-slate-900/80 px-1 py-0.5 rounded border border-slate-100 font-bold">
              {compareRows.length ? `基线：${compareRows.find(row => row.status === '基线')?.build || compareRows[0]?.build}，当前：${compareRows[compareRows.length - 1]?.build}` : '选中方案暂无历史结果'}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-12 gap-4">
          {/* 左侧：比对明细网格 */}
          <div className="col-span-8 theme-card rounded-xl p-4 shadow-soft">
            <h3 className="text-xs font-bold mb-3 border-b border-[var(--border-color)] pb-2 text-slate-800">多轮压测核心指标比对网格</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-[10px] text-left border-collapse">
                <thead>
                  <tr className="text-slate-400 font-bold border-b border-slate-50">
                    <th className="py-2 px-1">压测构建</th>
                    <th className="py-2 px-1 text-center">并发 VUs</th>
                    <th className="py-2 px-1 text-center">平均 RT</th>
                    <th className="py-2 px-1 text-center">95% RT</th>
                    <th className="py-2 px-1 text-center">峰值 TPS</th>
                    <th className="py-2 px-1 text-center">异常报错率</th>
                    <th className="py-2 px-1 text-center">CPU 峰值</th>
                    <th className="py-2 px-1 text-center">内存峰值</th>
                    <th className="py-2 px-1 text-center">评估结论</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50/50 text-slate-600 font-medium">
                  {compareRows.map((row, idx) => (
                    <tr key={idx} className="hover:bg-slate-50/30">
                      <td className="py-2.5 px-1 font-bold text-slate-800 font-mono">{row.build}</td>
                      <td className="py-2.5 px-1 text-center font-bold text-slate-700">{row.vus}</td>
                      <td className="py-2.5 px-1 text-center">{formatMs(row.avg)}<div className="text-[7px] text-slate-400">{row.avgDelta}</div></td>
                      <td className="py-2.5 px-1 text-center font-semibold">{formatMs(row.p95)}<div className="text-[7px] text-slate-400">{row.p95Delta}</div></td>
                      <td className="py-2.5 px-1 text-center text-indigo-600 font-bold">{formatNumber(row.tps, '/s')}<div className="text-[7px] text-slate-400">{row.tpsDelta}</div></td>
                      <td className="py-2.5 px-1 text-center text-red-500 font-bold">{formatRate(row.errorRate)}</td>
                      <td className="py-2.5 px-1 text-center font-mono">{row.cpu === null ? '--' : `${row.cpu}%`}</td>
                      <td className="py-2.5 px-1 text-center font-mono">{row.mem === null ? '--' : `${row.mem}%`}</td>
                      <td className="py-2.5 px-1 text-center">
                        <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold ${
                          row.status === '回归' ? 'bg-red-50 text-red-600' : row.status === '告警' ? 'bg-amber-50 text-amber-600' : 'bg-emerald-50 text-emerald-600'
                        }`}>
                          {row.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {!compareRows.length && (
                    <tr>
                      <td colSpan={9} className="py-6 text-center text-slate-400 font-semibold">当前方案还没有可比对的执行结果。</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* 右侧：AI 调优瓶颈诊断 */}
          <div className="col-span-4 theme-card rounded-xl p-4 shadow-soft text-left flex flex-col justify-between ai-laser-healing-grid">
            <div className="relative z-10">
              <h3 className="text-xs font-bold border-b border-[var(--border-color)] pb-2 mb-2 flex items-center gap-1 text-slate-800">
                <Sparkles className="size-4 text-purple-600 animate-pulse shrink-0" />
                <span>AI 拐点与瓶颈诊断建议</span>
              </h3>
              <p className="text-[8px] text-slate-400 mb-3">基于选中方案的真实 PerfResult 历史结果提炼：</p>
              
              <div className="space-y-3 text-[9px] font-semibold text-slate-600 font-sans">
                <div className="p-2 border border-purple-100 bg-purple-50/20 rounded-lg">
                  <span className="font-bold text-purple-700 block">性能拐点标定</span>
                  <p className="text-slate-400 text-[8px] leading-relaxed mt-0.5">
                    {compareRows.some(row => row.isRegression)
                      ? '检测到当前结果相对基线存在 P95、错误率或 TPS 回退，请优先回看本轮变更和压测环境差异。'
                      : compareRows.length
                        ? '当前历史结果未出现明显回归，建议继续保留基线并观察后续版本趋势。'
                        : '暂无历史结果，执行至少两次后可自动形成基线与当前回归判断。'}
                  </p>
                </div>

                <div className="p-2 border border-slate-100 bg-slate-50/30 rounded-lg">
                  <span className="font-bold text-slate-700 block">硬件利用率评估</span>
                  <p className="text-slate-400 text-[8px] leading-relaxed mt-0.5">
                    {compareRows.length
                      ? `当前最新结果阈值状态为「${compareRows[compareRows.length - 1]?.status || '未知'}」，P95 ${formatMs(compareRows[compareRows.length - 1]?.p95)}，错误率 ${formatRate(compareRows[compareRows.length - 1]?.errorRate)}。`
                      : '尚无 CPU / 内存峰值数据，等待后端结果补充后展示。'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  if (viewMode === 'plan-create') {
    return renderPlanCreate();
  }

  if (viewMode === 'script-gen') {
    return renderScriptGen();
  }

  if (viewMode === 'history-compare') {
    return renderHistoryCompare();
  }

  return (
    <div className="space-y-4 text-left w-full">
      
      {viewMode === 'list' ? (
        // ==========================================================================
        // 渲染：19-性能测试方案列表页
        // ==========================================================================
        <div className="space-y-4 animate-[fadeIn_0.2s_ease-out]">
          <div className="flex justify-between items-start">
            <div className="text-left">
              <h1 className="text-base font-bold text-[var(--text-primary)]">性能测试</h1>
              <p className="text-[11px] text-[var(--text-secondary)] mt-1">{perfStatus.loading ? '正在同步后端性能方案...' : perfStatus.message}</p>
            </div>
            <div className="flex items-center gap-2">
              <button 
                onClick={() => setViewMode('history-compare')}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[11px] font-bold text-[var(--text-primary)] cursor-pointer transition-colors"
              >
                <span>性能历史比对</span>
              </button>
              <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[11px] font-bold text-[var(--text-primary)] cursor-pointer transition-colors">
                <span>运行队列 ({['running', 'stopping'].includes(runState.status) ? 1 : 0})</span>
              </button>
              <div className={`px-2.5 py-1.5 rounded-lg border text-[9px] font-bold ${
                runtimeDeps?.perf_runner?.jmeter?.available
                  ? 'border-emerald-500/20 text-emerald-600 bg-emerald-500/10'
                  : 'border-amber-500/20 text-amber-600 bg-amber-500/10'
              }`}>
                JMeter: {runtimeDeps?.perf_runner?.jmeter?.status || 'unknown'}
              </div>
              <label className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] text-[11px] font-bold text-[var(--text-primary)] cursor-pointer">
                <input
                  type="checkbox"
                  checked={useJMeterRunner}
                  onChange={(event) => setUseJMeterRunner(event.target.checked)}
                  className="size-3"
                />
                <span>真实 JMeter</span>
              </label>
              <label className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] text-[11px] font-bold text-[var(--text-primary)] cursor-pointer">
                <input
                  type="checkbox"
                  checked={generateHtmlReport}
                  onChange={(event) => setGenerateHtmlReport(event.target.checked)}
                  className="size-3"
                />
                <span>HTML 报告</span>
              </label>
              <button 
                onClick={openCreatePlan}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg glow-button-neon text-[11px] font-bold text-white cursor-pointer"
              >
                <Plus className="size-3.5" />
                <span>新建性能方案</span>
              </button>
            </div>
          </div>

          {/* 指标面板 */}
          <div className="grid grid-cols-4 gap-3.5">
            {displayStats.map((item, idx) => (
              <div key={idx} className="chroma-glass rounded-xl p-3.5 shadow-soft flex items-center justify-between">
                <div className="text-left">
                  <span className="text-[10px] text-[var(--text-secondary)] font-semibold">{item.label}</span>
                  <div className="text-xl font-bold mt-1 text-[var(--text-primary)] neon-pulse-number">{item.val}</div>
                  <div className="text-[9px] text-[var(--text-secondary)] mt-1"><span className="text-emerald-500 font-semibold">{item.change}</span></div>
                </div>
                {item.hasChart ? (
                  <div className="size-11 shrink-0 relative sonar-ripple-container">
                    <div className="sonar-ripple-circle"></div>
                    <div className="sonar-ripple-circle sonar-ripple-circle-delay"></div>
                    <svg className="w-full h-full transform -rotate-90 relative z-10" viewBox="0 0 36 36">
                      <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--border-color)" strokeWidth="2.8" />
                      <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--accent-color)" strokeWidth="2.8" strokeDasharray="85 15" />
                      <path d="M18,18 L18,2 A16,16 0 0,1 30,10 Z" fill="var(--accent-glow)" className="radar-sweeper-beam" />
                    </svg>
                    <div className="absolute inset-0 flex items-center justify-center text-[8px] font-bold text-[var(--text-primary)] z-10">
                      <AnimatedNumber value={item.chartValue ?? 85} />%
                    </div>
                  </div>
                ) : (
                  <div className={`p-2 rounded-lg ${item.color}`}>
                    <item.icon className="size-4" />
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* 7:5 选中联动布局 (等高 items-stretch 消除高度差及多余空白) */}
          <div className="grid grid-cols-12 gap-5 w-full items-stretch min-h-[380px]">
            {/* 左侧 7 份：方案列表 */}
            <div className="col-span-7 h-full flex flex-col">
              <div className="theme-card rounded-xl p-4 shadow-soft flex-1 flex flex-col justify-between h-full">
                <div>
                  <div className="flex items-center gap-2 mb-3.5 border-b border-[var(--border-color)] pb-3">
                    <div className="flex-1 flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--border-color)]/30">
                      <Search className="size-3.5 text-[var(--text-secondary)] shrink-0" />
                      <input type="text" placeholder="搜索方案名称、关联需求" className="bg-transparent border-none text-[10px] focus:outline-none w-full text-[var(--text-primary)]" />
                    </div>
                    <div className="flex items-center gap-1 text-[10px] text-[var(--text-secondary)] border border-[var(--border-color)] rounded px-2.5 py-1.5 bg-[var(--border-color)]/30 hover:bg-[var(--border-color)]/60 cursor-pointer">
                      <span>运行状态</span>
                      <ChevronDown className="size-3 text-slate-400" />
                    </div>
                  </div>

                  <div className="overflow-x-auto w-full">
                    <table className="w-full text-[11px] text-left border-collapse">
                      <thead>
                        <tr className="text-[var(--text-secondary)] font-bold border-b border-[var(--border-color)]">
                          <th className="py-2.5 px-2 w-[30px]"><input type="checkbox" className="rounded" /></th>
                          <th className="py-2.5 px-2">方案名称</th>
                          <th className="py-2.5 px-2">关联需求</th>
                          <th className="py-2.5 px-2 text-center">目标并发 VUs</th>
                          <th className="py-2.5 px-2">协议</th>
                          <th className="py-2.5 px-2 text-center">状态</th>
                          <th className="py-2.5 px-2 text-center">操作</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[var(--border-color)] text-[var(--text-secondary)] font-medium">
                        {displayPlans.map((plan, idx) => {
                          const isSelected = selectedPlanIndex === idx;
                          return (
                            <tr 
                              key={plan.backendId || idx} 
                              onClick={() => setSelectedPlanIndex(idx)}
                              className={`cursor-pointer transition-colors duration-150 ${
                                isSelected 
                                  ? 'bg-[var(--accent-glow)] border-l-2 border-l-[var(--accent-color)]' 
                                  : 'hover:bg-[var(--border-color)]/30'
                              }`}
                            >
                              <td className="py-3 px-2" onClick={(e) => e.stopPropagation()}>
                                <input type="checkbox" className="rounded" />
                              </td>
                              <td className="py-3 px-2">
                                <div className="flex items-center gap-2">
                                  <Gauge className={`size-3.5 shrink-0 ${isSelected ? 'text-[var(--accent-color)]' : 'text-slate-400'}`} />
                                  <span className="font-bold text-[var(--text-primary)]">{plan.name}</span>
                                </div>
                              </td>
                              <td className="py-3 px-2 font-bold text-[var(--accent-color)] hover:underline">{plan.ref}</td>
                              <td className="py-3 px-2 text-center font-bold text-[var(--text-primary)]">{plan.vus}</td>
                              <td className="py-3 px-2">
                                <span className="px-1.5 py-0.5 bg-[var(--border-color)]/50 rounded text-[9px] font-bold">
                                  {plan.type.split(' / ')[0]}
                                </span>
                              </td>
                              <td className="py-3 px-2 text-center">
                                <div className="flex items-center justify-center gap-1 text-[10px]">
                                  <span className={`size-1.5 rounded-full shrink-0 ${plan.statusColor}`}></span>
                                  <span>{plan.status}</span>
                                </div>
                              </td>
                              <td className="py-3 px-2 text-center" onClick={(e) => e.stopPropagation()}>
                                <div className="flex items-center justify-center gap-2 text-[var(--accent-color)] font-bold text-[10px]">
                                  <span className="hover:underline cursor-pointer" onClick={() => handleOpenReport(plan)}>报告</span>
                                  <span className="hover:underline cursor-pointer" onClick={() => openEditPlan(plan)}>编辑</span>
                                  <span className="hover:underline cursor-pointer" onClick={() => handleRunPerfPlan(plan)}>{isRunning && isSelected ? '执行中...' : '执行'}</span>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>

            {/* 右侧 5 份：压测集群遥测与负载雷达 (等高 3D 浮动卡片) */}
            <div className="col-span-5 h-full flex flex-col">
              <style>{`
                @keyframes telemetryPulse {
                  0%, 100% {
                    transform: scale(1);
                    opacity: 0.8;
                    filter: drop-shadow(0 0 2px currentColor);
                  }
                  50% {
                    transform: scale(1.18);
                    opacity: 1;
                    filter: drop-shadow(0 0 8px currentColor);
                  }
                }
                .telemetry-indicator-pulse {
                  animation: telemetryPulse 1.8s infinite ease-in-out;
                }
              `}</style>
              <TiltCard className="theme-card laser-chase-border rounded-xl p-4 shadow-soft text-left flex-1 flex flex-col justify-between h-full min-h-[380px]">
                <div className="space-y-4" style={{ transform: 'translateZ(20px)', transformStyle: 'preserve-3d' }}>
                  <div className="flex justify-between items-center border-b border-[var(--border-color)] pb-2.5">
                    <div className="flex items-center gap-1.5">
                      <Sparkles className="size-4 text-purple-500 animate-pulse" />
                      <span className="text-xs font-bold text-[var(--text-primary)] cyber-glitch-text cursor-pointer transition-all">集群遥测与响应雷达</span>
                    </div>
                    <span className="text-[8.5px] font-mono text-[var(--accent-color)] bg-[var(--accent-glow)] px-1.5 py-0.5 rounded">实时遥测</span>
                  </div>

                  <div>
                    <div className="text-[9px] text-[var(--text-secondary)] font-bold mb-1">当前监控方案:</div>
                    <div className="text-[10px] font-extrabold text-[var(--text-primary)] truncate">
                      {activePlan?.name}
                    </div>
                  </div>

                  {/* 3 个 Agent 微型卡片网格重构 */}
                  <div className="space-y-2">
                    <span className="text-[9px] text-[var(--text-secondary)] font-bold block mb-1">压测执行节点 (Injectors)</span>
                    <div className="grid grid-cols-3 gap-2">
                      {(agentLoads[selectedPlanIndex] || agentLoads[0]).map((agent, idx) => {
                        const isHighLoad = agent.status === 'high-load';
                        const isIdle = agent.status === 'idle';
                        const statusColor = isHighLoad 
                          ? 'text-red-500' 
                          : isIdle 
                            ? 'text-slate-400' 
                            : 'text-emerald-500';
                        const cityCode = agent.name.includes('北京') ? 'PEK' : agent.name.includes('深圳') ? 'SZX' : 'SHA';
                        
                        return (
                          <div 
                            key={idx} 
                            className={`p-2 border rounded-xl flex flex-col justify-between min-h-[90px] transition-all duration-300 ${
                              isHighLoad 
                                ? 'cyber-glitch-panel' 
                                : 'border-[var(--border-color)] bg-[var(--bg-app)] hover:border-[var(--accent-color)]/25 hover:shadow-md hover:scale-[1.02] shadow-sm'
                            }`}
                            style={{ transform: `translateZ(${10 + idx * 5}px)` }}
                          >
                            <div className="flex items-center justify-between gap-1 border-b border-[var(--border-color)] pb-1 mb-1">
                              <div className="flex flex-col text-left">
                                <span className="text-[8px] font-bold text-[var(--text-primary)] truncate">{agent.name.split(' ')[0]}</span>
                                <span className="text-[6.5px] text-[var(--text-secondary)] font-mono opacity-65">📍 {cityCode}</span>
                              </div>
                              <span className={`size-1.5 rounded-full telemetry-indicator-pulse ${statusColor}`} style={{ color: isHighLoad ? '#ef4444' : isIdle ? '#94a3b8' : '#10b981' }} />
                            </div>
                            
                            <div className="space-y-1.5">
                              {/* CPU 进度条 */}
                              <div className="space-y-0.5">
                                <div className="flex justify-between text-[7px] text-[var(--text-secondary)]">
                                  <span>CPU</span>
                                  <span className={`font-bold font-mono ${isHighLoad ? 'text-red-500' : 'text-[var(--text-primary)]'}`}>{agent.cpu}%</span>
                                </div>
                                <div className="h-1 w-full bg-[var(--border-color)] rounded-full overflow-hidden">
                                  <div 
                                    className={`h-full rounded-full transition-all duration-500 ${
                                      isHighLoad 
                                        ? 'bg-gradient-to-r from-red-500 to-rose-600' 
                                        : isIdle 
                                          ? 'bg-slate-400' 
                                          : 'bg-gradient-to-r from-emerald-400 to-teal-500'
                                    }`}
                                    style={{ width: `${agent.cpu}%` }}
                                  />
                                </div>
                              </div>

                              {/* MEM 进度条 */}
                              <div className="space-y-0.5">
                                <div className="flex justify-between text-[7px] text-[var(--text-secondary)]">
                                  <span>MEM</span>
                                  <span className="font-bold font-mono text-[var(--text-primary)]">{agent.mem}%</span>
                                </div>
                                <div className="h-1 w-full bg-[var(--border-color)] rounded-full overflow-hidden">
                                  <div 
                                    className={`h-full rounded-full transition-all duration-500 ${
                                      isHighLoad 
                                        ? 'bg-gradient-to-r from-orange-400 to-red-500' 
                                        : isIdle 
                                          ? 'bg-slate-400' 
                                          : 'bg-gradient-to-r from-blue-400 to-indigo-500'
                                    }`}
                                    style={{ width: `${agent.mem}%` }}
                                  />
                                </div>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* 响应时间波动曲线 Sparkline */}
                  <div className="space-y-2" style={{ transform: 'translateZ(10px)' }}>
                    <div className="flex justify-between items-center text-[9px] text-[var(--text-secondary)] font-bold">
                      <span>RT 响应延迟波动走势 (Sparkline)</span>
                      <span className="text-[8px] font-mono text-[var(--accent-color)]">
                        {activeTrendPoints.length ? `Avg: ${formatMs(activeTrendPoints[activeTrendPoints.length - 1]?.avg_ms)}` : '未执行'}
                      </span>
                    </div>
                    <div className="h-20 w-full border border-[var(--border-color)] bg-[var(--bg-app)] rounded-xl overflow-hidden relative flex items-center justify-center">
                      {!sparklinePath ? (
                        <span className="text-[8.5px] text-[var(--text-secondary)] opacity-60">暂无趋势结果，执行后自动聚合。</span>
                      ) : (
                        <svg className="w-full h-full p-1" viewBox="0 0 400 120" preserveAspectRatio="none">
                          <defs>
                            <linearGradient id="sparklineGrad" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor="var(--accent-color)" stopOpacity="0.25" />
                              <stop offset="100%" stopColor="var(--accent-color)" stopOpacity="0.0" />
                            </linearGradient>
                          </defs>
                          {/* 网格参考线 */}
                          <line x1="0" y1="30" x2="400" y2="30" stroke="var(--border-color)" strokeWidth="0.5" strokeDasharray="3,3" />
                          <line x1="0" y1="60" x2="400" y2="60" stroke="var(--border-color)" strokeWidth="0.5" strokeDasharray="3,3" />
                          <line x1="0" y1="90" x2="400" y2="90" stroke="var(--border-color)" strokeWidth="0.5" strokeDasharray="3,3" />
                          
                          {/* 阴影渐变区域 */}
                          <path 
                            key={`fill-${selectedPlanIndex}`}
                            d={sparklineFillPath}
                            fill="url(#sparklineGrad)"
                          />
                          {/* 波动曲线 */}
                          <path 
                            key={`path-${selectedPlanIndex}`}
                            d={sparklinePath}
                            fill="none" 
                            stroke="var(--accent-color)" 
                            strokeWidth="2" 
                            strokeLinecap="round"
                            className="path-drawn"
                          />
                        </svg>
                      )}
                    </div>
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-[var(--border-color)]" style={{ transform: 'translateZ(25px)' }}>
                  <button 
                    onClick={() => handleOpenReport(activePlan)}
                    className="w-full py-1.5 bg-[var(--bg-card)] border border-[var(--border-color)] hover:bg-[var(--border-color)]/50 text-[9.5px] font-bold text-[var(--text-primary)] rounded-lg cursor-pointer transition-colors"
                  >
                    调取节点实时日志与指标详情
                  </button>
                </div>
              </TiltCard>
            </div>
          </div>
        </div>
      ) : (
        // ==========================================================================
        // 渲染：20-性能测试执行报告工作台
        // ==========================================================================
        <div className="space-y-4 text-left">
          {/* 返回 */}
          <div className="flex justify-between items-center">
            <button 
              onClick={() => setViewMode('list')}
              className="flex items-center gap-1 px-2.5 py-1 rounded border border-[var(--border-color)] bg-[var(--bg-card)] text-[10px] text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 transition-colors shadow-sm cursor-pointer"
            >
              <ArrowLeft className="size-3" />
              <span>返回列表</span>
            </button>
            
            <div className="flex items-center gap-2">
              <button 
                onClick={handleRetest}
                disabled={isRunning}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[11px] font-bold text-[var(--text-primary)] cursor-pointer disabled:opacity-75 transition-colors"
              >
                <RotateCw className={`size-3.5 ${isRunning ? 'animate-spin' : ''}`} />
                <span>{isRunning ? '压测中...' : '重新跑压测'}</span>
              </button>
              <button
                onClick={handleDownloadPerfScript}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[11px] font-bold text-[var(--text-primary)] cursor-pointer transition-colors"
              >
                <Download className="size-3.5" />
                <span>下载 JMX</span>
              </button>
              <button
                onClick={() => handleExportPerfResult('json')}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[11px] font-bold text-[var(--text-primary)] cursor-pointer transition-colors"
              >
                <Download className="size-3.5" />
                <span>JSON</span>
              </button>
              <button
                onClick={() => handleExportPerfResult('html')}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[11px] font-bold text-[var(--text-primary)] cursor-pointer transition-colors"
              >
                <Download className="size-3.5" />
                <span>HTML</span>
              </button>
              <button
                onClick={handleDownloadPerfArtifacts}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[11px] font-bold text-[var(--text-primary)] cursor-pointer transition-colors"
              >
                <Download className="size-3.5" />
                <span>Artifacts</span>
              </button>
              <button
                onClick={handleStopPerfExecution}
                disabled={!['running', 'stopping'].includes(runState.status)}
                className="px-3 py-1.5 rounded-lg border border-red-500/30 hover:bg-red-500/10 text-red-500 text-[11px] font-bold cursor-pointer transition-colors bg-[var(--bg-card)] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {runState.status === 'stopping' ? '停止中...' : runState.status === 'aborted' ? '已中止' : '停止执行'}
              </button>
            </div>
          </div>

          <div className="theme-card rounded-xl p-4 shadow-soft">
            <h2 className="text-sm font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 flex items-center justify-between gap-2">
              <span className="truncate">{activePlan?.name || '性能压测报告'}</span>
              {runState.status !== 'idle' && (
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-[9px] font-bold ${
                  runState.status === 'running' ? 'bg-blue-500/10 text-blue-600' : runState.status === 'aborted' ? 'bg-amber-500/10 text-amber-600' : runState.status === 'failed' ? 'bg-red-500/10 text-red-600' : 'bg-emerald-500/10 text-emerald-600'
                }`}>
                  {runState.message || runState.status}
                </span>
              )}
            </h2>
            
            {/* 性能核心指标 */}
            <div className="grid grid-cols-4 gap-4 mt-3">
              {reportMetricsView.map((it, idx) => (
                <div key={idx} className="p-3 border border-[var(--border-color)] rounded-xl bg-[var(--border-color)]/20">
                  <span className="text-[10px] text-[var(--text-secondary)] font-semibold">{it.label}</span>
                  <div className={`text-xl font-bold mt-1 ${it.err ? 'text-red-500' : 'text-[var(--text-primary)]'}`}>{it.val}</div>
                  <div className="text-[9px] text-slate-400 mt-1 font-semibold">{it.sub}</div>
                </div>
              ))}
            </div>
            <div className="mt-3 rounded-xl border border-[var(--border-color)] bg-[var(--border-color)]/15 p-3">
              <div className="flex items-center justify-between gap-2 border-b border-[var(--border-color)] pb-2">
                <div className="text-[10px] font-bold text-[var(--text-primary)]">阈值判定</div>
                <span className={`px-2 py-0.5 rounded-full border text-[9px] font-bold ${thresholdBadge.className}`}>{thresholdBadge.text} · {thresholdView.source}</span>
              </div>
              <div className="grid grid-cols-4 gap-2 mt-2">
                {(thresholdView.items.length ? thresholdView.items : [{ label: '暂无阈值结果', actual: '--', threshold: '--', status: 'warning', message: '等待执行结果' }]).map((item, idx) => (
                  <div key={`${item.label}-${idx}`} className="min-w-0 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)]/70 p-2">
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-[8.5px] font-bold text-[var(--text-secondary)] truncate">{item.label || item.metric}</span>
                      <span className={`size-1.5 rounded-full ${item.status === 'pass' ? 'bg-emerald-500' : item.status === 'fail' ? 'bg-red-500' : 'bg-amber-500'}`} />
                    </div>
                    <div className="mt-1 text-[10px] font-extrabold text-[var(--text-primary)] truncate">{item.actual ?? '--'}</div>
                    <div className="text-[7.5px] text-slate-400 truncate">{item.threshold ?? '--'} · {item.message || item.status}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-12 gap-4">
            
            {/* 左侧：走势图 + 交易明细 */}
            <div className="col-span-8 min-w-0 space-y-4">
              
              {/* 性能监控走势图 */}
              <div className="theme-card rounded-xl p-4 shadow-soft">
                <span className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 mb-3.5 block">并发与响应时间走势</span>
                
                <div className="h-[160px] w-full mt-2 relative">
                  <svg className="w-full h-full" viewBox="0 0 520 160" preserveAspectRatio="none">
                    {/* 格线 */}
                    <line x1="40" y1="20" x2="500" y2="20" stroke="var(--border-color)" strokeWidth="1" strokeDasharray="3,3" />
                    <line x1="40" y1="60" x2="500" y2="60" stroke="var(--border-color)" strokeWidth="1" strokeDasharray="3,3" />
                    <line x1="40" y1="100" x2="500" y2="100" stroke="var(--border-color)" strokeWidth="1" strokeDasharray="3,3" />
                    <line x1="40" y1="140" x2="500" y2="140" stroke="var(--border-color)" strokeWidth="1" />

                    {trendAvgPath && <path d={trendAvgPath} fill="none" stroke="var(--accent-color)" strokeWidth="2.2" strokeLinecap="round" className="path-drawn" />}
                    {trendTpsPath && <path d={trendTpsPath} fill="none" stroke="#10b981" strokeWidth="1.8" strokeLinecap="round" strokeDasharray="4,2" className="path-drawn" />}

                    {/* 坐标 */}
                    <text x="30" y="24" textAnchor="end" className="text-[8px] fill-slate-400 font-medium">High</text>
                    <text x="30" y="104" textAnchor="end" className="text-[8px] fill-slate-400 font-medium">Low</text>
                    <text x="510" y="24" textAnchor="start" className="text-[8px] fill-blue-500 font-medium">RT</text>
                    <text x="510" y="64" textAnchor="start" className="text-[8px] fill-emerald-500 font-medium">TPS</text>
                  </svg>
                  {!trendAvgPath && !trendTpsPath && (
                    <div className="absolute inset-0 flex items-center justify-center text-[9px] font-semibold text-slate-400">暂无趋势数据，执行后自动展示。</div>
                  )}
                </div>
              </div>

              {/* 事务明细 Table */}
              <div className="theme-card rounded-xl p-4 shadow-soft">
                <span className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 mb-3 block">事务性能明细</span>
                
                <div className="overflow-x-auto w-full">
                  <table className="w-full text-[10px] text-left border-collapse min-w-[600px]">
                    <thead>
                      <tr className="text-slate-400 font-bold border-b border-slate-50">
                        <th className="py-2 px-1">事务名称 (URL)</th>
                        <th className="py-2 px-1 text-center">调用数</th>
                        <th className="py-2 px-1 text-center">平均 RT</th>
                        <th className="py-2 px-1 text-center">95% RT</th>
                        <th className="py-2 px-1 text-center">TPS</th>
                        <th className="py-2 px-1 text-center">报错数</th>
                        <th className="py-2 px-1 text-center">健康状态</th>
                      </tr>
                    </thead>
                  <tbody className="divide-y divide-slate-50/50 text-slate-600 font-medium">
                    {transactionDetailsView.map((row, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/50 transition-colors">
                        <td className="py-2.5 px-1 font-mono text-[9px] font-bold text-slate-700">{row.name}</td>
                        <td className="py-2.5 px-1 text-center font-bold text-slate-700">{row.count}</td>
                        <td className="py-2.5 px-1 text-center">{row.rt}</td>
                        <td className="py-2.5 px-1 text-center font-semibold text-slate-800">{row.rt95}</td>
                        <td className="py-2.5 px-1 text-center text-emerald-600 font-bold">{row.tps}</td>
                        <td className="py-2.5 px-1 text-center text-red-500 font-bold">{row.err}</td>
                        <td className="py-2.5 px-1 text-center">
                          <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold ${row.statusColor}`}>
                            {row.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                    {!transactionDetailsView.length && (
                      <tr>
                        <td colSpan={7} className="py-6 text-center text-slate-400 font-semibold">暂无事务明细，执行结果返回后展示。</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            </div>

            {/* 右侧：AI 瓶颈诊断 */}
            <div className="col-span-4 min-w-0 space-y-4">
              
              <TiltCard className="p-4 shadow-soft text-left space-y-3 flex-1 flex flex-col justify-between animate-[slideUpFade_0.4s_ease-out]">
                <div style={{ transformStyle: 'preserve-3d' }}>
                  <h3 
                    style={{ transform: 'translateZ(15px)' }}
                    className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 mb-2 flex items-center gap-1.5"
                  >
                    <Sparkles className="size-4 text-purple-600 animate-pulse" />
                    <span>AI 性能瓶颈诊断</span>
                  </h3>
                  <span style={{ transform: 'translateZ(10px)' }} className="text-[9px] text-[var(--text-secondary)]/85 block mb-3">报告快照风险项与建议</span>

                  <div className="space-y-3 text-[9.5px] leading-relaxed text-[var(--text-secondary)] font-semibold" style={{ transformStyle: 'preserve-3d', transform: 'translateZ(20px)' }}>
                    {(reportAdvice.risks.length ? reportAdvice.risks : [{ level: 'info', title: '暂无后端风险项', detail: '执行 generate-report 后会展示 data_snapshot.risk_items。' }]).map((risk, idx) => {
                      const isHigh = risk.level === 'high' || risk.level === 'critical';
                      const isMedium = risk.level === 'medium' || risk.level === 'warning';
                      return (
                        <div
                          key={`${risk.title || idx}-${idx}`}
                          className={`p-2 border rounded-lg transition-transform duration-200 ${isHigh ? 'border-red-500/20 bg-red-500/10' : isMedium ? 'border-amber-500/20 bg-amber-500/10' : 'border-emerald-500/20 bg-emerald-500/10'}`}
                          style={{ transform: 'translateZ(25px)' }}
                        >
                          <div className={`flex items-center gap-1 font-bold ${isHigh ? 'text-red-600' : isMedium ? 'text-amber-600' : 'text-emerald-600'}`}>
                            <AlertTriangle className="size-3.5" />
                            <span className="truncate">{risk.title || risk.name || '风险项'}</span>
                          </div>
                          <p className="text-[8px] text-[var(--text-secondary)]/80 mt-1 line-clamp-3">{risk.detail || risk.message || risk.description || '暂无详情'}</p>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="border-t border-[var(--border-color)] pt-4 space-y-2 mt-4">
                  <div className="text-[10px] font-bold text-[var(--text-primary)]">报告建议</div>
                  <div className="space-y-1.5 text-[8.5px] font-semibold text-slate-500">
                    {(reportAdvice.recommendations.length ? reportAdvice.recommendations : ['暂无后端 recommendations；可重新生成报告后刷新。']).map((item, idx) => (
                      <div key={`${String(item).slice(0, 16)}-${idx}`}>{idx + 1}. {typeof item === 'string' ? item : item.text || item.title || item.detail || '建议项'}</div>
                    ))}
                    {reportContentExcerpt && (
                      <div className="mt-2 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)]/60 p-2 text-[8px] leading-relaxed text-[var(--text-secondary)]/80">
                        {reportContentExcerpt}
                      </div>
                    )}
                  </div>
                </div>
              </TiltCard>

            </div>

          </div>

        </div>
      )}

    </div>
  );
}
