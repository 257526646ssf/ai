import React, { useState, useEffect, useRef } from 'react';
import { 
  Bot, 
  Send, 
  X, 
  Trash2, 
  MessageSquare, 
  ArrowRight, 
  Sparkles,
  Save,
  Clipboard,
  Check
} from 'lucide-react';
import { apiGet, apiPost, pickList } from '../lib/api';
import { useProjectContext } from '../lib/projectContext';

const PROMPT_TEMPLATE_LIMIT = 6;
const RECENT_ACTIVITY_LIMIT = 5;

const DRAFT_ACTIONS = [
  {
    type: 'test_points',
    label: '生成测试点',
    desc: '按当前上下文拆解',
    icon: Clipboard
  },
  {
    type: 'clarifying_questions',
    label: '生成澄清问题',
    desc: '补齐需求疑点',
    icon: MessageSquare
  },
  {
    type: 'defect_note',
    label: '生成缺陷备注',
    desc: '沉淀复现与影响',
    icon: Sparkles
  }
];

const currentTime = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

const showToast = (message, type = 'info') => {
  window.dispatchEvent(new CustomEvent('show-toast', { detail: { message, type } }));
};

const readField = (source, keys = []) => {
  if (!source || typeof source !== 'object') return undefined;
  for (const key of keys) {
    const value = source[key];
    if (value !== undefined && value !== null && value !== '') return value;
  }
  return undefined;
};

const pickKnownList = (payload, keys = []) => {
  if (Array.isArray(payload)) return payload;
  const picked = pickList(payload);
  if (picked.length) return picked;
  if (!payload || typeof payload !== 'object') return [];
  for (const key of keys) {
    const value = payload[key];
    if (Array.isArray(value)) return value;
    if (value && typeof value === 'object') {
      const nestedList = pickList(value);
      if (nestedList.length) return nestedList;
    }
  }
  return [];
};

const pickKnownLists = (payload, keys = []) => {
  if (Array.isArray(payload)) return payload;
  if (!payload || typeof payload !== 'object') return [];

  const lists = [];
  lists.push(...pickList(payload));
  for (const key of keys) {
    const value = payload[key];
    if (Array.isArray(value)) {
      lists.push(...value);
    } else if (value && typeof value === 'object') {
      lists.push(...pickList(value));
    }
  }
  return lists;
};

const compactText = (value, maxLength = 42) => {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...`;
};

const safeStringify = (value) => {
  if (value === null || value === undefined || value === '') return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

const normalizePromptTemplate = (item, index = 0, source = 'remote') => {
  const content = typeof item === 'string'
    ? item
    : readField(item, ['content', 'prompt', 'template', 'body', 'q', 'text']);
  const title = typeof item === 'string'
    ? compactText(item, 22)
    : readField(item, ['name', 'title', 'label', 'text', 'scene']) || compactText(content, 22);
  const normalizedContent = String(content || title || '').trim();
  if (!normalizedContent) return null;
  return {
    id: readField(item, ['id', 'template_id', 'templateId']) || `${source}-${index}-${normalizedContent.slice(0, 12)}`,
    title: compactText(title || normalizedContent, 24),
    content: normalizedContent,
    scene: typeof item === 'object' ? readField(item, ['scene', 'category', 'type']) : '',
    source
  };
};

const normalizeActivity = (item, index = 0, source = 'remote') => {
  if (typeof item === 'string') {
    return {
      id: `${source}-${index}`,
      title: compactText(item, 32),
      desc: '',
      time: '',
      summary: item
    };
  }

  const detail = readField(item, ['detail', 'metadata', 'payload']);
  const detailText = safeStringify(detail);
  const title = readField(item, ['summary', 'title', 'name', 'message', 'action'])
    || [readField(item, ['module', 'target_type', 'type']), readField(item, ['action'])].filter(Boolean).join(' / ')
    || '系统活动已记录';
  const desc = readField(item, ['description', 'desc', 'content'])
    || detailText
    || [readField(item, ['target_type']), readField(item, ['target_id'])].filter(Boolean).join(' / ');
  const createdAt = readField(item, ['created_at', 'createdAt', 'updated_at', 'updatedAt', 'time']);
  const summary = readField(item, ['summary', 'message'])
    || [title, desc].filter(Boolean).join('：');

  return {
    id: readField(item, ['id', 'activity_id', 'activityId']) || `${source}-${index}`,
    title: compactText(title, 34),
    desc: compactText(desc, 48),
    time: compactText(createdAt, 18),
    summary
  };
};

const mergePromptTemplates = (primary = [], fallback = []) => {
  const seen = new Set();
  return [...primary, ...fallback].filter((item) => {
    const key = item?.content?.trim();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, PROMPT_TEMPLATE_LIMIT);
};

const normalizePromptTemplates = (payload, source = 'remote') => (
  pickKnownList(payload, ['templates', 'prompt_templates', 'promptTemplates', 'prompts', 'common_prompts'])
    .map((item, index) => normalizePromptTemplate(item, index, source))
    .filter(Boolean)
    .slice(0, PROMPT_TEMPLATE_LIMIT)
);

const normalizeActivities = (payload, source = 'remote') => {
  const nestedContext = payload?.context && typeof payload.context === 'object' ? payload.context : {};
  const activityKeys = ['activities', 'recent_activities', 'recentActivities', 'operation_logs', 'operationLogs', 'operations', 'logs'];
  const list = pickKnownLists(payload, activityKeys)
    .concat(pickKnownLists(nestedContext, activityKeys));
  const normalized = list
    .map((item, index) => normalizeActivity(item, index, source))
    .filter((item) => item.summary)
    .slice(0, RECENT_ACTIVITY_LIMIT);
  const summary = readField(payload, ['summary', 'activity_summary', 'recent_activity_summary'])
    || readField(nestedContext, ['summary', 'activity_summary', 'recent_activity_summary']);
  if (summary && !normalized.some((item) => item.summary === summary)) {
    normalized.unshift(normalizeActivity(String(summary), 0, `${source}-summary`));
  }
  return normalized.slice(0, RECENT_ACTIVITY_LIMIT);
};

export default function AiAssistant({ activeTab, isOpen, onClose }) {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [copiedIndex, setCopiedIndex] = useState(null);
  const [promptTemplates, setPromptTemplates] = useState([]);
  const [recentActivities, setRecentActivities] = useState([]);
  const [isSavingPrompt, setIsSavingPrompt] = useState(false);
  const [draftingType, setDraftingType] = useState(null);
  const messagesEndRef = useRef(null);
  const { selectedProject } = useProjectContext();

  // Tab 对应的推荐问题
  const recommendations = {
    dashboard: [
      { text: "分析用例通过率下降的深层原因", q: "今天的测试用例执行通过率为87.6%，较昨日有所上升，但仍有部分失败和阻塞。请帮我分析用例失败的具体根源和趋势。" },
      { text: "有哪些待办需要我马上核对？", q: "分析目前的待办事项，告诉我哪几项的风险最高、需要立刻评审或修复，并给出行动建议。" },
      { text: "生成今日测试报告的AI摘要", q: "请汇总今日测试计划、接口测试、自动化测试的执行数据，并生成一份简明扼要的日报摘要。" }
    ],
    requirements: [
      { text: "如何使用 AI 解析我的 PRD 文档？", q: "我想将一份新的产品需求说明书导入系统，AI 是如何对其进行语义分析、关联提取并自动生成测试点的？请详细说明流程。" },
      { text: "为‘智能客服’模块分析需求关系图", q: "在当前的需求大脑拓扑图中，REQ-00004 发送文本消息节点与上下游有哪些依赖？它们是如何关联的？" },
      { text: "这几个未覆盖的需求怎么补齐用例？", q: "系统提示部分覆盖率为14.8%，未覆盖率为6.8%，针对这部分没有测试用例关联的需求，如何快速自动补齐？" }
    ],
    testcases: [
      { text: "为支付异常边界设计 5 个用例", q: "针对支付网关的‘退款接口’，请结合边界值分析方法，帮我智能生成 5 个包含异常边界场景的测试用例。" },
      { text: "如何评价当前用例集的AI评审质量？", q: "在右侧的 AI 评审面板中，健康度得分为 80 分。目前的用例集中存在哪些主要缺陷（如描述模糊、缺少断言）？该如何优化？" },
      { text: "把评审状态为‘待评审’的用例打包发我", q: "目前有 5 个用例处于‘待评审’状态，请把这 5 个用例的标题、优先级和类型以表格形式整理出来。" }
    ],
    execution: [
      { text: "展示自动化脚本夜间回归失败的分析", q: "自动化任务夜间回归 - 全量中有 12 个用例失败，AI 是否已经提取到了执行日志中的报错堆栈？有什么修复建议？" },
      { text: "为什么 TC-20250520-0004 阻塞了？", q: "查看用例执行详情，TC-20250520-0004 连续执行失败，目前的阻塞状态是因为什么引起的？是否与环境有关？" }
    ],
    apitesting: [
      { text: "编写测试 /api/v1/order/create 的脚本", q: "我想用 Python 编写一个脚本测试 /api/v1/order/create 接口，要求包含请求头、JSON Body、并在返回结果中验证 HTTP 状态码为 200，且 order_id 不为空。" },
      { text: "接口返回 401 报错怎么排查？", q: "在接口调试中遇到了 HTTP 401 Unauthorized 报错，这通常是由哪些原因引起的？在我们的平台中该如何快速定位？" }
    ],
    automation: [
      { text: "什么是用例自愈？如何在这里配置？", q: "AI 自动化测试中的‘用例自愈’是指什么？在平台执行过程中如果 UI 元素发生微调，AI 是如何实现自动定位和自愈运行的？" },
      { text: "帮我写一个 Selenium 自动化登录脚本", q: "请使用 Python + Selenium 写一个自动登录的测试脚本，包括输入用户名、密码、点击登录按钮，并等待页面跳转。" }
    ],
    performance: [
      { text: "并发 500 时 TPS 暴跌，该怎么优化？", q: "在性能压测过程中，并发用户数达到 500 时，系统的 TPS 发生断崖式下跌，且响应延迟从 100ms 飙升至 3s。请列出排查方向和优化策略。" },
      { text: "解释压测图表中的 P99 响应延迟", q: "性能测试报告中常说的 P90、P95、P99 响应延迟分别代表什么意思？为什么只看平均响应时间是不够的？" }
    ],
    reports: [
      { text: "总结今天电商平台的测试结果", q: "请综合今天电商平台的所有测试情况，评估系统当前是否达到了上线标准，风险主要集中在哪里？" },
      { text: "生成一份给项目经理看的质量简报", q: "以专业测试负责人的口吻，为项目经理生成一份精炼的质量简报，字数控制在 200 字以内，使用清晰的列表结构。" }
    ],
    llmconfig: [
      { text: "如何对接自定义的本地 DeepSeek 大模型？", q: "我想在平台中配置本地私有化部署的 DeepSeek-R1 模型，该如何填写 API 端点、模型标识以及 API 秘钥？" },
      { text: "API 报错 429 Too Many Requests 怎么办？", q: "在生成用例时，大模型接口返回了 429 报错，该如何通过限流配置、重试策略或更换 API Key 来解决该问题？" }
    ],
    settings: [
      { text: "配置多人协同和权限管理", q: "平台如何为测试团队配置多用户角色？如何区分测试负责人、普通测试员和开发人员的权限？" },
      { text: "通知服务怎么接入企业微信或飞书？", q: "我想把测试失败的告警和每日测试日报自动推送到企业微信或飞书群机器人，该如何配置 Webhook 链接？" }
    ]
  };

  const getRecommendations = () => {
    return recommendations[activeTab] || recommendations.dashboard;
  };

  const getPromptShortcuts = () => {
    const fallbackTemplates = getRecommendations().map((item, index) => normalizePromptTemplate(item, index, 'local')).filter(Boolean);
    return mergePromptTemplates(promptTemplates, fallbackTemplates);
  };

  const recentActivitySummaries = recentActivities
    .slice(0, RECENT_ACTIVITY_LIMIT)
    .map((item) => item.summary)
    .filter(Boolean);

  const buildAssistantContext = (query, currentMessages = messages) => {
    const recentMessages = currentMessages.slice(-6).map((item) => ({
      role: item.sender === 'ai' ? 'assistant' : 'user',
      content: item.text
    }));
    const currentProject = selectedProject
      ? {
          id: selectedProject.id,
          name: selectedProject.name,
          code: selectedProject.code
        }
      : null;

    return {
      prompt: query,
      active_tab: activeTab,
      activeTab,
      project_id: selectedProject?.id,
      project_name: selectedProject?.name || selectedProject?.code,
      current_project: currentProject,
      currentProject,
      recent_activity_summary: recentActivitySummaries,
      recentActivitySummary: recentActivitySummaries,
      recent_messages: recentMessages,
      recentMessages,
      messages: [...recentMessages, { role: 'user', content: query }]
    };
  };

  const appendAiMessage = (text) => {
    setMessages(prev => [...prev, {
      sender: 'ai',
      text,
      time: currentTime()
    }]);
  };

  const buildLocalDraft = (draftType, prompt = '') => {
    const projectName = selectedProject?.name || selectedProject?.code || '当前项目';
    const activityText = recentActivitySummaries.length
      ? recentActivitySummaries.slice(0, 3).map((item) => `- ${item}`).join('\n')
      : '- 暂无可用最近操作，建议先选择项目或刷新后端数据。';
    const focusLine = prompt.trim() ? `\n\n用户补充关注点：${prompt.trim()}` : '';

    if (draftType === 'test_points') {
      return `### 测试点草稿：${projectName}\n\n1. 核心链路：覆盖当前页面中与 ${activeTab} 相关的主流程、成功路径和数据落库。\n2. 异常链路：补充失败、超时、权限不足、重复提交和空数据场景。\n3. 数据一致性：核对需求、用例、执行记录、缺陷和报告之间的引用关系。\n4. 回归范围：优先回归最近操作影响到的模块。\n\n最近操作依据：\n${activityText}${focusLine}`;
    }

    if (draftType === 'clarifying_questions') {
      return `### 澄清问题草稿：${projectName}\n\n1. 当前变更的业务目标和验收口径是什么？\n2. 哪些用户角色、权限边界或异常输入必须覆盖？\n3. 最近操作中涉及的失败、缺陷或报告项是否已有最终结论？\n4. 是否存在必须兼容的历史数据、旧接口或自动化脚本？\n5. 本轮测试的准出门槛和阻塞条件是什么？\n\n最近操作依据：\n${activityText}${focusLine}`;
    }

    return `### 缺陷备注草稿：${projectName}\n\n- 现象：根据当前页面和最近操作，需补充一次可复现的失败说明。\n- 影响范围：优先核对 ${activeTab} 模块及其上下游数据链路。\n- 初步判断：可能与最新执行记录、接口返回、环境配置或需求变更同步有关。\n- 建议动作：补充复现步骤、实际结果、期望结果、日志截图和关联用例后再提交。\n\n最近操作依据：\n${activityText}${focusLine}`;
  };

  // 初始化欢迎词
  useEffect(() => {
    if (messages.length === 0) {
      const getWelcomeMessage = () => {
        switch (activeTab) {
          case 'dashboard':
            return "您好！我是您的 **AI 测试大脑**。当前我们正位于系统的 **Dashboard 首页**。今天系统整体的用例通过率是 **87.6%**，自动覆盖率达到了 **64.8%**，一切运行正常。有什么我可以帮您分析的吗？";
          case 'requirements':
            return "欢迎来到 **需求库**。我已为您成功解析了当前的 **12 份产品文档** 并提炼出 **186 个结构化需求项**。我可以帮您快速**提取测试点**，或者解答关于**需求大脑拓扑关联图**的问题。";
          case 'testcases':
            return "这里是 **测试用例库**。我已经根据您选择的‘发送文本消息’需求准备好了生成向导。您可以点击左下角选择**边界分析**、**场景导向**等 5 种生成策略。我可以立刻为您**智能编写高覆盖率的测试用例**。";
          case 'execution':
            return "当前正在 **用例执行** 模块。我们可以一键启动测试套件运行。如有执行失败，我可以实时帮您**抓取日志堆栈**、**诊断失败原因**并提供自愈脚本。";
          case 'apitesting':
            return "您正处于 **接口测试工作台**。在这里您可以对系统接口进行可视化的调试与断言设置。如果您需要，我可以直接帮您**根据接口路径生成对应的 Python/JS 测试脚本**，或**自动生成断言规则**。";
          case 'automation':
            return "这里是 **自动化中心**。AI 正在监控底层的脚本执行流。如果您需要编写 Selenium/Playwright 自动化脚本，或者对测试场景进行**动态自愈**配置，请随时向我提问！";
          case 'performance':
            return "当前位于 **性能压测工作台**。我们已经准备好了多个压测方案。如果您对**并发性能指标、P99延迟、资源占用率**的调优存在疑问，我很乐意提供架构优化建议。";
          case 'reports':
            return "您正在查看 **测试报告中心**。今天的最新报告显示整体质量良好，但有 3 个接口存在轻微的超时风险。我可以帮您**提炼一份给管理层汇报的质量分析简报**。";
          case 'llmconfig':
            return "这是 **LLM 智能模型配置中心**。我们当前已对接 OpenAI GPT-4o 作为主解析模型，DeepSeek 作为用例自愈推理引擎。如果您需要切换模型或自定义系统提示词（System Prompt），随时可以向我咨询最佳配置。";
          case 'settings':
            return "当前是 **系统设置**。在这里您可以管理通知 Webhook、协同权限以及测试环境。需要我指导您配置**企业微信/飞书群消息推送**吗？";
          default:
            return "您好！我是您的 **AI 测试助理**。很高兴为您服务，今天有什么测试任务交给我？";
        }
      };

      setMessages([
        {
          sender: 'ai',
          text: getWelcomeMessage(),
          time: currentTime()
        }
      ]);
    }
  }, [activeTab, messages.length]);

  // 打开助手时同步 Prompt 快捷项和最近操作上下文
  useEffect(() => {
    if (!isOpen) return;

    let cancelled = false;
    const controller = new AbortController();
    const projectId = selectedProject?.id;

    async function loadPromptTemplates() {
      try {
        const payload = await apiGet('/prompt-templates', {
          params: { page: 1, pageSize: PROMPT_TEMPLATE_LIMIT, projectId, activeTab },
          signal: controller.signal,
          timeoutMs: 8000
        });
        if (!cancelled) {
          setPromptTemplates(normalizePromptTemplates(payload));
        }
      } catch {
        if (!cancelled) setPromptTemplates([]);
      }
    }

    async function loadAssistantContext() {
      try {
        const payload = await apiGet('/assistant/context', {
          params: { projectId, activeTab, limit: RECENT_ACTIVITY_LIMIT },
          signal: controller.signal,
          timeoutMs: 8000
        });
        if (!cancelled) {
          setRecentActivities(normalizeActivities(payload));
        }
      } catch {
        try {
          const fallback = await apiGet('/system/recent-activities', {
            params: { projectId, limit: RECENT_ACTIVITY_LIMIT },
            signal: controller.signal,
            timeoutMs: 8000
          });
          if (!cancelled) {
            setRecentActivities(normalizeActivities(fallback, 'activity'));
          }
        } catch {
          if (!cancelled) setRecentActivities([]);
        }
      }
    }

    loadPromptTemplates();
    loadAssistantContext();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [activeTab, isOpen, selectedProject?.id]);

  // 滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const buildLocalFallbackReply = (query) => {
    if (query.includes("通过率") || query.includes("质量") || query.includes("准出")) {
      return `后端 AI 服务暂不可用，我先按当前页面做本地分析：请优先核对失败执行、阻塞执行、未关闭缺陷和最近报告的风险项。如果顶部已选中项目，恢复后端连接后我会自动基于该项目的真实执行、接口、自动化和性能数据重新生成结论。`;
    }
    if (query.includes("待办") || query.includes("待处理") || query.includes("风险")) {
      return `后端 AI 服务暂不可用。本地兜底建议先处理三类事项：未关闭高严重缺陷、失败或阻塞执行记录、缺少最近报告归档的测试范围。恢复后端连接后，我会用项目事实数据重新排序待办优先级。`;
    }
    if (query.includes("Python") || query.includes("脚本") || query.includes("代码")) {
      return `后端 AI 服务暂不可用。你可以先在接口测试或自动化中心生成对应项目资源，再让我基于后端保存的接口、环境和用例文件生成脚本建议。`;
    }
    return `后端 AI 服务暂不可用，我已收到“${query}”。请稍后重试，或先在当前页面完成数据同步；连接恢复后我会基于项目真实数据继续分析。`;
  };

  const handleSendMessage = async (textToSend) => {
    const query = textToSend || inputValue;
    if (!query.trim()) return;

    const userMsg = {
      sender: 'user',
      text: query,
      time: currentTime()
    };

    setMessages(prev => [...prev, userMsg]);
    if (!textToSend) setInputValue('');
    setIsTyping(true);

    try {
      const response = await apiPost('/chat', {
        message: query,
        context: buildAssistantContext(query)
      }, { timeoutMs: 15000 });
      const aiResponseText = response?.reply || response?.content || buildLocalFallbackReply(query);
      setIsTyping(false);
      appendAiMessage(aiResponseText);
    } catch (error) {
      setIsTyping(false);
      appendAiMessage(buildLocalFallbackReply(query));
      showToast(error?.message || 'AI 助手后端暂不可用，已使用本地兜底回复', 'warning');
    }
  };

  const copyTextToClipboard = async (text) => {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    document.execCommand('copy');
    textarea.remove();
  };

  const handleCopyText = async (text, index) => {
    try {
      await copyTextToClipboard(text);
      setCopiedIndex(index);
      setTimeout(() => setCopiedIndex(null), 2000);
    } catch (error) {
      showToast(error?.message || '复制失败，请检查浏览器剪贴板权限', 'error');
    }
  };

  const handleCopyCode = (text, index) => {
    handleCopyText(text, index);
  };

  const handleApplyPrompt = (template) => {
    setInputValue(template.content);
    showToast('已填入输入框，可编辑后发送', 'info');
  };

  const handleSendPrompt = (template) => {
    handleSendMessage(template.content);
  };

  const handleSavePrompt = async () => {
    const prompt = inputValue.trim();
    if (!prompt) {
      showToast('请先输入要保存的 Prompt', 'warning');
      return;
    }

    const title = compactText(prompt, 24);
    setIsSavingPrompt(true);
    try {
      const saved = await apiPost('/prompt-templates', {
        scene: `assistant_common_${activeTab}_${Date.now()}`,
        name: title,
        content: prompt,
        variables: [],
        is_builtin: false
      }, { timeoutMs: 10000 });
      const normalized = normalizePromptTemplate(saved, 0, 'saved')
        || normalizePromptTemplate({ name: title, content: prompt }, 0, 'saved');
      setPromptTemplates(prev => mergePromptTemplates([normalized], prev));
      showToast('已保存为常用 Prompt', 'success');
    } catch (error) {
      showToast(error?.message || '保存常用 Prompt 失败', 'error');
    } finally {
      setIsSavingPrompt(false);
    }
  };

  const handleUseActivity = (activity) => {
    setInputValue(`请基于这条最近操作继续分析：${activity.summary}`);
    showToast('最近操作摘要已带入输入框', 'info');
  };

  const handleCreateDraft = async (draftType) => {
    if (draftingType) return;

    const action = DRAFT_ACTIONS.find((item) => item.type === draftType);
    const prompt = inputValue.trim();
    setDraftingType(draftType);
    setIsTyping(true);

    try {
      const response = await apiPost('/assistant/drafts', {
        type: draftType,
        action: draftType,
        message: prompt,
        prompt,
        context: buildAssistantContext(prompt || action?.label || draftType)
      }, { timeoutMs: 12000 });
      const draftPayload = typeof response === 'string'
        ? response
        : readField(response, ['draft', 'content', 'text', 'message', 'result']);
      const draftText = typeof draftPayload === 'object'
        ? readField(draftPayload, ['content', 'text', 'message']) || safeStringify(draftPayload)
        : draftPayload;
      appendAiMessage(draftText || buildLocalDraft(draftType, prompt));
    } catch (error) {
      appendAiMessage(buildLocalDraft(draftType, prompt));
      showToast(error?.message || '草稿服务暂不可用，已生成本地兜底草稿', 'warning');
    } finally {
      setIsTyping(false);
      setDraftingType(null);
    }
  };

  // 简单的 Markdown 及代码高亮渲染器
  const renderMessageContent = (text, msgIdx) => {
    const lines = text.split('\n');
    const elements = [];
    let inCodeBlock = false;
    let codeContent = [];
    let codeLanguage = '';
    const escapeHtml = (value) => String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
    const renderInlineMarkdown = (value) => escapeHtml(value)
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/`(.*?)`/g, '<code class="px-1 py-0.5 rounded bg-black/5 dark:bg-white/10 font-mono text-[10px]">$1</code>');

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      // 处理代码块开始/结束
      if (line.trim().startsWith('```')) {
        if (!inCodeBlock) {
          inCodeBlock = true;
          codeLanguage = line.trim().substring(3) || 'javascript';
          codeContent = [];
        } else {
          inCodeBlock = false;
          const codeString = codeContent.join('\n');
          const currentCodeIdx = `${msgIdx}-${i}`;
          elements.push(
            <div key={`code-${i}`} className="my-2 border border-[var(--border-color)] rounded-lg overflow-hidden bg-black/10 dark:bg-black/30 font-mono text-[10px] w-full text-left">
              <div className="flex justify-between items-center bg-[var(--border-color)]/50 px-3 py-1.5 border-b border-[var(--border-color)]">
                <span className="text-[9px] uppercase font-bold tracking-wider opacity-60">{codeLanguage}</span>
                <button 
                  onClick={() => handleCopyCode(codeString, currentCodeIdx)}
                  className="flex items-center gap-1 text-[9px] opacity-60 hover:opacity-100 transition-opacity"
                >
                  {copiedIndex === currentCodeIdx ? (
                    <>
                      <Check className="size-3 text-emerald-500" />
                      <span className="text-emerald-500">已复制</span>
                    </>
                  ) : (
                    <>
                      <Clipboard className="size-3" />
                      <span>复制</span>
                    </>
                  )}
                </button>
              </div>
              <pre className="p-3 overflow-x-auto text-[10px] leading-relaxed select-text whitespace-pre text-slate-800 dark:text-slate-200">
                <code>{codeString}</code>
              </pre>
            </div>
          );
        }
        continue;
      }

      if (inCodeBlock) {
        codeContent.push(line);
        continue;
      }

      // 处理表格
      if (line.trim().startsWith('|') && lines[i + 1]?.trim().startsWith('|') && lines[i + 1]?.includes('-')) {
        const tableRows = [];
        let headerCols = line.split('|').map(c => c.trim()).filter(c => c);
        
        // 跨行读取表格内容
        let j = i + 2;
        while (j < lines.length && lines[j].trim().startsWith('|')) {
          tableRows.push(lines[j].split('|').map(c => c.trim()).filter(c => c));
          j++;
        }
        
        elements.push(
          <div key={`table-${i}`} className="overflow-x-auto my-2.5 max-w-full">
            <table className="w-full text-[9px] border-collapse text-left border border-[var(--border-color)]">
              <thead>
                <tr className="bg-[var(--border-color)]/30 border-b border-[var(--border-color)]">
                  {headerCols.map((h, idx) => (
                    <th key={idx} className="p-2 font-bold" dangerouslySetInnerHTML={{ __html: renderInlineMarkdown(h) }}></th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-color)] opacity-90">
                {tableRows.map((row, rIdx) => (
                  <tr key={rIdx} className="hover:bg-[var(--border-color)]/10">
                    {row.map((col, cIdx) => (
                      <td key={cIdx} className="p-2" dangerouslySetInnerHTML={{ __html: renderInlineMarkdown(col) }}></td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
        i = j - 1;
        continue;
      }

      // 处理普通行 (粗体, 行内代码)
      const renderedLine = renderInlineMarkdown(line);
      
      // 转化 Markdown 粗体 **text** 到 HTML
      // 转化 Markdown 行内代码 `code`
      
      if (line.trim().startsWith('*') || line.trim().startsWith('-')) {
        // 无序列表
        const cleanText = renderedLine.trim().substring(1).trim();
        elements.push(
          <li key={i} className="ml-4 list-disc text-[10.5px] leading-relaxed" dangerouslySetInnerHTML={{ __html: cleanText }} />
        );
      } else if (line.match(/^\d+\./)) {
        // 有序列表
        const dotIndex = renderedLine.indexOf('.');
        const cleanText = renderedLine.substring(dotIndex + 1).trim();
        elements.push(
          <li key={i} className="ml-4 list-decimal text-[10.5px] leading-relaxed" dangerouslySetInnerHTML={{ __html: cleanText }} />
        );
      } else if (line.trim() === '') {
        elements.push(<div key={i} className="h-1.5" />);
      } else {
        elements.push(
          <p key={i} className="text-[10.5px] leading-relaxed" dangerouslySetInnerHTML={{ __html: renderedLine }} />
        );
      }
    }

    return <div className="space-y-1 text-left w-full select-text">{elements}</div>;
  };

  const handleClearHistory = () => {
    setMessages([
      {
        sender: 'ai',
        text: "对话历史已清空。我是您的 AI 智能助理，请问现在有什么可以帮您？",
        time: currentTime()
      }
    ]);
    showToast('AI 对话历史已重置', 'info');
  };

  const promptShortcuts = getPromptShortcuts();
  const visibleRecentActivities = recentActivities.slice(0, 3);

  return (
    <div 
      className={`fixed top-0 right-0 h-screen w-full max-w-[360px] bg-[var(--bg-card)] border-l border-[var(--border-color)] shadow-2xl z-50 flex flex-col justify-between transition-transform duration-300 transform select-none ${
        isOpen ? 'translate-x-0' : 'translate-x-full'
      }`}
      style={{
        backdropFilter: 'blur(20px)',
        backgroundColor: 'var(--bg-card)'
      }}
    >
      {/* 头部 */}
      <div className="p-4 border-b border-[var(--border-color)] flex items-center justify-between">
        <div className="flex items-center gap-2">
          {/* AI 呼吸头像 */}
          <div className="relative size-7 rounded-full bg-zinc-950 flex items-center justify-center border border-white/10 shrink-0">
            <span className="absolute inset-0 rounded-full bg-blue-500 animate-ping opacity-25"></span>
            <Bot className="size-4 text-white" />
          </div>
          <div className="flex flex-col text-left">
            <span className="text-[12px] font-bold text-[var(--text-primary)] flex items-center gap-1.5 leading-none">
              测试大脑 AI 助手
              <span className="flex size-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full size-1.5 bg-emerald-500"></span>
              </span>
            </span>
            <span className="text-[9px] text-[var(--text-secondary)] mt-1">
              后端分析链路 • {selectedProject?.name || selectedProject?.code || '未选择项目'}
            </span>
          </div>
        </div>
        
        <div className="flex items-center gap-1.5">
          <button 
            onClick={handleClearHistory}
            title="清空会话" 
            className="p-1 rounded text-[var(--text-secondary)] hover:text-red-500 hover:bg-[var(--border-color)]/50 transition-colors cursor-pointer"
          >
            <Trash2 className="size-3.5" />
          </button>
          <button 
            onClick={onClose} 
            className="p-1 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--border-color)]/50 transition-colors cursor-pointer"
          >
            <X className="size-3.5" />
          </button>
        </div>
      </div>

      {/* 对话消息区 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex gap-2.5 ${msg.sender === 'user' ? 'flex-row-reverse' : ''}`}>
            {/* 头像 */}
            <div 
              style={msg.sender === 'user' ? { backgroundColor: 'var(--accent-color)', borderColor: 'var(--accent-color)' } : {}}
              className={`size-7 rounded-full flex items-center justify-center border shrink-0 text-[var(--accent-text)] ${
                msg.sender === 'user' 
                  ? '' 
                  : 'bg-zinc-950 border-white/10 text-white'
              }`}
            >
              {msg.sender === 'user' ? '我' : <Bot className="size-3.5" />}
            </div>

            {/* 气泡 */}
            <div 
              style={msg.sender === 'user' ? { backgroundColor: 'var(--accent-color)', color: 'var(--accent-text)', borderColor: 'var(--accent-color)' } : {}}
              className={`max-w-[260px] rounded-2xl px-3 py-2 text-[10.5px] border ${
                msg.sender === 'user'
                  ? 'rounded-tr-none'
                  : 'bg-[var(--border-color)]/30 text-[var(--text-primary)] border-[var(--border-color)] rounded-tl-none'
              } min-w-0 break-words`}
            >
              {renderMessageContent(msg.text, idx)}
              <div className={`text-[8px] mt-1 font-medium ${
                msg.sender === 'ai' ? 'flex items-center justify-between gap-2' : 'text-right'
              }`}>
                {msg.sender === 'ai' && (
                  <button
                    type="button"
                    onClick={() => handleCopyText(msg.text, `message-${idx}`)}
                    title="复制整条回复"
                    className="inline-flex items-center gap-1 opacity-45 hover:opacity-100 transition-opacity cursor-pointer"
                  >
                    {copiedIndex === `message-${idx}` ? (
                      <>
                        <Check className="size-2.5 text-emerald-500" />
                        <span className="text-emerald-500">已复制</span>
                      </>
                    ) : (
                      <>
                        <Clipboard className="size-2.5" />
                        <span>复制</span>
                      </>
                    )}
                  </button>
                )}
                <span className="shrink-0 opacity-45">{msg.time}</span>
              </div>
            </div>
          </div>
        ))}

        {/* AI 正在打字中... */}
        {isTyping && (
          <div className="flex gap-2.5">
            <div className="size-7 rounded-full bg-zinc-950 flex items-center justify-center border border-white/10 text-white shrink-0">
              <Bot className="size-3.5" />
            </div>
            <div className="bg-[var(--border-color)]/30 text-[var(--text-primary)] border border-[var(--border-color)] rounded-2xl rounded-tl-none px-3 py-2.5 text-[10.5px] flex items-center gap-1 w-14 justify-center">
              <span className="size-1 bg-[var(--text-secondary)] rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
              <span className="size-1 bg-[var(--text-secondary)] rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
              <span className="size-1 bg-[var(--text-secondary)] rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* 底部 Prompt、上下文和输入框 */}
      <div className="p-3 border-t border-[var(--border-color)] bg-[var(--bg-card)] space-y-2.5 max-h-[55vh] overflow-y-auto">
        {/* 结构化草稿动作 */}
        <div className="grid grid-cols-3 gap-1.5">
          {DRAFT_ACTIONS.map((action) => {
            const Icon = action.icon;
            const isCurrentDraft = draftingType === action.type;
            return (
              <button
                key={action.type}
                type="button"
                onClick={() => handleCreateDraft(action.type)}
                disabled={Boolean(draftingType) || isTyping}
                className="min-w-0 px-2 py-2 rounded-lg border border-[var(--border-color)] bg-[var(--border-color)]/15 hover:bg-[var(--border-color)]/45 text-[var(--text-primary)] transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
                title={action.label}
              >
                <Icon className="size-3.5 mx-auto mb-1 text-[var(--accent-color)]" />
                <span className="block text-[8.5px] font-bold truncate">{isCurrentDraft ? '生成中...' : action.label}</span>
                <span className="block text-[7px] text-[var(--text-secondary)] truncate mt-0.5">{action.desc}</span>
              </button>
            );
          })}
        </div>

        {/* 常用 Prompt */}
        <div className="space-y-1.5 text-left">
          <div className="text-[8px] font-bold text-[var(--text-secondary)] uppercase tracking-wider flex items-center justify-between gap-2">
            <span className="flex items-center gap-1 min-w-0">
              <Sparkles className="size-2.5 text-purple-500 animate-pulse shrink-0" />
              <span className="truncate">常用 Prompt</span>
            </span>
            <button
              type="button"
              onClick={handleSavePrompt}
              disabled={isSavingPrompt || !inputValue.trim()}
              title="保存当前输入为常用 Prompt"
              className="inline-flex items-center gap-1 px-1.5 py-1 rounded border border-[var(--border-color)] hover:bg-[var(--border-color)]/40 text-[var(--text-primary)] transition-colors disabled:opacity-45 disabled:cursor-not-allowed"
            >
              {isSavingPrompt ? <Check className="size-2.5 text-emerald-500" /> : <Save className="size-2.5" />}
              <span>保存</span>
            </button>
          </div>
          <div className="flex flex-col gap-1">
            {promptShortcuts.map((template) => (
              <div
                key={template.id}
                className="flex items-stretch gap-1 min-w-0"
              >
                <button
                  type="button"
                  onClick={() => handleApplyPrompt(template)}
                  className="text-left flex-1 min-w-0 px-2.5 py-1.5 text-[9px] font-medium text-[var(--text-primary)] bg-[var(--border-color)]/20 hover:bg-[var(--border-color)]/50 rounded-lg border border-[var(--border-color)] transition-colors cursor-pointer"
                  title={template.content}
                >
                  <span className="block truncate">{template.title}</span>
                  <span className="block truncate text-[7.5px] text-[var(--text-secondary)] mt-0.5">
                    {template.source === 'remote' ? '填入 · 后端模板' : template.source === 'saved' ? '填入 · 刚保存' : '填入 · 本地预设'}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => handleSendPrompt(template)}
                  disabled={isTyping}
                  title="直接发送"
                  className="px-2 rounded-lg border border-[var(--border-color)] bg-[var(--border-color)]/20 hover:bg-[var(--border-color)]/50 text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors cursor-pointer disabled:opacity-45 disabled:cursor-not-allowed shrink-0"
                >
                  <ArrowRight className="size-3" />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* 最近操作回溯 */}
        <div className="space-y-1.5 text-left">
          <div className="text-[8px] font-bold text-[var(--text-secondary)] uppercase tracking-wider flex items-center gap-1">
            <MessageSquare className="size-2.5 text-[var(--accent-color)] shrink-0" />
            <span className="truncate">最近操作</span>
          </div>
          <div className="flex flex-col gap-1">
            {visibleRecentActivities.length ? (
              visibleRecentActivities.map((activity) => (
                <button
                  key={activity.id}
                  type="button"
                  onClick={() => handleUseActivity(activity)}
                  className="text-left w-full min-w-0 px-2.5 py-1.5 text-[9px] font-medium text-[var(--text-primary)] bg-[var(--border-color)]/15 hover:bg-[var(--border-color)]/45 rounded-lg border border-[var(--border-color)] transition-colors cursor-pointer"
                  title={activity.summary}
                >
                  <span className="block truncate">{activity.title}</span>
                  <span className="block truncate text-[7.5px] text-[var(--text-secondary)] mt-0.5">
                    {activity.desc ? `带入 · ${activity.desc}` : activity.time ? `带入 · ${activity.time}` : '带入提问'}
                  </span>
                </button>
              ))
            ) : (
              <div className="px-2.5 py-1.5 text-[8.5px] text-[var(--text-secondary)] bg-[var(--border-color)]/10 rounded-lg border border-dashed border-[var(--border-color)]">
                暂无最近操作
              </div>
            )}
          </div>
        </div>

        {/* 真正输入区域 */}
        <form 
          onSubmit={(e) => {
            e.preventDefault();
            handleSendMessage();
          }}
          className="flex items-center gap-1.5"
        >
          <input 
            type="text" 
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="向 AI 测试大脑提问..." 
            className="flex-1 px-3 py-2 premium-input text-[10.5px]"
          />
          <button 
            type="submit"
            disabled={!inputValue.trim() || isTyping}
            className="p-2 rounded-xl accent-btn shrink-0 cursor-pointer"
          >
            <Send className="size-3.5" />
          </button>
        </form>
      </div>

    </div>
  );
}
