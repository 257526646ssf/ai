import React from 'react';
import { Bell, HelpCircle, ChevronDown, Menu } from 'lucide-react';
import { useProjectContext } from '../lib/projectContext';
import { apiGet } from '../lib/api';

const readStatusField = (source, keys = []) => {
  if (!source || typeof source !== 'object') return undefined;

  for (const key of keys) {
    const value = source[key];
    if (value !== undefined && value !== null && value !== '') return value;
  }

  return undefined;
};

const normalizeLlmStatus = ({ status, data, error }) => {
  if (status === 'loading') {
    return {
      label: '检测中',
      modelText: '读取后端状态',
      title: '正在读取后端 LLM 状态',
      dotClass: 'bg-blue-500',
      textClass: 'text-blue-600 dark:text-blue-400',
      pulse: true
    };
  }

  if (status === 'error') {
    return {
      label: '状态异常',
      modelText: error || '点击查看配置',
      title: error || 'LLM 状态接口不可用',
      dotClass: 'bg-red-500',
      textClass: 'text-red-600 dark:text-red-400',
      pulse: false
    };
  }

  const config = readStatusField(data, ['config', 'default_config', 'llm_config']) || {};
  const rawStatus = String(readStatusField(data, ['status', 'state', 'runtime_status']) || '').toLowerCase();
  const modelText =
    readStatusField(data, ['model', 'model_name', 'active_model']) ||
    readStatusField(config, ['model_name', 'model', 'name']) ||
    '模型待配置';
  const configured =
    data?.configured ??
    data?.has_config ??
    Boolean(readStatusField(data, ['model', 'model_name']) || Object.keys(config).length);
  const enabled = data?.enabled ?? data?.is_enabled ?? config?.is_enabled;
  const connected = Boolean(data?.connected) || ['ok', 'ready', 'online', 'connected'].includes(rawStatus);
  const reason = readStatusField(data, ['reason', 'error', 'message', 'detail']);

  if (enabled === false || rawStatus.includes('disabled')) {
    return {
      label: '未启用',
      modelText,
      title: reason || 'LLM 配置存在但未启用',
      dotClass: 'bg-amber-500',
      textClass: 'text-amber-600 dark:text-amber-400',
      pulse: false
    };
  }

  if (!configured || rawStatus.includes('missing') || rawStatus.includes('unconfigured') || rawStatus.includes('no_config')) {
    return {
      label: '未配置',
      modelText: '前往配置模型',
      title: '尚未配置可用 LLM，点击进入 LLM 配置',
      dotClass: 'bg-amber-500',
      textClass: 'text-amber-600 dark:text-amber-400',
      pulse: false
    };
  }

  if (connected) {
    return {
      label: '已就绪',
      modelText,
      title: `当前模型：${modelText}`,
      dotClass: 'bg-emerald-500',
      textClass: 'text-emerald-600 dark:text-emerald-400',
      pulse: true
    };
  }

  return {
    label: rawStatus.includes('fallback') ? '降级中' : '不可用',
    modelText: reason || modelText,
    title: reason || 'LLM 运行时当前不可用',
    dotClass: rawStatus.includes('fallback') ? 'bg-amber-500' : 'bg-red-500',
    textClass: rawStatus.includes('fallback') ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400',
    pulse: false
  };
};

const themeOptions = [
  { id: 'basic', label: '基础', title: '基础雅致' },
  { id: 'dark', label: '夜色', title: '科技夜空' },
  { id: 'editorial', label: '编辑', title: '编辑感亮色' },
  { id: 'cyber-glass', label: '玻璃', title: '未来玻璃' },
  { id: 'brutalist', label: '工业', title: '工业粗野' },
  { id: 'ibm', label: 'IBM', title: 'IBM 企业' },
  { id: 'airtable', label: 'Airtable', title: 'Airtable 工作流' },
  { id: 'clickhouse', label: 'ClickHouse', title: 'ClickHouse 深色' },
  { id: 'notion', label: 'Notion', title: 'Notion 极简' },
  { id: 'linear', label: 'Linear', title: 'Linear 深色' }
];

const tabTitles = {
  dashboard: 'Dashboard',
  requirements: '需求库',
  testcases: '测试用例',
  execution: '用例执行',
  apitesting: '接口测试',
  automation: '自动化中心',
  performance: '性能测试',
  reports: '测试报告',
  llmconfig: 'LLM 配置',
  settings: '系统设置'
};

const toolbarGroupClass =
  'flex min-w-0 items-center gap-2 rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)] px-3 py-2 shadow-sm';

export default function Topbar({ activeTab, theme, setTheme, setActiveTab, onOpenNavigation }) {
  const {
    projects,
    selectedProjectId,
    setSelectedProjectId,
    selectedProject,
    loading: projectLoading,
    error: projectError
  } = useProjectContext();
  const [llmState, setLlmState] = React.useState({ status: 'loading', data: null, error: '' });

  React.useEffect(() => {
    const controller = new AbortController();
    setLlmState((prev) => ({ ...prev, status: 'loading', error: '' }));

    apiGet('/system/llm-status', { signal: controller.signal, timeoutMs: 8000 })
      .then((data) => {
        setLlmState({ status: 'ready', data: data || {}, error: '' });
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setLlmState({
          status: 'error',
          data: null,
          error: error?.message || 'LLM 状态读取失败'
        });
      });

    return () => {
      controller.abort();
    };
  }, []);

  const llmStatus = normalizeLlmStatus(llmState);
  const currentTitle = tabTitles[activeTab] || 'Dashboard';
  const currentTheme = themeOptions.find((item) => item.id === theme) || themeOptions[0];
  const openLlmConfig = () => setActiveTab?.('llmconfig');

  return (
    <header className="sticky top-0 z-20 border-b border-[var(--border-color)] bg-[var(--bg-card)] px-4 py-3 backdrop-blur">
      <div className="flex min-w-0 flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <button
            type="button"
            onClick={onOpenNavigation}
            className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)] text-[var(--text-secondary)] shadow-sm transition-colors hover:bg-[var(--bg-app)] hover:text-[var(--text-primary)] lg:hidden"
            aria-label="打开导航"
          >
            <Menu className="size-4" />
          </button>

          <div className="min-w-0">
          <div className="mb-1 flex min-w-0 items-center gap-2 text-xs font-medium text-[var(--text-secondary)]">
            <span className="truncate">{activeTab === 'dashboard' ? '平台首页' : currentTitle}</span>
            <span className="text-[var(--border-color)]">/</span>
            <span className="truncate">{selectedProject?.name || selectedProject?.code || '当前项目'}</span>
          </div>
          <div className="truncate text-lg font-semibold text-[var(--text-primary)]">{currentTitle}</div>
          </div>
        </div>

        <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
          <label className={[toolbarGroupClass, 'max-w-full sm:max-w-[240px]'].join(' ')}>
            <span className="shrink-0 text-xs font-medium text-[var(--text-secondary)]">项目</span>
            <select
              value={selectedProjectId ?? ''}
              onChange={(event) => setSelectedProjectId(event.target.value)}
              disabled={projectLoading || projects.length === 0}
              title={projectError || selectedProject?.name || '全局项目'}
              className="min-w-0 flex-1 bg-transparent text-sm font-medium text-[var(--text-primary)] outline-none disabled:cursor-not-allowed"
            >
              {projects.length ? (
                projects.map((project) => (
                  <option key={project.id} value={String(project.id)}>
                    {project.name || project.code || `Project #${project.id}`}
                  </option>
                ))
              ) : (
                <option value="">{projectLoading ? '加载中' : '暂无项目'}</option>
              )}
            </select>
          </label>

          <label className={[toolbarGroupClass, 'max-w-full sm:max-w-[176px]'].join(' ')}>
            <span className="shrink-0 text-xs font-medium text-[var(--text-secondary)]">主题</span>
            <select
              value={theme}
              onChange={(event) => setTheme(event.target.value)}
              title={currentTheme.title}
              className="min-w-0 flex-1 bg-transparent text-sm font-medium text-[var(--text-primary)] outline-none"
            >
              {themeOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <button
            type="button"
            onClick={openLlmConfig}
            title={llmStatus.title}
            className={[toolbarGroupClass, 'max-w-full cursor-pointer sm:max-w-[260px]'].join(' ')}
          >
            <span className="relative flex size-2.5 shrink-0">
              {llmStatus.pulse && (
                <span className={`absolute inline-flex h-full w-full rounded-full ${llmStatus.dotClass} opacity-70 animate-ping`} />
              )}
              <span className={`relative inline-flex size-2.5 rounded-full ${llmStatus.dotClass}`} />
            </span>
            <div className="min-w-0 flex-1 text-left">
              <div className={`truncate text-xs font-semibold ${llmStatus.textClass}`}>LLM {llmStatus.label}</div>
              <div className="truncate text-xs text-[var(--text-secondary)]">{llmStatus.modelText}</div>
            </div>
            <ChevronDown className="size-4 shrink-0 text-[var(--text-secondary)]" />
          </button>

          <div className="flex items-center gap-1">
            <button
              type="button"
              className="flex size-10 items-center justify-center rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)] text-[var(--text-secondary)] shadow-sm transition-colors hover:bg-[var(--bg-app)] hover:text-[var(--text-primary)]"
              aria-label="消息通知"
            >
              <span className="relative inline-flex">
                <Bell className="size-4" />
                <span className="absolute -right-0.5 -top-0.5 size-1.5 rounded-full bg-red-500" />
              </span>
            </button>
            <button
              type="button"
              className="flex size-10 items-center justify-center rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)] text-[var(--text-secondary)] shadow-sm transition-colors hover:bg-[var(--bg-app)] hover:text-[var(--text-primary)]"
              aria-label="帮助中心"
            >
              <HelpCircle className="size-4" />
            </button>
          </div>

          <div className="flex min-w-0 items-center gap-3 rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)] px-3 py-2 shadow-sm">
            <img
              src="/avatar_zhang.png"
              alt="张明"
              className="size-9 rounded-full border border-[var(--border-color)] object-cover"
              onError={(event) => {
                event.currentTarget.src = 'https://ui-avatars.com/api/?name=%E5%BC%A0%E6%98%8E&background=2563eb&color=fff';
              }}
            />
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-[var(--text-primary)]">张明</div>
              <div className="truncate text-xs text-[var(--text-secondary)]">测试负责人</div>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
