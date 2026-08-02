class WebPerformanceTracker {
  constructor() {
    this.apiLatencies = [];
    this.webVitals = {
      fcp: null,
      lcp: null,
      domContentLoaded: null,
      loadComplete: null,
      ttfb: null
    };
    this.initNavigationTiming();
    this.initPerformanceObserver();
  }

  initNavigationTiming() {
    if (typeof window === 'undefined' || !window.performance) return;

    window.addEventListener('load', () => {
      setTimeout(() => {
        const perfEntries = performance.getEntriesByType('navigation');
        if (perfEntries && perfEntries.length > 0) {
          const nav = perfEntries[0];
          this.webVitals.domContentLoaded = Math.round(nav.domContentLoadedEventEnd - nav.startTime);
          this.webVitals.loadComplete = Math.round(nav.loadEventEnd - nav.startTime);
          this.webVitals.ttfb = Math.round(nav.responseStart - nav.requestStart);
        }
      }, 0);
    });
  }

  initPerformanceObserver() {
    if (typeof window === 'undefined' || !('PerformanceObserver' in window)) return;

    try {
      // Paint observer for FCP
      const paintObserver = new PerformanceObserver((entryList) => {
        for (const entry of entryList.getEntries()) {
          if (entry.name === 'first-contentful-paint') {
            this.webVitals.fcp = Math.round(entry.startTime);
          }
        }
      });
      paintObserver.observe({ type: 'paint', buffered: true });

      // LCP Observer
      const lcpObserver = new PerformanceObserver((entryList) => {
        const entries = entryList.getEntries();
        if (entries.length > 0) {
          const lastEntry = entries[entries.length - 1];
          this.webVitals.lcp = Math.round(lastEntry.startTime);
        }
      });
      lcpObserver.observe({ type: 'largest-contentful-paint', buffered: true });
    } catch (e) {
      console.warn('PerformanceObserver not supported in browser:', e);
    }
  }

  recordAPILatency(endpoint, latencyMs, isError = false) {
    this.apiLatencies.push({
      endpoint,
      latencyMs: Math.round(latencyMs),
      isError,
      timestamp: new Date().toISOString()
    });

    if (this.apiLatencies.length > 100) {
      this.apiLatencies = this.apiLatencies.slice(-100);
    }
  }

  getPerformanceReport() {
    const memoryInfo = (performance && performance.memory) ? {
      usedJSHeapMB: Math.round(performance.memory.usedJSHeapSize / (1024 * 1024) * 100) / 100,
      totalJSHeapMB: Math.round(performance.memory.totalJSHeapSize / (1024 * 1024) * 100) / 100,
      jsHeapLimitMB: Math.round(performance.memory.jsHeapSizeLimit / (1024 * 1024) * 100) / 100
    } : null;

    const totalRequests = this.apiLatencies.length;
    const avgAPILatency = totalRequests > 0
      ? Math.round(this.apiLatencies.reduce((sum, item) => sum + item.latencyMs, 0) / totalRequests)
      : 0;

    const errorRequests = this.apiLatencies.filter(i => i.isError).length;

    return {
      webVitals: this.webVitals,
      memory: memoryInfo,
      apiStats: {
        totalRequests,
        avgAPILatencyMs: avgAPILatency,
        errorRatePercent: totalRequests > 0 ? Math.round((errorRequests / totalRequests) * 100) : 0,
        recentRequests: this.apiLatencies.slice(-15)
      }
    };
  }
}

const perfTracker = new WebPerformanceTracker();
export default perfTracker;
