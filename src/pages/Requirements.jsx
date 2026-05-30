import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { 
  Folder, 
  FileText, 
  CheckSquare, 
  Search, 
  Plus, 
  RotateCw, 
  ChevronRight, 
  ArrowLeft,
  Upload,
  Layers,
  HelpCircle,
  TrendingUp,
  Sliders,
  Sparkles,
  ChevronDown
} from 'lucide-react';
import TiltCard from '../components/TiltCard';
import AnimatedNumber from '../components/AnimatedNumber';
import { apiGet, apiPost, apiRequest, formatDateTime, pickList } from '../lib/api';
import { useProjectContext } from '../lib/projectContext';

const mapRequirementStatus = (status) => {
  const normalized = String(status || '').toLowerCase();
  if (['confirmed', 'done', 'completed'].includes(normalized)) return { status: '已确认', statusColor: 'bg-emerald-500' };
  if (['parsed', 'generated'].includes(normalized)) return { status: '已解析', statusColor: 'bg-emerald-500' };
  if (['draft', 'pending'].includes(normalized)) return { status: '待确认', statusColor: 'bg-amber-500' };
  return { status: status || '待确认', statusColor: 'bg-blue-500' };
};

const mapRequirementLib = (lib) => ({
  id: `LIB-${lib.id}`,
  backendId: lib.id,
  name: lib.name || `需求库 #${lib.id}`,
  desc: lib.description || '后端需求库',
  domain: lib.domain || '需求管理',
  docs: lib.document_count || 0,
  items: lib.item_count || 0,
  rate: '0%',
  status: '已创建',
  statusColor: 'bg-blue-500',
  time: formatDateTime(lib.updated_at || lib.created_at),
  owner: lib.owner_name || '系统',
  raw: lib
});

const mapRequirementDocument = (doc) => {
  const parsed = doc.parser_status === 'parsed';
  return {
    id: `DOC-${doc.id}`,
    backendId: doc.id,
    name: doc.source_file_name || doc.name || `需求文档 #${doc.id}`,
    user: '系统',
    time: formatDateTime(doc.updated_at || doc.created_at),
    size: doc.source_type || 'text',
    status: parsed ? '已解析' : '待解析',
    color: parsed ? 'text-emerald-500' : 'text-amber-500',
    raw: doc
  };
};

const getItemKey = (item) => String(item?.backendId || item?.id || '');

const getBlockKey = (block) => String(block?.block_key || block?.id || block?.anchor_id || '');

const pickArray = (value) => {
  if (Array.isArray(value)) return value;
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : value.split(',').map(part => part.trim()).filter(Boolean);
    } catch {
      return value.split(',').map(part => part.trim()).filter(Boolean);
    }
  }
  return [];
};

const firstDefined = (...values) => values.find(value => value !== undefined && value !== null);

const toDisplayArray = (value) => {
  if (value === undefined || value === null || value === '') return [];
  if (Array.isArray(value)) return value;
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      return toDisplayArray(parsed);
    } catch {
      return [value];
    }
  }
  if (typeof value !== 'object') return [value];

  const entries = Object.entries(value);
  const flattened = entries.flatMap(([key, entryValue]) => {
    if (entryValue === undefined || entryValue === null || entryValue === '') return [];
    if (Array.isArray(entryValue)) return entryValue.map(item => (typeof item === 'object' && item !== null ? { group: key, ...item } : { group: key, value: item }));
    if (typeof entryValue === 'object') return [{ group: key, ...entryValue }];
    return [{ group: key, value: entryValue }];
  });

  return flattened.length ? flattened : [value];
};

const toDisplayText = (value, fallback = '') => {
  if (value === undefined || value === null || value === '') return fallback;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return fallback || String(value);
  }
};

const readMetadata = (value) => {
  if (!value) return {};
  if (typeof value === 'object') return value;
  try {
    return JSON.parse(value);
  } catch {
    return {};
  }
};

const normalizeBlock = (block, index = 0) => {
  if (!block || typeof block !== 'object') {
    return {
      block_key: `BLOCK-${index + 1}`,
      block_type: 'text',
      section_path: '未分节',
      line_start: undefined,
      line_end: undefined,
      raw_text: toDisplayText(block),
      raw: block
    };
  }
  const metadata = readMetadata(block.metadata_json || block.metadata || block.meta);
  const blockKey = block.block_key || block.anchor_id || block.id || `BLOCK-${index + 1}`;
  return {
    block_key: String(blockKey),
    block_type: block.block_type || block.type || 'paragraph',
    section_path: block.section_path || block.heading_path || block.section || '未分节',
    line_start: metadata.line_start ?? block.line_start ?? block.start_line,
    line_end: metadata.line_end ?? block.line_end ?? block.end_line,
    raw_text: block.raw_text || block.text || block.content || block.summary || '',
    raw: block
  };
};

const mapRequirementItem = (item) => {
  const statusMeta = mapRequirementStatus(item.status);
  const confidence = Number(item.confidence);
  return {
    id: item.item_number || `REQ-${String(item.id).padStart(5, '0')}`,
    backendId: item.id,
    title: item.title || `需求项 #${item.id}`,
    module: item.module || '未分组',
    actor: item.actor || '',
    goal: item.goal || '',
    priority: item.priority || 'P2',
    status: statusMeta.status,
    rawStatus: item.status || 'draft',
    granularityFlag: item.granularity_flag || item.granularityFlag || '',
    sourceAnchorIds: pickArray(item.source_anchor_ids || item.sourceAnchorIds),
    rate: Number.isFinite(confidence) && confidence > 0 ? `${Math.round(confidence * 100)}%` : '0%',
    summary: item.summary,
    raw: item
  };
};

export default function Requirements() {
  const { selectedProject, loading: projectLoading, error: projectError } = useProjectContext();
  const [viewMode, setViewMode] = useState('list'); // 'list' or 'workbench'
  const [selectedDocId, setSelectedDocId] = useState(null);
  const [selectedLibIndex, setSelectedLibIndex] = useState(0);
  const [projectContext, setProjectContext] = useState(null);
  const [remoteLibs, setRemoteLibs] = useState([]);
  const [remoteDocs, setRemoteDocs] = useState([]);
  const [remoteItems, setRemoteItems] = useState([]);
  const [requirementsStatus, setRequirementsStatus] = useState({ loading: true, message: '' });
  const [isCreatingLib, setIsCreatingLib] = useState(false);
  const [isCreatingDocument, setIsCreatingDocument] = useState(false);
  const [isGeneratingPoints, setIsGeneratingPoints] = useState(false);
  const [parseBlocks, setParseBlocks] = useState([]);
  const [selectedItemKeys, setSelectedItemKeys] = useState([]);
  const [editDraft, setEditDraft] = useState(null);
  const [itemQuality, setItemQuality] = useState({});
  const [traceability, setTraceability] = useState({});
  const [brainResult, setBrainResult] = useState(null);
  const [actionLoading, setActionLoading] = useState('');

  // ==========================================================================
  // VIEW 1: 需求库列表页 (11-页)
  // ==========================================================================
  
  const listStats = [
    { label: '需求库总数', val: remoteLibs.length || '24', change: remoteLibs.length ? '后端实时' : '↑ 2', icon: Folder, color: 'text-blue-500 bg-blue-500/10' },
    { label: '待解析库', val: remoteLibs.length ? remoteDocs.filter(doc => doc.status !== '已解析').length : '3', change: remoteLibs.length ? '当前库' : '↓ 1', icon: FileText, color: 'text-amber-500 bg-amber-500/10' },
    { label: '待确认库', val: remoteLibs.length ? remoteItems.filter(item => item.status !== '已确认').length : '5', change: remoteLibs.length ? '当前库' : '↑ 1', icon: FileText, color: 'text-blue-500 bg-blue-500/10' },
    { label: '覆盖率健康度', val: '78.4%', change: '↑ 1.6%', hasChart: true }
  ];

  const fallbackRequirementLibs = [
    { name: '智能客服系统需求库', desc: '客户服务与工单管理相关需求', domain: '客户服务', docs: 8, items: 1248, rate: '86.7%', status: '已完成', statusColor: 'bg-emerald-500', time: '2025-05-20 10:25', owner: '张明' },
    { name: '电商平台 V2.3 需求库', desc: '商品、订单、支付等核心流程需求', domain: '电子商务', docs: 12, items: 2156, rate: '91.2%', status: '已完成', statusColor: 'bg-emerald-500', time: '2025-05-19 16:48', owner: '李华' },
    { name: '支付网关需求库', desc: '支付接口与交易处理需求', domain: '支付金融', docs: 6, items: 854, rate: '74.5%', status: '待确认', statusColor: 'bg-amber-500', time: '2025-05-19 14:12', owner: '王芳' },
    { name: '数据中台需求库', desc: '数据采集、治理与服务化需求', domain: '数据中台', docs: 10, items: 1632, rate: '68.3%', status: '待确认', statusColor: 'bg-amber-500', time: '2025-05-18 11:33', owner: '赵强' },
    { name: '会员系统需求库', desc: '会员注册、积分、等级等需求', domain: '会员中心', docs: 5, items: 672, rate: '93.6%', status: '已完成', statusColor: 'bg-emerald-500', time: '2025-05-18 09:05', owner: '陈磊' },
    { name: '营销活动需求库', desc: '活动创建、优惠券、营销工具需求', domain: '营销活动', docs: 7, items: 1023, rate: '81.4%', status: '已完成', statusColor: 'bg-emerald-500', time: '2025-05-17 17:20', owner: '刘洋' },
    { name: '移动端 App 需求库', desc: 'iOS / Android 客户端相关需求', domain: '移动端', docs: 9, items: 1784, rate: '72.1%', status: '解析中', statusColor: 'bg-blue-500 animate-pulse', time: '2025-05-17 13:50', owner: '周敏' },
    { name: '报表系统需求库', desc: '报表中心与数据可视化需求', domain: '报表分析', docs: 4, items: 483, rate: '60.2%', status: '待解析', statusColor: 'bg-slate-400', time: '2025-05-16 10:40', owner: '孙伟' }
  ];

  const libDocs = [
    [
      { name: 'PRD_智能客服系统V2.1.docx', user: '张明', time: '10:24', size: '2.4 MB', status: '已解析', color: 'text-blue-500' },
      { name: '产品需求说明书_V2.1.pdf', user: '李华', time: '10:15', size: '3.1 MB', status: '已解析', color: 'text-red-500' },
      { name: '接口规范_客服平台_V2.1.xlsx', user: '王芳', time: '09:47', size: '1.8 MB', status: '已解析', color: 'text-emerald-500' }
    ],
    [
      { name: '电商平台_支付模块PRD_v2.3.docx', user: '李华', time: '昨天', size: '4.2 MB', status: '已解析', color: 'text-blue-500' },
      { name: '购物车结算变更文档.xlsx', user: '张明', time: '前天', size: '2.1 MB', status: '已解析', color: 'text-emerald-500' }
    ],
    [
      { name: '支付网关核心交易逻辑设计.pdf', user: '王芳', time: '05-19', size: '3.6 MB', status: '已解析', color: 'text-red-500' }
    ]
  ];

  // ==========================================================================
  // VIEW 2: 需求库详情分析工作台 (12-页)
  // ==========================================================================

  // 12-页：文档列表
  const fallbackDocsList = [
    { name: 'PRD_智能客服系统V2.1.docx', size: '2.4 MB', status: '已解析' },
    { name: '产品需求说明书_V2.1.pdf', size: '3.1 MB', status: '已解析' },
    { name: '接口规范_客服平台_V2.1.xlsx', size: '1.8 MB', status: '已解析' },
    { name: '数据库设计说明书_V2.1.docx', size: '2.7 MB', status: '已解析' },
    { name: '业务流程图_客服系统V2.1.xmind', size: '1.2 MB', status: '已解析' }
  ];

  // 12-页：结构化需求项
  const fallbackWorkbenchItems = [
    { id: 'REQ-00001', title: '用户登录与认证', module: '用户管理', priority: 'P0', status: '已确认', rate: '95%' },
    { id: 'REQ-00002', title: '第三方登录 (微信/支付宝)', module: '用户管理', priority: 'P1', status: '已确认', rate: '92%' },
    { id: 'REQ-00003', title: '会话列表展示', module: '会话管理', priority: 'P1', status: '已确认', rate: '90%' },
    { id: 'REQ-00004', title: '发送文本消息', module: '消息处理', priority: 'P0', status: '已确认', rate: '97%' },
    { id: 'REQ-00005', title: '发送图片消息', module: '消息处理', priority: 'P1', status: '待确认', rate: '85%' },
    { id: 'REQ-00006', title: '消息撤回与提示', module: '消息处理', priority: 'P2', status: '待确认', rate: '80%' }
  ];

  const [activeItem, setActiveItem] = useState(fallbackWorkbenchItems[3]); // 默认选中 REQ-00004 发送文本消息
  const [workbenchTab, setWorkbenchTab] = useState('testpoints'); // testpoints, questions, scope
  const requirementsLibs = remoteLibs.length ? remoteLibs : fallbackRequirementLibs;
  const docsList = remoteDocs.length ? remoteDocs : fallbackDocsList;
  const workbenchItems = remoteItems.length ? remoteItems : fallbackWorkbenchItems;
  const selectedBackendLibId = remoteLibs[selectedLibIndex]?.backendId;
  const selectedDoc = remoteDocs.find(doc => String(doc.backendId) === String(selectedDocId)) || remoteDocs[0];
  const blockLookup = useMemo(() => {
    const lookup = new Map();
    parseBlocks.forEach(block => lookup.set(getBlockKey(block), block));
    return lookup;
  }, [parseBlocks]);
  const activeItemKey = getItemKey(activeItem);
  const activeQuality = itemQuality[activeItemKey];
  const activeTraceability = traceability[activeItemKey];
  const activeAnchors = useMemo(() => {
    const ids = activeItem?.sourceAnchorIds || [];
    return ids.map(id => blockLookup.get(String(id))).filter(Boolean);
  }, [activeItem, blockLookup]);
  const brainRisks = toDisplayArray(brainResult?.risks || brainResult?.risk_items || brainResult?.riskItems);
  const brainSourceRefs = toDisplayArray(firstDefined(brainResult?.source_refs, brainResult?.sourceRefs, brainResult?.sources, brainResult?.refs));
  const activeSourceBlocks = toDisplayArray(activeTraceability?.source_blocks || activeTraceability?.sourceBlocks);
  const activeTestPoints = toDisplayArray(activeTraceability?.test_points || activeTraceability?.testPoints);
  const activeTestCases = toDisplayArray(activeTraceability?.test_cases || activeTraceability?.testCases);
  const activeQualityIssues = toDisplayArray(activeQuality?.issues);
  const activeQualityActions = toDisplayArray(activeQuality?.suggested_actions || activeQuality?.suggestedActions);

  const showToast = (message, type = 'success') => {
    window.dispatchEvent(new CustomEvent('show-toast', { detail: { message, type } }));
  };

  const handleExportRequirementReport = () => {
    if (!selectedBackendLibId) {
      showToast('当前没有真实需求库，无法导出后端报告。', 'info');
      return;
    }
    showToast('需求分析 PDF 报告导出未开放；请到报告中心使用 HTML/Markdown/JSON 真实导出，不会生成假文件。', 'info');
  };

  const loadRequirementLibDetails = useCallback(async () => {
    if (!selectedBackendLibId) {
      setRemoteDocs([]);
      setRemoteItems([]);
      setSelectedItemKeys([]);
      return;
    }

    const [docsPayload, itemsPayload] = await Promise.all([
      apiGet(`/requirement-libs/${selectedBackendLibId}/documents`, { params: { page: 1, pageSize: 50 } }),
      apiGet(`/requirement-libs/${selectedBackendLibId}/requirement-items`, { params: { page: 1, pageSize: 100 } })
    ]);
    const mappedDocs = pickList(docsPayload).map(mapRequirementDocument);
    const mappedItems = pickList(itemsPayload).map(mapRequirementItem);
    setRemoteDocs(mappedDocs);
    setRemoteItems(mappedItems);
    setSelectedItemKeys(prev => prev.filter(key => mappedItems.some(item => getItemKey(item) === key)));
    if (mappedItems.length) {
      setActiveItem(prev => (mappedItems.some(item => item.backendId === prev?.backendId) ? mappedItems.find(item => item.backendId === prev?.backendId) : mappedItems[0]));
    }
  }, [selectedBackendLibId]);

  useEffect(() => {
    let cancelled = false;

    async function loadRequirementLibs() {
      setRequirementsStatus({ loading: true, message: '正在同步后端需求库...' });
      try {
        if (projectLoading) return;
        const project = selectedProject;
        if (!project?.id) {
          if (!cancelled) {
            setProjectContext(null);
            setRemoteLibs([]);
            setRequirementsStatus({ loading: false, message: projectError || '后端暂无项目，显示演示需求库' });
          }
          return;
        }

        const libsPayload = await apiGet(`/projects/${project.id}/requirement-libs`, { params: { page: 1, pageSize: 50 } });
        const mappedLibs = pickList(libsPayload).map(mapRequirementLib);

        if (cancelled) return;
        setProjectContext(project);
        setRemoteLibs(mappedLibs);
        setSelectedLibIndex(prev => (mappedLibs[prev] ? prev : 0));
        setRequirementsStatus({
          loading: false,
          message: mappedLibs.length ? `已连接：${project.name || project.code || project.id}` : '后端暂无需求库，显示演示需求库'
        });
      } catch (error) {
        if (!cancelled) {
          setProjectContext(null);
          setRemoteLibs([]);
          setRequirementsStatus({ loading: false, message: error?.message || '后端暂不可用，显示演示需求库' });
        }
      }
    }

    loadRequirementLibs();
    return () => {
      cancelled = true;
    };
  }, [projectLoading, projectError, selectedProject]);

  useEffect(() => {
    let cancelled = false;

    loadRequirementLibDetails().catch(error => {
      if (!cancelled) {
        setRemoteDocs([]);
        setRemoteItems([]);
        setRequirementsStatus({ loading: false, message: error?.message || '需求库详情同步失败，显示演示数据' });
      }
    });

    return () => {
      cancelled = true;
    };
  }, [loadRequirementLibDetails]);

  useEffect(() => {
    if (!activeItem) {
      setEditDraft(null);
      return;
    }
    setEditDraft({
      title: activeItem.title || '',
      summary: activeItem.summary || '',
      module: activeItem.module || '',
      actor: activeItem.actor || '',
      goal: activeItem.goal || '',
      priority: activeItem.priority || 'P2',
      status: activeItem.rawStatus || activeItem.raw?.status || 'draft'
    });
  }, [activeItem]);

  const handleCreateRequirementLib = async () => {
    if (!projectContext?.id) {
      showToast('后端暂无可用项目，无法创建真实需求库。', 'error');
      return;
    }
    setIsCreatingLib(true);
    try {
      const created = await apiPost(`/projects/${projectContext.id}/requirement-libs`, {
        name: `${projectContext.name || '项目'} 前端接入需求库`,
        description: '由前端 Round 14 集成创建的真实需求库。'
      });
      const mapped = mapRequirementLib(created);
      setRemoteLibs(prev => [mapped, ...prev.filter(item => item.backendId !== mapped.backendId)]);
      setSelectedLibIndex(0);
      setRequirementsStatus({ loading: false, message: '真实需求库已创建' });
      showToast('新建需求库已写入后端。');
    } catch (error) {
      showToast(error?.message || '新建需求库失败。', 'error');
    } finally {
      setIsCreatingLib(false);
    }
  };

  const handleCreateRequirementDocument = async () => {
    if (!projectContext?.id || !selectedBackendLibId) {
      showToast('请先选择一个后端需求库。', 'error');
      return;
    }
    setIsCreatingDocument(true);
    try {
      const document = await apiPost(`/projects/${projectContext.id}/requirement-documents`, {
        lib_id: selectedBackendLibId,
        name: `前端导入需求说明 ${new Date().toLocaleTimeString('zh-CN', { hour12: false })}`,
        source_type: 'text',
        raw_content: '用户可以登录系统；错误密码需要提示并记录失败次数；连续失败后账号应被锁定并产生安全提示。'
      });
      const parsed = await apiPost(`/requirement-documents/${document.id}/parse`, { parse_mode: 'standard' });
      const extracted = await apiPost(`/requirement-documents/${document.id}/extract-items`, { mode: 'frontend' });
      setSelectedDocId(document.id);
      setParseBlocks((parsed?.blocks || pickList(parsed)).map(normalizeBlock));
      setRemoteDocs(prev => [mapRequirementDocument({ ...document, parser_status: 'parsed' }), ...prev]);
      const extractedItems = (extracted?.items || []).map(mapRequirementItem);
      setRemoteItems(prev => [...extractedItems, ...prev]);
      if (extractedItems.length) setActiveItem(extractedItems[0]);
      showToast('需求文档已导入、解析并提取需求项。');
    } catch (error) {
      showToast(error?.message || '需求文档导入失败。', 'error');
    } finally {
      setIsCreatingDocument(false);
    }
  };

  const handleGenerateTestPoints = async () => {
    if (!activeItem?.backendId) {
      showToast('当前为演示需求项，无法写入真实测试点。', 'info');
      return;
    }
    setIsGeneratingPoints(true);
    try {
      const result = await apiPost(`/requirement-items/${activeItem.backendId}/generate-test-points`, { mode: 'frontend' });
      showToast(`已生成 ${result.test_points?.length || 0} 个测试点。`);
    } catch (error) {
      showToast(error?.message || '测试点生成失败。', 'error');
    } finally {
      setIsGeneratingPoints(false);
    }
  };

  const refreshAfterAction = async () => {
    try {
      await loadRequirementLibDetails();
    } catch (error) {
      showToast(error?.message || '刷新需求项失败，请稍后重试。', 'error');
    }
  };

  const handleSaveActiveItem = async () => {
    if (!activeItem?.backendId || !editDraft) {
      showToast('当前为演示需求项，无法保存到后端。', 'info');
      return;
    }
    setActionLoading('save');
    try {
      const saved = await apiRequest(`/requirement-items/${activeItem.backendId}`, {
        method: 'PATCH',
        body: {
          title: editDraft.title,
          summary: editDraft.summary,
          module: editDraft.module,
          actor: editDraft.actor,
          goal: editDraft.goal,
          priority: editDraft.priority,
          status: editDraft.status
        }
      });
      const mapped = mapRequirementItem({ ...activeItem.raw, ...saved, ...editDraft, id: activeItem.backendId });
      setRemoteItems(prev => prev.map(item => (item.backendId === activeItem.backendId ? mapped : item)));
      setActiveItem(mapped);
      showToast('需求项已保存。');
    } catch (error) {
      showToast(error?.message || '保存需求项失败。', 'error');
    } finally {
      setActionLoading('');
    }
  };

  const handleConfirmActiveItem = async () => {
    if (!activeItem?.backendId) {
      showToast('当前为演示需求项，无法确认入库。', 'info');
      return;
    }
    setActionLoading('confirm');
    try {
      await apiPost(`/requirement-items/${activeItem.backendId}/confirm`, {});
      await refreshAfterAction();
      showToast('需求项已确认入库。');
    } catch (error) {
      showToast(error?.message || '确认需求项失败。', 'error');
    } finally {
      setActionLoading('');
    }
  };

  const handleShelveActiveItem = async () => {
    if (!activeItem?.backendId) {
      showToast('当前为演示需求项，无法搁置。', 'info');
      return;
    }
    setActionLoading('shelve');
    try {
      await apiPost(`/requirement-items/${activeItem.backendId}/shelve`, {});
      await refreshAfterAction();
      showToast('需求项已暂不入库。', 'info');
    } catch (error) {
      showToast(error?.message || '搁置需求项失败。', 'error');
    } finally {
      setActionLoading('');
    }
  };

  const handleSplitActiveItem = async () => {
    if (!activeItem?.backendId) {
      showToast('当前为演示需求项，无法拆分。', 'info');
      return;
    }
    const input = window.prompt('请输入 2 个子项，每行一个。格式：标题 | 摘要', `${activeItem.title} - 子项1 | ${activeItem.summary || ''}\n${activeItem.title} - 子项2 | ${activeItem.summary || ''}`);
    const parts = (input || '')
      .split('\n')
      .map(line => line.trim())
      .filter(Boolean)
      .map(line => {
        const [title, ...summaryParts] = line.split('|');
        return { title: title.trim(), summary: summaryParts.join('|').trim() };
      })
      .filter(part => part.title);
    if (parts.length < 2) {
      showToast('拆分至少需要 2 个子项。', 'info');
      return;
    }
    setActionLoading('split');
    try {
      await apiPost(`/requirement-items/${activeItem.backendId}/split`, { parts });
      await refreshAfterAction();
      showToast(`已拆分为 ${parts.length} 个子项。`);
    } catch (error) {
      showToast(error?.message || '拆分需求项失败。', 'error');
    } finally {
      setActionLoading('');
    }
  };

  const handleMergeSelectedItems = async () => {
    const selectedItems = workbenchItems.filter(item => selectedItemKeys.includes(getItemKey(item)) && item.backendId);
    if (selectedItems.length < 2) {
      showToast('请选择至少 2 个真实需求项后再合并。', 'info');
      return;
    }
    const title = window.prompt('合并后的需求标题（可选）', selectedItems.map(item => item.title).join(' / '));
    setActionLoading('merge');
    try {
      await apiPost('/requirement-items/merge', {
        item_ids: selectedItems.map(item => item.backendId),
        ...(title ? { title, summary: selectedItems.map(item => item.summary || item.title).join('\n') } : {})
      });
      setSelectedItemKeys([]);
      await refreshAfterAction();
      showToast(`已合并 ${selectedItems.length} 个需求项。`);
    } catch (error) {
      showToast(error?.message || '合并需求项失败。', 'error');
    } finally {
      setActionLoading('');
    }
  };

  const handleQualityCheckActiveItem = async () => {
    if (!activeItem?.backendId) {
      showToast('当前为演示需求项，无法进行后端质检。', 'info');
      return;
    }
    setActionLoading('quality');
    try {
      const result = await apiPost(`/requirement-items/${activeItem.backendId}/quality-check`, {});
      setItemQuality(prev => ({ ...prev, [activeItemKey]: result }));
      if (result?.granularity_flag) {
        setRemoteItems(prev => prev.map(item => (
          item.backendId === activeItem.backendId ? { ...item, granularityFlag: result.granularity_flag } : item
        )));
        setActiveItem(prev => ({ ...prev, granularityFlag: result.granularity_flag }));
      }
      showToast(`粒度质检完成，评分 ${result?.score ?? '--'}。`);
    } catch (error) {
      showToast(error?.message || '粒度质检失败。', 'error');
    } finally {
      setActionLoading('');
    }
  };

  const handleBrainAnalyze = async () => {
    if (!selectedBackendLibId) {
      showToast('当前为演示需求库，无法调用需求大脑。', 'info');
      return;
    }
    setActionLoading('brain');
    try {
      const analyzed = await apiPost(`/requirement-libs/${selectedBackendLibId}/brain/analyze`, {});
      let latest = analyzed;
      try {
        latest = await apiGet(`/requirement-libs/${selectedBackendLibId}/brain`);
      } catch {
        latest = analyzed;
      }
      setBrainResult(latest);
      showToast('需求大脑分析已更新。');
    } catch (error) {
      showToast(error?.message || '需求大脑接口暂不可用。', 'error');
    } finally {
      setActionLoading('');
    }
  };

  const handleRefreshTraceability = async () => {
    if (!activeItem?.backendId) {
      showToast('当前为演示需求项，无法刷新追溯关系。', 'info');
      return;
    }
    setActionLoading('trace');
    try {
      const result = await apiPost(`/requirement-items/${activeItem.backendId}/traceability/refresh`, {});
      setTraceability(prev => ({ ...prev, [activeItemKey]: result }));
      showToast('追溯关系已刷新。');
    } catch (error) {
      showToast(error?.message || '追溯刷新失败。', 'error');
    } finally {
      setActionLoading('');
    }
  };

  const toggleSelectedItem = (item) => {
    const key = getItemKey(item);
    setSelectedItemKeys(prev => (prev.includes(key) ? prev.filter(value => value !== key) : [...prev, key]));
  };

  const renderVersionDiff = () => {
    const diffData = [
      { id: 'REQ-00001', title: '用户登录与认证', type: 'modified', detail: '输入参数新增 verification_code (验证码) 字段', impact: '影响 3 个登录用例' },
      { id: 'REQ-00004', title: '发送文本消息', type: 'modified', detail: '新增敏感词自动阻断拦截规则', impact: '影响 2 个发送消息用例' },
      { id: 'REQ-00018', title: '传统人工转接控制', type: 'deleted', detail: '旧版本的纯人工轮询转接流程已废弃', impact: '波及 4 个关联用例 (建议删除)' },
      { id: 'REQ-00045', title: '智能工单自动分配', type: 'added', detail: '根据用户画像及标签自动分发工单的新算法逻辑', impact: '需补齐 6 个测试用例' },
      { id: 'REQ-00046', title: '消息撤回防泄漏机制', type: 'added', detail: '撤回超出 2 分钟的消息进行二次指纹校验防泄漏', impact: '需补齐 3 个测试用例' },
      { id: 'REQ-00003', title: '会话列表展示', type: 'unchanged', detail: '未发生改动', impact: '无需更新' }
    ];

    return (
      <div className="space-y-4">
        {/* 面包屑 */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <button 
              onClick={() => setViewMode('workbench')}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[var(--bg-card)] border border-[var(--border-color)] text-[10px] text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 transition-colors shadow-sm cursor-pointer"
            >
              <ArrowLeft className="size-3" />
              <span>返回工作台</span>
            </button>
            <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-secondary)] font-semibold">
              <span>需求库</span>
              <span>/</span>
              <span>智能客服系统</span>
              <span>/</span>
              <span className="text-[var(--text-primary)]">历史版本对比</span>
            </div>
          </div>
          <button 
            onClick={() => window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '已同步最新测试影响评估报告！', type: 'success' } }))}
            className="px-3 py-1.5 text-[11px] accent-btn"
          >
            同步用例集
          </button>
        </div>

        {/* 顶部对比控制 */}
        <div className="theme-card rounded-xl p-4 shadow-soft flex items-center justify-between">
          <div className="flex items-center gap-4 text-xs font-bold text-[var(--text-primary)]">
            <div className="flex items-center gap-2">
              <span className="opacity-60 text-[var(--text-secondary)]">当前版本:</span>
              <div className="px-3 py-1.5 rounded border border-[var(--border-color)] bg-[var(--border-color)]/20 font-mono text-[11px]">
                v2.1 (2025-05-20)
              </div>
            </div>
            <span className="text-[var(--text-secondary)] opacity-50">VS</span>
            <div className="flex items-center gap-2">
              <span className="opacity-60 text-[var(--text-secondary)]">历史版本:</span>
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-[var(--border-color)] bg-[var(--border-color)]/20 font-mono text-[11px] cursor-pointer">
                <span>v2.0 (2025-05-10)</span>
                <ChevronDown className="size-3.5" />
              </div>
            </div>
          </div>

          <div className="flex gap-4 text-[10px] font-bold text-[var(--text-secondary)]">
            <div className="flex items-center gap-1.5"><span className="size-2 rounded bg-emerald-500"></span> 新增 2 项</div>
            <div className="flex items-center gap-1.5"><span className="size-2 rounded bg-amber-500"></span> 修改 2 项</div>
            <div className="flex items-center gap-1.5"><span className="size-2 rounded bg-red-500"></span> 删除 1 项</div>
          </div>
        </div>

        {/* 核心比对区域 */}
        <div className="grid grid-cols-12 gap-4">
          {/* 左侧：版本对比树 */}
          <div className="col-span-8 theme-card rounded-xl p-4 shadow-soft">
            <h3 className="text-xs font-bold mb-3 border-b border-[var(--border-color)] pb-2 flex items-center gap-1.5 text-[var(--text-primary)]">
              <span>变更需求树对比明细</span>
              <span className="text-[9px] font-normal text-[var(--text-secondary)]">对比结果由 AI 自动标定</span>
            </h3>

            <div className="space-y-2 max-h-[480px] overflow-y-auto pr-1">
              {diffData.map((item, idx) => {
                let statusClasses = "border-[var(--border-color)] bg-[var(--bg-card)]";
                let badge = null;
                
                if (item.type === 'added') {
                  statusClasses = "border-emerald-500/20 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400";
                  badge = <span className="px-1.5 py-0.5 rounded bg-emerald-500 text-white text-[8px] font-bold shrink-0">+ 新增</span>;
                } else if (item.type === 'deleted') {
                  statusClasses = "border-red-500/20 bg-red-500/5 text-red-500 line-through";
                  badge = <span className="px-1.5 py-0.5 rounded bg-red-500 text-white text-[8px] font-bold shrink-0">- 删除</span>;
                } else if (item.type === 'modified') {
                  statusClasses = "border-amber-500/20 bg-amber-500/5 text-amber-600 dark:text-amber-400";
                  badge = <span className="px-1.5 py-0.5 rounded bg-amber-500 text-white text-[8px] font-bold shrink-0">* 修改</span>;
                } else {
                  statusClasses = "border-[var(--border-color)] bg-[var(--bg-card)] text-[var(--text-primary)]";
                }

                return (
                  <div key={idx} className={`p-3 border rounded-xl flex items-start justify-between gap-4 transition-all ${statusClasses}`}>
                    <div className="flex gap-2.5 items-start min-w-0 text-left">
                      <span className="font-mono font-bold opacity-60 mt-0.5 text-[var(--text-secondary)]">{item.id}</span>
                      <div className="min-w-0">
                        <div className="font-bold text-[11px] flex items-center gap-2">
                          <span className="truncate">{item.title}</span>
                          {badge}
                        </div>
                        <div className="text-[9.5px] opacity-75 mt-1">{item.detail}</div>
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <span className="text-[9px] font-bold opacity-60 bg-black/5 dark:bg-white/10 px-2 py-1 rounded-md text-[var(--text-primary)]">{item.impact}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 右侧：AI 影响 analysis 看板 */}
          <div className="col-span-4 space-y-4">
            <TiltCard className="p-4 shadow-soft animate-[slideUpFade_0.4s_ease-out]">
              <h3 style={{ transform: 'translateZ(15px)' }} className="text-xs font-bold border-b border-[var(--border-color)] pb-2 mb-3 text-[var(--text-primary)]">AI 变更波及测试评估</h3>
              
              <div className="space-y-3 text-left text-[10px]" style={{ transformStyle: 'preserve-3d', transform: 'translateZ(20px)' }}>
                <div className="p-3 bg-red-500/5 border border-red-500/10 rounded-xl space-y-1 transition-transform duration-200" style={{ transform: 'translateZ(25px)' }}>
                  <div className="font-bold text-red-500">高风险影响项 (3)</div>
                  <p className="text-[var(--text-secondary)] text-[9px] leading-relaxed">
                    用户登录认证逻辑字段变更，直接导致关联的 3 个核心 P0 登录用例失效，需重新配置参数映射。
                  </p>
                </div>

                <div className="p-3 bg-amber-500/5 border border-amber-500/10 rounded-xl space-y-1 transition-transform duration-200" style={{ transform: 'translateZ(25px)' }}>
                  <div className="font-bold text-amber-500">用例建议自愈</div>
                  <p className="text-[var(--text-secondary)] text-[9px] leading-relaxed">
                    检测到 2 个发送文本消息的用例与改动相似度极高，建议启动“用例智能自愈”。
                  </p>
                </div>

                <div className="p-3 bg-emerald-500/5 border border-emerald-500/10 rounded-xl space-y-1 transition-transform duration-200" style={{ transform: 'translateZ(25px)' }}>
                  <div className="font-bold text-emerald-500">需补齐用例估算 (9)</div>
                  <p className="text-[var(--text-secondary)] text-[9px] leading-relaxed">
                    针对新增的“工单分配”和“防泄漏撤回”，AI 已提取了 9 个测试因子。
                  </p>
                </div>
              </div>

              <div className="border-t border-[var(--border-color)] pt-3 mt-4 space-y-2" style={{ transformStyle: 'preserve-3d', transform: 'translateZ(15px)' }}>
                <button 
                  onClick={() => window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: 'AI 自动用例自愈已在后台启动！', type: 'info' } }))}
                  style={{ transform: 'translateZ(25px)' }}
                  className="w-full py-2 border border-blue-500/25 bg-blue-500/10 hover:bg-blue-500/20 text-blue-500 rounded-lg font-bold text-center cursor-pointer transition-colors"
                >
                  一键自愈受影响用例
                </button>
                <button 
                  onClick={() => {
                    window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '成功为 v2.1 补充生成 9 个差异用例！', type: 'success' } }));
                  }}
                  style={{ transform: 'translateZ(25px)' }}
                  className="w-full py-2 accent-btn rounded-lg font-bold text-center cursor-pointer text-white"
                >
                  AI 补齐 9 个差异用例
                </button>
              </div>
            </TiltCard>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4 text-left w-full animate-[fadeIn_0.2s_ease-out]">
      
      {viewMode === 'list' ? (
        // ==========================================================================
        // 渲染：需求库列表页 (11-页)
        // ==========================================================================
        <div className="space-y-4">
          {/* 标题栏 */}
          <div className="flex justify-between items-start">
            <div className="text-left">
              <h1 className="text-base font-bold text-[var(--text-primary)]">需求库</h1>
              <p className="text-[11px] text-[var(--text-secondary)] mt-1">集中管理各项目的需求文档与需求项，支持解析、确认与追踪。</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleCreateRequirementDocument}
                disabled={isCreatingDocument || !selectedBackendLibId}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[11px] font-bold text-[var(--text-primary)] shadow-sm cursor-pointer"
              >
                <RotateCw className="size-3.5" />
                <span>{isCreatingDocument ? '导入中...' : '导入需求文档'}</span>
              </button>
              <button 
                onClick={handleCreateRequirementLib}
                disabled={isCreatingLib}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg accent-btn text-[11px] font-bold text-white shadow-sm cursor-pointer"
              >
                <Plus className="size-3.5" />
                <span>{isCreatingLib ? '创建中...' : '新建需求库'}</span>
              </button>
            </div>
          </div>

          {/* 指标卡片 */}
          <div className="grid grid-cols-4 gap-3.5">
            {listStats.map((item, idx) => (
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
                  <div className="text-[9px] text-[var(--text-secondary)] mt-1">较昨日 <span className={item.change.includes('↑') ? 'text-emerald-500' : 'text-red-500'}>{item.change}</span></div>
                </div>
                {item.hasChart ? (
                  <div className="size-11 shrink-0 relative">
                    <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                      <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--border-color)" strokeWidth="2.8" />
                      <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--accent-color)" strokeWidth="2.8" strokeDasharray="78.4 21.6" />
                    </svg>
                    <div className="absolute inset-0 flex items-center justify-center text-[8px] font-bold text-[var(--text-primary)]">
                      <AnimatedNumber value={78} />%
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

          {/* 7:5 选中联动分栏布局 */}
          <div className="grid grid-cols-12 gap-5 w-full">
            
            {/* 左侧 7 份：需求库表格区 */}
            <div className="col-span-7 min-w-0 theme-card rounded-xl p-4 shadow-soft">
              
              {/* 表单过滤器 */}
              <div className="flex items-center gap-2 mb-3.5">
                <div className="flex items-center gap-1 text-[10px] text-[var(--text-secondary)] border border-[var(--border-color)] rounded px-2 py-1.5 bg-[var(--border-color)]/30 hover:bg-[var(--border-color)]/60 cursor-pointer">
                  <span>{requirementsStatus.message || '全部项目'}</span>
                  <ChevronDown className="size-3 text-slate-400" />
                </div>

                <div className="flex-1 flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--border-color)]/30">
                  <Search className="size-3.5 text-[var(--text-secondary)] shrink-0" />
                  <input 
                    type="text" 
                    placeholder="搜索需求库名称、描述" 
                    className="bg-transparent border-none text-[11px] focus:outline-none w-full text-[var(--text-primary)]"
                  />
                </div>

                {['领域', '状态'].map((f, i) => (
                  <div key={i} className="flex items-center gap-1 text-[10px] text-[var(--text-secondary)] border border-[var(--border-color)] rounded px-2 py-1.5 bg-[var(--border-color)]/30 hover:bg-[var(--border-color)]/60 cursor-pointer font-bold">
                    <span>{f}</span>
                    <ChevronDown className="size-3 text-slate-400" />
                  </div>
                ))}
              </div>

              {/* 数据表 */}
              <div className="overflow-x-auto w-full">
                <table className="w-full text-[11px] text-left border-collapse">
                  <thead>
                    <tr className="text-[var(--text-secondary)] font-bold border-b border-[var(--border-color)]">
                      <th className="py-2.5 px-2 w-[30px]"><input type="checkbox" className="rounded" /></th>
                      <th className="py-2.5 px-2">需求库名称</th>
                      <th className="py-2.5 px-2">业务领域</th>
                      <th className="py-2.5 px-2 text-center">项数</th>
                      <th className="py-2.5 px-2">用例覆盖率</th>
                      <th className="py-2.5 px-2 text-center">状态</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border-color)] text-[var(--text-secondary)] font-medium">
                    {requirementsLibs.map((lib, idx) => {
                      const isSelected = selectedLibIndex === idx;
                      return (
                        <tr 
                          key={idx} 
                          onClick={() => setSelectedLibIndex(idx)}
                          className={`cursor-pointer transition-colors duration-150 ${
                            isSelected 
                              ? 'bg-[var(--accent-glow)] border-l-2 border-l-[var(--accent-color)] font-semibold' 
                              : 'hover:bg-[var(--border-color)]/30'
                          }`}
                        >
                          <td className="py-3 px-2" onClick={(e) => e.stopPropagation()}><input type="checkbox" className="rounded" /></td>
                          <td className="py-3 px-2">
                            <div className="flex items-center gap-2">
                              <Folder className="size-3.5 text-blue-500 shrink-0" />
                              <div className="flex flex-col text-left">
                                <span className="font-bold text-[var(--text-primary)]">{lib.name}</span>
                                <span className="text-[9px] text-[var(--text-secondary)] mt-0.5">{lib.desc}</span>
                              </div>
                            </div>
                          </td>
                          <td className="py-3 px-2">
                            <span className="px-2 py-0.5 bg-[var(--border-color)]/50 rounded text-[10px] text-[var(--text-primary)]">
                              {lib.domain}
                            </span>
                          </td>
                          <td className="py-3 px-2 text-center font-bold text-[var(--text-primary)]">{lib.items}</td>
                          <td className="py-3 px-2">
                            <div className="flex items-center gap-2 min-w-[70px]">
                              <div className="flex-1 h-1 bg-[var(--border-color)] rounded-full overflow-hidden">
                                <div className="h-full bg-emerald-500" style={{ width: lib.rate }}></div>
                              </div>
                              <span className="text-[9.5px] font-bold text-[var(--text-primary)] shrink-0">{lib.rate}</span>
                            </div>
                          </td>
                          <td className="py-3 px-2 text-center">
                            <div className="flex items-center justify-center gap-1 text-[10px]">
                              <span className={`size-1.5 rounded-full shrink-0 ${lib.statusColor}`}></span>
                              <span>{lib.status}</span>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="flex justify-between items-center mt-4 border-t border-[var(--border-color)] pt-3">
                <span className="text-[10px] text-[var(--text-secondary)] font-semibold">共 24 条</span>
                <div className="flex items-center gap-2 text-[10px] text-[var(--text-secondary)]">
                  <button className="px-2 py-0.5 border border-[var(--border-color)] rounded bg-[var(--bg-card)]">‹</button>
                  <button className="px-2.5 py-0.5 bg-[var(--accent-color)] text-white rounded">1</button>
                  <button className="px-2.5 py-0.5 border border-[var(--border-color)] rounded bg-[var(--bg-card)]">2</button>
                  <button className="px-2.5 py-0.5 border border-[var(--border-color)] rounded bg-[var(--bg-card)]">3</button>
                  <button className="px-2 py-0.5 border border-[var(--border-color)] rounded bg-[var(--bg-card)]">›</button>
                </div>
              </div>

            </div>

            {/* 右侧 5 份：需求解析遥测大卡片 */}
            <div className="col-span-5 min-w-0 space-y-4">
              
              {/* 遥测总面板 */}
              <div className="theme-card rounded-xl p-4 shadow-soft text-left flex flex-col justify-between h-full min-h-[440px]">
                <div className="space-y-4">
                  <div className="flex justify-between items-center border-b border-[var(--border-color)] pb-2.5">
                    <div className="flex items-center gap-1.5">
                      <Sparkles className="size-4 text-purple-600 animate-pulse" />
                      <span className="text-xs font-bold text-[var(--text-primary)]">解析遥测与覆盖雷达</span>
                    </div>
                    <span className="text-[8.5px] font-mono text-[var(--accent-color)] bg-[var(--accent-glow)] px-1.5 py-0.5 rounded">
                      {requirementsLibs[selectedLibIndex]?.status || '待解析'}
                    </span>
                  </div>

                  <div>
                    <div className="text-[9px] text-[var(--text-secondary)] font-bold mb-1">当前需求库:</div>
                    <div className="text-[10px] font-extrabold text-[var(--text-primary)] truncate">
                      {requirementsLibs[selectedLibIndex]?.name}
                    </div>
                  </div>

                  {/* 需求库健康度条 */}
                  <div className="space-y-2 border border-[var(--border-color)] bg-[var(--bg-app)]/30 rounded-xl p-3">
                    <span className="text-[9px] text-[var(--text-secondary)] font-bold block mb-1">关联用例覆盖质量评估</span>
                    <div className="space-y-2 text-[9px] font-bold text-[var(--text-secondary)]">
                      <div className="space-y-1">
                        <div className="flex justify-between text-[var(--text-primary)]">
                          <span>核心验收指标 (P0)</span>
                          <span>{selectedLibIndex === 2 ? '54%' : '88%'}</span>
                        </div>
                        <div className="h-1 bg-[var(--border-color)] rounded-full overflow-hidden">
                          <div className="h-full bg-emerald-500" style={{ width: selectedLibIndex === 2 ? '54%' : '88%' }}></div>
                        </div>
                      </div>
                      <div className="space-y-1">
                        <div className="flex justify-between text-[var(--text-primary)]">
                          <span>异常边界校验 (P1)</span>
                          <span>{selectedLibIndex === 2 ? '42%' : '76%'}</span>
                        </div>
                        <div className="h-1 bg-[var(--border-color)] rounded-full overflow-hidden">
                          <div className="h-full bg-blue-500" style={{ width: selectedLibIndex === 2 ? '42%' : '76%' }}></div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* 最近导入解析的文档队列 */}
                  <div className="space-y-2">
                    <span className="text-[9px] text-[var(--text-secondary)] font-bold block">最近解析之源文档 ({requirementsLibs[selectedLibIndex]?.docs || 0} 个)</span>
                    <div className="space-y-2">
                      {(libDocs[selectedLibIndex] || libDocs[0]).map((doc, idx) => (
                        <div key={idx} className="p-2.5 border border-[var(--border-color)] bg-[var(--bg-card)] rounded-xl flex items-center justify-between text-[9.5px]">
                          <div className="flex items-center gap-2 min-w-0">
                            <FileText className={`size-4 shrink-0 ${doc.color}`} />
                            <div className="text-left min-w-0">
                              <div className="font-bold text-[var(--text-primary)] truncate">{doc.name}</div>
                              <div className="text-[7.5px] text-[var(--text-secondary)] mt-0.5">大小: {doc.size} | 确认人: {doc.user}</div>
                            </div>
                          </div>
                          <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-500 text-[8px] font-bold shrink-0">{doc.status}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-[var(--border-color)] space-y-2">
                  <button 
                    onClick={() => setViewMode('workbench')}
                    className="w-full py-1.5 bg-[var(--accent-color)] hover:opacity-95 text-white text-[9.5px] font-bold rounded-lg cursor-pointer text-center transition-opacity"
                  >
                    进入此需求库分析工作台
                  </button>
                </div>
              </div>

            </div>

          </div>
        </div>
      ) : viewMode === 'version-diff' ? (
        renderVersionDiff()
      ) : (
        // ==========================================================================
        // 渲染：需求库详情分析工作台 (12-页)
        // ==========================================================================
        <div className="space-y-4 animate-[fadeIn_0.2s_ease-out]">
          {/* 返回与面包屑 */}
          <div className="flex justify-between items-center bg-[var(--bg-card)] border border-[var(--border-color)] rounded-xl p-3.5 shadow-sm">
            <div className="flex items-center gap-3">
              <button 
                onClick={() => setViewMode('list')}
                className="flex items-center gap-1 px-2.5 py-1 rounded bg-[var(--bg-card)] border border-[var(--border-color)] text-[10px] text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 transition-colors shadow-sm cursor-pointer"
              >
                <ArrowLeft className="size-3" />
                <span>返回需求库</span>
              </button>
              <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-secondary)] font-semibold">
                <span>需求库</span>
                <span>/</span>
                <span className="text-[var(--text-primary)]">需求库工作台</span>
              </div>
            </div>
            
            <div className="flex items-center gap-2">
              <button 
                onClick={() => setViewMode('version-diff')}
                className="px-3 py-1.5 rounded-lg border border-[var(--accent-color)]/30 bg-[var(--accent-glow)] text-[var(--accent-color)] hover:opacity-90 text-[11px] font-bold cursor-pointer transition-all"
              >
                版本对比
              </button>
              <button 
                onClick={handleCreateRequirementDocument}
                disabled={isCreatingDocument || !selectedBackendLibId}
                className="px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[11px] font-bold text-[var(--text-primary)] cursor-pointer"
              >
                {isCreatingDocument ? '解析中...' : '导入并解析'}
              </button>
              <button 
                onClick={handleBrainAnalyze}
                disabled={actionLoading === 'brain' || !selectedBackendLibId}
                className="px-3 py-1.5 rounded-lg border border-purple-500/25 bg-purple-500/10 hover:bg-purple-500/15 text-[11px] font-bold text-purple-600 dark:text-purple-300 cursor-pointer"
              >
                {actionLoading === 'brain' ? '分析中...' : '需求大脑'}
              </button>
              <button
                onClick={handleExportRequirementReport}
                className="px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[11px] font-bold text-[var(--text-primary)] cursor-pointer"
              >
                导出报告
              </button>
              <button 
                onClick={handleGenerateTestPoints}
                disabled={isGeneratingPoints}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg accent-btn text-[11px] font-bold text-white cursor-pointer"
              >
                <span>{isGeneratingPoints ? '生成中...' : '智能生成测试点'}</span>
              </button>
            </div>
          </div>

          {/* 顶栏项目信息 */}
          <div className="theme-card rounded-xl p-4 shadow-soft text-left flex justify-between items-center">
            <div>
              <div className="flex items-center gap-2.5">
                <h2 className="text-sm font-bold text-[var(--text-primary)]">{requirementsLibs[selectedLibIndex]?.name || '智能客服系统 V2.1'}</h2>
                <span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 rounded text-[9px] font-bold">● 已解析</span>
              </div>
              <div className="flex items-center gap-4 text-[9.5px] text-[var(--text-secondary)] font-semibold mt-2">
                <span>文档总数: {requirementsLibs[selectedLibIndex]?.docs || 8}</span>
                <span>分析项数: {requirementsLibs[selectedLibIndex]?.items || 186}</span>
                <span>更新时间: {requirementsLibs[selectedLibIndex]?.time}</span>
                <span>架构评估: 稳健</span>
              </div>
            </div>
          </div>

          {/* 四个版块 Grid */}
          <div className="grid grid-cols-12 gap-4">
            
            {/* 左侧：文档上传 + 需求项列表 */}
            <div className="col-span-4 min-w-0 space-y-4">
              
              {/* 1. 文档上传与解析 */}
              <div className="theme-card rounded-xl p-4 shadow-soft text-left">
                <h3 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 mb-3">1. 文档上传与解析</h3>
                
                {/* 虚线上传区 */}
                <div
                  onClick={handleCreateRequirementDocument}
                  className="border border-dashed border-[var(--border-color)] rounded-lg p-4 flex flex-col items-center justify-center bg-[var(--border-color)]/30 hover:bg-[var(--border-color)]/50 cursor-pointer transition-colors"
                >
                  <Upload className="size-6 text-[var(--accent-color)] mb-1.5" />
                  <span className="text-[10px] font-bold text-[var(--text-primary)]">{isCreatingDocument ? '正在导入并解析...' : '点击创建一份后端需求文档'}</span>
                  <span className="text-[8px] text-[var(--text-secondary)] mt-1">支持 Word、Excel、PDF 等格式，单个文件不超过 50MB</span>
                </div>

                <div className="mt-3.5 space-y-2">
                  <div className="flex justify-between items-center text-[9px] font-bold text-[var(--text-secondary)]">
                    <span>已解析文档 list ({docsList.length})</span>
                    <span className="text-emerald-500">解析正常</span>
                  </div>
                  <div className="space-y-2.5">
                    {docsList.map((doc, idx) => (
                      <div
                        key={doc.backendId || idx}
                        onClick={() => doc.backendId && setSelectedDocId(doc.backendId)}
                        className={`flex justify-between items-center text-[9.5px] border-b border-[var(--border-color)] pb-1.5 last:border-b-0 ${doc.backendId ? 'cursor-pointer' : ''} ${selectedDoc?.backendId === doc.backendId ? 'text-[var(--accent-color)]' : ''}`}
                      >
                        <div className="flex items-center gap-1.5 min-w-0">
                          <FileText className={`size-3.5 shrink-0 ${idx % 2 === 0 ? 'text-blue-500' : 'text-red-500'}`} />
                          <span className="font-bold text-[var(--text-primary)] truncate">{doc.name}</span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0 text-[var(--text-secondary)] font-mono">
                          <span>{doc.size}</span>
                          <span className="text-emerald-500 font-bold">{doc.status}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="mt-3 pt-3 border-t border-[var(--border-color)]">
                  <div className="flex justify-between items-center text-[9px] font-bold text-[var(--text-secondary)] mb-2">
                    <span>Source anchors / 解析块 ({parseBlocks.length})</span>
                    <span className="font-mono">{selectedDoc?.id || 'DOC'}</span>
                  </div>
                  <div className="space-y-1.5 max-h-[150px] overflow-y-auto pr-1">
                    {parseBlocks.length ? parseBlocks.map((block) => (
                      <div key={block.block_key} className="p-2 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)]/30 text-[8px]">
                        <div className="flex justify-between gap-2 font-bold text-[var(--text-primary)]">
                          <span className="truncate">{block.section_path}</span>
                          <span className="font-mono shrink-0">L{block.line_start || '-'}-{block.line_end || '-'}</span>
                        </div>
                        <div className="mt-1 text-[var(--text-secondary)] leading-snug line-clamp-2">
                          [{block.block_type}] {block.raw_text || block.block_key}
                        </div>
                      </div>
                    )) : (
                      <div className="p-2 rounded-lg border border-dashed border-[var(--border-color)] text-[8.5px] text-[var(--text-secondary)] bg-[var(--bg-app)]/20">
                        暂无解析块。接口未就绪或尚未执行文档解析时会保持空态。
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* 2. 需求项列表 */}
              <div className="theme-card rounded-xl p-4 shadow-soft text-left">
                <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-2 mb-3 gap-2">
                  <h3 className="text-xs font-bold text-[var(--text-primary)]">2. 需求项列表 ({workbenchItems.length})</h3>
                  <button
                    onClick={handleMergeSelectedItems}
                    disabled={actionLoading === 'merge' || selectedItemKeys.length < 2}
                    className="px-2 py-1 rounded border border-[var(--border-color)] bg-[var(--bg-card)] text-[8.5px] font-bold text-[var(--text-primary)] disabled:opacity-50 whitespace-nowrap"
                  >
                    {actionLoading === 'merge' ? '合并中' : `合并(${selectedItemKeys.length})`}
                  </button>
                </div>
                
                <div className="flex gap-1.5 mb-3">
                  <div className="flex-1 flex items-center gap-1.5 px-2 py-1 rounded border border-[var(--border-color)] bg-[var(--border-color)]/30">
                    <Search className="size-3 text-[var(--text-secondary)] shrink-0" />
                    <input type="text" placeholder="搜索需求项标题..." className="bg-transparent border-none text-[9px] focus:outline-none w-full text-[var(--text-primary)]" />
                  </div>
                </div>

                <div className="space-y-1.5 max-h-[220px] overflow-y-auto pr-1">
                  {workbenchItems.map((item) => (
                    <div 
                      key={item.id}
                      onClick={() => setActiveItem(item)}
                      className={`flex justify-between items-center p-2 rounded-lg border text-[9px] cursor-pointer transition-all ${
                        activeItem?.id === item.id 
                          ? 'border-[var(--accent-color)] bg-[var(--accent-glow)]' 
                          : 'border-[var(--border-color)] bg-[var(--bg-card)] hover:border-[var(--accent-color)]/50'
                      }`}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <input
                          type="checkbox"
                          checked={selectedItemKeys.includes(getItemKey(item))}
                          onChange={() => toggleSelectedItem(item)}
                          onClick={(event) => event.stopPropagation()}
                          className="rounded shrink-0"
                        />
                        <span className="font-bold text-[var(--text-secondary)] shrink-0 font-mono">{item.id}</span>
                        <span className="font-bold text-[var(--text-primary)] truncate">{item.title}</span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="px-1.5 py-0.5 bg-[var(--border-color)] text-[var(--text-secondary)] rounded text-[8px]">{item.module}</span>
                        <span className="text-red-500 font-bold font-mono">{item.priority}</span>
                        {item.granularityFlag && (
                          <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500 text-[8px] max-w-[72px] truncate">{toDisplayText(item.granularityFlag)}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

            </div>

            {/* 中间：3. 需求大脑 (关系图谱 + 摘要) */}
            <div className="col-span-5 min-w-0 space-y-4">
              
              {/* 需求关系图谱 */}
              <div className="theme-card rounded-xl p-4 shadow-soft text-left flex flex-col justify-between h-[360px]">
                <div>
                  <div className="flex justify-between items-center border-b border-[var(--border-color)] pb-2 mb-2">
                    <span className="text-xs font-bold text-[var(--text-primary)]">3. 需求大脑 <span className="text-[9px] text-[var(--text-secondary)] font-normal">(依赖网络) ⓘ</span></span>
                    <span className="text-[8px] font-mono text-[var(--text-secondary)] bg-[var(--border-color)] px-1.5 py-0.5 rounded">关系图谱</span>
                  </div>
                </div>

                {/* SVG 拓扑图 (去硬编码，完美适配 10 大主题自适应) */}
                <div className="flex-1 relative flex items-center justify-center py-2 bg-[var(--bg-app)]/30 rounded-xl overflow-hidden">
                  <svg className="w-full h-full" viewBox="0 0 400 240">
                    {/* 连接线 */}
                    <line x1="200" y1="120" x2="80" y2="70" stroke="var(--border-color)" strokeWidth="1.5" strokeDasharray="3,3" />
                    <line x1="200" y1="120" x2="80" y2="170" stroke="var(--border-color)" strokeWidth="1.5" strokeDasharray="3,3" />
                    
                    <line x1="200" y1="120" x2="90" y2="120" stroke="var(--text-secondary)" strokeWidth="1.5" />
                    <line x1="200" y1="120" x2="200" y2="50" stroke="var(--text-secondary)" strokeWidth="1.5" />
                    <line x1="200" y1="120" x2="310" y2="70" stroke="var(--text-secondary)" strokeWidth="1.5" />
                    
                    <line x1="200" y1="120" x2="200" y2="190" stroke="var(--border-color)" strokeWidth="1.2" />
                    <line x1="200" y1="120" x2="310" y2="170" stroke="var(--border-color)" strokeWidth="1.2" />

                    {/* 中心节点 */}
                    <g transform="translate(140, 100)" className="cursor-pointer hover:scale-105 transform origin-center transition-transform">
                      <rect width="120" height="40" rx="8" fill="var(--accent-color)" />
                      <text x="60" y="20" fill="var(--accent-text)" textAnchor="middle" alignmentBaseline="middle" className="text-[10px] font-bold">发送文本消息</text>
                      <text x="60" y="32" fill="var(--accent-text)" opacity="0.85" textAnchor="middle" alignmentBaseline="middle" className="text-[7.5px] font-mono">REQ-00004</text>
                    </g>

                    {/* 环绕节点 1 */}
                    <g transform="translate(20, 50)">
                      <rect width="100" height="35" rx="6" fill="var(--bg-card)" stroke="var(--border-color)" strokeWidth="1" />
                      <text x="50" y="16" fill="var(--text-primary)" textAnchor="middle" alignmentBaseline="middle" className="text-[9px] font-bold">会话状态管理</text>
                      <text x="50" y="27" fill="var(--text-secondary)" textAnchor="middle" alignmentBaseline="middle" className="text-[7px] font-mono">REQ-00028</text>
                    </g>
                    {/* 环绕节点 2 */}
                    <g transform="translate(20, 102)">
                      <rect width="100" height="35" rx="6" fill="var(--bg-card)" stroke="var(--border-color)" strokeWidth="1" />
                      <text x="50" y="16" fill="var(--text-primary)" textAnchor="middle" alignmentBaseline="middle" className="text-[9px] font-bold">用户登录与认证</text>
                      <text x="50" y="27" fill="var(--text-secondary)" textAnchor="middle" alignmentBaseline="middle" className="text-[7px] font-mono">REQ-00001</text>
                    </g>
                    {/* 环绕节点 3 */}
                    <g transform="translate(20, 155)">
                      <rect width="100" height="35" rx="6" fill="var(--bg-card)" stroke="var(--border-color)" strokeWidth="1" />
                      <text x="50" y="16" fill="var(--text-primary)" textAnchor="middle" alignmentBaseline="middle" className="text-[9px] font-bold">发送图片消息</text>
                      <text x="50" y="27" fill="var(--text-secondary)" textAnchor="middle" alignmentBaseline="middle" className="text-[7px] font-mono">REQ-00005</text>
                    </g>
                    {/* 环绕节点 4 */}
                    <g transform="translate(150, 15)">
                      <rect width="100" height="35" rx="6" fill="var(--bg-card)" stroke="var(--border-color)" strokeWidth="1" />
                      <text x="50" y="16" fill="var(--text-primary)" textAnchor="middle" alignmentBaseline="middle" className="text-[9px] font-bold">会话列表展示</text>
                      <text x="50" y="27" fill="var(--text-secondary)" textAnchor="middle" alignmentBaseline="middle" className="text-[7px] font-mono">REQ-00003</text>
                    </g>
                    {/* 环绕节点 5 */}
                    <g transform="translate(150, 192)">
                      <rect width="100" height="35" rx="6" fill="var(--bg-card)" stroke="var(--border-color)" strokeWidth="1" />
                      <text x="50" y="16" fill="var(--text-primary)" textAnchor="middle" alignmentBaseline="middle" className="text-[9px] font-bold">消息撤回与提示</text>
                      <text x="50" y="27" fill="var(--text-secondary)" textAnchor="middle" alignmentBaseline="middle" className="text-[7px] font-mono">REQ-00006</text>
                    </g>
                    {/* 环绕节点 6 */}
                    <g transform="translate(280, 50)">
                      <rect width="100" height="35" rx="6" fill="var(--bg-card)" stroke="var(--border-color)" strokeWidth="1" />
                      <text x="50" y="16" fill="var(--text-primary)" textAnchor="middle" alignmentBaseline="middle" className="text-[9px] font-bold">消息内容审核</text>
                      <text x="50" y="27" fill="var(--text-secondary)" textAnchor="middle" alignmentBaseline="middle" className="text-[7px] font-mono">REQ-00035</text>
                    </g>
                    {/* 环绕节点 7 */}
                    <g transform="translate(280, 155)">
                      <rect width="100" height="35" rx="6" fill="var(--bg-card)" stroke="var(--border-color)" strokeWidth="1" />
                      <text x="50" y="16" fill="var(--text-primary)" textAnchor="middle" alignmentBaseline="middle" className="text-[9px] font-bold">消息存储</text>
                      <text x="50" y="27" fill="var(--text-secondary)" textAnchor="middle" alignmentBaseline="middle" className="text-[7px] font-mono">REQ-00036</text>
                    </g>
                  </svg>
                </div>

                {/* 拓扑图例 */}
                <div className="flex gap-3 text-[7.5px] font-bold opacity-60 border-t border-[var(--border-color)] pt-2.5 justify-center text-[var(--text-secondary)]">
                  <div className="flex items-center gap-1"><span className="size-1.5 rounded-full bg-blue-500"></span>前置</div>
                  <div className="flex items-center gap-1"><span className="size-1.5 rounded-full bg-purple-500"></span>同级</div>
                  <div className="flex items-center gap-1"><span className="size-1.5 rounded-full bg-amber-500"></span>后置</div>
                  <div className="flex items-center gap-1">─── 依赖关系</div>
                </div>
              </div>

              {/* 需求摘要 */}
              <div className="theme-card rounded-xl p-4 shadow-soft text-left space-y-2.5">
                <h3 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 flex items-center gap-1">
                  <Sparkles className="size-3.5 text-purple-600 animate-pulse" />
                  <span>核心业务摘要 / 风险追溯</span>
                </h3>
                <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed font-semibold">
                  {toDisplayText(firstDefined(brainResult?.summary, brainResult?.analysis_summary, brainResult?.analysisSummary), '该需求描述了客服在会话中发送文本消息的能力，包括输入、发送、存储与展示的完整流程。需保证内容合规，支持表情与特殊字符，消息成功后台实时展示给用户，并记录到会话历史。')}
                </p>
                <div className="text-[9px] space-y-1.5 font-bold text-[var(--text-secondary)]">
                  {brainRisks.slice(0, 3).map((risk, idx) => (
                    <div key={idx}>• 风险: {toDisplayText(risk?.title || risk?.summary || risk?.message || risk?.value || risk, '--')}</div>
                  ))}
                  {!brainRisks.length && (
                    <>
                      <div>• 关键字段: <span className="font-mono">message_id, session_id, content, msg_type</span></div>
                      <div>• 覆盖场景: 正向输入、拦截过滤、高并发重发、延迟校验</div>
                    </>
                  )}
                  {brainSourceRefs.slice(0, 3).map((ref, idx) => (
                    <div key={`ref-${idx}`} className="font-mono text-[8px]">source: {toDisplayText(ref?.block_key || ref?.section_path || ref?.id || ref?.value || ref, '--')}</div>
                  ))}
                </div>
              </div>

            </div>

            {/* 右侧：4. 需求项详情 */}
            <div className="col-span-3 min-w-0 theme-card rounded-xl p-4 shadow-soft text-left flex flex-col justify-between h-full min-h-[460px]">
              
              <div>
                <div className="flex justify-between items-start">
                  <span className="text-[10px] font-bold text-[var(--text-secondary)]">4. 需求项详情</span>
                  <span className="text-[8.5px] font-mono text-[var(--text-secondary)]">{activeItem.id}</span>
                </div>

                <div className="mt-3.5 space-y-2">
                  <input
                    value={editDraft?.title || ''}
                    onChange={(event) => setEditDraft(prev => ({ ...(prev || {}), title: event.target.value }))}
                    className="w-full rounded border border-[var(--border-color)] bg-[var(--bg-app)]/40 px-2 py-1.5 text-xs font-bold text-[var(--text-primary)] focus:outline-none"
                  />
                  <textarea
                    value={editDraft?.summary || ''}
                    onChange={(event) => setEditDraft(prev => ({ ...(prev || {}), summary: event.target.value }))}
                    rows={3}
                    placeholder="需求摘要"
                    className="w-full resize-none rounded border border-[var(--border-color)] bg-[var(--bg-app)]/40 px-2 py-1.5 text-[9px] text-[var(--text-primary)] focus:outline-none"
                  />
                  <div className="grid grid-cols-2 gap-1.5 text-[9px] text-[var(--text-secondary)] font-semibold">
                    <input value={editDraft?.module || ''} onChange={(event) => setEditDraft(prev => ({ ...(prev || {}), module: event.target.value }))} placeholder="模块" className="rounded border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1 text-[var(--text-primary)] focus:outline-none" />
                    <input value={editDraft?.priority || ''} onChange={(event) => setEditDraft(prev => ({ ...(prev || {}), priority: event.target.value }))} placeholder="优先级" className="rounded border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1 text-red-500 font-mono focus:outline-none" />
                    <input value={editDraft?.actor || ''} onChange={(event) => setEditDraft(prev => ({ ...(prev || {}), actor: event.target.value }))} placeholder="参与者" className="rounded border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1 text-[var(--text-primary)] focus:outline-none" />
                    <input value={editDraft?.goal || ''} onChange={(event) => setEditDraft(prev => ({ ...(prev || {}), goal: event.target.value }))} placeholder="目标" className="rounded border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1 text-[var(--text-primary)] focus:outline-none" />
                    <input value={editDraft?.status || ''} onChange={(event) => setEditDraft(prev => ({ ...(prev || {}), status: event.target.value }))} placeholder="status" className="rounded border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1 text-[var(--text-primary)] focus:outline-none" />
                    <div className="rounded border border-[var(--border-color)] bg-[var(--bg-card)] px-2 py-1 text-[var(--text-primary)] truncate">粒度: {toDisplayText(activeItem.granularityFlag, '未质检')}</div>
                  </div>
                </div>

                {/* 标签页切换 */}
                <div className="flex border-b border-[var(--border-color)] mt-4 text-[8.5px] font-bold text-[var(--text-secondary)]">
                  {[
                    { id: 'testpoints', label: '测试点' },
                    { id: 'questions', label: '待 clarified 问题 (2)' },
                    { id: 'scope', label: '覆盖范围' },
                    { id: 'quality', label: '质检' }
                  ].map((tab) => (
                    <button
                      key={tab.id}
                      onClick={() => setWorkbenchTab(tab.id)}
                      className={`flex-1 pb-1.5 border-b-2 text-center transition-all ${
                        workbenchTab === tab.id 
                          ? 'border-[var(--accent-color)] text-[var(--accent-color)]' 
                          : 'border-transparent hover:text-[var(--text-primary)]'
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>

                {/* 标签页内容 */}
                <div className="mt-3 text-[9px] leading-relaxed text-[var(--text-secondary)] font-semibold space-y-2.5">
                  {workbenchTab === 'testpoints' && (
                    <div className="space-y-3">
                      <div>
                        <div className="text-[var(--text-primary)] font-bold">需求描述</div>
                        <p className="text-[var(--text-secondary)] text-[8px] mt-0.5 leading-normal">{activeItem.summary || '客服在会话中输入文本内容并发送，系统将消息推送给用户并在会话窗口展示，同时记录到会话历史中。'}</p>
                      </div>
                      
                      <div className="space-y-1">
                        <div className="text-[var(--text-primary)] font-bold mb-1">系统级验收标准</div>
                        {[
                          '文本内容不超过 2000 字符，支持多语言标点和表情符',
                          '消息发送写入会话历史，包含精确发送毫秒数与唯一 ID',
                          '内容必须通过智能合规与安全防注入校验'
                        ].map((std, idx) => (
                          <div key={idx} className="flex gap-1.5 items-start text-[8.5px]">
                            <span className="text-emerald-500">✓</span>
                            <span className="text-[var(--text-secondary)] font-semibold leading-tight">{std}</span>
                          </div>
                        ))}
                      </div>
                      <div className="space-y-1">
                        <div className="flex items-center justify-between">
                          <div className="text-[var(--text-primary)] font-bold">来源锚点</div>
                          <button onClick={handleRefreshTraceability} disabled={actionLoading === 'trace'} className="text-[8px] px-1.5 py-0.5 rounded bg-[var(--border-color)] text-[var(--text-primary)]">
                            {actionLoading === 'trace' ? '刷新中' : '刷新追溯'}
                          </button>
                        </div>
                        {(activeAnchors.length ? activeAnchors : activeSourceBlocks).slice(0, 3).map((block, idx) => {
                          const normalized = normalizeBlock(block, idx);
                          return (
                            <div key={normalized.block_key || idx} className="p-2 rounded border border-[var(--border-color)] bg-[var(--bg-app)]/30 text-[8px]">
                              <div className="flex justify-between gap-2 font-bold text-[var(--text-primary)]">
                                <span className="truncate">{normalized.section_path}</span>
                                <span className="font-mono shrink-0">L{normalized.line_start || '-'}-{normalized.line_end || '-'}</span>
                              </div>
                              <div className="text-[var(--text-secondary)] leading-snug line-clamp-2">{normalized.raw_text || normalized.block_key}</div>
                            </div>
                          );
                        })}
                        {!activeAnchors.length && !activeSourceBlocks.length && (
                          <div className="p-2 rounded border border-dashed border-[var(--border-color)] text-[8px] text-[var(--text-secondary)]">暂无可映射 source_anchor_ids，解析或追溯接口返回后会在这里展示。</div>
                        )}
                      </div>
                    </div>
                  )}

                  {workbenchTab === 'questions' && (
                    <div className="space-y-2">
                      <div className="p-2 border border-[var(--border-color)] bg-[var(--bg-app)]/30 rounded-lg">
                        <div className="flex justify-between font-bold text-[var(--text-primary)]">
                          <span>1. 敏感词屏蔽后反馈</span>
                          <span className="text-red-500 font-mono text-[8px]">高</span>
                        </div>
                        <p className="text-[var(--text-secondary)] text-[8px] mt-0.5 leading-normal">当包含违规内容时，是直接禁止发送并提示红色报错，还是发送后仅展示星号屏蔽？（建议：弹窗红色错误并扣发）</p>
                      </div>
                      <div className="p-2 border border-[var(--border-color)] bg-[var(--bg-app)]/30 rounded-lg">
                        <div className="flex justify-between font-bold text-[var(--text-primary)]">
                          <span>2. 超时重传策略</span>
                          <span className="text-amber-500 font-mono text-[8px]">中</span>
                        </div>
                        <p className="text-[var(--text-secondary)] text-[8px] mt-0.5 leading-normal">消息推送失败时，重试机制由前端还是网关驱动？超时时间是否固定为 10 秒？</p>
                      </div>
                    </div>
                  )}

                  {workbenchTab === 'scope' && (
                    <div className="space-y-2">
                      <div className="p-2 border border-emerald-500/20 bg-emerald-500/5 rounded-lg text-emerald-600 dark:text-emerald-400">
                        <div className="font-bold">测试优先级: P0 (核心主流程)</div>
                        <p className="text-[8px] leading-relaxed mt-0.5">该需求为会话系统的最核心主干。任何故障将直接导致功能瘫痪，需在各轮次优先执行。</p>
                      </div>
                      <div className="p-2 border border-[var(--border-color)] bg-[var(--bg-app)]/30 rounded-lg">
                        <div className="font-bold text-[var(--text-primary)]">测试用例建议</div>
                        <p className="text-[8px] leading-relaxed mt-0.5">正向用例：4个 | 反向异常：6个 | 极限边界：3个</p>
                      </div>
                      {activeTraceability && (
                        <div className="p-2 border border-[var(--border-color)] bg-[var(--bg-app)]/30 rounded-lg">
                          <div className="font-bold text-[var(--text-primary)]">追溯覆盖</div>
                          <p className="text-[8px] leading-relaxed mt-0.5">
                            source blocks: {activeSourceBlocks.length} | test points: {activeTestPoints.length} | test cases: {activeTestCases.length} | coverage: {toDisplayText(activeTraceability.coverage, '--')}
                          </p>
                        </div>
                      )}
                    </div>
                  )}

                  {workbenchTab === 'quality' && (
                    <div className="space-y-2">
                      <button
                        onClick={handleQualityCheckActiveItem}
                        disabled={actionLoading === 'quality'}
                        className="w-full py-1.5 rounded bg-[var(--accent-color)] text-white text-[9px] font-bold"
                      >
                        {actionLoading === 'quality' ? '质检中...' : '运行粒度质检'}
                      </button>
                      <div className="p-2 border border-[var(--border-color)] bg-[var(--bg-app)]/30 rounded-lg">
                        <div className="flex justify-between font-bold text-[var(--text-primary)]">
                          <span>Score</span>
                          <span className="font-mono">{toDisplayText(activeQuality?.score, '--')}</span>
                        </div>
                        <div className="mt-1 text-[8px]">粒度标记: {toDisplayText(firstDefined(activeQuality?.granularity_flag, activeQuality?.granularityFlag, activeItem.granularityFlag), '未质检')}</div>
                      </div>
                      {activeQualityIssues.slice(0, 4).map((issue, idx) => (
                        <div key={idx} className="p-2 border border-amber-500/20 bg-amber-500/5 rounded-lg text-[8px]">
                          {toDisplayText(issue?.message || issue?.title || issue?.value || issue, '--')}
                        </div>
                      ))}
                      {activeQualityActions.slice(0, 4).map((action, idx) => (
                        <div key={`action-${idx}`} className="p-2 border border-emerald-500/20 bg-emerald-500/5 rounded-lg text-[8px] text-emerald-600 dark:text-emerald-400">
                          {toDisplayText(action?.message || action?.title || action?.value || action, '--')}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* 底部确认操作 */}
              <div className="border-t border-[var(--border-color)] pt-3.5 space-y-2 mt-4">
                <button
                  onClick={handleSaveActiveItem}
                  disabled={actionLoading === 'save'}
                  className="w-full py-2 border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[var(--text-primary)] text-[10px] font-bold rounded-lg cursor-pointer text-center transition-colors"
                >
                  {actionLoading === 'save' ? '保存中...' : '保存需求项编辑'}
                </button>
                <button 
                  onClick={handleConfirmActiveItem}
                  disabled={actionLoading === 'confirm'}
                  className="w-full py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-[10px] font-bold rounded-lg cursor-pointer text-center transition-colors"
                >
                  {actionLoading === 'confirm' ? '确认中...' : '确认解析此需求项'}
                </button>
                <div className="flex gap-2">
                  <button 
                    onClick={handleShelveActiveItem}
                    disabled={actionLoading === 'shelve'}
                    className="flex-1 py-1.5 border border-[var(--border-color)] bg-[var(--bg-card)] text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 text-[9px] font-bold rounded-lg cursor-pointer text-center"
                  >
                    {actionLoading === 'shelve' ? '搁置中' : '暂不入库'}
                  </button>
                  <button 
                    onClick={handleSplitActiveItem}
                    disabled={actionLoading === 'split'}
                    className="px-3 border border-[var(--border-color)] bg-[var(--bg-card)] text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 rounded-lg cursor-pointer text-center text-[9px] font-bold whitespace-nowrap"
                  >
                    {actionLoading === 'split' ? '拆分中' : '拆分'}
                  </button>
                </div>
              </div>

            </div>

          </div>
        </div>
      )}

    </div>
  );
}
