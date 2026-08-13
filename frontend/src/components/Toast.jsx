import React from 'react';
import { useApp } from '../context/AppContext';
import { CheckCircle2, AlertCircle, Info } from 'lucide-react';

export const Toast = () => {
  const { toasts } = useApp();

  if (!toasts.length) return null;

  return (
    <div className="toast-container">
      {toasts.map(toast => {
        const isSuccess = toast.type === 'success';
        const isError = toast.type === 'error';

        return (
          <div key={toast.id} className={`toast toast-${toast.type}`}>
            {isSuccess && <CheckCircle2 size={20} color="#10b981" />}
            {isError && <AlertCircle size={20} color="#ef4444" />}
            {!isSuccess && !isError && <Info size={20} color="#7B7481" />}
            <span>{toast.message}</span>
          </div>
        );
      })}
    </div>
  );
};
