import React, { useState, useEffect } from 'react';
import { ShieldCheck, BarChart3, Activity, Server, Eye, Search, MapPin, Cpu, HardDrive, RefreshCw, LogOut } from 'lucide-react';
import usageTracker from '../analytics/usageTracker';
import perfTracker from '../analytics/perfTracker';
import { apiService } from '../services/api';

export default function AdminDashboard({ onLogout }) {
  const [activeSubTab, setActiveSubTab] = useState('uso'); // 'uso', 'rendimiento', 'sistema'
  const [usageStats, setUsageStats] = useState(usageTracker.getAnalyticsSummary());
  const [perfReport, setPerfReport] = useState(perfTracker.getPerformanceReport());
  const [crawlerStats, setCrawlerStats] = useState([]);
  const [crawlerErrors, setCrawlerErrors] = useState([]);
  const [loading, setLoading] = useState(false);

  const refreshData = async () => {
    setLoading(true);
    setUsageStats(usageTracker.getAnalyticsSummary());
    setPerfReport(perfTracker.getPerformanceReport());

    try {
      const statsData = await apiService.getCrawlerStats();
      setCrawlerStats(statsData);
      const errorsData = await apiService.getCrawlerErrors();
      setCrawlerErrors(errorsData);
    } catch (err) {
      console.warn('API stats not available in offline/local mode:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshData();
    const interval = setInterval(refreshData, 10000);
    return () => clearInterval(interval);
  }, []);

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
            <h2 style={{ fontSize: '1.6rem', fontWeight: 800 }}>Métricas de Uso, Rendimiento y Salud</h2>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <button className="btn btn-outline" onClick={refreshData} disabled={loading} style={{ color: '#FFFFFF', borderColor: 'rgba(255, 255, 255, 0.3)' }}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} />
            Actualizar
          </button>
          <button className="btn btn-gold" onClick={onLogout} style={{ padding: '0.65rem 1.15rem' }}>
            <LogOut size={16} /> Cerrar Sesión
          </button>
        </div>
      </div>

      {/* Admin Tabs */}
      <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '2rem', borderBottom: '2px solid var(--border-light)', paddingBottom: '0.5rem' }}>
        <button 
          className={`btn ${activeSubTab === 'uso' ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => setActiveSubTab('uso')}
        >
          <BarChart3 size={18} /> Estadísticas de Uso Web
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
          <Server size={18} /> Salud del Rastreador y Sistema
        </button>
      </div>

      {/* TAB 1: ESTADÍSTICAS DE USO WEB */}
      {activeSubTab === 'uso' && (
        <div>
          {/* Top Counter Cards */}
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

          {/* Tables: Top Searches & Popular Items */}
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

      {/* TAB 2: RENDIMIENTO DE LA WEB (WEB VITALS & MEMORY) */}
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

      {/* TAB 3: SALUD DEL SISTEMA Y CRAWLER (FASE 1 & 2) */}
      {activeSubTab === 'sistema' && (
        <div className="glass-panel" style={{ padding: '1.75rem' }}>
          <h4 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.25rem', color: 'var(--uca-blue)' }}>
            Estado y Registro del Crawler de la Fase 1
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
      )}
    </div>
  );
}
