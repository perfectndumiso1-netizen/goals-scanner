import { tick } from './core.mjs';

// A Durable Object supplies atomic cross-invocation admission and durable
// dispatch cooldowns; process-local memory or eventually consistent KV cannot.
export class Scheduler {
  constructor(state, env) { this.state = state; this.env = env; }
  async fetch(request) {
    if (request.method !== 'POST') return new Response('Not found', { status: 404 });
    const { scheduledTime } = await request.json();
    const report = await tick({ storage: this.state.storage, env: this.env, scheduledTime });
    return Response.json(report);
  }
}

export default {
  async scheduled(event, env, context) {
    const job = env.SCHEDULER.get(env.SCHEDULER.idFromName('main-timer')).fetch('https://timer.internal/tick', {
      method: 'POST', body: JSON.stringify({ scheduledTime: event.scheduledTime }),
    }).then(response => {
      if (!response.ok) throw new Error('timer_unavailable');
    });
    context.waitUntil(job);
  },
  // No public dispatch API, bearer-header endpoint or URL secret to leak.
  fetch() { return new Response('Not found', { status: 404 }); },
};
