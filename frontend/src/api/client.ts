// Axios-based API client for FactLens backend
import axios from 'axios';
import type { Document, Evidence, Fact, Relationship, ProcessingRun, RequiredCase, SystemMetrics } from '../types';

const api = axios.create({
    baseURL: '/api',
    timeout: 60000,
});

// Documents
export const uploadDocument = (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return api.post<Document>('/documents/upload', fd);
};
export const listDocuments = (skip = 0, limit = 50) =>
    api.get<{ items: Document[]; total: number }>('/documents', { params: { skip, limit } });
export const getDocument = (id: string) => api.get<Document>(`/documents/${id}`);
export const triggerProcessing = (id: string) => api.post(`/documents/${id}/process`);
export const getProcessingRuns = (id: string) => api.get<ProcessingRun[]>(`/documents/${id}/runs`);

// Facts
export const listFacts = (params?: {
    skip?: number; limit?: number; status?: string;
    document_id?: string; predicate?: string; min_confidence?: number;
}) => api.get<{ items: Fact[]; total: number }>('/facts', { params });
export const getFact = (id: string) => api.get<Fact>(`/facts/${id}`);
export const getFactEvidence = (id: string) => api.get<Evidence[]>(`/facts/${id}/evidence`);

// Relationships
export const listRelationships = (params?: {
    skip?: number; limit?: number; type?: string; min_confidence?: number;
}) => api.get<{ items: Relationship[]; total: number }>('/relationships', { params });
export const getRelationship = (id: string) => api.get<Relationship>(`/relationships/${id}`);

// Query
export const queryFacts = (query: string, limit = 10) =>
    api.post('/query', { query, limit });

// Cases
export const getCases = () => api.get<{ cases: RequiredCase[]; generated_at: string }>('/cases');

// Metrics & health
export const getMetrics = () => api.get<SystemMetrics>('/metrics');
export const getHealth = () => api.get('/health');

export default api;
