import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  CheckCircle,
  FileText,
  Plus,
  RefreshCw,
  Save,
  Sparkles,
  Trash2
} from 'lucide-react';
import { apiGet, apiPost, apiRequest, pickList } from '../lib/api';

const NEW_TEMPLATE_ID = 'new';

const showToast = (message, type = 'success') => {
  window.dispatchEvent(new CustomEvent('show-toast', { detail: { message, type } }));
};

const normalizeVariables = (value) => {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  if (value && typeof value === 'object') {
    return Object.keys(value).map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return [];
    try {
      const parsed = JSON.parse(trimmed);
      return normalizeVariables(parsed);
    } catch {
      return trimmed.split(/[\n,，]+/).map((item) => item.trim()).filter(Boolean);
    }
  }
  return [];
};

const variablesToText = (variables) => normalizeVariables(variables).join(', ');

const normalizeTemplate = (template) => ({
  id: template.id ?? template.template_id ?? template.templateId,
  name: template.name || '未命名 Prompt',
  scene: template.scene || '',
  content: template.content || '',
  variables: normalizeVariables(template.variables),
  isBuiltin: Boolean(template.is_builtin ?? template.isBuiltin ?? template.builtin),
  updatedAt: template.updated_at || template.updatedAt || template.created_at || template.createdAt || '',
  raw: template
});

const createBlankDraft = () => ({
  id: null,
  name: '',
  scene: '',
  content: '',
  variablesText: ''
});

const toDraft = (template) => ({
  id: template.id,
  name: template.name,
  scene: template.scene,
  content: template.content,
  variablesText: variablesToText(template.variables)
});

const parseVariableNames = (value) => {
  const variables = normalizeVariables(value);
  const uniqueNames = [];
  const seen = new Set();
  variables.forEach((item) => {
    const name = item.trim();
    if (!name || seen.has(name)) return;
    seen.add(name);
    uniqueNames.push(name);
  });
  return uniqueNames;
};

const parseRenderVariables = (value) => {
  const text = value.trim();
  if (!text) return {};

  if (text.startsWith('{')) {
    const parsed = JSON.parse(text);
    const variables = parsed.variables && typeof parsed.variables === 'object'
      ? parsed.variables
      : parsed;
    if (!variables || Array.isArray(variables) || typeof variables !== 'object') {
      throw new Error('变量 JSON 必须是对象，例如 {"requirement":"登录需求"}');
    }
    return variables;
  }

  return text
    .split(/[\n,，]+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .reduce((result, line) => {
      const separatorIndex = line.indexOf('=');
      if (separatorIndex <= 0) {
        throw new Error('简单文本请使用 key=value 格式，每行或逗号分隔。');
      }
      const key = line.slice(0, separatorIndex).trim();
      const rawValue = line.slice(separatorIndex + 1).trim();
      if (!key) {
        throw new Error('变量名不能为空。');
      }
      result[key] = rawValue;
      return result;
    }, {});
};

const renderLocally = (content, variables) => Object.entries(variables).reduce(
  (result, [key, value]) => result.replaceAll(`{{${key}}}`, String(value)),
  content
);

export default function PromptTemplatePanel() {
  const [templates, setTemplates] = useState([]);
  const [activeId, setActiveId] = useState(NEW_TEMPLATE_ID);
  const [draft, setDraft] = useState(createBlankDraft);
  const [renderInput, setRenderInput] = useState('requirement=用户登录后可以查看订单列表');
  const [rendered, setRendered] = useState('');
  const [missingVariables, setMissingVariables] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [loadError, setLoadError] = useState('');

  const activeTemplate = useMemo(
    () => templates.find((template) => String(template.id) === String(activeId)) || null,
    [activeId, templates]
  );
  const isNewTemplate = activeId === NEW_TEMPLATE_ID || !draft.id;
  const canDelete = Boolean(activeTemplate && !activeTemplate.isBuiltin);

  const stats = useMemo(() => {
    const builtin = templates.filter((template) => template.isBuiltin).length;
    return {
      total: templates.length,
      builtin,
      custom: Math.max(0, templates.length - builtin)
    };
  }, [templates]);

  const loadTemplates = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setIsLoading(true);
    setLoadError('');
    try {
      const payload = await apiGet('/prompt-templates', { params: { page: 1, pageSize: 100 } });
      const nextTemplates = pickList(payload).map(normalizeTemplate).filter((item) => item.id !== undefined && item.id !== null);
      setTemplates(nextTemplates);
      setActiveId((currentId) => {
        if (currentId === NEW_TEMPLATE_ID) return currentId;
        return nextTemplates.some((item) => String(item.id) === String(currentId))
          ? currentId
          : String(nextTemplates[0]?.id || NEW_TEMPLATE_ID);
      });
    } catch (error) {
      const message = error.message || 'Prompt 模板加载失败';
      setLoadError(message);
      showToast(`Prompt 模板加载失败：${message}`, 'error');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  useEffect(() => {
    if (activeId === NEW_TEMPLATE_ID) {
      setDraft(createBlankDraft());
      setRendered('');
      setMissingVariables([]);
      return;
    }
    if (activeTemplate) {
      setDraft(toDraft(activeTemplate));
      setRendered('');
      setMissingVariables([]);
    }
  }, [activeId, activeTemplate]);

  const updateDraft = (key, value) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const buildSavePayload = () => {
    const name = draft.name.trim();
    const scene = draft.scene.trim();
    const content = draft.content;
    const variables = parseVariableNames(draft.variablesText);

    if (!name) throw new Error('模板名称不能为空。');
    if (!scene) throw new Error('scene 不能为空。');
    if (!content.trim()) throw new Error('Prompt 内容不能为空。');

    return {
      name,
      scene,
      content,
      variables
    };
  };

  const handleNewTemplate = () => {
    setActiveId(NEW_TEMPLATE_ID);
    setDraft(createBlankDraft());
    setRendered('');
    setMissingVariables([]);
  };

  const handleSave = async () => {
    if (isSaving) return;
    setIsSaving(true);
    try {
      const payload = buildSavePayload();
      const saved = isNewTemplate
        ? await apiPost('/prompt-templates', { ...payload, is_builtin: false })
        : await apiRequest(`/prompt-templates/${draft.id}`, { method: 'PATCH', body: payload });
      const normalized = normalizeTemplate(saved);

      setTemplates((current) => {
        if (isNewTemplate) return [normalized, ...current];
        return current.map((item) => (String(item.id) === String(normalized.id) ? normalized : item));
      });
      setActiveId(String(normalized.id));
      showToast(isNewTemplate ? '自定义 Prompt 模板已新增。' : 'Prompt 模板已更新。');
    } catch (error) {
      showToast(`保存 Prompt 模板失败：${error.message || error}`, 'error');
    } finally {
      setIsSaving(false);
    }
  };

  const handleTestRender = async () => {
    if (!draft.id) {
      showToast('请先保存模板，再执行测试渲染。', 'warning');
      return;
    }
    if (isTesting) return;
    setIsTesting(true);
    setRendered('');
    setMissingVariables([]);
    try {
      const variables = parseRenderVariables(renderInput);
      const result = await apiPost(
        `/prompt-templates/${draft.id}/test`,
        { ...variables, variables },
        { timeoutMs: 10000 }
      );
      const renderedText = result?.rendered ?? result?.rendered_preview ?? result?.renderedPreview;
      setRendered(renderedText === undefined ? renderLocally(draft.content, variables) : String(renderedText));
      setMissingVariables(normalizeVariables(result?.missing_variables || result?.missingVariables));
      showToast('Prompt 测试渲染完成。', 'success');
    } catch (error) {
      showToast(`测试渲染失败：${error.message || error}`, 'error');
    } finally {
      setIsTesting(false);
    }
  };

  const handleDelete = async () => {
    if (!canDelete || isDeleting) return;
    const confirmed = window.confirm(`确认删除 Prompt 模板「${activeTemplate.name}」？`);
    if (!confirmed) return;

    setIsDeleting(true);
    try {
      await apiRequest(`/prompt-templates/${activeTemplate.id}`, { method: 'DELETE' });
      const remaining = templates.filter((item) => String(item.id) !== String(activeTemplate.id));
      setTemplates(remaining);
      setActiveId(String(remaining[0]?.id || NEW_TEMPLATE_ID));
      showToast('自定义 Prompt 模板已删除。', 'info');
    } catch (error) {
      showToast(`删除 Prompt 模板失败：${error.message || error}`, 'error');
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="theme-card rounded-xl p-5 space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between border-b border-[var(--border-color)] pb-3">
        <div>
          <h2 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
            <Sparkles className="size-4 text-[var(--accent-color)]" />
            <span>Prompt 模板 / 常用 Prompt</span>
          </h2>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[9px] font-bold text-[var(--text-secondary)]">
            <span className="px-2 py-0.5 rounded bg-[var(--border-color)]/30 border border-[var(--border-color)]">TOTAL {stats.total}</span>
            <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-500 border border-emerald-500/15">BUILTIN {stats.builtin}</span>
            <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-500 border border-blue-500/15">CUSTOM {stats.custom}</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            title="刷新 Prompt 模板"
            onClick={() => loadTemplates()}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--border-color)]/30 hover:bg-[var(--border-color)]/60 text-[10px] font-bold text-[var(--text-primary)] transition-all active:scale-95 cursor-pointer border border-[var(--border-color)] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw className={`size-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            <span>刷新</span>
          </button>
          <button
            type="button"
            onClick={handleNewTemplate}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg glow-button-neon text-[10px] font-bold text-white cursor-pointer shadow-sm active:scale-95"
          >
            <Plus className="size-3.5" />
            <span>新增模板</span>
          </button>
        </div>
      </div>

      {loadError && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/15 bg-red-500/5 px-3 py-2 text-[10px] font-bold text-red-500">
          <AlertCircle className="size-3.5 shrink-0" />
          <span>{loadError}</span>
        </div>
      )}

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 lg:col-span-4 border border-[var(--border-color)] rounded-xl overflow-hidden bg-[var(--bg-card)]/40">
          <div className="px-3 py-2 border-b border-[var(--border-color)] flex items-center justify-between">
            <span className="text-[10px] font-black text-[var(--text-primary)] uppercase">Template Registry</span>
            {isLoading && <RefreshCw className="size-3.5 animate-spin text-[var(--accent-color)]" />}
          </div>

          <div className="max-h-[430px] overflow-y-auto divide-y divide-[var(--border-color)]">
            <button
              type="button"
              onClick={handleNewTemplate}
              className={`w-full px-3 py-3 text-left transition-colors ${
                activeId === NEW_TEMPLATE_ID
                  ? 'bg-[var(--accent-glow)]/40 border-l-[3px] border-[var(--accent-color)]'
                  : 'hover:bg-[var(--border-color)]/25 border-l-[3px] border-transparent'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-black text-[var(--text-primary)]">新增自定义模板</span>
                <span className="px-1.5 py-0.5 rounded text-[8px] font-black bg-blue-500/10 text-blue-500">DRAFT</span>
              </div>
              <div className="mt-1 text-[9px] text-[var(--text-secondary)] font-semibold">POST /prompt-templates</div>
            </button>

            {templates.map((template) => {
              const selected = String(template.id) === String(activeId);
              return (
                <button
                  key={template.id}
                  type="button"
                  onClick={() => setActiveId(String(template.id))}
                  className={`w-full px-3 py-3 text-left transition-colors ${
                    selected
                      ? 'bg-[var(--accent-glow)]/40 border-l-[3px] border-[var(--accent-color)]'
                      : 'hover:bg-[var(--border-color)]/25 border-l-[3px] border-transparent'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-black text-[var(--text-primary)] truncate">{template.name}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[8px] font-black shrink-0 ${
                      template.isBuiltin ? 'bg-emerald-500/10 text-emerald-500' : 'bg-blue-500/10 text-blue-500'
                    }`}>
                      {template.isBuiltin ? 'BUILTIN' : 'CUSTOM'}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center gap-1.5 text-[9px] text-[var(--text-secondary)] font-semibold">
                    <FileText className="size-3 shrink-0" />
                    <span className="truncate">{template.scene || '未绑定 scene'}</span>
                  </div>
                </button>
              );
            })}

            {!isLoading && templates.length === 0 && (
              <div className="px-3 py-6 text-center text-[10px] font-bold text-[var(--text-secondary)]">
                暂无 Prompt 模板
              </div>
            )}
          </div>
        </div>

        <div className="col-span-12 lg:col-span-8 grid grid-cols-12 gap-4">
          <div className="col-span-12 xl:col-span-7 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="block text-[10px] font-bold text-[var(--text-primary)]">模板名称</label>
                <input
                  type="text"
                  value={draft.name}
                  onChange={(event) => updateDraft('name', event.target.value)}
                  className="w-full px-3 py-2 premium-input text-[11px] font-bold"
                  placeholder="例如：需求拆解 Prompt"
                />
              </div>
              <div className="space-y-1.5">
                <label className="block text-[10px] font-bold text-[var(--text-primary)]">scene</label>
                <input
                  type="text"
                  value={draft.scene}
                  onChange={(event) => updateDraft('scene', event.target.value)}
                  className="w-full px-3 py-2 premium-input text-[11px] font-mono"
                  placeholder="test_case_generation"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="block text-[10px] font-bold text-[var(--text-primary)]">variables</label>
              <input
                type="text"
                value={draft.variablesText}
                onChange={(event) => updateDraft('variablesText', event.target.value)}
                className="w-full px-3 py-2 premium-input text-[11px] font-mono"
                placeholder="requirement, project_name, risk_level"
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-[10px] font-bold text-[var(--text-primary)]">Prompt 内容</label>
              <textarea
                value={draft.content}
                onChange={(event) => updateDraft('content', event.target.value)}
                rows={12}
                className="w-full px-3 py-2 premium-input text-[11px] leading-relaxed font-mono resize-y min-h-[240px]"
                placeholder="请根据 {{requirement}} 生成结构化测试用例..."
              />
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
              <div className="flex items-center gap-2 text-[9px] font-bold text-[var(--text-secondary)]">
                {activeTemplate?.isBuiltin ? (
                  <span className="inline-flex items-center gap-1 text-emerald-500">
                    <CheckCircle className="size-3.5" />
                    系统内置模板
                  </span>
                ) : (
                  <span>{isNewTemplate ? '未保存草稿' : '自定义模板'}</span>
                )}
              </div>

              <div className="flex items-center gap-2">
                {activeTemplate?.isBuiltin ? (
                  <button
                    type="button"
                    disabled
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500/5 text-red-500/50 border border-red-500/10 rounded-lg text-[10px] font-bold cursor-not-allowed"
                  >
                    <Trash2 className="size-3.5" />
                    <span>内置模板不可删除</span>
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleDelete}
                    disabled={!canDelete || isDeleting}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-500 border border-red-500/15 rounded-lg text-[10px] font-bold cursor-pointer transition-all active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    {isDeleting ? <RefreshCw className="size-3.5 animate-spin" /> : <Trash2 className="size-3.5" />}
                    <span>删除</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={isSaving}
                  className="flex items-center gap-1.5 px-3 py-1.5 glow-button-neon text-white rounded-lg text-[10px] font-bold cursor-pointer transition-all active:scale-95 disabled:opacity-50"
                >
                  {isSaving ? <RefreshCw className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}
                  <span>{isNewTemplate ? '保存新增' : '保存修改'}</span>
                </button>
              </div>
            </div>
          </div>

          <div className="col-span-12 xl:col-span-5 space-y-3">
            <div className="rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)]/40 overflow-hidden">
              <div className="px-3 py-2 border-b border-[var(--border-color)] flex items-center justify-between">
                <span className="text-[10px] font-black text-[var(--text-primary)]">测试渲染</span>
                <button
                  type="button"
                  onClick={handleTestRender}
                  disabled={isTesting || !draft.id}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[var(--border-color)]/30 hover:bg-[var(--border-color)]/60 text-[9px] font-bold text-[var(--text-primary)] transition-all active:scale-95 cursor-pointer border border-[var(--border-color)] disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isTesting ? <RefreshCw className="size-3 animate-spin" /> : <Sparkles className="size-3" />}
                  <span>{draft.id ? '运行' : '先保存'}</span>
                </button>
              </div>

              <div className="p-3 space-y-3">
                <textarea
                  value={renderInput}
                  onChange={(event) => setRenderInput(event.target.value)}
                  rows={7}
                  className="w-full px-3 py-2 premium-input text-[10.5px] leading-relaxed font-mono resize-y min-h-[145px]"
                  placeholder={'{"requirement":"登录需求"}\n或 requirement=登录需求'}
                />

                {missingVariables.length > 0 && (
                  <div className="rounded-lg border border-amber-500/15 bg-amber-500/5 px-3 py-2 text-[9px] font-bold text-amber-500">
                    缺少变量：{missingVariables.join(', ')}
                  </div>
                )}

                <div className="rounded-lg border border-[#223049] bg-[#0b0f19] overflow-hidden">
                  <div className="px-3 py-2 bg-[#141b2a] border-b border-[#223049] flex items-center justify-between">
                    <span className="text-[9px] font-mono font-bold text-slate-500">rendered.prompt</span>
                    {rendered && <span className="text-[8px] font-black text-emerald-400">READY</span>}
                  </div>
                  <pre className="min-h-[190px] max-h-[300px] overflow-auto whitespace-pre-wrap break-words p-3 text-[10px] leading-relaxed font-mono text-slate-300">
                    {rendered || '保存模板后输入变量，运行测试渲染。'}
                  </pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
