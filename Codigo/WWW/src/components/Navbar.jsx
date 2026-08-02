import React from 'react';
import { GraduationCap, MapPin, BookOpen, ShieldCheck, Sun, Moon } from 'lucide-react';

export default function Navbar({ activeTab, setActiveTab, isAdmin, setIsAdmin, setShowAdminModal, isDark, toggleTheme }) {
  return (
    <header className="glass-panel" style={{ position: 'sticky', top: 0, zIndex: 100, borderRadius: 0, borderTop: 'none', borderLeft: 'none', borderRight: 'none' }}>
      <div className="container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.85rem 1.5rem' }}>
        {/* UCA Logo & Brand */}
        <div 
          style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer' }}
          onClick={() => setActiveTab('inicio')}
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
            <div style={{ fontSize: '1.2rem', fontWeight: 800, letterSpacing: '-0.5px', color: 'var(--text-main)', lineHeight: 1.1 }}>
              RUCT <span className="text-gradient">España</span>
            </div>
            <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--uca-cyan)', textTransform: 'uppercase', letterSpacing: '0.8px' }}>
              Universidad de Cádiz (UCA)
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button 
            className={`btn ${activeTab === 'inicio' ? 'btn-primary' : 'btn-outline'}`}
            style={{ padding: '0.5rem 1rem', fontSize: '0.88rem' }}
            onClick={() => setActiveTab('inicio')}
          >
            Inicio
          </button>
          <button 
            className={`btn ${activeTab === 'universidades' ? 'btn-primary' : 'btn-outline'}`}
            style={{ padding: '0.5rem 1rem', fontSize: '0.88rem' }}
            onClick={() => setActiveTab('universidades')}
          >
            <GraduationCap size={16} />
            Universidades
          </button>
          <button 
            className={`btn ${activeTab === 'titulaciones' ? 'btn-primary' : 'btn-outline'}`}
            style={{ padding: '0.5rem 1rem', fontSize: '0.88rem' }}
            onClick={() => setActiveTab('titulaciones')}
          >
            <BookOpen size={16} />
            Titulaciones
          </button>
          <button 
            className={`btn ${activeTab === 'cercania' ? 'btn-gold' : 'btn-outline'}`}
            style={{ padding: '0.5rem 1rem', fontSize: '0.88rem' }}
            onClick={() => setActiveTab('cercania')}
          >
            <MapPin size={16} />
            Por Cercanía
          </button>

          {/* Dark Mode Toggle */}
          <button 
            onClick={toggleTheme}
            className="btn btn-outline"
            style={{ padding: '0.5rem', borderRadius: '50%', width: '38px', height: '38px' }}
            title={isDark ? "Cambiar a Modo Claro" : "Cambiar a Modo Oscuro"}
          >
            {isDark ? <Sun size={18} color="var(--uca-sun)" /> : <Moon size={18} color="var(--uca-blue)" />}
          </button>

          {/* Admin Login / Dashboard Trigger */}
          {isAdmin ? (
            <button 
              className="btn btn-primary"
              style={{ background: 'linear-gradient(135deg, #10B981, #059669)', padding: '0.5rem 1rem', fontSize: '0.85rem' }}
              onClick={() => setActiveTab('admin')}
            >
              <ShieldCheck size={16} />
              Panel Admin
            </button>
          ) : (
            <button 
              className="btn btn-outline"
              style={{ padding: '0.5rem 0.85rem', fontSize: '0.82rem', borderColor: 'var(--border-light)' }}
              onClick={() => setShowAdminModal(true)}
            >
              <ShieldCheck size={16} />
              Admin
            </button>
          )}
        </nav>
      </div>
    </header>
  );
}
