import React, { useState } from 'react';
import { 
  Play, 
  RotateCcw, 
  ChevronDown, 
  Search, 
  Sliders,
  CheckCircle,
  XCircle,
  AlertTriangle,
  FileImage,
  Sparkles,
  ExternalLink,
  ChevronRight,
  ChevronLeft,
  ArrowLeft
} from 'lucide-react';
import TiltCard from '../components/TiltCard';
import AnimatedNumber from '../components/AnimatedNumber';
import { apiGet, apiPost, downloadTextFile, formatDateTime, pickList } from '../lib/api';
import { useProjectContext } from '../lib/projectContext';

const DEMO_PROJECT_NAME = 'AI 测试演示项目';
const TEST_CASE_PAGE_SIZE = 50;

const numberText = (value, fallback = '0') => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toLocaleString('zh-CN') : fallback;
};

const toFiniteNumber = (value, fallback = 0) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};

const clampPercent = (value) => Math.max(0, Math.min(100, value));

const toPercentLabel = (part, total, fallback = '0%') => {
  const totalNum = Number(total);
  const partNum = Number(part);
  if (!Number.isFinite(totalNum) || totalNum <= 0 || !Number.isFinite(partNum)) return fallback;
  return `${clampPercent((partNum / totalNum) * 100).toFixed(1)}%`;
};

const parsePercent = (value, fallback = 0) => {
  const num = Number(String(value || '').replace('%', ''));
  return Number.isFinite(num) ? clampPercent(num) : fallback;
};

const formatSeconds = (value) => {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return '—';
  return `${Math.round(seconds)}s`;
};

const caseCode = (id) => `TC-${String(id || 0).padStart(6, '0')}`;
const defectCode = (id) => `DEF-${String(id || 0).padStart(6, '0')}`;

const formatTimeOnly = (value) => {
  const full = formatDateTime(value);
  if (!full || full === '--') return '—';
  return full.split(' ')[1] || full;
};

const mapExecutionStatus = (status) => {
  const normalized = String(status || '').toLowerCase();
  if (['pass', 'passed', 'success', 'succeeded'].includes(normalized)) return '通过';
  if (['fail', 'failed', 'failure', 'error'].includes(normalized)) return '失败';
  if (['block', 'blocked'].includes(normalized)) return '阻塞';
  if (['skip', 'skipped'].includes(normalized)) return '跳过';
  return status ? String(status) : '待执行';
};

const isFailedOrBlocked = (status) => ['失败', '阻塞'].includes(mapExecutionStatus(status));

const mapRoundStatus = (round) => {
  const normalized = String(round?.status || '').toLowerCase();
  if (toFiniteNumber(round?.fail_count) || toFiniteNumber(round?.block_count)) return '部分失败';
  if (['completed', 'complete', 'done', 'success'].includes(normalized)) return '成功';
  if (['in_progress', 'running', 'pending'].includes(normalized)) return '进行中';
  return round?.status || '待执行';
};

const executionStatusClass = (status) => {
  if (status === '通过') return 'text-emerald-600 bg-emerald-500/10 border-emerald-500/20';
  if (status === '失败') return 'text-red-500 bg-red-500/10 border-red-500/20';
  if (status === '阻塞') return 'text-amber-500 bg-amber-500/10 border-amber-500/20';
  return 'text-blue-500 bg-blue-500/10 border-blue-500/20';
};

const executionTextClass = (status) => {
  if (status === '失败') return 'text-red-500 font-bold';
  if (status === '通过') return 'text-emerald-500';
  if (status === '阻塞') return 'text-amber-500';
  return 'text-blue-500';
};

const mapDefectSeverity = (severity) => {
  const normalized = String(severity || '').toLowerCase();
  if (['fatal', 'blocker', 'critical'].includes(normalized)) return normalized === 'fatal' ? '致命' : '严重';
  if (['high', 'major'].includes(normalized)) return '高';
  if (['medium', 'normal'].includes(normalized)) return '中';
  if (['low', 'minor'].includes(normalized)) return '低';
  return severity || '中';
};

const mapDefectStatus = (status) => {
  const normalized = String(status || '').toLowerCase();
  if (['open', 'new'].includes(normalized)) return '待修复';
  if (['in_progress', 'processing'].includes(normalized)) return '进行中';
  if (['resolved', 'verified'].includes(normalized)) return '待验证';
  if (['closed', 'done'].includes(normalized)) return '已关闭';
  return status || '待修复';
};

const defectStatusClass = (status) => {
  const normalized = String(status || '').toLowerCase();
  if (['closed', 'done'].includes(normalized)) return 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20';
  if (['resolved', 'verified'].includes(normalized)) return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
  if (['in_progress', 'processing'].includes(normalized)) return 'bg-amber-500/10 text-amber-500 border-amber-500/20';
  return 'bg-red-500/10 text-red-500 border-red-500/20';
};

const mapBackendDefect = (defect, casesById = new Map()) => {
  const rawCase = casesById.get(Number(defect.case_id)) || {};
  return {
    id: defect.defect_number || defectCode(defect.id),
    backendId: defect.id,
    caseBackendId: defect.case_id,
    title: defect.title || `缺陷 #${defect.id}`,
    severity: mapDefectSeverity(defect.severity),
    assignee: defect.assignee || '未分配',
    status: mapDefectStatus(defect.status),
    statusBg: defectStatusClass(defect.status),
    caseId: rawCase.case_number || (defect.case_id ? caseCode(defect.case_id) : '—'),
    time: formatDateTime(defect.updated_at || defect.created_at),
    raw: defect
  };
};

const mapBackendExecutionRow = (execution, casesById = new Map(), defectsByCase = new Map()) => {
  const rawCase = casesById.get(Number(execution.case_id)) || {};
  const status = mapExecutionStatus(execution.status);
  const defect = defectsByCase.get(Number(execution.case_id));

  return {
    id: rawCase.case_number || caseCode(execution.case_id),
    backendId: execution.case_id,
    backendExecutionId: execution.id,
    roundId: execution.round_id,
    title: rawCase.title || `测试用例 #${execution.case_id}`,
    priority: rawCase.priority || 'P2',
    status,
    actual: status,
    duration: formatSeconds(execution.execution_time),
    bug: defect?.id || '—',
    user: execution.executor_type || '后端',
    time: formatTimeOnly(execution.executed_at),
    date: formatDateTime(execution.executed_at),
    expected: rawCase.expected_result || '后端测试用例未提供预期结果。',
    actualDetail: execution.actual_result || execution.block_reason || execution.pass_remark || `${status}。`,
    raw: execution,
    rawCase
  };
};

const mapBackendCaseRow = (testCase, latestExecution, defectsByCase) => {
  if (latestExecution) {
    const casesById = new Map([[Number(testCase.id), testCase]]);
    return mapBackendExecutionRow(latestExecution, casesById, defectsByCase);
  }

  return {
    id: testCase.case_number || caseCode(testCase.id),
    backendId: testCase.id,
    title: testCase.title || `测试用例 #${testCase.id}`,
    priority: testCase.priority || 'P2',
    status: '待执行',
    actual: '待执行',
    duration: '—',
    bug: '—',
    user: '后端',
    time: '—',
    date: '-- --',
    expected: testCase.expected_result || '后端测试用例未提供预期结果。',
    actualDetail: '尚未产生执行记录。',
    rawCase: testCase
  };
};

const buildExecutionRows = (testCases, executions, defects) => {
  const casesById = new Map(testCases.map((item) => [Number(item.id), item]));
  const mappedDefects = defects.map((item) => mapBackendDefect(item, casesById));
  const defectsByCase = new Map();
  mappedDefects.forEach((defect) => {
    if (defect.caseBackendId && !defectsByCase.has(Number(defect.caseBackendId))) {
      defectsByCase.set(Number(defect.caseBackendId), defect);
    }
  });

  const sortedExecutions = [...executions].sort((a, b) => {
    const timeDiff = new Date(b.executed_at || b.created_at || 0).getTime() - new Date(a.executed_at || a.created_at || 0).getTime();
    if (timeDiff) return timeDiff;
    return toFiniteNumber(b.id) - toFiniteNumber(a.id);
  });
  const latestByCase = new Map();
  sortedExecutions.forEach((item) => {
    if (!latestByCase.has(Number(item.case_id))) latestByCase.set(Number(item.case_id), item);
  });

  const caseRows = testCases.map((item) => mapBackendCaseRow(item, latestByCase.get(Number(item.id)), defectsByCase));
  const extraRows = sortedExecutions
    .filter((item) => !casesById.has(Number(item.case_id)))
    .map((item) => mapBackendExecutionRow(item, casesById, defectsByCase));

  return { rows: [...caseRows, ...extraRows], defects: mappedDefects };
};

const buildStatsFromBackend = (statistics, rows, defects) => {
  const executedRows = rows.filter((row) => row.status !== '待执行');
  const total = toFiniteNumber(statistics?.total, executedRows.length);
  const passed = toFiniteNumber(statistics?.passed, executedRows.filter((row) => row.status === '通过').length);
  const failed = toFiniteNumber(statistics?.failed, executedRows.filter((row) => row.status === '失败').length);
  const blocked = toFiniteNumber(statistics?.blocked, executedRows.filter((row) => row.status === '阻塞').length);
  const totalCases = rows.length || total;
  const passRate = toPercentLabel(passed, total, total ? '0.0%' : '0%');
  const progressRate = totalCases ? clampPercent((total / totalCases) * 100) : 0;
  const remaining = Math.max(totalCases - total, 0);
  const avgSeconds = executedRows.reduce((sum, row) => sum + toFiniteNumber(row.raw?.execution_time), 0) / Math.max(executedRows.length, 1);
  const remainingMinutes = avgSeconds ? Math.ceil((remaining * avgSeconds) / 60) : 0;
  const severeCount = defects.filter((item) => ['致命', '严重'].includes(item.severity)).length;
  const highCount = defects.filter((item) => item.severity === '高').length;
  const mediumCount = defects.filter((item) => item.severity === '中').length;
  const lowCount = defects.filter((item) => item.severity === '低').length;

  return [
    { label: '用例通过率', val: passRate, detail: `通过 ${passed} | 失败 ${failed} | 阻塞 ${blocked}`, hasPie: true, pieRate: parsePercent(passRate) },
    { label: '执行进度', val: `${numberText(total)} / ${numberText(totalCases)}`, detail: `已执行 ${numberText(total)} | 进度 ${progressRate.toFixed(1)}%`, hasProgress: true, progressRate },
    { label: '预计剩余时间', val: remainingMinutes ? `${remainingMinutes}m` : '0m', detail: remaining ? `平均耗时: ${Math.round(avgSeconds || 0)}s/条 | 剩余: ${remaining}条` : '已全部执行完毕' },
    { label: '缺陷统计', val: numberText(defects.length), detail: `严重 ${severeCount} | 高 ${highCount} | 中 ${mediumCount} | 低 ${lowCount}`, change: '后端同步' },
    { label: '稳定性趋势', val: passRate, detail: `最近执行通过率 ${passRate}`, hasTrend: true }
  ];
};

const buildRunCards = (executions, rounds = []) => {
  const groups = new Map();
  executions.forEach((item) => {
    const key = item.round_id || `exec-${item.id}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  });

  const executionCards = Array.from(groups.entries())
    .map(([key, items]) => {
      const sorted = [...items].sort((a, b) => new Date(b.executed_at || 0).getTime() - new Date(a.executed_at || 0).getTime());
      const latest = sorted[0] || {};
      const pass = items.filter((item) => mapExecutionStatus(item.status) === '通过').length;
      const fail = items.filter((item) => mapExecutionStatus(item.status) === '失败').length;
      const block = items.filter((item) => mapExecutionStatus(item.status) === '阻塞').length;
      const rate = toPercentLabel(pass, items.length, '0%');
      return {
        runId: latest.round_id ? `Round #${latest.round_id}` : `EXEC #${String(key).replace('exec-', '')}`,
        roundBackendId: latest.round_id,
        time: formatDateTime(latest.executed_at),
        cases: items.length,
        pass,
        fail,
        block,
        rate,
        status: fail || block ? '部分失败' : '成功',
        color: fail || block ? 'text-amber-500' : 'text-emerald-500',
        latestAt: latest.executed_at
      };
    })
    .sort((a, b) => new Date(b.latestAt || 0).getTime() - new Date(a.latestAt || 0).getTime());

  const existingRoundIds = new Set(executionCards.map((card) => String(card.roundBackendId || '')).filter(Boolean));
  const roundCards = rounds
    .filter((round) => round?.id && !existingRoundIds.has(String(round.id)))
    .map((round) => {
      const total = toFiniteNumber(round.total_count);
      const pass = toFiniteNumber(round.pass_count);
      const fail = toFiniteNumber(round.fail_count);
      const block = toFiniteNumber(round.block_count);
      const status = mapRoundStatus(round);
      return {
        runId: `Round #${round.id}`,
        roundBackendId: round.id,
        time: formatDateTime(round.updated_at || round.created_at),
        cases: total,
        pass,
        fail,
        block,
        rate: toPercentLabel(pass, total, total ? '0.0%' : '0%'),
        status,
        color: status === '成功' ? 'text-emerald-500' : 'text-amber-500',
        latestAt: round.updated_at || round.created_at
      };
    });

  return [...executionCards, ...roundCards]
    .sort((a, b) => new Date(b.latestAt || 0).getTime() - new Date(a.latestAt || 0).getTime())
    .slice(0, 5);
};

const fetchProjectTestCases = async (projectId) => {
  const payload = await apiGet(`/projects/${projectId}/test-cases`, {
    params: { page: 1, pageSize: TEST_CASE_PAGE_SIZE }
  }).catch(() => null);
  return { payload, list: pickList(payload) };
};

const toActiveCase = (row) => ({
  id: row.id,
  title: row.title,
  priority: row.priority,
  status: row.status,
  expected: row.expected || '当执行正常登录流程时，结果需与预期文案完全匹配一致。',
  actual: row.actualDetail || (row.status === '失败' ? '由于内容校验失败，后端报错 400 Bad Request。' : '全部通过，断言状态 200。'),
  time: row.duration,
  date: row.date || '-- --',
  user: row.user,
  bug: row.bug
});

const countCaseStatuses = (rows) => rows.reduce((acc, row) => {
  acc.total += 1;
  if (row.status === '通过') acc.pass += 1;
  if (row.status === '失败') acc.fail += 1;
  if (row.status === '阻塞') acc.block += 1;
  return acc;
}, { total: 0, pass: 0, fail: 0, block: 0 });

export default function Execution() {
  const { selectedProject, loading: projectLoading, error: projectError } = useProjectContext();
  const [viewMode, setViewMode] = useState('list'); // 'list' or 'history-records'
  const [activeCase, setActiveCase] = useState({
    id: 'TC-20250520-0002',
    title: '用户登录-密码错误提示',
    priority: 'P1',
    status: '失败',
    expected: '当用户输入错误密码时，系统应提示“密码错误，请重新输入”。',
    actual: '系统提示“登录失败”，未明确提示密码错误错误。',
    time: '21s',
    date: '2025-05-20 10:25:18',
    user: '李华',
    bug: 'BUG-20250520-0248'
  });

  const historyBugs = [
    { id: 'BUG-20250520-0248', title: '用户登录密码错误时系统提示登录失败，未明确提示密码错误', severity: '严重', assignee: '李华', status: '进行中', statusBg: 'bg-amber-500/10 text-amber-500 border-amber-500/20', caseId: 'TC-20250520-0002', time: '2025-05-20 10:25' },
    { id: 'BUG-20250520-0255', title: '用户登录验证码接口响应超时导致阻塞', severity: '高', assignee: '王芳', status: '待验证', statusBg: 'bg-blue-500/10 text-blue-500 border-blue-500/20', caseId: 'TC-20250520-0004', time: '2025-05-20 10:24' },
    { id: 'BUG-20250520-0239', title: '修改昵称输入超长字符串时前端表单发生越界闪退', severity: '致命', assignee: '赵强', status: '待修复', statusBg: 'bg-red-500/10 text-red-500 border-red-500/20', caseId: 'TC-20250520-0007', time: '2025-05-20 10:24' },
    { id: 'BUG-20250519-0112', title: '移动端App在低电量或无网络时发送消息未进行本地缓存丢包', severity: '高', assignee: '刘洋', status: '已关闭', statusBg: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20', caseId: 'TC-20250519-0824', time: '2025-05-19 14:22' },
    { id: 'BUG-20250519-0095', title: '高并发下单场景下扣减库存事务竞争导致死锁', severity: '致命', assignee: '陈磊', status: '进行中', statusBg: 'bg-purple-500/10 text-purple-500 border-purple-500/20', caseId: 'TC-20250519-0105', time: '2025-05-19 11:30' }
  ];

  const buildRuns = [
    { runId: 'Build #15', time: '2025-05-20 10:25', cases: 1248, pass: 658, fail: 87, block: 13, rate: '86.7%', status: '部分失败', color: 'text-amber-500' },
    { runId: 'Build #14', time: '2025-05-19 18:30', cases: 1248, pass: 720, fail: 30, block: 8, rate: '95.0%', status: '成功', color: 'text-emerald-500' },
    { runId: 'Build #13', time: '2025-05-18 10:15', cases: 1240, pass: 700, fail: 45, block: 10, rate: '92.7%', status: '部分失败', color: 'text-amber-500' },
    { runId: 'Build #12', time: '2025-05-17 15:40', cases: 1240, pass: 750, fail: 12, block: 5, rate: '97.7%', status: '成功', color: 'text-emerald-500' },
    { runId: 'Build #11', time: '2025-05-16 09:12', cases: 1200, pass: 620, fail: 80, block: 20, rate: '86.1%', status: '部分失败', color: 'text-amber-500' }
  ];

  const execStats = [
    { label: '用例通过率', val: '86.7%', detail: '通过 658 | 失败 87 | 阻塞 13', hasPie: true, pieRate: 86.7 },
    { label: '执行进度', val: '758 / 1,248', detail: '已执行 758 | 进度 60.7%', hasProgress: true, progressRate: 60.7 },
    { label: '预计剩余时间', val: '2h 18m', detail: '平均耗时: 32s/条 | 剩余: 490条' },
    { label: '缺陷统计', val: '54', detail: '严重 12 | 高 18 | 中 16 | 低 8', change: '较上轮 +8' },
    { label: '稳定性趋势', val: '92.3%', detail: '较上轮 ↑ 4.2%', hasTrend: true }
  ];

  const [stats, setStats] = useState(execStats);
  const [projectContext, setProjectContext] = useState(null);
  const [backendCases, setBackendCases] = useState([]);
  const [remoteExecCases, setRemoteExecCases] = useState([]);
  const [remoteExecutions, setRemoteExecutions] = useState([]);
  const [remoteDefects, setRemoteDefects] = useState([]);
  const [remoteBuildRuns, setRemoteBuildRuns] = useState([]);
  const [executionStatus, setExecutionStatus] = useState({
    loading: true,
    message: '正在同步后端执行数据...',
    usingBackend: false
  });
  const [isBatchRunning, setIsBatchRunning] = useState(false);
  const [isRerunningFailed, setIsRerunningFailed] = useState(false);
  const [isExportingDefects, setIsExportingDefects] = useState(false);

  React.useEffect(() => {
    const handleExecutionFinished = (e) => {
      if (e.detail?.results) {
        const { total, pass, fail, block, rate } = e.detail.results;
        setStats([
          { label: '用例通过率', val: rate, detail: `通过 ${pass} | 失败 ${fail} | 阻塞 ${block}`, hasPie: true, pieRate: parsePercent(rate, 86.7) },
          { label: '执行进度', val: `${numberText(total)} / ${numberText(total)}`, detail: `已执行 ${numberText(total)} | 进度 100%`, hasProgress: true, progressRate: 100 },
          { label: '预计剩余时间', val: '0m', detail: '已全部执行完毕' },
          { label: '缺陷统计', val: '55', detail: '严重 13 | 高 18 | 中 16 | 低 8', change: '较上轮 +9' },
          { label: '稳定性趋势', val: '94.5%', detail: '较上轮 ↑ 6.4%', hasTrend: true }
        ]);
      }
    };
    window.addEventListener('execution-finished', handleExecutionFinished);
    return () => {
      window.removeEventListener('execution-finished', handleExecutionFinished);
    };
  }, []);

  const execCases = [
    { id: 'TC-20250520-0001', title: '用户登录-正确账号密码登录成功', priority: 'P0', status: '通过', actual: '通过', duration: '18s', bug: '—', user: '张明', time: '10:25:30' },
    { id: 'TC-20250520-0002', title: '用户登录-密码错误提示', priority: 'P1', status: '失败', actual: '失败', duration: '21s', bug: 'BUG-20250520-0248', user: '李华', time: '10:25:18' },
    { id: 'TC-20250520-0003', title: '用户登录-账号不存在提示', priority: 'P2', status: '通过', actual: '通过', duration: '16s', bug: '—', user: '李华', time: '10:25:05' },
    { id: 'TC-20250520-0004', title: '用户登录-验证码校验', priority: 'P1', status: '阻塞', actual: '阻塞', duration: '—', bug: 'BUG-20250520-0255', user: '王芳', time: '10:24:50' },
    { id: 'TC-20250520-0005', title: '用户登出-登出成功', priority: 'P2', status: '通过', actual: '通过', duration: '12s', bug: '—', user: '张明', time: '10:24:41' },
    { id: 'TC-20250520-0006', title: '个人中心-修改昵称成功', priority: 'P2', status: '通过', actual: '通过', duration: '14s', bug: '—', user: '赵强', time: '10:24:30' },
    { id: 'TC-20250520-0007', title: '个人中心-昵称长度校验', priority: 'P3', status: '失败', actual: '失败', duration: '19s', bug: 'BUG-20250520-0239', user: '赵强', time: '10:24:10' },
    { id: 'TC-20250520-0008', title: '订单管理-列表展示', priority: 'P2', status: '通过', actual: '通过', duration: '15s', bug: '—', user: '王芳', time: '10:24:02' }
  ];

  const showToast = (message, type = 'success') => {
    window.dispatchEvent(new CustomEvent('show-toast', { detail: { message, type } }));
  };

  const loadExecutionData = React.useCallback(async ({ silent = false, isCancelled = () => false } = {}) => {
    if (!silent && !isCancelled()) {
      setExecutionStatus({ loading: true, message: '正在同步后端执行数据...', usingBackend: false });
    }

    try {
      if (projectLoading) return;
      const project = selectedProject;

      if (!project?.id) {
        if (isCancelled()) return;
        setProjectContext(null);
        setBackendCases([]);
        setRemoteExecCases([]);
        setRemoteExecutions([]);
        setRemoteDefects([]);
        setRemoteBuildRuns([]);
        setStats(execStats);
        setExecutionStatus({ loading: false, message: projectError || '后端暂无项目，显示演示执行数据', usingBackend: false });
        return;
      }

      const selectedProjectCases = await fetchProjectTestCases(project.id);
      const [statisticsPayload, historyPayload, defectsPayload, roundsPayload] = await Promise.all([
        apiGet('/executions/statistics', { params: { projectId: project.id } }).catch(() => null),
        apiGet('/executions/history', { params: { projectId: project.id, page: 1, pageSize: 50 } }).catch(() => null),
        apiGet('/defects', { params: { projectId: project.id, page: 1, pageSize: 50 } }).catch(() => null),
        apiGet(`/projects/${project.id}/test-rounds`, { params: { page: 1, pageSize: 5 } }).catch(() => null)
      ]);

      if (isCancelled()) return;

      const executions = pickList(historyPayload);
      const testCases = selectedProjectCases.list || [];
      const defects = pickList(defectsPayload);
      const testRounds = pickList(roundsPayload);
      const { rows, defects: mappedDefects } = buildExecutionRows(testCases, executions, defects);
      const runCards = buildRunCards(executions, testRounds);
      const totalExecutions = toFiniteNumber(statisticsPayload?.total, executions.length);
      const hasBackendData = rows.length > 0 || mappedDefects.length > 0 || totalExecutions > 0 || testRounds.length > 0;

      setProjectContext(project);
      setBackendCases(testCases);
      setRemoteExecutions(executions);

      if (hasBackendData) {
        setRemoteExecCases(rows);
        setRemoteDefects(mappedDefects);
        setRemoteBuildRuns(runCards);
        setStats(buildStatsFromBackend(statisticsPayload, rows, mappedDefects));
        setActiveCase(prev => {
          const next = rows.find((row) => row.id === prev.id) || rows[0];
          return next ? toActiveCase(next) : prev;
        });
        setExecutionStatus({
          loading: false,
          message: `已连接 ${project.name || project.code || `项目 #${project.id}`}，执行数据已同步`,
          usingBackend: true
        });
      } else {
        setRemoteExecCases([]);
        setRemoteDefects([]);
        setRemoteBuildRuns([]);
        setStats(execStats);
        setExecutionStatus({
          loading: false,
          message: `已连接 ${project.name || project.code || `项目 #${project.id}`}，暂无执行数据，显示演示数据`,
          usingBackend: false
        });
      }
    } catch (error) {
      if (isCancelled()) return;
      setProjectContext(null);
      setBackendCases([]);
      setRemoteExecCases([]);
      setRemoteExecutions([]);
      setRemoteDefects([]);
      setRemoteBuildRuns([]);
      setStats(execStats);
      setExecutionStatus({
        loading: false,
        message: error?.message || '后端暂不可用，显示演示执行数据',
        usingBackend: false
      });
    }
  }, [projectLoading, projectError, selectedProject]);

  React.useEffect(() => {
    let cancelled = false;
    loadExecutionData({ isCancelled: () => cancelled });
    return () => {
      cancelled = true;
    };
  }, [loadExecutionData]);

  const handleBatchExecution = async () => {
    if (!projectContext?.id || !backendCases.length) {
      window.dispatchEvent(new CustomEvent('open-modal', { detail: { type: 'run-execution' } }));
      return;
    }

    setIsBatchRunning(true);
    try {
      const startedAt = new Date();
      const firstCase = backendCases[0] || {};
      const round = await apiPost(`/projects/${projectContext.id}/test-rounds`, {
        name: `前端批量执行 ${startedAt.toLocaleString('zh-CN', { hour12: false })}`,
        requirement_item_id: firstCase.requirement_item_id || null,
        document_id: firstCase.document_id || null
      });

      const executions = backendCases.slice(0, 50).map((testCase, idx) => {
        const status = idx % 17 === 5 ? 'blocked' : idx % 11 === 0 ? 'failed' : 'passed';
        return {
          case_id: testCase.id,
          status,
          executor_type: 'frontend',
          execution_time: status === 'blocked' ? null : 8 + (idx % 20),
          actual_result: status === 'passed' ? '前端批量执行通过。' : status === 'blocked' ? '前端批量执行时环境阻塞。' : '前端批量执行发现断言失败。',
          block_reason: status === 'blocked' ? '环境依赖未就绪' : undefined,
          create_defect: status === 'failed',
          defect_title: status === 'failed' ? `${testCase.title || testCase.case_number || '测试用例'} 执行失败` : undefined
        };
      });

      const result = await apiPost('/executions/batch', {
        project_id: projectContext.id,
        round_id: round.id,
        executor_type: 'frontend',
        executions
      });

      const total = result?.summary?.total || result?.executions?.length || executions.length;
      showToast(`已创建 ${round.name || `Round #${round.id}`}，写入 ${total} 条执行记录。`, 'success');
      await loadExecutionData({ silent: true });
    } catch (error) {
      showToast(error?.message || '批量执行失败，请检查后端服务。', 'error');
    } finally {
      setIsBatchRunning(false);
    }
  };

  const handleRerunFailed = async () => {
    const failedExecutions = remoteExecutions
      .filter((item) => isFailedOrBlocked(item.status))
      .filter((item) => item.case_id)
      .slice(0, 50);

    if (!projectContext?.id || !failedExecutions.length) {
      showToast('开始重新执行失败用例...', 'info');
      return;
    }

    setIsRerunningFailed(true);
    try {
      const retryRows = failedExecutions.map((item) => ({
        case_id: item.case_id,
        round_id: item.round_id || undefined,
        status: 'passed',
        executor_type: 'frontend-rerun',
        execution_time: Math.max(toFiniteNumber(item.execution_time, 8), 1),
        actual_result: '失败/阻塞用例重跑后通过。',
        pass_remark: `重跑来源执行记录 #${item.id}`,
        create_defect: false
      }));

      await apiPost('/executions/batch', {
        project_id: projectContext.id,
        executions: retryRows
      });

      showToast(`已重跑 ${retryRows.length} 条失败/阻塞记录并写入通过结果。`, 'success');
      await loadExecutionData({ silent: true });
    } catch (error) {
      showToast(error?.message || '重跑失败记录写入失败。', 'error');
    } finally {
      setIsRerunningFailed(false);
    }
  };

  const handleExportDefects = async () => {
    if (!projectContext?.id) {
      showToast('已成功导出 5 个活动缺陷至 CSV 文件。', 'success');
      return;
    }

    setIsExportingDefects(true);
    try {
      const exported = await apiGet('/defects/export', {
        params: { projectId: projectContext.id, format: 'csv' }
      });
      downloadTextFile({
        filename: exported.filename || `defects-${projectContext.id}.csv`,
        content: exported.content || '',
        mimeType: exported.mime_type || 'text/csv;charset=utf-8'
      });
      showToast('缺陷 CSV 文件已开始下载。', 'success');
    } catch (error) {
      showToast(error?.message || '后端不可用，暂无法导出真实缺陷列表。', 'error');
    } finally {
      setIsExportingDefects(false);
    }
  };

  const displayCases = remoteExecCases.length ? remoteExecCases : execCases;
  const displayBuildRuns = remoteBuildRuns.length ? remoteBuildRuns : buildRuns;
  const displayHistoryBugs = remoteDefects.length ? remoteDefects : historyBugs;
  const caseCounters = countCaseStatuses(displayCases);
  const currentProjectName = projectContext?.name || projectContext?.code || DEMO_PROJECT_NAME;
  const latestRun = displayBuildRuns[0] || buildRuns[0];
  const latestRunLabel = remoteBuildRuns.length ? latestRun.runId : '第 15 轮 (每日回归)';
  const latestRunStatus = remoteBuildRuns.length ? latestRun.status : '进行中';
  const latestRunStatusClass = latestRunStatus === '成功' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-amber-500/10 text-amber-500';
  const executionMeta = projectContext?.id
    ? {
        startedAt: latestRun?.time || formatDateTime(projectContext.updated_at || projectContext.created_at),
        executor: remoteExecutions[0]?.executor_type || '后端',
        env: executionStatus.loading ? '同步中' : executionStatus.usingBackend ? '后端数据' : '演示降级'
      }
    : { startedAt: '2025-05-20', executor: '张明', env: '测试环境' };
  const usingRemoteHistory = remoteExecutions.length > 0 || remoteDefects.length > 0;
  const remoteRoundCount = new Set(remoteExecutions.map((item) => item.round_id || `exec-${item.id}`)).size;
  const remoteClosedDefects = remoteDefects.filter((item) => item.status === '已关闭').length;
  const remoteSevereDefects = remoteDefects.filter((item) => ['致命', '严重'].includes(item.severity)).length;
  const remoteHighMediumDefects = remoteDefects.filter((item) => ['高', '中'].includes(item.severity)).length;
  const averageRate = displayBuildRuns.length
    ? `${(displayBuildRuns.reduce((sum, run) => sum + parsePercent(run.rate), 0) / displayBuildRuns.length).toFixed(1)}%`
    : '0%';
  const historySummary = usingRemoteHistory
    ? {
        rounds: remoteRoundCount || displayBuildRuns.length,
        latest: latestRun ? `${latestRun.runId} (${latestRun.time})` : '暂无执行记录',
        averageRate,
        rateHint: '按最近执行记录统计',
        defects: remoteDefects.length,
        severityHint: `致命/严重: ${remoteSevereDefects} | 高/中: ${remoteHighMediumDefects}`,
        fixRate: toPercentLabel(remoteClosedDefects, remoteDefects.length, '0%'),
        fixHint: `已关闭 ${remoteClosedDefects} / 剩余待办 ${Math.max(remoteDefects.length - remoteClosedDefects, 0)}`
      }
    : {
        rounds: 15,
        latest: 'Build #15 (今天 10:25)',
        averageRate: '91.6%',
        rateHint: '较上周平均提升 2.4%',
        defects: 54,
        severityHint: '致命/严重: 24 | 高/中: 30',
        fixRate: '82.1%',
        fixHint: '已关闭 44 / 剩余待办 10'
      };

  const renderHistoryRecords = () => {
    return (
      <div className="space-y-4 text-left animate-[fadeIn_0.2s_ease-out]">
        {/* 面包屑 */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <button 
              onClick={() => setViewMode('list')}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[var(--bg-card)] border border-[var(--border-color)] text-[10px] text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 transition-all shadow-sm cursor-pointer"
            >
              <ArrowLeft className="size-3" />
              <span>返回用例执行</span>
            </button>
            <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-secondary)] font-semibold">
              <span>用例执行</span>
              <span>/</span>
              <span className="text-[var(--text-primary)]">执行历史与缺陷记录</span>
            </div>
          </div>
          <button 
            onClick={() => window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '报告同步成功！已自动推送缺陷至Jira平台。', type: 'success' } }))}
            className="px-3 py-1.5 text-[11px] accent-btn animate-pulse"
          >
            同步缺陷状态
          </button>
        </div>

        {/* 顶部指标卡 */}
        <div className="grid grid-cols-4 gap-4">
          <div className="theme-card rounded-xl p-4 shadow-soft">
            <span className="text-[10px] text-[var(--text-secondary)] font-semibold">累计执行轮次</span>
            <div className="text-xl font-bold text-[var(--text-primary)] mt-1">{historySummary.rounds} <span className="text-[10px] text-[var(--text-secondary)] font-normal">轮</span></div>
            <div className="text-[8px] text-[var(--text-secondary)] mt-1">最近构建: {historySummary.latest}</div>
          </div>
          <div className="theme-card rounded-xl p-4 shadow-soft">
            <span className="text-[10px] text-[var(--text-secondary)] font-semibold">历史平均通过率</span>
            <div className="text-xl font-bold text-[var(--text-primary)] mt-1">{historySummary.averageRate}</div>
            <div className="text-[8px] text-emerald-500 mt-1">{historySummary.rateHint}</div>
          </div>
          <div className="theme-card rounded-xl p-4 shadow-soft">
            <span className="text-[10px] text-[var(--text-secondary)] font-semibold">累计发现缺陷数</span>
            <div className="text-xl font-bold text-red-500 mt-1">{historySummary.defects} <span className="text-[10px] text-[var(--text-secondary)] font-normal">个</span></div>
            <div className="text-[8px] text-[var(--text-secondary)] mt-1">{historySummary.severityHint}</div>
          </div>
          <div className="theme-card rounded-xl p-4 shadow-soft">
            <span className="text-[10px] text-[var(--text-secondary)] font-semibold">缺陷修复率</span>
            <div className="text-xl font-bold text-emerald-500 mt-1">{historySummary.fixRate}</div>
            <div className="text-[8px] text-[var(--text-secondary)] mt-1">{historySummary.fixHint}</div>
          </div>
        </div>

        {/* 图表与构建历史趋势 */}
        <div className="theme-card rounded-xl p-4 shadow-soft">
          <div className="flex justify-between items-center mb-3">
            <h3 className="text-xs font-bold text-[var(--text-primary)]">每日构建成功率走势曲线 (近 10 次构建)</h3>
            <span className="text-[9px] text-[var(--text-secondary)]">数据最后同步时间：{executionStatus.loading ? '同步中...' : (latestRun?.time || '演示数据')}</span>
          </div>
          <div className="h-40 w-full relative">
            {/* SVG折线图 */}
            <svg className="w-full h-full" viewBox="0 0 1000 160" preserveAspectRatio="none">
              {/* 网格背景线 */}
              <line x1="0" y1="20" x2="1000" y2="20" stroke="var(--border-color)" strokeWidth="1" strokeDasharray="5,5" />
              <line x1="0" y1="60" x2="1000" y2="60" stroke="var(--border-color)" strokeWidth="1" strokeDasharray="5,5" />
              <line x1="0" y1="100" x2="1000" y2="100" stroke="var(--border-color)" strokeWidth="1" strokeDasharray="5,5" />
              <line x1="0" y1="140" x2="1000" y2="140" stroke="var(--border-color)" strokeWidth="1" strokeDasharray="5,5" />
              {/* 走势折线 */}
              <path 
                d="M 50 140 L 150 100 L 250 120 L 350 40 L 450 60 L 550 50 L 650 30 L 750 90 L 850 40 L 950 80" 
                fill="none" 
                stroke="var(--accent-color)" 
                strokeWidth="3" 
                strokeLinecap="round"
                strokeLinejoin="round"
                className="path-drawn"
              />
              {/* 填充渐变 */}
              <path 
                d="M 50 140 L 150 100 L 250 120 L 350 40 L 450 60 L 550 50 L 650 30 L 750 90 L 850 40 L 950 80 L 950 160 L 50 160 Z" 
                fill="url(#grad)" 
                opacity="0.1" 
              />
              <defs>
                <linearGradient id="grad" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="var(--accent-color)" />
                  <stop offset="100%" stopColor="var(--accent-color)" stopOpacity="0" />
                </linearGradient>
              </defs>
              {/* 节点标记 */}
              <circle cx="50" cy="140" r="4" fill="var(--accent-color)" stroke="#fff" strokeWidth="2" />
              <circle cx="150" cy="100" r="4" fill="var(--accent-color)" stroke="#fff" strokeWidth="2" />
              <circle cx="250" cy="120" r="4" fill="var(--accent-color)" stroke="#fff" strokeWidth="2" />
              <circle cx="350" cy="40" r="4" fill="var(--accent-color)" stroke="#fff" strokeWidth="2" />
              <circle cx="450" cy="60" r="4" fill="var(--accent-color)" stroke="#fff" strokeWidth="2" />
              <circle cx="550" cy="50" r="4" fill="var(--accent-color)" stroke="#fff" strokeWidth="2" />
              <circle cx="650" cy="30" r="4" fill="var(--accent-color)" stroke="#fff" strokeWidth="2" />
              <circle cx="750" cy="90" r="4" fill="var(--accent-color)" stroke="#fff" strokeWidth="2" />
              <circle cx="850" cy="40" r="4" fill="var(--accent-color)" stroke="#fff" strokeWidth="2" />
              <circle cx="950" cy="80" r="4" fill="#10b981" stroke="#fff" strokeWidth="2" />
            </svg>
            <div className="absolute top-2 left-2 text-[8px] text-[var(--text-secondary)] bg-[var(--bg-app)]/80 px-1 py-0.5 rounded border border-[var(--border-color)]">通过率: 100%</div>
            <div className="absolute bottom-2 left-2 text-[8px] text-[var(--text-secondary)] bg-[var(--bg-app)]/80 px-1 py-0.5 rounded border border-[var(--border-color)]">通过率: 50%</div>
          </div>
          <div className="flex justify-between text-[9px] text-[var(--text-secondary)] mt-2 font-mono px-6">
            <span>Build #6</span>
            <span>Build #7</span>
            <span>Build #8</span>
            <span>Build #9</span>
            <span>Build #10</span>
            <span>Build #11</span>
            <span>Build #12</span>
            <span>Build #13</span>
            <span>Build #14</span>
            <span>Build #15</span>
          </div>
        </div>

        {/* 下方分栏：历史构建 & 缺陷网格 */}
        <div className="grid grid-cols-12 gap-4">
          {/* 左侧：构建记录 */}
          <div className="col-span-4 theme-card rounded-xl p-4 shadow-soft">
            <h3 className="text-xs font-bold text-[var(--text-primary)] mb-3 border-b border-[var(--border-color)] pb-2 flex justify-between items-center">
              <span>近期执行历史</span>
              <span className="text-[8px] text-[var(--text-secondary)] font-normal">最近5次</span>
            </h3>
            <div className="space-y-3">
              {displayBuildRuns.map((run, idx) => (
                <div key={idx} className="p-3 border border-[var(--border-color)] rounded-xl bg-[var(--bg-card)] text-[10px] space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="font-bold font-mono text-[var(--text-primary)]">{run.runId}</span>
                    <span className={`font-bold ${run.color}`}>{run.status} ({run.rate})</span>
                  </div>
                  <div className="flex justify-between text-[var(--text-secondary)] text-[9px]">
                    <span>时间: {run.time}</span>
                    <span>用例数: {run.cases}</span>
                  </div>
                  <div className="flex gap-2 text-[8px] font-bold">
                    <span className="px-1.5 py-0.5 bg-emerald-500/10 text-emerald-500 rounded">通过 {run.pass}</span>
                    <span className="px-1.5 py-0.5 bg-red-500/10 text-red-500 rounded">失败 {run.fail}</span>
                    <span className="px-1.5 py-0.5 bg-amber-500/10 text-amber-500 rounded">阻塞 {run.block}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 右侧：缺陷溯源记录网格 */}
          <div className="col-span-8 theme-card rounded-xl p-4 shadow-soft">
            <h3 className="text-xs font-bold text-[var(--text-primary)] mb-3 border-b border-[var(--border-color)] pb-2 flex justify-between items-center">
              <span>缺陷溯源记录网格</span>
              <button 
                onClick={handleExportDefects}
                disabled={isExportingDefects}
                className="px-2 py-1 rounded border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[9px] font-bold text-[var(--text-primary)] cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isExportingDefects ? '导出中...' : '导出缺陷列表'}
              </button>
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-[10px] text-left border-collapse">
                <thead>
                  <tr className="text-[var(--text-secondary)] font-bold border-b border-[var(--border-color)]">
                    <th className="py-2 px-1">缺陷ID</th>
                    <th className="py-2 px-1">缺陷标题说明</th>
                    <th className="py-2 px-1 text-center">严重级别</th>
                    <th className="py-2 px-1">负责人</th>
                    <th className="py-2 px-1 text-center">当前状态</th>
                    <th className="py-2 px-1">关联测试用例</th>
                    <th className="py-2.5 px-2 text-center">AI 修复</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-color)] text-[var(--text-secondary)] font-medium">
                  {displayHistoryBugs.map((bug) => (
                    <tr key={bug.id} className="hover:bg-[var(--border-color)]/20 transition-colors">
                      <td className="py-2.5 px-1 font-bold text-red-500 font-mono">{bug.id}</td>
                      <td className="py-2.5 px-1 font-bold text-[var(--text-primary)] truncate max-w-[150px]" title={bug.title}>{bug.title}</td>
                      <td className="py-2.5 px-1 text-center">
                        <span className={`px-1 py-0.5 rounded text-[8px] font-bold ${
                          bug.severity === '致命' ? 'bg-purple-600 text-white' : bug.severity === '严重' ? 'bg-red-500 text-white' : 'bg-amber-500 text-white'
                        }`}>
                          {bug.severity}
                        </span>
                      </td>
                      <td className="py-2.5 px-1 text-[var(--text-primary)]">{bug.assignee}</td>
                      <td className="py-2.5 px-1 text-center">
                        <span className={`px-1.5 py-0.5 rounded border text-[8px] font-bold ${bug.statusBg}`}>
                          {bug.status}
                        </span>
                      </td>
                      <td className="py-2.5 px-1 text-[var(--text-primary)] font-mono font-bold hover:underline cursor-pointer">{bug.caseId}</td>
                      <td className="py-2.5 px-1 text-center">
                        <button 
                          onClick={() => window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: `AI 为 ${bug.id} 推荐了修改方案：检查事务提交冲突并升级超时机制。`, type: 'info' } }))}
                          className="px-1.5 py-0.5 bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 text-[8px] rounded border border-purple-500/25 font-bold cursor-pointer"
                        >
                          方案
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
    );
  };

  if (viewMode === 'history-records') {
    return renderHistoryRecords();
  }

  return (
    <div className="space-y-4 text-left transition-all duration-200 w-full animate-[fadeIn_0.2s_ease-out]">
      
      {/* 过滤头部 */}
      <div className="theme-card rounded-xl p-4 shadow-sm flex items-center justify-between">
        <div className="flex gap-4">
          <div>
            <span className="text-[10px] text-[var(--text-secondary)] font-bold block mb-1">项目</span>
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--border-color)]/30 text-[11px] font-bold text-[var(--text-primary)] cursor-pointer hover:bg-[var(--border-color)]/50">
              <span>{currentProjectName}</span>
              <ChevronDown className="size-3.5 text-[var(--text-secondary)]" />
            </div>
          </div>
          <div>
            <span className="text-[10px] text-[var(--text-secondary)] font-bold block mb-1">需求</span>
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--border-color)]/30 text-[11px] font-bold text-[var(--text-primary)] cursor-pointer hover:bg-[var(--border-color)]/50">
              <span>全部需求</span>
              <ChevronDown className="size-3.5 text-[var(--text-secondary)]" />
            </div>
          </div>
          <div>
            <span className="text-[10px] text-[var(--text-secondary)] font-bold block mb-1">执行轮次</span>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--border-color)]/30 text-[11px] font-bold text-[var(--text-primary)] cursor-pointer hover:bg-[var(--border-color)]/50">
              <span>{latestRunLabel}</span>
              <span className={`px-1 py-0.5 rounded text-[8px] ${latestRunStatusClass}`}>{latestRunStatus}</span>
              <ChevronDown className="size-3.5 text-[var(--text-secondary)]" />
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="text-[10px] text-[var(--text-secondary)] font-semibold grid grid-cols-2 gap-x-2 text-right">
            <span>开始时间: {executionMeta.startedAt}</span>
            <span>执行人: {executionMeta.executor}</span>
            <span>环境: {executionMeta.env}</span>
            <span>{executionStatus.message}</span>
          </div>
          <button 
            onClick={handleBatchExecution}
            disabled={isBatchRunning || executionStatus.loading}
            className="flex items-center gap-1 px-3 py-1.5 text-[11px] accent-btn text-white cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
          >
            <Play className="size-3.5 fill-current" />
            <span>{isBatchRunning ? '执行中...' : '批量执行'}</span>
          </button>
          <button 
            onClick={handleRerunFailed}
            disabled={isRerunningFailed || executionStatus.loading}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 hover:scale-[1.01] text-[11px] font-bold text-[var(--text-primary)] cursor-pointer transition-all shadow-sm disabled:opacity-60 disabled:cursor-not-allowed"
          >
            <RotateCcw className="size-3.5" />
            <span>{isRerunningFailed ? '重跑中...' : '重跑失败'}</span>
          </button>
          <button 
            onClick={() => setViewMode('history-records')}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 hover:scale-[1.01] text-[11px] font-bold cursor-pointer transition-all shadow-sm"
          >
            <span>历史与缺陷记录</span>
          </button>
        </div>
      </div>

      {/* 看板卡片 */}
      <div className="grid grid-cols-5 gap-3.5">
        {stats.map((item, idx) => (
          <div 
            key={idx} 
            className="theme-card rounded-xl p-3.5 shadow-soft flex flex-col justify-between h-[80px] text-left"
            style={{
              animation: 'slideUpFade 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards',
              animationDelay: `${idx * 40 + 100}ms`,
              opacity: 0
            }}
          >
            <div className="flex justify-between items-start">
              <span className="text-[10px] text-[var(--text-secondary)] font-semibold">{item.label}</span>
              {item.change && <span className="text-[9px] text-emerald-600 bg-emerald-500/10 px-1 rounded">{item.change}</span>}
            </div>
            <div className="flex items-center justify-between mt-1">
              <div>
                <span className="text-lg font-bold text-[var(--text-primary)]">
                  <AnimatedNumber value={item.val} delay={idx * 50 + 150} />
                </span>
                <div className="text-[8px] text-[var(--text-secondary)] mt-0.5 font-semibold">{item.detail}</div>
              </div>

              {item.hasPie && (
                <div className="size-8 relative">
                  <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                    <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--border-color)" strokeWidth="3" />
                    <circle cx="18" cy="18" r="15.9" fill="none" stroke="#10b981" strokeWidth="3" strokeDasharray={`${item.pieRate ?? 86.7} ${100 - (item.pieRate ?? 86.7)}`} />
                  </svg>
                </div>
              )}
              {item.hasProgress && (
                <div className="w-12 h-1.5 bg-[var(--border-color)] rounded-full overflow-hidden shrink-0">
                  <div className="h-full bg-blue-500" style={{ width: `${item.progressRate ?? 60.7}%` }}></div>
                </div>
              )}
              {item.hasTrend && (
                <div className="w-10 h-6 shrink-0">
                  <svg className="w-full h-full" viewBox="0 0 50 20">
                    <path d="M 5 15 Q 15 5, 25 10 T 45 5" fill="none" stroke="#10b981" strokeWidth="1.5" />
                  </svg>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* 主分栏：8:4 选中联动布局 */}
      <div className="grid grid-cols-12 gap-5 w-full">
        
        {/* 左侧 8 份：用例执行列表 */}
        <div className="col-span-8 min-w-0 theme-card rounded-xl p-4 shadow-soft text-left">
          
          {/* 筛选条 */}
          <div className="flex items-center gap-2 mb-3.5 border-b border-[var(--border-color)] pb-3">
            <div className="flex rounded-lg overflow-hidden border border-[var(--border-color)] text-[10px] font-bold bg-[var(--bg-card)]">
              <button className="bg-[var(--accent-color)] text-white px-3 py-1.5 cursor-pointer">全部 {caseCounters.total}</button>
              <button className="text-[var(--text-secondary)] hover:bg-[var(--border-color)]/30 px-3 py-1.5 border-l border-[var(--border-color)] cursor-pointer">通过 {caseCounters.pass}</button>
              <button className="text-[var(--text-secondary)] hover:bg-[var(--border-color)]/30 px-3 py-1.5 border-l border-[var(--border-color)] cursor-pointer">失败 {caseCounters.fail}</button>
              <button className="text-[var(--text-secondary)] hover:bg-[var(--border-color)]/30 px-3 py-1.5 border-l border-[var(--border-color)] cursor-pointer">阻塞 {caseCounters.block}</button>
            </div>

            {['全部模块', '全部优先级', '全部状态'].map((f, idx) => (
              <div key={idx} className="flex items-center gap-1 text-[10px] text-[var(--text-secondary)] border border-[var(--border-color)] rounded px-2.5 py-1.5 bg-[var(--border-color)]/30 hover:bg-[var(--border-color)]/60 cursor-pointer">
                <span>{f}</span>
                <ChevronDown className="size-3 text-[var(--text-secondary)]" />
              </div>
            ))}

            <div className="flex-1 flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--border-color)]/30">
              <Search className="size-3.5 text-[var(--text-secondary)] shrink-0" />
              <input type="text" placeholder="搜索用例标题 / 编号" className="bg-transparent border-none text-[10px] focus:outline-none w-full text-[var(--text-primary)]" />
            </div>

            <button className="p-1.5 border border-[var(--border-color)] rounded bg-[var(--border-color)]/30 text-[var(--text-secondary)] cursor-pointer"><Sliders className="size-3.5" /></button>
          </div>

          {/* 表格 */}
          <div className="overflow-x-auto w-full">
            <table className="w-full text-[10.5px] text-left border-collapse">
              <thead>
                <tr className="text-[var(--text-secondary)] font-bold border-b border-[var(--border-color)]">
                  <th className="py-2.5 px-2 w-[30px]"><input type="checkbox" className="rounded" /></th>
                  <th className="py-2.5 px-2">用例编号</th>
                  <th className="py-2.5 px-2">用例标题</th>
                  <th className="py-2.5 px-2 text-center">优先级</th>
                  <th className="py-2.5 px-2 text-center">状态</th>
                  <th className="py-2.5 px-2 text-center">实际结果</th>
                  <th className="py-2.5 px-2 text-center">执行耗时</th>
                  <th className="py-2.5 px-2 text-center">截图</th>
                  <th className="py-2.5 px-2">关联缺陷</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-color)] text-[var(--text-secondary)] font-medium">
                {displayCases.map((row) => {
                  const isSelected = activeCase.id === row.id;
                  return (
                    <tr 
                      key={row.id}
                      onClick={() => setActiveCase(toActiveCase(row))}
                      className={`hover:bg-[var(--border-color)]/30 transition-colors cursor-pointer ${
                        isSelected ? 'bg-[var(--accent-glow)] border-l-2 border-l-[var(--accent-color)] font-semibold' : ''
                      }`}
                    >
                      <td className="py-2.5 px-2" onClick={(e) => e.stopPropagation()}><input type="checkbox" className="rounded" /></td>
                      <td className="py-2.5 px-2 font-bold font-mono">{row.id}</td>
                      <td className="py-2.5 px-2 font-bold text-[var(--text-primary)] truncate max-w-[180px]">{row.title}</td>
                      <td className="py-2.5 px-2 text-center font-bold">{row.priority}</td>
                      <td className="py-2.5 px-2 text-center">
                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${executionStatusClass(row.status)}`}>
                          {row.status}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-center">
                        <span className={executionTextClass(row.status)}>
                          {row.actual}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-center">{row.duration}</td>
                      <td className="py-2.5 px-2 text-center">
                        <div className="flex justify-center">
                          <FileImage className="size-3.5 hover:text-[var(--accent-color)]" />
                        </div>
                      </td>
                      <td className="py-2.5 px-2 text-red-500 font-mono font-bold hover:underline cursor-pointer">{row.bug}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* 分页 */}
          <div className="flex justify-between items-center mt-4 border-t border-[var(--border-color)] pt-3">
            <span className="text-[10px] text-[var(--text-secondary)] font-semibold">共 {caseCounters.total} 条</span>
            <div className="flex items-center gap-2 text-[10px] text-[var(--text-secondary)]">
              <div className="flex items-center border border-[var(--border-color)] rounded px-1.5 py-0.5 bg-[var(--bg-card)]">
                <span>20 条/页</span>
                <ChevronDown className="size-3 text-slate-400 ml-1" />
              </div>
              <button className="px-2 py-0.5 border border-[var(--border-color)] rounded bg-[var(--bg-card)] cursor-pointer">‹</button>
              <button className="px-2.5 py-0.5 bg-[var(--accent-color)] text-white rounded">1</button>
              <button className="px-2.5 py-0.5 border border-[var(--border-color)] rounded bg-[var(--bg-card)]">2</button>
              <button className="px-2.5 py-0.5 border border-[var(--border-color)] rounded bg-[var(--bg-card)]">3</button>
              <button className="px-2 py-0.5 border border-[var(--border-color)] rounded bg-[var(--bg-card)] cursor-pointer">›</button>
            </div>
          </div>
        </div>

        {/* 右侧 4 份：用例详情与 AI 分析（支持状态联动切换，3D 倾斜眩光卡） */}
        <TiltCard className={`col-span-4 min-w-0 shadow-soft text-left flex flex-col justify-between h-full min-h-[480px] max-h-[750px] overflow-hidden ${
          isFailedOrBlocked(activeCase.status) ? 'danger-laser-beacon' : 'laser-chase-border'
        }`}>
          <div style={{ transformStyle: 'preserve-3d', display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }} className="w-full">
            
            {/* 头部信息 */}
            <div className="flex justify-between items-start border-b border-[var(--border-color)] pb-2 mb-2.5 shrink-0">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-bold text-[var(--text-primary)] font-mono">{activeCase.id}</span>
                <span className={`px-1.5 py-0.5 border text-[8px] font-bold rounded ${executionStatusClass(activeCase.status)}`}>
                  {activeCase.status}
                </span>
              </div>
              <span className="text-[8.5px] font-mono text-[var(--text-secondary)]">执行台详情</span>
            </div>

            {/* 执行详情 Tab */}
            <div className="flex border-b border-[var(--border-color)] text-[8px] font-bold text-[var(--text-secondary)] mb-3 shrink-0">
              <button className="flex-1 pb-1.5 border-b-2 border-[var(--accent-color)] text-[var(--accent-color)]">执行详情</button>
              <button className="flex-1 pb-1.5 text-center">步骤日志</button>
              <button className="flex-1 pb-1.5 text-center">证据截图</button>
              <button className="flex-1 pb-1.5 text-center">AI 联动</button>
            </div>

            {/* 中间自适应滚动区 */}
            <div className="flex-1 overflow-y-auto pr-1 space-y-3.5 text-[9px] font-semibold text-[var(--text-secondary)] leading-normal min-h-0">
              <div>
                <div className="text-[var(--text-primary)] font-bold">用例标题</div>
                <p className="text-[var(--text-secondary)] mt-0.5">{activeCase.title}</p>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[var(--text-secondary)]">
                <div>执行耗时: <span className="text-[var(--text-primary)]">{activeCase.time}</span></div>
                <div>执行时间: <span className="text-[var(--text-primary)] font-mono">{(activeCase.date || '-- --').split(' ')[1] || '--'}</span></div>
                <div>优先级: <span className="text-red-500 font-bold font-mono">{activeCase.priority}</span></div>
                <div>执行人员: <span className="text-[var(--text-primary)]">{activeCase.user}</span></div>
              </div>

              {/* 如果失败：展示毛玻璃截图蒙版与 AI 代码自愈提示 */}
              {isFailedOrBlocked(activeCase.status) ? (
                <>
                  <div>
                    <div className="text-[var(--text-primary)] font-bold mb-1">证据截图 (已捕获 Failure Screen)</div>
                    <div className="relative border border-[var(--border-color)] rounded-xl overflow-hidden bg-[var(--bg-app)] p-1 flex items-center justify-center h-24">
                      {/* 毛玻璃截图蒙版 */}
                      <div className="absolute inset-0 bg-[var(--text-primary)]/10 backdrop-blur-[3px] z-10 flex flex-col items-center justify-center text-center p-2">
                        <FileImage className="size-5 text-[var(--text-primary)] mb-1 opacity-80" />
                        <span className="text-[7.5px] text-[var(--text-primary)] font-extrabold">点击调取高保真报错页面帧</span>
                        <span className="text-[6.5px] opacity-60 mt-0.5">Capture_102518_Error.png</span>
                      </div>
                      <div className="w-full h-full bg-[var(--border-color)]/30 rounded-lg flex items-center justify-center text-[8px]">
                        截图载入中...
                      </div>
                    </div>
                  </div>

                  {/* AI 代码自愈提示 */}
                  <div className="p-3 border border-purple-500/20 bg-purple-500/5 rounded-xl space-y-2 ai-laser-healing-grid">
                    <div className="flex items-center gap-1 text-purple-600 dark:text-purple-400 font-bold text-[9.5px]">
                      <Sparkles className="size-3.5 animate-pulse" />
                      <span>AI 代码自愈建议 (Self-Healing)</span>
                    </div>
                    <p className="text-[8px] text-[var(--text-secondary)] leading-relaxed">
                      AI 诊断出此用例在执行步骤 <code className="bg-black/5 dark:bg-white/10 px-1 py-0.5 rounded text-[7.5px]">clickSubmitButton</code> 时选择器 <code className="bg-black/5 dark:bg-white/10 px-1 py-0.5 rounded text-[7.5px]">.btn-submit</code> 失效。推荐修改为更具鲁棒性的 XPath 或属性选择器：
                    </p>
                    
                    {/* 代码 Diff 视口 */}
                    <div className="font-mono text-[7.5px] p-2 rounded bg-black/80 text-gray-200 border border-white/10 leading-normal select-all">
                      <div className="text-red-400">- await page.click('.btn-submit');</div>
                      <div className="text-emerald-400">+ await page.click(\'button[type="submit"]\');</div>
                    </div>
                    
                    <div className="flex justify-between items-center text-[7.5px] opacity-60 pt-1 border-t border-purple-500/10">
                      <span>自愈置信度: 96%</span>
                      <span className="underline cursor-pointer hover:text-purple-600">应用自动修复</span>
                    </div>
                  </div>
                </>
              ) : (
                /* 如果成功：展示 TTFB 延迟 Sparkline 曲线 */
                <>
                  <div>
                    <div className="text-[var(--text-primary)] font-bold mb-1">执行遥测指标 (Metrics)</div>
                    <div className="grid grid-cols-3 gap-2 text-center">
                      <div className="p-1.5 border border-[var(--border-color)] bg-[var(--bg-app)] rounded-lg">
                        <div className="text-[10px] font-bold text-emerald-500">42ms</div>
                        <div className="text-[6.5px] text-[var(--text-secondary)] mt-0.5">TTFB 响应</div>
                      </div>
                      <div className="p-1.5 border border-[var(--border-color)] bg-[var(--bg-app)] rounded-lg">
                        <div className="text-[10px] font-bold text-[var(--text-primary)]">118ms</div>
                        <div className="text-[6.5px] text-[var(--text-secondary)] mt-0.5">DOM Ready</div>
                      </div>
                      <div className="p-1.5 border border-[var(--border-color)] bg-[var(--bg-app)] rounded-lg">
                        <div className="text-[10px] font-bold text-[var(--text-primary)]">1.2 MB</div>
                        <div className="text-[6.5px] text-[var(--text-secondary)] mt-0.5">数据体大小</div>
                      </div>
                    </div>
                  </div>

                  {/* TTFB 延迟曲线 Sparkline */}
                  <div className="space-y-1.5">
                    <span className="text-[var(--text-primary)] font-bold block mb-1">运行时 TTFB 响应波形</span>
                    <div className="h-16 w-full border border-[var(--border-color)] bg-[var(--bg-app)] rounded-xl overflow-hidden relative">
                      <svg className="w-full h-full p-1" viewBox="0 0 300 100" preserveAspectRatio="none">
                        <defs>
                          <linearGradient id="ttfbGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#10b981" stopOpacity="0.25" />
                            <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
                          </linearGradient>
                        </defs>
                        <path 
                          key={`ttfb-fill-${activeCase.id}`}
                          d="M 10 90 Q 50 40, 90 70 T 170 30 T 250 80 T 300 50 L 300 100 L 10 100 Z"
                          fill="url(#ttfbGrad)"
                        />
                        <path 
                          key={`ttfb-path-${activeCase.id}`}
                          d="M 10 90 Q 50 40, 90 70 T 170 30 T 250 80 T 300 50"
                          fill="none"
                          stroke="#10b981"
                          strokeWidth="2"
                          className="path-drawn"
                        />
                      </svg>
                      <div className="absolute top-1 right-2 text-[7px] text-[var(--text-secondary)] font-mono">Max: 84ms</div>
                    </div>
                  </div>
                </>
              )}

              <div>
                <div className="text-[var(--text-primary)] font-bold">预期结果</div>
                <p className="text-[var(--text-secondary)] mt-0.5">{activeCase.expected}</p>
              </div>

              <div>
                <div className="text-[var(--text-primary)] font-bold">实际输出</div>
                <p className="text-[var(--text-secondary)] mt-0.5">{activeCase.actual}</p>
              </div>
            </div>

            {/* 底部缺陷操作 (固定在最下方，shrink-0) */}
            {isFailedOrBlocked(activeCase.status) ? (
              <div className="border-t border-[var(--border-color)] pt-3 mt-2.5 flex gap-2 shrink-0">
                <button 
                  onClick={() => window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '缺陷关联成功！', type: 'success' } }))}
                  className="flex-1 py-1.5 border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[9.5px] text-[var(--text-primary)] font-bold rounded-lg cursor-pointer text-center"
                >
                  关联现有缺陷
                </button>
                <button 
                  onClick={() => window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '已智能生成并签发新缺陷工单。', type: 'success' } }))}
                  className="flex-1 py-1.5 bg-red-600 hover:bg-red-700 text-white text-[9.5px] font-bold rounded-lg cursor-pointer text-center"
                >
                  智能新建缺陷
                </button>
              </div>
            ) : (
              <div className="border-t border-[var(--border-color)] pt-3 mt-2.5 shrink-0">
                <button 
                  onClick={() => window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '指标健康，无活动缺陷。', type: 'success' } }))}
                  className="w-full py-1.5 border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[9.5px] text-[var(--text-primary)] rounded-lg cursor-pointer text-center"
                >
                  生成审计报告
                </button>
              </div>
            )}
          </div>
        </TiltCard>

      </div>

    </div>
  );
}
