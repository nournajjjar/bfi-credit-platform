import axios from 'axios'

const http = axios.create({ baseURL: 'http://localhost:8000' })

http.interceptors.request.use(config => {
  const token = localStorage.getItem('bfi_token')
  if (token) config.headers.Authorization = 'Bearer ' + token
  return config
})

export const api = {

  // ══ RESEARCH ══════════════════════════════════════════════════
  searchCompanies: (q, topN = 8) =>
    http.get('/api/research/search', { params: { q, top_n: topN } })
      .then(r => r.data),

  generateReport: (formData) =>
    http.post('/api/research/generate-report', formData)
      .then(r => r.data),

  generateReportWithPdf: (formData, queryParams = {}) =>
    http.post('/api/research/generate-report-with-pdf', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: queryParams,
    }).then(r => r.data),

  deepResearch: (company_name, gouvernorat = 'Tunisie', label_secteur = '') =>
    http.post('/api/research/deep-research', null, {
      params: { company_name, gouvernorat, label_secteur }
    }).then(r => r.data),

  // ══ JOBS ══════════════════════════════════════════════════════
  listJobs: () =>
    http.get('/api/jobs/').then(r => r.data.jobs || []),

  getJob: (jobId) =>
    http.get(`/api/jobs/${jobId}`).then(r => r.data),

  downloadJobDocx: (jobId) =>
    `http://localhost:8000/api/jobs/${jobId}/download`,

  // ══ REFINEMENT ════════════════════════════════════════════════
  getReports: () =>
    http.get('/api/refinement/reports').then(r => r.data.reports || []),

  getSections: (reportId) =>
    http.get(`/api/refinement/reports/${reportId}/sections`).then(r => r.data),

  refineSection: (reportId, sectionId, instruction, history = []) =>
    http.post(`/api/refinement/reports/${reportId}/sections/${sectionId}/refine`, {
      instruction,
      conversation_history: history
    }).then(r => r.data),

  applyVersion: (reportId, sectionId, version) =>
    http.post(`/api/refinement/reports/${reportId}/sections/${sectionId}/apply/${version}`)
      .then(r => r.data),

  revertSection: (reportId, sectionId) =>
    http.post(`/api/refinement/reports/${reportId}/sections/${sectionId}/revert`)
      .then(r => r.data),

  getHistory: (reportId, sectionId) =>
    http.get(`/api/refinement/reports/${reportId}/sections/${sectionId}/history`)
      .then(r => r.data),

  getPendingChanges: (reportId) =>
    http.get(`/api/refinement/reports/${reportId}/pending-changes`).then(r => r.data),

  generateDocx: (reportId) =>
    http.post(`/api/refinement/reports/${reportId}/generate`).then(r => r.data),

  downloadRefinedDocx: (reportId) =>
    `http://localhost:8000/api/refinement/reports/${reportId}/download`,

  deleteReport: (reportId) =>
    http.delete(`/api/refinement/reports/${reportId}`).then(r => r.data),

  askQuestion: (reportId, question, sectionId = null) =>
    http.post(`/api/refinement/reports/${reportId}/ask`,
      { question, section_id: sectionId }).then(r => r.data),

  // ══ STRESS TEST ═══════════════════════════════════════════════
  stressPrefill: (reportId) =>
    http.get(`/api/stress-test/prefill/${reportId}`).then(r => r.data),

  stressRun: (payload) =>
    http.post('/api/stress-test/run', payload).then(r => r.data),

  stressRecommend: (payload) =>
    http.post('/api/stress-test/recommend', payload).then(r => r.data),

  stressRecommendSaved: (reportId) =>
    http.post(`/api/stress-test/recommend-saved/${reportId}`, {}).then(r => r.data),

  stressSaved: (reportId) =>
    http.get(`/api/stress-test/saved/${reportId}`).then(r => r.data),

  stressOverview: (reportId) =>
    http.get(`/api/stress-test/overview/${reportId}`).then(r => r.data),

  // ══ FORECAST ══════════════════════════════════════════════════
  forecastLoad: (reportId) =>
    http.get(`/api/forecast/load/${reportId}`).then(r => r.data),

  forecastExtractPdf: (formData) =>
    http.post('/api/forecast/extract-pdf', formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data),

  forecastRun: (payload) =>
    http.post('/api/forecast/run', payload).then(r => r.data),
}