import React, { useEffect, useState, useCallback } from 'react';
import { X, FileText, ExternalLink, Award, Layers, AlertTriangle, BookOpen, ChevronDown, ChevronUp, User } from 'lucide-react';
import { apiService } from '../services/api';
import SubjectDetailModal from './SubjectDetailModal';

const getSubjectKey = (subject, index) => String(
  subject.id ?? subject.codigo ?? `${subject.nombre_elemento || 'elemento'}|${subject.curso || ''}|${subject.cuatrimestre || ''}|${subject.creditos_ects || ''}|${index}`
);

export default function PlanModal({ degree, onClose }) {
  const [loading, setLoading] = useState(true);
  const [planData, setPlanData] = useState(null);
  const [expandedSubject, setExpandedSubject] = useState(null);
  const [selectedSubject, setSelectedSubject] = useState(null);

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

  const loadCurriculum = useCallback(async (signal) => {
    if (!degree || !degree.codigo_estudio) return;
    setLoading(true);

    try {
      const data = await apiService.getDegreeCurriculum(degree.codigo_estudio, { signal });
      setPlanData(data || {});
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.info('Plan curricular desglosado no disponible en API. Mostrando ficha oficial:', err.message);
        // Si el plan no tiene tabla desglosada en BOE o es de universidad privada, mostramos la ficha oficial sin romper el modal
        setPlanData({ plan_estudios: { elementos_curriculares: [], resumen_creditos: {} } });
      }
    } finally {
      setLoading(false);
    }
  }, [degree]);

  useEffect(() => {
    const controller = new AbortController();
    loadCurriculum(controller.signal);
    return () => controller.abort();
  }, [loadCurriculum]);

  if (!degree) return null;

  const getSafeUrl = (url) => {
    if (!url) return null;
    const clean = url.trim();
    if (/^https?:\/\//i.test(clean)) return clean;
    return null;
  };

  const curriculum = planData?.plan_estudios ? planData.plan_estudios : (planData || {});
  const elementos = Array.isArray(curriculum.elementos_curriculares) ? curriculum.elementos_curriculares : [];
  const resumen = (curriculum.resumen_creditos && typeof curriculum.resumen_creditos === 'object' && !Array.isArray(curriculum.resumen_creditos)) ? curriculum.resumen_creditos : {};
  const boeUrl = getSafeUrl(planData?.boe_url || degree.boe_url);
  const boeFecha = planData?.boe_fecha || degree.boe_fecha;

  const isMaster = (degree.nivel_academico || '').toLowerCase().includes('máster') || (degree.nivel_academico || '').toLowerCase().includes('master');
  const isDoctor = (degree.nivel_academico || '').toLowerCase().includes('doctor') || 
                   (degree.nivel_academico || '').toLowerCase().includes('99/2011') ||
                   (degree.titulo || '').toLowerCase().includes('doctor');
  const isPrivada = (degree.universidad_tipo || '').toLowerCase().includes('privad');

  const numAnnual = parseFloat(degree.precio_estimado_anual);
  const numEcts = parseFloat(degree.precio_credito_ects);
  const annualPrice = (!isNaN(numAnnual) && numAnnual > 0) 
    ? Math.round(numAnnual) 
    : ((!isNaN(numEcts) && numEcts > 0) ? Math.round(numEcts * 60 + 45) : null);

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
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem', flexWrap: 'wrap' }}>
              <span className={`badge ${isDoctor ? 'badge-doctorado' : isMaster ? 'badge-master' : 'badge-grado'}`}>
                {isDoctor ? 'Doctorado Oficial' : isMaster ? 'Máster Universitario' : 'Grado Oficial'}
              </span>
              {isPrivada && <span className="badge badge-privada">Universidad Privada</span>}
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

          {/* Pricing & Fees Banner */}
          {annualPrice && (
            <div style={{
              background: 'rgba(16, 185, 129, 0.08)',
              border: '1px solid rgba(16, 185, 129, 0.25)',
              padding: '1rem 1.25rem',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '1.5rem',
              flexWrap: 'wrap',
              gap: '0.75rem'
            }}>
              <div>
                <span style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--success)' }}>
                  💶 {isPrivada ? 'Honorarios Privados Estimados (1º Curso):' : 'Tarifa Oficial de Primera Matrícula:'}
                </span>
                <div style={{ fontSize: '1.3rem', fontWeight: 800, color: 'var(--text-main)', marginTop: '0.2rem' }}>
                  ~{annualPrice} € / año
                  {degree.precio_credito_ects && (
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 500, marginLeft: '0.5rem' }}>
                      ({degree.precio_credito_ects} € / crédito ECTS)
                    </span>
                  )}
                </div>
              </div>

              {(degree.precio_credito_2 || degree.precio_credito_3 || degree.precio_credito_4) && (
                <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  {degree.precio_credito_2 && <span><strong>2ª:</strong> {degree.precio_credito_2}€/c</span>}
                  {degree.precio_credito_3 && <span><strong>3ª:</strong> {degree.precio_credito_3}€/c</span>}
                  {degree.precio_credito_4 && <span><strong>4ª:</strong> {degree.precio_credito_4}€/c</span>}
                </div>
              )}
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
              marginBottom: '1.75rem',
              flexWrap: 'wrap',
              gap: '0.75rem'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <FileText size={24} color="var(--uca-cyan)" />
                <div>
                  <div style={{ fontWeight: 700, fontSize: '0.95rem' }}>Boletín Oficial del Estado (BOE)</div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Documento oficial con la resolución de verificación del título.</div>
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
              <div style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.5rem' }}>Cargando información del plan de estudios...</div>
              <div style={{ fontSize: '0.85rem' }}>Analizando asignaturas, créditos ECTS y estructura oficial...</div>
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
                    {Object.entries(resumen).map(([k, v]) => (
                      <div key={k} style={{ background: 'var(--bg-main)', padding: '0.85rem 1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
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
                  <Layers size={18} color="var(--uca-cyan)" /> {curriculum.tipo_estructura === 'programa_doctorado_investigacion' || (degree.nivel_academico || '').toLowerCase().includes('doctor') ? 'Estructura Investigadora y Formativa (RD 99/2011)' : `Estructura de Asignaturas, Módulos y Materias (${elementos.length})`}
                </h3>

                {curriculum.tipo_estructura === 'programa_doctorado_investigacion' || (degree.nivel_academico || '').toLowerCase().includes('doctor') ? (
                  <div style={{
                    padding: '2rem 1.75rem',
                    background: 'linear-gradient(135deg, rgba(0, 132, 200, 0.05) 0%, rgba(15, 23, 42, 0.02) 100%)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid rgba(0, 132, 200, 0.25)',
                    textAlign: 'left'
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
                      <div style={{ padding: '0.65rem', background: 'rgba(0, 132, 200, 0.15)', borderRadius: '10px', color: 'var(--uca-blue)' }}>
                        <Award size={26} />
                      </div>
                      <div>
                        <h4 style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-main)', margin: 0 }}>
                          Programa Oficial de Doctorado e Investigación
                        </h4>
                        <span style={{ fontSize: '0.82rem', color: 'var(--uca-cyan)', fontWeight: 600 }}>
                          Regulado por el Real Decreto 99/2011
                        </span>
                      </div>
                    </div>

                    <p style={{ fontSize: '0.92rem', color: 'var(--text-main)', lineHeight: 1.6, marginBottom: '1.25rem' }}>
                      Conforme a la normativa universitaria española (Real Decreto 99/2011), los estudios de Doctorado no se estructuran en asignaturas lectivas tradicionales con créditos ECTS, sino que se articulan en torno a <strong>Líneas de Investigación Científica, Actividades Formativas Transversales</strong> (seminarios, congresos y estancias) y la elaboración y defensa pública de la <strong>Tesis Doctoral</strong> bajo tutela académica anual.
                    </p>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
                      <div style={{ background: 'var(--bg-main)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', marginBottom: '0.25rem' }}>
                          Dedicación Académica
                        </div>
                        <div style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--uca-blue)' }}>
                          Investigación & Tesis Doctoral
                        </div>
                      </div>
                      <div style={{ background: 'var(--bg-main)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', marginBottom: '0.25rem' }}>
                          Régimen de Matrícula
                        </div>
                        <div style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-main)' }}>
                          Tutela Académica Anual Oficial
                        </div>
                      </div>
                    </div>

                    {boeUrl && (
                      <a
                        href={boeUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="btn btn-outline"
                        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}
                      >
                        <FileText size={16} /> Consultar Memoria de Verificación en BOE <ExternalLink size={14} />
                      </a>
                    )}
                  </div>
                ) : (curriculum.tipo_estructura === 'consorcio_europeo_erasmus_mundus' || degree.es_alianza_europea || (degree.titulo || '').toLowerCase().includes('erasmus mundus') || (degree.titulo || '').toLowerCase().includes('sea-eu')) ? (
                  <div style={{
                    padding: '2rem 1.75rem',
                    background: 'linear-gradient(135deg, rgba(14, 165, 233, 0.08) 0%, rgba(99, 102, 241, 0.05) 100%)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid rgba(14, 165, 233, 0.3)',
                    textAlign: 'left'
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
                      <div style={{ padding: '0.65rem', background: 'rgba(14, 165, 233, 0.15)', borderRadius: '10px', color: '#0EA5E9' }}>
                        <Award size={26} />
                      </div>
                      <div>
                        <h4 style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-main)', margin: 0 }}>
                          Programa Internacional de Excelencia Europea (Erasmus Mundus / Alianza Universitaria)
                        </h4>
                        <span style={{ fontSize: '0.82rem', color: '#0EA5E9', fontWeight: 600 }}>
                          Consorcio Universitario Internacional Acreditado por la Comisión Europea
                        </span>
                      </div>
                    </div>

                    <p style={{ fontSize: '0.92rem', color: 'var(--text-main)', lineHeight: 1.6, marginBottom: '1.25rem' }}>
                      Este título de Máster Conjunto se imparte en consorcio transnacional entre prestigiosas universidades europeas en lengua inglesa. La docencia se distribuye de forma itinerante a lo largo de los semestres en los campus asociados y el plan de estudios completo, convenios de movilidad y becas de excelencia Erasmus Mundus se gestionan de manera unificada a través del portal central del consorcio europeo.
                    </p>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
                      <div style={{ background: 'var(--bg-main)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', marginBottom: '0.25rem' }}>
                          Carga Docente Oficial
                        </div>
                        <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--uca-blue)' }}>
                          {curriculum.ects_exigidos ?? 'N/D'} ECTS Verificados
                        </div>
                      </div>
                      <div style={{ background: 'var(--bg-main)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', marginBottom: '0.25rem' }}>
                          Idioma y Movilidad
                        </div>
                        <div style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-main)' }}>
                          Inglés / Itinerancia Transnacional
                        </div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                      {degree.web_fuente_directa_url && (
                        <a
                          href={degree.web_fuente_directa_url}
                          target="_blank"
                          rel="noreferrer"
                          className="btn btn-primary"
                          style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}
                        >
                          <ExternalLink size={14} /> Portal Oficial del Consorcio Europeo
                        </a>
                      )}
                      {boeUrl && (
                        <a
                          href={boeUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="btn btn-outline"
                          style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}
                        >
                          <FileText size={16} /> Resolución Oficial en BOE <ExternalLink size={14} />
                        </a>
                      )}
                    </div>
                  </div>
                ) : elementos.length === 0 ? (
                  <div style={{
                    padding: '2.5rem 1.75rem',
                    background: 'var(--bg-main)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px dashed var(--border-light)',
                    textAlign: 'center'
                  }}>
                    <div style={{ display: 'inline-flex', padding: '0.75rem', background: 'rgba(0, 132, 200, 0.12)', borderRadius: '50%', color: 'var(--uca-cyan)', marginBottom: '1rem' }}>
                      <FileText size={28} />
                    </div>
                    <h4 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--text-main)' }}>
                      Plan de Estudios Gestionado por la Universidad
                    </h4>
                    <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', maxWidth: '600px', margin: '0 auto 1.5rem auto', lineHeight: 1.6 }}>
                      Esta titulación oficial está verificada por el Consejo de Universidades y registrada en el RUCT. Al tratarse de una titulación impartida por una universidad privada o verificada bajo resoluciones generales sin desglose de asignaturas en el BOE, las guías docentes pormenorizadas, itinerarios y convalidaciones se gestionan directamente a través del portal y secretaría de la propia universidad.
                    </p>
                    {boeUrl && (
                      <a
                        href={boeUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="btn btn-outline"
                        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}
                      >
                        <FileText size={16} /> Consultar Resolución Oficial en BOE <ExternalLink size={14} />
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
                          <th style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>Guía / Temario</th>
                        </tr>
                      </thead>
                      <tbody>
                        {elementos.map((elem, idx) => {
                          const subjectKey = getSubjectKey(elem, idx);
                          const guia = elem.guia_docente || {};
                          const hasDetails = Boolean(elem.url_guia_docente || elem.temario || guia.temario || guia.sistema_evaluacion || elem.sistema_evaluacion);
                          const isExpanded = expandedSubject === subjectKey;
                          const temarioList = elem.temario || guia.temario || [];
                          const evalList = elem.sistema_evaluacion || guia.sistema_evaluacion || [];
                          const profList = elem.profesorado || guia.profesorado || [];
                          const bibList = elem.bibliografia || guia.bibliografia || [];
                          const rawGuideUrl = elem.url_guia_docente || guia.url_guia_docente;
                          const guideUrl = getSafeUrl(rawGuideUrl);

                          return (
                            <React.Fragment key={subjectKey}>
                              <tr 
                                style={{ 
                                  borderBottom: isExpanded ? 'none' : '1px solid var(--border-light)', 
                                  background: isExpanded ? 'rgba(0, 132, 200, 0.08)' : (idx % 2 === 0 ? 'transparent' : 'rgba(0, 132, 200, 0.03)'),
                                  cursor: hasDetails ? 'pointer' : 'default'
                                }}
                                onClick={() => hasDetails && setExpandedSubject(isExpanded ? null : subjectKey)}
                              >
                                <td style={{ padding: '0.65rem 1rem', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                                  {elem.materia || elem.modulo ? (
                                    /menci|itinerari|especialid/i.test(elem.materia || elem.modulo) ? (
                                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', color: 'var(--uca-blue)', fontWeight: 600 }}>
                                        🏷️ {elem.materia || elem.modulo}
                                      </span>
                                    ) : (
                                      elem.materia || elem.modulo
                                    )
                                  ) : '-'}
                                </td>
                                <td style={{ padding: '0.65rem 1rem', fontWeight: 600 }}>
                                  <button
                                    type="button"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setSelectedSubject(elem);
                                    }}
                                    aria-label={`Ver ficha docente y temario de ${elem.nombre_elemento || 'esta asignatura'}`}
                                    style={{
                                      background: 'none',
                                      border: 'none',
                                      padding: 0,
                                      color: 'var(--uca-blue)',
                                      fontWeight: 700,
                                      fontSize: '0.88rem',
                                      textAlign: 'left',
                                      cursor: 'pointer',
                                      textDecoration: 'underline',
                                      textDecorationColor: 'rgba(0, 132, 200, 0.4)',
                                      display: 'inline-flex',
                                      alignItems: 'center',
                                      gap: '0.35rem'
                                    }}
                                    onMouseEnter={(e) => e.currentTarget.style.color = 'var(--uca-navy)'}
                                    onMouseLeave={(e) => e.currentTarget.style.color = 'var(--uca-blue)'}
                                  >
                                    {elem.nombre_elemento}
                                    <BookOpen size={13} style={{ opacity: 0.8, flexShrink: 0 }} />
                                  </button>
                                </td>
                                <td style={{ padding: '0.65rem 1rem', fontWeight: 700, color: 'var(--uca-blue)' }}>{elem.creditos_ects || '-'}</td>
                                <td style={{ padding: '0.65rem 1rem' }}>
                                  <span className="badge" style={{ background: 'rgba(0, 132, 200, 0.1)', color: 'var(--uca-cyan)' }}>
                                    {elem.caracter || elem.tipo || 'OB'}
                                  </span>
                                </td>
                                <td style={{ padding: '0.65rem 1rem' }}>{elem.curso ? `${elem.curso}º` : '-'}</td>
                                <td style={{ padding: '0.65rem 1rem' }}>{elem.cuatrimestre || '-'}</td>
                                <td style={{ padding: '0.65rem 1rem', textAlign: 'center' }}>
                                  {hasDetails ? (
                                    <button
                                      type="button"
                                      aria-label="Ver temario y guía docente"
                                      style={{
                                        background: isExpanded ? 'var(--uca-blue)' : 'rgba(0, 132, 200, 0.12)',
                                        color: isExpanded ? '#FFFFFF' : 'var(--uca-blue)',
                                        border: 'none',
                                        borderRadius: 'var(--radius-sm)',
                                        padding: '0.3rem 0.6rem',
                                        fontSize: '0.78rem',
                                        fontWeight: 600,
                                        cursor: 'pointer',
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        gap: '0.3rem'
                                      }}
                                    >
                                      <BookOpen size={13} />
                                      {isExpanded ? 'Ocultar' : 'Temario'}
                                      {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                                    </button>
                                  ) : guideUrl ? (
                                    <a
                                      href={guideUrl}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      onClick={(e) => e.stopPropagation()}
                                      style={{ color: 'var(--uca-blue)', display: 'inline-flex', alignItems: 'center', gap: '0.2rem', fontSize: '0.78rem' }}
                                    >
                                      Guía <ExternalLink size={11} />
                                    </a>
                                  ) : (
                                    <span style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>-</span>
                                  )}
                                </td>
                              </tr>

                              {/* Accordion Drawer: Temario y Guía Docente */}
                              {isExpanded && (
                                <tr style={{ background: 'rgba(0, 132, 200, 0.04)', borderBottom: '1px solid var(--border-light)' }}>
                                  <td colSpan={7} style={{ padding: '1.25rem 1.5rem' }}>
                                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
                                      {/* Bloque 1: Temario Oficial */}
                                      {temarioList.length > 0 && (
                                        <div style={{ background: 'var(--bg-main)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontWeight: 700, color: 'var(--uca-blue)', marginBottom: '0.6rem', fontSize: '0.9rem' }}>
                                            <BookOpen size={16} /> Temario Oficial ({temarioList.length} bloques/temas)
                                          </div>
                                          <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.82rem', lineHeight: 1.5, color: 'var(--text-main)' }}>
                                            {temarioList.map((t, tIdx) => (
                                              <li key={tIdx} style={{ marginBottom: '0.35rem' }}>
                                                <strong>{typeof t === 'string' ? t : (t.titulo || t.orden || `Tema ${tIdx + 1}`)}</strong>
                                                {t.contenidos && Array.isArray(t.contenidos) && t.contenidos.length > 0 && (
                                                  <ul style={{ paddingLeft: '1rem', marginTop: '0.2rem', color: 'var(--text-muted)', fontSize: '0.78rem' }}>
                                                    {t.contenidos.slice(0, 3).map((sub, sIdx) => (
                                                      <li key={sIdx}>{sub}</li>
                                                    ))}
                                                  </ul>
                                                )}
                                              </li>
                                            ))}
                                          </ul>
                                        </div>
                                      )}

                                      {/* Bloque 2: Sistema de Evaluación */}
                                      {(evalList.length > 0 || elem.criterios_evaluacion || guia.criterios_evaluacion) && (
                                        <div style={{ background: 'var(--bg-main)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontWeight: 700, color: 'var(--success)', marginBottom: '0.6rem', fontSize: '0.9rem' }}>
                                            ⚖️ Sistema de Evaluación y Ponderaciones
                                          </div>
                                          {evalList.length > 0 ? (
                                            <div style={{ fontSize: '0.82rem' }}>
                                              {evalList.map((ev, evIdx) => (
                                                <div key={evIdx} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.25rem 0', borderBottom: '1px dashed var(--border-light)' }}>
                                                  <span>{ev.tarea || ev.instrumentos || `Prueba ${evIdx + 1}`}</span>
                                                  <strong style={{ color: 'var(--uca-blue)' }}>{ev.ponderacion_porcentaje ? `${ev.ponderacion_porcentaje}%` : 'Ponderado'}</strong>
                                                </div>
                                              ))}
                                            </div>
                                          ) : (
                                            <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.45 }}>
                                              {elem.criterios_evaluacion || guia.criterios_evaluacion}
                                            </p>
                                          )}
                                        </div>
                                      )}

                                      {/* Bloque 3: Profesorado y Enlace */}
                                      <div style={{ background: 'var(--bg-main)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.6rem', fontSize: '0.9rem' }}>
                                          <User size={16} /> Equipo Docente e Información
                                        </div>
                                        {profList.length > 0 ? (
                                          <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.82rem', color: 'var(--text-main)', marginBottom: '0.75rem' }}>
                                            {profList.map((p, pIdx) => (
                                              <li key={pIdx}>
                                                {typeof p === 'string' ? p : p.nombre_completo}
                                                {p.coordinador && <span style={{ marginLeft: '0.3rem', fontSize: '0.72rem', color: 'var(--uca-sun)', fontWeight: 700 }}>(Coordinador)</span>}
                                              </li>
                                            ))}
                                          </ul>
                                        ) : (
                                          <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                                            {guia.departamento ? `Departamento: ${guia.departamento}` : 'Consultar profesorado en la guía oficial.'}
                                          </p>
                                        )}

                                        {bibList.length > 0 && (
                                          <div style={{ marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px dashed var(--border-light)', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                                            <strong>Bibliografía básica:</strong> {bibList.slice(0, 2).map(b => typeof b === 'string' ? b : (b.titulo || b.referencia || '')).join(' · ')}
                                          </div>
                                        )}

                                        {guideUrl && (
                                          <div style={{ marginTop: '0.75rem' }}>
                                            <a
                                              href={guideUrl}
                                              target="_blank"
                                              rel="noopener noreferrer"
                                              className="btn btn-outline"
                                              style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.78rem', padding: '0.35rem 0.75rem' }}
                                            >
                                              <ExternalLink size={13} /> Ver Guía Docente Completa
                                            </a>
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  </td>
                                </tr>
                              )}
                            </React.Fragment>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Modal / Tarjeta detallada de asignatura individual */}
      {selectedSubject && (
        <SubjectDetailModal
          subject={selectedSubject}
          degree={degree}
          onClose={() => setSelectedSubject(null)}
        />
      )}
    </div>
  );
}
