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
  Activity,
  Terminal,
  ActivityIcon
} from 'lucide-react';
import TiltCard from '../components/TiltCard';
import AnimatedNumber from '../components/AnimatedNumber';
import { apiGet, apiPost, formatDateTime, pickList } from '../lib/api';
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

  const initialBody = `{
  "raw_text": "用户需要在智能客服系统的对话窗口中输入文本内容并发送，系统检测是否有违规内容后保存入库",
  "source_type": "text",
  "options": {
    "granularity": "normal",
    "extract_rules": true
  }
}`;

  const initialResponse = `{
  "status": "success",
  "data": {
    "document_summary": "智能客服文本消息发送与合规校验模块",
    "items": [
      {
        "item_number": "REQ-00004",
        "title": "发送文本消息",
        "summary": "客服在会话中输入文本并发送，推送给用户并在窗口展示，记录到会话历史。",
        "priority": "P0"
      }
    ],
    "confidence": 0.97,
    "latency_ms": 420
  }
}`;

  const [requestBody, setRequestBody] = useState(initialBody);
  const [responseBody, setResponseBody] = useState('');

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
      return;
    }

    const [envPayload, scenarioPayload, schedulePayload] = await Promise.all([
      apiGet(`/api-test-libs/${lib.backendId}/environments`, { params: { page: 1, pageSize: 20 } }).catch(() => null),
      apiGet(`/api-test-libs/${lib.backendId}/scenarios`, { params: { page: 1, pageSize: 20 } }).catch(() => null),
      apiGet(`/api-test-libs/${lib.backendId}/schedules`, { params: { page: 1, pageSize: 20 } }).catch(() => null)
    ]);
    const envs = pickList(envPayload);
    const scenarios = pickList(scenarioPayload);
    const schedules = pickList(schedulePayload);
    const endpointById = new Map((lib.rawApis || []).map((api) => [String(api.id), api]));
    const caseById = new Map((lib.rawCases || []).map((item) => [String(item.id), item]));
    const primaryScenario = scenarios[0];
    const steps = (primaryScenario?.nodes || []).map((node, index) => {
      const testCase = caseById.get(String(node.case_id));
      const endpoint = endpointById.get(String(testCase?.endpoint_id));
      return {
        id: node.id || `Step ${index + 1}`,
        name: testCase?.name || node.name || `Backend case #${node.case_id || index + 1}`,
        method: endpoint?.method || 'CASE',
        url: endpoint?.path || `case:${node.case_id || index + 1}`,
        desc: primaryScenario?.description || 'Backend scenario node',
        extracts: Object.keys(node.extract || {}).join(', ') || 'backend runner',
        delay: `${testCase?.expected_status || 200}`
      };
    });

    setRemoteEnvConfigs(envs);
    setRemoteScenarioSteps(steps);
    setRemoteSchedules(schedules);
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

  const handleSend = async () => {
    setIsSending(true);
    setResponseBody('');
    try {
      let parsedBody = {};
      try {
        parsedBody = requestBody ? JSON.parse(requestBody) : {};
      } catch {
        parsedBody = { raw_text: requestBody };
      }
      const result = await apiPost('/apis/debug', {
        method: 'GET',
        url: 'http://127.0.0.1:8000/api/v2/projects',
        query: { page: '1', pageSize: '1' },
        body: parsedBody,
        expected_status: 200,
        assertions: [{ type: 'status_code', expected: 200 }]
      }, { timeoutMs: 10000 });
      setResponseBody(JSON.stringify(result, null, 2));
      showToast(`接口调试完成，HTTP ${result.status_code || result.status || 'ok'}，耗时 ${result.duration_ms || 0}ms。`, 'success');
    } catch (error) {
      setResponseBody(JSON.stringify({ error: error?.message || '接口调试失败' }, null, 2));
      showToast(error?.message || '接口调试失败，请检查后端服务。', 'error');
    } finally {
      setIsSending(false);
    }
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
      const executions = result.executions || [];
      const passed = executions.filter((item) => item.status === 'passed').length;
      setResponseBody(JSON.stringify(result, null, 2));
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
      let environment = remoteEnvConfigs.find((item) => item.is_active || item.isActive) || remoteEnvConfigs[0];
      if (!environment?.id) {
        environment = await apiPost(`/api-test-libs/${activeLib.backendId}/environments`, {
          name: 'Local Backend',
          base_url: 'http://127.0.0.1:8000',
          variables: { project_id: projectContext?.id },
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
          order: index + 1
        })),
        edges: caseIds.slice(1).map((caseId, index) => ({
          source: `case-${caseIds[index]}`,
          target: `case-${caseId}`
        })),
        data_mappings: {}
      });

      const scenarioResult = await apiPost(`/api-scenarios/${scenario.id}/execute`, {
        environment_id: environment.id,
        base_url: environment.base_url || 'http://127.0.0.1:8000',
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
      setResponseBody(JSON.stringify({ scenarioResult, scheduleResult }, null, 2));
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
      ? remoteEnvConfigs.flatMap((env) => Object.entries(env.variables || {}).map(([key, value]) => ({
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
    return (
      <div className="space-y-4 text-left w-full animate-[fadeIn_0.2s_ease-out]">
        {/* 返回 */}
        <div className="flex justify-between items-center">
          <button 
            onClick={() => setViewMode('list')}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] text-[10.5px] text-[var(--text-secondary)] hover:bg-[var(--border-color)] hover:scale-[1.02] transition-all shadow-sm cursor-pointer"
          >
            <ArrowLeft className="size-3" />
            <span>返回接口列表</span>
          </button>
          
          <div className="flex items-center gap-2">
            <button 
              onClick={() => window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '接口配置保存成功！', type: 'success' } }))}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)] text-[11px] font-bold text-[var(--text-primary)] cursor-pointer transition-colors"
            >
              <Save className="size-3.5 text-[var(--text-secondary)]" />
              <span>保存配置</span>
            </button>
            <button 
              onClick={() => window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: 'AI 已智能为您生成 5 条边界断言用例！', type: 'success' } }))}
              className="px-3.5 py-1.5 text-[11px] glow-button-neon rounded-lg"
            >
              <Sparkles className="size-3.5 text-white inline mr-1 animate-pulse" />
              AI 智能生成用例
            </button>
          </div>
        </div>

        {/* 接口 URL 与方法 */}
        <div className="theme-card rounded-xl p-4 shadow-soft flex items-center justify-between">
          <div className="flex items-center gap-2 w-full">
            <span className="px-3 py-1.5 bg-[rgba(59,130,246,0.12)] text-blue-500 border border-blue-500/20 font-bold rounded-lg text-xs shrink-0">POST</span>
            <div className="flex-1 flex items-center gap-2 px-3 py-2 border border-[var(--border-color)] bg-[var(--bg-app)]/30 rounded-lg text-xs font-mono font-bold text-[var(--text-primary)]">
              <span>{activeApi?.path || '/api/v2/projects'}</span>
            </div>
            <button 
              onClick={handleSend}
              disabled={isSending}
              className="flex items-center gap-1.5 px-4 py-2 glow-button-neon rounded-lg text-xs font-bold cursor-pointer disabled:opacity-75 transition-all"
            >
              <Send className="size-3.5" />
              <span>{isSending ? '正在运行...' : '运行'}</span>
            </button>
          </div>
        </div>

        {/* 8:4 选中联动双面板 */}
        <div className="grid grid-cols-12 gap-4 items-start w-full">
          {/* 左侧 8/12: Request + Response 控制台 */}
          <div className="col-span-12 lg:col-span-8 space-y-4">
            {/* Request */}
            <div className="theme-card rounded-xl p-4 shadow-soft">
              <div className="flex justify-between items-center border-b border-[var(--border-color)] pb-2 mb-3">
                <span className="text-xs font-bold text-[var(--text-primary)]">请求报文定义 (Request)</span>
                <div className="p-0.5 border border-[var(--border-color)] rounded-lg flex gap-0.5 bg-[var(--bg-app)] text-[9px] font-bold">
                  {['Headers', 'Params', 'Body', 'Auth'].map((tab) => {
                    const isTabActive = requestTab === tab.toLowerCase();
                    return (
                      <button 
                        key={tab}
                        onClick={() => setRequestTab(tab.toLowerCase())}
                        className={`px-3 py-1 rounded-md transition-all duration-200 cursor-pointer ${
                          isTabActive 
                            ? 'bg-[var(--bg-card)] text-[var(--accent-color)] border border-[var(--border-color)]/50 shadow-sm font-extrabold' 
                            : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-card)]/30'
                        }`}
                      >
                        {tab}
                      </button>
                    );
                  })}
                </div>
              </div>

              {requestTab === 'body' ? (
                <textarea 
                  value={requestBody}
                  onChange={(e) => setRequestBody(e.target.value)}
                  className="w-full h-36 font-mono text-[10.5px] p-3 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30 focus:outline-none focus:border-[var(--accent-color)] leading-relaxed text-[var(--text-primary)] quantum-input-glow"
                />
              ) : (
                <div className="h-36 flex items-center justify-center text-[10px] text-[var(--text-secondary)] border border-[var(--border-color)] bg-[var(--bg-app)]/30 rounded-lg">
                  当前选项卡已在系统环境变量中统一鉴权，此字段在此方案中保持静态。
                </div>
              )}
            </div>

            {/* Response - macOS Terminal 风格 */}
            <div className="theme-card rounded-xl p-4 shadow-soft">
              <div className="flex justify-between items-center border-b border-[var(--border-color)] pb-2 mb-3">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-bold text-[var(--text-primary)]">响应控制台 (Response)</span>
                  {responseBody && (
                    <div className="flex items-center gap-2.5 text-[9.5px] font-bold text-[var(--text-secondary)]">
                      <span className="text-emerald-500 bg-[rgba(16,185,129,0.12)] px-1.5 py-0.5 rounded border border-[rgba(16,185,129,0.2)]">200 OK</span>
                      <span>Latency: 420ms</span>
                      <span>Size: 1.2 KB</span>
                    </div>
                  )}
                </div>
                <div className="p-0.5 border border-[var(--border-color)] rounded-lg flex gap-0.5 bg-[var(--bg-app)] text-[9px] font-bold">
                  {['Body', 'Headers', 'Console'].map((tab) => {
                    const isTabActive = responseTab === tab.toLowerCase();
                    return (
                      <button 
                        key={tab}
                        onClick={() => setResponseTab(tab.toLowerCase())}
                        className={`px-3 py-1 rounded-md transition-all duration-200 cursor-pointer ${
                          isTabActive 
                            ? 'bg-[var(--bg-card)] text-[var(--accent-color)] border border-[var(--border-color)]/50 shadow-sm font-extrabold' 
                            : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-card)]/30'
                        }`}
                      >
                        {tab}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* macOS 终端外观包装 */}
              <div className="mac-terminal w-full relative overflow-hidden cyber-matrix-console">
                <div className="flex items-center justify-between px-3 py-2 border-b border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)] relative z-10">
                  <div className="flex items-center gap-1.5">
                    <span className="size-2.5 rounded-full bg-[#ff5f56]" />
                    <span className="size-2.5 rounded-full bg-[#ffbd2e]" />
                    <span className="size-2.5 rounded-full bg-[#27c93f]" />
                  </div>
                  <span className="text-[9.5px] font-mono text-zinc-500 select-none">bash - response - 420ms</span>
                  <div className="w-[30px]" />
                </div>
                
                <div className="p-4 overflow-y-auto max-h-56 font-mono text-[10.5px] leading-relaxed text-zinc-300 text-left bg-zinc-950/50 rounded-b-xl min-h-[140px] relative z-10">
                  {isSending ? (
                    <div className="h-28 flex flex-col items-center justify-center text-zinc-500 gap-2 font-sans">
                      <span className="animate-spin text-lg">↻</span>
                      <span className="text-[9.5px]">正在向网关发起动态 TLS 校验握手并拉取报文数据...</span>
                    </div>
                  ) : responseBody ? (
                    <pre className="whitespace-pre-wrap">{responseBody}</pre>
                  ) : (
                    <div className="h-28 flex items-center justify-center text-zinc-500 font-sans text-[10px]">
                      等待连接。请点击上方“运行”按钮触发 HTTP 请求流。
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* 右侧 4/12: AI 智能断言生成与雷达监控 (3D 倾斜眩光卡) */}
          <div className="col-span-12 lg:col-span-4 space-y-4">
            <TiltCard className="p-4 shadow-soft space-y-4 animate-[slideUpFade_0.4s_ease-out] ai-laser-healing-grid">
              <div className="relative z-10" style={{ transform: 'translateZ(15px)', transformStyle: 'preserve-3d' }}>
                <h3 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 flex items-center gap-1.5">
                  <Sparkles className="size-4 text-[var(--accent-color)] animate-pulse" />
                  <span>AI 智能断言校验网格</span>
                </h3>
                <span className="text-[9px] text-[var(--text-secondary)] block mt-1.5">机器学习特征工程：自动根据响应结构体推荐最完备的逻辑断言</span>
              </div>

              <div className="space-y-3 relative z-10" style={{ transform: 'translateZ(10px)' }}>
                {[
                  { id: 'as1', assert: 'Response Status == 200', desc: 'SLA 合规性：确保服务器应答 200', checked: true },
                  { id: 'as2', assert: 'Response.data contains "items"', desc: '数据完整性：校验返回主体含有效项', checked: true },
                  { id: 'as3', assert: 'items[0].priority == "P0"', desc: '核心属性校验：解析出的首位需求必须是 P0', checked: true },
                  { id: 'as4', assert: 'Response latency < 1500ms', desc: '性能阈值哨兵：确保响应在 1.5s 以内', checked: true }
                ].map((as) => (
                  <div key={as.id} className="p-2.5 border border-[var(--border-color)] bg-[var(--bg-app)]/30 rounded-lg text-left hover:border-[var(--accent-color)] transition-all">
                    <label className="flex items-start gap-2 cursor-pointer">
                      <input type="checkbox" defaultChecked={as.checked} className="rounded size-3.5 accent-[var(--accent-color)] mt-0.5 shrink-0" />
                      <div>
                        <span className="font-mono text-[9px] font-bold text-[var(--text-primary)] block">{as.assert}</span>
                        <span className="text-[8px] text-[var(--text-secondary)] mt-0.5 block leading-tight">{as.desc}</span>
                      </div>
                    </label>
                  </div>
                ))}
              </div>

              <div className="border-t border-[var(--border-color)] pt-3.5 relative z-10" style={{ transform: 'translateZ(20px)' }}>
                <button 
                  onClick={handleRunAssertions}
                  disabled={isRunningAssertions}
                  className="w-full py-2 bg-zinc-950 hover:bg-zinc-800 text-white dark:bg-zinc-800 dark:hover:bg-zinc-700 text-[10px] font-bold rounded-lg cursor-pointer text-center flex items-center justify-center gap-1.5 transition-colors"
                >
                  <Play className="size-3 fill-current" />
                  <span>{isRunningAssertions ? '执行中...' : '批量执行物理断言'}</span>
                </button>
              </div>
            </TiltCard>

            {/* 响应时间 Sparkline 卡片 */}
            <TiltCard className="theme-card rounded-xl p-4 shadow-soft text-left">
              <h4 className="text-[10.5px] font-bold text-[var(--text-primary)] mb-2 flex items-center gap-1.5">
                <Activity className="size-3.5 text-[var(--accent-color)]" />
                <span>实时网关响应时延监控</span>
              </h4>
              <div className="h-16 w-full relative">
                {/* 简易 SVG 时延折线图，带渐变 */}
                <svg className="w-full h-full" viewBox="0 0 100 30" preserveAspectRatio="none">
                  <defs>
                    <linearGradient id="area-grad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--accent-color)" stopOpacity="0.25" />
                      <stop offset="100%" stopColor="var(--accent-color)" stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  {/* 面积渐变 */}
                  <path 
                    d="M 0 30 L 0 20 L 15 15 L 30 25 L 45 10 L 60 18 L 75 8 L 90 22 L 100 12 L 100 30 Z" 
                    fill="url(#area-grad)" 
                  />
                  {/* 折线 */}
                  <path 
                    d="M 0 20 L 15 15 L 30 25 L 45 10 L 60 18 L 75 8 L 90 22 L 100 12" 
                    fill="none" 
                    stroke="var(--accent-color)" 
                    strokeWidth="1.2" 
                    className="path-drawn"
                  />
                  {/* 斑点 */}
                  <circle cx="100" cy="12" r="1.5" fill="var(--accent-color)" className="animate-ping" />
                </svg>
              </div>
              <div className="flex justify-between text-[8px] text-[var(--text-secondary)] mt-1.5">
                <span>9次前: 220ms</span>
                <span>当前: 120ms</span>
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
