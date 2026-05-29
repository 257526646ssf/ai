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
import { apiGet, apiPost, downloadTextFile, formatDateTime, pickList } from '../lib/api';
import { useProjectContext } from '../lib/projectContext';

const PROJECT_SCAN_LIMIT = 80;

const showToast = (message, type = 'success') => {
  window.dispatchEvent(new CustomEvent('show-toast', { detail: { message, type } }));
};

const mapBackendPerfPlan = (plan, latestResult = null) => {
  const assets = plan.target_assets_json || plan.targetAssetsJson || {};
  const schema = plan.plan_schema || plan.planSchema || {};
  const summary = latestResult?.summary_data || latestResult?.summaryData || {};
  const vus = Number(assets.vus || schema?.scenarios?.[0]?.users || 100);
  const status = plan.status === 'executed' ? '已完成' : plan.status === 'scripted' ? '已生成脚本' : plan.status === 'planned' ? '已规划' : '草稿';
  const statusColor = plan.status === 'executed' ? 'bg-emerald-500' : plan.status === 'scripted' ? 'bg-blue-500' : 'bg-slate-400';
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
    latestResult
  };
};

export default function Performance() {
  const { selectedProject } = useProjectContext();
  const [viewMode, setViewMode] = useState('list'); // 'list', 'report', 'plan-create', 'script-gen', 'history-compare'
  const [isRunning, setIsRunning] = useState(false);
  const [pressureMode, setPressureMode] = useState(0);
  const [planName, setPlanName] = useState('智能客服高并发接口压力测试');
  const [selectedPlanIndex, setSelectedPlanIndex] = useState(0);
  const [projectContext, setProjectContext] = useState(null);
  const [remotePlans, setRemotePlans] = useState([]);
  const [perfStatus, setPerfStatus] = useState({ loading: true, usingBackend: false, message: '正在同步后端性能方案...' });
  const [perfExecution, setPerfExecution] = useState(null);
  const [generatedScriptContent, setGeneratedScriptContent] = useState('');
  const [useJMeterRunner, setUseJMeterRunner] = useState(false);
  const [generateHtmlReport, setGenerateHtmlReport] = useState(true);
  const [targetApis, setTargetApis] = useState([
    { method: 'POST', url: '/api/v1/auth/login', weight: 30 },
    { method: 'POST', url: '/api/v1/session/create', weight: 40 },
    { method: 'POST', url: '/api/v1/message/send', weight: 30 }
  ]);
  const compareData = [
    { build: 'Build #3', vus: 1000, avgRt: '245ms', rt95: '410ms', maxTps: '3,850/s', errRate: '0.08%', cpu: '78%', mem: '64%', status: '正常' },
    { build: 'Build #2', vus: 800, avgRt: '184ms', rt95: '320ms', maxTps: '2,450/s', errRate: '0.02%', cpu: '54%', mem: '58%', status: '优秀' },
    { build: 'Build #1', vus: 500, avgRt: '156ms', rt95: '240ms', maxTps: '1,800/s', errRate: '0.00%', cpu: '42%', mem: '45%', status: '优秀' }
  ];

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
  const displayStats = remotePlans.length ? [
    { label: '方案总数', val: String(remotePlans.length), change: projectContext?.name || '后端项目', icon: Gauge, color: 'text-blue-500 bg-blue-500/10' },
    { label: '总执行次数', val: String(remotePlans.filter(item => item.latestResult).length), change: '由 PerfResult 汇总', icon: Clock, color: 'text-purple-500 bg-purple-500/10' },
    { label: '并发上限 (VUs)', val: String(Math.max(...remotePlans.map(item => Number(item.vus || 0)), 0)), change: '后端方案目标并发', icon: Play, color: 'text-indigo-500 bg-indigo-500/10' },
    { label: '健康方案数', val: String(remotePlans.filter(item => item.status === '已完成').length), change: '已执行方案', hasChart: true }
  ] : perfStats;

  const loadPerformanceData = React.useCallback(async ({ silent = false } = {}) => {
    if (!silent) setPerfStatus(prev => ({ ...prev, loading: true }));
    try {
      const projects = selectedProject?.id
        ? [selectedProject]
        : pickList(await apiGet('/projects', { params: { page: 1, pageSize: PROJECT_SCAN_LIMIT } }));
      if (!projects.length) {
        setPerfStatus({ loading: false, usingBackend: false, message: '后端暂无项目，列表使用内置样例。' });
        return;
      }

      let selected = { project: projects[0], plans: [] };
      for (const project of projects) {
        const payload = await apiGet(`/projects/${project.id}/perf-plans`, { params: { page: 1, pageSize: 20 } }).catch(() => null);
        const items = pickList(payload);
        if (items.length > 0) {
          selected = { project, plans: items };
          break;
        }
      }

      const enrichedPlans = await Promise.all(selected.plans.map(async (plan) => {
        const resultPayload = await apiGet(`/perf-plans/${plan.id}/results`).catch(() => null);
        const latestResult = pickList(resultPayload)[0] || null;
        return mapBackendPerfPlan(plan, latestResult);
      }));

      setProjectContext(selected.project);
      setRemotePlans(enrichedPlans);
      setSelectedPlanIndex(0);
      setPerfStatus({
        loading: false,
        usingBackend: enrichedPlans.length > 0,
        message: enrichedPlans.length > 0
          ? `已同步后端项目「${selected.project.name}」的性能方案。`
          : `后端项目「${selected.project.name}」暂无性能方案，可新建后执行。`
      });
    } catch (error) {
      setPerfStatus({ loading: false, usingBackend: false, message: `性能方案加载失败：${error.message || error}` });
      showToast(`性能方案加载失败：${error.message || error}`, 'error');
    }
  }, [selectedProject]);

  React.useEffect(() => {
    loadPerformanceData();
  }, [loadPerformanceData]);

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
    { label: '并发 VUs', val: '500', sub: '最高 VUs: 800' },
    { label: '平均响应时间 (RT)', val: '184ms', sub: '95% RT: 320ms' },
    { label: '吞吐量 (TPS)', val: '2,450 /s', sub: '峰值: 3,600 /s' },
    { label: '异常率', val: '0.02%', sub: '共产生 18 个报错', err: true }
  ];

  const transactionDetails = [
    { name: 'POST /api/v1/payment/check', count: '145,210', rt: '184ms', rt95: '320ms', tps: '2,450 /s', err: '18 (0.01%)', status: '优秀', statusColor: 'text-emerald-500 bg-emerald-50' },
    { name: 'GET /api/v1/payment/gateway', count: '98,420', rt: '110ms', rt95: '180ms', tps: '1,600 /s', err: '0 (0.00%)', status: '优秀', statusColor: 'text-emerald-500 bg-emerald-50' }
  ];

  const createPerfPlanFromForm = async () => {
    if (!projectContext?.id) {
      throw new Error('后端暂无可关联的项目，请先在项目管理中创建项目。');
    }
    const vus = pressureMode === 0 ? 100 : pressureMode === 1 ? 500 : 1000;
    return apiPost(`/projects/${projectContext.id}/perf-plans`, {
      name: planName || 'Performance Plan',
      description: '由性能测试页面创建的后端压测方案',
      target_assets: {
        apis: targetApis,
        vus,
        protocol: 'HTTP / JSON',
        ref: 'REQ-PERF',
        owner: '系统'
      },
      target_doc: targetApis.map(item => `${item.method} ${item.url}`).join('\n'),
      status: 'draft'
    });
  };

  const ensureBackendPerfPlan = async (plan = activePlan) => {
    if (plan?.backendId) return plan;
    const created = await createPerfPlanFromForm();
    return mapBackendPerfPlan(created);
  };

  const handleRunPerfPlan = async (plan = activePlan) => {
    if (isRunning) return;
    setIsRunning(true);
    try {
      const target = await ensureBackendPerfPlan(plan);
      const planResult = await apiPost(`/perf-plans/${target.backendId}/generate-plan`, {});
      const scriptResult = await apiPost(`/perf-plans/${target.backendId}/generate-script`, {});
      setGeneratedScriptContent(scriptResult?.script?.content || '');
      const executionPayload = await apiPost(`/perf-plans/${target.backendId}/execute`, {
        mode: useJMeterRunner ? 'real' : 'placeholder',
        use_jmeter: useJMeterRunner,
        generate_html_report: generateHtmlReport,
        virtual_users: target.vus,
        target_apis: targetApis
      });
      await apiPost(`/perf-plans/${target.backendId}/generate-report`, {}).catch(() => null);
      const result = executionPayload.result || executionPayload;
      setPerfExecution({ ...result, plan: planResult?.plan || target.raw, planId: target.backendId });
      setSelectedPlanIndex(Math.max(0, displayPlans.findIndex(item => item.backendId === target.backendId)));
      setViewMode('report');
      await loadPerformanceData({ silent: true });
      showToast(`性能方案「${target.name}」已完成后端压测执行。`);
    } catch (error) {
      showToast(`性能压测执行失败：${error.message || error}`, 'error');
    } finally {
      setIsRunning(false);
    }
  };

  const handleGeneratePerfScript = async () => {
    if (isRunning) return;
    setIsRunning(true);
    try {
      const target = await ensureBackendPerfPlan(activePlan);
      await apiPost(`/perf-plans/${target.backendId}/generate-plan`, {});
      const scriptResult = await apiPost(`/perf-plans/${target.backendId}/generate-script`, {});
      setGeneratedScriptContent(scriptResult?.script?.content || '');
      await loadPerformanceData({ silent: true });
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

  const reportResult = perfExecution || activePlan?.latestResult;
  const reportSummary = reportResult?.summary_data || reportResult?.summaryData || {};
  const reportMetricsView = reportResult ? [
    { label: '并发 VUs', val: String(activePlan?.vus || 100), sub: `执行状态: ${reportResult.status || 'completed'}` },
    { label: '平均响应时间 (RT)', val: `${reportSummary.avg_ms ?? '--'}ms`, sub: `95% RT: ${reportSummary.p95_ms ?? '--'}ms` },
    { label: '吞吐量 (TPS)', val: reportSummary.tps ? `${reportSummary.tps} /s` : '占位执行', sub: `持续时长: ${reportResult.duration || '--'}s` },
    { label: '异常率', val: `${Number(reportSummary.error_rate || 0) * 100}%`, sub: `错误明细: ${(reportResult.error_details || reportResult.errorDetails || []).length} 条`, err: Number(reportSummary.error_rate || 0) > 0 }
  ] : reportMetrics;

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
              <span className="text-[var(--text-primary)]">新建性能测试方案</span>
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
                  defaultValue={500}
                  className="premium-input w-full px-3 py-2 text-[11px]"
                />
              </div>
              <div className="space-y-1.5">
                <label className="block text-[var(--text-primary)]">持续时间</label>
                <select className="premium-input w-full px-3 py-2 text-[11px]">
                  <option value="5m">5 分钟</option>
                  <option value="10m">10 分钟</option>
                  <option value="30m">30 分钟</option>
                  <option value="1h">1 小时</option>
                </select>
              </div>
            </div>
            <div className="space-y-1.5">
              <label className="block text-[var(--text-primary)]">加压模式</label>
              <div className="grid grid-cols-3 gap-2">
                {['阶梯加压 (Ramping)', '恒定并发 (Constant)', '骤增压测 (Spike)'].map((mode, i) => (
                  <label 
                    key={i} 
                    onClick={() => setPressureMode(i)}
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
          </div>

          {/* 右侧：接口与权重 */}
          <div className="col-span-6 theme-card rounded-xl p-4 shadow-soft flex flex-col justify-between">
            <div>
              <h3 className="text-xs font-bold border-b border-[var(--border-color)] pb-2 mb-3 flex justify-between items-center text-slate-800">
                <span>压测接口列表与权重配置</span>
                <span className="text-[9px] text-slate-400 font-normal">总权重应等于 100%</span>
              </h3>
              <div className="space-y-2.5 max-h-[220px] overflow-y-auto pr-1">
                {targetApis.map((api, idx) => (
                  <div key={idx} className="flex gap-2 items-center">
                    <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold ${api.method === 'POST' ? 'text-blue-600 bg-blue-50' : 'text-emerald-600 bg-emerald-50'}`}>{api.method}</span>
                    <input 
                      type="text" 
                      value={api.url} 
                      onChange={(e) => {
                        const newApis = [...targetApis];
                        newApis[idx].url = e.target.value;
                        setTargetApis(newApis);
                      }}
                      className="premium-input flex-1 px-2 py-1.5 font-mono text-[9px]"
                    />
                    <div className="flex items-center gap-1 shrink-0">
                      <input 
                        type="number" 
                        value={api.weight} 
                        onChange={(e) => {
                          const newApis = [...targetApis];
                          newApis[idx].weight = Number(e.target.value);
                          setTargetApis(newApis);
                        }}
                        className="premium-input w-10 px-1 py-1 text-[10px] text-center font-bold"
                      />
                      <span className="text-[9px] text-slate-400 font-bold">%</span>
                    </div>
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
              <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-emerald-500"></span> Build #1 (500 VUs)</span>
              <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-blue-500"></span> Build #2 (800 VUs)</span>
              <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-purple-500"></span> Build #3 (1000 VUs)</span>
            </div>
          </h3>
          <div className="h-44 w-full relative mt-2">
            <svg className="w-full h-full" viewBox="0 0 1000 160" preserveAspectRatio="none">
              {/* 网格线 */}
              <line x1="0" y1="20" x2="1000" y2="20" stroke="var(--border-color)" strokeWidth="1" strokeDasharray="5,5" />
              <line x1="0" y1="80" x2="1000" y2="80" stroke="var(--border-color)" strokeWidth="1" strokeDasharray="5,5" />
              <line x1="0" y1="140" x2="1000" y2="140" stroke="var(--border-color)" strokeWidth="1" strokeDasharray="5,5" />
              {/* Build #1 TPS (浅绿) */}
              <path d="M 50 140 Q 250 80, 500 100 T 950 120" fill="none" stroke="var(--accent-color)" strokeWidth="2.2" opacity="0.5" strokeDasharray="4,2" className="path-drawn" />
              {/* Build #2 TPS (青色) */}
              <path d="M 50 140 Q 250 60, 500 70 T 950 90" fill="none" stroke="#06b6d4" strokeWidth="2.2" opacity="0.75" className="path-drawn" />
              {/* Build #3 TPS (紫色) */}
              <path d="M 50 140 Q 250 30, 500 50 T 950 130" fill="none" stroke="#d946ef" strokeWidth="2.8" className="path-drawn" />
            </svg>
            <div className="absolute top-2 left-2 text-[8px] text-slate-400 bg-white/80 dark:bg-slate-900/80 px-1 py-0.5 rounded border border-slate-100 font-bold">拐点分析点 (VUs=920, RT=320ms)</div>
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
                  {compareData.map((row, idx) => (
                    <tr key={idx} className="hover:bg-slate-50/30">
                      <td className="py-2.5 px-1 font-bold text-slate-800 font-mono">{row.build}</td>
                      <td className="py-2.5 px-1 text-center font-bold text-slate-700">{row.vus}</td>
                      <td className="py-2.5 px-1 text-center">{row.avgRt}</td>
                      <td className="py-2.5 px-1 text-center font-semibold">{row.rt95}</td>
                      <td className="py-2.5 px-1 text-center text-indigo-600 font-bold">{row.maxTps}</td>
                      <td className="py-2.5 px-1 text-center text-red-500 font-bold">{row.errRate}</td>
                      <td className="py-2.5 px-1 text-center font-mono">{row.cpu}</td>
                      <td className="py-2.5 px-1 text-center font-mono">{row.mem}</td>
                      <td className="py-2.5 px-1 text-center">
                        <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold ${
                          row.status === '优秀' ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'
                        }`}>
                          {row.status}
                        </span>
                      </td>
                    </tr>
                  ))}
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
              <p className="text-[8px] text-slate-400 mb-3">经多轮交叉曲线比对提炼：</p>
              
              <div className="space-y-3 text-[9px] font-semibold text-slate-600 font-sans">
                <div className="p-2 border border-purple-100 bg-purple-50/20 rounded-lg">
                  <span className="font-bold text-purple-700 block">性能拐点标定</span>
                  <p className="text-slate-400 text-[8px] leading-relaxed mt-0.5">
                    系统在并发达到 920 VUs 以上时，由于接口 <code className="bg-black/5 px-0.5 py-0.2 rounded text-[7.5px]">/payment/check</code> 耗时陡升，TPS 曲线发生明显崩塌（由 3850 下跌至 1200）。建议针对支付锁加装非阻塞异步队列。
                  </p>
                </div>

                <div className="p-2 border border-slate-100 bg-slate-50/30 rounded-lg">
                  <span className="font-bold text-slate-700 block">硬件利用率评估</span>
                  <p className="text-slate-400 text-[8px] leading-relaxed mt-0.5">
                    Build #3 中 CPU 峰值达到 78%（主要是内存垃圾回收机制 GC 占用较高），内存达到 64%。推荐在 Node 启动命令中调整内存堆栈上限。
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
                <span>运行队列 (0)</span>
              </button>
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
                onClick={() => setViewMode('plan-create')}
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
                      <AnimatedNumber value={85} />%
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
                                  <span className="hover:underline cursor-pointer" onClick={() => {
                                    setPerfExecution(plan.latestResult ? { ...plan.latestResult, planId: plan.backendId } : null);
                                    setViewMode('report');
                                  }}>报告</span>
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
                        {selectedPlanIndex === 3 ? '未开始' : selectedPlanIndex === 1 ? 'Avg: 210ms' : 'Avg: 170ms'}
                      </span>
                    </div>
                    <div className="h-20 w-full border border-[var(--border-color)] bg-[var(--bg-app)] rounded-xl overflow-hidden relative flex items-center justify-center">
                      {selectedPlanIndex === 3 ? (
                        <span className="text-[8.5px] text-[var(--text-secondary)] opacity-60">方案排队中，等待调度注入器...</span>
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
                            d={`${
                              selectedPlanIndex === 0 
                                ? 'M 10 120 C 80 40, 160 140, 240 70 S 320 30, 400 90' 
                                : selectedPlanIndex === 1 
                                  ? 'M 10 90 C 70 120, 130 30, 200 110 S 310 130, 400 40' 
                                  : 'M 10 100 C 60 70, 120 120, 180 50 S 300 20, 400 80'
                            } L 400 120 L 10 120 Z`}
                            fill="url(#sparklineGrad)"
                          />
                          {/* 波动曲线 */}
                          <path 
                            key={`path-${selectedPlanIndex}`}
                            d={
                              selectedPlanIndex === 0 
                                ? 'M 10 120 C 80 40, 160 140, 240 70 S 320 30, 400 90' 
                                : selectedPlanIndex === 1 
                                  ? 'M 10 90 C 70 120, 130 30, 200 110 S 310 130, 400 40' 
                                  : 'M 10 100 C 60 70, 120 120, 180 50 S 300 20, 400 80'
                            } 
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
                    onClick={() => setViewMode('report')}
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
              <button className="px-3 py-1.5 rounded-lg border border-red-500/30 hover:bg-red-500/10 text-red-500 text-[11px] font-bold cursor-pointer transition-colors bg-[var(--bg-card)]">
                停止执行
              </button>
            </div>
          </div>

          <div className="theme-card rounded-xl p-4 shadow-soft">
            <h2 className="text-sm font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2">{activePlan?.name || '性能压测报告'}</h2>
            
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

                    {/* VUs 黄色区域/柱状 */}
                    <path d="M 40 140 L 90 120 L 140 100 L 190 80 L 240 60 L 290 60 L 340 60 L 390 80 L 440 100 L 500 140" fill="var(--accent-glow)" stroke="var(--accent-color)" strokeWidth="1" opacity="0.2" />

                    {/* 响应时间 RT (主题色曲线) */}
                    <path d="M 40 130 L 90 125 L 140 115 L 190 98 L 240 85 L 290 70 L 340 65 L 390 72 L 440 90 L 500 120" fill="none" stroke="var(--accent-color)" strokeWidth="2.2" strokeLinecap="round" className="path-drawn" />
                    
                    {/* 吞吐量 TPS (绿色曲线) */}
                    <path d="M 40 138 L 90 118 L 140 95 L 190 78 L 240 50 L 290 48 L 340 45 L 390 70 L 440 95 L 500 135" fill="none" stroke="#10b981" strokeWidth="1.8" strokeLinecap="round" strokeDasharray="4,2" className="path-drawn" />

                    {/* 坐标 */}
                    <text x="30" y="24" textAnchor="end" className="text-[8px] fill-slate-400 font-medium">800 VUs</text>
                    <text x="30" y="64" textAnchor="end" className="text-[8px] fill-slate-400 font-medium">400 VUs</text>
                    <text x="30" y="104" textAnchor="end" className="text-[8px] fill-slate-400 font-medium">200 VUs</text>

                    <text x="510" y="24" textAnchor="start" className="text-[8px] fill-blue-500 font-medium">320ms</text>
                    <text x="510" y="64" textAnchor="start" className="text-[8px] fill-blue-500 font-medium">160ms</text>
                  </svg>
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
                    {transactionDetails.map((row, idx) => (
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
                  <span style={{ transform: 'translateZ(10px)' }} className="text-[9px] text-[var(--text-secondary)]/85 block mb-3">大模型对当前压测指标的瓶颈根因诊断</span>

                  <div className="space-y-3 text-[9.5px] leading-relaxed text-[var(--text-secondary)] font-semibold" style={{ transformStyle: 'preserve-3d', transform: 'translateZ(20px)' }}>
                    <div className="p-2 border border-red-500/20 bg-red-500/10 rounded-lg transition-transform duration-200" style={{ transform: 'translateZ(25px)' }}>
                      <div className="flex items-center gap-1 text-red-600 font-bold">
                        <AlertTriangle className="size-3.5" />
                        <span>数据库连接池占满 (VUs &gt; 450)</span>
                      </div>
                      <p className="text-[8px] text-[var(--text-secondary)]/80 mt-1">当虚拟并发用户达到 450 以上时，接口响应时间出现陡增。由于读写事务未分离，数据库连接池占用率达到 100% 引发队列积压。</p>
                    </div>

                    <div className="p-2 border border-amber-500/20 bg-amber-500/10 rounded-lg transition-transform duration-200" style={{ transform: 'translateZ(25px)' }}>
                      <div className="flex items-center gap-1 text-amber-600 font-bold">
                        <AlertTriangle className="size-3.5" />
                        <span>缓存穿透风险</span>
                      </div>
                      <p className="text-[8px] text-[var(--text-secondary)]/80 mt-1">在大流量并发请求下，部分非常规消息的返回结果未命中 Redis，直接穿透至数据库，造成数据库 CPU 占用率达 85%。</p>
                    </div>
                  </div>
                </div>

                <div className="border-t border-[var(--border-color)] pt-4 space-y-2 mt-4">
                  <div className="text-[10px] font-bold text-[var(--text-primary)]">AI 调优建议</div>
                  <div className="space-y-1.5 text-[8.5px] font-semibold text-slate-500">
                    <div>1. 扩容数据库连接池最大参数由 100 增至 300。</div>
                    <div>2. 启用缓存防空命中机制，设置空值缓存超时 60s。</div>
                    <div>3. 针对高频支付接口启用 Redis 哨兵集群读写分离。</div>
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
