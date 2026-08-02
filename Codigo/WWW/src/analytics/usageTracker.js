class UsageTracker {
  constructor() {
    this.storageKey = 'ruct_web_usage_analytics_v1';
    this.events = this.loadEvents();
  }

  loadEvents() {
    try {
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

  saveEvents() {
    try {
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
    // Keep max 200 search logs
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

  getAnalyticsSummary() {
    // Calculate top search terms
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

    return {
      totalPageViews: this.events.pageViews,
      totalSearches: this.events.searches.length,
      totalNearbySearches: this.events.nearbySearches,
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
