import React, { useState, useEffect, useRef } from 'react';
import { 
  X, 
  Upload, 
  Sparkles, 
  Play, 
  FileText, 
  CheckCircle, 
  Loader2, 
  Terminal,
  Database,
  Check,
  AlertTriangle,
  FileCheck
} from 'lucide-react';

export default function GlobalModal({ setActiveTab }) {
  const [modalState, setModalState] = useState({ isOpen: false, type: null, data: null });
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [logs, setLogs] = useState([]);
  const [files, setFiles] = useState([]);
  
  // 表单数据 (新建用例)
  const [newCaseData, setNewCaseData] = useState({
    title: '',
    priority: 'P0',
    type: '功能测试',
    ref: 'REQ-00004'
  });

  const logEndRef = useRef(null);

  useEffect(() => {
    const handleOpenModal = (e) => {
      const { type, data } = e.detail || {};
      setModalState({ isOpen: true, type, data });
      setLoading(false);
      setProgress(0);
      setLogs([]);
      setFiles([]);
      // 重置新建用例表单
      if (type === 'new-case') {
        setNewCaseData({
          title: '',
          priority: 'P0',
          type: '功能测试',
          ref: data?.reqId || 'REQ-00004'
        });
      }
    };

    window.addEventListener('open-modal', handleOpenModal);
    return () => {
      window.removeEventListener('open-modal', handleOpenModal);
    };
  }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const closeModal = () => {
    setModalState({ isOpen: false, type: null, data: null });
  };

  const addLog = (text, delay) => {
    return new Promise((resolve) => {
      setTimeout(() => {
        setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${text}`]);
        resolve();
      }, delay);
    });
  };

  // ======================== 逻辑：上传需求并解析 ========================
  const handleUploadAndParse = async () => {
    if (files.length === 0) {
      window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '请先选择要上传的文档', type: 'warning' } }));
      return;
    }
    setLoading(true);
    setProgress(10);
    
    await addLog("开始连接 AI 需求解析引擎...", 300);
    setProgress(30);
    await addLog(`读取文档: ${files[0].name} (${(files[0].size / 1024 / 1024).toFixed(2)} MB)`, 500);
    setProgress(50);
    await addLog("正在抽取需求核心意图与实体...", 600);
    setProgress(75);
    await addLog("分析业务流程节点及异常分支...", 500);
    setProgress(90);
    await addLog("正在构建需求追溯拓扑关系图...", 600);
    setProgress(100);
    await addLog("需求解析全部完成！共提取 8 个关键测试点，已建立 4 条关联链。", 300);

    setLoading(false);
    window.dispatchEvent(new CustomEvent('show-toast', { 
      detail: { message: `《${files[0].name}》解析成功，已导入需求库！`, type: 'success' } 
    }));
    closeModal();
  };

  // ======================== 逻辑：AI 智能生成用例 ========================
  const handleAiGenerateCases = async () => {
    setLoading(true);
    
    await addLog("启动 GPT-4o 智能用例模型...", 200);
    await addLog("分析关联需求项: REQ-001.1 用户登录与认证", 300);
    await addLog("装载生成策略: 标准覆盖 + 边界值校验", 400);
    await addLog("正在提取测试因子：账户长度、格式、敏感词、重试次数", 400);
    await addLog("AI 正在编写用例 1: 正确账号密码登录...", 200);
    await addLog("AI 正在编写用例 2: 输入错误密码时提示错误...", 150);
    await addLog("AI 正在编写用例 3: 连续错误登录 5 次后账号锁定 (异常边界)...", 180);
    await addLog("AI 正在编写用例 4: 未输入账号密码时登录按钮置灰...", 120);
    await addLog("正在对生成的用例进行智能评审与去重...", 300);
    await addLog("智能评审完成，用例覆盖率质量评分: 92/100 (优质)", 200);
    await addLog("正在保存到用例库数据库...", 300);
    await addLog("用例导入完成！已成功写入 4 个功能/异常测试用例。", 100);

    setLoading(false);
    
    // 派发事件：通知用例库追加新生成的用例
    window.dispatchEvent(new CustomEvent('cases-generated', {
      detail: {
        cases: [
          { id: 'TC-AI-001', title: '【AI生成】使用正确的账号密码进行登录验证', priority: 'P0', type: '功能测试', ref: 'REQ-001.1', status: '已通过', color: 'text-emerald-500 bg-emerald-50 border-emerald-100' },
          { id: 'TC-AI-002', title: '【AI生成】密码输入框包含特殊字符SQL注入校验', priority: 'P1', type: '安全测试', ref: 'REQ-001.3', status: '待评审', color: 'text-amber-500 bg-amber-50 border-amber-100' },
          { id: 'TC-AI-003', title: '【AI生成】用户名输入超长字符(255位)边界测试', priority: 'P2', type: '异常测试', ref: 'REQ-001.1', status: '待评审', color: 'text-amber-500 bg-amber-50 border-amber-100' },
          { id: 'TC-AI-004', title: '【AI生成】断网状态下点击登录按钮的友好错误反馈', priority: 'P1', type: '界面测试', ref: 'REQ-001.4', status: '已通过', color: 'text-emerald-500 bg-emerald-50 border-emerald-100' },
        ]
      }
    }));

    window.dispatchEvent(new CustomEvent('show-toast', { 
      detail: { message: 'AI 成功生成并导入 4 个测试用例！', type: 'success' } 
    }));
    closeModal();
  };

  // ======================== 逻辑：接口请求发送 ========================
  const handleSendApiRequest = async () => {
    setLoading(true);
    await addLog("正在解析请求配置...", 100);
    await addLog("正在解析参数、头部和 JSON 载荷...", 150);
    await addLog("正在建立 TCP 连接并执行 TLS 握手 (http://localhost:3000)...", 300);
    await addLog("发送 HTTP POST /api/v1/order/create 载荷 132 bytes...", 200);
    await addLog("正在等待服务端返回数据...", 400);
    await addLog("收到 HTTP/1.1 200 OK 响应，大小: 324 bytes", 100);
    await addLog("正在执行测试断言 (Assertion Checks)...", 150);
    await addLog("断言 1: status_code == 200 (PASS)", 50);
    await addLog("断言 2: response.code == 200 (PASS)", 50);
    await addLog("断言 3: data.order_id exists (PASS)", 50);
    await addLog("断言 4: data.status == 'pending_payment' (PASS)", 50);
    
    setLoading(false);
    
    // 派发接口返回成功的事件，让 ApiTesting 页面展现 response
    window.dispatchEvent(new CustomEvent('api-response-success', {
      detail: {
        response: JSON.stringify({
          code: 200,
          message: "success",
          data: {
            order_id: "ORD-20250520-998877",
            status: "pending_payment",
            amount: 198.00,
            goods_id: "GOODS-10029",
            create_time: "2025-05-20 10:32:15"
          }
        }, null, 2)
      }
    }));

    window.dispatchEvent(new CustomEvent('show-toast', { 
      detail: { message: '接口发送成功！断言通过率 100%', type: 'success' } 
    }));
    closeModal();
  };

  // ======================== 逻辑：新建测试用例 ========================
  const handleCreateCase = () => {
    if (!newCaseData.title.trim()) {
      window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: '请输入用例标题', type: 'warning' } }));
      return;
    }

    const randomId = 'TC-' + new Date().getFullYear() + String(new Date().getMonth() + 1).padStart(2, '0') + String(new Date().getDate()).padStart(2, '0') + '-' + Math.floor(1000 + Math.random() * 9000);
    const newCase = {
      id: randomId,
      title: newCaseData.title,
      priority: newCaseData.priority,
      type: newCaseData.type,
      ref: newCaseData.ref,
      status: '待评审',
      color: 'text-amber-500 bg-amber-50 border-amber-100'
    };

    window.dispatchEvent(new CustomEvent('case-created', { detail: { case: newCase } }));
    window.dispatchEvent(new CustomEvent('show-toast', { detail: { message: `用例 ${randomId} 创建成功！`, type: 'success' } }));
    closeModal();
  };

  // ======================== 逻辑：用例执行中 ========================
  const handleRunExecution = async () => {
    setLoading(true);
    setProgress(5);
    
    await addLog("正在拉取待执行用例集...", 150);
    setProgress(15);
    await addLog("启动自动化测试执行引擎...", 200);
    setProgress(25);
    await addLog("用例 1: TC-20250520-0001 正确账号登录 - 开始执行...", 200);
    await addLog("TC-20250520-0001 执行成功 (PASS)", 100);
    setProgress(40);
    await addLog("用例 2: TC-20250520-0002 密码错误提示 - 开始执行...", 150);
    await addLog("TC-20250520-0002 执行成功 (PASS)", 80);
    setProgress(60);
    await addLog("用例 3: TC-20250520-0003 错误登录5次锁定 - 开始执行...", 200);
    await addLog("TC-20250520-0003 出现未捕获异常: [AssertionError] 提示信息不符 (FAIL)", 150);
    setProgress(80);
    await addLog("用例 4: TC-20250520-0004 登录按钮置灰 - 开始执行...", 150);
    await addLog("TC-20250520-0004 执行成功 (PASS)", 100);
    setProgress(100);
    await addLog("用例执行套件全部完成！成功: 3, 失败: 1, 阻塞: 0. 正在汇总报告...", 250);

    setLoading(false);
    window.dispatchEvent(new CustomEvent('show-toast', { 
      detail: { message: '用例执行结束！请前往测试报告查看结果', type: 'info' } 
    }));
    
    // 派发执行结果，通知用例执行页面
    window.dispatchEvent(new CustomEvent('execution-finished', {
      detail: {
        results: {
          total: 4,
          pass: 3,
          fail: 1,
          block: 0,
          rate: '75.0%'
        }
      }
    }));
  };

  if (!modalState.isOpen) return null;

  return (
    <div className="fixed inset-0 z-[999] flex items-center justify-center pointer-events-auto">
      {/* 遮罩背景 */}
      <div 
        onClick={closeModal}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity duration-300"
      ></div>

      {/* 模态框主体 */}
      <div 
        className="relative theme-card rounded-2xl w-full max-w-lg p-5 z-10 scale-100 animate-[modalShow_0.2s_ease-out] border border-[var(--border-color)] overflow-hidden flex flex-col max-h-[90vh]"
        style={{
          backgroundColor: 'var(--bg-card)',
          color: 'var(--text-primary)'
        }}
      >
        {/* 头部 */}
        <div className="flex justify-between items-center pb-3 border-b border-[var(--border-color)] mb-4 select-none shrink-0">
          <div className="flex items-center gap-2">
            {modalState.type === 'upload-req' && <Upload className="size-4 text-blue-500" />}
            {modalState.type === 'generate-cases' && <Sparkles className="size-4 text-purple-500 animate-pulse" />}
            {modalState.type === 'api-request' && <Play className="size-4 text-teal-500 animate-pulse" />}
            {modalState.type === 'new-case' && <Database className="size-4 text-indigo-500" />}
            {modalState.type === 'run-execution' && <Loader2 className="size-4 text-blue-500 animate-spin" />}
            
            <h3 className="text-xs font-bold">
              {modalState.type === 'upload-req' && 'PRD 需求文档导入与 AI 解析'}
              {modalState.type === 'generate-cases' && 'AI 用例批量智能生成向导'}
              {modalState.type === 'api-request' && 'HTTP 接口测试调试雷达'}
              {modalState.type === 'new-case' && '手动创建测试用例'}
              {modalState.type === 'run-execution' && '用例回归套件实时执行中'}
            </h3>
          </div>
          <button 
            onClick={closeModal} 
            className="p-1 rounded-md text-[var(--text-secondary)] hover:bg-[var(--border-color)]/50 transition-colors cursor-pointer"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* 滚动内容区 */}
        <div className="flex-1 overflow-y-auto space-y-4 pr-1 text-left text-[11px] select-text">
          
          {/* ======================== MODAL 1: 上传需求 ======================== */}
          {modalState.type === 'upload-req' && (
            <div className="space-y-4">
              <div 
                className="border-2 border-dashed border-[var(--border-color)] rounded-xl p-6 flex flex-col items-center justify-center bg-[var(--border-color)]/10 hover:bg-[var(--border-color)]/20 cursor-pointer transition-colors relative"
                onClick={() => {
                  const input = document.createElement('input');
                  input.type = 'file';
                  input.accept = '.docx,.pdf,.xlsx,.xmind';
                  input.onchange = (e) => {
                    const selected = e.target.files[0];
                    if (selected) {
                      setFiles([selected]);
                      setLogs([`[系统提示] 选择文件: ${selected.name} (${(selected.size/1024/1024).toFixed(2)}MB)`]);
                    }
                  };
                  input.click();
                }}
              >
                <Upload className="size-8 text-blue-500 mb-2 opacity-80" />
                <span className="font-bold">点击选择需求文档</span>
                <span className="text-[9px] text-[var(--text-secondary)] mt-1">支持 Word, PDF, Excel, XMind 文件</span>
                {files.length > 0 && (
                  <div className="absolute inset-0 bg-[var(--bg-card)] flex flex-col items-center justify-center p-4 rounded-xl border border-blue-500">
                    <FileText className="size-8 text-blue-500 mb-1" />
                    <span className="font-bold text-center truncate w-full max-w-[280px]">{files[0].name}</span>
                    <span className="text-[9px] text-[var(--text-secondary)] mt-0.5">点击空白处重新选择</span>
                  </div>
                )}
              </div>

              {files.length > 0 && !loading && logs.length > 0 && (
                <button 
                  onClick={handleUploadAndParse}
                  className="w-full py-2 accent-btn rounded-lg font-bold text-center cursor-pointer"
                >
                  开始 AI 智能解析
                </button>
              )}
            </div>
          )}

          {/* ======================== MODAL 2: AI 生成用例 ======================== */}
          {modalState.type === 'generate-cases' && !loading && logs.length === 0 && (
            <div className="space-y-4">
              <div className="p-3 bg-[var(--border-color)]/20 border border-[var(--border-color)] rounded-xl text-[10.5px] leading-relaxed">
                <span className="font-bold text-purple-600 block mb-1">AI 用例说明：</span>
                系统将调取 **OpenAI GPT-4o** 大模型，针对所选的测试需求进行深度语义提取。生成结束后，用例数据将真实追加到您的用例列表首部。
              </div>
              <div className="space-y-2">
                <span className="text-[10px] text-[var(--text-secondary)] font-bold block">1. 确认生成策略</span>
                <div className="grid grid-cols-2 gap-2">
                  <div className="p-2 border border-blue-500 bg-blue-500/5 rounded-lg font-bold">标准覆盖策略 (推荐)</div>
                  <div className="p-2 border border-[var(--border-color)] bg-[var(--border-color)]/20 rounded-lg opacity-70">异常边界分析</div>
                </div>
              </div>
              <button 
                onClick={handleAiGenerateCases}
                className="w-full py-2 accent-btn rounded-lg font-bold text-center cursor-pointer"
              >
                立即启动生成
              </button>
            </div>
          )}

          {/* ======================== MODAL 3: HTTP 接口请求 ======================== */}
          {modalState.type === 'api-request' && !loading && logs.length === 0 && (
            <div className="space-y-4 text-center py-4 select-none">
              <div className="relative size-20 mx-auto flex items-center justify-center">
                <div className="absolute inset-0 border border-teal-500 rounded-full animate-ping opacity-45"></div>
                <div className="absolute inset-2 border border-teal-500 rounded-full animate-[ping_1.5s_infinite] opacity-30"></div>
                <div className="size-12 rounded-full bg-teal-500/10 flex items-center justify-center border border-teal-500">
                  <Play className="size-6 text-teal-600 animate-pulse" />
                </div>
              </div>
              <div className="space-y-1">
                <div className="font-bold">接口调试雷达已准备就绪</div>
                <div className="text-[9px] text-[var(--text-secondary)]">即将发送 POST 请求到 http://localhost:3000/api/v1/order/create</div>
              </div>
              <button 
                onClick={handleSendApiRequest}
                className="w-full py-2 accent-btn rounded-lg font-bold text-center cursor-pointer"
              >
                发送请求并执行断言
              </button>
            </div>
          )}

          {/* ======================== MODAL 4: 新建用例表单 ======================== */}
          {modalState.type === 'new-case' && (
            <div className="space-y-3.5">
              <div>
                <label className="text-[10px] text-[var(--text-secondary)] font-bold block mb-1">用例标题</label>
                <input 
                  type="text" 
                  value={newCaseData.title}
                  onChange={(e) => setNewCaseData({ ...newCaseData, title: e.target.value })}
                  placeholder="请输入清晰的用例描述，如：用户在断网状态下尝试提交订单"
                  className="w-full px-3 py-2 premium-input text-[10.5px]"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-[var(--text-secondary)] font-bold block mb-1">优先级</label>
                  <select 
                    value={newCaseData.priority}
                    onChange={(e) => setNewCaseData({ ...newCaseData, priority: e.target.value })}
                    className="w-full px-2.5 py-2 premium-input text-[10.5px]"
                  >
                    <option value="P0">P0 (高影响/阻断)</option>
                    <option value="P1">P1 (核心功能)</option>
                    <option value="P2">P2 (次要功能)</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-[var(--text-secondary)] font-bold block mb-1">用例类型</label>
                  <select 
                    value={newCaseData.type}
                    onChange={(e) => setNewCaseData({ ...newCaseData, type: e.target.value })}
                    className="w-full px-2.5 py-2 premium-input text-[10.5px]"
                  >
                    <option value="功能测试">功能测试</option>
                    <option value="异常测试">异常测试</option>
                    <option value="安全测试">安全测试</option>
                    <option value="性能测试">性能测试</option>
                    <option value="兼容性测试">兼容性测试</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-[10px] text-[var(--text-secondary)] font-bold block mb-1">关联需求编号</label>
                <input 
                  type="text" 
                  value={newCaseData.ref}
                  onChange={(e) => setNewCaseData({ ...newCaseData, ref: e.target.value })}
                  placeholder="REQ-00004"
                  className="w-full px-3 py-2 premium-input text-[10.5px]"
                />
              </div>

              <div className="flex gap-2.5 pt-2">
                <button 
                  onClick={closeModal}
                  className="flex-1 py-2 border border-[var(--border-color)] bg-[var(--bg-card)] text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 rounded-lg text-[10.5px] font-bold text-center cursor-pointer transition-colors"
                >
                  取消
                </button>
                <button 
                  onClick={handleCreateCase}
                  className="flex-1 py-2 accent-btn rounded-lg text-[10.5px] font-bold text-center cursor-pointer"
                >
                  确认保存
                </button>
              </div>
            </div>
          )}

          {/* ======================== MODAL 5: 执行用例回归 ======================== */}
          {modalState.type === 'run-execution' && !loading && logs.length === 0 && (
            <div className="space-y-4 text-center py-4 select-none">
              <div className="relative size-16 mx-auto flex items-center justify-center">
                <Loader2 className="size-8 text-blue-500 animate-spin" />
              </div>
              <div className="space-y-1">
                <div className="font-bold">冒烟/回归测试引擎就绪</div>
                <div className="text-[9px] text-[var(--text-secondary)]">即将一键执行当前版本的测试计划集 (4 个核心用例)</div>
              </div>
              <button 
                onClick={handleRunExecution}
                className="w-full py-2 accent-btn rounded-lg font-bold text-center cursor-pointer"
              >
                立即开始运行
              </button>
            </div>
          )}

          {/* ======================== 进度条 (公共) ======================== */}
          {loading && progress > 0 && (
            <div className="space-y-1 bg-[var(--border-color)]/10 p-3 rounded-xl border border-[var(--border-color)] shrink-0">
              <div className="flex justify-between text-[9px] font-bold">
                <span>正在执行任务...</span>
                <span>{progress}%</span>
              </div>
              <div className="w-full bg-[var(--border-color)]/30 h-1.5 rounded-full overflow-hidden">
                <div className="h-full transition-all duration-300" style={{ width: `${progress}%`, backgroundColor: 'var(--accent-color)' }}></div>
              </div>
            </div>
          )}

          {/* ======================== AI 控制台日志输出 (公共) ======================== */}
          {logs.length > 0 && (
            <div className="mac-terminal p-3 shrink-0 h-44 overflow-y-auto flex flex-col gap-1 w-full text-left">
              <div className="flex items-center gap-1.5 opacity-60 pb-1.5 border-b border-white/10 mb-1 select-none">
                <Terminal className="size-3 text-[#8be9fd]" />
                <span className="text-[#8be9fd]">AI 控制台输出日志</span>
              </div>
              <div className="flex-1 overflow-y-auto space-y-1 text-left">
                {logs.map((log, idx) => (
                  <div key={idx} className="whitespace-pre-wrap select-text leading-relaxed">
                    {log}
                  </div>
                ))}
                {loading && (
                  <div className="flex items-center gap-1 opacity-70 text-slate-400">
                    <span>█</span>
                    <span className="animate-pulse">等待响应中...</span>
                  </div>
                )}
                <div ref={logEndRef} />
              </div>
            </div>
          )}

          {/* 执行完毕后的下一步引导 (如用例运行) */}
          {modalState.type === 'run-execution' && logs.length > 0 && !loading && (
            <div className="flex gap-2.5 pt-1.5 shrink-0">
              <button 
                onClick={closeModal}
                className="flex-1 py-2 border border-[var(--border-color)] bg-[var(--bg-card)] text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 rounded-lg text-[10.5px] font-bold text-center cursor-pointer transition-colors"
              >
                关闭窗口
              </button>
              <button 
                onClick={() => {
                  closeModal();
                  setActiveTab('reports');
                }}
                className="flex-1 py-2 accent-btn rounded-lg text-[10.5px] font-bold text-center cursor-pointer flex items-center justify-center gap-1"
              >
                <FileCheck className="size-3.5" />
                <span>查看测试报告</span>
              </button>
            </div>
          )}

        </div>
      </div>
      
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes modalShow {
          from {
            transform: scale(0.95);
            opacity: 0;
          }
          to {
            transform: scale(1);
            opacity: 1;
          }
        }
      `}} />
    </div>
  );
}
