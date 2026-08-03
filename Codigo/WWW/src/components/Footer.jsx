import React from 'react';
import { GraduationCap, Heart } from 'lucide-react';

export default function Footer({ onNavigate }) {
  return (
    <footer style={{
      background: 'var(--uca-navy)',
      color: '#94A3B8',
      padding: '3rem 1.5rem 2rem 1.5rem',
      marginTop: '4rem',
      borderTop: '3px solid var(--uca-cyan)'
    }}>
      <div className="container" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '2rem', marginBottom: '2.5rem' }}>
        {/* Brand Column */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', color: '#FFFFFF', marginBottom: '0.85rem' }}>
            <GraduationCap size={26} color="var(--uca-azure)" />
            <span style={{ fontSize: '1.35rem', fontWeight: 800, letterSpacing: '-0.5px' }}>UniHub</span>
          </div>
          <p style={{ fontSize: '0.88rem', lineHeight: 1.6, marginBottom: '1rem' }}>
            Plataforma universitaria para la consulta integral de universidades y titulaciones en España con búsqueda inteligente por cercanía geográfica.
          </p>
        </div>

        {/* Quick Links */}
        <div>
          <h4 style={{ color: '#FFFFFF', fontSize: '1rem', fontWeight: 700, marginBottom: '1rem' }}>Navegación</h4>
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.88rem' }}>
            <li>
              <span onClick={() => onNavigate && onNavigate('universidades')} style={{ color: 'var(--uca-azure)', cursor: 'pointer' }}>
                Universidades de España
              </span>
            </li>
            <li>
              <span onClick={() => onNavigate && onNavigate('titulaciones')} style={{ color: '#94A3B8', cursor: 'pointer' }}>
                Grados y Másteres Vigentes
              </span>
            </li>
            <li>
              <span onClick={() => onNavigate && onNavigate('cercania')} style={{ color: '#94A3B8', cursor: 'pointer' }}>
                Localización por Cercanía
              </span>
            </li>
            <li>
              <span onClick={() => onNavigate && onNavigate('sobre-nosotros')} style={{ color: '#94A3B8', cursor: 'pointer' }}>
                Sobre Nosotros (TFG UCA)
              </span>
            </li>
          </ul>
        </div>

        {/* Project info */}
        <div>
          <h4 style={{ color: '#FFFFFF', fontSize: '1rem', fontWeight: 700, marginBottom: '1rem' }}>UniHub España</h4>
          <p style={{ fontSize: '0.85rem', lineHeight: 1.6 }}>
            Desarrollado como Trabajo Fin de Grado en Ingeniería Informática por Alejandro Ramos Rodríguez en la Universidad de Cádiz.
          </p>
        </div>
      </div>

      <div className="container" style={{ borderTop: '1px solid rgba(255, 255, 255, 0.1)', paddingTop: '1.5rem', textAlign: 'center', fontSize: '0.82rem' }}>
        <p>© 2026 UniHub. Creado con <Heart size={14} color="var(--uca-gold)" style={{ verticalAlign: 'middle' }} /> para la comunidad universitaria de España.</p>
      </div>
    </footer>
  );
}
