import React from 'react';
import { GraduationCap, Award, BookOpen, Code, Database, Heart, ExternalLink } from 'lucide-react';

export default function AboutUs() {
  return (
    <div className="container" style={{ padding: '3rem 1.5rem 4rem 1.5rem', maxWidth: '900px' }}>
      {/* Header Banner */}
      <div className="glass-panel" style={{
        background: 'linear-gradient(135deg, var(--uca-navy) 0%, var(--uca-blue) 100%)',
        color: '#FFFFFF',
        padding: '2.5rem 2rem',
        borderRadius: 'var(--radius-lg)',
        marginBottom: '2.5rem',
        textAlign: 'center'
      }}>
        <div style={{
          display: 'inline-flex',
          padding: '0.85rem',
          background: 'rgba(255, 255, 255, 0.15)',
          borderRadius: '50%',
          color: 'var(--uca-sun)',
          marginBottom: '1rem'
        }}>
          <GraduationCap size={36} />
        </div>
        <h1 style={{ fontSize: '2.2rem', fontWeight: 800, marginBottom: '0.75rem' }}>
          Sobre Nosotros - Proyecto UniHub
        </h1>
        <p style={{ fontSize: '1.05rem', color: '#E2E8F0', maxWidth: '700px', margin: '0 auto' }}>
          Plataforma web y sistema distribuido para la consulta e inspección de educación superior en España.
        </p>
      </div>

      {/* Main Author & Academic Information */}
      <div className="glass-panel" style={{ padding: '2rem', marginBottom: '2rem', borderLeft: '4px solid var(--uca-cyan)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.25rem' }}>
          <div style={{ background: 'rgba(0, 132, 200, 0.12)', padding: '0.75rem', borderRadius: 'var(--radius-md)', color: 'var(--uca-cyan)' }}>
            <Award size={28} />
          </div>
          <div>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--uca-navy)' }}>
              Trabajo Fin de Grado (TFG)
            </h2>
            <div style={{ fontSize: '0.95rem', color: 'var(--uca-azure)', fontWeight: 600 }}>
              Universidad de Cádiz (UCA)
            </div>
          </div>
        </div>

        <div style={{ fontSize: '1rem', color: 'var(--text-main)', lineHeight: 1.7, marginBottom: '1.5rem' }}>
          Este proyecto ha sido desarrollado por el alumno <strong>Alejandro Ramos Rodríguez</strong> como su <strong>Trabajo Fin de Grado</strong> dentro del <strong>Grado en Ingeniería Informática</strong> de la <strong>Universidad de Cádiz (UCA)</strong>.
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1.25rem' }}>
          <div style={{ background: 'var(--bg-main)', padding: '1rem 1.25rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
            <div style={{ fontSize: '0.8rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700 }}>Autor del Proyecto</div>
            <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-main)', marginTop: '0.2rem' }}>Alejandro Ramos Rodríguez</div>
          </div>

          <div style={{ background: 'var(--bg-main)', padding: '1rem 1.25rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
            <div style={{ fontSize: '0.8rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700 }}>Titulación</div>
            <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-main)', marginTop: '0.2rem' }}>Grado en Ingeniería Informática</div>
          </div>

          <div style={{ background: 'var(--bg-main)', padding: '1rem 1.25rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
            <div style={{ fontSize: '0.8rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700 }}>Institución Universitaria</div>
            <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--uca-blue)', marginTop: '0.2rem' }}>Universidad de Cádiz (UCA)</div>
          </div>
        </div>
      </div>

      {/* Origin of Data & Architecture */}
      <div className="glass-panel" style={{ padding: '2rem' }}>
        <h3 style={{ fontSize: '1.25rem', fontWeight: 800, marginBottom: '1rem', color: 'var(--uca-blue)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Database size={22} color="var(--uca-gold)" /> Origen de los Datos e Infraestructura
        </h3>
        
        <p style={{ fontSize: '0.95rem', color: 'var(--text-muted)', lineHeight: 1.7, marginBottom: '1.25rem' }}>
          Los datos sobre las universidades públicas y privadas, titulaciones vigentes y planes de estudio desglosados son obtenidos a través del Registro Oficial <strong>RUCT</strong> (Registro de Universidades, Centros y Títulos) del Ministerio de Educación, Formación Profesional y Deportes de España, junto con las publicaciones oficiales del <strong>Boletín Oficial del Estado (BOE)</strong>.
        </p>

        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
          <a 
            href="https://www.educacion.gob.es/ruct/home" 
            target="_blank" 
            rel="noreferrer" 
            className="btn btn-outline"
            style={{ fontSize: '0.88rem' }}
          >
            Portal Oficial RUCT <ExternalLink size={14} />
          </a>
          <a 
            href="https://www.boe.es" 
            target="_blank" 
            rel="noreferrer" 
            className="btn btn-outline"
            style={{ fontSize: '0.88rem' }}
          >
            Boletín Oficial del Estado (BOE) <ExternalLink size={14} />
          </a>
          <a 
            href="https://www.uca.es" 
            target="_blank" 
            rel="noreferrer" 
            className="btn btn-outline"
            style={{ fontSize: '0.88rem', color: 'var(--uca-cyan)', borderColor: 'var(--uca-cyan)' }}
          >
            Universidad de Cádiz (UCA) <ExternalLink size={14} />
          </a>
        </div>
      </div>
    </div>
  );
}
