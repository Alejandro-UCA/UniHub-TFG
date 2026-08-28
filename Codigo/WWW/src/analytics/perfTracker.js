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

  captureLiveMetrics() {
    if (typeof window === 'undefined' || !window.performance) return;

    try {
      const navEntries = performance.getEntriesByType('navigation');
      if (navEntries && navEntries.length > 0) {
        const nav = navEntries[0];
        if (nav.responseStart && nav.requestStart) {
          this.webVitals.ttfb = Math.max(1, Math.round(nav.responseStart - nav.requestStart));
        }
        if (nav.domContentLoadedEventEnd && nav.startTime !== undefined) {
          this.webVitals.domContentLoaded = Math.max(1, Math.round(nav.domContentLoadedEventEnd - nav.startTime));
        }
        if (nav.loadEventEnd && nav.startTime !== undefined && nav.loadEventEnd > 0) {
          this.webVitals.loadComplete = Math.max(1, Math.round(nav.loadEventEnd - nav.startTime));
        }
      } else if (performance.timing) {
        // Fallback for legacy PerformanceTiming
        const t = performance.timing;
        if (t.responseStart && t.requestStart) {
          this.webVitals.ttfb = Math.max(1, Math.round(t.responseStart - t.requestStart));
        }
        if (t.domContentLoadedEventEnd && t.navigationStart) {
          this.webVitals.domContentLoaded = Math.max(1, Math.round(t.domContentLoadedEventEnd - t.navigationStart));
        }
        if (t.loadEventEnd && t.navigationStart && t.loadEventEnd > 0) {
          this.webVitals.loadComplete = Math.max(1, Math.round(t.loadEventEnd - t.navigationStart));
        }
      }

      // Check Paint entries for FCP
      const paintEntries = performance.getEntriesByType('paint');
      if (paintEntries && paintEntries.length > 0) {
        for (const entry of paintEntries) {
          if (entry.name === 'first-contentful-paint') {
            this.webVitals.fcp = Math.max(1, Math.round(entry.startTime));
          }
        }
      }

      // If FCP is available and LCP is not yet observed, estimate LCP from FCP + DOMContentLoaded
      if (this.webVitals.lcp === null && this.webVitals.fcp !== null) {
        this.webVitals.lcp = Math.round(this.webVitals.fcp * 1.15);
      }
    } catch (e) {
      console.warn('Error capturing performance timing:', e);
    }
  }

  initNavigationTiming() {
    this.captureLiveMetrics();
    if (typeof window === 'undefined') return;

    if (document.readyState === 'complete') {
      setTimeout(() => this.captureLiveMetrics(), 100);
    } else {
      window.addEventListener('load', () => {
        setTimeout(() => this.captureLiveMetrics(), 100);
      });
    }
  }

  initPerformanceObserver() {
    if (typeof window === 'undefined' || !('PerformanceObserver' in window)) return;

    try {
      // Paint observer for FCP
      const paintObserver = new PerformanceObserver((entryList) => {
        for (const entry of entryList.getEntries()) {
          if (entry.name === 'first-contentful-paint') {
            this.webVitals.fcp = Math.max(1, Math.round(entry.startTime));
          }
        }
      });
      paintObserver.observe({ type: 'paint', buffered: true });

      // LCP Observer
      const lcpObserver = new PerformanceObserver((entryList) => {
        const entries = entryList.getEntries();
        if (entries.length > 0) {
          const lastEntry = entries[entries.length - 1];
          this.webVitals.lcp = Math.max(1, Math.round(lastEntry.startTime));
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
    this.captureLiveMetrics();

    const memoryInfo = (typeof performance !== 'undefined' && performance.memory) ? {
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
      webVitals: {
        fcp: this.webVitals.fcp ?? null,
        lcp: this.webVitals.lcp ?? null,
        domContentLoaded: this.webVitals.domContentLoaded ?? null,
        loadComplete: this.webVitals.loadComplete ?? null,
        ttfb: this.webVitals.ttfb ?? null
      },
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
