import React, { useState } from 'react';
import { 
  Home, 
  Folder, 
  CheckSquare, 
  PlayCircle, 
  Network, 
  Cpu, 
  Gauge, 
  FileText, 
  Settings2,
  Settings,
  ChevronDown,
  ChevronRight,
  Menu
} from 'lucide-react';

export default function Navigation({ activeTab, setActiveTab }) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  const menuItems = [
    { id: 'dashboard', label: 'Dashboard', icon: Home },
    { id: 'requirements', label: '需求库', icon: Folder },
    { id: 'testcases', label: '测试用例库', icon: CheckSquare },
    { id: 'execution', label: '用例执行', icon: PlayCircle },
    { id: 'apitesting', label: '接口测试', icon: Network },
    { id: 'automation', label: '自动化中心', icon: Cpu },
    { id: 'performance', label: '性能测试', icon: Gauge },
    { id: 'reports', label: '测试报告', icon: FileText },
    { id: 'llmconfig', label: 'LLM 配置', icon: Settings2 },
  ];

  return (
    <aside 
      className={`bg-[var(--bg-card)] border-r border-[var(--border-color)] flex flex-col justify-between select-none h-screen sticky top-0 shrink-0 transition-all duration-300 z-50 ${
        isCollapsed ? 'w-[64px]' : 'w-[220px]'
      }`}
      style={{
        boxShadow: 'var(--shadow-style)'
      }}
    >
      {/* 顶部 Logo 区域 */}
      <div>
        <div className="p-4 flex items-center justify-between border-b border-[var(--border-color)]">
          {!isCollapsed && (
            <div className="flex items-center gap-2.5">
              <div className="relative size-6 shrink-0 flex items-center justify-center bg-[var(--accent-color)] rounded-md shadow-sm transition-all duration-300">
                <div className="absolute inset-1.5 border-[1.5px] border-white opacity-40 rounded-sm transform -translate-x-0.5 -translate-y-0.5"></div>
                <div className="absolute inset-1.5 border-[1.5px] border-white rounded-sm bg-[var(--accent-color)]"></div>
              </div>
              <span className="font-bold text-[var(--text-primary)] text-[14px] tracking-tight">AI 测试平台</span>
            </div>
          )}
          
          {/* 折叠开关 */}
          <button 
            onClick={() => setIsCollapsed(!isCollapsed)}
            className={`text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors mx-auto p-1.5 rounded hover:bg-[var(--border-color)]/50 cursor-pointer ${isCollapsed ? 'block' : ''}`}
          >
            <Menu className="size-[16px]" />
          </button>
        </div>

        {/* 菜单列表 */}
        <nav className="px-2 py-4 space-y-1 relative">
          {menuItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                title={isCollapsed ? item.label : undefined}
                className={`relative w-full flex items-center rounded-lg text-xs font-black transition-all duration-250 py-3.5 overflow-hidden cursor-pointer ${
                  isCollapsed ? 'justify-center px-0' : 'pl-6 pr-4 gap-3'
                } ${
                  isActive 
                    ? 'sidebar-active-glow text-[var(--text-primary)] font-black shadow-md' 
                    : 'text-[var(--text-secondary)] hover:bg-[var(--border-color)]/40 hover:text-[var(--text-primary)] font-bold'
                }`}
              >
                {/* 侧边左侧高亮拉伸指示条 (带重点色呼吸发光效果) */}
                <div 
                  className={`absolute left-0 top-1/2 -translate-y-1/2 w-[3.5px] rounded-r bg-[var(--accent-color)] transition-all duration-300 ${
                    isActive 
                      ? 'h-[60%] opacity-100 shadow-[0_0_10px_var(--accent-color)]' 
                      : 'h-0 opacity-0'
                  }`}
                />

                {/* 折叠模式下的外圈呼吸呼吸框 */}
                {isCollapsed && isActive && (
                  <div className="absolute inset-1.5 rounded-lg border border-[var(--accent-color)]/30 bg-[var(--accent-glow)] -z-10 animate-pulse" />
                )}

                <Icon 
                  className={`size-[17px] shrink-0 transition-all duration-200 ${
                    isActive 
                      ? 'text-[var(--accent-color)] scale-110 drop-shadow-[0_0_6px_var(--accent-glow)]' 
                      : 'text-[var(--text-secondary)] hover:scale-105'
                  }`} 
                />
                {!isCollapsed && (
                  <span className="transition-transform duration-200 origin-left">
                    {item.label}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* 底部项目选择器 & 系统设置 */}
      <div className="p-2 border-t border-[var(--border-color)] space-y-2">
        {/* 当前项目 */}
        {!isCollapsed ? (
          <div className="bg-[var(--border-color)]/40 border border-[var(--border-color)] rounded-lg p-2.5 transition-all">
            <div className="text-[10px] text-[var(--text-secondary)] font-black mb-1">当前项目</div>
            <button className="w-full flex items-center justify-between text-left cursor-pointer">
              <span className="text-xs font-black text-[var(--text-primary)] truncate">AI 测试演示项目</span>
              <ChevronDown className="size-3 text-[var(--text-secondary)] shrink-0 font-bold" />
            </button>
          </div>
        ) : (
          <div className="flex justify-center py-1.5">
            <div className="size-2.5 rounded-full bg-[var(--accent-color)] animate-ping" title="AI 测试演示项目"></div>
          </div>
        )}

        {/* 系统设置 */}
        <button 
          onClick={() => setActiveTab('settings')}
          className={`relative w-full flex items-center justify-between rounded-lg text-xs transition-all py-3 cursor-pointer ${
            isCollapsed ? 'justify-center px-0' : 'pl-5 pr-3'
          } ${
            activeTab === 'settings' 
              ? 'sidebar-active-glow text-[var(--text-primary)] font-black shadow-md' 
              : 'text-[var(--text-secondary)] hover:bg-[var(--border-color)]/40 hover:text-[var(--text-primary)] font-bold'
          }`}
        >
          {activeTab === 'settings' && (
            <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3.5px] h-[60%] rounded-r bg-[var(--accent-color)] shadow-[0_0_10px_var(--accent-color)]" />
          )}
          {isCollapsed && activeTab === 'settings' && (
            <div className="absolute inset-1.5 rounded-lg border border-[var(--accent-color)]/30 bg-[var(--accent-glow)] -z-10 animate-pulse" />
          )}

          <div className="flex items-center gap-2.5">
            <Settings 
              className={`size-[15px] transition-all ${
                activeTab === 'settings' 
                  ? 'text-[var(--accent-color)] scale-110 drop-shadow-[0_0_6px_var(--accent-glow)]' 
                  : 'text-[var(--text-secondary)]'
              }`} 
            />
            {!isCollapsed && <span>系统设置</span>}
          </div>
          {!isCollapsed && <ChevronRight className="size-3 text-[var(--text-secondary)] font-bold" />}
        </button>
      </div>
    </aside>
  );
}
