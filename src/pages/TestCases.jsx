import React, { useState, useEffect } from 'react';
import { 
  Sparkles, 
  Settings, 
  ChevronDown, 
  Download, 
  Share2, 
  CheckCircle2, 
  AlertCircle,
  FileCheck,
  Code,
  ArrowLeft,
  Search,
  CheckCircle,
  HelpCircle
} from 'lucide-react';
import TiltCard from '../components/TiltCard';
import AnimatedNumber from '../components/AnimatedNumber';
import { apiGet, apiPost, downloadTextFile, formatDateTime, pickList } from '../lib/api';
import { useProjectContext } from '../lib/projectContext';

const mapCaseStatus = (status) => {
  const normalized = String(status || '').toLowerCase();
  if (['confirmed', 'passed', 'approved'].includes(normalized)) return '已通过';
  if (['failed', 'rejected'].includes(normalized)) return '需优化';
  return '待评审';
};

const mapBackendCase = (item) => ({
  id: item.case_number || `TC-${String(item.id).padStart(6, '0')}`,
  backendId: item.id,
  title: item.title || `测试用例 #${item.id}`,
  priority: item.priority || 'P2',
  type: item.case_type || '功能测试',
  ref: item.requirement_item_id ? `REQ-${item.requirement_item_id}` : 'REQ',
  status: mapCaseStatus(item.status),
  raw: item
});

const toRecord = (value) => {
  if (value && typeof value === 'object' && !Array.isArray(value)) return value;
  return {};
};

const toArray = (value, keys = []) => {
  if (Array.isArray(value)) return value;
  if (value === null || value === undefined || value === '') return [];
  if (typeof value === 'string') return [value];
  if (typeof value !== 'object') return [value];

  const record = toRecord(value);
  const candidateKeys = [...keys, 'items', 'list', 'records', 'results', 'data'];
  for (const key of candidateKeys) {
    if (Array.isArray(record[key])) return record[key];
  }
  return [];
};

const toNumber = (value, fallback = 0) => {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
};

const stringifyValue = (value) => {
  if (value === null || value === undefined || value === '') return '暂无';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (typeof value === 'object') {
    return value.text || value.message || value.title || value.name || value.description || JSON.stringify(value);
  }
  return String(value);
};

const normalizeIssue = (issue) => {
  const record = toRecord(issue);
  const rawType = String(record.type || record.severity || record.level || 'info').toLowerCase();
  const type = rawType.includes('danger') || rawType.includes('error') || rawType.includes('critical')
    ? 'danger'
    : rawType.includes('warn') || rawType.includes('medium')
      ? 'warning'
      : 'info';
  return {
    type,
    text: stringifyValue(record.text || record.message || record.description || record.title || issue)
  };
};

const normalizeCheck = (check) => {
  const record = toRecord(check);
  return {
    name: stringifyValue(record.name || record.rule || record.key || record.code || check),
    status: stringifyValue(record.status || record.result || record.pass || 'unknown'),
    message: stringifyValue(record.message || record.detail || record.reason || '')
  };
};

const normalizeIssueCounts = (value) => {
  if (!value) return [];
  if (Array.isArray(value)) {
    return value.map((item, index) => {
      const record = toRecord(item);
      return {
        key: stringifyValue(record.key || record.type || record.name || `issue_${index + 1}`),
        count: toNumber(record.count || record.value || record.total, 0)
      };
    });
  }
  if (typeof value === 'object') {
    return Object.entries(value).map(([key, count]) => ({ key, count: toNumber(count, 0) }));
  }
  return [{ key: 'issues', count: toNumber(value, 0) }];
};

const getCaseBackendId = (caseItem) => caseItem?.backendId || caseItem?.raw?.id || caseItem?.id;

const normalizeQualityReview = (payload, fallbackCase) => {
  const root = toRecord(payload);
  const source = root.review && typeof root.review === 'object' ? root.review : root;
  const rawScore = source.score ?? source.quality_score ?? source.total_score;
  const score = rawScore === undefined || rawScore === null ? null : Math.max(0, Math.min(100, toNumber(rawScore, 0)));
  const issues = [
    ...toArray(source.issues || source.issue_list || source.problems || source.errors).map(normalizeIssue),
    ...toArray(source.warnings).map(item => normalizeIssue({ type: 'warning', text: stringifyValue(item) }))
  ];
  const suggestedActions = toArray(source.suggested_actions || source.suggestions || source.actions || source.recommendations)
    .map(stringifyValue);
  const duplicateCandidates = toArray(source.duplicate_candidates || source.duplicates || source.duplicateCases)
    .map((item) => {
      const record = toRecord(item);
      return {
        id: stringifyValue(record.case_number || record.case_id || record.id || item),
        title: stringifyValue(record.title || record.name || record.summary || '')
      };
    });
  const checks = toArray(source.checks || source.rules || source.check_results || source.validations).map(normalizeCheck);
  const fallbackScore = score ?? (issues.length ? 70 : 95);
  const reviewStatus = stringifyValue(source.review_status || source.status || (fallbackScore >= 85 ? 'approved' : 'changes_required'));

  return {
    caseId: stringifyValue(source.case_number || source.case_id || source.caseId || fallbackCase?.id),
    backendId: source.case_id || source.caseId || fallbackCase?.backendId,
    score: fallbackScore,
    review_status: reviewStatus,
    issues,
    suggested_actions: suggestedActions,
    duplicate_candidates: duplicateCandidates,
    checks,
    raw: payload
  };
};

const normalizeQualitySummary = (payload, fallbackCases, reviews = {}) => {
  const source = toRecord(payload?.summary || payload);
  const reviewValues = Object.values(reviews || {});
  const duplicateGroups = toArray(source.duplicate_groups || source.duplicateGroups || source.duplicates);
  const localAverage = reviewValues.length
    ? Math.round(reviewValues.reduce((total, item) => total + toNumber(item.score, 0), 0) / reviewValues.length)
    : 0;
  const fallbackNeedsReview = fallbackCases.filter(item => item.status !== '已通过').length;

  return {
    averageScore: toNumber(source.average_score ?? source.avg_score ?? source.score_avg ?? source.averageScore, localAverage),
    reviewRequiredCount: toNumber(source.review_required_count ?? source.need_review_count ?? source.needs_review_count ?? source.pending_review_count, fallbackNeedsReview),
    duplicateGroupCount: toNumber(source.duplicate_group_count ?? source.duplicate_groups_count ?? source.duplicate_count, duplicateGroups.length),
    unexecutableCount: toNumber(source.unexecutable_count ?? source.not_executable_count ?? source.non_executable_count, 0),
    priorityMismatchCount: toNumber(source.priority_mismatch_count ?? source.priority_inconsistent_count ?? source.priority_issue_count, 0),
    issueCounts: normalizeIssueCounts(source.issue_counts || source.issueCounts || {}),
    raw: payload
  };
};

export default function TestCases() {
  const { selectedProject, loading: projectLoading, error: projectError } = useProjectContext();
  const [strategy, setStrategy] = useState('standard'); // standard, boundary, risk, scenario, custom
  const [caseCount, setCaseCount] = useState(20);
  const [viewMode, setViewMode] = useState('list'); // 'list' or 'ai-review-diff'
  const [selectedCaseId, setSelectedCaseId] = useState('TC-20250520-0003'); // 默认选中待评审用例
  const [projectContext, setProjectContext] = useState(null);
  const [selectedLib, setSelectedLib] = useState(null);
  const [selectedRequirementItem, setSelectedRequirementItem] = useState(null);
  const [testcaseStatus, setTestcaseStatus] = useState({ loading: true, message: '' });
  const [isGeneratingCases, setIsGeneratingCases] = useState(false);
  const [isExportingCases, setIsExportingCases] = useState(false);
  const [qualitySummary, setQualitySummary] = useState(null);
  const [qualitySummaryStatus, setQualitySummaryStatus] = useState({ loading: false, message: '' });
  const [caseReviews, setCaseReviews] = useState({});
  const [selectedCaseIds, setSelectedCaseIds] = useState([]);
  const [reviewLoadingCaseId, setReviewLoadingCaseId] = useState(null);
  const [isBatchReviewing, setIsBatchReviewing] = useState(false);

  // 页用例列表
  const initialCases = [
    { id: 'TC-20250520-0001', title: '用户使用正确账号密码登录系统', priority: 'P0', type: '功能测试', ref: 'REQ-001.1', status: '已通过' },
    { id: 'TC-20250520-0002', title: '用户输入错误密码时提示错误信息', priority: 'P1', type: '功能测试', ref: 'REQ-001.2', status: '已通过' },
    { id: 'TC-20250520-0003', title: '连续错误登录 5 次后账号锁定', priority: 'P0', type: '异常测试', ref: 'REQ-001.3', status: '待评审' },
    { id: 'TC-20250520-0004', title: '未输入账号密码时登录按钮置灰', priority: 'P2', type: '界面测试', ref: 'REQ-001.4', status: '待评审' },
    { id: 'TC-20250520-0005', title: '点击“忘记密码”跳转到重置密码页', priority: 'P2', type: '功能测试', ref: 'REQ-001.5', status: '已通过' },
    { id: 'TC-20250520-0006', title: '重置密码邮件发送成功提示', priority: 'P2', type: '功能测试', ref: 'REQ-001.5', status: '已通过' },
    { id: 'TC-20250520-0007', title: '输入格式不正确的邮箱提示错误', priority: 'P1', type: '异常测试', ref: 'REQ-001.5', status: '待评审' },
    { id: 'TC-20250520-0008', title: '登录成功后跳转到首页', priority: 'P1', type: '功能测试', ref: 'REQ-001.1', status: '已通过' },
    { id: 'TC-20250520-0009', title: '会话超时后重新登录验证', priority: 'P2', type: '异常测试', ref: 'REQ-001.6', status: '待评审' },
    { id: 'TC-20250520-0010', title: '多端同时登录时会话冲突处理', priority: 'P2', type: '兼容性测试', ref: 'REQ-001.7', status: '待评审' },
  ];

  const [cases, setCases] = useState(initialCases);

  useEffect(() => {
    const handleCaseCreated = (e) => {
      if (e.detail?.case) {
        const newCase = {
          id: e.detail.case.id,
          title: e.detail.case.title,
          priority: e.detail.case.priority,
          type: e.detail.case.type,
          ref: e.detail.case.ref,
          status: e.detail.case.status || '待评审'
        };
        setCases(prev => [newCase, ...prev]);
        setSelectedCaseId(newCase.id);
      }
    };
    
    const handleCasesGenerated = (e) => {
      if (e.detail?.cases) {
        const newCases = e.detail.cases.map(c => ({
          id: c.id,
          title: c.title,
          priority: c.priority,
          type: c.type,
          ref: c.ref,
          status: c.status || '待评审'
        }));
        setCases(prev => [...newCases, ...prev]);
        if (newCases.length > 0) {
          setSelectedCaseId(newCases[0].id);
        }
      }
    };

    window.addEventListener('case-created', handleCaseCreated);
    window.addEventListener('cases-generated', handleCasesGenerated);

    return () => {
      window.removeEventListener('case-created', handleCaseCreated);
      window.removeEventListener('cases-generated', handleCasesGenerated);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadBackendCases = async () => {
      setTestcaseStatus({ loading: true, message: '正在同步后端测试用例...' });
      try {
        if (projectLoading) return;
        const project = selectedProject;
        if (!project?.id) {
          if (!cancelled) {
            setProjectContext(null);
            setSelectedLib(null);
            setSelectedRequirementItem(null);
            setTestcaseStatus({ loading: false, message: projectError || '后端暂无项目，显示演示用例' });
          }
          return;
        }

        const libsPayload = await apiGet(`/projects/${project.id}/requirement-libs`, { params: { page: 1, pageSize: 1 } });
        const lib = pickList(libsPayload)[0] || null;
        let requirementItem = null;
        if (lib?.id) {
          const itemsPayload = await apiGet(`/requirement-libs/${lib.id}/requirement-items`, { params: { page: 1, pageSize: 1 } });
          requirementItem = pickList(itemsPayload)[0] || null;
        }

        const caseParams = {
          page: 1,
          pageSize: 50,
          libId: lib?.id,
          requirementItemId: requirementItem?.id
        };
        const casesPayload = await apiGet(`/projects/${project.id}/test-cases`, { params: caseParams });
        const backendCases = pickList(casesPayload).map(mapBackendCase);

        if (cancelled) return;

        setProjectContext(project);
        setSelectedLib(lib);
        setSelectedRequirementItem(requirementItem ? {
          backendId: requirementItem.id,
          id: requirementItem.item_number || `REQ-${String(requirementItem.id).padStart(3, '0')}`,
          title: requirementItem.title || '未命名需求项'
        } : null);

        if (backendCases.length) {
          setCases(backendCases);
          setSelectedCaseId(backendCases[0].id);
        }

        const sourceName = project.name || project.code || `项目 #${project.id}`;
        setTestcaseStatus({
          loading: false,
          message: backendCases.length
            ? `已连接 ${sourceName}，更新时间 ${formatDateTime(project.updated_at || project.created_at)}`
            : '后端暂无测试用例，显示演示用例'
        });
      } catch (error) {
        if (!cancelled) {
          setTestcaseStatus({ loading: false, message: error?.message || '后端同步失败，显示演示用例' });
        }
      }
    };

    loadBackendCases();
    return () => {
      cancelled = true;
    };
  }, [projectLoading, projectError, selectedProject]);

  const handleOpenNewCaseModal = () => {
    window.dispatchEvent(new CustomEvent('open-modal', { detail: { type: 'new-case', data: { reqId: selectedRequirementItem?.id || 'REQ-00001' } } }));
  };

  const handleOpenAiGenerateModal = async () => {
    if (!selectedRequirementItem?.backendId) {
      window.dispatchEvent(new CustomEvent('open-modal', { detail: { type: 'generate-cases' } }));
      return;
    }

    setIsGeneratingCases(true);
    try {
      const generated = await apiPost(`/requirement-items/${selectedRequirementItem.backendId}/generate-test-cases`, {
        mode: strategy,
        count: caseCount
      });
      const mappedCases = (generated.cases || generated.test_cases || []).map(mapBackendCase);
      if (mappedCases.length) {
        setCases(prev => [...mappedCases, ...prev.filter(item => !mappedCases.some(newItem => newItem.backendId === item.backendId))]);
        setSelectedCaseId(mappedCases[0].id);
      }
      setTestcaseStatus({ loading: false, message: `已生成 ${mappedCases.length} 条后端用例` });
      window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: `已生成 ${mappedCases.length} 条后端测试用例。`, type: 'success' } }));
    } catch (error) {
      window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: error?.message || '测试用例生成失败。', type: 'error' } }));
    } finally {
      setIsGeneratingCases(false);
    }
  };

  const handleExportCases = async (format) => {
    if (!projectContext?.id && !selectedRequirementItem?.backendId) {
      window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '后端数据尚未同步，暂不能导出真实用例。', type: 'error' } }));
      return;
    }

    setIsExportingCases(true);
    try {
      const exported = await apiGet('/test-cases/export', {
        params: {
          projectId: projectContext?.id,
          requirementItemId: selectedRequirementItem?.backendId,
          format
        }
      });
      downloadTextFile({
        filename: exported.filename,
        content: exported.content,
        mimeType: exported.mime_type
      });
      window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '测试用例文件已开始下载。', type: 'success' } }));
    } catch (error) {
      window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: error?.message || '测试用例导出失败。', type: 'error' } }));
    } finally {
      setIsExportingCases(false);
    }
  };

  const showToast = (message, type = 'info') => {
    window.dispatchEvent(new CustomEvent('show-toast', { detail: { message, type } }));
  };

  const mapReviewStatusToCaseStatus = (reviewStatus) => {
    const normalized = String(reviewStatus || '').toLowerCase();
    if (['approved', 'passed', 'confirmed'].includes(normalized)) return '已通过';
    if (['changes_required', 'failed', 'rejected'].includes(normalized)) return '需优化';
    return '待评审';
  };

  const buildLocalQualityReview = (caseItem) => {
    const title = caseItem?.title || '';
    const issues = [];
    const checks = [
      {
        name: '标题可执行性',
        status: title.length >= 8 ? 'pass' : 'warning',
        message: title.length >= 8 ? '标题具备基本操作语义' : '标题过短，建议补充操作对象和期望结果'
      },
      {
        name: '优先级一致性',
        status: caseItem?.priority ? 'pass' : 'warning',
        message: caseItem?.priority ? `当前优先级为 ${caseItem.priority}` : '缺少优先级'
      },
      {
        name: '需求关联',
        status: caseItem?.ref ? 'pass' : 'warning',
        message: caseItem?.ref ? `已关联 ${caseItem.ref}` : '缺少需求项引用'
      }
    ];

    if (!title.includes('时间') && !title.includes('分钟') && title.includes('锁定')) {
      issues.push({ type: 'warning', text: '本地规则提示：锁定类用例建议明确时间窗口、锁定时长和解锁条件。' });
    }
    if (caseItem?.status !== '已通过') {
      issues.push({ type: 'info', text: '本地规则提示：该用例仍处于待评审状态，建议补充可观测断言。' });
    }

    const duplicateCandidates = cases
      .filter(item => item.id !== caseItem?.id && item.title && item.title === caseItem?.title)
      .map(item => ({ id: item.id, title: item.title }));

    return {
      caseId: caseItem?.id,
      backendId: getCaseBackendId(caseItem),
      score: Math.max(55, 95 - issues.length * 12 - duplicateCandidates.length * 8),
      review_status: issues.length || duplicateCandidates.length ? 'changes_required' : 'approved',
      issues,
      suggested_actions: issues.length
        ? ['补充前置条件、可观测断言和失败恢复路径。', '确认优先级与需求风险等级一致。']
        : ['当前本地规则未发现明显问题，可等待后端深度评审。'],
      duplicate_candidates: duplicateCandidates,
      checks,
      localFallback: true
    };
  };

  const loadProjectQualitySummary = async () => {
    if (!projectContext?.id) {
      setQualitySummary(normalizeQualitySummary(null, cases, caseReviews));
      setQualitySummaryStatus({ loading: false, message: '本地规则摘要，未连接后端质量汇总' });
      return;
    }

    setQualitySummaryStatus({ loading: true, message: '正在刷新质量摘要...' });
    try {
      const payload = await apiGet(`/projects/${projectContext.id}/test-case-quality-summary`);
      setQualitySummary(normalizeQualitySummary(payload, cases, caseReviews));
      setQualitySummaryStatus({ loading: false, message: '质量摘要已刷新' });
    } catch (error) {
      setQualitySummary(normalizeQualitySummary(null, cases, caseReviews));
      setQualitySummaryStatus({ loading: false, message: '后端质量摘要不可用，已展示本地规则摘要' });
      showToast(error?.message || '质量摘要接口不可用，已展示本地规则摘要。', 'error');
    }
  };

  useEffect(() => {
    loadProjectQualitySummary();
  }, [projectContext?.id, cases.length]);

  const requestSingleReview = async (caseItem) => {
    const endpointId = getCaseBackendId(caseItem);
    const body = {
      project_id: projectContext?.id,
      case_id: caseItem?.backendId,
      case_number: caseItem?.id,
      test_case: caseItem?.raw || caseItem
    };
    const attempts = [
      () => apiPost(`/test-cases/${endpointId}/quality-review`, body, { timeoutMs: 15000 }),
      () => apiPost('/test-cases/rule-validate', body, { timeoutMs: 15000 }),
      () => apiPost('/test-cases/ai-review', body, { timeoutMs: 20000 })
    ];

    let lastError = null;
    for (const attempt of attempts) {
      try {
        return await attempt();
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError;
  };

  const handleSingleQualityReview = async (caseId = selectedCaseId) => {
    const caseItem = cases.find(item => item.id === caseId);
    if (!caseItem) {
      showToast('请先选择一条用例。', 'error');
      return;
    }

    setReviewLoadingCaseId(caseItem.id);
    try {
      const payload = await requestSingleReview(caseItem);
      const review = normalizeQualityReview(payload, caseItem);
      setCaseReviews(prev => ({ ...prev, [caseItem.id]: review }));
      setCases(prev => prev.map(item => item.id === caseItem.id ? { ...item, status: mapReviewStatusToCaseStatus(review.review_status) } : item));
      showToast('质量评审已完成。', 'success');
      loadProjectQualitySummary();
    } catch (error) {
      const fallbackReview = buildLocalQualityReview(caseItem);
      setCaseReviews(prev => ({ ...prev, [caseItem.id]: fallbackReview }));
      setQualitySummary(normalizeQualitySummary(null, cases, { ...caseReviews, [caseItem.id]: fallbackReview }));
      showToast(error?.message || '后端质量评审不可用，已展示本地规则提示，未写入后端。', 'error');
    } finally {
      setReviewLoadingCaseId(null);
    }
  };

  const handleBatchQualityReview = async () => {
    const targetIds = selectedCaseIds.length ? selectedCaseIds : cases.map(item => item.id);
    const targets = cases.filter(item => targetIds.includes(item.id));
    if (!targets.length) {
      showToast('当前没有可评审的用例。', 'error');
      return;
    }

    setIsBatchReviewing(true);
    try {
      const payload = await apiPost('/test-cases/review-batch', {
        project_id: projectContext?.id,
        case_ids: targets.map(getCaseBackendId),
        case_numbers: targets.map(item => item.id),
        test_cases: targets.map(item => item.raw || item)
      }, { timeoutMs: 30000 });
      const resultItems = toArray(payload?.results || payload?.reviews || payload, ['results', 'reviews', 'items', 'cases']);
      const updatedReviews = {};

      resultItems.forEach((item, index) => {
        const record = toRecord(item);
        const matchedCase = targets.find(target => {
          const backendId = String(getCaseBackendId(target));
          return String(record.case_number || '') === String(target.id)
            || String(record.case_id || record.caseId || record.id || '') === backendId;
        }) || targets[index];
        if (matchedCase) {
          updatedReviews[matchedCase.id] = normalizeQualityReview(item, matchedCase);
        }
      });

      if (Object.keys(updatedReviews).length) {
        setCaseReviews(prev => ({ ...prev, ...updatedReviews }));
        setCases(prev => prev.map(item => updatedReviews[item.id] ? { ...item, status: mapReviewStatusToCaseStatus(updatedReviews[item.id].review_status) } : item));
      }
      if (payload?.summary) {
        setQualitySummary(normalizeQualitySummary(payload.summary, cases, { ...caseReviews, ...updatedReviews }));
      } else {
        loadProjectQualitySummary();
      }
      showToast(`批量评审已提交并处理 ${Object.keys(updatedReviews).length || targets.length} 条用例。`, 'success');
    } catch (error) {
      const fallbackReviews = targets.reduce((acc, item) => ({ ...acc, [item.id]: buildLocalQualityReview(item) }), {});
      setCaseReviews(prev => ({ ...prev, ...fallbackReviews }));
      setQualitySummary(normalizeQualitySummary(null, cases, { ...caseReviews, ...fallbackReviews }));
      showToast(error?.message || '批量评审接口不可用，已展示本地规则提示，未写入后端。', 'error');
    } finally {
      setIsBatchReviewing(false);
    }
  };

  const handleSaveReviewOpinion = async (decision) => {
    const caseItem = cases.find(item => item.id === selectedCaseId);
    if (!caseItem) {
      showToast('请先选择一条用例。', 'error');
      return;
    }

    const opinion = window.prompt(decision === 'approved' ? '请输入通过意见：' : '请输入需修改意见：');
    if (opinion === null) return;

    try {
      await apiPost(`/test-cases/${getCaseBackendId(caseItem)}/review-opinions`, {
        project_id: projectContext?.id,
        case_id: caseItem.backendId,
        case_number: caseItem.id,
        decision,
        opinion,
        comment: opinion
      });
      setCases(prev => prev.map(item => item.id === caseItem.id ? { ...item, status: mapReviewStatusToCaseStatus(decision) } : item));
      setCaseReviews(prev => ({
        ...prev,
        [caseItem.id]: {
          ...(prev[caseItem.id] || buildLocalQualityReview(caseItem)),
          review_status: decision,
          localFallback: false
        }
      }));
      showToast('评审意见已保存。', 'success');
      loadProjectQualitySummary();
    } catch (error) {
      showToast(error?.message || '保存评审意见失败，未写入后端。', 'error');
    }
  };

  const toggleCaseSelection = (caseId) => {
    setSelectedCaseIds(prev => prev.includes(caseId) ? prev.filter(id => id !== caseId) : [...prev, caseId]);
  };

  const toggleAllCaseSelection = () => {
    setSelectedCaseIds(prev => prev.length === cases.length ? [] : cases.map(item => item.id));
  };

  // 动态获取不同用例的 AI 评审结果
  const getAiReviewDetails = (caseId) => {
    const currentCase = cases.find(c => c.id === caseId);
    if (!currentCase) return null;

    const backendReview = caseReviews[caseId];
    if (backendReview) {
      const score = toNumber(backendReview.score, 0);
      const reviewStatus = String(backendReview.review_status || '').toLowerCase();
      const rating = reviewStatus === 'approved' || score >= 85 ? '质量达标' : '需修改';
      const colorClass = reviewStatus === 'approved' || score >= 85 ? 'text-[var(--accent-color)]' : 'text-amber-500';
      const circleColor = reviewStatus === 'approved' || score >= 85 ? 'var(--accent-color)' : '#f59e0b';
      const issues = toArray(backendReview.issues).map(normalizeIssue);
      const suggestedActions = toArray(backendReview.suggested_actions).map(stringifyValue);
      return {
        score,
        rating,
        colorClass,
        circleColor,
        review_status: backendReview.review_status,
        issues,
        suggested_actions: suggestedActions,
        duplicate_candidates: toArray(backendReview.duplicate_candidates),
        checks: toArray(backendReview.checks).map(normalizeCheck),
        suggestions: suggestedActions.length ? suggestedActions.join('；') : '后端质量评审已返回，暂无额外整改建议。',
        localFallback: backendReview.localFallback,
        details: {
          title: currentCase.title,
          precondition: stringifyValue(currentCase.raw?.precondition || '请以当前用例前置条件为准'),
          steps: toArray(currentCase.raw?.steps || currentCase.raw?.test_steps || ['请以当前用例步骤为准']).map(stringifyValue),
          expect: stringifyValue(currentCase.raw?.expected_result || currentCase.raw?.expect || '请以当前用例预期结果为准')
        }
      };
    }

    if (currentCase.status === '已通过') {
      return {
        score: 95,
        rating: '优质用例',
        colorClass: 'text-[var(--accent-color)]',
        circleColor: 'var(--accent-color)',
        issues: [],
        suggestions: '该用例测试目的明确，前置条件和测试步骤十分详尽，覆盖了主要的正向业务链路，无需额外优化。',
        details: {
          title: currentCase.title,
          precondition: '用户已注册成功，且处于未登录状态',
          steps: [
            '在用户名框输入正常已注册账号，密码框输入正确密码',
            '点击登录按钮',
            '确认系统是否成功登录并跳转至首页'
          ],
          expect: '登录成功，跳转至系统首页且显示用户信息'
        }
      };
    } else {
      // 待评审/需优化的用例
      if (caseId === 'TC-20250520-0003') {
        return {
          score: 65,
          rating: '一般用例',
          colorClass: 'text-amber-500',
          circleColor: '#f59e0b',
          issues: [
            { type: 'danger', text: '未定义冻结持续时间：账户锁定时未指明具体解冻时长（应为15分钟）。' },
            { type: 'warning', text: '缺少操作的时间窗口：错误登录的频次应限制在特定时间内（如5分钟内）。' },
            { type: 'info', text: '缺少安全预警机制：冻结时未指明是否需要给用户发送安全警报邮件。' }
          ],
          suggestions: '该测试用例中对于“锁定”的定义过于宽泛，在自动化测试中容易导致断言歧义。建议细化锁定的时间间隔、解锁条件及异频通知。',
          details: {
            title: currentCase.title,
            precondition: '用户已注册成功，且处于未登录状态',
            steps: [
              '在用户名框输入正常账号，密码框输入错误密码',
              '点击登录按钮，连续执行此操作 5 次'
            ],
            expect: '登录 5 次失败后，账号锁定，不允许再登录'
          }
        };
      }

      // 默认待评审
      return {
        score: 72,
        rating: '待完善',
        colorClass: 'text-amber-500',
        circleColor: '#f59e0b',
        issues: [
          { type: 'warning', text: '前置条件不够具体：未指明网络状态或系统初始环境配置。' },
          { type: 'info', text: '预期结果缺乏可观测的UI反馈：未指定具体的错误提示文本。' }
        ],
        suggestions: '该测试用例需要补充详细的预期错误文本以及输入框失焦状态下的 UI 响应，以便进行无侵入式端到端测试断言。',
        details: {
          title: currentCase.title,
          precondition: '系统处于就绪状态，已打开登录界面',
          steps: [
            '清空用户名与密码输入框',
            '点击登录按钮'
          ],
          expect: '系统应阻止提交，并显示错误提示'
        }
      };
    }
  };

  const activeReview = getAiReviewDetails(selectedCaseId);

  const renderAiReviewDiff = () => {
    const currentCase = cases.find(c => c.id === selectedCaseId) || {};
    return (
      <div className="space-y-4 animate-[fadeIn_0.2s_ease-out] w-full text-left">
        {/* 面包屑 */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <button 
              onClick={() => setViewMode('list')}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] text-[10.5px] text-[var(--text-secondary)] hover:bg-[var(--border-color)] transition-all hover:scale-[1.02] shadow-sm cursor-pointer"
            >
              <ArrowLeft className="size-3" />
              <span>返回用例库</span>
            </button>
            <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-secondary)]/70 font-semibold">
              <span>测试用例库</span>
              <span>/</span>
              <span>用户登录与认证</span>
              <span>/</span>
              <span className="text-[var(--text-primary)]">AI 评审优化对比</span>
            </div>
          </div>
          <button 
            onClick={() => {
              window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '已采纳 AI 评审，用例已更新并生效！', type: 'success' } }));
              setCases(prev => prev.map(c => c.id === selectedCaseId ? { ...c, title: '【AI优化】用户在 5 分钟内连续输入错误密码 5 次，系统锁定账号 15 分钟并发送通知邮件', status: '已通过' } : c));
              setViewMode('list');
            }}
            className="px-4 py-2 text-[11.5px] accent-btn"
          >
            采纳 AI 评审建议
          </button>
        </div>

        {/* 顶部简述 */}
        <div className="theme-card rounded-xl p-4 shadow-soft flex items-center justify-between">
          <div className="text-left">
            <div className="flex items-center gap-2">
              <span className="font-mono font-bold text-[var(--text-secondary)]">{selectedCaseId}</span>
              <h2 className="font-bold text-xs text-[var(--text-primary)]">{currentCase.title}</h2>
            </div>
            <p className="text-[10px] text-[var(--text-secondary)] mt-1.5 leading-none">关联需求项: {currentCase.ref || '—'} | 用例类型: {currentCase.type || '功能测试'}</p>
          </div>
          <div className="flex gap-4 text-[10px] font-bold">
            <div className="p-2.5 border border-[rgba(16,185,129,0.2)] bg-[rgba(16,185,129,0.05)] rounded-xl text-center">
              <div className="text-emerald-500 font-bold text-base leading-none">92</div>
              <div className="text-[8px] text-[var(--text-secondary)] mt-1">优化后质量分</div>
            </div>
            <div className="p-2.5 border border-[var(--border-color)] bg-[var(--border-color)]/20 rounded-xl text-center">
              <div className="font-bold text-base leading-none text-[var(--text-secondary)]">{activeReview?.score || 65}</div>
              <div className="text-[8px] text-[var(--text-secondary)] mt-1">原用例质量分</div>
            </div>
          </div>
        </div>

        {/* 左右 Diff 面板 */}
        <div className="grid grid-cols-12 gap-4">
          {/* 左边：原用例（高亮删除） */}
          <div className="col-span-6 theme-card rounded-xl p-4 shadow-soft text-left">
            <h3 className="text-xs font-bold text-red-500 border-b border-[rgba(239,68,68,0.15)] pb-2 mb-3">原始用例内容 (即将变更)</h3>
            <div className="space-y-4 font-sans text-[10.5px]">
              <div>
                <span className="font-bold text-[var(--text-secondary)] block">用例标题</span>
                <div className="bg-[rgba(239,68,68,0.08)] text-red-500 dark:text-red-400 p-2.5 rounded-lg mt-1 border border-[rgba(239,68,68,0.15)] font-medium">
                  {currentCase.title}
                </div>
              </div>
              
              <div>
                <span className="font-bold text-[var(--text-secondary)] block">前置条件</span>
                <div className="bg-[var(--border-color)]/40 p-2.5 rounded-lg mt-1 border border-[var(--border-color)] text-[var(--text-primary)]">
                  {activeReview?.details.precondition}
                </div>
              </div>

              <div>
                <span className="font-bold text-[var(--text-secondary)] block">测试步骤</span>
                <div className="space-y-2 mt-1.5">
                  {activeReview?.details.steps.map((st, i) => (
                    <div key={i} className="flex gap-2 p-2 bg-[rgba(239,68,68,0.04)] border border-[rgba(239,68,68,0.06)] rounded-lg">
                      <span className="font-bold text-red-400 opacity-60">{i + 1}.</span>
                      <span className="line-through text-red-500 dark:text-red-400">{st}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <span className="font-bold text-[var(--text-secondary)] block">预期结果</span>
                <div className="bg-[rgba(239,68,68,0.08)] text-red-500 dark:text-red-400 p-2.5 rounded-lg mt-1 border border-[rgba(239,68,68,0.15)] font-medium">
                  {activeReview?.details.expect}
                </div>
              </div>
            </div>
          </div>

          {/* 右边：优化后用例（高亮新增） */}
          <div className="col-span-6 theme-card rounded-xl p-4 shadow-soft text-left">
            <h3 className="text-xs font-bold text-[var(--accent-color)] border-b border-[var(--accent-glow)] pb-2 mb-3">AI 评审优化后内容 (规范无歧义)</h3>
            <div className="space-y-4 font-sans text-[10.5px]">
              <div>
                <span className="font-bold text-[var(--text-secondary)] block">用例标题</span>
                <div className="bg-[rgba(16,185,129,0.08)] text-emerald-600 dark:text-emerald-400 p-2.5 rounded-lg mt-1 border border-[rgba(16,185,129,0.15)] font-bold">
                  【AI优化】用户在 5 分钟内连续输入错误密码 5 次，系统锁定账号 15 分钟并发送通知邮件
                </div>
              </div>
              
              <div>
                <span className="font-bold text-[var(--text-secondary)] block">前置条件</span>
                <div className="bg-[var(--border-color)]/40 p-2.5 rounded-lg mt-1 border border-[var(--border-color)] text-[var(--text-primary)] font-bold">
                  用户已注册成功，且处于未登录状态，并确保邮箱接口状态正常。
                </div>
              </div>

              <div>
                <span className="font-bold text-[var(--text-secondary)] block">测试步骤</span>
                <div className="space-y-2 mt-1.5">
                  <div className="flex gap-2 p-2 bg-[rgba(16,185,129,0.04)] border border-[rgba(16,185,129,0.06)] rounded-lg font-bold">
                    <span className="font-bold text-emerald-500">1.</span>
                    <span className="text-emerald-700 dark:text-emerald-400">输入同一注册成功的用户名，并在5分钟内连续输入错误密码5次，操作间隔不超过15秒。</span>
                  </div>
                  <div className="flex gap-2 p-2 bg-[rgba(16,185,129,0.04)] border border-[rgba(16,185,129,0.06)] rounded-lg font-bold">
                    <span className="font-bold text-emerald-500">2.</span>
                    <span className="text-emerald-700 dark:text-emerald-400">在第 5 次登录失败时，验证界面是否立即弹出“账户已冻结，请于15分钟后再试”的红色警示，且登录按钮进入短暂禁用状态。</span>
                  </div>
                  <div className="flex gap-2 p-2 bg-[rgba(16,185,129,0.04)] border border-[rgba(16,185,129,0.06)] rounded-lg font-bold">
                    <span className="font-bold text-emerald-500">3.</span>
                    <span className="text-emerald-700 dark:text-emerald-400">登录用户注册绑定的邮箱，检查是否收到发件人为安全中心的“异频异常登录锁定提醒”警报邮件。</span>
                  </div>
                </div>
              </div>

              <div>
                <span className="font-bold text-[var(--text-secondary)] block">预期结果</span>
                <div className="bg-[rgba(16,185,129,0.08)] text-emerald-600 dark:text-emerald-400 p-2.5 rounded-lg mt-1 border border-[rgba(16,185,129,0.15)] font-bold">
                  系统在第5次失败后触发锁定条件，精准控制锁定时间为15分钟，拦截所有后续登录尝试；同时后台安全队列中成功分发并递送安全告警邮件给目标用户。
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const getStatusBadge = (status) => {
    if (status === '已通过') {
      return (
        <span className="px-2.5 py-0.5 rounded-full text-[9px] font-bold bg-[rgba(16,185,129,0.12)] text-emerald-600 dark:text-emerald-400 border border-[rgba(16,185,129,0.2)]">
          已通过
        </span>
      );
    }
    if (status === '需优化') {
      return (
        <span className="px-2.5 py-0.5 rounded-full text-[9px] font-bold bg-[rgba(239,68,68,0.1)] text-red-500 border border-[rgba(239,68,68,0.18)]">
          需优化
        </span>
      );
    }
    return (
      <span className="px-2.5 py-0.5 rounded-full text-[9px] font-bold bg-[rgba(245,158,11,0.12)] text-amber-600 dark:text-amber-400 border border-[rgba(245,158,11,0.2)] animate-pulse">
        待评审
      </span>
    );
  };

  const displayQualitySummary = qualitySummary || normalizeQualitySummary(null, cases, caseReviews);
  const displayIssueCounts = toArray(displayQualitySummary.issueCounts);

  return (
    <div className="space-y-4 text-left transition-all duration-300 w-full">
      {viewMode === 'ai-review-diff' ? (
        renderAiReviewDiff()
      ) : (
        <>
          {/* 顶栏 */}
          <div className="flex flex-wrap justify-between items-center gap-3 theme-card rounded-xl p-4 shadow-soft">
            <div className="flex flex-wrap gap-4 min-w-0">
              <div>
                <span className="text-[10px] text-[var(--text-secondary)] font-bold block mb-1">项目</span>
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)] text-[11px] font-bold text-[var(--text-primary)] cursor-pointer hover:bg-[var(--border-color)] transition-colors">
                  <span>{projectContext?.name || projectContext?.code || 'AI 测试演示项目'}</span>
                  <ChevronDown className="size-3.5 text-[var(--text-secondary)]" />
                </div>
              </div>
              <div>
                <span className="text-[10px] text-[var(--text-secondary)] font-bold block mb-1">需求库</span>
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)] text-[11px] font-bold text-[var(--text-primary)] cursor-pointer hover:bg-[var(--border-color)] transition-colors">
                  <span>{selectedLib?.name || '智能客服系统需求库 v1.2'}</span>
                  <ChevronDown className="size-3.5 text-[var(--text-secondary)]" />
                </div>
              </div>
              <div>
                <span className="text-[10px] text-[var(--text-secondary)] font-bold block mb-1">需求项</span>
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)] text-[11px] font-bold text-[var(--text-primary)] cursor-pointer hover:bg-[var(--border-color)] transition-colors">
                  <span>{selectedRequirementItem ? `${selectedRequirementItem.id} ${selectedRequirementItem.title}` : 'REQ-001 用户登录与认证'}</span>
                  <ChevronDown className="size-3.5 text-[var(--text-secondary)]" />
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <span className="text-[10px] text-[var(--text-secondary)] font-semibold hidden md:inline">
                {testcaseStatus.loading ? testcaseStatus.message : `用例库总数: ${cases.length} | ${testcaseStatus.message || '本地演示数据'}`}
              </span>
              <button 
                onClick={handleOpenNewCaseModal}
                className="px-3.5 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)] text-[11px] font-bold text-[var(--text-primary)] cursor-pointer transition-all"
              >
                + 手动新建
              </button>
              <button 
                onClick={handleOpenAiGenerateModal}
                disabled={isGeneratingCases}
                className="px-4 py-1.5 text-[11px] accent-btn"
              >
                <Sparkles className="size-3 text-white inline mr-1" />
                {isGeneratingCases ? '生成中...' : 'AI 批量生成'}
              </button>
            </div>
          </div>

          {/* R23 用例质量摘要 */}
          <div className="theme-card rounded-xl p-4 shadow-soft space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border-color)] pb-3">
              <div className="min-w-0">
                <h3 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
                  <CheckCircle className="size-4 text-[var(--accent-color)]" />
                  <span>用例质量评审与规则摘要</span>
                </h3>
                <p className="text-[9.5px] text-[var(--text-secondary)] mt-1">
                  {qualitySummaryStatus.loading ? qualitySummaryStatus.message : qualitySummaryStatus.message || '展示项目级质量规则统计'}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={loadProjectQualitySummary}
                  disabled={qualitySummaryStatus.loading}
                  className="px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)] text-[10px] font-bold text-[var(--text-primary)] cursor-pointer transition-all whitespace-nowrap disabled:opacity-60"
                >
                  {qualitySummaryStatus.loading ? '刷新中' : '刷新摘要'}
                </button>
                <button
                  onClick={handleBatchQualityReview}
                  disabled={isBatchReviewing}
                  className="px-3 py-1.5 rounded-lg bg-[var(--accent-color)] text-[var(--accent-text)] text-[10px] font-bold cursor-pointer hover:opacity-90 transition-all whitespace-nowrap disabled:opacity-60"
                >
                  {isBatchReviewing ? '评审中' : `批量评审${selectedCaseIds.length ? `(${selectedCaseIds.length})` : '(当前列表)'}`}
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-5 gap-2.5">
              {[
                { label: '平均分', value: displayQualitySummary.averageScore || '--', tone: 'text-[var(--accent-color)]' },
                { label: '需评审数', value: displayQualitySummary.reviewRequiredCount, tone: 'text-amber-500' },
                { label: '重复组', value: displayQualitySummary.duplicateGroupCount, tone: 'text-blue-500' },
                { label: '不可执行', value: displayQualitySummary.unexecutableCount, tone: 'text-red-500' },
                { label: '优先级不一致', value: displayQualitySummary.priorityMismatchCount, tone: 'text-purple-500' }
              ].map((item) => (
                <div key={item.label} className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/40 p-3 min-w-0">
                  <div className={`text-base font-bold leading-none ${item.tone}`}>{item.value}</div>
                  <div className="text-[9px] text-[var(--text-secondary)] font-bold mt-1.5 truncate">{item.label}</div>
                </div>
              ))}
            </div>

            <div className="flex flex-wrap gap-1.5">
              <span className="text-[9.5px] text-[var(--text-secondary)] font-bold py-1">issue_counts</span>
              {displayIssueCounts.length ? displayIssueCounts.map((item) => (
                <span key={item.key} className="px-2 py-1 rounded-md border border-[var(--border-color)] bg-[var(--bg-card)] text-[9px] text-[var(--text-primary)] font-semibold">
                  {item.key}: {item.count}
                </span>
              )) : (
                <span className="px-2 py-1 rounded-md border border-[var(--border-color)] bg-[var(--bg-card)] text-[9px] text-[var(--text-secondary)]">
                  暂无后端 issue_counts
                </span>
              )}
            </div>
          </div>

          {/* 7:5 选中联动双面板 */}
          <div className="grid grid-cols-12 gap-4 items-start w-full">
            {/* 左侧 7/12: 用例策略与生成结果 */}
            <div className="col-span-12 lg:col-span-7 space-y-4">
              
              {/* AI 生成配置区 */}
              <div className="theme-card rounded-xl p-4 shadow-soft space-y-3.5">
                <h3 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 flex items-center gap-1.5">
                  <Sparkles className="size-4 text-[var(--accent-color)] animate-pulse" />
                  <span>AI 用例智能生成策略</span>
                </h3>

                {/* 策略单选网格 */}
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2.5">
                  {[
                    { id: 'standard', label: '标准覆盖', desc: '基于需求项核心链路全覆盖' },
                    { id: 'boundary', label: '边界分析', desc: '聚焦边界输入与异常约束' },
                    { id: 'risk', label: '风险优先', desc: '优先深挖高危支付与越权场景' },
                    { id: 'scenario', label: '场景导向', desc: '拟真用户复杂链条行为生成' },
                    { id: 'custom', label: '自定义策略', desc: '灵活注入Prompt与校验规则' }
                  ].map((opt) => (
                    <div 
                      key={opt.id}
                      onClick={() => setStrategy(opt.id)}
                      className={`p-3 border rounded-xl cursor-pointer text-left transition-all ${
                        strategy === opt.id 
                          ? 'border-[var(--accent-color)] bg-[var(--accent-glow)] shadow-sm' 
                          : 'border-[var(--border-color)] bg-[var(--bg-app)]/40 hover:bg-[var(--border-color)]/30'
                      }`}
                    >
                      <input 
                        type="radio" 
                        checked={strategy === opt.id} 
                        onChange={() => {}} 
                        className="size-3 cursor-pointer accent-[var(--accent-color)]" 
                      />
                      <div className="text-[11px] font-bold text-[var(--text-primary)] mt-2">{opt.label}</div>
                      <div className="text-[9px] text-[var(--text-secondary)] mt-1 leading-tight">{opt.desc}</div>
                    </div>
                  ))}
                </div>

                {/* 类型与粒度配置行 */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-[var(--border-color)] pt-3 text-[10px] font-bold text-[var(--text-secondary)]">
                  <div>
                    <span className="text-[var(--text-secondary)] block mb-1.5">用例覆盖类型</span>
                    <div className="flex flex-wrap gap-1">
                      {['全部', '功能测试', '异常测试', '界面', '安全'].map((t, idx) => (
                        <span 
                          key={idx} 
                          className={`px-2.5 py-1.5 rounded-lg border text-[9.5px] cursor-pointer transition-all ${
                            idx === 0 
                              ? 'bg-[var(--accent-color)] text-[var(--accent-text)] border-[var(--accent-color)]' 
                              : 'bg-[var(--bg-card)] text-[var(--text-primary)] border-[var(--border-color)] hover:bg-[var(--border-color)]/50'
                          }`}
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div>
                    <span className="text-[var(--text-secondary)] block mb-1.5">生成用例粒度</span>
                    <div className="flex gap-1">
                      {['中粒度 (推荐)', '大粒度', '小粒度'].map((g, idx) => (
                        <span 
                          key={idx} 
                          className={`px-2.5 py-1.5 rounded-lg border text-[9.5px] cursor-pointer transition-all ${
                            idx === 0 
                              ? 'bg-[var(--accent-color)] text-[var(--accent-text)] border-[var(--accent-color)]' 
                              : 'bg-[var(--bg-card)] text-[var(--text-primary)] border-[var(--border-color)] hover:bg-[var(--border-color)]/50'
                          }`}
                        >
                          {g}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                {/* 模型参数与一键生成 */}
                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border-color)] pt-3.5">
                  <div className="flex flex-wrap gap-4 items-center">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-[var(--text-secondary)] font-bold">思考模型</span>
                      <div className="flex items-center gap-1 px-2.5 py-1 rounded border border-[var(--border-color)] bg-[var(--bg-app)] text-[10px] font-bold text-[var(--text-primary)] cursor-pointer">
                        <span>Gemini 1.5 Pro</span>
                        <ChevronDown className="size-3 text-[var(--text-secondary)]" />
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-[var(--text-secondary)] font-bold">数量</span>
                      <div className="flex items-center rounded border border-[var(--border-color)] bg-[var(--bg-app)] text-[10px] font-bold text-[var(--text-primary)] overflow-hidden">
                        <button onClick={() => setCaseCount(Math.max(5, caseCount - 5))} className="px-2 py-1 bg-[var(--bg-card)] text-center hover:bg-[var(--border-color)]">-</button>
                        <span className="px-3 py-1 text-center bg-transparent min-w-[20px]">{caseCount}</span>
                        <button onClick={() => setCaseCount(caseCount + 5)} className="px-2 py-1 bg-[var(--bg-card)] text-center hover:bg-[var(--border-color)]">+</button>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button 
                      onClick={handleOpenAiGenerateModal}
                      disabled={isGeneratingCases}
                      className="px-4 py-2 text-[11px] accent-btn"
                    >
                      <Sparkles className="size-3 text-white inline mr-1" />
                      {isGeneratingCases ? '正在生成...' : `生成用例 (${caseCount}条)`}
                    </button>
                  </div>
                </div>

              </div>

              {/* 生成结果 Table */}
              <div className="theme-card rounded-xl p-4 shadow-soft">
                <div className="flex justify-between items-center border-b border-[var(--border-color)] pb-2.5 mb-3.5">
                  <span className="text-xs font-bold text-[var(--text-primary)]">
                    生成结果列表 <span className="text-[10px] text-[var(--text-secondary)] font-semibold">(共 {cases.length} 条)</span>
                  </span>
                  <div className="flex items-center gap-2 text-[10px] font-bold text-[var(--text-secondary)]">
                    <button className="px-2 py-1 border border-[var(--border-color)] rounded bg-[var(--bg-card)] hover:bg-[var(--border-color)] text-[9.5px]">筛选</button>
                    <div className="flex border border-[var(--border-color)] rounded overflow-hidden">
                      <button className="bg-[var(--accent-glow)] text-[var(--text-primary)] border-r border-[var(--border-color)] px-2 py-1 text-[9.5px]">列表视图</button>
                      <button className="bg-[var(--bg-card)] px-2 py-1 text-[9.5px] hover:bg-[var(--border-color)]">看板</button>
                    </div>
                  </div>
                </div>

                <div className="overflow-x-auto w-full">
                  <table className="w-full text-[11px] text-left border-collapse min-w-[720px]">
                    <thead>
                      <tr className="text-[var(--text-secondary)] font-bold border-b border-[var(--border-color)]">
                        <th className="py-2 px-2 w-[24px]">
                          <input
                            type="checkbox"
                            checked={cases.length > 0 && selectedCaseIds.length === cases.length}
                            onChange={toggleAllCaseSelection}
                            className="rounded border-[var(--border-color)] accent-[var(--accent-color)]"
                          />
                        </th>
                        <th className="py-2 px-2">用例编号</th>
                        <th className="py-2 px-2">用例标题</th>
                        <th className="py-2 px-2 text-center">优先级</th>
                        <th className="py-2 px-2">类型</th>
                        <th className="py-2 px-2">需求项</th>
                        <th className="py-2 px-2 text-center">质量</th>
                        <th className="py-2 px-2 text-center">状态</th>
                        <th className="py-2 px-2 text-center">操作</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--border-color)] text-[var(--text-primary)] font-medium">
                      {cases.map((c) => {
                        const rowReview = caseReviews[c.id];
                        return (
                        <tr 
                          key={c.id} 
                          onClick={() => setSelectedCaseId(c.id)}
                          className={`cursor-pointer transition-all duration-150 ${
                            selectedCaseId === c.id 
                              ? 'bg-[var(--accent-glow)] border-l-2 border-l-[var(--accent-color)]' 
                              : 'hover:bg-[var(--border-color)]/30'
                          }`}
                        >
                          <td className="py-3 px-2" onClick={(e) => e.stopPropagation()}>
                            <input 
                              type="checkbox" 
                              checked={selectedCaseIds.includes(c.id)}
                              onChange={() => toggleCaseSelection(c.id)}
                              className="rounded border-[var(--border-color)] accent-[var(--accent-color)]" 
                            />
                          </td>
                          <td className="py-3 px-2 font-mono font-bold text-[var(--text-secondary)]">{c.id}</td>
                          <td className="py-3 px-2 font-bold truncate max-w-[200px] text-[var(--text-primary)]" title={c.title}>
                            {c.title}
                          </td>
                          <td className="py-3 px-2 text-center font-bold">
                            <span className={c.priority === 'P0' ? 'text-red-500' : 'text-[var(--text-secondary)]'}>
                              {c.priority}
                            </span>
                          </td>
                          <td className="py-3 px-2">
                            <span className="px-1.5 py-0.5 bg-[var(--border-color)]/70 text-[var(--text-secondary)] text-[9.5px] rounded">
                              {c.type}
                            </span>
                          </td>
                          <td className="py-3 px-2 text-[var(--accent-color)] font-bold">{c.ref}</td>
                          <td className="py-3 px-2 text-center">
                            {rowReview ? (
                              <span className={`font-bold ${toNumber(rowReview.score, 0) >= 85 ? 'text-[var(--accent-color)]' : 'text-amber-500'}`}>
                                {toNumber(rowReview.score, 0)}
                              </span>
                            ) : (
                              <span className="text-[var(--text-secondary)]">--</span>
                            )}
                          </td>
                          <td className="py-3 px-2 text-center">
                            {getStatusBadge(c.status)}
                          </td>
                          <td className="py-3 px-2 text-center" onClick={(e) => e.stopPropagation()}>
                            <button
                              onClick={() => handleSingleQualityReview(c.id)}
                              disabled={reviewLoadingCaseId === c.id}
                              className="px-2 py-1 rounded-md border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)] text-[9px] font-bold text-[var(--text-primary)] whitespace-nowrap disabled:opacity-60"
                            >
                              {reviewLoadingCaseId === c.id ? '评审中' : '单条评审'}
                            </button>
                          </td>
                        </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="flex justify-between items-center mt-4 border-t border-[var(--border-color)] pt-3">
                  <span className="text-[10px] text-[var(--text-secondary)]">共 {cases.length} 条</span>
                  <div className="flex items-center gap-1.5 text-[10px] text-[var(--text-secondary)]">
                    <button className="px-2 py-0.5 border border-[var(--border-color)] rounded bg-[var(--bg-card)] hover:bg-[var(--border-color)]">‹</button>
                    <button className="px-2.5 py-0.5 bg-[var(--accent-color)] text-[var(--accent-text)] rounded">1</button>
                    <button className="px-2.5 py-0.5 border border-[var(--border-color)] rounded bg-[var(--bg-card)] hover:bg-[var(--border-color)]">2</button>
                    <button className="px-2.5 py-0.5 border border-[var(--border-color)] rounded bg-[var(--bg-card)] hover:bg-[var(--border-color)]">›</button>
                  </div>
                </div>
              </div>

            </div>

            {/* 右侧 5/12: AI 用例评审与质量管家 */}
            <div className="col-span-12 lg:col-span-5 space-y-4">
              
              {/* AI 评审主要面板 (3D 倾斜眩光卡) */}
              <TiltCard className="p-4 shadow-soft animate-[slideUpFade_0.4s_ease-out]">
                <h3 
                  style={{ transform: 'translateZ(15px)' }}
                  className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 mb-3 text-left flex flex-wrap justify-between items-center gap-2"
                >
                  <span>AI 用例质量评审管家</span>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[10px] text-[var(--text-secondary)] font-normal font-mono">ID: {selectedCaseId}</span>
                    <button
                      onClick={() => handleSingleQualityReview(selectedCaseId)}
                      disabled={reviewLoadingCaseId === selectedCaseId}
                      className="px-2 py-1 rounded-md border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)] text-[9px] font-bold text-[var(--text-primary)] whitespace-nowrap disabled:opacity-60"
                    >
                      {reviewLoadingCaseId === selectedCaseId ? '评审中' : '评审当前'}
                    </button>
                  </div>
                </h3>

                {activeReview ? (
                  <div className="space-y-4 animate-[fadeIn_0.25s_ease-out]" style={{ transformStyle: 'preserve-3d' }}>
                    
                    {/* 环形图评分 */}
                    <div className="flex items-center gap-4 border-b border-[var(--border-color)] pb-4" style={{ transformStyle: 'preserve-3d', transform: 'translateZ(10px)' }}>
                      <div className="relative size-[88px] shrink-0" style={{ transformStyle: 'preserve-3d', transform: 'translateZ(25px)' }}>
                        <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                          <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--border-color)" strokeWidth="3" />
                          <circle 
                            cx="18" 
                            cy="18" 
                            r="15.9" 
                            fill="none" 
                            stroke={activeReview.circleColor} 
                            strokeWidth="3.2" 
                            strokeDasharray={`${activeReview.score} ${100 - activeReview.score}`} 
                            className="transition-all duration-1000 ease-out"
                          />
                        </svg>
                        <div className="absolute inset-0 flex flex-col items-center justify-center">
                          <span className="text-lg font-bold text-[var(--text-primary)] leading-none">
                            <AnimatedNumber value={activeReview.score} />
                          </span>
                          <span className="text-[7.5px] text-[var(--text-secondary)] scale-90 leading-none mt-1">质量分</span>
                        </div>
                      </div>

                      <div className="text-left space-y-1.5" style={{ transform: 'translateZ(20px)' }}>
                        <div className="flex items-center gap-2">
                          <span className={`text-[12.5px] font-bold ${activeReview.colorClass}`}>{activeReview.rating}</span>
                          <span className="text-[9.5px] text-[var(--text-secondary)]">（覆盖与完备度综合评分）</span>
                        </div>
                        <p className="text-[9.5px] text-[var(--text-secondary)] leading-relaxed">{activeReview.suggestions}</p>
                        <div className="flex flex-wrap gap-1.5">
                          <span className="px-2 py-0.5 rounded-full border border-[var(--border-color)] bg-[var(--bg-card)] text-[8.5px] text-[var(--text-secondary)] font-bold">
                            review_status: {activeReview.review_status || 'local_preview'}
                          </span>
                          {activeReview.localFallback && (
                            <span className="px-2 py-0.5 rounded-full border border-[rgba(245,158,11,0.25)] bg-[rgba(245,158,11,0.08)] text-[8.5px] text-amber-500 font-bold">
                              本地规则提示，未写入后端
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* 改进意见列表 */}
                    <div className="text-left">
                      <div className="text-[10.5px] font-bold text-[var(--text-primary)] mb-2">AI 校验缺陷排查与整改建议</div>
                      {activeReview.issues.length > 0 ? (
                        <div className="space-y-2 max-h-[160px] overflow-y-auto pr-1">
                          {activeReview.issues.map((iss, i) => (
                            <div 
                              key={i} 
                              className={`p-2.5 rounded-lg border text-[9.5px] flex items-start gap-2 ${
                                iss.type === 'danger' 
                                  ? 'bg-[rgba(239,68,68,0.06)] border-[rgba(239,68,68,0.15)] text-[var(--text-primary)]' 
                                  : iss.type === 'warning'
                                    ? 'bg-[rgba(245,158,11,0.06)] border-[rgba(245,158,11,0.15)] text-[var(--text-primary)]'
                                    : 'bg-[rgba(59,130,246,0.06)] border-[rgba(59,130,246,0.15)] text-[var(--text-primary)]'
                              }`}
                            >
                              <AlertCircle className={`size-3.5 shrink-0 mt-0.5 ${
                                iss.type === 'danger' ? 'text-red-500' : iss.type === 'warning' ? 'text-amber-500' : 'text-blue-500'
                              }`} />
                              <span className="leading-snug">{iss.text}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="p-3 bg-[rgba(16,185,129,0.06)] border border-[rgba(16,185,129,0.15)] rounded-lg text-[9.5px] text-[var(--text-secondary)] flex items-center gap-2">
                          <CheckCircle2 className="size-4 text-emerald-500 shrink-0" />
                          <span>完美！AI 评审未发现任何语义歧义与前置条件遗漏，符合一等测试用例规范。</span>
                        </div>
                      )}
                    </div>

                    {(activeReview.suggested_actions?.length > 0 || activeReview.duplicate_candidates?.length > 0 || activeReview.checks?.length > 0) && (
                      <div className="grid grid-cols-1 gap-2 text-left border-t border-[var(--border-color)] pt-3">
                        {activeReview.suggested_actions?.length > 0 && (
                          <div>
                            <div className="text-[10px] font-bold text-[var(--text-primary)] mb-1.5">suggested_actions</div>
                            <div className="flex flex-wrap gap-1.5">
                              {activeReview.suggested_actions.map((action, index) => (
                                <span key={`${action}-${index}`} className="px-2 py-1 rounded-md bg-[var(--accent-glow)]/40 border border-[var(--accent-glow)] text-[9px] text-[var(--text-primary)] font-semibold">
                                  {action}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {activeReview.duplicate_candidates?.length > 0 && (
                          <div>
                            <div className="text-[10px] font-bold text-[var(--text-primary)] mb-1.5">duplicate_candidates</div>
                            <div className="space-y-1">
                              {activeReview.duplicate_candidates.map((item, index) => (
                                <div key={`${item.id || index}-${index}`} className="px-2 py-1.5 rounded-md border border-[var(--border-color)] bg-[var(--bg-app)]/40 text-[9px] text-[var(--text-secondary)]">
                                  <span className="font-mono font-bold text-[var(--text-primary)]">{item.id || `候选 ${index + 1}`}</span>
                                  <span className="ml-1">{item.title || '可能重复用例'}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {activeReview.checks?.length > 0 && (
                          <div>
                            <div className="text-[10px] font-bold text-[var(--text-primary)] mb-1.5">checks</div>
                            <div className="space-y-1 max-h-[120px] overflow-y-auto pr-1">
                              {activeReview.checks.map((check, index) => (
                                <div key={`${check.name}-${index}`} className="flex items-start justify-between gap-2 px-2 py-1.5 rounded-md border border-[var(--border-color)] bg-[var(--bg-app)]/40 text-[9px]">
                                  <span className="font-bold text-[var(--text-primary)]">{check.name}</span>
                                  <span className="text-[var(--text-secondary)] text-right">{check.status}{check.message && check.message !== '暂无' ? ` · ${check.message}` : ''}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    <div className="flex flex-wrap gap-2 pt-2 border-t border-[var(--border-color)]">
                      <button
                        onClick={() => handleSaveReviewOpinion('approved')}
                        className="flex-1 min-w-[110px] py-1.5 bg-[rgba(16,185,129,0.1)] border border-[rgba(16,185,129,0.2)] text-emerald-600 dark:text-emerald-400 rounded-lg text-[10px] font-bold cursor-pointer text-center hover:bg-[rgba(16,185,129,0.16)] transition-all whitespace-nowrap"
                      >
                        保存通过意见
                      </button>
                      <button
                        onClick={() => handleSaveReviewOpinion('changes_required')}
                        className="flex-1 min-w-[110px] py-1.5 bg-[rgba(245,158,11,0.08)] border border-[rgba(245,158,11,0.2)] text-amber-600 dark:text-amber-400 rounded-lg text-[10px] font-bold cursor-pointer text-center hover:bg-[rgba(245,158,11,0.14)] transition-all whitespace-nowrap"
                      >
                        保存修改意见
                      </button>
                    </div>

                    {/* 操作按钮组 */}
                    {activeReview.score < 90 && (
                      <div className="flex gap-2 pt-2 border-t border-[var(--border-color)]">
                        <button 
                          onClick={() => setViewMode('ai-review-diff')}
                          className="flex-1 py-1.5 border border-[var(--accent-glow)] bg-[var(--accent-glow)]/40 hover:bg-[var(--accent-glow)] rounded-lg text-[10px] font-bold text-[var(--text-primary)] cursor-pointer text-center transition-all"
                        >
                          对比 AI 优化步骤
                        </button>
                        <button 
                          onClick={() => {
                            window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '用例已一键完成规范化修复！', type: 'success' } }));
                            setCases(prev => prev.map(c => c.id === selectedCaseId ? { ...c, title: '【AI优化】用户在 5 分钟内连续输入错误密码 5 次，系统锁定账号 15 分钟并发送通知邮件', status: '已通过' } : c));
                          }}
                          className="flex-1 py-1.5 bg-[var(--accent-color)] text-[var(--accent-text)] rounded-lg text-[10px] font-bold cursor-pointer text-center hover:opacity-90 transition-all shadow-[var(--accent-glow)]"
                        >
                          一键自愈修复
                        </button>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="py-12 flex flex-col items-center justify-center text-[var(--text-secondary)] gap-2">
                    <HelpCircle className="size-8 opacity-40 animate-bounce" />
                    <span className="text-[10px]">请在左侧列表中点击选择用例以开始 AI 评审</span>
                  </div>
                )}
              </TiltCard>

              {/* 用例片段库 */}
              <div className="theme-card rounded-xl p-4 shadow-soft text-left">
                <div className="flex justify-between items-center border-b border-[var(--border-color)] pb-2 mb-2.5">
                  <span className="text-xs font-bold text-[var(--text-primary)]">快捷用例片段库</span>
                  <span className="text-[9.5px] text-[var(--accent-color)] cursor-pointer hover:underline">维护模板</span>
                </div>
                <span className="text-[8px] text-[var(--text-secondary)] block mb-3">勾选通用测试步骤组合，快速构建复杂用例场景</span>

                <div className="space-y-2 text-[9px] font-semibold text-[var(--text-secondary)]">
                  {[
                    { label: '用户登录与验证码二次鉴权流程', type: '功能' },
                    { label: '高频连续重试锁定机制 (防刷爆)', type: '异常' },
                    { label: '多端会话互踢与单点登录 (SSO)', type: '兼容' },
                    { label: 'Token 过期静默重刷新链路', type: '安全' }
                  ].map((p, idx) => (
                    <div key={idx} className="flex items-center justify-between border-b border-[var(--border-color)]/50 pb-2 last:border-b-0">
                      <div className="flex items-center gap-2">
                        <input type="checkbox" className="rounded size-3 border-[var(--border-color)] accent-[var(--accent-color)] cursor-pointer" />
                        <span className="text-[var(--text-primary)]">{p.label}</span>
                      </div>
                      <span className="px-1.5 py-0.5 border border-[var(--border-color)] text-[8px] rounded bg-[var(--bg-app)]">
                        {p.type}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* 导出与分享 */}
              <div className="theme-card rounded-xl p-4 shadow-soft text-left space-y-2.5">
                <h3 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2">数据报表分发</h3>
                <div className="grid grid-cols-2 gap-2 text-center text-[10px] font-bold text-[var(--text-primary)]">
                  <button
                    onClick={() => handleExportCases('csv')}
                    disabled={isExportingCases}
                    className="flex items-center justify-center gap-1 p-2 border border-[var(--border-color)] rounded-lg hover:bg-[var(--border-color)]/30 cursor-pointer bg-[var(--bg-card)] transition-colors"
                  >
                    <Download className="size-3.5 text-[var(--text-secondary)]" />
                    <span>{isExportingCases ? '导出中' : '导出 CSV'}</span>
                  </button>
                  <button
                    onClick={() => handleExportCases('markdown')}
                    disabled={isExportingCases}
                    className="flex items-center justify-center gap-1 p-2 border border-[var(--border-color)] rounded-lg hover:bg-[var(--border-color)]/30 cursor-pointer bg-[var(--bg-card)] transition-colors"
                  >
                    <Download className="size-3.5 text-[var(--text-secondary)]" />
                    <span>{isExportingCases ? '导出中' : '导出 Markdown'}</span>
                  </button>
                </div>
              </div>

            </div>
          </div>
        </>
      )}
    </div>
  );
}
