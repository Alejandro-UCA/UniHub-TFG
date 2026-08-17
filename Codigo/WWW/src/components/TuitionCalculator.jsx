import React, { useState, useEffect, useMemo } from 'react';
import { Calculator, Building2, GraduationCap, BookOpen, CheckSquare, Square, RefreshCw, AlertCircle, Sparkles, Receipt, Layers } from 'lucide-react';
import { apiService } from '../services/api';
import usageTracker from '../analytics/usageTracker';

export default function TuitionCalculator() {
  const [universities, setUniversities] = useState([]);
  const [selectedUnivCode, setSelectedUnivCode] = useState('');
  const [degrees, setDegrees] = useState([]);
  const [selectedDegreeCode, setSelectedDegreeCode] = useState('');
  const [degreeDetail, setDegreeDetail] = useState(null);
  
  const [loadingUnivs, setLoadingUnivs] = useState(true);
  const [loadingDegrees, setLoadingDegrees] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [apiError, setApiError] = useState(null);

  // Map of subject selections: { [subjectIdOrIndex]: { selected: boolean, tier: 1 | 2 | 3 | 4 } }
  const [subjectSelections, setSubjectSelections] = useState({});

  // 1. Fetch All Universities (Public & Private)
  const fetchAllUnivs = async () => {
    setLoadingUnivs(true);
    setApiError(null);
    try {
      const data = await apiService.getUniversities({ limit: 300 });
      const allUnivs = data || [];
      setUniversities(allUnivs);
      if (allUnivs.length > 0) {
        setSelectedUnivCode(allUnivs[0].codigo);
      }
    } catch (err) {
      console.error('Error cargando universidades en calculadora:', err);
      setApiError('No se pudo conectar con el servidor API para obtener el listado de universidades.');
    } finally {
      setLoadingUnivs(false);
    }
  };

  useEffect(() => {
    fetchAllUnivs();
  }, []);

  // 2. Fetch Degrees when University Changes
  useEffect(() => {
    if (!selectedUnivCode) return;
    setLoadingDegrees(true);
    setDegrees([]);
    setSelectedDegreeCode('');
    setDegreeDetail(null);
    setSubjectSelections({});

    const controller = new AbortController();
    apiService.getDegrees({ universidad_codigo: selectedUnivCode, con_plan: true, limit: 500 }, { signal: controller.signal })
      .then(data => {
        setDegrees(data || []);
        if (data && data.length > 0) {
          setSelectedDegreeCode(data[0].codigo_estudio);
        }
        setLoadingDegrees(false);
      })
      .catch(err => {
        if (err.name !== 'AbortError') {
          console.error('Error cargando titulaciones:', err);
          setLoadingDegrees(false);
        }
      });
    return () => controller.abort();
  }, [selectedUnivCode]);

  // 3. Fetch Degree Detail when Degree Changes
  useEffect(() => {
    if (!selectedDegreeCode) return;
    setLoadingDetail(true);
    const controller = new AbortController();
    apiService.getDegreeByCode(selectedDegreeCode, { signal: controller.signal })
      .then(data => {
        setDegreeDetail(data);
        setLoadingDetail(false);
        if (data) {
          usageTracker.trackDegreeView(data.codigo_estudio, data.titulo);

          // Pre-select 1st year subjects by default if explicit curso tag exists
          const elems = data.plan_estudios?.elementos_curriculares || [];
          const initialMap = {};
          elems.forEach((elem, idx) => {
            const isFirstYear = String(elem.curso || '').includes('1');
            initialMap[idx] = {
              selected: isFirstYear,
              tier: 1 // 1ª matrícula
            };
          });
          setSubjectSelections(initialMap);
        }
      })
      .catch(err => {
        if (err.name !== 'AbortError') {
          console.error('Error cargando detalle de titulación:', err);
          setLoadingDetail(false);
        }
      });
    return () => controller.abort();
  }, [selectedDegreeCode]);

  // Selected University object
  const currentUniv = useMemo(() => {
    return universities.find(u => u.codigo === selectedUnivCode);
  }, [universities, selectedUnivCode]);

  // Get real ECTS price by tier from database
  const getEctsPrice = (tier) => {
    if (!degreeDetail) return 16.80;
    const base = parseFloat(degreeDetail.precio_credito_ects) || 16.80;
    if (tier === 1) return base;
    if (tier === 2) return parseFloat(degreeDetail.precio_credito_2) || (base * 1.5);
    if (tier === 3) return parseFloat(degreeDetail.precio_credito_3) || (base * 3.0);
    if (tier >= 4) return parseFloat(degreeDetail.precio_credito_4) || (base * 4.5);
    return base;
  };
  
  const baseEctsPrice = getEctsPrice(1);
  const adminFees = parseFloat(import.meta.env.VITE_ADMIN_FEES || "45.00"); // Tasas administrativas de secretaría y carné

  // Elements list
  const elements = degreeDetail?.plan_estudios?.elementos_curriculares || [];

  // Group elements by course
  const groupedByCourse = useMemo(() => {
    const map = {};
    elements.forEach((elem, idx) => {
      const courseStr = elem.curso ? `${elem.curso}º Curso` : 'Asignaturas de la Titulación';
      if (!map[courseStr]) map[courseStr] = [];
      map[courseStr].push({ ...elem, originalIndex: idx });
    });
    return map;
  }, [elements]);

  // Handle Toggle Subject Selection
  const toggleSubject = (idx) => {
    setSubjectSelections(prev => ({
      ...prev,
      [idx]: {
        selected: !prev[idx]?.selected,
        tier: prev[idx]?.tier || 1
      }
    }));
  };

  // Handle Change Enrolment Tier (1ª, 2ª, 3ª, 4ª)
  const changeTier = (idx, newTier) => {
    setSubjectSelections(prev => ({
      ...prev,
      [idx]: {
        selected: true, // auto select if tier changed
        tier: parseInt(newTier, 10)
      }
    }));
  };

  // Select / Deselect All
  const selectAll = (selectState) => {
    const updated = {};
    elements.forEach((_, idx) => {
      updated[idx] = {
        selected: selectState,
        tier: subjectSelections[idx]?.tier || 1
      };
    });
    setSubjectSelections(updated);
  };

  // Select / Deselect Course
  const selectCourseAll = (courseName, selectState) => {
    const courseItems = groupedByCourse[courseName] || [];
    setSubjectSelections(prev => {
      const updated = { ...prev };
      courseItems.forEach(item => {
        updated[item.originalIndex] = {
          selected: selectState,
          tier: prev[item.originalIndex]?.tier || 1
        };
      });
      return updated;
    });
  };

  // Estado del tipo de exención / bonificación de matrícula
  const [discountType, setDiscountType] = useState('ninguno');

  const isPrivada = (currentUniv?.tipo || '').toLowerCase().includes('privad');

  // Diccionario explicativo de condiciones de bonificación / exención
  const DISCOUNT_INFO = {
    ninguno: null,
    fn_general: isPrivada ? 'Exención autonómica NO aplicable en universidades privadas. La matrícula se calculará con la tarifa de honorarios privados ordinarios.' : 'Disponible acreditando el Título de Familia Numerosa de Categoría General vigente antes del inicio del curso académico. Aplica un 50% de descuento en el importe de créditos ECTS y en las tasas administrativas de secretaría.',
    fn_especial: isPrivada ? 'Exención autonómica NO aplicable en universidades privadas. La matrícula se calculará con la tarifa de honorarios privados ordinarios.' : 'Disponible acreditando el Título de Familia Numerosa de Categoría Especial vigente. Otorga exención del 100% (gratuidad total) en asignaturas y apertura/tasas de secretaría.',
    discapacidad: isPrivada ? 'Exención autonómica NO aplicable en universidades privadas. Se abonará la tarifa privada fijada por el centro.' : 'Disponible presentando el Dictamen Oficial de Discapacidad igual o superior al 33% emitido por el IMSERSO o la Comunidad Autónoma. Otorga exención completa del 100%.',
    beca_mec: isPrivada ? `Beca MEC en Universidad Privada: El Ministerio exime ÚNICAMENTE la cuantía del precio público oficial equivalente (~${import.meta.env.VITE_BECA_MEC_REFERENCE_PRICE || "1.008"} €/año para 60 ECTS). El estudiante deberá abonar la diferencia hasta cubrir los honorarios privados.` : 'Exención provisional del 100% en créditos matriculados en 1ª matrícula. Requiere haber formalizado la solicitud de Beca MEC antes del plazo oficial. Si la beca fuera denegada, la universidad reclamará el abono en el primer cuatrimestre. Las tasas administrativas (45 €) deben abonarse salvo exención paralela.',
    mh_bachillerato: isPrivada ? 'Matrícula de Honor en Privada: Exime la cuantía equivalente al precio público oficial en 1º curso (60 ECTS x tarifa pública), debiendo abonarse la diferencia privada.' : 'Disponible exclusivamente para alumnos matriculados en 1º curso con Matrícula de Honor o Premio Extraordinario en Bachillerato o CFGS. Exime del pago del 100% de los créditos del primer curso (60 ECTS).',
    bonif_99: isPrivada ? 'La Bonificación del 99% por Rendimiento Académico de la CCAA NO aplica a universidades privadas.' : 'Disponible para estudiantes de universidades públicas andaluzas que aprobaron créditos en 1ª matrícula en el curso inmediatamente anterior y no son becarios del Ministerio (Decreto 99% CCAA). Bonifica el 99% de los créditos aprobados.',
    victima_violencia: isPrivada ? 'Exención autonómica NO aplicable en universidades privadas.' : 'Exención completa (100%) acreditando condición oficial de Víctima de Violencia de Género, Víctima del Terrorismo o Beneficiario del Ingreso Mínimo Vital mediante resolución judicial o administrativa.'
  };

  // Calcular desglose de costes e importes finales
  const calculation = useMemo(() => {
    let totalEcts = 0;
    let totalSubjectCost = 0;
    const tierCounts = { 1: 0, 2: 0, 3: 0, 4: 0 };
    const tierCosts = { 1: 0, 2: 0, 3: 0, 4: 0 };
    let selectedSubjectsCount = 0;

    elements.forEach((elem, idx) => {
      const state = subjectSelections[idx];
      if (state?.selected) {
        selectedSubjectsCount++;
        const ects = parseFloat(elem.creditos_ects) || 6;
        totalEcts += ects;
        
        const ectsPriceForTier = getEctsPrice(state.tier);
        const subjectPrice = ects * ectsPriceForTier;
        
        totalSubjectCost += subjectPrice;
        tierCounts[state.tier] = (tierCounts[state.tier] || 0) + 1;
        tierCosts[state.tier] = (tierCosts[state.tier] || 0) + subjectPrice;
      }
    });

    let discountAmount = 0;
    let finalAdminFees = selectedSubjectsCount > 0 ? adminFees : 0;
    let discountLabel = '';

    if (!isPrivada) {
      if (discountType === 'fn_general') {
        discountAmount = totalSubjectCost * 0.5;
        finalAdminFees = finalAdminFees * 0.5;
        discountLabel = 'Exención 50% Familia Numerosa General';
      } else if (discountType === 'fn_especial' || discountType === 'discapacidad' || discountType === 'victima_violencia') {
        discountAmount = totalSubjectCost;
        finalAdminFees = 0;
        discountLabel = 'Exención 100% Gratuidad Total';
      } else if (discountType === 'beca_mec') {
        discountAmount = tierCosts[1] || 0;
        discountLabel = 'Exención Beca MEC (1ª Matrícula)';
      } else if (discountType === 'mh_bachillerato') {
        discountAmount = Math.min(totalSubjectCost, 60 * baseEctsPrice);
        discountLabel = 'Exención M.H. Bachillerato/CFGS (60 ECTS)';
      } else if (discountType === 'bonif_99') {
        discountAmount = (tierCosts[1] || 0) * 0.99;
        discountLabel = 'Bonificación 99% CCAA Rendimiento';
      }
    } else {
      // Logic for Private Universities: Only MEC / MH cover equivalent public pricing cap (~16.80 €/ECTS)
      const publicEctsEquivPrice = parseFloat(degreeDetail?.precio_credito_ects) || 16.80;
      if (discountType === 'beca_mec') {
        let firstTierEctsSum = 0;
        elements.forEach((elem, idx) => {
          const state = subjectSelections[idx];
          if (state?.selected && state?.tier === 1) {
            firstTierEctsSum += parseFloat(elem.creditos_ects) || 6;
          }
        });
        discountAmount = firstTierEctsSum * publicEctsEquivPrice;
        discountLabel = 'Cobertura Beca MEC (Equivalente Precio Público)';
      } else if (discountType === 'mh_bachillerato') {
        discountAmount = Math.min(totalEcts, 60) * publicEctsEquivPrice;
        discountLabel = 'Cobertura M.H. Bachillerato (Equivalente Precio Público)';
      }
    }

    const grandTotal = Math.max(0, totalSubjectCost - discountAmount + finalAdminFees);

    return {
      selectedSubjectsCount,
      totalEcts,
      tierCounts,
      tierCosts,
      totalSubjectCost,
      discountAmount,
      discountLabel,
      adminFees: finalAdminFees,
      grandTotal
    };
  }, [elements, subjectSelections, baseEctsPrice, discountType, isPrivada]);

  return (
    <div style={{ padding: '2rem 0', maxWidth: '1280px', margin: '0 auto' }}>
      
      {/* Header Banner */}
      <div className="glass-panel" style={{ padding: '2rem', marginBottom: '2rem', borderRadius: '16px', background: 'linear-gradient(135deg, rgba(0, 168, 204, 0.12) 0%, rgba(15, 23, 42, 0.6) 100%)', border: '1px solid rgba(0, 168, 204, 0.25)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.75rem' }}>
          <div style={{ background: 'var(--uca-cyan)', padding: '0.75rem', borderRadius: '12px', color: '#0F172A', display: 'flex' }}>
            <Calculator size={28} />
          </div>
          <div>
            <h2 style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--text-main)', margin: 0 }}>
              Calculadora Oficial de Matrícula Universitaria
            </h2>
            <p style={{ color: 'var(--text-muted)', margin: '0.25rem 0 0 0', fontSize: '0.95rem' }}>
              Simula el coste exacto de tu matrícula seleccionando asignaturas y aplicando recargos por 1ª, 2ª, 3ª o 4ª matrícula según el Decreto de Precios Públicos oficial.
            </p>
          </div>
        </div>
      </div>

      {/* Selectors Bar */}
      <div className="glass-panel" style={{ padding: '1.5rem', marginBottom: '2rem', borderRadius: '12px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem' }}>
          
          {/* Public & Private University Selector */}
          <div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 700, fontSize: '0.9rem', color: 'var(--uca-cyan)', marginBottom: '0.5rem' }}>
              <Building2 size={18} /> 1. Selecciona Universidad (Pública / Privada)
            </label>
            {loadingUnivs ? (
              <div style={{ padding: '0.75rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>Cargando universidades...</div>
            ) : (
              <select
                aria-label="Seleccionar universidad"
                value={selectedUnivCode}
                onChange={(e) => setSelectedUnivCode(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  borderRadius: '8px',
                  background: 'var(--bg-card)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-light)',
                  fontWeight: 600,
                  fontSize: '0.95rem',
                  outline: 'none'
                }}
              >
                {universities.map(u => (
                  <option key={u.codigo} value={u.codigo}>
                    [{(u.tipo || '').toLowerCase().includes('privad') ? 'Privada' : 'Pública'}] {u.nombre} ({u.comunidad_autonoma})
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Degree Selector */}
          <div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 700, fontSize: '0.9rem', color: 'var(--uca-cyan)', marginBottom: '0.5rem' }}>
              <GraduationCap size={18} /> 2. Selecciona Titulación
            </label>
            {loadingDegrees ? (
              <div style={{ padding: '0.75rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>Cargando titulaciones oficiales...</div>
            ) : degrees.length === 0 ? (
              <div style={{ padding: '0.75rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>No hay titulaciones disponibles.</div>
            ) : (
              <select
                aria-label="Seleccionar titulación"
                value={selectedDegreeCode}
                onChange={(e) => setSelectedDegreeCode(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  borderRadius: '8px',
                  background: 'var(--bg-card)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-light)',
                  fontWeight: 600,
                  fontSize: '0.95rem',
                  outline: 'none'
                }}
              >
                {degrees.map(d => (
                  <option key={d.codigo_estudio} value={d.codigo_estudio}>
                    [{d.nivel_academico ? d.nivel_academico.split('-')[0].trim() : 'Estudio'}] {d.titulo}
                  </option>
                ))}
              </select>
            )}
          </div>

        </div>
      </div>

      {/* Main Content Layout: Subjects List (Left) + Receipt Card (Right) */}
      {loadingDetail ? (
        <div className="glass-panel" style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          <RefreshCw size={32} className="spin" style={{ marginBottom: '1rem', color: 'var(--uca-cyan)' }} />
          <div>Cargando plan de estudios oficial y asignaturas desde la base de datos...</div>
        </div>
      ) : degreeDetail && elements.length > 0 ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 400px), 1fr))', gap: '2rem' }}>
          
          {/* Left Column: Subjects Picker */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
              <div>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-main)', margin: 0 }}>
                  Asignaturas de la Titulación
                </h3>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  {elements.length} asignaturas encontradas en el Plan de Estudios oficial (BOE)
                </span>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  onClick={() => selectAll(true)}
                  style={{
                    padding: '0.4rem 0.8rem',
                    borderRadius: '6px',
                    background: 'rgba(0, 168, 204, 0.15)',
                    color: 'var(--uca-cyan)',
                    border: '1px solid rgba(0, 168, 204, 0.3)',
                    cursor: 'pointer',
                    fontSize: '0.82rem',
                    fontWeight: 600
                  }}
                >
                  Seleccionar Todas
                </button>
                <button
                  onClick={() => selectAll(false)}
                  style={{
                    padding: '0.4rem 0.8rem',
                    borderRadius: '6px',
                    background: 'rgba(239, 68, 68, 0.1)',
                    color: '#EF4444',
                    border: '1px solid rgba(239, 68, 68, 0.25)',
                    cursor: 'pointer',
                    fontSize: '0.82rem',
                    fontWeight: 600
                  }}
                >
                  Desmarcar Todas
                </button>
              </div>
            </div>

            {/* Subjects List Grouped by Course */}
            {Object.keys(groupedByCourse).sort((a, b) => a.localeCompare(b)).map(courseName => (
              <div key={courseName} className="glass-panel" style={{ marginBottom: '1.5rem', padding: '1.25rem', borderRadius: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
                  <h4 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--uca-cyan)', margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Layers size={18} /> {courseName}
                  </h4>
                  <div style={{ display: 'flex', gap: '0.35rem' }}>
                    <button
                      onClick={() => selectCourseAll(courseName, true)}
                      style={{
                        padding: '0.25rem 0.6rem',
                        borderRadius: '4px',
                        background: 'rgba(0, 168, 204, 0.12)',
                        color: 'var(--uca-cyan)',
                        border: '1px solid rgba(0, 168, 204, 0.25)',
                        cursor: 'pointer',
                        fontSize: '0.75rem',
                        fontWeight: 600
                      }}
                    >
                      + Marcar {courseName}
                    </button>
                    <button
                      onClick={() => selectCourseAll(courseName, false)}
                      style={{
                        padding: '0.25rem 0.6rem',
                        borderRadius: '4px',
                        background: 'rgba(255, 255, 255, 0.05)',
                        color: 'var(--text-muted)',
                        border: '1px solid var(--border-light)',
                        cursor: 'pointer',
                        fontSize: '0.75rem',
                        fontWeight: 600
                      }}
                    >
                      - Desmarcar
                    </button>
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {groupedByCourse[courseName].map(subject => {
                    const idx = subject.originalIndex;
                    const state = subjectSelections[idx] || { selected: false, tier: 1 };
                    const ects = parseFloat(subject.creditos_ects) || 6;
                    const ectsPriceForTier = getEctsPrice(state.tier);
                    const itemCost = ects * ectsPriceForTier;

                    return (
                      <div
                        key={idx}
                        style={{
                          padding: '0.85rem 1rem',
                          borderRadius: '8px',
                          background: state.selected ? 'rgba(0, 168, 204, 0.08)' : 'var(--bg-card)',
                          border: state.selected ? '1px solid var(--uca-cyan)' : '1px solid var(--border-light)',
                          display: 'grid',
                          gridTemplateColumns: 'auto 1fr auto auto',
                          alignItems: 'center',
                          gap: '1rem',
                          transition: 'all 0.2s ease'
                        }}
                      >
                        {/* Checkbox */}
                        <div onClick={() => toggleSubject(idx)} style={{ cursor: 'pointer', display: 'flex', color: state.selected ? 'var(--uca-cyan)' : 'var(--text-muted)' }}>
                          {state.selected ? <CheckSquare size={20} /> : <Square size={20} />}
                        </div>

                        {/* Subject Info */}
                        <div>
                          <div style={{ fontWeight: 600, fontSize: '0.95rem', color: 'var(--text-main)' }}>
                            {subject.nombre_elemento}
                          </div>
                          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'flex', gap: '0.75rem', marginTop: '0.15rem' }}>
                            <span><strong>ECTS:</strong> {ects} cr.</span>
                            {subject.caracter && <span><strong>Tipo:</strong> {subject.caracter}</span>}
                          </div>
                        </div>

                        {/* Enrolment Tier Selector (1ª, 2ª, 3ª, 4ª) */}
                        <div>
                          <select
                            aria-label="Seleccionar número de matrícula"
                            value={state.tier}
                            onChange={(e) => changeTier(idx, e.target.value)}
                            style={{
                              padding: '0.35rem 0.6rem',
                              borderRadius: '6px',
                              background: state.tier > 1 ? 'rgba(245, 158, 11, 0.15)' : 'var(--bg-card)',
                              color: state.tier > 1 ? '#F59E0B' : 'var(--text-main)',
                              border: state.tier > 1 ? '1px solid #F59E0B' : '1px solid var(--border-light)',
                              fontWeight: 600,
                              fontSize: '0.82rem',
                              cursor: 'pointer'
                            }}
                          >
                            <option value={1}>1ª Matrícula ({getEctsPrice(1).toFixed(2)}€/cr)</option>
                            <option value={2}>2ª Matrícula ({getEctsPrice(2).toFixed(2)}€/cr)</option>
                            <option value={3}>3ª Matrícula ({getEctsPrice(3).toFixed(2)}€/cr)</option>
                            <option value={4}>4ª+ Matrícula ({getEctsPrice(4).toFixed(2)}€/cr)</option>
                          </select>
                        </div>

                        {/* Cost Output */}
                        <div style={{ fontWeight: 700, fontSize: '0.95rem', color: state.selected ? '#10B981' : 'var(--text-muted)', textAlign: 'right', minWidth: '80px' }}>
                          {state.selected ? `${itemCost.toFixed(2)} €` : '0.00 €'}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          {/* Right Column: Receipt Breakdown Panel */}
          <div>
            <div className="glass-panel" style={{ padding: '1.5rem', borderRadius: '12px', position: 'sticky', top: '2rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem', paddingBottom: '0.75rem', borderBottom: '1px solid var(--border-light)' }}>
                <Receipt size={22} style={{ color: 'var(--uca-cyan)' }} />
                <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: 'var(--text-main)', margin: 0 }}>
                  Desglose de Matrícula
                </h3>
              </div>

              {/* Price Tariff Details */}
              <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: '1.25rem', background: 'rgba(255, 255, 255, 0.03)', padding: '0.75rem', borderRadius: '8px' }}>
                <div><strong>Universidad:</strong> {currentUniv?.nombre}</div>
                <div style={{ marginTop: '0.2rem' }}><strong>Tarifa 1ª Matrícula:</strong> {baseEctsPrice.toFixed(2)} € / crédito</div>
                <div style={{ marginTop: '0.2rem' }}><strong>Fuente:</strong> {degreeDetail.fuente_precio || 'Decreto CCAA Oficial'}</div>
              </div>

              {/* Discount / Exemption Selector */}
              <div style={{ marginBottom: '1.25rem' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontWeight: 700, fontSize: '0.82rem', color: 'var(--uca-cyan)', marginBottom: '0.4rem' }}>
                  <Sparkles size={16} /> Exención o Bonificación Aplicable
                </label>
                <select
                  aria-label="Seleccionar exención o bonificación"
                  value={discountType}
                  onChange={(e) => setDiscountType(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.55rem 0.75rem',
                    borderRadius: '8px',
                    background: 'var(--bg-card)',
                    color: 'var(--text-main)',
                    border: '1px solid var(--border-light)',
                    fontWeight: 600,
                    fontSize: '0.85rem',
                    outline: 'none',
                    cursor: 'pointer'
                  }}
                >
                  <option value="ninguno">Ordinaria / Sin Descuento (0%)</option>
                  <option value="fn_general">Familia Numerosa General (50% Exención)</option>
                  <option value="fn_especial">Familia Numerosa Especial (100% Exención Total)</option>
                  <option value="discapacidad">Discapacidad ≥ 33% (100% Exención Total)</option>
                  <option value="beca_mec">Solicitante Beca Ministerio MEC (100% 1ª Matrícula)</option>
                  <option value="mh_bachillerato">Matrícula de Honor Bachillerato/CFGS (100% 1º Año)</option>
                  <option value="bonif_99">Bonificación 99% CCAA Rendimiento Académico</option>
                  <option value="victima_violencia">Víctima Violencia Género / Terrorismo / IMV (100%)</option>
                </select>

                {/* Explanatory Info Box for Selected Discount */}
                {DISCOUNT_INFO[discountType] && (
                  <div style={{
                    marginTop: '0.65rem',
                    padding: '0.65rem 0.85rem',
                    borderRadius: '8px',
                    background: 'rgba(0, 168, 204, 0.08)',
                    border: '1px solid rgba(0, 168, 204, 0.25)',
                    fontSize: '0.78rem',
                    color: 'var(--text-main)',
                    lineHeight: 1.45,
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '0.5rem'
                  }}>
                    <AlertCircle size={16} style={{ color: 'var(--uca-cyan)', flexShrink: 0, marginTop: '0.1rem' }} />
                    <div>
                      <strong>Condiciones de Disponibilidad:</strong>
                      <div style={{ marginTop: '0.2rem', color: 'var(--text-muted)' }}>{DISCOUNT_INFO[discountType]}</div>
                    </div>
                  </div>
                )}
              </div>

              {/* Summary Metrics */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.9rem', marginBottom: '1.5rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-main)' }}>
                  <span>Asignaturas Seleccionadas:</span>
                  <strong>{calculation.selectedSubjectsCount}</strong>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-main)' }}>
                  <span>Total Créditos ECTS:</span>
                  <strong>{calculation.totalEcts} ECTS</strong>
                </div>

                {/* Subtotals by Tier */}
                {calculation.tierCounts[1] > 0 && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                    <span>• {calculation.tierCounts[1]} asig. en 1ª Matrícula:</span>
                    <span>{calculation.tierCosts[1].toFixed(2)} €</span>
                  </div>
                )}
                {calculation.tierCounts[2] > 0 && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: '#F59E0B', fontSize: '0.85rem' }}>
                    <span>• {calculation.tierCounts[2]} asig. en 2ª Matrícula:</span>
                    <span>{calculation.tierCosts[2].toFixed(2)} €</span>
                  </div>
                )}
                {calculation.tierCounts[3] > 0 && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: '#EF4444', fontSize: '0.85rem' }}>
                    <span>• {calculation.tierCounts[3]} asig. en 3ª Matrícula:</span>
                    <span>{calculation.tierCosts[3].toFixed(2)} €</span>
                  </div>
                )}
                {calculation.tierCounts[4] > 0 && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: '#DC2626', fontSize: '0.85rem' }}>
                    <span>• {calculation.tierCounts[4]} asig. en 4ª+ Matrícula:</span>
                    <span>{calculation.tierCosts[4].toFixed(2)} €</span>
                  </div>
                )}

                <div style={{ borderTop: '1px dashed var(--border-light)', paddingTop: '0.6rem', display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  <span>Tasas Administración/Secretaría:</span>
                  <span>{calculation.adminFees.toFixed(2)} €</span>
                </div>

                {/* Applied Discount Line */}
                {calculation.discountAmount > 0 && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: '#10B981', fontWeight: 700, fontSize: '0.85rem' }}>
                    <span>🏷️ {calculation.discountLabel}:</span>
                    <span>-{calculation.discountAmount.toFixed(2)} €</span>
                  </div>
                )}
              </div>

              {/* Total Final Price */}
              <div style={{
                padding: '1.25rem',
                borderRadius: '10px',
                background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(16, 185, 129, 0.05) 100%)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                textAlign: 'center',
                marginBottom: '1rem'
              }}>
                <div style={{ fontSize: '0.85rem', color: '#10B981', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  {isPrivada ? '💎 Honorarios Privados Estimados' : '💶 Importe Matrícula Pública Estimada'}
                </div>
                <div style={{ fontSize: '2.2rem', fontWeight: 900, color: '#10B981', margin: '0.3rem 0' }}>
                  {calculation.grandTotal.toFixed(2)} €
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  (Valores oficiales calculados según tarifa ECTS pública)
                </div>
              </div>

              {/* Print Simulation Button */}
              <button
                onClick={() => window.print()}
                className="btn btn-secondary"
                style={{ width: '100%', padding: '0.65rem', fontSize: '0.85rem', fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}
              >
                <Receipt size={16} /> Imprimir / Guardar Simulación
              </button>

            </div>
          </div>

        </div>
      ) : (
        <div className="glass-panel" style={{ padding: '3.5rem 2rem', textAlign: 'center', borderRadius: '12px' }}>
          <div style={{ display: 'inline-flex', padding: '0.85rem', background: 'rgba(243, 167, 18, 0.12)', borderRadius: '50%', color: 'var(--uca-sun)', marginBottom: '1.25rem' }}>
            <AlertCircle size={36} />
          </div>
          <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--text-main)' }}>
            Esta titulación no dispone de asignaturas desglosadas en el BOE
          </h3>
          <p style={{ color: 'var(--text-muted)', maxWidth: '540px', margin: '0 auto', fontSize: '0.92rem', lineHeight: 1.6 }}>
            No se ha encontrado una tabla de asignaturas y créditos lectivos publicada en el BOE para este estudio. Por favor, selecciona otra titulación del selector superior para simular tu matrícula.
          </p>
        </div>
      )}

    </div>
  );
}
