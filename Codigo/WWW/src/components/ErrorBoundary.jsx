import React from 'react';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });
    console.error('ErrorBoundary caught error:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div 
          role="alert" 
          aria-live="assertive"
          className="container"
          style={{
            padding: '3rem 1.5rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '50vh'
          }}
        >
          <div 
            className="glass-panel" 
            style={{ 
              maxWidth: '560px', 
              width: '100%', 
              padding: '2.5rem 2rem', 
              textAlign: 'center',
              borderTop: '4px solid var(--uca-gold)'
            }}
          >
            <div style={{
              display: 'inline-flex',
              padding: '0.85rem',
              borderRadius: '50%',
              background: 'rgba(243, 167, 18, 0.15)',
              color: 'var(--uca-gold)',
              marginBottom: '1.25rem'
            }}>
              <AlertTriangle size={36} />
            </div>

            <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--text-main)', marginBottom: '0.6rem' }}>
              Algo no funcionó como se esperaba
            </h2>

            <p style={{ color: 'var(--text-muted)', fontSize: '0.92rem', lineHeight: 1.6, marginBottom: '1.75rem' }}>
              Se ha producido un error inesperado al procesar esta sección. Puedes intentar restablecer la vista o volver a la página de inicio.
            </p>

            {this.state.error?.message && (
              <details style={{ textAlign: 'left', background: 'var(--bg-main)', padding: '0.75rem 1rem', borderRadius: 'var(--radius-sm)', marginBottom: '1.75rem', fontSize: '0.8rem', color: 'var(--text-muted)', cursor: 'pointer' }}>
                <summary style={{ fontWeight: 600, color: 'var(--text-main)' }}>Detalles técnicos del error</summary>
                <pre style={{ marginTop: '0.5rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'monospace' }}>
                  {this.state.error.message}
                </pre>
              </details>
            )}

            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center', flexWrap: 'wrap' }}>
              <button 
                type="button"
                className="btn btn-primary" 
                onClick={this.handleReset}
                style={{ padding: '0.6rem 1.25rem', fontSize: '0.88rem' }}
              >
                <RefreshCw size={16} /> Reintentar
              </button>

              <button 
                type="button"
                className="btn btn-outline" 
                onClick={() => { window.location.href = '/'; }}
                style={{ padding: '0.6rem 1.25rem', fontSize: '0.88rem' }}
              >
                <Home size={16} /> Ir al Inicio
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

