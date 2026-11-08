// Pico brusco: backpressure (429/503 con Retry-After) y sin 5xx no controlados.
import { sleep, check } from 'k6';
import http from 'k6/http';
import { submit, GOALS, BASE_URL } from './common.js';

export const options = { stages: [{ duration: '20s', target: 5 }, { duration: '10s', target: 100 }, { duration: '1m', target: 100 }, { duration: '20s', target: 0 }] };

export default function () {
  submit(GOALS[__ITER % GOALS.length], 3);
  sleep(1);
}
