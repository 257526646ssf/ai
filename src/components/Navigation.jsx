import React, { useEffect, useState } from 'react';
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

const menuItems = [
  { id: 'dashboard', label: 'Dashboard', icon: Home },
  { id: 'requirements', label: '需求库', icon: Folder },
  { id: 'testcases', label: '测试用例', icon: CheckSquare },
  { id: 'execution', label: '用例执行', icon: PlayCircle },
  { id: 'apitesting', label: '接口测试', icon: Network },
  { id: 'automation', label: '自动化中心', icon: Cpu },
  { id: 'performance', label: '性能测试', icon: Gauge },
  { id: 'reports', label: '测试报告', icon: FileText },
  { id: 'llmconfig', label: 'LLM 配置', icon: Settings2 }
];

const baseItemClass =
  'group relative flex w-full min-w-0 items-center rounded-xl text-left text-sm transition-colors duration-200';

export default function Navigation({ activeTab, setActiveTab, isMobileOpen = false, onCloseMobile }) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  useEffect(() => {
    const closeOnDesktop = () => {
      if (window.innerWidth >= 1024) {
        onCloseMobile?.();
      }
    };
    closeOnDesktop();
    window.addEventListener('resize', closeOnDesktop);
    return () => window.removeEventListener('resize', closeOnDesktop);
  }, [onCloseMobile]);

  const renderItem = (item) => {
    const Icon = item.icon;
    const isActive = activeTab === item.id;

    return (
      <button
        key={item.id}
        type="button"
        onClick={() => {
          setActiveTab(item.id);
          onCloseMobile?.();
        }}
        title={isCollapsed ? item.label : undefined}
        className={[
          baseItemClass,
          isCollapsed ? 'justify-center px-0 py-3.5' : 'gap-3 px-3.5 py-3',
          isActive
            ? 'sidebar-active-glow text-[var(--text-primary)]'
            : 'text-[var(--text-secondary)] hover:bg-[var(--border-color)]/45 hover:text-[var(--text-primary)]'
        ].join(' ')}
      >
        <Icon
          className={[
            'shrink-0 transition-colors duration-200',
            isCollapsed ? 'size-[18px]' : 'size-[17px]',
            isActive ? 'text-[var(--accent-color)]' : 'text-[var(--text-secondary)] group-hover:text-[var(--text-primary)]'
          ].join(' ')}
        />
        {!isCollapsed && <span className="min-w-0 truncate font-semibold">{item.label}</span>}
      </button>
    );
  };

  return (
    <aside
      className={[
        'fixed inset-y-0 left-0 z-30 flex h-[100dvh] max-w-[86vw] flex-col justify-between border-r border-[var(--border-color)] bg-[var(--bg-card)] backdrop-blur transition-transform duration-200 lg:sticky lg:max-w-none lg:translate-x-0 lg:transition-[width] lg:duration-200',
        isMobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        isCollapsed ? 'lg:w-[72px]' : 'w-[232px]'
      ].join(' ')}
      style={{ boxShadow: 'var(--shadow-style)' }}
    >
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-center justify-between gap-3 border-b border-[var(--border-color)] px-3 py-3.5">
          {!isCollapsed ? (
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-[var(--border-color)] bg-[var(--bg-app)] text-[var(--accent-color)]">
                <div className="size-3 rounded-[4px] bg-[var(--accent-color)]" />
              </div>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-[var(--text-primary)]">AI 测试平台</div>
                <div className="truncate text-xs text-[var(--text-secondary)]">Workspace</div>
              </div>
            </div>
          ) : (
            <div className="mx-auto flex size-9 items-center justify-center rounded-xl border border-[var(--border-color)] bg-[var(--bg-app)] text-[var(--accent-color)]">
              <div className="size-3 rounded-[4px] bg-[var(--accent-color)]" />
            </div>
          )}

          <button
            type="button"
            onClick={() => setIsCollapsed((prev) => !prev)}
            className="flex size-9 shrink-0 items-center justify-center rounded-lg text-[var(--text-secondary)] transition-colors hover:bg-[var(--border-color)]/45 hover:text-[var(--text-primary)]"
            aria-label={isCollapsed ? '展开导航' : '收起导航'}
          >
            <Menu className="size-4" />
          </button>
        </div>

        <nav className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto px-3 py-4">
          {menuItems.map(renderItem)}
        </nav>
      </div>

      <div className="border-t border-[var(--border-color)] px-3 py-3">
        {!isCollapsed ? (
          <div className="mb-2 rounded-xl border border-[var(--border-color)] bg-[var(--bg-app)] px-3 py-2.5">
            <div className="mb-1 text-[11px] font-medium text-[var(--text-secondary)]">当前项目</div>
            <button
              type="button"
              className="flex w-full items-center justify-between gap-2 text-left text-sm font-semibold text-[var(--text-primary)]"
            >
              <span className="truncate">AI 测试演示项目</span>
              <ChevronDown className="size-4 shrink-0 text-[var(--text-secondary)]" />
            </button>
          </div>
        ) : (
          <div className="mb-2 flex justify-center">
            <span className="inline-flex size-2.5 rounded-full bg-[var(--accent-color)]" title="当前项目" />
          </div>
        )}

        <button
          type="button"
          onClick={() => setActiveTab('settings')}
          title={isCollapsed ? '系统设置' : undefined}
          className={[
            baseItemClass,
            isCollapsed ? 'justify-center px-0 py-3.5' : 'justify-between gap-3 px-3.5 py-3',
            activeTab === 'settings'
              ? 'sidebar-active-glow text-[var(--text-primary)]'
              : 'text-[var(--text-secondary)] hover:bg-[var(--border-color)]/45 hover:text-[var(--text-primary)]'
          ].join(' ')}
        >
          <div className={['flex min-w-0 items-center', isCollapsed ? 'justify-center' : 'gap-3'].join(' ')}>
            <Settings
              className={[
                'shrink-0 transition-colors duration-200',
                isCollapsed ? 'size-[18px]' : 'size-[17px]',
                activeTab === 'settings' ? 'text-[var(--accent-color)]' : 'text-[var(--text-secondary)]'
              ].join(' ')}
            />
            {!isCollapsed && <span className="truncate font-semibold">系统设置</span>}
          </div>
          {!isCollapsed && <ChevronRight className="size-4 shrink-0 text-[var(--text-secondary)]" />}
        </button>
      </div>
    </aside>
  );
}
