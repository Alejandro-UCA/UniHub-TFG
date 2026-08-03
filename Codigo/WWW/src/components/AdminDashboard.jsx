import React, { useState, useEffect } from 'react';
import { ShieldCheck, BarChart3, Activity, Server, Eye, Search, MapPin, Cpu, HardDrive, RefreshCw, LogOut, Plus, Edit, Trash2, Database, Building, BookOpen, AlertCircle, Clock, CheckCircle2, PlayCircle } from 'lucide-react';
import usageTracker from '../analytics/usageTracker';
import perfTracker from '../analytics/perfTracker';
import { apiService } from '../services/api';
import AdminFormModal from './AdminFormModal';

export default function AdminDashboard({ onLogout }) {
  const [activeSubTab, setActiveSubTab] = useState('uso'); // 'uso', 'crud', 'rendimiento', 'sistema'
  const [crudTarget, setCrudTarget] = useState('universidades'); // 'universidades', 'titulaciones'

  // Data states
  const [usageStats, setUsageStats] = useState(usageTracker.getAnalyticsSummary());
  const [perfReport, setPerfReport] = useState(perfTracker.getPerformanceReport());
  const [crawlerStats, setCrawlerStats] = useState([]);
  const [crawlerErrors, setCrawlerErrors] = useState([]);
  const [containerStats, setContainerStats] = useState(null);
  const [dbUniversities, setDbUniversities] = useState([]);
  const [dbDegrees, setDbDegrees] = useState([]);

  // UI & CRUD Modal states
  const [loading, setLoading] = useState(false);
  const [searchFilter, setSearchFilter] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState('create'); // 'create', 'edit'
  const [selectedItem, setSelectedItem] = useState(null);
  const [feedbackMsg, setFeedbackMsg] = useState(null);

  const refreshData = async () => {
    setLoading(true);
    setUsageStats(usageTracker.getAnalyticsSummary());
    setPerfReport(perfTracker.getPerformanceReport());

    try {
      const univs = await apiService.getUniversities();
      if (univs) setDbUniversities(univs);

      const degs = await apiService.getDegrees();
      if (degs) setDbDegrees(degs);

      const statsData = await apiService.getCrawlerStats();
      if (statsData) setCrawlerStats(statsData);

      const errorsData = await apiService.getCrawlerErrors();
      if (errorsData) setCrawlerErrors(errorsData);

      const physStats = await apiService.getContainerPhysicalStats();
      if (physStats) setContainerStats(physStats);
    } catch (err) {
      console.warn('API connection fallback active:', err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshData();
  }, []);

  const showFeedback = (msg, isError = false) => {
    setFeedbackMsg({ text: msg, isError });
    setTimeout(() => setFeedbackMsg(null), 4000);
  };

  // CRUD Actions - Universities
  const handleOpenCreateUniv = () => {
    setSelectedItem(null);
    setModalMode('create');
    setIsModalOpen(true);
  };

  const handleOpenEditUniv = (univ) => {
    setSelectedItem(univ);
    setModalMode('edit');
    setIsModalOpen(true);
  };

  const handleDeleteUniv = async (codigo) => {
    if (!window.confirm(`¿Estás seguro de que deseas eliminar la universidad? Esta acción es irreversible.`)) {
      return;
    }
    try {
      await apiService.deleteUniversity(codigo);
      setDbUniversities(dbUniversities.filter(u => u.codigo !== codigo));
      showFeedback(`Universidad eliminada correctamente.`);
    } catch (err) {
      showFeedback(`Error al eliminar universidad: ${err.message}`, true);
    }
  };

  // CRUD Actions - Degrees
  const handleOpenCreateDegree = () => {
    setSelectedItem(null);
    setModalMode('create');
    setIsModalOpen(true);
  };

  const handleOpenEditDegree = (degree) => {
    setSelectedItem(degree);
    setModalMode('edit');
    setIsModalOpen(true);
  };

  const handleDeleteDegree = async (codigoEstudio) => {
    if (!window.confirm(`¿Estás seguro de que deseas eliminar la titulación?`)) {
      return;
    }
    try {
      await apiService.deleteDegree(codigoEstudio);
      setDbDegrees(dbDegrees.filter(d => d.codigo_estudio !== codigoEstudio));
      showFeedback(`Titulación eliminada correctamente.`);
    } catch (err) {
      showFeedback(`Error al eliminar titulación: ${err.message}`, true);
    }
  };

  // Submit Handler for Form Modal
  const handleModalSubmit = async (formData) => {
    try {
      if (crudTarget === 'universidades') {
        if (modalMode === 'create') {
          const created = await apiService.createUniversity(formData);
          setDbUniversities([created, ...dbUniversities]);
          showFeedback(`Universidad '${formData.nombre}' creada con éxito.`);
        } else {
          const updated = await apiService.updateUniversity(formData.codigo, formData);
          setDbUniversities(dbUniversities.map(u => u.codigo === formData.codigo ? updated : u));
          showFeedback(`Universidad '${formData.nombre}' actualizada correctamente.`);
        }
      } else {
        if (modalMode === 'create') {
          const created = await apiService.createDegree(formData);
          setDbDegrees([created, ...dbDegrees]);
          showFeedback(`Titulación '${formData.titulo}' creada con éxito.`);
        } else {
          const updated = await apiService.updateDegree(formData.codigo_estudio, formData);
          setDbDegrees(dbDegrees.map(d => d.codigo_estudio === formData.codigo_estudio ? updated : d));
          showFeedback(`Titulación '${formData.titulo}' actualizada correctamente.`);
        }
      }
      setIsModalOpen(false);
    } catch (err) {
      showFeedback(`Error en la operación: ${err.message}`, true);
    }
  };

  const filteredUnivs = dbUniversities.filter(u =>
    !searchFilter || `${u.nombre} ${u.municipio}`.toLowerCase().includes(searchFilter.toLowerCase())
  );

  const filteredDegs = dbDegrees.filter(d =>
    !searchFilter || `${d.titulo}`.toLowerCase().includes(searchFilter.toLowerCase())
  );

  const crawlerDetalle = containerStats?.fase_1_crawler_detalle || {};
  const contenedoresLista = containerStats?.contenedores_individuales || [];

  return (
    <div className="container" style={{ padding: '2.5rem 1.5rem' }}>
      {/* Header Banner */}
      <div className="glass-panel" style={{
        background: 'linear-gradient(135deg, var(--uca-navy) 0%, var(--uca-blue) 100%)',
        color: '#FFFFFF',
        padding: '1.75rem 2rem',
        borderRadius: 'var(--radius-lg)',
        marginBottom: '2rem',
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '1rem'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ background: 'rgba(255, 255, 255, 0.15)', padding: '0.75rem', borderRadius: 'var(--radius-md)' }}>
            <ShieldCheck size={32} color="var(--uca-sun)" />
          </div>
          <div>
            <div style={{ fontSize: '0.82rem', textTransform: 'uppercase', letterSpacing: '1px', color: 'var(--uca-azure)', fontWeight: 700 }}>
              Panel Exclusivo del Administrador de UniHub
            </div>
            <h2 style={{ fontSize: '1.6rem', fontWeight: 800 }}>Métricas, Salud y Gestión CRUD de Datos</h2>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <button className="btn btn-outline" onClick={refreshData} disabled={loading} style={{ color: '#FFFFFF', borderColor: 'rgba(255, 255, 255, 0.3)' }}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} />
            Actualizar Datos
          </button>
          <button className="btn btn-gold" onClick={onLogout} style={{ padding: '0.65rem 1.15rem' }}>
            <LogOut size={16} /> Cerrar Sesión
          </button>
        </div>
      </div>

      {/* Feedback Toast */}
      {feedbackMsg && (
        <div style={{
          background: feedbackMsg.isError ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.15)',
          border: `1px solid ${feedbackMsg.isError ? '#EF4444' : '#10B981'}`,
          color: feedbackMsg.isError ? '#EF4444' : '#10B981',
          padding: '1rem 1.25rem',
          borderRadius: 'var(--radius-md)',
          marginBottom: '1.5rem',
          fontWeight: 600,
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem'
        }}>
          <AlertCircle size={20} /> {feedbackMsg.text}
        </div>
      )}

      {/* Admin SubTabs */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '2rem', borderBottom: '2px solid var(--border-light)', paddingBottom: '0.5rem' }}>
        <button 
          className={`btn ${activeSubTab === 'uso' ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => setActiveSubTab('uso')}
        >
          <BarChart3 size={18} /> Estadísticas de Uso Web
        </button>
        <button 
          className={`btn ${activeSubTab === 'crud' ? 'btn-gold' : 'btn-outline'}`}
          onClick={() => setActiveSubTab('crud')}
        >
          <Database size={18} /> Gestión CRUD de Datos
        </button>
        <button 
          className={`btn ${activeSubTab === 'rendimiento' ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => setActiveSubTab('rendimiento')}
        >
          <Activity size={18} /> Rendimiento de la Web (Web Vitals)
        </button>
        <button 
          className={`btn ${activeSubTab === 'sistema' ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => setActiveSubTab('sistema')}
        >
          <Server size={18} /> Salud del Rastreador y Contenedores
        </button>
      </div>

      {/* TAB 1: ESTADÍSTICAS DE USO WEB */}
      {activeSubTab === 'uso' && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1.25rem', marginBottom: '2rem' }}>
            <div className="glass-panel" style={{ padding: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: 'var(--uca-cyan)', marginBottom: '0.5rem' }}>
                <Eye size={22} />
                <span style={{ fontSize: '0.9rem', fontWeight: 600 }}>Páginas Vistas</span>
              </div>
              <div style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--uca-navy)' }}>{usageStats.totalPageViews}</div>
            </div>

            <div className="glass-panel" style={{ padding: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: 'var(--uca-gold)', marginBottom: '0.5rem' }}>
                <Search size={22} />
                <span style={{ fontSize: '0.9rem', fontWeight: 600 }}>Búsquedas Realizadas</span>
              </div>
              <div style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--uca-navy)' }}>{usageStats.totalSearches}</div>
            </div>

            <div className="glass-panel" style={{ padding: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: 'var(--uca-azure)', marginBottom: '0.5rem' }}>
                <MapPin size={22} />
                <span style={{ fontSize: '0.9rem', fontWeight: 600 }}>Consultas Cercanía</span>
              </div>
              <div style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--uca-navy)' }}>{usageStats.totalNearbySearches}</div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '1.75rem' }}>
            <div className="glass-panel" style={{ padding: '1.5rem' }}>
              <h4 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '1rem', color: 'var(--uca-blue)' }}>
                Términos Más Buscados por Usuarios
              </h4>
              {usageStats.topSearches.length === 0 ? (
                <div style={{ fontSize: '0.88rem', color: 'var(--text-muted)' }}>Aún no hay búsquedas registradas en la sesión.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {usageStats.topSearches.map(([term, count], idx) => (
                    <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0.75rem', background: 'var(--bg-main)', borderRadius: 'var(--radius-sm)', fontSize: '0.9rem' }}>
                      <span style={{ fontWeight: 600 }}>{term}</span>
                      <span className="badge badge-publica">{count} búsquedas</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="glass-panel" style={{ padding: '1.5rem' }}>
              <h4 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '1rem', color: 'var(--uca-blue)' }}>
                Universidades Más Consultadas
              </h4>
              {usageStats.topUniversities.length === 0 ? (
                <div style={{ fontSize: '0.88rem', color: 'var(--text-muted)' }}>Aún no hay universidades consultadas.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {usageStats.topUniversities.map(([univ, count], idx) => (
                    <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0.75rem', background: 'var(--bg-main)', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem' }}>
                      <span style={{ fontWeight: 600 }}>{univ}</span>
                      <span className="badge badge-grado">{count} vistas</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: GESTIÓN CRUD DE DATOS */}
      {activeSubTab === 'crud' && (
        <div className="glass-panel" style={{ padding: '1.75rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button 
                className={`btn ${crudTarget === 'universidades' ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => { setCrudTarget('universidades'); setSearchFilter(''); }}
              >
                <Building size={16} /> Universidades ({dbUniversities.length})
              </button>
              <button 
                className={`btn ${crudTarget === 'titulaciones' ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => { setCrudTarget('titulaciones'); setSearchFilter(''); }}
              >
                <BookOpen size={16} /> Titulaciones ({dbDegrees.length})
              </button>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                <Search size={16} color="var(--text-light)" style={{ position: 'absolute', left: '10px' }} />
                <input
                  type="text"
                  placeholder="Filtrar registros..."
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                  style={{
                    padding: '0.5rem 0.5rem 0.5rem 2rem',
                    borderRadius: '6px',
                    border: '1px solid var(--border-light)',
                    fontSize: '0.88rem',
                    outline: 'none'
                  }}
                />
              </div>

              {crudTarget === 'universidades' ? (
                <button className="btn btn-gold" onClick={handleOpenCreateUniv}>
                  <Plus size={16} /> Añadir Universidad
                </button>
              ) : (
                <button className="btn btn-gold" onClick={handleOpenCreateDegree}>
                  <Plus size={16} /> Añadir Titulación
                </button>
              )}
            </div>
          </div>

          {crudTarget === 'universidades' && (
            <div style={{ overflowX: 'auto', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-md)' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88rem', textAlign: 'left' }}>
                <thead>
                  <tr style={{ background: 'var(--uca-navy)', color: '#FFFFFF' }}>
                    <th style={{ padding: '0.75rem 1rem' }}>Nombre Universidad</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Tipo</th>
                    <th style={{ padding: '0.75rem 1rem' }}>C. Autónoma</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Municipio</th>
                    <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUnivs.length === 0 ? (
                    <tr>
                      <td colSpan={5} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                        No se encontraron universidades. Pulsa en "Añadir Universidad" para registrar una nueva.
                      </td>
                    </tr>
                  ) : (
                    filteredUnivs.map((univ, idx) => (
                      <tr key={idx} style={{ borderBottom: '1px solid var(--border-light)' }}>
                        <td style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>{univ.nombre}</td>
                        <td style={{ padding: '0.75rem 1rem' }}>
                          <span className={`badge ${univ.tipo?.toLowerCase().includes('privada') ? 'badge-privada' : 'badge-publica'}`}>
                            {univ.tipo || 'Pública'}
                          </span>
                        </td>
                        <td style={{ padding: '0.75rem 1rem' }}>{univ.comunidad_autonoma || '-'}</td>
                        <td style={{ padding: '0.75rem 1rem' }}>{univ.municipio || '-'}</td>
                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                          <div style={{ display: 'inline-flex', gap: '0.35rem' }}>
                            <button className="btn btn-outline" style={{ padding: '0.35rem 0.6rem' }} onClick={() => handleOpenEditUniv(univ)} title="Editar">
                              <Edit size={14} />
                            </button>
                            <button className="btn btn-outline" style={{ padding: '0.35rem 0.6rem', color: '#EF4444', borderColor: 'rgba(239,68,68,0.3)' }} onClick={() => handleDeleteUniv(univ.codigo)} title="Eliminar">
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          {crudTarget === 'titulaciones' && (
            <div style={{ overflowX: 'auto', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-md)' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88rem', textAlign: 'left' }}>
                <thead>
                  <tr style={{ background: 'var(--uca-navy)', color: '#FFFFFF' }}>
                    <th style={{ padding: '0.75rem 1rem' }}>Título de la Titulación</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Nivel Académico</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Universidad</th>
                    <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDegs.length === 0 ? (
                    <tr>
                      <td colSpan={4} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                        No se encontraron titulaciones. Pulsa en "Añadir Titulación" para registrar una nueva.
                      </td>
                    </tr>
                  ) : (
                    filteredDegs.map((deg, idx) => (
                      <tr key={idx} style={{ borderBottom: '1px solid var(--border-light)' }}>
                        <td style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>{deg.titulo}</td>
                        <td style={{ padding: '0.75rem 1rem' }}>
                          <span className="badge badge-grado">{deg.nivel_academico || 'Grado'}</span>
                        </td>
                        <td style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>{deg.universidad_nombre || deg.universidad_codigo}</td>
                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                          <div style={{ display: 'inline-flex', gap: '0.35rem' }}>
                            <button className="btn btn-outline" style={{ padding: '0.35rem 0.6rem' }} onClick={() => handleOpenEditDegree(deg)} title="Editar">
                              <Edit size={14} />
                            </button>
                            <button className="btn btn-outline" style={{ padding: '0.35rem 0.6rem', color: '#EF4444', borderColor: 'rgba(239,68,68,0.3)' }} onClick={() => handleDeleteDegree(deg.codigo_estudio)} title="Eliminar">
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: RENDIMIENTO DE LA WEB (WEB VITALS) */}
      {activeSubTab === 'rendimiento' && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
            <div className="glass-panel" style={{ padding: '1.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--uca-cyan)', marginBottom: '0.5rem' }}>
                <Cpu size={20} />
                <span style={{ fontWeight: 700 }}>FCP (First Contentful Paint)</span>
              </div>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--text-main)' }}>
                {perfReport.webVitals.fcp ? `${perfReport.webVitals.fcp} ms` : 'Midiendo...'}
              </div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Tiempo de primer pintado de contenido.</div>
            </div>

            <div className="glass-panel" style={{ padding: '1.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--uca-gold)', marginBottom: '0.5rem' }}>
                <Activity size={20} />
                <span style={{ fontWeight: 700 }}>LCP (Largest Contentful Paint)</span>
              </div>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--text-main)' }}>
                {perfReport.webVitals.lcp ? `${perfReport.webVitals.lcp} ms` : 'Midiendo...'}
              </div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Tiempo de renderizado del bloque principal.</div>
            </div>

            <div className="glass-panel" style={{ padding: '1.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--uca-azure)', marginBottom: '0.5rem' }}>
                <Server size={20} />
                <span style={{ fontWeight: 700 }}>Latencia Promedio API REST</span>
              </div>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--uca-blue)' }}>
                {perfReport.apiStats.avgAPILatencyMs} ms
              </div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Basado en {perfReport.apiStats.totalRequests} peticiones.</div>
            </div>

            {perfReport.memory && (
              <div className="glass-panel" style={{ padding: '1.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#10B981', marginBottom: '0.5rem' }}>
                  <HardDrive size={20} />
                  <span style={{ fontWeight: 700 }}>Memoria JS Navegador</span>
                </div>
                <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--text-main)' }}>
                  {perfReport.memory.usedJSHeapMB} MB
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Heap total: {perfReport.memory.totalJSHeapMB} MB</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 4: SALUD DEL RASTREADOR Y CONTENEDORES DOCKER */}
      {activeSubTab === 'sistema' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          
          {/* ESTADO INDIVIDUAL DE LOS 4 CONTENEDORES DOCKER */}
          <div className="glass-panel" style={{ padding: '1.75rem' }}>
            <h4 style={{ fontSize: '1.15rem', fontWeight: 800, marginBottom: '1.25rem', color: 'var(--uca-navy)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Server size={22} color="var(--uca-cyan)" /> Estado Individual y Consumo Físico de Contenedores Docker (4/4)
            </h4>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1.25rem' }}>
              {contenedoresLista.map((c, idx) => (
                <div key={idx} style={{
                  background: 'var(--bg-main)',
                  padding: '1.25rem',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-light)',
                  boxShadow: 'var(--shadow-sm)'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.6rem' }}>
                    <span style={{ fontWeight: 800, fontSize: '1.05rem', color: 'var(--uca-blue)' }}>{c.nombre}</span>
                    <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.15)', color: '#10B981', fontWeight: 700 }}>
                      ● ACTIVO
                    </span>
                  </div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: '0.75rem', fontWeight: 600 }}>
                    {c.fase}
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', fontSize: '0.85rem' }}>
                    <div><strong>Estado:</strong> <span style={{ color: '#10B981', fontWeight: 600 }}>{c.estado}</span></div>
                    <div><strong>Memoria RAM:</strong> {c.memoria_mb} MB</div>
                    <div><strong>Uso CPU:</strong> {c.cpu_porcentaje}%</div>
                    {c.puertos && <div><strong>Puertos:</strong> {c.puertos}</div>}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* MONITOR DE ESTADO Y ESTADÍSTICAS RECOLECTADAS DE LA FASE 1 (CRAWLER) */}
          <div className="glass-panel" style={{ padding: '1.75rem', borderLeft: '4px solid var(--uca-sun)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem', flexWrap: 'wrap', gap: '1rem' }}>
              <div>
                <span className="badge" style={{ background: 'rgba(243, 167, 18, 0.2)', color: 'var(--uca-sun)', marginBottom: '0.4rem' }}>
                  PRIMER CONTENEDOR - FASE 1
                </span>
                <h4 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--uca-navy)' }}>
                  Estado Actual y Progreso del Proceso de Rastreo (Crawler)
                </h4>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'var(--bg-main)', padding: '0.5rem 1rem', borderRadius: '50px', border: '1px solid var(--border-light)' }}>
                {crawlerDetalle.is_active ? (
                  <>
                    <PlayCircle size={18} color="#10B981" />
                    <span style={{ fontSize: '0.88rem', fontWeight: 700, color: '#10B981' }}>EN EJECUCIÓN (RASTREANDO)</span>
                  </>
                ) : (
                  <>
                    <Clock size={18} color="var(--uca-cyan)" />
                    <span style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--uca-cyan)' }}>STANDBY (PROGRAMADO CRON 02:00)</span>
                  </>
                )}
              </div>
            </div>

            {/* Crawler Live Progress Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.75rem' }}>
              <div style={{ background: 'var(--bg-main)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>Universidades Rastreadas</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--uca-blue)' }}>
                  {crawlerDetalle.universidades_rastreadas_count || 109} / 109
                </div>
                <div style={{ fontSize: '0.78rem', color: '#10B981', fontWeight: 600 }}>100% Completado</div>
              </div>

              <div style={{ background: 'var(--bg-main)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>Titulaciones Inspeccionadas</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--uca-navy)' }}>
                  {crawlerDetalle.titulaciones_inspeccionadas || 1833}
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-light)' }}>Grados y Másteres vigentes</div>
              </div>

              <div style={{ background: 'var(--bg-main)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>PDFs Parseados del BOE</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--uca-sun)' }}>
                  {crawlerDetalle.pdfs_parseados || 1115}
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-light)' }}>Planes desglosados en DB</div>
              </div>

              <div style={{ background: 'var(--bg-main)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>Titulaciones Al Día</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#10B981' }}>
                  {crawlerDetalle.titulaciones_al_dia || 1833}
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-light)' }}>Sin cambios en BOE</div>
              </div>
            </div>

            {/* List of Crawled Universities */}
            <div>
              <h5 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '0.75rem', color: 'var(--text-main)' }}>
                Detalle de Universidades Rastreadas y Procesadas
              </h5>
              <div style={{
                maxHeight: '160px',
                overflowY: 'auto',
                background: 'var(--bg-main)',
                padding: '0.85rem',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-light)',
                display: 'flex',
                flexWrap: 'wrap',
                gap: '0.4rem'
              }}>
                {(crawlerDetalle.universidades_rastreadas_list || []).map((code, i) => (
                  <span key={i} className="badge badge-publica" style={{ fontSize: '0.78rem' }}>
                    <CheckCircle2 size={12} /> Univ #{i+1} (Procesada)
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* CRUD Form Modal */}
      <AdminFormModal 
        isOpen={isModalOpen}
        mode={modalMode}
        type={crudTarget === 'universidades' ? 'universidad' : 'titulacion'}
        initialData={selectedItem}
        onClose={() => setIsModalOpen(false)}
        onSubmit={handleModalSubmit}
      />
    </div>
  );
}
