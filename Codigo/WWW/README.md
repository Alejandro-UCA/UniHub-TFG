# UniHub Web — Portal Web Interactivo y Calculadora (Fase 3)

**UniHub Web** es una Single Page Application (SPA) construida con **React 19** y **Vite 8** que proporciona acceso interactivo al catálogo oficial de educación superior en España, estimación financiera de matrícula, geolocalización de campus y panel de control administrativo.

---

## 🚀 Características Principales

1. **Buscador Vocacional y Filtros Avanzados**:
   - Búsqueda en tiempo real por titulación, universidad, comunidad autónoma, provincia, tipo de centro (público/privado) y **Rama de Conocimiento** (*Ciencias Sociales y Jurídicas, Ingeniería y Arquitectura, Ciencias de la Salud, Artes y Humanidades, Ciencias*).
   - Enrutamiento SPA sincronizado con la **History API** del navegador (`popstate` / `pushState`) para navegación fluida y soporte de botones atrás/adelante.

2. **Visualizador Curricular Oficial ([`PlanModal.jsx`](file:///d:/Proyecto/Codigo/WWW/src/components/PlanModal.jsx))**:
   - Desglose interactivo de planes de estudio organizados por curso académico y cuatrimestre (`1C`, `2C`, `Anual`).
   - Resaltado visual de **Menciones Curriculares e Itinerarios Oficiales** (`[Mención en...]`).
   - Tarjeta interactiva para programas de doctorado bajo el **RD 99/2011**: badge oficial verificado, Escuela de Doctorado responsable, cuadrícula de líneas de investigación científica acreditadas, actividades formativas transversales, régimen de dedicación y tutela académica anual.

3. **Simulador Financiero "Calcula tu Matrícula" ([`TuitionCalculator.jsx`](file:///d:/Proyecto/Codigo/WWW/src/components/TuitionCalculator.jsx))**:
   - Estimación basada en las tarifas disponibles, con indicación de fuente y sin inventar valores ausentes.
   - Multiplicadores por repetición de asignatura ($1.0\times, 1.5\times, 3.0\times, 4.5\times$).
   - Sistema completo de exenciones y bonificaciones sociales: **Beca MEC**, **Familia Numerosa**, **Discapacidad $\ge 33\%$**, **Bonificación 99\% CCAA** y **Matrículas de Honor**.

4. **Geolocalización y Cercanía ([`Geolocation.jsx`](file:///d:/Proyecto/Codigo/WWW/src/components/Geolocation.jsx))**:
   - Cálculo de distancias mediante fórmula Haversine a más de 50 capitales y ciudades españolas o mediante GPS del navegador.

5. **Banner Interactivo de Estado de Conexión**:
   - Detección automática en tiempo real de caídas del backend o pérdida de conectividad, con alerta visual y botón de reintento inmediato.

6. **Panel de Control Administrativo ([`AdminDashboard.jsx`](file:///d:/Proyecto/Codigo/WWW/src/components/AdminDashboard.jsx))**:
   - Acceso asegurado mediante token `X-API-Key`.
   - Exportación masiva CSV (con UTF-8 BOM y desinfección anti CSV Injection) y JSON.
   - Semáforos Core Web Vitals (LCP, FID, CLS), telemetría de recursos Docker cgroup (RAM RSS / CPU %) y monitor de sincronización ETL en vivo.

---

## 🛠️ Stack Tecnológico

- **Framework**: React 19
- **Bundler & Dev Server**: Vite 8
- **Linter & Análisis Estático**: Oxlint
- **Iconografía**: Lucide React
- **Estilos**: CSS3 moderno con variables corporativas de la Universidad de Cádiz (UCA), diseño *glassmorphism* y scrollbars estándar multiplataforma.
- **Servidor Web Producción**: Nginx 1.25-alpine (Dockerizado multi-etapa).

---

## 📦 Scripts Disponibles

```bash
# Instalar dependencias
npm install

# Iniciar servidor de desarrollo local (HMR)
npm run dev

# Compilar para producción
npm run build

# Previsualizar el build de producción
npm run preview

# Ejecutar análisis de código con Oxlint
npm run lint
```
