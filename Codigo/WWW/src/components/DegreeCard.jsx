import React from 'react';
import { CheckCircle2, ChevronRight } from 'lucide-react';
import usageTracker from '../analytics/usageTracker';

export default React.memo(function DegreeCard({ degree, onSelectDegree }) {
  const isMaster = (degree.nivel_academico || '').toLowerCase().includes('máster') || (degree.nivel_academico || '').toLowerCase().includes('master');
  const isDoctor = (degree.nivel_academico || '').toLowerCase().includes('doctor') || 
                   (degree.nivel_academico || '').toLowerCase().includes('99/2011') ||
                   (degree.titulo || '').toLowerCase().includes('doctor');
  const isInteruniv = (degree.titulo || '').toLowerCase().includes('interuniversitario') || 
                      (degree.origen_fuente || '').includes('interuniversitario') ||
                      (degree.titulo || '').toLowerCase().includes(' y la universidad') ||
                      (degree.titulo || '').toLowerCase().includes(' y la universitat');
  const isEuropean = degree.es_alianza_europea || 
                     (degree.origen_fuente || '').includes('alianza_europea') ||
                     (degree.plan_estudios?.tipo_estructura || '') === 'consorcio_europeo_erasmus_mundus' ||
                     (degree.titulo || '').toLowerCase().includes('erasmus mundus') ||
                     (degree.titulo || '').toLowerCase().includes('sea-eu');
  const isAffiliated = Boolean(degree.centro_adscrito) || 
                       (degree.origen_fuente || '').includes('centro_adscrito');
  const isExtinct = (degree.estado || '').toLowerCase().includes('extin') || 
                    (degree.estado || '').toLowerCase().includes('suprim') || 
                    (degree.estado || '').toLowerCase().includes('no vigente');

  const handleClick = () => {
    usageTracker.trackDegreeView(degree.codigo_estudio, degree.titulo);
    onSelectDegree(degree);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleClick();
    }
  };

  return (
    <div 
      className="glass-panel" 
      tabIndex={0}
      role="article"
      onKeyDown={handleKeyDown}
      style={{
        padding: '1.35rem',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        height: '100%',
        position: 'relative'
      }}
    >
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.35rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
            <span className={`badge ${isDoctor ? 'badge-doctorado' : isMaster ? 'badge-master' : 'badge-grado'}`}>
              {isDoctor ? 'Doctorado (RD 99/2011)' : isMaster ? 'Máster' : 'Grado Oficial'}
            </span>
            {isEuropean && (
              <span className="badge" style={{ background: 'rgba(14, 165, 233, 0.15)', color: '#0EA5E9', border: '1px solid rgba(14, 165, 233, 0.35)', fontSize: '0.7rem', fontWeight: 700 }}>
                🌍 Alianza Europea / Erasmus
              </span>
            )}
            {isAffiliated && (
              <span className="badge" style={{ background: 'rgba(139, 92, 246, 0.15)', color: '#8B5CF6', border: '1px solid rgba(139, 92, 246, 0.35)', fontSize: '0.7rem', fontWeight: 700 }}>
                🏛️ {degree.centro_adscrito || 'Centro Adscrito'}
              </span>
            )}
            {isInteruniv && (
              <span className="badge" style={{ background: 'rgba(99, 102, 241, 0.15)', color: '#6366F1', border: '1px solid rgba(99, 102, 241, 0.35)', fontSize: '0.7rem', fontWeight: 700 }}>
                🤝 Interuniversitario
              </span>
            )}
            {isExtinct && (
              <span className="badge" style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#D97706', border: '1px solid rgba(245, 158, 11, 0.35)', fontSize: '0.7rem', fontWeight: 700 }}>
                ⚠️ A extinguir
              </span>
            )}
          </div>
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

        {/* ECTS Credit Price & Estimated Annual Tuition Badge (Phase 1 Part 3 & Phase 2) */}
        {(degree.precio_credito_ects || degree.precio_estimado_anual) && (
          <div style={{
            background: 'rgba(16, 185, 129, 0.08)',
            border: '1px solid rgba(16, 185, 129, 0.25)',
            borderRadius: 'var(--radius-sm)',
            padding: '0.45rem 0.65rem',
            marginBottom: '0.85rem',
            fontSize: '0.78rem'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.2rem' }}>
              <span style={{ color: 'var(--success)', fontWeight: 700 }}>💶 1ª Matrícula:</span>
              <span style={{ fontWeight: 800, color: 'var(--text-main)' }}>
                ~{Math.round(parseFloat(degree.precio_estimado_anual) || ((parseFloat(degree.precio_credito_ects) || 0) * 60 + 45))} €/año
                {degree.precio_credito_ects && (
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 400, marginLeft: '0.35rem' }}>
                    ({degree.precio_credito_ects} €/c)
                  </span>
                )}
              </span>
            </div>
            
            {(degree.precio_credito_2 || degree.precio_credito_3 || degree.precio_credito_4) && (
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.4rem', paddingTop: '0.4rem', borderTop: '1px dashed rgba(16, 185, 129, 0.2)' }}>
                {degree.precio_credito_2 && <span>2ª: {degree.precio_credito_2}€</span>}
                {degree.precio_credito_3 && <span>3ª: {degree.precio_credito_3}€</span>}
                {degree.precio_credito_4 && <span>4ª: {degree.precio_credito_4}€</span>}
              </div>
            )}
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.75rem', color: 'var(--success)' }}>
            <CheckCircle2 size={14} />
            <span>BOE</span>
          </div>
          {degree.gestionado_por_admin && (
            <div title="Registro bloqueado y administrado manualmente (No sobrescribible por ETL)" style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.72rem', color: 'var(--uca-gold)', background: 'rgba(243, 167, 18, 0.1)', padding: '0.15rem 0.35rem', borderRadius: '4px' }}>
              <span>Bloqueado</span>
            </div>
          )}
        </div>

        <button 
          onClick={handleClick}
          className="btn btn-secondary" 
          style={{ padding: '0.4rem 0.85rem', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.25rem' }}
        >
          <span>{isDoctor ? 'Estructura Investigadora' : 'Plan de Estudios'}</span>
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
});
