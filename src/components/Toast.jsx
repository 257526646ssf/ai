import React, { useState, useEffect } from 'react';
import { CheckCircle2, AlertTriangle, AlertCircle, Info, X } from 'lucide-react';

export default function Toast() {
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    const handleShowToast = (e) => {
      const { message, type = 'success', duration = 3000 } = e.detail || {};
      const id = Date.now() + Math.random().toString(36).substr(2, 5);
      
      const newToast = { id, message, type };
      setToasts(prev => [...prev, newToast]);

      // 定时删除
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id));
      }, duration);
    };

    window.addEventListener('show-toast', handleShowToast);
    return () => {
      window.removeEventListener('show-toast', handleShowToast);
    };
  }, []);

  const removeToast = (id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  const getToastStyles = (type) => {
    switch (type) {
      case 'success':
        return {
          icon: <CheckCircle2 className="size-4 text-emerald-500 shrink-0" />,
          classes: 'border-emerald-500/20 bg-emerald-500/5 text-emerald-500 dark:text-emerald-400'
        };
      case 'warning':
        return {
          icon: <AlertTriangle className="size-4 text-amber-500 shrink-0" />,
          classes: 'border-amber-500/20 bg-amber-500/5 text-amber-500 dark:text-amber-400'
        };
      case 'error':
        return {
          icon: <AlertCircle className="size-4 text-red-500 shrink-0" />,
          classes: 'border-red-500/20 bg-red-500/5 text-red-500 dark:text-red-400'
        };
      case 'info':
      default:
        return {
          icon: <Info className="size-4 text-blue-500 shrink-0" />,
          classes: 'border-blue-500/20 bg-blue-500/5 text-blue-500 dark:text-blue-400'
        };
    }
  };

  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-5 right-5 z-[9999] flex flex-col gap-2.5 max-w-sm pointer-events-none select-none">
      {toasts.map((toast) => {
        const styles = getToastStyles(toast.type);
        return (
          <div
            key={toast.id}
            className={`flex items-center gap-3 px-4 py-3 rounded-xl border shadow-lg pointer-events-auto backdrop-blur-md animate-[slideIn_0.2s_ease-out] ${styles.classes}`}
            style={{
              animation: 'slideIn 0.2s ease-out'
            }}
          >
            {styles.icon}
            <span className="text-[11px] font-bold text-left tracking-tight flex-1">
              {toast.message}
            </span>
            <button 
              onClick={() => removeToast(toast.id)}
              className="p-0.5 rounded-md hover:bg-black/10 dark:hover:bg-white/10 transition-colors shrink-0 cursor-pointer"
            >
              <X className="size-3 opacity-60 hover:opacity-100" />
            </button>
          </div>
        );
      })}

      <style dangerouslySetInnerHTML={{__html: `
        @keyframes slideIn {
          from {
            transform: translateX(100%) translateY(-10px);
            opacity: 0;
          }
          to {
            transform: translateX(0) translateY(0);
            opacity: 1;
          }
        }
      `}} />
    </div>
  );
}
