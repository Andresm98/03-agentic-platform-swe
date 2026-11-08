// Carga constante mientras se inyectan fallos (escenario 14); registra cada task_id.
import { sleep, check } from 'k6';
import http from 'k6/http';
import { submit, GOALS, BASE_URL } from './common.js';

export const options = { vus: 10, duration: __ENV.DURATION || '3m' };

export default function () {
  const res = submit(GOALS[__ITER % GOALS.length], 2);
  if (res.status === 202) {
    console.log(`TASK ${res.json('task_id')}`);
  }
  sleep(1);
}
