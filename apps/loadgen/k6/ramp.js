// Rampa -> meseta -> caida (escenarios 4 y 5).
import { sleep, check } from 'k6';
import http from 'k6/http';
import { submit, GOALS, BASE_URL } from './common.js';

export const options = { stages: [{ duration: '2m', target: 20 }, { duration: '5m', target: 20 }, { duration: '1m', target: 0 }], thresholds: { http_req_duration: ['p(95)<2000'] } };

export default function () {
  submit(GOALS[__ITER % GOALS.length], 3);
  sleep(1);
}
