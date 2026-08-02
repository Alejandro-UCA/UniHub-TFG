// Geographic coordinates (lat, lng) for Spanish provincial capitals and university hubs
export const SPANISH_CITIES_COORDS = {
  "cadiz": { lat: 36.5271, lng: -6.2886, province: "Cádiz", name: "Cádiz (UCA)" },
  "madrid": { lat: 40.4168, lng: -3.7038, province: "Madrid", name: "Madrid" },
  "barcelona": { lat: 41.3851, lng: 2.1734, province: "Barcelona", name: "Barcelona" },
  "sevilla": { lat: 37.3891, lng: -5.9845, province: "Sevilla", name: "Sevilla" },
  "valencia": { lat: 39.4699, lng: -0.3763, province: "Valencia", name: "Valencia" },
  "zaragoza": { lat: 41.6488, lng: -0.8896, province: "Zaragoza", name: "Zaragoza" },
  "malaga": { lat: 36.7213, lng: -4.4214, province: "Málaga", name: "Málaga" },
  "granada": { lat: 37.1773, lng: -3.5986, province: "Granada", name: "Granada" },
  "cordoba": { lat: 37.8882, lng: -4.7794, province: "Córdoba", name: "Córdoba" },
  "santiago": { lat: 42.8782, lng: -8.5448, province: "A Coruña", name: "Santiago de Compostela" },
  "salamanca": { lat: 40.9701, lng: -5.6635, province: "Salamanca", name: "Salamanca" },
  "bilbao": { lat: 43.2630, lng: -2.9350, province: "Bizkaia", name: "Bilbao" },
  "valladolid": { lat: 41.6523, lng: -4.7245, province: "Valladolid", name: "Valladolid" },
  "alicante": { lat: 38.3452, lng: -0.4815, province: "Alicante", name: "Alicante" },
  "murcia": { lat: 37.9922, lng: -1.1307, province: "Murcia", name: "Murcia" },
  "oviedo": { lat: 43.3619, lng: -5.8494, province: "Asturias", name: "Oviedo" },
  "santander": { lat: 43.4623, lng: -3.8099, province: "Cantabria", name: "Santander" },
  "palma": { lat: 39.5696, lng: 2.6502, province: "Illes Balears", name: "Palma de Mallorca" },
  "laspalmas": { lat: 28.1235, lng: -15.4363, province: "Las Palmas", name: "Las Palmas de Gran Canaria" }
};

/**
 * Calculates the great-circle distance between two points on the Earth
 * using the Haversine formula (in Kilometers).
 */
export function calculateHaversineDistance(lat1, lon1, lat2, lon2) {
  const R = 6371; // Radius of the Earth in km
  const dLat = (lat2 - lat1) * (Math.PI / 180);
  const dLon = (lon2 - lon1) * (Math.PI / 180);
  
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(lat1 * (Math.PI / 180)) *
      Math.cos(lat2 * (Math.PI / 180)) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
      
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  const distance = R * c;
  
  return Math.round(distance * 10) / 10; // Round to 1 decimal place
}

/**
 * Resolves or estimates coordinates for a university based on its province/municipality or name.
 */
export function getUniversityCoords(univ) {
  const text = `${univ.nombre} ${univ.municipio} ${univ.provincia} ${univ.comunidad_autonoma}`.toLowerCase();
  
  for (const [key, city] of Object.entries(SPANISH_CITIES_COORDS)) {
    if (text.includes(key) || text.includes(city.province.toLowerCase())) {
      return city;
    }
  }
  
  // Default to Madrid if unknown
  return SPANISH_CITIES_COORDS["madrid"];
}
