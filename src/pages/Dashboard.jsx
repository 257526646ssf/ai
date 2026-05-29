import React, { useState } from 'react';
import { 
  Folder, 
  FileText, 
  CheckSquare, 
  Play, 
  Target, 
  Network, 
  Cpu, 
  Gauge, 
  Upload, 
  Sparkles, 
  Bot,
  AlertCircle,
  FileCheck
} from 'lucide-react';
import TiltCard from '../components/TiltCard';
import AnimatedNumber from '../components/AnimatedNumber';
import { apiGet, formatDateTime, pickList } from '../lib/api';
import { useProjectContext } from '../lib/projectContext';

const numberText = (value, fallback = '0') => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toLocaleString('zh-CN') : fallback;
};

const percentFromCounts = (total, defects, fallback = '87.6%') => {
  const totalNum = Number(total);
  const defectNum = Number(defects);
  if (!Number.isFinite(totalNum) || totalNum <= 0) return fallback;
  const passRate = Math.max(0, Math.min(100, ((totalNum - Math.max(defectNum, 0)) / totalNum) * 100));
  return `${passRate.toFixed(1)}%`;
};

const countFromSummary = (summary = {}, keys = []) => keys.reduce((sum, key) => sum + Number(summary?.[key] || 0), 0);

const percentFromSummary = (summary = {}, fallback = '0%') => {
  const total = Number(summary?.total || 0);
  if (!Number.isFinite(total) || total <= 0) return fallback;
  const passed = countFromSummary(summary, ['pass', 'passed', 'success', 'succeeded', 'completed']);
  return `${Math.max(0, Math.min(100, (passed / total) * 100)).toFixed(1)}%`;
};

const activityIconByType = (type = '') => {
  const lowered = String(type).toLowerCase();
  if (lowered.includes('defect') || lowered.includes('bug')) return { icon: AlertCircle, iconStyle: 'bg-red-500 text-white', style: 'border-red-500/20 text-red-500 bg-red-500/5' };
  if (lowered.includes('execution') || lowered.includes('run')) return { icon: Play, iconStyle: 'bg-blue-500 text-white', style: 'border-emerald-500/20 text-emerald-500 bg-emerald-500/5' };
  if (lowered.includes('auto')) return { icon: Cpu, iconStyle: 'bg-amber-500 text-white', style: 'border-amber-500/20 text-amber-500 bg-amber-500/5' };
  if (lowered.includes('report')) return { icon: FileCheck, iconStyle: 'bg-purple-500 text-white', style: 'border-purple-500/20 text-purple-500 bg-purple-500/5' };
  return { icon: FileText, iconStyle: 'bg-purple-500 text-white', style: 'border-blue-500/20 text-blue-500 bg-blue-500/5' };
};

const finiteNumber = (value, fallback = 0) => {
  if (value === null || value === undefined || value === '') return fallback;
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};

const clampNumber = (value, min, max) => Math.max(min, Math.min(max, value));

const readField = (source, keys = []) => {
  if (!source || typeof source !== 'object') return undefined;
  for (const key of keys) {
    const value = source[key];
    if (value !== undefined && value !== null && value !== '') return value;
  }
  return undefined;
};

const readArrayField = (source, keys = []) => {
  if (Array.isArray(source)) return source;
  const value = readField(source, keys);
  return Array.isArray(value) ? value : [];
};

const compactNumberText = (value) => {
  const num = finiteNumber(value, 0);
  if (num >= 10000) return `${(num / 10000).toFixed(num >= 100000 ? 0 : 1)}W`;
  if (num >= 1000) return `${(num / 1000).toFixed(num >= 10000 ? 0 : 1)}K`;
  return String(Math.round(num));
};

const percentText = (value) => `${clampNumber(finiteNumber(value, 0), 0, 100).toFixed(1)}%`;

const normalizePercentValue = (value) => {
  const num = finiteNumber(value, NaN);
  if (!Number.isFinite(num)) return null;
  return clampNumber(num <= 1 ? num * 100 : num, 0, 100);
};

const formatTrendLabel = (value, index) => {
  if (value === null || value === undefined || value === '') return String(index + 1).padStart(2, '0');
  const text = String(value);
  const isoDate = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (isoDate) return `${isoDate[2]}-${isoDate[3]}`;
  return text.length > 6 ? text.slice(-6) : text;
};

const readSeriesValue = (series, keys, index) => {
  if (Array.isArray(series)) {
    const matched = series.find((item) => {
      const name = String(readField(item, ['key', 'name', 'type', 'status', 'label']) || '').toLowerCase();
      return keys.some((key) => name.includes(key));
    });
    const values = readArrayField(matched, ['data', 'values', 'points']);
    return finiteNumber(values[index], 0);
  }
  const values = readArrayField(series, keys);
  return finiteNumber(values[index], 0);
};

const normalizeTrendPoint = (item, index) => {
  if (Array.isArray(item)) {
    const hasLabel = Number.isNaN(Number(item[0]));
    const offset = hasLabel ? 1 : 0;
    return {
      label: formatTrendLabel(hasLabel ? item[0] : undefined, index),
      pass: finiteNumber(item[offset], 0),
      fail: finiteNumber(item[offset + 1], 0),
      block: finiteNumber(item[offset + 2], 0),
      other: finiteNumber(item[offset + 3], 0)
    };
  }

  const pass = finiteNumber(readField(item, ['pass', 'passed', 'success', 'succeeded', 'completed', 'ok']), 0);
  const fail = finiteNumber(readField(item, ['fail', 'failed', 'failure', 'error', 'errors']), 0);
  const block = finiteNumber(readField(item, ['block', 'blocked', 'blocking']), 0);
  const explicitOther = readField(item, ['other', 'others', 'pending', 'skipped', 'unexecuted', 'not_run', 'unknown']);
  const total = finiteNumber(readField(item, ['total', 'count']), 0);

  return {
    label: formatTrendLabel(readField(item, ['label', 'date', 'day', 'period', 'name', 'time']), index),
    pass,
    fail,
    block,
    other: explicitOther === undefined ? Math.max(total - pass - fail - block, 0) : finiteNumber(explicitOther, 0)
  };
};

const normalizeExecutionTrend = (payload) => {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload.map(normalizeTrendPoint).slice(-14);
  const labels = readArrayField(payload, ['labels', 'dates', 'days', 'periods']);
  if (labels.length) {
    const series = payload.series || payload;
    return labels.map((label, index) => ({
      label: formatTrendLabel(label, index),
      pass: readSeriesValue(series, ['pass', 'passed', 'success', 'succeeded', 'completed', 'ok'], index),
      fail: readSeriesValue(series, ['fail', 'failed', 'failure', 'error', 'errors'], index),
      block: readSeriesValue(series, ['block', 'blocked', 'blocking'], index),
      other: readSeriesValue(series, ['other', 'others', 'pending', 'skipped', 'unexecuted', 'not_run', 'unknown'], index)
    })).slice(-14);
  }

  return readArrayField(payload, ['items', 'list', 'records', 'rows', 'points', 'data'])
    .map(normalizeTrendPoint)
    .slice(-14);
};

const emptyCoverage = () => ({
  hasData: false,
  total: 0,
  covered: 0,
  partial: 0,
  uncovered: 0,
  coveredPercent: 0,
  partialPercent: 0,
  uncoveredPercent: 0
});

const normalizeRequirementCoverage = (payload) => {
  if (!payload || (Array.isArray(payload) && payload.length === 0)) return emptyCoverage();

  if (Array.isArray(payload)) {
    const counts = payload.reduce((acc, item, index) => {
      if (Array.isArray(item)) {
        const [label, count] = Number.isNaN(Number(item[0])) ? item : [index, item[0]];
        const key = String(label).toLowerCase();
        if (key.includes('partial') || key.includes('部分')) acc.partial += finiteNumber(count, 0);
        else if (key.includes('uncovered') || key.includes('missing') || key.includes('not') || key.includes('未')) acc.uncovered += finiteNumber(count, 0);
        else acc.covered += finiteNumber(count, 0);
        return acc;
      }

      const key = String(readField(item, ['status', 'type', 'name', 'label', 'coverage']) || '').toLowerCase();
      const count = finiteNumber(readField(item, ['count', 'value', 'total']), 0);
      if (key.includes('partial') || key.includes('部分')) acc.partial += count;
      else if (key.includes('uncovered') || key.includes('missing') || key.includes('not') || key.includes('未')) acc.uncovered += count;
      else acc.covered += count;
      return acc;
    }, { covered: 0, partial: 0, uncovered: 0 });
    const total = counts.covered + counts.partial + counts.uncovered;
    return total > 0
      ? {
          hasData: true,
          total,
          ...counts,
          coveredPercent: (counts.covered / total) * 100,
          partialPercent: (counts.partial / total) * 100,
          uncoveredPercent: (counts.uncovered / total) * 100
        }
      : emptyCoverage();
  }

  const entries = readArrayField(payload, ['items', 'list', 'records', 'rows', 'data']);
  if (entries.length) return normalizeRequirementCoverage(entries);

  const covered = finiteNumber(readField(payload, ['covered', 'covered_count', 'full', 'full_covered', 'linked', 'passed']), 0);
  const partial = finiteNumber(readField(payload, ['partial', 'partial_count', 'partially_covered']), 0);
  const uncoveredValue = readField(payload, ['uncovered', 'uncovered_count', 'missing', 'missing_count', 'not_covered', 'notCovered']);
  const explicitTotal = finiteNumber(readField(payload, ['total', 'requirement_total', 'requirement_items', 'all']), 0);
  const uncovered = uncoveredValue === undefined ? Math.max(explicitTotal - covered - partial, 0) : finiteNumber(uncoveredValue, 0);
  const total = explicitTotal || covered + partial + uncovered;
  const explicitRate = normalizePercentValue(readField(payload, ['coverage_rate', 'covered_rate', 'rate', 'percent', 'percentage']));
  const coveredPercent = explicitRate ?? (total > 0 ? (covered / total) * 100 : 0);
  const partialPercent = total > 0 ? (partial / total) * 100 : 0;
  const uncoveredPercent = total > 0 ? (uncovered / total) * 100 : Math.max(0, 100 - coveredPercent - partialPercent);

  return total > 0 || explicitRate !== null
    ? {
        hasData: true,
        total,
        covered,
        partial,
        uncovered,
        coveredPercent,
        partialPercent,
        uncoveredPercent
      }
    : emptyCoverage();
};

const normalizeModuleHeatmap = (payload) => {
  const defaultDimensions = ['需求', '用例', '执行', '缺陷'];
  if (!payload || (Array.isArray(payload) && payload.length === 0)) return { dimensions: defaultDimensions, rows: [] };

  const configuredDimensions = Array.isArray(payload) ? [] : readArrayField(payload, ['dimensions', 'columns', 'metrics']);
  const dimensions = (configuredDimensions.length
    ? configuredDimensions
    : defaultDimensions
  ).map((item) => String(readField(item, ['label', 'name', 'key']) || item));

  const matrix = readArrayField(payload, ['data', 'matrix', 'values']);
  const moduleLabels = readArrayField(payload, ['modules', 'module_names', 'labels']);
  const rowPayload = Array.isArray(payload)
    ? payload
    : (moduleLabels.length && matrix.length
      ? moduleLabels.map((module, index) => ({
          module: readField(module, ['module', 'name', 'label', 'module_name']) || module,
          values: matrix[index]
        }))
      : readArrayField(payload, ['rows', 'items', 'list', 'records', 'modules']));

  const metricKeys = [
    ['requirements', 'requirement_items', 'requirement_count', 'req', '需求'],
    ['test_cases', 'cases', 'case_count', '用例'],
    ['executions', 'execution_count', 'runs', '执行'],
    ['defects', 'defect_count', 'bugs', '缺陷']
  ];

  const rows = rowPayload.map((row, rowIndex) => {
    const label = String(readField(row, ['module', 'module_name', 'name', 'label', 'title']) || `模块 ${rowIndex + 1}`);
    const values = readField(row, ['values', 'cells', 'data', 'metrics']);
    const cells = dimensions.map((dim, dimIndex) => {
      if (Array.isArray(values)) {
        const cell = values[dimIndex];
        return finiteNumber(readField(cell, ['value', 'count', 'heat']) ?? cell, 0);
      }
      if (values && typeof values === 'object') {
        return finiteNumber(readField(values, [String(dim), String(dim).toLowerCase(), ...(metricKeys[dimIndex] || [])]), 0);
      }
      return finiteNumber(readField(row, metricKeys[dimIndex] || [String(dim), String(dim).toLowerCase()]), 0);
    });
    return { label, cells };
  }).filter((row) => row.label && row.cells.some((value) => value > 0)).slice(0, 8);

  return { dimensions, rows };
};

const heatmapThemeRgb = (theme) => {
  switch (theme) {
    case 'clickhouse': return '234, 179, 8';
    case 'brutalist': return '0, 0, 0';
    case 'cyber-glass': return '6, 182, 212';
    case 'dark': return '37, 99, 235';
    case 'linear': return '92, 92, 214';
    case 'editorial': return '28, 25, 23';
    case 'ibm': return '15, 98, 254';
    case 'airtable': return '37, 99, 235';
    case 'notion': return '55, 53, 47';
    default: return '79, 70, 229';
  }
};

export default function Dashboard({ theme }) {
  const { selectedProject, loading: projectLoading, error: projectError } = useProjectContext();
  const [hoveredRow, setHoveredRow] = React.useState(null);
  const [hoveredCol, setHoveredCol] = React.useState(null);
  const [reloadKey, setReloadKey] = React.useState(0);
  const [dashboardData, setDashboardData] = React.useState(null);
  const [remoteActivities, setRemoteActivities] = React.useState([]);
  const [apiState, setApiState] = React.useState({
    status: 'idle',
    projectName: '演示项目',
    updatedAt: null,
    error: ''
  });

  React.useEffect(() => {
    let cancelled = false;

    async function loadDashboardData() {
      setApiState(prev => ({ ...prev, status: 'loading', error: '' }));
      try {
        if (projectLoading) return;
        const project = selectedProject;

        if (!project?.id) {
          if (!cancelled) {
            setDashboardData(null);
            setRemoteActivities([]);
            setApiState({ status: projectError ? 'offline' : 'empty', projectName: '演示项目', updatedAt: null, error: projectError || '' });
          }
          return;
        }

        const [dashboard, activitiesPayload] = await Promise.all([
          apiGet(`/projects/${project.id}/dashboard`),
          apiGet('/system/recent-activities', { params: { projectId: project.id, limit: 5 } }).catch(() => ({ list: [] }))
        ]);

        if (cancelled) return;
        setDashboardData(dashboard);
        setRemoteActivities(pickList(activitiesPayload).map((item, idx) => {
          const meta = activityIconByType(item.target_type || item.type || item.route);
          return {
            id: item.id || `remote-${idx}`,
            title: item.title || item.name || '系统活动已记录',
            desc: item.description || [item.target_type, item.target_id].filter(Boolean).join(' / ') || `项目：${project.name || project.code || project.id}`,
            time: formatDateTime(item.created_at || item.updated_at),
            user: item.user || item.actor || '系统',
            tag: item.action || item.target_type || 'Activity',
            ...meta
          };
        }));
        setApiState({
          status: 'online',
          projectName: project.name || project.code || `项目 ${project.id}`,
          updatedAt: dashboard.updated_at,
          error: ''
        });
      } catch (error) {
        if (!cancelled) {
          setDashboardData(null);
          setRemoteActivities([]);
          setApiState({
            status: 'offline',
            projectName: '演示项目',
            updatedAt: null,
            error: error?.message || '后端暂不可用'
          });
        }
      }
    }

    loadDashboardData();
    return () => {
      cancelled = true;
    };
  }, [projectLoading, projectError, selectedProject, reloadKey]);


  // 根据主题自适应图表色彩
  const getThemeChartColors = () => {
    switch (theme) {
      case 'clickhouse':
        return { pass: '#eab308', fail: '#ef4444', block: '#f59e0b', unexec: '#262626' };
      case 'brutalist':
        return { pass: '#000000', fail: '#ff0000', block: '#ffff00', unexec: '#cccccc' };
      case 'cyber-glass':
        return { pass: '#06b6d4', fail: '#ec4899', block: '#f59e0b', unexec: 'rgba(255,255,255,0.06)' };
      default:
        return { pass: 'var(--accent-color)', fail: '#ef4444', block: '#f59e0b', unexec: 'var(--border-color)' };
    }
  };

  const chartColor = getThemeChartColors();
  const trendPoints = normalizeExecutionTrend(dashboardData?.execution_trend);
  const trendHasData = trendPoints.length > 0;
  const trendMax = Math.max(1, ...trendPoints.flatMap((point) => [point.pass, point.fail, point.block, point.other]));
  const trendScaleLabels = [trendMax, trendMax * 0.75, trendMax * 0.5, trendMax * 0.25, 0].map(compactNumberText);
  const trendChart = { left: 40, right: 500, top: 20, bottom: 140 };
  const trendX = (index) => (trendPoints.length <= 1
    ? (trendChart.left + trendChart.right) / 2
    : trendChart.left + index * ((trendChart.right - trendChart.left) / (trendPoints.length - 1)));
  const trendY = (value) => trendChart.bottom - (finiteNumber(value, 0) / trendMax) * (trendChart.bottom - trendChart.top);
  const trendCoordinates = (key) => trendPoints.map((point, index) => [trendX(index), trendY(point[key])]);
  const trendLinePath = (key) => trendCoordinates(key).map(([x, y], index) => `${index === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
  const trendAreaPath = (key) => {
    const coordinates = trendCoordinates(key);
    if (!coordinates.length) return '';
    const line = coordinates.map(([x, y], index) => `${index === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
    const first = coordinates[0];
    const last = coordinates[coordinates.length - 1];
    return `${line} L ${last[0].toFixed(1)} ${trendChart.bottom} L ${first[0].toFixed(1)} ${trendChart.bottom} Z`;
  };
  const trendSeries = [
    { key: 'pass', color: 'var(--accent-color)', width: 2.2 },
    { key: 'fail', color: chartColor.fail, width: 1.8 },
    { key: 'block', color: chartColor.block, width: 1.6 },
    { key: 'other', color: chartColor.unexec === 'var(--border-color)' ? '#8e9aaf' : chartColor.unexec, width: 1.4 }
  ];
  const requirementCoverage = normalizeRequirementCoverage(dashboardData?.requirement_coverage);
  const coverageTotal = requirementCoverage.total || finiteNumber(dashboardData?.requirement_items, 0);
  const coverageCoveredDash = requirementCoverage.hasData ? clampNumber(requirementCoverage.coveredPercent, 0, 100) : 0;
  const coveragePartialDash = requirementCoverage.hasData ? clampNumber(requirementCoverage.partialPercent, 0, 100 - coverageCoveredDash) : 0;
  const coverageRows = [
    { label: '已覆盖', count: requirementCoverage.covered, percent: requirementCoverage.coveredPercent, colorClass: 'bg-[var(--accent-color)] animate-pulse' },
    { label: '部分覆盖', count: requirementCoverage.partial, percent: requirementCoverage.partialPercent, colorClass: 'bg-[#f59e0b]' },
    { label: '未覆盖', count: requirementCoverage.uncovered, percent: requirementCoverage.uncoveredPercent, colorClass: 'bg-[var(--border-color)]' }
  ];
  const moduleHeatmap = normalizeModuleHeatmap(dashboardData?.module_heatmap);
  const heatmapRows = moduleHeatmap.rows;
  const heatmapDimensions = moduleHeatmap.dimensions;
  const heatmapMax = Math.max(0, ...heatmapRows.flatMap((row) => row.cells));
  const heatmapGridStyle = { gridTemplateColumns: `minmax(0, 1.2fr) repeat(${heatmapDimensions.length}, minmax(0, 1fr))` };
  const executionSummary = dashboardData?.execution_summary || {};
  const apiExecutionSummary = dashboardData?.api_execution_summary || {};
  const autoExecutionSummary = dashboardData?.auto_execution_summary || {};
  const defectSeveritySummary = dashboardData?.defect_severity_summary || {};
  const passRate = dashboardData?.executions ? percentFromSummary(executionSummary, '0%') : percentFromCounts(dashboardData?.test_cases, dashboardData?.defects);
  const apiPassRate = percentFromSummary(apiExecutionSummary, dashboardData ? '0%' : '87.0%');
  const autoPassRate = percentFromSummary(autoExecutionSummary, dashboardData ? '0%' : '90.1%');
  const failedExecutions = countFromSummary(executionSummary, ['fail', 'failed', 'failure', 'error']);
  const blockedExecutions = countFromSummary(executionSummary, ['block', 'blocked']);
  const severeDefects = countFromSummary(defectSeveritySummary, ['fatal', 'blocker', 'critical', '严重', '致命']);
  const highDefects = countFromSummary(defectSeveritySummary, ['high', 'major', '高']);
  const backendStatusText = apiState.status === 'online'
    ? `已连接：${apiState.projectName}`
    : apiState.status === 'loading'
      ? '正在同步后端数据'
      : apiState.status === 'empty'
        ? '后端暂无项目，显示演示数据'
        : '后端离线，显示演示数据';
  const updatedAtText = apiState.status === 'online'
    ? `数据更新时间：${formatDateTime(apiState.updatedAt)}`
    : apiState.status === 'loading'
      ? '数据同步中...'
      : '数据更新时间：演示数据';

  // ======================== 第一排：指标数据 ========================
  const stats = [
    { label: '需求库总数', value: numberText(dashboardData?.requirement_libs, '24'), change: dashboardData ? '后端实时' : '↑ 2', icon: Folder, color: 'text-blue-500 bg-blue-500/10' },
    { label: '需求总数', value: numberText(dashboardData?.requirement_items, '1,248'), change: dashboardData ? '来自后端统计' : '↑ 54 (+4.5%)', icon: FileText, color: 'text-emerald-500 bg-emerald-500/10' },
    { label: '测试用例总数', value: numberText(dashboardData?.test_cases, '3,652'), change: dashboardData ? '实时项目数据' : '↑ 132 (+3.7%)', icon: CheckSquare, color: 'text-amber-500 bg-amber-500/10' },
    { label: '用例执行总数', value: numberText(dashboardData?.executions, '2,891'), change: dashboardData ? '执行记录聚合' : '↑ 156 (+5.7%)', icon: Play, color: 'text-purple-500 bg-purple-500/10' },
    { label: '用例通过率', value: passRate, change: dashboardData ? `缺陷 ${numberText(dashboardData?.defects, '0')}` : '↑ 3.2%', icon: Target, color: 'text-cyan-500 bg-cyan-500/10' },
    { label: '接口测试库总数', value: numberText(dashboardData?.api_test_libs, '186'), change: dashboardData ? `接口 ${numberText(dashboardData?.api_endpoints, '0')}` : '↑ 4', icon: Network, color: 'text-indigo-500 bg-indigo-500/10' },
    { label: '自动化脚本总数', value: numberText(dashboardData?.auto_case_files, '842'), change: dashboardData ? `项目 ${numberText(dashboardData?.auto_projects, '0')}` : '↑ 27', icon: Cpu, color: 'text-slate-500 bg-slate-500/10' },
    { label: '性能测试方案总数', value: numberText(dashboardData?.perf_plans, '24'), change: dashboardData ? `结果 ${numberText(dashboardData?.perf_results, '0')}` : '↑ 1', icon: Gauge, color: 'text-rose-500 bg-rose-500/10' },
  ];

  // ======================== 最近活动数据 ========================
  const activities = [
    { id: 1, title: '执行任务 #EXEC-20250520-0089 完成', desc: '项目：智能客服系统 / 版本：v2.3.0', time: '10:24', user: '张明', tag: '通过率 92.1%', style: 'border-emerald-500/20 text-emerald-500 bg-emerald-500/5', icon: CheckSquare, iconStyle: 'bg-emerald-500 text-white' },
    { id: 2, title: '接口测试 【POST /api/v1/order/create】 执行完成', desc: '项目：电商平台 / 环境：测试环境', time: '10:15', user: '李华', tag: '通过率 92.3%', style: 'border-emerald-500/20 text-emerald-500 bg-emerald-500/5', icon: Play, iconStyle: 'bg-blue-500 text-white' },
    { id: 3, title: '自动化任务「夜间回归 - 全量」执行完成', desc: '项目：智能客服系统 / 共 120 个用例', time: '09:47', user: '王芳', tag: '通过率 90.0%', style: 'border-emerald-500/20 text-emerald-500 bg-emerald-500/5', icon: Cpu, iconStyle: 'bg-amber-500 text-white' },
    { id: 4, title: '缺陷 #BUG-20250520-003 已创建', desc: '项目：电商平台 / 严重程度：高', time: '09:32', user: '赵强', tag: 'P1', style: 'border-red-500/20 text-red-500 bg-red-500/5', icon: AlertCircle, iconStyle: 'bg-red-500 text-white' },
    { id: 5, title: '需求文档《支付系统需求说明书》已上传', desc: '项目：支付系统 / 版本：v1.2', time: '09:15', user: '陈磊', tag: '新增需求 24', style: 'border-blue-500/20 text-blue-500 bg-blue-500/5', icon: FileText, iconStyle: 'bg-purple-500 text-white' }
  ];
  const visibleActivities = remoteActivities.length ? remoteActivities : activities;

  // ======================== 快速操作配置 ========================
  const quickActions = [
    { title: '快速上传需求', desc: '支持 Word、Excel、PDF', icon: Upload, type: 'upload-req' },
    { title: '快速生成用例', desc: '基于需求智能生成用例', icon: Sparkles, type: 'generate-cases' },
    { title: '快速执行接口测试', desc: '选择接口集合，立即执行', icon: Network, type: 'api-request' },
    { title: '创建自动化任务', desc: '构建并执行自动化任务', icon: Cpu, type: 'toast', message: '已成功创建自动化流水线任务！' },
    { title: '创建性能测试方案', desc: '配置并启动性能测试', icon: Gauge, type: 'toast', message: '性能压测方案模版配置已保存！' },
    { title: '生成测试报告', desc: '汇总结果，生成报告', icon: FileCheck, type: 'run-execution' }
  ];

  const handleQuickAction = (act) => {
    if (act.type === 'toast') {
      window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: act.message, type: 'success' } }));
    } else {
      window.dispatchEvent(new CustomEvent('open-modal', { detail: { type: act.type } }));
    }
  };

  // ======================== 项目健康度 ========================
  const healthMetrics = [
    { label: '用例通过率', val: passRate, change: dashboardData ? '后端执行' : '↑ 3.2%', linePath: 'M 5 20 Q 20 5, 35 15 T 65 5 T 95 8' },
    { label: '缺陷总数', val: numberText(dashboardData?.defects, '2.34'), unit: dashboardData ? '个' : '/KLOC', change: dashboardData ? `严重 ${severeDefects + highDefects}` : '↓ 0.21', linePath: 'M 5 5 Q 20 20, 35 12 T 65 18 T 95 22' },
    { label: '自动化通过率', val: autoPassRate, change: dashboardData ? `执行 ${numberText(dashboardData?.auto_executions, '0')}` : '↑ 1.6%', linePath: 'M 5 18 Q 20 12, 35 14 T 65 8 T 95 4' },
    { label: '接口通过率', val: apiPassRate, change: dashboardData ? `执行 ${numberText(dashboardData?.api_executions, '0')}` : '↑ 2.8%', linePath: 'M 5 22 Q 20 15, 35 18 T 65 10 T 95 5' }
  ];

  // ======================== 今日测试执行概览 ========================
  const executionOverview = dashboardData ? [
    { type: '主链执行', plan: numberText(dashboardData?.test_rounds, '0'), pass: numberText(countFromSummary(executionSummary, ['pass', 'passed', 'success']), '0'), fail: failedExecutions + blockedExecutions, rate: passRate },
    { type: '接口测试', plan: numberText(dashboardData?.api_test_libs, '0'), pass: numberText(countFromSummary(apiExecutionSummary, ['pass', 'passed', 'success', 'completed']), '0'), fail: countFromSummary(apiExecutionSummary, ['fail', 'failed', 'error']), rate: apiPassRate },
    { type: '自动化测试', plan: numberText(dashboardData?.auto_projects, '0'), pass: numberText(countFromSummary(autoExecutionSummary, ['pass', 'passed', 'success', 'completed']), '0'), fail: countFromSummary(autoExecutionSummary, ['fail', 'failed', 'error']), rate: autoPassRate },
    { type: '性能测试', plan: numberText(dashboardData?.perf_plans, '0'), pass: numberText(dashboardData?.perf_results, '0'), fail: 0, rate: dashboardData?.perf_results ? '已产出' : '待执行' }
  ] : [
    { type: '测试计划', plan: 8, exec: 8, pass: '6,532', fail: 982, rate: '86.9%' },
    { type: '接口测试', plan: 23, exec: 23, pass: '1,256', fail: 187, rate: '87.0%' },
    { type: '自动化测试', plan: 15, exec: 15, pass: '3,842', fail: 421, rate: '90.1%' },
    { type: '性能测试', plan: 3, exec: 3, pass: '27', fail: 3, rate: '90.0%' }
  ];

  // ======================== 待办事项 ========================
  const todos = dashboardData ? [
    ...(dashboardData.defects ? [{ text: `处理当前项目 ${numberText(dashboardData.defects)} 个缺陷，优先看严重/高优先级`, priority: severeDefects + highDefects ? '高' : '中', priorityColor: severeDefects + highDefects ? 'text-red-500 bg-red-500/10 border-red-500/10' : 'text-amber-500 bg-amber-500/10 border-amber-500/10' }] : []),
    ...(failedExecutions ? [{ text: `复盘 ${failedExecutions} 条失败执行记录并补充缺陷关联`, priority: '高', priorityColor: 'text-red-500 bg-red-500/10 border-red-500/10' }] : []),
    ...(blockedExecutions ? [{ text: `解除 ${blockedExecutions} 条阻塞执行，确认环境或数据依赖`, priority: '中', priorityColor: 'text-amber-500 bg-amber-500/10 border-amber-500/10' }] : []),
    ...(dashboardData.api_test_cases ? [{ text: `检查 ${numberText(dashboardData.api_test_cases)} 条接口用例的最近运行状态`, priority: '中', priorityColor: 'text-amber-500 bg-amber-500/10 border-amber-500/10' }] : []),
    ...(dashboardData.reports ? [{ text: `复核最新 ${numberText(dashboardData.reports)} 份报告的准出结论`, priority: '低', priorityColor: 'text-blue-500 bg-blue-500/10 border-blue-500/10' }] : [])
  ].slice(0, 6) : [
    { text: '评审需求文档《用户权限管理需求说明书》', priority: '高', priorityColor: 'text-red-500 bg-red-500/10 border-red-500/10' },
    { text: '修复缺陷 #BUG-20250519-011', priority: '高', priorityColor: 'text-red-500 bg-red-500/10 border-red-500/10' },
    { text: '执行测试计划「版本 v2.3.0 上线回归」', priority: '中', priorityColor: 'text-amber-500 bg-amber-500/10 border-amber-500/10' },
    { text: '完善接口文档 /api/v1/user/profile', priority: '中', priorityColor: 'text-amber-500 bg-amber-500/10 border-amber-500/10' },
    { text: '性能测试「并发 500 - 订单接口」执行分析', priority: '中', priorityColor: 'text-amber-500 bg-amber-500/10 border-amber-500/10' },
    { text: '整理测试报告（周报）', priority: '低', priorityColor: 'text-blue-500 bg-blue-500/10 border-blue-500/10' }
  ];
  const visibleTodos = todos.length ? todos : [
    { text: '当前项目暂无高风险待办，继续补充执行记录和报告证据', priority: '低', priorityColor: 'text-blue-500 bg-blue-500/10 border-blue-500/10' }
  ];
  const todoCount = visibleTodos.length;

  return (
    <div className="space-y-5 text-left relative pb-10 w-full animate-[fadeIn_0.2s_ease-out]">
      
      {/* 顶部指示 */}
      <div className="flex justify-between items-center text-[10px] opacity-60 text-[var(--text-secondary)]">
        <div>{backendStatusText}</div>
        <div 
          onClick={() => {
            setReloadKey(prev => prev + 1);
            window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '正在同步后端最新数据...', type: 'info' } }));
          }}
          className="flex items-center gap-1.5 cursor-pointer hover:opacity-100 transition-all font-semibold"
        >
          <span>{updatedAtText}</span>
          <span className="scale-110 font-bold">↻</span>
        </div>
      </div>

      {/* AI 智能网关大盘诊断摘要 (3D 倾斜眩光卡) */}
      <TiltCard 
        className="p-5 flex items-center justify-between gap-4 border border-[var(--accent-color)]/40 bg-[var(--accent-glow)]/20 backdrop-blur-lg relative overflow-hidden animate-[slideUpFade_0.4s_ease-out] laser-chase-border cyber-meteor-dust"
      >
        <div className="flex items-center gap-3 relative z-20" style={{ transformStyle: 'preserve-3d' }}>
          <div className="p-3 rounded-xl bg-purple-500/20 text-purple-600 dark:text-purple-300 shrink-0 transition-transform duration-200 shadow-md" style={{ transform: 'translateZ(30px)' }}>
            <Sparkles className="size-6 animate-pulse" />
          </div>
          <div className="text-left" style={{ transform: 'translateZ(20px)' }}>
            <div className="font-black text-xs text-[var(--text-primary)] flex items-center gap-2">
              <span className="cyber-glitch-text cursor-pointer transition-all text-sm font-black glorious-highlight-text" data-text="AI 测试效能管家">AI 测试效能管家</span>
              <span className="px-2 py-0.5 bg-purple-500/20 text-purple-600 dark:text-purple-300 rounded font-black text-[9px] tracking-wider uppercase border border-purple-500/30 animate-pulse">v2.5 Live</span>
            </div>
            <p className="text-[12px] text-[var(--text-primary)] mt-2 leading-relaxed font-bold">
              当前项目共记录了 <span className="crucial-glow-text font-black">{numberText(dashboardData?.test_rounds, '3')}</span> 个测试轮次，主链执行通过率为 <span className="glorious-highlight-text text-[13px] font-black">{passRate}</span>。后端发现 <span className="text-red-500 font-black text-[13px] underline decoration-wavy underline-offset-4">{numberText(dashboardData?.defects, '12')} 个缺陷</span>，其中严重/高风险 <span className="text-red-500 font-black">{dashboardData ? severeDefects + highDefects : 12}</span> 个；建议优先复盘失败执行与接口自动化结果，避免影响后续 <span className="text-[var(--accent-color)] font-extrabold underline">准出判断</span>。
            </p>
          </div>
        </div>
        <button 
          onClick={() => window.dispatchEvent(new CustomEvent('open-ai-chat'))}
          style={{ transform: 'translateZ(25px)' }}
          className="px-4 py-2 rounded-xl glow-button-neon font-black text-[11px] whitespace-nowrap cursor-pointer transition-all shrink-0 relative z-20 shadow-lg tracking-wider"
        >
          查看 AI 调优大纲
        </button>
      </TiltCard>

      {/* ======================== 第一排：指标卡片 (改为 4 列以扩展宽度) ======================== */}
      <div className="grid grid-cols-4 gap-4">
        {stats.map((item, idx) => {
          const Icon = item.icon;
          return (
            <TiltCard 
              key={idx} 
              className="chroma-glass rounded-xl p-4 shadow-sm flex items-center justify-between shimmer-sweep"
              style={{
                animation: 'slideUpFade 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards',
                animationDelay: `${idx * 40 + 100}ms`,
                opacity: 0
              }}
            >
              <div className="text-left" style={{ transform: 'translateZ(20px)' }}>
                <span className="text-[10.5px] font-bold text-[var(--text-secondary)] tracking-tight block">{item.label}</span>
                <div className="mt-2.5">
                  <span className="text-2.5xl font-black tracking-tight digital-matrix-number">
                    <AnimatedNumber value={item.value} delay={idx * 50 + 150} />
                  </span>
                </div>
                <div className="mt-1 flex items-center text-[9px] font-bold">
                  <span className="text-emerald-500">
                    {item.change}
                  </span>
                </div>
              </div>
              
              <div 
                className={`p-3 rounded-xl ${item.color.split(' ')[1]} ${item.color.split(' ')[0]} shrink-0`}
                style={{ transform: 'translateZ(25px)' }}
              >
                <Icon className="size-[18px]" />
              </div>
            </TiltCard>
          );
        })}
      </div>

      {/* ======================== 第二排：高级分析图表 ======================== */}
      <div className="grid grid-cols-12 gap-5">
        
        {/* 用例执行趋势（近14天） */}
        <div className="col-span-5 theme-card rounded-xl p-4 shadow-sm flex flex-col justify-between min-h-[260px]">
          <div>
            <div className="flex justify-between items-center border-b border-[var(--border-color)] pb-2.5 mb-3">
              <span className="text-xs font-bold text-[var(--text-primary)]">用例执行趋势（近14天）</span>
              <div className="flex items-center gap-1 text-[9.5px] opacity-70 border border-[var(--border-color)] rounded px-1.5 py-0.5 hover:opacity-100 cursor-pointer text-[var(--text-primary)] font-bold">
                <span>近 14 天</span>
                <span className="scale-75 origin-center">▼</span>
              </div>
            </div>
            
            {/* 图例 */}
            <div className="flex gap-4 text-xs font-black mb-3">
              <div className="flex items-center gap-2 text-[var(--text-primary)]">
                <span className="size-2.5 rounded-full border border-white/10 shadow-sm shrink-0" style={{ backgroundColor: 'var(--accent-color)' }}></span>
                <span>通过</span>
              </div>
              <div className="flex items-center gap-2 text-[var(--text-primary)]">
                <span className="size-2.5 rounded-full border border-white/10 shadow-sm shrink-0" style={{ backgroundColor: chartColor.fail }}></span>
                <span>失败</span>
              </div>
              <div className="flex items-center gap-2 text-[var(--text-primary)]">
                <span className="size-2.5 rounded-full border border-white/10 shadow-sm shrink-0" style={{ backgroundColor: chartColor.block }}></span>
                <span>阻塞</span>
              </div>
              <div className="flex items-center gap-2 text-[var(--text-primary)]">
                <span className="size-2.5 rounded-full border border-white/10 shadow-sm shrink-0" style={{ backgroundColor: chartColor.unexec === 'var(--border-color)' ? '#8e9aaf' : chartColor.unexec }}></span>
                <span>其他</span>
              </div>
            </div>
          </div>

          {/* SVG 折线图 */}
          <div className="relative h-[160px] w-full mt-2">
            <svg className="w-full h-full" viewBox="0 0 520 160" preserveAspectRatio="none">
              {/* 背景格线 */}
              <line x1="40" y1="20" x2="500" y2="20" stroke="var(--border-color)" strokeWidth="0.8" strokeDasharray="3,3" />
              <line x1="40" y1="50" x2="500" y2="50" stroke="var(--border-color)" strokeWidth="0.8" strokeDasharray="3,3" />
              <line x1="40" y1="80" x2="500" y2="80" stroke="var(--border-color)" strokeWidth="0.8" strokeDasharray="3,3" />
              <line x1="40" y1="110" x2="500" y2="110" stroke="var(--border-color)" strokeWidth="0.8" strokeDasharray="3,3" />
              <line x1="40" y1="140" x2="500" y2="140" stroke="var(--border-color)" strokeWidth="1" />

              {/* 轴刻度 */}
              {trendScaleLabels.map((label, index) => (
                <text
                  key={index}
                  x="30"
                  y={24 + index * 30}
                  textAnchor="end"
                  stroke="var(--bg-card)"
                  strokeWidth="2.5"
                  paintOrder="stroke fill"
                  className="text-[11px] fill-current text-[var(--text-primary)] font-black"
                >
                  {label}
                </text>
              ))}

              {trendPoints.map((point, index) => (
                <text
                  key={`${point.label}-${index}`}
                  x={trendX(index)}
                  y="154"
                  textAnchor="middle"
                  stroke="var(--bg-card)"
                  strokeWidth="2.5"
                  paintOrder="stroke fill"
                  className="text-[11px] fill-current text-[var(--text-primary)] font-black"
                >
                  {point.label}
                </text>
              ))}

              <defs>
                <linearGradient id="grad_dashboard_pass" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="var(--accent-color)" />
                  <stop offset="100%" stopColor="var(--accent-color)" stopOpacity="0" />
                </linearGradient>
              </defs>

              {trendHasData && (
                <path
                  d={trendAreaPath('pass')}
                  fill="url(#grad_dashboard_pass)"
                  opacity="0.15"
                />
              )}

              {trendHasData && trendSeries.map((series, seriesIndex) => (
                <React.Fragment key={series.key}>
                  <path
                    d={trendLinePath(series.key)}
                    fill="none"
                    stroke={series.color}
                    strokeWidth={series.width}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="path-drawn"
                  />
                  <path
                    d={trendLinePath(series.key)}
                    fill="none"
                    stroke={series.color}
                    strokeWidth={series.width}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="svg-pulse-path"
                    opacity="0.7"
                  />
                  {trendCoordinates(series.key).map(([cx, cy], index) => (
                    <circle
                      key={index}
                      cx={cx}
                      cy={cy}
                      r={seriesIndex === 0 ? 2.5 : 2}
                      fill="var(--bg-card)"
                      stroke={series.color}
                      strokeWidth={seriesIndex === 0 ? 1.5 : 1.2}
                      style={{
                        transformOrigin: `${cx}px ${cy}px`,
                        animation: 'scaleUpBounce 0.45s cubic-bezier(0.34, 1.56, 0.64, 1) forwards',
                        animationDelay: `${index * 45 + 260 + seriesIndex * 80}ms`,
                        opacity: 0
                      }}
                    />
                  ))}
                  {trendCoordinates(series.key).slice(-1).map(([cx, cy]) => (
                    <React.Fragment key="last">
                      <circle cx={cx} cy={cy} r="5" fill={series.color} opacity="0.28" className="animate-ping" pointerEvents="none" />
                      <circle cx={cx} cy={cy} r="3" fill={series.color} opacity="0.15" className="telemetry-indicator-pulse" pointerEvents="none" />
                    </React.Fragment>
                  ))}
                </React.Fragment>
              ))}
            </svg>
            {!trendHasData && (
              <div className="absolute inset-0 flex items-center justify-center text-[11px] font-black text-[var(--text-secondary)]">
                暂无后端趋势数据
              </div>
            )}
          </div>
        </div>

        {/* 需求覆盖率 (圆环) */}
        <div className="col-span-3 theme-card rounded-xl p-4 shadow-sm flex flex-col justify-between min-h-[260px]">
          <div className="border-b border-[var(--border-color)] pb-2.5">
            <span className="text-xs font-bold text-[var(--text-primary)]">需求覆盖率</span>
          </div>

          <div className="flex items-center justify-between py-2.5">
            {/* SVG 圆环 - 动态绘制 */}
            <div className="relative size-[95px] shrink-0 sonar-ripple-container">
              <div className="sonar-ripple-circle"></div>
              <div className="sonar-ripple-circle sonar-ripple-circle-delay"></div>
              <svg className="w-full h-full transform -rotate-90 relative z-10" viewBox="0 0 36 36">
                <circle cx="18" cy="18" r="15.915" fill="none" stroke="var(--border-color)" strokeWidth="3" />
                <circle cx="18" cy="18" r="15.915" fill="none" stroke="#f59e0b" strokeWidth="3.2"
                  strokeDasharray={`${coveragePartialDash} ${100 - coveragePartialDash}`}
                  strokeDashoffset={-coverageCoveredDash}
                  className="transition-all duration-100 ease-out"
                />
                <circle cx="18" cy="18" r="15.915" fill="none" stroke="var(--accent-color)" strokeWidth="3.2"
                  strokeDasharray={`${coverageCoveredDash} ${100 - coverageCoveredDash}`}
                  strokeDashoffset="0"
                  className="transition-all duration-100 ease-out"
                />
                <path d="M18,18 L18,2 A16,16 0 0,1 30,10 Z" fill="var(--accent-glow)" className="radar-sweeper-beam" />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center z-10">
                <span className="text-[13.5px] font-black leading-none text-[var(--text-primary)]">{requirementCoverage.hasData ? percentText(requirementCoverage.coveredPercent) : '--'}</span>
                <span className="text-[8px] text-[var(--text-secondary)] opacity-60 mt-1 leading-none">{requirementCoverage.hasData ? '已覆盖' : '暂无数据'}</span>
              </div>
            </div>

            {/* 右侧指标说明 - 联动滚动 */}
            <div className="flex-1 pl-3.5 space-y-2 text-[9px] font-bold text-[var(--text-primary)]">
              {coverageRows.map((item) => (
                <div key={item.label} className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className={`size-2 rounded-full shrink-0 ${item.colorClass}`}></span>
                    <span className="opacity-80">{item.label}</span>
                  </div>
                  <span>
                    {requirementCoverage.hasData ? numberText(item.count, '0') : '--'}{' '}
                    <span className="opacity-45 font-normal">({requirementCoverage.hasData ? percentText(item.percent) : '--'})</span>
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="border-t border-[var(--border-color)] pt-2 text-right">
            <span className="text-[9px] text-[var(--text-secondary)] opacity-50">需求总数：{numberText(coverageTotal, '0')}</span>
          </div>
        </div>

        {/* 模块使用热力图 */}
        <div className="col-span-4 theme-card rounded-xl p-4 shadow-sm flex flex-col justify-between min-h-[260px]">
          <div className="border-b border-[var(--border-color)] pb-2.5 mb-2">
            <span className="text-xs font-black text-[var(--text-primary)]">模块使用热力图</span>
          </div>

          <div>
            {/* 十字列标题高亮 */}
            <div className="grid text-xs font-black text-center mb-2.5 py-1.5 rounded bg-[var(--border-color)]/40 text-[var(--text-primary)]" style={heatmapGridStyle}>
              <div></div>
              {heatmapDimensions.map((dim, idx) => {
                const isColHovered = hoveredCol === idx;
                return (
                  <div 
                    key={idx} 
                    className={`transition-all duration-200 ${isColHovered ? 'text-[var(--accent-color)] scale-110 font-black' : 'opacity-80'}`}
                  >
                    {dim}
                  </div>
                );
              })}
            </div>

            {/* 热力网格容器，加装绝对定位纵向激光雷达扫描线 */}
            <div className="relative overflow-hidden rounded-lg p-0.5">
              <div className="absolute left-0 w-full h-[2.5px] bg-gradient-to-r from-transparent via-[var(--accent-color)] to-transparent pointer-events-none animate-scan-y z-10" />
              
              {heatmapRows.length ? (
                <div className="space-y-2 relative z-0">
                {heatmapRows.map((row, rowIdx) => {
                  const isRowHovered = hoveredRow === rowIdx;
                  return (
                    <div key={row.label} className="grid items-center gap-1 text-center" style={heatmapGridStyle}>
                      {/* 十字行标题高亮 */}
                      <span 
                        className={`text-[11px] font-black text-left truncate pr-1 transition-all duration-200 ${
                          isRowHovered 
                            ? 'text-[var(--accent-color)] scale-105 origin-left font-black translate-x-0.5' 
                            : 'text-[var(--text-primary)] opacity-85'
                        }`}
                      >
                        {row.label}
                      </span>
                      {row.cells.map((rawValue, colIdx) => {
                        const level = heatmapMax > 4
                          ? Math.ceil((finiteNumber(rawValue, 0) / heatmapMax) * 4)
                          : Math.round(finiteNumber(rawValue, 0));
                        const val = clampNumber(level, 0, 4);
                        const rgb = heatmapThemeRgb(theme);
                        const fillStyle = { backgroundColor: `rgba(${rgb}, ${val > 0 ? 0.10 + val * 0.18 : 0.06})` };
                        
                        // 部署多频波段闪烁
                        const pulseClass = val === 4 
                          ? 'heat-pulse-high' 
                          : val === 3 
                            ? 'heat-pulse-med' 
                            : val === 2 
                              ? 'heat-pulse-low' 
                              : '';

                        const isCurrentHovered = hoveredRow === rowIdx && hoveredCol === colIdx;

                        return (
                          <div 
                            key={colIdx} 
                            onMouseEnter={() => {
                              setHoveredRow(rowIdx);
                              setHoveredCol(colIdx);
                            }}
                            onMouseLeave={() => {
                              setHoveredRow(null);
                              setHoveredCol(null);
                            }}
                            style={{
                              ...fillStyle,
                              animation: 'scaleIn 0.35s cubic-bezier(0.34, 1.56, 0.64, 1) forwards',
                              animationDelay: `${(rowIdx * 4 + colIdx) * 16 + 120}ms`,
                              opacity: 0
                            }}
                            className={`h-4 rounded transition-all duration-200 transform cursor-pointer border border-[var(--border-color)]/60 ${pulseClass} ${
                              isCurrentHovered 
                                ? 'scale-125 border-[var(--accent-color)] shadow-[0_0_10px_var(--accent-glow)] z-20' 
                                : 'hover:scale-115'
                            }`}
                            title={`${row.label} - ${heatmapDimensions[colIdx]}: ${numberText(rawValue, '0')}`}
                          />
                        );
                      })}
                    </div>
                  );
                })}
                </div>
              ) : (
                <div className="min-h-[150px] flex items-center justify-center text-[11px] font-black text-[var(--text-secondary)]">
                  暂无模块热力数据
                </div>
              )}
            </div>
          </div>

          {/* 滑轨能量流光 */}
          <div className="border-t border-[var(--border-color)] pt-2.5 flex items-center justify-between text-[10px] text-[var(--text-primary)] font-black">
            <div className="flex items-center gap-2">
              <span>低</span>
              <span className="w-20 h-2 rounded-full border border-[var(--border-color)] thermal-legend-flow" />
              <span>高</span>
            </div>
            <span className="text-[var(--text-secondary)] font-extrabold">需求总数：{numberText(dashboardData?.requirement_items, '0')}</span>
          </div>
        </div>

      </div>

      {/* ======================== 第三排：细节与操作流 ======================== */}
      <div className="grid grid-cols-12 gap-5">
        
        {/* 最近活动 */}
        <div className="col-span-4 theme-card rounded-xl p-4 shadow-sm flex flex-col justify-between min-h-[300px]">
          <div className="border-b border-[var(--border-color)] pb-2.5 mb-3">
            <span className="text-xs font-bold text-[var(--text-primary)]">最近活动</span>
          </div>

          <div className="flex-1 space-y-3">
            {visibleActivities.map((act, idx) => {
              const Icon = act.icon;
              const statusClass = act.style.includes('emerald')
                ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/30'
                : act.style.includes('red')
                  ? 'text-red-600 dark:text-red-400 bg-red-500/10 border-red-500/30'
                  : 'text-blue-600 dark:text-blue-400 bg-blue-500/10 border-blue-500/30';

              return (
                <div 
                  key={act.id} 
                  className="flex gap-2.5 text-left items-start"
                  style={{
                    animation: 'slideUpFade 0.45s cubic-bezier(0.16, 1, 0.3, 1) forwards',
                    animationDelay: `${idx * 80 + 250}ms`,
                    opacity: 0
                  }}
                >
                  <div className={`p-2 rounded-full shrink-0 ${act.iconStyle} shadow-sm`}>
                    <Icon className="size-3.5" />
                  </div>
                  
                  <div className="flex-1 min-w-0 text-[var(--text-primary)]">
                    <div className="text-xs font-black truncate leading-snug">
                      {act.title}
                    </div>
                    <div className="text-[11px] text-[var(--text-secondary)] mt-1 truncate font-bold">
                      {act.desc}
                    </div>
                    <div className="flex items-center gap-2.5 mt-1 text-[10px] text-[var(--text-secondary)] font-extrabold">
                      <span>{act.time}</span>
                      <span>•</span>
                      <span>{act.user}</span>
                    </div>
                  </div>

                  <div className={`text-[10px] font-black border px-2 py-0.5 rounded shrink-0 shadow-sm ${statusClass}`}>
                    {act.tag}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="text-center pt-3 border-t border-[var(--border-color)] mt-3">
            <span 
              onClick={() => window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '正在加载历史活动日志...', type: 'info' } }))}
              className="text-[10px] font-bold hover:opacity-85 transition-all cursor-pointer text-[var(--accent-color)]"
            >
              查看全部活动 →
            </span>
          </div>
        </div>

        {/* 快速操作与项目健康度 */}
        <div className="col-span-4 flex flex-col gap-4">
          
          {/* 快速操作 */}
          <div className="theme-card rounded-xl p-4 shadow-sm">
            <div className="border-b border-[var(--border-color)] pb-2.5 mb-3">
              <span className="text-xs font-bold text-[var(--text-primary)]">快速操作</span>
            </div>
            
            <div className="grid grid-cols-3 gap-2">
              {quickActions.map((act, idx) => {
                const Icon = act.icon;
                return (
                  <button 
                    key={idx}
                    onClick={() => handleQuickAction(act)}
                    style={{
                      animation: 'slideUpFade 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards',
                      animationDelay: `${idx * 50 + 200}ms`,
                      opacity: 0
                    }}
                    className="quick-action-item flex flex-col items-center justify-center p-2.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/30 text-[var(--text-primary)] text-center transition-all cursor-pointer hover:scale-[1.03] hover:border-[var(--accent-color)]/50 shadow-sm"
                  >
                    <Icon className="size-[15px] shrink-0 mb-1 transition-transform duration-200" style={{ color: 'var(--accent-color)' }} />
                    <span className="text-[9px] font-bold tracking-tight block truncate w-full">{act.title}</span>
                    <span className="text-[7.5px] font-normal opacity-50 mt-0.5 block truncate w-full scale-95 origin-center">{act.desc}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* 项目健康度 */}
          <div className="theme-card rounded-xl p-4 shadow-sm">
            <div className="border-b border-[var(--border-color)] pb-2.5 mb-3">
              <span className="text-xs font-bold text-[var(--text-primary)]">项目健康度</span>
            </div>

            <div className="grid grid-cols-4 gap-2 text-center text-[var(--text-primary)]">
              {healthMetrics.map((met, idx) => (
                <div 
                  key={met.label} 
                  style={{
                    animation: 'slideUpFade 0.45s cubic-bezier(0.16, 1, 0.3, 1) forwards',
                    animationDelay: `${idx * 80 + 350}ms`,
                    opacity: 0
                  }}
                  className="border border-[var(--border-color)] rounded-lg p-2 bg-[var(--border-color)]/20 flex flex-col justify-between min-h-[85px] shadow-sm"
                >
                  <div className="text-[8px] text-[var(--text-secondary)] font-bold truncate leading-tight">{met.label}</div>
                  <div className="mt-1 text-[11.5px] font-black">
                    <AnimatedNumber value={met.val} delay={idx * 60 + 300} />
                    {met.unit && <span className="text-[7px] font-normal opacity-45 ml-0.5 inline-block">{met.unit}</span>}
                  </div>
                  
                  {/* 微折线图 */}
                  <div className="h-6 w-full my-1.5">
                    <svg className="w-full h-full" viewBox="0 0 100 30" preserveAspectRatio="none">
                      <path 
                        d={met.linePath} 
                        fill="none" 
                        stroke="var(--accent-color)" 
                        strokeWidth="1.8" 
                        strokeLinecap="round" 
                        className="path-drawn"
                      />
                    </svg>
                  </div>
                  
                  <div className="text-[8px] font-bold text-emerald-500 leading-none">{met.change}</div>
                </div>
              ))}
            </div>
          </div>

        </div>

        {/* 测试执行与待办 */}
        <div className="col-span-4 flex flex-col gap-4">
          
          {/* 测试执行概览（今日） */}
          <div className="theme-card rounded-xl p-4 shadow-sm flex-1 flex flex-col justify-between min-h-[140px]">
            <div>
              <div className="border-b border-[var(--border-color)] pb-2.5 mb-2">
                <span className="text-xs font-black text-[var(--text-primary)]">测试执行概览（今日）</span>
              </div>

              <table className="w-full text-xs text-left border-collapse">
                <thead>
                  <tr className="border-b border-[var(--border-color)] text-[var(--text-primary)] font-black">
                    <th className="py-2 font-black text-[11.5px]">类型</th>
                    <th className="py-2 font-black text-center text-[11.5px]">计划数</th>
                    <th className="py-2 font-black text-center text-[11.5px]">通过数</th>
                    <th className="py-2 font-black text-center text-[11.5px]">失败数</th>
                    <th className="py-2 font-black text-center text-[11.5px]">通过率</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-color)] text-[var(--text-primary)] font-bold">
                  {executionOverview.map((row, idx) => (
                    <tr key={idx} className="hover:bg-[var(--border-color)]/20 transition-colors">
                      <td className="py-2 font-black">{row.type.substring(0, 5)}</td>
                      <td className="py-2 text-center">{row.plan}</td>
                      <td className="py-2 text-center font-black text-[var(--accent-color)]">{row.pass}</td>
                      <td className="py-2 text-center text-red-600 dark:text-red-400 font-black">{row.fail}</td>
                      <td className="py-2 text-center font-black text-[var(--accent-color)]">{row.rate}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* 待办事项 */}
          <div className="theme-card rounded-xl p-4 shadow-sm">
            <div className="flex justify-between items-center border-b border-[var(--border-color)] pb-2.5 mb-2.5 text-[var(--text-primary)]">
              <span className="text-xs font-black">待办事项</span>
              <span className="text-[11px] font-black text-[var(--text-secondary)]">待处理事项 {todoCount}</span>
            </div>

            <div className="space-y-2 overflow-y-auto max-h-[120px]">
              {visibleTodos.map((todo, idx) => (
                <div key={idx} className="flex items-center justify-between gap-2.5 text-left text-xs py-2 border-b border-[var(--border-color)] last:border-b-0 text-[var(--text-primary)]">
                  <div className="flex items-center gap-2 min-w-0">
                    <input 
                      type="checkbox" 
                      className="rounded border-[var(--border-color)] text-blue-600 focus:ring-blue-500 size-3 shrink-0 cursor-pointer bg-transparent"
                      style={{ accentColor: 'var(--accent-color)' }}
                    />
                    <span className="font-bold truncate">{todo.text}</span>
                  </div>
                  <span className={`px-2 py-0.5 border text-[10px] font-black rounded shrink-0 shadow-sm ${todo.priorityColor}`}>
                    {todo.priority}
                  </span>
                </div>
              ))}
            </div>
          </div>

        </div>

      </div>

    </div>
  );
}
