import React, { useState, useEffect } from 'react';
import { X, Save, AlertCircle, Building, BookOpen } from 'lucide-react';

export default function AdminFormModal({ isOpen, mode, type, initialData, onClose, onSubmit }) {
  const [formData, setFormData] = useState({});
  const [error, setError] = useState('');

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
          telefono: ''
        });
      } else {
        setFormData({
          codigo_estudio: '',
          titulo: '',
          nivel_academico: 'Grado - RD 822/2021 (2)',
          estado: 'Publicado en B.O.E.',
          universidad_codigo: ''
        });
      }
    }
  }, [initialData, type, isOpen]);

  if (!isOpen) return null;

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setError('');

    if (type === 'universidad' && (!formData.codigo || !formData.nombre)) {
      setError('El código y el nombre de la universidad son obligatorios.');
      return;
    }
    if (type === 'titulacion' && (!formData.codigo_estudio || !formData.titulo || !formData.universidad_codigo)) {
      setError('El código de estudio, título y código de universidad son obligatorios.');
      return;
    }

    onSubmit(formData);
  };

  const isEdit = mode === 'edit';

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" style={{ maxWidth: '580px' }} onClick={(e) => e.stopPropagation()}>
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
            {type === 'universidad' ? <Building size={22} color="var(--uca-sun)" /> : <BookOpen size={22} color="var(--uca-azure)" />}
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700 }}>
              {isEdit ? `Editar ${type === 'universidad' ? 'Universidad' : 'Titulación'}` : `Añadir Nueva ${type === 'universidad' ? 'Universidad' : 'Titulación'}`}
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

          {type === 'universidad' ? (
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
            </>
          ) : (
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
                    placeholder="2504059"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)', background: isEdit ? 'var(--bg-main)' : 'var(--bg-card)' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Código Universidad *</label>
                  <input
                    type="text"
                    name="universidad_codigo"
                    value={formData.universidad_codigo || ''}
                    onChange={handleChange}
                    required
                    placeholder="089"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Título Oficial *</label>
                <input
                  type="text"
                  name="titulo"
                  value={formData.titulo || ''}
                  onChange={handleChange}
                  required
                  placeholder="Graduado o Graduada en Ciencia de Datos"
                  style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.3rem' }}>Nivel Académico / Plan</label>
                  <input
                    type="text"
                    name="nivel_academico"
                    value={formData.nivel_academico || ''}
                    onChange={handleChange}
                    placeholder="Grado - RD 822/2021 (2)"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}
                  />
                </div>
                <div>
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
