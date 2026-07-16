import axios from 'axios';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_URL,
});

export const uploadGPX = (file, chauffeurId) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('chauffeur_id', chauffeurId);
  return api.post('/api/v1/collecte/gpx/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

export const getTrace = (traceId) => api.get(`/api/v1/traces/${traceId}`);

export const getEdges = (status = '') => api.get('/api/v1/map/edges', { params: { status } });

export const searchPlaces = (q) => api.get('/api/v1/places/search', { params: { q } });

export const scrapeCity = (city) => api.post('/api/v1/places/scrape', null, { params: { city } });

export const validateDrone = (payload) => api.post('/api/v1/drone/validate', payload);
