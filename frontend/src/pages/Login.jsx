import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { PrimaryButton } from '../components/PrimaryButton';
import { ShieldCheck, Lock, Mail, Eye, EyeOff, CheckCircle2 } from 'lucide-react';

// Matches backend/app/tasks/seed_users.py — one account per role, seeded for local dev.
const DEMO_PASSWORD = 'Password123!';

export const Login = () => {
  const { loginUser } = useApp();
  const [email, setEmail] = useState('admin@qemscorp.dev');
  const [password, setPassword] = useState(DEMO_PASSWORD);
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await loginUser(email, password);
    } catch (err) {
      setError(err.message || 'Login failed. Check your credentials.');
    } finally {
      setSubmitting(false);
    }
  };

  const fillDemo = (roleEmail) => {
    setEmail(roleEmail);
    setPassword(DEMO_PASSWORD);
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      position: 'relative',
      padding: '2rem'
    }}>
      <div className="glass-card" style={{
        maxWidth: '1000px',
        width: '100%',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
        gap: '2.5rem',
        padding: '3rem',
        borderRadius: '24px',
        position: 'relative',
        zIndex: 1
      }}>
        {/* Left Login Form */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem', color: 'var(--primary)' }}>
            <ShieldCheck size={36} />
            <h1 style={{ fontSize: '1.8rem', background: 'linear-gradient(135deg, var(--primary), var(--secondary))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>QEMS</h1>
          </div>

          <h2 style={{ fontSize: '1.5rem', marginBottom: '0.4rem', color: 'var(--text-main)' }}>Welcome Back 👋</h2>
          <p style={{ color: 'var(--text-muted)', marginBottom: '2rem', fontSize: '0.95rem' }}>Login to access your QA Error Dashboard</p>

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {error && (
              <div style={{
                background: 'var(--status-open-bg)',
                color: 'var(--status-open-text)',
                padding: '0.75rem 1rem',
                borderRadius: 'var(--radius-md)',
                fontSize: '0.85rem',
              }}>
                {error}
              </div>
            )}

            <div className="form-group">
              <label>Email Address</label>
              <div style={{ position: 'relative' }}>
                <input 
                  type="email" 
                  className="form-control" 
                  style={{ width: '100%', paddingLeft: '2.75rem' }} 
                  placeholder="name@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required 
                />
                <Mail size={18} style={{ position: 'absolute', left: '1rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
              </div>
            </div>

            <div className="form-group">
              <label>Password</label>
              <div style={{ position: 'relative' }}>
                <input 
                  type={showPassword ? 'text' : 'password'} 
                  className="form-control" 
                  style={{ width: '100%', paddingLeft: '2.75rem', paddingRight: '2.75rem' }} 
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required 
                />
                <Lock size={18} style={{ position: 'absolute', left: '1rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                <button 
                  type="button" 
                  onClick={() => setShowPassword(!showPassword)}
                  style={{ position: 'absolute', right: '1rem', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', color: 'var(--text-muted)' }}>
                <input 
                  type="checkbox" 
                  checked={rememberMe} 
                  onChange={(e) => setRememberMe(e.target.checked)} 
                />
                Remember me
              </label>
              <a href="#forgot" onClick={(e) => e.preventDefault()} style={{ color: 'var(--primary)', textDecoration: 'none', fontWeight: 600 }}>Forgot password?</a>
            </div>

            <div style={{ marginTop: '0.5rem' }}>
              <PrimaryButton type="submit" disabled={submitting} fullWidth size="lg">
                {submitting ? 'Signing In…' : 'Sign In to QEMS'}
              </PrimaryButton>
            </div>
          </form>

          {/* Quick Demo Fill Buttons */}
          <div style={{ marginTop: '2rem', paddingTop: '1.5rem', borderTop: '1px solid var(--border-light)' }}>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Demo Accounts</p>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <button type="button" className="btn-secondary" style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem' }} onClick={() => fillDemo('admin@qemscorp.dev')}>Admin</button>
              <button type="button" className="btn-secondary" style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem' }} onClick={() => fillDemo('qa@qemscorp.dev')}>QA Reviewer</button>
              <button type="button" className="btn-secondary" style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem' }} onClick={() => fillDemo('owner@qemscorp.dev')}>Dept Owner</button>
              <button type="button" className="btn-secondary" style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem' }} onClick={() => fillDemo('viewer@qemscorp.dev')}>Viewer</button>
            </div>
          </div>
        </div>

        {/* Right Feature Card */}
        <div style={{
          background: 'linear-gradient(135deg, rgba(123, 116, 129, 0.1), rgba(156, 148, 163, 0.1))',
          borderRadius: '16px',
          padding: '2.5rem',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center'
        }}>
          <h2 style={{ fontSize: '1.8rem', marginBottom: '1rem', lineHeight: 1.3 }}>Centralized Quality Error Management System</h2>
          <p style={{ color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: '2rem' }}>
            Seamlessly track operational mistakes, manage rebuttal disputes, auto-generate quality reports, and maintain regulatory compliance in real time.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {[
              'Real-time QA error logging & automated ID generation',
              'Collaborative rebuttal dispute management workflow',
              'Interactive analytical dashboards & trend visualizers',
              'Exportable audit reports for operations & executive teams'
            ].map((feature, idx) => (
              <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: 'var(--text-main)', fontSize: '0.95rem' }}>
                <CheckCircle2 size={20} color="#10b981" />
                <span>{feature}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
