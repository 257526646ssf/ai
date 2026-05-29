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
  Check,
  ExternalLink,
  XCircle,
  AlertTriangle,
  Activity
} from 'lucide-react';
import TiltCard from '../components/TiltCard';
import AnimatedNumber from '../components/AnimatedNumber';
import { apiGet, apiPost, downloadBase64File, formatDateTime, pickList } from '../lib/api';
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
  const extra = project.extra_config || project.extraConfig || {};
  const caseCount = Number(extra.case_count || extra.caseCount || 0);
  const buildCount = Number(extra.build_count || extra.buildCount || project.id || 0);
  const successRate = extra.success_rate || extra.successRate || (caseCount ? '100.0%' : '待执行');
  return {
    backendId: project.id,
    name: project.name || 'Automation Project',
    desc: extra.description || project.type || '后端自动化项目',
    stack: frameworkName(project.framework, project.language),
    framework: project.framework || 'pytest',
    language: project.language || 'python',
    cases: caseCount,
    rate: successRate,
    build: buildCount,
    time: formatDateTime(project.updated_at || project.created_at),
    owner: extra.owner || '系统',
    raw: project
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
  const [projStack, setProjStack] = useState('playwright');
  const [projLang, setProjLang] = useState('js');

  const [selectedFile, setSelectedFile] = useState('tests/auth/login.spec.js');

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
        description: source.desc || '由前端自动化中心创建',
        owner: '系统',
        case_count: 0,
        build_count: 0,
        success_rate: '待执行'
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

  const handleRunAutomation = async (project = activeProj) => {
    if (isRunningAutomation) return;
    setIsRunningAutomation(true);
    try {
      const target = await ensureBackendAutoProject(project);
      setCliLogs([
        `[RUN] POST /auto-projects/${target.backendId}/generate-framework`,
        `[RUN] POST /auto-projects/${target.backendId}/generate-cases`,
        `[RUN] POST /auto-projects/${target.backendId}/execute`
      ]);
      await apiPost(`/auto-projects/${target.backendId}/generate-framework`, {});
      await apiPost(`/auto-projects/${target.backendId}/generate-cases`, {});
      const requestedMode = autoRunnerMode === 'playwright' && !String(target.stack || '').toLowerCase().includes('playwright')
        ? 'auto'
        : autoRunnerMode;
      const playwrightStatus = runtimeDeps?.auto_runner?.playwright;
      if (requestedMode === 'playwright' && playwrightStatus && !playwrightStatus.available) {
        showToast('Playwright runner 依赖未就绪：未检测到 Node.js/npx，请先安装依赖或切换为占位 runner。', 'error');
        return;
      }
      const execution = await apiPost(`/auto-projects/${target.backendId}/execute`, { mode: requestedMode, timeout_ms: 10000 });
      setAutoExecution(execution);
      setViewMode('run-result');
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
      await apiPost(`/auto-projects/${created.id}/generate-framework`, {});
      await apiPost(`/auto-projects/${created.id}/generate-cases`, {});
      await loadAutomationData({ silent: true });
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

  const fileTree = [
    { name: 'tests/', isFolder: true, children: [
      { name: 'auth/', isFolder: true, children: [
        { name: 'login.spec.js', isFolder: false, status: 'pass' },
        { name: 'register.spec.js', isFolder: false, status: 'pass' }
      ]},
      { name: 'checkout/', isFolder: true, children: [
        { name: 'cart.spec.js', isFolder: false, status: 'fail' },
        { name: 'payment.spec.js', isFolder: false, status: 'pass' }
      ]},
      { name: 'profile.spec.js', isFolder: false, status: 'pass' }
    ]}
  ];

  const buildHistory = [
    { id: 'Build #84', time: '今天 10:25', trigger: 'Git Push', status: '失败', statusColor: 'text-red-500 bg-red-50 border-red-100', duration: '1m 24s' },
    { id: 'Build #83', time: '昨天 18:40', trigger: '定时任务', status: '成功', statusColor: 'text-emerald-500 bg-emerald-50 border-emerald-100', duration: '1m 18s' },
    { id: 'Build #82', time: '2025-05-18 10:15', trigger: '手动触发', status: '成功', statusColor: 'text-emerald-500 bg-emerald-50 border-emerald-100', duration: '1m 20s' },
    { id: 'Build #81', time: '2025-05-17 14:12', trigger: 'Git Push', status: '成功', statusColor: 'text-emerald-500 bg-emerald-50 border-emerald-100', duration: '1m 19s' }
  ];

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

        {/* 双栏布局 */}
        <div className="grid grid-cols-12 gap-4">
          {/* 左侧：脚本文件目录树 */}
          <div className="col-span-4 theme-card rounded-xl p-4 shadow-soft">
            <h3 className="text-xs font-bold mb-3 border-b border-[var(--border-color)] pb-2">自动化测试脚本目录树</h3>
            <div className="space-y-2 font-mono text-[10px]">
              {fileTree.map((node, i) => (
                <div key={i} className="space-y-1">
                  <div className="flex items-center gap-1.5 text-slate-700 font-bold">
                    <Folder className="size-3.5 text-amber-500" />
                    <span>{node.name}</span>
                  </div>
                  <div className="pl-4 space-y-1 border-l border-slate-100/50">
                    {node.children.map((child, j) => (
                      <div key={j} className="space-y-1">
                        {child.isFolder ? (
                          <>
                            <div className="flex items-center gap-1.5 text-slate-600 font-bold mt-1">
                              <Folder className="size-3.5 text-amber-400" />
                              <span>{child.name}</span>
                            </div>
                            <div className="pl-4 space-y-1 border-l border-slate-100/50">
                              {child.children.map((subChild, k) => (
                                <div 
                                  key={k} 
                                  onClick={() => setSelectedFile(`tests/${child.name}${subChild.name}`)}
                                  className={`flex items-center justify-between p-1.5 rounded cursor-pointer transition-colors ${
                                    selectedFile === `tests/${child.name}${subChild.name}` ? 'bg-indigo-50/50 text-indigo-700 font-bold' : 'hover:bg-slate-50'
                                  }`}
                                >
                                  <div className="flex items-center gap-1.5">
                                    <FileText className="size-3.5 text-slate-400" />
                                    <span>{subChild.name}</span>
                                  </div>
                                  <span className={`size-1.5 rounded-full ${subChild.status === 'pass' ? 'bg-emerald-500' : 'bg-red-500 animate-pulse'}`}></span>
                                </div>
                              ))}
                            </div>
                          </>
                        ) : (
                          <div 
                            onClick={() => setSelectedFile(`tests/${child.name}`)}
                            className={`flex items-center justify-between p-1.5 rounded cursor-pointer transition-colors ${
                              selectedFile === `tests/${child.name}` ? 'bg-indigo-50/50 text-indigo-700 font-bold' : 'hover:bg-slate-50'
                            }`}
                          >
                            <div className="flex items-center gap-1.5">
                              <FileText className="size-3.5 text-slate-400" />
                              <span>{child.name}</span>
                            </div>
                            <span className={`size-1.5 rounded-full ${child.status === 'pass' ? 'bg-emerald-500' : 'bg-red-500 animate-pulse'}`}></span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 右侧：统计图表与构建历史 */}
          <div className="col-span-8 space-y-4">
            {/* 折线走势 */}
            <div className="theme-card rounded-xl p-4 shadow-soft">
              <h3 className="text-xs font-bold mb-3">当前脚本: <span className="font-mono" style={{ color: 'var(--accent-color)' }}>{selectedFile}</span> 执行成功率波形图</h3>
              <div className="h-24 w-full relative">
                <svg className="w-full h-full" viewBox="0 0 500 80" preserveAspectRatio="none">
                  <path d="M 10 70 Q 100 10, 200 40 T 400 20 T 490 10" fill="none" stroke="var(--accent-color)" strokeWidth="2" strokeLinecap="round" className="path-drawn" />
                  <path d="M 10 70 Q 100 10, 200 40 T 400 20 T 490 10 L 490 80 L 10 80 Z" fill="url(#grad_proj)" opacity="0.1" />
                  <defs>
                    <linearGradient id="grad_proj" x1="0%" y1="0%" x2="0%" y2="100%">
                      <stop offset="0%" stopColor="var(--accent-color)" />
                      <stop offset="100%" stopColor="var(--accent-color)" stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  <circle cx="10" cy="70" r="3" fill="var(--accent-color)" />
                  <circle cx="100" cy="25" r="3" fill="var(--accent-color)" />
                  <circle cx="200" cy="40" r="3" fill="var(--accent-color)" />
                  <circle cx="300" cy="27" r="3" fill="var(--accent-color)" />
                  <circle cx="400" cy="20" r="3" fill="var(--accent-color)" />
                  <circle cx="490" cy="10" r="3" fill="var(--accent-color)" />
                </svg>
              </div>
              <div className="flex justify-between text-[8px] text-slate-400 mt-1.5 font-mono">
                <span>05-15</span>
                <span>05-16</span>
                <span>05-17</span>
                <span>05-18</span>
                <span>05-19</span>
                <span>今天 10:25</span>
              </div>
            </div>

            {/* 构建历史表格 */}
            <div className="theme-card rounded-xl p-4 shadow-soft">
              <h3 className="text-xs font-bold mb-3 border-b border-[var(--border-color)] pb-2 flex justify-between items-center">
                <span>流水线构建历史记录</span>
                <span className="text-[8px] text-slate-400 font-normal">默认显示近4次</span>
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-[10px] text-left border-collapse">
                  <thead>
                    <tr className="text-slate-400 font-bold border-b border-slate-50">
                      <th className="py-2 px-1">构建编号</th>
                      <th className="py-2 px-1">触发时间</th>
                      <th className="py-2 px-1">触发类型</th>
                      <th className="py-2 px-1 text-center">构建状态</th>
                      <th className="py-2 px-1">运行时长</th>
                      <th className="py-2 px-1 text-center">日志详情</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50/50 text-slate-600 font-medium">
                    {buildHistory.map((b) => (
                      <tr key={b.id} className="hover:bg-slate-50/30 transition-colors">
                        <td className="py-2.5 px-1 font-bold text-slate-800 font-mono">{b.id}</td>
                        <td className="py-2.5 px-1 text-slate-500">{b.time}</td>
                        <td className="py-2.5 px-1 text-slate-600">{b.trigger}</td>
                        <td className="py-2.5 px-1 text-center">
                          <span className={`px-1.5 py-0.5 rounded border text-[8px] font-bold ${b.statusColor}`}>
                            {b.status}
                          </span>
                        </td>
                        <td className="py-2.5 px-1 font-mono text-slate-400">{b.duration}</td>
                        <td className="py-2.5 px-1 text-center">
                          <button 
                            onClick={() => setViewMode('run-result')}
                            className="px-1.5 py-0.5 border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[var(--accent-color)] text-[8px] rounded font-bold cursor-pointer transition-colors"
                          >
                            控制台日志
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderRunResult = () => {
    const summary = autoExecution?.summary || { total: activeProj.cases || 24, passed: 23, failed: 1, errors: 0 };
    const isSuccess = !autoExecution || ['completed', 'passed', 'success'].includes(String(autoExecution.status || '').toLowerCase());
    const durationText = autoExecution?.duration_ms ? `${Math.max(1, Math.round(autoExecution.duration_ms / 1000))}s` : '1m 24s';
    const logLines = autoExecution?.log_excerpt ? String(autoExecution.log_excerpt).split('\n').filter(Boolean) : [];
    const runnerMode = autoExecution?.artifacts?.runner?.mode || autoExecution?.artifacts?.runner?.name || 'placeholder';
    const artifactEvidence = autoExecution?.artifacts?.evidence || [];
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
              <span className="text-[var(--text-primary)]">构建执行结果 {autoExecution?.id ? `(Execution #${autoExecution.id})` : '(Build #84)'}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
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
            <div className={`text-base font-bold mt-1 flex items-center gap-1 ${isSuccess ? 'text-emerald-500' : 'text-red-500'}`}>
              {isSuccess ? <CheckCircle className="size-4 shrink-0" /> : <XCircle className="size-4 shrink-0" />}
              <span>{isSuccess ? '执行完成' : '执行失败'}</span>
            </div>
          </div>
          <div className="theme-card rounded-xl p-4 shadow-soft">
            <span className="text-[10px] text-slate-400 font-semibold">通过情况统计</span>
            <div className="text-base font-bold mt-1 text-slate-700">通过: {summary.passed || 0} | 失败: {summary.failed || 0} | 错误: {summary.errors || 0}</div>
          </div>
        </div>

        <div className="theme-card rounded-xl p-4 shadow-soft flex items-center justify-between">
          <div>
            <div className="text-[10px] text-slate-400 font-semibold">Runner 模式</div>
            <div className="text-sm font-bold text-slate-800 mt-1">{runnerMode}</div>
          </div>
          <div className="flex-1 ml-6">
            <div className="text-[10px] text-slate-400 font-semibold mb-2">Artifacts</div>
            <div className="flex flex-wrap gap-2">
              {artifactEvidence.length ? artifactEvidence.slice(0, 6).map((item, idx) => (
                <span key={`${item.kind}-${idx}`} className="px-2 py-1 rounded border border-[var(--border-color)] bg-[var(--bg-app)] text-[9px] font-mono text-[var(--text-primary)]">
                  {item.kind}:{item.relative_path || item.source || idx + 1}
                </span>
              )) : (
                <span className="text-[10px] text-slate-400">暂无 runner artifacts</span>
              )}
            </div>
          </div>
        </div>

        {/* 核心区：高保真终端控制台 & 失败步骤诊断 */}
        <div className="grid grid-cols-12 gap-4">
          {/* 左侧：高拟真终端控制台 */}
          <div className="col-span-7 mac-terminal p-4 flex flex-col font-mono text-[9px] text-left relative overflow-hidden cyber-matrix-console bg-[#0d0208]">
            <div className="flex justify-between items-center border-b border-white/10 pb-2 mb-3 shrink-0 relative z-10">
              <div className="flex items-center gap-2">
                <Terminal className="size-4 text-[#8be9fd]" />
                <span className="font-bold text-[#8be9fd]">Playwright Test Log Console</span>
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
                <>
                  <p className="text-slate-500">[10:25:01] INFO  Initializing playwright runner on host "node-executor-04"...</p>
                  <p className="text-slate-500">[10:25:03] INFO  Scanning 24 files under /workspace/tests...</p>
                  <p className="text-[#50fa7b]">[10:25:04] SUCCESS  tests/auth/login.spec.js passed (3.4s) | 12 cases</p>
                  <p className="text-[#ff5555] font-bold">[10:25:18] ERROR  tests/checkout/cart.spec.js failed (8.2s) | 1 case failed</p>
                  <p className="text-[#8be9fd]">[10:25:21] INFO  Step snapshot generated. Saving stack trace info...</p>
                  <p className="text-slate-500">[10:25:25] INFO  Playwright test run complete. 23 passed, 1 failed.</p>
                </>
              )}
            </div>
          </div>

          {/* 右侧：用例失败诊断 & AI 自愈分析 */}
          <div className="col-span-5 space-y-4">
            {/* 失败截图看板 (带毛玻璃模糊遮罩) */}
            <div className="theme-card rounded-xl p-4 shadow-soft text-left relative overflow-hidden">
              <h3 className="text-xs font-bold mb-2">测试失败截图证据</h3>
              <div className="relative border border-slate-100 rounded-lg overflow-hidden bg-slate-100 h-28 flex items-center justify-center">
                {/* 模拟页面背景 */}
                <div className="absolute inset-0 bg-[#e2e8f0]/40 flex flex-col justify-between p-3 scale-95 select-none opacity-40">
                  <div className="h-4 bg-slate-300 w-1/4 rounded"></div>
                  <div className="space-y-1">
                    <div className="h-2 bg-slate-300 w-full rounded"></div>
                    <div className="h-2 bg-slate-300 w-5/6 rounded"></div>
                  </div>
                  <div className="h-8 bg-blue-600 w-1/3 rounded self-end flex items-center justify-center text-[8px] text-white">确认订单</div>
                </div>

                {/* 毛玻璃遮罩 */}
                <div className="absolute inset-0 backdrop-blur-[2.5px] bg-slate-900/40 flex flex-col items-center justify-center text-white">
                  <AlertTriangle className="size-8 text-[#ff5555] drop-shadow-md animate-bounce mb-1" />
                  <span className="text-[10px] font-bold drop-shadow">运行时定位超时异常发生点</span>
                  <span className="text-[8px] opacity-75 mt-0.5 font-mono">Snapshot: error_step_14.png</span>
                </div>
              </div>
            </div>

            {/* AI 自愈建议 */}
            <div className="p-4 border border-purple-100 bg-purple-50/20 rounded-xl space-y-2.5 text-left ai-laser-healing-grid">
              <div className="flex items-center gap-1.5 text-purple-700 font-bold relative z-10">
                <Sparkles className="size-4 animate-pulse text-purple-600" />
                <span className="text-xs">AI 自动化自愈诊断</span>
              </div>
              <div className="space-y-1.5 text-[9.5px] leading-relaxed text-slate-600 font-semibold font-sans relative z-10">
                <p>
                  <strong>原因诊断</strong>：元素选择器 <code className="bg-black/5 dark:bg-white/10 px-1 py-0.5 rounded font-mono text-[8px]">button.submit-order</code> 未能在超时时间 5000ms 内成功绘制。原因是系统结算接口发生了约 4.2 秒的偶发性抖动网络阻塞。
                </p>
                <p className="text-purple-600 font-bold">
                  <strong>自愈建议</strong>：将点击前的等待延迟自愈改写为显式等待，或者改用更健壮的文案匹配定位器：
                </p>
                <div className="bg-purple-950 text-[#f8f8f2] p-2 rounded-lg font-mono text-[8px] leading-normal font-bold">
                  {`// 替换旧定位器并重试\\nawait page.locator('text=确认订单').click({ timeout: 10000 });`}
                </div>
              </div>
              <div className="flex justify-between items-center text-[8px] text-purple-400 pt-2 border-t border-purple-100/50 relative z-10">
                <span>智能诊断置信度: 95%</span>
                <span className="underline cursor-pointer">反馈偏差</span>
              </div>
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
                            <div>最近构建: <span className="text-[var(--text-secondary)] font-mono">{proj.time.split(' ')[0]}</span></div>
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
                        <span className="px-1.5 py-0.5 bg-[var(--accent-color)] text-[var(--accent-text)] text-[8px] font-extrabold rounded uppercase">{activeProj.stack.split(' / ')[1] || activeProj.stack}</span>
                      </div>
                    </div>

                    {/* 动态文件骨架树 */}
                    <div className="space-y-1 text-left">
                      <span className="text-slate-400 block text-[9px] mb-1">AI 推荐的工程目录架构：</span>
                      <div className="p-3 border border-[var(--border-color)] bg-[var(--bg-app)]/30 rounded-lg text-slate-500 space-y-1">
                        {activeProj.stack.toLowerCase().includes('playwright') && (
                          <>
                            <div className="flex items-center gap-1"><Folder className="size-3 text-amber-500" /> tests/</div>
                            <div className="pl-3.5 flex items-center gap-1 text-emerald-500 font-bold"><FileText className="size-3 text-slate-400" /> login.spec.ts <span className="opacity-50 font-normal text-[8px]">(AI 生成)</span></div>
                            <div className="pl-3.5 flex items-center gap-1 text-emerald-500 font-bold"><FileText className="size-3 text-slate-400" /> payment.spec.ts <span className="opacity-50 font-normal text-[8px]">(AI 生成)</span></div>
                            <div className="flex items-center gap-1 text-cyan-500 font-bold"><FileText className="size-3" /> playwright.config.ts</div>
                          </>
                        )}
                        {activeProj.stack.toLowerCase().includes('appium') && (
                          <>
                            <div className="flex items-center gap-1"><Folder className="size-3 text-amber-500" /> tests/specs/</div>
                            <div className="pl-3.5 flex items-center gap-1 text-emerald-500 font-bold"><FileText className="size-3 text-slate-400" /> mobile_login.spec.js <span className="opacity-50 font-normal text-[8px]">(AI 生成)</span></div>
                            <div className="pl-3.5 flex items-center gap-1 text-emerald-500 font-bold"><FileText className="size-3 text-slate-400" /> gesture.spec.js <span className="opacity-50 font-normal text-[8px]">(AI 生成)</span></div>
                            <div className="flex items-center gap-1 text-cyan-500 font-bold"><FileText className="size-3" /> wdio.conf.js</div>
                          </>
                        )}
                        {activeProj.stack.toLowerCase().includes('pytest') && (
                          <>
                            <div className="flex items-center gap-1"><Folder className="size-3 text-amber-500" /> tests/api/</div>
                            <div className="pl-3.5 flex items-center gap-1 text-emerald-500 font-bold"><FileText className="size-3 text-slate-400" /> test_users.py <span className="opacity-50 font-normal text-[8px]">(AI 生成)</span></div>
                            <div className="pl-3.5 flex items-center gap-1 text-emerald-500 font-bold"><FileText className="size-3 text-slate-400" /> test_order.py <span className="opacity-50 font-normal text-[8px]">(AI 生成)</span></div>
                            <div className="flex items-center gap-1 text-cyan-500 font-bold"><FileText className="size-3" /> pytest.ini</div>
                          </>
                        )}
                        {activeProj.stack.toLowerCase().includes('supertest') && (
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
                          点击下方「完成」按钮，系统将在后台自动拉取 Git 仓库并执行脚手架注入。
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
