// Comun a todos los escenarios. BASE_URL: orquestador (compose) o NLB (AWS).
import http from 'k6/http';
import { check } from 'k6';

export const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8001';
const PARAMS = { headers: { 'Content-Type': 'application/json' }, tags: { name: 'POST /tasks' } };

export function submit(goal, complexity, extraHeaders) {
  const params = { ...PARAMS, headers: { ...PARAMS.headers, ...(extraHeaders || {}) } };
  const res = http.post(`${BASE_URL}/tasks`, JSON.stringify({ goal, complexity }), params);
  check(res, { 'accepted or shed': (r) => [202, 429, 503].includes(r.status) });
  return res;
}

export const GOALS = [
  'Evalua el autoscaling con KEDA y su coste',
  'Analiza la resiliencia del gateway LLM',
  'Revisa la seguridad de la flota y sus secretos',
];
