import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import Hero from './components/Hero';
import UnivCard from './components/UnivCard';
import DegreeCard from './components/DegreeCard';
import PlanModal from './components/PlanModal';
import Geolocation from './components/Geolocation';
import AdminLogin from './components/AdminLogin';
import AdminDashboard from './components/AdminDashboard';
import Pagination from './components/Pagination';
import Footer from './components/Footer';

import { apiService } from './services/api';
import usageTracker from './analytics/usageTracker';
import { Search, Filter, RefreshCw, BookOpen, GraduationCap, MapPin } from 'lucide-react';

const MOCK_UNIVERSITIES = [
  { codigo: "089", nombre: "CUNEF Universidad", tipo: "Privada", comunidad_autonoma: "Comunidad de Madrid", municipio: "Madrid", provincia: "Madrid", web: "www.cunef.edu", email: "info@cunef.edu" },
  { codigo: "057", nombre: "IE Universidad", tipo: "Privada", comunidad_autonoma: "Comunidad de Castilla y León", municipio: "Segovia", provincia: "Segovia", web: "www.ie.edu/universidad", email: "universidad@ie.edu" },
  { codigo: "015", nombre: "Universidad Complutense de Madrid", tipo: "Pública", comunidad_autonoma: "Comunidad de Madrid", municipio: "Madrid", provincia: "Madrid", web: "www.ucm.es", email: "infocom@ucm.es" },
  { codigo: "005", nombre: "Universidad de Sevilla", tipo: "Pública", comunidad_autonoma: "Comunidad de Andalucía", municipio: "Sevilla", provincia: "Sevilla", web: "www.us.es", email: "info@us.es" },
  { codigo: "023", nombre: "Universidad de Cádiz (UCA)", tipo: "Pública", comunidad_autonoma: "Comunidad de Andalucía", municipio: "Cádiz", provincia: "Cádiz", web: "www.uca.es", email: "atencion.usuario@uca.es" },
  { codigo: "003", nombre: "Universidad Autónoma de Madrid", tipo: "Pública", comunidad_autonoma: "Comunidad de Madrid", municipio: "Madrid", provincia: "Madrid", web: "www.uam.es", email: "informacion@uam.es" }
];

const MOCK_DEGREES = [
  { codigo_estudio: "2504059", titulo: "Graduado o Graduada en Administración y Dirección de Empresas por la CUNEF Universidad", nivel_academico: "Grado - RD 822/2021 (2)", estado: "Publicado en B.O.E.", universidad_codigo: "089", universidad_nombre: "CUNEF Universidad", boe_url: "http://www.boe.es/boe/dias/2025/01/16/pdfs/BOE-A-2025-708.pdf", boe_fecha: "2025-01-16" },
  { codigo_estudio: "2504639", titulo: "Graduado o Graduada en Ciencia de Datos / Bachelor in Data Science por la CUNEF Universidad", nivel_academico: "Grado - RD 822/2021 (2)", estado: "Publicado en B.O.E.", universidad_codigo: "089", universidad_nombre: "CUNEF Universidad", boe_url: "http://www.boe.es/boe/dias/2024/06/10/pdfs/BOE-A-2024-11800.pdf", boe_fecha: "2024-06-10" },
  { codigo_estudio: "2504126", titulo: "Graduado o Graduada en Derecho por la CUNEF Universidad", nivel_academico: "Grado - RD 1393/2007 (1)", estado: "Publicado en B.O.E.", universidad_codigo: "089", universidad_nombre: "CUNEF Universidad" },
  { codigo_estudio: "2500021", titulo: "Graduado o Graduada en Ingeniería Informática por la Universidad de Cádiz", nivel_academico: "Grado - RD 1393/2007 (1)", estado: "Publicado en B.O.E.", universidad_codigo: "023", universidad_nombre: "Universidad de Cádiz (UCA)" },
  { codigo_estudio: "4317230", titulo: "Máster Universitario en Ciencia de Datos e Inteligencia Artificial por la CUNEF Universidad", nivel_academico: "Máster - RD 822/2021 (3)", estado: "Publicado en B.O.E.", universidad_codigo: "089", universidad_nombre: "CUNEF Universidad" }
];

export default function App() {
  const [activeTab, setActiveTab] = useState('inicio');
  const [isDark, setIsDark] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [selectedDegree, setSelectedDegree] = useState(null);

  // Check URL route for manual /admin access
  useEffect(() => {
    const path = window.location.pathname;
    if (path === '/admin' || path === '/admin/' || path === '/admin/login') {
      setActiveTab('admin-login');
    }
  }, []);

  // Data states
  const [universities, setUniversities] = useState(MOCK_UNIVERSITIES);
  const [degrees, setDegrees] = useState(MOCK_DEGREES);
  const [loading, setLoading] = useState(false);

  // Search & Filter states
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTipo, setSelectedTipo] = useState('todos');
  const [selectedCCAA, setSelectedCCAA] = useState('todas');

  // Pagination states
  const [univCurrentPage, setUnivCurrentPage] = useState(1);
  const [univItemsPerPage, setUnivItemsPerPage] = useState(20);

  const [degreeCurrentPage, setDegreeCurrentPage] = useState(1);
  const [degreeItemsPerPage, setDegreeItemsPerPage] = useState(20);

  // Track initial page view & load data
  useEffect(() => {
    usageTracker.trackPageView('home');
    loadInitialData();
  }, []);

  // Reset pagination on filter change
  useEffect(() => {
    setUnivCurrentPage(1);
    setDegreeCurrentPage(1);
  }, [searchQuery, selectedTipo, selectedCCAA]);

  // Theme toggle
  const toggleTheme = () => {
    setIsDark(!isDark);
    document.documentElement.setAttribute('data-theme', !isDark ? 'dark' : 'light');
  };

  const loadInitialData = async () => {
    setLoading(true);
    try {
      const univData = await apiService.getUniversities();
      if (univData && univData.length > 0) {
        setUniversities(univData);
      }
      const degData = await apiService.getDegrees();
      if (degData && degData.length > 0) {
        setDegrees(degData);
      }
    } catch (e) {
      console.warn('API REST loading fallback active. Showing offline sample dataset.');
    } finally {
      setLoading(false);
    }
  };

  const handleHeroSearch = (query) => {
    setSearchQuery(query);
  };

  // Filtered universities
  const filteredUniversities = universities.filter(u => {
    const matchesQuery = !searchQuery || `${u.nombre} ${u.municipio} ${u.provincia}`.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesTipo = selectedTipo === 'todos' || (u.tipo || '').toLowerCase().includes(selectedTipo);
    const matchesCCAA = selectedCCAA === 'todas' || (u.comunidad_autonoma || '').toLowerCase().includes(selectedCCAA.toLowerCase());
    return matchesQuery && matchesTipo && matchesCCAA;
  });

  // Filtered degrees
  const filteredDegrees = degrees.filter(d => {
    const matchesQuery = !searchQuery || `${d.titulo} ${d.codigo_estudio}`.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesTipo = selectedTipo === 'todos' || (
      selectedTipo === 'grado' ? (d.nivel_academico || '').toLowerCase().includes('grado') :
      selectedTipo === 'master' ? ((d.nivel_academico || '').toLowerCase().includes('máster') || (d.nivel_academico || '').toLowerCase().includes('master')) :
      true
    );
    return matchesQuery && matchesTipo;
  });

  // Paginated Slices
  const paginatedUniversities = filteredUniversities.slice(
    (univCurrentPage - 1) * univItemsPerPage,
    univCurrentPage * univItemsPerPage
  );

  const paginatedDegrees = filteredDegrees.slice(
    (degreeCurrentPage - 1) * degreeItemsPerPage,
    degreeCurrentPage * degreeItemsPerPage
  );

  const handleViewUniversityDegrees = (univ) => {
    setSearchQuery(univ.nombre);
    setActiveTab('titulaciones');
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top Navbar */}
      <Navbar 
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        isDark={isDark}
        toggleTheme={toggleTheme}
      />

      {/* Main Content Areas */}
      <main style={{ flex: 1 }}>
        {activeTab === 'inicio' && (
          <>
            <Hero 
              onSearch={handleHeroSearch}
              setActiveTab={setActiveTab}
              totalUnivs={universities.length}
              totalDegrees={degrees.length}
            />

            {/* Featured Universities Preview */}
            <section className="container" style={{ padding: '3.5rem 1.5rem 1.5rem 1.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.75rem' }}>
                <div>
                  <h2 style={{ fontSize: '1.6rem', fontWeight: 800 }}>Universidades Destacadas</h2>
                  <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>Las 6 universidades más visitadas en la plataforma</p>
                </div>
                <button 
                  className="btn btn-outline" 
                  onClick={() => setActiveTab('universidades')}
                >
                  Ver Todas ({universities.length})
                </button>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1.5rem' }}>
                {universities.slice(0, 6).map((univ) => (
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
                Información de contacto, sitio web oficial y titulaciones asociadas.
              </p>
            </div>

            {/* Filter Bar */}
            <div className="glass-panel" style={{ padding: '1.25rem', marginBottom: '2rem', display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center' }}>
              <div style={{ flex: 1, minWidth: '240px', position: 'relative', display: 'flex', alignItems: 'center' }}>
                <Search size={18} color="var(--text-light)" style={{ position: 'absolute', left: '12px' }} />
                <input 
                  type="text"
                  placeholder="Filtrar por nombre o provincia..."
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

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Filter size={16} color="var(--uca-cyan)" />
                <select 
                  value={selectedTipo}
                  onChange={(e) => setSelectedTipo(e.target.value)}
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
                Buscador de Titulaciones Oficiales Vigentes ({filteredDegrees.length})
              </h2>
              <p style={{ fontSize: '0.92rem', color: 'var(--text-muted)' }}>
                Selecciona cualquier titulación para abrir su plan de estudios extraído del BOE más reciente.
              </p>
            </div>

            {/* Filter Bar */}
            <div className="glass-panel" style={{ padding: '1.25rem', marginBottom: '2rem', display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center' }}>
              <div style={{ flex: 1, minWidth: '240px', position: 'relative', display: 'flex', alignItems: 'center' }}>
                <Search size={18} color="var(--text-light)" style={{ position: 'absolute', left: '12px' }} />
                <input 
                  type="text"
                  placeholder="Buscar por grado o máster (ej. Ciencia de Datos, Derecho...)"
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

              <select 
                value={selectedTipo}
                onChange={(e) => setSelectedTipo(e.target.value)}
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
              </select>
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
              totalItems={filteredDegrees.length}
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

        {activeTab === 'admin-login' && !isAdmin && (
          <AdminLogin 
            onLoginSuccess={() => {
              setIsAdmin(true);
              setActiveTab('admin');
            }}
          />
        )}

        {activeTab === 'admin' && isAdmin && (
          <AdminDashboard 
            onLogout={() => {
              setIsAdmin(false);
              setActiveTab('inicio');
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
      <Footer onNavigate={(tab) => setActiveTab(tab)} />
    </div>
  );
}
