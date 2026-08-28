import React, { useEffect } from 'react';
import { X, BookOpen, User, ExternalLink, Bookmark, Globe } from 'lucide-react';

export default function SubjectDetailModal({ subject, degree, onClose }) {
  // Manejo de la tecla Escape para accesibilidad
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Lock body scroll safely
  useEffect(() => {
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prevOverflow; };
  }, []);

  if (!subject) return null;

  const getSafeUrl = (url) => {
    if (!url) return null;
    const clean = url.trim();
    if (/^https?:\/\//i.test(clean)) return clean;
    return null;
  };

  const guia = subject.guia_docente || {};
  const temarioList = subject.temario || guia.temario || [];
  const evalList = subject.sistema_evaluacion || guia.sistema_evaluacion || [];
  const profList = subject.profesorado || guia.profesorado || [];
  const bibList = subject.bibliografia || guia.bibliografia || [];
  const criteriosEval = subject.criterios_evaluacion || guia.criterios_evaluacion;
  const guideUrl = getSafeUrl(subject.url_guia_docente || guia.url_guia_docente);
  const idioma = subject.idioma || guia.idioma || 'Castellano';
  const departamento = subject.departamento || guia.departamento || (subject.materia || subject.modulo || 'No especificado');
  const area = guia.area_conocimiento;
  const crTeoria = subject.creditos_teoria || guia.creditos?.teoria;
  const crPractica = subject.creditos_practica || guia.creditos?.practicas;

  return (
    <div 
      className="modal-overlay" 
      onClick={onClose} 
      role="dialog" 
      aria-modal="true" 
      aria-labelledby="subject-modal-title"
      style={{ zIndex: 1100 }}
    >
      <div 
        className="modal-content" 
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: '850px', maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}
      >
        {/* Header con gradiente institucional UCA */}
        <div style={{
          background: 'linear-gradient(135deg, var(--uca-navy) 0%, var(--uca-blue) 100%)',
          color: '#FFFFFF',
          padding: '1.5rem 1.75rem',
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          borderTopLeftRadius: 'var(--radius-lg)',
          borderTopRightRadius: 'var(--radius-lg)',
          flexShrink: 0
        }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem', flexWrap: 'wrap' }}>
              <span className="badge" style={{ background: 'rgba(255, 255, 255, 0.2)', color: '#FFFFFF', fontWeight: 700 }}>
                {subject.caracter || 'N/D'} · {subject.creditos_ects || 'N/D'} ECTS
              </span>
              {subject.curso && (
                <span className="badge" style={{ background: 'rgba(243, 167, 18, 0.25)', color: 'var(--uca-sun)', fontWeight: 700 }}>
                  {subject.curso}º Curso
                </span>
              )}
              {subject.cuatrimestre && (
                <span className="badge" style={{ background: 'rgba(0, 132, 200, 0.25)', color: 'var(--uca-cyan)', fontWeight: 600 }}>
                  {subject.cuatrimestre}
                </span>
              )}
              <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.2)', color: '#A7F3D0', display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
                <Globe size={11} /> {idioma}
              </span>
            </div>

            <h2 id="subject-modal-title" style={{ fontSize: '1.35rem', fontWeight: 800, lineHeight: 1.25, margin: 0 }}>
              {subject.nombre_elemento}
            </h2>

            {degree?.titulo && (
              <p style={{ fontSize: '0.85rem', color: '#CBD5E1', marginTop: '0.35rem', marginBottom: 0 }}>
                {degree.titulo} {degree.universidad_nombre ? `· ${degree.universidad_nombre}` : ''}
              </p>
            )}
          </div>

          <button 
            onClick={onClose}
            aria-label="Cerrar ficha de asignatura"
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
              flexShrink: 0,
              transition: 'background 0.2s'
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.3)'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.15)'}
          >
            <X size={20} />
          </button>
        </div>

        {/* Cuerpo con scroll */}
        <div style={{ padding: '1.5rem 1.75rem', overflowY: 'auto', flexGrow: 1 }}>
          {/* Quick Stats Grid */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: '0.85rem',
            marginBottom: '1.5rem'
          }}>
            <div style={{ background: 'var(--bg-main)', padding: '0.85rem 1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-light)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', marginBottom: '0.2rem' }}>
                Carga Lectiva
              </div>
              <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--uca-blue)' }}>
                {subject.creditos_ects || 'N/D'} ECTS
              </div>
              {(crTeoria || crPractica) && (
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.15rem' }}>
                  {crTeoria ? `${crTeoria}h Teoría` : ''} {crPractica ? `· ${crPractica}h Prácticas` : ''}
                </div>
              )}
            </div>

            <div style={{ background: 'var(--bg-main)', padding: '0.85rem 1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-light)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', marginBottom: '0.2rem' }}>
                Departamento / Área
              </div>
              <div style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-main)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={departamento}>
                {departamento}
              </div>
              {area && (
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.15rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {area}
                </div>
              )}
            </div>

            <div style={{ background: 'var(--bg-main)', padding: '0.85rem 1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-light)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', marginBottom: '0.2rem' }}>
                Carácter Académico
              </div>
              <div style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-main)' }}>
                {subject.caracter === 'FB' ? 'Formación Básica' :
                 subject.caracter === 'OB' ? 'Obligatoria' :
                 subject.caracter === 'OP' ? 'Optativa' :
                 subject.caracter === 'TFG' ? 'Trabajo Fin de Grado' :
                 subject.caracter === 'PE' ? 'Prácticas Externas' : (subject.caracter || 'Obligatoria')}
              </div>
            </div>
          </div>

          {/* Bloque 1: Temario Oficial */}
          <div style={{ marginBottom: '1.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.85rem', color: 'var(--uca-navy)' }}>
              <BookOpen size={18} color="var(--uca-blue)" />
              <h3 style={{ fontSize: '1.05rem', fontWeight: 800, margin: 0 }}>
                Temario Oficial y Programa Docente ({temarioList.length > 0 ? `${temarioList.length} Bloques/Temas` : 'Contenidos'})
              </h3>
            </div>

            {temarioList.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {temarioList.map((t, idx) => (
                  <div 
                    key={t.id ?? t.codigo ?? `${String(t.titulo || t.nombre || t).slice(0, 80)}-${idx}`}
                    style={{
                      background: 'var(--bg-main)',
                      border: '1px solid var(--border-light)',
                      borderRadius: 'var(--radius-md)',
                      padding: '0.9rem 1.1rem'
                    }}
                  >
                    <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-main)', display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
                      <span style={{ 
                        background: 'rgba(0, 132, 200, 0.12)', 
                        color: 'var(--uca-blue)', 
                        padding: '0.15rem 0.45rem', 
                        borderRadius: 'var(--radius-sm)', 
                        fontSize: '0.75rem',
                        fontWeight: 800,
                        flexShrink: 0
                      }}>
                        {typeof t === 'object' && t.orden ? t.orden : `${idx + 1}`}
                      </span>
                      <span>{typeof t === 'string' ? t : (t.titulo || `Bloque ${idx + 1}`)}</span>
                    </div>

                    {typeof t === 'object' && t.contenidos && Array.isArray(t.contenidos) && t.contenidos.length > 0 && (
                      <ul style={{ margin: '0.5rem 0 0 0', paddingLeft: '1.5rem', fontSize: '0.82rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                        {t.contenidos.map((sub, sIdx) => (
                          <li key={sIdx} style={{ marginBottom: '0.2rem' }}>{sub}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div style={{
                background: 'var(--bg-main)',
                padding: '1.25rem',
                borderRadius: 'var(--radius-md)',
                border: '1px dashed var(--border-light)',
                color: 'var(--text-muted)',
                fontSize: '0.88rem',
                lineHeight: 1.5
              }}>
                El temario detallado de esta asignatura se imparte conforme al proyecto docente oficial y guías de cátedra de la universidad.
              </div>
            )}
          </div>

          {/* Bloque 2: Sistema de Evaluación */}
          <div style={{ marginBottom: '1.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.85rem', color: 'var(--uca-navy)' }}>
              <span style={{ fontSize: '1.1rem' }}>⚖️</span>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 800, margin: 0 }}>
                Sistema de Evaluación y Ponderaciones
              </h3>
            </div>

            {evalList.length > 0 ? (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '0.75rem', marginBottom: '0.75rem' }}>
                {evalList.map((ev, evIdx) => (
                  <div 
                    key={evIdx}
                    style={{
                      background: 'var(--bg-main)',
                      border: '1px solid var(--border-light)',
                      borderRadius: 'var(--radius-md)',
                      padding: '0.85rem 1rem',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between'
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--text-main)', marginBottom: '0.2rem' }}>
                        {ev.tarea || `Prueba de Evaluación ${evIdx + 1}`}
                      </div>
                      {ev.instrumentos && (
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                          {ev.instrumentos}
                        </div>
                      )}
                    </div>
                    <div style={{ marginTop: '0.6rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Ponderación:</span>
                      <strong style={{ fontSize: '1rem', color: 'var(--success)' }}>
                        {ev.ponderacion_porcentaje ? `${ev.ponderacion_porcentaje}%` : 'Ponderado'}
                      </strong>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}

            {criteriosEval && (
              <div style={{
                background: 'rgba(0, 132, 200, 0.04)',
                border: '1px solid var(--border-light)',
                borderRadius: 'var(--radius-md)',
                padding: '0.9rem 1.1rem',
                fontSize: '0.82rem',
                color: 'var(--text-main)',
                lineHeight: 1.55
              }}>
                <div style={{ fontWeight: 700, color: 'var(--uca-blue)', marginBottom: '0.3rem' }}>
                  Criterios y Normativa de Calificación:
                </div>
                {criteriosEval}
              </div>
            )}
          </div>

          {/* Bloque 3: Profesorado y Bibliografía */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
            {/* Profesorado */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.65rem', color: 'var(--uca-navy)' }}>
                <User size={16} color="var(--uca-blue)" />
                <h4 style={{ fontSize: '0.95rem', fontWeight: 800, margin: 0 }}>Equipo Docente</h4>
              </div>

              {profList.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  {profList.map((p, pIdx) => {
                    const isCoord = typeof p === 'object' && p.coordinador;
                    const pName = typeof p === 'string' ? p : p.nombre_completo;
                    const pCat = typeof p === 'object' ? p.categoria : '';
                    return (
                      <div 
                        key={pIdx} 
                        style={{
                          background: 'var(--bg-main)',
                          border: isCoord ? '1px solid rgba(243, 167, 18, 0.4)' : '1px solid var(--border-light)',
                          borderRadius: 'var(--radius-sm)',
                          padding: '0.6rem 0.8rem',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between'
                        }}
                      >
                        <div>
                          <div style={{ fontWeight: 600, fontSize: '0.84rem', color: 'var(--text-main)' }}>{pName}</div>
                          {pCat && <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>{pCat}</div>}
                        </div>
                        {isCoord && (
                          <span className="badge" style={{ background: 'rgba(243, 167, 18, 0.15)', color: 'var(--uca-sun)', fontSize: '0.7rem' }}>
                            Coordinador/a
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                  {departamento ? `Asignada al Departamento de ${departamento}.` : 'Profesorado asignado por la secretaría del centro.'}
                </div>
              )}
            </div>

            {/* Bibliografía */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.65rem', color: 'var(--uca-navy)' }}>
                <Bookmark size={16} color="var(--uca-blue)" />
                <h4 style={{ fontSize: '0.95rem', fontWeight: 800, margin: 0 }}>Bibliografía Recomendada</h4>
              </div>

              {bibList.length > 0 ? (
                <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.45 }}>
                  {bibList.map((b, bIdx) => (
                    <li key={bIdx} style={{ marginBottom: '0.3rem' }}>{b}</li>
                  ))}
                </ul>
              ) : (
                <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                  Las referencias bibliográficas y manuales de apoyo se facilitan en el aula virtual / campus docente.
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div style={{
          padding: '1rem 1.75rem',
          background: 'var(--bg-main)',
          borderTop: '1px solid var(--border-light)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottomLeftRadius: 'var(--radius-lg)',
          borderBottomRightRadius: 'var(--radius-lg)',
          flexShrink: 0
        }}>
          <div>
            {guideUrl ? (
              <a
                href={guideUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-outline"
                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.82rem' }}
              >
                <ExternalLink size={14} /> Consultar Guía Docente Oficial en Universidad
              </a>
            ) : (
              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                Ficha Curricular Validada por UniHub
              </span>
            )}
          </div>

          <button
            onClick={onClose}
            className="btn btn-primary"
            style={{ fontSize: '0.85rem', padding: '0.45rem 1.25rem' }}
          >
            Cerrar Ficha
          </button>
        </div>
      </div>
    </div>
  );
}
