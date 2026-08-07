import React, { useState, useEffect } from 'react';
import { ShieldCheck, BarChart3, Activity, Server, Eye, Search, MapPin, Cpu, HardDrive, RefreshCw, LogOut, Plus, Edit, Trash2, Database, Building, BookOpen, AlertCircle, Clock, CheckCircle2, PlayCircle, Code, FileText, ExternalLink, AlertTriangle, FileX, WifiOff, Terminal } from 'lucide-react';
import usageTracker from '../analytics/usageTracker';
import perfTracker from '../analytics/perfTracker';
import { apiService } from '../services/api';
import AdminFormModal from './AdminFormModal';

export default function AdminDashboard({ onLogout }) {
  const [activeSubTab, setActiveSubTab] = useState('uso'); // 'uso', 'crud', 'rendimiento', 'sistema', 'api_docs'
  const [crudTarget, setCrudTarget] = useState('universidades'); // 'universidades', 'titulaciones'

  // Data states
  const [usageStats, setUsageStats] = useState(usageTracker.getAnalyticsSummary());
  const [perfReport, setPerfReport] = useState(perfTracker.getPerformanceReport());
  const [crawlerStats, setCrawlerStats] = useState([]);
  const [crawlerErrors, setCrawlerErrors] = useState([]);
  const [containerStats, setContainerStats] = useState(null);
  const [dbUniversities, setDbUniversities] = useState([]);
  const [dbDegrees, setDbDegrees] = useState([]);
  const [checkpointData, setCheckpointData] = useState(null);
  const [errorsLogData, setErrorsLogData] = useState([]);
  const [apiDocsInfoData, setApiDocsInfoData] = useState(null);

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
      const univs = await apiService.getUniversities({ limit: 500 });
      if (univs) setDbUniversities(univs);

      const degs = await apiService.getDegrees({ limit: 500 });
      if (degs) setDbDegrees(degs);

      const statsData = await apiService.getCrawlerStats();
      if (statsData) setCrawlerStats(statsData);

      const errorsData = await apiService.getCrawlerErrors();
      if (errorsData) setCrawlerErrors(errorsData);

      const physStats = await apiService.getContainerPhysicalStats();
      if (physStats) setContainerStats(physStats);

      const cpData = await apiService.getCrawlerCheckpoint();
      if (cpData) setCheckpointData(cpData);

      const errLog = await apiService.getCrawlerErrorsLog();
      if (errLog) setErrorsLogData(errLog);

      const docsInfo = await apiService.getApiDocsInfo();
      if (docsInfo) setApiDocsInfoData(docsInfo);
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

  const handleTriggerEtlSync = async () => {
    try {
      setLoading(true);
      await apiService.triggerEtlSync();
      showFeedback('Sincronización ETL relacional iniciada en segundo plano en PostgreSQL.');
      setTimeout(refreshData, 10000); // 10 segundos para dar tiempo a procesar 13,000 JSONs
    } catch (err) {
      showFeedback(`Error al desencadenar sincronización ETL: ${err.message}`, true);
    } finally {
      setLoading(false);
    }
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
      refreshData();
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
      refreshData();
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
          <button className="btn btn-outline" onClick={handleTriggerEtlSync} disabled={loading} style={{ color: 'var(--uca-sun)', borderColor: 'var(--uca-sun)' }}>
            <Database size={16} /> Sincronizar Datos ETL
          </button>
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
        <button 
          className={`btn ${activeSubTab === 'api_docs' ? 'btn-gold' : 'btn-outline'}`}
          onClick={() => setActiveSubTab('api_docs')}
        >
          <Code size={18} /> Documentación y Capacidades API
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
                      <span className="badge badge-privada">{count} vistas</span>
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
        <div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                className={`btn ${crudTarget === 'universidades' ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => setCrudTarget('universidades')}
              >
                <Building size={16} /> Universidades ({dbUniversities.length})
              </button>
              <button
                className={`btn ${crudTarget === 'titulaciones' ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => setCrudTarget('titulaciones')}
              >
                <BookOpen size={16} /> Titulaciones ({dbDegrees.length})
              </button>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <div style={{ position: 'relative', width: '240px' }}>
                <Search size={16} style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                <input
                  type="text"
                  placeholder="Filtrar registros..."
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.5rem 0.75rem 0.5rem 2.2rem',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-light)',
                    fontSize: '0.88rem'
                  }}
                />
              </div>

              {crudTarget === 'universidades' ? (
                <button className="btn btn-gold" onClick={handleOpenCreateUniv}>
                  <Plus size={16} /> Crear Universidad
                </button>
              ) : (
                <button className="btn btn-gold" onClick={handleOpenCreateDegree}>
                  <Plus size={16} /> Crear Titulación
                </button>
              )}
            </div>
          </div>

          {crudTarget === 'universidades' ? (
            <div className="glass-panel" style={{ padding: '1rem', overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88rem' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid var(--border-light)', textAlign: 'left' }}>
                    <th style={{ padding: '0.75rem' }}>Código</th>
                    <th style={{ padding: '0.75rem' }}>Nombre</th>
                    <th style={{ padding: '0.75rem' }}>Tipo</th>
                    <th style={{ padding: '0.75rem' }}>Comunidad Autónoma</th>
                    <th style={{ padding: '0.75rem', textAlign: 'right' }}>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUnivs.map((u) => (
                    <tr key={u.codigo} style={{ borderBottom: '1px solid var(--border-light)' }}>
                      <td style={{ padding: '0.75rem', fontWeight: 700 }}>{u.codigo}</td>
                      <td style={{ padding: '0.75rem', fontWeight: 600 }}>{u.nombre}</td>
                      <td style={{ padding: '0.75rem' }}>
                        <span className={`badge ${u.tipo?.toLowerCase().includes('pública') ? 'badge-publica' : 'badge-privada'}`}>
                          {u.tipo}
                        </span>
                      </td>
                      <td style={{ padding: '0.75rem' }}>{u.comunidad_autonoma}</td>
                      <td style={{ padding: '0.75rem', textAlign: 'right' }}>
                        <button className="btn btn-outline" onClick={() => handleOpenEditUniv(u)} style={{ padding: '0.3rem 0.6rem', marginRight: '0.4rem' }}>
                          <Edit size={14} />
                        </button>
                        <button className="btn btn-outline" onClick={() => handleDeleteUniv(u.codigo)} style={{ padding: '0.3rem 0.6rem', color: '#EF4444', borderColor: 'rgba(239, 68, 68, 0.3)' }}>
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="glass-panel" style={{ padding: '1rem', overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88rem' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid var(--border-light)', textAlign: 'left' }}>
                    <th style={{ padding: '0.75rem' }}>Código</th>
                    <th style={{ padding: '0.75rem' }}>Título</th>
                    <th style={{ padding: '0.75rem' }}>Nivel</th>
                    <th style={{ padding: '0.75rem' }}>Univ Código</th>
                    <th style={{ padding: '0.75rem', textAlign: 'right' }}>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDegs.map((d) => (
                    <tr key={d.codigo_estudio} style={{ borderBottom: '1px solid var(--border-light)' }}>
                      <td style={{ padding: '0.75rem', fontWeight: 700 }}>{d.codigo_estudio}</td>
                      <td style={{ padding: '0.75rem', fontWeight: 600 }}>{d.titulo}</td>
                      <td style={{ padding: '0.75rem' }}>{d.nivel_academico}</td>
                      <td style={{ padding: '0.75rem' }}>{d.universidad_codigo}</td>
                      <td style={{ padding: '0.75rem', textAlign: 'right' }}>
                        <button className="btn btn-outline" onClick={() => handleOpenEditDegree(d)} style={{ padding: '0.3rem 0.6rem', marginRight: '0.4rem' }}>
                          <Edit size={14} />
                        </button>
                        <button className="btn btn-outline" onClick={() => handleDeleteDegree(d.codigo_estudio)} style={{ padding: '0.3rem 0.6rem', color: '#EF4444', borderColor: 'rgba(239, 68, 68, 0.3)' }}>
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: RENDIMIENTO DE LA WEB */}
      {activeSubTab === 'rendimiento' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem' }}>
          <div className="glass-panel" style={{ padding: '1.5rem' }}>
            <h4 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1rem', color: 'var(--uca-navy)' }}>
              Core Web Vitals del Navegador
            </h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-main)', borderRadius: 'var(--radius-sm)' }}>
                <span>TTFB (Time to First Byte):</span>
                <strong>{perfReport.webVitals.TTFB ? `${perfReport.webVitals.TTFB} ms` : 'Medida en progreso'}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-main)', borderRadius: 'var(--radius-sm)' }}>
                <span>FCP (First Contentful Paint):</span>
                <strong>{perfReport.webVitals.FCP ? `${perfReport.webVitals.FCP} ms` : 'Medida en progreso'}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-main)', borderRadius: 'var(--radius-sm)' }}>
                <span>LCP (Largest Contentful Paint):</span>
                <strong>{perfReport.webVitals.LCP ? `${perfReport.webVitals.LCP} ms` : 'Medida en progreso'}</strong>
              </div>
            </div>
          </div>

          <div className="glass-panel" style={{ padding: '1.5rem' }}>
            <h4 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1rem', color: 'var(--uca-navy)' }}>
              Métricas de Memoria JS Heap
            </h4>
            {perfReport.memory.isSupported ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-main)', borderRadius: 'var(--radius-sm)' }}>
                  <span>Uso Actual Heap:</span>
                  <strong>{perfReport.memory.usedJSHeapMB} MB</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-main)', borderRadius: 'var(--radius-sm)' }}>
                  <span>Límite Máximo Heap:</span>
                  <strong>{perfReport.memory.jsHeapSizeLimitMB} MB</strong>
                </div>
              </div>
            ) : (
              <div style={{ fontSize: '0.88rem', color: 'var(--text-muted)' }}>
                Métricas de Heap no soportadas por la Performance API de este navegador.
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

          {/* DATOS DE CHECKPOINT.JSON Y REGISTRO DE ERRORES (FASE 1) */}
          <div className="glass-panel" style={{ padding: '1.75rem', borderLeft: '4px solid var(--uca-navy)' }}>
            <h4 style={{ fontSize: '1.25rem', fontWeight: 800, marginBottom: '1.25rem', color: 'var(--uca-navy)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <FileText size={22} color="var(--uca-navy)" /> Diagnóstico y Métricas de Checkpoint de la Fase 1 (checkpoint.json)
            </h4>

            {/* KPI Cards de Checkpoint */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1.75rem' }}>
              <div style={{ background: 'var(--bg-main)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>Univs Procesadas (Checkpoint)</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--uca-blue)' }}>
                  {checkpointData?.total_universidades_procesadas || 0} / 109
                </div>
              </div>

              <div style={{ background: 'var(--bg-main)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>Titulaciones Registradas</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--uca-navy)' }}>
                  {checkpointData?.total_titulaciones_procesadas || 0}
                </div>
              </div>

              <div style={{ background: 'var(--bg-main)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>PDFs Descartados (No Plan)</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--uca-sun)' }}>
                  {checkpointData?.total_pdfs_descartados_no_plan || 0}
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-light)' }}>Omitidos en descargas</div>
              </div>

              <div style={{ background: 'var(--bg-main)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>Fallos Descarga (Timeout/Refused)</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#EF4444' }}>
                  {checkpointData?.total_fallos_descarga_pdf || 0}
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-light)' }}>Registrados atómicamente</div>
              </div>
            </div>

            {/* TABLA DE ERRORES SCRAPING (errores_crawler.json) */}
            <div style={{ marginBottom: '1.75rem' }}>
              <h5 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '0.75rem', color: '#EF4444', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <AlertTriangle size={18} /> Registro de Incidencias de Scraping (errores_crawler.json)
              </h5>
              {errorsLogData.length === 0 ? (
                <div style={{ fontSize: '0.88rem', color: 'var(--text-muted)', padding: '0.75rem', background: 'var(--bg-main)', borderRadius: 'var(--radius-sm)' }}>
                  No hay incidencias de scraping registradas. El sistema opera limpiamente.
                </div>
              ) : (
                <div style={{ overflowX: 'auto', maxHeight: '220px', overflowY: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                    <thead>
                      <tr style={{ borderBottom: '2px solid var(--border-light)', textAlign: 'left', background: 'var(--bg-main)' }}>
                        <th style={{ padding: '0.5rem' }}>Fecha/Hora</th>
                        <th style={{ padding: '0.5rem' }}>Fase</th>
                        <th style={{ padding: '0.5rem' }}>Entidad ID</th>
                        <th style={{ padding: '0.5rem' }}>Motivo Fallo</th>
                        <th style={{ padding: '0.5rem' }}>Detalle Excepción</th>
                      </tr>
                    </thead>
                    <tbody>
                      {errorsLogData.map((errItem, idx) => (
                        <tr key={idx} style={{ borderBottom: '1px solid var(--border-light)' }}>
                          <td style={{ padding: '0.5rem', fontWeight: 600 }}>{errItem.timestamp || 'N/A'}</td>
                          <td style={{ padding: '0.5rem' }}><span className="badge badge-privada">{errItem.fase}</span></td>
                          <td style={{ padding: '0.5rem', fontWeight: 700 }}>{errItem.id_entidad}</td>
                          <td style={{ padding: '0.5rem', color: '#EF4444', fontWeight: 600 }}>{errItem.motivo_fallo}</td>
                          <td style={{ padding: '0.5rem', fontFamily: 'monospace', fontSize: '0.78rem' }}>{errItem.detalles_excepcion}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* TABLA DE FALLOS DE DESCARGA DE PDFS */}
            {checkpointData?.failed_pdf_downloads && Object.keys(checkpointData.failed_pdf_downloads).length > 0 && (
              <div>
                <h5 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '0.75rem', color: 'var(--uca-sun)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <WifiOff size={18} /> Registro Meticuloso de PDFs con Fallos de Conexión
                </h5>
                <div style={{ overflowX: 'auto', maxHeight: '180px', overflowY: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                    <thead>
                      <tr style={{ borderBottom: '2px solid var(--border-light)', textAlign: 'left', background: 'var(--bg-main)' }}>
                        <th style={{ padding: '0.5rem' }}>URL del PDF Candidate</th>
                        <th style={{ padding: '0.5rem' }}>Titulación</th>
                        <th style={{ padding: '0.5rem' }}>Motivo del Fallo</th>
                        <th style={{ padding: '0.5rem' }}>Fecha/Hora</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(checkpointData.failed_pdf_downloads).map(([pdfUrl, item], idx) => (
                        <tr key={idx} style={{ borderBottom: '1px solid var(--border-light)' }}>
                          <td style={{ padding: '0.5rem', fontFamily: 'monospace', fontSize: '0.78rem' }}>{pdfUrl}</td>
                          <td style={{ padding: '0.5rem', fontWeight: 700 }}>{item.codigo_estudio}</td>
                          <td style={{ padding: '0.5rem', color: '#EF4444' }}>{item.motivo_fallo}</td>
                          <td style={{ padding: '0.5rem' }}>{item.timestamp}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* NUEVA TAB 5: DOCUMENTACIÓN Y CAPACIDADES DE LA API REST */}
      {activeSubTab === 'api_docs' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          
          {/* BANNER DE ACCESO DIRECTO A SWAGGER Y REDOC */}
          <div className="glass-panel" style={{
            background: 'linear-gradient(135deg, var(--uca-navy) 0%, var(--uca-blue) 100%)',
            color: '#FFFFFF',
            padding: '1.75rem',
            borderRadius: 'var(--radius-lg)',
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '1rem'
          }}>
            <div>
              <span className="badge" style={{ background: 'rgba(255, 255, 255, 0.2)', color: '#FFFFFF', marginBottom: '0.5rem' }}>
                OPENAPI 3.0 & FASTAPI
              </span>
              <h3 style={{ fontSize: '1.5rem', fontWeight: 800 }}>Documentación e Interfaz Interactiva de la API REST</h3>
              <p style={{ fontSize: '0.9rem', opacity: 0.9, marginTop: '0.25rem' }}>
                Acceso directo a la documentación oficial Swagger UI y ReDoc para probar peticiones y auditar esquemas JSON.
              </p>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
              <a
                href={apiDocsInfoData?.swagger_ui_url || 'http://localhost:8000/docs'}
                target="_blank"
                rel="noreferrer"
                className="btn btn-gold"
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
              >
                <ExternalLink size={16} /> Abrir Swagger UI (/docs)
              </a>
              <a
                href={apiDocsInfoData?.redoc_ui_url || 'http://localhost:8000/redoc'}
                target="_blank"
                rel="noreferrer"
                className="btn btn-outline"
                style={{ color: '#FFFFFF', borderColor: 'rgba(255, 255, 255, 0.4)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}
              >
                <FileText size={16} /> Abrir ReDoc UI (/redoc)
              </a>
            </div>
          </div>

          {/* DIRECTORIO INTERACTIVO DE ENDPOINTS DE LA API */}
          <div className="glass-panel" style={{ padding: '1.75rem' }}>
            <h4 style={{ fontSize: '1.25rem', fontWeight: 800, marginBottom: '1.25rem', color: 'var(--uca-navy)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Terminal size={22} color="var(--uca-gold)" /> Directorio de Endpoints y Capacidades del Sistema (15 Endpoints)
            </h4>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.25rem' }}>
              {(apiDocsInfoData?.endpoints_disponibles || [
                { metodo: "GET", path: "/api/v1/universidades", descripcion: "Listado con ordenación prioritaria (Públicas primero) y filtros." },
                { metodo: "GET", path: "/api/v1/universidades/{codigo}", descripcion: "Ficha detallada de universidad por su código RUCT." },
                { metodo: "GET", path: "/api/v1/universidades/{codigo}/titulaciones", descripcion: "Titulaciones oficiales vigentes asociadas." },
                { metodo: "POST", path: "/api/v1/universidades", descripcion: "[CRUD Admin] Crea un nuevo centro en PostgreSQL." },
                { metodo: "PUT", path: "/api/v1/universidades/{codigo}", descripcion: "[CRUD Admin] Actualiza los datos de una universidad." },
                { metodo: "DELETE", path: "/api/v1/universidades/{codigo}", descripcion: "[CRUD Admin] Elimina universidad en cascada." },
                { metodo: "GET", path: "/api/v1/titulaciones", descripcion: "Listado de titulaciones clasificadas por nivel académico." },
                { metodo: "GET", path: "/api/v1/titulaciones/{codigo_estudio}/plan-estudios", descripcion: "Estructura curricular ECTS y BOE." },
                { metodo: "POST", path: "/api/v1/titulaciones", descripcion: "[CRUD Admin] Registra nueva titulación." },
                { metodo: "PUT", path: "/api/v1/titulaciones/{codigo_estudio}", descripcion: "[CRUD Admin] Modifica datos de titulación." },
                { metodo: "DELETE", path: "/api/v1/titulaciones/{codigo_estudio}", descripcion: "[CRUD Admin] Elimina titulación." },
                { metodo: "GET", path: "/api/v1/estadisticas/contenedores", descripcion: "Analizador en vivo del consumo Docker." },
                { metodo: "GET", path: "/api/v1/crawler/checkpoint", descripcion: "Muestra avance, PDFs descartados y fallos." },
                { metodo: "GET", path: "/api/v1/crawler/errores_json", descripcion: "Acceso al registro completo errores_crawler.json." },
                { metodo: "POST", path: "/api/v1/etl/sync", descripcion: "Desencadena sincronización ETL atómica." }
              ]).map((ep, idx) => (
                <div key={idx} style={{
                  background: 'var(--bg-main)',
                  padding: '1.15rem',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-light)'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.6rem' }}>
                    <span className="badge" style={{
                      background: ep.metodo === 'GET' ? 'rgba(16, 185, 129, 0.2)' : ep.metodo === 'POST' ? 'rgba(59, 130, 246, 0.2)' : ep.metodo === 'PUT' ? 'rgba(243, 167, 18, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                      color: ep.metodo === 'GET' ? '#10B981' : ep.metodo === 'POST' ? '#3B82F6' : ep.metodo === 'PUT' ? 'var(--uca-sun)' : '#EF4444',
                      fontWeight: 800,
                      fontSize: '0.8rem'
                    }}>
                      {ep.metodo}
                    </span>
                    <span style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.88rem', color: 'var(--uca-navy)' }}>
                      {ep.path}
                    </span>
                  </div>

                  <p style={{ fontSize: '0.84rem', color: 'var(--text-main)', margin: 0, lineHeight: '1.4' }}>
                    {ep.descripcion}
                  </p>
                </div>
              ))}
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
