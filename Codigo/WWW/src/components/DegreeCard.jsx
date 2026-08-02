import React from 'react';
import { BookOpen, FileText, CheckCircle2, ChevronRight } from 'lucide-react';
import usageTracker from '../analytics/usageTracker';

export default function DegreeCard({ degree, onSelectDegree }) {
  const isMaster = (degree.nivel_academico || '').toLowerCase().includes('máster') || (degree.nivel_academico || '').toLowerCase().includes('master');
  const isDoctor = (degree.nivel_academico || '').toLowerCase().includes('doctor');

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
      transition: 'transform 0.25s ease, box-shadow 0.25s ease',
      cursor: 'pointer'
    }}
    onClick={handleClick}
    onMouseEnter={(e) => {
      e.currentTarget.style.transform = 'translateY(-3px)';
      e.currentTarget.style.boxShadow = 'var(--shadow-md)';
    }}
    onMouseLeave={(e) => {
      e.currentTarget.style.transform = 'translateY(0)';
      e.currentTarget.style.boxShadow = 'var(--shadow-sm)';
    }}
    >
      <div>
        {/* Header Badges */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-light)', background: 'var(--bg-main)', padding: '0.2rem 0.6rem', borderRadius: '6px' }}>
            RUCT {degree.codigo_estudio}
          </span>
          <span className={`badge ${isMaster ? 'badge-master' : isDoctor ? 'badge-privada' : 'badge-grado'}`}>
            {isMaster ? 'Máster' : isDoctor ? 'Doctorado' : 'Grado'}
          </span>
        </div>

        {/* Degree Title */}
        <h4 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.6rem', lineHeight: 1.35 }}>
          {degree.titulo}
        </h4>

        {/* Academic Level & Status */}
        <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: '1rem', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
          {degree.nivel_academico && (
            <div><strong style={{ color: 'var(--text-main)' }}>Plan:</strong> {degree.nivel_academico}</div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: '#10B981', fontWeight: 600 }}>
            <CheckCircle2 size={14} /> Vigente en B.O.E.
          </div>
        </div>
      </div>

      {/* Action Link */}
      <div style={{
        paddingTop: '0.75rem',
        borderTop: '1px solid var(--border-light)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        color: 'var(--uca-cyan)',
        fontWeight: 600,
        fontSize: '0.85rem'
      }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
          <FileText size={15} /> Ver Plan de Estudios (BOE)
        </span>
        <ChevronRight size={16} />
      </div>
    </div>
  );
}
