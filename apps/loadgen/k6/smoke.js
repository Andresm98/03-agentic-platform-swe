// Humo: una tarea recorre la flota y su estado es consultable.
import { sleep, check } from 'k6';
import http from 'k6/http';
import { submit, GOALS, BASE_URL } from './common.js';

export const options = { vus: 1, iterations: 3, thresholds: { checks: ['rate==1'] } };

export default function () {
  const res = submit(GOALS[0], 2);
  check(res, { 'status 202': (r) => r.status === 202 });
  const id = res.json('task_id');
  let status = '';
  for (let i = 0; i < 60 && status !== 'completed' && status !== 'failed'; i++) {
    sleep(1);
    status = http.get(`${BASE_URL}/tasks/${id}`).json('status');
  }
  check(status, { 'completed': (s) => s === 'completed' });
}
