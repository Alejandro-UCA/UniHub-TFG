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

    if (response.status === 204) {
      return null;
    }

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || `Error API (${response.status}): ${response.statusText}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    const elapsed = performance.now() - startTime;
    perfTracker.recordAPILatency(endpoint, elapsed, true);
    console.warn(`API call error for ${endpoint}:`, error.message);
    throw error;
  }
}

export const apiService = {
  // Universities GET
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

  // Universities CRUD (Admin)
  async createUniversity(data) {
    return fetchAPI('/universidades', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  },

  async updateUniversity(codigo, data) {
    return fetchAPI(`/universidades/${codigo}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  },

  async deleteUniversity(codigo) {
    return fetchAPI(`/universidades/${codigo}`, {
      method: 'DELETE'
    });
  },

  // Degrees GET
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

  // Degrees CRUD (Admin)
  async createDegree(data) {
    return fetchAPI('/titulaciones', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  },

  async updateDegree(codigoEstudio, data) {
    return fetchAPI(`/titulaciones/${codigoEstudio}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  },

  async deleteDegree(codigoEstudio) {
    return fetchAPI(`/titulaciones/${codigoEstudio}`, {
      method: 'DELETE'
    });
  },

  // Crawler Stats & Error Logs
  async getCrawlerStats() {
    return fetchAPI('/estadisticas');
  },

  async getCrawlerErrors() {
    return fetchAPI('/errores');
  }
};
