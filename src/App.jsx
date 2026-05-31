import React, { useEffect, useState } from 'react';
import { Bot } from 'lucide-react';
import Navigation from './components/Navigation';
import Topbar from './components/Topbar';
import AiAssistant from './components/AiAssistant';
import Toast from './components/Toast';
import GlobalModal from './components/GlobalModal';
import InteractiveBackground from './components/InteractiveBackground';
import { ProjectProvider } from './lib/projectContext';
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
    console.error('Runtime Error Captured by Boundary:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            padding: '30px',
            color: '#e11d48',
            background: '#fff1f2',
            border: '2px solid #fda4af',
            zIndex: 999999,
            position: 'fixed',
            inset: 0,
            overflow: 'auto',
            fontFamily: 'monospace',
            textAlign: 'left'
          }}
        >
          <h2 style={{ fontSize: '20px', fontWeight: 'bold', marginBottom: '15px' }}>
            系统前端运行时错误
          </h2>
          <p style={{ fontSize: '13px', fontWeight: 'bold' }}>
            请截图或将下面的错误堆栈提供给 AI 助手继续诊断。
          </p>
          <pre
            style={{
              whiteSpace: 'pre-wrap',
              background: '#fff',
              padding: '15px',
              borderRadius: '8px',
              border: '1px solid #fecdd3',
              marginTop: '10px',
              fontSize: '12px',
              color: '#334155'
            }}
          >
            {this.state.error && this.state.error.stack}
          </pre>
        </div>
      );
    }

    return this.props.children;
  }
}

const renderPageByTab = (activeTab, dashboardTheme) => {
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

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [dashboardTheme, setDashboardTheme] = useState('basic');
  const [isAiOpen, setIsAiOpen] = useState(false);

  useEffect(() => {
    const handleOpenAiChat = () => {
      setIsAiOpen(true);
    };

    window.addEventListener('open-ai-chat', handleOpenAiChat);

    return () => {
      window.removeEventListener('open-ai-chat', handleOpenAiChat);
    };
  }, []);

  return (
    <ErrorBoundary>
      <ProjectProvider>
        <div
          className="app-shell grid-bg relative font-sans transition-colors duration-300"
          style={{
            backgroundColor: 'var(--bg-app)',
            color: 'var(--text-primary)'
          }}
          data-theme={dashboardTheme}
        >
          <div className="app-shell__background" aria-hidden="true">
            <div
              className="absolute left-[-10%] top-[-12%] h-[34rem] w-[34rem] bg-[var(--accent-color)] aurora-blob"
              style={{ animation: 'floatBlob1 28s infinite linear' }}
            />
            <div
              className="absolute bottom-[-16%] right-[-10%] h-[38rem] w-[38rem] bg-[var(--accent-color)] aurora-blob"
              style={{ animation: 'floatBlob2 34s infinite linear', filter: 'hue-rotate(55deg) blur(150px)' }}
            />
            <div
              className="absolute left-[30%] top-[18%] h-[28rem] w-[28rem] bg-[var(--accent-color)] aurora-blob"
              style={{ animation: 'floatBlob3 24s infinite ease-in-out', filter: 'hue-rotate(-35deg) blur(160px)' }}
            />
            <InteractiveBackground />
          </div>

          <div className="app-shell__layout">
            <Navigation activeTab={activeTab} setActiveTab={setActiveTab} />

            <div className="app-shell__body">
              <Topbar
                activeTab={activeTab}
                theme={dashboardTheme}
                setTheme={setDashboardTheme}
                setActiveTab={setActiveTab}
              />

              <main className="app-shell__content">
                <div className="app-shell__content-inner">
                  {renderPageByTab(activeTab, dashboardTheme)}
                </div>
              </main>
            </div>
          </div>

          <AiAssistant
            activeTab={activeTab}
            isOpen={isAiOpen}
            onClose={() => setIsAiOpen(false)}
          />

          <Toast />
          <GlobalModal setActiveTab={setActiveTab} />

          {!isAiOpen && (
            <div className="fixed bottom-5 right-5 z-40 flex items-center gap-2.5">
              <div className="hidden rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] px-3 py-2 text-xs font-semibold text-[var(--text-primary)] shadow-sm backdrop-blur sm:flex">
                AI 助手已就绪
              </div>
              <button
                type="button"
                onClick={() => setIsAiOpen(true)}
                className="accent-btn flex size-11 items-center justify-center rounded-xl border border-white/10 shadow-lg"
                aria-label="打开 AI 助手"
              >
                <Bot className="size-[18px]" />
              </button>
            </div>
          )}
        </div>
      </ProjectProvider>
    </ErrorBoundary>
  );
}
