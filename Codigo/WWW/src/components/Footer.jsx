import React from 'react';
import { GraduationCap, ShieldCheck, Scale, Info } from 'lucide-react';

export default function Footer({ onNavigate }) {
  return (
    <footer style={{
      background: 'var(--uca-navy)',
      color: '#94A3B8',
      padding: '3.5rem 1.5rem 2rem 1.5rem',
      marginTop: '4rem',
      borderTop: '3px solid var(--uca-cyan)'
    }}>
      <div className="container" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '2.5rem', marginBottom: '2.5rem' }}>
        {/* Brand Column */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', color: '#FFFFFF', marginBottom: '0.85rem' }}>
            <GraduationCap size={28} color="var(--uca-azure)" />
            <span style={{ fontSize: '1.4rem', fontWeight: 800, letterSpacing: '-0.5px' }}>UniHub</span>
          </div>
          <p style={{ fontSize: '0.88rem', lineHeight: 1.6, marginBottom: '1rem' }}>
            Plataforma universitaria para la consulta integral de universidades y titulaciones en España con búsqueda inteligente por cercanía geográfica y simulador de matrícula.
          </p>
        </div>

        {/* Quick Links */}
        <div>
          <h4 style={{ color: '#FFFFFF', fontSize: '1rem', fontWeight: 700, marginBottom: '1rem' }}>Navegación</h4>
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.6rem', fontSize: '0.88rem' }}>
            <li>
              <button onClick={() => onNavigate && onNavigate('universidades')} style={{ color: 'var(--uca-azure)', cursor: 'pointer', background: 'none', border: 'none', padding: 0, font: 'inherit', fontSize: 'inherit' }} tabIndex={0}>
                Universidades de España
              </button>
            </li>
            <li>
              <button onClick={() => onNavigate && onNavigate('titulaciones')} style={{ color: '#94A3B8', cursor: 'pointer', background: 'none', border: 'none', padding: 0, font: 'inherit', fontSize: 'inherit' }} tabIndex={0}>
                Grados y Másteres Vigentes
              </button>
            </li>
            <li>
              <button onClick={() => onNavigate && onNavigate('cercania')} style={{ color: '#94A3B8', cursor: 'pointer', background: 'none', border: 'none', padding: 0, font: 'inherit', fontSize: 'inherit' }} tabIndex={0}>
                Localización por Cercanía
              </button>
            </li>
            <li>
              <button onClick={() => onNavigate && onNavigate('calculadora')} style={{ color: '#94A3B8', cursor: 'pointer', background: 'none', border: 'none', padding: 0, font: 'inherit', fontSize: 'inherit' }} tabIndex={0}>
                Calculadora de Matrícula
              </button>
            </li>
            <li>
              <button onClick={() => onNavigate && onNavigate('sobre-nosotros')} style={{ color: '#94A3B8', cursor: 'pointer', background: 'none', border: 'none', padding: 0, font: 'inherit', fontSize: 'inherit' }} tabIndex={0}>
                Sobre Nosotros (TFG UCA)
              </button>
            </li>
          </ul>
        </div>

        {/* Legal Notice & Official Data Sources */}
        <div>
          <h4 style={{ color: '#FFFFFF', fontSize: '1rem', fontWeight: 700, marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Scale size={18} color="var(--uca-gold)" /> Fuentes y Aviso Legal
          </h4>
          <p style={{ fontSize: '0.82rem', lineHeight: 1.6, color: '#94A3B8' }}>
            Los datos mostrados en UniHub proceden exclusivamente de <strong>fuentes públicas oficiales</strong> del Gobierno de España (Registro de Universidades, Centros y Títulos - RUCT y Boletín Oficial del Estado - BOE) y de los portales web institucionales de las universidades. UniHub no genera datos ficticios ni es titular de los registros oficiales.
          </p>
        </div>

        {/* Project info */}
        <div>
          <h4 style={{ color: '#FFFFFF', fontSize: '1rem', fontWeight: 700, marginBottom: '1rem' }}>UniHub España</h4>
          <p style={{ fontSize: '0.85rem', lineHeight: 1.6, color: '#94A3B8' }}>
            Desarrollado como Trabajo Fin de Grado en el Grado en Ingeniería Informática por Alejandro Ramos Rodríguez en la Universidad de Cádiz (UCA).
          </p>
        </div>
      </div>

      <div className="container" style={{ borderTop: '1px solid rgba(255, 255, 255, 0.1)', paddingTop: '1.5rem', textAlign: 'center', fontSize: '0.82rem', color: '#64748B' }}>
        <p>© 2026 UniHub. Proyecto de Fin de Grado en Ingeniería Informática — Escuela Superior de Ingeniería, Universidad de Cádiz (UCA).</p>
      </div>
    </footer>
  );
}
