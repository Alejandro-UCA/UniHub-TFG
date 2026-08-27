import React, { useState, useEffect } from 'react';
import { GraduationCap, MapPin, BookOpen, Sun, Moon, Info, Calculator, Menu, X, ShieldCheck } from 'lucide-react';

export default function Navbar({ activeTab, setActiveTab, isDark, toggleTheme }) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  const handleNavClick = (tab) => {
    setActiveTab(tab);
    setIsMenuOpen(false);
  };

  const handleBrandKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleNavClick('inicio');
    }
  };

  // Close mobile menu on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isMenuOpen) {
        setIsMenuOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isMenuOpen]);

  return (
    <header className="glass-panel" style={{ position: 'sticky', top: 0, zIndex: 100, borderRadius: 0, borderTop: 'none', borderLeft: 'none', borderRight: 'none' }}>
      <div className="container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.85rem 1.5rem', position: 'relative' }}>
        {/* Brand */}
        <div 
          role="button"
          tabIndex={0}
          aria-label="UniHub - Ir a página de inicio"
          style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer', userSelect: 'none' }}
          onClick={() => handleNavClick('inicio')}
          onKeyDown={handleBrandKeyDown}
        >
          <div style={{
            background: 'linear-gradient(135deg, var(--uca-blue), var(--uca-cyan))',
            padding: '0.5rem',
            borderRadius: '10px',
            color: '#FFFFFF',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: 'var(--shadow-sm)'
          }}>
            <GraduationCap size={26} />
          </div>
          <div>
            <div style={{ fontSize: '1.35rem', fontWeight: 800, letterSpacing: '-0.5px', color: 'var(--text-main)', lineHeight: 1.1 }}>
              Uni<span className="text-gradient">Hub</span>
            </div>
            <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--uca-cyan)', textTransform: 'uppercase', letterSpacing: '0.8px' }}>
              Educación Superior en España
            </div>
          </div>
        </div>

        {/* Action Controls & Mobile Hamburger Button */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button 
            type="button"
            onClick={toggleTheme}
            className="btn btn-outline"
            style={{ padding: '0.5rem', borderRadius: '50%', width: '38px', height: '38px' }}
            title={isDark ? "Cambiar a Modo Claro" : "Cambiar a Modo Oscuro"}
            aria-label={isDark ? "Cambiar a Modo Claro" : "Cambiar a Modo Oscuro"}
          >
            {isDark ? <Sun size={18} color="var(--uca-sun)" /> : <Moon size={18} color="var(--uca-blue)" />}
          </button>

          <button 
            type="button"
            className="mobile-menu-btn"
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            aria-expanded={isMenuOpen}
            aria-controls="main-navigation"
            aria-label={isMenuOpen ? "Cerrar Menú de Navegación" : "Abrir Menú de Navegación"}
          >
            {isMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>

        {/* Navigation Tabs */}
        <nav 
          id="main-navigation"
          aria-label="Navegación principal"
          className={`nav-links ${isMenuOpen ? 'open' : ''}`} 
          style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}
        >
          <button 
            type="button"
            className={`btn nav-tab-btn ${activeTab === 'inicio' ? 'btn-primary' : 'btn-outline'}`}
            onClick={() => handleNavClick('inicio')}
            aria-current={activeTab === 'inicio' ? 'page' : undefined}
          >
            Inicio
          </button>
          <button 
            type="button"
            className={`btn nav-tab-btn ${activeTab === 'universidades' ? 'btn-primary' : 'btn-outline'}`}
            onClick={() => handleNavClick('universidades')}
            aria-current={activeTab === 'universidades' ? 'page' : undefined}
          >
            <GraduationCap size={16} />
            Universidades
          </button>
          <button 
            type="button"
            className={`btn nav-tab-btn ${activeTab === 'titulaciones' ? 'btn-primary' : 'btn-outline'}`}
            onClick={() => handleNavClick('titulaciones')}
            aria-current={activeTab === 'titulaciones' ? 'page' : undefined}
          >
            <BookOpen size={16} />
            Titulaciones
          </button>
          <button 
            type="button"
            className={`btn nav-tab-btn ${activeTab === 'cercania' ? 'btn-gold' : 'btn-outline'}`}
            onClick={() => handleNavClick('cercania')}
            aria-current={activeTab === 'cercania' ? 'page' : undefined}
          >
            <MapPin size={16} />
            Por Cercanía
          </button>
          <button 
            type="button"
            className={`btn nav-tab-btn ${activeTab === 'calculadora' ? 'btn-primary' : 'btn-outline'}`}
            style={activeTab !== 'calculadora' ? { borderColor: 'rgba(16, 185, 129, 0.4)' } : {}}
            onClick={() => handleNavClick('calculadora')}
            aria-current={activeTab === 'calculadora' ? 'page' : undefined}
          >
            <Calculator size={16} style={{ color: activeTab === 'calculadora' ? '#FFFFFF' : '#10B981' }} />
            Calcula tu Matrícula
          </button>
          <button 
            type="button"
            className={`btn nav-tab-btn ${activeTab === 'sobre-nosotros' ? 'btn-primary' : 'btn-outline'}`}
            onClick={() => handleNavClick('sobre-nosotros')}
            aria-current={activeTab === 'sobre-nosotros' ? 'page' : undefined}
          >
            <Info size={16} />
            Sobre Nosotros
          </button>
          <button 
            type="button"
            className={`btn nav-tab-btn ${activeTab === 'admin' || activeTab === 'admin-login' ? 'btn-primary' : 'btn-outline'}`}
            style={activeTab !== 'admin' && activeTab !== 'admin-login' ? { borderColor: 'rgba(239, 68, 68, 0.4)' } : {}}
            onClick={() => handleNavClick('admin')}
            title="Panel de Administración"
            aria-current={activeTab === 'admin' || activeTab === 'admin-login' ? 'page' : undefined}
          >
            <ShieldCheck size={16} style={{ color: activeTab === 'admin' || activeTab === 'admin-login' ? '#FFFFFF' : 'var(--uca-sun)' }} />
            Admin
          </button>
        </nav>
      </div>
    </header>
  );
}
