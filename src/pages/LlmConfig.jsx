import React, { useState, useEffect, useRef } from 'react';
import { 
  Sparkles, 
  Save, 
  CheckCircle, 
  ChevronDown, 
  Terminal, 
  AlertCircle, 
  RefreshCw, 
  Plus, 
  Trash2, 
  Globe, 
  ShieldCheck, 
  Activity, 
  Zap, 
  Eye, 
  EyeOff,
  Sliders,
  Database,
  ArrowUpRight
} from 'lucide-react';
import TiltCard from '../components/TiltCard';
import AnimatedNumber from '../components/AnimatedNumber';
import PromptTemplatePanel from '../components/PromptTemplatePanel';
import { apiGet, apiPost, apiRequest, pickList } from '../lib/api';

const HIDDEN_KEY_LABEL = 'env:AITEST_LLM_API_KEY';
const DEFAULT_MODELS = [
  { id: 'gpt-4o', name: 'gpt-4o-2024-08-06', provider: 'OpenAI / Azure LLM Proxy', baseUrl: 'https://api.openai.com/v1', apiKey: HIDDEN_KEY_LABEL, apiKeyRef: 'AITEST_LLM_API_KEY', temp: 0.7, tokens: 4096, latency: 184, rate: '99.9%', status: 'online', isDefault: true },
  { id: 'claude-3-5', name: 'claude-3-5-sonnet', provider: 'Claude Anthropic', baseUrl: 'https://api.anthropic.com/v1', apiKey: HIDDEN_KEY_LABEL, apiKeyRef: 'AITEST_LLM_API_KEY', temp: 0.5, tokens: 8192, latency: 210, rate: '99.8%', status: 'online', isDefault: false },
  { id: 'deepseek-coder', name: 'deepseek-coder', provider: 'DeepSeek API', baseUrl: 'https://api.deepseek.com/v1', apiKey: HIDDEN_KEY_LABEL, apiKeyRef: 'AITEST_LLM_API_KEY', temp: 0.2, tokens: 4096, latency: 340, rate: '99.1%', status: 'online', isDefault: false },
  { id: 'local-llama', name: 'local-llama-3', provider: 'Custom Local LLM', baseUrl: 'http://localhost:11434/v1', apiKey: HIDDEN_KEY_LABEL, apiKeyRef: 'AITEST_LLM_API_KEY', temp: 0.8, tokens: 2048, latency: 0, rate: '0.0%', status: 'offline', isDefault: false }
];

const showToast = (message, type = 'success') => {
  window.dispatchEvent(new CustomEvent('show-toast', { detail: { message, type } }));
};

const mapBackendModel = (config, index = 0) => {
  const moduleBinding = config.module_binding || config.moduleBinding || {};
  const modelName = config.model_name || config.model || 'placeholder';
  const enabled = Boolean(config.is_enabled ?? config.enabled);
  return {
    id: `llm-${config.id}`,
    backendId: config.id,
    name: modelName,
    provider: moduleBinding.provider || config.provider || 'OpenAI-compatible',
    baseUrl: config.base_url || config.baseUrl || '',
    apiKey: config.api_key_ref ? `env:${config.api_key_ref}` : HIDDEN_KEY_LABEL,
    apiKeyRef: config.api_key_ref || 'AITEST_LLM_API_KEY',
    temp: Number(config.temperature ?? 0.7),
    tokens: Number(config.max_tokens ?? config.maxTokens ?? 4096),
    latency: enabled ? Number(moduleBinding.last_latency_ms || 0) : 0,
    rate: moduleBinding.success_rate || (enabled ? '待测速' : '0.0%'),
    status: enabled ? 'online' : 'offline',
    isDefault: Boolean(config.is_default ?? (index === 0 && enabled))
  };
};

export default function LlmConfig() {
  // 模型数据库状态驱动，包含大厂多模型路由信息
  const [models, setModels] = useState(DEFAULT_MODELS);

  const [activeModelId, setActiveModelId] = useState('gpt-4o');
  const [showKey, setShowKey] = useState(false);
  const [activeStrategy, setActiveStrategy] = useState('智能低延迟路由 (Auto-Latency)');
  const [isLoadingConfigs, setIsLoadingConfigs] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  
  // 运行诊断状态
  const [isTesting, setIsTesting] = useState(false);
  const [testStatus, setTestStatus] = useState('success'); // 'idle', 'testing', 'success'
  const [terminalLogs, setTerminalLogs] = useState([
    { type: 'system', text: '> Gateway System initialized. Proxy module ready.' },
    { type: 'info', text: '[INFO] Loaded models registry: 4 configs found.' },
    { type: 'success', text: '[ONLINE] Router connected. Gateway load factor: 12%.' }
  ]);
  
  // 延迟波动历史（最近 7 次测试）
  const [latencyHistory, setLatencyHistory] = useState([178, 195, 172, 185, 210, 190, 184]);
  
  // 用于终端日志滚动
  const logsEndRef = useRef(null);

  // 获取当前选中模型的信息
  const currentModel = models.find(m => m.id === activeModelId) || models[0];

  // 配置表单对应的内部临时状态，与当前激活的模型同步
  const [provider, setProvider] = useState(currentModel.provider);
  const [modelName, setModelName] = useState(currentModel.name);
  const [baseUrl, setBaseUrl] = useState(currentModel.baseUrl);
  const [apiKey, setApiKey] = useState(currentModel.apiKey);
  const [temp, setTemp] = useState(currentModel.temp);
  const [tokens, setTokens] = useState(currentModel.tokens);

  const buildConfigPayload = (model = currentModel) => ({
    name: `${provider || model.provider || 'OpenAI-compatible'} / ${modelName || model.name || 'placeholder'}`,
    base_url: baseUrl || model.baseUrl || null,
    api_key_ref: (apiKey || model.apiKey || HIDDEN_KEY_LABEL).replace(/^env:/, '') || 'AITEST_LLM_API_KEY',
    model_name: modelName || model.name || 'placeholder',
    max_tokens: Number(tokens || model.tokens || 4096),
    temperature: Number(temp ?? model.temp ?? 0.7),
    is_default: Boolean(model.isDefault),
    is_enabled: model.status !== 'offline',
    module_binding: {
      ...(model.moduleBinding || {}),
      provider: provider || model.provider || 'OpenAI-compatible',
      strategy: activeStrategy
    }
  });

  const loadLlmConfigs = React.useCallback(async ({ silent = false } = {}) => {
    if (!silent) setIsLoadingConfigs(true);
    try {
      const payload = await apiGet('/llm-configs', { params: { page: 1, pageSize: 100 } });
      const nextModels = pickList(payload).map(mapBackendModel);
      if (nextModels.length > 0) {
        setModels(nextModels);
        const defaultModel = nextModels.find((item) => item.isDefault) || nextModels[0];
        setActiveModelId(defaultModel.id);
        setTerminalLogs([
          { type: 'system', text: '> Gateway registry synchronized from backend.' },
          { type: 'info', text: `[INFO] Loaded backend LLM configs: ${nextModels.length}.` },
          { type: 'success', text: '[READY] Backend model registry is active.' }
        ]);
      }
    } catch (error) {
      setTerminalLogs(prev => [
        ...prev,
        { type: 'error', text: `[ERROR] Failed to load backend LLM configs: ${error.message || error}` }
      ]);
      showToast(`LLM 配置加载失败：${error.message || error}`, 'error');
    } finally {
      setIsLoadingConfigs(false);
    }
  }, []);

  useEffect(() => {
    loadLlmConfigs();
  }, [loadLlmConfigs]);

  // 监听激活模型变化，同步回填表单
  useEffect(() => {
    if (currentModel) {
      setProvider(currentModel.provider);
      setModelName(currentModel.name);
      setBaseUrl(currentModel.baseUrl);
      setApiKey(currentModel.apiKey);
      setTemp(currentModel.temp);
      setTokens(currentModel.tokens);
      setTestStatus(currentModel.status === 'online' ? 'success' : 'idle');
      
      setTerminalLogs([
        { type: 'system', text: `> Routing session switched to Model: ${currentModel.id}` },
        { type: 'info', text: `[INFO] Provider: ${currentModel.provider} | EndPoint: ${currentModel.baseUrl}` },
        { type: 'success', text: `[READY] Selected target node configuration loaded.` }
      ]);
    }
  }, [activeModelId]);

  // 滚动到底部
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [terminalLogs]);

  // 修改表单字段并同步写回 models 数组
  const handleFieldChange = (key, val) => {
    if (key === 'provider') setProvider(val);
    if (key === 'modelName') setModelName(val);
    if (key === 'baseUrl') setBaseUrl(val);
    if (key === 'apiKey') setApiKey(val);
    
    setModels(prev => prev.map(m => {
      if (m.id === activeModelId) {
        return { 
          ...m, 
          provider: key === 'provider' ? val : m.provider,
          name: key === 'modelName' ? val : m.name,
          baseUrl: key === 'baseUrl' ? val : m.baseUrl,
          apiKey: key === 'apiKey' ? val : m.apiKey
        };
      }
      return m;
    }));
    if (testStatus === 'success') setTestStatus('idle');
  };

  // 修改滑动条参数并写回 models 数组
  const handleTempChange = (val) => {
    setTemp(val);
    setModels(prev => prev.map(m => m.id === activeModelId ? { ...m, temp: val } : m));
    if (testStatus === 'success') setTestStatus('idle');
  };

  const handleTokensChange = (val) => {
    setTokens(val);
    setModels(prev => prev.map(m => m.id === activeModelId ? { ...m, tokens: val } : m));
    if (testStatus === 'success') setTestStatus('idle');
  };

  const saveCurrentConfig = async ({ silent = false } = {}) => {
    const payload = buildConfigPayload();
    const saved = currentModel.backendId
      ? await apiRequest(`/llm-configs/${currentModel.backendId}`, { method: 'PATCH', body: payload })
      : await apiPost('/llm-configs', payload);
    const mapped = mapBackendModel(saved);
    setModels(prev => {
      const withoutCurrent = prev.filter(item => item.id !== activeModelId);
      return [...withoutCurrent, mapped].sort((a, b) => (b.isDefault ? 1 : 0) - (a.isDefault ? 1 : 0));
    });
    setActiveModelId(mapped.id);
    if (!silent) {
      showToast('网关配置已保存到后端，凭证仅保存为环境变量引用。');
    }
    return mapped;
  };

  // 保存当前网关全部配置
  const handleSaveAll = async () => {
    if (isSaving) return;
    setIsSaving(true);
    try {
      await saveCurrentConfig();
      await loadLlmConfigs({ silent: true });
    } catch (error) {
      showToast(`网关配置保存失败：${error.message || error}`, 'error');
      setTerminalLogs(prev => [...prev, { type: 'error', text: `[ERROR] Save failed: ${error.message || error}` }]);
    } finally {
      setIsSaving(false);
    }
  };

  // 将当前选中模型设为默认网关路由
  const handleSetDefault = async () => {
    setModels(prev => prev.map(m => ({
      ...m,
      isDefault: m.id === activeModelId
    })));
    try {
      if (currentModel.backendId) {
        await apiRequest(`/llm-configs/${currentModel.backendId}`, {
          method: 'PATCH',
          body: { ...buildConfigPayload(), is_default: true, is_enabled: true }
        });
        await loadLlmConfigs({ silent: true });
      }
      showToast(`已成功将模型 ${modelName} 设为全局默认网关路由。`);
    } catch (error) {
      showToast(`默认路由更新失败：${error.message || error}`, 'error');
    }
  };

  // 删除当前选中的自定义模型
  const handleDeleteModel = async () => {
    if (currentModel.isDefault) {
      showToast('无法移除当前的系统默认路由模型，请先将其他模型设为默认值。', 'error');
      return;
    }
    if (models.length <= 1) {
      showToast('至少需要保留一个模型路由节点。', 'error');
      return;
    }
    try {
      if (currentModel.backendId) {
        await apiRequest(`/llm-configs/${currentModel.backendId}`, { method: 'DELETE' });
      }
      const remaining = models.filter(m => m.id !== activeModelId);
      setModels(remaining);
      setActiveModelId(remaining[0].id);
      showToast('模型路由节点已停用。', 'info');
    } catch (error) {
      showToast(`模型路由节点停用失败：${error.message || error}`, 'error');
    }
  };

  // 新增一个自定义模型路由配置
  const handleAddNewModel = async () => {
    try {
      const saved = await apiPost('/llm-configs', {
        name: 'Custom OpenAI Compatible',
        provider: 'OpenAI-compatible',
        base_url: 'http://127.0.0.1:11434/v1',
        api_key_ref: 'AITEST_LLM_API_KEY',
        model_name: 'custom-openai-compatible',
        max_tokens: 4096,
        temperature: 0.7,
        is_default: false,
        is_enabled: false,
        module_binding: { provider: 'OpenAI-compatible', strategy: activeStrategy }
      });
      const mapped = mapBackendModel(saved);
      setModels(prev => [...prev, mapped]);
      setActiveModelId(mapped.id);
      showToast('已在后端新建待配置的模型路由，请补充服务参数。', 'info');
    } catch (error) {
      showToast(`新建模型路由失败：${error.message || error}`, 'error');
    }
  };

  // 运行连接测试，包含动态控制台输出与延迟波动折线更新
  const runConnectionTest = async () => {
    if (isTesting) return;
    setIsTesting(true);
    setTestStatus('testing');
    
    setTerminalLogs([
      { type: 'system', text: `> Initializing Diagnostic Check on Endpoint: ${baseUrl}` }
    ]);

    try {
      const modelForTest = currentModel.backendId ? currentModel : await saveCurrentConfig({ silent: true });
      setTerminalLogs(prev => [
        ...prev,
        { type: 'info', text: `[HTTP] POST /llm-configs/${modelForTest.backendId}/test` },
        { type: 'info', text: '[AUTH] Credentials are resolved on backend through environment reference.' }
      ]);
      const startedAt = Date.now();
      const result = await apiPost(`/llm-configs/${modelForTest.backendId}/test`, {}, { timeoutMs: 15000 });
      const newLatency = Math.max(1, Date.now() - startedAt);
      const connected = Boolean(result.connected);
      const statusText = result.status || (connected ? 'ok' : 'fallback');

      setModels(prev => prev.map(m => m.id === modelForTest.id ? {
        ...m,
        latency: newLatency,
        status: connected ? 'online' : 'offline',
        rate: connected ? '100.0%' : '降级'
      } : m));
      setTerminalLogs(prev => [
        ...prev,
        {
          type: connected ? 'success' : 'error',
          text: connected
            ? `[${statusText.toUpperCase()}] Backend handshake established. Model ${modelName} active.`
            : `[${statusText.toUpperCase()}] Backend reached, but real LLM runtime is unavailable.`
        },
        { type: 'system', text: `> Diagnostics complete. Backend RTT: ${newLatency}ms.` }
      ]);
      setLatencyHistory(prev => [...prev.slice(1), newLatency]);
      setTestStatus(connected ? 'success' : 'idle');
      showToast(
        connected
          ? `与模型 ${modelName} 测试成功，后端响应 ${newLatency}ms。`
          : `后端连接完成，但真实 LLM 当前不可用：${result.reason || result.error || statusText}`,
        connected ? 'success' : 'info'
      );
    } catch (error) {
      setTerminalLogs(prev => [...prev, { type: 'error', text: `[ERROR] ${error.message || error}` }]);
      setTestStatus('idle');
      showToast(`模型连接测试失败：${error.message || error}`, 'error');
    } finally {
      setIsTesting(false);
    }
  };

  // 极简 SVG 折线图和渐变面积生成器
  const getLinePath = (data) => {
    const width = 150;
    const height = 36;
    const padding = 4;
    const points = data.map((val, i) => {
      const x = padding + (i * (width - padding * 2)) / (data.length - 1);
      const y = height - padding - (val / 400) * (height - padding * 2);
      return `${x},${y}`;
    });
    return `M ${points.join(' L ')}`;
  };

  const getAreaPath = (data) => {
    const width = 150;
    const height = 36;
    const padding = 4;
    const points = data.map((val, i) => {
      const x = padding + (i * (width - padding * 2)) / (data.length - 1);
      const y = height - padding - (val / 400) * (height - padding * 2);
      return `${x},${y}`;
    });
    return `M ${padding},${height - padding} L ${points.join(' L ')} L ${width - padding},${height - padding} Z`;
  };

  return (
    <div className="space-y-5 text-left transition-all duration-200 w-full pb-10">
      
      {/* 顶栏 */}
      <div className="flex justify-between items-center bg-[var(--bg-card)] border border-[var(--border-color)] rounded-xl p-4 shadow-sm">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-base font-bold text-[var(--text-primary)]">LLM 网关中心</h1>
            <span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-500 rounded-full text-[9px] font-bold flex items-center gap-1">
              <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
              网关在线
            </span>
          </div>
          <p className="text-[11px] text-[var(--text-secondary)] mt-1">配置并调度测试平台多服务商大语言模型接口，实现智能负载流控、健康自愈及数据诊断。</p>
        </div>
        <div className="flex gap-2">
          <button 
            onClick={handleSaveAll}
            disabled={isSaving}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg glow-button-neon text-[11px] font-bold text-white cursor-pointer shadow-sm disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isSaving ? <RefreshCw className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}
            <span>{isSaving ? '保存中...' : '保存网关配置'}</span>
          </button>
        </div>
      </div>

      {/* 第一排：网关多维指标卡 */}
      <div className="grid grid-cols-4 gap-4">
        {/* 指标1：当前主要默认路由 */}
        <div className="chroma-glass rounded-xl p-4 flex flex-col justify-between border min-h-[90px]">
          <div className="flex items-center justify-between text-[10px] opacity-60 text-[var(--text-secondary)] font-medium">
            <span>默认路由模型</span>
            <Activity className="size-3.5 text-blue-500" />
          </div>
          <div className="mt-2 flex flex-col">
            <span className="text-sm font-bold text-[var(--text-primary)] truncate">
              {models.find(m => m.isDefault)?.name || '未设定'}
            </span>
            <span className="text-[9px] opacity-50 mt-1 truncate">
              服务商：{models.find(m => m.isDefault)?.provider || '未设定'}
            </span>
          </div>
        </div>

        {/* 指标2：平均延迟 (RTT) */}
        <div className="chroma-glass cyber-meteor-dust rounded-xl p-4 flex flex-col justify-between border min-h-[90px]">
          <div className="flex items-center justify-between text-[10px] opacity-60 text-[var(--text-secondary)] font-medium">
            <span>网关平均延迟</span>
            <Zap className="size-3.5 text-amber-500" />
          </div>
          <div className="mt-2 flex items-center justify-between">
            <div className="flex flex-col">
              <span className="text-xl font-black text-[var(--text-primary)] leading-tight neon-pulse-number">
                {currentModel.latency > 0 ? <><AnimatedNumber value={currentModel.latency} />ms</> : 'Offline'}
              </span>
              <span className="text-[9px] text-emerald-500 font-semibold mt-1">较昨日 -14ms ↓</span>
            </div>
            {/* 迷你 Sparkline */}
            <div className="w-20 h-8 opacity-70">
              <svg className="w-full h-full" viewBox="0 0 150 36">
                <path 
                  d={getAreaPath(latencyHistory)} 
                  fill="url(#spark_grad)" 
                  opacity="0.15" 
                />
                <path 
                  d={getLinePath(latencyHistory)} 
                  fill="none" 
                  stroke="var(--accent-color)" 
                  strokeWidth="2" 
                  strokeLinecap="round" 
                  className="path-drawn"
                />
                <defs>
                  <linearGradient id="spark_grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent-color)" />
                    <stop offset="100%" stopColor="var(--accent-color)" stopOpacity="0" />
                  </linearGradient>
                </defs>
              </svg>
            </div>
          </div>
        </div>

        {/* 指标3：请求成功率 */}
        <div className="chroma-glass rounded-xl p-4 flex flex-col justify-between border min-h-[90px]">
          <div className="flex items-center justify-between text-[10px] opacity-60 text-[var(--text-secondary)] font-medium">
            <span>连接稳定性 (7d)</span>
            <ShieldCheck className="size-3.5 text-emerald-500" />
          </div>
          <div className="mt-2 flex flex-col">
            <span className="text-xl font-black text-[var(--text-primary)] leading-tight neon-pulse-number"><AnimatedNumber value={99.85} />%</span>
            <span className="text-[9px] opacity-50 mt-1">近 7 天累计 24,531 次调用</span>
          </div>
        </div>

        {/* 指标4：节点并发吞吐 */}
        <div className="chroma-glass cyber-meteor-dust rounded-xl p-4 flex flex-col justify-between border min-h-[90px]">
          <div className="flex items-center justify-between text-[10px] opacity-60 text-[var(--text-secondary)] font-medium">
            <span>就绪路由节点</span>
            <Database className="size-3.5 text-purple-500" />
          </div>
          <div className="mt-2 flex flex-col">
            <span className="text-xl font-black text-[var(--text-primary)] leading-tight neon-pulse-number">
              <AnimatedNumber value={models.filter(m => m.status === 'online').length} /> / <AnimatedNumber value={models.length} /> Active
            </span>
            <span className="text-[9px] opacity-50 mt-1">剩余 {models.filter(m => m.status !== 'online').length} 处于备用或休眠</span>
          </div>
        </div>
      </div>

      {/* 第二排：主分栏核心视图（7:5 经典大厂后台布局） */}
      <div className="grid grid-cols-12 gap-5 w-full">
        
        {/* 左侧：服务节点表格与详细接口配置 (7 col) */}
        <div className="col-span-12 lg:col-span-7 flex flex-col gap-4">
          
          {/* 1. 模型注册列表卡片 */}
          <div className="theme-card rounded-xl p-4 space-y-3">
            <div className="flex justify-between items-center border-b border-[var(--border-color)] pb-2.5">
              <h2 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
                <Database className="size-4 text-[var(--accent-color)]" />
                  <span>接入模型网关路由表 (Model Registry){isLoadingConfigs ? ' · 同步中' : ''}</span>
              </h2>
              <button 
                onClick={handleAddNewModel}
                className="flex items-center gap-1 px-2 py-1 rounded bg-[var(--border-color)]/30 hover:bg-[var(--border-color)]/60 text-[9px] font-bold text-[var(--text-primary)] transition-all active:scale-95 cursor-pointer border border-[var(--border-color)]"
              >
                <Plus className="size-3" />
                <span>新增接入节点</span>
              </button>
            </div>

            <div className="overflow-x-auto w-full">
              <table className="w-full text-[10.5px] text-left border-collapse">
                <thead>
                  <tr className="border-b border-[var(--border-color)] opacity-60 text-[var(--text-secondary)] font-bold">
                    <th className="pb-2 font-bold pl-2">模型代号</th>
                    <th className="pb-2 font-bold">供应商 (Provider)</th>
                    <th className="pb-2 font-bold">接口端点 (Endpoint)</th>
                    <th className="pb-2 font-bold text-center">当前延迟</th>
                    <th className="pb-2 font-bold text-center">状态</th>
                    <th className="pb-2 font-bold text-center pr-2">路由</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-color)] font-medium text-[var(--text-primary)]">
                  {models.map((m) => {
                    const isSelected = activeModelId === m.id;
                    return (
                      <tr 
                        key={m.id}
                        onClick={() => setActiveModelId(m.id)}
                        className={`hover:bg-[var(--border-color)]/25 cursor-pointer transition-all duration-150 ${
                          isSelected 
                            ? 'bg-[var(--accent-glow)]/40 border-l-[3px] border-[var(--accent-color)]' 
                            : 'border-l-[3px] border-transparent'
                        }`}
                      >
                        <td className="py-2.5 font-bold pl-2 truncate max-w-[120px]">{m.name}</td>
                        <td className="py-2.5 opacity-80">{m.provider}</td>
                        <td className="py-2.5 opacity-60 font-mono text-[9px] truncate max-w-[140px]">{m.baseUrl}</td>
                        <td className="py-2.5 text-center font-bold">
                          {m.latency > 0 ? (
                            <span className="text-[10px] text-emerald-500">{m.latency}ms</span>
                          ) : (
                            <span className="text-[10px] text-slate-400">—</span>
                          )}
                        </td>
                        <td className="py-2.5 text-center">
                          <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[8px] font-bold ${
                            m.status === 'online' 
                              ? 'bg-emerald-500/10 text-emerald-500' 
                              : 'bg-red-500/10 text-red-500'
                          }`}>
                            <span className={`size-1 rounded-full ${m.status === 'online' ? 'bg-emerald-500' : 'bg-red-500'}`}></span>
                            {m.status.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-2.5 text-center pr-2">
                          {m.isDefault ? (
                            <span className="px-1.5 py-0.5 bg-[var(--accent-color)] text-white text-[8px] font-black rounded shadow-sm">DEFAULT</span>
                          ) : (
                            <span className="text-[9px] opacity-40 font-bold">Backup</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* 2. 当前选中模型详细配置卡片 */}
          <div className="theme-card rounded-xl p-5 flex flex-col justify-between space-y-4">
            <div>
              <div className="flex justify-between items-center border-b border-[var(--border-color)] pb-2 mb-3">
                <h2 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
                  <Sliders className="size-4 text-[var(--accent-color)]" />
                  <span>服务接口与连接安全配置</span>
                </h2>
                <span className="text-[9px] opacity-50 font-mono font-semibold uppercase">NODE: {activeModelId}</span>
              </div>

              <div className="space-y-4 text-xs font-semibold text-[var(--text-secondary)] leading-normal">
                {/* 供应商与名称 */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="block text-[var(--text-primary)]">API 供应商 (Provider)</label>
                    <div className="flex items-center justify-between px-3 py-2 premium-input text-[11px] font-bold cursor-pointer relative group">
                      <span>{provider}</span>
                      <ChevronDown className="size-3.5 text-slate-400" />
                      <div className="absolute top-full left-0 right-0 mt-1 rounded-lg bg-[var(--bg-card)] border border-[var(--border-color)] shadow-lg hidden group-hover:block z-20">
                        {['OpenAI / Azure LLM Proxy', 'Claude Anthropic', 'DeepSeek API', 'Custom Local LLM'].map((item) => (
                          <div 
                            key={item} 
                            onClick={() => handleFieldChange('provider', item)}
                            className="px-3 py-2 hover:bg-[var(--border-color)]/50 text-[10px] font-bold text-[var(--text-primary)] transition-colors text-left"
                          >
                            {item}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                  
                  <div className="space-y-1.5">
                    <label className="block text-[var(--text-primary)]">模型别名 (Model Name)</label>
                    <div className="flex items-center justify-between px-3 py-2 premium-input text-[11px] font-bold cursor-pointer relative group">
                      <span>{modelName}</span>
                      <ChevronDown className="size-3.5 text-slate-400" />
                      <div className="absolute top-full left-0 right-0 mt-1 rounded-lg bg-[var(--bg-card)] border border-[var(--border-color)] shadow-lg hidden group-hover:block z-20">
                        {['gpt-4o-2024-08-06', 'gpt-4-turbo', 'claude-3-5-sonnet', 'deepseek-coder', 'local-llama-3'].map((item) => (
                          <div 
                            key={item} 
                            onClick={() => handleFieldChange('modelName', item)}
                            className="px-3 py-2 hover:bg-[var(--border-color)]/50 text-[10px] font-bold text-[var(--text-primary)] transition-colors text-left"
                          >
                            {item}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                {/* API Base URL */}
                <div className="space-y-1.5">
                  <label className="block text-[var(--text-primary)]">API Base URL (终点网络地址)</label>
                  <div className="relative">
                    <input 
                      type="text" 
                      value={baseUrl} 
                      onChange={(e) => handleFieldChange('baseUrl', e.target.value)}
                      className="w-full pl-8 pr-3 py-2 premium-input text-[11px] quantum-input-glow"
                    />
                    <Globe className="size-3.5 text-slate-400 absolute left-2.5 top-1/2 transform -translate-y-1/2" />
                  </div>
                </div>

                {/* API Key 安全隐藏 */}
                <div className="space-y-1.5">
                  <label className="block text-[var(--text-primary)]">API 授权凭证 (Secret API Key)</label>
                  <div className="text-[9px] text-[var(--text-secondary)] -mt-0.5 mb-1">
                    前端只保存环境变量引用，不写入或回显明文 Key。
                  </div>
                  <div className="relative">
                    <input 
                      type={showKey ? 'text' : 'password'} 
                      value={apiKey}
                      onChange={(e) => handleFieldChange('apiKey', e.target.value)}
                      className="w-full px-3 py-2 premium-input text-[11px] font-mono pr-10 quantum-input-glow"
                    />
                    <button 
                      onClick={() => setShowKey(!showKey)}
                      className="absolute right-3 top-1/2 transform -translate-y-1/2 text-slate-400 hover:text-[var(--accent-color)] transition-colors cursor-pointer"
                    >
                      {showKey ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* 操作控制板 */}
            <div className="border-t border-[var(--border-color)] pt-4 flex justify-between items-center text-[10px] font-bold mt-4">
              <div className="flex gap-2">
                <button 
                  onClick={handleSetDefault}
                  disabled={isSaving || isTesting}
                  className="px-3 py-1.5 bg-[var(--border-color)]/40 hover:bg-[var(--border-color)]/80 text-[var(--text-primary)] border border-[var(--border-color)] rounded-lg cursor-pointer transition-all active:scale-95"
                >
                  设为系统默认路由
                </button>
                <button 
                  onClick={handleDeleteModel}
                  disabled={currentModel.isDefault}
                  className="px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-500 border border-red-500/15 rounded-lg cursor-pointer transition-all active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-1"
                >
                  <Trash2 className="size-3" />
                  <span>移除节点</span>
                </button>
              </div>

              <div className="flex items-center gap-2">
                {testStatus === 'success' && (
                  <div className="flex items-center gap-1 text-emerald-500 animate-[fadeIn_0.2s_ease-out]">
                    <CheckCircle className="size-3.5 fill-current text-emerald-100 dark:text-emerald-950/40" />
                    <span>通过诊断验证</span>
                  </div>
                )}
                {testStatus === 'testing' && (
                  <div className="flex items-center gap-1 text-[var(--accent-color)]">
                    <RefreshCw className="size-3 animate-spin" />
                    <span>诊断连接中...</span>
                  </div>
                )}
                {testStatus === 'idle' && (
                  <div className="flex items-center gap-1 text-amber-500 animate-[fadeIn_0.2s_ease-out]">
                    <AlertCircle className="size-3.5" />
                    <span>参数发生变更</span>
                  </div>
                )}

                <button 
                  onClick={runConnectionTest}
                  disabled={isTesting}
                  className="px-3 py-1.5 glow-button-neon text-white rounded-lg cursor-pointer transition-all active:scale-95 disabled:opacity-50 flex items-center gap-1"
                >
                  {isTesting ? <RefreshCw className="size-3 animate-spin" /> : <Activity className="size-3" />}
                  <span>测试连接</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* 右侧：高级模型运行参数与模拟终端 (5 col) */}
        <div className="col-span-12 lg:col-span-5 flex flex-col gap-4">
          
          {/* 1. 高级策略与微调 */}
          <TiltCard className="theme-card laser-chase-border rounded-xl p-5 space-y-4">
            <div style={{ transform: 'translateZ(20px)', transformStyle: 'preserve-3d' }}>
              <h2 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 flex items-center gap-1.5">
                <Sliders className="size-4 text-purple-500" />
                <span className="cyber-glitch-text cursor-pointer transition-all">智能负载与模型核心策略</span>
              </h2>

              <div className="space-y-4 text-xs font-semibold text-[var(--text-secondary)] leading-normal">
                {/* 生成温度 */}
                <div className="space-y-2" style={{ transform: 'translateZ(10px)' }}>
                  <div className="flex justify-between">
                    <label className="text-[var(--text-primary)]">生成温度 (Temperature)</label>
                    <span className="font-bold text-[var(--accent-color)]">{temp}</span>
                  </div>
                  <input 
                    type="range" 
                    min="0" 
                    max="1.5" 
                    step="0.1" 
                    value={temp}
                    onChange={(e) => handleTempChange(parseFloat(e.target.value))}
                    className="w-full cursor-pointer"
                    style={{ accentColor: 'var(--accent-color)' }}
                  />
                  <span className="text-[9px] text-[var(--text-secondary)] block font-medium leading-none">值越高生成越多样，值越低生成结果越稳定（用例推荐 0.2 ~ 0.5）。</span>
                </div>

                {/* 最大 Tokens */}
                <div className="space-y-2 pt-2 border-t border-[var(--border-color)]" style={{ transform: 'translateZ(15px)' }}>
                  <div className="flex justify-between">
                    <label className="text-[var(--text-primary)]">最大 Tokens 限制 (Max Tokens)</label>
                    <span className="font-bold text-[var(--accent-color)]">{tokens}</span>
                  </div>
                  <input 
                    type="range" 
                    min="512" 
                    max="8192" 
                    step="256" 
                    value={tokens}
                    onChange={(e) => handleTokensChange(parseInt(e.target.value))}
                    className="w-full cursor-pointer"
                    style={{ accentColor: 'var(--accent-color)' }}
                  />
                  <span className="text-[9px] text-[var(--text-secondary)] block font-medium leading-none">每次请求模型能返回的最大字符长度上限。</span>
                </div>

                {/* 路由负载策略 */}
                <div className="space-y-1.5 pt-2 border-t border-[var(--border-color)]" style={{ transform: 'translateZ(20px)' }}>
                  <label className="block text-[var(--text-primary)]">网关分发路由策略 (Gateway Policy)</label>
                  <div className="flex items-center justify-between px-3 py-2 premium-input text-[11px] font-bold cursor-pointer relative group">
                    <span>{activeStrategy}</span>
                    <ChevronDown className="size-3.5 text-slate-400" />
                    <div className="absolute top-full left-0 right-0 mt-1 rounded-lg bg-[var(--bg-card)] border border-[var(--border-color)] shadow-lg hidden group-hover:block z-20">
                      {[
                        { name: '智能低延迟路由 (Auto-Latency)', desc: '优先选择最快响应的可用端点' },
                        { name: '主备自动灾备 (Failover Retry)', desc: '主端点故障自动无感降级备用' },
                        { name: '智能负载均衡 (Round-Robin)', desc: '按权重在各健康模型间分发' }
                      ].map((item) => (
                        <div 
                          key={item.name} 
                          onClick={() => {
                            setActiveStrategy(item.name);
                            window.dispatchEvent(new CustomEvent('show-toast', { 
                              detail: { message: `网关路由策略切换为: ${item.name}`, type: 'info' } 
                            }));
                          }}
                          className="px-3 py-2 hover:bg-[var(--border-color)]/50 text-left transition-colors"
                        >
                          <div className="text-[10px] font-bold text-[var(--text-primary)]">{item.name}</div>
                          <div className="text-[8px] text-[var(--text-secondary)] mt-0.5">{item.desc}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </TiltCard>

          {/* 2. 模拟诊断终端与物理测速 */}
          <TiltCard className="theme-card laser-chase-border rounded-xl flex-1 flex flex-col min-h-[260px] overflow-hidden">
            <div style={{ transform: 'translateZ(20px)', transformStyle: 'preserve-3d', display: 'flex', flexDirection: 'column', height: '100%' }}>
              {/* 终端头部 */}
              <div className="flex items-center justify-between px-4 py-2 bg-[#141b2a] border-b border-[#223049] select-none shrink-0" style={{ transform: 'translateZ(10px)' }}>
                <div className="flex items-center gap-2">
                  <span className="size-2.5 rounded-full bg-[#ff5f56]"></span>
                  <span className="size-2.5 rounded-full bg-[#ffbd2e]"></span>
                  <span className="size-2.5 rounded-full bg-[#27c93f]"></span>
                </div>
                <span className="text-[10px] text-slate-500 font-mono font-bold flex items-center gap-1.5">
                  <Terminal className="size-3" />
                  <span>diagnostic-console.sh</span>
                </span>
                <div className="w-10"></div>
              </div>

              {/* 终端内容区 */}
              <div className="p-4 flex-1 cyber-matrix-console bg-[#0b0f19] font-mono text-[9.5px] space-y-1.5 overflow-y-auto max-h-[160px] text-left leading-relaxed" style={{ transform: 'translateZ(15px)' }}>
                {terminalLogs.map((log, index) => {
                  let colorClass = 'text-slate-400';
                  if (log.type === 'system') colorClass = 'text-purple-400 font-bold';
                  if (log.type === 'success') colorClass = 'text-emerald-400 font-bold';
                  if (log.type === 'info') colorClass = 'text-cyan-400';
                  if (log.type === 'error') colorClass = 'text-rose-400 font-bold';
                  
                  return (
                    <div key={index} className={colorClass}>
                      {log.text}
                    </div>
                  );
                })}
                <div ref={logsEndRef} />
              </div>

              {/* 底部雷达状态监视栏 */}
              <div className="bg-[#0f1524] border-t border-[#223049] px-4 py-3 flex items-center justify-between text-[9px] font-mono shrink-0" style={{ transform: 'translateZ(25px)' }}>
                <div className="flex flex-col text-left gap-1">
                  <span className="text-slate-500">RTT LATENCY METRIC</span>
                  <span className="text-[var(--accent-color)] font-bold flex items-center gap-1">
                    <Activity className="size-3 animate-pulse" />
                    <span>实时网络延迟波动曲线</span>
                  </span>
                </div>
                
                <div className="flex flex-col text-right gap-1">
                  <span className="text-slate-500">TTFB AVERAGE</span>
                  <span className="text-emerald-400 font-bold">
                    {currentModel.latency > 0 ? `${Math.floor(currentModel.latency * 0.8)}ms` : '—'}
                  </span>
                </div>
              </div>
            </div>
          </TiltCard>

        </div>

      </div>

      <PromptTemplatePanel />

    </div>
  );
}
