import React, { useEffect, useRef, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle,
  Clock,
  Cpu,
  Database,
  HardDrive,
  Layers,
  Lock,
  RefreshCw,
  Save,
  Settings,
  ShieldAlert,
  Terminal,
  Trash2
} from 'lucide-react';
import TiltCard from '../components/TiltCard';
import AnimatedNumber from '../components/AnimatedNumber';
import { apiGet, apiPost, formatDateTime } from '../lib/api';
import { useProjectContext } from '../lib/projectContext';

const isRecord = (value) => value && typeof value === 'object' && !Array.isArray(value);

const firstValue = (...values) => values.find((value) => value !== undefined && value !== null && value !== '');

const toFiniteNumber = (value, fallback = 0) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};

const formatCount = (value, fallback = '0') => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toLocaleString('zh-CN') : fallback;
};

const formatBytes = (value) => {
  const bytes = Number(value);
  if (!Number.isFinite(bytes)) return '--';
  if (bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const scaled = bytes / (1024 ** index);
  const digits = scaled >= 100 || index === 0 ? 0 : 1;
  return `${scaled.toFixed(digits)} ${units[index]}`;
};

const normalizeBool = (value) => value === true || value === 1 || value === '1' || String(value).toLowerCase() === 'true';

const normalizeModuleRows = (value) => {
  if (Array.isArray(value)) {
    return value.map((item, index) => {
      if (isRecord(item)) {
        return {
          name: firstValue(item.module, item.name, item.key, `module-${index + 1}`),
          records: toFiniteNumber(firstValue(item.records, item.record_count, item.recordCount), 0),
          files: toFiniteNumber(firstValue(item.files, item.file_count, item.fileCount), 0),
          bytes: toFiniteNumber(firstValue(item.bytes, item.byte_count, item.byteCount, item.size_bytes, item.sizeBytes), 0)
        };
      }
      return { name: String(item), records: 0, files: 0, bytes: 0 };
    });
  }

  if (isRecord(value)) {
    return Object.entries(value).map(([name, item]) => ({
      name,
      records: toFiniteNumber(firstValue(item?.records, item?.record_count, item?.recordCount), 0),
      files: toFiniteNumber(firstValue(item?.files, item?.file_count, item?.fileCount), 0),
      bytes: toFiniteNumber(firstValue(item?.bytes, item?.byte_count, item?.byteCount, item?.size_bytes, item?.sizeBytes), 0)
    }));
  }

  return [];
};

const normalizeStorageSummary = (payload) => {
  const source = isRecord(payload?.summary) ? payload.summary : (isRecord(payload) ? payload : {});
  const cache = isRecord(source.cache) ? source.cache : {};
  const cleanup = isRecord(source.cleanup) ? source.cleanup : {};
  const files = isRecord(source.files) ? source.files : {};
  const sections = isRecord(source.sections) ? source.sections : {};
  const sectionRows = normalizeModuleRows(sections);
  const moduleRows = normalizeModuleRows(firstValue(source.modules, cleanup.modules, sections.modules));
  const sectionBytes = sectionRows.reduce((sum, item) => sum + toFiniteNumber(item.bytes, 0), 0);
  const sectionFiles = sectionRows.reduce((sum, item) => sum + toFiniteNumber(item.files, 0), 0);
  const sectionRecords = sectionRows.reduce((sum, item) => sum + toFiniteNumber(item.records, 0), 0);
  const totalBytes = toFiniteNumber(firstValue(source.total_bytes, source.totalBytes, source.storage_bytes, source.storageBytes, sections.total?.bytes), sectionRows.length ? sectionBytes : NaN);
  const cacheBytes = toFiniteNumber(
    firstValue(
      source.cache_bytes,
      source.cacheBytes,
      cache.bytes,
      cleanup.bytes,
      source.reclaimable_bytes,
      source.reclaimableBytes,
      sections.artifacts?.bytes,
      sections.backups?.bytes
    ),
    Number.isFinite(totalBytes) ? totalBytes : NaN
  );

  return {
    totalBytes,
    cacheBytes,
    displayBytes: Number.isFinite(cacheBytes) ? cacheBytes : totalBytes,
    fileCount: toFiniteNumber(firstValue(source.file_count, source.fileCount, files.count, cleanup.file_count, cleanup.fileCount), sectionFiles),
    recordCount: toFiniteNumber(firstValue(source.record_count, source.recordCount, cleanup.record_count, cleanup.recordCount), sectionRecords),
    modules: moduleRows.length ? moduleRows : sectionRows,
    updatedAt: firstValue(source.updated_at, source.updatedAt, source.checked_at, source.checkedAt),
    raw: payload
  };
};

const normalizeBackupStatus = (payload) => {
  const source = isRecord(payload?.status) ? payload.status : (isRecord(payload) ? payload : {});
  const latest = firstValue(source.latest, source.latest_backup, source.latestBackup, source.last_backup, source.lastBackup, source.backup);
  const latestRecord = isRecord(latest) ? latest : {};
  return {
    lastBackupAt: firstValue(
      source.last_backup_at,
      source.lastBackupAt,
      latestRecord.created_at,
      latestRecord.createdAt,
      latestRecord.updated_at,
      latestRecord.updatedAt,
      typeof latest === 'string' ? latest : undefined
    ),
    needsBackup: normalizeBool(firstValue(source.needs_backup, source.needsBackup, source.required, source.is_required, false)),
    backupId: firstValue(source.backup_id, source.backupId, latestRecord.backup_id, latestRecord.id),
    reason: firstValue(source.reason, source.message, source.detail),
    raw: payload
  };
};

const normalizeCleanupImpact = (payload) => {
  const source = isRecord(payload?.impact)
    ? payload.impact
    : isRecord(payload?.preview)
      ? payload.preview
      : isRecord(payload?.result)
        ? payload.result
        : (isRecord(payload) ? payload : {});
  const modules = normalizeModuleRows(firstValue(source.modules, source.module_impacts, source.moduleImpacts));
  return {
    records: toFiniteNumber(firstValue(source.records, source.record_count, source.recordCount, source.affected_records, source.affectedRecords), 0),
    files: toFiniteNumber(firstValue(source.files, source.file_count, source.fileCount, source.affected_files, source.affectedFiles), 0),
    bytes: toFiniteNumber(firstValue(source.bytes, source.byte_count, source.byteCount, source.reclaimed_bytes, source.reclaimedBytes, source.size_bytes, source.sizeBytes), 0),
    modules,
    warnings: Array.isArray(source.warnings) ? source.warnings : [],
    raw: payload
  };
};

const CLEANUP_MODULE_OPTIONS = [
  { value: 'execution_history', label: '执行历史' },
  { value: 'api_execution_history', label: 'API 执行历史' },
  { value: 'artifacts', label: '运行产物' }
];

const DEFAULT_CLEANUP_MODULES = CLEANUP_MODULE_OPTIONS.map((option) => option.value);

export default function SettingsPage() {
  const { selectedProject } = useProjectContext();
  const [logLevel, setLogLevel] = useState('info');
  const [isBackingUp, setIsBackingUp] = useState(false);
  const [isDryRunningCleanup, setIsDryRunningCleanup] = useState(false);
  const [isExecutingCleanup, setIsExecutingCleanup] = useState(false);
  const [cleanupModules, setCleanupModules] = useState(DEFAULT_CLEANUP_MODULES);
  const [cleanupConfirm, setCleanupConfirm] = useState('');
  const [cleanupPreview, setCleanupPreview] = useState(null);
  const [cleanupResult, setCleanupResult] = useState(null);
  const [cleanupError, setCleanupError] = useState('');
  const [maxWorkers, setMaxWorkers] = useState(8);
  const [timeoutLimit, setTimeoutLimit] = useState(30);
  const [schemaStatus, setSchemaStatus] = useState(null);
  const [runtimeDeps, setRuntimeDeps] = useState(null);
  const [storageSummary, setStorageSummary] = useState(null);
  const [storageError, setStorageError] = useState('');
  const [backupStatus, setBackupStatus] = useState(null);
  const [backupError, setBackupError] = useState('');
  const [settingsApiState, setSettingsApiState] = useState({ status: 'loading', message: '' });
  const [terminalLogs, setTerminalLogs] = useState([
    { type: 'system', text: '> Settings console initialized.' },
    { type: 'info', text: '[SYNC] Waiting for backend system status.' }
  ]);

  const logsEndRef = useRef(null);

  const appendLog = (entry) => {
    setTerminalLogs((prev) => [...prev.slice(-80), entry]);
  };

  const showToast = (message, type = 'success') => {
    window.dispatchEvent(new CustomEvent('show-toast', { detail: { message, type } }));
  };

  const selectedCleanupModules = Array.from(new Set(
    cleanupModules.filter((moduleName) => DEFAULT_CLEANUP_MODULES.includes(moduleName))
  ));

  const updateCleanupModules = (moduleName, checked) => {
    setCleanupModules((prev) => {
      if (checked) return Array.from(new Set([...prev, moduleName]));
      return prev.filter((item) => item !== moduleName);
    });
    setCleanupPreview(null);
    setCleanupResult(null);
    setCleanupConfirm('');
    setCleanupError('');
  };

  const buildCleanupPayload = (dryRun) => {
    if (!selectedCleanupModules.length) {
      throw new Error('请至少选择一个清理模块。');
    }

    return {
      dry_run: dryRun,
      modules: selectedCleanupModules,
      module: selectedCleanupModules[0],
      project_id: selectedProject?.id || undefined
    };
  };

  const loadStorageSummary = async () => {
    setStorageError('');
    try {
      const payload = await apiGet('/system/storage-summary', {
        params: { projectId: selectedProject?.id || undefined }
      });
      const summary = normalizeStorageSummary(payload);
      setStorageSummary(summary);
      appendLog({ type: 'success', text: `[STORAGE] Summary loaded. Size: ${formatBytes(summary.displayBytes)}` });
    } catch (error) {
      const message = error?.message || '存储摘要接口不可用';
      setStorageSummary(null);
      setStorageError(message);
      appendLog({ type: 'system', text: `[STORAGE] ${message}` });
    }
  };

  const loadBackupStatus = async () => {
    setBackupError('');
    try {
      const payload = await apiGet('/system/backup-status', {
        params: { projectId: selectedProject?.id || undefined }
      });
      const status = normalizeBackupStatus(payload);
      setBackupStatus(status);
      appendLog({
        type: status.needsBackup ? 'info' : 'success',
        text: `[BACKUP] Last backup: ${formatDateTime(status.lastBackupAt)} | needs_backup=${status.needsBackup}`
      });
    } catch (error) {
      const message = error?.message || '备份状态接口不可用';
      setBackupStatus(null);
      setBackupError(message);
      appendLog({ type: 'system', text: `[BACKUP] ${message}` });
    }
  };

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [terminalLogs]);

  useEffect(() => {
    let cancelled = false;

    async function loadSystemSettings() {
      try {
        const [schema, preference, dependencies] = await Promise.all([
          apiGet('/system/schema-status'),
          apiGet('/system/preferences/runtime-settings').catch(() => null),
          apiGet('/system/runtime-dependencies').catch(() => null)
        ]);

        if (cancelled) return;
        setSchemaStatus(schema);
        setRuntimeDeps(dependencies);
        const value = preference?.value || {};
        if (value.logLevel) setLogLevel(value.logLevel);
        if (Number.isFinite(Number(value.maxWorkers))) setMaxWorkers(Number(value.maxWorkers));
        if (Number.isFinite(Number(value.timeoutLimit))) setTimeoutLimit(Number(value.timeoutLimit));
        setSettingsApiState({ status: 'online', message: '后端配置已同步' });
        appendLog({ type: 'success', text: `[SYNC] Schema ${(schema.status || 'unknown').toUpperCase()} | tables ${schema.tables_present || 0}/${schema.tables_total || 0}` });
      } catch (error) {
        if (!cancelled) {
          setSchemaStatus(null);
          setSettingsApiState({ status: 'offline', message: error?.message || '后端暂不可用，显示本地配置' });
          appendLog({ type: 'system', text: `[SYNC] Backend settings unavailable: ${error?.message || 'unknown error'}` });
        }
      }
    }

    loadSystemSettings();
    loadStorageSummary();
    loadBackupStatus();
    return () => {
      cancelled = true;
    };
  }, [selectedProject?.id]);

  const handleBackup = async () => {
    if (isBackingUp) return;
    setIsBackingUp(true);
    appendLog({ type: 'system', text: '> Creating backend backup snapshot...' });

    try {
      const snapshot = await apiPost('/system/backup', {
        name: `frontend-snapshot-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}`,
        project_id: selectedProject?.id || undefined
      });
      appendLog({ type: 'success', text: `[BACKUP] Snapshot created: ${snapshot.backup_id || snapshot.id || 'ok'}` });
      setSettingsApiState({ status: 'online', message: '后端备份已创建' });
      showToast('系统备份已创建，正在刷新备份状态。', 'success');
      await loadBackupStatus();
    } catch (error) {
      const message = error?.message || '备份请求失败';
      appendLog({ type: 'system', text: `[BACKUP] ${message}` });
      showToast(message, 'error');
    } finally {
      setIsBackingUp(false);
    }
  };

  const handleCleanupDryRun = async () => {
    if (isDryRunningCleanup) return;
    if (!selectedCleanupModules.length) {
      const message = '请至少选择一个清理模块。';
      setCleanupError(message);
      showToast(message, 'warning');
      return;
    }
    setCleanupError('');
    setCleanupResult(null);
    setCleanupConfirm('');
    setIsDryRunningCleanup(true);
    appendLog({ type: 'system', text: '> Running cleanup dry-run...' });

    try {
      const payload = await apiPost('/system/cleanup', buildCleanupPayload(true), { timeoutMs: 20000 });
      const impact = normalizeCleanupImpact(payload);
      setCleanupPreview(impact);
      appendLog({
        type: 'info',
        text: `[CLEANUP] Dry-run: records=${impact.records}, files=${impact.files}, bytes=${formatBytes(impact.bytes)}`
      });
      showToast('清理预检完成，请确认影响范围后再执行。', 'success');
    } catch (error) {
      const message = error?.message || '清理预检失败';
      setCleanupPreview(null);
      setCleanupError(message);
      appendLog({ type: 'system', text: `[CLEANUP] Dry-run failed: ${message}` });
      showToast(message, 'error');
    } finally {
      setIsDryRunningCleanup(false);
    }
  };

  const handleExecuteCleanup = async () => {
    if (isExecutingCleanup || cleanupConfirm !== 'CLEANUP') return;
    if (!cleanupPreview) {
      const message = '请先完成 dry-run 预检，再执行真实清理。';
      setCleanupError(message);
      showToast(message, 'warning');
      return;
    }
    if (!selectedCleanupModules.length) {
      const message = '请至少选择一个清理模块。';
      setCleanupError(message);
      showToast(message, 'warning');
      return;
    }
    setCleanupError('');
    setIsExecutingCleanup(true);
    appendLog({ type: 'system', text: '> Executing confirmed cleanup...' });

    try {
      const payload = await apiPost('/system/cleanup', {
        ...buildCleanupPayload(false),
        confirm_text: 'CLEANUP',
        confirm: 'CLEANUP',
        confirmation: 'CLEANUP'
      }, { timeoutMs: 30000 });
      const result = normalizeCleanupImpact(payload);
      setCleanupResult(result);
      setCleanupPreview(null);
      setCleanupConfirm('');
      appendLog({
        type: 'success',
        text: `[CLEANUP] Completed: records=${result.records}, files=${result.files}, reclaimed=${formatBytes(result.bytes)}`
      });
      showToast('清理已由后端执行完成。', 'success');
      await Promise.all([loadStorageSummary(), loadBackupStatus()]);
    } catch (error) {
      const message = error?.message || '清理执行失败';
      setCleanupError(message);
      appendLog({ type: 'system', text: `[CLEANUP] Execute failed: ${message}` });
      showToast(message, 'error');
    } finally {
      setIsExecutingCleanup(false);
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
      appendLog({ type: 'success', text: `[CONFIG] Runtime settings persisted: ${saved.key || 'runtime-settings'}` });
      showToast('系统运行参数已保存。', 'success');
    } catch (error) {
      const message = error?.message || '配置保存失败';
      setSettingsApiState({ status: 'offline', message });
      appendLog({ type: 'system', text: `[CONFIG] Save failed: ${message}` });
      showToast(message, 'error');
    }
  };

  const cleanupImpact = cleanupResult || cleanupPreview;
  const cleanupImpactLabel = cleanupResult ? '最近清理结果' : '清理预检影响';

  return (
    <div className="space-y-5 text-left transition-all duration-200 w-full pb-10">
      <div className="flex flex-col md:flex-row md:justify-between md:items-center gap-3 bg-[var(--bg-card)] border border-[var(--border-color)] rounded-xl p-4 shadow-sm">
        <div>
          <h1 className="text-base font-bold text-[var(--text-primary)]">系统设置</h1>
          <p className="text-[11px] text-[var(--text-secondary)] mt-1">
            管理运行参数、存储清理和备份状态。当前项目：{selectedProject?.name || selectedProject?.code || '未选择'}
          </p>
        </div>
        <button
          onClick={handleSaveSettings}
          className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg accent-btn text-[11px] font-bold text-white cursor-pointer shadow-sm"
        >
          <Save className="size-3.5" />
          <span>保存配置</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <div className="theme-card rounded-xl p-4 flex flex-col justify-between border min-h-[96px]">
          <div className="flex items-center justify-between text-[10px] opacity-70 text-[var(--text-secondary)] font-medium">
            <span>核心服务状态</span>
            <Activity className={`size-3.5 ${settingsApiState.status === 'online' ? 'text-emerald-500 animate-pulse' : 'text-amber-500'}`} />
          </div>
          <div className="mt-2 flex flex-col">
            <span className="text-sm font-bold text-[var(--text-primary)]">
              {settingsApiState.status === 'online' ? '健康在线' : settingsApiState.status === 'loading' ? '同步中' : '离线降级'}
            </span>
            <span className="text-[9px] opacity-60 mt-1 break-words">{settingsApiState.message || '等待后端响应'}</span>
          </div>
        </div>

        <div className="theme-card rounded-xl p-4 flex flex-col justify-between border min-h-[96px]">
          <div className="flex items-center justify-between text-[10px] opacity-70 text-[var(--text-secondary)] font-medium">
            <span>数据卷规格</span>
            <Cpu className="size-3.5 text-blue-500" />
          </div>
          <div className="mt-2 flex flex-col">
            <span className="text-sm font-bold text-[var(--text-primary)]">
              {(schemaStatus?.database_url_type || 'SQLite').toUpperCase()} / <AnimatedNumber value={schemaStatus?.tables_present || 0} /> tables
            </span>
            <span className="text-[9px] opacity-60 mt-1">Schema: {schemaStatus?.schema_version || 'unknown'}</span>
          </div>
        </div>

        <div className="theme-card rounded-xl p-4 flex flex-col justify-between border min-h-[96px]">
          <div className="flex items-center justify-between text-[10px] opacity-70 text-[var(--text-secondary)] font-medium">
            <span>后端存储占用</span>
            <HardDrive className="size-3.5 text-purple-500" />
          </div>
          <div className="mt-2 flex flex-col">
            <span className="text-sm font-bold text-[var(--text-primary)]">{formatBytes(storageSummary?.displayBytes)}</span>
            <span className="text-[9px] opacity-60 mt-1">
              文件 {formatCount(storageSummary?.fileCount)} / 记录 {formatCount(storageSummary?.recordCount)}
            </span>
            {storageError && <span className="text-[9px] text-red-500 mt-1 break-words">{storageError}</span>}
          </div>
        </div>

        <div className="theme-card rounded-xl p-4 flex flex-col justify-between border min-h-[96px]">
          <div className="flex items-center justify-between text-[10px] opacity-70 text-[var(--text-secondary)] font-medium">
            <span>备份提醒</span>
            <Clock className={`size-3.5 ${backupStatus?.needsBackup ? 'text-amber-500' : 'text-emerald-500'}`} />
          </div>
          <div className="mt-2 flex flex-col">
            <span className={`text-sm font-bold ${backupStatus?.needsBackup ? 'text-amber-500' : 'text-[var(--text-primary)]'}`}>
              {backupError ? '状态不可用' : backupStatus ? (backupStatus.needsBackup ? '需要备份' : '备份状态正常') : '加载中'}
            </span>
            <span className="text-[9px] opacity-60 mt-1">Last backup: {formatDateTime(backupStatus?.lastBackupAt)}</span>
            {backupError && <span className="text-[9px] text-red-500 mt-1 break-words">{backupError}</span>}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-5 w-full">
        <div className="col-span-12 lg:col-span-7 flex flex-col gap-4">
          <div className="theme-card rounded-xl p-5 space-y-5">
            <div className="space-y-3">
              <h2 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 flex items-center gap-1.5">
                <Settings className="size-4 text-[var(--accent-color)]" />
                <span>日志策略配置</span>
              </h2>
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 text-xs font-semibold text-[var(--text-secondary)]">
                <span>系统调试日志输出级别</span>
                <div className="flex rounded-lg overflow-hidden border border-[var(--border-color)] text-[10px] bg-[var(--bg-card)] w-fit">
                  {['debug', 'info', 'warn', 'error'].map((level) => (
                    <button
                      key={level}
                      onClick={() => {
                        setLogLevel(level);
                        appendLog({ type: 'info', text: `[CONFIG] Log level changed to ${level.toUpperCase()}` });
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

            <div className="space-y-4 pt-4 border-t border-[var(--border-color)]">
              <h2 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 flex items-center gap-1.5">
                <Layers className="size-4 text-[var(--accent-color)]" />
                <span>测试执行引擎参数</span>
              </h2>

              <div className="space-y-4 text-xs font-semibold text-[var(--text-secondary)]">
                <div className="space-y-2">
                  <div className="flex justify-between gap-3">
                    <label className="text-[var(--text-primary)]">最大并发数 (Concurrency Workers)</label>
                    <span className="font-bold text-[var(--accent-color)]"><AnimatedNumber value={maxWorkers} /> 线程</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="32"
                    step="1"
                    value={maxWorkers}
                    onChange={(event) => setMaxWorkers(parseInt(event.target.value, 10))}
                    className="w-full cursor-pointer"
                    style={{ accentColor: 'var(--accent-color)' }}
                  />
                  <span className="text-[9px] text-[var(--text-secondary)] block font-medium leading-normal">
                    用于控制 Playwright / API 调试等执行器的并发上限。
                  </span>
                </div>

                <div className="space-y-2 pt-2 border-t border-[var(--border-color)]">
                  <div className="flex justify-between gap-3">
                    <label className="text-[var(--text-primary)]">默认超时时间 (Timeout Limit)</label>
                    <span className="font-bold text-[var(--accent-color)]"><AnimatedNumber value={timeoutLimit} />s</span>
                  </div>
                  <input
                    type="range"
                    min="5"
                    max="180"
                    step="5"
                    value={timeoutLimit}
                    onChange={(event) => setTimeoutLimit(parseInt(event.target.value, 10))}
                    className="w-full cursor-pointer"
                    style={{ accentColor: 'var(--accent-color)' }}
                  />
                  <span className="text-[9px] text-[var(--text-secondary)] block font-medium leading-normal">
                    用于接口调试、执行任务和外部请求的默认等待周期。
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="theme-card rounded-xl p-5 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-[var(--border-color)] pb-3">
              <h2 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
                <Trash2 className="size-4 text-red-500" />
                <span>数据清理流程</span>
              </h2>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={loadStorageSummary}
                  className="flex items-center gap-1 px-2.5 py-1.5 border border-[var(--border-color)] rounded-lg text-[10px] font-bold text-[var(--text-primary)] hover:bg-[var(--border-color)]/40"
                >
                  <RefreshCw className="size-3" />
                  <span>刷新摘要</span>
                </button>
                <button
                  onClick={handleCleanupDryRun}
                  disabled={isDryRunningCleanup || isExecutingCleanup || !selectedCleanupModules.length}
                  className="flex items-center gap-1 px-3 py-1.5 bg-red-500/10 hover:bg-red-500/15 text-red-500 border border-red-500/20 rounded-lg text-[10px] font-bold disabled:opacity-60"
                >
                  <AlertTriangle className="size-3" />
                  <span>{isDryRunningCleanup ? '预检中...' : 'Dry-run 预检'}</span>
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              {CLEANUP_MODULE_OPTIONS.map((option) => (
                <label
                  key={option.value}
                  className="flex items-center gap-2 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/20 px-3 py-2 text-[10px] font-bold text-[var(--text-secondary)]"
                >
                  <input
                    type="checkbox"
                    checked={selectedCleanupModules.includes(option.value)}
                    disabled={isDryRunningCleanup || isExecutingCleanup}
                    onChange={(event) => updateCleanupModules(option.value, event.target.checked)}
                    className="size-3"
                    style={{ accentColor: 'rgb(239 68 68)' }}
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
              <div className="p-3 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30">
                <div className="text-[9px] text-[var(--text-secondary)] font-bold">记录影响</div>
                <div className="text-base font-bold text-[var(--text-primary)] mt-1">{formatCount(cleanupImpact?.records)}</div>
              </div>
              <div className="p-3 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30">
                <div className="text-[9px] text-[var(--text-secondary)] font-bold">文件影响</div>
                <div className="text-base font-bold text-[var(--text-primary)] mt-1">{formatCount(cleanupImpact?.files)}</div>
              </div>
              <div className="p-3 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30">
                <div className="text-[9px] text-[var(--text-secondary)] font-bold">字节影响</div>
                <div className="text-base font-bold text-[var(--text-primary)] mt-1">{formatBytes(cleanupImpact?.bytes)}</div>
              </div>
            </div>

            <div className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/20 p-3">
              <div className="text-[10px] font-bold text-[var(--text-primary)] mb-2">{cleanupImpactLabel}</div>
              {cleanupImpact ? (
                <div className="space-y-2">
                  {cleanupImpact.modules.length ? cleanupImpact.modules.map((item) => (
                    <div key={item.name} className="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_80px_80px_96px] gap-2 text-[10px] text-[var(--text-secondary)]">
                      <span className="font-bold text-[var(--text-primary)] truncate">{item.name}</span>
                      <span>记录 {formatCount(item.records)}</span>
                      <span>文件 {formatCount(item.files)}</span>
                      <span>{formatBytes(item.bytes)}</span>
                    </div>
                  )) : (
                    <div className="text-[10px] text-[var(--text-secondary)]">后端未返回模块明细。</div>
                  )}
                  {cleanupImpact.warnings.map((warning, index) => (
                    <div key={index} className="text-[10px] text-amber-500">{String(warning)}</div>
                  ))}
                </div>
              ) : (
                <div className="text-[10px] text-[var(--text-secondary)]">先运行 dry-run，页面会展示真实影响范围；不会模拟成功结果。</div>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_auto] gap-3 items-end">
              <label className="text-[10px] font-bold text-[var(--text-secondary)]">
                输入确认文本 CLEANUP 后执行真实清理
                <input
                  value={cleanupConfirm}
                  onChange={(event) => setCleanupConfirm(event.target.value)}
                  placeholder="CLEANUP"
                  className="mt-1 w-full px-3 py-2 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30 text-[11px] text-[var(--text-primary)] font-mono focus:outline-none focus:border-red-500"
                />
              </label>
              <button
                onClick={handleExecuteCleanup}
                disabled={!cleanupPreview || cleanupConfirm !== 'CLEANUP' || isExecutingCleanup || !selectedCleanupModules.length}
                className="flex items-center justify-center gap-1 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-[10px] font-bold disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Lock className="size-3.5" />
                <span>{isExecutingCleanup ? '执行中...' : '执行清理'}</span>
              </button>
            </div>

            {cleanupError && (
              <div className="rounded-lg border border-red-500/25 bg-red-500/10 text-red-500 text-[10px] p-3 break-words">
                {cleanupError}
              </div>
            )}
          </div>
        </div>

        <div className="col-span-12 lg:col-span-5 flex flex-col gap-4">
          <div className="theme-card rounded-xl p-5 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-[var(--border-color)] pb-3">
              <h2 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
                <Database className="size-4 text-blue-500" />
                <span>备份状态</span>
              </h2>
              <button
                onClick={loadBackupStatus}
                className="flex items-center justify-center gap-1 px-2.5 py-1.5 border border-[var(--border-color)] rounded-lg text-[10px] font-bold text-[var(--text-primary)] hover:bg-[var(--border-color)]/40"
              >
                <RefreshCw className="size-3" />
                <span>刷新</span>
              </button>
            </div>

            <div className={`rounded-lg border p-3 text-[10px] ${
              backupError
                ? 'border-red-500/25 bg-red-500/10 text-red-500'
                : backupStatus?.needsBackup
                  ? 'border-amber-500/25 bg-amber-500/10 text-amber-600 dark:text-amber-400'
                  : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
            }`}>
              <div className="flex items-center gap-1.5 font-bold">
                {backupError || backupStatus?.needsBackup ? <AlertTriangle className="size-3.5" /> : <CheckCircle className="size-3.5" />}
                <span>{backupError ? '备份状态不可用' : backupStatus ? (backupStatus.needsBackup ? '后端提示需要备份' : '备份状态正常') : '正在加载备份状态'}</span>
              </div>
              <div className="mt-1 text-[var(--text-secondary)]">
                Last backup: {formatDateTime(backupStatus?.lastBackupAt)}
                {backupStatus?.backupId ? ` / #${backupStatus.backupId}` : ''}
              </div>
              {backupStatus?.reason && <div className="mt-1">{backupStatus.reason}</div>}
              {backupError && <div className="mt-1 text-red-500 break-words">{backupError}</div>}
            </div>

            <button
              onClick={handleBackup}
              disabled={isBackingUp}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-2 border border-[var(--border-color)] hover:bg-[var(--border-color)]/40 rounded-lg text-[10px] text-[var(--text-primary)] font-bold cursor-pointer disabled:opacity-60"
            >
              <RefreshCw className={`size-3.5 text-[var(--text-secondary)] ${isBackingUp ? 'animate-spin' : ''}`} />
              <span>{isBackingUp ? '备份中...' : '创建后端备份'}</span>
            </button>
          </div>

          <div className="theme-card rounded-xl p-5 space-y-3 border border-red-500/10 bg-red-500/[0.01]">
            <h2 className="text-xs font-bold text-red-500 flex items-center gap-1.5 border-b border-red-500/15 pb-2">
              <ShieldAlert className="size-4 text-red-500" />
              <span>高风险操作说明</span>
            </h2>
            <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
              本页不再提供模拟恢复、模拟初始化数据或假清理成功。涉及恢复、初始化、重置数据的操作必须由后端提供真实接口和审计结果后再接入。
            </p>
          </div>

          <TiltCard className="mac-terminal rounded-xl flex flex-col min-h-[220px] max-h-[300px] overflow-hidden">
            <div style={{ transform: 'translateZ(20px)', transformStyle: 'preserve-3d', display: 'flex', flexDirection: 'column', height: '100%' }}>
              <div className="flex items-center justify-between px-4 py-2 bg-[#141b2a] border-b border-[#223049] select-none shrink-0" style={{ transform: 'translateZ(10px)' }}>
                <div className="flex items-center gap-2">
                  <span className="size-2.5 rounded-full bg-[#ff5f56]" />
                  <span className="size-2.5 rounded-full bg-[#ffbd2e]" />
                  <span className="size-2.5 rounded-full bg-[#27c93f]" />
                </div>
                <span className="text-[10px] text-slate-500 font-mono font-bold flex items-center gap-1.5">
                  <Terminal className="size-3" />
                  <span>ops-daemon.log</span>
                </span>
                <div className="w-10" />
              </div>

              <div className="p-4 flex-1 bg-[#0b0f19] font-mono text-[9px] space-y-1.5 overflow-y-auto text-left leading-relaxed" style={{ transform: 'translateZ(15px)' }}>
                {terminalLogs.map((log, index) => {
                  let colorClass = 'text-slate-400';
                  if (log.type === 'system') colorClass = 'text-red-300 font-bold';
                  if (log.type === 'success') colorClass = 'text-emerald-400 font-bold';
                  if (log.type === 'info') colorClass = 'text-cyan-400';
                  return (
                    <div key={`${log.text}-${index}`} className={colorClass}>
                      {log.text}
                    </div>
                  );
                })}
                <div ref={logsEndRef} />
              </div>
            </div>
          </TiltCard>

          <div className="theme-card rounded-xl p-4 flex flex-col gap-2">
            <div className="text-[10px] font-bold text-[var(--text-primary)]">执行器依赖</div>
            <div className="text-[9px] text-[var(--text-secondary)] leading-relaxed">
              Playwright: {runtimeDeps?.auto_runner?.playwright?.status || 'unknown'} / JMeter: {runtimeDeps?.perf_runner?.jmeter?.status || 'unknown'}
            </div>
            <div className="text-[9px] text-[var(--text-secondary)]">检查时间：{formatDateTime(runtimeDeps?.checked_at || schemaStatus?.checked_at)}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
