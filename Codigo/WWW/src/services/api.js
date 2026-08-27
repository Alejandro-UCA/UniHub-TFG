import perfTracker from '../analytics/perfTracker';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const sleep = (ms) => new Promise(res => setTimeout(res, ms));

async function fetchAPI(endpoint, options = {}, retryCount = 0) {
  const url = `${API_BASE_URL}${endpoint}`;
  const startTime = performance.now();
  const MAX_RETRIES = 3;
  const BASE_DELAY = 300;

  try {
    const adminApiKey = typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('adminApiKey') : null;
    const headers = {
      'Content-Type': 'application/json',
      ...(adminApiKey ? { 'X-API-Key': adminApiKey } : {}),
      ...options.headers,
    };

    const controller = options.signal ? null : new AbortController();
    const signal = options.signal || controller?.signal;
    const timeoutId = controller ? setTimeout(() => controller.abort(), 15000) : null;

    const response = await fetch(url, {
      ...options,
      headers,
      signal,
    });

    if (timeoutId) clearTimeout(timeoutId);

    const elapsed = performance.now() - startTime;
    perfTracker.recordAPILatency(endpoint, elapsed);

    if (response.status === 204) {
      return null;
    }

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      let errorMsg = errData.detail;
      
      if (Array.isArray(errorMsg)) {
        errorMsg = errorMsg.map(e => `${e.loc?.join('.') || 'Campo'}: ${e.msg}`).join(' | ');
      }
      
      const isRetryable = response.status >= 500 || response.status === 429;
      if (isRetryable && retryCount < MAX_RETRIES) {
        await sleep(BASE_DELAY * Math.pow(2, retryCount));
        return fetchAPI(endpoint, options, retryCount + 1);
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
    const isRetryable = error.name === 'TypeError' || error.message.includes('Failed to fetch') || error.message.includes('network');
    if (isRetryable && retryCount < MAX_RETRIES) {
      await sleep(BASE_DELAY * Math.pow(2, retryCount));
      return fetchAPI(endpoint, options, retryCount + 1);
    }
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
    if (params.skip !== undefined && params.skip !== null) query.append('skip', String(params.skip));
    if (params.limit !== undefined && params.limit !== null) query.append('limit', String(params.limit));

    const queryString = query.toString() ? `?${query.toString()}` : '';
    return fetchAPI(`/universidades${queryString}`, options);
  },

  async getUniversityByCode(codigo, options = {}) {
    return fetchAPI(`/universidades/${encodeURIComponent(codigo)}`, options);
  },

  async getUniversityDegrees(codigo, options = {}) {
    return fetchAPI(`/universidades/${encodeURIComponent(codigo)}/titulaciones`, options);
  },

  // Universities CRUD (Admin)
  async createUniversity(data, options = {}) {
    return fetchAPI('/universidades', {
      ...options,
      method: 'POST',
      body: JSON.stringify(data)
    });
  },

  async updateUniversity(codigo, data, options = {}) {
    return fetchAPI(`/universidades/${encodeURIComponent(codigo)}`, {
      ...options,
      method: 'PUT',
      body: JSON.stringify(data)
    });
  },

  async deleteUniversity(codigo, options = {}) {
    return fetchAPI(`/universidades/${encodeURIComponent(codigo)}`, {
      ...options,
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
    if (params.rama && params.rama !== 'todas') query.append('rama', params.rama);
    if (params.con_plan !== undefined && params.con_plan !== null) query.append('con_plan', String(params.con_plan));
    if (params.skip !== undefined && params.skip !== null) query.append('skip', String(params.skip));
    if (params.limit !== undefined && params.limit !== null) query.append('limit', String(params.limit));

    const queryString = query.toString() ? `?${query.toString()}` : '';
    return fetchAPI(`/titulaciones${queryString}`, options);
  },

  async getDegreeByCode(codigoEstudio, options = {}) {
    return fetchAPI(`/titulaciones/${encodeURIComponent(codigoEstudio)}`, options);
  },

  async getDegreeCurriculum(codigoEstudio, options = {}) {
    return fetchAPI(`/titulaciones/${encodeURIComponent(codigoEstudio)}/plan-estudios`, options);
  },

  // Degrees CRUD (Admin)
  async createDegree(data, options = {}) {
    return fetchAPI('/titulaciones', {
      ...options,
      method: 'POST',
      body: JSON.stringify(data)
    });
  },

  async updateDegree(codigoEstudio, data, options = {}) {
    return fetchAPI(`/titulaciones/${encodeURIComponent(codigoEstudio)}`, {
      ...options,
      method: 'PUT',
      body: JSON.stringify(data)
    });
  },

  async deleteDegree(codigoEstudio, options = {}) {
    return fetchAPI(`/titulaciones/${encodeURIComponent(codigoEstudio)}`, {
      ...options,
      method: 'DELETE'
    });
  },

  // Subjects CRUD (Admin)
  async getDegreeSubjects(codigoEstudio, options = {}) {
    return fetchAPI(`/titulaciones/${encodeURIComponent(codigoEstudio)}/asignaturas`, options);
  },

  async createDegreeSubject(codigoEstudio, data, options = {}) {
    return fetchAPI(`/titulaciones/${encodeURIComponent(codigoEstudio)}/asignaturas`, {
      ...options,
      method: 'POST',
      body: JSON.stringify(data)
    });
  },

  async updateDegreeSubject(asignaturaId, data, options = {}) {
    return fetchAPI(`/titulaciones/asignaturas/${encodeURIComponent(asignaturaId)}`, {
      ...options,
      method: 'PUT',
      body: JSON.stringify(data)
    });
  },

  async deleteDegreeSubject(asignaturaId, options = {}) {
    return fetchAPI(`/titulaciones/asignaturas/${encodeURIComponent(asignaturaId)}`, {
      ...options,
      method: 'DELETE'
    });
  },

  // Crawler Stats, Physical Container Stats & Error Logs
  async getCrawlerStats(options = {}) {
    return fetchAPI('/estadisticas', options);
  },

  async getCrawlerErrors(options = {}) {
    return fetchAPI('/errores', options);
  },

  async getContainerPhysicalStats(options = {}) {
    return fetchAPI('/estadisticas/contenedores', options);
  },

  async getCrawlerCheckpoint(options = {}) {
    return fetchAPI('/crawler/checkpoint', options);
  },

  async getCrawlerErrorsLog(options = {}) {
    return fetchAPI('/crawler/errores_json', options);
  },

  async getApiDocsInfo(options = {}) {
    return fetchAPI('/api_docs_info', options);
  },

  async getCurriculumCoverage(options = {}) {
    return fetchAPI('/estadisticas/cobertura', options);
  },

  async triggerEtlSync(options = {}) {
    return fetchAPI('/etl/sync', {
      ...options,
      method: 'POST'
    });
  },

  async verifyAdminAuth(apiKey, options = {}) {
    return fetchAPI('/auth/verify', {
      ...options,
      headers: { 'X-API-Key': apiKey, ...options.headers }
    });
  }
};
