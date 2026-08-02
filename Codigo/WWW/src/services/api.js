import perfTracker from '../analytics/perfTracker';

const API_BASE_URL = 'http://localhost:8000/api/v1';

async function fetchAPI(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const startTime = performance.now();
  
  try {
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    });

    const elapsed = performance.now() - startTime;
    perfTracker.recordAPILatency(endpoint, elapsed);

    if (!response.ok) {
      throw new Error(`Error API (${response.status}): ${response.statusText}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    const elapsed = performance.now() - startTime;
    perfTracker.recordAPILatency(endpoint, elapsed, true);
    console.warn(`Fallback local data mode active for ${endpoint}:`, error.message);
    throw error;
  }
}

export const apiService = {
  // Universities
  async getUniversities(params = {}) {
    const query = new URLSearchParams();
    if (params.tipo) query.append('tipo', params.tipo);
    if (params.ccaa) query.append('cccaa', params.ccaa);
    if (params.nombre) query.append('nombre', params.nombre);
    if (params.skip) query.append('skip', params.skip);
    if (params.limit) query.append('limit', params.limit || 100);

    const queryString = query.toString() ? `?${query.toString()}` : '';
    return fetchAPI(`/universidades${queryString}`);
  },

  async getUniversityByCode(codigo) {
    return fetchAPI(`/universidades/${codigo}`);
  },

  async getUniversityDegrees(codigo) {
    return fetchAPI(`/universidades/${codigo}/titulaciones`);
  },

  // Degrees
  async getDegrees(params = {}) {
    const query = new URLSearchParams();
    if (params.titulo) query.append('titulo', params.titulo);
    if (params.nivel_academico) query.append('nivel_academico', params.nivel_academico);
    if (params.universidad_codigo) query.append('universidad_codigo', params.universidad_codigo);
    if (params.skip) query.append('skip', params.skip);
    if (params.limit) query.append('limit', params.limit || 100);

    const queryString = query.toString() ? `?${query.toString()}` : '';
    return fetchAPI(`/titulaciones${queryString}`);
  },

  async getDegreeByCode(codigoEstudio) {
    return fetchAPI(`/titulaciones/${codigoEstudio}`);
  },

  async getDegreeCurriculum(codigoEstudio) {
    return fetchAPI(`/titulaciones/${codigoEstudio}/plan-estudios`);
  },

  // Crawler Stats & Error Logs
  async getCrawlerStats() {
    return fetchAPI('/estadisticas');
  },

  async getCrawlerErrors() {
    return fetchAPI('/errores');
  }
};
