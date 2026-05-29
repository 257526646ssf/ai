import React, { useEffect, useState } from 'react';
import { 
  FileText, 
  Download, 
  Share2, 
  Sparkles, 
  CheckCircle,
  AlertTriangle,
  BookOpen,
  Plus,
  ArrowLeft,
  Settings,
  PlusSquare,
  Trash2,
  Copy,
  ChevronDown,
  Layers
} from 'lucide-react';
import TiltCard from '../components/TiltCard';
import AnimatedNumber from '../components/AnimatedNumber';
import { apiGet, apiPost, downloadTextFile, formatDateTime, pickList } from '../lib/api';

const toPercentLabel = (value, fallback = '97.46%') => {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  const normalized = num > 0 && num <= 1 ? num * 100 : num;
  return `${normalized.toFixed(normalized >= 99 ? 2 : 1)}%`;
};

const readReportMetrics = (report = {}) => {
  const snapshot = report.data_snapshot || {};
  const summary = snapshot.summary_metrics || snapshot.summary || {};
  const defects = snapshot.defects || {};
  const passRate = summary.pass_rate ?? summary.execution_pass_rate ?? summary.test_case_pass_rate ?? summary.coverage_rate;
  const defectCount = summary.defects ?? summary.defect_count ?? defects.total ?? defects.count ?? 0;
  return { passRate, defectCount };
};

const mapBackendReport = (report) => {
  const metrics = readReportMetrics(report);
  const rate = toPercentLabel(metrics.passRate, '暂无');
  const rateValue = Number(metrics.passRate);
  const normalizedRate = rateValue > 0 && rateValue <= 1 ? rateValue * 100 : rateValue;
  const status = Number.isFinite(normalizedRate)
    ? normalizedRate >= 95
      ? '优秀'
      : normalizedRate >= 85
        ? '良好'
        : '待改进'
    : report.status === 'generated'
      ? '已生成'
      : report.status || '已生成';

  return {
    id: String(report.id),
    raw: report,
    name: report.name || `测试报告 #${report.id}`,
    type: report.type || '综合评估',
    date: formatDateTime(report.generated_at || report.created_at),
    rate,
    bugs: Number(metrics.defectCount) || 0,
    status
  };
};

const buildReportInsights = (report) => {
  if (!report) return [];
  const raw = report.raw || {};
  const metrics = readReportMetrics(raw);
  const defects = Number(metrics.defectCount) || report.bugs || 0;
  const passRate = Number(metrics.passRate);
  const normalizedRate = passRate > 0 && passRate <= 1 ? passRate * 100 : passRate;
  const releaseType = defects > 0 || (Number.isFinite(normalizedRate) && normalizedRate < 95) ? 'warning' : 'success';

  return [
    {
      title: '后端报告聚合结果',
      text: raw.content ? '报告内容已由后端聚合器生成，可进入详情页下载 Markdown / HTML / JSON 文件。' : '后端已有报告记录，但暂未包含可展示的正文快照。',
      type: 'info'
    },
    {
      title: releaseType === 'success' ? '当前准出风险较低' : '仍需关注准出风险',
      text: `当前报告统计通过率为 ${report.rate}，残留缺陷 ${defects} 个。建议结合缺陷严重级别与关键链路覆盖情况做最终签发判断。`,
      type: releaseType
    }
  ];
};

export default function Reports() {
  const [viewMode, setViewMode] = useState('list'); // 'list', 'report-detail', 'template-manage', 'lightweight-conclusion'
  const [selectedReportId, setSelectedReportId] = useState('REP-20250520-01');
  const [projectContext, setProjectContext] = useState(null);
  const [remoteReports, setRemoteReports] = useState([]);
  const [reportStatus, setReportStatus] = useState({ loading: true, error: '' });
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [isDownloadingReport, setIsDownloadingReport] = useState(false);
  const [isGeneratingConclusion, setIsGeneratingConclusion] = useState(false);

  const reportAiInsights = {
    'REP-20250520-01': [
      { title: '二期首个里程碑分析意见', text: '经过自动化回归和高频接口压力测试，系统当前通过率达 100%，性能基线指标相比上月优化 12%。但高并发下发现轻微的连接池等待现象，应在正式上线前扩容。', type: 'info' },
      { title: '总体准出评估', text: '满足所有一期及二期功能性指标，系统缺陷率收敛至 0.00 个/KLOC，稳定性维持在 95% 高位。允许无风险发布。', type: 'success' }
    ],
    'REP-20250519-02': [
      { title: '负载压测瓶颈提示', text: '在高并发 (500 并发) 持续压测下，发现数据库连接池出现大量的事务排队挂起，TTFB 突增至 1.8s。这是由于事务锁未及时释放导致的。', type: 'warning' },
      { title: '优化阻断建议', text: '建议对支付模块的更新锁进行细粒度拆分，暂缓核心数据库的同步写策略，直到压测通过率达到 99.9% 准出基线。', type: 'danger' }
    ],
    'REP-20250519-03': [
      { title: '电商系统回归质量说明', text: '本次电商大版本回归中发现 54 个残留缺陷，其中有 8 个严重缺陷挂起在结算模块，主要表现为优惠券计算金额精度偏差。', type: 'danger' },
      { title: '版本发布风险警告', text: '当前核心结算支付模块的用例通过率仅有 85%，严重阻碍业务上线。强烈建议封版进行缺陷收敛后再考虑发布。', type: 'warning' }
    ]
  };

  const fallbackReports = [
    { id: 'REP-20250520-01', name: 'AI测试平台二期首个里程碑分析报告', type: '综合评估', date: '2025-05-20 10:25', rate: '100%', bugs: 0, status: '优秀' },
    { id: 'REP-20250519-02', name: '智能客服系统 V2.1 性能负载压测报告', type: '性能专项', date: '2025-05-19 16:48', rate: '99.98%', bugs: 18, status: '良好' },
    { id: 'REP-20250519-03', name: '电商平台回归测试分析报告', type: '阶段回归', date: '2025-05-19 14:12', rate: '92.4%', bugs: 54, status: '待改进' }
  ];
  const reports = remoteReports.length ? remoteReports : fallbackReports;
  const selectedReport = reports.find(rep => rep.id === selectedReportId) || reports[0];
  const selectedInsights = reportAiInsights[selectedReportId] || buildReportInsights(selectedReport);

  useEffect(() => {
    let cancelled = false;

    async function loadReports() {
      setReportStatus({ loading: true, error: '' });
      try {
        const projectsPayload = await apiGet('/projects', { params: { page: 1, pageSize: 1 } });
        const project = pickList(projectsPayload)[0];
        if (!project?.id) {
          if (!cancelled) {
            setProjectContext(null);
            setRemoteReports([]);
            setReportStatus({ loading: false, error: '后端暂无项目，已显示演示报告' });
          }
          return;
        }

        const reportsPayload = await apiGet(`/projects/${project.id}/reports`, { params: { page: 1, pageSize: 20 } });
        const mappedReports = pickList(reportsPayload).map(mapBackendReport);

        if (cancelled) return;
        setProjectContext(project);
        setRemoteReports(mappedReports);
        setReportStatus({
          loading: false,
          error: mappedReports.length ? '' : '后端暂无报告，已显示演示报告'
        });
        if (mappedReports.length) {
          setSelectedReportId(prev => (mappedReports.some(rep => rep.id === prev) ? prev : mappedReports[0].id));
        }
      } catch (error) {
        if (!cancelled) {
          setProjectContext(null);
          setRemoteReports([]);
          setReportStatus({ loading: false, error: error?.message || '后端暂不可用，已显示演示报告' });
        }
      }
    }

    loadReports();
    return () => {
      cancelled = true;
    };
  }, []);

  const showToast = (message, type = 'success') => {
    window.dispatchEvent(new CustomEvent('show-toast', { detail: { message, type } }));
  };

  const handleDownloadReport = async (format = 'markdown') => {
    const id = selectedReport?.id;
    if (!id || !/^\d+$/.test(String(id))) {
      showToast('当前为演示报告，暂无后端下载文件。', 'info');
      return;
    }

    setIsDownloadingReport(true);
    try {
      const exported = await apiGet(`/reports/${id}/download`, { params: { format } });
      downloadTextFile({
        filename: exported.filename,
        content: exported.content,
        mimeType: exported.mime_type
      });
      showToast('测试报告文件已开始下载。');
    } catch (error) {
      showToast(error?.message || '报告下载失败，请检查后端服务。', 'error');
    } finally {
      setIsDownloadingReport(false);
    }
  };

  const handleCreateComprehensiveReport = async () => {
    if (!projectContext?.id) {
      showToast('后端暂无可用项目，无法生成真实报告。', 'error');
      return;
    }

    setIsGeneratingReport(true);
    try {
      const created = await apiPost('/reports/comprehensive', {
        project_id: projectContext.id,
        title: `${projectContext.name || '项目'} 综合测试报告`,
        type: 'comprehensive'
      });
      const report = created.report || created;
      const mapped = mapBackendReport(report);
      setRemoteReports(prev => [mapped, ...prev.filter(item => item.id !== mapped.id)]);
      setSelectedReportId(mapped.id);
      setReportStatus({ loading: false, error: '' });
      showToast('综合测试报告已由后端生成。');
    } catch (error) {
      showToast(error?.message || '综合测试报告生成失败。', 'error');
    } finally {
      setIsGeneratingReport(false);
    }
  };

  const handleOpenLightweightConclusion = async () => {
    setViewMode('lightweight-conclusion');
    if (!projectContext?.id) return;

    setIsGeneratingConclusion(true);
    try {
      const result = await apiPost('/reports/lightweight-conclusions', {
        project_id: projectContext.id,
        type: 'release',
        save: false
      });
      if (result.conclusion) {
        setConclusionText(result.conclusion);
        showToast('轻量测试结论已按后端数据刷新。');
      }
    } catch (error) {
      showToast(error?.message || '轻量测试结论刷新失败，保留当前文本。', 'error');
    } finally {
      setIsGeneratingConclusion(false);
    }
  };

  const handleArchiveConclusion = async () => {
    if (!projectContext?.id) {
      showToast('当前为演示数据，结论未写入后端。', 'info');
      setViewMode('list');
      return;
    }

    setIsGeneratingConclusion(true);
    try {
      const result = await apiPost('/reports/lightweight-conclusions', {
        project_id: projectContext.id,
        type: 'release',
        save: true,
        title: `${projectContext.name || '项目'} 轻量准出结论`
      });
      if (result.conclusion) setConclusionText(result.conclusion);
      if (result.report) {
        const mapped = mapBackendReport(result.report);
        setRemoteReports(prev => [mapped, ...prev.filter(item => item.id !== mapped.id)]);
        setSelectedReportId(mapped.id);
      }
      showToast('测试结论已归档到后端报告中心。');
      setViewMode('list');
    } catch (error) {
      showToast(error?.message || '测试结论归档失败。', 'error');
    } finally {
      setIsGeneratingConclusion(false);
    }
  };

  // 模版管理的组件块数据
  const [templateBlocks, setTemplateBlocks] = useState([
    { id: '1', name: '质量大盘概览', desc: '展示版本通过率及模块占比', enabled: true },
    { id: '2', name: '缺陷分布分析', desc: '展现引入Bug的严重度漏斗', enabled: true },
    { id: '3', name: '接口覆盖漏斗', desc: '覆盖率健康度雷达看板', enabled: true },
    { id: '4', name: 'AI 自动签发意见', desc: '大模型出具的版本上线分析', enabled: true }
  ]);

  const [conclusionText, setConclusionText] = useState(
    `【智能客服系统 V2.1 回归测试签发结论】\n本次回归测试共执行自动化用例 1,248 条，通过率达 98.4%。\n遗留活动缺陷 3 个（均为 P3 低影响，均有对应修复排期）。\n综上所述，当前版本质量达标，性能指标优良，评估风险可控，予以签发上线。`
  );

  const renderReportDetail = () => {
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
              <span>返回报告中心</span>
            </button>
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400 font-semibold">
              <span>报告中心</span>
              <span>/</span>
              <span className="text-[var(--text-primary)]">{selectedReport?.name || '电商平台回归测试分析报告'}</span>
            </div>
          </div>
          <button 
            onClick={() => handleDownloadReport('html')}
            disabled={isDownloadingReport}
            className="px-3 py-1.5 rounded-lg accent-btn text-[11px] font-bold text-white cursor-pointer shadow-sm flex items-center gap-1"
          >
            <Download className="size-3.5" />
            <span>{isDownloadingReport ? '下载中...' : '下载测试报告 HTML'}</span>
          </button>
        </div>

        {/* 核心大盘与缺陷分布 */}
        <div className="grid grid-cols-12 gap-4">
          {/* Left: 质量大盘 */}
          <div className="col-span-8 theme-card rounded-xl p-4 shadow-soft space-y-4">
            <h3 className="text-xs font-bold border-b border-[var(--border-color)] pb-2 text-slate-800">模块质量大盘明细</h3>
            
            <div className="grid grid-cols-3 gap-4">
              <div className="border border-slate-100 rounded-xl p-3 flex flex-col justify-between items-center bg-[#fafafb]">
                <span className="text-[9px] text-slate-400 font-bold">总体通过率</span>
                <div className="size-16 relative mt-1.5 sonar-ripple-container">
                  <div className="sonar-ripple-circle !border-[#10b981]"></div>
                  <div className="sonar-ripple-circle sonar-ripple-circle-delay !border-[#10b981]"></div>
                  <svg className="w-full h-full transform -rotate-90 relative z-10" viewBox="0 0 36 36">
                    <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--border-color)" strokeWidth="3" />
                    <circle cx="18" cy="18" r="15.9" fill="none" stroke="#10b981" strokeWidth="3" strokeDasharray="92.4 7.6" className="path-drawn" />
                    <path d="M18,18 L18,2 A16,16 0 0,1 30,10 Z" fill="rgba(16, 185, 129, 0.15)" className="radar-sweeper-beam" />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-[var(--text-primary)] z-10"><AnimatedNumber value={92.4} />%</div>
                </div>
              </div>

              <div className="col-span-2 border border-slate-100 rounded-xl p-3 text-[9px] font-semibold text-slate-500 bg-[#fafafb] space-y-1.5">
                <span className="text-slate-400 block font-bold">各模块用例通过明细</span>
                <div className="space-y-1 scale-95 origin-left">
                  <div className="flex justify-between"><span>用户认证模块: 100%</span><span>156 / 156</span></div>
                  <div className="flex justify-between"><span>会话对话模块: 94.5%</span><span>512 / 542</span></div>
                  <div className="flex justify-between text-red-500"><span>核心结算支付: 85.0%</span><span>243 / 286</span></div>
                </div>
              </div>
            </div>

            {/* 缺陷分布 */}
            <div className="border-t border-slate-100 pt-3 text-[10px]">
              <span className="font-bold block mb-2 text-slate-700">引入缺陷等级分布</span>
              <div className="grid grid-cols-5 gap-2 text-center font-bold">
                <div className="p-2 bg-purple-500/10 rounded-lg text-purple-700 text-[9px]">
                  <div>1 个</div>
                  <div className="text-[7.5px] opacity-60 mt-0.5">致命 (Fatal)</div>
                </div>
                <div className="p-2 bg-red-500/10 rounded-lg text-red-600 text-[9px]">
                  <div>8 个</div>
                  <div className="text-[7.5px] opacity-60 mt-0.5">严重 (Critical)</div>
                </div>
                <div className="p-2 bg-amber-500/10 rounded-lg text-amber-600 text-[9px]">
                  <div>15 个</div>
                  <div className="text-[7.5px] opacity-60 mt-0.5">高 (High)</div>
                </div>
                <div className="p-2 bg-blue-500/10 rounded-lg text-blue-600 text-[9px]">
                  <div>20 个</div>
                  <div className="text-[7.5px] opacity-60 mt-0.5">中 (Medium)</div>
                </div>
                <div className="p-2 bg-slate-500/10 rounded-lg text-slate-500 text-[9px]">
                  <div>10 个</div>
                  <div className="text-[7.5px] opacity-60 mt-0.5">低 (Low)</div>
                </div>
              </div>
            </div>
          </div>

          {/* Right: AI 建议 */}
          <TiltCard className="col-span-4 theme-card rounded-xl p-4 shadow-soft text-left flex flex-col justify-between">
            <div style={{ transform: 'translateZ(20px)', transformStyle: 'preserve-3d' }}>
              <h3 className="text-xs font-bold text-slate-800 border-b border-[var(--border-color)] pb-2 mb-3 flex items-center gap-1">
                <Sparkles className="size-4 text-purple-600 animate-pulse" />
                <span>AI 质量分析评估意见</span>
              </h3>
              
              <div className="space-y-3.5 text-[9.5px] font-semibold text-slate-600 leading-relaxed font-sans">
                <div className="p-3 bg-red-500/5 border border-red-500/10 rounded-xl" style={{ transform: 'translateZ(10px)' }}>
                  <span className="font-bold text-red-500">发现核心风险挂起项</span>
                  <p className="text-[8px] text-slate-400 mt-1 leading-normal">
                    由于结算模块测试用例通过率发生了一定的下滑 (85%)，系统引入了 1 个致命的“死锁事务挂起”缺陷仍未修复，这可能对大规模并发时的交易准确度带来影响。
                  </p>
                </div>

                <div className="p-3 bg-purple-500/5 border border-purple-500/10 rounded-xl" style={{ transform: 'translateZ(15px)' }}>
                  <span className="font-bold text-purple-700">上线签发意见说明</span>
                  <p className="text-[8px] text-slate-400 mt-1 leading-normal">
                    在当前未修复该致命死锁缺陷前，建议阻止直接发布上线。若业务必须紧急发布，应部署连接超时与自愈哨兵。
                  </p>
                </div>
              </div>
            </div>

            <button 
              onClick={handleOpenLightweightConclusion}
              className="w-full py-2 accent-btn text-[10px] font-bold rounded-lg cursor-pointer text-center mt-4"
              style={{ transform: 'translateZ(25px)' }}
            >
              {isGeneratingConclusion ? '生成签发文案中...' : '微调上线签发文案'}
            </button>
          </TiltCard>
        </div>
      </div>
    );
  };

  const renderTemplateManage = () => {
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
              <span>返回报告中心</span>
            </button>
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400 font-semibold">
              <span>报告中心</span>
              <span>/</span>
              <span className="text-[var(--text-primary)]">报告模板管理画板</span>
            </div>
          </div>
          <button 
            onClick={() => {
              window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '自定义报告模板已应用生效！', type: 'success' } }));
              setViewMode('list');
            }}
            className="px-3 py-1.5 rounded-lg accent-btn text-[11px] font-bold text-white cursor-pointer shadow-sm"
          >
            保存并应用模板
          </button>
        </div>

        {/* 模板画布 */}
        <div className="theme-card rounded-xl p-4 shadow-soft">
          <div className="flex justify-between items-center border-b border-[var(--border-color)] pb-2 mb-4">
            <h3 className="text-xs font-bold text-slate-800">可视化报告组件块拖拽与排序</h3>
            <span className="text-[8px] text-slate-400">点击垃圾桶图标可停用该渲染块</span>
          </div>

          <div className="grid grid-cols-12 gap-4">
            {/* 画布 */}
            <div className="col-span-8 space-y-3">
              {templateBlocks.map((block, idx) => (
                <div key={block.id} className="p-3 border border-[var(--border-color)] bg-[var(--bg-card)] rounded-xl flex items-center justify-between shadow-sm cursor-grab hover:border-blue-500/25 transition-all">
                  <div className="flex items-center gap-2.5">
                    <Layers className="size-4 text-slate-400 shrink-0" />
                    <div className="text-left font-bold text-[10px]">
                      <span className="text-slate-800">{block.name}</span>
                      <span className="text-[8px] text-slate-400 font-normal ml-2">{block.desc}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[8.5px] text-slate-400 font-mono">第 {idx + 1} 块</span>
                    <button 
                      onClick={() => {
                        window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: `已移除组件块：${block.name}`, type: 'info' } }));
                        setTemplateBlocks(prev => prev.filter(b => b.id !== block.id));
                      }}
                      className="p-1 text-[var(--text-secondary)] hover:text-red-500 cursor-pointer"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* 备选 */}
            <div className="col-span-4 theme-card rounded-xl p-3 shadow-soft text-[10px] space-y-3 text-left">
              <span className="font-bold text-slate-700 block border-b pb-1">可供加入画布的备选组件</span>
              <div className="space-y-2">
                {[
                  { name: '性能专项波形', desc: 'TPS 瓶颈交叉交叉比对' },
                  { name: '测试报告签发书', desc: '上线签收大纲说明文本' },
                  { name: '接口覆盖漏斗', desc: '覆盖率健康度雷达看板' }
                ].map((item, idx) => (
                  <div key={idx} className="p-2 border border-slate-100 rounded-lg flex items-center justify-between bg-slate-50/50">
                    <div className="min-w-0">
                      <div className="font-bold text-slate-700 truncate">{item.name}</div>
                      <div className="text-[7.5px] text-slate-400 truncate">{item.desc}</div>
                    </div>
                    <button 
                      onClick={() => {
                        const newBlock = { id: String(Date.now()), name: item.name, desc: item.desc, enabled: true };
                        setTemplateBlocks(prev => [...prev, newBlock]);
                        window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: `已向画布追加组件块：${item.name}`, type: 'success' } }));
                      }}
                      className="p-1 bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[var(--accent-color)] rounded border border-[var(--border-color)] cursor-pointer"
                    >
                      <Plus className="size-3" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderLightweightConclusion = () => {
    return (
      <div className="space-y-4 text-left animate-[fadeIn_0.2s_ease-out] w-full">
        {/* 面包屑 */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <button 
              onClick={() => setViewMode('report-detail')}
              className="flex items-center gap-1 px-2.5 py-1 rounded border border-[var(--border-color)] bg-[var(--bg-card)] text-[10px] text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 transition-colors shadow-sm cursor-pointer"
            >
              <ArrowLeft className="size-3" />
              <span>返回报告详情</span>
            </button>
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400 font-semibold">
              <span>报告中心</span>
              <span>/</span>
              <span>阶段分析</span>
              <span>/</span>
              <span className="text-[var(--text-primary)]">轻量测试结论生成</span>
            </div>
          </div>
          <button 
            onClick={handleArchiveConclusion}
            disabled={isGeneratingConclusion}
            className="px-3 py-1.5 rounded-lg accent-btn text-[11px] font-bold text-white cursor-pointer shadow-sm"
          >
            {isGeneratingConclusion ? '归档中...' : '签发并归档结论'}
          </button>
        </div>

        {/* 结论大框 */}
        <div className="grid grid-cols-12 gap-4">
          <div className="col-span-4 theme-card rounded-xl p-4 shadow-soft space-y-4 text-xs font-semibold text-[var(--text-secondary)]">
            <h3 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2">大模型智能意见微调</h3>
            <div className="space-y-2">
              <label className="text-[10px] text-[var(--text-secondary)] font-bold block">签发结论模板文本</label>
              <textarea 
                value={conclusionText} 
                onChange={(e) => setConclusionText(e.target.value)}
                className="w-full h-40 p-2.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-app)] text-[10px] text-[var(--text-primary)] font-mono resize-none focus:outline-none focus:border-[var(--accent-color)]"
              />
            </div>
          </div>
          <div className="col-span-8 theme-card rounded-xl p-4 shadow-soft space-y-4">
            <h3 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2 flex items-center gap-1">
              <Sparkles className="size-4 text-purple-600 animate-pulse" />
              <span>实时效果预演</span>
            </h3>
            <div className="p-4 border border-[var(--border-color)] bg-[var(--bg-app)] rounded-xl whitespace-pre-wrap font-mono text-[10px] text-[var(--text-primary)]">
              {conclusionText}
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4 text-left p-1 w-full flex flex-col h-full min-h-0">
      {viewMode === 'list' && (
        <>
          {/* 第一排：报告多维指标看板 (防高度压缩 Bug 修复) */}
          <div className="grid grid-cols-4 gap-4 flex-shrink-0">
            <div className="theme-card rounded-xl p-4 flex flex-col justify-between border min-h-[96px] shrink-0">
              <div className="flex items-center justify-between text-[10px] opacity-60 text-[var(--text-secondary)] font-medium">
                <span>分析报告总数</span>
                <FileText className="size-3.5 text-blue-500" />
              </div>
              <div className="mt-2 flex flex-col">
                <span className="text-xl font-black text-[var(--text-primary)] leading-tight"><AnimatedNumber value={reports.length} /> 份</span>
                <span className="text-[9px] text-[var(--text-secondary)] mt-1">覆盖系统 8 个核心业务模块</span>
              </div>
            </div>

            <div className="theme-card rounded-xl p-4 flex flex-col justify-between border min-h-[96px] shrink-0">
              <div className="flex items-center justify-between text-[10px] opacity-60 text-[var(--text-secondary)] font-medium">
                <span>最新构建通过率</span>
                <CheckCircle className="size-3.5 text-emerald-500" />
              </div>
              <div className="mt-2 flex flex-col">
                <span className="text-xl font-black text-emerald-500 leading-tight"><AnimatedNumber value={97.46} />%</span>
                <span className="text-[9px] text-[var(--text-secondary)] mt-1">较上周平均提升 3.2% ↑</span>
              </div>
            </div>

            <div className="theme-card rounded-xl p-4 flex flex-col justify-between border min-h-[96px] shrink-0">
              <div className="flex items-center justify-between text-[10px] opacity-60 text-[var(--text-secondary)] font-medium">
                <span>累计发现残留缺陷</span>
                <AlertTriangle className="size-3.5 text-amber-500 animate-pulse" />
              </div>
              <div className="mt-2 flex flex-col">
                <span className="text-xl font-black text-red-500 leading-tight"><AnimatedNumber value={72} /> 个</span>
                <span className="text-[9px] text-[var(--text-secondary)] mt-1">其中致命/严重级别共 24 个</span>
              </div>
            </div>

            <div className="theme-card rounded-xl p-4 flex flex-col justify-between border min-h-[96px] shrink-0">
              <div className="flex items-center justify-between text-[10px] opacity-60 text-[var(--text-secondary)] font-medium">
                <span>AI 准出评估</span>
                <Sparkles className="size-3.5 text-purple-500" />
              </div>
              <div className="mt-2 flex flex-col">
                <span className="text-xl font-black text-[var(--text-primary)] leading-tight">安全准出</span>
                <span className="text-[9px] text-[var(--text-secondary)] mt-1">2 个发布轮次通过 AI 审计</span>
              </div>
            </div>
          </div>

          {/* 第二排：主分栏（7:5 选中联动布局，彻底解决留白与高度不对齐） */}
          <div className="grid grid-cols-12 gap-5 w-full items-stretch flex-1 min-h-0">
            {/* 左侧 7 份：报告列表 */}
            <div className="col-span-7 h-full flex flex-col min-h-0">
              <div className="theme-card rounded-xl p-4 shadow-sm text-left flex-1 flex flex-col justify-between h-full min-h-0">
                <div className="flex flex-col flex-1 min-h-0">
                  <div className="flex justify-between items-center mb-3 shrink-0">
                    <span className="text-xs font-bold text-[var(--text-primary)]">质量分析报告列表</span>
                    <div className="flex items-center gap-2">
                      <span className="text-[9px] text-[var(--text-secondary)]">
                        {reportStatus.loading ? '正在同步后端报告...' : reportStatus.error || '点击查看 AI 审核意见'}
                      </span>
                      <button
                        onClick={handleCreateComprehensiveReport}
                        disabled={isGeneratingReport}
                        className="px-2 py-1 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[9px] text-[var(--text-primary)] cursor-pointer flex items-center gap-1 font-bold"
                      >
                        <PlusSquare className="size-3" />
                        <span>{isGeneratingReport ? '生成中' : '生成报告'}</span>
                      </button>
                    </div>
                  </div>
                  
                  {/* 可滚动列表容器，自适应撑满 */}
                  <div className="space-y-2.5 flex-1 overflow-y-auto pr-1 min-h-0">
                    {reports.map((rep) => {
                      const isSelected = selectedReportId === rep.id;
                      return (
                        <div 
                          key={rep.id}
                          onClick={() => setSelectedReportId(rep.id)}
                          className={`p-3.5 border rounded-xl flex items-center justify-between cursor-pointer transition-all duration-200 ${
                            isSelected 
                              ? 'border-[var(--accent-color)] bg-[var(--accent-glow)] shadow-md' 
                              : 'border-[var(--border-color)] bg-[var(--bg-card)] hover:border-[var(--accent-color)]/50'
                          }`}
                        >
                          <div className="flex items-center gap-3 min-w-0">
                            <div className={`p-2 rounded-lg ${isSelected ? 'bg-[var(--accent-color)] text-white' : 'bg-[var(--border-color)] text-[var(--text-secondary)]'}`}>
                              <FileText className="size-4" />
                            </div>
                            <div className="text-left min-w-0">
                              <div className="font-bold text-[10.5px] text-[var(--text-primary)] truncate">{rep.name}</div>
                              <div className="flex items-center gap-2 mt-1.5 text-[8.5px] text-[var(--text-secondary)]">
                                <span className="px-1.5 py-0.5 rounded border border-[var(--border-color)]">{rep.type}</span>
                                <span>{rep.date}</span>
                                <span>•</span>
                                <span>缺陷: <span className="font-bold text-red-500">{rep.bugs}</span></span>
                              </div>
                            </div>
                          </div>

                          <div className="flex items-center gap-3 text-[10px] font-bold text-[var(--text-secondary)]">
                            <div className="text-right mr-1">
                              <div className="text-[10px] font-black text-[var(--text-primary)]">{rep.rate}</div>
                              <div className="text-[7.5px] text-[var(--text-secondary)]">通过率</div>
                            </div>
                            <span className={`px-2 py-0.5 rounded text-[9px] font-bold ${
                              rep.status === '优秀' 
                                ? 'text-emerald-600 bg-emerald-500/10' 
                                : rep.status === '良好' 
                                  ? 'text-blue-600 bg-blue-500/10' 
                                  : 'text-amber-600 bg-amber-500/10'
                            }`}>{rep.status}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>

            {/* 右侧 5 份：AI 意见 (弹性撑开对齐) */}
            <div className="col-span-5 h-full flex flex-col min-h-0">
              <TiltCard className="col-span-5 min-w-0 theme-card rounded-xl p-4 shadow-sm text-left flex-1 flex flex-col justify-between h-full min-h-0">
                <div className="flex flex-col flex-1 min-h-0" style={{ transform: 'translateZ(20px)', transformStyle: 'preserve-3d' }}>
                  <h3 className="text-xs font-bold text-[var(--text-primary)] border-b border-[var(--border-color)] pb-2.5 mb-3 flex items-center justify-between shrink-0">
                    <div className="flex items-center gap-1.5">
                      <Sparkles className="size-4 text-purple-600 animate-pulse" />
                      <span>AI 质量评估意见</span>
                    </div>
                    <span className="text-[8.5px] font-mono opacity-50">{selectedReportId}</span>
                  </h3>

                  <div className="space-y-3 text-[9.5px] font-semibold leading-relaxed font-sans flex-1 overflow-y-auto pr-1 min-h-0">
                    {selectedInsights.length ? (
                      selectedInsights.map((insight, idx) => (
                        <div 
                          key={idx}
                          className={`p-3 border rounded-xl space-y-1 ${
                            insight.type === 'danger' 
                              ? 'bg-red-500/5 border-red-500/20' 
                              : insight.type === 'warning' 
                                ? 'bg-amber-500/5 border-amber-500/20'
                                : insight.type === 'success'
                                  ? 'bg-emerald-500/5 border-emerald-500/20'
                                  : 'bg-blue-500/5 border-blue-500/20'
                          }`}
                          style={{ transform: `translateZ(${10 + idx * 5}px)` }}
                        >
                          <div className={`font-bold flex items-center gap-1 ${
                            insight.type === 'danger' 
                              ? 'text-red-500' 
                              : insight.type === 'warning' 
                                ? 'text-amber-500'
                                : insight.type === 'success'
                                  ? 'text-emerald-500'
                                  : 'text-blue-500'
                          }`}>
                            <div className="size-1.5 rounded-full bg-current shrink-0" />
                            <span>{insight.title}</span>
                          </div>
                          <p className="text-[8.5px] text-[var(--text-secondary)] leading-normal">
                            {insight.text}
                          </p>
                        </div>
                      ))
                    ) : (
                      <div className="text-center py-8 text-[var(--text-secondary)]">暂无 AI 分析数据</div>
                    )}
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-[var(--border-color)] flex gap-2 shrink-0" style={{ transform: 'translateZ(25px)' }}>
                  <button 
                    onClick={() => setViewMode('report-detail')}
                    className="flex-1 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[9.5px] text-[var(--text-primary)] cursor-pointer text-center font-bold"
                  >
                    查看完整报告详情
                  </button>
                  <button 
                    onClick={() => handleDownloadReport('markdown')}
                    disabled={isDownloadingReport}
                    className="px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[9.5px] text-[var(--text-primary)] cursor-pointer flex items-center justify-center"
                  >
                    <Download className="size-3.5" />
                  </button>
                  <button 
                    onClick={() => window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '分享链接已复制到剪贴板！', type: 'success' } }))}
                    className="px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/50 text-[9.5px] text-[var(--text-primary)] cursor-pointer flex items-center justify-center"
                  >
                    <Share2 className="size-3.5" />
                  </button>
                </div>
              </TiltCard>
            </div>
          </div>
        </>
      )}

      {viewMode === 'report-detail' && renderReportDetail()}
      {viewMode === 'template-manage' && renderTemplateManage()}
      {viewMode === 'lightweight-conclusion' && renderLightweightConclusion()}
    </div>
  );
}
