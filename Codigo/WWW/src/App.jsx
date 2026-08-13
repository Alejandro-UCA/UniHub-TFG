import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import Hero from './components/Hero';
import UnivCard from './components/UnivCard';
import DegreeCard from './components/DegreeCard';
import PlanModal from './components/PlanModal';
import Geolocation from './components/Geolocation';
import AdminLogin from './components/AdminLogin';
import AdminDashboard from './components/AdminDashboard';
import AboutUs from './components/AboutUs';
import TuitionCalculator from './components/TuitionCalculator';
import Pagination from './components/Pagination';
import Footer from './components/Footer';

import { apiService } from './services/api';
import usageTracker from './analytics/usageTracker';
import { Search, Filter } from 'lucide-react';

const MOCK_UNIVERSITIES = [
  { codigo: "015", nombre: "Universidad Complutense de Madrid", tipo: "Pública", comunidad_autonoma: "Comunidad de Madrid", municipio: "Madrid", provincia: "Madrid", web: "www.ucm.es", email: "infocom@ucm.es" },
  { codigo: "005", nombre: "Universidad de Sevilla", tipo: "Pública", comunidad_autonoma: "Comunidad de Andalucía", municipio: "Sevilla", provincia: "Sevilla", web: "www.us.es", email: "info@us.es" },
  { codigo: "023", nombre: "Universidad de Cádiz (UCA)", tipo: "Pública", comunidad_autonoma: "Comunidad de Andalucía", municipio: "Cádiz", provincia: "Cádiz", web: "www.uca.es", email: "atencion.usuario@uca.es" },
  { codigo: "003", nombre: "Universidad Autónoma de Madrid", tipo: "Pública", comunidad_autonoma: "Comunidad de Madrid", municipio: "Madrid", provincia: "Madrid", web: "www.uam.es", email: "informacion@uam.es" },
  { codigo: "089", nombre: "CUNEF Universidad", tipo: "Privada", comunidad_autonoma: "Comunidad de Madrid", municipio: "Madrid", provincia: "Madrid", web: "www.cunef.edu", email: "info@cunef.edu" },
  { codigo: "057", nombre: "IE Universidad", tipo: "Privada", comunidad_autonoma: "Comunidad de Castilla y León", municipio: "Segovia", provincia: "Segovia", web: "www.ie.edu/universidad", email: "universidad@ie.edu" }
];

const MOCK_DEGREES = [
  { codigo_estudio: "2500021", titulo: "Graduado o Graduada en Ingeniería Informática por la Universidad de Cádiz", nivel_academico: "Grado - RD 1393/2007 (1)", estado: "Publicado en B.O.E.", universidad_codigo: "023", universidad_nombre: "Universidad de Cádiz", boe_url: "http://www.boe.es" },
  { codigo_estudio: "5601512", titulo: "Programa de Doctorado en Didáctica de las Ciencias Experimentales por la Universidad de Cádiz", nivel_academico: "Doctor - RD 99/2011 (0)", estado: "Publicado en B.O.E.", universidad_codigo: "023", universidad_nombre: "Universidad de Cádiz", boe_url: "http://www.boe.es" },
  { codigo_estudio: "2504059", titulo: "Graduado o Graduada en Administración y Dirección de Empresas por la CUNEF Universidad", nivel_academico: "Grado - RD 822/2021 (2)", estado: "Publicado en B.O.E.", universidad_codigo: "089", universidad_nombre: "CUNEF Universidad", boe_url: "http://www.boe.es/boe/dias/2025/01/16/pdfs/BOE-A-2025-708.pdf", boe_fecha: "2025-01-16" },
  { codigo_estudio: "2504639", titulo: "Graduado o Graduada en Ciencia de Datos / Bachelor in Data Science por la CUNEF Universidad", nivel_academico: "Grado - RD 822/2021 (2)", estado: "Publicado en B.O.E.", universidad_codigo: "089", universidad_nombre: "CUNEF Universidad", boe_url: "http://www.boe.es/boe/dias/2024/06/10/pdfs/BOE-A-2024-11800.pdf", boe_fecha: "2024-06-10" },
  { codigo_estudio: "4317230", titulo: "Máster Universitario en Ciencia de Datos e Inteligencia Artificial por la CUNEF Universidad", nivel_academico: "Máster - RD 822/2021 (3)", estado: "Publicado en B.O.E.", universidad_codigo: "089", universidad_nombre: "CUNEF Universidad" }
];

export default function App() {
  const [activeTab, setActiveTab] = useState('inicio');
  const [isDark, setIsDark] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [selectedDegree, setSelectedDegree] = useState(null);

  const navigateToTab = (tab) => {
    setActiveTab(tab);
    window.history.pushState({ tab }, '', `/${tab === 'inicio' ? '' : tab}`);
  };

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
      setActiveTab('admin-login');
    }
  }, []);

  // Estados de datos
  const [universities, setUniversities] = useState(MOCK_UNIVERSITIES);
  const [degrees, setDegrees] = useState(MOCK_DEGREES);
  const [loading, setLoading] = useState(false);

  // Estados de búsqueda y filtros
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedUnivTipo, setSelectedUnivTipo] = useState('todos');
  const [selectedDegreeTipo, setSelectedDegreeTipo] = useState('todos');
  const [selectedCCAA, setSelectedCCAA] = useState('todas');
  const [selectedUnivCodigo, setSelectedUnivCodigo] = useState('');

  // Estados de paginación
  // Estados de paginación y totales
  const [univCurrentPage, setUnivCurrentPage] = useState(1);
  const [univItemsPerPage, setUnivItemsPerPage] = useState(20);

  const [degreeCurrentPage, setDegreeCurrentPage] = useState(1);
  const [degreeItemsPerPage, setDegreeItemsPerPage] = useState(20);
  const [degreeTotalItems, setDegreeTotalItems] = useState(MOCK_DEGREES.length);

  // Registrar vista inicial de página y cargar datos
  useEffect(() => {
    usageTracker.trackPageView('home');
    loadInitialData();
  }, []);

  // Reiniciar paginación al cambiar filtros
  useEffect(() => {
    setUnivCurrentPage(1);
    setDegreeCurrentPage(1);
  }, [searchQuery, selectedUnivTipo, selectedDegreeTipo, selectedCCAA, selectedUnivCodigo]);

  // Alternador de tema visual (Modo Claro / Oscuro)
  const toggleTheme = () => {
    setIsDark(!isDark);
    document.documentElement.setAttribute('data-theme', !isDark ? 'dark' : 'light');
  };

  const loadInitialData = async () => {
    setLoading(true);
    try {
      // Cargar todas las universidades a la vez (son pocas) para soportar mapas y filtros cruzados
      const univRes = await apiService.getUniversities({ limit: 500 }, { returnWithTotal: true });
      // Si la API devuelve un array (incluso si está vacío), la DB está inicializada
      if (univRes && Array.isArray(univRes.data)) {
        setUniversities(univRes.data);
      }
      
      // Nota: No llamamos a fetchDegreesPage(1) aquí.
      // Al actualizar 'universities', el useEffect de abajo se disparará automáticamente,
      // evitando una llamada duplicada a la API en el arranque.
    } catch (e) {
      console.warn('API REST loading fallback active. Showing offline sample dataset.');
    } finally {
      setLoading(false);
    }
  };

  const fetchDegreesPage = async (page, signal) => {
    setLoading(true);
    try {
      const skip = (page - 1) * degreeItemsPerPage;
      const res = await apiService.getDegrees({ 
        limit: degreeItemsPerPage, 
        skip,
        titulo: searchQuery,
        nivel_academico: selectedDegreeTipo,
        ccaa: selectedCCAA,
        tipo_universidad: selectedUnivTipo,
        universidad_codigo: selectedUnivCodigo
      }, { returnWithTotal: true, signal });
      
      if (res && res.data) {
        setDegrees(res.data);
        setDegreeTotalItems(res.totalCount || res.data.length);
      }
    } catch (e) {
      console.warn('Error fetching degrees page', e);
    } finally {
      setLoading(false);
    }
  };

  // Escuchar cambios en filtros o paginación de titulaciones para refrescar datos en vivo
  useEffect(() => {
    // Evitamos llamar a la API antes del montaje inicial completo
    if (!universities || universities.length === MOCK_UNIVERSITIES.length && universities[0]?.codigo === MOCK_UNIVERSITIES[0]?.codigo) return;

    const controller = new AbortController();
    const delayDebounceFn = setTimeout(() => {
      fetchDegreesPage(degreeCurrentPage, controller.signal);
    }, 300);

    return () => { clearTimeout(delayDebounceFn); controller.abort(); };
  }, [degreeCurrentPage, degreeItemsPerPage, searchQuery, selectedDegreeTipo, selectedCCAA, selectedUnivTipo, selectedUnivCodigo]);

  const handleHeroSearch = (query) => {
    setSearchQuery(query);
  };

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

  // Filtered & Sorted degrees (including Doctorados and CCAA filter)
  // Ya no filtramos en memoria las titulaciones, la API lo hace por nosotros
  const filteredDegrees = degrees;

  // Top 6 Most Visited Universities for Featured Section
  const topVisitedUnivs = React.useMemo(() => usageTracker.getTopVisitedUniversities(universities, 6), [universities]);

  // Paginated Slices
  const paginatedUniversities = filteredUniversities.slice(
    (univCurrentPage - 1) * univItemsPerPage,
    univCurrentPage * univItemsPerPage
  );

  // Titulaciones ya están paginadas desde el servidor
  const paginatedDegrees = degrees;

  const handleViewUniversityDegrees = (univ) => {
    setSearchQuery('');
    setSelectedUnivCodigo(univ.codigo);
    navigateToTab('titulaciones');
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top Navbar */}
      <Navbar 
        activeTab={activeTab}
        setActiveTab={navigateToTab}
        isDark={isDark}
        toggleTheme={toggleTheme}
      />

      {/* Main Content Areas */}
      <main style={{ flex: 1 }}>
        {activeTab === 'inicio' && (
          <>
            <Hero 
              onSearch={handleHeroSearch}
              setActiveTab={navigateToTab}
              totalUnivs={universities.length}
              totalDegrees={degrees.length}
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
              {paginatedUniversities.map((univ) => (
                <UnivCard 
                  key={univ.codigo}
                  univ={univ}
                  onViewDegrees={handleViewUniversityDegrees}
                />
              ))}
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
                Buscador de Titulaciones Oficiales Vigentes ({degreeTotalItems})
              </h2>
              <p style={{ fontSize: '0.92rem', color: 'var(--text-muted)' }}>
                Filtra por Grado, Máster o Doctorado y selecciona cualquier titulación para abrir su plan de estudios desglosado.
              </p>
            </div>

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
              </div>
            </div>

            {/* Degrees Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1.5rem' }}>
              {paginatedDegrees.map((degree) => (
                <DegreeCard 
                  key={degree.codigo_estudio}
                  degree={degree}
                  onSelectDegree={(deg) => setSelectedDegree(deg)}
                />
              ))}
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

        {activeTab === 'admin-login' && !isAdmin && (
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
              sessionStorage.removeItem('adminApiKey');
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
      <Footer onNavigate={(tab) => navigateToTab(tab)} />
    </div>
  );
}
