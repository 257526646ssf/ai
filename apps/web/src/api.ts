import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:3000";

export const api = axios.create({
  baseURL: `${API_BASE}/api/v1`,
});

export function setToken(token: string) {
  api.defaults.headers.common.Authorization = `Bearer ${token}`;
}
