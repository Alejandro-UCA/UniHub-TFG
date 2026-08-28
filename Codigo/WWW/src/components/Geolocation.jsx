import React, { useState, useEffect } from 'react';
import { MapPin, Navigation, Compass } from 'lucide-react';
import { calculateHaversineDistance, SPANISH_CITIES_COORDS, getUniversityCoords } from '../utils/distance';
import usageTracker from '../analytics/usageTracker';
import UnivCard from './UnivCard';
import Pagination from './Pagination';

export default function Geolocation({ universities, onViewDegrees }) {
  const [userLocation, setUserLocation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedCity, setSelectedCity] = useState('cadiz'); // Por defecto Cádiz (UCA)

  // Estados de paginación
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(20);

  // Solicitar geolocalización al navegador
  const handleGetLocation = () => {
    if (!navigator.geolocation) {
      setError('La geolocalización no está soportada por tu navegador. Puedes seleccionar una ciudad manualmente.');
      return;
    }

    setLoading(true);
    setError(null);

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const coords = {
          lat: position.coords.latitude,
          lng: position.coords.longitude,
          name: 'Mi Ubicación Actual'
        };
        setUserLocation(coords);
        setLoading(false);
        usageTracker.trackNearbySearch();
      },
      (err) => {
        console.warn('Geolocation denied or failed:', err);
        const fallbackCity = SPANISH_CITIES_COORDS[selectedCity]?.name || selectedCity;
        setError(`No se pudo acceder a tu ubicación exacta. Se ha activado la estimación por ciudad (${fallbackCity}).`);
        setLoading(false);
        setUserLocation(SPANISH_CITIES_COORDS[selectedCity]);
      },
      { timeout: 10000, enableHighAccuracy: true }
    );
  };

  useEffect(() => {
    setUserLocation(SPANISH_CITIES_COORDS[selectedCity]);
    setCurrentPage(1);
  }, [selectedCity]);

  // Calculate distance for each university and sort (Memoized)
  const univsWithDistance = React.useMemo(() => {
    return universities.map((u) => {
      const coords = getUniversityCoords(u);
      const dist = userLocation && coords
        ? calculateHaversineDistance(userLocation.lat, userLocation.lng, coords.lat, coords.lng)
        : null;
      return { ...u, distanceKm: dist, targetCity: coords?.name || 'Ubicación no disponible' };
    }).sort((a, b) => (a.distanceKm ?? Infinity) - (b.distanceKm ?? Infinity));
  }, [universities, userLocation]);

  // Paginated Slice
  const paginatedUnivs = univsWithDistance.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  return (
    <div className="container" style={{ padding: '2.5rem 1.5rem' }}>
      {/* Header Banner */}
      <div className="glass-panel" style={{
        background: 'linear-gradient(135deg, var(--uca-navy) 0%, var(--uca-blue) 100%)',
        color: '#FFFFFF',
        padding: '2rem 2.25rem',
        borderRadius: 'var(--radius-lg)',
        marginBottom: '2.5rem',
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '1.5rem'
      }}>
        <div style={{ maxWidth: '650px' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', background: 'rgba(255, 255, 255, 0.15)', padding: '0.3rem 0.85rem', borderRadius: '50px', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.85rem' }}>
            <Compass size={16} color="var(--uca-sun)" /> Búsqueda por Cercanía a tu Ubicación
          </div>
          <h2 style={{ fontSize: '1.8rem', fontWeight: 800, marginBottom: '0.5rem' }}>
            Encuentra Universidades Cercanas
          </h2>
          <p style={{ fontSize: '0.95rem', color: '#E2E8F0', lineHeight: 1.5 }}>
            Utiliza la geolocalización de tu navegador o elige un punto de referencia para calcular la distancia en kilómetros a todas las universidades de España.
          </p>
        </div>

        {/* Action Controls */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', minWidth: '260px' }}>
          <button 
            className="btn btn-gold"
            onClick={handleGetLocation}
            disabled={loading}
            style={{ width: '100%', padding: '0.85rem 1.25rem' }}
          >
            <Navigation size={18} />
            {loading ? 'Obteniendo GPS...' : 'Usar Mi Ubicación Actual (GPS)'}
          </button>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.82rem', color: '#CBD5E1' }}>
            <span>O selecciona ciudad:</span>
            <select 
              aria-label="Seleccionar ciudad de referencia para cálculo de distancias"
              value={selectedCity} 
              onChange={(e) => setSelectedCity(e.target.value)}
              style={{
                background: 'rgba(255, 255, 255, 0.15)',
                color: '#FFFFFF',
                border: '1px solid rgba(255, 255, 255, 0.3)',
                padding: '0.35rem 0.65rem',
                borderRadius: '6px',
                outline: 'none',
                cursor: 'pointer',
                fontSize: '0.85rem'
              }}
            >
              {Object.entries(SPANISH_CITIES_COORDS).map(([key, city]) => (
                <option key={key} value={key} style={{ color: '#000' }}>
                  {city.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Active Location Info & Error Messages */}
      {error && (
        <div 
          role="alert"
          style={{ background: 'rgba(243, 167, 18, 0.12)', border: '1px solid var(--uca-gold)', padding: '1rem 1.25rem', borderRadius: 'var(--radius-md)', color: 'var(--text-main)', marginBottom: '2rem', fontSize: '0.9rem' }}
        >
          ⚠️ {error}
        </div>
      )}

      {userLocation && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
          <div style={{ fontSize: '1.05rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <MapPin size={20} color="var(--uca-cyan)" />
            Punto de referencia activo: <span className="text-gradient">{userLocation.name}</span>
          </div>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Ordenadas de menor a mayor distancia ({univsWithDistance.length} universidades)
          </span>
        </div>
      )}

      {/* Sorted Universities Grid with Distance integrated inside Card */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1.5rem' }}>
        {paginatedUnivs.map((univ) => (
          <UnivCard 
            key={univ.codigo} 
            univ={univ} 
            onViewDegrees={onViewDegrees} 
            distanceKm={univ.distanceKm}
          />
        ))}
      </div>

      {/* Pagination Controls */}
      <Pagination 
        currentPage={currentPage}
        totalItems={univsWithDistance.length}
        itemsPerPage={itemsPerPage}
        onPageChange={setCurrentPage}
        onItemsPerPageChange={setItemsPerPage}
      />
    </div>
  );
}
