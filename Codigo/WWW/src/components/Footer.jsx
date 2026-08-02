import React from 'react';
import { GraduationCap, ShieldCheck, Heart, Globe } from 'lucide-react';

export default function Footer({ onOpenAdmin }) {
  return (
    <footer style={{
      background: 'var(--uca-navy)',
      color: '#94A3B8',
      padding: '3rem 1.5rem 2rem 1.5rem',
      marginTop: '4rem',
      borderTop: '3px solid var(--uca-cyan)'
    }}>
      <div className="container" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '2rem', marginBottom: '2.5rem' }}>
        {/* Brand Column */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', color: '#FFFFFF', marginBottom: '0.85rem' }}>
            <GraduationCap size={26} color="var(--uca-azure)" />
            <span style={{ fontSize: '1.25rem', fontWeight: 800, letterSpacing: '-0.5px' }}>RUCT España</span>
          </div>
          <p style={{ fontSize: '0.88rem', lineHeight: 1.6, marginBottom: '1rem' }}>
            Portal universitario oficial desarrollado con la identidad visual y estilo de la <strong>Universidad de Cádiz (UCA)</strong> en Andalucía, España.
          </p>
        </div>

        {/* Quick Links */}
        <div>
          <h4 style={{ color: '#FFFFFF', fontSize: '1rem', fontWeight: 700, marginBottom: '1rem' }}>Enlaces Rápidos</h4>
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.88rem' }}>
            <li><a href="https://www.uca.es" target="_blank" rel="noreferrer" style={{ color: 'var(--uca-azure)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '0.35rem' }}><Globe size={14} /> Web Oficial Universidad de Cádiz</a></li>
            <li><a href="https://www.educacion.gob.es/ruct/home" target="_blank" rel="noreferrer" style={{ color: '#94A3B8', textDecoration: 'none' }}>Registro Oficial RUCT (Ministerio)</a></li>
            <li><a href="https://www.boe.es" target="_blank" rel="noreferrer" style={{ color: '#94A3B8', textDecoration: 'none' }}>Boletín Oficial del Estado (BOE)</a></li>
          </ul>
        </div>

        {/* Admin Section */}
        <div>
          <h4 style={{ color: '#FFFFFF', fontSize: '1rem', fontWeight: 700, marginBottom: '1rem' }}>Administración</h4>
          <p style={{ fontSize: '0.85rem', marginBottom: '0.85rem' }}>
            El acceso al panel de métricas de rendimiento y estadísticas está reservado exclusivamente para el Administrador de la Web.
          </p>
          <button className="btn btn-outline" style={{ padding: '0.45rem 0.85rem', fontSize: '0.8rem', color: 'var(--uca-sun)', borderColor: 'var(--uca-gold)' }} onClick={onOpenAdmin}>
            <ShieldCheck size={14} /> Acceso Administrador
          </button>
        </div>
      </div>

      <div className="container" style={{ borderTop: '1px solid rgba(255, 255, 255, 0.1)', paddingTop: '1.5rem', textAlign: 'center', fontSize: '0.82rem' }}>
        <p>© 2026 Proyecto Universitario RUCT. Diseñado con <Heart size={14} color="var(--uca-gold)" style={{ verticalAlign: 'middle' }} /> e inspirado en la Universidad de Cádiz (UCA).</p>
      </div>
    </footer>
  );
}
