class UsageTracker {
  constructor() {
    this.storageKey = 'unihub_web_usage_analytics_v1';
    this.events = this.loadEvents();
  }

  loadEvents() {
    try {
      if (typeof localStorage === 'undefined') throw new Error('localStorage not available');
      const data = localStorage.getItem(this.storageKey);
      return data ? JSON.parse(data) : {
        pageViews: 0,
        searches: [],
        universityViews: {},
        degreeViews: {},
        nearbySearches: 0,
        recentEvents: []
      };
    } catch (e) {
      return {
        pageViews: 0,
        searches: [],
        universityViews: {},
        degreeViews: {},
        nearbySearches: 0,
        recentEvents: []
      };
    }
  }

  // Agregamos el método para podar los mapas
  _pruneViewsMap(viewsMap, maxEntries = 500) {
    const keys = Object.keys(viewsMap);
    if (keys.length <= maxEntries) return viewsMap;
    const sorted = keys.sort((a, b) => viewsMap[b] - viewsMap[a]);
    const pruned = {};
    sorted.slice(0, maxEntries).forEach(k => { pruned[k] = viewsMap[k]; });
    return pruned;
  }

  saveEvents() {
    try {
      if (typeof localStorage === 'undefined') throw new Error('localStorage not available');
      this.events.universityViews = this._pruneViewsMap(this.events.universityViews);
      this.events.degreeViews = this._pruneViewsMap(this.events.degreeViews);
      localStorage.setItem(this.storageKey, JSON.stringify(this.events));
    } catch (e) {
      console.warn('Could not save usage analytics:', e);
    }
  }

  trackPageView(pageName) {
    this.events.pageViews += 1;
    this.addRecentEvent('PAGE_VIEW', { page: pageName });
    this.saveEvents();
  }

  trackSearch(query, category = 'all') {
    if (!query || query.trim().length < 2) return;
    this.events.searches.push({
      term: query.trim(),
      category,
      timestamp: new Date().toISOString()
    });
    if (this.events.searches.length > 200) {
      this.events.searches = this.events.searches.slice(-200);
    }
    this.addRecentEvent('SEARCH', { term: query, category });
    this.saveEvents();
  }

  trackUniversityView(univCode, univName) {
    const key = `${univCode} - ${univName}`;
    this.events.universityViews[key] = (this.events.universityViews[key] || 0) + 1;
    this.addRecentEvent('UNIV_VIEW', { code: univCode, name: univName });
    this.saveEvents();
  }

  trackDegreeView(degreeCode, degreeTitle) {
    const key = `${degreeCode} - ${degreeTitle}`;
    this.events.degreeViews[key] = (this.events.degreeViews[key] || 0) + 1;
    this.addRecentEvent('DEGREE_VIEW', { code: degreeCode, title: degreeTitle });
    this.saveEvents();
  }

  trackNearbySearch(coords) {
    this.events.nearbySearches += 1;
    this.addRecentEvent('GEOLOCATION', { coords });
    this.saveEvents();
  }

  addRecentEvent(type, details) {
    this.events.recentEvents.unshift({
      type,
      details,
      timestamp: new Date().toISOString()
    });
    if (this.events.recentEvents.length > 50) {
      this.events.recentEvents = this.events.recentEvents.slice(0, 50);
    }
  }

  getTopVisitedUniversities(universitiesList, limit = 6) {
    if (!universitiesList || universitiesList.length === 0) return [];
    const sorted = [...universitiesList].sort((a, b) => {
      const countA = this.events.universityViews[`${a.codigo} - ${a.nombre}`] || 0;
      const countB = this.events.universityViews[`${b.codigo} - ${b.nombre}`] || 0;
      return countB - countA;
    });
    return sorted.slice(0, limit);
  }

  getAnalyticsSummary() {
    const termCounts = {};
    this.events.searches.forEach(s => {
      termCounts[s.term] = (termCounts[s.term] || 0) + 1;
    });
    const topSearches = Object.entries(termCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);

    const topUniversities = Object.entries(this.events.universityViews)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);

    const topDegrees = Object.entries(this.events.degreeViews)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);

    const calculatorViews = this.events.recentEvents.filter(e => e.type === 'PAGE_VIEW' && e.details?.page === 'calculadora').length;
    const totalSearchCount = this.events.searches.length;
    const conversionRatioPct = totalSearchCount > 0 ? Math.round((calculatorViews / totalSearchCount) * 10000) / 100 : 0;

    return {
      totalPageViews: this.events.pageViews,
      totalSearches: totalSearchCount,
      totalNearbySearches: this.events.nearbySearches,
      conversionRatioSearchToCalculatorPct: conversionRatioPct,
      topSearches,
      topUniversities,
      topDegrees,
      recentEvents: this.events.recentEvents
    };
  }

  clearAnalytics() {
    this.events = {
      pageViews: 0,
      searches: [],
      universityViews: {},
      degreeViews: {},
      nearbySearches: 0,
      recentEvents: []
    };
    this.saveEvents();
  }
}

const usageTracker = new UsageTracker();
export default usageTracker;
