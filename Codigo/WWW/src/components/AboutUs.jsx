import React from 'react';
import { GraduationCap, Award, BookOpen, Database, ExternalLink, Server, Zap, Globe, DollarSign } from 'lucide-react';

export default function AboutUs() {
  const swaggerUrl = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/v1').replace(/\/api\/v1\/?$/, '/docs');

  return (
    <div className="container" style={{ padding: '3rem 1.5rem 4rem 1.5rem', maxWidth: '1000px' }}>
      {/* Header Banner */}
      <div className="glass-panel" style={{
        background: 'linear-gradient(135deg, var(--uca-navy) 0%, var(--uca-blue) 100%)',
        color: '#FFFFFF',
        padding: '2.75rem 2rem',
        borderRadius: 'var(--radius-lg)',
        marginBottom: '2.5rem',
        textAlign: 'center',
        boxShadow: 'var(--shadow-lg)'
      }}>
        <div style={{
          display: 'inline-flex',
          padding: '0.85rem',
          background: 'rgba(255, 255, 255, 0.15)',
          borderRadius: '50%',
          color: 'var(--uca-sun)',
          marginBottom: '1rem'
        }}>
          <GraduationCap size={40} />
        </div>
        <h1 style={{ fontSize: '2.4rem', fontWeight: 800, marginBottom: '0.75rem' }}>
          Sobre Nosotros - Proyecto UniHub
        </h1>
        <p style={{ fontSize: '1.1rem', color: '#E2E8F0', maxWidth: '750px', margin: '0 auto', lineHeight: 1.6 }}>
          Plataforma web abierta, API REST e infraestructura contenerizada para la inspección, simulación financiera y análisis de la educación superior universitaria en España.
        </p>
      </div>

      {/* Main Author & Academic Information */}
      <div className="glass-panel" style={{ padding: '2.25rem', marginBottom: '2rem', borderLeft: '5px solid var(--uca-cyan)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.25rem' }}>
          <div style={{ background: 'rgba(0, 132, 200, 0.12)', padding: '0.85rem', borderRadius: 'var(--radius-md)', color: 'var(--uca-cyan)' }}>
            <Award size={32} />
          </div>
          <div>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--uca-navy)' }}>
              Trabajo Fin de Grado (TFG)
            </h2>
            <div style={{ fontSize: '1rem', color: 'var(--uca-azure)', fontWeight: 700 }}>
              Universidad de Cádiz (UCA) — Escuela Superior de Ingeniería (ESI)
            </div>
          </div>
        </div>

        <div style={{ fontSize: '1rem', color: 'var(--text-main)', lineHeight: 1.75, marginBottom: '1.75rem' }}>
          El proyecto <strong>UniHub</strong> ha sido diseñado y desarrollado por el estudiante <strong>Alejandro Ramos Rodríguez</strong> como su <strong>Trabajo Fin de Grado</strong> dentro del <strong>Grado en Ingeniería Informática</strong> en la <strong>Universidad de Cádiz (UCA)</strong>. Nace con el propósito de resolver la fragmentación del acceso a los planes de estudio oficiales, unificar los decretos de precios públicos y honorarios privados, y proporcionar un simulador financiero de matrícula transparente y accesible.
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.25rem' }}>
          <div style={{ background: 'var(--bg-main)', padding: '1.15rem 1.25rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
            <div style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700, letterSpacing: '0.5px' }}>Autor del Proyecto</div>
            <div style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-main)', marginTop: '0.2rem' }}>Alejandro Ramos Rodríguez</div>
            <div style={{ fontSize: '0.85rem', color: 'var(--uca-azure)', fontWeight: 600 }}>Grado en Ingeniería Informática</div>
          </div>

          <div style={{ background: 'var(--bg-main)', padding: '1.15rem 1.25rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
            <div style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700, letterSpacing: '0.5px' }}>Tutoría & Escuela</div>
            <div style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-main)', marginTop: '0.2rem' }}>Escuela Superior de Ingeniería</div>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Campus de Puerto Real (UCA)</div>
          </div>

          <div style={{ background: 'var(--bg-main)', padding: '1.15rem 1.25rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
            <div style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700, letterSpacing: '0.5px' }}>Institución Universitaria</div>
            <div style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--uca-blue)', marginTop: '0.2rem' }}>Universidad de Cádiz (UCA)</div>
            <div style={{ fontSize: '0.85rem', color: 'var(--uca-cyan)', fontWeight: 600 }}>www.uca.es</div>
          </div>
        </div>
      </div>

      {/* Project Architecture & Technological Advancement Breakdown */}
      <div className="glass-panel" style={{ padding: '2.25rem', marginBottom: '2rem' }}>
        <h3 style={{ fontSize: '1.4rem', fontWeight: 800, marginBottom: '0.5rem', color: 'var(--uca-navy)', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <Zap size={26} color="var(--uca-gold)" /> Arquitectura Global y Estado del Proyecto (4 Fases)
        </h3>
        <p style={{ fontSize: '0.95rem', color: 'var(--text-muted)', marginBottom: '1.75rem', lineHeight: 1.6 }}>
          UniHub se estructura en una arquitectura modular en 4 Fases integradas de punta a punta:
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.5rem' }}>
          {/* Phase 1 */}
          <div style={{ background: 'var(--bg-main)', padding: '1.35rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-light)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.75rem' }}>
              <div style={{ background: 'rgba(0, 132, 200, 0.15)', padding: '0.5rem', borderRadius: 'var(--radius-sm)', color: 'var(--uca-cyan)' }}>
                <Globe size={20} />
              </div>
              <h4 style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--uca-navy)' }}>Fase 1: Crawler & BOE</h4>
            </div>
            <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
              Sistema multihilo de recolección de datos sobre RUCT, parser de PDFs del BOE en dos procesos (Red/CPU), rascado de webs oficiales universitarias (públicas y privadas) y más de <strong>13.653 planes estructurados</strong>.
            </p>
          </div>

          {/* Phase 2 */}
          <div style={{ background: 'var(--bg-main)', padding: '1.35rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-light)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.75rem' }}>
              <div style={{ background: 'rgba(10, 37, 64, 0.15)', padding: '0.5rem', borderRadius: 'var(--radius-sm)', color: 'var(--uca-blue)' }}>
                <Database size={20} />
              </div>
              <h4 style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--uca-navy)' }}>Fase 2: API REST & PostgreSQL</h4>
            </div>
            <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
              Base de datos relacional PostgreSQL con índices GIN por trigramas (`pg_trgm`), rol de lectura restringido `unihub_api_user`, migración masiva por lotes (ETL) y sincronización reactiva HTTP POST.
            </p>
          </div>

          {/* Phase 3 */}
          <div style={{ background: 'var(--bg-main)', padding: '1.35rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-light)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.75rem' }}>
              <div style={{ background: 'rgba(217, 119, 6, 0.15)', padding: '0.5rem', borderRadius: 'var(--radius-sm)', color: 'var(--uca-gold)' }}>
                <DollarSign size={20} />
              </div>
              <h4 style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--uca-navy)' }}>Fase 3: Web SPA & Calculadora</h4>
            </div>
            <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
              Frontend React responsive con simulador financiero "Calcula tu Matrícula" (desgloses por repetición, Beca MEC, 99% CCAA, exenciones privadas), diseño móvil hamburguesa, accesibilidad A11y y geolocalización.
            </p>
          </div>

          {/* Phase 4 */}
          <div style={{ background: 'var(--bg-main)', padding: '1.35rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-light)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.75rem' }}>
              <div style={{ background: 'rgba(16, 185, 129, 0.15)', padding: '0.5rem', borderRadius: 'var(--radius-sm)', color: '#10B981' }}>
                <Server size={20} />
              </div>
              <h4 style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--uca-navy)' }}>Fase 4: Docker & Telemetría</h4>
            </div>
            <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
              Orquestación física con Docker Compose (4 contenedores `unihub_*`), volumen persistente `unihub_postgres_data`, telemetría cgroup de RAM/CPU y estimación de huella de carbono Green IT ($gCO_2$).
            </p>
          </div>
        </div>
      </div>

      {/* Origin of Data & Links */}
      <div className="glass-panel" style={{ padding: '2.25rem' }}>
        <h3 style={{ fontSize: '1.3rem', fontWeight: 800, marginBottom: '1rem', color: 'var(--uca-blue)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <BookOpen size={24} color="var(--uca-cyan)" /> Fuentes Oficiales de Información
        </h3>
        
        <p style={{ fontSize: '0.95rem', color: 'var(--text-muted)', lineHeight: 1.7, marginBottom: '1.5rem' }}>
          La información procesada por UniHub procede de fuentes de datos de dominio público del Gobierno de España y las comunidades autónomas:
        </p>

        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
          <a 
            href="https://www.educacion.gob.es/ruct/home" 
            target="_blank" 
            rel="noopener noreferrer" 
            className="btn btn-outline"
            style={{ fontSize: '0.88rem' }}
          >
            Portal Oficial RUCT <ExternalLink size={14} />
          </a>
          <a 
            href="https://www.boe.es" 
            target="_blank" 
            rel="noopener noreferrer" 
            className="btn btn-outline"
            style={{ fontSize: '0.88rem' }}
          >
            Boletín Oficial del Estado (BOE) <ExternalLink size={14} />
          </a>
          <a 
            href="https://www.uca.es" 
            target="_blank" 
            rel="noopener noreferrer" 
            className="btn btn-outline"
            style={{ fontSize: '0.88rem', color: 'var(--uca-cyan)', borderColor: 'var(--uca-cyan)' }}
          >
            Universidad de Cádiz (UCA) <ExternalLink size={14} />
          </a>
          <a 
            href={swaggerUrl} 
            target="_blank" 
            rel="noopener noreferrer" 
            className="btn btn-gold"
            style={{ fontSize: '0.88rem' }}
          >
            Documentación Swagger API <ExternalLink size={14} />
          </a>
        </div>
      </div>
    </div>
  );
}
