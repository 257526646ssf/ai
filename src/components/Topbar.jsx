import React from 'react';
import { Bell, HelpCircle, ChevronDown, Sparkles } from 'lucide-react';

export default function Topbar({ activeTab, theme, setTheme }) {
  // 10种首页美学风格
  const themeOptions = [
    { id: 'basic', label: '01 基础雅致版' },
    { id: 'dark', label: '02 科技夜空深色版' },
    { id: 'editorial', label: '03 奢华编辑社论版' },
    { id: 'cyber-glass', label: '04 玻璃未来流光版' },
    { id: 'brutalist', label: '05 粗野工业硬核版' },
    { id: 'ibm', label: '06 IBM 经典蓝灰版' },
    { id: 'airtable', label: '07 Airtable 七彩网格版' },
    { id: 'clickhouse', label: '08 ClickHouse 黑黄版' },
    { id: 'notion', label: '09 Notion 极简灰白版' },
    { id: 'linear', label: '10 Linear 精密极黑版' },
  ];

  // 映射 Tab 标题
  const tabTitles = {
    dashboard: 'Dashboard',
    requirements: '需求库',
    testcases: '测试用例库',
    execution: '用例执行',
    apitesting: '接口测试',
    automation: '自动化中心',
    performance: '性能测试',
    reports: '测试报告中心',
    llmconfig: 'LLM 配置',
    settings: '系统设置',
  };

  const currentThemeLabel = themeOptions.find(o => o.id === theme)?.label || '01 基础雅致版';

  return (
    <header className="h-[56px] bg-[var(--bg-card)] border-b border-[var(--border-color)] flowing-laser-wire text-[var(--text-primary)] px-6 flex items-center justify-between sticky top-0 z-40 select-none shrink-0 shadow-[0_1px_3px_rgba(0,0,0,0.01)] transition-colors duration-300">
      {/* 左侧：页面标题 */}
      <div className="flex items-center gap-3">
        <span className="text-xs text-[var(--text-secondary)] font-extrabold">
          {activeTab === 'dashboard' ? '平台首页' : tabTitles[activeTab] || 'Dashboard'}
        </span>
        <span className="text-[var(--text-secondary)] opacity-55 text-xs font-black">/</span>
        <span className="text-sm font-black text-[var(--text-primary)] tracking-wide">
          {activeTab === 'dashboard' ? 'Dashboard' : tabTitles[activeTab] || 'Dashboard'}
        </span>
      </div>

      {/* 右侧：功能按钮与用户信息 */}
      <div className="flex items-center gap-4">
        {/* 核心：10 套全站风格秒切换器 */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--border-color)]/40 text-xs font-black text-[var(--text-primary)] hover:bg-[var(--border-color)]/60 cursor-pointer relative group z-50 transition-all shadow-sm">
          <Sparkles className="size-3.5 text-amber-500 animate-pulse" />
          <span>
            风格选择: <strong className="text-[var(--accent-color)] font-black underline decoration-2">{currentThemeLabel}</strong>
          </span>
          <ChevronDown className="size-3.5 text-[var(--text-secondary)] font-black" />
          
          {/* 下拉面板容器 - pt-2 提供了透明的保护垫片，防止鼠标移动时 hover 状态丢失 */}
          <div className="absolute top-full right-0 pt-2 w-60 hidden group-hover:block z-50">
            <div className="rounded-xl bg-[var(--bg-card)] border border-[var(--border-color)] shadow-xl p-1.5">
              <div className="text-[10px] font-black text-[var(--text-secondary)] uppercase px-2.5 py-1.5 border-b border-[var(--border-color)] mb-1 select-none">
                美学风格决策中心
              </div>
              {themeOptions.map((opt) => (
                <button
                  key={opt.id}
                  onClick={() => setTheme(opt.id)}
                  className={`w-full text-left px-2.5 py-2 rounded-lg text-xs font-black transition-colors ${
                    opt.id === theme 
                      ? 'bg-[var(--accent-glow)] text-[var(--accent-color)] font-black' 
                      : 'text-[var(--text-secondary)] hover:bg-[var(--border-color)]/50 hover:text-[var(--text-primary)]'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* LLM 状态 */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--border-color)]/40 text-xs font-black text-[var(--text-secondary)]">
          <span>LLM 状态</span>
          <span className="flex items-center gap-1.5 font-black text-[var(--text-primary)]">
            <span className="relative flex size-2 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full size-2 bg-emerald-500"></span>
            </span>
            已连接
          </span>
        </div>

        {/* 模型显示 */}
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-[var(--border-color)]/40 text-xs font-black text-[var(--text-primary)] hover:bg-[var(--border-color)]/60 cursor-pointer transition-all shadow-sm">
          <span>OpenAI GPT-4o</span>
          <ChevronDown className="size-3 text-[var(--text-secondary)] font-black" />
        </div>

        {/* 消息与帮助 */}
        <div className="flex items-center gap-3 text-slate-400">
          <button className="relative hover:text-slate-600 transition-colors">
            <Bell className="size-[16px]" />
            <span className="absolute top-0 right-0 size-[5px] bg-red-500 rounded-full border border-white"></span>
          </button>
          <button className="hover:text-slate-600 transition-colors">
            <HelpCircle className="size-[16px]" />
          </button>
        </div>

        <div className="h-6 w-px bg-slate-100"></div>

        {/* 负责人头像 */}
        <div className="flex items-center gap-2.5">
          <img 
            src="/avatar_zhang.png" 
            alt="张明" 
            className="size-[32px] rounded-full object-cover border border-slate-100 shadow-sm"
            onError={(e) => {
              e.target.src = "https://ui-avatars.com/api/?name=%E5%BC%A0%E6%98%8E&background=2563eb&color=fff";
            }}
          />
          <div className="flex flex-col text-left">
            <span className="text-xs font-black text-[var(--text-primary)] leading-tight">张明</span>
            <span className="text-[11px] text-[var(--text-secondary)] font-extrabold mt-0.5 leading-none">测试负责人</span>
          </div>
        </div>
      </div>
    </header>
  );
}
