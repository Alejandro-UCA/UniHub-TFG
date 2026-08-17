import React, { useEffect, useState } from 'react';
import { X, FileText, ExternalLink, Award, Layers, AlertTriangle } from 'lucide-react';
import { apiService } from '../services/api';

export default function PlanModal({ degree, onClose }) {
  const [loading, setLoading] = useState(true);
  const [planData, setPlanData] = useState(null);
  const [error, setError] = useState(null);

  const isExtinct = (degree?.estado || '').toLowerCase().includes('extin') || 
                    (degree?.estado || '').toLowerCase().includes('suprim') || 
                    (degree?.estado || '').toLowerCase().includes('no vigente');

  // Manejador de la tecla Escape para accesibilidad (A11y)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Bloquear scroll del body mientras el modal está abierto
  useEffect(() => {
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prevOverflow; };
  }, []);

  useEffect(() => {
    async function loadCurriculum() {
      if (!degree || !degree.codigo_estudio) return;
      setLoading(true);
      setError(null);

      try {
        const data = await apiService.getDegreeCurriculum(degree.codigo_estudio);
        setPlanData(data);
      } catch (err) {
        console.warn('Could not load curriculum from API, displaying local fallback:', err);
        setError('No se pudo conectar a la API o el plan de estudios está en proceso de digitalización.');
      } finally {
        setLoading(false);
      }
    }

    loadCurriculum();
  }, [degree]);

  if (!degree) return null;

  const curriculum = planData?.plan_estudios ? planData.plan_estudios : (planData || {});
  const elementos = curriculum.elementos_curriculares || [];
  const resumen = curriculum.resumen_creditos || {};
  const boeUrl = planData?.boe_url || degree.boe_url;
  const boeFecha = planData?.boe_fecha || degree.boe_fecha;

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div style={{
          background: 'linear-gradient(135deg, var(--uca-navy) 0%, var(--uca-blue) 100%)',
          color: '#FFFFFF',
          padding: '1.5rem 1.75rem',
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          borderTopLeftRadius: 'var(--radius-lg)',
          borderTopRightRadius: 'var(--radius-lg)'
        }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
              <span className="badge badge-grado">Titulación Oficial</span>
              {boeFecha && <span className="badge" style={{ background: 'rgba(243, 167, 18, 0.2)', color: 'var(--uca-sun)' }}>BOE: {boeFecha}</span>}
            </div>
            <h2 style={{ fontSize: '1.35rem', fontWeight: 800, lineHeight: 1.3 }}>{degree.titulo}</h2>
            {degree.universidad_nombre && (
              <p style={{ fontSize: '0.88rem', color: '#CBD5E1', marginTop: '0.25rem' }}>{degree.universidad_nombre}</p>
            )}
          </div>
          <button 
            onClick={onClose}
            aria-label="Cerrar modal"
            style={{
              background: 'rgba(255, 255, 255, 0.15)',
              border: 'none',
              color: '#FFFFFF',
              borderRadius: '50%',
              width: '36px',
              height: '36px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'background 0.2s'
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.3)'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.15)'}
          >
            <X size={20} />
          </button>
        </div>

        {/* Modal Body */}
        <div style={{ padding: '1.75rem' }}>
          {/* Extinction Alert Banner */}
          {isExtinct && (
            <div style={{
              background: 'rgba(245, 158, 11, 0.12)',
              border: '1px solid rgba(245, 158, 11, 0.35)',
              padding: '1rem 1.25rem',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.85rem',
              marginBottom: '1.5rem',
              color: '#B45309'
            }}>
              <AlertTriangle size={22} style={{ flexShrink: 0, marginTop: '2px' }} />
              <div>
                <div style={{ fontWeight: 800, fontSize: '0.95rem', marginBottom: '0.2rem' }}>
                  ⚠️ Titulación oficial en proceso de extinción
                </div>
                <div style={{ fontSize: '0.85rem', lineHeight: 1.45, color: 'var(--text-main)' }}>
                  Este plan de estudios no admite nuevos estudiantes de primer ingreso (título suprimido o en fase de sustitución). Se mantiene registrado en el catálogo ministerial oficial exclusivamente a efectos de convocatorias de examen, docencia residual y convalidaciones para alumnos ya matriculados.
                </div>
              </div>
            </div>
          )}

          {/* BOE Document Button */}
          {boeUrl && (
            <div style={{
              background: 'rgba(0, 132, 200, 0.08)',
              border: '1px solid var(--border-uca)',
              padding: '1rem 1.25rem',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '1.75rem'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <FileText size={24} color="var(--uca-cyan)" />
                <div>
                  <div style={{ fontWeight: 700, fontSize: '0.95rem' }}>Boletín Oficial del Estado (BOE)</div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Documento oficial con la última modificación del plan de estudios.</div>
                </div>
              </div>
              <a 
                href={boeUrl} 
                target="_blank" 
                rel="noreferrer" 
                className="btn btn-primary"
                style={{ padding: '0.5rem 1.25rem', fontSize: '0.85rem' }}
              >
                Abrir PDF en BOE <ExternalLink size={14} />
              </a>
            </div>
          )}

          {loading ? (
            <div style={{ textAlign: 'center', padding: '3rem 0', color: 'var(--text-muted)' }}>
              <div style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.5rem' }}>Cargando plan de estudios del BOE...</div>
              <div style={{ fontSize: '0.85rem' }}>Analizando asignaturas, créditos ECTS y módulos...</div>
            </div>
          ) : error ? (
            <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', padding: '1.25rem', borderRadius: 'var(--radius-md)', color: '#EF4444', fontSize: '0.9rem' }}>
              {error}
            </div>
          ) : (
            <>
              {/* Credit Summaries */}
              {Object.keys(resumen).length > 0 && (
                <div style={{ marginBottom: '2rem' }}>
                  <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Award size={18} color="var(--uca-gold)" /> Resumen de Créditos ECTS
                  </h3>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.85rem' }}>
                    {Object.entries(resumen).map(([k, v], idx) => (
                      <div key={idx} style={{ background: 'var(--bg-main)', padding: '0.85rem 1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>{k}</div>
                        <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--uca-blue)' }}>{v} ECTS</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Subjects & Modules Breakdown */}
              <div>
                <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Layers size={18} color="var(--uca-cyan)" /> Estructura de Asignaturas, Módulos y Materias ({elementos.length})
                </h3>

                {elementos.length === 0 ? (
                  <div style={{
                    padding: '2rem 1.5rem',
                    background: 'var(--bg-main)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px dashed var(--border-light)',
                    textAlign: 'center'
                  }}>
                    <div style={{ display: 'inline-flex', padding: '0.75rem', background: 'rgba(243, 167, 18, 0.12)', borderRadius: '50%', color: 'var(--uca-sun)', marginBottom: '1rem' }}>
                      <FileText size={28} />
                    </div>
                    <h4 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--text-main)' }}>
                      No se ha encontrado un plan de estudios desglosado en el BOE
                    </h4>
                    <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)', maxWidth: '580px', margin: '0 auto 1.25rem auto', lineHeight: 1.5 }}>
                      Esta titulación oficial puede corresponder a un programa de Doctorado (que carece de asignaturas lectivas tradicionales), a una titulación de reciente implantación o a una universidad privada cuyos planes detallados se gestionan directamente en su propio portal docente.
                    </p>
                    {boeUrl && (
                      <a
                        href={boeUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="btn btn-outline"
                        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}
                      >
                        <FileText size={16} /> Consultar Resolución en BOE <ExternalLink size={14} />
                      </a>
                    )}
                  </div>
                ) : (
                  <div style={{ overflowX: 'auto', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-md)' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88rem', textAlign: 'left' }}>
                      <thead>
                        <tr style={{ background: 'var(--uca-navy)', color: '#FFFFFF' }}>
                          <th style={{ padding: '0.75rem 1rem' }}>Módulo / Materia</th>
                          <th style={{ padding: '0.75rem 1rem' }}>Nombre Elemento / Asignatura</th>
                          <th style={{ padding: '0.75rem 1rem' }}>ECTS</th>
                          <th style={{ padding: '0.75rem 1rem' }}>Carácter</th>
                          <th style={{ padding: '0.75rem 1rem' }}>Curso</th>
                          <th style={{ padding: '0.75rem 1rem' }}>Cuatrimestre</th>
                        </tr>
                      </thead>
                      <tbody>
                        {elementos.map((elem, idx) => (
                          <tr key={idx} style={{ borderBottom: '1px solid var(--border-light)', background: idx % 2 === 0 ? 'transparent' : 'rgba(0, 132, 200, 0.03)' }}>
                            <td style={{ padding: '0.65rem 1rem', fontSize: '0.82rem', color: 'var(--text-muted)' }}>{elem.materia || elem.modulo || '-'}</td>
                            <td style={{ padding: '0.65rem 1rem', fontWeight: 600 }}>{elem.nombre_elemento}</td>
                            <td style={{ padding: '0.65rem 1rem', fontWeight: 700, color: 'var(--uca-blue)' }}>{elem.creditos_ects || '-'}</td>
                            <td style={{ padding: '0.65rem 1rem' }}>
                              <span className="badge" style={{ background: 'rgba(0, 132, 200, 0.1)', color: 'var(--uca-cyan)' }}>
                                {elem.caracter || 'OB'}
                              </span>
                            </td>
                            <td style={{ padding: '0.65rem 1rem' }}>{elem.curso || '-'}</td>
                            <td style={{ padding: '0.65rem 1rem' }}>{elem.cuatrimestre || '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
