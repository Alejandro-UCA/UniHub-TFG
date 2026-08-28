import React from 'react';
import { MapPin, Globe, Mail, BookOpen, ExternalLink } from 'lucide-react';
import usageTracker from '../analytics/usageTracker';

export default React.memo(function UnivCard({ univ, onViewDegrees, distanceKm }) {
  const isPrivada = (univ?.tipo || '').toLowerCase().includes('privada');
  const univName = univ?.nombre || 'Universidad sin nombre';
  const univCode = univ?.codigo || '';

  const handleClick = () => {
    if (univCode) {
      usageTracker.trackUniversityView(univCode, univName);
    }
    if (onViewDegrees) {
      onViewDegrees(univ);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleClick();
    }
  };

  // Safe external URL helper preventing javascript: and data: URIs
  const getSafeWebUrl = (url) => {
    if (!url) return null;
    const clean = url.trim();
    if (/^https?:\/\//i.test(clean)) return clean;
    if (/^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/i.test(clean)) return `https://${clean}`;
    return null;
  };

  const safeWebUrl = getSafeWebUrl(univ?.web);

  return (
    <div 
      className="glass-panel card-hover" 
      tabIndex={0}
      role="article"
      aria-label={`Ficha de ${univName}`}
      onKeyDown={handleKeyDown}
      style={{
        padding: '1.5rem',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        height: '100%'
      }}
      onClick={handleClick}
    >
      <div>
        {/* Card Header: Type Badge & Optional Distance */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem', gap: '0.5rem' }}>
          <span className={`badge ${isPrivada ? 'badge-privada' : 'badge-publica'}`}>
            {isPrivada ? 'Privada' : 'Pública'}
          </span>
          {distanceKm !== undefined && distanceKm !== null && (
            <span style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--uca-sun)', background: 'rgba(243, 167, 18, 0.15)', padding: '0.2rem 0.6rem', borderRadius: '6px', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
              <MapPin size={14} /> {distanceKm} km
            </span>
          )}
        </div>

        {/* University Name */}
        <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.75rem', lineHeight: 1.3 }}>
          {univName}
        </h3>

        {/* Location & Details */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', fontSize: '0.88rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
          {univ?.comunidad_autonoma && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <MapPin size={16} color="var(--uca-cyan)" />
              <span>{univ.municipio ? `${univ.municipio}, ` : ''}{univ.comunidad_autonoma}</span>
            </div>
          )}

          {safeWebUrl && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Globe size={16} color="var(--uca-azure)" />
              <a 
                href={safeWebUrl} 
                target="_blank" 
                rel="noopener noreferrer"
                style={{ color: 'var(--uca-cyan)', textDecoration: 'none' }}
                onClick={(e) => e.stopPropagation()}
                aria-label={`Visitar sitio web oficial de ${univName}`}
              >
                {univ.web.replace(/^https?:\/\//, '')}
              </a>
            </div>
          )}

          {univ?.email && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Mail size={16} color="var(--text-light)" />
              <a 
                href={`mailto:${univ.email}`}
                style={{ fontSize: '0.82rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'inherit', textDecoration: 'none' }}
                onClick={(e) => e.stopPropagation()}
                aria-label={`Enviar correo a ${univ.email}`}
              >
                {univ.email}
              </a>
            </div>
          )}
        </div>
      </div>

      {/* Action Footer */}
      <div style={{
        paddingTop: '0.85rem',
        borderTop: '1px solid var(--border-light)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--uca-cyan)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <BookOpen size={15} /> Ver titulaciones vigentes
          </span>
          {univ?.gestionado_por_admin && (
            <div title="Registro bloqueado y administrado manualmente (No sobrescribible por ETL)" style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.72rem', color: 'var(--uca-gold)', background: 'rgba(243, 167, 18, 0.1)', padding: '0.15rem 0.35rem', borderRadius: '4px' }}>
              <span>Bloqueado</span>
            </div>
          )}
        </div>
        <ExternalLink size={16} color="var(--text-light)" />
      </div>
    </div>
  );
});
