import React, { useState, useEffect, useCallback, Suspense } from 'react';
import Navbar from './components/Navbar';
import Hero from './components/Hero';
import UnivCard from './components/UnivCard';
import DegreeCard from './components/DegreeCard';
import PlanModal from './components/PlanModal';
import ErrorBoundary from './components/ErrorBoundary';

import { apiService } from './services/api';
import usageTracker from './analytics/usageTracker';
import { Search, Filter, AlertCircle, RefreshCw, X } from 'lucide-react';

const Geolocation = React.lazy(() => import('./components/Geolocation'));
const AdminLogin = React.lazy(() => import('./components/AdminLogin'));
const AdminDashboard = React.lazy(() => import('./components/AdminDashboard'));
const AboutUs = React.lazy(() => import('./components/AboutUs'));
const TuitionCalculator = React.lazy(() => import('./components/TuitionCalculator'));
const Pagination = React.lazy(() => import('./components/Pagination'));
const Footer = React.lazy(() => import('./components/Footer'));

export default function App() {
  const [activeTab, setActiveTab] = useState('inicio');
  const [isDark, setIsDark] = useState(false);
  const [isAdmin, setIsAdmin] = useState(() => apiService.hasAdminSession());
  const [selectedDegree, setSelectedDegree] = useState(null);
  const [initialDataLoaded, setInitialDataLoaded] = useState(false);

  const navigateToTab = useCallback((tab) => {
    setActiveTab(tab);
    window.history.pushState({ tab }, '', `/${tab === 'inicio' ? '' : tab}`);
  }, []);

  useEffect(() => {
    const handlePopState = (event) => {
      if (event.state && event.state.tab) {
        setActiveTab(event.state.tab);
      } else {
        setActiveTab('inicio');
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Comprobar ruta de la URL para acceso manual a la vista de administración (/admin)
  useEffect(() => {
    const path = window.location.pathname;
    if (path === '/admin' || path === '/admin/' || path === '/admin/login') {
      if (apiService.hasAdminSession()) {
        setIsAdmin(true);
        setActiveTab('admin');
      } else {
        setActiveTab('admin-login');
      }
    }
  }, []);

  // Estados de datos
  const [universities, setUniversities] = useState([]);
  const [degrees, setDegrees] = useState([]);
  const [loading, setLoading] = useState(false);
  const [apiError, setApiError] = useState(null);
  const [degreeError, setDegreeError] = useState(null);

  // Estados de búsqueda y filtros
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedUnivTipo, setSelectedUnivTipo] = useState('todos');
  const [selectedDegreeTipo, setSelectedDegreeTipo] = useState('todos');
  const [selectedCCAA, setSelectedCCAA] = useState('todas');
  const [selectedRama, setSelectedRama] = useState('todas');
  const [selectedUnivCodigo, setSelectedUnivCodigo] = useState('');

  // Estados de paginación y totales
  const [univCurrentPage, setUnivCurrentPage] = useState(1);
  const [univItemsPerPage, setUnivItemsPerPage] = useState(20);

  const [degreeCurrentPage, setDegreeCurrentPage] = useState(1);
  const [degreeItemsPerPage, setDegreeItemsPerPage] = useState(20);
  const [degreeTotalItems, setDegreeTotalItems] = useState(0);
  const [degreeReloadToken, setDegreeReloadToken] = useState(0);

  const loadInitialData = useCallback(async () => {
    setLoading(true);
    setApiError(null);
    try {
      const univRes = await apiService.getAllUniversities();
      
      setUniversities(univRes || []);
    } catch (err) {
      setApiError('Error al cargar los datos iniciales desde el servidor API.');
      console.warn('API REST loading failed.', err);
    } finally {
      setLoading(false);
      setInitialDataLoaded(true);
      setDegreeReloadToken(token => token + 1);
    }
  }, []);

  // Registrar la visita una única vez; cambios de paginación no son visitas.
  useEffect(() => {
    usageTracker.trackPageView('home');
  }, []);

  // La carga de universidades no depende de la paginación de titulaciones.
  useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);

  // Reiniciar paginación al cambiar filtros
  useEffect(() => {
    setUnivCurrentPage(1);
    setDegreeCurrentPage(1);
  }, [searchQuery, selectedUnivTipo, selectedDegreeTipo, selectedCCAA, selectedRama, selectedUnivCodigo]);

  // Alternador de tema visual (Modo Claro / Oscuro)
  const toggleTheme = () => {
    setIsDark(!isDark);
    document.documentElement.setAttribute('data-theme', !isDark ? 'dark' : 'light');
  };

  const handleNavClickTab = useCallback((tab) => {
    if (tab === 'titulaciones' && activeTab !== 'titulaciones') {
      setSelectedUnivCodigo('');
    }
    navigateToTab(tab);
  }, [activeTab, navigateToTab]);

  const fetchDegreesPage = useCallback(async (page, signal) => {
    setLoading(true);
    setDegreeError(null);
    try {
      const skip = (page - 1) * degreeItemsPerPage;
      const res = await apiService.getDegrees({ 
        limit: degreeItemsPerPage, 
        skip,
        titulo: searchQuery,
        nivel_academico: selectedDegreeTipo,
        ccaa: selectedCCAA,
        tipo_universidad: selectedUnivTipo,
        rama: selectedRama,
        universidad_codigo: selectedUnivCodigo
      }, { returnWithTotal: true, signal });
      
      if (res && res.data) {
        setDegrees(res.data);
        setDegreeTotalItems(res.totalCount || res.data.length);
      } else {
        setDegrees([]);
        setDegreeTotalItems(0);
      }
    } catch (e) {
      if (e?.name !== 'AbortError') {
        console.warn('Error fetching degrees page', e);
        setDegrees([]);
        setDegreeTotalItems(0);
        setDegreeError('No se pudieron cargar las titulaciones. Comprueba la conexión con la API y vuelve a intentarlo.');
      }
    } finally {
      setLoading(false);
    }
  }, [degreeItemsPerPage, searchQuery, selectedDegreeTipo, selectedCCAA, selectedUnivTipo, selectedRama, selectedUnivCodigo]);

  // Escuchar cambios en filtros o paginación de titulaciones para refrescar datos en vivo
  useEffect(() => {
    if (!initialDataLoaded) return;

    const controller = new AbortController();
    const delayDebounceFn = setTimeout(() => {
      fetchDegreesPage(degreeCurrentPage, controller.signal);
    }, 300);

    return () => { clearTimeout(delayDebounceFn); controller.abort(); };
  }, [initialDataLoaded, degreeCurrentPage, fetchDegreesPage, degreeReloadToken]);

  const handleHeroSearch = useCallback((query) => {
    setSelectedUnivCodigo('');
    setSearchQuery(query);
    navigateToTab('titulaciones');
  }, [navigateToTab]);

  // Generate unique list of CCAA for filter dropdowns
  const uniqueCCAAs = React.useMemo(() => {
    const list = [...new Set(universities.map(u => u.comunidad_autonoma).filter(Boolean))];
    return list.sort((a, b) => a.localeCompare(b));
  }, [universities]);

  // Filtered & Sorted universities (Publics first, then Privates)
  const filteredUniversities = React.useMemo(() => {
    return universities.filter(u => {
      const matchesQuery = !searchQuery || `${u.nombre} ${u.municipio} ${u.provincia}`.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesTipo = selectedUnivTipo === 'todos' || (u.tipo || '').toLowerCase().includes(selectedUnivTipo);
      const matchesCCAA = selectedCCAA === 'todas' || (u.comunidad_autonoma || '').toLowerCase().includes(selectedCCAA.toLowerCase());
      return matchesQuery && matchesTipo && matchesCCAA;
    }).sort((a, b) => {
      const isAPublic = (a.tipo || '').toLowerCase().includes('públic') || (a.tipo || '').toLowerCase().includes('public');
      const isBPublic = (b.tipo || '').toLowerCase().includes('públic') || (b.tipo || '').toLowerCase().includes('public');
      if (isAPublic && !isBPublic) return -1;
      if (!isAPublic && isBPublic) return 1;
      return (a.nombre || '').localeCompare(b.nombre || '');
    });
  }, [universities, searchQuery, selectedUnivTipo, selectedCCAA]);

  // Map of universities by code for fast CCAA lookup
  const univCodeMap = React.useMemo(() => {
    const map = {};
    universities.forEach(u => {
      if (u.codigo) map[u.codigo] = u;
    });
    return map;
  }, [universities]);

  // Top 6 Most Visited Universities for Featured Section
  const topVisitedUnivs = React.useMemo(() => usageTracker.getTopVisitedUniversities(universities, 6), [universities]);

  // Paginated Slices
  const paginatedUniversities = filteredUniversities.slice(
    (univCurrentPage - 1) * univItemsPerPage,
    univCurrentPage * univItemsPerPage
  );

  // Titulaciones ya están paginadas desde el servidor
  const paginatedDegrees = degrees;
  const incompleteDegreesOnPage = React.useMemo(
    () => degrees.filter((degree) => degree.plan_incompleto || (degree.estado_calidad_plan && !degree.tiene_plan_verificado)).length,
    [degrees]
  );

  const handleViewUniversityDegrees = useCallback((univ) => {
    setSearchQuery('');
    setSelectedUnivCodigo(univ.codigo);
    navigateToTab('titulaciones');
  }, [navigateToTab]);

  return (
    <ErrorBoundary>
      <Suspense fallback={<div style={{ padding: '2rem', textAlign: 'center' }}>Cargando...</div>}>
        <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
          {/* Top Navbar */}
          <Navbar 
            activeTab={activeTab}
            setActiveTab={handleNavClickTab}
            isDark={isDark}
            toggleTheme={toggleTheme}
          />

          {/* Offline/API Fallback Alert Banner */}
          {apiError && (
            <div 
              role="alert"
              style={{
                background: 'rgba(243, 167, 18, 0.12)',
                borderBottom: '1px solid rgba(243, 167, 18, 0.35)',
                padding: '0.75rem 1.5rem',
                color: 'var(--text-main)',
                fontSize: '0.88rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '0.75rem'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <AlertCircle size={18} color="var(--uca-gold)" />
                <span>{apiError}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <button
                  type="button"
                  onClick={loadInitialData}
                  className="btn btn-outline"
                  style={{ padding: '0.25rem 0.65rem', fontSize: '0.78rem', borderRadius: '6px' }}
                >
                  <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
                  Reintentar conexión
                </button>
                <button
                  type="button"
                  onClick={() => setApiError(null)}
                  aria-label="Cerrar aviso de desconexión"
                  style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', padding: '0.2rem' }}
                >
                  <X size={16} />
                </button>
              </div>
            </div>
          )}

          {/* Main Content Areas */}
          <main style={{ flex: 1 }}>
            {activeTab === 'inicio' && (
          <>
            <Hero 
              onSearch={handleHeroSearch}
              setActiveTab={handleNavClickTab}
              totalUnivs={universities.length}
              totalDegrees={degreeTotalItems}
            />

            {/* Featured Universities Section (Top 6 Most Visited) */}
            <section className="container" style={{ padding: '3.5rem 1.5rem 1.5rem 1.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.75rem' }}>
                <div>
                  <h2 style={{ fontSize: '1.6rem', fontWeight: 800 }}>Universidades Destacadas</h2>
                  <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>Las 6 universidades más visitadas en la plataforma</p>
                </div>
                <button 
                  className="btn btn-outline" 
                  onClick={() => navigateToTab('universidades')}
                >
                  Ver Todas ({universities.length})
                </button>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1.5rem' }}>
                {topVisitedUnivs.map((univ) => (
                  <UnivCard 
                    key={univ.codigo}
                    univ={univ}
                    onViewDegrees={handleViewUniversityDegrees}
                  />
                ))}
              </div>
            </section>
          </>
        )}

        {activeTab === 'universidades' && (
          <section className="container" style={{ padding: '2.5rem 1.5rem' }}>
            <div style={{ marginBottom: '2rem' }}>
              <h2 style={{ fontSize: '1.8rem', fontWeight: 800, marginBottom: '0.5rem' }}>
                Directorio Oficial de Universidades ({filteredUniversities.length})
              </h2>
              <p style={{ fontSize: '0.92rem', color: 'var(--text-muted)' }}>
                Ordenadas prioritariamente: primero públicas y posteriormente privadas.
              </p>
            </div>

            {/* Filter Bar */}
            <div className="glass-panel" style={{ padding: '1.25rem', marginBottom: '2rem', display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center' }}>
              <div style={{ flex: 1, minWidth: '240px', position: 'relative', display: 'flex', alignItems: 'center' }}>
                <Search size={18} color="var(--text-light)" style={{ position: 'absolute', left: '12px' }} />
                <input 
                  type="text"
                  placeholder="Filtrar por nombre o provincia..."
                  aria-label="Buscar universidades por nombre"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.65rem 0.65rem 0.65rem 2.4rem',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-light)',
                    background: 'var(--bg-card)',
                    color: 'var(--text-main)',
                    outline: 'none'
                  }}
                />
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Filter size={16} color="var(--uca-cyan)" />
                  <select 
                    aria-label="Filtrar por tipo de universidad"
                    value={selectedUnivTipo}
                    onChange={(e) => setSelectedUnivTipo(e.target.value)}
                    style={{
                      padding: '0.65rem 1rem',
                      borderRadius: 'var(--radius-sm)',
                      border: '1px solid var(--border-light)',
                      background: 'var(--bg-card)',
                      color: 'var(--text-main)',
                      outline: 'none'
                    }}
                  >
                    <option value="todos">Todos los tipos</option>
                    <option value="pública">Públicas</option>
                    <option value="privada">Privadas</option>
                  </select>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Filter size={16} color="var(--uca-cyan)" />
                  <select 
                    aria-label="Filtrar por Comunidad Autónoma"
                    value={selectedCCAA}
                    onChange={(e) => setSelectedCCAA(e.target.value)}
                    style={{
                      padding: '0.65rem 1rem',
                      borderRadius: 'var(--radius-sm)',
                      border: '1px solid var(--border-light)',
                      background: 'var(--bg-card)',
                      color: 'var(--text-main)',
                      outline: 'none'
                    }}
                  >
                    <option value="todas">Todas las Comunidades</option>
                    {uniqueCCAAs.map(ccaa => (
                      <option key={ccaa} value={ccaa}>{ccaa}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            {/* Universities Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1.5rem' }}>
              {paginatedUniversities.length === 0 ? (
                <div className="glass-panel" style={{ padding: '3.5rem 2rem', textAlign: 'center', borderRadius: '12px', gridColumn: '1 / -1' }}>
                  <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>🏛️</div>
                  <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--text-main)' }}>
                    No se encontraron universidades con los filtros seleccionados
                  </h3>
                  <p style={{ color: 'var(--text-muted)', maxWidth: '500px', margin: '0 auto 1.25rem auto', fontSize: '0.9rem', lineHeight: 1.5 }}>
                    Prueba a cambiar el tipo de centro, la Comunidad Autónoma o el término de búsqueda.
                  </p>
                  <button
                    onClick={() => {
                      setSearchQuery('');
                      setSelectedUnivTipo('todos');
                      setSelectedCCAA('todas');
                    }}
                    className="btn btn-primary"
                    style={{ padding: '0.5rem 1.25rem', fontSize: '0.85rem' }}
                  >
                    Restablecer filtros de universidad
                  </button>
                </div>
              ) : (
                paginatedUniversities.map((univ) => (
                  <UnivCard 
                    key={univ.codigo}
                    univ={univ}
                    onViewDegrees={handleViewUniversityDegrees}
                  />
                ))
              )}
            </div>

            {/* Pagination Controls */}
            <Pagination 
              currentPage={univCurrentPage}
              totalItems={filteredUniversities.length}
              itemsPerPage={univItemsPerPage}
              onPageChange={setUnivCurrentPage}
              onItemsPerPageChange={setUnivItemsPerPage}
            />
          </section>
        )}

        {activeTab === 'titulaciones' && (
          <section className="container" style={{ padding: '2.5rem 1.5rem' }}>
            <div style={{ marginBottom: '2rem' }}>
              <h2 style={{ fontSize: '1.8rem', fontWeight: 800, marginBottom: '0.5rem' }}>
                Buscador de Titulaciones Oficiales ({degreeTotalItems})
              </h2>
              <p style={{ fontSize: '0.92rem', color: 'var(--text-muted)' }}>
                Filtra por Grado, Máster o Doctorado y selecciona cualquier titulación para abrir su plan de estudios desglosado.
              </p>
            </div>

            {selectedUnivCodigo && (
              <div style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.75rem',
                background: 'rgba(0, 132, 200, 0.12)',
                border: '1px solid var(--uca-blue)',
                padding: '0.5rem 1rem',
                borderRadius: '50px',
                fontSize: '0.88rem',
                color: 'var(--uca-blue)',
                marginBottom: '1.5rem'
              }}>
                <span>🎓 Filtrando titulaciones de: <strong>{univCodeMap[selectedUnivCodigo]?.nombre || `Universidad ${selectedUnivCodigo}`}</strong></span>
                <button 
                  onClick={() => setSelectedUnivCodigo('')}
                  style={{
                    background: 'var(--uca-blue)',
                    color: '#FFFFFF',
                    border: 'none',
                    borderRadius: '12px',
                    padding: '0.2rem 0.6rem',
                    cursor: 'pointer',
                    fontSize: '0.78rem',
                    fontWeight: 700
                  }}
                  title="Mostrar titulaciones de todas las universidades"
                >
                  ✕ Quitar filtro
                </button>
              </div>
            )}

            {incompleteDegreesOnPage > 0 && (
              <div role="status" style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '0.65rem',
                padding: '0.85rem 1rem',
                marginBottom: '1.25rem',
                background: 'rgba(245, 158, 11, 0.1)',
                border: '1px solid rgba(245, 158, 11, 0.35)',
                borderRadius: 'var(--radius-md)',
                color: '#92400E',
                fontSize: '0.85rem',
                lineHeight: 1.45
              }}>
                <AlertCircle size={18} style={{ flexShrink: 0, marginTop: '1px' }} />
                <span><strong>Aviso:</strong> esta página incluye {incompleteDegreesOnPage} {incompleteDegreesOnPage === 1 ? 'titulación con datos' : 'titulaciones con datos'} incompletos o pendientes de verificación. Se muestran para consulta, pero debes contrastarlos con la fuente oficial.</span>
              </div>
            )}

            {/* Filter Bar */}
            <div className="glass-panel" style={{ padding: '1.25rem', marginBottom: '2rem', display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center' }}>
              <div style={{ flex: 1, minWidth: '240px', position: 'relative', display: 'flex', alignItems: 'center' }}>
                <Search size={18} color="var(--text-light)" style={{ position: 'absolute', left: '12px' }} />
                <input 
                  type="text"
                  placeholder="Buscar por grado, máster o doctorado (ej. Ciencia de Datos, Derecho, Didáctica...)"
                  aria-label="Buscar titulaciones por nombre"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.65rem 0.65rem 0.65rem 2.4rem',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-light)',
                    background: 'var(--bg-card)',
                    color: 'var(--text-main)',
                    outline: 'none'
                  }}
                />
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                <select 
                  aria-label="Filtrar por nivel académico"
                  value={selectedDegreeTipo}
                  onChange={(e) => setSelectedDegreeTipo(e.target.value)}
                  style={{
                    padding: '0.65rem 1rem',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-light)',
                    background: 'var(--bg-card)',
                    color: 'var(--text-main)',
                    outline: 'none'
                  }}
                >
                  <option value="todos">Todos los niveles</option>
                  <option value="grado">Grados</option>
                  <option value="master">Másteres</option>
                  <option value="doctorado">Doctorados</option>
                </select>

                <select 
                  aria-label="Filtrar por tipo de universidad"
                  value={selectedUnivTipo}
                  onChange={(e) => setSelectedUnivTipo(e.target.value)}
                  style={{
                    padding: '0.65rem 1rem',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-light)',
                    background: 'var(--bg-card)',
                    color: 'var(--text-main)',
                    outline: 'none'
                  }}
                >
                  <option value="todos">Todas las Universidades</option>
                  <option value="pública">Solo Públicas</option>
                  <option value="privada">Solo Privadas</option>
                </select>

                <select 
                  aria-label="Filtrar por Comunidad Autónoma"
                  value={selectedCCAA}
                  onChange={(e) => setSelectedCCAA(e.target.value)}
                  style={{
                    padding: '0.65rem 1rem',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-light)',
                    background: 'var(--bg-card)',
                    color: 'var(--text-main)',
                    outline: 'none'
                  }}
                >
                  <option value="todas">Todas las Comunidades</option>
                  {uniqueCCAAs.map(ccaa => (
                    <option key={ccaa} value={ccaa}>{ccaa}</option>
                  ))}
                </select>

                <select 
                  aria-label="Filtrar por Rama de Conocimiento"
                  value={selectedRama}
                  onChange={(e) => setSelectedRama(e.target.value)}
                  style={{
                    padding: '0.65rem 1rem',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-light)',
                    background: 'var(--bg-card)',
                    color: 'var(--text-main)',
                    outline: 'none'
                  }}
                >
                  <option value="todas">Todas las Ramas</option>
                  <option value="sociales">Ciencias Sociales y Jurídicas</option>
                  <option value="ingenieria">Ingeniería y Arquitectura</option>
                  <option value="salud">Ciencias de la Salud</option>
                  <option value="artes">Artes y Humanidades</option>
                  <option value="ciencias">Ciencias Experimentales</option>
                </select>
              </div>
            </div>

            {/* Degrees Grid */}
            {degreeError && (
              <div role="alert" className="glass-panel" style={{ padding: '1rem 1.25rem', marginBottom: '1.25rem', borderColor: 'rgba(239, 68, 68, 0.45)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#B91C1C' }}>
                  <AlertCircle size={18} />
                  <span>{degreeError}</span>
                </div>
                <button type="button" className="btn btn-outline" onClick={() => setDegreeReloadToken(token => token + 1)}>
                  <RefreshCw size={14} /> Reintentar
                </button>
              </div>
            )}
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', 
              gap: '1.5rem',
              opacity: loading ? 0.6 : 1,
              transition: 'opacity 0.2s ease'
            }}>
              {loading && paginatedDegrees.length === 0 ? (
                <div className="glass-panel" style={{ padding: '3.5rem 2rem', textAlign: 'center', borderRadius: '12px', gridColumn: '1 / -1' }}>
                  <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-muted)' }}>
                    Cargando titulaciones oficiales...
                  </div>
                </div>
              ) : paginatedDegrees.length === 0 ? (
                <div className="glass-panel" style={{ padding: '3.5rem 2rem', textAlign: 'center', borderRadius: '12px', gridColumn: '1 / -1' }}>
                  <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>🔍</div>
                  <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--text-main)' }}>
                    No se encontraron titulaciones oficiales con los filtros seleccionados
                  </h3>
                  <p style={{ color: 'var(--text-muted)', maxWidth: '500px', margin: '0 auto 1.25rem auto', fontSize: '0.9rem', lineHeight: 1.5 }}>
                    Prueba a modificar los términos de búsqueda, el nivel académico o restablecer los filtros.
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      setSearchQuery('');
                      setSelectedDegreeTipo('todos');
                      setSelectedUnivTipo('todos');
                      setSelectedCCAA('todas');
                      setSelectedRama('todas');
                      setSelectedUnivCodigo('');
                    }}
                    className="btn btn-primary"
                    style={{ padding: '0.5rem 1.25rem', fontSize: '0.85rem' }}
                  >
                    Restablecer todos los filtros
                  </button>
                </div>
              ) : (
                paginatedDegrees.map((degree) => (
                  <DegreeCard 
                    key={degree.codigo_estudio}
                    degree={degree}
                    onSelectDegree={(deg) => setSelectedDegree(deg)}
                  />
                ))
              )}
            </div>

            {/* Pagination Controls */}
            <Pagination 
              currentPage={degreeCurrentPage}
              totalItems={degreeTotalItems}
              itemsPerPage={degreeItemsPerPage}
              onPageChange={setDegreeCurrentPage}
              onItemsPerPageChange={setDegreeItemsPerPage}
            />
          </section>
        )}

        {activeTab === 'cercania' && (
          <Geolocation 
            universities={universities}
            onViewDegrees={handleViewUniversityDegrees}
          />
        )}

        {activeTab === 'calculadora' && (
          <TuitionCalculator />
        )}

        {activeTab === 'sobre-nosotros' && (
          <AboutUs />
        )}

        {(activeTab === 'admin-login' || (activeTab === 'admin' && !isAdmin)) && (
          <AdminLogin 
            onLoginSuccess={() => {
              setIsAdmin(true);
              navigateToTab('admin');
            }}
          />
        )}

        {activeTab === 'admin' && isAdmin && (
          <AdminDashboard 
            onLogout={() => {
              apiService.clearAdminApiKey();
              setIsAdmin(false);
              navigateToTab('inicio');
            }}
          />
        )}
      </main>

      {/* BOE Curriculum Modal */}
      {selectedDegree && (
        <PlanModal 
          degree={selectedDegree}
          onClose={() => setSelectedDegree(null)}
        />
      )}

      {/* Footer */}
      <Footer onNavigate={handleNavClickTab} />
    </div>
      </Suspense>
    </ErrorBoundary>
  );
}
