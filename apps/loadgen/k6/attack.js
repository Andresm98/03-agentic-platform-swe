// Abuso (escenario 13): token falso, rafagas y payloads grandes. Nunca debe gastar tokens live.
import { sleep, check } from 'k6';
import http from 'k6/http';
import { submit, GOALS, BASE_URL } from './common.js';

export const options = { scenarios: { burst: { executor: 'constant-arrival-rate', rate: 200, timeUnit: '1s', duration: '1m', preAllocatedVUs: 100, maxVUs: 300 } } };

export default function () {
  const n = __ITER % 3;
  if (n === 0) {
    submit('intento de modo live', 3, { 'X-Demo-Token': 'token-falso-' + __ITER });
  } else if (n === 1) {
    const big = 'x'.repeat(200000);
    const res = http.post(`${BASE_URL}/tasks`, JSON.stringify({ goal: big }), { headers: { 'Content-Type': 'application/json' } });
    check(res, { 'payload grande rechazado': (r) => [413, 422, 429].includes(r.status) });
  } else {
    const res = http.post(`${BASE_URL}/tasks`, JSON.stringify({ goal: 'x', mode: 'live' }), { headers: { 'Content-Type': 'application/json' } });
    check(res, { 'campo mode rechazado': (r) => [422, 429].includes(r.status) });
  }
}
