import React, { useState } from 'react';
import { ShieldCheck, Lock, User, AlertCircle, GraduationCap } from 'lucide-react';

export default function AdminLogin({ onLoginSuccess }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    setError('');

    const ADMIN_USER = import.meta.env.VITE_ADMIN_USER || 'admin';
    if (username.trim() === ADMIN_USER && password.trim() !== '') {
      // Almacenamos la contraseña como API Key para las peticiones CRUD y ETL.
      // La validación real la hará el backend al enviar la cabecera X-API-Key.
      sessionStorage.setItem('adminApiKey', password.trim());
      onLoginSuccess();
    } else {
      setError('Credenciales de administrador incorrectas o API Key vacía. Acceso restringido únicamente al Administrador.');
    }
  };

  return (
    <div style={{
      minHeight: '80vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '2.5rem 1.5rem'
    }}>
      <div className="glass-panel" style={{ width: '100%', maxWidth: '440px', padding: '0', overflow: 'hidden', boxShadow: 'var(--shadow-lg)' }}>
        {/* Header */}
        <div style={{
          background: 'linear-gradient(135deg, var(--uca-navy) 0%, var(--uca-blue) 100%)',
          color: '#FFFFFF',
          padding: '2rem 1.75rem',
          textAlign: 'center'
        }}>
          <div style={{ display: 'inline-flex', padding: '0.75rem', background: 'rgba(255, 255, 255, 0.15)', borderRadius: '12px', color: 'var(--uca-sun)', marginBottom: '0.85rem' }}>
            <ShieldCheck size={32} />
          </div>
          <h3 style={{ fontSize: '1.4rem', fontWeight: 800 }}>Acceso de Administrador</h3>
          <p style={{ fontSize: '0.85rem', color: '#CBD5E1', marginTop: '0.35rem' }}>UniHub - Panel Interno de Rendimiento</p>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} style={{ padding: '2rem 1.75rem' }}>
          <div style={{ fontSize: '0.88rem', color: 'var(--text-muted)', marginBottom: '1.5rem', lineHeight: 1.5 }}>
            El resto de usuarios que visitan la web son <strong>usuarios no registrados</strong>. Esta página requiere autenticación privilegiada.
          </div>

          {error && (
            <div style={{
              background: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              padding: '0.85rem 1rem',
              borderRadius: 'var(--radius-sm)',
              color: '#EF4444',
              fontSize: '0.85rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              marginBottom: '1.25rem'
            }}>
              <AlertCircle size={18} />
              <span>{error}</span>
            </div>
          )}

          {/* Username Input */}
          <div style={{ marginBottom: '1.25rem' }}>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '0.4rem' }}>
              Usuario Administrador
            </label>
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <User size={18} color="var(--text-light)" style={{ position: 'absolute', left: '12px' }} />
              <input 
                type="text"
                placeholder="Usuario ('admin')"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                style={{
                  width: '100%',
                  padding: '0.75rem 0.75rem 0.75rem 2.5rem',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-light)',
                  background: 'var(--bg-main)',
                  color: 'var(--text-main)',
                  outline: 'none',
                  fontSize: '0.95rem'
                }}
              />
            </div>
          </div>

          {/* Password Input */}
          <div style={{ marginBottom: '1.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '0.4rem' }}>
              Contraseña
            </label>
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <Lock size={18} color="var(--text-light)" style={{ position: 'absolute', left: '12px' }} />
              <input 
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                style={{
                  width: '100%',
                  padding: '0.75rem 0.75rem 0.75rem 2.5rem',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-light)',
                  background: 'var(--bg-main)',
                  color: 'var(--text-main)',
                  outline: 'none',
                  fontSize: '0.95rem'
                }}
              />
            </div>
          </div>

          {/* Submit Button */}
          <button 
            type="submit" 
            className="btn btn-primary" 
            style={{ width: '100%', padding: '0.85rem', fontSize: '0.95rem', fontWeight: 700 }}
          >
            Iniciar Sesión como Administrador
          </button>
        </form>
      </div>
    </div>
  );
}
