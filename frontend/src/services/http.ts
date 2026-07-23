import axios from 'axios'

/**
 * Axios instance for the Joule Verne backend API.
 * In dev, requests are proxied by Vite to localhost:8000.
 * In production, same-origin requests go through the ALB.
 */
export const backendHttp = axios.create({
  baseURL: import.meta.env.VITE_BACKEND_URL || '/',
  timeout: 30000,
})
