import React, { useState } from 'react';
import { 
  Network, 
  Search, 
  ChevronDown, 
  ArrowLeft, 
  Send, 
  Save, 
  Sparkles,
  CheckCircle,
  XCircle,
  Database,
  Plus,
  Play,
  RotateCw,
  Cpu,
  Terminal,
  Clipboard,
  FileInput
} from 'lucide-react';
import TiltCard from '../components/TiltCard';
import AnimatedNumber from '../components/AnimatedNumber';
import { apiGet, apiPost, formatDateTime, inferFileFormat, pickList, readFileAsBase64 } from '../lib/api';
import { useProjectContext } from '../lib/projectContext';

const numberText = (value, fallback = '0') => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toLocaleString('zh-CN') : fallback;
};

const toPercentLabel = (passed, total, fallback = '0%') => {
  const p = Number(passed);
  const t = Number(total);
  if (!Number.isFinite(p) || !Number.isFinite(t) || t <= 0) return fallback;
  return `${Math.max(0, Math.min(100, (p / t) * 100)).toFixed(1)}%`;
};

const IMPORT_SOURCES = [
  {
    id: 'openapi_json',
    label: 'OpenAPI JSON',
    sourceType: 'openapi',
    format: 'json',
    mode: 'text',
    sample: '{\n  "openapi": "3.0.0",\n  "info": { "title": "Demo API", "version": "1.0.0" },\n  "paths": {\n    "/api/v1/ping": {\n      "get": {\n        "summary": "Ping",\n        "responses": { "200": { "description": "ok" } }\n      }\n    }\n  }\n}'
  },
  {
    id: 'openapi_yaml',
    label: 'OpenAPI YAML',
    sourceType: 'openapi',
    format: 'yaml',
    mode: 'text',
    sample: 'openapi: 3.0.0\ninfo:\n  title: Demo API\n  version: 1.0.0\npaths:\n  /api/v1/ping:\n    get:\n      summary: Ping\n      responses:\n        "200":\n          description: ok'
  },
  {
    id: 'har',
    label: 'HAR',
    sourceType: 'har',
    format: 'json',
    mode: 'text',
    sample: '{\n  "log": {\n    "version": "1.2",\n    "entries": []\n  }\n}'
  },
  {
    id: 'docx',
    label: 'DOCX',
    sourceType: 'docx',
    format: 'docx',
    mode: 'file',
    accept: '.docx',
    sample: ''
  },
  {
    id: 'pdf',
    label: 'PDF',
    sourceType: 'pdf',
    format: 'pdf',
    mode: 'file',
    accept: '.pdf',
    sample: ''
  },
  {
    id: 'xlsx',
    label: 'XLSX',
    sourceType: 'xlsx',
    format: 'xlsx',
    mode: 'file',
    accept: '.xlsx',
    sample: ''
  },
  {
    id: 'xmind',
    label: 'XMind',
    sourceType: 'xmind',
    format: 'xmind',
    mode: 'file',
    accept: '.xmind',
    sample: ''
  }
];

const FILE_IMPORT_ACCEPT = '.docx,.pdf,.xlsx,.xmind';
const FILE_IMPORT_SOURCE_IDS = new Set(['docx', 'pdf', 'xlsx', 'xmind']);
const MAX_IMPORT_FILE_SIZE = 50 * 1024 * 1024;

const HTTP_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'];
const EMPTY_ROW = { key: '', value: '', enabled: true };
const DATA_FACTORY_SCENARIOS = [
  { id: 'normal', label: '正常', keys: ['normal', 'valid', 'happy_path', 'success'] },
  { id: 'boundary', label: '边界', keys: ['boundary', 'edge', 'edge_case', 'limit'] },
  { id: 'invalid', label: '异常', keys: ['invalid', 'exception', 'error', 'negative'] },
  { id: 'empty', label: '空值', keys: ['empty', 'null', 'null_value', 'blank', 'missing'] },
  { id: 'special', label: '特殊字符', keys: ['special', 'special_char', 'special_chars', 'unicode'] }
];
const FACTORY_RESULT_KEYS = ['items', 'samples', 'records', 'results', 'test_data', 'cases', 'parameters', 'data', 'suggestions', 'generated'];

const firstDefined = (...values) => values.find((value) => value !== undefined && value !== null && value !== '');

const isRecord = (value) => value && typeof value === 'object' && !Array.isArray(value);

const toRecord = (value) => {
  if (isRecord(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed = JSON.parse(value);
      return isRecord(parsed) ? parsed : {};
    } catch {
      return {};
    }
  }
  return {};
};

const toList = (payload) => {
  if (Array.isArray(payload)) return payload;
  if (payload && typeof payload === 'object') return pickList(payload);
  return [];
};

const safeStringify = (value) => {
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value ?? null, null, 2);
  } catch {
    return String(value);
  }
};

const formatFileSize = (size) => {
  const numeric = Number(size);
  if (!Number.isFinite(numeric) || numeric <= 0) return '--';
  if (numeric >= 1024 * 1024) return `${(numeric / (1024 * 1024)).toFixed(1)} MB`;
  if (numeric >= 1024) return `${Math.round(numeric / 1024)} KB`;
  return `${numeric} B`;
};

const normalizeFactorySource = (payload) => {
  if (Array.isArray(payload)) return { items: payload };
  const source = toRecord(payload);
  const nested = FACTORY_RESULT_KEYS.map((key) => source[key]).find((value) => value !== undefined && value !== null);
  if (Array.isArray(nested)) return { items: nested };
  if (isRecord(nested)) return nested;
  return source;
};

const normalizeFactoryItemsForScenario = (payload, scenario) => {
  const source = normalizeFactorySource(payload);
  const directValue = scenario.keys.map((key) => source[key]).find((value) => value !== undefined && value !== null);
  let items = [];

  if (Array.isArray(directValue)) {
    items = directValue;
  } else if (directValue !== undefined && directValue !== null) {
    items = [directValue];
  } else {
    const candidates = [
      ...FACTORY_RESULT_KEYS.flatMap((key) => toList(source[key])),
      ...toList(source.scenarios)
    ];
    items = candidates.filter((item) => {
      const record = toRecord(item);
      const kind = String(firstDefined(record.category, record.type, record.kind, record.scenario, record.group, '')).toLowerCase();
      return scenario.keys.includes(kind);
    });
  }

  return items.map((item, index) => {
    const record = toRecord(item);
    return {
      id: `${scenario.id}-${index}`,
      title: firstDefined(record.name, record.title, record.label, record.description, `${scenario.label} #${index + 1}`),
      value: isRecord(item) ? item : { value: item }
    };
  });
};

const getTargetPayload = (record, target) => {
  const keyMap = {
    body: ['body', 'request_body', 'requestBody', 'body_data', 'bodyData', 'payload_body'],
    variables: ['variables', 'vars', 'env_vars', 'envVars', 'runtime_variables', 'runtimeVariables'],
    query: ['query', 'params', 'parameters', 'request_query', 'requestQuery', 'query_params', 'queryParams']
  };
  const directKeys = keyMap[target] || [target];
  const containerKeys = ['request', 'request_payload', 'requestPayload', 'payload', 'mapping', 'mappings', 'mapped', 'targets'];

  for (const key of directKeys) {
    if (record[key] !== undefined && record[key] !== null) return record[key];
  }

  for (const containerKey of containerKeys) {
    const container = toRecord(record[containerKey]);
    for (const key of directKeys) {
      if (container[key] !== undefined && container[key] !== null) return container[key];
    }
  }

  return undefined;
};

const getFactoryApplyValue = (item, target) => {
  const record = toRecord(item?.value);
  const mappedValue = getTargetPayload(record, target);
  if (mappedValue !== undefined) {
    return target === 'body' ? mappedValue : toRecord(mappedValue);
  }

  if (target === 'body') {
    return firstDefined(record.body, record.request_body, record.requestBody, record.payload, record.data, record.value, item?.value);
  }
  return toRecord(firstDefined(
    record.variables,
    record.vars,
    record.params,
    record.query,
    record.headers,
    record.body,
    record.payload,
    record.data,
    item?.value
  ));
};

const objectToRows = (value, fallback = [EMPTY_ROW]) => {
  const entries = Object.entries(toRecord(value));
  if (!entries.length) return fallback.map((row) => ({ ...row }));
  return entries.map(([key, itemValue]) => ({
    key,
    value: typeof itemValue === 'string' ? itemValue : safeStringify(itemValue),
    enabled: true
  }));
};

const rowsToObject = (rows) => {
  return (Array.isArray(rows) ? rows : []).reduce((record, row) => {
    const key = String(row?.key || '').trim();
    if (!key || row?.enabled === false) return record;
    record[key] = row?.value ?? '';
    return record;
  }, {});
};

const parseBodyInput = (text) => {
  const trimmed = String(text ?? '').trim();
  if (!trimmed) return undefined;
  try {
    return JSON.parse(trimmed);
  } catch {
    return trimmed;
  }
};

const parseJsonSource = (text) => {
  const trimmed = String(text ?? '').trim();
  if (!trimmed) return { ok: false, value: null, message: '请输入导入内容。' };
  try {
    return { ok: true, value: JSON.parse(trimmed), message: '' };
  } catch (error) {
    return { ok: false, value: null, message: error?.message || 'JSON 解析失败。' };
  }
};

const joinUrl = (baseUrl, path) => {
  const rawPath = String(path || '').trim();
  if (/^https?:\/\//i.test(rawPath)) return rawPath;
  const base = String(baseUrl || '').replace(/\/+$/, '');
  const nextPath = rawPath ? `/${rawPath.replace(/^\/+/, '')}` : '';
  return `${base}${nextPath}`;
};

const readErrorMessage = (error, fallback = '请求失败') => {
  const payload = error?.payload;
  if (isRecord(payload)) return payload.message || payload.detail || error?.message || fallback;
  return error?.message || fallback;
};

const pickSavedCase = (result) => {
  const payload = toRecord(result);
  const nestedResult = toRecord(payload.result);
  return (
    payload.saved_case ||
    payload.savedCase ||
    payload.test_case ||
    payload.testCase ||
    payload.case ||
    nestedResult.saved_case ||
    nestedResult.test_case ||
    null
  );
};

const normalizeDebugResult = (result) => {
  const payload = toRecord(result);
  const response = toRecord(payload.response);
  return {
    raw: result,
    statusCode: payload.status_code ?? payload.status ?? response.status_code ?? response.status ?? '--',
    durationMs: payload.duration_ms ?? payload.elapsed_ms ?? payload.latency_ms ?? response.duration_ms ?? 0,
    headers: toRecord(payload.headers || payload.response_headers || response.headers),
    scriptResults: payload.script_results || payload.scriptResults || response.script_results || null,
    savedCase: pickSavedCase(result)
  };
};

const mapBackendLib = (lib, apis = [], cases = []) => {
  const activeCount = apis.length;
  const readyCases = cases.filter((item) => item.status !== 'disabled').length;
  const rate = readyCases ? '100.0%' : activeCount ? '0.0%' : '—';
  return {
    backendId: lib.id,
    raw: lib,
    rawApis: apis,
    rawCases: cases,
    name: lib.name || `接口库 #${lib.id}`,
    desc: lib.description || lib.import_source || '后端接口测试库',
    type: 'HTTP / JSON',
    count: activeCount,
    cases: cases.length,
    rate,
    time: formatDateTime(lib.latest_sync_at || lib.updated_at || lib.created_at),
    owner: lib.owner_name || '后端',
    health: rate === '—' ? '待导入' : rate,
    activeCount,
    riskCount: Math.max(cases.length - readyCases, 0)
  };
};

export default function ApiTesting() {
  const { selectedProject, loading: projectLoading, error: projectError } = useProjectContext();
  const [viewMode, setViewMode] = useState('list'); // 'list' or 'workbench' or 'env-scenario'
  const [selectedLibIdx, setSelectedLibIdx] = useState(0); // 列表页选中联动索引
  const [isSending, setIsSending] = useState(false);
  const [requestTab, setRequestTab] = useState('body'); // headers, params, body, auth
  const [responseTab, setResponseTab] = useState('body'); // body, headers, console
  const [selectedStepIdx, setSelectedStepIdx] = useState(0); // 链路编排页选中步骤
  const [projectContext, setProjectContext] = useState(null);
  const [remoteLibs, setRemoteLibs] = useState([]);
  const [apiStatus, setApiStatus] = useState({ loading: true, message: '正在同步后端接口库...', usingBackend: false });
  const [isSyncingSwagger, setIsSyncingSwagger] = useState(false);
  const [isRunningAssertions, setIsRunningAssertions] = useState(false);
  const [remoteEnvConfigs, setRemoteEnvConfigs] = useState([]);
  const [remoteScenarioSteps, setRemoteScenarioSteps] = useState([]);
  const [remoteSchedules, setRemoteSchedules] = useState([]);
  const [scenarioRunResult, setScenarioRunResult] = useState(null);
  const [isRunningScenarioChain, setIsRunningScenarioChain] = useState(false);

  // 15-页指标
  const apiStats = [
    { label: '接口库总数', val: '12', change: '↑ 1', icon: Database },
    { label: '接口总数', val: '432', change: '↑ 18', icon: Network },
    { label: '测试用例数', val: '1,854', change: '↑ 56', icon: CheckCircle },
    { label: '执行通过率', val: '94.2%', change: '↑ 0.8%', hasChart: true }
  ];

  const apiLibs = [
    { name: 'AI服务与底层接口定义', desc: '大模型代理微服务、用例执行引擎接口', type: 'HTTP / JSON', count: 18, cases: 156, rate: '96.2%', time: '今天 10:25', owner: '张明', health: '96.2%', activeCount: 16, riskCount: 0 },
    { name: '电商平台核心交易接口', desc: '商品、购物车、下单与结算服务接口', type: 'gRPC / Protobuf', count: 42, cases: 512, rate: '93.5%', time: '昨天 16:48', owner: '李华', health: '93.5%', activeCount: 38, riskCount: 1 },
    { name: '支付网关与清算服务', desc: '渠道对接、退款、三方清算接口', type: 'HTTP / XML', count: 15, cases: 243, rate: '90.1%', time: '昨天 14:12', owner: '王芳', health: '90.1%', activeCount: 12, riskCount: 2 },
    { name: '用户中心与统一鉴权', desc: 'SSO 登录、Token 校验与权限拉取接口', type: 'HTTP / JSON', count: 24, cases: 312, rate: '98.5%', time: '05-18 11:33', owner: '赵强', health: '98.5%', activeCount: 24, riskCount: 0 },
    { name: '促销与优惠券发布系统', desc: '秒杀活动、满减发放与核销业务接口', type: 'HTTP / JSON', count: 30, cases: 298, rate: '89.4%', time: '05-18 09:05', owner: '陈磊', health: '89.4%', activeCount: 25, riskCount: 3 }
  ];

  const [responseBody, setResponseBody] = useState('');
  const [importSourceId, setImportSourceId] = useState('openapi_json');
  const [importText, setImportText] = useState(IMPORT_SOURCES[0].sample);
  const [importGenerateCases, setImportGenerateCases] = useState(true);
  const [importCreateCases, setImportCreateCases] = useState(true);
  const [importFile, setImportFile] = useState(null);
  const [isImporting, setIsImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [importError, setImportError] = useState('');
  const importFileInputRef = React.useRef(null);
  const [debugForm, setDebugForm] = useState({
    method: 'GET',
    url: '',
    baseUrl: 'http://127.0.0.1:8000',
    path: '/api/v2/projects',
    expectedStatus: '200',
    body: '{\n  "page": 1,\n  "pageSize": 1\n}'
  });
  const [debugHeaders, setDebugHeaders] = useState([{ key: 'Content-Type', value: 'application/json', enabled: true }]);
  const [debugQuery, setDebugQuery] = useState([{ key: 'page', value: '1', enabled: true }, { key: 'pageSize', value: '1', enabled: true }]);
  const [selectedEnvironmentId, setSelectedEnvironmentId] = useState('');
  const [envVarRows, setEnvVarRows] = useState([{ key: 'base_url', value: 'http://127.0.0.1:8000', enabled: true }]);
  const [runVarRows, setRunVarRows] = useState([{ key: 'trace_id', value: 'manual-r25', enabled: true }]);
  const [saveAsCase, setSaveAsCase] = useState(false);
  const [savedCaseResult, setSavedCaseResult] = useState(null);
  const [debugResult, setDebugResult] = useState(null);
  const [enableScripts, setEnableScripts] = useState(false);
  const [preScript, setPreScript] = useState('setHeader("X-R25-Trace", variables.trace_id)');
  const [postScript, setPostScript] = useState('assertStatus(expected_status)');
  const [scenarioMappingRows, setScenarioMappingRows] = useState([
    { key: 'token', value: '$.data.token', enabled: true },
    { key: 'request_id', value: '$.headers.x-request-id', enabled: false }
  ]);
  const [remoteMocks, setRemoteMocks] = useState([]);
  const [mockForm, setMockForm] = useState({
    method: 'GET',
    path: '/api/v1/mock-smoke',
    statusCode: '200',
    responseBody: '{\n  "ok": true,\n  "source": "mock"\n}'
  });
  const [mockStatus, setMockStatus] = useState({ type: 'info', message: 'Mock 规则尚未加载。' });
  const [isSavingMock, setIsSavingMock] = useState(false);
  const [isDispatchingMock, setIsDispatchingMock] = useState(false);
  const [dataFactoryState, setDataFactoryState] = useState({ loading: false, result: null, error: '' });

  React.useEffect(() => {
    const handleApiResponseSuccess = (e) => {
      if (e.detail?.response) {
        setResponseBody(e.detail.response);
      }
    };
    window.addEventListener('api-response-success', handleApiResponseSuccess);
    return () => {
      window.removeEventListener('api-response-success', handleApiResponseSuccess);
    };
  }, []);

  const envConfigs = [
    { id: '1', key: 'GatewayHost', value: 'https://gateway-test.domain.com', desc: '测试环境主网关域名' },
    { id: '2', key: 'AuthHeader', value: 'Bearer {{global_token}}', desc: '全局身份验证头' },
    { id: '3', key: 'AppId', value: 'ai_qa_platform_v2', desc: '系统标识' },
    { id: '4', key: 'RateLimit', value: '100/sec', desc: '请求速率限制' }
  ];

  const scenarioSteps = [
    { id: 'Step 1', name: '智能客服用户授权登录', method: 'POST', url: '/api/v1/auth/login', desc: '获取会话鉴权Token', extracts: 'Token = response.body.data.token', delay: '45ms' },
    { id: 'Step 2', name: '创建新会话窗口', method: 'POST', url: '/api/v1/session/create', desc: '传入Token创建独立会话', extracts: 'SessionId = response.body.data.session_id', delay: '120ms' },
    { id: 'Step 3', name: '发送合规文本消息', method: 'POST', url: '/api/v1/message/send', desc: '依赖SessionId发送对话', extracts: 'MessageId = response.body.data.msg_id', delay: '380ms' },
    { id: 'Step 4', name: '拉取消息历史校验', method: 'GET', url: '/api/v1/message/history', desc: '校验消息是否存在并合法', extracts: '—', delay: '65ms' }
  ];

  const showToast = (message, type = 'success') => {
    window.dispatchEvent(new CustomEvent('show-toast', { detail: { message, type } }));
  };

  const fetchApiLibDetail = React.useCallback(async (lib) => {
    const apisPayload = await apiGet(`/api-test-libs/${lib.id}/apis`, { params: { page: 1, pageSize: 20 } }).catch(() => null);
    const apis = pickList(apisPayload);
    const caseLists = await Promise.all(
      apis.slice(0, 10).map((api) => apiGet(`/apis/${api.id}/test-cases`, { params: { page: 1, pageSize: 20 } }).catch(() => null))
    );
    const cases = caseLists.flatMap((payload) => pickList(payload));
    return mapBackendLib(lib, apis, cases);
  }, []);

  const loadApiRuntimeData = React.useCallback(async (lib) => {
    if (!lib?.backendId) {
      setRemoteEnvConfigs([]);
      setRemoteScenarioSteps([]);
      setRemoteSchedules([]);
      setRemoteMocks([]);
      return;
    }

    const [envPayload, scenarioPayload, schedulePayload, mockPayload] = await Promise.all([
      apiGet(`/api-test-libs/${lib.backendId}/environments`, { params: { page: 1, pageSize: 20 } }).catch(() => null),
      apiGet(`/api-test-libs/${lib.backendId}/scenarios`, { params: { page: 1, pageSize: 20 } }).catch(() => null),
      apiGet(`/api-test-libs/${lib.backendId}/schedules`, { params: { page: 1, pageSize: 20 } }).catch(() => null),
      apiGet(`/api-test-libs/${lib.backendId}/mocks`, { params: { page: 1, pageSize: 20 } }).catch((error) => ({ __error: error }))
    ]);
    const envs = pickList(envPayload);
    const scenarios = pickList(scenarioPayload);
    const schedules = pickList(schedulePayload);
    const mocks = mockPayload?.__error ? [] : pickList(mockPayload);
    const endpointById = new Map((lib.rawApis || []).map((api) => [String(api.id), api]));
    const caseById = new Map((lib.rawCases || []).map((item) => [String(item.id), item]));
    const primaryScenario = scenarios[0];
    const steps = toList(primaryScenario?.nodes).map((node, index) => {
      const testCase = caseById.get(String(node.case_id));
      const endpoint = endpointById.get(String(testCase?.endpoint_id));
      const extract = toRecord(node.extract);
      return {
        id: node.id || `Step ${index + 1}`,
        name: testCase?.name || node.name || `Backend case #${node.case_id || index + 1}`,
        method: endpoint?.method || 'CASE',
        url: endpoint?.path || `case:${node.case_id || index + 1}`,
        desc: primaryScenario?.description || 'Backend scenario node',
        extracts: Object.keys(extract).join(', ') || 'backend runner',
        delay: `${testCase?.expected_status || 200}`
      };
    });

    setRemoteEnvConfigs(envs);
    setRemoteScenarioSteps(steps);
    setRemoteSchedules(schedules);
    setRemoteMocks(mocks);
    setMockStatus(mockPayload?.__error
      ? { type: 'error', message: readErrorMessage(mockPayload.__error, 'Mock 规则加载失败。') }
      : { type: mocks.length ? 'success' : 'info', message: mocks.length ? `已加载 ${mocks.length} 条 Mock 规则。` : '暂无 Mock 规则。' });
  }, []);

  const loadApiTestingData = React.useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setApiStatus({ loading: true, message: '正在同步后端接口库...', usingBackend: false });
    }
    try {
      if (projectLoading) return;
      const project = selectedProject;

      if (!project?.id) {
        setProjectContext(null);
        setRemoteLibs([]);
        setApiStatus({ loading: false, message: projectError || '后端暂无项目，显示演示接口库', usingBackend: false });
        return;
      }

      const libsPayload = await apiGet(`/projects/${project.id}/api-test-libs`, { params: { page: 1, pageSize: 10 } }).catch(() => null);
      const libs = pickList(libsPayload);
      const detailedLibs = await Promise.all(libs.map((lib) => fetchApiLibDetail(lib)));
      setProjectContext(project);
      setRemoteLibs(detailedLibs);
      setSelectedLibIdx(0);
      setApiStatus({
        loading: false,
        message: detailedLibs.length ? `已连接 ${project.name || project.code}，接口库已同步` : `已连接 ${project.name || project.code}，暂无接口库`,
        usingBackend: detailedLibs.length > 0
      });
    } catch (error) {
      setProjectContext(null);
      setRemoteLibs([]);
      setApiStatus({ loading: false, message: error?.message || '后端暂不可用，显示演示接口库', usingBackend: false });
    }
  }, [fetchApiLibDetail, projectLoading, projectError, selectedProject]);

  React.useEffect(() => {
    loadApiTestingData();
  }, [loadApiTestingData]);

  const activeBackendLib = remoteLibs[selectedLibIdx] || remoteLibs[0];

  React.useEffect(() => {
    loadApiRuntimeData(activeBackendLib);
  }, [loadApiRuntimeData, activeBackendLib?.backendId]);

  React.useEffect(() => {
    const activeApi = activeBackendLib?.rawApis?.[0];
    if (!activeApi) return;
    setDebugForm((prev) => ({
      ...prev,
      method: String(activeApi.method || prev.method || 'GET').toUpperCase(),
      path: activeApi.path || prev.path,
      url: ''
    }));
  }, [activeBackendLib?.backendId]);

  React.useEffect(() => {
    const activeEnv = remoteEnvConfigs.find((item) => item?.is_active || item?.isActive) || remoteEnvConfigs[0];
    if (!activeEnv?.id) return;
    setSelectedEnvironmentId((prev) => (
      prev && remoteEnvConfigs.some((item) => String(item.id) === String(prev)) ? prev : String(activeEnv.id)
    ));
    setDebugForm((prev) => ({
      ...prev,
      baseUrl: activeEnv.base_url || prev.baseUrl
    }));
    setEnvVarRows(objectToRows({
      ...toRecord(activeEnv.variables),
      ...(activeEnv.base_url ? { base_url: activeEnv.base_url } : {})
    }, [{ key: 'base_url', value: activeEnv.base_url || 'http://127.0.0.1:8000', enabled: true }]));
  }, [remoteEnvConfigs]);

  const updateKeyValueRow = (setter, index, patch) => {
    setter((prev) => (Array.isArray(prev) ? prev : []).map((row, rowIndex) => (
      rowIndex === index ? { ...row, ...patch } : row
    )));
  };

  const addKeyValueRow = (setter) => {
    setter((prev) => [...(Array.isArray(prev) ? prev : []), { ...EMPTY_ROW }]);
  };

  const removeKeyValueRow = (setter, index) => {
    setter((prev) => {
      const nextRows = (Array.isArray(prev) ? prev : []).filter((_, rowIndex) => rowIndex !== index);
      return nextRows.length ? nextRows : [{ ...EMPTY_ROW }];
    });
  };

  const renderKeyValueRows = (rows, setter, { keyPlaceholder = 'key', valuePlaceholder = 'value', addLabel = '添加一行' } = {}) => {
    const safeRows = Array.isArray(rows) && rows.length ? rows : [{ ...EMPTY_ROW }];
    return (
      <div className="space-y-2">
        {safeRows.map((row, index) => (
          <div key={index} className="grid grid-cols-[18px_minmax(0,0.9fr)_minmax(0,1.2fr)_24px] gap-1.5 items-center">
            <input
              type="checkbox"
              checked={row.enabled !== false}
              onChange={(event) => updateKeyValueRow(setter, index, { enabled: event.target.checked })}
              className="size-3 accent-[var(--accent-color)]"
            />
            <input
              value={row.key || ''}
              onChange={(event) => updateKeyValueRow(setter, index, { key: event.target.value })}
              placeholder={keyPlaceholder}
              className="min-w-0 px-2 py-1.5 rounded-md border border-[var(--border-color)] bg-[var(--bg-app)]/30 text-[10px] text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-color)]"
            />
            <input
              value={row.value || ''}
              onChange={(event) => updateKeyValueRow(setter, index, { value: event.target.value })}
              placeholder={valuePlaceholder}
              className="min-w-0 px-2 py-1.5 rounded-md border border-[var(--border-color)] bg-[var(--bg-app)]/30 text-[10px] text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-color)]"
            />
            <button
              type="button"
              onClick={() => removeKeyValueRow(setter, index)}
              className="size-6 rounded-md border border-[var(--border-color)] text-[var(--text-secondary)] hover:text-red-500 hover:border-red-500/40 flex items-center justify-center"
              title="删除"
            >
              <XCircle className="size-3" />
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() => addKeyValueRow(setter)}
          className="w-full py-1.5 border border-dashed border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] text-[10px] rounded-lg cursor-pointer text-center flex items-center justify-center gap-1 hover:border-[var(--accent-color)] transition-all"
        >
          <Plus className="size-3" />
          <span>{addLabel}</span>
        </button>
      </div>
    );
  };

  const getActiveLibId = () => activeBackendLib?.backendId || activeBackendLib?.raw?.id || null;
  const activeImportSource = IMPORT_SOURCES.find((item) => item.id === importSourceId) || IMPORT_SOURCES[0];
  const isFileImportSource = activeImportSource.mode === 'file';

  const handleImportSourceChange = (sourceId) => {
    const currentSource = IMPORT_SOURCES.find((item) => item.id === importSourceId) || IMPORT_SOURCES[0];
    const nextSource = IMPORT_SOURCES.find((item) => item.id === sourceId) || IMPORT_SOURCES[0];
    setImportSourceId(sourceId);
    setImportError('');
    setImportResult(null);
    if (nextSource.mode === 'file') {
      if (!importFile || inferFileFormat(importFile) !== nextSource.format) {
        setImportFile(null);
      }
      return;
    }
    if (!importText.trim() || importText === currentSource.sample || currentSource.mode === 'file') {
      setImportText(nextSource.sample);
    }
  };

  const openImportFilePicker = () => {
    importFileInputRef.current?.click();
  };

  const handleImportFileChange = (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    const sourceFormat = inferFileFormat(file);
    if (!FILE_IMPORT_SOURCE_IDS.has(sourceFormat)) {
      const message = '当前仅支持导入 DOCX / PDF / XLSX / XMind 文件。';
      setImportError(message);
      showToast(message, 'error');
      return;
    }
    if (file.size > MAX_IMPORT_FILE_SIZE) {
      const message = '单个导入文件不能超过 50MB。';
      setImportError(message);
      showToast(message, 'error');
      return;
    }

    setImportSourceId(sourceFormat);
    setImportFile(file);
    setImportError('');
    setImportResult(null);
  };

  const handleImportApis = async () => {
    const source = IMPORT_SOURCES.find((item) => item.id === importSourceId) || IMPORT_SOURCES[0];
    setIsImporting(true);
    setImportError('');
    setImportResult(null);
    try {
      let libId = getActiveLibId();
      if (!libId) {
        if (!projectContext?.id) throw new Error('当前没有可用项目，无法创建接口库。');
        const createdLib = await apiPost(`/projects/${projectContext.id}/api-test-libs`, {
          name: `R25 导入接口库 ${new Date().toLocaleString('zh-CN', { hour12: false })}`,
          description: 'R25 前端导入面板创建',
          import_source: source.sourceType
        });
        libId = createdLib?.id;
      }
      if (!libId) throw new Error('接口库创建失败，后端未返回 lib id。');

      const payload = {
        source_type: source.sourceType,
        source_format: source.format,
        generate_cases: importGenerateCases,
        create_cases: importCreateCases
      };
      if (source.mode === 'file') {
        if (!(importFile instanceof File)) {
          throw new Error('请先选择要导入的文件。');
        }
        const contentBase64 = await readFileAsBase64(importFile);
        Object.assign(payload, {
          source_file_name: importFile.name,
          file_name: importFile.name,
          mime_type: importFile.type || undefined,
          content_type: importFile.type || undefined,
          file_size: importFile.size,
          upload_mode: 'base64',
          content_base64: contentBase64
        });
      } else {
        Object.assign(payload, {
          raw_text: importText,
          content: importText
        });
        if (source.format === 'json') {
          const parsed = parseJsonSource(importText);
          if (!parsed.ok) throw new Error(parsed.message);
          if (source.sourceType === 'har') {
            payload.har = parsed.value;
          } else {
            payload.schema = parsed.value;
          }
        }
      }

      const result = await apiPost(`/api-test-libs/${libId}/apis/import`, payload, { timeoutMs: 20000 });
      setImportResult(result);
      showToast('接口导入完成，列表已刷新。', 'success');
      await loadApiTestingData({ silent: true });
    } catch (error) {
      const message = readErrorMessage(error, '接口导入失败。');
      setImportError(message);
      showToast(message, 'error');
    } finally {
      setIsImporting(false);
    }
  };

  const buildDebugPayload = (forceSaveAsCase = false) => {
    const expectedStatus = Number(debugForm.expectedStatus);
    const headers = rowsToObject(debugHeaders);
    const query = rowsToObject(debugQuery);
    const runVariables = rowsToObject(runVarRows);
    const environmentVariables = rowsToObject(envVarRows);
    return {
      method: String(debugForm.method || 'GET').toUpperCase(),
      url: debugForm.url.trim() || joinUrl(debugForm.baseUrl, debugForm.path),
      base_url: debugForm.baseUrl,
      path: debugForm.path,
      headers,
      headers_override: headers,
      query,
      body: parseBodyInput(debugForm.body),
      expected_status: Number.isFinite(expectedStatus) ? expectedStatus : undefined,
      assertions: Number.isFinite(expectedStatus) ? [{ type: 'status_code', expected: expectedStatus }] : [],
      environment_id: selectedEnvironmentId || undefined,
      environment_variables: environmentVariables,
      variables: runVariables,
      save_as_case: Boolean(saveAsCase || forceSaveAsCase),
      enable_scripts: Boolean(enableScripts),
      pre_script: enableScripts ? preScript : undefined,
      post_script: enableScripts ? postScript : undefined
    };
  };

  const handleLoadMocks = async () => {
    const libId = getActiveLibId();
    if (!libId) {
      setMockStatus({ type: 'error', message: '当前没有可用接口库，无法加载 Mock。' });
      return;
    }
    try {
      const payload = await apiGet(`/api-test-libs/${libId}/mocks`, { params: { page: 1, pageSize: 20 } });
      const rules = pickList(payload);
      setRemoteMocks(rules);
      setMockStatus({ type: 'success', message: rules.length ? `已加载 ${rules.length} 条 Mock 规则。` : '暂无 Mock 规则。' });
    } catch (error) {
      setMockStatus({ type: 'error', message: readErrorMessage(error, 'Mock 规则加载失败。') });
    }
  };

  const handleSaveMockRule = async () => {
    const libId = getActiveLibId();
    if (!libId) {
      setMockStatus({ type: 'error', message: '当前没有可用接口库，无法新增 Mock。' });
      return;
    }
    setIsSavingMock(true);
    try {
      const payload = {
        method: mockForm.method,
        path: mockForm.path,
        status_code: Number(mockForm.statusCode) || 200,
        response_body: parseBodyInput(mockForm.responseBody),
        is_enabled: true
      };
      const result = await apiPost(`/api-test-libs/${libId}/mocks`, payload, { timeoutMs: 10000 });
      setMockStatus({ type: 'success', message: `Mock 规则已提交：${result?.id ? `#${result.id}` : '后端已接收'}` });
      await handleLoadMocks();
    } catch (error) {
      setMockStatus({ type: 'error', message: readErrorMessage(error, 'Mock 规则提交失败。') });
    } finally {
      setIsSavingMock(false);
    }
  };

  const handleToggleMockRule = async (rule) => {
    const libId = getActiveLibId();
    if (!libId || !rule?.id) {
      setMockStatus({ type: 'error', message: 'Mock 规则缺少 id，无法启停。' });
      return;
    }
    const nextEnabled = !(rule.is_enabled ?? rule.isEnabled ?? rule.enabled);
    try {
      await apiPost(`/api-test-libs/${libId}/mocks`, {
        id: rule.id,
        action: nextEnabled ? 'enable' : 'disable',
        is_enabled: nextEnabled
      }, { timeoutMs: 10000 });
      setMockStatus({ type: 'success', message: `Mock 规则已${nextEnabled ? '启用' : '停用'}。` });
      await handleLoadMocks();
    } catch (error) {
      setMockStatus({ type: 'error', message: readErrorMessage(error, 'Mock 规则启停失败。') });
    }
  };

  const handleDispatchMockSmoke = async () => {
    const libId = getActiveLibId();
    if (!libId) {
      setMockStatus({ type: 'error', message: '当前没有可用接口库，无法 dispatch。' });
      return;
    }
    setIsDispatchingMock(true);
    try {
      const result = await apiPost('/api-mocks/dispatch', {
        lib_id: libId,
        method: mockForm.method,
        path: mockForm.path,
        headers: rowsToObject(debugHeaders),
        query: rowsToObject(debugQuery),
        body: parseBodyInput(debugForm.body),
        variables: rowsToObject(runVarRows)
      }, { timeoutMs: 10000 });
      setMockStatus({ type: 'success', message: 'Mock dispatch 已返回真实结果。' });
      setResponseBody(safeStringify(result));
      setResponseTab('body');
    } catch (error) {
      const message = readErrorMessage(error, 'Mock dispatch 失败。');
      setMockStatus({ type: 'error', message });
      setResponseBody(safeStringify({ error: message, payload: error?.payload || null }));
    } finally {
      setIsDispatchingMock(false);
    }
  };

  const handleSyncSwagger = async () => {
    if (!projectContext?.id) {
      showToast('后端暂无可用项目，暂无法同步 Swagger。', 'error');
      return;
    }

    setIsSyncingSwagger(true);
    try {
      const lib = await apiPost(`/projects/${projectContext.id}/api-test-libs`, {
        name: `Round16 Swagger 接口库 ${new Date().toLocaleString('zh-CN', { hour12: false })}`,
        description: '前端同步 Swagger 生成的接口库',
        import_source: 'openapi'
      });

      const imported = await apiPost(`/api-test-libs/${lib.id}/apis/import`, {
        source_type: 'openapi',
        generate_cases: true,
        schema: {
          openapi: '3.0.0',
          info: { title: 'Round16 ApiTesting Smoke', version: '1.0.0' },
          paths: {
            '/api/v2/projects': {
              get: {
                summary: 'List projects',
                responses: { '200': { description: 'ok' } }
              }
            },
            '/api/v2/system/schema-status': {
              get: {
                summary: 'Schema status',
                responses: { '200': { description: 'ok' } }
              }
            }
          }
        }
      });

      showToast(`已同步 ${imported.imported || pickList(imported.apis).length || 0} 个接口，并生成 ${imported.test_case_count || 0} 条接口用例。`, 'success');
      await loadApiTestingData({ silent: true });
    } catch (error) {
      showToast(error?.message || 'Swagger 同步失败，请检查后端服务。', 'error');
    } finally {
      setIsSyncingSwagger(false);
    }
  };

  const handleSend = async ({ forceSaveAsCase = false } = {}) => {
    setIsSending(true);
    setResponseBody('');
    setDebugResult(null);
    if (forceSaveAsCase) setSavedCaseResult(null);
    try {
      const result = await apiPost('/apis/debug', buildDebugPayload(forceSaveAsCase), { timeoutMs: 15000 });
      const normalized = normalizeDebugResult(result);
      setDebugResult(normalized);
      setResponseBody(safeStringify(result));
      if (normalized.savedCase) {
        setSavedCaseResult(normalized.savedCase);
        await loadApiTestingData({ silent: true });
      }
      showToast(`接口调试完成，HTTP ${normalized.statusCode || 'ok'}，耗时 ${normalized.durationMs || 0}ms。`, 'success');
    } catch (error) {
      const message = readErrorMessage(error, '接口调试失败。');
      setResponseBody(safeStringify({ error: message, payload: error?.payload || null }));
      showToast(message, 'error');
    } finally {
      setIsSending(false);
    }
  };

  const buildDataFactoryPayload = () => {
    const activeApi = activeBackendLib?.rawApis?.[0];
    const activeApiCase = activeBackendLib?.rawCases?.[0];
    const modes = DATA_FACTORY_SCENARIOS.map((item) => item.id);
    return {
      project_id: projectContext?.id || selectedProject?.id || undefined,
      lib_id: getActiveLibId() || undefined,
      api_id: activeApi?.id || undefined,
      api_case_id: activeApiCase?.id || undefined,
      modes,
      targets: ['body', 'query', 'variables'],
      count: 12,
      max_count: 12,
      request: {
        method: String(debugForm.method || 'GET').toUpperCase(),
        url: debugForm.url.trim() || joinUrl(debugForm.baseUrl, debugForm.path),
        base_url: debugForm.baseUrl,
        path: debugForm.path,
        headers: rowsToObject(debugHeaders),
        query: rowsToObject(debugQuery),
        body: parseBodyInput(debugForm.body)
      },
      schema: {
        headers: activeApi?.headers_schema || {},
        query: activeApi?.query_schema || {},
        body: activeApi?.body_schema || {}
      },
      variables: rowsToObject(runVarRows),
      environment_variables: rowsToObject(envVarRows)
    };
  };

  const handleGenerateTestData = async () => {
    setDataFactoryState({ loading: true, result: null, error: '' });
    try {
      const result = await apiPost('/data-factory/api-parameters/generate', buildDataFactoryPayload(), { timeoutMs: 20000 });
      setDataFactoryState({ loading: false, result, error: '' });
      showToast('测试数据已由后端数据工厂生成。', 'success');
    } catch (error) {
      const message = readErrorMessage(error, '测试数据生成失败。');
      setDataFactoryState({ loading: false, result: null, error: message });
      showToast(message, 'error');
    }
  };

  const handleCopyFactoryItem = async (item) => {
    const content = safeStringify(item?.value);
    try {
      if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable');
      await navigator.clipboard.writeText(content);
      showToast('测试数据已复制到剪贴板。', 'success');
    } catch {
      setResponseBody(content);
      setResponseTab('body');
      showToast('当前浏览器无法写入剪贴板，已放入响应控制台。', 'warning');
    }
  };

  const handleApplyFactoryItemToVariables = (item) => {
    const variables = getFactoryApplyValue(item, 'variables');
    const entries = Object.entries(variables);
    if (!entries.length) {
      showToast('该数据项没有可应用到变量的键值。', 'warning');
      return;
    }
    setRunVarRows(objectToRows(variables));
    showToast('已应用到本次运行变量。', 'success');
  };

  const handleApplyFactoryItemToBody = (item) => {
    const bodyValue = getFactoryApplyValue(item, 'body');
    setDebugForm((prev) => ({ ...prev, body: typeof bodyValue === 'string' ? bodyValue : safeStringify(bodyValue) }));
    setRequestTab('body');
    showToast('已应用到请求体。', 'success');
  };

  const renderDataFactoryPanel = () => {
    if (!dataFactoryState.loading && !dataFactoryState.error && !dataFactoryState.result) return null;

    return (
      <div className="theme-card rounded-xl p-4 shadow-soft space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-color)] pb-2">
          <h3 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
            <Sparkles className="size-3.5 text-[var(--accent-color)]" />
            <span>数据工厂结果</span>
          </h3>
          <button
            onClick={handleGenerateTestData}
            disabled={dataFactoryState.loading}
            className="px-2.5 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)] text-[10px] font-bold text-[var(--text-primary)] disabled:opacity-60"
          >
            {dataFactoryState.loading ? '生成中...' : '重新生成'}
          </button>
        </div>

        {dataFactoryState.loading && (
          <div className="min-h-20 flex items-center justify-center text-[10px] text-[var(--text-secondary)]">
            正在调用 /data-factory/api-parameters/generate...
          </div>
        )}

        {dataFactoryState.error && (
          <div className="rounded-lg border border-red-500/25 bg-red-500/10 text-red-500 text-[10px] p-3 break-words">
            {dataFactoryState.error}
          </div>
        )}

        {dataFactoryState.result && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {DATA_FACTORY_SCENARIOS.map((scenario) => {
              const items = normalizeFactoryItemsForScenario(dataFactoryState.result, scenario);
              return (
                <div key={scenario.id} className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30 p-3 min-w-0">
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <div className="text-[10px] font-bold text-[var(--text-primary)]">{scenario.label}</div>
                    <div className="text-[8px] text-[var(--text-secondary)]">{items.length} 组</div>
                  </div>
                  {items.length ? (
                    <div className="space-y-2">
                      {items.map((item) => (
                        <div key={item.id} className="rounded-md border border-[var(--border-color)] bg-[var(--bg-card)]/70 p-2 space-y-2">
                          <div className="text-[9px] font-bold text-[var(--text-primary)] truncate" title={item.title}>{item.title}</div>
                          <pre className="max-h-28 overflow-auto whitespace-pre-wrap break-all text-[8.5px] font-mono text-[var(--text-secondary)]">{safeStringify(item.value)}</pre>
                          <div className="flex flex-wrap gap-1.5">
                            <button
                              onClick={() => handleCopyFactoryItem(item)}
                              className="flex items-center gap-1 px-2 py-1 rounded border border-[var(--border-color)] text-[8.5px] font-bold text-[var(--text-primary)] hover:bg-[var(--border-color)]"
                            >
                              <Clipboard className="size-3" />
                              <span>复制</span>
                            </button>
                            <button
                              onClick={() => handleApplyFactoryItemToVariables(item)}
                              className="flex items-center gap-1 px-2 py-1 rounded border border-[var(--border-color)] text-[8.5px] font-bold text-[var(--text-primary)] hover:bg-[var(--border-color)]"
                            >
                              <FileInput className="size-3" />
                              <span>应用变量</span>
                            </button>
                            <button
                              onClick={() => handleApplyFactoryItemToBody(item)}
                              className="flex items-center gap-1 px-2 py-1 rounded bg-[var(--accent-color)] text-white text-[8.5px] font-bold hover:opacity-90"
                            >
                              <Save className="size-3" />
                              <span>应用请求体</span>
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="rounded-md border border-dashed border-[var(--border-color)] p-3 text-[9px] text-[var(--text-secondary)] text-center">
                      后端未返回该类型数据。
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  const handleRunAssertions = async () => {
    const activeLib = (remoteLibs.length ? remoteLibs : apiLibs)[selectedLibIdx] || remoteLibs[0];
    const caseIds = (activeLib?.rawCases || []).map((item) => item.id).filter(Boolean).slice(0, 10);
    if (!caseIds.length) {
      showToast('当前接口库还没有后端接口用例，请先同步 Swagger。', 'info');
      return;
    }

    setIsRunningAssertions(true);
    try {
      const result = await apiPost('/api-test-cases/batch-executions', {
        case_ids: caseIds,
        base_url: 'http://127.0.0.1:8000'
      }, { timeoutMs: 15000 });
      const executions = toList(toRecord(result).executions || result);
      const passed = executions.filter((item) => item.status === 'passed').length;
      setResponseBody(safeStringify(result));
      showToast(`已执行 ${executions.length} 条接口断言，通过 ${passed} 条。`, passed === executions.length ? 'success' : 'warning');
    } catch (error) {
      showToast(error?.message || '接口断言执行失败。', 'error');
    } finally {
      setIsRunningAssertions(false);
    }
  };

  // 渲染：环境配置与场景链路编排
  const handlePublishAndRunScenario = async () => {
    const activeLib = remoteLibs[selectedLibIdx] || remoteLibs[0];
    const caseIds = (activeLib?.rawCases || []).map((item) => item.id).filter(Boolean).slice(0, 3);
    if (!activeLib?.backendId || caseIds.length === 0) {
      showToast('当前接口库还没有可编排的后端用例，请先同步 Swagger。', 'info');
      return;
    }

    setIsRunningScenarioChain(true);
    try {
      const extractMappings = rowsToObject(scenarioMappingRows);
      let environment = remoteEnvConfigs.find((item) => String(item.id) === String(selectedEnvironmentId))
        || remoteEnvConfigs.find((item) => item.is_active || item.isActive)
        || remoteEnvConfigs[0];
      if (!environment?.id) {
        environment = await apiPost(`/api-test-libs/${activeLib.backendId}/environments`, {
          name: 'Local Backend',
          base_url: 'http://127.0.0.1:8000',
          variables: { project_id: projectContext?.id, ...rowsToObject(envVarRows) },
          is_active: true
        });
      }

      const scenario = await apiPost(`/api-test-libs/${activeLib.backendId}/scenarios`, {
        name: `Scenario ${new Date().toLocaleString('zh-CN', { hour12: false })}`,
        description: 'Frontend-created API scenario chain',
        nodes: caseIds.map((caseId, index) => ({
          id: `case-${caseId}`,
          type: 'case',
          case_id: caseId,
          order: index + 1,
          extract: index === 0 ? extractMappings : {}
        })),
        edges: caseIds.slice(1).map((caseId, index) => ({
          source: `case-${caseIds[index]}`,
          target: `case-${caseId}`
        })),
        data_mappings: { extract: extractMappings }
      });

      const scenarioResult = await apiPost(`/api-scenarios/${scenario.id}/execute`, {
        environment_id: environment.id,
        base_url: environment.base_url || 'http://127.0.0.1:8000',
        variables: rowsToObject(runVarRows),
        data_mappings: { extract: extractMappings },
        stop_on_failure: false
      }, { timeoutMs: 15000 });

      let schedule = remoteSchedules[0];
      if (!schedule?.id) {
        schedule = await apiPost(`/api-test-libs/${activeLib.backendId}/schedules`, {
          name: 'Manual scenario smoke',
          cron_expression: '* * * * *',
          target_type: 'scenario',
          target_ids: [scenario.id],
          is_enabled: true
        });
      }
      const scheduleResult = await apiPost(`/api-schedules/${schedule.id}/run`, {
        force: true,
        environment_id: environment.id,
        base_url: environment.base_url || 'http://127.0.0.1:8000'
      }, { timeoutMs: 15000 });

      setScenarioRunResult({ scenarioResult, scheduleResult });
      setResponseBody(safeStringify({ scenarioResult, scheduleResult }));
      await loadApiRuntimeData(activeLib);
      showToast(`场景链路已执行：${scenarioResult?.summary?.status || scenarioResult?.status || 'done'}，计划任务已回写。`, 'success');
    } catch (error) {
      showToast(error?.message || '场景链路执行失败，请检查后端服务。', 'error');
    } finally {
      setIsRunningScenarioChain(false);
    }
  };

  const renderEnvScenario = () => {
    const displayEnvConfigs = remoteEnvConfigs.length
      ? remoteEnvConfigs.flatMap((env) => Object.entries(toRecord(env.variables)).map(([key, value]) => ({
        id: `${env.id}-${key}`,
        key,
        value: String(value),
        desc: `${env.name || 'Backend env'} / ${env.base_url || '--'}`
      }))).concat(remoteEnvConfigs.map((env) => ({
        id: `${env.id}-base-url`,
        key: 'base_url',
        value: env.base_url || '--',
        desc: env.is_active || env.isActive ? 'active backend environment' : 'backend environment'
      })))
      : envConfigs;
    const displayScenarioSteps = remoteScenarioSteps.length ? remoteScenarioSteps : scenarioSteps;
    const latestSchedule = remoteSchedules[0];
    const scenarioSummary = scenarioRunResult?.scenarioResult?.summary || latestSchedule?.last_result || latestSchedule?.lastResult;
    const scenarioResultPayload = toRecord(scenarioRunResult?.scenarioResult);
    const extractedVariables = toRecord(scenarioResultPayload.extracted_variables || scenarioResultPayload.extractedVariables);
    const nodeResults = toList(scenarioResultPayload.node_results || scenarioResultPayload.nodeResults || scenarioResultPayload.nodes);
    return (
      <div className="space-y-4 text-left animate-[fadeIn_0.2s_ease-out] w-full">
        {/* 流光连线动画样式注入 */}
        <style dangerouslySetInnerHTML={{__html: `
          @keyframes dash-flow {
            to {
              stroke-dashoffset: -20;
            }
          }
          .svg-flow-line {
            stroke-dasharray: 6, 4;
            animation: dash-flow 1.5s linear infinite;
          }
        `}} />

        {/* 面包屑 */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <button 
              onClick={() => setViewMode('list')}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] text-[10.5px] text-[var(--text-secondary)] hover:bg-[var(--border-color)] hover:scale-[1.02] transition-all shadow-sm cursor-pointer"
            >
              <ArrowLeft className="size-3" />
              <span>返回接口列表</span>
            </button>
            <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-secondary)]/70 font-semibold">
              <span>接口测试</span>
              <span>/</span>
              <span className="text-[var(--text-primary)]">接口环境配置与场景链路</span>
            </div>
          </div>
          <button 
            onClick={handlePublishAndRunScenario}
            disabled={isRunningScenarioChain}
            className="px-4 py-2 text-[11.5px] accent-btn"
          >
            {isRunningScenarioChain ? '后端链路执行中...' : '发布配置并执行链路'}
          </button>
        </div>

        {/* 顶部简述 */}
        <div className="theme-card rounded-xl p-4 shadow-soft flex items-center justify-between">
          <div className="text-left">
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 bg-[rgba(59,130,246,0.12)] text-blue-500 rounded text-[9.5px] font-bold">场景: 登录支付下单链路</span>
              <h2 className="font-bold text-xs text-[var(--text-primary)]">核心业务流程自动化链路测试</h2>
            </div>
            <p className="text-[10px] text-[var(--text-secondary)] mt-1.5 leading-none">
              后端环境: {remoteEnvConfigs[0]?.base_url || '待创建'} | 场景节点: {displayScenarioSteps.length} | 计划任务: {latestSchedule?.id ? `#${latestSchedule.id}` : '待创建'}
            </p>
          </div>
          <div className="flex gap-2">
            <div className="px-3 py-1.5 border border-[var(--border-color)] bg-[var(--bg-app)] rounded-lg text-[10px] text-[var(--text-primary)] font-bold">场景状态: {scenarioSummary?.status || '未执行'}</div>
            <div className="px-3 py-1.5 border border-[var(--border-color)] bg-[var(--bg-app)] rounded-lg text-[10px] text-[var(--text-primary)] font-bold">最近执行: {latestSchedule?.last_run_at ? formatDateTime(latestSchedule.last_run_at) : '--'}</div>
          </div>
        </div>

        <div className="grid grid-cols-12 gap-4 items-start w-full">
          {/* 左侧：多套测试环境配置 */}
          <div className="col-span-12 lg:col-span-5 theme-card rounded-xl p-4 shadow-soft space-y-4">
            <div className="flex justify-between items-center border-b border-[var(--border-color)] pb-2">
              <h3 className="text-xs font-bold text-[var(--text-primary)]">全局多套环境参数配置</h3>
              <div className="p-0.5 border border-[var(--border-color)] rounded-lg flex gap-0.5 bg-[var(--bg-app)] text-[9px] font-bold">
                <button className="bg-[var(--accent-color)] text-[var(--accent-text)] px-2.5 py-1 rounded-md transition-all shadow-sm">TEST</button>
                <button className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--border-color)]/30 px-2.5 py-1 rounded-md transition-all">DEV</button>
                <button className="text-[var(--text-secondary)] hover:text(--text-primary) hover:bg-[var(--border-color)]/30 px-2.5 py-1 rounded-md transition-all">PRE</button>
              </div>
            </div>

            <div className="space-y-3">
              <div className="p-3 bg-[var(--bg-app)] border border-[var(--border-color)] rounded-lg text-[9.5px] space-y-1.5">
                <div className="font-bold text-[var(--text-primary)]">网关基本特征</div>
                <div className="grid grid-cols-2 gap-2 text-[var(--text-secondary)]">
                  <div>网关地址: <span className="text-[var(--text-primary)] font-mono font-bold">gateway-test.api</span></div>
                  <div>运行状态: <span className="text-emerald-500 font-bold">● Healthy</span></div>
                </div>
              </div>

              <div className="overflow-x-auto w-full">
                <table className="w-full text-[10px] text-left border-collapse">
                  <thead>
                    <tr className="text-[var(--text-secondary)] font-bold border-b border-[var(--border-color)]">
                      <th className="py-2 px-1">参数名 (Key)</th>
                      <th className="py-2 px-1">配置值 (Value)</th>
                      <th className="py-2 px-1">描述说明</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border-color)]/50 text-[var(--text-primary)] font-mono">
                    {displayEnvConfigs.map((cfg) => (
                      <tr key={cfg.id} className="hover:bg-[var(--border-color)]/30">
                        <td className="py-2.5 px-1 font-bold text-[var(--text-primary)]">{cfg.key}</td>
                        <td className="py-2.5 px-1 text-[var(--accent-color)] truncate max-w-[140px]" title={cfg.value}>{cfg.value}</td>
                        <td className="py-2.5 px-1 text-[9px] text-[var(--text-secondary)] font-sans">{cfg.desc}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <button 
                onClick={() => window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '新增环境变量键值对模板就绪。', type: 'info' } }))}
                className="w-full py-2 border border-dashed border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] text-[10px] rounded-lg cursor-pointer text-center flex items-center justify-center gap-1 hover:border-[var(--accent-color)] transition-all"
              >
                <Plus className="size-3.5" />
                <span>添加全局环境变量</span>
              </button>
            </div>
          </div>

          {/* 右侧：流式场景链路编排（SVG 呼吸跑马灯流光线条） */}
          <div className="col-span-12 lg:col-span-7 theme-card rounded-xl p-4 shadow-soft">
            <div className="flex justify-between items-center border-b border-[var(--border-color)] pb-2 mb-4">
              <h3 className="text-xs font-bold text-[var(--text-primary)]">流式 API 场景链路编排可视化控制台</h3>
              <button 
                onClick={() => window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '拓扑依赖拓扑图智能对齐完成。', type: 'success' } }))}
                className="px-2 py-0.5 text-[9px] font-bold border border-[var(--border-color)] rounded bg-[var(--bg-card)] hover:bg-[var(--border-color)] text-[var(--text-primary)] cursor-pointer transition-all"
              >
                智能排版对齐
              </button>
            </div>

            <div className="grid grid-cols-12 gap-4">
              {/* 步骤列表 */}
              <div className="col-span-7 space-y-4 max-h-[460px] overflow-y-auto pr-1">
                {displayScenarioSteps.map((step, idx) => {
                  const isSelected = selectedStepIdx === idx;
                  return (
                    <div key={idx} className="relative flex items-start gap-3">
                      {/* SVG 呼吸跑马灯流光连线 */}
                      {idx < displayScenarioSteps.length - 1 && (
                        <div className="absolute left-[15px] top-8 bottom-0 w-[2px] -z-10" style={{ height: 'calc(100% + 16px)' }}>
                          <svg className="w-full h-full" preserveAspectRatio="none">
                            <line 
                              x1="1" y1="0" x2="1" y2="100%" 
                              stroke="var(--border-color)" 
                              strokeWidth="2" 
                            />
                            <line 
                              x1="1" y1="0" x2="1" y2="100%" 
                              stroke="var(--accent-color)" 
                              strokeWidth="2" 
                              className="svg-flow-line"
                            />
                          </svg>
                        </div>
                      )}

                      <div 
                        onClick={() => setSelectedStepIdx(idx)}
                        className={`size-8 rounded-full border flex items-center justify-center shrink-0 text-[10px] font-bold font-mono cursor-pointer transition-all ${
                          isSelected 
                            ? 'border-[var(--accent-color)] bg-[var(--accent-color)] text-[var(--accent-text)] scale-110 shadow-lg' 
                            : 'border-[var(--border-color)] bg-[var(--bg-app)] text-[var(--text-secondary)] hover:border-[var(--accent-color)]'
                        }`}
                      >
                        {idx + 1}
                      </div>

                      <div 
                        onClick={() => setSelectedStepIdx(idx)}
                        className={`flex-1 p-3 border rounded-xl text-[10px] text-left transition-all shadow-sm cursor-pointer ${
                          isSelected 
                            ? 'border-[var(--accent-color)] bg-[var(--accent-glow)] scale-[1.01]' 
                            : 'border-[var(--border-color)] bg-[var(--bg-card)] hover:border-[var(--accent-color)]/50'
                        }`}
                      >
                        <div className="flex justify-between items-center">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <span className="px-1.5 py-0.5 rounded text-[8px] font-bold bg-[rgba(59,130,246,0.12)] text-blue-500">{step.method}</span>
                            <span className="font-bold text-[var(--text-primary)] truncate" title={step.name}>{step.name}</span>
                          </div>
                          <span className="font-mono text-[var(--text-secondary)] text-[8.5px]">{step.url}</span>
                        </div>
                        <p className="text-[var(--text-secondary)] mt-1 text-[9px]">{step.desc}</p>
                        
                        {step.extracts !== '—' && (
                          <div className="mt-2 pt-2 border-t border-[var(--border-color)]/40 flex items-center gap-2">
                            <span className="text-[8px] bg-[rgba(139,92,246,0.12)] text-purple-500 px-1 py-0.5 rounded font-bold">参数提取</span>
                            <code className="text-purple-500 font-mono text-[8.5px] font-bold">{step.extracts}</code>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}

                <button 
                  onClick={() => window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '新步骤已追加至链路末尾，请配置URL及参数。', type: 'success' } }))}
                  className="py-2 border border-dashed border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--accent-color)] text-[10px] rounded-lg cursor-pointer text-center flex items-center justify-center gap-1 ml-11 transition-all"
                  style={{ width: 'calc(100% - 44px)' }}
                >
                  <Plus className="size-3.5" />
                  <span>向场景链路插入新请求步骤</span>
                </button>
              </div>

              {/* 联动步骤参数详情与 AI 智能断言 */}
              <div className="col-span-5 theme-card rounded-xl p-4 bg-[var(--bg-app)]/30 text-left space-y-4">
                <div>
                  <h4 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1">
                    <Sparkles className="size-3.5 text-[var(--accent-color)]" />
                    <span>步骤 {selectedStepIdx + 1} 遥测与 AI 断言</span>
                  </h4>
                  <p className="text-[8px] text-[var(--text-secondary)] mt-1">当前请求：<span className="font-mono font-semibold">{displayScenarioSteps[selectedStepIdx]?.method} {displayScenarioSteps[selectedStepIdx]?.url}</span></p>
                </div>

                <div className="space-y-3">
                  <div className="p-2.5 border border-[var(--border-color)] bg-[var(--bg-card)] rounded-lg text-[9.5px] space-y-1.5">
                    <div className="font-bold text-[var(--text-primary)]">性能预期遥测</div>
                    <div className="flex justify-between text-[9px] text-[var(--text-secondary)]">
                      <span>预估延迟:</span>
                      <span className="font-mono text-[var(--text-primary)] font-bold">{displayScenarioSteps[selectedStepIdx]?.delay}</span>
                    </div>
                    <div className="flex justify-between text-[9px] text-[var(--text-secondary)]">
                      <span>网络开销:</span>
                      <span className="font-mono text-[var(--text-primary)]">~ 1.2 KB</span>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="text-[9.5px] font-bold text-[var(--text-primary)]">变量提取映射</div>
                    <p className="text-[8px] text-[var(--text-secondary)]">变量名 -&gt; JSONPath，创建场景写入 data_mappings.extract 与首节点 extract。</p>
                    {renderKeyValueRows(scenarioMappingRows, setScenarioMappingRows, {
                      keyPlaceholder: '变量名',
                      valuePlaceholder: '$.data.id',
                      addLabel: '添加提取映射'
                    })}
                  </div>

                  {(Object.keys(extractedVariables).length > 0 || nodeResults.length > 0) && (
                    <div className="p-2.5 border border-[var(--border-color)] bg-[var(--bg-card)] rounded-lg text-[9px] space-y-2">
                      <div className="font-bold text-[var(--text-primary)]">最近执行提取结果</div>
                      {Object.keys(extractedVariables).length > 0 && (
                        <pre className="max-h-24 overflow-auto whitespace-pre-wrap break-all font-mono text-[8.5px] text-emerald-500">{safeStringify(extractedVariables)}</pre>
                      )}
                      {nodeResults.length > 0 && (
                        <pre className="max-h-28 overflow-auto whitespace-pre-wrap break-all font-mono text-[8.5px] text-[var(--text-secondary)]">{safeStringify(nodeResults)}</pre>
                      )}
                    </div>
                  )}

                  <div className="space-y-2">
                    <div className="text-[9.5px] font-bold text-[var(--text-primary)]">AI 自动注入的链路断言规则</div>
                    <label className="flex items-start gap-2 p-2 border border-[var(--border-color)] bg-[var(--bg-card)] rounded-lg text-[9px] cursor-pointer">
                      <input type="checkbox" defaultChecked className="rounded size-3 accent-[var(--accent-color)] mt-0.5" />
                      <div>
                        <div className="font-mono text-[var(--text-primary)] font-bold">status_code == 200</div>
                        <span className="text-[8px] text-[var(--text-secondary)]">验证步骤响应为成功状态码</span>
                      </div>
                    </label>
                    <label className="flex items-start gap-2 p-2 border border-[var(--border-color)] bg-[var(--bg-card)] rounded-lg text-[9px] cursor-pointer">
                      <input type="checkbox" defaultChecked className="rounded size-3 accent-[var(--accent-color)] mt-0.5" />
                      <div>
                        <div className="font-mono text-[var(--text-primary)] font-bold">response.time &lt; 500ms</div>
                        <span className="text-[8px] text-[var(--text-secondary)]">SLA性能阈值报警防护断言</span>
                      </div>
                    </label>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  // 渲染：主接口列表
  const renderListMode = () => {
    const displayLibs = remoteLibs.length ? remoteLibs : apiLibs;
    const displayStats = remoteLibs.length ? [
      { label: '接口库总数', val: numberText(remoteLibs.length), change: '后端同步', icon: Database },
      { label: '接口总数', val: numberText(remoteLibs.reduce((sum, item) => sum + Number(item.count || 0), 0)), change: '后端同步', icon: Network },
      { label: '测试用例数', val: numberText(remoteLibs.reduce((sum, item) => sum + Number(item.cases || 0), 0)), change: '后端同步', icon: CheckCircle },
      { label: '执行通过率', val: toPercentLabel(remoteLibs.reduce((sum, item) => sum + Number(item.cases || 0), 0), remoteLibs.reduce((sum, item) => sum + Number(item.cases || 0), 0), '0%'), change: apiStatus.message, hasChart: true }
    ] : apiStats;
    const activeLib = displayLibs[selectedLibIdx] || displayLibs[0];
    return (
      <div className="space-y-4 w-full">
        <div className="flex justify-between items-start">
          <div className="text-left">
            <h1 className="text-base font-bold text-[var(--text-primary)]">接口测试中心</h1>
            <p className="text-[11px] text-[var(--text-secondary)] mt-1">管理应用多端核心接口定义，智能匹配用例与全链路覆盖率评估。</p>
          </div>
          <div className="flex items-center gap-2">
            <button 
              onClick={() => setViewMode('env-scenario')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)] text-[11px] font-bold text-[var(--text-primary)] cursor-pointer transition-colors"
            >
              <span>环境与链路编排</span>
            </button>
            <button 
              onClick={handleSyncSwagger}
              disabled={isSyncingSwagger || apiStatus.loading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)] text-[11px] font-bold text-[var(--text-primary)] cursor-pointer transition-colors"
            >
              <RotateCw className="size-3.5 text-[var(--text-secondary)]" />
              <span>{isSyncingSwagger ? '同步中...' : '同步 Swagger'}</span>
            </button>
            <button 
              onClick={() => window.dispatchEvent(new CustomEvent('open-modal', { detail: { type: 'new-api-lib' } }))}
              className="px-3.5 py-1.5 text-[11px] accent-btn"
            >
              <Plus className="size-3.5 text-white inline mr-1" />
              新建接口库
            </button>
          </div>
        </div>

        {/* 指标面板 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5">
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
                <span className="text-[10px] text-[var(--text-secondary)] font-semibold">{item.label}</span>
                <div className="text-xl font-bold mt-1 text-[var(--text-primary)]">
                  <AnimatedNumber value={item.val} delay={idx * 60 + 150} />
                </div>
                <div className="text-[9px] text-[var(--text-secondary)] mt-1">较昨日 <span className="text-emerald-500 font-semibold">{item.change}</span></div>
              </div>
              {item.hasChart ? (
                <div className="size-11 shrink-0 relative sonar-ripple-container">
                  <div className="sonar-ripple-circle"></div>
                  <div className="sonar-ripple-circle sonar-ripple-circle-delay"></div>
                  <svg className="w-full h-full transform -rotate-90 relative z-10" viewBox="0 0 36 36">
                    <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--border-color)" strokeWidth="2.8" />
                    <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--accent-color)" strokeWidth="2.8" strokeDasharray="94.2 5.8" />
                    <path d="M18,18 L18,2 A16,16 0 0,1 30,10 Z" fill="var(--accent-glow)" className="radar-sweeper-beam" />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center text-[8.5px] font-bold text-[var(--text-primary)] z-10">
                  <AnimatedNumber value={parseFloat(item.val) || 0} />%
                  </div>
                </div>
              ) : (
                <div className="p-2 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)] text-[var(--accent-color)]">
                  <item.icon className="size-4" />
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="theme-card rounded-xl p-4 shadow-soft space-y-3">
          <input
            ref={importFileInputRef}
            type="file"
            accept={activeImportSource.accept || FILE_IMPORT_ACCEPT}
            className="hidden"
            onChange={handleImportFileChange}
          />
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border-color)] pb-2">
            <div>
              <h3 className="text-xs font-bold text-[var(--text-primary)]">接口文档导入面板</h3>
              <p className="text-[9.5px] text-[var(--text-secondary)] mt-1">可继续粘贴 OpenAPI / HAR 文本，也可上传 DOCX / PDF / XLSX / XMind 并把文件信息发送给后端解析。</p>
            </div>
            <div className="p-0.5 border border-[var(--border-color)] rounded-lg flex gap-0.5 bg-[var(--bg-app)] text-[9px] font-bold">
              {IMPORT_SOURCES.map((source) => {
                const active = importSourceId === source.id;
                return (
                  <button
                    key={source.id}
                    type="button"
                    onClick={() => handleImportSourceChange(source.id)}
                    className={`px-2.5 py-1 rounded-md transition-all ${active ? 'bg-[var(--bg-card)] text-[var(--accent-color)] border border-[var(--border-color)]/50 shadow-sm' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-card)]/30'}`}
                  >
                    {source.label}
                  </button>
                );
              })}
            </div>
          </div>
          {isFileImportSource ? (
            <div className="rounded-lg border border-dashed border-[var(--border-color)] bg-[var(--bg-app)]/20 p-3">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-[10px] font-bold text-[var(--text-primary)]">
                    <FileInput className="size-4 text-[var(--accent-color)]" />
                    <span>{importFile ? importFile.name : '选择待导入文件'}</span>
                  </div>
                  <div className="mt-1 text-[9px] text-[var(--text-secondary)]">
                    {importFile ? `${activeImportSource.label} · ${formatFileSize(importFile.size)}` : '支持 DOCX / PDF / XLSX / XMind，导入时会发送文件名、格式、大小和 content_base64。'}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={openImportFilePicker}
                  className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-3 py-1.5 text-[10px] font-bold text-[var(--text-primary)] hover:bg-[var(--border-color)]/40"
                >
                  <FileInput className="size-3.5" />
                  <span>{importFile ? '重新选择' : '选择文件'}</span>
                </button>
              </div>
            </div>
          ) : (
            <textarea
              value={importText}
              onChange={(event) => setImportText(event.target.value)}
              className="w-full h-36 font-mono text-[10px] p-3 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30 focus:outline-none focus:border-[var(--accent-color)] leading-relaxed text-[var(--text-primary)]"
            />
          )}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3 text-[10px] text-[var(--text-secondary)]">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" checked={importGenerateCases} onChange={(event) => setImportGenerateCases(event.target.checked)} className="size-3 accent-[var(--accent-color)]" />
                <span>generate_cases</span>
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" checked={importCreateCases} onChange={(event) => setImportCreateCases(event.target.checked)} className="size-3 accent-[var(--accent-color)]" />
                <span>create_cases</span>
              </label>
              <span className="font-mono text-[var(--text-secondary)]">target: {activeLib?.backendId ? `lib #${activeLib.backendId}` : '自动创建接口库'}</span>
            </div>
            <button
              onClick={handleImportApis}
              disabled={isImporting}
              className="flex items-center gap-1.5 px-3.5 py-1.5 text-[11px] accent-btn disabled:opacity-70"
            >
              <RotateCw className={`size-3.5 ${isImporting ? 'animate-spin' : ''}`} />
              <span>{isImporting ? '导入中...' : '导入接口'}</span>
            </button>
          </div>
          {(importError || importResult) && (
            <div className={`p-3 rounded-lg border text-[10px] ${importError ? 'border-red-500/30 bg-red-500/10 text-red-500' : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600'}`}>
              {importError ? (
                <span className="break-all">{importError}</span>
              ) : (
                <pre className="max-h-28 overflow-auto whitespace-pre-wrap break-all font-mono">{safeStringify(importResult)}</pre>
              )}
            </div>
          )}
        </div>

        {/* 7:5 选中联动列表区 */}
        <div className="grid grid-cols-12 gap-4 items-start w-full">
          {/* 左侧 7/12 Table */}
          <div className="col-span-12 lg:col-span-7 theme-card rounded-xl p-4 shadow-soft">
            {/* 过滤器 */}
            <div className="flex flex-wrap items-center gap-2 mb-3.5">
              <div className="flex-1 flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30">
                <Search className="size-3.5 text-[var(--text-secondary)] shrink-0" />
                <input type="text" placeholder="搜索接口库名称、描述" className="bg-transparent border-none text-[10px] focus:outline-none w-full text-[var(--text-primary)]" />
              </div>
              <div className="flex items-center gap-1.5 text-[10.5px] text-[var(--text-secondary)] border border-[var(--border-color)] rounded px-3 py-1.5 bg-[var(--bg-card)] hover:bg-[var(--border-color)] cursor-pointer transition-colors">
                <span>协议类型</span>
                <ChevronDown className="size-3 text-[var(--text-secondary)]" />
              </div>
            </div>

            <div className="overflow-x-auto w-full">
              <table className="w-full text-[11px] text-left border-collapse min-w-[500px]">
                <thead>
                  <tr className="text-[var(--text-secondary)] font-bold border-b border-[var(--border-color)]">
                    <th className="py-2.5 px-2">接口库名称</th>
                    <th className="py-2.5 px-2">服务类型</th>
                    <th className="py-2.5 px-2 text-center">接口数</th>
                    <th className="py-2.5 px-2 text-center">用例数</th>
                    <th className="py-2.5 px-2">通过率</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-color)] text-[var(--text-primary)] font-medium">
                  {displayLibs.map((lib, idx) => (
                    <tr 
                      key={idx}
                      onClick={() => setSelectedLibIdx(idx)}
                      onDoubleClick={() => setViewMode('workbench')}
                      className={`cursor-pointer transition-colors ${
                        selectedLibIdx === idx 
                          ? 'bg-[var(--accent-glow)] border-l-2 border-l-[var(--accent-color)] font-bold' 
                          : 'hover:bg-[var(--border-color)]/30'
                      }`}
                    >
                      <td className="py-3 px-2">
                        <div className="flex items-center gap-2">
                          <Network className="size-3.5 text-[var(--accent-color)] shrink-0" />
                          <div className="flex flex-col text-left">
                            <span className="font-bold text-[var(--text-primary)]">{lib.name}</span>
                            <span className="text-[9px] text-[var(--text-secondary)] mt-0.5">{lib.desc}</span>
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-2">
                        <span className="px-2 py-0.5 bg-[var(--border-color)] text-[9.5px] rounded text-[var(--text-secondary)]">
                          {lib.type}
                        </span>
                      </td>
                      <td className="py-3 px-2 text-center font-mono">{lib.count}</td>
                      <td className="py-3 px-2 text-center font-mono">{lib.cases}</td>
                      <td className="py-3 px-2 w-[80px]">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-1 bg-[var(--border-color)] rounded-full overflow-hidden">
                            <div className="h-full bg-[var(--accent-color)]" style={{ width: lib.rate }}></div>
                          </div>
                          <span className="text-[9px] font-bold text-[var(--text-primary)] shrink-0">{lib.rate}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* 右侧 5/12 联动指标大卡片：AI 智能接口时延雷达与可用性监控 */}
          <div className="col-span-12 lg:col-span-5 space-y-4">
            <TiltCard className="theme-card laser-chase-border p-4 shadow-soft flex flex-col justify-between min-h-[460px]">
              <div style={{ transform: 'translateZ(20px)', transformStyle: 'preserve-3d' }}>
                <h3 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 mb-3 flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <Sparkles className="size-4 text-[var(--accent-color)] animate-pulse" />
                    <span className="cyber-glitch-text cursor-pointer transition-all">AI 智能接口时延雷达与可用性</span>
                  </div>
                  <span className="text-[8.5px] font-mono text-[var(--accent-color)] bg-[var(--accent-glow)] px-1.5 py-0.5 rounded">实时监测</span>
                </h3>
                
                <div className="space-y-3.5 animate-[fadeIn_0.2s_ease-out]">
                  {/* 库基本特征 */}
                  <div>
                    <span className="text-slate-400 block text-[9px] mb-1">当前分析接口库：</span>
                    <div className="p-2 bg-[var(--bg-app)]/50 border border-[var(--border-color)] rounded-lg text-left text-[10px] font-bold text-[var(--text-primary)]">
                      {activeLib.name}
                    </div>
                  </div>

                  {/* 时延雷达波动走势 */}
                  <div className="text-left space-y-1.5">
                    <span className="text-slate-400 block text-[9px]">SLA 实时响应延迟波动走势 (Sparkline)：</span>
                    <div className="h-20 w-full cyber-matrix-grid lava-glow-aurora border border-[var(--border-color)] bg-[var(--bg-app)]/30 rounded-lg overflow-hidden relative">
                      <svg className="w-full h-full p-1" viewBox="0 0 500 100" preserveAspectRatio="none">
                        <defs>
                          <linearGradient id="apiSparklineGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="var(--accent-color)" stopOpacity="0.25" />
                            <stop offset="100%" stopColor="var(--accent-color)" stopOpacity="0.0" />
                          </linearGradient>
                          <filter id="glow-effect" x="-20%" y="-20%" width="140%" height="140%">
                            <feGaussianBlur stdDeviation="2.5" result="blur" />
                            <feMerge>
                              <feMergeNode in="blur" />
                              <feMergeNode in="SourceGraphic" />
                            </feMerge>
                          </filter>
                        </defs>
                        <line x1="0" y1="25" x2="500" y2="25" stroke="var(--border-color)" strokeWidth="0.5" strokeDasharray="3,3" />
                        <line x1="0" y1="50" x2="500" y2="50" stroke="var(--border-color)" strokeWidth="0.5" strokeDasharray="3,3" />
                        <line x1="0" y1="75" x2="500" y2="75" stroke="var(--border-color)" strokeWidth="0.5" strokeDasharray="3,3" />
                        
                        {/* 根据选中索引动态生成折线和渐变 */}
                        <path 
                          key={`fill-${selectedLibIdx}`}
                          d={`${
                            selectedLibIdx === 0 ? 'M 0 65 Q 100 20, 200 70 T 300 40 T 500 50' :
                            selectedLibIdx === 1 ? 'M 0 85 Q 120 40, 240 90 T 360 25 T 500 75' :
                            selectedLibIdx === 2 ? 'M 0 75 Q 90 15, 180 85 T 270 30 T 500 65' :
                            selectedLibIdx === 3 ? 'M 0 50 Q 80 30, 160 45 T 240 40 T 500 35' :
                            'M 0 95 Q 100 25, 200 90 T 300 55 T 500 70'
                          } L 500 100 L 0 100 Z`}
                          fill="url(#apiSparklineGrad)"
                        />
                        <path 
                          key={`line-${selectedLibIdx}`}
                          d={
                            selectedLibIdx === 0 ? 'M 0 65 Q 100 20, 200 70 T 300 40 T 500 50' :
                            selectedLibIdx === 1 ? 'M 0 85 Q 120 40, 240 90 T 360 25 T 500 75' :
                            selectedLibIdx === 2 ? 'M 0 75 Q 90 15, 180 85 T 270 30 T 500 65' :
                            selectedLibIdx === 3 ? 'M 0 50 Q 80 30, 160 45 T 240 40 T 500 35' :
                            'M 0 95 Q 100 25, 200 90 T 300 55 T 500 70'
                          }
                          fill="none"
                          stroke="var(--accent-color)"
                          strokeWidth="2.5"
                          strokeLinecap="round"
                          filter="url(#glow-effect)"
                          className="path-drawn"
                        />
                      </svg>
                      <div className="absolute top-1.5 left-2 text-[8px] font-bold text-[var(--accent-color)] bg-[var(--bg-card)]/80 border border-[var(--border-color)] px-1 py-0.2 rounded font-mono">
                        {selectedLibIdx === 0 ? 'Avg: 156ms' :
                         selectedLibIdx === 1 ? 'Avg: 210ms' :
                         selectedLibIdx === 2 ? 'Avg: 184ms' :
                         selectedLibIdx === 3 ? 'Avg: 95ms' : 'Avg: 250ms'}
                      </div>
                    </div>
                  </div>

                  {/* 激活与高危缺陷指标 */}
                  <div className="grid grid-cols-2 gap-3.5">
                    <div className="p-3 border border-[var(--border-color)] bg-[var(--bg-app)]/50 rounded-lg text-left" style={{ transform: 'translateZ(10px)' }}>
                      <span className="text-[9px] text-[var(--text-secondary)] block">测试用例数</span>
                      <span className="text-base font-bold font-mono text-[var(--text-primary)] neon-pulse-number">{activeLib.cases}</span>
                    </div>
                    <div className="p-3 border border-[var(--border-color)] bg-[var(--bg-app)]/50 rounded-lg text-left" style={{ transform: 'translateZ(10px)' }}>
                      <span className="text-[9px] text-[var(--text-secondary)] block">可用性 SLA</span>
                      <span className="text-base font-bold font-mono text-emerald-500 neon-pulse-number" style={{ '--accent-color': '#10b981', '--accent-glow': 'rgba(16,185,129,0.25)' }}>{activeLib.health}</span>
                    </div>
                  </div>

                  {/* 异常接口风险监测 */}
                  <div className="text-left space-y-2" style={{ transform: 'translateZ(15px)' }}>
                    <div className="text-[9.5px] font-bold text-[var(--text-primary)]">接口高频运行异常风险 (最近 1h)</div>
                    <div className="space-y-1.5 text-[9px] font-semibold">
                      {[
                        { method: 'POST', url: '/api/v1/auth/login/verify', fail: '15.4% 失败率', color: 'text-red-500' },
                        { method: 'GET', url: '/api/v1/checkout/gateway', fail: '8.2% 失败率', color: 'text-amber-500' }
                      ].map((item, idx) => (
                        <div key={idx} className="flex justify-between items-center p-2 border border-[var(--border-color)] bg-[var(--bg-card)] rounded-lg">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <span className="px-1 py-0.5 rounded text-[7.5px] font-bold bg-[rgba(59,130,246,0.12)] text-blue-500">{item.method}</span>
                            <span className="text-[var(--text-primary)] font-mono truncate max-w-[140px]">{item.url}</span>
                          </div>
                          <span className={`font-bold ${item.color}`}>{item.fail}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-[var(--border-color)]" style={{ transform: 'translateZ(25px)' }}>
                <button 
                  onClick={() => setViewMode('workbench')}
                  className="w-full py-2 bg-[var(--accent-color)] text-[var(--accent-text)] text-[10.5px] font-bold rounded-lg cursor-pointer text-center hover:opacity-90 transition-all shadow-[var(--accent-glow)]"
                >
                  双击或点击进入工作台进行调试
                </button>
              </div>
            </TiltCard>
          </div>
        </div>
      </div>
    );
  };

  // 渲染：接口测试调试工作台
  const renderWorkbenchMode = () => {
    const displayLibs = remoteLibs.length ? remoteLibs : apiLibs;
    const activeLib = displayLibs[selectedLibIdx] || displayLibs[0];
    const activeApi = activeLib?.rawApis?.[0];
    const selectedEnv = remoteEnvConfigs.find((item) => String(item.id) === String(selectedEnvironmentId));
    const responseConsole = {
      script_results: debugResult?.scriptResults || null,
      saved_case: savedCaseResult || debugResult?.savedCase || null,
      environment_priority: '环境变量 < 本次运行覆盖',
      variables: rowsToObject(runVarRows)
    };
    const responseText = responseTab === 'headers'
      ? safeStringify(debugResult?.headers || {})
      : responseTab === 'console'
        ? safeStringify(responseConsole)
        : responseBody;
    const mockRules = toList(remoteMocks);

    return (
      <div className="space-y-4 text-left w-full animate-[fadeIn_0.2s_ease-out]">
        <div className="flex flex-wrap justify-between items-center gap-3">
          <button
            onClick={() => setViewMode('list')}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] text-[10.5px] text-[var(--text-secondary)] hover:bg-[var(--border-color)] hover:scale-[1.02] transition-all shadow-sm cursor-pointer"
          >
            <ArrowLeft className="size-3" />
            <span>返回接口列表</span>
          </button>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => activeApi && setDebugForm((prev) => ({
                ...prev,
                method: String(activeApi.method || prev.method).toUpperCase(),
                path: activeApi.path || prev.path,
                url: ''
              }))}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)] text-[11px] font-bold text-[var(--text-primary)] cursor-pointer transition-colors"
            >
              <Save className="size-3.5 text-[var(--text-secondary)]" />
              <span>填充选中接口</span>
            </button>
            <button
              onClick={handleRunAssertions}
              disabled={isRunningAssertions}
              className="flex items-center gap-1.5 px-3.5 py-1.5 text-[11px] glow-button-neon rounded-lg disabled:opacity-70"
            >
              <Play className="size-3.5" />
              <span>{isRunningAssertions ? '断言执行中...' : '批量执行断言'}</span>
            </button>
          </div>
        </div>

        <div className="theme-card rounded-xl p-4 shadow-soft space-y-3">
          <div className="grid grid-cols-12 gap-2 items-end">
            <label className="col-span-12 sm:col-span-2 text-[10px] font-bold text-[var(--text-secondary)]">
              Method
              <select
                value={debugForm.method}
                onChange={(event) => setDebugForm((prev) => ({ ...prev, method: event.target.value }))}
                className="mt-1 w-full px-2 py-2 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30 text-[11px] text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-color)]"
              >
                {HTTP_METHODS.map((method) => <option key={method} value={method}>{method}</option>)}
              </select>
            </label>
            <label className="col-span-12 sm:col-span-4 text-[10px] font-bold text-[var(--text-secondary)]">
              Full URL
              <input
                value={debugForm.url}
                onChange={(event) => setDebugForm((prev) => ({ ...prev, url: event.target.value }))}
                placeholder="可选；填写后优先使用完整 URL"
                className="mt-1 w-full px-3 py-2 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30 text-[11px] text-[var(--text-primary)] font-mono focus:outline-none focus:border-[var(--accent-color)]"
              />
            </label>
            <label className="col-span-12 sm:col-span-3 text-[10px] font-bold text-[var(--text-secondary)]">
              Base URL
              <input
                value={debugForm.baseUrl}
                onChange={(event) => setDebugForm((prev) => ({ ...prev, baseUrl: event.target.value }))}
                className="mt-1 w-full px-3 py-2 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30 text-[11px] text-[var(--text-primary)] font-mono focus:outline-none focus:border-[var(--accent-color)]"
              />
            </label>
            <label className="col-span-12 sm:col-span-3 text-[10px] font-bold text-[var(--text-secondary)]">
              Path
              <input
                value={debugForm.path}
                onChange={(event) => setDebugForm((prev) => ({ ...prev, path: event.target.value }))}
                className="mt-1 w-full px-3 py-2 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30 text-[11px] text-[var(--text-primary)] font-mono focus:outline-none focus:border-[var(--accent-color)]"
              />
            </label>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2 text-[10px] text-[var(--text-secondary)]">
              <span className="px-2 py-1 rounded border border-[var(--border-color)] bg-[var(--bg-app)] font-mono break-all">
                {debugForm.url.trim() || joinUrl(debugForm.baseUrl, debugForm.path)}
              </span>
              <label className="flex items-center gap-1">
                <span>Expected</span>
                <input
                  value={debugForm.expectedStatus}
                  onChange={(event) => setDebugForm((prev) => ({ ...prev, expectedStatus: event.target.value }))}
                  className="w-16 px-2 py-1 rounded-md border border-[var(--border-color)] bg-[var(--bg-app)]/30 text-[10px] text-[var(--text-primary)] font-mono focus:outline-none focus:border-[var(--accent-color)]"
                />
              </label>
              <span>Env: {selectedEnv?.name || selectedEnvironmentId || '未选择'}</span>
            </div>
            <button
              onClick={() => handleSend()}
              disabled={isSending}
              className="flex items-center gap-1.5 px-4 py-2 glow-button-neon rounded-lg text-xs font-bold cursor-pointer disabled:opacity-75 transition-all"
            >
              <Send className="size-3.5" />
              <span>{isSending ? '正在运行...' : '运行 /apis/debug'}</span>
            </button>
          </div>
        </div>

        <div className="grid grid-cols-12 gap-4 items-start w-full">
          <div className="col-span-12 lg:col-span-8 space-y-4">
            <div className="theme-card rounded-xl p-4 shadow-soft">
              <div className="flex flex-wrap justify-between items-center gap-2 border-b border-[var(--border-color)] pb-2 mb-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-bold text-[var(--text-primary)]">请求报文定义 (Request)</span>
                  <button
                    onClick={handleGenerateTestData}
                    disabled={dataFactoryState.loading}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-[var(--accent-color)]/30 bg-[var(--accent-glow)] text-[var(--accent-color)] text-[9px] font-bold hover:bg-[var(--accent-color)] hover:text-white transition-colors disabled:opacity-60"
                  >
                    <Sparkles className={`size-3 ${dataFactoryState.loading ? 'animate-spin' : ''}`} />
                    <span>{dataFactoryState.loading ? '生成中...' : '生成测试数据'}</span>
                  </button>
                </div>
                <div className="p-0.5 border border-[var(--border-color)] rounded-lg flex gap-0.5 bg-[var(--bg-app)] text-[9px] font-bold">
                  {['Headers', 'Params', 'Body', 'Auth'].map((tab) => {
                    const tabId = tab.toLowerCase();
                    const isTabActive = requestTab === tabId;
                    return (
                      <button
                        key={tab}
                        onClick={() => setRequestTab(tabId)}
                        className={`px-3 py-1 rounded-md transition-all duration-200 cursor-pointer ${isTabActive ? 'bg-[var(--bg-card)] text-[var(--accent-color)] border border-[var(--border-color)]/50 shadow-sm font-extrabold' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-card)]/30'}`}
                      >
                        {tab}
                      </button>
                    );
                  })}
                </div>
              </div>

              {requestTab === 'headers' && renderKeyValueRows(debugHeaders, setDebugHeaders, {
                keyPlaceholder: 'Header',
                valuePlaceholder: 'Header value',
                addLabel: '添加 Header override'
              })}
              {requestTab === 'params' && renderKeyValueRows(debugQuery, setDebugQuery, {
                keyPlaceholder: 'Query',
                valuePlaceholder: 'Query value',
                addLabel: '添加 Query 参数'
              })}
              {requestTab === 'body' && (
                <textarea
                  value={debugForm.body}
                  onChange={(event) => setDebugForm((prev) => ({ ...prev, body: event.target.value }))}
                  className="w-full h-44 font-mono text-[10.5px] p-3 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30 focus:outline-none focus:border-[var(--accent-color)] leading-relaxed text-[var(--text-primary)] quantum-input-glow"
                />
              )}
              {requestTab === 'auth' && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <label className="text-[10px] font-bold text-[var(--text-secondary)]">
                    Environment
                    <select
                      value={selectedEnvironmentId}
                      onChange={(event) => setSelectedEnvironmentId(event.target.value)}
                      className="mt-1 w-full px-2 py-2 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30 text-[11px] text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-color)]"
                    >
                      <option value="">不使用环境</option>
                      {remoteEnvConfigs.map((env) => (
                        <option key={env.id} value={env.id}>{env.name || `Env #${env.id}`}</option>
                      ))}
                    </select>
                  </label>
                  <div className="p-3 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30 text-[10px] text-[var(--text-secondary)]">
                    <div className="font-bold text-[var(--text-primary)]">运行优先级</div>
                    <div className="mt-1 font-mono">环境变量 &lt; 本次运行覆盖</div>
                    <div className="mt-1 break-all">payload: environment_id, variables, headers_override</div>
                  </div>
                </div>
              )}
            </div>

            {renderDataFactoryPanel()}

            <div className="theme-card rounded-xl p-4 shadow-soft">
              <div className="flex flex-wrap justify-between items-center gap-2 border-b border-[var(--border-color)] pb-2 mb-3">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="text-xs font-bold text-[var(--text-primary)]">响应控制台 (Response)</span>
                  {responseBody && (
                    <div className="flex flex-wrap items-center gap-2 text-[9.5px] font-bold text-[var(--text-secondary)]">
                      <span className="text-emerald-500 bg-[rgba(16,185,129,0.12)] px-1.5 py-0.5 rounded border border-[rgba(16,185,129,0.2)]">HTTP {debugResult?.statusCode || '--'}</span>
                      <span>Latency: {debugResult?.durationMs || 0}ms</span>
                    </div>
                  )}
                </div>
                <div className="p-0.5 border border-[var(--border-color)] rounded-lg flex gap-0.5 bg-[var(--bg-app)] text-[9px] font-bold">
                  {['Body', 'Headers', 'Console'].map((tab) => {
                    const tabId = tab.toLowerCase();
                    const isTabActive = responseTab === tabId;
                    return (
                      <button
                        key={tab}
                        onClick={() => setResponseTab(tabId)}
                        className={`px-3 py-1 rounded-md transition-all duration-200 cursor-pointer ${isTabActive ? 'bg-[var(--bg-card)] text-[var(--accent-color)] border border-[var(--border-color)]/50 shadow-sm font-extrabold' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-card)]/30'}`}
                      >
                        {tab}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="mac-terminal w-full relative overflow-hidden cyber-matrix-console">
                <div className="flex items-center justify-between px-3 py-2 border-b border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)] relative z-10">
                  <div className="flex items-center gap-1.5">
                    <span className="size-2.5 rounded-full bg-[#ff5f56]" />
                    <span className="size-2.5 rounded-full bg-[#ffbd2e]" />
                    <span className="size-2.5 rounded-full bg-[#27c93f]" />
                  </div>
                  <span className="text-[9.5px] font-mono text-zinc-500 select-none">response - /apis/debug</span>
                  <div className="w-[30px]" />
                </div>

                <div className="p-4 overflow-y-auto max-h-72 font-mono text-[10.5px] leading-relaxed text-zinc-300 text-left bg-zinc-950/50 rounded-b-xl min-h-[180px] relative z-10">
                  {isSending ? (
                    <div className="h-32 flex flex-col items-center justify-center text-zinc-500 gap-2 font-sans">
                      <span className="animate-spin text-lg">↻</span>
                      <span className="text-[9.5px]">正在调用后端调试执行器...</span>
                    </div>
                  ) : responseText ? (
                    <pre className="whitespace-pre-wrap break-all">{responseText}</pre>
                  ) : (
                    <div className="h-32 flex items-center justify-center text-zinc-500 font-sans text-[10px]">
                      等待运行结果，失败时会显示后端真实错误。
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="col-span-12 lg:col-span-4 space-y-4">
            <TiltCard className="theme-card rounded-xl p-4 shadow-soft text-left space-y-3">
              <h3 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 flex items-center gap-1.5">
                <Database className="size-3.5 text-[var(--accent-color)]" />
                <span>环境变量与覆盖</span>
              </h3>
              <div className="text-[9px] text-[var(--text-secondary)] bg-[var(--bg-app)]/50 border border-[var(--border-color)] rounded-lg p-2">
                环境变量 &lt; 本次运行覆盖。运行 payload 会带 environment_id、variables 与 headers_override。
              </div>
              <div>
                <div className="text-[9.5px] font-bold text-[var(--text-primary)] mb-2">环境变量</div>
                {renderKeyValueRows(envVarRows, setEnvVarRows, {
                  keyPlaceholder: 'Env key',
                  valuePlaceholder: 'Env value',
                  addLabel: '添加环境变量'
                })}
              </div>
              <div>
                <div className="text-[9.5px] font-bold text-[var(--text-primary)] mb-2">本次运行覆盖 variables</div>
                {renderKeyValueRows(runVarRows, setRunVarRows, {
                  keyPlaceholder: '变量名',
                  valuePlaceholder: '覆盖值',
                  addLabel: '添加运行覆盖'
                })}
              </div>
            </TiltCard>

            <TiltCard className="theme-card rounded-xl p-4 shadow-soft text-left space-y-3">
              <h3 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 flex items-center gap-1.5">
                <Terminal className="size-3.5 text-[var(--accent-color)]" />
                <span>保存用例与受控脚本</span>
              </h3>
              <label className="flex items-center gap-2 text-[10px] text-[var(--text-secondary)] cursor-pointer">
                <input type="checkbox" checked={saveAsCase} onChange={(event) => setSaveAsCase(event.target.checked)} className="size-3 accent-[var(--accent-color)]" />
                <span>调试成功后传 save_as_case=true</span>
              </label>
              <button
                onClick={() => handleSend({ forceSaveAsCase: true })}
                disabled={isSending || !responseBody}
                className="w-full py-2 bg-zinc-950 hover:bg-zinc-800 text-white dark:bg-zinc-800 dark:hover:bg-zinc-700 text-[10px] font-bold rounded-lg cursor-pointer text-center flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
              >
                <Save className="size-3" />
                <span>保存当前调试为接口用例</span>
              </button>
              {(savedCaseResult || debugResult?.savedCase) && (
                <pre className="max-h-28 overflow-auto whitespace-pre-wrap break-all font-mono text-[8.5px] text-emerald-500 border border-emerald-500/20 bg-emerald-500/10 rounded-lg p-2">{safeStringify(savedCaseResult || debugResult.savedCase)}</pre>
              )}
              <div className="border-t border-[var(--border-color)] pt-3 space-y-2">
                <label className="flex items-center gap-2 text-[10px] text-[var(--text-secondary)] cursor-pointer">
                  <input type="checkbox" checked={enableScripts} onChange={(event) => setEnableScripts(event.target.checked)} className="size-3 accent-[var(--accent-color)]" />
                  <span>启用 pre/post script，后端按 allowlist DSL 受控执行</span>
                </label>
                <textarea
                  value={preScript}
                  onChange={(event) => setPreScript(event.target.value)}
                  disabled={!enableScripts}
                  className="w-full h-16 font-mono text-[9.5px] p-2 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30 focus:outline-none focus:border-[var(--accent-color)] leading-relaxed text-[var(--text-primary)] disabled:opacity-50"
                />
                <textarea
                  value={postScript}
                  onChange={(event) => setPostScript(event.target.value)}
                  disabled={!enableScripts}
                  className="w-full h-16 font-mono text-[9.5px] p-2 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30 focus:outline-none focus:border-[var(--accent-color)] leading-relaxed text-[var(--text-primary)] disabled:opacity-50"
                />
                {debugResult?.scriptResults && (
                  <pre className="max-h-24 overflow-auto whitespace-pre-wrap break-all font-mono text-[8.5px] text-[var(--text-secondary)] border border-[var(--border-color)] rounded-lg p-2">{safeStringify(debugResult.scriptResults)}</pre>
                )}
              </div>
            </TiltCard>

            <TiltCard className="theme-card rounded-xl p-4 shadow-soft text-left space-y-3">
              <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-2">
                <h3 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
                  <Cpu className="size-3.5 text-[var(--accent-color)]" />
                  <span>Mock 服务</span>
                </h3>
                <button onClick={handleLoadMocks} className="px-2 py-1 text-[9px] font-bold border border-[var(--border-color)] rounded bg-[var(--bg-card)] hover:bg-[var(--border-color)] text-[var(--text-primary)]">刷新</button>
              </div>
              <div className={`text-[9px] rounded-lg border p-2 ${mockStatus.type === 'error' ? 'border-red-500/30 bg-red-500/10 text-red-500' : 'border-[var(--border-color)] bg-[var(--bg-app)]/30 text-[var(--text-secondary)]'}`}>{mockStatus.message}</div>
              <div className="space-y-2 max-h-36 overflow-auto">
                {mockRules.length ? mockRules.map((rule, index) => {
                  const enabled = rule.is_enabled ?? rule.isEnabled ?? rule.enabled;
                  return (
                    <div key={rule.id || index} className="p-2 border border-[var(--border-color)] bg-[var(--bg-app)]/30 rounded-lg text-[9px]">
                      <div className="flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <div className="font-mono font-bold text-[var(--text-primary)] truncate">{rule.method || 'ANY'} {rule.path || rule.url || '--'}</div>
                          <div className="text-[var(--text-secondary)] truncate">status {rule.status_code || rule.status || 200}</div>
                        </div>
                        <button
                          onClick={() => handleToggleMockRule(rule)}
                          className={`px-2 py-1 rounded text-[8.5px] font-bold ${enabled ? 'bg-emerald-500/10 text-emerald-500' : 'bg-zinc-500/10 text-[var(--text-secondary)]'}`}
                        >
                          {enabled ? '启用' : '停用'}
                        </button>
                      </div>
                    </div>
                  );
                }) : (
                  <div className="text-[9px] text-[var(--text-secondary)] border border-dashed border-[var(--border-color)] rounded-lg p-3 text-center">暂无规则</div>
                )}
              </div>
              <div className="grid grid-cols-3 gap-2">
                <select
                  value={mockForm.method}
                  onChange={(event) => setMockForm((prev) => ({ ...prev, method: event.target.value }))}
                  className="px-2 py-1.5 rounded-md border border-[var(--border-color)] bg-[var(--bg-app)]/30 text-[10px] text-[var(--text-primary)]"
                >
                  {HTTP_METHODS.map((method) => <option key={method} value={method}>{method}</option>)}
                </select>
                <input
                  value={mockForm.path}
                  onChange={(event) => setMockForm((prev) => ({ ...prev, path: event.target.value }))}
                  className="col-span-2 min-w-0 px-2 py-1.5 rounded-md border border-[var(--border-color)] bg-[var(--bg-app)]/30 text-[10px] text-[var(--text-primary)] font-mono"
                />
              </div>
              <div className="grid grid-cols-[70px_minmax(0,1fr)] gap-2">
                <input
                  value={mockForm.statusCode}
                  onChange={(event) => setMockForm((prev) => ({ ...prev, statusCode: event.target.value }))}
                  className="px-2 py-1.5 rounded-md border border-[var(--border-color)] bg-[var(--bg-app)]/30 text-[10px] text-[var(--text-primary)] font-mono"
                />
                <textarea
                  value={mockForm.responseBody}
                  onChange={(event) => setMockForm((prev) => ({ ...prev, responseBody: event.target.value }))}
                  className="h-16 font-mono text-[9.5px] p-2 rounded-md border border-[var(--border-color)] bg-[var(--bg-app)]/30 text-[var(--text-primary)]"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <button onClick={handleSaveMockRule} disabled={isSavingMock} className="py-2 text-[10px] font-bold rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)] text-[var(--text-primary)] disabled:opacity-60">{isSavingMock ? '提交中...' : '新增规则'}</button>
                <button onClick={handleDispatchMockSmoke} disabled={isDispatchingMock} className="py-2 text-[10px] font-bold rounded-lg bg-zinc-950 hover:bg-zinc-800 text-white disabled:opacity-60">{isDispatchingMock ? 'Dispatch...' : 'Dispatch smoke'}</button>
              </div>
            </TiltCard>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4 text-left w-full transition-all duration-300">
      {viewMode === 'list' && renderListMode()}
      {viewMode === 'workbench' && renderWorkbenchMode()}
      {viewMode === 'env-scenario' && renderEnvScenario()}
    </div>
  );
}
