import React from 'react';
import { BookOpen, FileText, CheckCircle2, ChevronRight } from 'lucide-react';
import usageTracker from '../analytics/usageTracker';

export default React.memo(function DegreeCard({ degree, onSelectDegree }) {
  const isMaster = (degree.nivel_academico || '').toLowerCase().includes('máster') || (degree.nivel_academico || '').toLowerCase().includes('master');
  const isDoctor = (degree.nivel_academico || '').toLowerCase().includes('doctor') || 
                   (degree.nivel_academico || '').toLowerCase().includes('99/2011') ||
                   (degree.titulo || '').toLowerCase().includes('doctor');

  const handleClick = () => {
    usageTracker.trackDegreeView(degree.codigo_estudio, degree.titulo);
    onSelectDegree(degree);
  };

  return (
    <div className="glass-panel" style={{
      padding: '1.35rem',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'space-between',
      height: '100%',
      position: 'relative'
    }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
          <span className={`badge ${isDoctor ? 'badge-doctor' : isMaster ? 'badge-master' : 'badge-grado'}`}>
            {isDoctor ? 'Doctorado' : isMaster ? 'Máster' : 'Grado Oficial'}
          </span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>
            {degree.codigo_estudio}
          </span>
        </div>

        <h3 style={{ fontSize: '1.05rem', fontWeight: 700, lineHeight: 1.35, marginBottom: '0.5rem' }}>
          {degree.titulo}
        </h3>

        {degree.universidad_nombre && (
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.75rem', fontWeight: 500 }}>
            {degree.universidad_nombre}
          </p>
        )}

        {/* ECTS Credit Price & Estimated Annual Tuition Badge (Phase 1 Part 3) */}
        {degree.precio_credito_ects && (
          <div style={{
            background: 'rgba(16, 185, 129, 0.08)',
            border: '1px solid rgba(16, 185, 129, 0.25)',
            borderRadius: 'var(--radius-sm)',
            padding: '0.45rem 0.65rem',
            marginBottom: '0.85rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '0.78rem'
          }}>
            <span style={{ color: 'var(--success)', fontWeight: 700 }}>💶 Matrícula Pública Estimada:</span>
            <span style={{ fontWeight: 800, color: 'var(--text-main)' }}>
              ~{Math.round(degree.precio_estimado_anual || (degree.precio_credito_ects * 60 + 45))} €/año
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 400, marginLeft: '0.35rem' }}>
                ({degree.precio_credito_ects} €/ECTS)
              </span>
            </span>
          </div>
        )}
      </div>

      <div style={{
        marginTop: '1.25rem',
        paddingTop: '0.75rem',
        borderTop: '1px solid var(--border-light)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.78rem', color: 'var(--success)' }}>
          <CheckCircle2 size={14} />
          <span>Verificado BOE</span>
        </div>

        <button 
          onClick={handleClick}
          className="btn btn-secondary" 
          style={{ padding: '0.4rem 0.85rem', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.25rem' }}
        >
          <span>Plan de Estudios</span>
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
});
