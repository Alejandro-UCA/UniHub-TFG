import React, { useState, useEffect } from 'react';
import { ShieldCheck, BarChart3, Activity, Server, Eye, Search, MapPin, Cpu, HardDrive, RefreshCw, LogOut, Plus, Edit, Trash2, Database, Building, BookOpen, AlertCircle, Clock, Disc } from 'lucide-react';
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
    if (!window.confirm(`¿Estás seguro de que deseas eliminar la universidad [${codigo}]? Esta acción es irreversible.`)) {
      return;
    }
    try {
      await apiService.deleteUniversity(codigo);
      setDbUniversities(dbUniversities.filter(u => u.codigo !== codigo));
      showFeedback(`Universidad [${codigo}] eliminada correctamente.`);
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
    if (!window.confirm(`¿Estás seguro de que deseas eliminar la titulación [${codigoEstudio}]?`)) {
      return;
    }
    try {
      await apiService.deleteDegree(codigoEstudio);
      setDbDegrees(dbDegrees.filter(d => d.codigo_estudio !== codigoEstudio));
      showFeedback(`Titulación [${codigoEstudio}] eliminada correctamente.`);
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
    !searchFilter || `${u.codigo} ${u.nombre} ${u.municipio}`.toLowerCase().includes(searchFilter.toLowerCase())
  );

  const filteredDegs = dbDegrees.filter(d =>
    !searchFilter || `${d.codigo_estudio} ${d.titulo} ${d.universidad_codigo}`.toLowerCase().includes(searchFilter.toLowerCase())
  );

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
              Panel Exclusivo del Administrador de la Web
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
                    <th style={{ padding: '0.75rem 1rem' }}>Código</th>
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
                      <td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                        No se encontraron universidades. Pulsa en "Añadir Universidad" para registrar una nueva.
                      </td>
                    </tr>
                  ) : (
                    filteredUnivs.map((univ) => (
                      <tr key={univ.codigo} style={{ borderBottom: '1px solid var(--border-light)' }}>
                        <td style={{ padding: '0.75rem 1rem', fontWeight: 700, color: 'var(--uca-cyan)' }}>{univ.codigo}</td>
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
                    <th style={{ padding: '0.75rem 1rem' }}>Cód. Estudio</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Título de la Titulación</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Nivel Académico</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Cód. Univ.</th>
                    <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDegs.length === 0 ? (
                    <tr>
                      <td colSpan={5} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                        No se encontraron titulaciones. Pulsa en "Añadir Titulación" para registrar una nueva.
                      </td>
                    </tr>
                  ) : (
                    filteredDegs.map((deg) => (
                      <tr key={deg.codigo_estudio} style={{ borderBottom: '1px solid var(--border-light)' }}>
                        <td style={{ padding: '0.75rem 1rem', fontWeight: 700, color: 'var(--uca-blue)' }}>{deg.codigo_estudio}</td>
                        <td style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>{deg.titulo}</td>
                        <td style={{ padding: '0.75rem 1rem' }}>
                          <span className="badge badge-grado">{deg.nivel_academico || 'Grado'}</span>
                        </td>
                        <td style={{ padding: '0.75rem 1rem', fontWeight: 700 }}>{deg.universidad_codigo}</td>
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

      {/* TAB 4: SALUD DEL RASTREADOR Y CONSUMO FÍSICO DE CONTENEDORES DOCKER */}
      {activeSubTab === 'sistema' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          {/* Cron Schedule Info Banner */}
          <div className="glass-panel" style={{ background: 'linear-gradient(135deg, rgba(0, 43, 73, 0.95), rgba(0, 132, 200, 0.85))', color: '#FFFFFF', padding: '1.5rem', borderRadius: 'var(--radius-md)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
              <Clock size={24} color="var(--uca-sun)" />
              <h4 style={{ fontSize: '1.15rem', fontWeight: 800 }}>Programación Cron Activa en Contenedor Crawler (Fase 1)</h4>
            </div>
            <p style={{ fontSize: '0.9rem', color: '#E2E8F0' }}>
              El contenedor <strong>ruct_crawler</strong> ejecuta la sincronización de datos de forma automatizada cada mes el día <strong>1 de cada mes a las 2:00 AM (<code style={{ background: 'rgba(255,255,255,0.2)', padding: '0.1rem 0.4rem', borderRadius: '4px' }}>0 2 1 * *</code>)</strong>.
            </p>
          </div>

          {/* Physical Resource Container Metrics */}
          {containerStats && (
            <div className="glass-panel" style={{ padding: '1.75rem' }}>
              <h4 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.25rem', color: 'var(--uca-blue)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <HardDrive size={20} color="var(--uca-cyan)" /> Consumo Físico de Recursos de los Contenedores Docker
              </h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: '1.25rem' }}>
                <div style={{ background: 'var(--bg-main)', padding: '1.1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                  <div style={{ fontSize: '0.8rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700 }}>Memoria RAM Máxima (RSS)</div>
                  <div style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--uca-navy)' }}>
                    {containerStats.memoria_fisica.rss_actual_mb} MB
                  </div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-light)', marginTop: '0.25rem' }}>
                    Virtual (VSZ): {containerStats.memoria_fisica.vsz_virtual_mb} MB ({containerStats.memoria_fisica.memoria_sistema_usada_porcentaje}% sistema)
                  </div>
                </div>

                <div style={{ background: 'var(--bg-main)', padding: '1.1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                  <div style={{ fontSize: '0.8rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700 }}>Espacio en Disco (Datos JSON/PDF)</div>
                  <div style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--uca-blue)' }}>
                    {containerStats.almacenamiento_disco.datos_json_y_pdf_mb} MB
                  </div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-light)', marginTop: '0.25rem' }}>
                    Equivalente a {containerStats.almacenamiento_disco.datos_json_y_pdf_gb} GB en disco
                  </div>
                </div>

                <div style={{ background: 'var(--bg-main)', padding: '1.1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                  <div style={{ fontSize: '0.8rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700 }}>Procesador CPU & Hilos</div>
                  <div style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--uca-gold)' }}>
                    {containerStats.procesador_cpu.porcentaje_cpu_actual}% CPU
                  </div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-light)', marginTop: '0.25rem' }}>
                    CPU Acumulada: {containerStats.procesador_cpu.tiempo_cpu_acumulado_seg}s ({containerStats.procesador_cpu.num_hilos_activos} hilos)
                  </div>
                </div>

                <div style={{ background: 'var(--bg-main)', padding: '1.1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                  <div style={{ fontSize: '0.8rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700 }}>Partición del Disco Anfitrión</div>
                  <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#10B981' }}>
                    {containerStats.almacenamiento_disco.porcentaje_disco_usado}% Usado
                  </div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-light)', marginTop: '0.25rem' }}>
                    Libre: {containerStats.almacenamiento_disco.disco_libre_sistema_gb} GB de {containerStats.almacenamiento_disco.disco_total_sistema_gb} GB
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Crawler History Logs */}
          <div className="glass-panel" style={{ padding: '1.75rem' }}>
            <h4 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.25rem', color: 'var(--uca-blue)' }}>
              Registro de Ejecuciones del Rastreador de la Fase 1
            </h4>

            {crawlerStats.length === 0 ? (
              <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                No se han recibido registros recientes del crawler a través de la API REST de la Fase 2.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {crawlerStats.map((st, idx) => (
                  <div key={idx} style={{ background: 'var(--bg-main)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                    <div style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--uca-cyan)', marginBottom: '0.5rem' }}>
                      Reporte del {st.timestamp_reporte ? new Date(st.timestamp_reporte).toLocaleString() : 'Reciente'}
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.75rem', fontSize: '0.85rem' }}>
                      <div><strong>Memoria usada:</strong> {st.uso_memoria_actual_mb} MB</div>
                      <div><strong>Pico Memoria:</strong> {st.pico_maximo_memoria_mb} MB</div>
                      <div><strong>Tiempo total:</strong> {st.tiempo_total_ejecucion_seg} s</div>
                      <div><strong>PDFs Parseados:</strong> {st.pdfs_parseados}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
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
