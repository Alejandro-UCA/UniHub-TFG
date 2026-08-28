import perfTracker from '../analytics/perfTracker';

// La API se publica tras el mismo origen mediante Nginx. Un fallback relativo
// evita llamar al localhost del visitante si falta la variable de compilación.
export const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';
let adminApiKey = null;

export const setAdminApiKey = (apiKey) => {
  adminApiKey = apiKey || null;
};

export const clearAdminApiKey = () => {
  adminApiKey = null;
};

export const hasAdminSession = () => Boolean(adminApiKey);

const combineAbortSignals = (callerSignal, timeoutSignal) => {
  if (!callerSignal) return { signal: timeoutSignal, cleanup: () => {} };
  if (typeof AbortSignal !== 'undefined' && typeof AbortSignal.any === 'function') {
    return { signal: AbortSignal.any([callerSignal, timeoutSignal]), cleanup: () => {} };
  }

  const combinedController = new AbortController();
  const abortCombined = (event) => combinedController.abort(event?.target?.reason);
  callerSignal.addEventListener('abort', abortCombined, { once: true });
  timeoutSignal.addEventListener('abort', abortCombined, { once: true });
  if (callerSignal.aborted) combinedController.abort(callerSignal.reason);

  return {
    signal: combinedController.signal,
    cleanup: () => {
      callerSignal.removeEventListener('abort', abortCombined);
      timeoutSignal.removeEventListener('abort', abortCombined);
    }
  };
};

const sleep = (ms) => new Promise(res => setTimeout(res, ms));

async function fetchAPI(endpoint, options = {}, retryCount = 0) {
  const url = `${API_BASE_URL}${endpoint}`;
  const startTime = performance.now();
  const MAX_RETRIES = 3;
  const BASE_DELAY = 300;
  const { admin: requiresAdminAuth = false, returnWithTotal = false, timeoutMs = 15000, ...requestOptions } = options;
  const method = (requestOptions.method || 'GET').toUpperCase();
  const canRetry = ['GET', 'HEAD', 'OPTIONS'].includes(method);
  let timeoutId = null;
  let cleanupSignal = () => {};

  try {
    const currentAdminApiKey = requiresAdminAuth ? adminApiKey : null;
    const headers = {
      'Content-Type': 'application/json',
      ...(currentAdminApiKey ? { 'X-API-Key': currentAdminApiKey } : {}),
      ...requestOptions.headers,
    };

    const timeoutController = new AbortController();
    timeoutId = setTimeout(() => timeoutController.abort(), timeoutMs);
    const combinedSignals = combineAbortSignals(requestOptions.signal, timeoutController.signal);
    cleanupSignal = combinedSignals.cleanup;

    const response = await fetch(url, {
      ...requestOptions,
      headers,
      signal: combinedSignals.signal,
    });

    if (timeoutId) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }

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
      if (isRetryable && canRetry && retryCount < MAX_RETRIES) {
        await sleep(BASE_DELAY * Math.pow(2, retryCount));
        return fetchAPI(endpoint, options, retryCount + 1);
      }
      throw new Error(errorMsg || `Error API (${response.status}): ${response.statusText}`);
    }

    const data = await response.json();
    
    if (returnWithTotal) {
      const totalCount = parseInt(response.headers.get('X-Total-Count') || '0', 10);
      return { data, totalCount };
    }
    
    return data;
  } catch (error) {
    if (error.name === 'AbortError') {
      throw error;
    }
    const elapsed = performance.now() - startTime;
    perfTracker.recordAPILatency(endpoint, elapsed, true);
    const isRetryable = error.name === 'TypeError' || error.message.includes('Failed to fetch') || error.message.includes('network');
    if (isRetryable && canRetry && retryCount < MAX_RETRIES) {
      await sleep(BASE_DELAY * Math.pow(2, retryCount));
      return fetchAPI(endpoint, options, retryCount + 1);
    }
    console.warn(`API call error for ${endpoint}:`, error.message);
    throw error;
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
    cleanupSignal();
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

  async getAllUniversities(params = {}, options = {}) {
    const pageSize = 500;
    const firstPage = await this.getUniversities({ ...params, skip: 0, limit: pageSize }, { ...options, returnWithTotal: true });
    const universities = firstPage.data || [];
    const total = firstPage.totalCount || universities.length;
    for (let skip = universities.length; skip < total; skip += pageSize) {
      const page = await this.getUniversities({ ...params, skip, limit: pageSize }, options);
      universities.push(...(page || []));
    }
    return universities;
  },

  async getUniversityByCode(codigo, options = {}) {
    return fetchAPI(`/universidades/${encodeURIComponent(codigo)}`, options);
  },

  async getUniversityDegrees(codigo, params = {}, options = {}) {
    const query = new URLSearchParams();
    if (params.skip !== undefined && params.skip !== null) query.append('skip', String(params.skip));
    if (params.limit !== undefined && params.limit !== null) query.append('limit', String(params.limit));
    const queryString = query.toString() ? `?${query.toString()}` : '';
    return fetchAPI(`/universidades/${encodeURIComponent(codigo)}/titulaciones${queryString}`, options);
  },

  // Universities CRUD (Admin)
  async createUniversity(data, options = {}) {
    return fetchAPI('/universidades', {
      ...options,
      admin: true,
      method: 'POST',
      body: JSON.stringify(data)
    });
  },

  async updateUniversity(codigo, data, options = {}) {
    return fetchAPI(`/universidades/${encodeURIComponent(codigo)}`, {
      ...options,
      admin: true,
      method: 'PUT',
      body: JSON.stringify(data)
    });
  },

  async deleteUniversity(codigo, options = {}) {
    return fetchAPI(`/universidades/${encodeURIComponent(codigo)}`, {
      ...options,
      admin: true,
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

  async getAllDegrees(params = {}, options = {}) {
    const pageSize = 500;
    const firstPage = await this.getDegrees({ ...params, skip: 0, limit: pageSize }, { ...options, returnWithTotal: true });
    const degrees = firstPage.data || [];
    const total = firstPage.totalCount || degrees.length;
    for (let skip = degrees.length; skip < total; skip += pageSize) {
      const page = await this.getDegrees({ ...params, skip, limit: pageSize }, options);
      degrees.push(...(page || []));
    }
    return degrees;
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
      admin: true,
      method: 'POST',
      body: JSON.stringify(data)
    });
  },

  async updateDegree(codigoEstudio, data, options = {}) {
    return fetchAPI(`/titulaciones/${encodeURIComponent(codigoEstudio)}`, {
      ...options,
      admin: true,
      method: 'PUT',
      body: JSON.stringify(data)
    });
  },

  async deleteDegree(codigoEstudio, options = {}) {
    return fetchAPI(`/titulaciones/${encodeURIComponent(codigoEstudio)}`, {
      ...options,
      admin: true,
      method: 'DELETE'
    });
  },

  // Subjects CRUD (Admin)
  async getDegreeSubjects(codigoEstudio, params = {}, options = {}) {
    const query = new URLSearchParams();
    if (params.skip !== undefined && params.skip !== null) query.append('skip', String(params.skip));
    if (params.limit !== undefined && params.limit !== null) query.append('limit', String(params.limit));
    const queryString = query.toString() ? `?${query.toString()}` : '';
    return fetchAPI(`/titulaciones/${encodeURIComponent(codigoEstudio)}/asignaturas${queryString}`, options);
  },

  async getAllDegreeSubjects(codigoEstudio, options = {}) {
    const pageSize = 500;
    const firstPage = await this.getDegreeSubjects(codigoEstudio, { skip: 0, limit: pageSize }, { ...options, returnWithTotal: true });
    const subjects = firstPage.data || [];
    const total = firstPage.totalCount || subjects.length;
    for (let skip = subjects.length; skip < total; skip += pageSize) {
      const page = await this.getDegreeSubjects(codigoEstudio, { skip, limit: pageSize }, options);
      subjects.push(...(page || []));
    }
    return subjects;
  },

  async createDegreeSubject(codigoEstudio, data, options = {}) {
    return fetchAPI(`/titulaciones/${encodeURIComponent(codigoEstudio)}/asignaturas`, {
      ...options,
      admin: true,
      method: 'POST',
      body: JSON.stringify(data)
    });
  },

  async updateDegreeSubject(asignaturaId, data, options = {}) {
    return fetchAPI(`/titulaciones/asignaturas/${encodeURIComponent(asignaturaId)}`, {
      ...options,
      admin: true,
      method: 'PUT',
      body: JSON.stringify(data)
    });
  },

  async deleteDegreeSubject(asignaturaId, options = {}) {
    return fetchAPI(`/titulaciones/asignaturas/${encodeURIComponent(asignaturaId)}`, {
      ...options,
      admin: true,
      method: 'DELETE'
    });
  },

  // Crawler Stats, Physical Container Stats & Error Logs
  async getCrawlerStats(options = {}) {
    return fetchAPI('/estadisticas', { ...options, admin: true });
  },

  async getCrawlerErrors(options = {}) {
    return fetchAPI('/errores', { ...options, admin: true });
  },

  async getContainerPhysicalStats(options = {}) {
    return fetchAPI('/estadisticas/contenedores', { ...options, admin: true });
  },

  async getCrawlerCheckpoint(options = {}) {
    return fetchAPI('/crawler/checkpoint', { ...options, admin: true });
  },

  async getCrawlerErrorsLog(options = {}) {
    return fetchAPI('/crawler/errores_json', { ...options, admin: true });
  },

  async getApiDocsInfo(options = {}) {
    return fetchAPI('/api_docs_info', options);
  },

  async getCurriculumCoverage(options = {}) {
    return fetchAPI('/estadisticas/cobertura', { ...options, admin: true });
  },

  async triggerEtlSync(options = {}) {
    return fetchAPI('/etl/sync', {
      ...options,
      admin: true,
      timeoutMs: options.timeoutMs ?? 600000,
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

apiService.setAdminApiKey = setAdminApiKey;
apiService.clearAdminApiKey = clearAdminApiKey;
apiService.hasAdminSession = hasAdminSession;
