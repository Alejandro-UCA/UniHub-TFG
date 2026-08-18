import React, { useState, useEffect } from 'react';
import { X, Save, AlertCircle, Building, BookOpen, Layers } from 'lucide-react';

export default function AdminFormModal({ isOpen, mode, type, initialData, onClose, onSubmit }) {
  const [formData, setFormData] = useState({});
  const [error, setError] = useState('');

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (initialData) {
      setFormData(initialData);
    } else {
      if (type === 'universidad') {
        setFormData({
          codigo: '',
          nombre: '',
          tipo: 'Pública',
          comunidad_autonoma: 'Comunidad de Madrid',
          municipio: '',
          provincia: '',
          web: '',
          email: '',
          telefono: '',
          gestionado_por_admin: false
        });
      } else if (type === 'titulacion') {
        setFormData({
          codigo_estudio: '',
          titulo: '',
          nivel_academico: 'Grado - RD 822/2021 (2)',
          estado: 'Publicado en B.O.E.',
          universidad_codigo: '',
          precio_credito_ects: '',
          precio_credito_2: '',
          precio_credito_3: '',
          precio_credito_4: '',
          gestionado_por_admin: false
        });
      } else if (type === 'asignatura') {
        setFormData({
          nombre_elemento: '',
          creditos_ects: '6',
          caracter: 'OB',
          curso: '1',
          cuatrimestre: '1C',
          modulo: '',
          materia: ''
        });
      }
    }
  }, [initialData, type, isOpen]);

  if (!isOpen) return null;

  const handleChange = (e) => {
    const value = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setFormData({ ...formData, [e.target.name]: value });
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setError('');

    if (type === 'universidad' && (!formData.codigo || !formData.codigo.trim() || !formData.nombre || !formData.nombre.trim())) {
      setError('El código y el nombre de la universidad son obligatorios.');
      return;
    }
    if (type === 'titulacion' && (!formData.codigo_estudio || !formData.codigo_estudio.trim() || !formData.titulo || !formData.titulo.trim() || !formData.universidad_codigo || !formData.universidad_codigo.trim())) {
      setError('El código de estudio, título y código de universidad son obligatorios.');
      return;
    }
    if (type === 'asignatura' && (!formData.nombre_elemento || !formData.nombre_elemento.trim())) {
      setError('El nombre de la asignatura es obligatorio.');
      return;
    }

    onSubmit(formData);
  };

  const isEdit = mode === 'edit';

  const getTypeLabel = () => {
    if (type === 'universidad') return 'Universidad';
    if (type === 'titulacion') return 'Titulación';
    return 'Asignatura';
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" style={{ maxWidth: '600px' }} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div style={{
          background: 'linear-gradient(135deg, var(--uca-navy) 0%, var(--uca-blue) 100%)',
          color: '#FFFFFF',
          padding: '1.25rem 1.5rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderTopLeftRadius: 'var(--radius-lg)',
          borderTopRightRadius: 'var(--radius-lg)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            {type === 'universidad' ? (
              <Building size={22} color="var(--uca-sun)" />
            ) : type === 'titulacion' ? (
              <BookOpen size={22} color="var(--uca-azure)" />
            ) : (
              <Layers size={22} color="var(--uca-gold)" />
            )}
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700 }}>
              {isEdit ? `Editar ${getTypeLabel()}` : `Añadir Nueva ${getTypeLabel()}`}
            </h3>
          </div>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', color: '#FFFFFF', cursor: 'pointer' }}>
            <X size={20} />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} style={{ padding: '1.5rem' }}>
          {error && (
            <div style={{
              background: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              padding: '0.75rem 1rem',
              borderRadius: 'var(--radius-sm)',
              color: '#EF4444',
              fontSize: '0.85rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              marginBottom: '1.25rem'
            }}>
              <AlertCircle size={18} />
              <span>{error}</span>
            </div>
          )}

          {type === 'universidad' && (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Código RUCT *</label>
                  <input
                    type="text"
                    name="codigo"
                    value={formData.codigo || ''}
                    onChange={handleChange}
                    disabled={isEdit}
                    required
                    placeholder="089"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)', background: isEdit ? 'var(--bg-main)' : 'var(--bg-card)' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Nombre Universidad *</label>
                  <input
                    type="text"
                    name="nombre"
                    value={formData.nombre || ''}
                    onChange={handleChange}
                    required
                    placeholder="Universidad de Cádiz"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Tipo</label>
                  <select
                    name="tipo"
                    value={formData.tipo || 'Pública'}
                    onChange={handleChange}
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  >
                    <option value="Pública">Pública</option>
                    <option value="Privada">Privada</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Comunidad Autónoma</label>
                  <input
                    type="text"
                    name="comunidad_autonoma"
                    value={formData.comunidad_autonoma || ''}
                    onChange={handleChange}
                    placeholder="Comunidad de Andalucía"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Municipio</label>
                  <input
                    type="text"
                    name="municipio"
                    value={formData.municipio || ''}
                    onChange={handleChange}
                    placeholder="Cádiz"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Provincia</label>
                  <input
                    type="text"
                    name="provincia"
                    value={formData.provincia || ''}
                    onChange={handleChange}
                    placeholder="Cádiz"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Sitio Web</label>
                  <input
                    type="text"
                    name="web"
                    value={formData.web || ''}
                    onChange={handleChange}
                    placeholder="www.uca.es"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Email Contacto</label>
                  <input
                    type="email"
                    name="email"
                    value={formData.email || ''}
                    onChange={handleChange}
                    placeholder="info@uca.es"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  />
                </div>
              </div>

              <div style={{ background: 'var(--bg-main)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <input
                  type="checkbox"
                  id="gestionado_por_admin"
                  name="gestionado_por_admin"
                  checked={formData.gestionado_por_admin || false}
                  onChange={handleChange}
                  style={{ width: '1.25rem', height: '1.25rem', cursor: 'pointer' }}
                />
                <label htmlFor="gestionado_por_admin" style={{ fontSize: '0.88rem', fontWeight: 600, cursor: 'pointer' }}>
                  Proteger Centro (No sobrescribir por ETL Automático)
                </label>
              </div>
            </>
          )}

          {type === 'titulacion' && (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Código Estudio *</label>
                  <input
                    type="text"
                    name="codigo_estudio"
                    value={formData.codigo_estudio || ''}
                    onChange={handleChange}
                    disabled={isEdit}
                    required
                    placeholder="2500123"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)', background: isEdit ? 'var(--bg-main)' : 'var(--bg-card)' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Título Oficial *</label>
                  <input
                    type="text"
                    name="titulo"
                    value={formData.titulo || ''}
                    onChange={handleChange}
                    required
                    placeholder="Grado en Ingeniería Informática"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Nivel Académico</label>
                  <select
                    name="nivel_academico"
                    value={formData.nivel_academico || 'Grado - RD 822/2021 (2)'}
                    onChange={handleChange}
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  >
                    <option value="Grado - RD 822/2021 (2)">Grado - RD 822/2021</option>
                    <option value="Máster Universitario - RD 822/2021 (2)">Máster Universitario - RD 822/2021</option>
                    <option value="Doctorado - RD 99/2011">Doctorado - RD 99/2011</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Cód. Universidad *</label>
                  <input
                    type="text"
                    name="universidad_codigo"
                    value={formData.universidad_codigo || ''}
                    onChange={handleChange}
                    required
                    placeholder="005"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Estado</label>
                <input
                  type="text"
                  name="estado"
                  value={formData.estado || 'Publicado en B.O.E.'}
                  onChange={handleChange}
                  placeholder="Publicado en B.O.E."
                  style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Precio Crédito (1ª Matrícula)</label>
                  <input
                    type="number"
                    step="0.01"
                    name="precio_credito_ects"
                    value={formData.precio_credito_ects || ''}
                    onChange={handleChange}
                    placeholder="12.62"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Precio 2ª Matrícula</label>
                  <input
                    type="number"
                    step="0.01"
                    name="precio_credito_2"
                    value={formData.precio_credito_2 || ''}
                    onChange={handleChange}
                    placeholder="25.24"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Precio 3ª Matrícula</label>
                  <input
                    type="number"
                    step="0.01"
                    name="precio_credito_3"
                    value={formData.precio_credito_3 || ''}
                    onChange={handleChange}
                    placeholder="54.27"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Precio 4ª Matrícula</label>
                  <input
                    type="number"
                    step="0.01"
                    name="precio_credito_4"
                    value={formData.precio_credito_4 || ''}
                    onChange={handleChange}
                    placeholder="74.72"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  />
                </div>
              </div>

              <div style={{ background: 'var(--bg-main)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <input
                  type="checkbox"
                  id="gestionado_por_admin_tit"
                  name="gestionado_por_admin"
                  checked={formData.gestionado_por_admin || false}
                  onChange={handleChange}
                  style={{ width: '1.25rem', height: '1.25rem', cursor: 'pointer' }}
                />
                <label htmlFor="gestionado_por_admin_tit" style={{ fontSize: '0.88rem', fontWeight: 600, cursor: 'pointer' }}>
                  Proteger Titulación (No sobrescribir por ETL Automático)
                </label>
              </div>
            </>
          )}

          {type === 'asignatura' && (
            <>
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Nombre de la Asignatura *</label>
                <input
                  type="text"
                  name="nombre_elemento"
                  value={formData.nombre_elemento || ''}
                  onChange={handleChange}
                  required
                  placeholder="Ej. Cálculo Diferencial e Integral"
                  style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Créditos ECTS</label>
                  <input
                    type="text"
                    name="creditos_ects"
                    value={formData.creditos_ects || '6'}
                    onChange={handleChange}
                    placeholder="6"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Carácter</label>
                  <select
                    name="caracter"
                    value={formData.caracter || 'OB'}
                    onChange={handleChange}
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  >
                    <option value="FB">Formación Básica (FB)</option>
                    <option value="OB">Obligatoria (OB)</option>
                    <option value="OP">Optativa (OP)</option>
                    <option value="PE">Prácticas Externas (PE)</option>
                    <option value="TFG">Trabajo Fin Grado (TFG)</option>
                    <option value="TFM">Trabajo Fin Máster (TFM)</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Curso</label>
                  <select
                    name="curso"
                    value={formData.curso || '1'}
                    onChange={handleChange}
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  >
                    <option value="1">1º Curso</option>
                    <option value="2">2º Curso</option>
                    <option value="3">3º Curso</option>
                    <option value="4">4º Curso</option>
                    <option value="5">5º Curso</option>
                    <option value="6">6º Curso</option>
                  </select>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Cuatrimestre</label>
                  <select
                    name="cuatrimestre"
                    value={formData.cuatrimestre || '1C'}
                    onChange={handleChange}
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  >
                    <option value="1C">Primer Cuatrimestre (1C)</option>
                    <option value="2C">Segundo Cuatrimestre (2C)</option>
                    <option value="Anual">Anual</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Materia</label>
                  <input
                    type="text"
                    name="materia"
                    value={formData.materia || ''}
                    onChange={handleChange}
                    placeholder="Ej. Matemáticas"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: '1.5rem' }}>
                <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Módulo o Mención Curricular</label>
                <input
                  type="text"
                  name="modulo"
                  value={formData.modulo || ''}
                  onChange={handleChange}
                  placeholder="Ej. Mención en Inteligencia Artificial"
                  style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                />
              </div>
            </>
          )}

          {/* Form Actions */}
          <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', paddingTop: '1rem', borderTop: '1px solid var(--border-light)' }}>
            <button type="button" className="btn btn-outline" onClick={onClose}>
              Cancelar
            </button>
            <button type="submit" className="btn btn-primary">
              <Save size={16} /> Guardar Cambios
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
