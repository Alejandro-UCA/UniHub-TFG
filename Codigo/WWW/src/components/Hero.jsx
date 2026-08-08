import React, { useState } from 'react';
import { Search, MapPin, BookOpen, GraduationCap, ArrowRight } from 'lucide-react';
import usageTracker from '../analytics/usageTracker';

export default function Hero({ onSearch, setActiveTab, totalUnivs, totalDegrees }) {
  const [searchTerm, setSearchTerm] = useState('');

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    if (!searchTerm.trim()) return;
    usageTracker.trackSearch(searchTerm, 'hero');
    onSearch(searchTerm);
    setActiveTab('titulaciones');
  };

  return (
    <section style={{
      background: 'linear-gradient(135deg, var(--uca-navy) 0%, var(--uca-blue) 60%, #004B87 100%)',
      color: '#FFFFFF',
      padding: '4rem 1.5rem 5rem 1.5rem',
      position: 'relative',
      overflow: 'hidden'
    }}>
      {/* Decorative Background Elements */}
      <div style={{
        position: 'absolute',
        top: '-10%',
        right: '-5%',
        width: '450px',
        height: '450px',
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(0, 168, 232, 0.25) 0%, rgba(0, 43, 73, 0) 70%)',
        pointerEvents: 'none'
      }} />

      <div className="container" style={{ position: 'relative', zIndex: 2, textAlign: 'center', maxWidth: '900px' }}>
        {/* UniHub Badge */}
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.5rem',
          background: 'rgba(255, 255, 255, 0.12)',
          border: '1px solid rgba(255, 255, 255, 0.25)',
          padding: '0.35rem 1rem',
          borderRadius: '50px',
          fontSize: '0.85rem',
          fontWeight: 600,
          marginBottom: '1.5rem',
          backdropFilter: 'blur(8px)'
        }}>
          <span style={{ color: 'var(--uca-sun)' }}>★</span> UniHub: Tu Guía de Educación Superior
        </div>

        <h1 style={{ fontSize: 'clamp(2.2rem, 5vw, 3.4rem)', fontWeight: 800, marginBottom: '1.25rem', lineHeight: 1.15 }}>
          Explora las <span className="text-gradient">Universidades y Titulaciones</span> de España
        </h1>

        <p style={{ fontSize: '1.15rem', color: '#E2E8F0', marginBottom: '2.5rem', fontWeight: 400, maxWidth: '750px', margin: '0 auto 2.5rem auto' }}>
          Acceso centralizado a universidades públicas y privadas, Grados, Másteres y planes de estudio desglosados con localización por cercanía geográfica.
        </p>

        {/* Quick Search Form */}
        <form onSubmit={handleSearchSubmit} style={{
          background: 'rgba(255, 255, 255, 0.95)',
          borderRadius: 'var(--radius-md)',
          padding: '0.5rem',
          display: 'flex',
          gap: '0.5rem',
          boxShadow: '0 12px 32px rgba(0, 0, 0, 0.25)',
          maxWidth: '650px',
          margin: '0 auto 3rem auto',
          backdropFilter: 'blur(10px)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', paddingLeft: '1rem', color: '#64748B' }}>
            <Search size={22} />
          </div>
          <input 
            type="text" 
            placeholder="Busca titulación (ej. Derecho, Inteligencia Artificial, Informática...)"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              flex: 1,
              border: 'none',
              outline: 'none',
              fontSize: '1rem',
              color: '#1A2530',
              background: 'transparent',
              padding: '0.75rem 0.5rem'
            }}
          />
          <button type="submit" className="btn btn-primary" style={{ padding: '0.75rem 1.75rem', fontSize: '0.95rem' }}>
            Buscar
          </button>
        </form>

        {/* Stat Badges */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1.25rem' }}>
          <div className="glass-panel" style={{ padding: '1.25rem', background: 'rgba(255, 255, 255, 0.08)', borderColor: 'rgba(255, 255, 255, 0.15)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', color: 'var(--uca-sun)', marginBottom: '0.25rem' }}>
              <GraduationCap size={22} />
              <span style={{ fontSize: '1.8rem', fontWeight: 800 }}>{totalUnivs !== undefined ? totalUnivs : 109}</span>
            </div>
            <div style={{ fontSize: '0.85rem', color: '#CBD5E1', fontWeight: 500 }}>Universidades Oficiales</div>
          </div>

          <div className="glass-panel" style={{ padding: '1.25rem', background: 'rgba(255, 255, 255, 0.08)', borderColor: 'rgba(255, 255, 255, 0.15)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', color: 'var(--uca-azure)', marginBottom: '0.25rem' }}>
              <BookOpen size={22} />
              <span style={{ fontSize: '1.8rem', fontWeight: 800 }}>{totalDegrees !== undefined ? totalDegrees : '1.800+'}</span>
            </div>
            <div style={{ fontSize: '0.85rem', color: '#CBD5E1', fontWeight: 500 }}>Titulaciones Vigentes</div>
          </div>

          <div 
            className="glass-panel" 
            style={{ padding: '1.25rem', background: 'rgba(255, 255, 255, 0.08)', borderColor: 'rgba(255, 255, 255, 0.15)', cursor: 'pointer' }}
            onClick={() => setActiveTab('cercania')}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', color: 'var(--uca-sun)', marginBottom: '0.25rem' }}>
              <MapPin size={22} />
              <span style={{ fontSize: '1.2rem', fontWeight: 700 }}>Geolocalización</span>
            </div>
            <div style={{ fontSize: '0.85rem', color: '#CBD5E1', fontWeight: 500, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.25rem' }}>
              Búsqueda por Cercanía <ArrowRight size={14} />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
