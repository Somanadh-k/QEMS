import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import * as api from '../api/client';
import { getAccessToken, clearTokens, setTokens, SessionExpiredError } from '../api/client';
import { mapListItem, mapDetail } from '../api/mappers';

const AppContext = createContext();

// No stock photo by default — Avatar falls back to initials until the user picks a real one.
const DEFAULT_AVATAR = null;

export const AppProvider = ({ children }) => {
  const [isLoggedIn, setIsLoggedIn] = useState(() => !!getAccessToken());
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('qems_user');
    return saved ? JSON.parse(saved) : null;
  });

  const [errors, setErrors] = useState([]);
  const [errorsLoading, setErrorsLoading] = useState(false);

  const [selectedErrorId, setSelectedErrorId] = useState(null);
  const [selectedError, setSelectedError] = useState(null);
  const [errorDetailLoading, setErrorDetailLoading] = useState(false);

  const [departments, setDepartments] = useState([]);
  const [categories, setCategories] = useState([]);
  const [processes, setProcesses] = useState([]);
  const [users, setUsers] = useState([]);

  const [activeTab, setActiveTab] = useState(() => (isLoggedIn ? 'dashboard' : 'login'));
  const [searchQuery, setSearchQuery] = useState('');
  const [theme, setTheme] = useState(() => localStorage.getItem('qems_theme') || 'light');
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((message, type = 'info') => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3500);
  }, []);

  const logoutUser = useCallback(() => {
    clearTokens();
    localStorage.removeItem('qems_user');
    setIsLoggedIn(false);
    setUser(null);
    setErrors([]);
    setSelectedError(null);
    setActiveTab('login');
  }, []);

  const handleApiError = useCallback(
    (err, fallbackMessage) => {
      if (err instanceof SessionExpiredError) {
        addToast('Your session expired. Please log in again.', 'error');
        logoutUser();
        return;
      }
      addToast(err.message || fallbackMessage, 'error');
    },
    [addToast, logoutUser]
  );

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('qems_theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'light' ? 'dark' : 'light'));
    addToast(`Switched to ${theme === 'light' ? 'Dark' : 'Light'} Mode`, 'info');
  };

  useEffect(() => {
    if (user) localStorage.setItem('qems_user', JSON.stringify(user));
  }, [user]);

  const loadLookups = useCallback(async () => {
    try {
      const [deps, cats, usrs, procs] = await Promise.all([
        api.listDepartments(),
        api.listCategories(),
        api.listUsers(),
        api.listProcesses(),
      ]);
      setDepartments(deps);
      setCategories(cats);
      setUsers(usrs);
      setProcesses(procs);
      return { departments: deps, categories: cats, users: usrs, processes: procs };
    } catch (err) {
      handleApiError(err, 'Failed to load reference data.');
      return { departments: [], categories: [], users: [], processes: [] };
    }
  }, [handleApiError]);

  // Dashboard/QA-Errors-list totals are derived client-side by filtering this array, so
  // it has to hold every record rather than just the first page -- a hard-coded
  // page_size:100 with `res.total` discarded meant every KPI tile went silently wrong
  // past 100 errors (finding D-01). page_size:100 is the API's own max, so this loops
  // pages rather than requesting a bigger one. MAX_PAGES is a sanity cap, not a real
  // limit: it stops a runaway loop rather than being expected to bind in practice.
  const PAGE_SIZE = 100;
  const MAX_PAGES = 50; // 5,000 records
  const fetchErrorsWith = useCallback(
    async (lookups) => {
      setErrorsLoading(true);
      try {
        const items = [];
        let page = 1;
        let total = Infinity;
        while (items.length < total && page <= MAX_PAGES) {
          const res = await api.listErrors({ page, page_size: PAGE_SIZE });
          items.push(...res.items);
          total = res.total;
          if (res.items.length === 0) break; // defensive: avoid an infinite loop
          page += 1;
        }
        setErrors(items.map((item) => mapListItem(item, lookups)));
      } catch (err) {
        handleApiError(err, 'Failed to load QA errors.');
      } finally {
        setErrorsLoading(false);
      }
    },
    [handleApiError]
  );

  const refreshErrors = useCallback(
    () => fetchErrorsWith({ departments, categories }),
    [fetchErrorsWith, departments, categories]
  );

  // Restore session on reload: if a token is already saved, reload lookups + errors.
  useEffect(() => {
    if (isLoggedIn) {
      (async () => {
        const lookups = await loadLookups();
        await fetchErrorsWith(lookups);
      })();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loginUser = async (email, password) => {
    const res = await api.login(email, password);
    setTokens(res.access_token, res.refresh_token);

    const loggedInUser = {
      user_id: res.user.user_id,
      name: res.user.full_name,
      email: res.user.email,
      roles: res.user.roles,
      role: res.user.roles[0] || 'User',
      department_id: res.user.department_id,
      avatar: DEFAULT_AVATAR,
      phone: '',
      employeeId: `EMP-${String(res.user.user_id).padStart(3, '0')}`,
      address: '',
    };
    setUser(loggedInUser);
    setIsLoggedIn(true);
    setActiveTab('dashboard');
    addToast(`Welcome back, ${loggedInUser.name}!`, 'success');

    const lookups = await loadLookups();
    const departmentName = lookups.departments.find((d) => d.department_id === loggedInUser.department_id)?.name;
    if (departmentName) {
      setUser((prev) => ({ ...prev, department: departmentName }));
    }
    await fetchErrorsWith(lookups);
  };

  const addError = async (payload) => {
    const created = await api.createError(payload);
    addToast(`QA Error ${created.qa_error_code} created successfully!`, 'success');
    await refreshErrors();
    return created;
  };

  const loadErrorDetail = useCallback(
    async (qaErrorCodeOrPk) => {
      const match = errors.find((e) => e.id === qaErrorCodeOrPk || e.pk === qaErrorCodeOrPk);
      const pk = match ? match.pk : qaErrorCodeOrPk;
      if (!pk) return;
      setErrorDetailLoading(true);
      try {
        const detail = await api.getError(pk);
        setSelectedError(mapDetail(detail, { departments, categories, users }));
      } catch (err) {
        handleApiError(err, 'Failed to load error details.');
      } finally {
        setErrorDetailLoading(false);
      }
    },
    [errors, departments, categories, users, handleApiError]
  );

  const transitionErrorStatus = async (pk, newStatus, adminOverride = false) => {
    try {
      await api.updateErrorStatus(pk, newStatus, adminOverride);
      addToast(`Status updated to "${newStatus}".`, 'success');
      await Promise.all([refreshErrors(), loadErrorDetail(pk)]);
    } catch (err) {
      handleApiError(err, 'Failed to update status.');
    }
  };

  const addRebuttal = async (pk, text) => {
    try {
      await api.submitRebuttal(pk, text);
      addToast('Rebuttal submitted.', 'success');
      await Promise.all([refreshErrors(), loadErrorDetail(pk)]);
    } catch (err) {
      handleApiError(err, 'Failed to submit rebuttal.');
    }
  };

  const recordDecision = async (pk, decision, notes) => {
    try {
      await api.recordDecision(pk, decision, notes);
      addToast(`Decision recorded: ${decision}.`, 'success');
      await Promise.all([refreshErrors(), loadErrorDetail(pk)]);
    } catch (err) {
      handleApiError(err, 'Failed to record decision.');
    }
  };

  return (
    <AppContext.Provider
      value={{
        errors,
        errorsLoading,
        selectedError,
        errorDetailLoading,
        loadErrorDetail,
        user,
        setUser,
        activeTab,
        setActiveTab,
        selectedErrorId,
        setSelectedErrorId,
        searchQuery,
        setSearchQuery,
        theme,
        toggleTheme,
        toasts,
        addToast,
        departments,
        categories,
        users,
        addError,
        transitionErrorStatus,
        addRebuttal,
        recordDecision,
        processes,
        loginUser,
        logoutUser,
      }}
    >
      {children}
    </AppContext.Provider>
  );
};

export const useApp = () => useContext(AppContext);
