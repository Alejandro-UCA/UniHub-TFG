import React, { useState } from 'react';
import { GraduationCap, MapPin, BookOpen, Sun, Moon, Info, Calculator, Menu, X } from 'lucide-react';

export default function Navbar({ activeTab, setActiveTab, isDark, toggleTheme }) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  const handleNavClick = (tab) => {
    setActiveTab(tab);
    setIsMenuOpen(false);
  };

  return (
    <header className="glass-panel" style={{ position: 'sticky', top: 0, zIndex: 100, borderRadius: 0, borderTop: 'none', borderLeft: 'none', borderRight: 'none' }}>
      <div className="container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.85rem 1.5rem', position: 'relative' }}>
        {/* Brand */}
        <div 
          style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer' }}
          onClick={() => handleNavClick('inicio')}
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

        {/* Mobile Hamburger Button */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button 
            onClick={toggleTheme}
            className="btn btn-outline"
            style={{ padding: '0.5rem', borderRadius: '50%', width: '38px', height: '38px' }}
            title={isDark ? "Cambiar a Modo Claro" : "Cambiar a Modo Oscuro"}
          >
            {isDark ? <Sun size={18} color="var(--uca-sun)" /> : <Moon size={18} color="var(--uca-blue)" />}
          </button>

          <button 
            className="mobile-menu-btn"
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            aria-label="Abrir Menú de Navegación"
          >
            {isMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>

        {/* Navigation Tabs */}
        <nav className={`nav-links ${isMenuOpen ? 'open' : ''}`} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button 
            className={`btn ${activeTab === 'inicio' ? 'btn-primary' : 'btn-outline'}`}
            style={{ padding: '0.5rem 1rem', fontSize: '0.88rem' }}
            onClick={() => handleNavClick('inicio')}
          >
            Inicio
          </button>
          <button 
            className={`btn ${activeTab === 'universidades' ? 'btn-primary' : 'btn-outline'}`}
            style={{ padding: '0.5rem 1rem', fontSize: '0.88rem' }}
            onClick={() => handleNavClick('universidades')}
          >
            <GraduationCap size={16} />
            Universidades
          </button>
          <button 
            className={`btn ${activeTab === 'titulaciones' ? 'btn-primary' : 'btn-outline'}`}
            style={{ padding: '0.5rem 1rem', fontSize: '0.88rem' }}
            onClick={() => handleNavClick('titulaciones')}
          >
            <BookOpen size={16} />
            Titulaciones
          </button>
          <button 
            className={`btn ${activeTab === 'cercania' ? 'btn-gold' : 'btn-outline'}`}
            style={{ padding: '0.5rem 1rem', fontSize: '0.88rem' }}
            onClick={() => handleNavClick('cercania')}
          >
            <MapPin size={16} />
            Por Cercanía
          </button>
          <button 
            className={`btn ${activeTab === 'calculadora' ? 'btn-primary' : 'btn-outline'}`}
            style={{ padding: '0.5rem 1rem', fontSize: '0.88rem', borderColor: 'rgba(16, 185, 129, 0.4)' }}
            onClick={() => handleNavClick('calculadora')}
          >
            <Calculator size={16} style={{ color: '#10B981' }} />
            Calcula tu Matrícula
          </button>
          <button 
            className={`btn ${activeTab === 'sobre-nosotros' ? 'btn-primary' : 'btn-outline'}`}
            style={{ padding: '0.5rem 1rem', fontSize: '0.88rem' }}
            onClick={() => handleNavClick('sobre-nosotros')}
          >
            <Info size={16} />
            Sobre Nosotros
          </button>
        </nav>
      </div>
    </header>
  );
}
