import React, { useState } from 'react';
import Navigation from './components/Navigation';
import Topbar from './components/Topbar';
import AiAssistant from './components/AiAssistant';
import Toast from './components/Toast';
import GlobalModal from './components/GlobalModal';
import InteractiveBackground from './components/InteractiveBackground';
import { Bot } from 'lucide-react';
import { ProjectProvider } from './lib/projectContext';

// 导入子页面
import Dashboard from './pages/Dashboard';
import Requirements from './pages/Requirements';
import TestCases from './pages/TestCases';
import Execution from './pages/Execution';
import ApiTesting from './pages/ApiTesting';
import Automation from './pages/Automation';
import Performance from './pages/Performance';
import Reports from './pages/Reports';
import LlmConfig from './pages/LlmConfig';
import SettingsPage from './pages/SettingsPage';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, errorInfo) {
    console.error("Runtime Error Captured by Boundary:", error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '30px', color: '#e11d48', background: '#fff1f2', border: '2px solid #fda4af', zIndex: 999999, position: 'fixed', inset: 0, overflow: 'auto', fontFamily: 'monospace', textAlign: 'left' }}>
          <h2 style={{ fontSize: '20px', fontWeight: 'bold', marginBottom: '15px' }}>🚨 系统前端渲染崩溃 (Runtime Error)</h2>
          <p style={{ fontSize: '13px', fontWeight: 'bold' }}>请截图或将下方错误堆栈提供给 AI 助手进行诊断：</p>
          <pre style={{ whiteSpace: 'pre-wrap', background: '#fff', padding: '15px', borderRadius: '8px', border: '1px solid #fecdd3', marginTop: '10px', fontSize: '12px', color: '#334155' }}>
            {this.state.error && this.state.error.stack}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [dashboardTheme, setDashboardTheme] = useState('basic'); // 默认基础风格
  const [isAiOpen, setIsAiOpen] = useState(false);

  React.useEffect(() => {
    const handleOpenAiChat = () => {
      setIsAiOpen(true);
    };
    window.addEventListener('open-ai-chat', handleOpenAiChat);
    return () => {
      window.removeEventListener('open-ai-chat', handleOpenAiChat);
    };
  }, []);

  // 渲染子模块
  const renderPage = () => {
    switch (activeTab) {
      case 'dashboard':
        return <Dashboard theme={dashboardTheme} />;
      case 'requirements':
        return <Requirements />;
      case 'testcases':
        return <TestCases />;
      case 'execution':
        return <Execution />;
      case 'apitesting':
        return <ApiTesting />;
      case 'automation':
        return <Automation />;
      case 'performance':
        return <Performance />;
      case 'reports':
        return <Reports />;
      case 'llmconfig':
        return <LlmConfig />;
      case 'settings':
        return <SettingsPage />;
      default:
        return <Dashboard theme={dashboardTheme} />;
    }
  };

  return (
    <ErrorBoundary>
      <ProjectProvider>
      <div 
        className="min-h-screen flex font-sans transition-colors duration-300 relative grid-bg overflow-hidden"
        style={{
          backgroundColor: 'var(--bg-app)',
          color: 'var(--text-primary)'
        }}
        data-theme={dashboardTheme}
      >
      {/* 沉醉流光弥散极光背景 (自适应多色相极光气泡) */}
      <div className="absolute top-[-15%] left-[-15%] w-[55vw] h-[55vw] bg-[var(--accent-color)] aurora-blob" style={{ animation: 'floatBlob1 24s infinite linear' }}></div>
      <div className="absolute bottom-[-20%] right-[-15%] w-[60vw] h-[60vw] bg-[var(--accent-color)] aurora-blob" style={{ animation: 'floatBlob2 30s infinite linear', filter: 'hue-rotate(60deg) blur(150px)' }}></div>
      <div className="absolute top-[25%] left-[30%] w-[45vw] h-[45vw] bg-[var(--accent-color)] aurora-blob" style={{ animation: 'floatBlob3 20s infinite ease-in-out', filter: 'hue-rotate(-45deg) blur(160px)' }}></div>
      <InteractiveBackground />

      {/* 左侧固定侧边栏 */}
      <Navigation activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* 右侧主区域 */}
      <div className="flex-1 flex flex-col min-w-0 h-screen">
        {/* 顶部栏 */}
        <Topbar 
          activeTab={activeTab} 
          theme={dashboardTheme} 
          setTheme={setDashboardTheme} 
          setActiveTab={setActiveTab}
        />

        {/* 页面主工作区 */}
        <main className="flex-1 p-5 overflow-y-auto w-full min-w-0">
          {renderPage()}
        </main>
      </div>

      {/* AI 助手侧边栏 */}
      <AiAssistant 
        activeTab={activeTab} 
        isOpen={isAiOpen} 
        onClose={() => setIsAiOpen(false)} 
      />

      {/* 全局 Toast 通知 */}
      <Toast />

      {/* 全局业务模态框 */}
      <GlobalModal setActiveTab={setActiveTab} />

      {/* 右下角全局 AI 助手悬浮球 */}
      {!isAiOpen && (
        <div className="fixed bottom-6 right-6 flex items-center gap-2.5 z-40 select-none pointer-events-auto animate-[fadeIn_0.3s_ease-out]">
          <div className="bg-[var(--bg-card)] border border-[var(--border-color)] shadow-xl rounded-xl py-1.5 px-3 text-[10px] font-bold text-[var(--text-primary)] animate-bounce select-none">
            AI 测试大脑已就绪
          </div>
          <button 
            onClick={() => setIsAiOpen(true)}
            className="size-11 accent-btn rounded-full hover:scale-110 transition-all border border-white/10 flex items-center justify-center shadow-lg"
          >
            <Bot className="size-[19px]" />
          </button>
        </div>
      )}
      </div>
      </ProjectProvider>
    </ErrorBoundary>
  );
}
