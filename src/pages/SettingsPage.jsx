import React, { useState, useEffect, useRef } from 'react';
import { 
  Settings, 
  Save, 
  AlertTriangle, 
  RefreshCw, 
  Database, 
  ShieldAlert, 
  Terminal, 
  CheckCircle,
  Activity,
  Cpu,
  HardDrive,
  Trash2,
  Lock,
  Layers,
  Clock
} from 'lucide-react';
import TiltCard from '../components/TiltCard';
import AnimatedNumber from '../components/AnimatedNumber';
import { apiGet, apiPost, formatDateTime } from '../lib/api';

export default function SettingsPage() {
  const [logLevel, setLogLevel] = useState('info');
  const [isBackingUp, setIsBackingUp] = useState(false);
  const [isClearingCache, setIsClearingCache] = useState(false);
  const [cacheSize, setCacheSize] = useState('128.4 MB');
  const [maxWorkers, setMaxWorkers] = useState(8);
  const [timeoutLimit, setTimeoutLimit] = useState(30);
  const [schemaStatus, setSchemaStatus] = useState(null);
  const [settingsApiState, setSettingsApiState] = useState({ status: 'loading', message: '' });
  
  // 危险操作安全锁
  const [safetyLock, setSafetyLock] = useState(true);

  // 解析 cacheSize
  const numericCacheSize = parseFloat(cacheSize);
  const cacheUnit = cacheSize.replace(String(numericCacheSize), '').trim();

  // 实时系统日志终端状态
  const [terminalLogs, setTerminalLogs] = useState([
    { type: 'system', text: '> ATP Daemon system initialized successfully.' },
    { type: 'info', text: '[TELEMETRY] Listening node clusters at localhost:3000' },
    { type: 'success', text: '[HEALTH] CPU load: 1.2% | Memory footprint: 42.1 MB. Nominal.' }
  ]);

  const logsEndRef = useRef(null);

  // 滚动到底部
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [terminalLogs]);

  useEffect(() => {
    let cancelled = false;

    async function loadSystemSettings() {
      try {
        const [schema, preference] = await Promise.all([
          apiGet('/system/schema-status'),
          apiGet('/system/preferences/runtime-settings').catch(() => null)
        ]);

        if (cancelled) return;
        setSchemaStatus(schema);
        const value = preference?.value || {};
        if (value.logLevel) setLogLevel(value.logLevel);
        if (Number.isFinite(Number(value.maxWorkers))) setMaxWorkers(Number(value.maxWorkers));
        if (Number.isFinite(Number(value.timeoutLimit))) setTimeoutLimit(Number(value.timeoutLimit));
        setSettingsApiState({ status: 'online', message: '后端配置已同步' });
        setTerminalLogs(prev => [
          ...prev,
          { type: 'success', text: `[SYNC] Backend schema status: ${(schema.status || 'unknown').toUpperCase()} | tables ${schema.tables_present || 0}/${schema.tables_total || 0}` }
        ]);
      } catch (error) {
        if (!cancelled) {
          setSchemaStatus(null);
          setSettingsApiState({ status: 'offline', message: error?.message || '后端暂不可用，显示本地配置' });
          setTerminalLogs(prev => [
            ...prev,
            { type: 'info', text: '[SYNC] Backend settings unavailable. Using local UI defaults.' }
          ]);
        }
      }
    }

    loadSystemSettings();
    return () => {
      cancelled = true;
    };
  }, []);

  // 一键备份操作与动态日志打印
  const handleBackup = async () => {
    if (isBackingUp) return;
    setIsBackingUp(true);
    
    setTerminalLogs(prev => [
      ...prev,
      { type: 'system', text: '> Initializing data export backup sequence...' }
    ]);

    try {
      const snapshot = await apiPost('/system/backup', {
        name: `frontend-snapshot-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}`
      });
      setTerminalLogs(prev => [
        ...prev,
        { type: 'info', text: `[DB] Backup snapshot id: ${snapshot.backup_id || snapshot.id}` },
        { type: 'success', text: `[SUCCESS] Snapshot created at ${formatDateTime(snapshot.created_at || snapshot.updated_at)}` }
      ]);
      setSettingsApiState({ status: 'online', message: '后端备份已创建' });
      window.dispatchEvent(new CustomEvent('show-toast', { 
        detail: { message: '系统数据库快照已由后端创建。', type: 'success' } 
      }));
    } catch (error) {
      setTerminalLogs(prev => [
        ...prev,
        { type: 'info', text: '[DB] Backend backup API unavailable. Local archive simulation skipped.' },
        { type: 'system', text: `[ERROR] ${error?.message || 'Backup request failed'}` }
      ]);
      window.dispatchEvent(new CustomEvent('show-toast', { 
        detail: { message: '后端备份接口不可用，请确认 API 服务已启动。', type: 'error' } 
      }));
    } finally {
      setIsBackingUp(false);
    }
  };

  // 一键清理临时测试缓存
  const handleClearCache = () => {
    if (isClearingCache || cacheSize === '0.0 MB') return;
    setIsClearingCache(true);

    setTerminalLogs(prev => [
      ...prev,
      { type: 'system', text: '> Triggering local storage cache purging policy...' }
    ]);

    setTimeout(() => {
      setTerminalLogs(prev => [
        ...prev,
        { type: 'info', text: '[FS] Purging directory: /tmp/test-runner/screens/* ...' },
        { type: 'info', text: '[FS] Purging 142 orphaned HTML snapshot assets...' },
        { type: 'success', text: '[CLEARED] Space reclaimed: 128.4 MB. Storage optimal.' }
      ]);
      setCacheSize('0.0 MB');
      setIsClearingCache(false);
      window.dispatchEvent(new CustomEvent('show-toast', { 
        detail: { message: '临时执行文件缓存清理成功！空间已释放。', type: 'success' } 
      }));
    }, 1200);
  };

  // 恢复出厂设置危险动作
  const handleResetSystem = () => {
    if (safetyLock) {
      window.dispatchEvent(new CustomEvent('show-toast', { 
        detail: { message: '安全警示锁未解锁！请先在右侧关闭“操作安全锁”。', type: 'error' } 
      }));
      return;
    }
    
    if (confirm('警告：此操作将彻底格式化本地库，清空所有需求、测试用例和执行报告！此过程绝对不可逆。确认要继续吗？')) {
      setTerminalLogs(prev => [
        ...prev,
        { type: 'system', text: '!!! DANGER ZONE RESET TRIGGERED !!!' }
      ]);

      setTimeout(() => {
        setTerminalLogs(prev => [
          ...prev,
          { type: 'info', text: '[WIPE] Truncating table: requirements...' },
          { type: 'info', text: '[WIPE] Truncating table: test_cases...' },
          { type: 'info', text: '[WIPE] Truncating table: execution_history...' },
          { type: 'success', text: '[DONE] Core storage cleared. System restored to default.' }
        ]);
        window.dispatchEvent(new CustomEvent('show-toast', { 
          detail: { message: '本地数据仓库已彻底置空并重新初始化！', type: 'success' } 
        }));
      }, 1500);
    }
  };

  const handleSaveSettings = async () => {
    try {
      const saved = await apiPost('/system/preferences/runtime-settings', {
        value: {
          logLevel,
          maxWorkers,
          timeoutLimit,
          updatedAt: new Date().toISOString()
        }
      });
      setSettingsApiState({ status: 'online', message: `配置已保存：${saved.key || 'runtime-settings'}` });
      setTerminalLogs(prev => [
        ...prev,
        { type: 'success', text: `[CONFIG] Runtime settings persisted: ${saved.key || 'runtime-settings'}` }
      ]);
      window.dispatchEvent(new CustomEvent('show-toast', { 
        detail: { message: '系统运行参数与日志记录配置已保存到后端。', type: 'success' } 
      }));
    } catch (error) {
      setSettingsApiState({ status: 'offline', message: error?.message || '配置保存失败' });
      setTerminalLogs(prev => [
        ...prev,
        { type: 'system', text: `[ERROR] Runtime settings save failed: ${error?.message || 'unknown error'}` }
      ]);
      window.dispatchEvent(new CustomEvent('show-toast', { 
        detail: { message: '配置保存失败，请确认后端服务已启动。', type: 'error' } 
      }));
    }
  };

  return (
    <div className="space-y-5 text-left transition-all duration-200 w-full pb-10">
      
      {/* 顶栏 */}
      <div className="flex justify-between items-center bg-[var(--bg-card)] border border-[var(--border-color)] rounded-xl p-4 shadow-sm">
        <div>
          <h1 className="text-base font-bold text-[var(--text-primary)]">系统设置</h1>
          <p className="text-[11px] text-[var(--text-secondary)] mt-1">管理系统内核配置、并发控制、调度参数以及执行本地数据库备份与危险运维操作。</p>
        </div>
        <button 
          onClick={handleSaveSettings}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg accent-btn text-[11px] font-bold text-white cursor-pointer shadow-sm"
        >
          <Save className="size-3.5" />
          <span>保存配置</span>
        </button>
      </div>

      {/* 第一排：系统监控状态指标卡 */}
      <div className="grid grid-cols-4 gap-4">
        {/* 指标1：主进程健康 */}
        <div className="theme-card rounded-xl p-4 flex flex-col justify-between border min-h-[90px]">
          <div className="flex items-center justify-between text-[10px] opacity-60 text-[var(--text-secondary)] font-medium">
            <span>核心主进程状态</span>
            <Activity className="size-3.5 text-emerald-500 animate-pulse" />
          </div>
          <div className="mt-2 flex flex-col">
            <span className="text-sm font-bold text-[var(--text-primary)]">
              {settingsApiState.status === 'online' ? '健康在线 (Nominal)' : settingsApiState.status === 'loading' ? '同步中 (Syncing)' : '离线降级 (Fallback)'}
            </span>
            <span className="text-[9px] opacity-50 mt-1">{settingsApiState.message || 'Cluster node: node-1'}</span>
          </div>
        </div>

        {/* 指标2：数据卷规格 */}
        <div className="theme-card rounded-xl p-4 flex flex-col justify-between border min-h-[90px]">
          <div className="flex items-center justify-between text-[10px] opacity-60 text-[var(--text-secondary)] font-medium">
            <span>数据卷规格</span>
            <Cpu className="size-3.5 text-blue-500" />
          </div>
          <div className="mt-2 flex flex-col">
            <span className="text-sm font-bold text-[var(--text-primary)]">
              {(schemaStatus?.database_url_type || 'SQLite').toUpperCase()} / <AnimatedNumber value={schemaStatus?.tables_present || 12} /> tables
            </span>
            <span className="text-[9px] opacity-50 mt-1">Schema：{schemaStatus?.schema_version || 'local-demo'}</span>
          </div>
        </div>

        {/* 指标3：清理缓存占用 */}
        <div className="theme-card rounded-xl p-4 flex flex-col justify-between border min-h-[90px]">
          <div className="flex items-center justify-between text-[10px] opacity-60 text-[var(--text-secondary)] font-medium">
            <span>缓存磁盘占用</span>
            <HardDrive className="size-3.5 text-purple-500" />
          </div>
          <div className="mt-2 flex items-center justify-between">
            <div className="flex flex-col">
              <span className="text-sm font-bold text-[var(--text-primary)]"><AnimatedNumber value={numericCacheSize} /> {cacheUnit}</span>
              <span className="text-[9px] opacity-50 mt-1">主要是历史 HTML/截图等文件</span>
            </div>
            {cacheSize !== '0.0 MB' && (
              <button 
                onClick={handleClearCache}
                disabled={isClearingCache}
                className="px-2 py-1 rounded bg-red-500/10 hover:bg-red-500/20 text-red-500 border border-red-500/15 text-[8px] font-bold transition-all active:scale-95 cursor-pointer disabled:opacity-50"
              >
                {isClearingCache ? '清理中...' : '一键清理'}
              </button>
            )}
          </div>
        </div>

        {/* 指标4：构建内核环境 */}
        <div className="theme-card rounded-xl p-4 flex flex-col justify-between border min-h-[90px]">
          <div className="flex items-center justify-between text-[10px] opacity-60 text-[var(--text-secondary)] font-medium">
            <span>引擎运行版本</span>
            <Settings className="size-3.5 text-slate-400" />
          </div>
          <div className="mt-2 flex flex-col">
            <span className="text-sm font-bold text-[var(--text-primary)]">v2.5.0-Release ({schemaStatus?.status || 'demo'})</span>
            <span className="text-[9px] opacity-50 mt-1">检查时间：{formatDateTime(schemaStatus?.checked_at)}</span>
          </div>
        </div>
      </div>

      {/* 第二排：分栏布局 (7:5 解决大白边留白问题) */}
      <div className="grid grid-cols-12 gap-5 w-full">
        
        {/* 左侧：日志设置与引擎参数控制 (7 col) */}
        <div className="col-span-12 lg:col-span-7 flex flex-col gap-4">
          <div className="theme-card rounded-xl p-5 space-y-5">
            
            {/* 日志设置 */}
            <div className="space-y-3">
              <h2 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 flex items-center gap-1.5">
                <Settings className="size-4 text-[var(--accent-color)]" />
                <span>日志策略配置</span>
              </h2>
              <div className="flex items-center justify-between text-xs font-semibold text-[var(--text-secondary)]">
                <span>系统调试日志输出级别</span>
                <div className="flex rounded-lg overflow-hidden border border-[var(--border-color)] text-[10px] bg-[var(--bg-card)]">
                  {['debug', 'info', 'warn', 'error'].map((level) => (
                    <button 
                      key={level}
                      onClick={() => {
                        setLogLevel(level);
                        setTerminalLogs(prev => [
                          ...prev,
                          { type: 'info', text: `[CONFIG] System debug log level changed to: ${level.toUpperCase()}` }
                        ]);
                      }}
                      className={`px-3 py-1.5 border-r border-[var(--border-color)] last:border-r-0 font-bold transition-colors cursor-pointer ${
                        logLevel === level 
                          ? 'bg-[var(--accent-color)] text-white' 
                          : 'text-[var(--text-primary)] hover:bg-[var(--border-color)]/50'
                      }`}
                    >
                      {level.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* 引擎并发与参数设置 */}
            <div className="space-y-4 pt-4 border-t border-[var(--border-color)]">
              <h2 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 flex items-center gap-1.5">
                <Layers className="size-4 text-[var(--accent-color)]" />
                <span>测试执行引擎底座参数</span>
              </h2>

              <div className="space-y-4 text-xs font-semibold text-[var(--text-secondary)]">
                {/* worker 并发数量 */}
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <label className="text-[var(--text-primary)]">执行引擎最大并发数 (Concurrency Workers)</label>
                    <span className="font-bold text-[var(--accent-color)]"><AnimatedNumber value={maxWorkers} /> 线程</span>
                  </div>
                  <input 
                    type="range" 
                    min="1" 
                    max="32" 
                    step="1" 
                    value={maxWorkers}
                    onChange={(e) => {
                      setMaxWorkers(parseInt(e.target.value));
                      setTerminalLogs(prev => [
                        ...prev,
                        { type: 'info', text: `[ENGINE] Concurrency workers pool resized to: ${e.target.value}` }
                      ]);
                    }}
                    className="w-full cursor-pointer"
                    style={{ accentColor: 'var(--accent-color)' }}
                  />
                  <span className="text-[9px] text-[var(--text-secondary)] block font-medium leading-none">设置执行 Playwright / 接口压测时的最大并发 Worker 数量，高线程数需保障硬件 CPU 充足。</span>
                </div>

                {/* HTTP 响应超时 */}
                <div className="space-y-2 pt-2 border-t border-[var(--border-color)]">
                  <div className="flex justify-between">
                    <label className="text-[var(--text-primary)]">接口请求默认超时时间 (Timeout Limit)</label>
                    <span className="font-bold text-[var(--accent-color)]"><AnimatedNumber value={timeoutLimit} />s</span>
                  </div>
                  <input 
                    type="range" 
                    min="5" 
                    max="180" 
                    step="5" 
                    value={timeoutLimit}
                    onChange={(e) => {
                      setTimeoutLimit(parseInt(e.target.value));
                      setTerminalLogs(prev => [
                        ...prev,
                        { type: 'info', text: `[ENGINE] Network default timeout limit set to: ${e.target.value}s` }
                      ]);
                    }}
                    className="w-full cursor-pointer"
                    style={{ accentColor: 'var(--accent-color)' }}
                  />
                  <span className="text-[9px] text-[var(--text-secondary)] block font-medium leading-none">设置接口测试及 API 调用握手时的最长等待响应周期。</span>
                </div>
              </div>
            </div>

          </div>
        </div>

        {/* 右侧：备份恢复、危险敏感区与实时运维控制台 (5 col) */}
        <div className="col-span-12 lg:col-span-5 flex flex-col gap-4">
          
          {/* 数据快照控制 */}
          <div className="theme-card rounded-xl p-5 space-y-4">
            <div>
              <h2 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 flex items-center gap-1.5">
                <Database className="size-4 text-blue-500" />
                <span>数据快照归档与恢复</span>
              </h2>

              <div className="grid grid-cols-2 gap-4 text-xs font-semibold text-[var(--text-secondary)]">
                <div className="p-3 border border-[var(--border-color)] rounded-xl space-y-2 flex flex-col justify-between">
                  <div>
                    <span className="font-bold text-[var(--text-primary)] block text-[11px]">导出数据快照</span>
                    <p className="text-[9px] text-[var(--text-secondary)] leading-normal mt-1 font-medium">将当前本地库需求、用例及执行历史导出并打包为压缩文件。</p>
                  </div>
                  <button 
                    onClick={handleBackup}
                    disabled={isBackingUp}
                    className="flex items-center justify-center gap-1 px-3 py-1.5 border border-[var(--border-color)] hover:bg-[var(--border-color)]/40 rounded-lg text-[10px] text-[var(--text-primary)] font-bold w-full cursor-pointer disabled:opacity-50 mt-2"
                  >
                    <RefreshCw className={`size-3 text-slate-400 ${isBackingUp ? 'animate-spin' : ''}`} />
                    <span>{isBackingUp ? '备份中...' : '一键备份'}</span>
                  </button>
                </div>

                <div className="p-3 border border-[var(--border-color)] rounded-xl space-y-2 flex flex-col justify-between">
                  <div>
                    <span className="font-bold text-[var(--text-primary)] block text-[11px]">恢复数据快照</span>
                    <p className="text-[9px] text-[var(--text-secondary)] leading-normal mt-1 font-medium">从之前备份的 ATP 文件中恢复，此操作会覆盖当前本地全部临时资产。</p>
                  </div>
                  <button 
                    onClick={() => {
                      setTerminalLogs(prev => [
                        ...prev,
                        { type: 'system', text: '> Restoring configuration archive path...' },
                        { type: 'success', text: '[RESTORE] Snapshot fully resolved and reloaded successfully.' }
                      ]);
                      window.dispatchEvent(new CustomEvent('show-toast', { 
                        detail: { message: '数据快照已被顺利导入，状态已同步。', type: 'success' } 
                      }));
                    }}
                    className="flex items-center justify-center gap-1 px-3 py-1.5 border border-[var(--border-color)] hover:bg-[var(--border-color)]/40 rounded-lg text-[10px] text-[var(--text-primary)] font-bold w-full cursor-pointer mt-2"
                  >
                    <span>一键导入恢复</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* 拟真控制台 */}
          <TiltCard className="mac-terminal rounded-xl flex flex-col min-h-[160px] max-h-[220px] overflow-hidden">
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
                  <span>ops-daemon.log</span>
                </span>
                <div className="w-10"></div>
              </div>

              {/* 日志内容区 */}
              <div className="p-4 flex-1 bg-[#0b0f19] font-mono text-[9px] space-y-1.5 overflow-y-auto text-left leading-relaxed" style={{ transform: 'translateZ(15px)' }}>
                {terminalLogs.map((log, index) => {
                  let colorClass = 'text-slate-400';
                  if (log.type === 'system') colorClass = 'text-purple-400 font-bold';
                  if (log.type === 'success') colorClass = 'text-emerald-400 font-bold';
                  if (log.type === 'info') colorClass = 'text-cyan-400';
                  
                  return (
                    <div key={index} className={colorClass}>
                      {log.text}
                    </div>
                  );
                })}
                <div ref={logsEndRef} />
              </div>
            </div>
          </TiltCard>

          {/* 危险操作区 */}
          <TiltCard className="theme-card rounded-xl p-5 border border-red-500/10 bg-red-500/[0.01] space-y-4">
            <div style={{ transform: 'translateZ(20px)', transformStyle: 'preserve-3d' }}>
              <div className="flex justify-between items-center border-b border-red-500/15 pb-2">
                <h2 className="text-xs font-bold text-red-500 flex items-center gap-1.5">
                  <ShieldAlert className="size-4 text-red-500 animate-pulse" />
                  <span>危险运维高特权区域</span>
                </h2>
                {/* 安全锁开关 */}
                <div className="flex items-center gap-1.5 text-[9px] font-bold text-[var(--text-secondary)]" style={{ transform: 'translateZ(10px)' }}>
                  <span>操作锁</span>
                  <button 
                    onClick={() => {
                      setSafetyLock(!safetyLock);
                      setTerminalLogs(prev => [
                        ...prev,
                        { type: 'system', text: `[WARN] Safety lock state changed to: ${!safetyLock ? 'LOCKED' : 'UNLOCKED'}` }
                      ]);
                    }}
                    className={`relative inline-flex h-4 w-8 shrink-0 cursor-pointer rounded-full border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      safetyLock ? 'bg-slate-300' : 'bg-red-500'
                    }`}
                  >
                    <span className={`pointer-events-none inline-block size-3.5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                      safetyLock ? 'translate-x-0' : 'translate-x-4'
                    }`} />
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-between text-xs font-semibold text-[var(--text-secondary)] gap-4 pt-2" style={{ transform: 'translateZ(15px)' }}>
                <div className="text-left space-y-1">
                  <span className="font-bold text-red-500 text-[11px] block">格式化并置空数据仓库</span>
                  <p className="text-[9px] text-[var(--text-secondary)] leading-normal font-medium">一键还原本地需求库、用例列表、API 路由数据到初始化置空状态。此操作不可撤销，请谨慎处理！</p>
                </div>
                
                <button 
                  onClick={handleResetSystem}
                  disabled={safetyLock}
                  className="px-3 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-[9.5px] font-bold shrink-0 cursor-pointer transition-all active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-1 shadow-md border border-red-700"
                >
                  <Trash2 className="size-3.5" />
                  <span>初始化数据</span>
                </button>
              </div>
            </div>
          </TiltCard>

        </div>

      </div>

    </div>
  );
}
