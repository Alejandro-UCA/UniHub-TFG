import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

export default function Pagination({ currentPage, totalItems, itemsPerPage, onPageChange, onItemsPerPageChange }) {
  const totalPages = Math.ceil(totalItems / itemsPerPage) || 1;
  const startItem = totalItems === 0 ? 0 : (currentPage - 1) * itemsPerPage + 1;
  const endItem = Math.min(currentPage * itemsPerPage, totalItems);

  const pageSizeOptions = [5, 10, 20, 50, 100];

  return (
    <div className="glass-panel" style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      flexWrap: 'wrap',
      gap: '1rem',
      padding: '0.85rem 1.25rem',
      marginTop: '1.75rem'
    }}>
      {/* Items Count Summary */}
      <div style={{ fontSize: '0.88rem', color: 'var(--text-muted)' }}>
        Mostrando <strong style={{ color: 'var(--text-main)' }}>{startItem}-{endItem}</strong> de <strong style={{ color: 'var(--text-main)' }}>{totalItems}</strong> resultados
      </div>

      {/* Page Size Selector */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.88rem' }}>
        <span style={{ color: 'var(--text-muted)' }}>Mostrar por página:</span>
        <select 
          value={itemsPerPage} 
          onChange={(e) => {
            onItemsPerPageChange(Number(e.target.value));
            onPageChange(1);
          }}
          className="form-control"
          style={{ padding: '0.35rem 0.6rem', fontSize: '0.88rem', borderRadius: '8px', width: 'auto' }}
        >
          {pageSizeOptions.map(size => (
            <option key={size} value={size}>{size}</option>
          ))}
        </select>
      </div>

      {/* Navigation Buttons */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
        <button
          className="btn btn-outline"
          style={{ padding: '0.4rem 0.65rem', borderRadius: '8px', fontSize: '0.85rem' }}
          disabled={currentPage === 1}
          onClick={() => onPageChange(currentPage - 1)}
        >
          <ChevronLeft size={16} /> Anterior
        </button>

        <span style={{ padding: '0 0.5rem', fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-main)' }}>
          Página {currentPage} de {totalPages}
        </span>

        <button
          className="btn btn-outline"
          style={{ padding: '0.4rem 0.65rem', borderRadius: '8px', fontSize: '0.85rem' }}
          disabled={currentPage >= totalPages}
          onClick={() => onPageChange(currentPage + 1)}
        >
          Siguiente <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}
