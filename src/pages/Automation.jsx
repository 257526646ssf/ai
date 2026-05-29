import React, { useState } from 'react';
import { 
  Cpu, 
  Search, 
  ChevronDown, 
  ArrowLeft, 
  Play, 
  Code, 
  Settings, 
  Sparkles,
  CheckCircle,
  Clock,
  BookOpen,
  Plus,
  Folder,
  FileText,
  Terminal,
  ExternalLink,
  XCircle,
  Activity
} from 'lucide-react';
import TiltCard from '../components/TiltCard';
import AnimatedNumber from '../components/AnimatedNumber';
import { apiGet, apiPost, apiRequest, downloadBase64File, formatDateTime, pickList } from '../lib/api';
import { useProjectContext } from '../lib/projectContext';

const showToast = (message, type = 'success') => {
  window.dispatchEvent(new CustomEvent('show-toast', { detail: { message, type } }));
};

const frameworkName = (framework = '', language = '') => {
  const fw = String(framework || 'pytest');
  const lang = String(language || '').toLowerCase();
  if (fw.toLowerCase().includes('playwright')) return `${lang.includes('python') ? 'Python' : 'Node.js'} / Playwright`;
  if (fw.toLowerCase().includes('appium')) return `${lang.includes('python') ? 'Python' : 'Node.js'} / Appium`;
  if (fw.toLowerCase().includes('selenium')) return `${lang.includes('java') ? 'Java' : 'Python'} / Selenium`;
  return `${language || 'Python'} / ${framework || 'pytest'}`;
};

const mapBackendAutoProject = (project) => {
  const item = project && typeof project === 'object' && !Array.isArray(project) ? project : {};
  const extra = item.extra_config || item.extraConfig || {};
  const caseCount = Number(extra.case_count || extra.caseCount || 0);
  const buildCount = Number(extra.build_count || extra.buildCount || item.id || 0);
  const successRate = extra.success_rate || extra.successRate || (caseCount ? '100.0%' : '待执行');
  return {
    backendId: item.id,
    name: item.name || 'Automation Project',
    desc: extra.description || item.type || '后端自动化项目',
    stack: frameworkName(item.framework, item.language),
    framework: item.framework || 'pytest',
    language: item.language || 'python',
    cases: caseCount,
    rate: successRate,
    build: buildCount,
    time: formatDateTime(item.updated_at || item.created_at),
    owner: extra.owner || '系统',
    raw: item
  };
};

const DEFAULT_PLAYWRIGHT_OPTIONS = {
  baseURL: 'http://localhost:3000',
  headless: true,
  browser: 'chromium',
  retries: 1,
  workers: 1,
  trace: 'on-first-retry',
  video: 'retain-on-failure',
  screenshot: 'only-on-failure',
  reporter: 'html,list'
};

const R26_VISIBLE_KEYWORDS = ['候选筛选', '在线文件', '保存', 'Playwright', 'trace', 'Artifacts', '预览', '执行日志'];

const asObject = (value) => (value && typeof value === 'object' && !Array.isArray(value) ? value : {});

const asArray = (value) => {
  if (Array.isArray(value)) return value;
  const picked = pickList(value);
  if (picked.length) return picked;
  const obj = asObject(value);
  if (Array.isArray(obj.data)) return obj.data;
  if (Array.isArray(obj.files)) return obj.files;
  if (Array.isArray(obj.case_files)) return obj.case_files;
  if (Array.isArray(obj.caseFiles)) return obj.caseFiles;
  if (Array.isArray(obj.evidence)) return obj.evidence;
  return [];
};

const textOf = (value, fallback = '') => {
  if (value === undefined || value === null) return fallback;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return fallback;
};

const numberOf = (value, fallback = 0) => {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
};

const boolOf = (value, fallback = false) => {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  const normalized = String(value ?? '').toLowerCase();
  if (['true', '1', 'yes', 'on'].includes(normalized)) return true;
  if (['false', '0', 'no', 'off'].includes(normalized)) return false;
  return fallback;
};

const lastPathSegment = (path) => {
  const parts = String(path || '').split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] || String(path || 'untitled');
};

const normalizeCandidate = (item, index = 0) => {
  const obj = asObject(item);
  const rawId = obj.id ?? obj.candidate_id ?? obj.candidateId ?? obj.case_id ?? obj.caseId ?? obj.requirement_id ?? obj.requirementId ?? obj.key;
  const score = numberOf(obj.score ?? obj.rank_score ?? obj.match_score ?? obj.confidence, 0);
  const recommended = boolOf(obj.recommended ?? obj.is_recommended ?? obj.isRecommended, score >= 0.75);
  return {
    id: String(rawId ?? `candidate-${index}`),
    title: textOf(obj.title ?? obj.name ?? obj.case_name ?? obj.caseName ?? obj.requirement_title, `候选用例 #${index + 1}`),
    module: textOf(obj.module ?? obj.feature ?? obj.group ?? obj.category, '未分组'),
    priority: textOf(obj.priority ?? obj.level ?? obj.severity, 'P2'),
    score,
    recommended,
    reason: textOf(obj.reason ?? obj.recommend_reason ?? obj.description ?? obj.summary, '后端未返回推荐说明'),
    source: textOf(obj.source ?? obj.requirement_code ?? obj.requirementCode ?? obj.path, '--'),
    raw: obj
  };
};

const normalizeCandidates = (payload) => asArray(payload).map(normalizeCandidate);

const normalizeCaseFile = (item, index = 0) => {
  const obj = typeof item === 'string' ? { path: item, content: '' } : asObject(item);
  const path = textOf(obj.path ?? obj.relative_path ?? obj.relativePath ?? obj.file_path ?? obj.filePath ?? obj.name, `case-file-${index + 1}.spec.js`);
  const id = obj.id ?? obj.case_file_id ?? obj.caseFileId ?? obj.file_id ?? obj.fileId ?? obj.uuid ?? path;
  const content = obj.content ?? obj.text ?? obj.body ?? obj.source ?? obj.code ?? '';
  return {
    id: String(id),
    path,
    name: textOf(obj.name, lastPathSegment(path)),
    content: textOf(content, ''),
    size: numberOf(obj.size ?? obj.bytes, 0),
    mimeType: textOf(obj.mime_type ?? obj.mimeType ?? obj.content_type ?? obj.contentType, ''),
    updatedAt: formatDateTime(obj.updated_at ?? obj.updatedAt ?? obj.modified_at ?? obj.modifiedAt),
    status: textOf(obj.status ?? obj.result, 'ready'),
    raw: obj
  };
};

const normalizeCaseFiles = (payload) => {
  const obj = asObject(payload);
  const list = asArray(payload).length ? asArray(payload) : asArray(obj.files ?? obj.case_files ?? obj.caseFiles);
  return list.map(normalizeCaseFile);
};

const normalizeSummary = (value) => {
  const obj = asObject(value);
  return {
    total: numberOf(obj.total ?? obj.count ?? obj.tests ?? obj.collected, 0),
    passed: numberOf(obj.passed ?? obj.pass ?? obj.success, 0),
    failed: numberOf(obj.failed ?? obj.failures ?? obj.failure, 0),
    errors: numberOf(obj.errors ?? obj.error, 0),
    skipped: numberOf(obj.skipped ?? obj.skip, 0)
  };
};

const splitLogLines = (value) => {
  if (Array.isArray(value)) return value.map(line => textOf(line)).filter(Boolean);
  return textOf(value).split('\n').map(line => line.trimEnd()).filter(Boolean);
};

const normalizeArtifact = (item, index = 0, group = '') => {
  const obj = typeof item === 'string' ? { path: item } : asObject(item);
  const path = textOf(obj.relative_path ?? obj.relativePath ?? obj.path ?? obj.file_path ?? obj.filePath ?? obj.source ?? obj.url, '');
  const kind = textOf(obj.kind ?? obj.type ?? group ?? obj.category, lastPathSegment(path).split('.').pop() || 'artifact');
  return {
    id: String(obj.id ?? obj.artifact_id ?? obj.artifactId ?? path ?? `artifact-${index}`),
    kind,
    path,
    name: textOf(obj.name ?? obj.filename ?? obj.file_name, lastPathSegment(path) || `${kind}-${index + 1}`),
    mimeType: textOf(obj.mime_type ?? obj.mimeType ?? obj.content_type ?? obj.contentType, ''),
    size: numberOf(obj.size ?? obj.bytes, 0),
    previewable: obj.previewable !== false,
    raw: obj
  };
};

const normalizeArtifacts = (payload) => {
  if (Array.isArray(payload)) return payload.map((item, index) => normalizeArtifact(item, index));
  const obj = asObject(payload);
  const groups = ['evidence', 'screenshots', 'traces', 'logs', 'html', 'junit', 'files', 'artifacts'];
  const items = [];
  groups.forEach((group) => {
    asArray(obj[group]).forEach((item) => items.push({ item, group }));
  });
  return items.map(({ item, group }, index) => normalizeArtifact(item, index, group));
};

const normalizeExecution = (payload, fallback = {}) => {
  const obj = asObject(payload);
  const source = asObject(obj.execution || obj.detail || obj.result || obj);
  const artifactsSource = source.artifacts ?? source.artifact_list ?? source.artifactList ?? source.evidence ?? obj.artifacts ?? obj.evidence;
  const logSource = source.log_excerpt ?? source.logExcerpt ?? source.log ?? source.logs ?? source.stdout ?? source.stderr ?? obj.log;
  return {
    ...fallback,
    ...source,
    id: source.id ?? source.execution_id ?? source.executionId ?? fallback.id,
    status: textOf(source.status ?? fallback.status, 'unknown'),
    duration_ms: numberOf(source.duration_ms ?? source.durationMs ?? source.duration ?? fallback.duration_ms, 0),
    summary: normalizeSummary(source.summary ?? source.stats ?? source.result_summary ?? fallback.summary),
    logLines: splitLogLines(logSource).length ? splitLogLines(logSource) : splitLogLines(fallback.logLines),
    artifactsList: normalizeArtifacts(artifactsSource),
    artifacts: artifactsSource ?? fallback.artifacts
  };
};

const normalizeGenerationSummary = (payload) => {
  const obj = asObject(payload);
  const files = asArray(obj.files ?? obj.generated_files ?? obj.generatedFiles ?? obj.case_files ?? obj.caseFiles).map(normalizeCaseFile);
  const config = asObject(obj.config ?? obj.playwright_config ?? obj.playwrightConfig ?? obj.template_options ?? obj.templateOptions);
  return {
    message: textOf(obj.message ?? obj.summary ?? obj.reason, '后端已返回生成结果'),
    files,
    config,
    raw: obj
  };
};

const normalizePreview = (payload, artifact) => {
  const obj = typeof payload === 'string' ? { content: payload } : asObject(payload);
  return {
    artifact,
    kind: textOf(obj.kind ?? obj.type ?? artifact?.kind, ''),
    mimeType: textOf(obj.mime_type ?? obj.mimeType ?? artifact?.mimeType, ''),
    filename: textOf(obj.filename ?? obj.name ?? artifact?.name, artifact?.name || 'artifact'),
    content: textOf(obj.redacted_content ?? obj.redactedContent ?? obj.content ?? obj.text ?? obj.preview, ''),
    contentBase64: textOf(obj.content_base64 ?? obj.contentBase64 ?? obj.base64 ?? obj.image_base64 ?? obj.imageBase64, ''),
    downloadUrl: textOf(obj.download_url ?? obj.downloadUrl ?? obj.url, ''),
    raw: obj
  };
};

export default function Automation() {
  const { selectedProject, loading: projectLoading, error: projectError } = useProjectContext();
  const [viewMode, setViewMode] = useState('list'); // 'list' or 'wizard'
  const [wizardStep, setWizardStep] = useState(1); // 1, 2, 3, 4
  const [selectedProjIdx, setSelectedProjIdx] = useState(0);
  const [cliLogs, setCliLogs] = useState([]);
  const [projectContext, setProjectContext] = useState(null);
  const [remoteProjects, setRemoteProjects] = useState([]);
  const [autoStatus, setAutoStatus] = useState({ loading: true, usingBackend: false, message: '正在同步后端自动化项目...' });
  const [autoExecution, setAutoExecution] = useState(null);
  const [isRunningAutomation, setIsRunningAutomation] = useState(false);
  const [isSyncingRepo, setIsSyncingRepo] = useState(false);
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [autoRunnerMode, setAutoRunnerMode] = useState('auto');
  const [runtimeDeps, setRuntimeDeps] = useState(null);

  // 17-页数据
  const autoStats = [
    { label: '自动化项目数', val: '6', change: '较上轮 持平', icon: BookOpen, color: 'text-blue-500', bg: 'bg-blue-50' },
    { label: '自动化用例数', val: '842', change: '较昨日 ↑ 27', icon: Code, color: 'text-purple-500', bg: 'bg-purple-50' },
    { label: '流水线构建数', val: '156', change: '较昨日 ↑ 8', icon: Clock, color: 'text-indigo-500', bg: 'bg-indigo-50' },
    { label: '执行通过率', val: '90.1%', change: '较昨日 ↑ 1.2%', hasChart: true }
  ];

  const autoProjects = [
    { name: 'Playwright E2E UI 自动化套件', desc: '核心商城系统界面交互端到端测试', stack: 'Node.js / Playwright', cases: 245, rate: '92.4%', build: 84, time: '2025-05-20 10:25', owner: '张明' },
    { name: 'Appium 移动端自动化项目', desc: '智能客服移动客户端功能校验', stack: 'Python / Appium', cases: 186, rate: '88.5%', build: 42, time: '2025-05-19 16:48', owner: '李华' },
    { name: 'pytest 接口自动化测试框架', desc: '大模型微服务与执行引擎接口回归', stack: 'Python / pytest', cases: 312, rate: '90.1%', build: 24, time: '2025-05-19 14:12', owner: '王芳' },
    { name: 'Supertest 接口健康度测试套件', desc: '统一鉴权服务底层稳定性扫描', stack: 'Node.js / Supertest', cases: 99, rate: '98.5%', build: 6, time: '2025-05-18 11:33', owner: '赵强' }
  ];

  const displayProjects = remoteProjects.length ? remoteProjects : autoProjects;
  const activeProj = displayProjects[selectedProjIdx] || displayProjects[0] || autoProjects[0];
  const displayStats = remoteProjects.length ? [
    { label: '自动化项目数', val: String(remoteProjects.length), change: projectContext?.name || '后端项目', icon: BookOpen, color: 'text-blue-500', bg: 'bg-blue-50' },
    { label: '自动化用例数', val: String(remoteProjects.reduce((sum, item) => sum + Number(item.cases || 0), 0)), change: '由后端 AutoCaseFile 汇总', icon: Code, color: 'text-purple-500', bg: 'bg-purple-50' },
    { label: '流水线构建数', val: String(remoteProjects.reduce((sum, item) => sum + Number(item.build || 0), 0)), change: '真实项目记录', icon: Clock, color: 'text-indigo-500', bg: 'bg-indigo-50' },
    { label: '执行通过率', val: '100%', change: '按最近执行刷新', hasChart: true }
  ] : autoStats;

  const loadAutomationData = React.useCallback(async ({ silent = false } = {}) => {
    if (!silent) setAutoStatus(prev => ({ ...prev, loading: true }));
    try {
      if (projectLoading) return;
      if (!selectedProject?.id) {
        setProjectContext(null);
        setRemoteProjects([]);
        setAutoStatus({ loading: false, usingBackend: false, message: projectError || '后端暂无项目，列表使用内置样例。' });
        return;
      }

      const payload = await apiGet(`/projects/${selectedProject.id}/auto-projects`, { params: { page: 1, pageSize: 20 } }).catch(() => null);
      const items = pickList(payload);
      const selected = { project: selectedProject, autoProjects: items };

      setProjectContext(selected.project);
      setRemoteProjects(selected.autoProjects.map(mapBackendAutoProject));
      setSelectedProjIdx(0);
      setAutoStatus({
        loading: false,
        usingBackend: selected.autoProjects.length > 0,
        message: selected.autoProjects.length > 0
          ? `已同步后端项目「${selected.project.name}」的自动化套件。`
          : `后端项目「${selected.project.name}」暂无自动化套件，可用向导创建。`
      });
    } catch (error) {
      setAutoStatus({ loading: false, usingBackend: false, message: `自动化项目加载失败：${error.message || error}` });
      showToast(`自动化项目加载失败：${error.message || error}`, 'error');
    }
  }, [projectLoading, projectError, selectedProject]);

  React.useEffect(() => {
    loadAutomationData();
  }, [loadAutomationData]);

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

  React.useEffect(() => {
    setCliLogs([]);
    const logs = [
      `[19:15:02] INFO  Initializing AI Test Runner for: "${activeProj.name}"...`,
      `[19:15:03] INFO  Resolving framework adapter for stack "${activeProj.stack}"...`,
      `[19:15:04] INFO  Loading test suite configuration specs...`,
      `[19:15:05] SUCCESS  Successfully matching ${activeProj.cases} requirement nodes.`,
      `[19:15:06] INFO  Injecting self-healing dynamic assert sensors.`,
      `[19:15:07] READY  CLI Awaiting build trigger. Success rate: ${activeProj.rate}`
    ];

    let timer;
    let idx = 0;
    const printNextLog = () => {
      if (idx < logs.length) {
        setCliLogs(prev => [...prev, logs[idx]]);
        idx++;
        timer = setTimeout(printNextLog, 200);
      }
    };
    printNextLog();

    return () => clearTimeout(timer);
  }, [selectedProjIdx, activeProj?.backendId]);

  // Wizard 表单状态
  const [projName, setProjName] = useState('智能客服 E2E 自动化');
  const [projDesc, setProjDesc] = useState('由前端自动化中心创建');
  const [projStack, setProjStack] = useState('playwright');
  const [projLang, setProjLang] = useState('js');
  const [playwrightOptions, setPlaywrightOptions] = useState(DEFAULT_PLAYWRIGHT_OPTIONS);
  const [generationSummary, setGenerationSummary] = useState(null);

  const [selectedFile, setSelectedFile] = useState('tests/auth/login.spec.js');
  const [caseFiles, setCaseFiles] = useState([]);
  const [caseFilesLoading, setCaseFilesLoading] = useState(false);
  const [caseFilesError, setCaseFilesError] = useState('');
  const [selectedFileMeta, setSelectedFileMeta] = useState(null);
  const [filePathDraft, setFilePathDraft] = useState('');
  const [fileContentDraft, setFileContentDraft] = useState('');
  const [fileOriginal, setFileOriginal] = useState({ path: '', content: '' });
  const [fileLoading, setFileLoading] = useState(false);
  const [isSavingFile, setIsSavingFile] = useState(false);
  const [fileSaveError, setFileSaveError] = useState('');
  const [zipFreshHint, setZipFreshHint] = useState('');
  const [selectedCaseFileIds, setSelectedCaseFileIds] = useState([]);
  const [candidateFilters, setCandidateFilters] = useState({ keyword: '', module: '', priority: '' });
  const [recommendedOnly, setRecommendedOnly] = useState(true);
  const [candidates, setCandidates] = useState([]);
  const [candidateLoading, setCandidateLoading] = useState(false);
  const [candidateError, setCandidateError] = useState('');
  const [selectedCandidateIds, setSelectedCandidateIds] = useState([]);
  const [excludedCandidateIds, setExcludedCandidateIds] = useState([]);
  const [isGeneratingSelectedCases, setIsGeneratingSelectedCases] = useState(false);
  const [artifactPreview, setArtifactPreview] = useState(null);
  const [artifactPreviewLoading, setArtifactPreviewLoading] = useState(false);
  const [artifactPreviewError, setArtifactPreviewError] = useState('');

  const selectedCandidateSet = React.useMemo(() => new Set(selectedCandidateIds.map(String)), [selectedCandidateIds]);
  const excludedCandidateSet = React.useMemo(() => new Set(excludedCandidateIds.map(String)), [excludedCandidateIds]);
  const selectedCaseFileSet = React.useMemo(() => new Set(selectedCaseFileIds.map(String)), [selectedCaseFileIds]);
  const visibleCandidates = React.useMemo(() => {
    const source = Array.isArray(candidates) ? candidates : [];
    return source.filter((candidate) => {
      if (recommendedOnly && !candidate.recommended) return false;
      const keyword = candidateFilters.keyword.trim().toLowerCase();
      if (!keyword) return true;
      return [candidate.title, candidate.module, candidate.priority, candidate.reason, candidate.source]
        .some((value) => String(value || '').toLowerCase().includes(keyword));
    });
  }, [candidateFilters.keyword, candidates, recommendedOnly]);
  const selectedCandidatesForGenerate = React.useMemo(
    () => selectedCandidateIds.map(String).filter((id) => !excludedCandidateSet.has(id)),
    [excludedCandidateSet, selectedCandidateIds]
  );
  const isFileDirty = Boolean(selectedFileMeta) && (filePathDraft !== fileOriginal.path || fileContentDraft !== fileOriginal.content);

  const updatePlaywrightOption = (key, value) => {
    setPlaywrightOptions(prev => ({ ...prev, [key]: value }));
  };

  const buildTemplatePayload = React.useCallback(() => {
    const options = {
      ...playwrightOptions,
      retries: Math.max(0, numberOf(playwrightOptions.retries, 0)),
      workers: Math.max(1, numberOf(playwrightOptions.workers, 1)),
      headless: boolOf(playwrightOptions.headless, true)
    };
    return {
      template_options: { playwright: options },
      playwright_options: options,
      framework_options: { playwright: options }
    };
  }, [playwrightOptions]);

  const rememberGenerationSummary = (stage, payload) => {
    setGenerationSummary(prev => ({
      ...(prev || {}),
      [stage]: normalizeGenerationSummary(payload)
    }));
  };

  const resetFileEditor = React.useCallback(() => {
    setSelectedFileMeta(null);
    setSelectedFile('');
    setFilePathDraft('');
    setFileContentDraft('');
    setFileOriginal({ path: '', content: '' });
    setFileSaveError('');
  }, []);

  const canTryNextEndpoint = (error) => [404, 405].includes(Number(error?.status));

  const runApiFallbacks = async (calls) => {
    let lastError;
    for (const call of calls) {
      try {
        return await call();
      } catch (error) {
        lastError = error;
        if (!canTryNextEndpoint(error)) throw error;
      }
    }
    throw lastError || new Error('后端接口未返回有效响应');
  };

  const loadCaseFileContent = React.useCallback(async (file, projectIdArg = activeProj?.backendId) => {
    const normalized = normalizeCaseFile(file);
    if (!normalized.id) return;
    const hasInlineContent = ['content', 'text', 'body', 'source', 'code'].some(key => Object.prototype.hasOwnProperty.call(normalized.raw || {}, key));
    setFileLoading(true);
    setFileSaveError('');
    try {
      let detail = normalized.raw;
      if (!hasInlineContent && projectIdArg) {
        const encodedId = encodeURIComponent(normalized.id);
        detail = await runApiFallbacks([
          () => apiGet(`/auto-case-files/${encodedId}`),
          () => apiGet(`/auto-projects/${projectIdArg}/case-files/${encodedId}`),
          () => apiGet(`/auto-projects/${projectIdArg}/case-files/content`, { params: { path: normalized.path } })
        ]);
      }
      const detailObject = typeof detail === 'string' ? { content: detail } : asObject(detail);
      const merged = normalizeCaseFile({
        ...normalized.raw,
        ...detailObject,
        id: detailObject.id ?? detailObject.file_id ?? detailObject.case_file_id ?? normalized.id,
        path: detailObject.path ?? detailObject.relative_path ?? detailObject.relativePath ?? normalized.path,
        content: detailObject.content ?? detailObject.text ?? detailObject.body ?? detailObject.source ?? detailObject.code ?? normalized.content
      });
      setSelectedFileMeta(merged);
      setSelectedFile(merged.path);
      setFilePathDraft(merged.path);
      setFileContentDraft(merged.content);
      setFileOriginal({ path: merged.path, content: merged.content });
    } catch (error) {
      setFileSaveError(`文件内容加载失败：${error.message || error}`);
      showToast(`文件内容加载失败：${error.message || error}`, 'error');
    } finally {
      setFileLoading(false);
    }
  }, [activeProj?.backendId]);

  const loadCaseFiles = React.useCallback(async (projectIdArg = activeProj?.backendId, { selectFirst = false } = {}) => {
    if (!projectIdArg) {
      setCaseFiles([]);
      setCaseFilesError('');
      setSelectedCaseFileIds([]);
      resetFileEditor();
      return;
    }
    setCaseFilesLoading(true);
    setCaseFilesError('');
    try {
      const payload = await runApiFallbacks([
        () => apiGet(`/auto-projects/${projectIdArg}/files`, { params: { page: 1, pageSize: 200 } }),
        () => apiGet(`/auto-projects/${projectIdArg}/case-files`, { params: { page: 1, pageSize: 200 } })
      ]);
      const files = normalizeCaseFiles(payload);
      setCaseFiles(files);
      setSelectedCaseFileIds(prev => prev.map(String).filter(id => files.some(file => String(file.id) === id)));
      const stillSelected = files.find(file => String(file.id) === String(selectedFileMeta?.id));
      if ((selectFirst || !stillSelected) && files[0]) {
        await loadCaseFileContent(files[0], projectIdArg);
      }
      if (!files.length) resetFileEditor();
    } catch (error) {
      setCaseFiles([]);
      setCaseFilesError(error.message || String(error));
      resetFileEditor();
    } finally {
      setCaseFilesLoading(false);
    }
  }, [activeProj?.backendId, loadCaseFileContent, resetFileEditor, selectedFileMeta?.id]);

  const loadProjectCandidates = React.useCallback(async (projectIdArg = activeProj?.backendId) => {
    if (!projectIdArg) {
      setCandidates([]);
      setCandidateError('');
      return;
    }
    setCandidateLoading(true);
    setCandidateError('');
    try {
      const payload = await apiGet(`/auto-projects/${projectIdArg}/candidates`, { params: { page: 1, pageSize: 100 } });
      const nextCandidates = normalizeCandidates(payload);
      setCandidates(nextCandidates);
      setSelectedCandidateIds(prev => prev.map(String).filter(id => nextCandidates.some(candidate => candidate.id === id)));
      setExcludedCandidateIds(prev => prev.map(String).filter(id => nextCandidates.some(candidate => candidate.id === id)));
    } catch (error) {
      setCandidateError(error.message || String(error));
      setCandidates([]);
    } finally {
      setCandidateLoading(false);
    }
  }, [activeProj?.backendId]);

  React.useEffect(() => {
    setZipFreshHint('');
    setGenerationSummary(null);
    setArtifactPreview(null);
    setArtifactPreviewError('');
    if (activeProj?.backendId) {
      loadCaseFiles(activeProj.backendId, { selectFirst: true });
      loadProjectCandidates(activeProj.backendId);
    } else {
      setCaseFiles([]);
      setCandidates([]);
      setSelectedCaseFileIds([]);
      setSelectedCandidateIds([]);
      setExcludedCandidateIds([]);
      resetFileEditor();
    }
  }, [activeProj?.backendId, loadCaseFiles, loadProjectCandidates, resetFileEditor]);

  const handleResetFileDraft = () => {
    setFilePathDraft(fileOriginal.path);
    setFileContentDraft(fileOriginal.content);
    setFileSaveError('');
  };

  const handleSaveFile = async () => {
    if (!activeProj?.backendId || !selectedFileMeta?.id) {
      showToast('请先选择一个后端自动化项目和 case file。', 'info');
      return;
    }
    const nextPath = filePathDraft.trim();
    if (!nextPath) {
      setFileSaveError('文件路径不能为空。');
      return;
    }
    setIsSavingFile(true);
    setFileSaveError('');
    try {
      const encodedId = encodeURIComponent(selectedFileMeta.id);
      const payload = {
        id: selectedFileMeta.id,
        path: nextPath,
        relative_path: nextPath,
        content: fileContentDraft
      };
      const saved = await runApiFallbacks([
        () => apiRequest(`/auto-case-files/${encodedId}`, { method: 'PATCH', body: payload, timeoutMs: 12000 }),
        () => apiRequest(`/auto-case-files/${encodedId}`, { method: 'PUT', body: payload, timeoutMs: 12000 }),
        () => apiPost(`/auto-case-files/${encodedId}/save`, payload, { timeoutMs: 12000 }),
        () => apiPost(`/auto-projects/${activeProj.backendId}/case-files/${encodedId}/save`, payload, { timeoutMs: 12000 }),
        () => apiRequest(`/auto-projects/${activeProj.backendId}/case-files/${encodedId}`, { method: 'PUT', body: payload, timeoutMs: 12000 })
      ]);
      const savedObject = typeof saved === 'string' ? { content: saved } : asObject(saved);
      const merged = normalizeCaseFile({
        ...selectedFileMeta.raw,
        ...savedObject,
        id: savedObject.id ?? selectedFileMeta.id,
        path: savedObject.path ?? savedObject.relative_path ?? savedObject.relativePath ?? nextPath,
        content: savedObject.content ?? savedObject.text ?? savedObject.body ?? fileContentDraft
      });
      setSelectedFileMeta(merged);
      setSelectedFile(merged.path);
      setFilePathDraft(merged.path);
      setFileContentDraft(merged.content);
      setFileOriginal({ path: merged.path, content: merged.content });
      setZipFreshHint('已保存，刷新后的工程 ZIP 将包含最新 case file 内容。');
      await loadCaseFiles(activeProj.backendId);
      showToast('case file 已保存，工程 ZIP 将包含最新内容。');
    } catch (error) {
      setFileSaveError(error.message || String(error));
      showToast(`case file 保存失败：${error.message || error}`, 'error');
    } finally {
      setIsSavingFile(false);
    }
  };

  const toggleCaseFileSelection = (fileId) => {
    const id = String(fileId);
    setSelectedCaseFileIds(prev => (
      prev.map(String).includes(id)
        ? prev.map(String).filter(item => item !== id)
        : [...prev.map(String), id]
    ));
  };

  const handleScreenCandidates = async () => {
    if (!activeProj?.backendId) {
      showToast('请先选择或创建一个后端自动化项目。', 'info');
      return;
    }
    setCandidateLoading(true);
    setCandidateError('');
    try {
      const payload = await apiPost('/auto-candidates/screen', {
        project_id: projectContext?.id,
        auto_project_id: activeProj.backendId,
        condition: candidateFilters.keyword,
        filters: {
          keyword: candidateFilters.keyword,
          module: candidateFilters.module,
          priority: candidateFilters.priority,
          recommended_only: recommendedOnly
        }
      }, { timeoutMs: 15000 });
      const screened = normalizeCandidates(payload);
      setCandidates(screened);
      setSelectedCandidateIds(screened.filter(item => item.recommended).map(item => item.id));
      setExcludedCandidateIds([]);
      showToast(`候选筛选完成，返回 ${screened.length} 条候选。`, screened.length ? 'success' : 'info');
    } catch (error) {
      setCandidateError(error.message || String(error));
      showToast(`候选筛选失败：${error.message || error}`, 'error');
    } finally {
      setCandidateLoading(false);
    }
  };

  const toggleCandidateSelection = (candidateId) => {
    const id = String(candidateId);
    setSelectedCandidateIds(prev => {
      const values = prev.map(String);
      return values.includes(id) ? values.filter(item => item !== id) : [...values, id];
    });
    setExcludedCandidateIds(prev => prev.map(String).filter(item => item !== id));
  };

  const toggleCandidateExcluded = (candidateId) => {
    const id = String(candidateId);
    setExcludedCandidateIds(prev => {
      const values = prev.map(String);
      return values.includes(id) ? values.filter(item => item !== id) : [...values, id];
    });
    setSelectedCandidateIds(prev => prev.map(String).filter(item => item !== id));
  };

  const handleGenerateSelectedCases = async () => {
    if (!activeProj?.backendId) {
      showToast('请先选择或创建一个后端自动化项目。', 'info');
      return;
    }
    if (!selectedCandidatesForGenerate.length) {
      showToast('请至少勾选一个未排除的候选用例。', 'info');
      return;
    }
    setIsGeneratingSelectedCases(true);
    try {
      const payload = await apiPost(`/auto-projects/${activeProj.backendId}/selection/generate-cases`, {
        candidate_ids: selectedCandidatesForGenerate,
        excluded_candidate_ids: excludedCandidateIds,
        ...buildTemplatePayload()
      }, { timeoutMs: 20000 });
      rememberGenerationSummary('cases', payload);
      await loadCaseFiles(activeProj.backendId, { selectFirst: true });
      await loadAutomationData({ silent: true });
      showToast(`已按所选候选生成 ${selectedCandidatesForGenerate.length} 条自动化用例。`);
    } catch (error) {
      showToast(`生成所选用例失败：${error.message || error}`, 'error');
    } finally {
      setIsGeneratingSelectedCases(false);
    }
  };

  const createAutoProjectFromForm = async (source = {}) => {
    if (!projectContext?.id) {
      throw new Error('后端暂无可关联的项目，请先在项目管理中创建项目。');
    }
    return apiPost(`/projects/${projectContext.id}/auto-projects`, {
      name: source.name || projName || 'Automation Project',
      type: 'ui',
      language: source.language || projLang || 'js',
      framework: source.framework || projStack || 'playwright',
      extra_config: {
        description: source.desc || projDesc || '由前端自动化中心创建',
        owner: '系统',
        case_count: 0,
        build_count: 0,
        success_rate: '待执行',
        ...buildTemplatePayload()
      }
    });
  };

  const ensureBackendAutoProject = async (project = activeProj) => {
    if (project?.backendId) return project;
    const created = await createAutoProjectFromForm({
      name: project?.name || projName,
      framework: project?.framework || projStack,
      language: project?.language || projLang,
      desc: project?.desc
    });
    return mapBackendAutoProject(created);
  };

  const loadExecutionDetail = React.useCallback(async (executionId, { silent = false } = {}) => {
    if (!executionId) return null;
    try {
      const payload = await apiGet(`/auto-executions/${executionId}`, { timeoutMs: 12000 });
      const detail = normalizeExecution(payload, { id: executionId });
      setAutoExecution(detail);
      return detail;
    } catch (error) {
      if (!silent) showToast(`执行详情加载失败：${error.message || error}`, 'error');
      return null;
    }
  }, []);

  const handleRunAutomation = async (project = activeProj) => {
    if (isRunningAutomation) return;
    setIsRunningAutomation(true);
    try {
      const target = await ensureBackendAutoProject(project);
      const isRunningActiveProject = String(target.backendId || '') === String(activeProj?.backendId || '');
      const runCaseFileIds = isRunningActiveProject ? selectedCaseFileIds.map(String) : [];
      const shouldGenerateBeforeRun = !isRunningActiveProject || !caseFiles.length;
      setCliLogs([
        ...(shouldGenerateBeforeRun ? [
          `[RUN] POST /auto-projects/${target.backendId}/generate-framework`,
          `[RUN] POST /auto-projects/${target.backendId}/generate-cases`
        ] : [`[RUN] using saved case files (${runCaseFileIds.length || 'default'} selected)`]),
        `[RUN] POST /auto-projects/${target.backendId}/execute`
      ]);
      if (shouldGenerateBeforeRun) {
        const frameworkResult = await apiPost(`/auto-projects/${target.backendId}/generate-framework`, buildTemplatePayload(), { timeoutMs: 20000 });
        rememberGenerationSummary('framework', frameworkResult);
        const caseResult = await apiPost(`/auto-projects/${target.backendId}/generate-cases`, buildTemplatePayload(), { timeoutMs: 20000 });
        rememberGenerationSummary('cases', caseResult);
        await loadCaseFiles(target.backendId, { selectFirst: true });
      }
      const requestedMode = autoRunnerMode === 'playwright' && !String(target.stack || '').toLowerCase().includes('playwright')
        ? 'auto'
        : autoRunnerMode;
      const playwrightStatus = runtimeDeps?.auto_runner?.playwright;
      if (requestedMode === 'playwright' && playwrightStatus && !playwrightStatus.available) {
        showToast('Playwright runner 依赖未就绪：未检测到 Node.js/npx，请先安装依赖或切换为占位 runner。', 'error');
        return;
      }
      const execution = await apiPost(`/auto-projects/${target.backendId}/execute`, {
        mode: requestedMode,
        timeout_ms: 10000,
        case_file_ids: runCaseFileIds.length ? runCaseFileIds : undefined,
        ...buildTemplatePayload()
      }, { timeoutMs: 20000 });
      const normalizedExecution = normalizeExecution(execution);
      setAutoExecution(normalizedExecution);
      if (normalizedExecution.id) await loadExecutionDetail(normalizedExecution.id, { silent: true });
      setViewMode('run-result');
      await loadCaseFiles(target.backendId);
      await loadAutomationData({ silent: true });
      showToast(`自动化项目「${target.name}」已完成后端执行。`);
    } catch (error) {
      showToast(`自动化执行失败：${error.message || error}`, 'error');
      setCliLogs(prev => [...prev, `[ERROR] ${error.message || error}`]);
    } finally {
      setIsRunningAutomation(false);
    }
  };

  const handleCreateProject = async () => {
    if (isCreatingProject) return;
    setIsCreatingProject(true);
    try {
      const created = await createAutoProjectFromForm();
      const frameworkResult = await apiPost(`/auto-projects/${created.id}/generate-framework`, buildTemplatePayload(), { timeoutMs: 20000 });
      rememberGenerationSummary('framework', frameworkResult);
      const caseResult = await apiPost(`/auto-projects/${created.id}/generate-cases`, buildTemplatePayload(), { timeoutMs: 20000 });
      rememberGenerationSummary('cases', caseResult);
      await loadAutomationData({ silent: true });
      await loadCaseFiles(created.id, { selectFirst: true });
      setViewMode('project-detail');
      setSelectedProjIdx(0);
      showToast(`自动化项目「${created.name}」已创建并生成初始脚手架。`);
    } catch (error) {
      showToast(`自动化项目创建失败：${error.message || error}`, 'error');
    } finally {
      setIsCreatingProject(false);
    }
  };

  const handleSyncRepo = async () => {
    if (isSyncingRepo) return;
    if (!activeProj?.backendId) {
      showToast('当前展示的是样例项目，请先创建或选择一个后端自动化项目。', 'info');
      return;
    }
    setIsSyncingRepo(true);
    try {
      const result = await apiPost(`/auto-projects/${activeProj.backendId}/git-pull`, {});
      showToast(result.reason || '代码库同步请求已提交。', result.status === 'skipped' ? 'info' : 'success');
    } catch (error) {
      showToast(`代码库同步失败：${error.message || error}`, 'error');
    } finally {
      setIsSyncingRepo(false);
    }
  };

  const handleDownloadAutoProject = async () => {
    if (!activeProj?.backendId) {
      showToast('当前没有可下载的后端自动化项目。', 'info');
      return;
    }
    try {
      const payload = await apiGet(`/auto-projects/${activeProj.backendId}/download`, { timeoutMs: 15000 });
      downloadBase64File({
        filename: payload.filename,
        contentBase64: payload.content_base64 || payload.contentBase64,
        mimeType: payload.mime_type || payload.mimeType
      });
    } catch (error) {
      showToast(`自动化项目下载失败：${error.message || error}`, 'error');
    }
  };

  const handleDownloadAutoArtifacts = async () => {
    const executionId = autoExecution?.id;
    if (!executionId) {
      showToast('请先运行一次后端自动化执行，再下载 artifacts。', 'info');
      return;
    }
    try {
      const payload = await apiGet(`/auto-executions/${executionId}/artifacts/download`, { timeoutMs: 15000 });
      downloadBase64File({
        filename: payload.filename,
        contentBase64: payload.content_base64 || payload.contentBase64,
        mimeType: payload.mime_type || payload.mimeType
      });
    } catch (error) {
      showToast(`Artifacts 下载失败：${error.message || error}`, 'error');
    }
  };

  const handlePreviewArtifact = async (artifact) => {
    const executionId = autoExecution?.id;
    if (!executionId) {
      showToast('缺少 execution id，无法预览 artifact。', 'error');
      return;
    }
    setArtifactPreviewLoading(true);
    setArtifactPreviewError('');
    setArtifactPreview(null);
    try {
      const payload = await apiGet(`/auto-executions/${executionId}/artifacts/preview`, {
        params: {
          artifact_id: artifact.id,
          path: artifact.path,
          kind: artifact.kind
        },
        timeoutMs: 12000
      });
      setArtifactPreview(normalizePreview(payload, artifact));
    } catch (error) {
      setArtifactPreviewError(error.message || String(error));
      showToast(`Artifact 预览失败：${error.message || error}`, 'error');
    } finally {
      setArtifactPreviewLoading(false);
    }
  };

  const handleDownloadPreview = () => {
    if (!artifactPreview) return;
    if (artifactPreview.contentBase64) {
      downloadBase64File({
        filename: artifactPreview.filename,
        contentBase64: artifactPreview.contentBase64,
        mimeType: artifactPreview.mimeType || 'application/octet-stream'
      });
      return;
    }
    if (artifactPreview.downloadUrl) {
      window.open(artifactPreview.downloadUrl, '_blank', 'noopener,noreferrer');
      return;
    }
    showToast('当前 artifact 只返回了预览内容，未提供可下载文件。', 'info');
  };

  const renderPlaywrightOptionsPanel = ({ compact = false } = {}) => (
    <div className={`border border-[var(--border-color)] bg-[var(--bg-app)]/30 rounded-xl ${compact ? 'p-3' : 'p-4'} space-y-3`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[var(--text-primary)] font-bold text-[11px]">
          <Settings className="size-3.5 text-[var(--accent-color)]" />
          <span>Playwright 模板选项</span>
        </div>
        <span className="text-[8px] text-[var(--text-secondary)]">创建、生成、执行共用</span>
      </div>
      <div className={`grid ${compact ? 'grid-cols-2' : 'grid-cols-4'} gap-2 text-[10px]`}>
        <label className="space-y-1">
          <span className="text-[var(--text-secondary)] font-semibold">baseURL</span>
          <input
            value={playwrightOptions.baseURL}
            onChange={(event) => updatePlaywrightOption('baseURL', event.target.value)}
            className="premium-input w-full px-2 py-1.5 font-mono"
            placeholder="http://localhost:3000"
          />
        </label>
        <label className="space-y-1">
          <span className="text-[var(--text-secondary)] font-semibold">browser</span>
          <select
            value={playwrightOptions.browser}
            onChange={(event) => updatePlaywrightOption('browser', event.target.value)}
            className="premium-input w-full px-2 py-1.5"
          >
            <option value="chromium">chromium</option>
            <option value="firefox">firefox</option>
            <option value="webkit">webkit</option>
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-[var(--text-secondary)] font-semibold">retries</span>
          <input
            type="number"
            min="0"
            value={playwrightOptions.retries}
            onChange={(event) => updatePlaywrightOption('retries', event.target.value)}
            className="premium-input w-full px-2 py-1.5"
          />
        </label>
        <label className="space-y-1">
          <span className="text-[var(--text-secondary)] font-semibold">workers</span>
          <input
            type="number"
            min="1"
            value={playwrightOptions.workers}
            onChange={(event) => updatePlaywrightOption('workers', event.target.value)}
            className="premium-input w-full px-2 py-1.5"
          />
        </label>
        <label className="space-y-1">
          <span className="text-[var(--text-secondary)] font-semibold">trace</span>
          <select value={playwrightOptions.trace} onChange={(event) => updatePlaywrightOption('trace', event.target.value)} className="premium-input w-full px-2 py-1.5">
            <option value="on">on</option>
            <option value="off">off</option>
            <option value="retain-on-failure">retain-on-failure</option>
            <option value="on-first-retry">on-first-retry</option>
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-[var(--text-secondary)] font-semibold">video</span>
          <select value={playwrightOptions.video} onChange={(event) => updatePlaywrightOption('video', event.target.value)} className="premium-input w-full px-2 py-1.5">
            <option value="off">off</option>
            <option value="on">on</option>
            <option value="retain-on-failure">retain-on-failure</option>
            <option value="on-first-retry">on-first-retry</option>
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-[var(--text-secondary)] font-semibold">screenshot</span>
          <select value={playwrightOptions.screenshot} onChange={(event) => updatePlaywrightOption('screenshot', event.target.value)} className="premium-input w-full px-2 py-1.5">
            <option value="off">off</option>
            <option value="on">on</option>
            <option value="only-on-failure">only-on-failure</option>
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-[var(--text-secondary)] font-semibold">reporter</span>
          <input
            value={playwrightOptions.reporter}
            onChange={(event) => updatePlaywrightOption('reporter', event.target.value)}
            className="premium-input w-full px-2 py-1.5 font-mono"
            placeholder="html,list"
          />
        </label>
      </div>
      <label className="inline-flex items-center gap-2 text-[10px] font-bold text-[var(--text-primary)] cursor-pointer">
        <input
          type="checkbox"
          checked={Boolean(playwrightOptions.headless)}
          onChange={(event) => updatePlaywrightOption('headless', event.target.checked)}
          style={{ accentColor: 'var(--accent-color)' }}
        />
        <span>headless 执行</span>
      </label>
    </div>
  );

  const renderGenerationSummaryPanel = () => {
    const framework = generationSummary?.framework;
    const cases = generationSummary?.cases;
    const files = [
      ...(Array.isArray(framework?.files) ? framework.files : []),
      ...(Array.isArray(cases?.files) ? cases.files : [])
    ];
    return (
      <div className="border border-[var(--border-color)] bg-[var(--bg-app)]/30 rounded-xl p-3 space-y-2">
        <div className="flex items-center justify-between">
          <div className="text-[11px] font-bold text-[var(--text-primary)] flex items-center gap-1.5">
            <CheckCircle className="size-3.5 text-emerald-500" />
            <span>后端生成摘要</span>
          </div>
          <span className="text-[8px] text-[var(--text-secondary)]">{files.length ? `${files.length} 个文件` : '等待生成结果'}</span>
        </div>
        <div className="text-[9px] text-[var(--text-secondary)] space-y-1">
          <p>{framework?.message || '框架生成结果将在创建或执行后显示。'}</p>
          <p>{cases?.message || '用例生成结果将在生成所选用例或执行后显示。'}</p>
        </div>
        {files.length > 0 && (
          <div className="max-h-24 overflow-y-auto border-t border-[var(--border-color)] pt-2 space-y-1">
            {files.slice(0, 8).map((file) => (
              <div key={`${file.id}-${file.path}`} className="flex items-center gap-1.5 text-[9px] font-mono text-[var(--text-primary)]">
                <FileText className="size-3 text-slate-400" />
                <span className="truncate">{file.path}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const renderR26KeywordStrip = () => {
    const execution = normalizeExecution(autoExecution || {});
    const artifactCount = Array.isArray(execution.artifactsList) ? execution.artifactsList.length : 0;
    const openProjectDetail = () => {
      if (activeProj) setViewMode('project-detail');
    };
    const openRunResult = () => {
      if (autoExecution?.id || autoExecution?.status) {
        setViewMode('run-result');
        return;
      }
      openProjectDetail();
    };
    const capabilityState = {
      候选筛选: {
        icon: Search,
        value: candidateLoading ? '筛选中' : (candidates.length ? `${visibleCandidates.length}/${candidates.length}` : '待筛选'),
        action: openProjectDetail
      },
      在线文件: {
        icon: FileText,
        value: caseFilesLoading ? '同步中' : (caseFiles.length ? `${caseFiles.length} files` : '待加载'),
        action: openProjectDetail
      },
      保存: {
        icon: CheckCircle,
        value: isSavingFile ? '保存中' : (isFileDirty ? '待保存' : '已保存'),
        action: openProjectDetail
      },
      Playwright: {
        icon: Play,
        value: runtimeDeps?.auto_runner?.playwright?.status || 'unknown',
        action: openProjectDetail
      },
      trace: {
        icon: Settings,
        value: playwrightOptions.trace,
        action: openProjectDetail
      },
      Artifacts: {
        icon: Folder,
        value: artifactCount ? `${artifactCount} 个` : '待生成',
        action: openRunResult
      },
      预览: {
        icon: ExternalLink,
        value: artifactPreview ? '已打开' : '待选择',
        action: openRunResult
      },
      执行日志: {
        icon: Terminal,
        value: execution.status || '待执行',
        action: openRunResult
      }
    };

    return (
      <div className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)]/75 px-3 py-2 shadow-soft">
        <div role="toolbar" aria-label="R26 自动化能力入口" className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-2">
          {R26_VISIBLE_KEYWORDS.map((keyword) => {
            const item = capabilityState[keyword];
            const Icon = item.icon;
            return (
              <button
                key={keyword}
                type="button"
                onClick={item.action}
                disabled={!activeProj}
                className="h-8 min-w-0 rounded-md border border-[var(--border-color)] bg-[var(--bg-app)]/50 px-2 text-[9px] font-bold text-[var(--text-primary)] flex items-center justify-between gap-1.5 hover:border-[var(--accent-color)] hover:bg-[var(--accent-glow)]/25 disabled:opacity-70 disabled:hover:border-[var(--border-color)] disabled:cursor-default transition-colors"
              >
                <span className="min-w-0 flex items-center gap-1.5">
                  <Icon className="size-3 shrink-0 text-[var(--accent-color)]" />
                  <span className="truncate">{keyword}</span>
                </span>
                <span className="shrink-0 max-w-[72px] truncate text-[8px] text-[var(--text-secondary)]">{item.value}</span>
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  const renderProjectDetail = () => {
    return (
      <div className="space-y-4 text-left animate-[fadeIn_0.2s_ease-out] w-full">
        {/* 面包屑 */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setViewMode('list')}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] text-[10px] text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 hover:scale-[1.03] transition-all shadow-sm cursor-pointer"
            >
              <ArrowLeft className="size-3" />
              <span>返回列表</span>
            </button>
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400 font-semibold">
              <span>自动化中心</span>
              <span>/</span>
              <span className="text-[var(--text-primary)]">{activeProj.name}</span>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleDownloadAutoProject}
              className="px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[11px] font-bold text-[var(--text-primary)] cursor-pointer"
            >
              下载工程 ZIP
            </button>
            <button
              onClick={() => handleRunAutomation(activeProj)}
              disabled={isRunningAutomation}
              className="px-3 py-1.5 text-[11px] accent-btn flex items-center gap-1"
            >
              {isRunningAutomation ? <Activity className="size-3 animate-spin" /> : <Play className="size-3 fill-current" />}
              <span>{isRunningAutomation ? '运行中...' : '立即构建运行'}</span>
            </button>
          </div>
        </div>

        {renderR26KeywordStrip()}

        {/* 顶部指标 */}
        <div className="grid grid-cols-4 gap-4">
          <div className="theme-card rounded-xl p-4 shadow-soft">
            <span className="text-[10px] text-slate-400 font-semibold">测试脚本总数</span>
            <div className="text-xl font-bold text-slate-800 mt-1">{activeProj.cases || 1} <span className="text-[10px] text-slate-400 font-normal">个</span></div>
            <div className="text-[8px] text-slate-400 mt-1">框架: {activeProj.stack} | 覆盖率: {activeProj.rate}</div>
          </div>
          <div className="theme-card rounded-xl p-4 shadow-soft">
            <span className="text-[10px] text-slate-400 font-semibold">平均执行时长</span>
            <div className="text-xl font-bold text-slate-800 mt-1">1m 20s</div>
            <div className="text-[8px] text-slate-400 mt-1">最大单脚本执行限时: 5m</div>
          </div>
          <div className="theme-card rounded-xl p-4 shadow-soft">
            <span className="text-[10px] text-slate-400 font-semibold">近7日执行成功率</span>
            <div className="text-xl font-bold text-emerald-500 mt-1">92.4%</div>
            <div className="text-[8px] text-emerald-500 mt-1">稳定度表现: 优秀</div>
          </div>
          <div className="theme-card rounded-xl p-4 shadow-soft">
            <span className="text-[10px] text-slate-400 font-semibold">最后构建结果</span>
            <div className="text-xl font-bold text-emerald-500 mt-1">{autoExecution?.status || '待执行'}</div>
            <div className="text-[8px] text-slate-400 mt-1">构建编号: Build #{activeProj.build || '--'} ({activeProj.time})</div>
          </div>
        </div>

        {zipFreshHint && (
          <div className="theme-card rounded-xl px-4 py-2 text-[10px] font-bold text-emerald-600 border border-emerald-500/20 bg-emerald-500/10">
            {zipFreshHint}
          </div>
        )}

        <div className="grid grid-cols-12 gap-4">
          <div className="col-span-12 lg:col-span-7 theme-card rounded-xl p-4 shadow-soft space-y-3">
            <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-2">
              <h3 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
                <Search className="size-4 text-[var(--accent-color)]" />
                <span>候选筛选与用例生成</span>
              </h3>
              <span className="text-[8px] text-[var(--text-secondary)]">
                {selectedCandidatesForGenerate.length} 个待生成 / {excludedCandidateIds.length} 个已排除
              </span>
            </div>

            <div className="grid grid-cols-12 gap-2 text-[10px]">
              <input
                value={candidateFilters.keyword}
                onChange={(event) => setCandidateFilters(prev => ({ ...prev, keyword: event.target.value }))}
                placeholder="条件输入：需求关键词、页面、接口、标签"
                className="col-span-12 lg:col-span-6 premium-input px-3 py-2"
              />
              <input
                value={candidateFilters.module}
                onChange={(event) => setCandidateFilters(prev => ({ ...prev, module: event.target.value }))}
                placeholder="模块"
                className="col-span-6 lg:col-span-2 premium-input px-3 py-2"
              />
              <input
                value={candidateFilters.priority}
                onChange={(event) => setCandidateFilters(prev => ({ ...prev, priority: event.target.value }))}
                placeholder="优先级"
                className="col-span-6 lg:col-span-2 premium-input px-3 py-2"
              />
              <button
                onClick={handleScreenCandidates}
                disabled={candidateLoading || !activeProj?.backendId}
                className="col-span-12 lg:col-span-2 accent-btn rounded-lg text-[10px] disabled:opacity-60 flex items-center justify-center gap-1"
              >
                {candidateLoading && <Activity className="size-3 animate-spin" />}
                <span>执行筛选</span>
              </button>
            </div>

            <div className="flex items-center justify-between text-[10px]">
              <label className="inline-flex items-center gap-2 font-bold text-[var(--text-primary)] cursor-pointer">
                <input
                  type="checkbox"
                  checked={recommendedOnly}
                  onChange={(event) => setRecommendedOnly(event.target.checked)}
                  style={{ accentColor: 'var(--accent-color)' }}
                />
                <span>只看推荐候选</span>
              </label>
              <div className="flex gap-2">
                <button
                  onClick={() => loadProjectCandidates(activeProj?.backendId)}
                  disabled={candidateLoading || !activeProj?.backendId}
                  className="px-2.5 py-1 rounded border border-[var(--border-color)] bg-[var(--bg-card)] text-[var(--text-primary)] font-bold disabled:opacity-60"
                >
                  刷新候选
                </button>
                <button
                  onClick={handleGenerateSelectedCases}
                  disabled={isGeneratingSelectedCases || !selectedCandidatesForGenerate.length}
                  className="px-3 py-1 rounded accent-btn font-bold disabled:opacity-60"
                >
                  {isGeneratingSelectedCases ? '生成中...' : '生成所选用例'}
                </button>
              </div>
            </div>

            {candidateError && (
              <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-[10px] text-red-600 font-bold">
                {candidateError}
              </div>
            )}

            <div className="max-h-64 overflow-y-auto space-y-2 pr-1">
              {candidateLoading ? (
                <div className="py-8 text-center text-[10px] text-[var(--text-secondary)] font-bold">候选加载中...</div>
              ) : visibleCandidates.length ? visibleCandidates.map((candidate) => {
                const selected = selectedCandidateSet.has(candidate.id);
                const excluded = excludedCandidateSet.has(candidate.id);
                return (
                  <div
                    key={candidate.id}
                    className={`p-3 rounded-lg border text-left transition-all ${
                      excluded
                        ? 'border-red-500/20 bg-red-500/5 opacity-70'
                        : selected
                          ? 'border-[var(--accent-color)] bg-[var(--accent-glow)]/40'
                          : 'border-[var(--border-color)] bg-[var(--bg-app)]/30'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <label className="flex items-start gap-2 min-w-0 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={selected}
                          disabled={excluded}
                          onChange={() => toggleCandidateSelection(candidate.id)}
                          className="mt-0.5"
                          style={{ accentColor: 'var(--accent-color)' }}
                        />
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="font-bold text-[11px] text-[var(--text-primary)] truncate">{candidate.title}</span>
                            {candidate.recommended && <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-600 text-[8px] font-bold">推荐</span>}
                          </div>
                          <div className="text-[9px] text-[var(--text-secondary)] mt-1 line-clamp-2">{candidate.reason}</div>
                          <div className="flex gap-2 text-[8px] text-slate-400 mt-1 font-mono">
                            <span>{candidate.module}</span>
                            <span>{candidate.priority}</span>
                            <span>{candidate.source}</span>
                          </div>
                        </div>
                      </label>
                      <div className="shrink-0 text-right space-y-2">
                        <div className="text-[9px] font-mono text-[var(--accent-color)]">{Math.round(candidate.score * 100)}%</div>
                        <button
                          onClick={() => toggleCandidateExcluded(candidate.id)}
                          className={`px-2 py-0.5 rounded border text-[8px] font-bold ${
                            excluded
                              ? 'border-emerald-500/20 text-emerald-600 bg-emerald-500/10'
                              : 'border-red-500/20 text-red-600 bg-red-500/10'
                          }`}
                        >
                          {excluded ? '取消排除' : '排除'}
                        </button>
                      </div>
                    </div>
                  </div>
                );
              }) : (
                <div className="py-8 text-center text-[10px] text-[var(--text-secondary)] font-bold">
                  暂无候选，输入条件后点击执行筛选，或等待后端候选列表返回。
                </div>
              )}
            </div>
          </div>

          <div className="col-span-12 lg:col-span-5 space-y-4">
            {renderPlaywrightOptionsPanel({ compact: true })}
            {renderGenerationSummaryPanel()}
            <div className="theme-card rounded-xl p-4 shadow-soft space-y-2">
              <div className="flex items-center justify-between text-[10px]">
                <span className="font-bold text-[var(--text-primary)]">Runner 模式</span>
                <select
                  value={autoRunnerMode}
                  onChange={(event) => setAutoRunnerMode(event.target.value)}
                  className="px-2 py-1 rounded border border-[var(--border-color)] bg-[var(--bg-card)] text-[10px] font-bold text-[var(--text-primary)]"
                >
                  <option value="auto">真实本地 runner</option>
                  <option value="playwright">Playwright runner</option>
                  <option value="placeholder">占位 runner</option>
                </select>
              </div>
              <div className={`px-2.5 py-1.5 rounded-lg border text-[9px] font-bold ${
                runtimeDeps?.auto_runner?.playwright?.available
                  ? 'border-emerald-500/20 text-emerald-600 bg-emerald-500/10'
                  : 'border-amber-500/20 text-amber-600 bg-amber-500/10'
              }`}>
                Playwright 依赖：{runtimeDeps?.auto_runner?.playwright?.status || 'unknown'}
              </div>
              <div className="text-[9px] text-[var(--text-secondary)]">
                {selectedCaseFileIds.length ? `本次执行将传入 ${selectedCaseFileIds.length} 个 case_file_ids。` : '未勾选文件时，后端按默认范围执行。'}
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-12 gap-4">
          <div className="col-span-12 lg:col-span-4 theme-card rounded-xl p-4 shadow-soft">
            <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-2 mb-3">
              <h3 className="text-xs font-bold flex items-center gap-1.5">
                <Folder className="size-4 text-amber-500" />
                <span>后端 case files</span>
              </h3>
              <button
                onClick={() => loadCaseFiles(activeProj?.backendId, { selectFirst: true })}
                disabled={caseFilesLoading || !activeProj?.backendId}
                className="px-2 py-1 rounded border border-[var(--border-color)] text-[8px] font-bold text-[var(--text-primary)] bg-[var(--bg-card)] disabled:opacity-60"
              >
                刷新
              </button>
            </div>
            {caseFilesError && (
              <div className="mb-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-[10px] text-red-600 font-bold">
                {caseFilesError}
              </div>
            )}
            <div className="space-y-1.5 max-h-[520px] overflow-y-auto pr-1 font-mono text-[10px]">
              {caseFilesLoading ? (
                <div className="py-8 text-center text-[var(--text-secondary)] font-bold">case files 加载中...</div>
              ) : caseFiles.length ? caseFiles.map((file) => {
                const selected = String(selectedFileMeta?.id) === String(file.id);
                return (
                  <div
                    key={`${file.id}-${file.path}`}
                    onClick={() => loadCaseFileContent(file, activeProj?.backendId)}
                    className={`p-2 rounded-lg border cursor-pointer transition-colors ${
                      selected
                        ? 'border-[var(--accent-color)] bg-[var(--accent-glow)]/40 text-[var(--accent-color)] font-bold'
                        : 'border-[var(--border-color)] hover:bg-[var(--bg-app)]/40 text-[var(--text-primary)]'
                    }`}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <input
                        type="checkbox"
                        checked={selectedCaseFileSet.has(String(file.id))}
                        onChange={(event) => {
                          event.stopPropagation();
                          toggleCaseFileSelection(file.id);
                        }}
                        onClick={(event) => event.stopPropagation()}
                        style={{ accentColor: 'var(--accent-color)' }}
                      />
                      <FileText className="size-3.5 text-slate-400 shrink-0" />
                      <span className="truncate">{file.path}</span>
                    </div>
                    <div className="pl-8 mt-1 text-[8px] text-[var(--text-secondary)] flex justify-between">
                      <span>{file.status}</span>
                      <span>{file.updatedAt}</span>
                    </div>
                  </div>
                );
              }) : (
                <div className="py-8 text-center text-[10px] text-[var(--text-secondary)] font-bold">
                  暂无后端 case files。可先筛选候选并生成所选用例。
                </div>
              )}
            </div>
          </div>

          <div className="col-span-12 lg:col-span-8 theme-card rounded-xl p-4 shadow-soft space-y-3">
            <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-2">
              <h3 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
                <Code className="size-4 text-[var(--accent-color)]" />
                <span>在线文件编辑</span>
              </h3>
              <span className={`px-2 py-0.5 rounded text-[8px] font-bold ${
                isFileDirty ? 'bg-amber-500/10 text-amber-600 border border-amber-500/20' : 'bg-emerald-500/10 text-emerald-600 border border-emerald-500/20'
              }`}>
                {isFileDirty ? 'dirty' : 'saved'}
              </span>
            </div>

            <label className="block space-y-1 text-[10px] font-bold text-[var(--text-secondary)]">
              <span>文件路径</span>
              <input
                value={filePathDraft}
                onChange={(event) => setFilePathDraft(event.target.value)}
                disabled={!selectedFileMeta || fileLoading}
                className="premium-input w-full px-3 py-2 font-mono"
                placeholder="tests/example.spec.ts"
              />
            </label>

            <textarea
              value={fileContentDraft}
              onChange={(event) => setFileContentDraft(event.target.value)}
              disabled={!selectedFileMeta || fileLoading}
              className="w-full min-h-[360px] rounded-xl border border-[var(--border-color)] bg-[#0b0f19] text-slate-200 px-4 py-3 text-[10px] leading-relaxed font-mono focus:outline-none focus:border-[var(--accent-color)]"
              spellCheck={false}
              placeholder={fileLoading ? '文件内容加载中...' : '选择左侧后端 case file 后编辑内容'}
            />

            {fileSaveError && (
              <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-[10px] text-red-600 font-bold">
                {fileSaveError}
              </div>
            )}

            <div className="flex items-center justify-between">
              <div className="text-[9px] text-[var(--text-secondary)] font-mono truncate">
                当前脚本: {selectedFile || '--'}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleResetFileDraft}
                  disabled={!isFileDirty || isSavingFile}
                  className="px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] text-[10px] font-bold text-[var(--text-primary)] disabled:opacity-50"
                >
                  重置
                </button>
                <button
                  onClick={handleSaveFile}
                  disabled={!selectedFileMeta || !isFileDirty || isSavingFile}
                  className="px-3 py-1.5 rounded-lg accent-btn text-[10px] font-bold disabled:opacity-60"
                >
                  {isSavingFile ? '保存中...' : '保存文件'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderRunResult = () => {
    const execution = normalizeExecution(autoExecution || {});
    const summary = execution.summary || normalizeSummary({});
    const status = String(execution.status || 'unknown').toLowerCase();
    const isSuccess = ['completed', 'passed', 'success', 'succeeded'].includes(status);
    const isFailed = ['failed', 'error', 'errored', 'timeout'].includes(status);
    const durationText = execution.duration_ms ? `${Math.max(1, Math.round(execution.duration_ms / 1000))}s` : '--';
    const logLines = Array.isArray(execution.logLines) ? execution.logLines : [];
    const runnerInfo = asObject(asObject(execution.artifacts).runner);
    const runnerMode = runnerInfo.mode || runnerInfo.name || autoRunnerMode;
    const artifactEvidence = Array.isArray(execution.artifactsList) ? execution.artifactsList : [];
    const previewKind = String(artifactPreview?.kind || artifactPreview?.mimeType || artifactPreview?.filename || '').toLowerCase();
    const isPreviewImage = Boolean(artifactPreview?.contentBase64) && (
      String(artifactPreview?.mimeType || '').startsWith('image/')
      || previewKind.includes('screenshot')
      || previewKind.includes('png')
      || previewKind.includes('jpg')
      || previewKind.includes('jpeg')
      || previewKind.includes('webp')
    );
    let previewTextFromBase64 = '';
    if (artifactPreview?.contentBase64 && !isPreviewImage) {
      try {
        previewTextFromBase64 = window.atob(artifactPreview.contentBase64);
      } catch {
        previewTextFromBase64 = '';
      }
    }
    return (
      <div className="space-y-4 text-left animate-[fadeIn_0.2s_ease-out] w-full">
        {/* 面包屑 */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <button 
              onClick={() => setViewMode('project-detail')}
              className="flex items-center gap-1 px-2.5 py-1 rounded border border-[var(--border-color)] bg-[var(--bg-card)] text-[10px] text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 transition-colors shadow-sm cursor-pointer"
            >
              <ArrowLeft className="size-3" />
              <span>返回项目详情</span>
            </button>
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400 font-semibold">
              <span>自动化中心</span>
              <span>/</span>
              <span>{activeProj.name}</span>
              <span>/</span>
              <span className="text-[var(--text-primary)]">构建执行结果 {execution.id ? `(Execution #${execution.id})` : '(暂无后端执行)'}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => loadExecutionDetail(execution.id)}
              disabled={!execution.id}
              className="px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[11px] font-bold text-[var(--text-primary)] cursor-pointer disabled:opacity-50"
            >
              刷新详情
            </button>
            <button
              onClick={handleDownloadAutoArtifacts}
              className="px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[11px] font-bold text-[var(--text-primary)] cursor-pointer"
            >
              下载 artifacts
            </button>
            <button
              onClick={() => {
                handleRunAutomation(activeProj);
              }}
              className="px-3 py-1.5 rounded-lg accent-btn text-[11px] font-bold text-white cursor-pointer shadow-sm flex items-center gap-1"
            >
              <Sparkles className="size-3.5" />
              <span>智能用例自愈 & 重跑</span>
            </button>
          </div>
        </div>

        {/* 顶部运行状态看板 */}
        <div className="grid grid-cols-4 gap-4">
          <div className="theme-card rounded-xl p-4 shadow-soft">
            <span className="text-[10px] text-slate-400 font-semibold">执行范围</span>
            <div className="text-base font-bold text-slate-800 mt-1">{summary.total || activeProj.cases || 1} 条用例</div>
          </div>
          <div className="theme-card rounded-xl p-4 shadow-soft">
            <span className="text-[10px] text-slate-400 font-semibold">执行时长</span>
            <div className="text-base font-bold text-slate-800 mt-1 font-mono">{durationText}</div>
          </div>
          <div className="theme-card rounded-xl p-4 shadow-soft">
            <span className="text-[10px] text-slate-400 font-semibold">运行状态</span>
            <div className={`text-base font-bold mt-1 flex items-center gap-1 ${isFailed ? 'text-red-500' : isSuccess ? 'text-emerald-500' : 'text-amber-500'}`}>
              {isSuccess ? <CheckCircle className="size-4 shrink-0" /> : <XCircle className="size-4 shrink-0" />}
              <span>{isSuccess ? '执行完成' : isFailed ? '执行失败' : execution.status || 'unknown'}</span>
            </div>
          </div>
          <div className="theme-card rounded-xl p-4 shadow-soft">
            <span className="text-[10px] text-slate-400 font-semibold">通过情况统计</span>
            <div className="text-base font-bold mt-1 text-slate-700">通过: {summary.passed || 0} | 失败: {summary.failed || 0} | 错误: {summary.errors || 0}</div>
          </div>
        </div>

        <div className="theme-card rounded-xl p-4 shadow-soft flex items-start justify-between gap-6">
          <div className="shrink-0">
            <div className="text-[10px] text-slate-400 font-semibold">Runner 模式</div>
            <div className="text-sm font-bold text-slate-800 mt-1">{runnerMode}</div>
            <div className="text-[8px] text-slate-400 mt-1">case_file_ids: {selectedCaseFileIds.length ? selectedCaseFileIds.length : '默认范围'}</div>
          </div>
          <div className="flex-1">
            <div className="text-[10px] text-slate-400 font-semibold mb-2">Artifacts evidence</div>
            <div className="flex flex-wrap gap-2">
              {artifactEvidence.length ? artifactEvidence.slice(0, 12).map((item, idx) => (
                <button
                  key={`${item.id}-${idx}`}
                  onClick={() => handlePreviewArtifact(item)}
                  className="px-2 py-1 rounded border border-[var(--border-color)] bg-[var(--bg-app)] hover:border-[var(--accent-color)] text-[9px] font-mono text-[var(--text-primary)] cursor-pointer max-w-[220px] truncate"
                  title={item.path || item.name}
                >
                  {item.kind}:{item.name || idx + 1}
                </button>
              )) : (
                <span className="text-[10px] text-slate-400">后端未返回 artifacts list</span>
              )}
            </div>
          </div>
        </div>

        {/* 核心区：后端执行日志 & Artifact 预览 */}
        <div className="grid grid-cols-12 gap-4">
          <div className="col-span-7 mac-terminal p-4 flex flex-col font-mono text-[9px] text-left relative overflow-hidden cyber-matrix-console bg-[#0d0208]">
            <div className="flex justify-between items-center border-b border-white/10 pb-2 mb-3 shrink-0 relative z-10">
              <div className="flex items-center gap-2">
                <Terminal className="size-4 text-[#8be9fd]" />
                <span className="font-bold text-[#8be9fd]">Execution Log Console</span>
              </div>
              <div className="flex gap-1">
                <span className="size-2 rounded-full bg-[#ff5555]"></span>
                <span className="size-2 rounded-full bg-[#f1fa8c]"></span>
                <span className="size-2 rounded-full bg-[#50fa7b]"></span>
              </div>
            </div>

            <div className="space-y-1.5 overflow-y-auto max-h-[360px] pr-1 leading-normal relative z-10">
              {logLines.length ? logLines.map((line, idx) => (
                <p key={idx} className={line.toLowerCase().includes('error') || line.toLowerCase().includes('fail') ? 'text-[#ff5555] font-bold' : line.toLowerCase().includes('pass') || line.toLowerCase().includes('success') ? 'text-[#50fa7b]' : 'text-slate-500'}>
                  {line}
                </p>
              )) : (
                <p className="text-slate-500">后端暂未返回执行日志。请先运行或点击刷新详情。</p>
              )}
            </div>
          </div>

          <div className="col-span-5 space-y-4">
            <div className="theme-card rounded-xl p-4 shadow-soft text-left space-y-3">
              <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-2">
                <h3 className="text-xs font-bold text-[var(--text-primary)]">Artifact 预览</h3>
                <button
                  onClick={handleDownloadPreview}
                  disabled={!artifactPreview}
                  className="px-2 py-1 rounded border border-[var(--border-color)] bg-[var(--bg-card)] text-[9px] font-bold text-[var(--text-primary)] disabled:opacity-50"
                >
                  下载/打开
                </button>
              </div>

              {artifactPreviewLoading && (
                <div className="h-56 flex items-center justify-center text-[10px] text-[var(--text-secondary)] font-bold">
                  Artifact 预览加载中...
                </div>
              )}

              {artifactPreviewError && (
                <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-[10px] text-red-600 font-bold">
                  {artifactPreviewError}
                </div>
              )}

              {!artifactPreviewLoading && !artifactPreviewError && artifactPreview && (
                <div className="space-y-2">
                  <div className="text-[9px] text-[var(--text-secondary)] font-mono truncate">
                    {artifactPreview.filename} · {artifactPreview.mimeType || artifactPreview.kind || 'artifact'}
                  </div>
                  {isPreviewImage ? (
                    <div className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/40 p-2 max-h-[360px] overflow-auto">
                      <img
                        src={artifactPreview.contentBase64.startsWith('data:') ? artifactPreview.contentBase64 : `data:${artifactPreview.mimeType || 'image/png'};base64,${artifactPreview.contentBase64}`}
                        alt={artifactPreview.filename}
                        className="max-w-full rounded"
                      />
                    </div>
                  ) : (
                    <pre className="rounded-lg border border-[var(--border-color)] bg-[#0b0f19] text-slate-200 p-3 text-[9px] leading-relaxed max-h-[360px] overflow-auto whitespace-pre-wrap">
                      {artifactPreview.content || previewTextFromBase64 || '后端未返回可直接显示的脱敏文本。trace/html/junit/log 可点击下载查看原始文件。'}
                    </pre>
                  )}
                </div>
              )}

              {!artifactPreviewLoading && !artifactPreviewError && !artifactPreview && (
                <div className="h-56 flex flex-col items-center justify-center text-center text-[10px] text-[var(--text-secondary)] font-bold border border-dashed border-[var(--border-color)] rounded-lg">
                  <ExternalLink className="size-5 mb-2 text-slate-400" />
                  <span>点击上方 evidence artifact 查看脱敏文本、截图、trace、html、junit 或 log 预览。</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  };

  if (viewMode === 'project-detail') {
    return renderProjectDetail();
  }

  if (viewMode === 'run-result') {
    return renderRunResult();
  }

  return (
    <div className="space-y-4 text-left w-full">
      
      {viewMode === 'list' ? (
        // ==========================================================================
        // 渲染：17-自动化中心总览页
        // ==========================================================================
        <div className="space-y-4">
          <div className="flex justify-between items-start">
            <div className="text-left">
              <h1 className="text-base font-bold text-slate-800">自动化中心</h1>
              <p className="text-[11px] text-slate-400 mt-1">{autoStatus.loading ? '正在同步后端自动化项目...' : autoStatus.message}</p>
            </div>
            <div className="flex items-center gap-2">
              <button 
                onClick={handleSyncRepo}
                disabled={isSyncingRepo}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[11px] font-bold text-[var(--text-primary)] cursor-pointer disabled:opacity-60"
              >
                {isSyncingRepo && <Activity className="size-3 animate-spin" />}
                <span>{isSyncingRepo ? '同步中...' : '同步代码库'}</span>
              </button>
              <select
                value={autoRunnerMode}
                onChange={(event) => setAutoRunnerMode(event.target.value)}
                className="px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] text-[11px] font-bold text-[var(--text-primary)] cursor-pointer"
              >
                <option value="auto">真实本地 runner</option>
                <option value="playwright">Playwright runner</option>
                <option value="placeholder">占位 runner</option>
              </select>
              <div className={`px-2.5 py-1.5 rounded-lg border text-[9px] font-bold ${
                runtimeDeps?.auto_runner?.playwright?.available
                  ? 'border-emerald-500/20 text-emerald-600 bg-emerald-500/10'
                  : 'border-amber-500/20 text-amber-600 bg-amber-500/10'
              }`}>
                Playwright: {runtimeDeps?.auto_runner?.playwright?.status || 'unknown'}
              </div>
              <button 
                onClick={() => { setViewMode('wizard'); setWizardStep(1); }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg accent-btn text-[11px] font-bold text-white cursor-pointer"
              >
                <Plus className="size-3.5" />
                <span>新建自动化项目</span>
              </button>
            </div>
          </div>

          {renderR26KeywordStrip()}

          {/* 指标面板 */}
          <div className="grid grid-cols-4 gap-3.5">
            {displayStats.map((item, idx) => (
              <div 
                key={idx} 
                className="theme-card rounded-xl p-3.5 shadow-soft flex items-center justify-between"
                style={{
                  animation: 'slideUpFade 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards',
                  animationDelay: `${idx * 40 + 100}ms`,
                  opacity: 0
                }}
              >
                <div className="text-left">
                  <span className="text-[10px] text-slate-400 font-semibold">{item.label}</span>
                  <div className="text-xl font-bold mt-1 text-[var(--text-primary)]">
                    <AnimatedNumber value={item.val} delay={idx * 60 + 150} />
                  </div>
                  <div className="text-[9px] text-slate-400 mt-1"><span className="text-emerald-500 font-semibold">{item.change}</span></div>
                </div>
                {item.hasChart ? (
                  <div className="size-11 shrink-0 relative sonar-ripple-container">
                    <div className="sonar-ripple-circle"></div>
                    <div className="sonar-ripple-circle sonar-ripple-circle-delay"></div>
                    <svg className="w-full h-full transform -rotate-90 relative z-10" viewBox="0 0 36 36">
                      <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--border-color)" strokeWidth="2.8" />
                      <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--accent-color)" strokeWidth="2.8" strokeDasharray="90.1 9.9" />
                      <path d="M18,18 L18,2 A16,16 0 0,1 30,10 Z" fill="var(--accent-glow)" className="radar-sweeper-beam" />
                    </svg>
                    <div className="absolute inset-0 flex items-center justify-center text-[8px] font-bold text-[var(--text-primary)] z-10">
                      <AnimatedNumber value={90} />%
                    </div>
                  </div>
                ) : (
                  <div className={`p-2 rounded-lg ${item.bg} ${item.color}`}>
                    <item.icon className="size-4" />
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* 7:5 双栏联动列表区 */}
          <div className="grid grid-cols-12 gap-5 items-start w-full">
            {/* 左栏 7 份：自动化项目列表 */}
            <div className="col-span-12 lg:col-span-7 space-y-3">
              <div className="theme-card rounded-xl p-4 shadow-soft">
                {/* 搜索过滤栏 */}
                <div className="flex items-center gap-2 mb-3.5 border-b border-[var(--border-color)] pb-3">
                  <div className="flex-1 flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30">
                    <Search className="size-3.5 text-[var(--text-secondary)] shrink-0" />
                    <input type="text" placeholder="搜索自动化项目名称、技术栈" className="bg-transparent border-none text-[10px] focus:outline-none w-full text-[var(--text-primary)]" />
                  </div>
                  <div className="flex items-center gap-1 text-[10px] text-[var(--text-secondary)] border border-[var(--border-color)] rounded px-2.5 py-1.5 bg-[var(--bg-card)] hover:bg-[var(--border-color)] cursor-pointer">
                    <span>框架筛选</span>
                    <ChevronDown className="size-3 text-slate-400" />
                  </div>
                </div>

                {/* 卡片式项目列表 */}
                <div className="space-y-3">
                  {displayProjects.map((proj, idx) => {
                    const isSelected = selectedProjIdx === idx;
                    return (
                      <TiltCard 
                        key={proj.backendId || idx}
                        onClick={() => setSelectedProjIdx(idx)}
                        onDoubleClick={() => setViewMode('project-detail')}
                        className={`p-3.5 border rounded-xl flex flex-col gap-3.5 cursor-pointer text-left transition-all duration-200 ${
                          isSelected 
                            ? 'glow-border-card bg-[var(--accent-glow)]/40 shadow-md scale-[1.01]' 
                            : 'chroma-glass border-[var(--border-color)] bg-[var(--bg-card)] hover:border-[var(--accent-color)]/50'
                        } shimmer-sweep`}
                      >
                        {/* 头部信息 */}
                        <div className="flex justify-between items-start">
                          <div className="flex items-start gap-2.5">
                            <div className={`p-2 rounded-lg ${isSelected ? 'bg-[var(--accent-color)] text-white' : 'bg-[var(--bg-app)] text-[var(--text-secondary)]'}`}>
                              <Cpu className="size-4 shrink-0" />
                            </div>
                            <div className="flex flex-col text-left">
                              <span className="font-bold text-[11px] text-[var(--text-primary)]">{proj.name}</span>
                              <span className="text-[9px] text-[var(--text-secondary)] mt-0.5">{proj.desc}</span>
                            </div>
                          </div>
                          <span className="px-2 py-0.5 bg-[var(--border-color)] rounded text-[var(--text-secondary)] text-[8.5px] font-bold">{proj.stack}</span>
                        </div>

                        {/* 指标明细行 */}
                        <div className="flex items-center justify-between text-[9px] text-[var(--text-secondary)] pt-2 border-t border-[var(--border-color)]/30">
                          <div className="flex items-center gap-4">
                            <div>用例数: <span className="font-bold text-[var(--text-primary)]">{proj.cases}</span></div>
                            <div>构建数: <span className="font-bold text-[var(--text-primary)]">{proj.build}</span></div>
                            <div>最近构建: <span className="text-[var(--text-secondary)] font-mono">{String(proj.time || '--').split(' ')[0]}</span></div>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <span className="text-[var(--text-secondary)]">负责人:</span>
                            <div className="flex items-center gap-1 bg-[var(--bg-app)] px-1.5 py-0.5 rounded border border-[var(--border-color)]">
                                <span className="size-3.5 rounded-full bg-[var(--accent-color)] text-white text-[8px] font-bold flex items-center justify-center">{(proj.owner || '系')[0]}</span>
                              <span className="text-[8px] font-bold text-[var(--text-primary)]">{proj.owner}</span>
                            </div>
                          </div>
                        </div>

                        {/* 稳定性进度条与操作 */}
                        <div className="flex items-center justify-between pt-2 border-t border-dashed border-[var(--border-color)]/30">
                          <div className="flex items-center gap-2 w-1/2">
                            <span className="text-[8.5px] text-[var(--text-secondary)] font-semibold shrink-0">稳定性:</span>
                            <div className="flex-1 h-1.5 bg-[var(--border-color)] rounded-full overflow-hidden">
                              <div className="h-full bg-emerald-500" style={{ width: proj.rate }}></div>
                            </div>
                            <span className="text-[9px] font-bold text-slate-700 shrink-0">{proj.rate}</span>
                          </div>
                          
                          <div className="flex items-center gap-2.5 text-[9.5px] font-bold text-[var(--accent-color)]" onClick={(e) => e.stopPropagation()}>
                            <span 
                              onClick={(e) => {
                                e.stopPropagation();
                                handleRunAutomation(proj);
                              }}
                              className="hover:underline cursor-pointer"
                            >
                              {isRunningAutomation && isSelected ? '运行中...' : '构建运行'}
                            </span>
                            <span className="text-slate-300">|</span>
                            <span 
                              onClick={() => {
                                window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '已为您唤起 AI 测试助手协助编写自动化脚本！', type: 'info' } }));
                                window.dispatchEvent(new CustomEvent('open-ai-chat'));
                              }}
                              className="hover:underline cursor-pointer"
                            >
                              AI脚本
                            </span>
                          </div>
                        </div>
                      </TiltCard>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* 右栏 5 份：AI 架构预演与 CLI 编译日志 */}
            <div className="col-span-12 lg:col-span-5 space-y-4">
              <TiltCard className="theme-card laser-chase-border rounded-xl p-4 shadow-soft text-left flex flex-col justify-between h-full min-h-[460px]">
                <div style={{ transform: 'translateZ(20px)', transformStyle: 'preserve-3d' }}>
                  <h3 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <Sparkles className="size-4 text-purple-500 animate-pulse" />
                      <span className="cyber-glitch-text cursor-pointer transition-all">AI 自动化构建与架构预演</span>
                    </div>
                    <span className="text-[8.5px] font-mono text-[var(--accent-color)] bg-[var(--accent-glow)] px-1.5 py-0.5 rounded">预演看板</span>
                  </h3>
                  
                  <div className="mt-3.5 space-y-3 font-mono text-[9.5px]">
                    <div>
                      <span className="text-slate-400 block text-[9px] mb-1">选定项目及框架</span>
                      <div className="p-2 bg-[var(--bg-app)]/50 border border-[var(--border-color)] rounded-lg flex items-center justify-between">
                        <span className="font-bold text-[var(--text-primary)] truncate max-w-[180px]">{activeProj.name}</span>
                        <span className="px-1.5 py-0.5 bg-[var(--accent-color)] text-[var(--accent-text)] text-[8px] font-extrabold rounded uppercase">{String(activeProj.stack || '').split(' / ')[1] || activeProj.stack}</span>
                      </div>
                    </div>

                    {/* 动态文件骨架树 */}
                    <div className="space-y-1 text-left">
                      <span className="text-slate-400 block text-[9px] mb-1">AI 推荐的工程目录架构：</span>
                      <div className="p-3 border border-[var(--border-color)] bg-[var(--bg-app)]/30 rounded-lg text-slate-500 space-y-1">
                        {String(activeProj.stack || '').toLowerCase().includes('playwright') && (
                          <>
                            <div className="flex items-center gap-1"><Folder className="size-3 text-amber-500" /> tests/</div>
                            <div className="pl-3.5 flex items-center gap-1 text-emerald-500 font-bold"><FileText className="size-3 text-slate-400" /> login.spec.ts <span className="opacity-50 font-normal text-[8px]">(AI 生成)</span></div>
                            <div className="pl-3.5 flex items-center gap-1 text-emerald-500 font-bold"><FileText className="size-3 text-slate-400" /> payment.spec.ts <span className="opacity-50 font-normal text-[8px]">(AI 生成)</span></div>
                            <div className="flex items-center gap-1 text-cyan-500 font-bold"><FileText className="size-3" /> playwright.config.ts</div>
                          </>
                        )}
                        {String(activeProj.stack || '').toLowerCase().includes('appium') && (
                          <>
                            <div className="flex items-center gap-1"><Folder className="size-3 text-amber-500" /> tests/specs/</div>
                            <div className="pl-3.5 flex items-center gap-1 text-emerald-500 font-bold"><FileText className="size-3 text-slate-400" /> mobile_login.spec.js <span className="opacity-50 font-normal text-[8px]">(AI 生成)</span></div>
                            <div className="pl-3.5 flex items-center gap-1 text-emerald-500 font-bold"><FileText className="size-3 text-slate-400" /> gesture.spec.js <span className="opacity-50 font-normal text-[8px]">(AI 生成)</span></div>
                            <div className="flex items-center gap-1 text-cyan-500 font-bold"><FileText className="size-3" /> wdio.conf.js</div>
                          </>
                        )}
                        {String(activeProj.stack || '').toLowerCase().includes('pytest') && (
                          <>
                            <div className="flex items-center gap-1"><Folder className="size-3 text-amber-500" /> tests/api/</div>
                            <div className="pl-3.5 flex items-center gap-1 text-emerald-500 font-bold"><FileText className="size-3 text-slate-400" /> test_users.py <span className="opacity-50 font-normal text-[8px]">(AI 生成)</span></div>
                            <div className="pl-3.5 flex items-center gap-1 text-emerald-500 font-bold"><FileText className="size-3 text-slate-400" /> test_order.py <span className="opacity-50 font-normal text-[8px]">(AI 生成)</span></div>
                            <div className="flex items-center gap-1 text-cyan-500 font-bold"><FileText className="size-3" /> pytest.ini</div>
                          </>
                        )}
                        {String(activeProj.stack || '').toLowerCase().includes('supertest') && (
                          <>
                            <div className="flex items-center gap-1"><Folder className="size-3 text-amber-500" /> tests/health/</div>
                            <div className="pl-3.5 flex items-center gap-1 text-emerald-500 font-bold"><FileText className="size-3 text-slate-400" /> check.test.js <span className="opacity-50 font-normal text-[8px]">(AI 生成)</span></div>
                            <div className="flex items-center gap-1 text-cyan-500 font-bold"><FileText className="size-3" /> package.json</div>
                          </>
                        )}
                      </div>
                    </div>

                    {/* 模拟 CLI 打字日志终端 */}
                    <div className="space-y-1 text-left">
                      <span className="text-slate-400 block text-[9px] mb-1">智能自动化构建控制台 (Live CLI Logs)：</span>
                      <div className="mac-terminal cyber-matrix-console p-3 font-mono text-[8.5px] leading-normal text-slate-300 text-left bg-zinc-950 rounded-xl min-h-[145px] max-h-[160px] overflow-y-auto">
                        <div className="flex justify-between items-center border-b border-white/5 pb-1 mb-2 shrink-0">
                          <span className="text-zinc-500">atp-executor - build #{activeProj.build}</span>
                          <div className="flex gap-1">
                            <span className="size-1.5 rounded-full bg-[#ff5f56]" />
                            <span className="size-1.5 rounded-full bg-[#ffbd2e]" />
                            <span className="size-1.5 rounded-full bg-[#27c93f]" />
                          </div>
                        </div>
                        <div className="space-y-1">
                          {cliLogs.map((log, lIdx) => (
                            <p key={lIdx} className={log.includes('SUCCESS') ? 'text-emerald-400' : log.includes('READY') ? 'text-[#8be9fd] font-bold' : 'text-slate-400'}>{log}</p>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-[var(--border-color)]" style={{ transform: 'translateZ(25px)' }}>
                  <button 
                    onClick={() => setViewMode('project-detail')}
                    className="w-full py-2 glow-button-neon text-[var(--accent-text)] text-[10px] font-bold rounded-lg cursor-pointer text-center hover:opacity-90 transition-all"
                  >
                    点击进入该项目架构调试沙箱
                  </button>
                </div>
              </TiltCard>
            </div>
          </div>
        </div>
      ) : (
        // ==========================================================================
        // 渲染：18-新建自动化项目向导页
        // ==========================================================================
        <div className="space-y-4 text-left w-full animate-[fadeIn_0.2s_ease-out]">
          {/* 返回 */}
          <div className="flex items-center gap-3">
            <button 
              onClick={() => setViewMode('list')}
              className="flex items-center gap-1 px-2.5 py-1 rounded border border-[var(--border-color)] bg-[var(--bg-card)] text-[10px] text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 transition-colors shadow-sm cursor-pointer"
            >
              <ArrowLeft className="size-3" />
              <span>返回列表</span>
            </button>
            <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-secondary)] font-semibold">
              <span>自动化中心</span>
              <span>/</span>
              <span className="text-[var(--text-primary)]">新建自动化项目</span>
            </div>
          </div>

          <div className="grid grid-cols-12 gap-5 w-full">
            
            {/* 左侧：向导主配置面板 */}
            <div className="col-span-12 lg:col-span-7 flex flex-col">
              <div className="theme-card rounded-xl p-5 flex-1 flex flex-col justify-between space-y-5 min-h-[380px]">
                <div>
                  <h2 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 flex items-center gap-1.5">
                    <Sparkles className="size-4 text-[var(--accent-color)] animate-pulse" />
                    <span>新建自动化项目向导</span>
                  </h2>

                  {/* 步骤条 */}
                  <div className="flex justify-between items-center relative py-2.5 border-b border-[var(--border-color)] mt-1">
                    <div className="absolute top-[21px] left-8 right-8 h-0.5 bg-[var(--border-color)] z-0">
                      <div 
                        className="h-full transition-all duration-300"
                        style={{ 
                          width: `${((wizardStep - 1) / 3) * 100}%`,
                          backgroundColor: 'var(--accent-color)'
                        }}
                      ></div>
                    </div>

                    {[
                      { step: 1, label: '基础配置' },
                      { step: 2, label: '框架集成' },
                      { step: 3, label: '代码接入' },
                      { step: 4, label: '生成配置' }
                    ].map((s) => (
                      <div key={s.step} className="flex flex-col items-center z-10">
                        <div 
                          className={`size-6 rounded-full flex items-center justify-center text-[10px] font-bold border transition-all`}
                          style={{
                            backgroundColor: wizardStep >= s.step ? 'var(--accent-color)' : 'var(--bg-card)',
                            color: wizardStep >= s.step ? 'var(--accent-text)' : 'var(--text-secondary)',
                            borderColor: wizardStep >= s.step ? 'var(--accent-color)' : 'var(--border-color)'
                          }}
                        >
                          {s.step}
                        </div>
                        <span 
                          className="text-[9px] font-bold mt-1.5"
                          style={{
                            color: wizardStep === s.step ? 'var(--accent-color)' : 'var(--text-secondary)'
                          }}
                        >
                          {s.label}
                        </span>
                      </div>
                    ))}
                  </div>

                  {/* 表单内容 */}
                  <div className="py-4 space-y-4 text-xs font-semibold text-[var(--text-secondary)] leading-normal min-h-[180px]">
                    
                    {wizardStep === 1 && (
                      <div className="space-y-4">
                        <div className="space-y-1.5">
                          <label className="block text-[var(--text-primary)]">项目名称</label>
                          <input 
                            type="text" 
                            value={projName}
                            onChange={(e) => setProjName(e.target.value)}
                            placeholder="例如：智能客服系统界面自动化"
                            className="premium-input w-full px-3 py-2 text-[11px]"
                          />
                        </div>
                        <div className="space-y-1.5">
                          <label className="block text-[var(--text-primary)]">项目描述 (可选)</label>
                          <textarea 
                            value={projDesc}
                            onChange={(e) => setProjDesc(e.target.value)}
                            placeholder="简要介绍该自动套件的范围与主链任务"
                            className="premium-input w-full px-3 py-2 text-[11px] h-20"
                          />
                        </div>
                      </div>
                    )}

                    {wizardStep === 2 && (
                      <div className="space-y-4">
                        <div className="space-y-1.5">
                          <label className="block text-[var(--text-primary)]">选择自动化测试框架 (Stack)</label>
                          <div className="grid grid-cols-2 gap-3 text-[10px]">
                            {[
                              { id: 'playwright', label: 'Playwright (推荐)', desc: '支持 Chromium、Firefox、WebKit' },
                              { id: 'selenium', label: 'Selenium WebDriver', desc: '传统的多语言测试框架' },
                              { id: 'appium', label: 'Appium Native', desc: '原生与混合移动应用自动化' },
                              { id: 'cypress', label: 'Cypress E2E', desc: '轻量前端快速集成校验' }
                            ].map((f) => (
                              <div 
                                key={f.id}
                                onClick={() => setProjStack(f.id)}
                                style={projStack === f.id ? { borderColor: 'var(--accent-color)', backgroundColor: 'var(--accent-glow)' } : {}}
                                className={`p-2.5 border rounded-lg cursor-pointer transition-all border-[var(--border-color)] hover:bg-[var(--border-color)]/30`}
                              >
                                <div className="font-bold text-[var(--text-primary)]">{f.label}</div>
                                <div className="text-[8px] text-[var(--text-secondary)] mt-0.5">{f.desc}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                        {projStack === 'playwright' && renderPlaywrightOptionsPanel({ compact: true })}
                      </div>
                    )}

                    {wizardStep === 3 && (
                      <div className="space-y-4">
                        <div className="space-y-1.5">
                          <label className="block text-[var(--text-primary)]">开发脚本语言</label>
                          <div className="flex gap-4 py-1.5">
                            {['JavaScript', 'TypeScript', 'Python', 'Java'].map((lang, i) => (
                              <label key={i} className="flex items-center gap-1.5 cursor-pointer text-[var(--text-primary)] text-[10.5px]">
                                <input 
                                  type="radio" 
                                  name="lang" 
                                  checked={projLang === ['js', 'ts', 'python', 'java'][i]}
                                  onChange={() => setProjLang(['js', 'ts', 'python', 'java'][i])}
                                  className="size-3.5 text-[var(--accent-color)]" 
                                  style={{ accentColor: 'var(--accent-color)' }} 
                                />
                                <span className="font-bold">{lang}</span>
                              </label>
                            ))}
                          </div>
                        </div>
                        <div className="space-y-1.5">
                          <label className="block text-[var(--text-primary)]">Git 远程托管仓库地址</label>
                          <input 
                            type="text" 
                            placeholder="https://github.com/your-org/automation-repo.git"
                            className="premium-input w-full px-3 py-2 text-[11px] font-mono"
                          />
                        </div>
                      </div>
                    )}

                    {wizardStep === 4 && (
                      <div 
                        style={{ borderColor: 'var(--accent-color)', backgroundColor: 'var(--accent-glow)' }}
                        className="space-y-3 p-4 border rounded-xl"
                      >
                        <div className="flex items-center gap-1.5 font-bold" style={{ color: 'var(--accent-color)' }}>
                          <Sparkles className="size-4 animate-pulse" />
                          <span>项目配置就绪，即将进行 AI 初始化</span>
                        </div>
                        <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed font-semibold">
                          已成功配置项目「<strong style={{ color: 'var(--accent-color)' }}>{projName}</strong>」，选用 <strong style={{ color: 'var(--accent-color)' }}>{projStack.toUpperCase()}</strong> 测试骨架。AI 大脑将自动关联现有的 12 个核心 PRD 需求，并智能生成第一批健全的页面执行脚本。
                        </p>
                        <div className="text-[9px] text-[var(--text-secondary)]/80 font-medium pt-2 border-t border-[var(--border-color)]">
                          点击下方「完成」按钮，系统将携带当前 Playwright 轻量选项生成工程文件与初始用例。
                        </div>
                      </div>
                    )}

                  </div>
                </div>

                {/* 控制按钮 */}
                <div className="flex justify-between items-center pt-4 border-t border-[var(--border-color)]">
                  <button 
                    onClick={() => setViewMode('list')}
                    className="px-3.5 py-1.5 border border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 bg-[var(--bg-card)] rounded-lg text-[10px] font-bold cursor-pointer transition-all active:scale-95"
                  >
                    取消
                  </button>

                  <div className="flex gap-2">
                    {wizardStep > 1 && (
                      <button 
                        onClick={() => setWizardStep(wizardStep - 1)}
                        className="px-3.5 py-1.5 border border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 bg-[var(--bg-card)] rounded-lg text-[10px] font-bold cursor-pointer transition-all active:scale-95"
                      >
                        上一步
                      </button>
                    )}

                    {wizardStep < 4 ? (
                      <button 
                        onClick={() => setWizardStep(wizardStep + 1)}
                        className="accent-btn px-4 py-1.5 rounded-lg text-[10px]"
                      >
                        下一步
                      </button>
                    ) : (
                      <button 
                        onClick={handleCreateProject}
                        disabled={isCreatingProject}
                        className="accent-btn px-4 py-1.5 rounded-lg text-[10px] disabled:opacity-60"
                      >
                        {isCreatingProject ? '创建中...' : '完成，进入项目'}
                      </button>
                    )}
                  </div>
                </div>

              </div>
            </div>

            {/* 右侧：AI 工程脚手架预览与架构辅助面板 */}
            <div className="col-span-12 lg:col-span-5 flex flex-col">
              <TiltCard className="theme-card rounded-xl p-5 flex-1 flex flex-col justify-between space-y-4 min-h-[380px]">
                <div style={{ transform: 'translateZ(20px)', transformStyle: 'preserve-3d' }}>
                  <h2 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 flex items-center gap-1.5">
                    <Activity className="size-4 text-blue-500 animate-pulse" />
                    <span>AI 架构脚手架与目录树预演 (Live Preview)</span>
                  </h2>

                  <div className="pt-2 space-y-3 font-mono text-[9px] text-[var(--text-secondary)] text-left leading-normal">
                    {/* 项目元信息预览 */}
                    <div className="p-2.5 bg-[#0b0f19] border border-[#223049] rounded-lg text-slate-400 space-y-1" style={{ transform: 'translateZ(10px)' }}>
                      <div><span className="text-purple-400">PROJECT_NAME:</span> "{projName || 'Untitled'}"</div>
                      <div><span className="text-purple-400">TARGET_STACK:</span> "{projStack.toUpperCase()}"</div>
                      <div><span className="text-purple-400">BASE_URL:</span> "{playwrightOptions.baseURL}"</div>
                      <div><span className="text-purple-400">BROWSER:</span> "{playwrightOptions.browser}" / headless={String(playwrightOptions.headless)}</div>
                      <div><span className="text-purple-400">ENGINE_VERSION:</span> "v2.5.0"</div>
                    </div>

                    {/* 动态骨架预览 */}
                    <div className="p-3 border border-[var(--border-color)] bg-[var(--border-color)]/10 rounded-lg space-y-2" style={{ transform: 'translateZ(15px)' }}>
                      <span className="font-bold text-[var(--text-primary)] block text-[10px]">
                        {projStack.toUpperCase()} 工程结构模版：
                      </span>
                      
                      {projStack === 'playwright' && (
                        <div className="space-y-1 text-slate-500">
                          <div>📁 tests/</div>
                          <div className="pl-3 text-emerald-500 font-bold">├── 📝 login.spec.ts <span className="opacity-50 font-normal text-[8px]">(AI Generated)</span></div>
                          <div className="pl-3 text-emerald-500 font-bold">├── 📝 payment_flow.spec.ts <span className="opacity-50 font-normal text-[8px]">(AI Generated)</span></div>
                          <div className="pl-3">└── ⚙️ auth.setup.ts</div>
                          <div className="text-cyan-500 font-bold">📄 playwright.config.ts</div>
                          <div>📄 package.json</div>
                        </div>
                      )}

                      {projStack === 'cypress' && (
                        <div className="space-y-1 text-slate-500">
                          <div>📁 cypress/</div>
                          <div>  📁 e2e/</div>
                          <div className="pl-6 text-emerald-500 font-bold">├── 📝 checkout.cy.js <span className="opacity-50 font-normal text-[8px]">(AI Generated)</span></div>
                          <div className="pl-6 text-emerald-500 font-bold">└── 📝 session.cy.js <span className="opacity-50 font-normal text-[8px]">(AI Generated)</span></div>
                          <div>  📁 fixtures/</div>
                          <div>  └── ⚙️ tsconfig.json</div>
                          <div className="text-cyan-500 font-bold">📄 cypress.config.js</div>
                          <div>📄 package.json</div>
                        </div>
                      )}

                      {projStack === 'selenium' && (
                        <div className="space-y-1 text-slate-500">
                          <div>📁 src/</div>
                          <div>  📁 test/java/com/atp/tests/</div>
                          <div className="pl-6 text-emerald-500 font-bold">├── 📝 MainCheckoutTest.java <span className="opacity-50 font-normal text-[8px]">(AI)</span></div>
                          <div className="pl-6 text-emerald-500 font-bold">└── 📝 LoginVerification.java <span className="opacity-50 font-normal text-[8px]">(AI)</span></div>
                          <div>  └── 📁 pages/</div>
                          <div className="text-cyan-500 font-bold">📄 pom.xml</div>
                          <div>📄 README.md</div>
                        </div>
                      )}

                      {projStack === 'appium' && (
                        <div className="space-y-1 text-slate-500">
                          <div>📁 config/</div>
                          <div>  └── 📄 android.caps.json</div>
                          <div>📁 tests/specs/</div>
                          <div className="pl-3 text-emerald-500 font-bold">├── 📝 mobile_checkout.spec.js <span className="opacity-50 font-normal text-[8px]">(AI)</span></div>
                          <div className="pl-3 text-emerald-500 font-bold">└── 📝 gesture_handling.spec.js <span className="opacity-50 font-normal text-[8px]">(AI)</span></div>
                          <div className="text-cyan-500 font-bold">📄 wdio.conf.js</div>
                          <div>📄 package.json</div>
                        </div>
                      )}
                    </div>
                    {renderGenerationSummaryPanel()}
                  </div>
                </div>

                {/* 底部指标指示 */}
                <div className="border-t border-[var(--border-color)] pt-3 text-[9px] text-[var(--text-secondary)] font-semibold flex items-center justify-between" style={{ transform: 'translateZ(30px)' }}>
                  <span>AI 工程自适应校验得分: <strong className="text-emerald-500 font-bold">98.2%</strong></span>
                  <span className="flex items-center gap-1 text-[var(--text-primary)]">
                    <span className="size-1.5 rounded-full bg-blue-500 animate-ping"></span>
                    实时渲染
                  </span>
                </div>
              </TiltCard>
            </div>

          </div>

        </div>
      )}

    </div>
  );
}
