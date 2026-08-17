import perfTracker from '../analytics/perfTracker';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

async function fetchAPI(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const startTime = performance.now();
  
  try {
    const adminApiKey = sessionStorage.getItem('adminApiKey');
    const headers = {
      'Content-Type': 'application/json',
      ...(adminApiKey ? { 'X-API-Key': adminApiKey } : {}),
      ...options.headers,
    };

    const response = await fetch(url, {
      ...options,
      headers,
    });

    const elapsed = performance.now() - startTime;
    perfTracker.recordAPILatency(endpoint, elapsed);

    if (response.status === 204) {
      return null;
    }

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      let errorMsg = errData.detail;
      
      // Manejar formato de errores de validación de FastAPI (Pydantic) que devuelven un Array
      if (Array.isArray(errorMsg)) {
        errorMsg = errorMsg.map(e => `${e.loc?.join('.') || 'Campo'}: ${e.msg}`).join(' | ');
      }
      
      throw new Error(errorMsg || `Error API (${response.status}): ${response.statusText}`);
    }

    const data = await response.json();
    
    if (options.returnWithTotal) {
      const totalCount = parseInt(response.headers.get('X-Total-Count') || '0', 10);
      return { data, totalCount };
    }
    
    return data;
  } catch (error) {
    if (error.name === 'AbortError') {
      return null;
    }
    const elapsed = performance.now() - startTime;
    perfTracker.recordAPILatency(endpoint, elapsed, true);
    console.warn(`API call error for ${endpoint}:`, error.message);
    throw error;
  }
}

export const apiService = {
  // Universities GET
  async getUniversities(params = {}, options = {}) {
    const query = new URLSearchParams();
    if (params.tipo && params.tipo !== 'todos') query.append('tipo', params.tipo);
    if (params.ccaa && params.ccaa !== 'todas') query.append('ccaa', params.ccaa);
    if (params.nombre) query.append('nombre', params.nombre);
    if (params.skip !== undefined) query.append('skip', params.skip);
    if (params.limit !== undefined) query.append('limit', params.limit);

    const queryString = query.toString() ? `?${query.toString()}` : '';
    return fetchAPI(`/universidades${queryString}`, options);
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
  async getDegrees(params = {}, options = {}) {
    const query = new URLSearchParams();
    if (params.titulo) query.append('titulo', params.titulo);
    if (params.nivel_academico && params.nivel_academico !== 'todos') query.append('nivel_academico', params.nivel_academico);
    if (params.universidad_codigo) query.append('universidad_codigo', params.universidad_codigo);
    if (params.ccaa && params.ccaa !== 'todas') query.append('ccaa', params.ccaa);
    if (params.tipo_universidad && params.tipo_universidad !== 'todos') query.append('tipo_universidad', params.tipo_universidad);
    if (params.con_plan !== undefined && params.con_plan !== null) query.append('con_plan', params.con_plan);
    if (params.skip !== undefined) query.append('skip', params.skip);
    if (params.limit !== undefined) query.append('limit', params.limit);

    const queryString = query.toString() ? `?${query.toString()}` : '';
    return fetchAPI(`/titulaciones${queryString}`, options);
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

  // Crawler Stats, Physical Container Stats & Error Logs
  async getCrawlerStats() {
    return fetchAPI('/estadisticas');
  },

  async getCrawlerErrors() {
    return fetchAPI('/errores');
  },

  async getContainerPhysicalStats() {
    return fetchAPI('/estadisticas/contenedores');
  },

  async getCrawlerCheckpoint() {
    return fetchAPI('/crawler/checkpoint');
  },

  async getCrawlerErrorsLog() {
    return fetchAPI('/crawler/errores_json');
  },

  async getApiDocsInfo() {
    return fetchAPI('/api_docs_info');
  },

  async getCurriculumCoverage() {
    return fetchAPI('/estadisticas/cobertura');
  },

  async triggerEtlSync() {
    return fetchAPI('/etl/sync', {
      method: 'POST'
    });
  },

  async verifyAdminAuth(apiKey) {
    return fetchAPI('/auth/verify', {
      headers: { 'X-API-Key': apiKey }
    });
  }
};
