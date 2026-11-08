// Carga sostenida moderada para detectar fugas.
import { sleep, check } from 'k6';
import http from 'k6/http';
import { submit, GOALS, BASE_URL } from './common.js';

export const options = { vus: 10, duration: __ENV.DURATION || '30m' };

export default function () {
  submit(GOALS[__ITER % GOALS.length], 3);
  sleep(1);
}
