import React from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  CheckCircle,
  ClipboardList,
  Download,
  Edit3,
  FileText,
  Filter,
  Info,
  Layers,
  Plus,
  PlusSquare,
  RefreshCw,
  Save,
  Search,
  Settings,
  Sparkles,
  Star,
  Trash2
} from 'lucide-react';
import TiltCard from '../components/TiltCard';
import AnimatedNumber from '../components/AnimatedNumber';
import { apiDownload, apiGet, apiPost, apiRequest, formatDownloadError, formatDateTime, pickList } from '../lib/api';
import { useProjectContext } from '../lib/projectContext';

const SUPPORTED_DOWNLOAD_FORMATS = [
  { id: 'markdown', label: 'Markdown' },
  { id: 'html', label: 'HTML' },
  { id: 'json', label: 'JSON' }
];

const UNSUPPORTED_DOWNLOAD_FORMATS = [
  { id: 'pdf', label: 'PDF' },
  { id: 'word', label: 'Word' }
];

const REPORT_DOWNLOAD_FORMATS = [...SUPPORTED_DOWNLOAD_FORMATS, ...UNSUPPORTED_DOWNLOAD_FORMATS];

const DRILLDOWN_SECTIONS = [
  { id: 'requirements', label: '需求快照' },
  { id: 'executions', label: '执行快照' },
  { id: 'defects', label: '缺陷快照' },
  { id: 'api', label: '接口快照' },
  { id: 'automation', label: '自动化快照' },
  { id: 'performance', label: '性能快照' },
  { id: 'risks', label: '风险快照' }
];

const CONCLUSION_TYPES = [
  { id: 'daily', label: '测试日报', hint: '按当天/当前项目证据生成进展摘要' },
  { id: 'smoke', label: '提测反馈', hint: '面向研发/产品的提测质量反馈' },
  { id: 'release', label: '上线建议', hint: '基于缺陷、执行、接口、自动化和性能证据判断' },
  { id: 'risk', label: '风险清单', hint: '聚焦阻塞项、证据来源和下一步动作' }
];

const DEFAULT_TEMPLATE_SECTIONS = [
  { key: 'overview', name: '范围概览', order: 1, enabled: true },
  { key: 'requirements', name: '需求覆盖', order: 2, enabled: true },
  { key: 'executions', name: '执行结果', order: 3, enabled: true },
  { key: 'defects', name: '缺陷分析', order: 4, enabled: true },
  { key: 'risks', name: '风险与建议', order: 5, enabled: true }
];

const TEMPLATE_FORMAT_OPTIONS = [
  { id: 'markdown', label: 'Markdown' },
  { id: 'html', label: 'HTML' },
  { id: 'json', label: 'JSON' }
];

const EMPTY_FILTERS = {
  keyword: '',
  type: 'all',
  scope: '',
  dateFrom: '',
  dateTo: '',
  sort: 'latest'
};

const REPORT_TYPE_LABELS = {
  comprehensive: '综合报告',
  performance: '性能专项',
  lightweight: '轻量结论',
  lightweight_conclusion: '轻量结论',
  conclusion: '测试结论',
  daily: '测试日报',
  smoke: '提测反馈',
  release: '上线建议',
  risk: '风险清单'
};

const FIELD_LABELS = {
  id: 'ID',
  item_number: '需求编号',
  document_id: '来源文档',
  source_document_ids_json: '来源文档',
  requirement_item_id: '需求项',
  requirement_item_ids_json: '需求项',
  title: '标题',
  name: '名称',
  module: '模块',
  priority: '优先级',
  status: '状态',
  severity: '严重级别',
  case_id: '用例',
  case_number: '用例编号',
  defect_number: '缺陷编号',
  executor_type: '执行方式',
  executed_at: '执行时间',
  execution_time: '耗时',
  duration_ms: '耗时',
  actual_result: '实际结果',
  block_reason: '阻塞原因',
  skip_reason: '跳过原因',
  method: '方法',
  path: '路径',
  endpoint_id: '接口',
  case_type: '用例类型',
  run_type: '运行类型',
  error_message: '错误',
  auto_project_id: '自动化项目',
  plan_id: '性能计划',
  level: '等级',
  source: '来源',
  detail: '详情',
  template_version: '模板版本',
  report_type: '报告类型'
};

const SECTION_FIELDS = {
  requirements: ['item_number', 'title', 'module', 'priority', 'status', 'document_id'],
  executions: ['case_id', 'requirement_item_id', 'executor_type', 'status', 'actual_result', 'block_reason', 'skip_reason', 'executed_at'],
  defects: ['defect_number', 'title', 'severity', 'status', 'case_id', 'requirement_item_id', 'actual_result', 'remark'],
  api: ['name', 'method', 'path', 'run_type', 'status', 'duration_ms', 'error_message'],
  automation: ['name', 'auto_project_id', 'status', 'duration_ms', 'executed_at'],
  performance: ['name', 'plan_id', 'status', 'duration', 'executed_at'],
  risks: ['level', 'title', 'detail', 'source', 'status']
};

const showToast = (message, type = 'success') => {
  window.dispatchEvent(new CustomEvent('show-toast', { detail: { message, type } }));
};

const asObject = (value) => (value && typeof value === 'object' && !Array.isArray(value) ? value : {});

const asArray = (value) => {
  if (Array.isArray(value)) return value;
  const picked = pickList(value);
  if (picked.length) return picked;
  const obj = asObject(value);
  for (const key of ['data', 'items', 'list', 'records', 'rows', 'risks', 'risk_items']) {
    if (Array.isArray(obj[key])) return obj[key];
  }
  return [];
};

const textOf = (value, fallback = '') => {
  if (value === undefined || value === null || value === '') return fallback;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return fallback;
};

const numberOf = (value, fallback = 0) => {
  if (value === undefined || value === null || value === '') return fallback;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
};

const boolOf = (value, fallback = false) => {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  const normalized = String(value ?? '').toLowerCase();
  if (['true', '1', 'yes', 'on', 'enabled'].includes(normalized)) return true;
  if (['false', '0', 'no', 'off', 'disabled'].includes(normalized)) return false;
  return fallback;
};

const safeJsonText = (value) => {
  try {
    return JSON.stringify(value || {}, null, 0);
  } catch {
    return '';
  }
};

const formatCompactValue = (value) => {
  if (value === undefined || value === null || value === '') return '--';
  if (typeof value === 'number') return Number.isInteger(value) ? value.toLocaleString('zh-CN') : value.toFixed(2);
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (Array.isArray(value)) return value.length ? value.map(item => textOf(item, safeJsonText(item))).join('、') : '--';
  if (typeof value === 'object') return safeJsonText(value);
  return String(value);
};

const isNumericId = (value) => /^\d+$/.test(String(value || ''));

const normalizePercentValue = (value) => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  const normalized = numeric > 0 && numeric <= 1 ? numeric * 100 : numeric;
  return Math.max(0, Math.min(100, normalized));
};

const toPercentLabel = (value) => {
  const normalized = normalizePercentValue(value);
  if (normalized === null) return '--';
  return `${normalized.toFixed(normalized >= 99 ? 2 : 1)}%`;
};

const readSnapshot = (report = {}) => {
  const obj = asObject(report);
  return obj.data_snapshot || obj.dataSnapshot || {};
};

const readSourceRefs = (report = {}) => {
  const obj = asObject(report);
  return obj.source_refs_json || obj.sourceRefsJson || obj.source_refs || obj.sourceRefs || {};
};

const readScope = (report = {}) => {
  const obj = asObject(report);
  return obj.related_scope_json || obj.relatedScopeJson || obj.scope || {};
};

const readSummaryMetrics = (report = {}) => {
  const snapshot = readSnapshot(report);
  const summary = snapshot.summary_metrics || snapshot.summary || {};
  const defects = snapshot.defects || {};
  const defectSummary = defects.summary || {};
  const executions = snapshot.executions || {};
  const executionSummary = executions.summary || {};

  return {
    requirementCount: numberOf(summary.requirement_item_count ?? snapshot.requirements?.summary?.count, 0),
    sourceCount: numberOf(summary.source_document_count ?? snapshot.source_documents?.summary?.count, 0),
    testCaseCount: numberOf(summary.test_case_count ?? snapshot.test_cases?.summary?.count, 0),
    executionCount: numberOf(summary.execution_count ?? executionSummary.count, 0),
    executionPassRate: summary.execution_pass_rate ?? summary.pass_rate ?? summary.coverage_rate,
    apiPassRate: summary.api_pass_rate,
    autoPassRate: summary.auto_pass_rate,
    defectCount: numberOf(summary.defect_count ?? summary.defects ?? defectSummary.count ?? defects.total, 0),
    openDefectCount: numberOf(summary.open_defect_count ?? defectSummary.open ?? defectSummary.new ?? 0, 0),
    riskCount: asArray(snapshot.risk_items || snapshot.risks).filter(item => String(item?.level || '').toLowerCase() !== 'low').length,
    perfResultCount: numberOf(summary.perf_result_count ?? snapshot.perf?.summary?.results, 0)
  };
};

const reportTypeLabel = (value) => REPORT_TYPE_LABELS[String(value || '').toLowerCase()] || value || '未分类';

const statusLabel = (report) => {
  const rawStatus = textOf(report?.status, 'generated');
  const metrics = readSummaryMetrics(report);
  const passRate = normalizePercentValue(metrics.executionPassRate);
  if (rawStatus && rawStatus !== 'generated') return rawStatus;
  if (metrics.riskCount > 0 || metrics.openDefectCount > 0) return '需复核';
  if (passRate !== null && passRate >= 95) return '可归档';
  if (passRate !== null && passRate > 0) return '需关注';
  return '已生成';
};

const statusBadgeClass = (status = '') => {
  const normalized = String(status).toLowerCase();
  if (['可归档', 'passed', 'pass', 'success', 'generated'].some(item => normalized.includes(item.toLowerCase()))) {
    return 'text-emerald-600 bg-emerald-500/10 border-emerald-500/20';
  }
  if (['需复核', 'fail', 'failed', 'error', 'block'].some(item => normalized.includes(item.toLowerCase()))) {
    return 'text-red-600 bg-red-500/10 border-red-500/20';
  }
  return 'text-amber-600 bg-amber-500/10 border-amber-500/20';
};

const riskBadgeClass = (level = '') => {
  const normalized = String(level || '').toLowerCase();
  if (['critical', 'fatal', 'blocker', 'high'].includes(normalized)) return 'text-red-600 bg-red-500/10 border-red-500/20';
  if (['medium', 'warning', 'major'].includes(normalized)) return 'text-amber-600 bg-amber-500/10 border-amber-500/20';
  return 'text-emerald-600 bg-emerald-500/10 border-emerald-500/20';
};

const readReportDateMs = (report = {}) => {
  const value = report.generated_at || report.generatedAt || report.created_at || report.createdAt || report.updated_at || report.updatedAt;
  const date = value ? new Date(value) : null;
  if (date && !Number.isNaN(date.getTime())) return date.getTime();
  return numberOf(report.id, 0);
};

const mapBackendReport = (report) => {
  const raw = asObject(report?.report || report);
  const metrics = readSummaryMetrics(raw);
  const sourceRefs = readSourceRefs(raw);
  const requirementIds = raw.requirement_item_ids_json || raw.requirementItemIdsJson || sourceRefs.requirement_item_ids || [];
  const sourceDocumentIds = raw.source_document_ids_json || raw.sourceDocumentIdsJson || sourceRefs.source_document_ids || [];
  const generatedAt = raw.generated_at || raw.generatedAt || raw.created_at || raw.createdAt || raw.updated_at || raw.updatedAt;
  const passRate = normalizePercentValue(metrics.executionPassRate);

  return {
    id: String(raw.id),
    raw,
    name: raw.name || raw.title || `报告 #${raw.id}`,
    type: raw.type || raw.report_type || 'comprehensive',
    typeLabel: reportTypeLabel(raw.type || raw.report_type || 'comprehensive'),
    generatedAt,
    generatedAtMs: readReportDateMs(raw),
    dateLabel: formatDateTime(generatedAt),
    passRate,
    passRateLabel: toPercentLabel(metrics.executionPassRate),
    defectCount: metrics.defectCount,
    openDefectCount: metrics.openDefectCount,
    riskCount: metrics.riskCount,
    requirementIds: Array.isArray(requirementIds) ? requirementIds : [],
    sourceDocumentIds: Array.isArray(sourceDocumentIds) ? sourceDocumentIds : [],
    templateId: raw.template_id || raw.templateId || '',
    templateVersion: raw.template_version || raw.templateVersion || '',
    status: statusLabel(raw),
    content: raw.content || ''
  };
};

const sectionLabel = (key) => {
  const matched = DRILLDOWN_SECTIONS.find(item => item.id === key);
  if (matched) return matched.label;
  const templateMatch = DEFAULT_TEMPLATE_SECTIONS.find(item => item.key === key);
  return templateMatch?.name || key || '未命名段落';
};

const normalizeTemplateSections = (sections) => {
  const source = Array.isArray(sections) && sections.length ? sections : [];
  return source.map((item, index) => {
    if (typeof item === 'string') {
      return { key: item, name: sectionLabel(item), order: index + 1, enabled: true };
    }
    const obj = asObject(item);
    const key = textOf(obj.key ?? obj.id ?? obj.code ?? obj.name, `section_${index + 1}`);
    return {
      key,
      name: textOf(obj.name ?? obj.label ?? obj.title, sectionLabel(key)),
      order: numberOf(obj.order ?? obj.sort_order ?? obj.sortOrder, index + 1),
      enabled: boolOf(obj.enabled ?? obj.is_enabled ?? obj.visible, true)
    };
  }).sort((a, b) => a.order - b.order);
};

const normalizeSupportedFormats = (template) => {
  const raw = template.supported_formats || template.supportedFormats || template.formats || template.output_formats;
  const formats = Array.isArray(raw) ? raw : [];
  return formats.length ? formats.map(item => String(item).toLowerCase()) : SUPPORTED_DOWNLOAD_FORMATS.map(item => item.id);
};

const mapBackendTemplate = (template) => {
  const raw = asObject(template);
  const sections = normalizeTemplateSections(raw.sections);
  return {
    id: String(raw.id),
    raw,
    name: raw.name || `模板 #${raw.id}`,
    reportType: raw.report_type || raw.reportType || raw.type || 'comprehensive',
    enabled: boolOf(raw.enabled ?? raw.is_enabled ?? raw.isEnabled, true),
    isDefault: boolOf(raw.is_default ?? raw.isDefault, false),
    templateVersion: raw.template_version || raw.templateVersion || 'v1',
    sections,
    supportedFormats: normalizeSupportedFormats(raw),
    updatedAt: raw.updated_at || raw.updatedAt || raw.created_at || raw.createdAt
  };
};

const emptyTemplateDraft = () => ({
  id: '',
  name: '',
  reportType: 'comprehensive',
  enabled: true,
  isDefault: false,
  templateVersion: 'v1',
  supportedFormats: SUPPORTED_DOWNLOAD_FORMATS.map(item => item.id),
  sections: DEFAULT_TEMPLATE_SECTIONS.map(item => ({ ...item }))
});

const templateToDraft = (template) => ({
  id: template?.id || '',
  name: template?.name || '',
  reportType: template?.reportType || 'comprehensive',
  enabled: template?.enabled ?? true,
  isDefault: template?.isDefault ?? false,
  templateVersion: template?.templateVersion || 'v1',
  supportedFormats: template?.supportedFormats?.length ? [...template.supportedFormats] : SUPPORTED_DOWNLOAD_FORMATS.map(item => item.id),
  sections: template?.sections?.length ? template.sections.map(item => ({ ...item })) : DEFAULT_TEMPLATE_SECTIONS.map(item => ({ ...item }))
});

const serializeTemplateSections = (sections) => sections
  .map((item, index) => ({
    key: textOf(item.key, `section_${index + 1}`).trim() || `section_${index + 1}`,
    name: textOf(item.name, sectionLabel(item.key)).trim() || sectionLabel(item.key),
    order: numberOf(item.order, index + 1),
    enabled: boolOf(item.enabled, true)
  }))
  .sort((a, b) => a.order - b.order);

const normalizeRiskItems = (payload, report) => {
  const snapshotRisks = asArray(readSnapshot(report?.raw || report).risk_items || readSnapshot(report?.raw || report).risks);
  const payloadList = asArray(payload).length
    ? asArray(payload)
    : asArray(payload?.risks || payload?.risk_items || payload?.items);
  const source = payloadList.length ? payloadList : snapshotRisks;

  return source.map((item, index) => {
    const obj = asObject(item);
    const id = textOf(obj.id ?? obj.risk_id ?? obj.riskId ?? obj.code, `${obj.source || 'risk'}-${index + 1}-${obj.title || 'item'}`);
    return {
      id,
      level: textOf(obj.level ?? obj.severity ?? obj.priority, 'low'),
      title: textOf(obj.title ?? obj.name, '未命名风险'),
      detail: textOf(obj.detail ?? obj.description ?? obj.message, '后端未返回风险详情'),
      source: textOf(obj.source ?? obj.module, 'report'),
      status: textOf(obj.status ?? obj.todo_status ?? obj.todoStatus, obj.todo_id || obj.todoId ? 'todo_created' : 'open'),
      todoId: obj.todo_id ?? obj.todoId ?? obj.task_id ?? obj.taskId,
      evidence: obj.evidence || obj.source_refs || obj.sourceRefs || {},
      raw: obj
    };
  });
};

const normalizeSnapshotItems = (section, snapshot) => {
  if (section === 'requirements') return asArray(snapshot.requirements?.items);
  if (section === 'executions') return asArray(snapshot.executions?.items);
  if (section === 'defects') return asArray(snapshot.defects?.items);
  if (section === 'risks') return asArray(snapshot.risk_items || snapshot.risks);
  if (section === 'api') {
    return [
      ...asArray(snapshot.api?.libs).map(item => ({ ...item, kind: '接口库' })),
      ...asArray(snapshot.api?.endpoints).map(item => ({ ...item, kind: '接口' })),
      ...asArray(snapshot.api?.test_cases).map(item => ({ ...item, kind: '接口用例' })),
      ...asArray(snapshot.api?.executions).map(item => ({ ...item, kind: '接口执行' }))
    ];
  }
  if (section === 'automation') {
    return [
      ...asArray(snapshot.auto?.projects).map(item => ({ ...item, kind: '自动化项目' })),
      ...asArray(snapshot.auto?.executions || snapshot.auto_executions).map(item => ({ ...item, kind: '自动化执行' }))
    ];
  }
  if (section === 'performance') {
    return [
      ...asArray(snapshot.perf?.plans || snapshot.performance_plans).map(item => ({ ...item, kind: '性能计划' })),
      ...asArray(snapshot.perf?.results || snapshot.performance_results).map(item => ({ ...item, kind: '性能结果' }))
    ];
  }
  return [];
};

const normalizeSnapshotSummary = (section, snapshot) => {
  if (section === 'requirements') return snapshot.requirements?.summary || {};
  if (section === 'executions') return snapshot.executions?.summary || snapshot.execution_summary || {};
  if (section === 'defects') return snapshot.defects?.summary || snapshot.defect_summary || {};
  if (section === 'api') return snapshot.api?.summary || snapshot.api_summary || {};
  if (section === 'automation') return snapshot.auto?.summary || snapshot.automation_summary || {};
  if (section === 'performance') return snapshot.perf?.summary || snapshot.performance_summary || {};
  if (section === 'risks') {
    const risks = asArray(snapshot.risk_items || snapshot.risks);
    return risks.reduce((acc, item) => {
      const level = String(item?.level || 'unknown');
      acc.total += 1;
      acc[level] = (acc[level] || 0) + 1;
      return acc;
    }, { total: 0 });
  }
  return {};
};

const normalizeDrilldownPayload = (payload, section, report) => {
  const raw = asObject(payload?.drilldown || payload?.data || payload);
  const snapshot = readSnapshot(report?.raw || report);
  const items = asArray(raw.items || raw.list || raw.records || raw[section]).length
    ? asArray(raw.items || raw.list || raw.records || raw[section])
    : normalizeSnapshotItems(section, snapshot);

  return {
    section,
    summary: asObject(raw.summary || raw.metrics || normalizeSnapshotSummary(section, snapshot)),
    items,
    evidence: asObject(raw.evidence || raw.source_refs || raw.sourceRefs || readSourceRefs(report?.raw || report)),
    source: textOf(raw.source, payload ? 'api' : 'report_snapshot'),
    raw
  };
};

const buildSnapshotDrilldown = (section, report) => normalizeDrilldownPayload(null, section, report);

const itemTitle = (item, index) => {
  const obj = asObject(item);
  return textOf(
    obj.title ?? obj.name ?? obj.case_number ?? obj.defect_number ?? obj.item_number ?? obj.path ?? obj.id,
    `记录 #${index + 1}`
  );
};

const itemSubtitle = (item) => {
  const obj = asObject(item);
  return [
    obj.kind,
    obj.module,
    obj.status,
    obj.priority || obj.severity,
    obj.source
  ].filter(Boolean).map(String).join(' / ');
};

const evidenceEntries = (evidence = {}) => {
  const obj = asObject(evidence);
  const countEntries = Object.entries(asObject(obj.counts)).map(([key, value]) => ({ key, value, countOnly: true }));
  const idEntries = Object.entries(obj)
    .filter(([, value]) => Array.isArray(value) && value.length)
    .map(([key, value]) => ({ key, value: value.slice(0, 10), countOnly: false }));
  return [...countEntries, ...idEntries].slice(0, 8);
};

const compactListText = (values = []) => values.map(item => String(item)).join('、');

function EmptyState({ title, description, action }) {
  return (
    <div className="min-h-[180px] rounded-xl border border-dashed border-[var(--border-color)] bg-[var(--border-color)]/10 p-6 flex flex-col items-center justify-center text-center">
      <Info className="size-7 text-[var(--text-secondary)] opacity-60" />
      <div className="mt-3 text-xs font-bold text-[var(--text-primary)]">{title}</div>
      <div className="mt-1 max-w-md text-[10px] leading-relaxed text-[var(--text-secondary)]">{description}</div>
      {action}
    </div>
  );
}

function StatusPill({ children, className = '' }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[9px] font-bold ${className}`}>
      {children}
    </span>
  );
}

export default function Reports() {
  const { selectedProject, loading: projectLoading, error: projectError } = useProjectContext();
  const [viewMode, setViewMode] = React.useState('list');
  const [reports, setReports] = React.useState([]);
  const [selectedReportId, setSelectedReportId] = React.useState('');
  const [reportStatus, setReportStatus] = React.useState({ loading: true, error: '' });
  const [filters, setFilters] = React.useState(EMPTY_FILTERS);
  const [templates, setTemplates] = React.useState([]);
  const [templateStatus, setTemplateStatus] = React.useState({ loading: true, error: '' });
  const [selectedTemplateId, setSelectedTemplateId] = React.useState('');
  const [templateDraft, setTemplateDraft] = React.useState(emptyTemplateDraft);
  const [isSavingTemplate, setIsSavingTemplate] = React.useState(false);
  const [isGeneratingReport, setIsGeneratingReport] = React.useState(false);
  const [isDownloadingReport, setIsDownloadingReport] = React.useState(false);
  const [newReportType, setNewReportType] = React.useState('comprehensive');
  const [newReportTitle, setNewReportTitle] = React.useState('');
  const [activeDrilldownSection, setActiveDrilldownSection] = React.useState('requirements');
  const [drilldownState, setDrilldownState] = React.useState({ loading: false, error: '', unsupported: false, data: null });
  const [riskState, setRiskState] = React.useState({ loading: false, error: '', unsupported: false, items: [] });
  const [riskActionState, setRiskActionState] = React.useState({});
  const [conclusionType, setConclusionType] = React.useState('release');
  const [conclusionResult, setConclusionResult] = React.useState(null);
  const [conclusionState, setConclusionState] = React.useState({ loading: false, error: '' });
  const [conclusionTitle, setConclusionTitle] = React.useState('');

  const selectedReport = React.useMemo(
    () => reports.find(report => String(report.id) === String(selectedReportId)) || null,
    [reports, selectedReportId]
  );

  const reportTypes = React.useMemo(() => {
    const unique = new Map();
    reports.forEach((report) => unique.set(report.type, report.typeLabel));
    return [...unique.entries()].map(([id, label]) => ({ id, label }));
  }, [reports]);

  const visibleReports = React.useMemo(() => {
    const keyword = filters.keyword.trim().toLowerCase();
    const scopeKeyword = filters.scope.trim().toLowerCase();
    const fromMs = filters.dateFrom ? new Date(`${filters.dateFrom}T00:00:00`).getTime() : null;
    const toMs = filters.dateTo ? new Date(`${filters.dateTo}T23:59:59`).getTime() : null;

    return reports
      .filter((report) => {
        if (filters.type !== 'all' && report.type !== filters.type) return false;
        if (keyword) {
          const haystack = [
            report.name,
            report.typeLabel,
            report.status,
            report.content,
            report.templateVersion
          ].join(' ').toLowerCase();
          if (!haystack.includes(keyword)) return false;
        }
        if (scopeKeyword) {
          const raw = report.raw || {};
          const scopeText = [
            compactListText(report.requirementIds),
            compactListText(report.sourceDocumentIds),
            raw.related_module,
            safeJsonText(readScope(raw)),
            safeJsonText(readSourceRefs(raw))
          ].join(' ').toLowerCase();
          if (!scopeText.includes(scopeKeyword)) return false;
        }
        if (fromMs && report.generatedAtMs < fromMs) return false;
        if (toMs && report.generatedAtMs > toMs) return false;
        return true;
      })
      .sort((a, b) => {
        if (filters.sort === 'oldest') return a.generatedAtMs - b.generatedAtMs;
        if (filters.sort === 'pass_desc') return numberOf(b.passRate, -1) - numberOf(a.passRate, -1);
        if (filters.sort === 'pass_asc') return numberOf(a.passRate, 101) - numberOf(b.passRate, 101);
        if (filters.sort === 'defects_desc') return b.defectCount - a.defectCount;
        if (filters.sort === 'defects_asc') return a.defectCount - b.defectCount;
        if (filters.sort === 'name') return a.name.localeCompare(b.name, 'zh-CN');
        return b.generatedAtMs - a.generatedAtMs;
      });
  }, [reports, filters]);

  const selectedMetrics = React.useMemo(
    () => readSummaryMetrics(selectedReport?.raw || {}),
    [selectedReport]
  );

  const totalDefects = React.useMemo(
    () => reports.reduce((sum, report) => sum + numberOf(report.defectCount, 0), 0),
    [reports]
  );

  const defaultTemplate = React.useMemo(
    () => templates.find(template => template.isDefault) || templates[0] || null,
    [templates]
  );

  const loadReports = React.useCallback(async () => {
    setReportStatus({ loading: true, error: '' });
    try {
      if (projectLoading) return;
      if (!selectedProject?.id) {
        setReports([]);
        setSelectedReportId('');
        setReportStatus({
          loading: false,
          error: projectError || '当前没有可用项目，报告中心不会展示演示数据。'
        });
        return;
      }

      const payload = await apiGet(`/projects/${selectedProject.id}/reports`, { params: { page: 1, pageSize: 100 } });
      const mapped = pickList(payload).map(mapBackendReport);
      setReports(mapped);
      setSelectedReportId(current => (mapped.some(report => report.id === current) ? current : mapped[0]?.id || ''));
      setReportStatus({ loading: false, error: '' });
    } catch (error) {
      setReports([]);
      setSelectedReportId('');
      setReportStatus({ loading: false, error: error?.message || '报告列表加载失败。' });
    }
  }, [projectLoading, projectError, selectedProject]);

  const loadTemplates = React.useCallback(async () => {
    setTemplateStatus({ loading: true, error: '' });
    try {
      const payload = await apiGet('/report-templates', { params: { page: 1, pageSize: 100 } });
      const mapped = pickList(payload).map(mapBackendTemplate);
      setTemplates(mapped);
      setSelectedTemplateId(current => (mapped.some(template => template.id === current) ? current : (mapped.find(template => template.isDefault)?.id || mapped[0]?.id || '')));
      setTemplateStatus({ loading: false, error: '' });
    } catch (error) {
      setTemplates([]);
      setSelectedTemplateId('');
      setTemplateStatus({ loading: false, error: error?.message || '报告模板加载失败。' });
    }
  }, []);

  React.useEffect(() => {
    loadReports();
  }, [loadReports]);

  React.useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  React.useEffect(() => {
    if (!visibleReports.length) return;
    if (!visibleReports.some(report => report.id === selectedReportId)) {
      setSelectedReportId(visibleReports[0].id);
    }
  }, [visibleReports, selectedReportId]);

  React.useEffect(() => {
    let cancelled = false;
    async function loadReportDetail() {
      if (!selectedReportId || !isNumericId(selectedReportId)) return;
      try {
        const detail = await apiGet(`/reports/${selectedReportId}`);
        if (cancelled) return;
        const mapped = mapBackendReport(detail);
        setReports(current => current.map(report => (report.id === mapped.id ? mapped : report)));
      } catch {
        // 列表接口已包含可展示字段；详情刷新失败时保留列表数据。
      }
    }
    loadReportDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedReport]);

  React.useEffect(() => {
    let cancelled = false;
    async function loadRisks() {
      if (!selectedReport) {
        setRiskState({ loading: false, error: '', unsupported: false, items: [] });
        return;
      }
      setRiskState({ loading: true, error: '', unsupported: false, items: normalizeRiskItems(null, selectedReport) });
      if (!isNumericId(selectedReport.id)) {
        setRiskState({ loading: false, error: '', unsupported: false, items: normalizeRiskItems(null, selectedReport) });
        return;
      }
      try {
        const payload = await apiGet(`/reports/${selectedReport.id}/risks`);
        if (cancelled) return;
        setRiskState({
          loading: false,
          error: '',
          unsupported: false,
          items: normalizeRiskItems(payload, selectedReport)
        });
      } catch (error) {
        if (cancelled) return;
        const snapshotItems = normalizeRiskItems(null, selectedReport);
        setRiskState({
          loading: false,
          error: error?.status === 404 || error?.status === 405
            ? '后端暂未开放 /reports/{id}/risks，当前展示报告 data_snapshot.risk_items。'
            : error?.message || '风险列表读取失败，当前展示报告快照。 ',
          unsupported: error?.status === 404 || error?.status === 405,
          items: snapshotItems
        });
      }
    }
    loadRisks();
    return () => {
      cancelled = true;
    };
  }, [selectedReportId]);

  React.useEffect(() => {
    let cancelled = false;
    async function loadDrilldown() {
      if (viewMode !== 'report-detail' || !selectedReport) return;
      const snapshotData = buildSnapshotDrilldown(activeDrilldownSection, selectedReport);
      setDrilldownState({ loading: true, error: '', unsupported: false, data: snapshotData });
      if (!isNumericId(selectedReport.id)) {
        setDrilldownState({ loading: false, error: '', unsupported: false, data: snapshotData });
        return;
      }
      try {
        const payload = await apiGet(`/reports/${selectedReport.id}/drilldown`, { params: { section: activeDrilldownSection } });
        if (cancelled) return;
        setDrilldownState({
          loading: false,
          error: '',
          unsupported: false,
          data: normalizeDrilldownPayload(payload, activeDrilldownSection, selectedReport)
        });
      } catch (error) {
        if (cancelled) return;
        setDrilldownState({
          loading: false,
          error: error?.status === 404 || error?.status === 405
            ? '后端暂未开放 drilldown API，当前展示报告 data_snapshot 快照。'
            : error?.message || '下钻明细读取失败，当前展示报告快照。',
          unsupported: error?.status === 404 || error?.status === 405,
          data: snapshotData
        });
      }
    }
    loadDrilldown();
    return () => {
      cancelled = true;
    };
  }, [viewMode, selectedReport, activeDrilldownSection]);

  const updateFilter = (key, value) => setFilters(current => ({ ...current, [key]: value }));

  const handleDownloadReport = async (format) => {
    if (!REPORT_DOWNLOAD_FORMATS.some(item => item.id === format)) {
      showToast(`不支持 ${format} 报告下载。`, 'error');
      return;
    }
    if (!selectedReport?.id || !isNumericId(selectedReport.id)) {
      showToast('当前没有可下载的真实后端报告。', 'error');
      return;
    }

    setIsDownloadingReport(true);
    try {
      await apiDownload(`/reports/${selectedReport.id}/download`, {
        params: { format },
        format,
        timeoutMs: 15000,
        defaultFilename: `report-${selectedReport.id}${format === 'markdown' ? '.md' : format === 'word' ? '.docx' : `.${format}`}`
      });
      showToast(`${format.toUpperCase()} 报告已开始下载。`);
    } catch (error) {
      showToast(formatDownloadError(error, '报告下载失败。'), 'error');
    } finally {
      setIsDownloadingReport(false);
    }
  };

  const handleCreateReport = async () => {
    if (!selectedProject?.id) {
      showToast('当前没有可用项目，无法生成真实报告。', 'error');
      return;
    }

    setIsGeneratingReport(true);
    try {
      const title = newReportTitle.trim() || `${selectedProject.name || `项目 ${selectedProject.id}`} ${reportTypeLabel(newReportType)}`;
      const payload = {
        project_id: selectedProject.id,
        title,
        name: title,
        type: newReportType,
        template_id: selectedTemplateId || undefined,
        scope: { project_id: selectedProject.id }
      };
      const created = await apiPost('/reports/comprehensive', payload);
      const mapped = mapBackendReport(created.report || created);
      setReports(current => [mapped, ...current.filter(item => item.id !== mapped.id)]);
      setSelectedReportId(mapped.id);
      setReportStatus({ loading: false, error: '' });
      setNewReportTitle('');
      showToast('报告已由后端聚合生成。');
    } catch (error) {
      showToast(error?.message || '报告生成失败。', 'error');
    } finally {
      setIsGeneratingReport(false);
    }
  };

  const handleEditTemplate = (template) => {
    setTemplateDraft(templateToDraft(template));
    setViewMode('template-manage');
  };

  const handleNewTemplate = () => {
    setTemplateDraft(emptyTemplateDraft());
    setViewMode('template-manage');
  };

  const handleSaveTemplate = async () => {
    if (!templateDraft.name.trim()) {
      showToast('请填写模板名称。', 'error');
      return;
    }
    setIsSavingTemplate(true);
    try {
      const payload = {
        name: templateDraft.name.trim(),
        report_type: templateDraft.reportType,
        type: templateDraft.reportType,
        enabled: templateDraft.enabled,
        is_default: templateDraft.isDefault,
        template_version: templateDraft.templateVersion || 'v1',
        supported_formats: templateDraft.supportedFormats,
        sections: serializeTemplateSections(templateDraft.sections)
      };

      if (templateDraft.id) {
        await apiRequest(`/report-templates/${templateDraft.id}`, { method: 'PATCH', body: payload });
        showToast('报告模板已更新。');
      } else {
        const created = await apiPost('/report-templates', payload);
        const mapped = mapBackendTemplate(created);
        setTemplateDraft(templateToDraft(mapped));
        setSelectedTemplateId(mapped.id);
        showToast('报告模板已创建。');
      }
      await loadTemplates();
    } catch (error) {
      showToast(error?.message || '模板保存失败。', 'error');
    } finally {
      setIsSavingTemplate(false);
    }
  };

  const handleDeleteTemplate = async (template) => {
    if (!template?.id) return;
    setIsSavingTemplate(true);
    try {
      await apiRequest(`/report-templates/${template.id}`, { method: 'DELETE' });
      if (templateDraft.id === template.id) setTemplateDraft(emptyTemplateDraft());
      showToast('报告模板已删除。');
      await loadTemplates();
    } catch (error) {
      showToast(error?.message || '模板删除失败。', 'error');
    } finally {
      setIsSavingTemplate(false);
    }
  };

  const handleSetDefaultTemplate = async (template) => {
    if (!template?.id) return;
    setIsSavingTemplate(true);
    try {
      const sameTypeTemplates = templates.filter(item => item.reportType === template.reportType && item.id !== template.id);
      await Promise.all(sameTypeTemplates.map(item => apiRequest(`/report-templates/${item.id}`, { method: 'PATCH', body: { is_default: false } }).catch(() => null)));
      await apiRequest(`/report-templates/${template.id}`, { method: 'PATCH', body: { is_default: true, enabled: true } });
      setSelectedTemplateId(template.id);
      showToast('默认模板已更新。');
      await loadTemplates();
    } catch (error) {
      showToast(error?.message || '设置默认模板失败。', 'error');
    } finally {
      setIsSavingTemplate(false);
    }
  };

  const handleRiskToTodo = async (risk) => {
    if (!selectedReport?.id || !isNumericId(selectedReport.id)) {
      showToast('当前没有可操作的真实报告。', 'error');
      return;
    }

    const riskId = String(risk.id || risk.title);
    setRiskActionState(current => ({ ...current, [riskId]: { loading: true, message: '' } }));
    const payload = {
      action: 'convert_to_todo',
      risk_id: riskId,
      risk,
      source: 'reports_center'
    };

    try {
      let result;
      try {
        result = await apiRequest(`/reports/${selectedReport.id}/risks`, { method: 'PATCH', body: payload });
      } catch (patchError) {
        if (![404, 405].includes(patchError?.status)) throw patchError;
        result = await apiPost(`/reports/${selectedReport.id}/risks/${encodeURIComponent(riskId)}/todo`, payload);
      }

      const message = result?.message
        || result?.status
        || (result?.already_exists || result?.idempotent ? '待办已存在，已返回现有记录。' : '风险已转为待办。');
      const todoId = result?.todo_id || result?.todoId || result?.task_id || result?.taskId;
      setRiskActionState(current => ({ ...current, [riskId]: { loading: false, message, result } }));
      setRiskState(current => ({
        ...current,
        items: current.items.map(item => item.id === riskId ? { ...item, status: message, todoId: todoId || item.todoId } : item)
      }));
      showToast(message);
    } catch (error) {
      const unsupported = [404, 405].includes(error?.status);
      const message = unsupported
        ? '后端暂未开放风险转待办接口，未做本地假成功。'
        : error?.message || '风险转待办失败。';
      setRiskActionState(current => ({ ...current, [riskId]: { loading: false, message, error: true } }));
      showToast(message, unsupported ? 'info' : 'error');
    }
  };

  const handleGenerateConclusion = async ({ save = false, nextType = conclusionType } = {}) => {
    if (!selectedProject?.id) {
      setConclusionResult(null);
      setConclusionState({ loading: false, error: '当前没有可用项目，无法生成真实轻量结论。' });
      showToast('当前没有可用项目，无法生成真实轻量结论。', 'error');
      return;
    }

    setConclusionState({ loading: true, error: '' });
    try {
      const result = await apiPost('/reports/lightweight-conclusions', {
        project_id: selectedProject.id,
        type: nextType,
        save,
        title: save ? (conclusionTitle.trim() || `${selectedProject.name || `项目 ${selectedProject.id}`} ${reportTypeLabel(nextType)}`) : undefined
      });
      setConclusionResult(result);
      if (result.report) {
        const mapped = mapBackendReport(result.report);
        setReports(current => [mapped, ...current.filter(item => item.id !== mapped.id)]);
        setSelectedReportId(mapped.id);
      }
      setConclusionState({ loading: false, error: '' });
      showToast(save ? '轻量结论已归档为后端报告。' : '轻量结论已由后端生成。');
    } catch (error) {
      setConclusionState({ loading: false, error: error?.message || '轻量结论生成失败。' });
      showToast(error?.message || '轻量结论生成失败。', 'error');
    }
  };

  const handleOpenConclusion = () => {
    setViewMode('lightweight-conclusion');
    setConclusionResult(null);
    setConclusionState({ loading: false, error: '' });
    if (selectedProject?.id) {
      handleGenerateConclusion({ save: false, nextType: conclusionType });
    }
  };

  const updateDraftSection = (index, patch) => {
    setTemplateDraft(current => ({
      ...current,
      sections: current.sections.map((section, sectionIndex) => sectionIndex === index ? { ...section, ...patch } : section)
    }));
  };

  const removeDraftSection = (index) => {
    setTemplateDraft(current => ({
      ...current,
      sections: current.sections.filter((_, sectionIndex) => sectionIndex !== index)
    }));
  };

  const addDraftSection = () => {
    setTemplateDraft(current => ({
      ...current,
      sections: [
        ...current.sections,
        { key: `section_${current.sections.length + 1}`, name: '新段落', order: current.sections.length + 1, enabled: true }
      ]
    }));
  };

  const toggleDraftFormat = (format) => {
    setTemplateDraft(current => {
      const exists = current.supportedFormats.includes(format);
      const next = exists
        ? current.supportedFormats.filter(item => item !== format)
        : [...current.supportedFormats, format];
      return { ...current, supportedFormats: next.length ? next : ['markdown'] };
    });
  };

  const renderSummaryCards = () => {
    const latest = reports[0];
    const latestRate = latest?.passRateLabel || '--';
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 flex-shrink-0">
        <div className="theme-card rounded-xl p-4 flex flex-col justify-between border min-h-[96px]">
          <div className="flex items-center justify-between text-[10px] opacity-70 text-[var(--text-secondary)] font-medium">
            <span>真实报告总数</span>
            <FileText className="size-3.5 text-blue-500" />
          </div>
          <div className="mt-2">
            <span className="text-xl font-black text-[var(--text-primary)] leading-tight"><AnimatedNumber value={reports.length} /> 份</span>
            <div className="text-[9px] text-[var(--text-secondary)] mt-1">{selectedProject?.name || '未选择项目'}</div>
          </div>
        </div>

        <div className="theme-card rounded-xl p-4 flex flex-col justify-between border min-h-[96px]">
          <div className="flex items-center justify-between text-[10px] opacity-70 text-[var(--text-secondary)] font-medium">
            <span>最新报告通过率</span>
            <CheckCircle className="size-3.5 text-emerald-500" />
          </div>
          <div className="mt-2">
            <span className="text-xl font-black text-emerald-500 leading-tight">{latestRate}</span>
            <div className="text-[9px] text-[var(--text-secondary)] mt-1">来自最新后端报告快照</div>
          </div>
        </div>

        <div className="theme-card rounded-xl p-4 flex flex-col justify-between border min-h-[96px]">
          <div className="flex items-center justify-between text-[10px] opacity-70 text-[var(--text-secondary)] font-medium">
            <span>累计缺陷记录</span>
            <AlertTriangle className="size-3.5 text-amber-500" />
          </div>
          <div className="mt-2">
            <span className="text-xl font-black text-red-500 leading-tight"><AnimatedNumber value={totalDefects} /> 个</span>
            <div className="text-[9px] text-[var(--text-secondary)] mt-1">按当前报告列表聚合</div>
          </div>
        </div>

        <div className="theme-card rounded-xl p-4 flex flex-col justify-between border min-h-[96px]">
          <div className="flex items-center justify-between text-[10px] opacity-70 text-[var(--text-secondary)] font-medium">
            <span>可用报告模板</span>
            <Layers className="size-3.5 text-purple-500" />
          </div>
          <div className="mt-2">
            <span className="text-xl font-black text-[var(--text-primary)] leading-tight"><AnimatedNumber value={templates.length} /> 个</span>
            <div className="text-[9px] text-[var(--text-secondary)] mt-1">默认：{defaultTemplate?.name || '后端默认'}</div>
          </div>
        </div>
      </div>
    );
  };

  const renderFilters = () => (
    <div className="theme-card rounded-xl p-3 shadow-sm border border-[var(--border-color)]">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-2 items-end">
        <label className="lg:col-span-3 text-[9px] font-bold text-[var(--text-secondary)]">
          关键词
          <div className="mt-1 flex items-center gap-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-2">
            <Search className="size-3.5 text-[var(--text-secondary)]" />
            <input
              value={filters.keyword}
              onChange={(event) => updateFilter('keyword', event.target.value)}
              placeholder="报告名称 / 状态 / 正文"
              className="min-w-0 flex-1 bg-transparent py-1.5 text-[10px] text-[var(--text-primary)] outline-none"
            />
          </div>
        </label>

        <label className="lg:col-span-2 text-[9px] font-bold text-[var(--text-secondary)]">
          报告类型
          <select
            value={filters.type}
            onChange={(event) => updateFilter('type', event.target.value)}
            className="mt-1 w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1.5 text-[10px] text-[var(--text-primary)] outline-none"
          >
            <option value="all">全部类型</option>
            {reportTypes.map(type => <option key={type.id} value={type.id}>{type.label}</option>)}
          </select>
        </label>

        <label className="lg:col-span-2 text-[9px] font-bold text-[var(--text-secondary)]">
          需求项/来源
          <input
            value={filters.scope}
            onChange={(event) => updateFilter('scope', event.target.value)}
            placeholder="REQ ID / 文档 ID / 来源"
            className="mt-1 w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1.5 text-[10px] text-[var(--text-primary)] outline-none"
          />
        </label>

        <label className="lg:col-span-1 text-[9px] font-bold text-[var(--text-secondary)]">
          开始
          <input
            type="date"
            value={filters.dateFrom}
            onChange={(event) => updateFilter('dateFrom', event.target.value)}
            className="mt-1 w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1.5 text-[10px] text-[var(--text-primary)] outline-none"
          />
        </label>

        <label className="lg:col-span-1 text-[9px] font-bold text-[var(--text-secondary)]">
          结束
          <input
            type="date"
            value={filters.dateTo}
            onChange={(event) => updateFilter('dateTo', event.target.value)}
            className="mt-1 w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1.5 text-[10px] text-[var(--text-primary)] outline-none"
          />
        </label>

        <label className="lg:col-span-2 text-[9px] font-bold text-[var(--text-secondary)]">
          排序
          <select
            value={filters.sort}
            onChange={(event) => updateFilter('sort', event.target.value)}
            className="mt-1 w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1.5 text-[10px] text-[var(--text-primary)] outline-none"
          >
            <option value="latest">最新生成优先</option>
            <option value="oldest">最早生成优先</option>
            <option value="pass_desc">通过率从高到低</option>
            <option value="pass_asc">通过率从低到高</option>
            <option value="defects_desc">缺陷数从高到低</option>
            <option value="defects_asc">缺陷数从低到高</option>
            <option value="name">按名称排序</option>
          </select>
        </label>

        <button
          onClick={() => setFilters(EMPTY_FILTERS)}
          className="lg:col-span-1 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1.5 text-[10px] font-bold text-[var(--text-primary)] hover:bg-[var(--border-color)]/40"
        >
          重置
        </button>
      </div>
    </div>
  );

  const renderReportList = () => (
    <div className="theme-card rounded-xl p-4 shadow-sm text-left flex-1 flex flex-col min-h-[420px]">
      <div className="flex flex-col gap-3 border-b border-[var(--border-color)] pb-3 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <div className="flex items-center gap-1.5 text-xs font-bold text-[var(--text-primary)]">
            <Filter className="size-4 text-[var(--accent-color)]" />
            <span>质量分析报告列表</span>
          </div>
          <div className="mt-1 text-[9px] text-[var(--text-secondary)]">
            {reportStatus.loading ? '正在同步后端报告...' : reportStatus.error || `当前筛选命中 ${visibleReports.length} / ${reports.length} 份`}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={selectedTemplateId}
            onChange={(event) => setSelectedTemplateId(event.target.value)}
            className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1.5 text-[10px] text-[var(--text-primary)] outline-none"
          >
            <option value="">使用后端默认模板</option>
            {templates.map(template => (
              <option key={template.id} value={template.id}>
                {template.name}{template.isDefault ? '（默认）' : ''}
              </option>
            ))}
          </select>
          <input
            value={newReportTitle}
            onChange={(event) => setNewReportTitle(event.target.value)}
            placeholder="报告标题（可选）"
            className="w-40 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1.5 text-[10px] text-[var(--text-primary)] outline-none"
          />
          <select
            value={newReportType}
            onChange={(event) => setNewReportType(event.target.value)}
            className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1.5 text-[10px] text-[var(--text-primary)] outline-none"
          >
            <option value="comprehensive">综合报告</option>
            <option value="performance">性能专项</option>
            <option value="release">上线建议</option>
            <option value="risk">风险清单</option>
          </select>
          <button
            onClick={handleCreateReport}
            disabled={isGeneratingReport || !selectedProject?.id}
            className="accent-btn inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-[10px] font-bold disabled:opacity-50"
          >
            <PlusSquare className="size-3.5" />
            <span>{isGeneratingReport ? '生成中...' : '生成报告'}</span>
          </button>
        </div>
      </div>

      <div className="mt-3 flex-1 overflow-y-auto pr-1">
        {reportStatus.loading && (
          <EmptyState title="正在读取报告" description="报告中心正在从后端同步真实报告列表。" />
        )}
        {!reportStatus.loading && reportStatus.error && !reports.length && (
          <EmptyState
            title="报告列表不可用"
            description={reportStatus.error}
            action={(
              <button onClick={loadReports} className="mt-3 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-3 py-1.5 text-[10px] font-bold text-[var(--text-primary)]">
                重新加载
              </button>
            )}
          />
        )}
        {!reportStatus.loading && !reportStatus.error && !reports.length && (
          <EmptyState
            title="暂无真实报告"
            description="后端当前没有返回报告记录。页面不会用本地样例填充，可先生成一份综合报告。"
          />
        )}
        {!reportStatus.loading && reports.length > 0 && visibleReports.length === 0 && (
          <EmptyState
            title="没有匹配的报告"
            description="当前筛选条件下没有命中记录，可调整类型、关键词、来源或日期范围。"
          />
        )}

        <div className="space-y-2.5">
          {visibleReports.map((report) => {
            const selected = report.id === selectedReportId;
            return (
              <button
                key={report.id}
                onClick={() => setSelectedReportId(report.id)}
                className={`w-full rounded-xl border p-3 text-left transition-all duration-200 ${
                  selected
                    ? 'border-[var(--accent-color)] bg-[var(--accent-glow)] shadow-md'
                    : 'border-[var(--border-color)] bg-[var(--bg-card)] hover:border-[var(--accent-color)]/50'
                }`}
              >
                <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                  <div className="flex min-w-0 items-start gap-3">
                    <div className={`rounded-lg p-2 ${selected ? 'bg-[var(--accent-color)] text-white' : 'bg-[var(--border-color)] text-[var(--text-secondary)]'}`}>
                      <FileText className="size-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="truncate text-[10.5px] font-bold text-[var(--text-primary)]">{report.name}</div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[8.5px] font-semibold text-[var(--text-secondary)]">
                        <span className="rounded border border-[var(--border-color)] px-1.5 py-0.5">{report.typeLabel}</span>
                        <span>{report.dateLabel}</span>
                        {report.templateVersion && <span>模板 {report.templateVersion}</span>}
                        <span>需求 {report.requirementIds.length}</span>
                        <span>来源 {report.sourceDocumentIds.length}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-2 text-[10px] font-bold text-[var(--text-secondary)]">
                    <div className="text-right">
                      <div className="text-[10px] font-black text-[var(--text-primary)]">{report.passRateLabel}</div>
                      <div className="text-[7.5px]">执行通过率</div>
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] font-black text-red-500">{report.defectCount}</div>
                      <div className="text-[7.5px]">缺陷</div>
                    </div>
                    <StatusPill className={statusBadgeClass(report.status)}>{report.status}</StatusPill>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );

  const renderSelectedReportPanel = () => {
    const snapshot = readSnapshot(selectedReport?.raw || {});
    const risks = riskState.items.length ? riskState.items : normalizeRiskItems(null, selectedReport);
    const topRisks = risks.slice(0, 4);
    const contentExcerpt = textOf(selectedReport?.content).trim().split('\n').filter(Boolean).slice(0, 4).join('\n');

    return (
      <TiltCard className="theme-card rounded-xl p-4 shadow-sm text-left flex-1 flex flex-col min-h-[420px]">
        <div className="flex flex-col flex-1 min-h-0" style={{ transform: 'translateZ(18px)', transformStyle: 'preserve-3d' }}>
          <div className="flex items-start justify-between gap-2 border-b border-[var(--border-color)] pb-2.5">
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 text-xs font-bold text-[var(--text-primary)]">
                <Sparkles className="size-4 text-purple-600" />
                <span>后端报告事实</span>
              </div>
              <div className="mt-1 truncate text-[8.5px] font-mono text-[var(--text-secondary)]">{selectedReport?.id ? `REPORT-${selectedReport.id}` : '未选择报告'}</div>
            </div>
            <button
              onClick={() => setViewMode('report-detail')}
              disabled={!selectedReport}
              className="shrink-0 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-2.5 py-1.5 text-[9.5px] font-bold text-[var(--text-primary)] hover:bg-[var(--border-color)]/40 disabled:opacity-50"
            >
              查看下钻
            </button>
          </div>

          {!selectedReport ? (
            <EmptyState title="未选择报告" description="请先从左侧选择一份后端报告。" />
          ) : (
            <div className="mt-3 flex-1 min-h-0 overflow-y-auto pr-1">
              <div className="grid grid-cols-2 gap-2">
                {[
                  { label: '需求项', value: selectedMetrics.requirementCount },
                  { label: '用例', value: selectedMetrics.testCaseCount },
                  { label: '执行', value: selectedMetrics.executionCount },
                  { label: '未关闭缺陷', value: selectedMetrics.openDefectCount }
                ].map(item => (
                  <div key={item.label} className="rounded-lg border border-[var(--border-color)] bg-[var(--border-color)]/15 p-2">
                    <div className="text-[8.5px] font-bold text-[var(--text-secondary)]">{item.label}</div>
                    <div className="mt-1 text-sm font-black text-[var(--text-primary)]">{formatCompactValue(item.value)}</div>
                  </div>
                ))}
              </div>

              <div className="mt-3 space-y-2">
                <div className="text-[10px] font-bold text-[var(--text-primary)]">风险项</div>
                {riskState.error && (
                  <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-2 text-[8.5px] font-semibold text-amber-600">
                    {riskState.error}
                  </div>
                )}
                {topRisks.length ? topRisks.map(risk => (
                  <div key={risk.id} className={`rounded-lg border p-2 ${riskBadgeClass(risk.level)}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-[9.5px] font-bold">{risk.title}</span>
                      <span className="shrink-0 text-[8px]">{risk.level}</span>
                    </div>
                    <p className="mt-1 line-clamp-3 text-[8px] leading-relaxed text-[var(--text-secondary)]">{risk.detail}</p>
                  </div>
                )) : (
                  <div className="rounded-lg border border-[var(--border-color)] bg-[var(--border-color)]/10 p-3 text-center text-[9px] text-[var(--text-secondary)]">
                    后端未返回风险项。
                  </div>
                )}
              </div>

              <div className="mt-3 rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)]/60 p-3">
                <div className="mb-2 text-[10px] font-bold text-[var(--text-primary)]">报告正文摘录</div>
                <pre className="max-h-32 whitespace-pre-wrap text-[8.5px] leading-relaxed text-[var(--text-secondary)] font-mono">
                  {contentExcerpt || '后端报告暂未返回可展示正文。'}
                </pre>
              </div>

              <div className="mt-3 rounded-xl border border-[var(--border-color)] bg-[var(--border-color)]/10 p-3">
                <div className="mb-2 text-[10px] font-bold text-[var(--text-primary)]">快照来源</div>
                <div className="grid grid-cols-2 gap-2 text-[8.5px] font-semibold text-[var(--text-secondary)]">
                  <div>需求 ID：{compactListText(selectedReport.requirementIds.slice(0, 6)) || '--'}</div>
                  <div>来源文档：{compactListText(selectedReport.sourceDocumentIds.slice(0, 6)) || '--'}</div>
                  <div>接口执行：{formatCompactValue(snapshot.api?.summary?.executions ?? readSourceRefs(selectedReport.raw).counts?.api_execution_ids)}</div>
                  <div>性能结果：{formatCompactValue(selectedMetrics.perfResultCount)}</div>
                </div>
              </div>
            </div>
          )}

          <div className="mt-4 border-t border-[var(--border-color)] pt-3">
            <div className="grid grid-cols-3 gap-2">
              {SUPPORTED_DOWNLOAD_FORMATS.map(format => (
                <button
                  key={format.id}
                  onClick={() => handleDownloadReport(format.id)}
                  disabled={!selectedReport || isDownloadingReport}
                  className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1.5 text-[9px] font-bold text-[var(--text-primary)] hover:bg-[var(--border-color)]/40 disabled:opacity-50"
                >
                  {format.label}
                </button>
              ))}
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {UNSUPPORTED_DOWNLOAD_FORMATS.map(format => (
                <button
                  key={format.id}
                  onClick={() => handleDownloadReport(format.id)}
                  disabled={!selectedReport || isDownloadingReport}
                  className="rounded-lg border border-dashed border-[var(--border-color)] bg-[var(--border-color)]/10 px-2 py-1.5 text-[9px] font-bold text-[var(--text-secondary)] disabled:opacity-50"
                >
                  {isDownloadingReport ? '下载中...' : format.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </TiltCard>
    );
  };

  const renderEvidencePanel = (evidence) => {
    const entries = evidenceEntries(evidence);
    return (
      <div className="rounded-xl border border-[var(--border-color)] bg-[var(--border-color)]/10 p-3">
        <div className="mb-2 flex items-center gap-1.5 text-[10px] font-bold text-[var(--text-primary)]">
          <BookOpen className="size-3.5 text-[var(--accent-color)]" />
          <span>证据来源</span>
        </div>
        {entries.length ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {entries.map(entry => (
              <div key={entry.key} className="min-w-0 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)]/70 p-2">
                <div className="truncate text-[8px] font-bold text-[var(--text-secondary)]">{entry.key}</div>
                <div className="mt-1 truncate text-[9.5px] font-black text-[var(--text-primary)]">
                  {entry.countOnly ? formatCompactValue(entry.value) : compactListText(entry.value)}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-[9px] text-[var(--text-secondary)]">后端未返回 source_refs_json。</div>
        )}
      </div>
    );
  };

  const renderDrilldownItems = () => {
    const data = drilldownState.data || buildSnapshotDrilldown(activeDrilldownSection, selectedReport);
    const fields = SECTION_FIELDS[activeDrilldownSection] || [];
    const items = asArray(data.items);
    const summaryEntries = Object.entries(asObject(data.summary)).slice(0, 10);

    return (
      <div className="space-y-4">
        {(drilldownState.error || drilldownState.loading) && (
          <div className={`rounded-xl border p-3 text-[9px] font-semibold ${
            drilldownState.error ? 'border-amber-500/20 bg-amber-500/10 text-amber-600' : 'border-blue-500/20 bg-blue-500/10 text-blue-600'
          }`}>
            {drilldownState.loading ? '正在读取下钻明细...' : drilldownState.error}
          </div>
        )}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {(summaryEntries.length ? summaryEntries : [['total', items.length]]).map(([key, value]) => (
            <div key={key} className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)]/70 p-2">
              <div className="truncate text-[8px] font-bold text-[var(--text-secondary)]">{FIELD_LABELS[key] || key}</div>
              <div className="mt-1 truncate text-sm font-black text-[var(--text-primary)]">{formatCompactValue(value)}</div>
            </div>
          ))}
        </div>

        {renderEvidencePanel(data.evidence)}

        <div className="space-y-2">
          {items.length ? items.slice(0, 30).map((item, index) => {
            const obj = asObject(item);
            const title = itemTitle(obj, index);
            const subtitle = itemSubtitle(obj);
            const status = obj.status || obj.level || obj.severity;
            return (
              <div key={`${title}-${index}`} className="rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)] p-3">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="truncate text-[10.5px] font-bold text-[var(--text-primary)]">{title}</div>
                    {subtitle && <div className="mt-1 truncate text-[8.5px] font-semibold text-[var(--text-secondary)]">{subtitle}</div>}
                  </div>
                  {status && <StatusPill className={statusBadgeClass(status)}>{formatCompactValue(status)}</StatusPill>}
                </div>
                <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2 text-[8.5px]">
                  {fields
                    .filter(field => obj[field] !== undefined && obj[field] !== null && obj[field] !== '')
                    .slice(0, 9)
                    .map(field => (
                      <div key={field} className="min-w-0 rounded-lg bg-[var(--border-color)]/15 px-2 py-1">
                        <span className="mr-1 font-bold text-[var(--text-secondary)]">{FIELD_LABELS[field] || field}:</span>
                        <span className="text-[var(--text-primary)]">{formatCompactValue(obj[field])}</span>
                      </div>
                    ))}
                </div>
              </div>
            );
          }) : (
            <EmptyState
              title="暂无下钻记录"
              description={`后端或报告快照没有返回 ${DRILLDOWN_SECTIONS.find(item => item.id === activeDrilldownSection)?.label} 明细。`}
            />
          )}
        </div>
      </div>
    );
  };

  const renderRiskTodoPanel = () => (
    <div className="theme-card rounded-xl p-4 shadow-soft space-y-3">
      <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-2">
        <div className="flex items-center gap-1.5 text-xs font-bold text-[var(--text-primary)]">
          <ClipboardList className="size-4 text-amber-500" />
          <span>风险转待办</span>
        </div>
        <StatusPill className={riskState.unsupported ? 'text-amber-600 bg-amber-500/10 border-amber-500/20' : 'text-emerald-600 bg-emerald-500/10 border-emerald-500/20'}>
          {riskState.unsupported ? 'API 待接入' : '真实 API'}
        </StatusPill>
      </div>

      {riskState.loading && <div className="text-[9px] font-semibold text-[var(--text-secondary)]">正在读取 /reports/{'{id}'}/risks...</div>}
      {riskState.error && <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-2 text-[8.5px] font-semibold text-amber-600">{riskState.error}</div>}

      <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
        {riskState.items.length ? riskState.items.map(risk => {
          const action = riskActionState[risk.id] || {};
          return (
            <div key={risk.id} className={`rounded-xl border p-3 ${riskBadgeClass(risk.level)}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-[10px] font-bold">{risk.title}</div>
                  <div className="mt-1 text-[8px] font-semibold opacity-80">来源：{risk.source} / 状态：{risk.status || 'open'}</div>
                </div>
                <button
                  onClick={() => handleRiskToTodo(risk)}
                  disabled={action.loading}
                  className="shrink-0 rounded-lg border border-current/20 bg-[var(--bg-card)]/60 px-2 py-1 text-[8.5px] font-bold hover:bg-white/50 disabled:opacity-60"
                >
                  {action.loading ? '处理中...' : '转待办'}
                </button>
              </div>
              <p className="mt-2 text-[8.5px] leading-relaxed text-[var(--text-secondary)]">{risk.detail}</p>
              {(risk.todoId || action.message) && (
                <div className="mt-2 rounded-lg border border-current/20 bg-[var(--bg-card)]/70 p-2 text-[8px] font-semibold">
                  {risk.todoId ? `待办 ID：${risk.todoId}` : ''}
                  {risk.todoId && action.message ? ' / ' : ''}
                  {action.message}
                </div>
              )}
            </div>
          );
        }) : (
          <EmptyState title="暂无风险项" description="后端未返回可转待办的风险项。" />
        )}
      </div>
    </div>
  );

  const renderReportDetail = () => (
    <div className="space-y-4 text-left animate-[fadeIn_0.2s_ease-out] w-full">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <button
            onClick={() => setViewMode('list')}
            className="flex items-center gap-1 rounded border border-[var(--border-color)] bg-[var(--bg-card)] px-2.5 py-1 text-[10px] text-[var(--text-primary)] shadow-sm hover:bg-[var(--border-color)]/50"
          >
            <ArrowLeft className="size-3" />
            <span>返回报告中心</span>
          </button>
          <div className="min-w-0 text-[11px] font-semibold text-[var(--text-secondary)]">
            <span>报告中心 / </span>
            <span className="text-[var(--text-primary)]">{selectedReport?.name || '未选择报告'}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {SUPPORTED_DOWNLOAD_FORMATS.map(format => (
            <button
              key={format.id}
              onClick={() => handleDownloadReport(format.id)}
              disabled={!selectedReport || isDownloadingReport}
              className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-3 py-1.5 text-[10px] font-bold text-[var(--text-primary)] hover:bg-[var(--border-color)]/40 disabled:opacity-50"
            >
              <Download className="size-3.5" />
              <span>{format.label}</span>
            </button>
          ))}
          {UNSUPPORTED_DOWNLOAD_FORMATS.map(format => (
            <button
              key={format.id}
              onClick={() => handleDownloadReport(format.id)}
              disabled={!selectedReport || isDownloadingReport}
              className="rounded-lg border border-dashed border-[var(--border-color)] bg-[var(--border-color)]/10 px-3 py-1.5 text-[10px] font-bold text-[var(--text-secondary)] disabled:opacity-50"
            >
              {isDownloadingReport ? '下载中...' : format.label}
            </button>
          ))}
        </div>
      </div>

      {!selectedReport ? (
        <EmptyState title="未选择报告" description="请回到报告列表选择一份真实报告。" />
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
            {[
              { label: '执行通过率', value: selectedReport.passRateLabel, sub: 'summary_metrics.execution_pass_rate' },
              { label: '缺陷总数', value: selectedMetrics.defectCount, sub: `${selectedMetrics.openDefectCount} 个未关闭` },
              { label: '需求范围', value: selectedMetrics.requirementCount, sub: `${selectedMetrics.sourceCount} 个来源文档` },
              { label: '模板版本', value: selectedReport.templateVersion || '--', sub: selectedReport.templateId ? `模板 ID ${selectedReport.templateId}` : '后端默认模板' }
            ].map(item => (
              <div key={item.label} className="theme-card rounded-xl border p-4">
                <div className="text-[9px] font-bold text-[var(--text-secondary)]">{item.label}</div>
                <div className="mt-1 text-xl font-black text-[var(--text-primary)]">{formatCompactValue(item.value)}</div>
                <div className="mt-1 text-[8.5px] text-[var(--text-secondary)]">{item.sub}</div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
            <div className="xl:col-span-8 theme-card rounded-xl p-4 shadow-soft">
              <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border-color)] pb-3">
                {DRILLDOWN_SECTIONS.map(section => (
                  <button
                    key={section.id}
                    onClick={() => setActiveDrilldownSection(section.id)}
                    className={`rounded-lg border px-2.5 py-1.5 text-[9px] font-bold transition-colors ${
                      activeDrilldownSection === section.id
                        ? 'border-[var(--accent-color)] bg-[var(--accent-glow)] text-[var(--accent-color)]'
                        : 'border-[var(--border-color)] bg-[var(--bg-card)] text-[var(--text-primary)] hover:bg-[var(--border-color)]/40'
                    }`}
                  >
                    {section.label}
                  </button>
                ))}
              </div>
              <div className="mt-4">
                {renderDrilldownItems()}
              </div>
            </div>

            <div className="xl:col-span-4">
              {renderRiskTodoPanel()}
            </div>
          </div>
        </>
      )}
    </div>
  );

  const renderTemplateManage = () => (
    <div className="space-y-4 text-left animate-[fadeIn_0.2s_ease-out] w-full">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setViewMode('list')}
            className="flex items-center gap-1 rounded border border-[var(--border-color)] bg-[var(--bg-card)] px-2.5 py-1 text-[10px] text-[var(--text-primary)] shadow-sm hover:bg-[var(--border-color)]/50"
          >
            <ArrowLeft className="size-3" />
            <span>返回报告中心</span>
          </button>
          <div className="text-[11px] font-semibold text-[var(--text-secondary)]">
            <span>报告中心 / </span>
            <span className="text-[var(--text-primary)]">报告模板 API 管理</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleNewTemplate}
            className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-3 py-1.5 text-[10px] font-bold text-[var(--text-primary)] hover:bg-[var(--border-color)]/40"
          >
            <Plus className="size-3.5" />
            <span>新建模板</span>
          </button>
          <button
            onClick={loadTemplates}
            className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-3 py-1.5 text-[10px] font-bold text-[var(--text-primary)] hover:bg-[var(--border-color)]/40"
          >
            <RefreshCw className="size-3.5" />
            <span>刷新</span>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        <div className="xl:col-span-5 theme-card rounded-xl p-4 shadow-soft">
          <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-2">
            <div className="flex items-center gap-1.5 text-xs font-bold text-[var(--text-primary)]">
              <Layers className="size-4 text-[var(--accent-color)]" />
              <span>模板列表</span>
            </div>
            <span className="text-[9px] font-semibold text-[var(--text-secondary)]">
              {templateStatus.loading ? '加载中...' : templateStatus.error || `${templates.length} 个模板`}
            </span>
          </div>

          <div className="mt-3 space-y-2 max-h-[640px] overflow-y-auto pr-1">
            {templateStatus.error && !templates.length && (
              <EmptyState title="模板 API 不可用" description={templateStatus.error} />
            )}
            {!templateStatus.loading && !templateStatus.error && !templates.length && (
              <EmptyState title="暂无模板" description="后端没有返回报告模板，可在右侧创建第一份模板。" />
            )}
            {templates.map(template => (
              <div
                key={template.id}
                className={`rounded-xl border p-3 ${
                  templateDraft.id === template.id
                    ? 'border-[var(--accent-color)] bg-[var(--accent-glow)]'
                    : 'border-[var(--border-color)] bg-[var(--bg-card)]'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-[10.5px] font-bold text-[var(--text-primary)]">{template.name}</div>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[8px] font-semibold text-[var(--text-secondary)]">
                      <span>{reportTypeLabel(template.reportType)}</span>
                      <span>v: {template.templateVersion}</span>
                      <span>{template.enabled ? 'enabled' : 'disabled'}</span>
                      {template.isDefault && <span className="text-[var(--accent-color)]">默认</span>}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <button onClick={() => handleEditTemplate(template)} className="rounded p-1 text-[var(--text-secondary)] hover:bg-[var(--border-color)]/50 hover:text-[var(--accent-color)]">
                      <Edit3 className="size-3.5" />
                    </button>
                    <button onClick={() => handleSetDefaultTemplate(template)} className="rounded p-1 text-[var(--text-secondary)] hover:bg-[var(--border-color)]/50 hover:text-amber-500">
                      <Star className="size-3.5" />
                    </button>
                    <button onClick={() => handleDeleteTemplate(template)} className="rounded p-1 text-[var(--text-secondary)] hover:bg-red-500/10 hover:text-red-500">
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                </div>

                <div className="mt-2 space-y-1">
                  {template.sections.map(section => (
                    <div key={`${template.id}-${section.key}`} className="flex items-center justify-between gap-2 rounded-lg bg-[var(--border-color)]/15 px-2 py-1 text-[8px] font-semibold">
                      <span className="truncate text-[var(--text-primary)]">#{section.order} {section.name}</span>
                      <span className={section.enabled ? 'text-emerald-600' : 'text-[var(--text-secondary)]'}>{section.enabled ? 'enabled' : 'disabled'}</span>
                    </div>
                  ))}
                </div>

                <div className="mt-2 flex flex-wrap gap-1">
                  {template.supportedFormats.map(format => (
                    <span key={`${template.id}-${format}`} className="rounded border border-[var(--border-color)] px-1.5 py-0.5 text-[7.5px] font-bold text-[var(--text-secondary)]">
                      {format}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="xl:col-span-7 theme-card rounded-xl p-4 shadow-soft">
          <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-2">
            <div className="flex items-center gap-1.5 text-xs font-bold text-[var(--text-primary)]">
              <Settings className="size-4 text-[var(--accent-color)]" />
              <span>{templateDraft.id ? '编辑模板' : '新建模板'}</span>
            </div>
            <button
              onClick={handleSaveTemplate}
              disabled={isSavingTemplate}
              className="accent-btn inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-[10px] font-bold disabled:opacity-60"
            >
              <Save className="size-3.5" />
              <span>{isSavingTemplate ? '保存中...' : '保存模板'}</span>
            </button>
          </div>

          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="text-[9px] font-bold text-[var(--text-secondary)]">
              模板名称
              <input
                value={templateDraft.name}
                onChange={(event) => setTemplateDraft(current => ({ ...current, name: event.target.value }))}
                placeholder="例如：上线风险复核模板"
                className="mt-1 w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-2 text-[10px] text-[var(--text-primary)] outline-none"
              />
            </label>
            <label className="text-[9px] font-bold text-[var(--text-secondary)]">
              报告类型
              <select
                value={templateDraft.reportType}
                onChange={(event) => setTemplateDraft(current => ({ ...current, reportType: event.target.value }))}
                className="mt-1 w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-2 text-[10px] text-[var(--text-primary)] outline-none"
              >
                <option value="comprehensive">综合报告</option>
                <option value="performance">性能专项</option>
                <option value="release">上线建议</option>
                <option value="risk">风险清单</option>
              </select>
            </label>
            <label className="text-[9px] font-bold text-[var(--text-secondary)]">
              模板版本
              <input
                value={templateDraft.templateVersion}
                onChange={(event) => setTemplateDraft(current => ({ ...current, templateVersion: event.target.value }))}
                className="mt-1 w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-2 text-[10px] text-[var(--text-primary)] outline-none"
              />
            </label>
            <div className="flex items-end gap-4 text-[10px] font-bold text-[var(--text-primary)]">
              <label className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={templateDraft.enabled}
                  onChange={(event) => setTemplateDraft(current => ({ ...current, enabled: event.target.checked }))}
                  style={{ accentColor: 'var(--accent-color)' }}
                />
                enabled
              </label>
              <label className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={templateDraft.isDefault}
                  onChange={(event) => setTemplateDraft(current => ({ ...current, isDefault: event.target.checked }))}
                  style={{ accentColor: 'var(--accent-color)' }}
                />
                设为默认
              </label>
            </div>
          </div>

          <div className="mt-4 rounded-xl border border-[var(--border-color)] bg-[var(--border-color)]/10 p-3">
            <div className="mb-2 flex items-center justify-between">
              <div className="text-[10px] font-bold text-[var(--text-primary)]">supported_formats</div>
              <div className="text-[8px] text-[var(--text-secondary)]">下载接口当前可用：Markdown / HTML / JSON</div>
            </div>
            <div className="flex flex-wrap gap-2">
              {TEMPLATE_FORMAT_OPTIONS.map(format => (
                <label key={format.id} className="flex items-center gap-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1 text-[9px] font-bold text-[var(--text-primary)]">
                  <input
                    type="checkbox"
                    checked={templateDraft.supportedFormats.includes(format.id)}
                    onChange={() => toggleDraftFormat(format.id)}
                    style={{ accentColor: 'var(--accent-color)' }}
                  />
                  {format.label}
                </label>
              ))}
            </div>
          </div>

          <div className="mt-4">
            <div className="mb-2 flex items-center justify-between">
              <div className="text-[10px] font-bold text-[var(--text-primary)]">sections / order / enabled</div>
              <button
                onClick={addDraftSection}
                className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1 text-[9px] font-bold text-[var(--text-primary)] hover:bg-[var(--border-color)]/40"
              >
                <Plus className="size-3" />
                <span>添加段落</span>
              </button>
            </div>

            <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1">
              {templateDraft.sections.map((section, index) => (
                <div key={`${section.key}-${index}`} className="grid grid-cols-12 gap-2 rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)] p-2">
                  <input
                    value={section.order}
                    onChange={(event) => updateDraftSection(index, { order: numberOf(event.target.value, index + 1) })}
                    className="col-span-2 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)] px-2 py-1.5 text-[9px] text-[var(--text-primary)] outline-none"
                    aria-label="order"
                  />
                  <input
                    value={section.key}
                    onChange={(event) => updateDraftSection(index, { key: event.target.value })}
                    className="col-span-3 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)] px-2 py-1.5 text-[9px] text-[var(--text-primary)] outline-none"
                    aria-label="key"
                  />
                  <input
                    value={section.name}
                    onChange={(event) => updateDraftSection(index, { name: event.target.value })}
                    className="col-span-4 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)] px-2 py-1.5 text-[9px] text-[var(--text-primary)] outline-none"
                    aria-label="name"
                  />
                  <label className="col-span-2 flex items-center justify-center gap-1 text-[8px] font-bold text-[var(--text-primary)]">
                    <input
                      type="checkbox"
                      checked={section.enabled}
                      onChange={(event) => updateDraftSection(index, { enabled: event.target.checked })}
                      style={{ accentColor: 'var(--accent-color)' }}
                    />
                    enabled
                  </label>
                  <button
                    onClick={() => removeDraftSection(index)}
                    className="col-span-1 flex items-center justify-center rounded-lg text-[var(--text-secondary)] hover:bg-red-500/10 hover:text-red-500"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const renderLightweightConclusion = () => {
    const selectedType = CONCLUSION_TYPES.find(item => item.id === conclusionType);
    return (
      <div className="space-y-4 text-left animate-[fadeIn_0.2s_ease-out] w-full">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setViewMode('list')}
              className="flex items-center gap-1 rounded border border-[var(--border-color)] bg-[var(--bg-card)] px-2.5 py-1 text-[10px] text-[var(--text-primary)] shadow-sm hover:bg-[var(--border-color)]/50"
            >
              <ArrowLeft className="size-3" />
              <span>返回报告中心</span>
            </button>
            <div className="text-[11px] font-semibold text-[var(--text-secondary)]">
              <span>报告中心 / </span>
              <span className="text-[var(--text-primary)]">轻量结论</span>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={conclusionTitle}
              onChange={(event) => setConclusionTitle(event.target.value)}
              placeholder="归档标题（可选）"
              className="w-56 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1.5 text-[10px] text-[var(--text-primary)] outline-none"
            />
            <button
              onClick={() => handleGenerateConclusion({ save: false })}
              disabled={conclusionState.loading}
              className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-3 py-1.5 text-[10px] font-bold text-[var(--text-primary)] hover:bg-[var(--border-color)]/40 disabled:opacity-60"
            >
              <Sparkles className="size-3.5" />
              <span>{conclusionState.loading ? '生成中...' : '生成结论'}</span>
            </button>
            <button
              onClick={() => handleGenerateConclusion({ save: true })}
              disabled={conclusionState.loading || !conclusionResult?.conclusion}
              className="accent-btn inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-[10px] font-bold disabled:opacity-60"
            >
              <Save className="size-3.5" />
              <span>归档为报告</span>
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
          <div className="xl:col-span-4 theme-card rounded-xl p-4 shadow-soft space-y-4">
            <div className="border-b border-[var(--border-color)] pb-2">
              <div className="text-xs font-bold text-[var(--text-primary)]">结论类型</div>
              <div className="mt-1 text-[9px] text-[var(--text-secondary)]">请求 /reports/lightweight-conclusions，由后端返回正文。</div>
            </div>
            <div className="space-y-2">
              {CONCLUSION_TYPES.map(type => (
                <button
                  key={type.id}
                  onClick={() => {
                    setConclusionType(type.id);
                    setConclusionResult(null);
                    handleGenerateConclusion({ save: false, nextType: type.id });
                  }}
                  className={`w-full rounded-xl border p-3 text-left transition-colors ${
                    conclusionType === type.id
                      ? 'border-[var(--accent-color)] bg-[var(--accent-glow)]'
                      : 'border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/30'
                  }`}
                >
                  <div className="text-[10px] font-bold text-[var(--text-primary)]">{type.label}</div>
                  <div className="mt-1 text-[8.5px] leading-relaxed text-[var(--text-secondary)]">{type.hint}</div>
                </button>
              ))}
            </div>

            <div className="rounded-xl border border-[var(--border-color)] bg-[var(--border-color)]/10 p-3 text-[9px] font-semibold text-[var(--text-secondary)]">
              当前类型：<span className="font-bold text-[var(--text-primary)]">{selectedType?.label}</span>
              <br />
              保存状态：{conclusionResult?.saved ? '已归档' : '未归档'}
            </div>
          </div>

          <div className="xl:col-span-8 theme-card rounded-xl p-4 shadow-soft">
            <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-2">
              <div className="flex items-center gap-1.5 text-xs font-bold text-[var(--text-primary)]">
                <FileText className="size-4 text-[var(--accent-color)]" />
                <span>后端结论正文</span>
              </div>
              {conclusionState.error && <StatusPill className="text-red-600 bg-red-500/10 border-red-500/20">生成失败</StatusPill>}
            </div>

            <div className="mt-4 min-h-[260px] rounded-xl border border-[var(--border-color)] bg-[var(--bg-app)] p-4">
              {conclusionState.loading ? (
                <div className="flex h-[220px] items-center justify-center text-[10px] font-bold text-[var(--text-secondary)]">正在等待后端生成结论...</div>
              ) : conclusionState.error ? (
                <EmptyState title="轻量结论生成失败" description={conclusionState.error} />
              ) : conclusionResult?.conclusion ? (
                <pre className="whitespace-pre-wrap text-[10px] leading-relaxed text-[var(--text-primary)] font-mono">{conclusionResult.conclusion}</pre>
              ) : (
                <EmptyState title="暂无结论正文" description="请选择日报、提测反馈、上线建议或风险清单类型，并由后端生成结论。" />
              )}
            </div>

            {conclusionResult?.metrics && (
              <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-2">
                {[
                  ['requirements', '需求'],
                  ['test_cases', '用例'],
                  ['executions', '执行'],
                  ['defects', '缺陷']
                ].map(([key, label]) => (
                  <div key={key} className="rounded-lg border border-[var(--border-color)] bg-[var(--border-color)]/10 p-2">
                    <div className="text-[8px] font-bold text-[var(--text-secondary)]">{label}</div>
                    <div className="mt-1 text-sm font-black text-[var(--text-primary)]">{formatCompactValue(conclusionResult.metrics?.[key]?.summary?.count ?? conclusionResult.metrics?.summary?.[`${key}_count`])}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4 text-left p-1 w-full flex flex-col h-full min-h-0">
      {viewMode === 'list' && (
        <>
          {renderSummaryCards()}
          {renderFilters()}

          <div className="grid grid-cols-1 xl:grid-cols-12 gap-5 w-full items-stretch flex-1 min-h-0">
            <div className="xl:col-span-7 h-full flex flex-col min-h-0">
              {renderReportList()}
            </div>
            <div className="xl:col-span-5 h-full flex flex-col min-h-0">
              {renderSelectedReportPanel()}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            <button
              onClick={() => setViewMode('template-manage')}
              className="theme-card rounded-xl border p-3 text-left hover:border-[var(--accent-color)]/50"
            >
              <div className="flex items-center gap-2 text-[10px] font-bold text-[var(--text-primary)]">
                <Settings className="size-4 text-[var(--accent-color)]" />
                <span>管理报告模板</span>
              </div>
              <div className="mt-1 text-[8.5px] text-[var(--text-secondary)]">读取、新建、编辑、删除和设默认模板。</div>
            </button>
            <button
              onClick={handleNewTemplate}
              className="theme-card rounded-xl border p-3 text-left hover:border-[var(--accent-color)]/50"
            >
              <div className="flex items-center gap-2 text-[10px] font-bold text-[var(--text-primary)]">
                <Plus className="size-4 text-emerald-500" />
                <span>新建模板</span>
              </div>
              <div className="mt-1 text-[8.5px] text-[var(--text-secondary)]">配置 sections / order / enabled / supported_formats。</div>
            </button>
            <button
              onClick={handleOpenConclusion}
              className="theme-card rounded-xl border p-3 text-left hover:border-[var(--accent-color)]/50"
            >
              <div className="flex items-center gap-2 text-[10px] font-bold text-[var(--text-primary)]">
                <Sparkles className="size-4 text-purple-600" />
                <span>轻量结论</span>
              </div>
              <div className="mt-1 text-[8.5px] text-[var(--text-secondary)]">日报 / 提测反馈 / 上线建议 / 风险清单。</div>
            </button>
          </div>
        </>
      )}

      {viewMode === 'report-detail' && renderReportDetail()}
      {viewMode === 'template-manage' && renderTemplateManage()}
      {viewMode === 'lightweight-conclusion' && renderLightweightConclusion()}
    </div>
  );
}
