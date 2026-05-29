import React, { useState } from 'react';
import { 
  Folder, 
  FileText, 
  CheckSquare, 
  Play, 
  Target, 
  Network, 
  Cpu, 
  Gauge, 
  Upload, 
  Sparkles, 
  Bot,
  AlertCircle,
  FileCheck
} from 'lucide-react';
import TiltCard from '../components/TiltCard';
import AnimatedNumber from '../components/AnimatedNumber';
import { apiGet, formatDateTime, pickList } from '../lib/api';

const numberText = (value, fallback = '0') => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toLocaleString('zh-CN') : fallback;
};

const percentFromCounts = (total, defects, fallback = '87.6%') => {
  const totalNum = Number(total);
  const defectNum = Number(defects);
  if (!Number.isFinite(totalNum) || totalNum <= 0) return fallback;
  const passRate = Math.max(0, Math.min(100, ((totalNum - Math.max(defectNum, 0)) / totalNum) * 100));
  return `${passRate.toFixed(1)}%`;
};

const activityIconByType = (type = '') => {
  const lowered = String(type).toLowerCase();
  if (lowered.includes('defect') || lowered.includes('bug')) return { icon: AlertCircle, iconStyle: 'bg-red-500 text-white', style: 'border-red-500/20 text-red-500 bg-red-500/5' };
  if (lowered.includes('execution') || lowered.includes('run')) return { icon: Play, iconStyle: 'bg-blue-500 text-white', style: 'border-emerald-500/20 text-emerald-500 bg-emerald-500/5' };
  if (lowered.includes('auto')) return { icon: Cpu, iconStyle: 'bg-amber-500 text-white', style: 'border-amber-500/20 text-amber-500 bg-amber-500/5' };
  if (lowered.includes('report')) return { icon: FileCheck, iconStyle: 'bg-purple-500 text-white', style: 'border-purple-500/20 text-purple-500 bg-purple-500/5' };
  return { icon: FileText, iconStyle: 'bg-purple-500 text-white', style: 'border-blue-500/20 text-blue-500 bg-blue-500/5' };
};

export default function Dashboard({ theme }) {
  const [progressValue, setProgressValue] = React.useState(0);
  const [casesCount, setCasesCount] = React.useState({ covered: 0, partial: 0, uncovered: 0 });
  const [hoveredRow, setHoveredRow] = React.useState(null);
  const [hoveredCol, setHoveredCol] = React.useState(null);
  const [reloadKey, setReloadKey] = React.useState(0);
  const [dashboardData, setDashboardData] = React.useState(null);
  const [remoteActivities, setRemoteActivities] = React.useState([]);
  const [apiState, setApiState] = React.useState({
    status: 'idle',
    projectName: '演示项目',
    updatedAt: null,
    error: ''
  });

  React.useEffect(() => {
    let start = 0;
    const end = 78.4;
    const duration = 1000;
    const stepTime = 15;
    const steps = duration / stepTime;
    const increment = end / steps;
    
    const covEnd = 977;
    const partEnd = 184;
    const uncovEnd = 87;
    
    const timer = setInterval(() => {
      start += increment;
      if (start >= end) {
        setProgressValue(end);
        setCasesCount({ covered: covEnd, partial: partEnd, uncovered: uncovEnd });
        clearInterval(timer);
      } else {
        const curProgress = Number(start.toFixed(1));
        setProgressValue(curProgress);
        const ratio = start / end;
        setCasesCount({
          covered: Math.floor(covEnd * ratio),
          partial: Math.floor(partEnd * ratio),
          uncovered: Math.floor(uncovEnd * ratio)
        });
      }
    }, stepTime);
    
    return () => clearInterval(timer);
  }, []);

  React.useEffect(() => {
    let cancelled = false;

    async function loadDashboardData() {
      setApiState(prev => ({ ...prev, status: 'loading', error: '' }));
      try {
        const projectsPayload = await apiGet('/projects', { params: { page: 1, pageSize: 1 } });
        const project = pickList(projectsPayload)[0];

        if (!project?.id) {
          if (!cancelled) {
            setDashboardData(null);
            setRemoteActivities([]);
            setApiState({ status: 'empty', projectName: '演示项目', updatedAt: null, error: '' });
          }
          return;
        }

        const [dashboard, activitiesPayload] = await Promise.all([
          apiGet(`/projects/${project.id}/dashboard`),
          apiGet('/system/recent-activities', { params: { projectId: project.id, limit: 5 } }).catch(() => ({ list: [] }))
        ]);

        if (cancelled) return;
        setDashboardData(dashboard);
        setRemoteActivities(pickList(activitiesPayload).map((item, idx) => {
          const meta = activityIconByType(item.target_type || item.type || item.route);
          return {
            id: item.id || `remote-${idx}`,
            title: item.title || item.name || '系统活动已记录',
            desc: item.description || [item.target_type, item.target_id].filter(Boolean).join(' / ') || `项目：${project.name || project.code || project.id}`,
            time: formatDateTime(item.created_at || item.updated_at),
            user: item.user || item.actor || '系统',
            tag: item.action || item.target_type || 'Activity',
            ...meta
          };
        }));
        setApiState({
          status: 'online',
          projectName: project.name || project.code || `项目 ${project.id}`,
          updatedAt: dashboard.updated_at,
          error: ''
        });
      } catch (error) {
        if (!cancelled) {
          setDashboardData(null);
          setRemoteActivities([]);
          setApiState({
            status: 'offline',
            projectName: '演示项目',
            updatedAt: null,
            error: error?.message || '后端暂不可用'
          });
        }
      }
    }

    loadDashboardData();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);


  // 根据主题自适应图表色彩
  const getThemeChartColors = () => {
    switch (theme) {
      case 'clickhouse':
        return { pass: '#eab308', fail: '#ef4444', block: '#f59e0b', unexec: '#262626' };
      case 'brutalist':
        return { pass: '#000000', fail: '#ff0000', block: '#ffff00', unexec: '#cccccc' };
      case 'cyber-glass':
        return { pass: '#06b6d4', fail: '#ec4899', block: '#f59e0b', unexec: 'rgba(255,255,255,0.06)' };
      default:
        return { pass: 'var(--accent-color)', fail: '#ef4444', block: '#f59e0b', unexec: 'var(--border-color)' };
    }
  };

  const chartColor = getThemeChartColors();
  const passRate = percentFromCounts(dashboardData?.test_cases, dashboardData?.defects);
  const backendStatusText = apiState.status === 'online'
    ? `已连接：${apiState.projectName}`
    : apiState.status === 'loading'
      ? '正在同步后端数据'
      : apiState.status === 'empty'
        ? '后端暂无项目，显示演示数据'
        : '后端离线，显示演示数据';
  const updatedAtText = apiState.status === 'online'
    ? `数据更新时间：${formatDateTime(apiState.updatedAt)}`
    : apiState.status === 'loading'
      ? '数据同步中...'
      : '数据更新时间：演示数据';

  // ======================== 第一排：指标数据 ========================
  const stats = [
    { label: '需求库总数', value: numberText(dashboardData?.requirement_libs, '24'), change: dashboardData ? '后端实时' : '↑ 2', icon: Folder, color: 'text-blue-500 bg-blue-500/10' },
    { label: '需求总数', value: numberText(dashboardData?.requirement_items, '1,248'), change: dashboardData ? '来自后端统计' : '↑ 54 (+4.5%)', icon: FileText, color: 'text-emerald-500 bg-emerald-500/10' },
    { label: '测试用例总数', value: numberText(dashboardData?.test_cases, '3,652'), change: dashboardData ? '实时项目数据' : '↑ 132 (+3.7%)', icon: CheckSquare, color: 'text-amber-500 bg-amber-500/10' },
    { label: '用例执行总数', value: numberText(dashboardData?.executions, '2,891'), change: dashboardData ? '执行记录聚合' : '↑ 156 (+5.7%)', icon: Play, color: 'text-purple-500 bg-purple-500/10' },
    { label: '用例通过率', value: passRate, change: dashboardData ? `缺陷 ${numberText(dashboardData?.defects, '0')}` : '↑ 3.2%', icon: Target, color: 'text-cyan-500 bg-cyan-500/10' },
    { label: '接口测试库总数', value: '186', change: '↑ 4', icon: Network, color: 'text-indigo-500 bg-indigo-500/10' },
    { label: '自动化脚本总数', value: '842', change: '↑ 27', icon: Cpu, color: 'text-slate-500 bg-slate-500/10' },
    { label: '性能测试方案总数', value: '24', change: '↑ 1', icon: Gauge, color: 'text-rose-500 bg-rose-500/10' },
  ];

  // ======================== 热力图数据 ========================
  const modules = ['认证模块', '交易模块', '知识库', '插件服务', '用户中心', '计费系统', '通知系统', '报表系统'];
  const dimensions = ['需求', '用例', '执行', '缺陷'];
  const heatmapData = [
    [4, 3, 2, 1], [3, 4, 3, 2], [2, 3, 1, 1], [1, 2, 2, 1],
    [3, 3, 4, 2], [2, 2, 3, 3], [1, 1, 2, 1], [2, 2, 1, 1]
  ];

  // ======================== 最近活动数据 ========================
  const activities = [
    { id: 1, title: '执行任务 #EXEC-20250520-0089 完成', desc: '项目：智能客服系统 / 版本：v2.3.0', time: '10:24', user: '张明', tag: '通过率 92.1%', style: 'border-emerald-500/20 text-emerald-500 bg-emerald-500/5', icon: CheckSquare, iconStyle: 'bg-emerald-500 text-white' },
    { id: 2, title: '接口测试 【POST /api/v1/order/create】 执行完成', desc: '项目：电商平台 / 环境：测试环境', time: '10:15', user: '李华', tag: '通过率 92.3%', style: 'border-emerald-500/20 text-emerald-500 bg-emerald-500/5', icon: Play, iconStyle: 'bg-blue-500 text-white' },
    { id: 3, title: '自动化任务「夜间回归 - 全量」执行完成', desc: '项目：智能客服系统 / 共 120 个用例', time: '09:47', user: '王芳', tag: '通过率 90.0%', style: 'border-emerald-500/20 text-emerald-500 bg-emerald-500/5', icon: Cpu, iconStyle: 'bg-amber-500 text-white' },
    { id: 4, title: '缺陷 #BUG-20250520-003 已创建', desc: '项目：电商平台 / 严重程度：高', time: '09:32', user: '赵强', tag: 'P1', style: 'border-red-500/20 text-red-500 bg-red-500/5', icon: AlertCircle, iconStyle: 'bg-red-500 text-white' },
    { id: 5, title: '需求文档《支付系统需求说明书》已上传', desc: '项目：支付系统 / 版本：v1.2', time: '09:15', user: '陈磊', tag: '新增需求 24', style: 'border-blue-500/20 text-blue-500 bg-blue-500/5', icon: FileText, iconStyle: 'bg-purple-500 text-white' }
  ];
  const visibleActivities = remoteActivities.length ? remoteActivities : activities;

  // ======================== 快速操作配置 ========================
  const quickActions = [
    { title: '快速上传需求', desc: '支持 Word、Excel、PDF', icon: Upload, type: 'upload-req' },
    { title: '快速生成用例', desc: '基于需求智能生成用例', icon: Sparkles, type: 'generate-cases' },
    { title: '快速执行接口测试', desc: '选择接口集合，立即执行', icon: Network, type: 'api-request' },
    { title: '创建自动化任务', desc: '构建并执行自动化任务', icon: Cpu, type: 'toast', message: '已成功创建自动化流水线任务！' },
    { title: '创建性能测试方案', desc: '配置并启动性能测试', icon: Gauge, type: 'toast', message: '性能压测方案模版配置已保存！' },
    { title: '生成测试报告', desc: '汇总结果，生成报告', icon: FileCheck, type: 'run-execution' }
  ];

  const handleQuickAction = (act) => {
    if (act.type === 'toast') {
      window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: act.message, type: 'success' } }));
    } else {
      window.dispatchEvent(new CustomEvent('open-modal', { detail: { type: act.type } }));
    }
  };

  // ======================== 项目健康度 ========================
  const healthMetrics = [
    { label: '用例通过率', val: '87.6%', change: '↑ 3.2%', linePath: 'M 5 20 Q 20 5, 35 15 T 65 5 T 95 8' },
    { label: '缺陷密度', val: '2.34', unit: '/KLOC', change: '↓ 0.21', linePath: 'M 5 5 Q 20 20, 35 12 T 65 18 T 95 22' },
    { label: '自动化覆盖', val: '64.8%', change: '↑ 1.6%', linePath: 'M 5 18 Q 20 12, 35 14 T 65 8 T 95 4' },
    { label: '需求覆盖率', val: '78.4%', change: '↑ 2.8%', linePath: 'M 5 22 Q 20 15, 35 18 T 65 10 T 95 5' }
  ];

  // ======================== 今日测试执行概览 ========================
  const executionOverview = [
    { type: '测试计划', plan: 8, exec: 8, pass: '6,532', fail: 982, rate: '86.9%' },
    { type: '接口测试', plan: 23, exec: 23, pass: '1,256', fail: 187, rate: '87.0%' },
    { type: '自动化测试', plan: 15, exec: 15, pass: '3,842', fail: 421, rate: '90.1%' },
    { type: '性能测试', plan: 3, exec: 3, pass: '27', fail: 3, rate: '90.0%' }
  ];

  // ======================== 待办事项 ========================
  const todos = [
    { text: '评审需求文档《用户权限管理需求说明书》', priority: '高', priorityColor: 'text-red-500 bg-red-500/10 border-red-500/10' },
    { text: '修复缺陷 #BUG-20250519-011', priority: '高', priorityColor: 'text-red-500 bg-red-500/10 border-red-500/10' },
    { text: '执行测试计划「版本 v2.3.0 上线回归」', priority: '中', priorityColor: 'text-amber-500 bg-amber-500/10 border-amber-500/10' },
    { text: '完善接口文档 /api/v1/user/profile', priority: '中', priorityColor: 'text-amber-500 bg-amber-500/10 border-amber-500/10' },
    { text: '性能测试「并发 500 - 订单接口」执行分析', priority: '中', priorityColor: 'text-amber-500 bg-amber-500/10 border-amber-500/10' },
    { text: '整理测试报告（周报）', priority: '低', priorityColor: 'text-blue-500 bg-blue-500/10 border-blue-500/10' }
  ];

  return (
    <div className="space-y-5 text-left relative pb-10 w-full animate-[fadeIn_0.2s_ease-out]">
      
      {/* 顶部指示 */}
      <div className="flex justify-between items-center text-[10px] opacity-60 text-[var(--text-secondary)]">
        <div>{backendStatusText}</div>
        <div 
          onClick={() => {
            setReloadKey(prev => prev + 1);
            window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '正在同步后端最新数据...', type: 'info' } }));
          }}
          className="flex items-center gap-1.5 cursor-pointer hover:opacity-100 transition-all font-semibold"
        >
          <span>{updatedAtText}</span>
          <span className="scale-110 font-bold">↻</span>
        </div>
      </div>

      {/* AI 智能网关大盘诊断摘要 (3D 倾斜眩光卡) */}
      <TiltCard 
        className="p-5 flex items-center justify-between gap-4 border border-[var(--accent-color)]/40 bg-[var(--accent-glow)]/20 backdrop-blur-lg relative overflow-hidden animate-[slideUpFade_0.4s_ease-out] laser-chase-border cyber-meteor-dust"
      >
        <div className="flex items-center gap-3 relative z-20" style={{ transformStyle: 'preserve-3d' }}>
          <div className="p-3 rounded-xl bg-purple-500/20 text-purple-600 dark:text-purple-300 shrink-0 transition-transform duration-200 shadow-md" style={{ transform: 'translateZ(30px)' }}>
            <Sparkles className="size-6 animate-pulse" />
          </div>
          <div className="text-left" style={{ transform: 'translateZ(20px)' }}>
            <div className="font-black text-xs text-[var(--text-primary)] flex items-center gap-2">
              <span className="cyber-glitch-text cursor-pointer transition-all text-sm font-black glorious-highlight-text" data-text="AI 测试效能管家">AI 测试效能管家</span>
              <span className="px-2 py-0.5 bg-purple-500/20 text-purple-600 dark:text-purple-300 rounded font-black text-[9px] tracking-wider uppercase border border-purple-500/30 animate-pulse">v2.5 Live</span>
            </div>
            <p className="text-[12px] text-[var(--text-primary)] mt-2 leading-relaxed font-bold">
              今日平台共处理了 <span className="crucial-glow-text font-black">3</span> 个回归测试流水线，用例平均通过率稳定在 <span className="glorious-highlight-text text-[13px] font-black">87.6%</span>。发现 <span className="text-red-500 font-black text-[13px] underline decoration-wavy underline-offset-4">12 个严重缺陷</span> 挂起（主要收敛在结算与支付模块），建议优先关注 <code className="bg-black/10 dark:bg-white/15 px-1.5 py-0.5 rounded font-mono text-[10px] text-pink-600 dark:text-pink-400 font-extrabold border border-pink-500/25">/api/v1/payment/check</code> 接口的连接池死锁风险，防止波及下周的 <span className="text-[var(--accent-color)] font-extrabold underline">v2.3.0 大版本签发</span>。
            </p>
          </div>
        </div>
        <button 
          onClick={() => window.dispatchEvent(new CustomEvent('open-ai-chat'))}
          style={{ transform: 'translateZ(25px)' }}
          className="px-4 py-2 rounded-xl glow-button-neon font-black text-[11px] whitespace-nowrap cursor-pointer transition-all shrink-0 relative z-20 shadow-lg tracking-wider"
        >
          查看 AI 调优大纲
        </button>
      </TiltCard>

      {/* ======================== 第一排：指标卡片 (改为 4 列以扩展宽度) ======================== */}
      <div className="grid grid-cols-4 gap-4">
        {stats.map((item, idx) => {
          const Icon = item.icon;
          return (
            <TiltCard 
              key={idx} 
              className="chroma-glass rounded-xl p-4 shadow-sm flex items-center justify-between shimmer-sweep"
              style={{
                animation: 'slideUpFade 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards',
                animationDelay: `${idx * 40 + 100}ms`,
                opacity: 0
              }}
            >
              <div className="text-left" style={{ transform: 'translateZ(20px)' }}>
                <span className="text-[10.5px] font-bold text-[var(--text-secondary)] tracking-tight block">{item.label}</span>
                <div className="mt-2.5">
                  <span className="text-2.5xl font-black tracking-tight digital-matrix-number">
                    <AnimatedNumber value={item.value} delay={idx * 50 + 150} />
                  </span>
                </div>
                <div className="mt-1 flex items-center text-[9px] font-bold">
                  <span className="text-emerald-500">
                    {item.change}
                  </span>
                </div>
              </div>
              
              <div 
                className={`p-3 rounded-xl ${item.color.split(' ')[1]} ${item.color.split(' ')[0]} shrink-0`}
                style={{ transform: 'translateZ(25px)' }}
              >
                <Icon className="size-[18px]" />
              </div>
            </TiltCard>
          );
        })}
      </div>

      {/* ======================== 第二排：高级分析图表 ======================== */}
      <div className="grid grid-cols-12 gap-5">
        
        {/* 用例执行趋势（近14天） */}
        <div className="col-span-5 theme-card rounded-xl p-4 shadow-sm flex flex-col justify-between min-h-[260px]">
          <div>
            <div className="flex justify-between items-center border-b border-[var(--border-color)] pb-2.5 mb-3">
              <span className="text-xs font-bold text-[var(--text-primary)]">用例执行趋势（近14天）</span>
              <div className="flex items-center gap-1 text-[9.5px] opacity-70 border border-[var(--border-color)] rounded px-1.5 py-0.5 hover:opacity-100 cursor-pointer text-[var(--text-primary)] font-bold">
                <span>近 14 天</span>
                <span className="scale-75 origin-center">▼</span>
              </div>
            </div>
            
            {/* 图例 */}
            <div className="flex gap-4 text-xs font-black mb-3">
              <div className="flex items-center gap-2 text-[var(--text-primary)]">
                <span className="size-2.5 rounded-full border border-white/10 shadow-sm shrink-0" style={{ backgroundColor: 'var(--accent-color)' }}></span>
                <span>通过</span>
              </div>
              <div className="flex items-center gap-2 text-[var(--text-primary)]">
                <span className="size-2.5 rounded-full border border-white/10 shadow-sm shrink-0" style={{ backgroundColor: chartColor.fail }}></span>
                <span>失败</span>
              </div>
              <div className="flex items-center gap-2 text-[var(--text-primary)]">
                <span className="size-2.5 rounded-full border border-white/10 shadow-sm shrink-0" style={{ backgroundColor: chartColor.block }}></span>
                <span>阻塞</span>
              </div>
              <div className="flex items-center gap-2 text-[var(--text-primary)]">
                <span className="size-2.5 rounded-full border border-white/10 shadow-sm shrink-0" style={{ backgroundColor: chartColor.unexec === 'var(--border-color)' ? '#8e9aaf' : chartColor.unexec }}></span>
                <span>其他</span>
              </div>
            </div>
          </div>

          {/* SVG 折线图 */}
          <div className="relative h-[160px] w-full mt-2">
            <svg className="w-full h-full" viewBox="0 0 520 160" preserveAspectRatio="none">
              {/* 背景格线 */}
              <line x1="40" y1="20" x2="500" y2="20" stroke="var(--border-color)" strokeWidth="0.8" strokeDasharray="3,3" />
              <line x1="40" y1="50" x2="500" y2="50" stroke="var(--border-color)" strokeWidth="0.8" strokeDasharray="3,3" />
              <line x1="40" y1="80" x2="500" y2="80" stroke="var(--border-color)" strokeWidth="0.8" strokeDasharray="3,3" />
              <line x1="40" y1="110" x2="500" y2="110" stroke="var(--border-color)" strokeWidth="0.8" strokeDasharray="3,3" />
              <line x1="40" y1="140" x2="500" y2="140" stroke="var(--border-color)" strokeWidth="1" />

              {/* 轴刻度 */}
              <text x="30" y="24" textAnchor="end" stroke="var(--bg-card)" strokeWidth="2.5" paintOrder="stroke fill" className="text-[11px] fill-current text-[var(--text-primary)] font-black">1.5K</text>
              <text x="30" y="54" textAnchor="end" stroke="var(--bg-card)" strokeWidth="2.5" paintOrder="stroke fill" className="text-[11px] fill-current text-[var(--text-primary)] font-black">1.2K</text>
              <text x="30" y="84" textAnchor="end" stroke="var(--bg-card)" strokeWidth="2.5" paintOrder="stroke fill" className="text-[11px] fill-current text-[var(--text-primary)] font-black">900</text>
              <text x="30" y="114" textAnchor="end" stroke="var(--bg-card)" strokeWidth="2.5" paintOrder="stroke fill" className="text-[11px] fill-current text-[var(--text-primary)] font-black">600</text>
              <text x="30" y="144" textAnchor="end" stroke="var(--bg-card)" strokeWidth="2.5" paintOrder="stroke fill" className="text-[11px] fill-current text-[var(--text-primary)] font-black">300</text>

              {Array.from({ length: 14 }).map((_, i) => {
                const x = 40 + i * (460 / 13);
                const day = String(7 + i).padStart(2, '0');
                return (
                  <text key={i} x={x} y="154" textAnchor="middle" stroke="var(--bg-card)" strokeWidth="2.5" paintOrder="stroke fill" className="text-[11px] fill-current text-[var(--text-primary)] font-black">
                    {day}
                  </text>
                );
              })}

              {/* 折线1：通过 (大厂主题色面积图) */}
              <path 
                d="M 40 85 L 75 75 L 110 65 L 145 68 L 180 50 L 215 62 L 250 50 L 285 58 L 320 48 L 355 52 L 390 42 L 425 45 L 460 55 L 500 45" 
                fill="none" stroke="var(--accent-color)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" className="path-drawn"
              />
              <path 
                d="M 40 85 L 75 75 L 110 65 L 145 68 L 180 50 L 215 62 L 250 50 L 285 58 L 320 48 L 355 52 L 390 42 L 425 45 L 460 55 L 500 45" 
                fill="none" stroke="var(--accent-color)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" className="svg-pulse-path"
                opacity="0.8"
              />
              <path
                d="M 40 85 L 75 75 L 110 65 L 145 68 L 180 50 L 215 62 L 250 50 L 285 58 L 320 48 L 355 52 L 390 42 L 425 45 L 460 55 L 500 45 L 500 140 L 40 140 Z"
                fill="url(#grad_dashboard_pass)" opacity="0.15"
              />
              <defs>
                <linearGradient id="grad_dashboard_pass" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="var(--accent-color)" />
                  <stop offset="100%" stopColor="var(--accent-color)" stopOpacity="0" />
                </linearGradient>
              </defs>
              {[
                [40, 85], [75, 75], [110, 65], [145, 68], [180, 50], [215, 62], 
                [250, 50], [285, 58], [320, 48], [355, 52], [390, 42], [425, 45], [460, 55], [500, 45]
              ].map(([cx, cy], i) => (
                <circle 
                  key={i} 
                  cx={cx} 
                  cy={cy} 
                  r="2.5" 
                  fill="var(--bg-card)" 
                  stroke="var(--accent-color)" 
                  strokeWidth="1.5" 
                  style={{
                    transformOrigin: `${cx}px ${cy}px`,
                    animation: 'scaleUpBounce 0.45s cubic-bezier(0.34, 1.56, 0.64, 1) forwards',
                    animationDelay: `${i * 60 + 300}ms`,
                    opacity: 0
                  }}
                />
              ))}
              {/* 最后一个通过点的雷达呼吸灯 */}
              <circle cx="500" cy="45" r="5" fill="var(--accent-color)" opacity="0.35" className="animate-ping" pointerEvents="none" />
              <circle cx="500" cy="45" r="3" fill="var(--accent-color)" opacity="0.15" className="telemetry-indicator-pulse" pointerEvents="none" />

              {/* 折线2：失败 */}
              <path 
                d="M 40 115 L 75 110 L 110 102 L 145 105 L 180 100 L 215 102 L 250 103 L 285 98 L 320 100 L 355 98 L 390 92 L 425 90 L 460 95 L 500 97" 
                fill="none" stroke={chartColor.fail} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="path-drawn"
              />
              <path 
                d="M 40 115 L 75 110 L 110 102 L 145 105 L 180 100 L 215 102 L 250 103 L 285 98 L 320 100 L 355 98 L 390 92 L 425 90 L 460 95 L 500 97" 
                fill="none" stroke={chartColor.fail} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="svg-pulse-path"
                opacity="0.8"
              />
              {[
                [40, 115], [75, 110], [110, 102], [145, 105], [180, 100], [215, 102], 
                [250, 103], [285, 98], [320, 100], [355, 98], [390, 92], [425, 90], [460, 95], [500, 97]
              ].map(([cx, cy], i) => (
                <circle 
                  key={i} 
                  cx={cx} 
                  cy={cy} 
                  r="2" 
                  fill="var(--bg-card)" 
                  stroke={chartColor.fail} 
                  strokeWidth="1.2" 
                  style={{
                    transformOrigin: `${cx}px ${cy}px`,
                    animation: 'scaleUpBounce 0.45s cubic-bezier(0.34, 1.56, 0.64, 1) forwards',
                    animationDelay: `${i * 60 + 500}ms`,
                    opacity: 0
                  }}
                />
              ))}
              {/* 最后一个失败点的雷达呼吸灯 */}
              <circle cx="500" cy="97" r="5" fill={chartColor.fail} opacity="0.35" className="animate-ping" pointerEvents="none" />
              <circle cx="500" cy="97" r="3" fill={chartColor.fail} opacity="0.15" className="telemetry-indicator-pulse" pointerEvents="none" />
            </svg>
          </div>
        </div>

        {/* 需求覆盖率 (圆环) */}
        <div className="col-span-3 theme-card rounded-xl p-4 shadow-sm flex flex-col justify-between min-h-[260px]">
          <div className="border-b border-[var(--border-color)] pb-2.5">
            <span className="text-xs font-bold text-[var(--text-primary)]">需求覆盖率</span>
          </div>

          <div className="flex items-center justify-between py-2.5">
            {/* SVG 圆环 - 动态绘制 */}
            <div className="relative size-[95px] shrink-0 sonar-ripple-container">
              <div className="sonar-ripple-circle"></div>
              <div className="sonar-ripple-circle sonar-ripple-circle-delay"></div>
              <svg className="w-full h-full transform -rotate-90 relative z-10" viewBox="0 0 36 36">
                <circle cx="18" cy="18" r="15.915" fill="none" stroke="var(--border-color)" strokeWidth="3" />
                <circle cx="18" cy="18" r="15.915" fill="none" stroke="#f59e0b" strokeWidth="3.2" 
                  strokeDasharray={`${(progressValue * 14.8) / 78.4} ${100 - (progressValue * 14.8) / 78.4}`} 
                  strokeDashoffset={-(progressValue * 78.4) / 78.4} 
                  className="transition-all duration-100 ease-out"
                />
                <circle cx="18" cy="18" r="15.915" fill="none" stroke="var(--accent-color)" strokeWidth="3.2" 
                  strokeDasharray={`${progressValue} ${100 - progressValue}`} 
                  strokeDashoffset="0" 
                  className="transition-all duration-100 ease-out"
                />
                <path d="M18,18 L18,2 A16,16 0 0,1 30,10 Z" fill="var(--accent-glow)" className="radar-sweeper-beam" />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center z-10">
                <span className="text-[13.5px] font-black leading-none text-[var(--text-primary)]">{progressValue}%</span>
                <span className="text-[8px] text-[var(--text-secondary)] opacity-60 mt-1 leading-none">已覆盖</span>
              </div>
            </div>

            {/* 右侧指标说明 - 联动滚动 */}
            <div className="flex-1 pl-3.5 space-y-2 text-[9px] font-bold text-[var(--text-primary)]">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="size-2 rounded-full shrink-0 bg-[var(--accent-color)] animate-pulse"></span>
                  <span className="opacity-80">已覆盖</span>
                </div>
                <span>{casesCount.covered} <span className="opacity-45 font-normal">({Math.round(progressValue)}%)</span></span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="size-2 rounded-full shrink-0 bg-[#f59e0b]"></span>
                  <span className="opacity-80">部分覆盖</span>
                </div>
                <span>{casesCount.partial} <span className="opacity-45 font-normal">(15%)</span></span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="size-2 rounded-full shrink-0 bg-[var(--border-color)]"></span>
                  <span className="opacity-80">未覆盖</span>
                </div>
                <span>{casesCount.uncovered} <span className="opacity-45 font-normal">(7%)</span></span>
              </div>
            </div>
          </div>

          <div className="border-t border-[var(--border-color)] pt-2 text-right">
            <span className="text-[9px] text-[var(--text-secondary)] opacity-50">需求总数：1,248</span>
          </div>
        </div>

        {/* 模块使用热力图 */}
        <div className="col-span-4 theme-card rounded-xl p-4 shadow-sm flex flex-col justify-between min-h-[260px]">
          <div className="border-b border-[var(--border-color)] pb-2.5 mb-2">
            <span className="text-xs font-black text-[var(--text-primary)]">模块使用热力图</span>
          </div>

          <div>
            {/* 十字列标题高亮 */}
            <div className="grid grid-cols-5 text-xs font-black text-center mb-2.5 py-1.5 rounded bg-[var(--border-color)]/40 text-[var(--text-primary)]">
              <div></div>
              {dimensions.map((dim, idx) => {
                const isColHovered = hoveredCol === idx;
                return (
                  <div 
                    key={idx} 
                    className={`transition-all duration-200 ${isColHovered ? 'text-[var(--accent-color)] scale-110 font-black' : 'opacity-80'}`}
                  >
                    {dim}
                  </div>
                );
              })}
            </div>

            {/* 热力网格容器，加装绝对定位纵向激光雷达扫描线 */}
            <div className="relative overflow-hidden rounded-lg p-0.5">
              <div className="absolute left-0 w-full h-[2.5px] bg-gradient-to-r from-transparent via-[var(--accent-color)] to-transparent pointer-events-none animate-scan-y z-10" />
              
              <div className="space-y-2 relative z-0">
                {modules.map((mod, rowIdx) => {
                  const isRowHovered = hoveredRow === rowIdx;
                  return (
                    <div key={rowIdx} className="grid grid-cols-5 items-center gap-1 text-center">
                      {/* 十字行标题高亮 */}
                      <span 
                        className={`text-[11px] font-black text-left truncate pr-1 transition-all duration-200 ${
                          isRowHovered 
                            ? 'text-[var(--accent-color)] scale-105 origin-left font-black translate-x-0.5' 
                            : 'text-[var(--text-primary)] opacity-85'
                        }`}
                      >
                        {mod}
                      </span>
                      {heatmapData[rowIdx].map((val, colIdx) => {
                        const getThemeRgb = (t) => {
                          switch (t) {
                            case 'clickhouse': return '234, 179, 8';
                            case 'brutalist': return '0, 0, 0';
                            case 'cyber-glass': return '6, 182, 212';
                            case 'dark': return '37, 99, 235';
                            case 'linear': return '92, 92, 214';
                            case 'editorial': return '28, 25, 23';
                            case 'ibm': return '15, 98, 254';
                            case 'airtable': return '37, 99, 235';
                            case 'notion': return '55, 53, 47';
                            default: return '79, 70, 229'; // basic
                          }
                        };
                        const rgb = getThemeRgb(theme);
                        const fillStyle = { backgroundColor: `rgba(${rgb}, ${0.12 + val * 0.19})` };
                        
                        // 部署多频波段闪烁
                        const pulseClass = val === 4 
                          ? 'heat-pulse-high' 
                          : val === 3 
                            ? 'heat-pulse-med' 
                            : val === 2 
                              ? 'heat-pulse-low' 
                              : '';

                        const isCurrentHovered = hoveredRow === rowIdx && hoveredCol === colIdx;

                        return (
                          <div 
                            key={colIdx} 
                            onMouseEnter={() => {
                              setHoveredRow(rowIdx);
                              setHoveredCol(colIdx);
                            }}
                            onMouseLeave={() => {
                              setHoveredRow(null);
                              setHoveredCol(null);
                            }}
                            style={{
                              ...fillStyle,
                              animation: 'scaleIn 0.35s cubic-bezier(0.34, 1.56, 0.64, 1) forwards',
                              animationDelay: `${(rowIdx * 4 + colIdx) * 16 + 120}ms`,
                              opacity: 0
                            }}
                            className={`h-4 rounded transition-all duration-200 transform cursor-pointer border border-[var(--border-color)]/60 ${pulseClass} ${
                              isCurrentHovered 
                                ? 'scale-125 border-[var(--accent-color)] shadow-[0_0_10px_var(--accent-glow)] z-20' 
                                : 'hover:scale-115'
                            }`}
                            title={`${mod} - ${dimensions[colIdx]}: 热度 ${val}`}
                          />
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* 滑轨能量流光 */}
          <div className="border-t border-[var(--border-color)] pt-2.5 flex items-center justify-between text-[10px] text-[var(--text-primary)] font-black">
            <div className="flex items-center gap-2">
              <span>低</span>
              <span className="w-20 h-2 rounded-full border border-[var(--border-color)] thermal-legend-flow" />
              <span>高</span>
            </div>
            <span className="text-[var(--text-secondary)] font-extrabold">需求总数：1,248</span>
          </div>
        </div>

      </div>

      {/* ======================== 第三排：细节与操作流 ======================== */}
      <div className="grid grid-cols-12 gap-5">
        
        {/* 最近活动 */}
        <div className="col-span-4 theme-card rounded-xl p-4 shadow-sm flex flex-col justify-between min-h-[300px]">
          <div className="border-b border-[var(--border-color)] pb-2.5 mb-3">
            <span className="text-xs font-bold text-[var(--text-primary)]">最近活动</span>
          </div>

          <div className="flex-1 space-y-3">
            {visibleActivities.map((act, idx) => {
              const Icon = act.icon;
              const statusClass = act.style.includes('emerald')
                ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/30'
                : act.style.includes('red')
                  ? 'text-red-600 dark:text-red-400 bg-red-500/10 border-red-500/30'
                  : 'text-blue-600 dark:text-blue-400 bg-blue-500/10 border-blue-500/30';

              return (
                <div 
                  key={act.id} 
                  className="flex gap-2.5 text-left items-start"
                  style={{
                    animation: 'slideUpFade 0.45s cubic-bezier(0.16, 1, 0.3, 1) forwards',
                    animationDelay: `${idx * 80 + 250}ms`,
                    opacity: 0
                  }}
                >
                  <div className={`p-2 rounded-full shrink-0 ${act.iconStyle} shadow-sm`}>
                    <Icon className="size-3.5" />
                  </div>
                  
                  <div className="flex-1 min-w-0 text-[var(--text-primary)]">
                    <div className="text-xs font-black truncate leading-snug">
                      {act.title}
                    </div>
                    <div className="text-[11px] text-[var(--text-secondary)] mt-1 truncate font-bold">
                      {act.desc}
                    </div>
                    <div className="flex items-center gap-2.5 mt-1 text-[10px] text-[var(--text-secondary)] font-extrabold">
                      <span>{act.time}</span>
                      <span>•</span>
                      <span>{act.user}</span>
                    </div>
                  </div>

                  <div className={`text-[10px] font-black border px-2 py-0.5 rounded shrink-0 shadow-sm ${statusClass}`}>
                    {act.tag}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="text-center pt-3 border-t border-[var(--border-color)] mt-3">
            <span 
              onClick={() => window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '正在加载历史活动日志...', type: 'info' } }))}
              className="text-[10px] font-bold hover:opacity-85 transition-all cursor-pointer text-[var(--accent-color)]"
            >
              查看全部活动 →
            </span>
          </div>
        </div>

        {/* 快速操作与项目健康度 */}
        <div className="col-span-4 flex flex-col gap-4">
          
          {/* 快速操作 */}
          <div className="theme-card rounded-xl p-4 shadow-sm">
            <div className="border-b border-[var(--border-color)] pb-2.5 mb-3">
              <span className="text-xs font-bold text-[var(--text-primary)]">快速操作</span>
            </div>
            
            <div className="grid grid-cols-3 gap-2">
              {quickActions.map((act, idx) => {
                const Icon = act.icon;
                return (
                  <button 
                    key={idx}
                    onClick={() => handleQuickAction(act)}
                    style={{
                      animation: 'slideUpFade 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards',
                      animationDelay: `${idx * 50 + 200}ms`,
                      opacity: 0
                    }}
                    className="quick-action-item flex flex-col items-center justify-center p-2.5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--border-color)]/30 text-[var(--text-primary)] text-center transition-all cursor-pointer hover:scale-[1.03] hover:border-[var(--accent-color)]/50 shadow-sm"
                  >
                    <Icon className="size-[15px] shrink-0 mb-1 transition-transform duration-200" style={{ color: 'var(--accent-color)' }} />
                    <span className="text-[9px] font-bold tracking-tight block truncate w-full">{act.title}</span>
                    <span className="text-[7.5px] font-normal opacity-50 mt-0.5 block truncate w-full scale-95 origin-center">{act.desc}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* 项目健康度 */}
          <div className="theme-card rounded-xl p-4 shadow-sm">
            <div className="border-b border-[var(--border-color)] pb-2.5 mb-3">
              <span className="text-xs font-bold text-[var(--text-primary)]">项目健康度</span>
            </div>

            <div className="grid grid-cols-4 gap-2 text-center text-[var(--text-primary)]">
              {healthMetrics.map((met, idx) => (
                <div 
                  key={met.label} 
                  style={{
                    animation: 'slideUpFade 0.45s cubic-bezier(0.16, 1, 0.3, 1) forwards',
                    animationDelay: `${idx * 80 + 350}ms`,
                    opacity: 0
                  }}
                  className="border border-[var(--border-color)] rounded-lg p-2 bg-[var(--border-color)]/20 flex flex-col justify-between min-h-[85px] shadow-sm"
                >
                  <div className="text-[8px] text-[var(--text-secondary)] font-bold truncate leading-tight">{met.label}</div>
                  <div className="mt-1 text-[11.5px] font-black">
                    <AnimatedNumber value={met.val} delay={idx * 60 + 300} />
                    {met.unit && <span className="text-[7px] font-normal opacity-45 ml-0.5 inline-block">{met.unit}</span>}
                  </div>
                  
                  {/* 微折线图 */}
                  <div className="h-6 w-full my-1.5">
                    <svg className="w-full h-full" viewBox="0 0 100 30" preserveAspectRatio="none">
                      <path 
                        d={met.linePath} 
                        fill="none" 
                        stroke="var(--accent-color)" 
                        strokeWidth="1.8" 
                        strokeLinecap="round" 
                        className="path-drawn"
                      />
                    </svg>
                  </div>
                  
                  <div className="text-[8px] font-bold text-emerald-500 leading-none">{met.change}</div>
                </div>
              ))}
            </div>
          </div>

        </div>

        {/* 测试执行与待办 */}
        <div className="col-span-4 flex flex-col gap-4">
          
          {/* 测试执行概览（今日） */}
          <div className="theme-card rounded-xl p-4 shadow-sm flex-1 flex flex-col justify-between min-h-[140px]">
            <div>
              <div className="border-b border-[var(--border-color)] pb-2.5 mb-2">
                <span className="text-xs font-black text-[var(--text-primary)]">测试执行概览（今日）</span>
              </div>

              <table className="w-full text-xs text-left border-collapse">
                <thead>
                  <tr className="border-b border-[var(--border-color)] text-[var(--text-primary)] font-black">
                    <th className="py-2 font-black text-[11.5px]">类型</th>
                    <th className="py-2 font-black text-center text-[11.5px]">计划数</th>
                    <th className="py-2 font-black text-center text-[11.5px]">通过数</th>
                    <th className="py-2 font-black text-center text-[11.5px]">失败数</th>
                    <th className="py-2 font-black text-center text-[11.5px]">通过率</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-color)] text-[var(--text-primary)] font-bold">
                  {executionOverview.map((row, idx) => (
                    <tr key={idx} className="hover:bg-[var(--border-color)]/20 transition-colors">
                      <td className="py-2 font-black">{row.type.substring(0, 5)}</td>
                      <td className="py-2 text-center">{row.plan}</td>
                      <td className="py-2 text-center font-black text-[var(--accent-color)]">{row.pass}</td>
                      <td className="py-2 text-center text-red-600 dark:text-red-400 font-black">{row.fail}</td>
                      <td className="py-2 text-center font-black text-[var(--accent-color)]">{row.rate}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* 待办事项 */}
          <div className="theme-card rounded-xl p-4 shadow-sm">
            <div className="flex justify-between items-center border-b border-[var(--border-color)] pb-2.5 mb-2.5 text-[var(--text-primary)]">
              <span className="text-xs font-black">待办事项</span>
              <span className="text-[11px] font-black text-[var(--text-secondary)]">待处理事项 6</span>
            </div>

            <div className="space-y-2 overflow-y-auto max-h-[120px]">
              {todos.map((todo, idx) => (
                <div key={idx} className="flex items-center justify-between gap-2.5 text-left text-xs py-2 border-b border-[var(--border-color)] last:border-b-0 text-[var(--text-primary)]">
                  <div className="flex items-center gap-2 min-w-0">
                    <input 
                      type="checkbox" 
                      className="rounded border-[var(--border-color)] text-blue-600 focus:ring-blue-500 size-3 shrink-0 cursor-pointer bg-transparent"
                      style={{ accentColor: 'var(--accent-color)' }}
                    />
                    <span className="font-bold truncate">{todo.text}</span>
                  </div>
                  <span className={`px-2 py-0.5 border text-[10px] font-black rounded shrink-0 shadow-sm ${todo.priorityColor}`}>
                    {todo.priority}
                  </span>
                </div>
              ))}
            </div>
          </div>

        </div>

      </div>

    </div>
  );
}
