
import axios from "axios"
const BASE = "http://127.0.0.1:8000"
export const api = {
  health: () => axios.get(`${BASE}/health`).then(r => r.data),
  stats: () => axios.get(`${BASE}/stats`).then(r => r.data),
  applications: () => axios.get(`${BASE}/applications`).then(r => r.data),
  application: id => axios.get(`${BASE}/applications/${id}`).then(r => r.data),
  auditTrail: id => axios.get(`${BASE}/audit-trail/${id}`).then(r => r.data),
  compliance: id => axios.get(`${BASE}/compliance/${id}`).then(r => r.data),
  complianceTemporal: (id, asOf) => axios.get(`${BASE}/compliance/${id}/temporal?as_of=${asOf}`).then(r => r.data),
  projections: () => axios.get(`${BASE}/projections`).then(r => r.data),
  upcasting: id => axios.get(`${BASE}/upcasting/${id}`).then(r => r.data),
  events: (params) => axios.get(`${BASE}/events`, { params }).then(r => r.data),
  streams: () => axios.get(`${BASE}/streams`).then(r => r.data),
  integrity: id => axios.get(`${BASE}/integrity/${id}`).then(r => r.data),
  mcpTools: () => axios.get(`${BASE}/mcp/tools`).then(r => r.data),
  mcpResources: () => axios.get(`${BASE}/mcp/resources`).then(r => r.data),
  runPipeline: data => axios.post(`${BASE}/pipeline/run`, data).then(r => r.data),
  runGasTown: () => axios.post(`${BASE}/demos/gastown`).then(r => r.data),
  runWhatIf: data => axios.post(`${BASE}/demos/whatif`, data).then(r => r.data),
  runUpcasting: () => axios.post(`${BASE}/demos/upcasting`).then(r => r.data),
  runLiveQuery: data => axios.post(`${BASE}/query`, data).then(r => r.data),
}
